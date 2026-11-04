"""Export allowlisted synthetic evaluation material; never run providers or alter originals."""

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = {
    ".py",
    ".ps1",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".html",
    ".svg",
    ".toml",
    ".yml",
    ".yaml",
    ".lock",
}
BINARY = {".png", ".wav"}
TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{18,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
)
LOCAL = re.compile(
    r"(?i)(?:(?<![a-z0-9])[a-z]:[\\/](?:[^\s\"'<>;,\]\)}]|\\ )+"
    r"|/(?:root|home|opt)/[^\s\"'<>;,\]\)}]+)"
)
IP = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
OMIT_SCRIPTS = {"monitor_status.py", "parallel_handoff.py", "check_comparison_ui.py"}
ROOT_JSON = {
    "budget-allocation.json",
    "coverage-and-freeze.json",
    "verification-receipt.json",
    "verification-tests.json",
    "final-verification-receipt.json",
    "native-runner-freeze.json",
    "runner-freeze-v2.json",
    "reference-judge-freeze.json",
    "secondary-review-freeze.json",
    "all-answers-frozen.json",
    "answers-frozen-before-grading.json",
    "anchor-provenance.json",
    "counterexamples.json",
    "failure-diagnosis.json",
    "validity-sensitivity.json",
    "lifecycle-verification.json",
    "native-runtime-metrics.json",
    "preregistered-sensitivity.json",
    "preregistered-review-decisions.json",
    "question-validity-audit.json",
    "review-semantic-boundaries.json",
    "review-completion.json",
    "configuration-amendment.json",
    "schedule-amendment.json",
    "grading-schedule-amendment.json",
    "grading-finalization-repair.json",
    "grading-boundary-receipt.json",
    "reporting-overlay.json",
    "report-visual-qa.json",
    "visual-review.json",
    "results.json",
    "per-question-results.json",
    "summary.json",
    "result-summary.json",
    "round.json",
    "source-freeze.json",
    "corpus-freeze.json",
    "campaign-freeze.json",
    "execution-freeze.json",
    "comparison-policy.json",
    "review-selection.json",
    "sensitivity.json",
    "evidence-diagnosis.json",
    "paired-analysis.json",
    "validity-analysis.json",
    "counterexample-analysis.json",
    "native-runtime-analysis.json",
    "post-evaluation-verification.json",
    "post-evaluation-amendment.json",
    "audio-to-synthesize.jsonl",
    "asr-observations.jsonl",
    "asr-quality-audit.json",
    "manual-grade-overrides.jsonl",
    "grade-review-overrides.jsonl",
    "assistant-grade-review.jsonl",
    "secondary-review.jsonl",
    "secondary-review-comparison.json",
    "native-diagnostics.json",
    "native-run-completion.json",
    "pipeline-completion.json",
    "post-bank-code-revision.json",
    "pricing-sources.json",
    "runtime-versions.json",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_ip(match):
    ip = match.group()
    parts = list(map(int, ip.split(".")))
    if (
        max(parts) > 255
        or parts[0] in {0, 10, 127}
        or ip.startswith(("192.168.", "192.0.2.", "198.51.100.", "203.0.113.", "169.254.", "255."))
    ):
        return ip
    # Version strings are checked separately; preserve common 1.x dependency versions.
    if parts[0] < 10:
        return ip
    return "203.0.113.10"


def sanitize(text):
    counts = Counter()
    for name, pattern, replacement in (
        ("credential_shape", TOKEN, "REDACTED_CREDENTIAL"),
        ("local_path", LOCAL, "LOCAL_PATH"),
    ):
        text, n = pattern.subn(replacement, text)
        counts[name] += n
    old = text
    text = IP.sub(safe_ip, text)
    counts["network_address"] += sum(a.group() != safe_ip(a) for a in IP.finditer(old))
    # JSON serializers may have escaped drive paths twice inside embedded HTML.
    if re.search(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", text):
        raise ValueError("PRIVATE_KEY_IN_ALLOWLISTED_EXPORT")
    return text, counts


def sanitize_bytes(path, data):
    if path.suffix not in TEXT:
        return data, Counter()
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    counts = Counter()

    def walk(value):
        if isinstance(value, str):
            result, found = sanitize(value)
            counts.update(found)
            return result
        if isinstance(value, list):
            return [walk(x) for x in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    if path.suffix == ".json":
        text = json.dumps(walk(json.loads(text)), ensure_ascii=False, indent=2) + "\n"
    elif path.suffix == ".jsonl":
        text = "".join(
            json.dumps(walk(json.loads(line)), ensure_ascii=False) + "\n"
            for line in text.splitlines()
            if line.strip()
        )
    else:
        text, counts = sanitize(text)
    return text.encode(), counts


def include(path):
    parts = path.parts
    if any(p.startswith(".") or p == "__pycache__" for p in parts):
        return False
    if path.suffix not in TEXT | BINARY:
        return False
    if len(parts) == 1:
        return (
            (path.suffix in {".py", ".ps1"} and path.name not in OMIT_SCRIPTS)
            or path.name in ROOT_JSON
            or path.suffix in {".md", ".html", ".png", ".svg"}
        )
    if parts[0] in {"bank", "suite-v1"}:
        return True
    if parts[0] == "runner":
        return path.suffix in {".py", ".html"}
    if parts[0].startswith("grading"):
        return path.suffix in {".json", ".jsonl"} and not any(
            x in path.name for x in ("request", "response", "usage")
        )
    return False


def export_round(label, source):
    if not re.fullmatch(r"v[1-6]", label):
        raise ValueError("USE_V1_THROUGH_V6_LABELS")
    source = source.resolve()
    target = ROOT / "evaluations" / label
    entries, changes = {}, Counter()
    for path in sorted(source.rglob("*")):
        if not path.is_file() or not include(path.relative_to(source)):
            continue
        relative = path.relative_to(source)
        original = path.read_bytes()
        public, counts = sanitize_bytes(path, original)
        if (
            relative.as_posix() == "memory-report.html"
            and not (source / "coverage-and-freeze.json").exists()
        ):
            old = b'href="coverage-and-freeze.json"'
            if old in public:
                public = public.replace(old, b'href="PUBLICATION.json"').replace(
                    "覆盖与哈希核对".encode(), "公开副本哈希核对".encode()
                )
                counts["unavailable_link_updated"] += 1
        out = target / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(public)
        entries[relative.as_posix()] = {
            "source_sha256": digest(original),
            "public_sha256": digest(public),
            "bytes": len(public),
            "redactions": dict(+counts),
        }
        changes.update(counts)
    result_name = "per-question-results.json" if label == "v1" else "results.json"
    results = json.loads((target / result_name).read_bytes())
    original_results = json.loads((source / result_name).read_bytes())
    # Redacting machine metadata must never silently alter a question, answer or verdict.
    for original_row, public_row in zip(original_results, results, strict=True):
        for key in ("id", "question", "criteria", "sources", "source_ids"):
            if original_row.get(key) != public_row.get(key):
                raise ValueError("SEMANTIC_RESULT_FIELD_CHANGED: " + key)
        for arm in original_row.get("arms") or {
            k: original_row[k] for k in ("native", "reference")
        }:
            a = original_row.get("arms", original_row)[arm]
            b = public_row.get("arms", public_row)[arm]
            for key in ("answer", "passed", "pass", "auto_grade", "grade", "status"):
                if a.get(key) != b.get(key):
                    raise ValueError("ANSWER_OR_VERDICT_CHANGED: " + key)
    for name, entry in entries.items():
        if (
            "/inputs/" in name
            or "/review-only/" in name
            or name.endswith("questions.jsonl")
            or "/assets/" in name
        ):
            if entry["redactions"]:
                raise ValueError("SYNTHETIC_TEST_INPUT_REQUIRES_MANUAL_REVIEW: " + name)
    source_file = target / "source-freeze.json"
    freeze = json.loads(source_file.read_bytes()) if source_file.exists() else {}
    summary_file = target / ("result-summary.json" if label == "v1" else "summary.json")
    summary = json.loads(summary_file.read_bytes())
    commits = freeze.get("arms") or {
        k: freeze[k + "_commit"] for k in ("old", "new") if k + "_commit" in freeze
    }
    if label == "v1":
        commits = {"native": summary.get("core_commit")}
    record = {
        "round": label,
        "semantic_question_instances": len(results),
        "lifecycle_checks": 18 if label == "v1" else 0,
        "scored_source_commits": commits,
        "authorship": "Project-authored fictional synthetic stories and questions",
        "media": "Project text/images and generic Windows System.Speech TTS output",
        "publication": "Sanitized derived copy; original evidence left unchanged",
        "unavailable_original_artifacts": ["coverage-and-freeze.json"]
        if label == "v2" and not (source / "coverage-and-freeze.json").exists()
        else [],
        "semantic_fidelity": "Questions, criteria, sources, answers and verdicts equal originals",
        "hash_policy": "Public hashes bind these bytes; historical freezes describe originals.",
        "results": result_name,
        "summary": summary_file.name,
        "redaction_counts": dict(+changes),
        "files": entries,
    }
    (target / "PUBLICATION.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {k: v for k, v in record.items() if k != "files"}


def export_toolkit(source, ref):
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", ref]).decode().strip()
    prefix = "benchmarks/memory_campaign/"
    paths = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(source),
                "ls-tree",
                "-r",
                "--name-only",
                commit,
                "--",
                prefix,
            ]
        )
        .decode()
        .splitlines()
    )
    files = {}
    for name in paths:
        path = Path(name)
        if path.suffix not in TEXT:
            continue
        data = subprocess.check_output(["git", "-C", str(source), "show", commit + ":" + name])
        public, counts = sanitize_bytes(path, data)
        out = ROOT / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(public)
        files[name] = {
            "source_sha256": digest(data),
            "public_sha256": digest(public),
            "redactions": dict(+counts),
        }
    (ROOT / "provenance/campaign-toolkit.json").write_text(
        json.dumps({"source_commit": commit, "files": files}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--round", action="append", default=[], metavar="vN=LOCAL_DIRECTORY")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--ref", required=True)
    args = p.parse_args()
    export_toolkit(args.source, args.ref)
    rounds = [
        export_round(label, Path(path))
        for label, path in (item.split("=", 1) for item in args.round)
    ]
    (ROOT / "evaluations/index.json").write_text(
        json.dumps({"rounds": rounds}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "rounds": len(rounds),
                "questions": sum(x["semantic_question_instances"] for x in rounds),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
