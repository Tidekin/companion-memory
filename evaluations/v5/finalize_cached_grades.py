"""Finish cached judging after an orchestration-only Windows log decoding failure."""
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

import parallel_grading as scheduling

ROOT = Path(__file__).resolve().parent


async def main():
    g = scheduling.load_grade()
    with g.FileLock(str(ROOT / 'cached-grading-finalize.lock'), timeout=0):
        failed = json.loads((ROOT / 'pipeline-status.json').read_text('utf-8'))
        assert failed['status'] == 'NEEDS_ATTENTION'
        assert failed['error_type'] == 'UnicodeDecodeError'
        receipt = json.loads((ROOT / 'grading-schedule-amendment.json').read_text('utf-8'))
        assert g.sha(Path(g.__file__)) == receipt['frozen_grade_source_sha256']
        assert g.sha(ROOT / 'all-answers-frozen.json') == receipt['answers_freeze_sha256']
        assert g.sha(ROOT / 'anchors.jsonl') == receipt['anchors_sha256']
        config, cases, failures = g.prepare()
        expected = {r['key'] for r in cases} | {r['key'] for r in failures}
        assert len(expected) == g.R.answers_total == 2976
        paths = {int(v): ROOT / p for v, p in receipt['vote_outputs'].items()}
        originals = {}
        for vote, path in paths.items():
            records = g.read_rows(path / 'grades.jsonl')
            assert len(records) == len({r['key'] for r in records}) == len(expected)
            assert {r['key'] for r in records} == expected
            sent = {r['batch_id'] for r in g.read_rows(path / 'requests.jsonl')}
            answered = {r['batch_id'] for r in g.read_rows(path / 'responses.jsonl')}
            assert sent == answered, f'Vote{vote} has an unanswered attempted batch'
            originals[vote] = {name: g.sha(path / name) for name in (
                'grades.jsonl', 'requests.jsonl', 'responses.jsonl')}
        before = {name: len(g.read_rows(ROOT / f'{name}-usage.jsonl'))
                  for name in ('deepseek', 'qwen')}
        scheduling.check_boundary_error(ROOT / 'grading-run.err')
        assert (g.OUT / 'vote-2').read_text('utf-8') == receipt['boundary_gate']
        g.save(ROOT / 'grading-finalization-failure.json', failed)
        g.save(ROOT / 'grading-boundary-receipt.json', {
            'vote1_complete': True, 'before_vote2_provider_request': True,
            'stderr_sha256': g.sha(ROOT / 'grading-run.err'),
            'binary_ascii_markers_verified': True, 'at': datetime.now(UTC).isoformat()})
        scheduling.promote_vote(g.OUT / 'vote-2', receipt['boundary_gate'],
                                paths[2], g.OUT / 'vote-2')
        assert not (g.OUT / 'vote-3').exists()
        paths[3].rename(g.OUT / 'vote-3')
        paths[2].parent.rmdir()

        def forbid_provider(request):
            raise AssertionError('Cached finalization must not make provider requests')

        g.MeteredTransport = lambda *args, **kwargs: httpx.MockTransport(forbid_provider)
        await g.main()  # Original frozen parser, normalization, majority and anchor gates.
        after = {name: len(g.read_rows(ROOT / f'{name}-usage.jsonl')) for name in before}
        assert before == after
        for vote, hashes in originals.items():
            for name, digest in hashes.items():
                assert g.sha(g.OUT / f'vote-{vote}' / name) == digest
        receipt.update(status='COMPLETED', finished_at=datetime.now(UTC).isoformat(),
                       final_vote_outputs={str(v): f'grading/vote-{v}' for v in (1, 2, 3)},
                       aggregation_provider_calls=0,
                       finalization_repair='Binary-safe Windows stderr inspection; cached only')
        g.save(ROOT / 'grading-schedule-amendment.json', receipt)
        manifest = json.loads((g.OUT / 'manifest.json').read_text('utf-8'))
        g.save(ROOT / 'grading-finalization-repair.json', {
            'status': 'VERIFIED_CACHED_FINALIZATION', 'at': datetime.now(UTC).isoformat(),
            'cause': 'Windows OS error text used non-UTF8 console encoding',
            'transport_disabled': True, 'new_provider_calls': 0,
            'original_vote_files_sha256': originals,
            'original_grading_source_sha256': g.sha(Path(g.__file__)),
            'grading_manifest_sha256': g.sha(g.OUT / 'manifest.json')})
        g.save(ROOT / 'pipeline-status.json', {
            'status': manifest['status'], 'at': datetime.now(UTC).isoformat(),
            'pid': os.getpid(), 'grading_manifest': 'grading/manifest.json'})
        print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
