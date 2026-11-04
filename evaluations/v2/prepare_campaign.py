"""One-time prepare/freeze only. No paid HTTP and no inference resume."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "runner"))
from scripts.memory_benchmark.cli import configuration, freeze, parser_probe, validate_run


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_configs():
    source = json.loads((ROOT / "source-freeze.json").read_text("utf-8"))
    policy = json.loads((ROOT / "campaign-budget.json").read_text("utf-8"))
    paths = {}
    for arm in ("old", "new"):
        config_file = ROOT / f"{arm}.toml"
        content = f'''workspace = "{WORKSPACE.as_posix()}"
source_checkout = "{source['source_checkout'].replace(chr(92), '/')}"
fixture_root = "{(ROOT / 'bank').as_posix()}"
embedding_cache_dir = "{(WORKSPACE / 'data/embedding-cache').as_posix()}"
revision = "{source[arm + '_commit']}"
preset = "full"
concurrency = 4
campaign_arm = "{arm}"
campaign_budget_path = "{(ROOT / 'deepseek-usage.jsonl').as_posix()}"

[provider]
adapter = "deepseek"
base_url = "https://api.deepseek.com"
model = "deepseek-flash"
[credentials]
env_file = "{(WORKSPACE / '.env').as_posix()}"
env_name = "COMPANION_MODEL_KEY"
[budget]
total_cny = {policy['deepseek']['total_cny']}
inference_cny = {policy['deepseek']['inference_cny']}
[pricing]
input_rate = 2.0
cached_input_rate = 0.04
output_rate = 8.0
safety_factor = 1.5
[native]
context_soft_tokens = 8000
max_output_tokens = 768
chat_thinking = "high"
chat_thinking_tokens = 3072
memory_extract_max_output_tokens = 2048
timeout_seconds = 45
lease_seconds = 120
[parser]
transport = "ssh"
host = "root@203.0.113.10"
port = 60022
known_hosts_file = "{(Path.home() / '.ssh/known_hosts').as_posix()}"
image = "sha256:f57cbc752e6e828e2ca044509c3e30ff78790d433116f092d2359448280c4aaa"
source_sha256 = "349cd037867fadfe27e8b7a8a969adb676ec98f908269e4f05be1c2a1a76a1ae"
'''
        config_file.write_text(content, "utf-8")
        paths[arm] = config_file
    return paths


def main():
    if "--configs-only" in sys.argv:
        write_configs()
        return
    assert not (ROOT / "campaign-freeze.json").exists()
    source = json.loads((ROOT / "source-freeze.json").read_text("utf-8"))
    configs = {arm: configuration(path) for arm, path in write_configs().items()}
    for arm in configs:
        assert configs[arm]["personas"] == [f"M{i:02}" for i in range(1, 7)]
        assert len(configs[arm]["selected_ids"]) == 576
    parser_probe(configs["old"])
    save(ROOT / "parser-preflight.json", {"status": "PASSED", "at": datetime.now(timezone.utc).isoformat(),
                                        "probe": "read-only SSH docker image inspect with existing trusted known_hosts",
                                        "image": configs["old"]["parser"]["image"], "same_parser_source_for_both": True})
    for arm, config in configs.items():
        run = ROOT / "arms" / arm
        freeze(config, run)
        validate_run(run)
        print("prepared", arm, len(config["selected_ids"]), config["source_commit"], flush=True)
    tooling = {p.relative_to(ROOT).as_posix(): sha(p) for p in (ROOT / "runner/scripts").rglob("*.py")}
    save(ROOT / "campaign-freeze.json", {"status": "PREPARED_NOT_STARTED", "at": datetime.now(timezone.utc).isoformat(),
        "source_freeze_sha256": sha(ROOT / "source-freeze.json"), "corpus_freeze_sha256": sha(ROOT / "corpus-freeze.json"),
        "campaign_budget_sha256": sha(ROOT / "campaign-budget.json"), "tooling_sha256": tooling,
        "arm_freeze_sha256": {a: sha(ROOT / "arms" / a / "freeze.json") for a in configs},
        "native_original_runner_commit": source["runner_commit"], "tooling_scope": "previous round harness; v2 counts, separate 50CNY DeepSeek and 50CNY Qwen caps, harness drives Core RETRY_WAIT for both arms",
        "answers_per_arm": 576, "paid_calls": 0})


if __name__ == "__main__":
    main()
