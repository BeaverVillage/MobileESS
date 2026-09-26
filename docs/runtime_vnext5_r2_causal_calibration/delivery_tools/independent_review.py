"""Independent v5 evidence audit: no scientific imports, fitting, or source edits.

Requires completed evaluation and FINAL_VERDICT. Replays all source forecasts,
strictly mature per-Job calibration pools, corrections, metrics and paired CIs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / 'runtime_vnext4_gpu_censored_running'
BASE = ROOT.parent / 'runtime_vnext_causal_tail'
PRE = ['DEVELOPMENT', 'CALIBRATION']
EVAL = ['EXPOSED_EVALUATION', 'MAY_HISTORICAL']
ARMS = ['R1', 'R2', 'R3']
METRICS = ['coverage', 'GPU_coverage', 'long_under', 'missed_GPU_slots',
           'overreserved_GPUh', 'reserved_GPUh', 'reserve_vs_requested',
           'pinball_Q90', 'MAE_bound_seconds', 'overreserve_vs_requested',
           'missed_slots_reduction']
SEED, DRAWS = 20260927, 2000
MAX_ERROR = 0.0


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def close(a, b, reason):
    global MAX_ERROR
    a, b = np.asarray(a, float), np.asarray(b, float)
    require(a.shape == b.shape, reason + ' SHAPE')
    require(np.allclose(a, b, rtol=5e-11, atol=1e-7, equal_nan=True), reason)
    finite = np.isfinite(a) & np.isfinite(b)
    if finite.any():
        MAX_ERROR = max(MAX_ERROR, float(np.abs(a[finite] - b[finite]).max()))


def exact(a, b, reason):
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    try:
        pd.testing.assert_series_equal(a, b, check_names=False,
                                       check_dtype=False, check_exact=True)
    except AssertionError as e:
        raise AssertionError(reason) from e


def divide(a, b):
    a, b = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
    return np.divide(a, b, out=np.full(a.shape, np.nan), where=b > 0)


def sufficient(frame):
    f = frame[frame.actual_seconds.notna()]
    y, q, g = [f[c].to_numpy(float) for c in
               ['actual_seconds', 'bound_seconds', 'num_gpus_req']]
    wall = np.maximum(f.requested_seconds.to_numpy(float) - f.elapsed_seconds.to_numpy(float), 0)
    covered = y <= q
    long = f.runtime_seconds.to_numpy(float) > 14400
    error = y - q
    return np.array([len(f), g.sum(), covered.sum(), (g * covered).sum(),
        long.sum(), (long & ~covered).sum(),
        (g * np.maximum(np.minimum(np.ceil(y / 900), 96) - np.minimum(np.ceil(q / 900), 96), 0)).sum(),
        (g * np.maximum(q - y, 0)).sum() / 3600,
        (g * q).sum() / 3600, (g * wall).sum() / 3600,
        (g * np.maximum(wall - y, 0)).sum() / 3600,
        np.maximum(.9 * error, -.1 * error).sum(), np.abs(error).sum()], float)


def summarize(v):
    return {'N': v[..., 0], 'GPU_weight': v[..., 1],
        'coverage': divide(v[..., 2], v[..., 0]), 'GPU_coverage': divide(v[..., 3], v[..., 1]),
        'long_N': v[..., 4], 'long_under': divide(v[..., 5], v[..., 4]),
        'missed_GPU_slots': v[..., 6], 'overreserved_GPUh': v[..., 7], 'reserved_GPUh': v[..., 8],
        'requested_reserved_GPUh': v[..., 9], 'requested_overreserved_GPUh': v[..., 10],
        'reserve_vs_requested': divide(v[..., 8], v[..., 9]),
        'overreserve_vs_requested': divide(v[..., 7], v[..., 10]),
        'pinball_Q90': divide(v[..., 11], v[..., 0]), 'MAE_bound_seconds': divide(v[..., 12], v[..., 0])}


def statistics(frame):
    result = summarize(sufficient(frame))
    result.update(unscorable_N=int(frame.actual_seconds.isna().sum()), query_N=len(frame))
    return result


def metric_table(path, frame, keys):
    table = pd.read_csv(path)
    groups = frame.groupby(keys)
    require(not table.duplicated(keys).any() and
            set(table[keys].itertuples(index=False, name=None)) == set(groups.groups),
            'METRIC_MEMBERSHIP ' + str(path))
    for key, part in groups:
        row = table
        for name, value in zip(keys, key):
            row = row[row[name].eq(value)]
        require(len(row) == 1, 'DUPLICATE_METRIC')
        for name, value in statistics(part).items():
            close([row.iloc[0][name]], [value], 'METRIC ' + str(key) + ' ' + name)
    return len(table)


def audit_sources(catalog, issues, jobs):
    require(catalog.job_issue_id.is_unique, 'DUPLICATE_RAW_SOURCE')
    require(set(catalog.role) == set(PRE + EVAL), 'RAW_SOURCE_ROLES')
    expected_issues = issues[issues.role.ne('TRAIN')].copy()
    expected_issues['issue_time'] = pd.to_datetime(expected_issues.issue_time, utc=True)
    require(set(catalog.issue_time) == set(expected_issues.issue_time) and len(expected_issues) == 59, 'RAW_ISSUE_SET')
    maturity = pd.read_csv(ROOT / 'SOURCE_MODEL_MATURITY_AUDIT.csv')
    require(len(maturity) == 59 and not maturity.issue_time.duplicated().any(), 'SOURCE_MATURITY_ROWS')
    parent_jobs_hash = sha(BASE / 'JOB_MEMBERSHIP.parquet')
    row_jobs = jobs.set_index('row_id')
    for issue in expected_issues.itertuples():
        t = issue.issue_time
        key = t.strftime('%Y%m%dT%H%M')
        folder = PARENT / 'fits/R2' / key
        prediction = PARENT / 'predictions/R2' / (key + '.parquet')
        receipt = load(folder / 'RECEIPT.json')
        require(sha(prediction) == receipt['prediction_sha256'], 'FROZEN_RAW_PREDICTION_HASH')
        proof = load(folder / 'PORTABLE_MEMBERSHIP.json')
        require(proof['parent_job_membership_sha256'] == parent_jobs_hash, 'RAW_PARENT_JOBS_HASH')
        require(sha(folder / 'ROW_IDS.npz') == proof['ordered_row_ids_sha256'], 'RAW_MEMBERSHIP_HASH')
        ids = np.load(folder / 'ROW_IDS.npz')['row_id']
        require(len(ids) == len(np.unique(ids)) == proof['N'], 'RAW_TRAINING_IDS')
        train = row_jobs.loc[ids]
        require(train.end_time.lt(t).all() and train.label_valid.all(), 'RAW_TRAINING_MATURITY')
        preprocessing = load(BASE / 'fits/LGBM_180_14' / key / 'RUNNING/preprocessing.json')
        require(pd.Timestamp(preprocessing['latest_end']) < t, 'RAW_PREPROCESSING_MATURITY')
        raw = pd.read_parquet(prediction).sort_values('job_issue_id')
        got = catalog[catalog.issue_time.eq(t)].sort_values('job_issue_id')
        require(len(raw) == len(got) and got.role.eq(issue.role).all() and got.state.eq('RUNNING').all(), 'RAW_SOURCE_QUERY_COHORT')
        for column in ['row_id', 'job_id', 'job_issue_id', 'issue_time', 'role', 'state', 'elapsed_seconds', 'submit_time', 'requested_seconds', 'num_gpus_req', 'partition', 'qos']:
            exact(got[column], raw[column], 'RAW_SOURCE ' + column)
        exact(got.raw_Q90, raw.Q90, 'RAW_Q90_BIT_EXACT')
        authority = row_jobs.loc[got.row_id]
        for column in ['start_time', 'end_time', 'label_valid']:
            exact(got[column], authority[column], 'RAW_LABEL ' + column)
        require(got.submit_time.le(t).all() and got.start_time.le(t).all() and got.end_time.gt(t).all(), 'SOURCE_NOT_RUNNING')
        exact(got.elapsed_seconds, (t - got.start_time).dt.total_seconds(), 'SOURCE_ELAPSED')
        m = maturity[pd.to_datetime(maturity.issue_time, utc=True).eq(t)].iloc[0]
        require(m.role == issue.role and m.query_N == len(got) and m.training_N == len(ids), 'MATURITY_LEDGER_COUNT')
        require(pd.Timestamp(m.latest_training_end) == train.end_time.max() and
                pd.Timestamp(m.latest_preprocessing_end) == pd.Timestamp(preprocessing['latest_end']), 'MATURITY_LEDGER_TIME')
        for column, source in [('source_prediction_sha256', prediction), ('source_receipt_sha256', folder / 'RECEIPT.json'), ('training_membership_sha256', folder / 'ROW_IDS.npz')]:
            require(m[column] == sha(source), 'MATURITY_LEDGER_HASH')
    return dict(issues=59, raw_forecasts=len(catalog), exact_frozen_PR71_R2_Q90=True,
                training_and_preprocessing_strictly_mature=True,
                model_prediction_replay_performed=False, new_model_fits=0)


def ecdf(values, weights):
    require(len(values) and np.isfinite(values).all() and np.isfinite(weights).all() and (weights > 0).all(), 'ECDF_INPUT')
    ordered = np.argsort(values, kind='stable')
    cumulative = np.cumsum(weights[ordered])
    require(np.isfinite(cumulative[-1]), 'ECDF_WEIGHT_TOTAL')
    crossing = np.flatnonzero(cumulative >= .9 * weights[ordered].sum())[0]
    return float(values[ordered[crossing]])


def audit_pools(catalog, dev, final, registration_time, freeze_time):
    output = pd.concat([dev, final[final.state.eq('RUNNING') & final.arm.isin(ARMS)]], ignore_index=True)
    require(not output.duplicated(['arm', 'job_issue_id']).any(), 'DUPLICATE_CALIBRATED_QUERY')
    require(len(output) == 3 * len(catalog), 'CALIBRATION_QUERY_EXCLUSION')
    ledger = pd.read_csv(ROOT / 'CALIBRATION_MEMBERSHIP_LEDGER.csv')
    require(len(ledger) == 59 and not ledger.issue_time.duplicated().any(), 'POOL_LEDGER_SET')
    expected_paths, fallback_issues, fallback_rows, deduplicated = set(), 0, 0, 0
    for t, query in catalog.groupby('issue_time', sort=True):
        role = query.role.iloc[0]
        prior = catalog.loc[(catalog.issue_time < t) & (catalog.end_time < t) & catalog.label_valid].copy()
        eligible_N = len(prior)
        prior = prior.sort_values(['job_id', 'issue_time', 'job_issue_id'], kind='stable')
        pool = prior.loc[~prior.job_id.duplicated(keep='last')].sort_values('job_id', kind='stable').copy()
        pool['residual_seconds'] = (pool.end_time - pool.issue_time).dt.total_seconds() - pool.raw_Q90
        require(pool.job_id.is_unique and not (set(pool.job_id) & set(query.job_id)), 'POOL_QUERY_JOB_LEAKAGE')
        require(np.isfinite(pool.residual_seconds).all(), 'POOL_NONFINITE_RESIDUAL')
        expected = pool[['job_id', 'row_id', 'job_issue_id', 'issue_time', 'end_time', 'elapsed_seconds', 'raw_Q90', 'num_gpus_req', 'residual_seconds']].rename(columns={'job_issue_id': 'source_job_issue_id', 'issue_time': 'source_issue_time'})
        folder = ROOT / 'calibration' / t.strftime('%Y%m%dT%H%M')
        expected_paths.add(folder / 'RECEIPT.json')
        receipt = load(folder / 'RECEIPT.json')
        require(sha(folder / 'MEMBERSHIP.parquet') == receipt['membership_sha256'], 'POOL_MEMBERSHIP_HASH')
        actual = pd.read_parquet(folder / 'MEMBERSHIP.parquet')
        require(list(actual.columns) == list(expected.columns), 'POOL_COLUMN_SET')
        for column in expected:
            exact(actual[column], expected[column], 'EXACT_MATURE_POOL ' + column)
        require(pd.Timestamp(receipt['issue_time']) == t and receipt['role'] == role, 'POOL_IDENTITY')
        created = pd.Timestamp(receipt['time'])
        require(created >= registration_time, 'POOL_BEFORE_REGISTRATION')
        if role in EVAL:
            require(created >= freeze_time, 'EVAL_POOL_BEFORE_FREEZE')
        else:
            require(created <= freeze_time, 'DEV_POOL_AFTER_FREEZE')
        fallback = len(pool) < 100
        weights = pool.num_gpus_req.to_numpy(float)
        values = pool.residual_seconds.to_numpy(float)
        require(np.isfinite(weights).all() and (weights > 0).all(), 'POOL_GPU_WEIGHTS')
        correction = {'R1': 0., 'R2': 0. if fallback else max(0., ecdf(values, np.ones(len(pool)))),
                      'R3': 0. if fallback else max(0., ecdf(values, weights))}
        require(receipt['correction_seconds'] == correction and receipt['support_fallback'] == fallback, 'ECDF_CORRECTION')
        require(receipt['eligible_forecast_rows'] == eligible_N and receipt['distinct_mature_Jobs'] == len(pool)
                and receipt['duplicate_source_forecasts_removed'] == eligible_N - len(pool)
                and receipt['prior_source_issue_count'] == pool.issue_time.nunique(), 'POOL_COUNTS')
        for name, value in [('latest_source_issue', pool.issue_time.max()), ('latest_mature_end', pool.end_time.max())]:
            require((receipt[name] is None and pd.isna(value)) or pd.Timestamp(receipt[name]) == value, 'POOL_LATEST_TIME')
        close([receipt['GPU_weight_sum']], [weights.sum()], 'POOL_GPU_WEIGHT_SUM')
        ess = float(weights.sum() ** 2 / np.square(weights).sum()) if len(pool) else None
        close([receipt['GPU_weight_ESS']], [ess], 'POOL_GPU_ESS')
        ledger_row = ledger[pd.to_datetime(ledger.issue_time, utc=True).eq(t)].iloc[0]
        require(ledger_row.role == role and ledger_row.distinct_mature_Jobs == len(pool)
                and ledger_row.duplicate_source_forecasts_removed == eligible_N - len(pool)
                and ledger_row.support_fallback == fallback
                and ledger_row.membership_sha256 == receipt['membership_sha256'], 'POOL_LEDGER')
        close([ledger_row.global_correction_seconds, ledger_row.GPU_correction_seconds, ledger_row.GPU_weight_ESS],
              [correction['R2'], correction['R3'], ess], 'POOL_LEDGER_NUMERIC')
        for arm in ARMS:
            got = output[output.issue_time.eq(t) & output.arm.eq(arm)].sort_values('job_issue_id')
            query = query.sort_values('job_issue_id')
            for column in catalog:
                exact(got[column], query[column], 'PREDICTION_SOURCE ' + column)
            require(np.array_equal(got.bound_seconds.to_numpy(), query.raw_Q90.to_numpy() + correction[arm]), 'CALIBRATED_BOUND_EXACT')
            require(got.correction_seconds.eq(correction[arm]).all() and got.support_fallback.eq(fallback).all()
                    and got.nominal_quantile.eq(.9).all(), 'CALIBRATION_METADATA')
            exact(got.runtime_seconds, (query.end_time - query.start_time).dt.total_seconds(), 'TOTAL_RUNTIME_LABEL')
            exact(got.actual_seconds, (query.end_time - query.issue_time).dt.total_seconds().where(query.label_valid), 'REMAINING_LABEL')
        fallback_issues += int(fallback)
        fallback_rows += len(query) if fallback else 0
        deduplicated += eligible_N - len(pool)
    require(expected_paths == set((ROOT / 'calibration').glob('*/RECEIPT.json')), 'POOL_RECEIPT_SET')
    require(np.isfinite(output.bound_seconds).all() and (output.bound_seconds >= output.raw_Q90).all(), 'NONFINITE_OR_NEGATIVE_CORRECTION')
    return dict(issues=len(expected_paths), exact_memberships=True, filter_maturity_before_latest_Job_dedup=True,
                residual_uses_source_issue=True, global_and_GPU_inverse_ECDF_exact=True,
                support_minimum_distinct_Jobs=100, fallback_issues=fallback_issues,
                fallback_queries_per_arm=fallback_rows, repeated_forecasts_removed_across_pools=deduplicated,
                predictions_checked=len(output), raw_R1_bit_exact=True,
                all_fallback_queries_retained=True, finite_nonnegative_additive_corrections=True)


def audit_r0_and_pending(final, jobs):
    require(not final.duplicated(['arm', 'job_issue_id']).any(), 'FINAL_DUPLICATE')
    require(final.loc[final.arm.eq('R0') | final.state.eq('PENDING'), 'role'].eq('MAY_HISTORICAL').all(), 'R0_PENDING_OUTSIDE_MAY')
    parent = pd.read_parquet(PARENT / 'PREDICTIONS.parquet')
    parent = parent[parent.arm.eq('R0')].sort_values('job_issue_id')
    r0 = final[final.arm.eq('R0')].sort_values('job_issue_id')
    require(len(r0) == len(parent), 'R0_QUERY_SIZE')
    for column in set(final.columns) & set(parent.columns):
        exact(r0[column], parent[column], 'R0_PARENT ' + column)
    require(r0.correction_seconds.eq(0).all() and (~r0.support_fallback).all(), 'R0_METADATA')
    exact(r0.raw_Q90, r0.bound_seconds, 'R0_RAW_TRANSPORT')
    pending = r0[r0.state.eq('PENDING')]
    for arm in ARMS:
        got = final[final.arm.eq(arm) & final.state.eq('PENDING')].sort_values('job_issue_id')
        require(len(got) == len(pending), 'PENDING_QUERY_SIZE')
        for column in final.columns.difference(['arm']):
            exact(got[column], pending[column], 'PENDING_R0_EXACT ' + column)
    labels = jobs.set_index('row_id').loc[final.row_id]
    total = (labels.end_time - labels.start_time).dt.total_seconds().to_numpy()
    remain = (labels.end_time.reset_index(drop=True) - final.issue_time.reset_index(drop=True)).dt.total_seconds().to_numpy()
    y = np.where(final.state.eq('RUNNING'), remain, total)
    y = np.where(labels.label_valid.to_numpy(), y, np.nan)
    require(np.array_equal(final.runtime_seconds, total, equal_nan=True), 'FINAL_TOTAL_RUNTIME')
    require(np.array_equal(final.actual_seconds, y, equal_nan=True), 'FINAL_TOTAL_REMAINING')
    return dict(rows=len(final), R0_May_only=True, Pending_queries_per_arm=len(pending),
                Pending_R0_every_column_bit_exact=True, total_runtime_gt_4h_definition=True)


def audit_metrics(dev, final):
    dev_N = metric_table(ROOT / 'DEVELOPMENT_CALIBRATION_METRICS.csv', dev, ['role', 'arm', 'state'])
    model_N = metric_table(ROOT / 'MODEL_METRICS.csv', final, ['role', 'arm', 'state'])
    running = final[final.state.eq('RUNNING')].copy()
    h = running.elapsed_seconds / 3600
    running['elapsed_regime'] = np.select([h < 1, h < 2, h < 4, h <= 8], ['<1h', '1-2h', '2-4h', '4-8h'], default='>8h')
    running['GPU_bucket'] = np.select([running.num_gpus_req.eq(1), running.num_gpus_req.le(4)], ['1 GPU', '2-4 GPU'], default='>4 GPU')
    elapsed_N = metric_table(ROOT / 'RUNNING_ELAPSED_REGIME_METRICS.csv', running, ['role', 'arm', 'elapsed_regime'])
    gpu_N = metric_table(ROOT / 'RUNNING_GPU_BUCKET_METRICS.csv', running, ['role', 'arm', 'GPU_bucket'])
    return dict(development_calibration_rows=dev_N, model_rows=model_N, elapsed_rows=elapsed_N,
                GPU_bucket_rows=gpu_N, all_direct_metrics_recomputed=True,
                missed_slots_definition='15-minute GPU-slot deficit, capped at 96 slots per forecast; scheduling proxy',
                requested_reference='max(requested_seconds-elapsed_seconds,0), including Pending elapsed zero',
                long_cohort='actual total runtime strictly greater than 4 hours')


def audit_uncertainty(final):
    saved = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv')
    keys = ['role', 'state', 'candidate', 'reference', 'block_days', 'metric']
    require(not saved.duplicated(keys).any(), 'DUPLICATE_CI')
    expected_keys, rows_checked, nonfinite = set(), 0, 0
    for (role, state), g in final.groupby(['role', 'state']):
        pairs = [('R2', 'R1'), ('R3', 'R1'), ('R3', 'R2')]
        if role == 'MAY_HISTORICAL':
            pairs += [(a, 'R0') for a in ARMS]
        for candidate, reference in pairs:
            a = g[g.arm.eq(candidate)].sort_values('job_issue_id')
            b = g[g.arm.eq(reference)].sort_values('job_issue_id')
            for column in ['job_issue_id', 'issue_time', 'actual_seconds']:
                exact(a[column], b[column], 'CI_PAIRING ' + column)
            a, b = a[a.actual_seconds.notna()], b[b.actual_seconds.notna()]
            va = np.array([sufficient(z) for _, z in a.groupby('issue_time', sort=True)])
            vb = np.array([sufficient(z) for _, z in b.groupby('issue_time', sort=True)])
            n = len(va)
            def effect(x, y):
                sa, sb = summarize(x), summarize(y)
                return np.stack([sa[k] - sb[k] for k in METRICS[:-1]] +
                                [1 - divide(sa['missed_GPU_slots'], sb['missed_GPU_slots'])], axis=-1)
            point = effect(va.sum(0), vb.sum(0))
            for block in [1, 7]:
                rng = np.random.default_rng(SEED)
                index = np.array([((rng.integers(n, size=math.ceil(n / block))[:, None] + np.arange(block)) % n).ravel()[:n] for _ in range(DRAWS)])
                samples = effect(va[index].sum(1), vb[index].sum(1))
                subset = saved[saved.role.eq(role) & saved.state.eq(state) & saved.candidate.eq(candidate) & saved.reference.eq(reference) & saved.block_days.eq(block)]
                require(set(subset.metric) == set(METRICS) and len(subset) == len(METRICS), 'CI_METRIC_SET')
                for k, metric in enumerate(METRICS):
                    expected_keys.add((role, state, candidate, reference, block, metric))
                    finite = np.isfinite(samples[:, k])
                    low, high = np.quantile(samples[finite, k], [.025, .975]) if finite.any() else (np.nan, np.nan)
                    row = subset[subset.metric.eq(metric)].iloc[0]
                    close([row.estimate, row.CI95_low, row.CI95_high], [point[k], low, high], 'CI ' + str((role, state, candidate, reference, block, metric)))
                    require(row.nonfinite_draws == int((~finite).sum()) and row.draws == DRAWS and row.N_days == n and row.N_pairs == len(a), 'CI_COUNTS')
                    nonfinite += int((~finite).sum())
                    rows_checked += 1
    require(set(saved[keys].itertuples(index=False, name=None)) == expected_keys and rows_checked == 330, 'CI_FULL_SET')
    return dict(rows=rows_checked, paired_comparisons_and_blocks=rows_checked // 11,
                draws=DRAWS, seed=SEED, block_lengths=[1, 7], nonfinite_draws=nonfinite,
                nonlinear_ratios_recomputed_each_draw=True, finite_draw_null_handling_checked=True)


def audit_selection(freeze):
    table = pd.read_csv(ROOT / 'DEVELOPMENT_CALIBRATION_METRICS.csv')
    options = []
    required = ['coverage', 'GPU_coverage', 'long_under', 'pinball_Q90', 'reserve_vs_requested', 'overreserved_GPUh', 'requested_overreserved_GPUh']
    require(np.isfinite(table[required]).all().all(), 'SELECTION_NONFINITE')
    raw = table[table.arm.eq('R1')].set_index('role').loc[PRE]
    for arm in ['R2', 'R3']:
        part = table[table.arm.eq(arm)].set_index('role').loc[PRE]
        safe = bool((part.coverage >= .9).all() and (part.GPU_coverage >= .9).all() and (part.long_under <= .15).all())
        pinball = bool((part.pinball_Q90 <= 1.02 * raw.pinball_Q90).all())
        options.append(dict(arm=arm, safety_pass=safe, pinball_margin_pass=pinball, eligible=safe and pinball,
                            reserve_preferred_pass=bool((part.overreserved_GPUh <= part.requested_overreserved_GPUh).all()),
                            mean_role_reserve_ratio=float(part.reserve_vs_requested.mean())))
    eligible = [v for v in options if v['eligible']]
    selected = min(eligible, key=lambda v: (not v['reserve_preferred_pass'], v['mean_role_reserve_ratio'], v['arm']))['arm'] if eligible else 'R1'
    require(freeze['selected_running'] == selected and len(freeze['options']) == len(options), 'SELECTION_REPLAY')
    for actual, expected in zip(freeze['options'], options):
        for key in expected:
            if key == 'mean_role_reserve_ratio':
                close([actual[key]], [expected[key]], 'SELECTION_RATIO')
            else:
                require(actual[key] == expected[key], 'SELECTION_OPTION ' + key)
    return dict(selected_running=selected, options=options, reserve_is_preference_not_hard_gate=True,
                positive_correction_cannot_reduce_pointwise_reserve_or_overreserve=True)


def audit_verdict(selection):
    path = ROOT / 'FINAL_VERDICT.json'
    require(path.exists(), 'WAIT_FOR_FINAL_VERDICT; no review JSON written')
    verdict = load(path)
    selected = selection['selected_running']
    require(verdict['selected_running'] == selected and verdict['Pending'] == 'R0 exact', 'VERDICT_SELECTION')
    require(verdict['rule_source_sha256'] == sha(ROOT / 'REGISTRATION.json'), 'VERDICT_RULE_HASH')
    table = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
    run = table[table.state.eq('RUNNING')]
    raw = run[run.arm.eq('R1')].set_index('role').loc[EVAL]
    ci = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv')
    expected_diagnostics = []
    for arm in ['R2', 'R3']:
        candidate = run[run.arm.eq(arm)].set_index('role').loc[EVAL]
        safe = bool((candidate.coverage >= .9).all() and (candidate.GPU_coverage >= .9).all()
                    and (candidate.long_under <= .15).all())
        pinball = bool((candidate.pinball_Q90 <= 1.02 * raw.pinball_Q90).all())
        preferred = bool((candidate.overreserved_GPUh <= candidate.requested_overreserved_GPUh).all())
        proof = []
        for role, reference in [('EXPOSED_EVALUATION', 'R1'), ('MAY_HISTORICAL', 'R1'), ('MAY_HISTORICAL', 'R0')]:
            row = ci[ci.role.eq(role) & ci.state.eq('RUNNING') & ci.candidate.eq(arm)
                     & ci.reference.eq(reference) & ci.metric.eq('missed_GPU_slots') & ci.block_days.eq(7)]
            require(len(row) == 1, 'VERDICT_CI_ROW')
            proof.append(dict(role=role, reference=reference,
                              CI95_high_negative=bool(row.iloc[0].CI95_high < 0)))
        expected_diagnostics.append(dict(arm=arm, preselected=selected == arm,
            both_evaluation_safety_pass=safe, both_evaluation_pinball_margin_pass=pinball,
            reserve_preferred_pass=preferred, robust_missed_reduction=all(p['CI95_high_negative'] for p in proof),
            missed_proof=proof))
    require(verdict['calibrator_diagnostics'] == expected_diagnostics, 'FINAL_DIAGNOSTIC_REPLAY')
    supported = any(d['preselected'] and d['both_evaluation_safety_pass']
                    and d['both_evaluation_pinball_margin_pass'] and d['robust_missed_reduction']
                    for d in expected_diagnostics)
    require(verdict['RUNTIME_CALIBRATION_SUPPORTED'] == supported, 'REGISTERED_SUPPORT_FORMULA')
    require(verdict['reserve_preferred_not_hard_support_gate'] is True, 'RESERVE_PREFERENCE_HIERARCHY')
    # Current registered selection retained raw. No calibrator can be promoted
    # by post-selection evaluation, even if a diagnostic arm improves later.
    require(selected == 'R1', 'EXPECTED_FIXED_HISTORICAL_RAW_SELECTION')
    require(verdict['RUNTIME_CALIBRATION_SUPPORTED'] is False, 'RAW_SELECTION_CANNOT_SUPPORT_CALIBRATION')
    for flag in ['PRODUCTION_REPLACEMENT_SUPPORTED', 'OPTIMIZER_INTEGRATION_READY', 'PRODUCTION_PROMOTED']:
        require(verdict[flag] is False, 'PRODUCTION_FLAG ' + flag)
    require(verdict['TEMPORAL_POLICY_CHANGED'] is False and verdict['NEW_MODEL_SEARCHED'] is False
            and verdict['model_training_executions'] == 0, 'VERDICT_UNCHANGED_BASE')
    return dict(final_verdict_sha256=sha(path), RUNTIME_CALIBRATION_SUPPORTED=False,
                report_source_sha256=sha(ROOT / 'delivery_tools/report.py'),
                all_calibrator_diagnostics_recomputed=True,
                registered_reason='DEV/CAL retained raw R1; post-freeze diagnostic arms cannot replace the selection',
                reserve_preference_not_used_as_hard_support_gate=True, production_flags_false=True)


def main(check_only=False, replace_review=False):
    require((ROOT / 'EVALUATION_COMPLETE.json').exists() and (ROOT / 'VALIDATION.json').exists(), 'WAIT_FOR_EVALUATION_AND_VALIDATION')
    registration, freeze, complete = [load(ROOT / name) for name in ['REGISTRATION.json', 'FINAL_SELECTION_FREEZE.json', 'EVALUATION_COMPLETE.json']]
    for name, digest in registration['code'].items():
        require(sha(ROOT / name) == digest == freeze['code'][name], 'FROZEN_SCIENTIFIC_CODE ' + name)
    for source, value in [('REGISTRATION.json', freeze['registration_sha256']),
                          ('DEVELOPMENT_CALIBRATION_METRICS.csv', freeze['metrics_sha256']),
                          ('DEV_CAL_PREDICTIONS.parquet', freeze['DEV_CAL_predictions_sha256']),
                          ('FINAL_SELECTION_FREEZE.json', complete['freeze_sha256']),
                          ('PREDICTIONS.parquet', complete['prediction_sha256']),
                          ('SOURCE_FORECASTS.parquet', registration['source_forecasts_sha256'])]:
        require(sha(ROOT / source) == value, 'CHAIN_HASH ' + source)
    reg_time, freeze_time, eval_time = [pd.Timestamp(v['time']) for v in [registration, freeze, complete]]
    require(reg_time < freeze_time < eval_time and not freeze['new_evaluation_metrics_computed']
            and freeze['May_already_exposed'] and not complete['evaluation_reselection'], 'FREEZE_SEQUENCE')
    preparation = load(ROOT / 'PREPARATION.json')
    require(preparation['model_fits'] == 0 and not preparation['TRAIN_R2_forecasts_available'], 'SOURCE_WARMUP_AUTHORITY')
    require(preparation['source_forecasts_sha256'] == registration['source_forecasts_sha256'], 'PREPARATION_SOURCE_HASH')
    catalog = pd.read_parquet(ROOT / 'SOURCE_FORECASTS.parquet')
    issues = pd.read_csv(BASE / 'ISSUES.csv')
    jobs = pd.read_parquet(BASE / 'JOB_MEMBERSHIP.parquet')
    dev = pd.read_parquet(ROOT / 'DEV_CAL_PREDICTIONS.parquet')
    final = pd.read_parquet(ROOT / 'PREDICTIONS.parquet')
    require(set(dev.role) == set(PRE) and set(final.role) == set(EVAL), 'DEV_EVAL_BOUNDARY')
    split = pd.read_csv(ROOT / 'EXACT_SPLITS.csv')
    require(np.array_equal(split.issue_time, issues.issue_time) and np.array_equal(split.role, issues.role)
            and np.array_equal(split.new_calibration_issue, issues.role.ne('TRAIN')) and not split.new_model_fit.any(), 'EXACT_SPLIT_PRESERVATION')
    sources = audit_sources(catalog, issues, jobs)
    pools = audit_pools(catalog, dev, final, reg_time, freeze_time)
    print('Independent 59 source and calibration membership replays PASS', flush=True)
    predictions = audit_r0_and_pending(final, jobs)
    metrics = audit_metrics(dev, final)
    uncertainty = audit_uncertainty(final)
    selection = audit_selection(freeze)
    verdict = audit_verdict(selection)
    result = dict(time=pd.Timestamp.now(tz='UTC').isoformat(), PASS=True,
                  audit_source_sha256=sha(__file__), scientific_source_sha256=registration['code'],
                  evaluation_complete_sha256=sha(ROOT / 'EVALUATION_COMPLETE.json'),
                  freeze_sequence_and_all_linked_hashes_PASS=True, sources=sources, calibration=pools,
                  predictions=predictions, metrics=metrics, uncertainty=uncertainty,
                  selection=selection, verdict=verdict, maximum_numeric_roundtrip_error=MAX_ERROR,
                  numeric_rtol=5e-11, numeric_atol=1e-7,
                  proxy_boundary='User-authorized D1_SCHEDULER_REQUEST_STATE_PROXY_V1 offline archive experiment',
                  request_provenance='UNVERIFIED/UNOBSERVED', historical_request_exactness_claimed=False,
                  historical_census_completeness='UNVERIFIED', outcome_independent_archive_inclusion_claimed=False,
                  May='Previously exposed historical diagnostic, not untouched confirmation',
                  finite_sample_or_temporal_coverage_guarantee=False, production_readiness=False,
                  model_training_during_review=0, scientific_imports_during_review=0, scientific_files_modified=False,
                  limitations=['Empirical weighted/unweighted residual quantiles have no formal coverage guarantee under temporal dependence.',
                               'Source prediction bytes and membership maturity are verified; models are not refitted or prediction-replayed.',
                               'Causal ordering is conditional on the supplied archive and authorized request proxies; historical census completeness is unverified.',
                               'Missed GPU slots are a scheduling proxy, not realized scheduler throughput.',
                               'Nonnegative correction cannot reduce inherited reserve or overreserve; reserve remains a preference and separately reported cost.',
                               'The registered DEV/CAL decision retained raw R1; this study supports no calibrator or production promotion.'])
    if not check_only:
        with (ROOT / 'INDEPENDENT_REVIEW.json').open('w' if replace_review else 'x', encoding='utf-8') as out:
            json.dump(result, out, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--replace-review', action='store_true', help='Replace only this independent review artifact after an audit-helper extension.')
    args = parser.parse_args()
    main(args.check_only, args.replace_review)
