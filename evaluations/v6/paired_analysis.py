"""Preregistered paired, clustered summaries over reviewed benchmark output."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ARMS = ('old', 'new', 'rag')
SEED = 20261104
REPETITIONS = 20000


def clustered(rows, field):
    groups = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    values = list(groups.values())
    counts = np.array([len(group) for group in values])
    passed = np.array([[sum(row['arms'][arm]['passed'] for row in group)
                        for arm in ARMS] for group in values])
    weights = np.random.default_rng(SEED).multinomial(
        len(values), np.full(len(values), 1 / len(values)), size=REPETITIONS)
    rates = (weights @ passed) / (weights @ counts)[:, None]
    delta = (rates[:, 1] - rates[:, 0]) * 100
    return {'cluster': field, 'clusters': len(values), 'repetitions': REPETITIONS,
            'seed': SEED, 'method': 'paired percentile cluster bootstrap, question-weighted ratio',
            'new_minus_old_points_95_ci': np.percentile(delta, [2.5, 97.5]).tolist(),
            'equal_cluster_weight_accuracy': dict(zip(
                ARMS, (passed / counts[:, None]).mean(axis=0).tolist()))}


def summarize(rows):
    changes = Counter('gain' if row['arms']['new']['passed'] else 'loss'
                      for row in rows
                      if row['arms']['old']['passed'] != row['arms']['new']['passed'])
    return {'instances': len(rows), 'fact_groups': len({r['dependency_group'] for r in rows}),
            'personas': len({r['persona'] for r in rows}), 'paired_changes': dict(changes),
            'accuracy': {arm: sum(r['arms'][arm]['passed'] for r in rows) / len(rows)
                         for arm in ARMS},
            'fact_group': clustered(rows, 'dependency_group'),
            'persona': clustered(rows, 'persona')}


def main():
    root = Path(sys.argv[sys.argv.index('--round') + 1]).resolve()
    source = root / 'results.json'
    rows = json.loads(source.read_text('utf-8'))
    assert len(rows) <= 800 and rows
    subsets = {'all': rows,
               'non_C17': [r for r in rows if r['category_id'] != 'C17'],
               'C28_chains': [r for r in rows if r['category_id'].startswith('C28')],
               'without_C28': [r for r in rows if not r['category_id'].startswith('C28')],
               'natural_C29_C30': [r for r in rows if r['category_id'] in ('C29', 'C30')]}
    output = {'results_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'interpretation': 'Exploratory: six personas and shared templates; no independent '
                               '792-sample or general-population causal claim.',
              'subsets': {key: summarize(value) for key, value in subsets.items()}}
    (root / 'paired-analysis.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({k: v['accuracy'] for k, v in output['subsets'].items()}))


if __name__ == '__main__':
    main()
