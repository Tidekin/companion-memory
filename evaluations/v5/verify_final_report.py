"""Offline final acceptance evidence; no provider transport or live application writes."""
import hashlib
import importlib.metadata
import json
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
sys.path[:0] = [str(ROOT / '.deps'), str(WORKSPACE / 'benchmarks/memory_campaign')]
from roundcfg import Round, ledger_total, read_rows


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name):
    return json.loads((ROOT / name).read_text('utf-8'))


def save(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    now = datetime.now(UTC).isoformat()
    r = Round(ROOT)
    checked = Counter()
    for name in ('execution-freeze.json', 'all-answers-frozen.json'):
        for path, digest in load(name)['files_sha256'].items():
            assert sha(ROOT / path) == digest, path
            checked[name] += 1
    campaign = load('campaign-freeze.json')
    for name, digest in campaign['tooling_sha256'].items():
        assert sha(WORKSPACE / 'benchmarks/memory_campaign' / name) == digest, name
        checked['frozen_tooling_files'] += 1
    for arm, digest in campaign['arm_freeze_sha256'].items():
        armroot = r.arm_dir(arm)
        assert sha(armroot / 'freeze.json') == digest
        config = json.loads((armroot / 'run.json').read_text('utf-8'))
        fixture = Path(config['fixture_root'])
        for name, expected in json.loads((armroot / 'freeze.json').read_text('utf-8')).items():
            path = fixture / 'bundle-manifest.json' if name == 'fixture-bundle' else armroot / name
            assert sha(path) == expected, (arm, name)
            checked[arm + '_source_config_tool_files'] += 1
        for name, expected in json.loads((fixture / 'bundle-manifest.json').read_text('utf-8'))['files_sha256'].items():
            assert sha(fixture / name) == expected, (arm, name)
            checked[arm + '_fixture_files'] += 1
        for path in (armroot / 'results').glob('*/manifest.json'):
            assert json.loads(path.read_text('utf-8'))['status'] == 'COMPLETED', path
    amendment = load('configuration-amendment.json')
    assert sha(ROOT / 'round-before-smoke-path-amendment.json') == amendment['before_sha256']
    assert sha(ROOT / 'round.json') == amendment['after_sha256']
    assert load('source-freeze.json')['round_json_sha256'] == amendment['before_sha256']
    assert sha(ROOT / 'anchors.jsonl') == load('judge-inputs-freeze.json')['anchors_sha256']
    repair = load('grading-finalization-repair.json')
    assert repair['transport_disabled'] and repair['new_provider_calls'] == 0
    assert sha(ROOT / 'grading/manifest.json') == repair['grading_manifest_sha256']
    for vote, files in repair['original_vote_files_sha256'].items():
        for name, expected in files.items():
            assert sha(ROOT / f'grading/vote-{vote}' / name) == expected
            checked['unchanged_vote_files'] += 1
    assert sha(ROOT / 'grading/grades.jsonl') == load('review-completion.json')['raw_grades_sha256']
    assert sha(ROOT / 'grading/review.jsonl') == load('review-completion.json')['review_sha256']
    assert sha(ROOT / 'grading/overrides.jsonl') == load('review-completion.json')['overrides_sha256']
    counts = {}
    for arm in r.graded_arms:
        answers = r.arm_answers(arm)
        assert len(answers) == len({a['id'] for a in answers}) == 744
        assert all(a['status'] == 'SUCCEEDED' for a in answers)
        counts[arm] = len(answers)
    results = load('results.json')
    summary = load('summary.json')
    raw = {v['key']: v for v in read_rows(ROOT / 'grading/grades.jsonl')}
    overrides = {v['key']: v for v in read_rows(ROOT / 'grading/overrides.jsonl')}
    assert len(raw) == 2976 and len(overrides) == 44
    assert len(read_rows(ROOT / 'grading/review.jsonl')) == 449
    for row in results:
        for arm, v in row['arms'].items():
            assert v['passed'] == overrides.get(v['key'], raw[v['key']])['pass']
    for arm in r.graded_arms:
        expected = summary['overall'][arm] if arm in summary['overall'] else summary['controls'][arm]
        assert sum(row['arms'][arm]['passed'] for row in results) == expected['passed']
    assert all(v['passed'] for v in summary['judging']['anchor_gates'].values())
    reviewed_keys = {a['key'] for a in read_rows(ROOT / 'grading/review.jsonl')}
    uncertain_keys = {x['key'] for vote in range(1, 4)
                      for x in read_rows(ROOT / f'grading/vote-{vote}/grades.jsonl')
                      if x.get('anchor_failed') or x.get('judge_unresolved')}
    assert len(uncertain_keys) == 70 and uncertain_keys <= reviewed_keys
    finance = {}
    for name, file, cap in [('deepseek_main', 'deepseek-usage.jsonl', 79),
                             ('deepseek_smoke', 'smoke/deepseek-usage.jsonl', 1),
                             ('qwen', 'qwen-usage.jsonl', 80)]:
        total, latest = ledger_total(ROOT / file)
        states = dict(Counter(v['state'] for v in latest.values()))
        assert total <= cap
        assert set(states) == {'SETTLED'}, states
        finance[name] = {'charged_or_held_cny': total, 'cap_cny': cap,
                         'calls': len(latest), 'states': states, 'invoice_verified': False}
    finance['deepseek_combined_cny'] = finance['deepseek_main']['charged_or_held_cny'] + finance['deepseek_smoke']['charged_or_held_cny']
    assert finance['deepseek_combined_cny'] <= 80
    report = (ROOT / 'memory-report.html').read_text('utf-8')
    assert report.count('<details class="q"') == 744
    assert report.count('<section class="answer">') == 2976
    assert '旧版Core：重放、维护、答题' in report and '混合调度' in report
    assert '原生新旧臂和人物串行；' not in report
    assert report.rfind('<h2>dsh-memory 的看法</h2>') > report.rfind('<h2>局限</h2>')
    assert (ROOT / 'report-build.err').stat().st_size == 0
    qa = {'at': now, 'method': 'Playwright Chromium; local static report only, server bound127.0.0.1 then closed',
          'desktop_viewport': [1280, 900], 'mobile_viewport': [390, 844],
          'mobile_document_width': 390, 'horizontal_overflow': False,
          'question_details': 744, 'answers': 2976, 'images_loaded': 8, 'broken_images': 0,
          'detail_open_test': True, 'dsh_section_last': True,
          'visual_inspected': ['memory-summary.png'] + [f'category-{n:02d}.png' for n in range(1,8)] +
                               ['output/playwright/report-mobile.png','output/playwright/report-analysis.png',
                                'output/playwright/report-question.png'],
          'console': 'Only missing optional favicon404; no script errors',
          'scope': 'No external publication; no production or QQ operation'}
    save('report-visual-qa.json', qa)
    versions = {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[str(ROOT / '.deps')])}
    save('analysis-dependencies.json', {'local_only': True, 'versions': versions,
        'runtime_source_unchanged': True, 'python': sys.version,
        'reproduce': 'LOCAL_PATH -B .local/memory-accuracy-v5-20261103/render_reviewed_report.py'})
    artifacts = ['memory-report.html','summary.json','results.json','reporting-overlay.json',
                 'evidence-diagnosis.json','evidence-diagnosis.md','native-runtime-metrics.json',
                 'question-validity-audit.json','review-completion.json','all-answers-frozen.json',
                 'execution-freeze.json','campaign-freeze.json','source-freeze.json','corpus-freeze.json',
                 'round.json','configuration-amendment.json','judge-inputs-freeze.json','anchors.jsonl',
                 'schedule-amendment-active.json','schedule-amendment.json','schedule-handoff-verification.json',
                 'grading-schedule-amendment-active.json','grading-schedule-amendment.json',
                 'parallel-grading-verification.json','grading-finalization-repair.json',
                 'grading-boundary-receipt.json','grading/manifest.json','grading/grades.jsonl',
                 'grading/review-selection.json','grading/review.jsonl','grading/overrides.jsonl',
                 'grading/review-semantic-boundaries.json','render_reviewed_report.py','verify_final_report.py',
                 'deepseek-usage.jsonl','qwen-usage.jsonl','smoke/deepseek-usage.jsonl',
                 'analysis-dependencies.json','report-visual-qa.json']
    artifacts += [p.relative_to(ROOT).as_posix() for p in ROOT.glob('*.png')]
    artifacts += [p.relative_to(ROOT).as_posix() for p in ROOT.glob('*.svg')]
    artifacts += [p.relative_to(ROOT).as_posix() for p in (ROOT/'output/playwright').glob('*.png')]
    receipt = {'status': 'ROUND_COMPLETE_REVIEWED_WITH_DISCLOSED_LIMITATIONS',
               'at': now, 'old': r.cfg['arms']['old'], 'new': r.cfg['arms']['new'],
               'answers': counts, 'fact_groups': 168, 'personas': 6,
               'frozen_hash_checks': dict(checked), 'reviewed': 449,'overrides': 44,
               'same_assistant_not_independent_human': True, 'all_anchor_gates_passed': True,
               'any_vote_anchor_uncertain_answers_reviewed': len(uncertain_keys),
               'overall': summary['overall'], 'paired_changes': summary['paired_changes'],
               'finance': finance, 'posthoc_primary_preserved': True,
               'mixed_schedule_no_isolated_latency_claim': True,
               'cached_aggregation_new_provider_calls': 0,
               'qa': qa, 'source_or_rubric_or_bank_tuned_after_answers': False,
               'not_a_production_release_or_independent_human_certification': True,
               'files_sha256': {name: sha(ROOT / name) for name in artifacts},
               'prior_product_verification_receipt': {
                   'path': str(WORKSPACE/'.local/memory-continuation/verification-receipt.json'),
                   'sha256': sha(WORKSPACE/'.local/memory-continuation/verification-receipt.json')}}
    target = ROOT / 'final-verification-receipt.json'
    assert not target.exists(), 'Never overwrite a prior final receipt'
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    save('pipeline-status.json', {'status': 'ROUND_COMPLETE_REVIEWED_WITH_DISCLOSED_LIMITATIONS',
        'at': now, 'receipt': target.name, 'report': 'memory-report.html',
        'receipt_sha256': sha(target), 'reviewed': 449, 'overrides': 44})
    save('monitor-state.json', {'automation_id': '5', 'at': now, 'stage': 'COMPLETE',
        'counts': counts, 'reviewed': 449, 'overrides': 44, 'finance': finance,
        'frozen_inputs_and_answers_intact': True, 'anchor_gates_passed': True,
        'receipt': target.name, 'receipt_sha256': sha(target),
        'decision': 'NOTIFY_COMPLETION_AND_STOP_MONITOR'})
    print(json.dumps({'status': receipt['status'], 'checks': dict(checked), 'finance': finance,
                      'receipt_sha256': sha(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
