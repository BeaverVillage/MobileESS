"""Fixed-family target-resolution study; only new offline evidence is written."""
import os
for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[key] = '1'
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import time
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'cc4_v2_hourly_future_workload'
PARENT = ROOT.parent / 'cc4_v24_request_state_burst'
REFIT = ROOT.parent / 'cc4_v21_causal_refit_hurdle'
Z = np.load(BASE / 'DATA.npz')
X, Y, DAYS = Z['X'], Z['y'], Z['days'].astype(str)
L = pd.read_csv(BASE / 'DAY_LEDGER.csv')
AV, ISS = pd.to_datetime(L.label_matured_at, utc=True), pd.to_datetime(L.issue_time, utc=True)
TR = np.flatnonzero(L.split.eq('TRAIN') & L.eligible)
OOS = np.flatnonzero(DAYS >= '2024-09-01')
H1 = np.load(REFIT / 'predictions/LGBM_weighted_c1_s20260924.npz')['q']
PARAMS = dict(num_leaves=15, learning_rate=.03, n_estimators=400, min_child_samples=50,
              n_jobs=1, deterministic=True, force_col_wise=True, random_state=20260924, verbosity=-1)
RESOLUTIONS = ['H1', 'H3', 'H6', 'CUM']
ROLES = ['DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION', 'MAY_HISTORICAL']
METHODS = ['AGGREGATED_H1', 'DIRECT']
SCALE = float(Y[TR].mean())
GAIN = .05
TOL = 1e-12
METRIC_NAMES = ['Q90_coverage', 'calibration_error', 'normalized_Q90_pinball',
                'requirement_ratio', 'high_load_coverage', 'positive_coverage', 'normalized_Q50_pinball']


def need(value, message):
    if not value: raise AssertionError(message)


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def now(): return pd.Timestamp.now(tz='UTC').isoformat()
def read(path): return json.loads((ROOT / path).read_text(encoding='utf-8'))


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series, pd.Index)): return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.bool_)): return value.item()
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp): return str(value)
    return value


def write(name, value):
    path = ROOT / name; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(clean(value), stream, ensure_ascii=False, indent=2, allow_nan=False)


def csv(name, rows):
    path = ROOT / (name + '.csv'); need(not path.exists(), 'IMMUTABLE ' + name)
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator='\n')


def spans(resolution):
    if resolution == 'CUM': return np.arange(24), np.zeros(24, int), np.arange(1, 25)
    width = int(resolution[1:]); starts = np.arange(0, 24, width)
    return starts + width - 1, starts, np.full(len(starts), width)


