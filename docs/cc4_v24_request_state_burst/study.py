"""CC4-v2.4: explicitly authorized offline request-state proxy experiment."""
import os
for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[key] = '1'
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / 'cc4_v23_burst_detector'
spec = importlib.util.spec_from_file_location('cc4_v23_readonly_reference', PARENT / 'study.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
Y, C0, L, DAYS, AV, ISS, TR, OOS = (getattr(prior, n) for n in ['Y', 'C0', 'L', 'DAYS', 'AV', 'ISS', 'TR', 'OOS'])
PARAMS = prior.PARAMS.copy()
BURST = prior.BURST
ROLES = prior.ROLES
GATE = .01
TAIL_LEVELS = [.5, .75, .9]
MEANINGFUL_DETECTOR_DELTA = .01
INCLUSIVE_TOLERANCE = 1e-12
FX = None


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def now():
    return pd.Timestamp.now(tz='UTC').isoformat()


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Index, pd.Series)): return [clean(v) for v in value]
    if isinstance(value, pd.Timestamp): return str(value)
    if isinstance(value, (np.integer, np.bool_)): return value.item()
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    return value


def write(name, value, exclusive=True):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(clean(value), stream, indent=2, ensure_ascii=False, default=str, allow_nan=False)


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def csv(name, rows):
    pd.DataFrame(rows).to_csv(ROOT / (name + '.csv'), index=False, lineterminator='\n')


def feature_data():
    global FX
    if FX is None:
        FX = np.load(ROOT / 'FEATURES.npz')['X']
    return FX


def source_guard():
    for name, digest in read('SOURCE_MANIFEST.json')['files'].items():
        require(sha(ROOT.parent / name) == digest, 'SOURCE_DRIFT ' + name)


def guard(final=False):
    frozen = read('FINAL_SELECTION_FREEZE.json' if final else 'CODE_FREEZE.json')
    for name, digest in frozen['code'].items(): require(sha(ROOT / name) == digest, 'CODE_DRIFT ' + name)
    require(sha(ROOT / 'PROTOCOL.json') == frozen['protocol_sha256'], 'PROTOCOL_DRIFT')
    for name, digest in read('FEATURE_RECEIPT.json')['artifacts'].items():
        require(sha(ROOT / name) == digest, 'FEATURE_OR_AUTHORITY_DRIFT ' + name)


def prepare():
    x = feature_data()
    require(x.shape[:2] == Y.shape and x.shape[2] > 71 and np.isfinite(x).all(), 'FEATURE_SHAPE_OR_FINITE')
    require(np.array_equal(x[:, :, :71], prior.Z['X']), 'BASE_FEATURE_CHANGED')
    require(len(read('FEATURE_NAMES.json')) == x.shape[2], 'FEATURE_NAMES')
    names = ['FEATURES.npz', 'FEATURE_NAMES.json', 'FEATURE_MEMBERSHIP.json',
             'FEATURE_AVAILABILITY_AUDIT.json', 'REQUEST_STATE_AUTHORITY_AUDIT.json',
             'REQUEST_STATE_PROXY_AUTHORIZATION.json', 'REQUEST_BINS.parquet',
             'REQUEST_EVENT_INDEX_MANIFEST.json', 'REQUEST_CATEGORY_VOCABULARY.json', 'request_features.py']
    write('FEATURE_RECEIPT.json', dict(time=now(), N_features=x.shape[2], artifacts={name: sha(ROOT / name) for name in names},
        boundary='D1_SCHEDULER_REQUEST_STATE_PROXY_V1', request_version_provenance='UNVERIFIED',
        request_revision_history='UNOBSERVED', historical_value_equality_claimed=False,
        request_immutability_claimed=False, production_readiness_fail_closed=True))


