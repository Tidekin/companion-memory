"""Deterministic schema, chronology and actual-media audit, before any paid inference."""

import bisect
import hashlib
import json
import wave
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
SUITE = BANK / "suite-v1"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return [json.loads(s) for s in p.read_text("utf-8").splitlines()]


def save(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main():
    assert not (BANK / "bundle-manifest.json").exists(), "never overwrite a frozen bank"
    assert not (ROOT / "deepseek-usage.jsonl").exists(), "bank must close before paid calls"
    qs = read(SUITE / "questions.jsonl")
    gold = read(SUITE / "review-only/criteria.jsonl")
    asr = {r["asset"]: r for r in read(BANK / "asr-observations.jsonl")}
    assert len(qs) == len(gold) == 576
    assert len({q["id"] for q in qs}) == 576
    assert {q["id"] for q in qs} == {g["id"] for g in gold}
    assert len({q["category"] for q in qs}) == 24
    assert len({q["group_id"] for q in qs}) == 144
    assert set(Counter(q["delay_days"] for q in qs).values()) == {144}
    sources, audio_seconds = [], []
    per_persona = {}
    for hp in sorted((SUITE / "inputs").glob("*.jsonl")):
        h = read(hp)
        assert len(h) == 360
        assert [r["turn"] for r in h] == list(range(1, 361))
        times = [datetime.fromisoformat(r["now"]) for r in h]
        assert times == sorted(set(times))
        ids = {r["id"]: r for r in h}
        selected = [q for q in qs if q["persona"] == hp.stem]
        assert len(selected) == 96
        for q in selected:
            when = datetime.fromisoformat(q["now"])
            assert q["cutoff_turn"] == bisect.bisect_right(times, when)
            assert q["cutoff_turn"] <= len(h)
            anchor = max(datetime.fromisoformat(ids[s]["now"]) for s in q["source_ids"])
            assert (when - anchor).total_seconds() == q["delay_days"] * 86400 + 900
            assert all(ids[s]["turn"] <= q["cutoff_turn"] for s in q["source_ids"])
        for row in h:
            if row.get("asset"):
                p = SUITE / row["asset"]
                assert p.resolve().is_relative_to(SUITE.resolve()) and p.is_file()
                assert not row["text"], "media authoring text must not become model input"
                if p.suffix == ".wav":
                    actual = asr[row["asset"]]
                    assert actual["sha256"] == sha(p) and actual["text"].strip()
                    with wave.open(str(p)) as wav:
                        seconds = wav.getnframes() / wav.getframerate()
                        assert 1 < seconds < 45
                        audio_seconds.append(seconds)
                elif p.suffix == ".png":
                    with Image.open(p) as image:
                        assert image.width * image.height <= 1_000_000
                        image.verify()
                else:
                    assert p.read_text("utf-8").strip()
            if "-Q" in row["id"] and "-X" not in row["id"]:
                sources.append(row)
        per_persona[hp.stem] = {"semantic_questions": 96, "maximum_cutoff_turn": max(q["cutoff_turn"] for q in selected)}
    assert len(audio_seconds) == len(asr) == 21
    manifest = {"version": 2, "classification": "SELF_AUTHORED_FICTIONAL_UNSEEN_AFTER_SOURCE_FREEZE",
                "semantic_instances": 576, "semantic_fact_groups": 144,
                "independent_lifecycle_cases": 18, "lifecycle_is_native_check_not_semantic_answer": True,
                "personas": 6, "turns_per_persona": 360, "history_days": 180,
                "delay_days": [0, 3, 15, 45], "source_modalities": dict(Counter(s["modality"] for s in sources)),
                "per_persona": per_persona, "source_freeze_sha256": sha(ROOT / "source-freeze.json"),
                "files_sha256": {p.relative_to(SUITE).as_posix(): sha(p) for p in sorted(SUITE.rglob("*")) if p.is_file()}}
    save(SUITE / "manifest.json", manifest)
    bundle = {"semantic": 576, "independent_lifecycle_cases": 18, "files_sha256": {
        p.relative_to(BANK).as_posix(): sha(p) for p in sorted(BANK.rglob("*")) if p.is_file()}}
    save(BANK / "bundle-manifest.json", bundle)
    audit = {"status": "FROZEN_SCHEMA_CHRONOLOGY_MEDIA_PASSED", "at": datetime.now(timezone.utc).isoformat(),
             "bundle_manifest_sha256": sha(BANK / "bundle-manifest.json"), "questions_sha256": sha(SUITE / "questions.jsonl"),
             "criteria_sha256": sha(SUITE / "review-only/criteria.jsonl"), "asr_sha256": sha(BANK / "asr-observations.jsonl"),
             "source_counts": manifest["source_modalities"], "audio_assets": len(audio_seconds),
             "audio_total_seconds": sum(audio_seconds), "checked_cutoffs": 576, "per_persona": per_persona,
             "asr_errors_preserved_not_replaced_with_authoring_text": True,
             "actual_pngs_inspected": {name: sha(SUITE / "assets" / name) for name in ["M02-Q18-S1.png", "M01-Q19-S1.png"]},
             "review_selection_preregistered": "M02/all24categories/d15 across3arms =72 answers, plus failures differing between arms",
             "old_bank_or_optimizer_probe_facts_imported": False,
             "limitation": "Six fictional people and 24 topic templates; repeated delay questions are correlated. Author is Claude (same agent that changed Core); review is not independent human grading."}
    save(ROOT / "corpus-freeze.json", audit)
    state = json.loads((ROOT / "bank-authoring-status.json").read_text("utf-8"))
    state.update(status="FROZEN", corpus_freeze_sha256=sha(ROOT / "corpus-freeze.json"))
    save(ROOT / "bank-authoring-status.json", state)
    print(json.dumps({"status": audit["status"], "source_counts": audit["source_counts"], "audio_seconds": audit["audio_total_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
