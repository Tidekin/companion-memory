"""Resume the Qwen RAG reference after the DeepSeek inference cap stopped it.

Attempted-but-unanswered questions (cancelled when the cap error stopped the gather) are
closed as FAILED and never replayed. Only never-attempted questions run. The DeepSeek cap
is raised to this round's remainder: round-3 cap 49 (smoke counted separately, at most 1).
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx

import run_rag
from run_rag import OUT, ROOT, SUITE, Calls, append, read, save

TOTAL_CNY, INFERENCE_CNY = 49, 47


async def main():
    manifest = json.loads((OUT / "manifest.json").read_text("utf-8"))
    assert manifest["status"] == "NEEDS_ATTENTION" and "CNY_CAP" in manifest.get("error", "")
    questions = {q["id"]: q for q in read(SUITE / "questions.jsonl")}
    answered = {a["id"] for a in read(OUT / "answers.jsonl")}
    attempted = {r["label"] for r in read(OUT / "requests.jsonl") if r["label"] in questions}
    for qid in sorted(attempted - answered):
        append(OUT / "answers.jsonl", {**questions[qid], "status": "FAILED", "answer": "",
               "infrastructure_error": True, "error": "CANCELLED_WHEN_CAP_STOPPED_RUN",
               "elapsed_seconds": None, "retrieved_turns": [], "recent_turns": []})
    manifest["resumes"] = manifest.get("resumes", []) + [{
        "at": datetime.now(timezone.utc).isoformat(), "closed_as_failed": sorted(attempted - answered),
        "deepseek_total_cny": TOTAL_CNY, "deepseek_inference_cny": INFERENCE_CNY}]
    manifest["status"] = "RUNNING"
    save(OUT / "manifest.json", manifest)
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False, follow_redirects=False) as client:
            calls = Calls(client)
            calls.deep.total_cny, calls.deep.inference_cny = TOTAL_CNY, INFERENCE_CNY
            await asyncio.gather(*(run_rag.persona(calls, f"S{i:02}") for i in range(1, 6)))
        answers = read(OUT / "answers.jsonl")
        assert len(answers) == len({a["id"] for a in answers}) == 480
        manifest["status"] = "COMPLETED"
    except BaseException as error:
        manifest.update(status="NEEDS_ATTENTION", error_type=type(error).__name__,
                        error=str(error)[:600])
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(OUT / "manifest.json", manifest)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
