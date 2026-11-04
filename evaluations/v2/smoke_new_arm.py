"""Crash/plumbing smoke of the changed Core on the OLD, already-exposed bank (not the holdout).

One persona, the earliest questions only, a separate small budget ledger whose spend is
added to this round's total. Answers here are never scored or used for the comparison.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "runner"))
from scripts.memory_benchmark.cli import configuration, environment, execute, freeze

OLD_BANK = WORKSPACE / ".local/_extract_cmp_20261102/bank"


def main(commit, count):
    smoke = ROOT / "smoke"
    smoke.mkdir(exist_ok=False)
    toml = (ROOT / "new.toml").read_text("utf-8")
    toml = toml.replace(f'fixture_root = "{(ROOT / "bank").as_posix()}"',
                        f'fixture_root = "{OLD_BANK.as_posix()}"')
    toml = toml.replace(f'campaign_budget_path = "{(ROOT / "deepseek-usage.jsonl").as_posix()}"',
                        f'campaign_budget_path = "{(smoke / "deepseek-usage.jsonl").as_posix()}"')
    toml = toml.replace("total_cny = 48\ninference_cny = 45.5", "total_cny = 2\ninference_cny = 1.8")
    assert OLD_BANK.as_posix() in toml and "total_cny = 2\n" in toml
    path = smoke / "smoke.toml"
    path.write_text(toml, "utf-8")
    config = configuration(path)
    assert config["source_commit"] == commit
    questions = sorted((json.loads(s) for s in (OLD_BANK / "suite-v1/questions.jsonl")
                        .read_text("utf-8").splitlines()), key=lambda q: (q["now"], q["id"]))
    chosen = [q["id"] for q in questions if q["persona"] == "N01"][:count]
    config.update(selected_ids=chosen, personas=["N01"])
    config = freeze(config, smoke / "arm")
    execute(config, ["-m", "scripts.memory_benchmark.worker"], "inference.log")
    print("smoke done", len(chosen))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
