import importlib.util
import json
from pathlib import Path

import pytest

from companion_memory import (
    Candidate,
    CoreError,
    MemoryReviewError,
    parse_extraction,
    resolve_review,
)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sqlite_demo", ROOT / "examples/sqlite_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def candidate(**changes):
    return Candidate.model_validate(
        {
            "subject": "user",
            "kind": "fact",
            "fact_key": "city",
            "content": "住在苏州",
            "evidence_event_id": "event-1",
            "evidence_quote": "我住在苏州",
            "speaker": "owner",
            **changes,
        }
    )


def review(**changes):
    return json.dumps(
        {
            "relations": [
                {
                    "supported": True,
                    "update_authorized": False,
                    "claims_replacement": False,
                    "replaces": [],
                    **changes,
                }
            ]
        }
    )


def test_sqlite_installed_helpers_and_source_erasure(tmp_path):
    result = demo.run(tmp_path / "example.sqlite")
    assert result["provider_calls"] == 0
    assert result["after_source_erasure"] == []


def test_unknown_usage_and_bad_source_never_write(tmp_path):
    store = demo.ExampleStore(tmp_path / "usage.sqlite")
    try:
        with store.db:
            store.db.execute("INSERT INTO model_usage VALUES('r','UNKNOWN')")
            store.db.execute("INSERT INTO events VALUES('event-1','我住在苏州')")
        with pytest.raises(CoreError, match="MODEL_USAGE_UNRESOLVED"):
            store.remember(candidate(), review(), "r")
        with store.db:
            store.db.execute("UPDATE model_usage SET state='SETTLED'")
        with pytest.raises(ValueError, match="EXACT_SOURCE"):
            store.remember(candidate(evidence_quote="编造来源"), review(), "r")
        assert store.one("SELECT count(*) AS n FROM facts", ())["n"] == 0
    finally:
        store.close()


def test_singleton_same_and_wrapped_conflict_compatibility():
    cat = {"m0": {"memory_id": "stored-1", "subject": "user", "origin": "model_inferred"}}
    _, relations = resolve_review(review(same=["m0"]), [candidate()], cat)
    assert relations == [{"same": "stored-1", "conflicts": [], "replaces": []}]
    _, relations = resolve_review(
        review(
            conflicts=[{"ref": "m0"}],
            replaces=[{"ref": "m0"}],
            update_authorized=True,
            claims_replacement=True,
        ),
        [candidate(update="replaces_previous")],
        cat,
    )
    assert relations[0]["replaces"] == ["stored-1"]


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"same": ["m0", "m1"]}, "schema"),
        ({"same": "c0"}, "invalid_reference"),
        ({"conflicts": ["m0", "m0"]}, "duplicate_relation"),
        ({"conflicts": ["m99"]}, "invalid_reference"),
        ({"replaces": ["m0"]}, "invalid_replacement"),
        ({"supported": "true"}, "schema"),
        ({"claims_replacement": True}, "update_disagreement"),
        ({"update_authorized": True}, "update_disagreement"),
    ],
)
def test_invalid_relations_rejected(changes, reason):
    cat = {"m0": {"memory_id": "stored-1", "subject": "user", "origin": "model_inferred"}}
    with pytest.raises(MemoryReviewError) as error:
        resolve_review(review(**changes), [candidate()], cat)
    assert error.value.feedback["reason"] == reason


def test_authorized_replacement_requires_target_and_origin_match():
    cat = {"m0": {"memory_id": "stored-1", "subject": "user", "origin": "model_inferred"}}
    with pytest.raises(MemoryReviewError) as error:
        resolve_review(
            review(conflicts=["m0"], update_authorized=True),
            [candidate(update="replaces_previous")],
            cat,
        )
    assert error.value.feedback["reason"] == "missing_replacement_target"
    with pytest.raises(MemoryReviewError) as error:
        resolve_review(review(same="m0"), [candidate(evidence_reference_id="source-ref")], cat)
    assert error.value.feedback["reason"] == "invalid_reference"


def test_extraction_restores_refs_after_bounded_json_repair():
    value = candidate().model_dump()
    value["evidence_event_id"] = "e0"
    text = json.dumps({"memories": [value]})[:-1]
    parsed, repaired = parse_extraction(text, {"e0": "real-event"})
    assert repaired and parsed.memories[0].evidence_event_id == "real-event"
    with pytest.raises(ValueError):
        parse_extraction('{"memories":[{"content":"unfinished', {})
