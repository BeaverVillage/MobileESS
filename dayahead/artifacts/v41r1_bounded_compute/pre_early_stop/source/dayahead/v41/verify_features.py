"""Independent equality check against saved R6 feature matrices."""
import numpy as np
import pandas as pd
from .workload import features, R5OUT, R6OUT
from .data import atomic_json
from .preflight import OUT, record


def main():
    bins = pd.read_parquet(R5OUT / 'inputs/arrival_bins_with_maturity.parquet')
    jobs = pd.read_parquet(R5OUT / 'inputs/GPU_related_candidates_preMay.parquet')
    work = jobs[jobs.model_cohort].copy()
    target = pd.read_parquet(R6OUT / 'V40R6_CUMULATIVE_TARGET.parquet')
    expected = np.load(R6OUT / 'features.npz')['X']
    rows = []
    # Cover all frozen target days whose full lag support exists in the input.
    for day in target.day.unique():
        from .data import issue_time
        if issue_time(day) + pd.Timedelta(hours=6, days=-28) < bins.index.min():
            continue
        got = features(day, bins, work)
        wanted = expected[target[(target.day == day) & (target.horizon == 'H4')].index]
        mismatch = np.argwhere(got != wanted)
        row = dict(day=day, elements=got.size, exact_equal=not len(mismatch),
                   max_abs_error=float(np.max(np.abs(got - wanted))))
        if len(mismatch):
            names = np.load(R6OUT / 'features.npz')['feature_names']
            row['examples'] = [{'window': int(k), 'feature': str(names[c]),
                                'new': float(got[k, c]), 'frozen': float(wanted[k, c])}
                               for k, c in mismatch[:8]]
        rows.append(row)
    result = dict(status='PASS' if rows and all(r['exact_equal'] for r in rows) else 'FAIL',
                  days=len(rows), rows=rows, frozen_feature_source=record(R6OUT / 'features.npz'))
    atomic_json(OUT / 'V41_H4_FEATURE_REPRODUCTION_AUDIT.json', result)
    print(result['status'], 'days', len(rows), 'failed', sum(not r['exact_equal'] for r in rows), flush=True)
    for row in rows:
        if not row['exact_equal']:
            print(row, flush=True)
            break
    if result['status'] != 'PASS':
        raise RuntimeError('FROZEN_R6_FEATURE_REPRODUCTION_FAILED')


if __name__ == '__main__':
    main()
