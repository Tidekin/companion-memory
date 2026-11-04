"""Offline evidence-chain diagnosis of a frozen round: where did each answer's facts get lost?

Stages per question and arm (no model calls; reads frozen artifacts only):
  executed      the exam reached a terminal SUCCEEDED answer
  sources_read  every source turn was perceived (media read, native turn completed)
  extracted     a long-term memory cites a source event (Core arms only)
  in_prompt     every source reached the answering prompt (text, media text or event ID)
  answered      graded pass (after review overrides)
A failure is attributed to the first stage that broke.
Usage: python -I diagnose_evidence.py <round_dir>
"""

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ARMS = ("old", "new", "rag")
STAGES = ("executed", "sources_read", "in_prompt", "answered")


def read(path):
    return [json.loads(s) for s in Path(path).read_text("utf-8").splitlines() if s.strip()]


def snippet(text, size=14):
    text = "".join((text or "").split())
    return text[:size] if len(text) >= 6 else None


def present(source, prompt):
    keys = [source.get("event_id"), snippet(source.get("text")),
            snippet(source.get("observed_text")), snippet(source.get("native_reply"), 10)
            if source.get("modality") not in ("text", "assistant") else None]
    compact = "".join(prompt.split())
    return any(key and key in compact for key in keys)


def core_arm(root, arm, questions):
    out = {}
    for persona_dir in sorted((root / "arms" / arm / "results").glob("[A-Z][0-9][0-9]")):
        turns = {r["id"]: r for r in read(persona_dir / "turns-observed.jsonl")}
        answers = {r["id"]: r for r in read(persona_dir / "answers.jsonl")}
        prompts = defaultdict(str)
        for row in read(persona_dir / "requests.jsonl"):
            if row.get("phase") == "exam" and row.get("case"):
                prompts[row["case"]] += json.dumps(row["payload"].get("messages", []),
                                                   ensure_ascii=False)
        db = sqlite3.connect(f"file:{persona_dir / 'core.sqlite3'}?mode=ro", uri=True)
        # Text turns carry no event ID in the log: match the owner event by its logical time.
        by_time = {at[:19]: event_id for event_id, at in db.execute(
            "SELECT event_id,occurred_at FROM events WHERE actor_id='owner'")}
        for turn in turns.values():
            if not turn.get("event_id"):
                at = datetime.fromisoformat(turn["now"]).astimezone(UTC).isoformat()[:19]
                turn["event_id"] = by_time.get(at)
        evidence = defaultdict(list)
        for event_id, created in db.execute(
                "SELECT me.event_id,m.created_at FROM memory_evidence me "
                "JOIN memories m USING(memory_id)"):
            evidence[event_id].append(created)
        for qid, answer in answers.items():
            q = questions[qid]
            sources = [turns[s] for s in q["source_ids"]]
            out[qid] = {
                "executed": answer["status"] == "SUCCEEDED",
                "sources_read": all(_read_ok(s) for s in sources),
                "extracted": any(evidence.get(s["event_id"]) for s in sources),
                "in_prompt": all(present(s, prompts[qid]) for s in sources),
                "sources_in_prompt": sum(present(s, prompts[qid]) for s in sources),
                "sources": len(sources)}
    return out


def _read_ok(source):
    state = (source.get("native_state") or {}).get("state", "SUCCEEDED")
    return state == "SUCCEEDED" and not source.get("media_error")


def rag_arm(root, questions):
    old_turns = {}
    for persona_dir in (root / "arms/old/results").glob("[A-Z][0-9][0-9]"):
        old_turns.update({r["id"]: r for r in read(persona_dir / "turns-observed.jsonl")})
    out = {}
    for answer in read(root / "rag/answers.jsonl"):
        q = questions[answer["id"]]
        seen = set(answer.get("retrieved_turns") or []) | set(answer.get("recent_turns") or [])
        sources = [old_turns[s] for s in q["source_ids"]]
        hit = sum(s["turn"] in seen for s in sources)
        out[answer["id"]] = {"executed": answer["status"] == "SUCCEEDED",
                             "sources_read": all(_read_ok(s) for s in sources),
                             "extracted": None, "in_prompt": hit == len(sources),
                             "sources_in_prompt": hit, "sources": len(sources)}
    return out


