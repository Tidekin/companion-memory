"""One campaign, with the previously requested parallel arm/vote scheduling.

All inference, admissions, lifecycle checks, judging and answer closure use the
unchanged toolkit. Only scheduling differs; no automatic rerun is implemented.
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
TOOLS = WORKSPACE / 'benchmarks/memory_campaign'
sys.path.insert(0, str(TOOLS))
from roundcfg import Round, read_rows, save, sha

R = Round(ROOT)


def state(status, **extra):
    save(ROOT / 'supervisor-status.json', {
        'status': status, 'at': datetime.now(UTC).isoformat(), 'pid': os.getpid(), **extra})
    print(status, flush=True)


def load_tool(name):
    spec = importlib.util.spec_from_file_location('final_campaign_' + name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_parallel(module, configs):
    module.state('LIFECYCLE_CHECKS')
    verification = ROOT / 'lifecycle-verification.json'
    if verification.exists():
        for name, digest in json.loads(verification.read_text('utf-8'))['files_sha256'].items():
            assert sha(ROOT / name) == digest, name
    else:
        for config in configs.values():
            module.lifecycle(config)
    workers, logs = {}, []
    try:
        for arm, config in configs.items():
            log = (R.arm_dir(arm) / 'inference.log').open('ab')
            logs.append(log)
            workers[arm] = subprocess.Popen(
                [sys.executable, '-B', '-m', 'scripts.memory_benchmark.worker'], cwd=ROOT,
                env=module.environment(config), stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        module.state('RUNNING_NATIVE_INFERENCE', schedule='parallel_two_arms_personas_serial',
                     workers={arm: p.pid for arm, p in workers.items()})
        codes = {arm: process.wait() for arm, process in workers.items()}
        save(ROOT / 'native-run-completion.json', {
            'exit_codes': codes, 'at': datetime.now(UTC).isoformat()})
        for config in configs.values():
            module.closure(config)
    finally:
        for log in logs:
            log.close()


async def fixed_votes(judge, config, cases, failures, lookup, paths, names):
    # A failed sibling must not cancel provider requests already sent by another vote.
    outcomes = await asyncio.gather(*(
        judge(config, cases, failures, lookup, path, vote, name)
        for vote, (path, name) in enumerate(zip(paths, names), 1)), return_exceptions=True)
    errors = [repr(value) for value in outcomes if isinstance(value, BaseException)]
    if errors:
        raise RuntimeError('Saved all sibling outcomes; no automatic retry: ' + str(errors))
    return outcomes


async def grade_parallel(module):
    with FileLock(str(module.OUT.parent / f'.{module.OUT.name}.lock'), timeout=0):
        config, cases, failures = module.prepare()
        names = list(module.G['judges'])
        assert names == ['deepseek', 'deepseek', 'qwen']
        assert not (module.OUT / 'grades.jsonl').exists()
        paths = [module.OUT / f'vote-{n}' for n in (1, 2, 3)]
        passes = await fixed_votes(module.judge, config, cases, failures,
                                   {c['key']: c for c in cases}, paths, names)
        for row in module.majority(passes):
            module.append(module.OUT / 'grades.jsonl', row)
        grades = read_rows(module.OUT / 'grades.jsonl')
        assert len(grades) == len({r['key'] for r in grades}) == R.answers_total
        gates = {path.name: module.anchor_gate(path) for path in paths}
        failed = [name for name, gate in gates.items() if gate and not gate['passed']]
        save(module.OUT / 'manifest.json', {
            'status': 'ANCHOR_GATE_FAILED' if failed else 'AUTO_COMPLETE_REVIEW_PENDING',
            'rubric': module.VERSION, 'votes': 3, 'judges': names,
            'schedule': 'parallel_three_fixed_votes', 'anchor_gates': gates,
            'anchor_failed_keys': sum(bool(r.get('anchor_failed')) for r in grades),
            'split_decisions': sum(r.get('agreement', 1) < 1 for r in grades),
            'total': R.answers_total, 'raw_grades_sha256': sha(module.OUT / 'grades.jsonl'),
            'at': datetime.now(UTC).isoformat()})


def verify_and_admit():
    assert not (ROOT / 'paid-campaign-started.json').exists(), 'Only one campaign is authorized'
    assert not R.deepseek_ledger.exists() and not R.qwen_ledger.exists()
    assert not (ROOT / 'smoke').exists()
    receipt = WORKSPACE / '.local/memory-reliability-20261104/product-verification.json'
    product = json.loads(receipt.read_text('utf-8'))
    assert product['status'] == 'VERIFIED_TARGETED_REPAIRS_AFTER_ONE_FULL_REPOSITORY_RUN'
    assert product['full_repository_runs'] == 1 and product['full_failures_targeted_pass'] == 17
    assert product['candidate'] == R.cfg['arms']['new']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKSPACE,
                                   text=True).strip() == product['candidate']
    assert not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=WORKSPACE)
    for name, digest in product['files_sha256'].items():
        assert sha(receipt.parent / name) == digest, name
    execution = json.loads((ROOT / 'execution-freeze.json').read_text('utf-8'))
    for name, digest in execution['files_sha256'].items():
        assert sha(ROOT / name) == digest, name
    campaign = json.loads((ROOT / 'campaign-freeze.json').read_text('utf-8'))
    for name, digest in campaign['tooling_sha256'].items():
        assert sha(TOOLS / name) == digest, name
    assert R.total == 792 and R.cfg['budget']['deepseek_total_cny'] == 79
    assert R.cfg['smoke']['budget_cny'] == 1 and R.cfg['budget']['qwen_total_cny'] == 80
    checks = json.loads((ROOT / 'pipeline-checks.json').read_text('utf-8'))
    assert checks['passed'] and checks['provider_calls'] == 0
    life = json.loads((ROOT / 'lifecycle-verification.json').read_text('utf-8'))
    assert life['passed'] and life['provider_calls'] == 0
    for arm in R.cfg['arms']:
        tree = ET.parse(R.arm_dir(arm) / 'lifecycle.xml')
        assert len(list(tree.iter('testcase'))) == 18
        assert not any(list(tree.iter(k)) for k in ('failure', 'error', 'skipped'))
    bound = ['pipeline.py', 'DESIGN.md', 'build_bank.py', 'anchors.jsonl', 'anchor-provenance.json',
             'preflight.json', 'preregistered-sensitivity.json', 'paired_analysis.py',
             'pipeline-checks.json', 'execution-freeze.json', 'lifecycle-verification.json',
             'arms/old/lifecycle.xml', 'arms/new/lifecycle.xml', 'old.toml', 'new.toml']
    save(ROOT / 'paid-campaign-started.json', {
        'status': 'SOLE_CAMPAIGN_ADMITTED_BEFORE_FIRST_PROVIDER_CALL',
        'at': datetime.now(UTC).isoformat(), 'candidate': product['candidate'],
        'product_verification_sha256': sha(receipt),
        'files_sha256': {name: sha(ROOT / name) for name in bound},
        'previous_new_paid_campaigns': 0, 'new_calls_before': 0,
        'caps_cny': {'deepseek_main': 79, 'deepseek_smoke': 1, 'qwen_all': 80}})


def main():
    with FileLock(str(ROOT / 'supervisor.lock'), timeout=0):
        verify_and_admit()
        sys.argv = [str(__file__), '--round', str(ROOT)]
        os.chdir(ROOT)
        state('EXPOSED_SMOKE')
        configs = {arm: (ROOT / f'{arm}.toml').read_bytes() for arm in R.cfg['arms']}
        try:
            load_tool('smoke').main()
        finally:
            # smoke.py creates temporary root configs. Preserve the already reviewed
            # identical arm configs; actual execution reads each frozen run.json.
            for arm, content in configs.items():
                (ROOT / f'{arm}.toml').write_bytes(content)
        answers = [a for p in (ROOT / 'smoke/arm/results').glob('*/answers.jsonl')
                   for a in read_rows(p)]
        assert len(answers) == 6 and all(a['status'] == 'SUCCEEDED' for a in answers)
        state('MAIN_CAMPAIGN_PARALLEL_ARMS')
        module = load_tool('run')
        module.native = lambda configs: native_parallel(module, configs)
        module.main()
        assert (ROOT / 'all-answers-frozen.json').exists()
        state('FIXED_BLIND_JUDGES_PARALLEL')
        asyncio.run(grade_parallel(load_tool('grade')))
        state('GRADING_COMPLETE_REVIEW_REQUIRED')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        state('NEEDS_ATTENTION_NO_AUTOMATIC_RERUN', error_type=type(error).__name__,
              error=str(error)[:600])
        raise
