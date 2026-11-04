"""Post-freeze version-blind judging. Reuse frozen rubric, budget and no-replay contract."""
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from filelock import FileLock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runner"))
from scripts.memory_benchmark.budget import Budget, MeteredTransport
from scripts.memory_benchmark.cli import validate_run
from scripts.memory_benchmark.rubric import RULES, normalize_grade
from scripts.memory_benchmark.runtime import credential

OUT = ROOT / "grading"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(s) for s in path.read_text("utf-8").splitlines()] if path.exists() else []


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def state(status, **details):
    save(ROOT / "pipeline-status.json", dict(status=status, at=datetime.now(UTC).isoformat(),
                                          pid=os.getpid(), **details))


def validate_coverage(questions, arms):
    ids = {q["id"] for q in questions}
    assert len(questions) == len(ids) == 576
    for arm, rows in arms.items():
        assert len(rows) == len({a["id"] for a in rows}) == len(ids), arm
        assert {a["id"] for a in rows} == ids, arm
        assert all(a["status"] in ("SUCCEEDED", "FAILED", "CANCELLED") for a in rows), arm


def parse_response(response, lookup):
    assert response["status"] == 200, "Saved judge HTTP failure; never replay it"
    content = response["response"]["choices"][0]["message"]["content"]
    parsed = json.loads(content)["grades"]
    keys = response["keys"]
    # Explicitly reviewed offline key transcription fixes, never score changes or HTTP retries.
    for fix in read(OUT / "key-transcription-corrections.jsonl"):
        if fix["batch_id"] != response.get("batch_id"):
            continue
        assert fix["response_sha256"] == hashlib.sha256(json.dumps(response, ensure_ascii=False).encode()).hexdigest()
        assert fix["correct_key"] in keys and fix["returned_key"] not in keys
        assert sum(r["key"] == fix["returned_key"] for r in parsed) == 1
        for row in parsed:
            if row["key"] == fix["returned_key"]:
                row["returned_key"] = row["key"]
                row["key"] = fix["correct_key"]
                row["key_transcription_corrected"] = True
    assert len(parsed) == len({r["key"] for r in parsed}) == len(keys)
    assert {r["key"] for r in parsed} == set(keys)
    return [normalize_grade(r, lookup[r["key"]]) for r in parsed]


def unresolved_requests(requests, responses):
    resolved = {r["batch_id"] for r in responses}
    return [r["batch_id"] for r in requests if r["batch_id"] not in resolved]


def prepare():
    OUT.mkdir(exist_ok=True)
    frozen = json.loads((ROOT / "all-answers-frozen.json").read_text("utf-8"))
    assert frozen["status"] == "ALL1728_ANSWERS_CLOSED_BEFORE_GOLD_READ"
    for name, digest in frozen["files_sha256"].items():
        assert sha(ROOT / name) == digest, name
    assert sha(ROOT / "corpus-freeze.json") == frozen["corpus_freeze_sha256"]
    configs = {a: validate_run(ROOT / "arms" / a) for a in ("old", "new")}
    execution = json.loads((ROOT / "execution-freeze.json").read_text("utf-8"))
    for name, digest in execution["files_sha256"].items():
        assert sha(ROOT / name) == digest, name
    bank = ROOT / "bank/suite-v1"
    questions = read(bank / "questions.jsonl")
    arms = {a: [r for p in sorted((ROOT / "arms" / a / "results").glob("*/answers.jsonl"))
                for r in read(p)] for a in ("old", "new")}
    arms["rag"] = read(ROOT / "rag/answers.jsonl")
    validate_coverage(questions, arms)
    budget = Budget.from_context(configs["old"])
    cost, latest = budget.snapshot()
    assert cost < 50 and not any(r["state"] == "RESERVED" for r in latest.values())
    assert all(r["state"] != "UNKNOWN" or r["phase"].startswith("inference:")
               for r in latest.values()), "Uncertain judge call cannot be replayed"
    # ONLY here: verified all original answer, source, corpus and execution hashes first.
    criteria = {c["id"]: c for c in read(bank / "review-only/criteria.jsonl")}
    cf = json.loads((ROOT / "corpus-freeze.json").read_text("utf-8"))
    assert sha(bank / "review-only/criteria.jsonl") == cf["criteria_sha256"]
    # source-freeze stores the ORIGINAL SCRIPT hash; the extracted RULES string has its own hash.
    original = ROOT.parent / "memory-benchmark-20261102/grade_suite.py"
    assert sha(original) == json.loads((ROOT / "source-freeze.json").read_text("utf-8"))["original_rules_sha256"]
    assert hashlib.sha256(RULES.encode()).hexdigest() == (
        "b48dafd4ca961f1e3fd9cf533e5ee8d01abcb20a8d2e937a050e3fc63180af7d")
    seed = sha(ROOT / "all-answers-frozen.json")
    qmap = {q["id"]: q for q in questions}
    cases, mapping, failed = [], [], []
    for arm, answers in arms.items():
        for a in answers:
            qid = a["id"]
            key = hashlib.sha256((seed + arm + qid).encode()).hexdigest()[:24]
            mapping.append(dict(key=key, arm=arm, id=qid,
                                answer_sha256=hashlib.sha256(a.get("answer", "").encode()).hexdigest()))
            if a["status"] != "SUCCEEDED" or not a.get("answer", "").strip():
                failed.append(dict(key=key, pass_=False, missing=[], violations=[],
                                   execution_failure=True, status=a["status"], error=a.get("error")))
                failed[-1]["pass"] = failed[-1].pop("pass_")
            else:
                cases.append(dict(key=key, question=qmap[qid]["question"], answer=a["answer"],
                                  required=criteria[qid]["required"], forbidden=criteria[qid]["forbidden"]))
    mapping.sort(key=lambda r: r["key"])
    cases.sort(key=lambda r: r["key"])
    if (OUT / "blind-mapping.json").exists():
        assert json.loads((OUT / "blind-mapping.json").read_text("utf-8")) == mapping
    else:
        save(OUT / "blind-mapping.json", mapping)
        save(OUT / "execution-failures.json", failed)
        save(OUT / "grading-freeze.json", dict(
            script_sha256=sha(Path(__file__)), answers_freeze_sha256=seed,
            rubric_file_sha256=sha(ROOT / "runner/scripts/memory_benchmark/rubric.py"),
            rules_sha256=hashlib.sha256(RULES.encode()).hexdigest(),
            criteria_sha256=cf["criteria_sha256"], at=datetime.now(UTC).isoformat(),
            total=1728, successful_candidates=len(cases), failures=len(failed),
            key_method="SHA256(answer-freezeSHA+arm+qid)[:24], lexicographic permutation",
            arm_and_version_labels_sent_to_judge=False, not_independent_human=True,
            batch_size=8, concurrency=3, max_output_tokens=1536, thinking="disabled"))
    return configs["old"], cases, failed


