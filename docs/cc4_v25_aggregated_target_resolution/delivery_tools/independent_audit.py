"""Independent saved-model/target replay; no study imports or model fitting."""
import os
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '1'
from pathlib import Path
import gzip
import hashlib
import json
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'cc4_v2_hourly_future_workload'
REFIT = ROOT.parent / 'cc4_v21_causal_refit_hurdle'
PARENT = ROOT.parent / 'cc4_v24_request_state_burst'
RESOLUTIONS = ['H1', 'H3', 'H6', 'CUM']
ROLES = ['DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION', 'MAY_HISTORICAL']
ENDS = {'H1': np.arange(24), 'H3': np.arange(2, 24, 3), 'H6': np.arange(5, 24, 6), 'CUM': np.arange(24)}
WIDTHS = {'H1': np.ones(24, int), 'H3': np.full(8, 3), 'H6': np.full(4, 6), 'CUM': np.arange(1, 25)}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def equal(a, b, name): assert np.array_equal(np.asarray(a), np.asarray(b)), name


def sums(values, resolution):
    if resolution == 'CUM': return np.cumsum(values, axis=1)
    width = int(resolution[1:])
    return np.stack([values[:, begin:begin+width].sum(axis=1) for begin in range(0, 24, width)], axis=1)


def main():
    assert (ROOT / 'EVALUATION_COMPLETE.json').exists() and not (ROOT / 'INDEPENDENT_AUDIT.json').exists()
    code, frozen, complete = [read(ROOT / n) for n in ['CODE_FREEZE.json', 'FINAL_SELECTION_FREEZE.json', 'EVALUATION_COMPLETE.json']]
    assert code['code'] == frozen['code'] and not frozen['evaluation_computed'] and frozen['no_evaluation_reranking']
    assert pd.Timestamp(code['time']) <= pd.Timestamp(frozen['time']) <= pd.Timestamp(complete['time'])
    for name, digest in frozen['code'].items(): assert sha(ROOT / name) == digest, name
    assert sha(ROOT / 'PROTOCOL.json') == code['protocol_sha256'] == frozen['protocol_sha256']
    assert sha(ROOT / 'FINAL_SELECTION_FREEZE.json') == complete['freeze_sha256']
    assert sha(ROOT / 'SELECTION_METRICS.csv') == frozen['selection_metrics_sha256']
    assert sha(ROOT / 'PREDICTIONS.parquet') == complete['prediction_sha256']
    sources = read(ROOT / 'SOURCE_MANIFEST.json')['files']
    for name, digest in sources.items(): assert sha(ROOT.parent / name) == digest, name
    prep = read(ROOT / 'PREPARATION_RECEIPT.json')
    assert prep['PASS']
    for name, digest in prep['artifacts'].items(): assert sha(ROOT / name) == digest, name
    audit = read(ROOT / 'RAW_TARGET_AUDIT.json')
    assert audit['PASS'] and audit['maximum_hourly_label_difference_GPUh'] == 0
    assert not audit['labels_from_future_completion_used_as_features'] and audit['exact_original_daily_maturity']
    protocol = read(ROOT / 'PROTOCOL.json')
    assert protocol['parameters'] == read(REFIT / 'PROTOCOL.json')['parameters']
    assert not protocol['TEMPORAL_POLICY_CHANGED'] and not protocol['FEATURE_FAMILY_CHANGED'] and not protocol['ARCHITECTURE_CHANGED']
    base, prepared = np.load(BASE / 'DATA.npz', allow_pickle=False), np.load(ROOT / 'TARGETS.npz', allow_pickle=False)
    x, y, days = base['X'], base['y'], base['days'].astype(str)
    assert x.shape == (443, 24, 71) and x.dtype == np.float32
    ledger = pd.read_csv(BASE / 'DAY_LEDGER.csv')
    equal(days, ledger.target_day, 'BASE_DAY_ALIGNMENT'); equal(prepared['days'].astype(str), days, 'PREPARED_DAYS')
    issue, maturity = pd.to_datetime(ledger.issue_time, utc=True), pd.to_datetime(ledger.label_matured_at, utc=True)
    training = np.flatnonzero(ledger.split.eq('TRAIN') & ledger.eligible)
    oos = np.flatnonzero(days >= '2024-09-01'); assert len(oos) == 273
    thresholds = read(ROOT / 'HIGH_LOAD_THRESHOLDS.json')
    equal(thresholds['TRAIN_day_indices'], training, 'THRESHOLD_TRAIN_MEMBERSHIP')
    scale = float(y[training].mean())
    assert scale == thresholds['common_TRAIN_hourly_mean_GPUh'] == protocol['normalizer']['value']
    targets = {}
    for resolution in RESOLUTIONS:
        targets[resolution] = sums(y, resolution)
        equal(targets[resolution], prepared['y_'+resolution], 'EXACT_TARGET_'+resolution)
        equal(prepared['X_'+resolution], x[:, ENDS[resolution]], 'EXACT_ANCHOR_'+resolution)
        equal(prepared['end_hour_'+resolution], ENDS[resolution], 'ENDPOINT_'+resolution)
        equal(prepared['span_'+resolution], WIDTHS[resolution], 'SPAN_'+resolution)
        ty = targets[resolution][training]
        expected = np.array([np.quantile(col[col > 0], .95) for col in ty.T]) if resolution == 'CUM' else np.full(ty.shape[1], np.quantile(ty[ty > 0], .95))
        equal(np.broadcast_to(thresholds[resolution], ty.shape[1]), expected, 'TRAIN_THRESHOLD_'+resolution)
        equal(protocol['resolutions'][resolution]['high_load_threshold'], expected, 'PROTOCOL_THRESHOLD_'+resolution)
    assert thresholds['H1'] == 860.3532222222221
    jobs = pd.read_parquet(ROOT / 'RAW_TARGET_JOB_MEMBERSHIP.parquet')
    assert jobs.id.is_unique and not jobs.duplicated(['archive_member_index', 'archive_row_index']).any()
    groups = jobs.groupby('day_index', sort=True).indices
    for i in range(len(days)):
        selected = jobs.iloc[groups.get(i, np.array([], int))]
        equal(np.bincount(selected.hour.to_numpy(), weights=selected.work_GPUh.to_numpy(), minlength=24), y[i], 'RAW_JOB_REPLAY')
    h1 = np.load(REFIT / 'predictions/LGBM_weighted_c1_s20260924.npz')['q']
    outputs = {(r, 'AGGREGATED_H1'): sums(h1, r) for r in RESOLUTIONS}
    outputs[('H1', 'DIRECT')] = h1.copy()
    for r in RESOLUTIONS[1:]: outputs[(r, 'DIRECT')] = np.full((len(days), len(ENDS[r]), 2), np.nan)
    model_count, weight_count = 0, 0
    for i in oos:
        indices = np.flatnonzero((maturity < issue.iloc[i]) & (issue < issue.iloc[i]) & ledger.split.ne('PURGE'))
        age = (issue.iloc[i] - pd.to_datetime(days[indices], utc=True)).total_seconds() / 86400
        weights = np.asarray(np.exp2(-np.maximum(age, 0) / 30))
        assert (maturity.iloc[indices] < issue.iloc[i]).all()
        folder = ROOT / 'fits' / days[i]
        recorded_membership = np.load(folder / 'TRAIN_MEMBERSHIP.npz')
        equal(recorded_membership['day_indices'], indices, 'DAY_TRAIN_MEMBERSHIP')
        equal(recorded_membership['weights'], weights, 'EXACT_NUMERIC_WEIGHTS')
        inherited = np.load(PARENT / 'fits' / days[i] / 'TRAIN_MEMBERSHIP.npz')
        equal(inherited['day_indices'], indices, 'INHERITED_MEMBERSHIP')
        equal(inherited['weights'], weights, 'INHERITED_WEIGHTS')
        receipt = read(folder / 'RECEIPT.json')
        assert receipt['training_days'] == len(indices) and receipt['day_index'] == int(i)
        assert pd.Timestamp(receipt['issue']) == issue.iloc[i] and pd.Timestamp(receipt['latest_maturity']) == maturity.iloc[indices].max()
        assert sha(folder / 'TRAIN_MEMBERSHIP.npz') == receipt['membership_sha256']
        raw_path = ROOT / 'raw' / (days[i]+'.npz')
        assert sha(raw_path) == receipt['prediction_sha256']
        raw = np.load(raw_path)
        assert set(raw.files) == {'H3', 'H6', 'CUM'}
        expected_models = set()
        for resolution in RESOLUTIONS[1:]:
            prediction = []
            assert receipt['model_rows'][resolution] == len(indices)*len(ENDS[resolution])
            for tau in [.5, .9]:
                name = f'{resolution}_Q{int(tau*100)}.txt.gz'; expected_models.add(name)
                assert sha(folder / name) == receipt['models'][name]
                booster = lgb.Booster(model_str=gzip.decompress((folder / name).read_bytes()).decode())
                assert booster.num_feature() == 71 and booster.dump_model()['objective'].startswith('quantile')
                logq = booster.predict(x[i, ENDS[resolution]], num_threads=1)
                q = np.expm1(logq)
                assert np.isfinite(logq).all() and np.isfinite(q).all()
                prediction.append(np.maximum(0, q)); model_count += 1
            prediction = np.stack(prediction, axis=-1)
            prediction[:, 1] = np.maximum(prediction[:, 0], prediction[:, 1])
            equal(prediction, raw[resolution], 'EXACT_CHECKPOINT_REPLAY_'+resolution)
            outputs[(resolution, 'DIRECT')][i] = prediction
        assert set(receipt['models']) == expected_models
        weight_count += len(weights)
    final = pd.read_parquet(ROOT / 'PREDICTIONS.parquet')
    assert set(final.resolution) == set(RESOLUTIONS) and set(final.method) == {'DIRECT', 'AGGREGATED_H1'}
    assert set(final.role) == set(ROLES) and not final.duplicated(['role', 'resolution', 'method', 'day', 'block']).any()
    assert np.isfinite(final[['actual','Q50','Q90']]).all().all() and (final.Q50 >= 0).all() and (final.Q90 >= final.Q50).all()
    for role in ROLES:
        ids = np.flatnonzero(ledger.split.eq(role) & ledger.eligible)
        for (resolution, method), q in outputs.items():
            selected = final[final.role.eq(role) & final.resolution.eq(resolution) & final.method.eq(method)]
            count = len(ENDS[resolution]); starts = ENDS[resolution] + 1 - WIDTHS[resolution]
            equal(selected.day, np.repeat(days[ids], count), 'EVALUATION_DAY_ORDER')
            equal(selected.block, np.tile(np.arange(count), len(ids)), 'EVALUATION_BLOCK_ORDER')
            for field, values in [('start_hour', starts), ('end_hour', ENDS[resolution]), ('duration', WIDTHS[resolution]),
                                  ('high_load_threshold', np.broadcast_to(thresholds[resolution], count))]:
                equal(selected[field], np.tile(values, len(ids)), 'EVALUATION_METADATA_'+field)
            for field, values in [('actual', targets[resolution][ids]), ('Q50', q[ids,:,0]), ('Q90', q[ids,:,1])]:
                equal(selected[field], values.ravel(), 'EXACT_PREDICTION_'+field)
    assert model_count == 1638
    result = dict(PASS=True, time=pd.Timestamp.now(tz='UTC').isoformat(), source_sha256=sha(__file__),
        inherited_sources_checked=len(sources), preparation_artifacts_checked=len(prep['artifacts']),
        raw_target_job_rows_replayed=len(jobs), exact_hourly_labels_replayed=y.size, exact_training_memberships=len(oos),
        exact_numeric_weights=weight_count, exact_checkpoint_replays=model_count, maximum_replay_difference=0.,
        exact_prediction_rows=len(final), exact_base_features=71, full_day_maturity_unchanged=True,
        no_CUM_monotonic_projection=True, no_hourly_refit=True, model_refits=0, study_imports=0,
        prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'), freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),
        limitations=['changed target estimands','sum of marginal quantiles not guaranteed aggregate quantile',
                    'CUM marginal curves may lack coherence','UNVERIFIED/UNOBSERVED inherited event-time proxy'])
    with (ROOT/'INDEPENDENT_AUDIT.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    print('INDEPENDENT AUDIT PASS', len(oos), model_count, len(final))


if __name__ == '__main__': main()
