"""Independent saved-model, membership and gated-composition replay.

Reads source arrays and saved checkpoints directly; no study import, fitting,
threshold selection, or quality-metric optimization is performed.
"""
import os
for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']: os.environ[name] = '1'
from pathlib import Path
import gzip
import hashlib
import json
import math
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'cc4_v2_hourly_future_workload'
PARENT = ROOT.parent / 'cc4_v23_burst_detector'
BURST = 860.3532222222221
GATE = .01
TAUS = [.5, .75, .9]


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def equal(x, y, label): assert np.array_equal(np.asarray(x), np.asarray(y)), label


def main():
    assert (ROOT / 'EVALUATION_COMPLETE.json').exists() and not (ROOT / 'INDEPENDENT_AUDIT.json').exists()
    registered, frozen, complete = [read(ROOT / name) for name in ['CODE_FREEZE.json', 'FINAL_SELECTION_FREEZE.json', 'EVALUATION_COMPLETE.json']]
    assert registered['code'] == frozen['code']
    assert pd.Timestamp(registered['time']) <= pd.Timestamp(frozen['time']) <= pd.Timestamp(complete['time'])
    assert not frozen['evaluation_computed'] and frozen['no_detector_threshold_search']
    for name, digest in frozen['code'].items(): assert sha(ROOT / name) == digest, name
    assert sha(ROOT / 'PROTOCOL.json') == frozen['protocol_sha256'] == registered['protocol_sha256']
    assert sha(ROOT / 'SELECTION_METRICS.csv') == frozen['selection_metrics_sha256']
    assert sha(ROOT / 'FINAL_SELECTION_FREEZE.json') == complete['freeze_sha256']
    assert sha(ROOT / 'PREDICTIONS.parquet') == complete['prediction_sha256']
    sources = read(ROOT / 'SOURCE_MANIFEST.json')['files']
    for name, digest in sources.items(): assert sha(ROOT.parent / name) == digest, name
    for name, digest in read(ROOT / 'FEATURE_RECEIPT.json')['artifacts'].items(): assert sha(ROOT / name) == digest, name
    event_manifest = read(ROOT / 'REQUEST_EVENT_INDEX_MANIFEST.json')
    for item in event_manifest['files']: assert sha(ROOT / item['path']) == item['sha256'], item['path']
    authority = read(ROOT / 'FEATURE_RECEIPT.json')
    assert authority['request_version_provenance'] == 'UNVERIFIED' and authority['request_revision_history'] == 'UNOBSERVED'
    assert not authority['historical_value_equality_claimed'] and not authority['request_immutability_claimed']
    assert authority['production_readiness_fail_closed'] and authority['N_features'] == 661
    assert not read(ROOT / 'REQUEST_STATE_AUTHORITY_AUDIT.json')['REQUEST_STATE_AUTHORITY_VERIFIED']
    authorization = read(ROOT / 'REQUEST_STATE_PROXY_AUTHORIZATION.json')
    assert authorization['experiment_status'] == 'AUTHORIZED_OFFLINE_PROXY' and not authorization['REQUEST_STATE_AUTHORITY_VERIFIED']
    protocol = read(ROOT / 'PROTOCOL.json')
    assert protocol['detector']['gate'] == GATE and protocol['C2']['conditional_quantiles'] == TAUS
    data = np.load(BASE / 'DATA.npz')
    x, y, days = data['X'], data['y'], data['days'].astype(str)
    extended = np.load(ROOT / 'FEATURES.npz')['X']
    assert extended.shape == (443, 24, 661) and extended.dtype == np.float32
    assert len(read(ROOT / 'FEATURE_NAMES.json')) == 661
    equal(extended[:, :, :71], x, 'BASE_FEATURES')
    assert np.isfinite(extended).all()
    ledger = pd.read_csv(BASE / 'DAY_LEDGER.csv')
    equal(ledger.target_day, days, 'DAYS')
    issue, maturity = pd.to_datetime(ledger.issue_time, utc=True), pd.to_datetime(ledger.label_matured_at, utc=True)
    oos = np.flatnonzero(days >= '2024-09-01')
    assert len(oos) == 273 and set(frozen['choices']) == {'C1', 'C2'}
    train_threshold = np.flatnonzero(ledger.split.eq('TRAIN') & ledger.eligible)
    positive = y[train_threshold][y[train_threshold] > 0]
    assert float(np.quantile(positive, .95)) == BURST and (maturity.iloc[train_threshold] < issue.iloc[oos[0]]).all()
    c0 = np.load(ROOT.parent / 'cc4_v21_causal_refit_hurdle' / 'predictions' / 'LGBM_weighted_c1_s20260924.npz')['q']
    risk, reference = np.full(y.shape, np.nan), np.full(y.shape, np.nan)
    tail, supported = np.full((*y.shape, 3), np.nan), np.zeros(len(days), bool)
    n_models = 0; n_weights = 0
    for i in oos:
        indices = np.flatnonzero((maturity < issue.iloc[i]) & (issue < issue.iloc[i]) & ledger.split.ne('PURGE'))
        age = (issue.iloc[i] - pd.to_datetime(days[indices], utc=True)).total_seconds() / 86400
        weights = np.asarray(np.exp2(-np.maximum(age, 0) / 30))
        burst = y[indices].ravel() > BURST
        assert burst.any() and (~burst).any() and (maturity.iloc[indices] < issue.iloc[i]).all()
        hw = np.repeat(weights, 24)
        alpha = float(hw[~burst].sum() / hw[burst].sum())
        folder = ROOT / 'fits' / days[i]
        membership = np.load(folder / 'TRAIN_MEMBERSHIP.npz')
        equal(membership['day_indices'], indices, 'TRAIN_MEMBERSHIP')
        equal(membership['weights'], weights, 'TRAIN_WEIGHTS')
        equal(membership['burst_flat_indices'], np.flatnonzero(burst), 'BURST_MEMBERSHIP')
        n_weights += len(weights)
        receipt = read(folder / 'RECEIPT.json')
        assert receipt['alpha'] == alpha and receipt['day_index'] == int(i)
        assert receipt['N_train_days'] == len(indices) and receipt['N_burst_hours'] == int(burst.sum())
        assert receipt['N_burst_days'] == int((y[indices] > BURST).any(axis=1).sum())
        assert receipt['request_version_provenance'] == 'UNVERIFIED' and receipt['event_time_proxy_only']
        assert pd.Timestamp(receipt['issue']) == issue.iloc[i] and pd.Timestamp(receipt['latest_maturity']) == maturity.iloc[indices].max()
        assert sha(folder / 'TRAIN_MEMBERSHIP.npz') == receipt['membership_sha256']
        assert receipt['feature_sha256'] == sha(ROOT / 'FEATURES.npz')
        raw_path = ROOT / 'raw' / (days[i] + '.npz')
        assert sha(raw_path) == receipt['prediction_sha256']
        recorded = np.load(raw_path)
        model = lgb.Booster(model_str=gzip.decompress((folder / 'request_detector.txt.gz').read_bytes()).decode())
        assert model.num_feature() == extended.shape[2]
        probability = model.predict(extended[i], num_threads=1)
        assert np.isfinite(probability).all() and ((probability >= 0) & (probability <= 1)).all()
        risk[i] = probability / (alpha - (alpha - 1) * probability)
        assert np.isfinite(risk[i]).all() and ((risk[i] >= 0) & (risk[i] <= 1)).all()
        equal(recorded['risk'], risk[i], 'DETECTOR_REPLAY')
        reference[i] = np.load(PARENT / 'raw' / (days[i] + '.npz'))['D1_BASE71_BALANCED']
        assert np.isfinite(reference[i]).all() and ((reference[i] >= 0) & (reference[i] <= 1)).all()
        equal(recorded['reference_risk'], reference[i], 'REFERENCE_DETECTOR')
        support = int(burst.sum()) >= 50 and int((y[indices] > BURST).any(axis=1).sum()) >= 10
        assert support == receipt['tail_supported'] == bool(recorded['tail_supported'])
        supported[i] = support
        expected_models = {'request_detector.txt.gz'}
        tail[i] = BURST
        if support:
            for k, tau in enumerate(TAUS):
                name = 'request_tail_' + str(tau) + '.txt.gz'
                expected_models.add(name)
                model = lgb.Booster(model_str=gzip.decompress((folder / name).read_bytes()).decode())
                assert model.num_feature() == extended.shape[2]
                log_prediction = model.predict(extended[i], num_threads=1)
                magnitude = np.expm1(log_prediction)
                assert np.isfinite(log_prediction).all() and np.isfinite(magnitude).all()
                tail[i, :, k] = np.maximum(BURST, magnitude)
        tail[i] = np.maximum.accumulate(tail[i], axis=1)
        assert np.isfinite(tail[i]).all() and (tail[i] >= BURST).all() and (np.diff(tail[i], axis=1) >= 0).all()
        equal(recorded['tail'], tail[i], 'TAIL_REPLAY')
        assert set(receipt['models']) == expected_models
        for name, digest in receipt['models'].items(): assert sha(folder / name) == digest
        n_models += len(expected_models)
    outputs = {'C0': (c0.copy(), reference)}
    pool_entries = 0
    for name, candidate in frozen['choices'].items():
        assert candidate['config']['gate'] == GATE
        assert candidate['config']['family'] == name
        assert candidate['config']['tail_quantile'] in ([None] if name == 'C1' else TAUS)
        q = c0.copy(); proof = read(ROOT / (name + '_CALIBRATION_MEMBERSHIP.json'))
        assert len(proof) == (len(oos) if name == 'C1' else 0)
        for position, i in enumerate(oos):
            gate = risk[i] >= GATE
            if name == 'C1':
                previous = np.array([j for j in oos if j < i and maturity.iloc[j] < issue.iloc[i] and ledger.split.iloc[j] != 'PURGE'], int)
                d, h = np.where(risk[previous] >= GATE)
                pool_days = previous[d]
                scores = (y[previous] - c0[previous, :, 1])[risk[previous] >= GATE]
                enough = len(scores) >= 50 and len(np.unique(pool_days)) >= 10
                delta = max(0., float(np.sort(scores)[math.ceil(.9 * (len(scores) + 1)) - 1])) if enough else 0.
                equal(proof[position]['pool_day_indices'], pool_days, 'CAL_POOL_DAYS')
                equal(proof[position]['pool_hours'], h, 'CAL_POOL_HOURS')
                assert proof[position]['delta'] == delta and proof[position]['supported'] == enough
                assert proof[position]['day'] == days[i] and pd.Timestamp(proof[position]['issue']) == issue.iloc[i]
                q[i, gate, 1] += delta
                pool_entries += len(scores)
            elif supported[i]:
                q[i, gate, 1] = np.maximum(c0[i, gate, 1], tail[i, gate, TAUS.index(candidate['config']['tail_quantile'])])
        equal(q[oos, :, 0], c0[oos, :, 0], 'Q50_CHANGED')
        equal(q[oos][risk[oos] < GATE], c0[oos][risk[oos] < GATE], 'OUTSIDE_GATE_CHANGED')
        outputs[name] = (q, risk)
    final = pd.read_parquet(ROOT / 'PREDICTIONS.parquet')
    roles = ['DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION', 'MAY_HISTORICAL']
    assert set(final.model) == set(outputs) and set(final.role) == set(roles)
    assert not final.duplicated(['model', 'role', 'day', 'hour']).any()
    assert np.isfinite(final[['actual', 'Q50', 'Q90', 'risk']]).all().all()
    assert (final.Q90 >= final.Q50).all() and final.risk.between(0, 1).all()
    for name, (q, p) in outputs.items():
        for role in roles:
            ids = np.flatnonzero(ledger.split.eq(role) & ledger.eligible)
            frame = final[final.model.eq(name) & final.role.eq(role)]
            equal(frame.day, np.repeat(days[ids], 24), 'EVAL_DAY_MEMBERSHIP')
            equal(frame.hour, np.tile(np.arange(24), len(ids)), 'EVAL_HOUR_MEMBERSHIP')
            for column, values in [('actual', y[ids]), ('Q50', q[ids, :, 0]), ('Q90', q[ids, :, 1]), ('risk', p[ids])]: equal(frame[column], values.ravel(), column)
            assert frame.threshold.eq(GATE).all()
    result = dict(PASS=True, time=pd.Timestamp.now(tz='UTC').isoformat(), independent_source_sha256=sha(__file__),
        inherited_sources_checked=len(sources), exact_training_memberships=len(oos), exact_numeric_weights=n_weights,
        request_event_index_files_checked=len(event_manifest['files']), request_event_index_rows=event_manifest['total_indexed_rows'],
        feature_count=int(extended.shape[2]), feature_sha256=sha(ROOT / 'FEATURES.npz'),
        prediction_sha256=sha(ROOT / 'PREDICTIONS.parquet'), selection_freeze_sha256=sha(ROOT / 'FINAL_SELECTION_FREEZE.json'),
        exact_checkpoint_replays=n_models, maximum_replay_difference=0., exact_calibration_pools=len(oos),
        exact_calibration_entries=pool_entries, exact_prediction_rows=len(final), outside_gate_and_Q50_unchanged=True,
        source_imports_from_study=0, models_refitted=0, request_provenance='UNVERIFIED/UNOBSERVED',
        actual_historical_request_state_verified=False, user_authorized_offline_proxy=True)
    with (ROOT / 'INDEPENDENT_AUDIT.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    print('INDEPENDENT AUDIT PASS', len(oos), n_models, len(final))


if __name__ == '__main__': main()
