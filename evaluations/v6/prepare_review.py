"""Offline fixed review selection plus any-vote uncertainty; no grade mutation."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.argv = [__file__, '--round', str(ROOT)]
spec = importlib.util.spec_from_file_location(
    'v6_review_selection', WORKSPACE / 'benchmarks/memory_campaign/report.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def main():
    rows, grades = P.load()
    selected = P.prepare_review(rows, grades)
    extra = {x['key'] for n in (1, 2, 3)
             for x in P.read_rows(P.GRADING / f'vote-{n}/grades.jsonl')
             if x.get('anchor_failed') or x.get('judge_unresolved')}
    known = {x['key'] for x in selected}
    supplemental = []
    for row in rows:
        for arm, value in row['arms'].items():
            if value['key'] in extra - known:
                supplemental.append(dict(
                    key=value['key'], arm=arm, id=row['id'],
                    reason='any_vote_anchor_failed_or_judge_unresolved',
                    answer_sha256=value['answer_sha256'], question=row['question'],
                    category=row['category'], required=row['criteria']['required'],
                    forbidden=row['criteria'].get('forbidden', []),
                    answer=value['answer'], auto_grade=grades[value['key']]))
    for name, data in (('review-supplement-selection.json', supplemental),
                       ('review-worklist.json', selected + supplemental)):
        path = P.GRADING / name
        if path.exists():
            assert json.loads(path.read_text('utf-8')) == data, name
        else:
            P.save(path, data)
    print(json.dumps({'fixed_selection': len(selected), 'any_vote_uncertain': len(extra),
                      'additional_uncertain': len(supplemental),
                      'total_to_review': len(selected) + len(supplemental)}))


if __name__ == '__main__':
    main()