def aggregate(values, resolution):
    """Hour is axis1; works for labels and the two frozen marginal bounds."""
    need(values.shape[1] == 24, 'HOURLY_AXIS')
    if resolution == 'CUM': return np.cumsum(values, axis=1)
    width = int(resolution[1:])
    return values.reshape((len(values), 24 // width, width) + values.shape[2:]).sum(axis=2)


def thresholds(resolution):
    y = aggregate(Y[TR], resolution)
    if resolution == 'CUM': return np.array([np.quantile(col[col > 0], .95) for col in y.T])
    return np.full(y.shape[1], np.quantile(y[y > 0], .95))


def role_ids(role): return np.flatnonzero(L.split.eq(role) & L.eligible)
def membership(i): return np.flatnonzero((AV < ISS.iloc[i]) & (ISS < ISS.iloc[i]) & L.split.ne('PURGE'))
def weights(ids, i): return np.exp2(-np.maximum((ISS.iloc[i] - pd.to_datetime(DAYS[ids], utc=True)).total_seconds() / 86400, 0) / 30)


def guard(final=False):
    frozen = read('FINAL_SELECTION_FREEZE.json' if final else 'CODE_FREEZE.json')
    for name, digest in frozen['code'].items(): need(sha(ROOT / name) == digest, 'CODE_DRIFT ' + name)
    need(sha(ROOT / 'PROTOCOL.json') == frozen['protocol_sha256'], 'PROTOCOL_DRIFT')
    for name, digest in read('PREPARATION_RECEIPT.json')['artifacts'].items():
        need(sha(ROOT / name) == digest, 'PREPARATION_DRIFT ' + name)


def source_guard():
    for name, digest in read('SOURCE_MANIFEST.json')['files'].items():
        need(sha(ROOT.parent / name) == digest, 'SOURCE_DRIFT ' + name)


def register():
    need(not (ROOT / 'CODE_FREEZE.json').exists(), 'REGISTERED')
    need(np.isfinite(H1[OOS]).all(), 'H1_AUTHORITY_INCOMPLETE')
    need(read('RAW_TARGET_AUDIT.json')['PASS'], 'RAW_AUDIT_REQUIRED')
    prepared = np.load(ROOT / 'TARGETS.npz'); recorded_thresholds = read('HIGH_LOAD_THRESHOLDS.json')
    need(np.array_equal(prepared['days'].astype(str), DAYS), 'TARGET_DAY_DRIFT')
    need(recorded_thresholds['common_TRAIN_hourly_mean_GPUh'] == SCALE, 'NORMALIZER_DRIFT')
    for r in RESOLUTIONS:
        need(np.array_equal(prepared['y_' + r], aggregate(Y, r)), 'PREPARED_LABEL_DRIFT ' + r)
        need(np.array_equal(prepared['X_' + r], X[:, spans(r)[0]]), 'PREPARED_FEATURE_DRIFT ' + r)
        need(np.array_equal(prepared['span_' + r], spans(r)[2]) and np.array_equal(prepared['end_hour_' + r], spans(r)[0]), 'TARGET_SPAN_DRIFT ' + r)
        need(np.array_equal(np.broadcast_to(recorded_thresholds[r], len(spans(r)[0])), thresholds(r)), 'THRESHOLD_DRIFT ' + r)
    files = json.loads((PARENT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files']
    for row in json.loads((PARENT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['files']:
        files[PARENT.name + '/' + row['path']] = row['sha256']
    files[PARENT.name + '/DELIVERY_MANIFEST.json'] = sha(PARENT / 'DELIVERY_MANIFEST.json')
    for name in ['FEATURE_CONTRACT.json', 'HOURLY_DATASET.parquet', 'SOURCE_MANIFEST.json']:
        files[BASE.name + '/' + name] = sha(BASE / name)
    write('SOURCE_MANIFEST.json', dict(base_PR=70, base_commit='74e190bf38f75a8c091d514ba7686d6c4684bc87', files=files))
    source_guard()
    write('PROTOCOL.json', dict(time=now(), version='CC4-v2.5', parameters=PARAMS,
        target='Same raw full-lifetime future-arrival GPUh at D-1 18:00; fixed modeled UTC+10 clock',
        resolutions={r: dict(end_hours=spans(r)[0], start_hours=spans(r)[1], duration_hours=spans(r)[2],
            high_load_threshold=thresholds(r), threshold_positive_TRAIN_counts=(aggregate(Y[TR], r) > 0).sum(axis=0)) for r in RESOLUTIONS},
        high_load='Positive TRAIN empirical Q95; pooled per H1/H3/H6, per-prefix for CUM; strict > threshold',
        feature_adapter='Unchanged 71 feature values at block END hourly anchor. No lag/calendar/maturity aggregation. Legacy horizon_hours=1 and window_start_slot retain hourly-anchor semantics; actual span is metadata. Prefix length already encoded by target_hour/lead_hours.',
        temporal='Exact PR64 expanding/full-day strict maturity/non-PURGE membership; 30-day half-life; daily refit',
        training='One pooled model per resolution/quantile; log1p target, expm1 with nonnegative support and Q90>=Q50 only; same per-observation day weight. Smaller number of rows per day is a target-resolution effect; no weight rescaling.',
        H1='Exact frozen refitted raw LightGBM reused for DIRECT and AGGREGATED_H1; no model search/refit variability',
        baseline='Sum frozen hourly Q50/Q90 over block or prefix; sum of quantiles is NOT guaranteed aggregate quantile',
        CUM='Raw marginal prefix forecasts; no monotonic projection. Report downward-prefix violations; no coherent planning-curve claim.',
        normalizer=dict(value=SCALE, source='one frozen eligible TRAIN hourly mean GPUh',
            loss='mean_day mean_output(pinball/target duration)/TRAIN hourly mean; same denominator for every resolution/role'),
        reserve='Nonoverlap:sum bounds/sum labels; CUM primary=terminal24 ratio. Prefix ratios separately, NEVER sum prefix bounds as reserve.',
        selection='DEV and CAL separately: primary ratio<2; high-load coverage>=H1+0.05; normalizedQ90pinball<=H1. Overall88..92 is preferred, not hard. Choose one eligible method per H3/H6/CUM; if none choose least-deficit research method with eligible=false. Rank by both-role coverage-band preference, mean calibration error, negative minimum high-load gain, mean normalized loss, mean reserve, fixed DIRECT-before-AGGREGATED_H1 tie. Primary resolution selected only among eligible frozen family choices; otherwise H1. No evaluation reselection.',
        support='For each DEV/CAL-eligible frozen family choice: require point gates in BOTH Dec-Feb and May, and 7-day CI lower(high-load difference vsH1)>0 and upper(normalized pinball difference vsH1)<=0 in BOTH. AGGREGATED_CC4_TARGET_SUPPORTED if any preregistered family passes. No evaluation reranking or promotion; primary selection stays frozen. Robust +5pp CI support reported separately. If all three fail, stop CC4 ML development and retain frozen interface.',
        method_effect='Direct-vs-summedH1 same-target contrasts reported separately; aggregation can be supported even if direct training does not beat summing. Cross-resolution high-load strata/outcomes differ; no hourly-predictor-superiority claim. Multiple unadjusted95% CIs are exploratory per-contrast conditional evidence, not simultaneous familywise confirmation.',
        bootstrap=dict(draws=2000, seed=20260927, blocks=[1, 7], unit='paired entire observed target day; all blocks/prefixes kept together',
            missing='nonfinite draws counted; any invalid draw makes the affected CI unavailable, never dropped or resampled'),
        May='already exposed historical diagnostic; never tuning', future_mature_labels='fixed prequential refit only, never selection',
        TEMPORAL_POLICY_CHANGED=False, FEATURE_FAMILY_CHANGED=False, ARCHITECTURE_CHANGED=False,
        provenance='inherited event-time proxy; ingestion/request-history UNVERIFIED/UNOBSERVED',
        PRODUCTION_PROMOTED=False, optimizer_executions=0))
    L.to_csv(ROOT / 'DAY_MEMBERSHIP.csv', index=False, lineterminator='\n')
    code = {name: sha(ROOT / name) for name in ['study.py', 'test_contract.py', 'prepare_targets.py', 'test_prepare_targets.py']}
    write('CODE_FREEZE.json', dict(time=now(), code=code, protocol_sha256=sha(ROOT / 'PROTOCOL.json')))


def fit_day(i):
    guard(); folder = ROOT / 'fits' / DAYS[i]
    if (folder / 'RECEIPT.json').exists(): return
    need(not folder.exists(), 'INCOMPLETE_FIT_FAIL_CLOSED')
    folder.mkdir(parents=True)
    tr = membership(i); w = np.asarray(weights(tr, i)); models = {}; predictions = {}
    np.savez_compressed(folder / 'TRAIN_MEMBERSHIP.npz', day_indices=tr, weights=w)
    for resolution in RESOLUTIONS[1:]:
        anchors, _, duration = spans(resolution); x = X[tr][:, anchors].reshape(-1, 71)
        y = aggregate(Y[tr], resolution).ravel(); sample_weight = np.repeat(w, len(anchors)); q = []
        for tau in [.5, .9]:
            booster = lgb.LGBMRegressor(objective='quantile', alpha=tau, **PARAMS).fit(x, np.log1p(y), sample_weight=sample_weight).booster_
            path = folder / f'{resolution}_Q{int(tau * 100)}.txt.gz'
            path.write_bytes(gzip.compress(booster.model_to_string().encode(), mtime=0))
            models[path.name] = sha(path)
            q.append(np.maximum(0, np.expm1(booster.predict(X[i, anchors], num_threads=1))))
        prediction = np.stack(q, axis=-1); prediction[:, 1] = np.maximum(prediction[:, 0], prediction[:, 1])
        need(np.isfinite(prediction).all(), 'NONFINITE_PREDICTION')
        predictions[resolution] = prediction
    raw = ROOT / 'raw' / (DAYS[i] + '.npz'); raw.parent.mkdir(exist_ok=True)
    np.savez_compressed(raw, **predictions)
    write(folder.relative_to(ROOT) / 'RECEIPT.json', dict(issue=ISS.iloc[i], day_index=i, training_days=len(tr),
        membership_sha256=sha(folder / 'TRAIN_MEMBERSHIP.npz'), latest_maturity=AV.iloc[tr].max(), models=models,
        prediction_sha256=sha(raw), model_rows={r: len(tr) * len(spans(r)[0]) for r in RESOLUTIONS[1:]}))
    print('FIT', DAYS[i], len(tr), flush=True)


def forecast(through):
    guard(); source_guard()
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as pool: list(pool.map(fit_day, map(int, OOS[DAYS[OOS] <= through])))


def predictions(through):
    out = {(r, 'AGGREGATED_H1'): aggregate(H1, r) for r in RESOLUTIONS}
    out[('H1', 'DIRECT')] = H1.copy()
    for r in RESOLUTIONS[1:]: out[(r, 'DIRECT')] = np.full((len(DAYS), len(spans(r)[0]), 2), np.nan)
    for i in OOS[DAYS[OOS] <= through]:
        raw = np.load(ROOT / 'raw' / (DAYS[i] + '.npz'))
        for r in RESOLUTIONS[1:]: out[(r, 'DIRECT')][i] = raw[r]
    return out


def daily_vector(y, q, resolution, threshold=None, duration=None, terminal=True):
    threshold = thresholds(resolution) if threshold is None else threshold
    duration = spans(resolution)[2] if duration is None else duration
    positive, high, covered = y > 0, y > threshold, y <= q[..., 1]
    e = y - q[..., 1]; loss = np.maximum(.9 * e, -.1 * e) / duration / SCALE
    median_loss = .5 * np.abs(y - q[..., 0]) / duration / SCALE
    reserve_y = y[:, -1] if resolution == 'CUM' and terminal else y.sum(axis=1)
    reserve_q = q[:, -1, 1] if resolution == 'CUM' and terminal else q[..., 1].sum(axis=1)
    return np.column_stack([np.full(len(y), y.shape[1]), covered.sum(axis=1), positive.sum(axis=1),
        (covered & positive).sum(axis=1), high.sum(axis=1), (covered & high).sum(axis=1),
        loss.sum(axis=1), reserve_y, reserve_q, median_loss.sum(axis=1)])


def summary(vector):
    total = vector.sum(axis=-2)
    with np.errstate(divide='ignore', invalid='ignore'):
        coverage = total[..., 1] / total[..., 0]
        return np.stack([coverage, np.abs(coverage - .9), total[..., 6] / total[..., 0],
            total[..., 8] / total[..., 7], total[..., 5] / total[..., 4], total[..., 3] / total[..., 2],
            total[..., 9] / total[..., 0]], axis=-1)


def metrics(y, q, resolution, threshold=None, duration=None, terminal=True):
    vector = daily_vector(y, q, resolution, threshold, duration, terminal)
    result = dict(zip(METRIC_NAMES, map(float, summary(vector))))
    error = y - q[..., 1]
    result.update(N_days=len(y), N_targets=y.size, actual_primary_GPUh=float(vector[:, 7].sum()),
        predicted_primary_GPUh=float(vector[:, 8].sum()), N_high_load=int(vector[:, 4].sum()),
        N_positive=int(vector[:, 2].sum()), Q90_pinball_GPUh=float(np.maximum(.9 * error, -.1 * error).mean()),
        Q50_pinball_GPUh=float((.5 * np.abs(y - q[..., 0])).mean()),
        prefix_downward_pairs_Q50=int((np.diff(q[..., 0], axis=1) < 0).sum()) if resolution == 'CUM' else 0,
        prefix_downward_pairs_Q90=int((np.diff(q[..., 1], axis=1) < 0).sum()) if resolution == 'CUM' else 0,
        max_prefix_drop_GPUh=float(max(0., -np.diff(q, axis=1).min())) if resolution == 'CUM' and q.shape[1] > 1 else 0.)
    return result


def criteria(candidate, hourly):
    need(np.isfinite([candidate[k] for k in METRIC_NAMES] + [hourly[k] for k in METRIC_NAMES]).all(), 'NONFINITE_GATE')
    high_deficit = max(0., hourly['high_load_coverage'] + GAIN - candidate['high_load_coverage'] - TOL)
    loss_deficit = max(0., candidate['normalized_Q90_pinball'] - hourly['normalized_Q90_pinball'] - TOL)
    ratio_deficit = max(0., candidate['requirement_ratio'] / 2 - 1)
    return high_deficit == 0 and loss_deficit == 0 and candidate['requirement_ratio'] < 2, high_deficit + loss_deficit + ratio_deficit


def rank_pair(rows, base):
    checks = [criteria(row, b) for row, b in zip(rows, base)]
    eligible = all(c[0] for c in checks)
    rank = (not eligible, 0. if eligible else sum(c[1] for c in checks),
        not all(.88 <= row['Q90_coverage'] <= .92 for row in rows),
        np.mean([row['calibration_error'] for row in rows]),
        -min(row['high_load_coverage'] - b['high_load_coverage'] for row, b in zip(rows, base)),
        np.mean([row['normalized_Q90_pinball'] for row in rows]), np.mean([row['requirement_ratio'] for row in rows]))
    return eligible, rank


def select():
    need(not (ROOT / 'FINAL_SELECTION_FREEZE.json').exists(), 'SELECTED'); guard()
    out = predictions('2024-11-30'); rows = []; scores = {}
    for role in ROLES[:2]:
        ids = role_ids(role)
        for (r, method), q in out.items():
            result = metrics(aggregate(Y[ids], r), q[ids], r); scores[(role, r, method)] = result
            rows.append(dict(role=role, resolution=r, method=method, **result))
    base = [scores[(role, 'H1', 'DIRECT')] for role in ROLES[:2]]; choices = {}
    for r in RESOLUTIONS[1:]:
        options = []
        for method in ['DIRECT', 'AGGREGATED_H1']:
            eligible, rank = rank_pair([scores[(role, r, method)] for role in ROLES[:2]], base)
            options.append((rank, 0 if method == 'DIRECT' else 1, method, eligible))
        rank, _, method, eligible = sorted(options)[0]
        choices[r] = dict(method=method, eligible=eligible, rank=rank)
    eligible_resolutions = [(v['rank'], RESOLUTIONS.index(r), r) for r, v in choices.items() if v['eligible']]
    primary = sorted(eligible_resolutions)[0][-1] if eligible_resolutions else 'H1'
    csv('SELECTION_METRICS', rows)
    write('FINAL_SELECTION_FREEZE.json', dict(time=now(), primary=primary, choices=choices,
        code=read('CODE_FREEZE.json')['code'], protocol_sha256=sha(ROOT / 'PROTOCOL.json'),
        selection_metrics_sha256=sha(ROOT / 'SELECTION_METRICS.csv'), evaluation_computed=False,
        no_evaluation_reranking=True, May='exposed historical diagnostic'))
    print('FROZEN', primary, choices, flush=True)


def paired(a, b, block):
    n = len(a); need(n == len(b), 'UNPAIRED_DAYS')
    rng = np.random.default_rng(20260927)
    starts = rng.integers(n, size=(2000, int(np.ceil(n / block))))
    ix = ((starts[:, :, None] + np.arange(block)) % n).reshape(2000, -1)[:, :n]
    draws = summary(a[ix]) - summary(b[ix]); point = summary(a) - summary(b); result = []
    for k, name in enumerate(METRIC_NAMES):
        invalid = int((~np.isfinite(draws[:, k])).sum())
        low, high = (np.nan, np.nan) if invalid else np.quantile(draws[:, k], [.025, .975])
        result.append(dict(metric=name, delta=point[k], CI95_low=low, CI95_high=high,
            nonfinite_draws=invalid, draws=2000, block_observed_days=block, N_days=n))
    return result


def support_decision(metrics_frame, intervals, frozen):
    """Pre-registered frozen-family research disposition; no evaluation re-selection."""
    gates, supported = [], []
    for r, choice in frozen['choices'].items():
        method = choice['method']; family_pass = bool(choice['eligible'])
        for role in ROLES[2:]:
            m = metrics_frame[metrics_frame.role.eq(role) & metrics_frame.resolution.eq(r) & metrics_frame.method.eq(method)].iloc[0]
            h = metrics_frame[metrics_frame.role.eq(role) & metrics_frame.resolution.eq('H1') & metrics_frame.method.eq('DIRECT')].iloc[0]
            point, _ = criteria(m, h)
            ci = intervals[intervals.role.eq(role) & intervals.resolution.eq(r) & intervals.method.eq(method)
                & intervals.contrast.eq('RESOLUTION_EFFECT') & intervals.block_observed_days.eq(7)].set_index('metric')
            high, loss = ci.loc['high_load_coverage'], ci.loc['normalized_Q90_pinball']
            available = high.nonfinite_draws == 0 and loss.nonfinite_draws == 0 and np.isfinite([high.CI95_low, loss.CI95_high]).all()
            direction = bool(available and high.CI95_low > 0 and loss.CI95_high <= TOL)
            family_pass = family_pass and point and direction
            gates.append(dict(resolution=r, method=method, role=role, eligible_at_freeze=choice['eligible'],
                point_gate=point, ratio_under_2=m.requirement_ratio < 2,
                high_load_gain=m.high_load_coverage - h.high_load_coverage,
                normalized_pinball_delta=m.normalized_Q90_pinball - h.normalized_Q90_pinball,
                preferred_coverage=.88 <= m.Q90_coverage <= .92, directional_7day_CI=direction,
                robust_five_pp_gain=bool(available and high.CI95_low >= GAIN),
                direct_cum_prefix_coherent=bool(m.prefix_downward_pairs_Q50 == 0 and m.prefix_downward_pairs_Q90 == 0)))
        if family_pass: supported.append(r)
    return gates, dict(AGGREGATED_CC4_TARGET_SUPPORTED=bool(supported), supported_frozen_families=supported,
        primary_frozen=frozen['primary'], primary_supported=frozen['primary'] in supported,
        PRODUCTION_REPLACEMENT_SUPPORTED=False, OPTIMIZER_INTEGRATION_READY=False, PRODUCTION_PROMOTED=False,
        CC4_ML_DEVELOPMENT_STOPPED=not supported, current_frozen_interface_retained=True,
        TEMPORAL_POLICY_CHANGED=False, FEATURE_FAMILY_CHANGED=False, ARCHITECTURE_CHANGED=False,
        claim='Exploratory per-contrast conditional historical target-resolution evidence; no simultaneous familywise95% guarantee, no hourly-predictor-superiority claim',
        May='exposed historical diagnostic; no tuning or evaluation reranking', provenance='UNVERIFIED/UNOBSERVED')


def evaluate():
    need(not (ROOT / 'EVALUATION_COMPLETE.json').exists(), 'EVALUATED'); guard(True); source_guard()
    out = predictions('2025-05-31'); rows, horizons, strata, intervals, frames = [], [], [], [], []
    for role in ROLES:
        ids = role_ids(role); vectors = {}
        for (r, method), allq in out.items():
            y, q = aggregate(Y[ids], r), allq[ids]; ends, starts, duration = spans(r)
            vectors[(r, method)] = daily_vector(y, q, r)
            rows.append(dict(role=role, resolution=r, method=method, **metrics(y, q, r)))
            for j in range(y.shape[1]):
                horizons.append(dict(role=role, resolution=r, method=method, block=j, start_hour=starts[j], end_hour=ends[j], duration=duration[j],
                    **metrics(y[:, j:j+1], q[:, j:j+1], r, thresholds(r)[j:j+1], duration[j:j+1])))
            for name, mask in [('zero', y == 0), ('positive', y > 0), ('high_load', y > thresholds(r))]:
                if not mask.any(): continue
                error = y[mask] - q[..., 1][mask]
                strata.append(dict(role=role, resolution=r, method=method, stratum=name, N=int(mask.sum()), coverage=float((error <= 0).mean()),
                    Q90_pinball_GPUh=float(np.maximum(.9 * error, -.1 * error).mean()),
                    normalized_Q90_pinball=float((np.maximum(.9 * (y - q[..., 1]), -.1 * (y - q[..., 1])) / duration / SCALE)[mask].mean())))
            frames.append(pd.DataFrame(dict(day=np.repeat(DAYS[ids], y.shape[1]), role=role, resolution=r, method=method,
                block=np.tile(np.arange(y.shape[1]), len(ids)), start_hour=np.tile(starts, len(ids)), end_hour=np.tile(ends, len(ids)),
                duration=np.tile(duration, len(ids)), actual=y.ravel(), Q50=q[..., 0].ravel(), Q90=q[..., 1].ravel(),
                high_load_threshold=np.tile(thresholds(r), len(ids)))))
        if role in ROLES[2:]:
            for r in RESOLUTIONS[1:]:
                contrasts = [('DIRECT', 'AGGREGATED_H1', r, 'SAME_TARGET_DIRECT_EFFECT'),
                    ('DIRECT', 'DIRECT', 'H1', 'RESOLUTION_EFFECT'), ('AGGREGATED_H1', 'DIRECT', 'H1', 'RESOLUTION_EFFECT')]
                for method, base_method, base_r, kind in contrasts:
                    for block in [1, 7]:
                        intervals.extend(dict(role=role, resolution=r, method=method, reference_resolution=base_r, reference_method=base_method,
                            contrast=kind, **value) for value in paired(vectors[(r, method)], vectors[(base_r, base_method)], block))
    for name, values in [('MODEL_METRICS', rows), ('HORIZON_METRICS', horizons), ('STRATIFIED_METRICS', strata), ('PAIRED_UNCERTAINTY', intervals)]: csv(name, values)
    gates, verdict = support_decision(pd.DataFrame(rows), pd.DataFrame(intervals), read('FINAL_SELECTION_FREEZE.json'))
    csv('GATES', gates); write('FINAL_VERDICT.json', verdict)
    pd.concat(frames, ignore_index=True).to_parquet(ROOT / 'PREDICTIONS.parquet', index=False)
    write('EVALUATION_COMPLETE.json', dict(time=now(), prediction_sha256=sha(ROOT / 'PREDICTIONS.parquet'),
        freeze_sha256=sha(ROOT / 'FINAL_SELECTION_FREEZE.json'), May='exposed historical diagnostic, never tuning'))


def verify():
    guard(True); source_guard(); frame = pd.read_parquet(ROOT / 'PREDICTIONS.parquet'); out = predictions('2025-05-31')
    proof = pd.read_parquet(BASE / 'FEATURE_MATURITY_PROOF.parquet')
    need((pd.to_datetime(proof.feature_available_at, utc=True) <= pd.to_datetime(proof.issue_time, utc=True)).all(), 'FEATURE_TIME')
    for i in OOS:
        folder = ROOT / 'fits' / DAYS[i]; receipt = read(folder.relative_to(ROOT) / 'RECEIPT.json'); saved = np.load(folder / 'TRAIN_MEMBERSHIP.npz'); tr = membership(i)
        need(np.array_equal(saved['day_indices'], tr) and np.array_equal(saved['weights'], weights(tr, i)), 'TRAINING_MEMBERSHIP')
        need((AV.iloc[tr] < ISS.iloc[i]).all(), 'IMMATURE_LABEL')
        need(sha(folder / 'TRAIN_MEMBERSHIP.npz') == receipt['membership_sha256'], 'MEMBERSHIP_BYTES')
        for name, digest in receipt['models'].items(): need(sha(folder / name) == digest, 'MODEL_BYTES')
        need(sha(ROOT / 'raw' / (DAYS[i] + '.npz')) == receipt['prediction_sha256'], 'RAW_BYTES')
    for role in ROLES:
        ids = role_ids(role)
        for (r, method), q in out.items():
            group = frame[frame.role.eq(role) & frame.resolution.eq(r) & frame.method.eq(method)]
            need(np.array_equal(group.day, np.repeat(DAYS[ids], len(spans(r)[0]))), 'EVALUATION_MEMBERSHIP')
            for column, value in [('actual', aggregate(Y[ids], r)), ('Q50', q[ids, :, 0]), ('Q90', q[ids, :, 1])]:
                need(np.array_equal(group[column], value.ravel()), 'FORECAST_DRIFT ' + column)
    need(np.isfinite(frame[['actual', 'Q50', 'Q90']]).all().all() and (frame.Q90 >= frame.Q50).all(), 'PREDICTION_SUPPORT')
    need(sha(ROOT / 'PREDICTIONS.parquet') == read('EVALUATION_COMPLETE.json')['prediction_sha256'], 'FINAL_PREDICTION_DRIFT')
    write('VALIDATION.json', dict(time=now(), PASS=True, fits=len(OOS) * 6, exact_day_memberships=len(OOS),
        prediction_rows=len(frame), source_features_unchanged=True, full_day_strict_maturity=True, raw_mass_audit=True,
        parent_evidence_unchanged=True, production_modified=False, proxy='UNVERIFIED/UNOBSERVED'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['register', 'development', 'select', 'evaluation', 'verify']); args = parser.parse_args()
    if args.stage == 'development': forecast('2024-11-30')
    elif args.stage == 'evaluation': guard(True); forecast('2025-05-31'); evaluate()
    else: globals()[args.stage]()
