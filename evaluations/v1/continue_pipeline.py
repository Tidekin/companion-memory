"""Continue the frozen experiment once all native profile writers have closed."""
import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def save(name, value):
    (BASE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def native_cost():
    total = 0
    for path in BASE.rglob('core.sqlite3'):
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        try:
            rows = conn.execute('SELECT state,billed_micro_usd FROM model_usage').fetchall()
            assert all(row[0] == 'SETTLED' for row in rows), (str(path), 'UNSETTLED_USAGE')
            total += sum(row[1] or 0 for row in rows)
        finally:
            conn.close()
    return total / 1e6


def main():
    print('Pipeline waiting for closed native manifests.', flush=True)
    while True:
        paths = list((BASE / 'native-final-v2').glob('P*/manifest.json'))
        manifests = [json.loads(p.read_text('utf-8')) for p in paths]
        if any(m['status'] == 'INTERRUPTED' for m in manifests):
            raise RuntimeError('NATIVE_INTERRUPTED_REQUIRES_REVIEW')
        if len(manifests) == 6 and all(m['status'] == 'COMPLETED' for m in manifests):
            break
        time.sleep(10)
    # The superseded run must also have closed before final expense aggregation.
    while any(json.loads(p.read_text('utf-8'))['status'] == 'STARTING'
              for p in (BASE / 'native-final-v1').glob('P*/manifest.json')):
        time.sleep(10)
    native = native_cost()
    # Reserve 0.30 USD for judging and 0.03 USD for unrecorded trial headroom.
    cap = round(min(1.4, 3.0 - native - .30 - .03), 6)
    assert cap > .10, 'INSUFFICIENT_EXPERIMENT_BUDGET'
    save('budget-allocation.json', {
        'deepseek_limit_cny': 30, 'qwen_limit_cny': 30,
        'conservative_cny_per_configured_usd': 10,
        'native_all_trials_usd': native, 'reference_cap_usd': cap,
        'judge_cap_usd': .3, 'trial_headroom_usd': .03,
        'maximum_deepseek_hold_cny': (native + cap + .3 + .03) * 10,
    })
    subprocess.run([sys.executable, '-B', str(BASE / 'run_reference.py'),
                    '--deepseek-cap', str(cap)], check=True)
    answers = list((BASE / 'native-final-v2').glob('P*/answers.jsonl'))
    answers.append(BASE / 'reference-final-v1/answers.jsonl')
    save('answers-frozen-before-grading.json', {
        str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in answers
    })
    subprocess.run([sys.executable, '-B', str(BASE / 'grade_suite.py')], check=True)
    save('pipeline-completion.json', {'status': 'INFERENCE_AND_AUTOGRADING_COMPLETED',
                                    'manual_review_and_report_pending': True})
    print('Inference and automatic grading complete; review remains.', flush=True)


if __name__ == '__main__':
    main()
