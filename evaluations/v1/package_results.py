"""Package only named synthetic test materials; never credentials or databases."""
import hashlib
import json
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKTREE = BASE.parent/'worktrees/memory-benchmark-20261102'


def main():
    names = [
        'memory-report.html', 'memory-summary.png', 'memory-summary.svg',
        'result-summary.json', 'per-question-results.json', 'native-diagnostics.json',
        'verification-receipt.json', 'report-ui-verification.json', 'verification-tests.json', 'secondary-review.jsonl',
        'manual-grade-overrides.jsonl', 'secondary-review-comparison.json', 'secondary-review-initial.jsonl', 'secondary-review-freeze.json',
        'grading-recovery-receipt.json', 'grader-index-normalization-change.json', 'reference-judge-freeze-initial.json',
        'asr-observations.jsonl', 'asr-quality-audit.json', 'pricing-sources.json',
        'runtime-versions.json', 'budget-allocation.json', 'answers-frozen-before-grading.json',
        'runner-freeze-v2.json', 'reference-judge-freeze.json', 'parser-image.json', 'parser-verification.json',
        'build_suite.py', 'run_public_memory.py', 'run_suite.py', 'run_reference.py',
        'grade_suite.py', 'collect_diagnostics.py', 'generate_report.py',
        'make_summary_chart.py', 'transcribe_assets.py',
    ]
    selected = [(BASE/n, n) for n in names if (BASE/n).exists()]
    selected += [(p, str(p.relative_to(BASE))) for p in (BASE/'suite-v1').rglob('*') if p.is_file()]
    for directory in sorted((BASE/'native-final-v2').glob('P*')):
        for name in ['answers.jsonl', 'manifest.json', 'maintenance.jsonl', 'isolation.jsonl', 'turns-observed.jsonl']:
            selected.append((directory/name, str((directory/name).relative_to(BASE))))
    for folder, names in [
        ('reference-final-v1', ['answers.jsonl', 'manifest.json', 'deepseek-usage.jsonl', 'qwen-usage.jsonl']),
        ('grading-final-v1', ['grades.jsonl', 'manifest.json', 'judge-usage.jsonl', 'unanswered.jsonl']),
    ]:
        selected += [(BASE/folder/n, folder+'/'+n) for n in names if (BASE/folder/n).exists()]
    test = WORKTREE/'tests/test_custom_memory_suite_lifecycle.py'
    selected.append((test, 'checks/test_custom_memory_suite_lifecycle.py'))
    for name in ['memory-check.xml', 'mixed-final-check.xml', 'lifecycle-final-check.xml']:
        selected.append((WORKTREE/'.local'/name, 'checks/'+name))
    archive = BASE/'memory-benchmark-714-results.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, name in selected:
            assert path.is_file(), str(path)
            assert not any(part in {'.env', '千问Key.txt', 'known_hosts'} for part in path.parts)
            z.write(path, name.replace('\\', '/'))
        z.writestr('readme.txt',
            'Companion Core memory benchmark, source-pinned 2026-11-02.\n'
            'Open memory-report.html locally; media and per-question evidence are included.\n'
            '714 instances = 696 semantic QA + 18 native lifecycle checks, reported separately.\n'
            'This is a self-authored synthetic suite, not the private original 714-question benchmark.\n'
            'No credentials or SQLite databases are packaged. Raw transport logs remain in the local experiment directory.\n'
            'Runner sources are a fixed-version reproduction record; rerunning requires the original checkout/runtime, '
            'configured provider credentials, SSH parser image, dates and paid approval window.\n'
            'The mixed check receipt contains 12 superseded harness-fixture failures; media57 were reused, '
            'and the corrected portable lifecycle18 passed in lifecycle-final-check.xml. '
            'verification-tests.json selects the 96 distinct successful checks.\n')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        members = len(z.namelist())
    receipt = {'path': str(archive), 'bytes': archive.stat().st_size, 'members': members,
               'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (BASE/'package-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', 'utf-8')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
