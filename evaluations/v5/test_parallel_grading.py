import asyncio
import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name('parallel_grading.py')
spec = importlib.util.spec_from_file_location('vote_scheduler_test', MODULE)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


def test_boundary_allows_first_vote_but_prevents_second_provider(tmp_path):
    gate = tmp_path / 'vote-2'
    scheduler.gate_next_vote(gate, 'owned')
    provider_calls = []

    async def judge(vote):
        (tmp_path / f'vote-{vote}').mkdir(exist_ok=True)
        provider_calls.append(vote)
        return {vote: True}

    async def original():
        return [await judge(vote) for vote in (1, 2, 3)]

    with pytest.raises(FileExistsError):
        asyncio.run(original())
    assert provider_calls == [1]
    with pytest.raises(FileExistsError):
        scheduler.gate_next_vote(gate, 'duplicate')
    assert gate.read_text() == 'owned'


def test_boundary_accepts_windows_codepage_without_mutating_evidence(tmp_path):
    log = tmp_path / 'grader.err'
    raw = 'FileExistsError: 文件已存在: vote-2'.encode('gbk')
    log.write_bytes(raw)
    scheduler.check_boundary_error(log)
    assert log.read_bytes() == raw
    log.write_bytes(b'RuntimeError: unrelated')
    with pytest.raises(AssertionError):
        scheduler.check_boundary_error(log)


def test_votes_overlap_and_failure_does_not_cancel_sibling(tmp_path):
    async def scenario():
        started = set()
        both = asyncio.Event()
        settled = []

        async def judge(config, cases, failures, lookup, out, seed, name):
            started.add(seed)
            if started == {2, 3}:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=2)
            if seed == 2:
                raise ValueError('saved failure')
            await asyncio.sleep(0)
            settled.append((seed, name))
            return {}

        with pytest.raises(RuntimeError, match='no automatic retry'):
            await scheduler.other_votes(judge, {}, [], [], {},
                                        {2: tmp_path / 'v2', 3: tmp_path / 'v3'})
        assert settled == [(3, 'qwen')]

    asyncio.run(scenario())


def test_promotion_requires_owned_gate_and_preserves_records(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, 'ROOT', tmp_path)
    gate = tmp_path / 'vote-2'
    source = tmp_path / 'parallel-vote-2'
    source.mkdir()
    (source / 'grades.jsonl').write_text('retained\n')
    scheduler.gate_next_vote(gate, 'owned')
    with pytest.raises(AssertionError, match='Unowned'):
        scheduler.promote_vote(gate, 'wrong', source, gate)
    assert source.is_dir() and gate.read_text() == 'owned'
    scheduler.promote_vote(gate, 'owned', source, gate)
    assert not source.exists()
    assert (gate / 'grades.jsonl').read_text() == 'retained\n'
