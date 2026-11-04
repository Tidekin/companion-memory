"""Round-only vote scheduling amendment; all judging uses the frozen grade.py."""
import asyncio
import importlib.util
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def gate_next_vote(path, payload):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(payload)


async def other_votes(judge, config, cases, failures, lookup, paths):
    # Await both even if one fails, so sibling provider requests are not cancelled.
    results = await asyncio.gather(
        judge(config, cases, failures, lookup, paths[2], 2, 'deepseek'),
        judge(config, cases, failures, lookup, paths[3], 3, 'qwen'),
        return_exceptions=True)
    errors = [repr(r) for r in results if isinstance(r, BaseException)]
    if errors:
        raise RuntimeError('Saved both vote outcomes; no automatic retry: ' + str(errors))
    return results


def promote_vote(gate, payload, source, destination):
    assert gate == destination and gate.is_file()
    assert gate.read_text('utf-8') == payload, 'Unowned boundary gate'
    assert source.is_dir() and source.resolve().is_relative_to(ROOT)
    assert destination.resolve().is_relative_to(ROOT)
    gate.unlink()
    source.rename(destination)


def load_grade():
    tools = ROOT.parents[1] / 'benchmarks/memory_campaign'
    os.chdir(ROOT)  # The existing toolkit resolves its fixed anchor path relative to cwd.
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location('parallel_existing_grade', tools / 'grade.py')
    grade = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grade)
    return grade