def main(root):
    root = Path(root)
    questions = {q["id"]: q for q in read(root / "bank/suite-v1/questions.jsonl")}
    results = {r["id"]: r for r in json.loads((root / "results.json").read_text("utf-8"))}
    arms = {"old": core_arm(root, "old", questions), "new": core_arm(root, "new", questions),
            "rag": rag_arm(root, questions)}
    rows, summary = [], {}
    for arm, stages in arms.items():
        lost = Counter()
        by_category = defaultdict(Counter)
        for qid, item in stages.items():
            item["answered"] = results[qid]["arms"][arm]["passed"]
            first = "passed" if item["answered"] else next(
                (stage for stage in STAGES if not item[stage]), "passed")
            # A wrong answer with every source in the prompt is a reading/answering failure.
            lost[first] += 1
            by_category[questions[qid]["category_id"]][first] += 1
            rows.append({"id": qid, "arm": arm, "category_id": questions[qid]["category_id"],
                         "delay_days": questions[qid]["delay_days"], "first_loss": first,
                         **item})
        evidence_ok = [item for item in stages.values() if item["executed"] and item["in_prompt"]]
        summary[arm] = {
            "first_loss": dict(lost),
            "executed_rate": sum(i["executed"] for i in stages.values()) / len(stages),
            "sources_read_rate": sum(i["sources_read"] for i in stages.values()) / len(stages),
            "extraction_coverage": (sum(bool(i["extracted"]) for i in stages.values())
                                    / len(stages)) if arm != "rag" else None,
            "full_evidence_in_prompt_rate": sum(i["in_prompt"] for i in stages.values())
            / len(stages),
            "pass_rate_given_full_evidence": (sum(i["answered"] for i in evidence_ok)
                                              / len(evidence_ok)) if evidence_ok else None,
            # Detector check: passing answers whose sources the text/ID matcher missed.
            "passed_but_evidence_not_detected": sum(
                i["answered"] and not i["in_prompt"] for i in stages.values()),
            "by_category": {k: dict(v) for k, v in sorted(by_category.items())}}
    (root / "evidence-diagnosis.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
    lines = ["| 环节 | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for key, label in (("executed_rate", "执行成功"), ("sources_read_rate", "来源都读到"),
                       ("extraction_coverage", "抽取覆盖"),
                       ("full_evidence_in_prompt_rate", "证据全部进prompt"),
                       ("pass_rate_given_full_evidence", "证据齐全时通过")):
        lines.append(f"| {label} | " + " | ".join(
            "—" if summary[a][key] is None else f"{summary[a][key]:.1%}" for a in ARMS) + " |")
    lines.append("| 通过但未检测到证据(匹配器漏检) | " + " | ".join(
        str(summary[a]["passed_but_evidence_not_detected"]) for a in ARMS) + " |")
    lines += ["", "| 首个断点 | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for stage in (*STAGES, "passed"):
        lines.append(f"| {stage} | " + " | ".join(
            str(summary[a]["first_loss"].get(stage, 0)) for a in ARMS) + " |")
    lines += ["", "| 考点 | 证据未进prompt(old/new/rag) | 证据齐全仍答错(old/new/rag) |", "|---|---|---|"]
    for cid in sorted({r["category_id"] for r in rows}):
        lines.append(f"| {cid} | " + "/".join(str(summary[a]["by_category"].get(cid, {})
                                                    .get("in_prompt", 0)) for a in ARMS)
                     + " | " + "/".join(str(summary[a]["by_category"].get(cid, {})
                                            .get("answered", 0)) for a in ARMS) + " |")
    (root / "evidence-diagnosis.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
