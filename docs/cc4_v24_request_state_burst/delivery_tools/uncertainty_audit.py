"""Independent pooled-hour bootstrap and tied-score AP; no study imports."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['Q90_pinball', 'coverage', 'positive_coverage', 'burst_coverage', 'requirement_ratio',
         'detector_recall', 'precision', 'false_positive_rate', 'pinball_minus_2pct_margin', 'PR_AUC', 'predicted_high_risk_fraction']


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ap(y, p):
    labels, scores = np.asarray(y, bool).ravel(), np.asarray(p, float).ravel()
    assert labels.any() and np.isfinite(scores).all()
    order = np.argsort(-scores, kind='stable')
    labels, scores = labels[order], scores[order]
    ends = np.r_[np.flatnonzero(scores[:-1] != scores[1:]), len(labels) - 1]
    true_positive = np.cumsum(labels)[ends]
    return float(np.dot(np.diff(np.r_[0, true_positive]) / labels.sum(), true_positive / (ends + 1)))


def metrics(y, q, risk, burst):
    y, q, risk = (np.asarray(v).ravel() for v in [y, q, risk])
    pos, tail, gate = y > 0, y > burst, risk >= .01
    assert pos.any() and tail.any() and (~tail).any() and y.sum() > 0
    error = y - q
    return np.array([np.maximum(.9 * error, -.1 * error).mean(), (y <= q).mean(),
        (y[pos] <= q[pos]).mean(), (y[tail] <= q[tail]).mean(), q.sum() / y.sum(),
        gate[tail].mean(), tail[gate].mean() if gate.any() else 0., gate[~tail].mean(), ap(tail, risk), gate.mean()])


def delta(y, q, p, bq, bp, burst):
    candidate, base = metrics(y, q, p, burst), metrics(y, bq, bp, burst)
    difference = candidate - base
    return np.r_[difference[:8], candidate[0] - 1.02 * base[0], difference[8:]]


def main():
    complete = read(ROOT / 'EVALUATION_COMPLETE.json')
    freeze = read(ROOT / 'FINAL_SELECTION_FREEZE.json')
    protocol = read(ROOT / 'PROTOCOL.json')
    assert not (ROOT / 'UNCERTAINTY_AUDIT.json').exists()
    assert sha(ROOT / 'PREDICTIONS.parquet') == complete['prediction_sha256']
    assert sha(ROOT / 'FINAL_SELECTION_FREEZE.json') == complete['freeze_sha256']
    assert sha(ROOT / 'PROTOCOL.json') == freeze['protocol_sha256']
    for name, digest in freeze['code'].items(): assert sha(ROOT / name) == digest
    assert ap([1, 0], [.5, .5]) == .5 and np.isclose(ap([1, 0, 1], [.8, .7, .6]), 5 / 6)
    predictions = pd.read_parquet(ROOT / 'PREDICTIONS.parquet')
    recorded = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv')
    assert len(recorded) == 88 and not recorded.duplicated(['role', 'model', 'metric', 'block_observed_days']).any()
    assert set(recorded.role) == {'EXPOSED_EVALUATION', 'MAY_HISTORICAL'}
    assert set(recorded.model) == {'C1', 'C2'} and set(recorded.metric) == set(NAMES)
    assert set(recorded.block_observed_days) == {1, 7}
    assert protocol['bootstrap']['draws'] == 2000 and protocol['bootstrap']['block_observed_days'] == [1, 7]
    results, maximum_error, reference_days = [], 0., 0
    for role in sorted(recorded.role.unique()):
        subset = predictions[predictions.role.eq(role)]
        base = subset[subset.model.eq('C0')].sort_values(['day', 'hour'])
        n = base.day.nunique()
        assert len(base) == n * 24 and base.threshold.eq(.01).all()
        for day, frame in base.groupby('day'):
            reference = np.load(ROOT.parent / 'cc4_v23_burst_detector' / 'raw' / (day + '.npz'))['D1_BASE71_BALANCED']
            assert np.array_equal(frame.risk, reference)
            reference_days += 1
        y, bq, bp = [base[key].to_numpy().reshape(n, 24) for key in ['actual', 'Q90', 'risk']]
        for model in ['C1', 'C2']:
            frame = subset[subset.model.eq(model)].sort_values(['day', 'hour'])
            assert np.array_equal(frame[['day', 'hour', 'actual']], base[['day', 'hour', 'actual']])
            assert freeze['choices'][model]['config']['gate'] == .01 and frame.threshold.eq(.01).all()
            q, p = [frame[key].to_numpy().reshape(n, 24) for key in ['Q90', 'risk']]
            point = delta(y, q, p, bq, bp, protocol['burst_threshold']['value'])
            for block in [1, 7]:
                rng = np.random.default_rng(protocol['bootstrap']['seed'])
                samples = []
                for _ in range(2000):
                    starts = rng.integers(n, size=int(np.ceil(n / block)))
                    index = np.concatenate([(start + np.arange(block)) % n for start in starts])[:n]
                    samples.append(delta(y[index], q[index], p[index], bq[index], bp[index], protocol['burst_threshold']['value']))
                samples = np.asarray(samples)
                assert np.isfinite(samples).all()
                lo, hi = np.quantile(samples, [.025, .975], axis=0)
                for k, name in enumerate(NAMES):
                    row = recorded[recorded.role.eq(role) & recorded.model.eq(model) & recorded.metric.eq(name) & recorded.block_observed_days.eq(block)].iloc[0]
                    actual = np.array([point[k], lo[k], hi[k]])
                    expected = row[['delta', 'CI95_low', 'CI95_high']].to_numpy(float)
                    error = float(np.max(np.abs(actual - expected)))
                    assert np.allclose(actual, expected, atol=1e-9, rtol=2e-12), (role, model, name, block)
                    assert row.N_days == n and row.draws == 2000
                    maximum_error = max(maximum_error, error)
                    results.append(dict(role=role, model=model, metric=name, block=block, max_error=error))
    value = dict(PASS=True, time=pd.Timestamp.now(tz='UTC').isoformat(), rows_checked=len(results), bootstrap_draws_recomputed=16000,
        reference_days_checked=reference_days, max_absolute_difference=maximum_error, source_sha256=sha(__file__),
        prediction_sha256=sha(ROOT / 'PREDICTIONS.parquet'), uncertainty_sha256=sha(ROOT / 'PAIRED_UNCERTAINTY.csv'), findings=results,
        limits=['conditional on frozen forecasts', 'no multiplicity correction', 'selection/refit uncertainty excluded',
                'May exposed historical diagnostic', 'request-state archive proxy provenance UNVERIFIED/UNOBSERVED'])
    with (ROOT / 'UNCERTAINTY_AUDIT.json').open('x', encoding='utf-8') as stream: json.dump(value, stream, indent=2)
    print('UNCERTAINTY AUDIT PASS', len(results), maximum_error)


if __name__ == '__main__': main()
