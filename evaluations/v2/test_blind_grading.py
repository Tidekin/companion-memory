import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("blind_grade", Path(__file__).with_name("grade_blind.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_coverage_refuses_missing_duplicate_and_nonterminal():
    questions = [{"id": str(i)} for i in range(696)]
    good = [{"id": str(i), "status": "SUCCEEDED"} for i in range(696)]
    mod.validate_coverage(questions, {"old": good})
    for broken in (good[:-1], good[:-1] + good[:1], good[:-1] + [{"id": "695", "status": "PENDING"}]):
        with pytest.raises(AssertionError):
            mod.validate_coverage(questions, {"old": broken})


def test_saved_uncertain_batch_not_replayable():
    assert mod.unresolved_requests([{"batch_id": "uncertain"}, {"batch_id": "done"}],
                                   [{"batch_id": "done"}]) == ["uncertain"]


def test_parser_rejects_duplicate_or_wrong_keys_and_keeps_semantic_false():
    import json
    case = {"key": "a", "required": ["甲"], "forbidden": ["乙"]}
    def response(rows):
        return {"status": 200, "keys": ["a"], "response": {"choices": [
            {"message": {"content": json.dumps({"grades": rows})}}]}}
    for rows in ([{"key": "b"}], [{"key": "a"}, {"key": "a"}]):
        with pytest.raises(AssertionError):
            mod.parse_response(response(rows), {"a": case})
    parsed = mod.parse_response(response([{"key": "a", "pass": True, "missing": [0], "violations": []}]), {"a": case})
    assert parsed[0]["pass"] is False
