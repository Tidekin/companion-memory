"""The post-RAG tail of run_campaign.py, run after the RAG resume: freeze all answers."""

import json
from datetime import datetime, timezone

from run_campaign import Budget, ROOT, read, save, sha, state, validate_run

configs = {a: validate_run(ROOT / "arms" / a) for a in ("old", "new")}
assert json.loads((ROOT / "rag/manifest.json").read_text("utf-8"))["status"] == "COMPLETED"
rag_answers = read(ROOT / "rag/answers.jsonl")
assert len(rag_answers) == len({a["id"] for a in rag_answers}) == 480
assert {a["id"] for a in rag_answers} == set(configs["old"]["selected_ids"])
assert all(a["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"} for a in rag_answers)
held, latest = Budget.from_context(configs["old"]).snapshot()
assert held <= 49 and not any(v["state"] == "RESERVED" for v in latest.values())
rag_errors = {r["id"]: r for r in read(ROOT / "rag/errors.jsonl")}
for row in latest.values():
    if row["state"] == "UNKNOWN" and row["phase"].startswith("inference:rag:"):
        assert rag_errors[row["id"]]["local_await_finished"] is True
q_records = {}
for row in read(ROOT / "qwen-usage.jsonl"):
    q_records.setdefault(row["id"], {}).update(row)
assert sum(v["charged_or_held_cny"] for v in q_records.values()) <= 50
assert not any(v["state"] == "RESERVED" for v in q_records.values())
files = [p for a in configs for p in (ROOT / "arms" / a / "results").glob("*/answers.jsonl")]
files.append(ROOT / "rag/answers.jsonl")
save(ROOT / "all-answers-frozen.json", {
    "status": "ALL1440_ANSWERS_CLOSED_BEFORE_GOLD_READ",
    "files_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in files},
    "corpus_freeze_sha256": sha(ROOT / "corpus-freeze.json"),
    "charged_or_held_cny": held, "failures_kept_in_denominator": True,
    "rag_resumed_after_cap": True, "at": datetime.now(timezone.utc).isoformat()})
state("READY_FOR_BLIND_GRADING", answers_per_arm=480, deepseek_charged_or_held_cny=held)
print("frozen", held)
