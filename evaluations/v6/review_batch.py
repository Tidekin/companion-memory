"""Offline review worksheet. Records only explicit assistant decisions; never infers grades."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'grading'


def read(name):
    return json.loads((ROOT / name).read_text('utf-8'))


def rows(name):
    path = ROOT / name
    return [json.loads(line) for line in path.read_text('utf-8').splitlines() if line.strip()] \
        if path.exists() else []


def materials():
    assert (ROOT / 'manifest.json').exists()
    groups = {}
    worklist = read('review-worklist.json')
    if (ROOT / 'review-boundary-selection.json').exists():
        worklist += read('review-boundary-selection.json')
    assert len(worklist) == len({item['key'] for item in worklist})
    for item in worklist:
        # Only the same exact question instance can share an inspection across arms.
        value = {key: item[key] for key in ('id', 'question', 'required', 'forbidden', 'answer')}
        digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if digest not in groups:
            groups[digest] = {'index': len(groups), 'material_sha256': digest, **value, 'members': []}
        groups[digest]['members'].append({key: item[key] for key in (
            'key', 'arm', 'answer_sha256', 'auto_grade')})
    result = list(groups.values())
    path = ROOT / 'review-materials.json'
    if path.exists():
        previous = read(path.name)
        assert result[:len(previous)] == previous
        if len(previous) != len(result):
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    else:
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    return result


def record(groups, path):
    decisions = json.loads(Path(path).read_text('utf-8'))
    decisions = [{**item, 'index': index} for item in decisions
                 for index in item.get('indices', [item.get('index')])]
    existing = {row['key']: row for row in rows('review.jsonl')}
    raw = {row['key']: row for row in rows('grades.jsonl')}
    added = changed = 0
    for decision in decisions:
        index, passed, reason = decision['index'], decision['pass'], decision['reason']
        assert type(index) is int and type(passed) is bool and reason.strip()
        group = groups[index]
        assert group['index'] == index
        for member in group['members']:
            key = member['key']
            assert member['auto_grade'] == raw[key]
            if key in existing:
                assert existing[key]['review_pass'] == passed and existing[key]['reason'] == reason
                continue
            review = {'key': key, 'review_pass': passed, 'reason': reason,
                      'answer_sha256': member['answer_sha256'],
                      'material_sha256': group['material_sha256'],
                      'at': datetime.now(UTC).isoformat(), 'reviewer': 'same_assistant',
                      'not_independent_human': True}
            with (ROOT / 'review.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(review, ensure_ascii=False) + '\n')
            existing[key] = review
            added += 1
            if passed != raw[key]['pass']:
                with (ROOT / 'overrides.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'key': key, 'pass': passed, 'reason': reason,
                                              'original_grade': raw[key]}, ensure_ascii=False) + '\n')
                changed += 1
    (ROOT / 'overrides.jsonl').touch(exist_ok=True)
    print(json.dumps({'new_reviews': added, 'new_overrides': changed, 'reviewed': len(existing)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--show', nargs=2, type=int)
    parser.add_argument('--record')
    args = parser.parse_args()
    groups = materials()
    if args.show:
        for group in groups[slice(*args.show)]:
            print(json.dumps({'i': group['index'], 'id': group['id'],
                'arms': [x['arm'] for x in group['members']],
                'auto': [x['auto_grade']['pass'] for x in group['members']],
                'question': group['question'], 'required': group['required'],
                'forbidden': group['forbidden'], 'answer': group['answer']}, ensure_ascii=False))
    elif args.record:
        record(groups, args.record)
    else:
        print(json.dumps({'question_answer_materials': len(groups),
                          'selected_keys': sum(len(group['members']) for group in groups)}))


if __name__ == '__main__':
    main()
