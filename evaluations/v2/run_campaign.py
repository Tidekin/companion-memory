"""Run only this already-prepared cohort once; no inference replay or gold reading."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runner"))
from scripts.memory_benchmark.budget import Budget
from scripts.memory_benchmark.cli import closure, environment, execute, validate_run


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(s) for s in path.read_text("utf-8").splitlines()] if path.exists() else []


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def state(status, **details):
    save(
        ROOT / "pipeline-status.json",
        {
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            **details,
        },
    )


def lifecycle(config):
    run = Path(config["run_dir"])
    temporary = ROOT.parent / "test-temp" / ("blind-comparison-" + config["campaign_arm"])
    assert temporary.resolve().is_relative_to((ROOT.parent / "test-temp").resolve())
    temporary.mkdir(parents=True, exist_ok=True)
    execute(
        config,
        [
            "-m",
            "pytest",
            str(Path(config["source_snapshot"]) / "tests/_benchmark_lifecycle_checks.py"),
            "-q",
            "--junitxml=" + str(run / "lifecycle.xml"),
            "--basetemp=" + str(temporary / "lifecycle"),
            "-o",
            "cache_dir=" + str(temporary / "pytest-cache"),
        ],
        "lifecycle.log",
    )
    tree = ET.parse(run / "lifecycle.xml")
    assert len(list(tree.iter("testcase"))) == 18
    assert not any(list(tree.iter(tag)) for tag in ("failure", "error", "skipped"))
    if temporary.exists():
        shutil.rmtree(temporary)


def main():
    with FileLock(str(ROOT / "campaign.lock"), timeout=0):
        preflight_resume = "--resume-preflight" in sys.argv
        if (ROOT / "run-started.json").exists():
            assert preflight_resume, "Never replay a started cohort"
            assert not (ROOT / "deepseek-usage.jsonl").exists()
            assert all(not (ROOT / "arms" / arm / "results").exists() for arm in ("old", "new"))
            assert not (ROOT / "pre-inference-resumed.json").exists()
        else:
            assert not preflight_resume
        frozen = json.loads((ROOT / "execution-freeze.json").read_text("utf-8"))
        for name, expected in frozen["files_sha256"].items():
            assert sha(ROOT / name) == expected, "Execution freeze changed: " + name
        configs = {a: validate_run(ROOT / "arms" / a) for a in ("old", "new")}
        assert not (ROOT / "deepseek-usage.jsonl").exists(), "Fresh round must start atzero"
        save(
            ROOT / ("pre-inference-resumed.json" if preflight_resume else "run-started.json"),
            {
                "pid": os.getpid(),
                "at": datetime.now(timezone.utc).isoformat(),
                "execution_freeze_sha256": sha(ROOT / "execution-freeze.json"),
            },
        )
        try:
            state("LIFECYCLE_CHECKS")
            for config in configs.values():
                lifecycle(config)
            state("RUNNING_NATIVE_INFERENCE")
            workers, logs = {}, {}
            try:
                for arm, config in configs.items():
                    logs[arm] = (ROOT / "arms" / arm / "inference.log").open("a", encoding="utf-8")
                    workers[arm] = subprocess.Popen(
                        [sys.executable, "-B", "-m", "scripts.memory_benchmark.worker"],
                        cwd=ROOT,
                        env=environment(config),
                        stdout=logs[arm],
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                state("RUNNING_NATIVE_INFERENCE", workers={a: p.pid for a, p in workers.items()})
                codes = {a: p.wait() for a, p in workers.items()}
            finally:
                for log in logs.values():
                    log.close()
            save(
                ROOT / "native-run-completion.json",
                {
                    "exit_codes": codes,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "worker_pids": {a: p.pid for a, p in workers.items()},
                },
            )
            for config in configs.values():
                closure(config)
            state("RUNNING_QWEN_RAG")
            with (ROOT / "rag.log").open("a", encoding="utf-8") as log:
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "run_rag.py")],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                assert result.returncode == 0, "Qwen RAG needs inspection"
            assert (
                json.loads((ROOT / "rag/manifest.json").read_text("utf-8"))["status"] == "COMPLETED"
            )
            rag_answers = read(ROOT / "rag/answers.jsonl")
            assert len(rag_answers) == len({a["id"] for a in rag_answers}) == 576
            assert {a["id"] for a in rag_answers} == set(configs["old"]["selected_ids"])
            assert all(a["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"} for a in rag_answers)
            meter = Budget.from_context(configs["old"])
            held, latest = meter.snapshot()
            assert held <= 50 and not any(v["state"] == "RESERVED" for v in latest.values())
            rag_errors = {r["id"]: r for r in read(ROOT / "rag/errors.jsonl")}
            for row in latest.values():
                if row["state"] == "UNKNOWN" and row["phase"].startswith("inference:rag:"):
                    assert rag_errors[row["id"]]["local_await_finished"] is True
            q_records = {}
            for row in read(ROOT / "qwen-usage.jsonl"):
                q_records.setdefault(row["id"], {}).update(row)
            assert sum(v["charged_or_held_cny"] for v in q_records.values()) <= 50
            assert not any(v["state"] == "RESERVED" for v in q_records.values())
            answer_files = [
                p for a in configs for p in (ROOT / "arms" / a / "results").glob("*/answers.jsonl")
            ]
            answer_files.append(ROOT / "rag/answers.jsonl")
            save(
                ROOT / "all-answers-frozen.json",
                {
                    "status": "ALL1728_ANSWERS_CLOSED_BEFORE_GOLD_READ",
                    "files_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in answer_files},
                    "corpus_freeze_sha256": sha(ROOT / "corpus-freeze.json"),
                    "charged_or_held_cny": held,
                    "failures_kept_in_denominator": True,
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            )
            state("READY_FOR_BLIND_GRADING", answers_per_arm=576, deepseek_charged_or_held_cny=held)
        except BaseException as error:
            state("NEEDS_ATTENTION", error_type=type(error).__name__, error=str(error)[:800])
            raise


if __name__ == "__main__":
    main()
