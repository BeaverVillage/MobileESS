"""Pending point-prediction ablation, independent of pooled/tail calibration."""
from common import *


def main():
    require((ROOT/'EVALUATION_COMPLETE.json').exists(), 'EVALUATION_NOT_COMPLETE')
    frame = pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    rows = []
    for role, panel in frame[frame.state.eq('PENDING')].groupby('role'):
        left = panel[panel.model.eq('MULTI_QUANTILE')]
        right = panel[panel.model.eq('MOE_POOLED')]
        joined = left[['job_issue_id', 'issue_time', 'actual_seconds', 'Q50']].merge(
            right[['job_issue_id', 'point']], on='job_issue_id', validate='one_to_one')
        require(len(joined) == len(left) == len(right), 'POINT_ABLATION_POPULATION')
        require(joined.actual_seconds.notna().all(), 'UNRESOLVED_POINT_LABEL')
        joined['candidate_abs_error'] = abs(joined.actual_seconds - joined.Q50)
        joined['reference_abs_error'] = abs(joined.actual_seconds - joined.point)
        days = joined.groupby('issue_time').agg(
            N=('job_issue_id', 'size'), candidate=('candidate_abs_error', 'sum'),
            reference=('reference_abs_error', 'sum')).to_numpy(float)
        n = len(days)
        totals = days.sum(axis=0)
        candidate = totals[1] / totals[0]
        reference = totals[2] / totals[0]
        for block in [1, 7]:
            rng = np.random.default_rng(20260926)
            bootstrap = []
            for _ in range(2000):
                starts = rng.integers(n, size=int(np.ceil(n / block)))
                indexes = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
                sample = days[indexes].sum(axis=0)
                bootstrap.append((sample[1] - sample[2]) / sample[0])
            low, high = np.quantile(bootstrap, [.025, .975])
            rows.append(dict(role=role, state='PENDING', N=len(joined), N_days=n,
                             candidate='MULTI_QUANTILE_raw_Q50', reference='MOE_raw_point',
                             candidate_MAE_seconds=candidate, reference_MAE_seconds=reference,
                             delta_MAE_seconds=candidate-reference, CI95_low=low, CI95_high=high,
                             block_issue_days=block, draws=2000, selection_used=False))
    pd.DataFrame(rows).to_csv(ROOT/'POINT_ARCHITECTURE_DIAGNOSTICS.csv', index=False)
    dump('POINT_ARCHITECTURE_DIAGNOSTICS_RECEIPT.json', dict(
        time=now(), input_sha256=sha(ROOT/'PREDICTIONS.parquet'), selection_used=False,
        scope='Pending total-runtime point MAE; same policy/cohort/OHE-SVD, before any residual correction',
        running_excluded_reason='Running also changes target formulation; not a pure model-family ablation'))


if __name__ == '__main__':
    main()
