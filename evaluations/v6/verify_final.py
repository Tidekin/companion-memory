"""Offline final integrity receipt. Existing receipts are checked, never overwritten."""
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
TOOLS = WORKSPACE / 'benchmarks/memory_campaign'
sys.path.insert(0, str(TOOLS))
from roundcfg import Round, ledger_total, read_rows, sha


def read(name):
    return json.loads((ROOT / name).read_text('utf-8'))


def bound_files(name):
    record = read(name)
    for path, digest in record['files_sha256'].items():
        assert sha(ROOT / path) == digest, (name, path)
    return len(record['files_sha256'])


def verify():
    receipt = ROOT / 'final-verification-receipt.json'
    if receipt.exists():
        for name, digest in read(receipt.name)['files_sha256'].items():
            assert sha(ROOT / name) == digest, name
        print('Existing final receipt and all bound deliverables unchanged')
        return
    r = Round(ROOT)
    assert r.total == 792 and len(r.personas) == 6
    assert r.cfg['arms']['new'] == '7074838d13336240968d39b0299ada126b610b99'
    delivery = read('post-evaluation-verification.json')
    assert delivery['benchmark_candidate'] == r.cfg['arms']['new']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKSPACE,
                                   text=True).strip() == delivery['delivery_candidate']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD^'], cwd=WORKSPACE,
                                   text=True).strip() == r.cfg['arms']['new']
    assert delivery['checks']['green'] == {'cases': 90, 'passed': 90, 'failed': 0}
    assert delivery['post_repair_paid_calls'] == delivery['post_repair_full_runs'] == 0
    for path, digest in delivery['source_sha256'].items():
        assert sha(WORKSPACE / path) == digest, ('delivery-source', path)
    bound_files('post-evaluation-verification.json')
    assert not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=WORKSPACE)
    checks = {name: bound_files(name) for name in (
        'execution-freeze.json', 'paid-campaign-started.json', 'all-answers-frozen.json',
        'lifecycle-verification.json')}
    product = WORKSPACE / '.local/memory-reliability-20261104/product-verification.json'
    assert read('paid-campaign-started.json')['product_verification_sha256'] == sha(product)
    for name, digest in json.loads(product.read_text('utf-8'))['files_sha256'].items():
        assert sha(product.parent / name) == digest, ('product', name)
    sys.path.insert(0, str(TOOLS / 'runner'))
    from scripts.memory_benchmark.cli import validate_run

    frozen = {arm: validate_run(r.arm_dir(arm)) for arm in ('old', 'new')}
    campaign = read('campaign-freeze.json')
    for name, digest in campaign['tooling_sha256'].items():
        assert sha(TOOLS / name) == digest, name
    status = read('grading/manifest.json')
    assert status['votes'] == 3 and status['judges'] == ['deepseek', 'deepseek', 'qwen']
    assert sha(ROOT / 'grading/grades.jsonl') == status['raw_grades_sha256']
    assert status['total'] == r.answers_total == 3168
    mapping = read('grading/blind-mapping.json')
    assert len(mapping) == len({m['key'] for m in mapping}) == r.answers_total
    raw = {x['key']: x for x in read_rows(ROOT / 'grading/grades.jsonl')}
    assert set(raw) == {m['key'] for m in mapping}
    final = {key: value['pass'] for key, value in raw.items()}
    overlays = read_rows(ROOT / 'grading/overrides.jsonl')
    assert len(overlays) == len({x['key'] for x in overlays})
    for overlay in overlays:
        key = overlay['key']
        assert overlay['original_grade'] == raw[key]
        assert type(overlay['pass']) is bool and overlay['pass'] != raw[key]['pass']
        final[key] = overlay['pass']
    answers = {arm: {x['id']: x for x in r.arm_answers(arm)} for arm in r.graded_arms}
    for arm in r.graded_arms:
        assert len(answers[arm]) == r.total
    for item in mapping:
        text = answers[item['arm']][item['id']].get('answer', '')
        assert hashlib.sha256(text.encode()).hexdigest() == item['answer_sha256']
    review = read_rows(ROOT / 'grading/review.jsonl')
    assert len(review) == len({x['key'] for x in review})
    answer_hash = {m['key']: m['answer_sha256'] for m in mapping}
    for item in review:
        assert type(item['review_pass']) is bool and item['review_pass'] == final[item['key']]
        assert item['answer_sha256'] == answer_hash[item['key']] and item['reason'].strip()
    reviewed = {x['key'] for x in review}
    selected = read('grading/review-selection.json')
    keys = {x['key'] for x in selected} if isinstance(selected, list) else set(selected['keys'])
    assert keys <= reviewed
    uncertain = set()
    votes = []
    for number in (1, 2, 3):
        vote = ROOT / 'grading' / f'vote-{number}'
        grades = read_rows(vote / 'grades.jsonl')
        assert len(grades) == len({x['key'] for x in grades}) == r.answers_total
        uncertain.update(x['key'] for x in grades
                         if x.get('anchor_failed') or x.get('judge_unresolved'))
        requests, responses = read_rows(vote / 'requests.jsonl'), read_rows(vote / 'responses.jsonl')
        assert {x['batch_id'] for x in requests} <= {x['batch_id'] for x in responses}
        votes.extend(vote / name for name in ('grades.jsonl', 'requests.jsonl', 'responses.jsonl'))
    assert uncertain <= reviewed
    supplemental = read('grading/review-supplement-selection.json')
    assert {x['key'] for x in supplemental} <= reviewed
    assert {x['key'] for x in read('grading/review-boundary-selection.json')} <= reviewed
    grade_freeze = read('grading/grading-freeze.json')
    assert grade_freeze['criteria_sha256'] == sha(r.suite / 'review-only/criteria.jsonl')
    assert grade_freeze['anchors_sha256'] == sha(ROOT / 'anchors.jsonl')
    summary, results = read('summary.json'), read('results.json')
    assert len(results) == r.total and len({row['id'] for row in results}) == r.total
    assert {row['id'] for row in results} == {row['id'] for row in r.questions}
    for row in results:
        assert set(row['arms']) == set(r.graded_arms)
        for value in row['arms'].values():
            assert value['passed'] == final[value['key']]
            assert value['answer_sha256'] == answer_hash[value['key']]
    for arm, score in summary['overall'].items():
        assert score['total'] == r.total
        assert score['passed'] == sum(row['arms'][arm]['passed'] for row in results)
        assert score['rate'] == score['passed'] / r.total
    paired = read('paired-analysis.json')
    assert paired['results_sha256'] == sha(ROOT / 'results.json')
    assert read('validity-sensitivity.json')['results_sha256'] == sha(ROOT / 'results.json')
    assert summary['post_evaluation_repair'] == delivery
    assert summary['raw_majority'] == {arm: sum(x['pass'] for key, x in raw.items()
        if key in {m['key'] for m in mapping if m['arm'] == arm}) for arm in r.graded_arms}
    for arm, expected in {'old': 721, 'new': 738, 'rag': 748, 'closed': 28}.items():
        assert summary['overall'][arm]['passed'] == expected
    visual = read('visual-review.json')
    assert visual['passed'] and len(visual['embedded_charts_inspected']) == 8
    qa = read('output/playwright/qa.json')
    assert qa['question_details'] == 792 and qa['answer_cards'] == 3168
    assert qa['images_loaded'] == 8
    assert not qa['desktop_horizontal_overflow'] and not qa['mobile_horizontal_overflow']
    finance = {}
    for label, path, cap in (('deepseek_main', r.deepseek_ledger, 79),
                             ('deepseek_smoke', ROOT / 'smoke/deepseek-usage.jsonl', 1),
                             ('qwen', r.qwen_ledger, 80)):
        total, latest = ledger_total(path)
        assert total <= cap + 1e-7 and all(x['state'] == 'SETTLED' for x in latest.values())
        finance[label] = {'charged_or_held_cny': total, 'cap_cny': cap,
                          'invoice_verified': False, 'requests': len(latest)}
    assert finance['deepseek_main']['charged_or_held_cny'] + finance[
        'deepseek_smoke']['charged_or_held_cny'] <= 80 + 1e-7
    v5 = WORKSPACE / '.local/memory-accuracy-v5-20261103'
    old = v5 / 'final-verification-receipt.json'
    assert sha(old) == 'cf5a2a3e81be836a27e99cc233c746e85325c6deb35207aba012ce51153b93ff'
    for name, digest in json.loads(old.read_text('utf-8'))['files_sha256'].items():
        assert sha(v5 / name) == digest, name
    files = [ROOT / name for name in (
        'round.json', 'source-freeze.json', 'corpus-freeze.json', 'execution-freeze.json',
        'campaign-freeze.json', 'paid-campaign-started.json', 'pipeline.py',
        'preregistered-sensitivity.json', 'all-answers-frozen.json', 'summary.json',
        'results.json', 'paired-analysis.json', 'paired_analysis.py', 'memory-report.html',
        'evidence-diagnosis.md', 'grading/manifest.json', 'grading/grading-freeze.json',
        'grading/blind-mapping.json', 'grading/grades.jsonl', 'grading/review-selection.json',
        'grading/review.jsonl', 'grading/overrides.jsonl', 'output/playwright/qa.json',
        'grading/review-supplement-selection.json', 'grading/review-worklist.json',
        'grading/review-boundary-selection.json',
        'native-runtime-metrics.json', 'native_runtime_analysis.py', 'render_report.py',
        'prepare_review.py', 'verify_final.py', 'qa_report.py', 'review_batch.py',
        'grading/review-materials.json',
        'question-validity-audit.json', 'validity-sensitivity.json', 'validity_analysis.py',
        'failure-diagnosis.json', 'review-semantic-boundaries.json', 'counterexamples.json',
        'counterexample_analysis.py', 'post-evaluation-verification.json',
        'post-evaluation-amendment.md', 'post_evaluation_verification.py',
        'post-evaluation-source-red.xml', 'post-evaluation-source-green.xml',
        'grading/review-amendments.jsonl', 'grading/review-corrections.json', 'visual-review.json',
        'deepseek-usage.jsonl', 'qwen-usage.jsonl', 'smoke/deepseek-usage.jsonl',
        'evidence-diagnosis.json')]
    files += votes + list(ROOT.glob('*.png')) + list(ROOT.glob('*.svg'))
    files += list((ROOT / 'grading').glob('review-decisions-*.json'))
    files += list((ROOT / 'output/playwright').glob('*.png'))
    for arm in ('old', 'new'):
        files += [r.arm_dir(arm) / 'run.json', r.arm_dir(arm) / 'freeze.json']
        for pattern in ('*/answers.jsonl', '*/requests.jsonl', '*/responses.jsonl',
                        '*/turns-observed.jsonl', '*/core.sqlite3'):
            files += list((r.arm_dir(arm) / 'results').glob(pattern))
        files.append(r.arm_dir(arm) / 'inference.log')
    for arm in ('rag', 'closed'):
        files += [ROOT / arm / name for name in ('answers.jsonl', 'requests.jsonl', 'responses.jsonl')]
    report = {
        'status': 'COMPLETE_REVIEWED_WITH_DISCLOSED_LIMITATIONS',
        'at': datetime.now(UTC).isoformat(), 'benchmark_candidate': r.cfg['arms']['new'],
        'delivery_candidate': delivery['delivery_candidate'],
        'baseline': r.cfg['arms']['old'], 'instances': 792, 'fact_groups': 180,
        'personas': 6, 'answers': {arm: len(value) for arm, value in answers.items()},
        'hash_checks': checks, 'all_anchor_gates_passed': all(
            value and value['passed'] for value in status['anchor_gates'].values()),
        'reviewed': len(review), 'any_vote_uncertain_reviewed': len(uncertain),
        'same_assistant_not_independent_human': True, 'finance': finance,
        'product_receipt': {
            'path': str(WORKSPACE / '.local/memory-reliability-20261104/product-verification.json'),
            'sha256': sha(WORKSPACE / '.local/memory-reliability-20261104/product-verification.json')},
        'native_profiles_frozen': {a: len(frozen[a]['personas']) for a in frozen},
        'overall': summary['overall'], 'full_paid_campaigns': 1,
        'frozen_source_bank_criteria_answers_changed_after_answers': False,
        'separate_post_evaluation_source_repair': True,
        'post_repair_paid_calls': 0, 'production_changes': 0,
        'full_repository_runs': 1, 'delivery_score_not_retested': True,
        'post_evaluation_receipt_sha256': sha(ROOT / 'post-evaluation-verification.json'),
        'v5_receipt_unchanged': sha(old),
        'files_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in files}}
    assert report['all_anchor_gates_passed'], 'Quality gate failure must be reported explicitly'
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('Final receipt created:', sha(receipt))


if __name__ == '__main__':
    verify()
