"""Offline verification of the public source/evaluation bundle. Zero provider calls."""

import argparse
import ast
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from export_evaluations import IP, LOCAL, TEXT, TOKEN, safe_ip
from sync_upstream import verify as verify_upstream

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    ".local",
    ".venv",
    ".planning",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "build",
    ".coverage",
}
MANIFEST = "provenance/release.json"


class ReportLinks(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.path = path

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key not in {"src", "href"} or not value:
                continue
            url = urlparse(value)
            if url.scheme or url.netloc or not url.path:
                continue
            target = self.path.parent / unquote(url.path)
            if not target.is_file():
                raise ValueError("MISSING_REPORT_LINK: " + self.path.parent.name + "/" + url.path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_files():
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts)
        and p.relative_to(ROOT).as_posix() != MANIFEST
    )


def check_sanitized(path, data):
    if path.suffix not in TEXT:
        return
    text = data.decode("utf-8-sig")
    if TOKEN.search(text) or LOCAL.search(text):
        raise ValueError("SENSITIVE_TEXT_PATTERN: " + str(path.relative_to(ROOT)))
    if any(m.group() != safe_ip(m) for m in IP.finditer(text)):
        raise ValueError("OPERATIONAL_NETWORK_ADDRESS: " + str(path.relative_to(ROOT)))
    if re.search(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", text):
        raise ValueError("PRIVATE_KEY_PATTERN: " + str(path.relative_to(ROOT)))
    if path.suffix == ".py":
        ast.parse(text, filename=str(path.relative_to(ROOT)))


def verify_round(path):
    record = json.loads((path / "PUBLICATION.json").read_bytes())
    for name, entry in record["files"].items():
        if sha((path / name).read_bytes()) != entry["public_sha256"]:
            raise ValueError("PUBLIC_EVALUATION_DRIFT: " + path.name + "/" + name)
    rows = json.loads((path / record["results"]).read_bytes())
    summary = json.loads((path / record["summary"]).read_bytes())
    if len(rows) != record["semantic_question_instances"] or len({r["id"] for r in rows}) != len(
        rows
    ):
        raise ValueError("QUESTION_COUNT_OR_DUPLICATES: " + path.name)
    scores = summary.get("overall") or {k: summary["semantic"][k] for k in ("native", "reference")}
    for arm, score in scores.items():
        passed = sum(
            bool(r.get("arms", r)[arm].get("passed", r.get("arms", r)[arm].get("pass")))
            for r in rows
        )
        if passed != score["passed"] or score.get("total", len(rows)) != len(rows):
            raise ValueError("SUMMARY_SCORE_MISMATCH: " + path.name + "/" + arm)
    bank = path / ("suite-v1" if path.name == "v1" else "bank/suite-v1")
    questions = [
        json.loads(line)
        for line in (bank / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(questions) != len(rows) + record["lifecycle_checks"]:
        raise ValueError("BANK_COUNT_MISMATCH: " + path.name)
    ReportLinks(path / "memory-report.html").feed(
        (path / "memory-report.html").read_text(encoding="utf-8")
    )
    return {
        "round": path.name,
        "semantic_questions": len(rows),
        "scores": {arm: score["passed"] for arm, score in scores.items()},
    }


def verify(freeze=False):
    upstream = verify_upstream()
    toolkit = json.loads((ROOT / "provenance/campaign-toolkit.json").read_bytes())
    for name, entry in toolkit["files"].items():
        if sha((ROOT / name).read_bytes()) != entry["public_sha256"]:
            raise ValueError("CAMPAIGN_TOOLKIT_DRIFT: " + name)
    rounds = [verify_round(ROOT / "evaluations" / f"v{i}") for i in range(1, 7)]
    files = {}
    for path in public_files():
        data = path.read_bytes()
        check_sanitized(path, data)
        files[path.relative_to(ROOT).as_posix()] = {"sha256": sha(data), "bytes": len(data)}
    record = {
        "format": 1,
        "source_commit": upstream["commit"],
        "provider_calls_during_publication": 0,
        "rounds": rounds,
        "files": files,
    }
    target = ROOT / MANIFEST
    if freeze:
        target.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    elif json.loads(target.read_bytes()) != record:
        raise ValueError("PUBLIC_RELEASE_MANIFEST_DRIFT")
    return {
        "status": "PUBLIC_BUNDLE_VERIFIED",
        "files": len(files),
        "bytes": sum(x["bytes"] for x in files.values()),
        "source": upstream,
        "rounds": rounds,
        "provider_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Bind the reviewed public candidate")
    args = parser.parse_args()
    print(json.dumps(verify(args.freeze), ensure_ascii=False, indent=2))