def register():
    require(not (ROOT / 'PROTOCOL.json').exists(), 'REGISTERED')
    files = dict(json.loads((PARENT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files'])
    for item in json.loads((PARENT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['files']:
        files[PARENT.name + '/' + item['path']] = item['sha256']
    files[PARENT.name + '/DELIVERY_MANIFEST.json'] = sha(PARENT / 'DELIVERY_MANIFEST.json')
    write('SOURCE_MANIFEST.json', dict(parent_PR=69, parent_commit='e672e4a81e22e9fdca3316f7e73611b39481faa6', files=files))
    source_guard()
    write('PROTOCOL.json', dict(time=now(), study='CC4-v2.4 Request-state Burst Forecast',
        May='exposed historical diagnostic; no untouched confirmation',
        user_authorized_boundary='Use archive request fields only as assumption-based scheduler-visible proxy under V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1; missing request-version authority does not stop offline experiment',
        provenance=dict(request_values_at_historical_issue='UNVERIFIED', revision_history='UNOBSERVED',
                        original_submission_immutability='NOT_CLAIMED', code_model_authority_is_not_historical_snapshot=True,
                        production_readiness_fail_closed=True),
        fixed_base='raw PR64 expanding + 30-day recency weighting + daily refit LightGBM, same predictions and training membership',
        target='unchanged next-day 24 hourly future lifetime GPU-work arrivals at D-1 18:00 modeled UTC+10',
        burst_threshold=dict(value=BURST, definition='unchanged TRAIN positive-hour Q95'),
        detector=dict(features='unchanged71 plus registered request-state features', parameters=PARAMS,
            class_weight='alpha=causal recency-weighted negative/positive mass; sample weights unchanged',
            score='inverse class-prior odds q/(alpha-(alpha-1)*q), not a probability calibration guarantee',
            gate=GATE, gate_selection='fixed0.01 for both C1/C2; no threshold search; equal to priorC2 and higher than priorC1'),
        reference_detector='PR69 D1_BASE71_BALANCED at matched fixed0.01 gate; old0.0025 only contextual reference',
        C1='same expanding mature earlier OOS high-risk C0 finite-rank Q90 residual correction; min50hours/10days else0',
        C2=dict(model='burst-only log1p multi-quantile LightGBM on registered request features', parameters=PARAMS,
                conditional_quantiles=TAIL_LEVELS, support='50bursthours/10days elseC0',
                operational_bound='max(C0Q90, conditional-tail quantile) only inside gate; Q50 unchanged; no unconditional-quantile guarantee'),
        selection=dict(hard='separatelyDEV/CAL: AP>=oldAP+.01, precision>=oldPrecision+.01, recall>=.60, burstcoverage>=.60, positivecoverage>=.85, ratio<2, pinball<=1.02*C0',
            meaningful_AP_precision_absolute_increment=MEANINGFUL_DETECTOR_DELTA, pinball_noninferiority_margin=.02,
            inclusive_comparison_absolute_tolerance=INCLUSIVE_TOLERANCE, strict_ratio_threshold_uses_no_tolerance=True,
            preferred='overall88..92 then detector/burst70% then lowest ratio then pinball',
            fallback='no feasible challenger =>retainC0; per-family minimum summed normalized deficits research candidate only',
            no_evaluation_reselection=True),
        bootstrap=dict(draws=2000, block_observed_days=[1, 7], seed=20260927, paired=True, fixed_forecast_conditional=True),
        execution=dict(independent_issue_workers=4, model_threads=1, deterministic=True),
        superiority_rule='DEV/CAL selected challenger plus hard gates in both diagnostic roles plus 7day CI AP/precision delta low>=.01, burst delta low>0, pinball2pctmargin high<=0; historical proxy scope only',
        stop_rule='If no frozen candidate meets meaningful ranking/precision and final forecast criteria, halt further hourly burst development; cumulative/3h/6h future research proposal only; no target change',
        evaluation_updates='earlier mature labels can enter only the frozen prequential refit/residual rules, never tuning',
        TEMPORAL_POLICY_CHANGED=False, BASE_MODEL_CHANGED=False, PRODUCTION_PROMOTED=False,
        optimizer_or_production_executions=0))
    shutil.copyfile(PARENT / 'DAY_MEMBERSHIP.csv', ROOT / 'DAY_MEMBERSHIP.csv')
    write('CODE_FREEZE.json', dict(time=now(), code={p.name: sha(p) for p in ROOT.glob('*.py') if p.name != 'delivery.py'},
                                  protocol_sha256=sha(ROOT / 'PROTOCOL.json')))


def fit_day(i):
    guard()
    path = ROOT / 'raw' / (DAYS[i] + '.npz')
    if path.exists(): return
    x = feature_data()
    train = prior.old.membership(i)
    daily_weights = np.asarray(prior.old.weights(train, i))
    weights = np.repeat(daily_weights, 24)
    labels = Y[train].ravel()
    burst = labels > BURST
    require((AV.iloc[train] < ISS.iloc[i]).all(), 'IMMATURE_TRAIN')
    require(burst.any() and (~burst).any(), 'DETECTOR_CLASS_SUPPORT')
    alpha = float(weights[~burst].sum() / weights[burst].sum())
    matrix = x[train].reshape(-1, x.shape[2])
    detector = lgb.LGBMClassifier(objective='binary', scale_pos_weight=alpha, **PARAMS).fit(matrix, burst.astype(int), sample_weight=weights).booster_
    folder = ROOT / 'fits' / DAYS[i]
    folder.mkdir(parents=True, exist_ok=True)
    def save(model, name): (folder / (name + '.txt.gz')).write_bytes(gzip.compress(model.model_to_string().encode(), mtime=0))
    save(detector, 'request_detector')
    risk = prior.corrected_probability(detector.predict(x[i], num_threads=1), alpha)
    tail_days = int((Y[train] > BURST).any(axis=1).sum())
    support = int(burst.sum()) >= 50 and tail_days >= 10
    tail = np.full((24, len(TAIL_LEVELS)), BURST)
    if support:
        for k, tau in enumerate(TAIL_LEVELS):
            model = lgb.LGBMRegressor(objective='quantile', alpha=tau, **PARAMS).fit(matrix[burst], np.log1p(labels[burst]), sample_weight=weights[burst]).booster_
            save(model, 'request_tail_' + str(tau))
            tail[:, k] = np.maximum(BURST, np.expm1(model.predict(x[i], num_threads=1)))
    tail = np.maximum.accumulate(tail, axis=1)
    reference = np.load(PARENT / 'raw' / (DAYS[i] + '.npz'))['D1_BASE71_BALANCED']
    path.parent.mkdir(exist_ok=True)
    np.savez_compressed(path, risk=risk, reference_risk=reference, tail=tail, tail_supported=np.array(support))
    np.savez_compressed(folder / 'TRAIN_MEMBERSHIP.npz', day_indices=train, weights=daily_weights, burst_flat_indices=np.flatnonzero(burst))
    write(folder.relative_to(ROOT) / 'RECEIPT.json', dict(issue=ISS.iloc[i], day_index=i, N_train_days=len(train),
        latest_maturity=AV.iloc[train].max(), alpha=alpha, tail_supported=support, N_burst_hours=int(burst.sum()), N_burst_days=tail_days,
        membership_sha256=sha(folder / 'TRAIN_MEMBERSHIP.npz'), models={p.name: sha(p) for p in folder.glob('*.txt.gz')},
        prediction_sha256=sha(path), feature_sha256=sha(ROOT / 'FEATURES.npz'),
        request_version_provenance='UNVERIFIED', event_time_proxy_only=True))
    print('FIT', DAYS[i], len(train), round(alpha, 3), flush=True)


def forecast(through):
    guard(); source_guard()
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(fit_day, map(int, OOS[DAYS[OOS] <= through])))


def raw(through):
    ids = OOS[DAYS[OOS] <= through]
    risk, reference = np.full(Y.shape, np.nan), np.full(Y.shape, np.nan)
    tail, support = np.full((*Y.shape, 3), np.nan), np.zeros(len(DAYS), bool)
    for i in ids:
        data = np.load(ROOT / 'raw' / (DAYS[i] + '.npz'))
        risk[i], reference[i], tail[i], support[i] = data['risk'], data['reference_risk'], data['tail'], bool(data['tail_supported'])
    return ids, risk, reference, tail, support


def compose(through, config, data=None):
    ids, risk, reference, tail, support = raw(through) if data is None else data
    q = C0.copy(); proof = []
    for i in ids:
        gate = risk[i] >= GATE
        if config['family'] == 'C1':
            previous = ids[(ids < i) & (AV.iloc[ids] < ISS.iloc[i]).to_numpy() & L.split.iloc[ids].ne('PURGE').to_numpy()]
            days, hours = np.where(risk[previous] >= GATE)
            pool_days = previous[days]
            supported = len(days) >= 50 and len(np.unique(pool_days)) >= 10
            delta = prior.old.residual_delta((Y[previous] - C0[previous, :, 1])[risk[previous] >= GATE]) if supported else 0.
            q[i, gate, 1] += delta
            proof.append(dict(day=DAYS[i], issue=ISS.iloc[i], pool_day_indices=pool_days, pool_hours=hours, delta=delta, supported=supported))
        elif support[i]:
            q[i, gate, 1] = np.maximum(C0[i, gate, 1], tail[i, gate, TAIL_LEVELS.index(config['tail_quantile'])])
    return q, proof


def score(q, risk, indices):
    return dict(**prior.old.stats(Y[indices], q[indices, :, 1]), **prior.detector_metrics(Y[indices], risk[indices], GATE))


def criteria(metrics, baseline):
    keys = ['PR_AUC', 'precision', 'detector_recall', 'burst_coverage', 'positive_coverage', 'requirement_ratio', 'Q90_pinball']
    require(np.isfinite([metrics[k] for k in keys] + [baseline[k] for k in keys]).all(), 'NONFINITE_SELECTION')
    targets = [baseline['PR_AUC'] + MEANINGFUL_DETECTOR_DELTA, baseline['precision'] + MEANINGFUL_DETECTOR_DELTA, .6, .6, .85]
    deficits = [0. if target - metrics[k] <= INCLUSIVE_TOLERANCE else 1 - metrics[k] / target for k, target in zip(keys[:5], targets)]
    limit = 1.02 * baseline['Q90_pinball']
    deficits += [max(0., metrics['requirement_ratio'] / 2 - 1), 0. if metrics['Q90_pinball'] - limit <= INCLUSIVE_TOLERANCE else metrics['Q90_pinball'] / limit - 1]
    return sum(deficits) == 0 and metrics['requirement_ratio'] < 2, sum(deficits)


def select():
    require(not (ROOT / 'FINAL_SELECTION_FREEZE.json').exists(), 'ALREADY_SELECTED')
    guard(); data = raw('2024-11-30'); risk, reference = data[1], data[2]
    baseline = {role: score(C0, reference, prior.old.role_ids(role)) for role in ROLES[:2]}
    rows, choices = [], {}
    for family in ['C1', 'C2']:
        ranked = []
        for tau in ([None] if family == 'C1' else TAIL_LEVELS):
            config = dict(family=family, gate=GATE, tail_quantile=tau)
            q, _ = compose('2024-11-30', config, data)
            metrics = [score(q, risk, prior.old.role_ids(role)) for role in ROLES[:2]]
            checks = [criteria(m, baseline[role]) for role, m in zip(ROLES[:2], metrics)]
            feasible = all(v[0] for v in checks)
            rank = (not feasible, 0. if feasible else sum(v[1] for v in checks),
                    not all(.88 <= m['coverage'] <= .92 for m in metrics),
                    not all(m['detector_recall'] >= .7 and m['burst_coverage'] >= .7 for m in metrics),
                    np.mean([m['requirement_ratio'] for m in metrics]), np.mean([m['Q90_pinball'] for m in metrics]))
            ranked.append((rank, config, feasible))
            rows.extend(dict(role=role, **config, hard_feasible=checks[k][0], normalized_deficit=checks[k][1], **m) for k, (role, m) in enumerate(zip(ROLES[:2], metrics)))
        rank, config, feasible = sorted(ranked, key=lambda v: v[0])[0]
        choices[family] = dict(config=config, hard_feasible=feasible, rank=rank)
    eligible = [(v['rank'], name) for name, v in choices.items() if v['hard_feasible']]
    winner = sorted(eligible)[0][1] if eligible else 'C0'
    csv('SELECTION_METRICS', rows)
    write('FINAL_SELECTION_FREEZE.json', dict(time=now(), selected=winner, choices=choices,
        code=read('CODE_FREEZE.json')['code'], protocol_sha256=sha(ROOT / 'PROTOCOL.json'),
        selection_metrics_sha256=sha(ROOT / 'SELECTION_METRICS.csv'), evaluation_computed=False,
        no_detector_threshold_search=True, user_authorized_offline_proxy=True, provenance='UNVERIFIED/UNOBSERVED'))
    print('FROZEN', winner, choices, flush=True)


def paired(y, q, p, base_q, reference, block):
    # Registered parent implementation recalculates nonlinear metrics and AP per paired draw.
    result = prior.paired(y, q, p, GATE, base_q, reference, GATE, block)
    n = len(y); rng = np.random.default_rng(20260927)
    starts = rng.integers(n, size=(2000, int(np.ceil(n / block))))
    index = ((starts[:, :, None] + np.arange(block)) % n).reshape(2000, -1)[:, :n]
    daily = (p >= GATE).mean(axis=1) - (reference >= GATE).mean(axis=1)
    delta = daily[index].mean(axis=1)
    result.append(dict(metric='predicted_high_risk_fraction', delta=float(daily.mean()), CI95_low=float(np.quantile(delta, .025)), CI95_high=float(np.quantile(delta, .975)), N_days=n, draws=2000, block_observed_days=block))
    return result


def evaluate():
    require(not (ROOT / 'EVALUATION_COMPLETE.json').exists(), 'ALREADY_EVALUATED')
    guard(True); source_guard(); data = raw('2025-05-31'); risk, reference = data[1], data[2]
    freeze = read('FINAL_SELECTION_FREEZE.json')
    outputs = {'C0': C0}; rows, strata, uncertainty, predictions, detectors = [], [], [], [], []
    for name, candidate in freeze['choices'].items():
        outputs[name], proof = compose('2025-05-31', candidate['config'], data)
        write(name + '_CALIBRATION_MEMBERSHIP.json', proof)
    for role in ROLES:
        indices = prior.old.role_ids(role)
        for name, p, gate in [('PR69_MATCHED_GATE', reference, GATE), ('PR69_PRIOR_C1_GATE', reference, .0025), ('REQUEST_STATE', risk, GATE)]:
            detectors.append(dict(role=role, detector=name, threshold=gate, **prior.detector_metrics(Y[indices], p[indices], gate)))
        for name, q in outputs.items():
            p = reference if name == 'C0' else risk
            rows.append(dict(role=role, model=name, **score(q, p, indices)))
            require(np.array_equal(q[indices][p[indices] < GATE], C0[indices][p[indices] < GATE]), 'OUTSIDE_GATE_CHANGED')
            require(np.array_equal(q[indices, :, 0], C0[indices, :, 0]), 'Q50_CHANGED')
            for stratum, mask in [('zero', Y[indices] == 0), ('positive', Y[indices] > 0), ('burst', Y[indices] > BURST), ('high_risk', p[indices] >= GATE), ('low_risk', p[indices] < GATE)]:
                if mask.any(): strata.append(dict(role=role, model=name, stratum=stratum, **prior.old.stats(Y[indices][mask], q[indices, :, 1][mask])))
            predictions.append(pd.DataFrame(dict(day=np.repeat(DAYS[indices], 24), hour=np.tile(np.arange(24), len(indices)), role=role, model=name,
                actual=Y[indices].ravel(), Q50=q[indices, :, 0].ravel(), Q90=q[indices, :, 1].ravel(), risk=p[indices].ravel(), threshold=GATE)))
            if role in ROLES[2:] and name != 'C0':
                for block in [1, 7]: uncertainty.extend(dict(role=role, model=name, reference='C0 forecast / PR69 balanced detector matched0.01 gate', **v) for v in paired(Y[indices], q[indices, :, 1], p[indices], C0[indices, :, 1], reference[indices], block))
    for name, values in [('MODEL_METRICS', rows), ('STRATIFIED_METRICS', strata), ('PAIRED_UNCERTAINTY', uncertainty), ('DETECTOR_METRICS', detectors)]: csv(name, values)
    pd.concat(predictions, ignore_index=True).to_parquet(ROOT / 'PREDICTIONS.parquet', index=False)
    write('EVALUATION_COMPLETE.json', dict(time=now(), prediction_sha256=sha(ROOT / 'PREDICTIONS.parquet'), freeze_sha256=sha(ROOT / 'FINAL_SELECTION_FREEZE.json'),
        historical_diagnostic_only=True, actual_historical_request_state_verified=False, offline_proxy_experiment=True))


def verify():
    guard(True); source_guard()
    require(sha(ROOT / 'DAY_MEMBERSHIP.csv') == sha(PARENT / 'DAY_MEMBERSHIP.csv'), 'SPLIT_DRIFT')
    require(np.array_equal(feature_data()[:, :, :71], prior.Z['X']), 'BASE_FEATURE_DRIFT')
    for item in read('REQUEST_EVENT_INDEX_MANIFEST.json')['files']:
        require(sha(ROOT / item['path']) == item['sha256'], 'REQUEST_EVENT_MEMBERSHIP_DRIFT')
    for i in OOS:
        folder = ROOT / 'fits' / DAYS[i]; receipt = read(folder.relative_to(ROOT) / 'RECEIPT.json')
        saved = np.load(folder / 'TRAIN_MEMBERSHIP.npz'); train = prior.old.membership(i)
        require(np.array_equal(saved['day_indices'], train) and np.array_equal(saved['weights'], np.asarray(prior.old.weights(train, i))), 'MEMBERSHIP_DRIFT')
        require(np.array_equal(saved['burst_flat_indices'], np.flatnonzero(Y[train].ravel() > BURST)), 'BURST_MEMBERSHIP_DRIFT')
        require((AV.iloc[train] < ISS.iloc[i]).all(), 'IMMATURE_TRAIN')
        require(sha(folder / 'TRAIN_MEMBERSHIP.npz') == receipt['membership_sha256'], 'MEMBERSHIP_HASH')
        for name, digest in receipt['models'].items(): require(sha(folder / name) == digest, 'MODEL_DRIFT')
        require(sha(ROOT / 'raw' / (DAYS[i] + '.npz')) == receipt['prediction_sha256'], 'RAW_DRIFT')
    frame = pd.read_parquet(ROOT / 'PREDICTIONS.parquet'); freeze = read('FINAL_SELECTION_FREEZE.json'); data = raw('2025-05-31')
    outputs = {'C0': (C0, data[2])}
    for name, candidate in freeze['choices'].items():
        q, proof = compose('2025-05-31', candidate['config'], data)
        require(clean(proof) == read(name + '_CALIBRATION_MEMBERSHIP.json'), 'CALIBRATION_POOL_DRIFT')
        outputs[name] = (q, data[1])
    for name, (q, risk) in outputs.items():
        for role in ROLES:
            indices = prior.old.role_ids(role); group = frame[frame.model.eq(name) & frame.role.eq(role)]
            require(np.array_equal(group.day, np.repeat(DAYS[indices], 24)) and np.array_equal(group.hour, np.tile(np.arange(24), len(indices))), 'EVAL_MEMBERSHIP')
            for column, array in [('actual', Y[indices]), ('Q50', q[indices, :, 0]), ('Q90', q[indices, :, 1]), ('risk', risk[indices])]: require(np.array_equal(group[column], array.ravel()), 'OUTPUT_DRIFT ' + column)
            require(group.threshold.eq(GATE).all(), 'THRESHOLD_DRIFT')
            require(np.array_equal(q[indices][risk[indices] < GATE], C0[indices][risk[indices] < GATE]), 'GATE_OUTSIDE_DRIFT')
    require(np.isfinite(frame[['Q50', 'Q90', 'risk']]).all().all() and (frame.Q90 >= frame.Q50).all(), 'INVALID_PREDICTION')
    require(sha(ROOT / 'PREDICTIONS.parquet') == read('EVALUATION_COMPLETE.json')['prediction_sha256'], 'PREDICTION_HASH')
    require(sha(ROOT / 'FINAL_SELECTION_FREEZE.json') == read('EVALUATION_COMPLETE.json')['freeze_sha256'], 'FREEZE_DRIFT')
    write('VALIDATION.json', dict(time=now(), PASS=True, exact_mature_memberships=len(OOS), exact_predictions=len(frame),
        parent_evidence_unchanged=True, inherited_base_predictions_unchanged=True, outside_gate_unchanged=True,
        request_version_provenance='UNVERIFIED', request_change_history='UNOBSERVED',
        causal_scope='authorized offline event-time proxy only; no historical request-value equality claim',
        production_readiness_fail_closed=True, production_modified=False))


def report():
    metrics = pd.read_csv(ROOT / 'MODEL_METRICS.csv'); uncertainty = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv'); freeze = read('FINAL_SELECTION_FREEZE.json')
    gates = []; superior = freeze['selected'] != 'C0'
    for role in ROLES[2:]:
        base = metrics[metrics.role.eq(role) & metrics.model.eq('C0')].iloc[0]
        for model in ['C1', 'C2']:
            row = metrics[metrics.role.eq(role) & metrics.model.eq(model)].iloc[0]
            feasible, deficit = criteria(row, base)
            ci = uncertainty[uncertainty.role.eq(role) & uncertainty.model.eq(model) & uncertainty.block_observed_days.eq(7)].set_index('metric')
            robust = bool(ci.loc['PR_AUC', 'CI95_low'] >= .01 and ci.loc['precision', 'CI95_low'] >= .01 and ci.loc['burst_coverage', 'CI95_low'] > 0 and ci.loc['pinball_minus_2pct_margin', 'CI95_high'] <= 0)
            gates.append(dict(role=role, model=model, hard_feasible=feasible, normalized_deficit=deficit, meaningful_AP=row.PR_AUC >= base.PR_AUC + .01 - INCLUSIVE_TOLERANCE,
                meaningful_precision=row.precision >= base.precision + .01 - INCLUSIVE_TOLERANCE, recall=row.detector_recall >= .6, burst=row.burst_coverage >= .6,
                ratio=row.requirement_ratio < 2, positive=row.positive_coverage >= .85, overall_preferred=.88 <= row.coverage <= .92,
                pinball_noninferior_point=row.Q90_pinball <= 1.02 * base.Q90_pinball, robust=robust))
            if model == freeze['selected']: superior = superior and feasible and robust
    csv('GATES', gates)
    verdict = dict(NEW_MODEL_SUPERIOR=bool(superior), PRODUCTION_REPLACEMENT_SUPPORTED=False, OPTIMIZER_INTEGRATION_READY=False, PRODUCTION_PROMOTED=False,
        TEMPORAL_POLICY_CHANGED=False, BASE_MODEL_CHANGED=False, selected=freeze['selected'],
        HOURLY_BURST_DEVELOPMENT_STOPPED=not superior, performance_scope='exposed historical offline proxy only',
        REQUEST_STATE_PROVENANCE='UNVERIFIED', REQUEST_CHANGE_HISTORY='UNOBSERVED',
        production_blocker='Historical request-state provenance unresolved; no untouched confirmation',
        future_research_proposals=['cumulative workload', '3h workload', '6h workload'] if not superior else [], target_changed=False)
    write('VERDICT.json', verdict)
    lines = ['# CC4-v2.4 최종 검토 — Request-state Burst Forecast', '',
        f"DEV/CAL에서 선택을 **{freeze['selected']}**로 freeze한 뒤 evaluation했다. May는 exposed historical diagnostic이며 untouched confirmation이 아니다.", '',
        '## 인과 경계와 고정 범위', '',
        '사용자의 명시적 지시에 따라 V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1를 계승했다. Archive의 요청 GPU/walltime/partition/QoS는 assumption-based scheduler-visible proxy다. Historical issue-time 값과 정확히 같았음, request immutability, 변경 빈도 0을 주장하지 않는다. Version provenance는 UNVERIFIED, 변경 이력은 UNOBSERVED다. 코드/모델 authority를 historical scheduler snapshot 증거로 사용하지 않았다. 이 한계는 offline 실험 중단 사유로 쓰지 않았으며 production readiness는 fail-closed다.', '',
        'Base raw LightGBM과 expanding/30-day/daily temporal policy, TRAIN burst threshold를 고정했다. 새 요청 feature는 실제 runtime 완료를 기다리지 않으며 submit<issue proxy 범위에서 계산한다. 기존 71 feature를 그대로 두고 request-state feature를 추가했다. No future runtime/end label enters request feature generation.', '',
        'Detector gate는 두 후보 모두 **0.01 고정**이다. 이전 C2와 같고 이전 C1 0.0025보다 높다. Gate/threshold 탐색이나 전체 scaling은 없다. C1은 gated causal residual, C2는 새 request-feature burst-only conditional magnitude quantile이다. Gate 밖 Q50/Q90 및 전체 Q50은 C0와 정확히 같다. C2는 operational Q90 후보이며 unconditional calibration 보장은 아니다.', '',
        'DEV/CAL 각각 AP·precision의 matched-gate PR69 detector 대비 +0.01 절대 개선, recall/burst≥60%, positive≥85%, ratio<2, pinball≤1.02×C0를 요구했다. 기준·feature·model 설정과 2% 의미 있는 pinball 악화 경계는 개발 결과를 보기 전에 등록했다. AP는 noninterpolated average precision이다.', '',
        '## 모델과 detector 결과', '',
        '| role | model | coverage | positive | burst | ratio | pinball | recall | precision | FPR | AP | high-risk fraction |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for _, r in metrics.iterrows(): lines.append(f'| {r.role} | {r.model} | {r.coverage:.2%} | {r.positive_coverage:.2%} | {r.burst_coverage:.2%} | {r.requirement_ratio:.3f} | {r.Q90_pinball:.3f} | {r.detector_recall:.2%} | {r.precision:.2%} | {r.false_positive_rate:.2%} | {r.PR_AUC:.4f} | {r.gated_fraction:.2%} |')
    lines += ['', 'C0 행의 detector 수치는 이전 PR69 balanced detector를 동일 gate0.01에서 평가한 reference다. C0 forecast에는 이 gate로 보정을 적용하지 않는다. 이전 C1 gate0.0025 수치는 DETECTOR_METRICS.csv에 별도로 보존한다.', '',
        '## Paired uncertainty', '', '동일 target-day를 paired로 묶어 1일/7개 관측일 circular block bootstrap을 각2,000회 시행했다. Forecast는 C0, detector는 matched-gate PR69와 비교한다. 매 draw에서 ratio/precision/FPR/AP를 다시 계산한다. CI는 frozen forecast 조건부이며 model selection/refit uncertainty와 multiple-comparison correction을 포함하지 않는다.', '',
        '| role | model | metric | delta | 7-day 95% CI |', '|---|---|---|---:|---|']
    for _, r in uncertainty[uncertainty.block_observed_days.eq(7) & uncertainty.metric.isin(['PR_AUC', 'precision', 'detector_recall', 'burst_coverage', 'Q90_pinball', 'pinball_minus_2pct_margin'])].iterrows(): lines.append(f'| {r.role} | {r.model} | {r.metric} | {r.delta:.4f} | [{r.CI95_low:.4f}, {r.CI95_high:.4f}] |')
    lines += ['', '## Stop rule과 판정', '', f"HOURLY_BURST_DEVELOPMENT_STOPPED = {str(not superior).upper()}. 이 판단은 사전 지정한 의미 있는 ranking/precision 개선과 최종 forecast gate 및 조건부 CI를 함께 적용했다.", '']
    if not superior: lines += ['Hourly burst 추가 모델 개발은 중단한다. 후속 연구 후보로 cumulative next-day GPU-work, 3시간 GPU-work, 6시간 GPU-work target을 제안만 한다. 더 긴 집계가 timing noise와 burst 희소성에 주는 영향을 별도 사전등록으로 평가할 수 있다. 이번 task에서는 label 재집계, target 변경이나 optimizer 연동을 구현하지 않았다.', '']
    lines += [f'- {key} = **{str(verdict[key]).upper()}**' for key in ['NEW_MODEL_SUPERIOR', 'PRODUCTION_REPLACEMENT_SUPPORTED', 'OPTIMIZER_INTEGRATION_READY', 'PRODUCTION_PROMOTED']]
    lines += ['', '과거 evaluation label은 해당 issue 이전 strict maturity를 만족하면 고정 prequential refit/residual 규칙에만 들어가며 tuning에는 사용하지 않는다. 기존 PR69 evidence는 보존했다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production은 수정·실행하지 않았다.', '']
    with (ROOT / 'FINAL_REVIEW_KO.md').open('x', encoding='utf-8', newline='\n') as stream: stream.write('\n'.join(lines))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['prepare', 'register', 'development', 'select', 'evaluation', 'verify', 'report']); args = parser.parse_args()
    if args.stage == 'development': forecast('2024-11-30')
    elif args.stage == 'evaluation': guard(True); forecast('2025-05-31'); evaluate()
    else: globals()[args.stage]()
