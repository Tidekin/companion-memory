"""Conservative estimate from exposed smoke and frozen v4 bills; no provider calls."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent


def snapshot(path):
    latest = {}
    for row in (json.loads(s) for s in path.read_text('utf-8').splitlines()):
        latest.setdefault(row['id'], {}).update(row)
    return sum(r['charged_or_held_cny'] for r in latest.values()), latest


smoke, calls = snapshot(root/'smoke/deepseek-usage.jsonl')
assert len(calls) == 21 and all(r['state'] == 'SETTLED' for r in calls.values())
oldroot = Path('LOCAL_PATH Core/.local/memory-accuracy-v4-20261103')
deep, _ = snapshot(oldroot/'deepseek-usage.jsonl')
qwen, _ = snapshot(oldroot/'qwen-usage.jsonl')
result = {
    'basis': '744/480 scaling of previous full round plus separate closed-book headroom; estimates are not guarantees',
    'smoke': {'answers': 6, 'succeeded': 6, 'provider_calls': len(calls), 'held_or_estimated_cny': smoke},
    'prior_round_charged_or_held_cny': {'deepseek': deep, 'qwen': qwen},
    'scaled_prior_round_estimate_cny': {'deepseek': deep*744/480, 'qwen': qwen*744/480},
    'planning_allowance_cny': {'deepseek_main': 65, 'qwen_all': 60},
    'hard_caps_cny': {'deepseek_main': 79, 'deepseek_smoke': 1, 'qwen_all': 80},
    'new_control_and_judge_note': 'Closed-book adds DeepSeek generation. One Qwen judge replaces one of the previous three DeepSeek votes. Anchor retries remain accounted and can stop at caps.',
    'execution': 'native arms and personas serial; no early stopping based on accuracy',
    'all_attempted_unknown_or_failed_calls_remain_charged_or_held': True,
}
(root/'cost-preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2), 'utf-8')
print(json.dumps(result,ensure_ascii=False))
