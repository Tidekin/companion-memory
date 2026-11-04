"""Offline, model-free timing of Core's recall stages against frozen round-3 databases.

Copies each persona's new-arm core.sqlite3, then at growing history points times:
history read (6 turns), turn-recall candidate read, ranking (BM25 + embeddings + rerank,
cold and warm), and memory search; finally runs five personas' rankings concurrently, as
the harness does, to expose waiting on the shared model locks. No provider calls.
Usage: python profile_recall.py <core_source_dir> <out_dir>
"""

import asyncio
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, sys.argv[1])

from companion import turn_recall  # noqa: E402
from companion.config import Settings  # noqa: E402
from companion.dialogue_history import recent_sent_sources  # noqa: E402
from companion.memory import Memory  # noqa: E402
from companion.privacy import ErasureLedger  # noqa: E402
from companion.store import Store  # noqa: E402

POINTS = (50, 100, 150, 200, 250, 300, 350)
QUESTION_IDS = ("R24", "R05", "R13")


def settings(directory):
    return Settings(database=str(directory / "core.sqlite3"),
                    erasure_ledger=str(directory / "erasures.jsonl"),
                    embedding_cache_dir="LOCAL_PATH Core/data/embedding-cache",
                    model_key="offline-profile", bridge_token="x" * 32,
                    owner_qq_id="10001", bot_qq_id="10002", memory_enabled=True,
                    max_recent_messages=12)


def ms(start):
    return round((time.perf_counter() - start) * 1000, 1)


def owner_events(store):
    return [row for row in store.rows(
        "SELECT e.event_id,e.conversation_id,e.occurred_at FROM events e "
        "WHERE e.actor_id='owner' AND e.redacted=0 AND e.source='qq.onebot' "
        "AND EXISTS (SELECT 1 FROM outbox o WHERE o.origin_event_id=e.event_id "
        "AND o.state='SENT') ORDER BY e.rowid")]


def persona_queries(persona):
    questions = [json.loads(s) for s in (ROOT / "bank/suite-v1/questions.jsonl")
                 .read_text("utf-8").splitlines()]
    return [next(q["question"] for q in questions if q["persona"] == persona
                 and q["category_id"] == cid) for cid in QUESTION_IDS]


def profile(persona, work):
    directory = work / persona
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "arms/new/results" / persona / "core.sqlite3", directory / "core.sqlite3")
    shutil.copy2(ROOT / "arms/new/results" / persona / "erasures.jsonl", directory / "erasures.jsonl")
    cfg = settings(directory)
    store = Store(cfg.database)
    memory = Memory(store, cfg, ErasureLedger(cfg.erasure_ledger))
    events, queries, rows = owner_events(store), persona_queries(persona), []
    for point in POINTS:
        if point > len(events):
            break
        event = events[point - 1]
        job = {"conversation_id": event["conversation_id"], "event_id": event["event_id"]}
        for query in queries:
            start = time.perf_counter()
            recent_sent_sources(store, job["conversation_id"], job["event_id"], 6)
            history = ms(start)
            start = time.perf_counter()
            candidates, notes = turn_recall._candidates(store, cfg, job)
            docs = [turn_recall._document(r, n, cfg.timezone)
                    for r, n in zip(candidates, notes, strict=True)]
            read = ms(start)
            start = time.perf_counter()
            turn_recall.lexical(query, docs)
            lexical = ms(start)
            start = time.perf_counter()
            turn_recall.semantic(cfg, query, docs)
            embed = ms(start)
            start = time.perf_counter()
            turn_recall.select(cfg, query, docs, turn_recall.CANDIDATES)
            rank = ms(start)
            start = time.perf_counter()
            memory.search(query, limit=12, now=event["occurred_at"])
            search = ms(start)
            rows.append({"persona": persona, "history_turns": point, "candidates": len(docs),
                         "history_read_ms": history, "candidate_read_ms": read,
                         "bm25_ms": lexical, "embed_ms": embed, "rank_total_ms": rank,
                         "memory_search_ms": search})
    store.close()
    return rows


async def concurrent(personas, work, point=300):
    """Five personas ranking at once in one process, like the benchmark worker."""
    stores, jobs = [], []
    for persona in personas:
        cfg = settings(work / persona)
        store = Store(cfg.database)
        events = owner_events(store)
        event = events[min(point, len(events)) - 1]
        stores.append(store)
        jobs.append((store, cfg, {"conversation_id": event["conversation_id"],
                                  "event_id": event["event_id"]},
                     persona_queries(persona)[0]))

    async def one(store, cfg, job, query):
        start = time.perf_counter()
        await turn_recall.prefetch(store, cfg, job, query)
        return ms(start)

    alone = [await one(*job) for job in jobs]
    together = await asyncio.gather(*(one(*job) for job in jobs))
    for store in stores:
        store.close()
    return {"history_turns": point, "alone_ms": alone, "concurrent_ms": list(together)}


def main():
    out = Path(sys.argv[2])
    work = out / "db"
    personas = sorted(p.name for p in (ROOT / "arms/new/results").glob("S0*"))
    rows = []
    for persona in personas:
        rows += profile(persona, work)
        print("profiled", persona, flush=True)
    contention = asyncio.run(concurrent(personas, work))
    table = {}
    for row in rows:
        table.setdefault(row["history_turns"], []).append(row)
    keys = ("candidates", "history_read_ms", "candidate_read_ms", "bm25_ms", "embed_ms",
            "rank_total_ms", "memory_search_ms")
    summary = {point: {key: round(statistics.median(r[key] for r in items), 1) for key in keys}
               for point, items in sorted(table.items())}
    result = {"note": "medians over personas x 3 queries; first call per persona includes "
                      "embedding cold start; memory search sees the end-state memory table",
              "by_history": summary, "contention": contention, "rows": rows}
    (out / "recall-profile.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                             "utf-8")
    print(json.dumps({"by_history": summary, "contention": contention}, ensure_ascii=False,
                     indent=1))


if __name__ == "__main__":
    main()
