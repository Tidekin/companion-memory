import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("comparison_report", Path(__file__).with_name("build_comparison_report.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_primary_score_includes_terminal_failure_without_averaging_rates():
    rows = [{"arms": {"old": {"passed": p, "status": s}}} for p,s in
            [(True,"SUCCEEDED"),(True,"SUCCEEDED"),(False,"CANCELLED")]]
    assert mod.score(rows,"old") == dict(passed=2,total=3,rate=2/3,execution_failures=1)


def test_modality_memberships_overlap_intentionally():
    rows = [{"input_modalities": ["text"]}, {"input_modalities": ["voice","image"]}]
    groups = mod.modality_groups(rows)
    assert groups["纯文字源"] == rows[:1]
    assert groups["含语音"] == groups["含图像"] == rows[1:]