async def main():
    with FileLock(str(ROOT / "blind-grading.lock"), timeout=0):
        config, cases, failures = prepare()
        lookup = {r["key"]: r for r in cases}

        def recover(response):
            rows = parse_response(response, lookup)
            done = {r["key"] for r in read(OUT / "grades.jsonl")}
            for row in rows:
                if row["key"] not in done:
                    append(OUT / "grades.jsonl", row)
                    done.add(row["key"])

        for response in read(OUT / "responses.jsonl"):
            recover(response)
        pending = unresolved_requests(read(OUT / "requests.jsonl"), read(OUT / "responses.jsonl"))
        assert not pending, "Attempted batch lacks saved response; preserve and inspect: " + str(pending)
        done = {r["key"] for r in read(OUT / "grades.jsonl")}
        for row in failures:
            if row["key"] not in done:
                append(OUT / "grades.jsonl", row)
        rows = [r for r in cases if r["key"] not in done]
        state("BLIND_GRADING", candidates=len(cases), completed=len(done))
        async with httpx.AsyncClient(timeout=120, trust_env=False, follow_redirects=False,
                                    transport=MeteredTransport(Budget.from_context(config), "judge")) as client:
            async def batch(part):
                keys = [r["key"] for r in part]
                batch_id = hashlib.sha256("".join(keys).encode()).hexdigest()
                body = dict(model=config["provider"]["model"], messages=[
                    dict(role="system", content=RULES),
                    dict(role="user", content=json.dumps(part, ensure_ascii=False))],
                    thinking={"type": "disabled"}, max_tokens=1536,
                    response_format={"type": "json_object"}, stream=False)
                append(OUT / "requests.jsonl", dict(batch_id=batch_id, keys=keys, payload=body,
                                                    at=datetime.now(UTC).isoformat()))
                started = time.monotonic()
                result = await client.post(config["provider"]["base_url"] + "/chat/completions",
                                           headers={"Authorization": "Bearer " + credential(config)}, json=body)
                try:
                    value = result.json()
                except ValueError:
                    value = {"unparsed_body": result.text}
                response = dict(batch_id=batch_id, keys=keys, status=result.status_code, response=value,
                                elapsed_seconds=time.monotonic()-started, at=datetime.now(UTC).isoformat())
                append(OUT / "responses.jsonl", response)
                recover(response)
                print("graded", len(read(OUT / "grades.jsonl")), "of1728", flush=True)

            for start in range(0, len(rows), 24):
                outcomes = await asyncio.gather(*(batch(rows[i:i+8])
                    for i in range(start, min(start+24, len(rows)), 8)), return_exceptions=True)
                errors = [type(r).__name__ + ":" + str(r) for r in outcomes if isinstance(r, BaseException)]
                if errors:
                    raise RuntimeError("Saved all sibling responses; no automatic retry: " + repr(errors))
        grades = read(OUT / "grades.jsonl")
        assert len(grades) == len({r["key"] for r in grades}) == 1728
        assert not unresolved_requests(read(OUT / "requests.jsonl"), read(OUT / "responses.jsonl"))
        save(OUT / "manifest.json", dict(status="AUTO_COMPLETE_CODEX_REVIEW_PENDING", total=1728,
            rules_sha256=hashlib.sha256(RULES.encode()).hexdigest(),
            annotation_errors=[r["key"] for r in grades if r.get("index_annotation_errors")],
            raw_grades_sha256=sha(OUT / "grades.jsonl"), at=datetime.now(UTC).isoformat()))
        state("AWAITING_GRADE_REVIEW", grades=1728)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BaseException as error:
        state("NEEDS_ATTENTION", stage="blind_grading", error=type(error).__name__ + ":" + str(error))
        raise
