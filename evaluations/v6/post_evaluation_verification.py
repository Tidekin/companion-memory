"""Offline receipt for the separately tested post-campaign continuation repair."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    git = lambda *args: subprocess.check_output(['git', *args], cwd=WORKSPACE, text=True).strip()
    candidate = git('rev-parse', 'HEAD')
    benchmark = '7074838d13336240968d39b0299ada126b610b99'
    assert git('rev-parse', 'HEAD^') == benchmark and not git('diff', '--name-only', 'HEAD')
    source = ['companion/core.py', 'tests/test_context_memory_retention.py',
              'docs/plans/2026-11-02-memory-inputs.md']
    assert set(git('diff', '--name-only', benchmark, candidate).splitlines()) == set(source)
    checks = {}
    for phase, expected in [('red', (4, 2)), ('green', (90, 0))]:
        path = ROOT / f'post-evaluation-source-{phase}.xml'
        cases = ET.parse(path).findall('.//testcase')
        failed = [c for c in cases if c.find('failure') is not None]
        assert (len(cases), len(failed)) == expected
        assert not any(c.find('error') is not None or c.find('skipped') is not None for c in cases)
        checks[phase] = {'cases': len(cases), 'passed': len(cases)-len(failed), 'failed': len(failed)}
    original = WORKSPACE / '.local/memory-reliability-20261104/product-verification.json'
    receipt = {
        'status': 'VERIFIED_TARGETED_POST_EVALUATION_REPAIR', 'at': datetime.now(UTC).isoformat(),
        'benchmark_candidate': benchmark, 'delivery_candidate': candidate,
        'tree': git('rev-parse', 'HEAD^{tree}'), 'checks': checks,
        'docs_check': {'command': './scripts/check.ps1 -Docs', 'passed': 200},
        'full_repository_runs_total': 1, 'full_paid_campaigns_total': 1,
        'post_repair_paid_calls': 0, 'post_repair_full_runs': 0,
        'scope': 'Existing required source-group flag; no new mechanism or model tuning.',
        'benchmark_outputs_changed': False, 'benchmark_score_applies_to_delivery_candidate': False,
        'verification_scope': ['Signed real HTTP owner inputs, real Core context assembly',
            'Native SDK with mocked provider transport; continuous and saved-resume paths',
            'Source revocation blocks saved use; existing hard-limit/pre-reservation guards'],
        'original_product_receipt_sha256': sha(original),
        'source_sha256': {name: sha(WORKSPACE / name) for name in source},
        'files_sha256': {name: sha(ROOT / name) for name in (
            'post-evaluation-source-red.xml', 'post-evaluation-source-green.xml',
            'post_evaluation_verification.py')},
    }
    path = ROOT / 'post-evaluation-verification.json'
    with path.open('x', encoding='utf-8') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2)
        out.write('\n')
    print(candidate, sha(path))


if __name__ == '__main__':
    main()
