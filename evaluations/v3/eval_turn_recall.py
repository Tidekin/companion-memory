"""Offline Recall@8 of raw-turn recall under candidate-pool and reranker settings.

Model-free with respect to DeepSeek: only local BM25, embeddings and ONNX rerankers run.
For each round-3 question (delays >= 3 days, whose sources usually fall outside the six
recent turns), candidates are the delivered turns up to the question's cutoff minus the
six recent ones, as in production. A question counts as recalled when every source turn
outside the recent window is among the eight turns finally selected.
Usage: python eval_turn_recall.py <core_source_dir> <out_dir>
"""

import json
import shutil
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, sys.argv[1])

from companion import reranker, turn_recall  # noqa: E402
from companion.config import Settings  # noqa: E402
from companion.dialogue_history import recent_sent_sources  # noqa: E402
from companion.memory_references import replay_many  # noqa: E402
from companion.store import Store  # noqa: E402

CACHE = Path("LOCAL_PATH Core/data/embedding-cache")
MODELS = {"m3-int8": CACHE / "local-bge-reranker-v2-m3-int8",
          "base-int8": CACHE / "local-bge-reranker-base-int8", "none": None}
POOLS = (12, 8)
LIMIT = 8


def read(path):
    return [json.loads(s) for s in Path(path).read_text("utf-8").splitlines() if s.strip()]


def fused(query, docs, settings):
    from collections import Counter

    scores = Counter()
    for ranking in (turn_recall._ranked(turn_recall.lexical(query, docs)),
                    turn_recall._ranked(turn_recall.semantic(settings, query, docs))):
        for rank, index in enumerate(ranking, 1):
            scores[index] += 1 / (60 + rank)
    return [index for index, _ in scores.most_common()]


def main():
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    questions = [q for q in read(ROOT / "bank/suite-v1/questions.jsonl") if q["delay_days"] >= 3]
    rows, timing = [], {name: [] for name in MODELS}
    for persona in sorted({q["persona"] for q in questions}):
        work = out / "db" / persona
        work.mkdir(parents=True, exist_ok=True)
        for name in ("core.sqlite3", "erasures.jsonl"):
            shutil.copy2(ROOT / "arms/new/results" / persona / name, work / name)
        settings = Settings(database=str(work / "core.sqlite3"),
                            erasure_ledger=str(work / "erasures.jsonl"),
                            embedding_cache_dir=str(CACHE), model_key="offline", bridge_token="x" * 32,
                            owner_qq_id="10001", bot_qq_id="10002", reranker_model_dir="")
        store = Store(settings.database)
        events = store.rows("SELECT event_id,conversation_id,occurred_at,rowid FROM events "
                            "WHERE actor_id='owner' AND source='qq.onebot' AND redacted=0")
        by_time = {row["occurred_at"][:19]: row for row in events}
        turns = {r["id"]: r for r in read(ROOT / f"bank/suite-v1/inputs/{persona}.jsonl")}
        order = sorted(turns.values(), key=lambda r: r["turn"])

        def event_of(turn):
            at = datetime.fromisoformat(turn["now"]).astimezone(UTC).isoformat()[:19]
            return by_time.get(at)

        for q in [q for q in questions if q["persona"] == persona]:
            last = next(e for t in reversed(order[:q["cutoff_turn"]]) if (e := event_of(t)))
            candidates = recent_sent_sources(store, last["conversation_id"], None, 600,
                                             cutoff_rowid=last["rowid"])
            recent = {row["event_id"] for row in candidates[-6:]}
            candidates = [row for row in candidates if row["event_id"] not in recent]
            notes = replay_many(store, [row["event_id"] for row in candidates])
            docs = [turn_recall._document(row, notes[row["event_id"]], settings.timezone)
                    for row in candidates]
            wanted = {event_of(turns[s])["event_id"] for s in q["source_ids"]
                      if event_of(turns[s])} - recent
            if not wanted or not docs:
                continue
            ids = [row["event_id"] for row in candidates]
            order_fused = fused(q["question"], docs, settings)
            result = {"id": q["id"], "category_id": q["category_id"], "delay": q["delay_days"],
                      "sources_outside_recent": len(wanted), "candidates": len(docs)}
            for name, path in MODELS.items():
                pool = order_fused[:max(POOLS)]
                if path is None:
                    scores = None
                else:
                    start = time.perf_counter()
                    values = reranker.scores(str(path), q["question"],
                                             [docs[i][:turn_recall.RERANK_CHARS] for i in pool])
                    timing[name].append((time.perf_counter() - start) * 1000)
                    scores = dict(zip(pool, values, strict=True))
                for size in POOLS:
                    subset = pool[:size]
                    if scores is not None:
                        subset = sorted(subset, key=lambda i: -scores[i])
                    chosen = {ids[i] for i in subset[:LIMIT]}
                    result[f"{name}@pool{size}"] = wanted <= chosen
                    result[f"{name}@pool{size}_any"] = bool(wanted & chosen)
                    if name == "m3-int8":
                        floored = [i for i in subset if scores[i] >= turn_recall.RERANK_FLOOR]
                        result[f"{name}@pool{size}+floor"] = wanted <= {ids[i] for i in
                                                                        floored[:LIMIT]}
            rows.append(result)
        store.close()
        print("evaluated", persona, flush=True)
    keys = [k for k in rows[0] if "@" in k]
    summary = {k: round(sum(r[k] for r in rows) / len(rows), 4) for k in keys}
    summary["questions"] = len(rows)
    summary["rerank_ms_median"] = {k: round(statistics.median(v), 1) for k, v in timing.items() if v}
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category_id"], {"n": 0})
        c["n"] += 1
        for k in ("m3-int8@pool12+floor", "m3-int8@pool8", "base-int8@pool12", "base-int8@pool8",
                  "none@pool12"):
            c[k] = c.get(k, 0) + r[k]
    (out / "turn-recall-eval.json").write_text(json.dumps(
        {"summary": summary, "by_category": by_cat, "rows": rows}, ensure_ascii=False, indent=1),
        "utf-8")
    print(json.dumps({"summary": summary, "by_category": by_cat}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