async def main():
    g = load_grade()
    import parallel_handoff as handles

    with g.FileLock(str(ROOT / 'grading-schedule-amendment.lock'), timeout=0):
        current = json.loads((ROOT / 'pipeline-status.json').read_text('utf-8'))
        assert current['status'] == 'RUNNING_BLIND_GRADING' and current['pid'] == 64876
        assert g.G['judges'] == ['deepseek', 'deepseek', 'qwen'] and len(g.ANCHORS) == 40
        assert g.sha(ROOT / 'anchors.jsonl') == (
            '205a7f5f8547d3710e3e84d901e042475e44962406b0c7493fa624ab4dd79882')
        assert g.sha(Path(g.__file__)) == json.loads((ROOT / 'campaign-freeze.json')
            .read_text('utf-8'))['tooling_sha256']['grade.py']
        assert not (ROOT / 'grading-schedule-amendment.json').exists()
        config, cases, failures = g.prepare()
        lookup = {r['key']: r for r in cases}
        assert not (g.OUT / 'vote-2').exists() and not (g.OUT / 'vote-3').exists()
        assert not (g.OUT / 'grades.jsonl').exists()
        old = handles.opened(64876)
        try:
            started = json.loads((ROOT / 'grading-run-started.json').read_text('utf-8'))
            assert abs((handles.born(old) - datetime.fromisoformat(started['at']))
                       .total_seconds()) < 5
            assert handles.code(old) == 259
            temporary = g.OUT / 'parallel'
            temporary.mkdir(exist_ok=False)
            paths = {2: temporary / 'vote-2', 3: temporary / 'vote-3'}
            payload = json.dumps({'purpose': 'Exclusive next-vote boundary',
                                  'operation': uuid.uuid4().hex,
                                  'old_grader': 64876, 'new_scheduler': os.getpid()})
            # judge() first calls out.mkdir(). This exclusive file stops the original
            # loop at vote2, after vote1 and before any vote2 provider request.
            gate_next_vote(g.OUT / 'vote-2', payload)
            receipt = {
                'status': 'ACTIVE', 'at': datetime.now(UTC).isoformat(),
                'reason': 'User requested concurrent independent judge votes',
                'pid': os.getpid(), 'existing_vote1_pid': 64876,
                'existing_vote1_created_at': handles.born(old).isoformat(),
                'existing_vote1_kept_running': True,
                'frozen_grade_source_sha256': g.sha(Path(g.__file__)),
                'scheduler_sha256': g.sha(Path(__file__)),
                'answers_freeze_sha256': g.sha(ROOT / 'all-answers-frozen.json'),
                'anchors_sha256': g.sha(ROOT / 'anchors.jsonl'),
                'judges': g.G['judges'], 'seeds': [1, 2, 3],
                'rules_anchors_retries_caps_unchanged': True,
                'vote_outputs': {'1': 'grading/vote-1', '2': 'grading/parallel/vote-2',
                                 '3': 'grading/parallel/vote-3'},
                'boundary_gate': payload,
                'expected_old_exit': 'FileExistsError at vote2 mkdir, before its first request',
            }
            g.save(ROOT / 'grading-schedule-amendment.json', receipt)
            g.save(ROOT / 'grading-schedule-amendment-active.json', receipt)
            g.save(ROOT / 'pipeline-status.json', {
                'status': 'RUNNING_PARALLEL_BLIND_GRADING', 'at': receipt['at'],
                'pid': os.getpid(), 'vote1_pid': 64876,
                'schedule_amendment': 'grading-schedule-amendment.json',
                'log': 'parallel-grading.log', 'error_log': 'parallel-grading.err'})
            print('Concurrent votes2/3 started; original vote1 remains running', flush=True)
            await other_votes(g.judge, config, cases, failures, lookup, paths)
            old_code = await asyncio.to_thread(handles.wait, old)
            vote1 = g.read_rows(g.OUT / 'vote-1/grades.jsonl')
            assert len(vote1) == len({r['key'] for r in vote1}) == g.R.answers_total
            assert old_code == 1
            error = (ROOT / 'grading-run.err').read_text('utf-8')
            assert 'FileExistsError' in error and 'vote-2' in error
            for vote in (2, 3):
                records = g.read_rows(paths[vote] / 'grades.jsonl')
                assert len(records) == len({r['key'] for r in records}) == g.R.answers_total
            # Preserve the original grader's intentional boundary failure as evidence.
            g.save(ROOT / 'grading-boundary-receipt.json', {
                'old_exit_code': old_code, 'vote1_complete': True,
                'before_vote2_provider_request': True,
                'stderr_sha256': g.sha(ROOT / 'grading-run.err'),
                'at': datetime.now(UTC).isoformat()})
            promote_vote(g.OUT / 'vote-2', payload, paths[2], g.OUT / 'vote-2')
            assert not (g.OUT / 'vote-3').exists()
            paths[3].rename(g.OUT / 'vote-3')
            temporary.rmdir()
            before = {name: len(g.read_rows(ROOT / f'{name}-usage.jsonl'))
                      for name in ('deepseek', 'qwen')}
            # Full cached votes: the unchanged finalizer validates and aggregates them.
            await g.main()
            after = {name: len(g.read_rows(ROOT / f'{name}-usage.jsonl')) for name in before}
            assert before == after, 'Cached aggregation unexpectedly made a provider call'
            receipt.update(status='COMPLETED', finished_at=datetime.now(UTC).isoformat(),
                           final_vote_outputs={str(v): f'grading/vote-{v}' for v in (1, 2, 3)},
                           aggregation_provider_calls=0)
            g.save(ROOT / 'grading-schedule-amendment.json', receipt)
            manifest = json.loads((g.OUT / 'manifest.json').read_text('utf-8'))
            g.save(ROOT / 'pipeline-status.json', {
                'status': manifest['status'], 'at': datetime.now(UTC).isoformat(),
                'pid': os.getpid(), 'grading_manifest': 'grading/manifest.json'})
        except BaseException as error:
            g.save(ROOT / 'pipeline-status.json', {
                'status': 'NEEDS_ATTENTION', 'at': datetime.now(UTC).isoformat(),
                'pid': os.getpid(), 'error_type': type(error).__name__, 'error': str(error)[:800],
                'schedule_amendment': 'grading-schedule-amendment.json'})
            raise
        finally:
            handles.kernel.CloseHandle(old)


if __name__ == '__main__':
    asyncio.run(main())
