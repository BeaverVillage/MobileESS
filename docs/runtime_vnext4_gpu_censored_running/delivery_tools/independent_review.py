"""Independent final audit; no study imports, fitting, or scientific-file edits.

Run only after EVALUATION_COMPLETE.json. Reconstructs safe fit membership from
immutable parent job events and supports either full local membership Parquets
or the lossless ordered-ID/column-digest delivery representation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'runtime_vnext_causal_tail'
SEED, DRAWS = 20260927, 2000
METRICS = ['coverage', 'GPU_coverage', 'long_under', 'missed_GPU_slots',
           'overreserved_GPUh', 'reserved_GPUh', 'reserve_vs_requested',
           'pinball_Q90', 'pinball_Q95', 'MAE_bound_seconds',
           'overreserve_vs_requested', 'missed_slots_reduction']
MAX_NUMERIC_ERROR = 0.0


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def close(actual, expected, reason):
    global MAX_NUMERIC_ERROR
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    require(a.shape == b.shape, reason + ' SHAPE')
    require(np.allclose(a, b, rtol=5e-11, atol=1e-7, equal_nan=True), reason)
    finite = np.isfinite(a) & np.isfinite(b)
    if finite.any():
        MAX_NUMERIC_ERROR = max(MAX_NUMERIC_ERROR, float(np.abs(a[finite] - b[finite]).max()))


def divide(a, b):
    a, b = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
    return np.divide(a, b, out=np.full(a.shape, np.nan), where=b > 0)


def sufficient(frame):
    f = frame[frame.actual_seconds.notna()]
    y = f.actual_seconds.to_numpy(float)
    q = f.bound_seconds.to_numpy(float)
    g = f.num_gpus_req.to_numpy(float)
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
        np.maximum(.9 * error, -.1 * error).sum(),
        np.maximum(.95 * error, -.05 * error).sum(), np.abs(error).sum()], float)


def summarize(v):
    return {'N': v[..., 0], 'GPU_weight': v[..., 1],
        'coverage': divide(v[..., 2], v[..., 0]), 'GPU_coverage': divide(v[..., 3], v[..., 1]),
        'long_N': v[..., 4], 'long_under': divide(v[..., 5], v[..., 4]),
        'missed_GPU_slots': v[..., 6], 'overreserved_GPUh': v[..., 7], 'reserved_GPUh': v[..., 8],
        'requested_reserved_GPUh': v[..., 9], 'requested_overreserved_GPUh': v[..., 10],
        'reserve_vs_requested': divide(v[..., 8], v[..., 9]),
        'overreserve_vs_requested': divide(v[..., 7], v[..., 10]),
        'pinball_Q90': divide(v[..., 11], v[..., 0]), 'pinball_Q95': divide(v[..., 12], v[..., 0]),
        'MAE_bound_seconds': divide(v[..., 13], v[..., 0])}


def statistics(f):
    result = summarize(sufficient(f))
    valid = f[f.actual_seconds.notna()]
    result.update(unscorable_N=int(f.actual_seconds.isna().sum()), query_N=len(f),
        MAE_Q50_seconds=float(np.abs(valid.actual_seconds - valid.Q50).mean())
        if np.isfinite(valid.Q50).all() else np.nan)
    return result


def check_metric_row(row, frame):
    for name, value in statistics(frame).items():
        close([row[name]], [value], 'METRIC ' + name)


def canonical(column):
    if column.name == 'job_id':
        payload, encoding = ('\n'.join(column.astype(str)) + '\n').encode(), 'utf8-lines'
    elif pd.api.types.is_datetime64_any_dtype(column):
        payload = column.dt.as_unit('ns').astype('int64').to_numpy(dtype='<i8').tobytes()
        encoding = 'utc-ns-int64-little-endian'
    elif column.name == 'right_censored':
        payload, encoding = column.to_numpy(dtype='u1').tobytes(), 'uint8'
    elif column.name == 'row_id':
        payload, encoding = column.to_numpy(dtype='<i8').tobytes(), 'int64-little-endian'
    else:
        payload, encoding = column.to_numpy(dtype='<f8').tobytes(), 'float64-little-endian'
    return dict(encoding=encoding, sha256=hashlib.sha256(payload).hexdigest())


def reconstruct(jobs, issue, family):
    t = pd.Timestamp(issue)
    f = jobs[jobs.submit_time.le(t) & jobs.start_time.notna() &
             jobs.start_time.ge(jobs.submit_time) & jobs.start_time.lt(t)].copy()
    exact = f.end_time.lt(t)
    observed_end = f.end_time.where(exact)
    observed_at = observed_end.fillna(t)
    total = (observed_at - f.start_time).dt.total_seconds()
    landmark = np.array([1800., 5400., 10800., 21600., 43200.])[
        pd.util.hash_pandas_object(f.job_id, index=False).to_numpy() % 5]
    lower = total.to_numpy() - landmark
    mask = (lower > 0) & observed_at.ge(t - pd.Timedelta(days=180))
    if family == 'R2':
        mask &= exact
    out = f.loc[mask, ['row_id', 'job_id', 'num_gpus_req']].copy()
    out['observed_end'] = observed_end[mask]
    out['observation_time'] = observed_at[mask]
    out['elapsed_seconds'] = landmark[mask]
    out['observed_total_seconds'] = total[mask]
    out['label_lower'] = lower[mask]
    out['label_upper'] = np.where(exact[mask], lower[mask], np.inf)
    out['right_censored'] = ~exact[mask]
    out = out.sort_values(['observation_time', 'job_id'], kind='stable')
    recency = np.exp(-np.log(2) / 14 * (t - out.observation_time).dt.total_seconds().to_numpy() / 86400)
    factor = out.num_gpus_req.to_numpy() * (1. + (out.observed_total_seconds.to_numpy() > 14400))
    normalizer = np.sum(recency * factor) / np.sum(recency)
    out['sample_weight'] = recency * factor / normalizer
    close([out.sample_weight.sum()], [recency.sum()], 'RECENCY_WEIGHT_SUM')
    return out.drop(columns='num_gpus_req'), float(normalizer)


def audit_fits(issues, jobs, freeze_time, registration_time):
    counts = {'R2': 0, 'R3': 0}
    full_count = portable_count = models = locally_verified_models = manifest_only_models = 0
    checkpoint_manifest = ROOT / 'MODEL_CHECKPOINT_MANIFEST.json'
    declared_checkpoints = {r['path'].replace('\\', '/'): r['sha256'] for r in load(checkpoint_manifest)['files']} if checkpoint_manifest.exists() else {}
    parent_digest = sha(BASE / 'JOB_MEMBERSHIP.parquet')
    expected_paths = set()
    for issue in issues[issues.role.ne('TRAIN')].itertuples():
        t = pd.Timestamp(issue.issue_time)
        key = t.strftime('%Y%m%dT%H%M')
        query = pd.read_parquet(BASE / 'predictions/LGBM_180_14' / (key + '.parquet'))
        query = query[query.state.eq('RUNNING')]
        for family in ['R2', 'R3']:
            folder = ROOT / 'fits' / family / key
            receipt_path = folder / 'RECEIPT.json'
            expected_paths.add(receipt_path)
            receipt = load(receipt_path)
            require(receipt['family'] == family and pd.Timestamp(receipt['issue_time']) == t, 'FIT_IDENTITY')
            require(pd.Timestamp(receipt['time']) >= registration_time, 'FIT_BEFORE_REGISTRATION')
            if issue.role in ['EXPOSED_EVALUATION', 'MAY_HISTORICAL']:
                require(pd.Timestamp(receipt['time']) >= freeze_time, 'EVALUATION_FIT_BEFORE_FREEZE')
            expected, normalizer = reconstruct(jobs, t, family)
            require(expected.job_id.is_unique, 'DUPLICATE_TRAIN_JOB')
            if family == 'R2':
                old = jobs[jobs.label_valid & jobs.end_time.lt(t) & jobs.end_time.ge(t - pd.Timedelta(days=180))]
                old = old.sort_values(['end_time', 'job_id'], kind='stable')
                landmarks = np.array([1800., 5400., 10800., 21600., 43200.])[
                    pd.util.hash_pandas_object(old.job_id, index=False).to_numpy() % 5]
                old = old[(old.end_time - old.start_time).dt.total_seconds().to_numpy() > landmarks]
                require(np.array_equal(expected.row_id, old.row_id), 'R2_PARENT_COHORT')
            local = folder / 'MEMBERSHIP.parquet'
            portable = folder / 'PORTABLE_MEMBERSHIP.json'
            require(local.exists() or portable.exists(), 'NO_MEMBERSHIP_EVIDENCE')
            if local.exists():
                require(sha(local) == receipt['membership_sha256'], 'FULL_MEMBERSHIP_HASH')
                actual = pd.read_parquet(local)
                for column in actual:
                    require(canonical(actual[column]) == canonical(expected[column]), 'SAFE_FIELD ' + column)
                full_count += 1
            if portable.exists():
                proof = load(portable)
                require(proof['parent_job_membership_sha256'] == parent_digest, 'PORTABLE_PARENT_HASH')
                require(proof['full_local_membership_sha256'] == receipt['membership_sha256'], 'PORTABLE_ORIGINAL_HASH')
                require(proof['ordered_row_ids_sha256'] == sha(folder / 'ROW_IDS.npz'), 'PORTABLE_ID_HASH')
                require(np.array_equal(np.load(folder / 'ROW_IDS.npz')['row_id'], expected.row_id), 'PORTABLE_ORDERED_IDS')
                require(proof['columns'] == {c: canonical(expected[c]) for c in proof['columns']}, 'PORTABLE_SAFE_FIELDS')
                require(proof['N'] == len(expected) and proof['weight_normalizer'] == normalizer, 'PORTABLE_SIZE_WEIGHT')
                portable_count += 1
            close([receipt['weight_normalizer'], receipt['weight_sum']], [normalizer, expected.sample_weight.sum()], 'WEIGHT_RECEIPT')
            require(receipt['N_train'] == len(expected) and receipt['N_censored'] == int(expected.right_censored.sum()), 'FIT_COUNTS')
            require(expected.loc[expected.right_censored, 'observed_end'].isna().all(), 'FUTURE_END_EXPOSED')
            require(np.isinf(expected.loc[expected.right_censored, 'label_upper']).all(), 'CENSOR_UPPER')
            predpath = ROOT / 'predictions' / family / (key + '.parquet')
            require(sha(predpath) == receipt['prediction_sha256'], 'FIT_PREDICTION_HASH')
            pred = pd.read_parquet(predpath)
            require(pred.job_issue_id.is_unique and np.array_equal(pred.job_issue_id, query.job_issue_id), 'FIT_QUERY_IDS')
            require(receipt['N_query'] == len(pred), 'FIT_QUERY_COUNT')
            for column in ['elapsed_seconds', 'requested_seconds', 'num_gpus_req', 'partition', 'qos']:
                pd.testing.assert_series_equal(pred[column].reset_index(drop=True), query[column].reset_index(drop=True))
            require(np.isfinite(pred[['Q50', 'Q90', 'Q95']]).all().all(), 'NONFINITE_QUANTILES')
            require((np.diff(pred[['Q50', 'Q90', 'Q95']].to_numpy(), axis=1) >= 0).all(), 'QUANTILE_ORDER')
            require(sha(ROOT / 'preprocessing' / (key + '.pkl.gz')) == receipt['preprocessing_sha256'], 'PREPROCESSOR_HASH')
            expected_models = {'Q50.txt.gz', 'Q90.txt.gz', 'Q95.txt.gz'} if family == 'R2' else {'AFT.ubj'}
            require(set(receipt['models']) == expected_models, 'MODEL_FILE_SET')
            for name, digest in receipt['models'].items():
                path = folder / name
                relative = path.relative_to(ROOT).as_posix()
                if path.exists():
                    require(sha(path) == digest, 'MODEL_HASH ' + name)
                    locally_verified_models += 1
                    if declared_checkpoints:
                        require(declared_checkpoints.get(relative) == digest, 'MODEL_MANIFEST_HASH ' + relative)
                else:
                    require(declared_checkpoints.get(relative) == digest, 'MISSING_MODEL_MANIFEST_AUTHORITY ' + relative)
                    manifest_only_models += 1
                models += 1
            counts[family] += 1
    require(expected_paths == set((ROOT / 'fits').glob('*/*/RECEIPT.json')), 'FIT_RECEIPT_SET')
    require(sum(counts.values()) == 118, 'EXPECTED_118_FITS')
    return dict(fit_receipts=counts, model_files=models, full_local_memberships=full_count,
                portable_memberships=portable_count, exact_safe_field_reconstruction=True,
                exact_R2_parent_membership=True, weight_sum_preserved=True,
                checkpoint_hashes_verified_from_local_bytes=locally_verified_models,
                checkpoints_unavailable_locally_manifest_only=manifest_only_models,
                checkpoint_manifest_sha256=sha(checkpoint_manifest) if checkpoint_manifest.exists() else None,
                model_prediction_replay_performed=False,
                checkpoint_scope='Present checkpoint bytes are hashed; missing checkpoint bytes are not verified or replayed. Missing files require exact receipt-to-delivered-manifest digest agreement.')


def audit_selection(freeze, jobs, issues):
    table = pd.read_csv(ROOT / 'DEVELOPMENT_CALIBRATION_METRICS.csv')
    parts = []
    for issue in issues[issues.role.isin(['DEVELOPMENT', 'CALIBRATION'])].itertuples():
        key = pd.Timestamp(issue.issue_time).strftime('%Y%m%dT%H%M')
        for arm in ['R1', 'R2', 'R3']:
            source = BASE / 'predictions/LGBM_180_14' / (key + '.parquet') if arm == 'R1' else ROOT / 'predictions' / arm / (key + '.parquet')
            raw = pd.read_parquet(source)
            raw = raw[raw.state.eq('RUNNING')].merge(jobs[['row_id', 'start_time', 'end_time', 'label_valid']], on='row_id', validate='many_to_one')
            raw['runtime_seconds'] = (raw.end_time - raw.start_time).dt.total_seconds()
            raw['actual_seconds'] = (raw.end_time - raw.issue_time).dt.total_seconds().where(raw.label_valid)
            raw['bound_seconds'], raw['arm'] = raw.Q90, arm
            parts.append(raw)
    reconstructed = pd.concat(parts, ignore_index=True)
    require(len(table) == 6 and set(table[['role', 'arm']].itertuples(index=False, name=None)) ==
            set(reconstructed.groupby(['role', 'arm']).groups), 'SELECTION_METRIC_SET')
    for _, row in table.iterrows():
        check_metric_row(row, reconstructed[reconstructed.role.eq(row.role) & reconstructed.arm.eq(row.arm)])
    required = ['coverage', 'GPU_coverage', 'long_under', 'overreserved_GPUh', 'requested_overreserved_GPUh', 'reserve_vs_requested']
    require(np.isfinite(table[required]).all().all(), 'SELECTION_NONFINITE')
    options = []
    for arm, g in table.groupby('arm'):
        require(set(g.role) == {'DEVELOPMENT', 'CALIBRATION'} and len(g) == 2, 'SELECTION_ROLES')
        options.append(dict(arm=arm, safety_pass=bool((g.coverage >= .9).all() and (g.GPU_coverage >= .9).all() and (g.long_under <= .15).all()),
            reserve_preferred_pass=bool((g.overreserved_GPUh <= g.requested_overreserved_GPUh).all()),
            reserve_ratio=float(g.reserve_vs_requested.mean())))
    eligible = [v for v in options if v['safety_pass']]
    chosen = min(eligible, key=lambda v: (not v['reserve_preferred_pass'], v['reserve_ratio'], v['arm']))['arm'] if eligible else 'R0'
    require(chosen == freeze['selected'] and freeze['operational_quantile'] == .9, 'SELECTION_REPRODUCTION')
    selected = table[table.arm.eq(chosen)]
    return dict(selected=chosen, operational_quantile=.9, options=options, metrics_recomputed_from_frozen_predictions=True,
        selected_overreserve_vs_requested_by_role=dict(zip(selected.role, selected.overreserve_vs_requested)),
        interpretation='Safety-first research selection. Reserve is a preference, not a hard adoption criterion; selection does not establish reserve efficiency or production suitability.')


def audit_predictions(f, jobs):
    require(not f.duplicated(['arm', 'job_issue_id']).any(), 'DUPLICATE_FINAL_QUERY')
    require(set(f.arm) == {'R0', 'R1', 'R2', 'R3'}, 'FINAL_ARMS')
    require(f.loc[f.arm.eq('R0'), 'role'].eq('MAY_HISTORICAL').all(), 'R0_OUTSIDE_MAY')
    require(f.loc[f.state.eq('PENDING'), 'role'].eq('MAY_HISTORICAL').all(), 'PENDING_OUTSIDE_MAY')
    legacy = pd.read_parquet(BASE / 'PREDICTIONS.parquet')
    legacy = legacy[legacy.model.eq('PR42_FROZEN_LGBM_NAIVE_REMAINING')].sort_values('job_issue_id')
    r0 = f[f.arm.eq('R0')].sort_values('job_issue_id')
    require(np.array_equal(r0.job_issue_id, legacy.job_issue_id) and np.array_equal(r0.bound_seconds, legacy.Q90), 'R0_DRIFT')
    pending = r0[r0.state.eq('PENDING')]
    inherited = pd.read_parquet(BASE / 'ISSUE_MEMBERSHIP.parquet')
    running = inherited[inherited.role.isin(['EXPOSED_EVALUATION', 'MAY_HISTORICAL']) & inherited.state.eq('RUNNING')].sort_values('job_issue_id')
    for arm in ['R1', 'R2', 'R3']:
        a = f[f.arm.eq(arm) & f.state.eq('PENDING')].sort_values('job_issue_id')
        require(np.array_equal(a.job_issue_id, pending.job_issue_id) and np.array_equal(a.bound_seconds, pending.bound_seconds), 'PENDING_R0_DRIFT')
        a = f[f.arm.eq(arm) & f.state.eq('RUNNING')].sort_values('job_issue_id')
        require(np.array_equal(a.job_issue_id, running.job_issue_id), 'RUNNING_QUERY_EXCLUSION')
        require(np.array_equal(a.bound_seconds, a.Q90), 'OPERATIONAL_QUANTILE_CHANGED')
        require(np.isfinite(a[['Q50', 'Q90', 'Q95']]).all().all(), 'FINAL_NONFINITE_QUANTILES')
        require((np.diff(a[['Q50', 'Q90', 'Q95']].to_numpy(), axis=1) >= 0).all(), 'FINAL_QUANTILE_ORDER')
        for issue, part in a.groupby('issue_time'):
            key = pd.Timestamp(issue).strftime('%Y%m%dT%H%M')
            source = BASE / 'predictions/LGBM_180_14' / (key + '.parquet') if arm == 'R1' else ROOT / 'predictions' / arm / (key + '.parquet')
            expected = pd.read_parquet(source)
            expected = expected[expected.state.eq('RUNNING')].sort_values('job_issue_id')
            part = part.sort_values('job_issue_id')
            require(np.array_equal(part.job_issue_id, expected.job_issue_id), 'FINAL_FIT_QUERY_IDS')
            for column in ['Q50', 'Q90', 'Q95']:
                require(np.array_equal(part[column], expected[column]), 'FINAL_FIT_QUANTILE ' + column)
    joined = f.merge(jobs[['row_id', 'start_time', 'end_time', 'label_valid']], on='row_id', suffixes=('', '_source'), validate='many_to_one')
    start, end = joined.start_time_source, joined.end_time_source
    total = (end - start).dt.total_seconds().to_numpy()
    actual = np.where(joined.state.eq('RUNNING'), (end - joined.issue_time).dt.total_seconds(), total)
    actual = np.where(joined.label_valid_source, actual, np.nan)
    require(np.array_equal(joined.runtime_seconds, total, equal_nan=True), 'TOTAL_RUNTIME_LABEL')
    require(np.array_equal(joined.actual_seconds, actual, equal_nan=True), 'TOTAL_REMAINING_LABEL')
    require(np.isfinite(f.actual_seconds).all(), 'FINAL_UNSCORABLE_QUERY')
    return dict(rows=len(f), Pending_R0_all_arms_bit_exact=True, exact_running_query_memberships=True,
        total_runtime_gt_4h_definition_verified=True, R0_May_only=True, finite_ordered_AFT_quantiles=True)


def audit_metrics(f):
    model = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
    expected_model = set(f.groupby(['role', 'arm', 'state']).groups)
    require(len(model) == len(expected_model) and set(model[['role', 'arm', 'state']].itertuples(index=False, name=None)) == expected_model, 'MODEL_METRIC_ROWS')
    for _, r in model.iterrows():
        check_metric_row(r, f[f.role.eq(r.role) & f.arm.eq(r.arm) & f.state.eq(r.state)])
    strata = pd.read_csv(ROOT / 'RUNNING_ELAPSED_METRICS.csv')
    expected_strata = set()
    for (role, arm), group in f[f.state.eq('RUNNING')].groupby(['role', 'arm']):
        elapsed = group.elapsed_seconds / 3600
        names = np.select([elapsed < 1, elapsed < 2, elapsed < 4, elapsed <= 8], ['<1h', '1-2h', '2-4h', '4-8h'], default='>8h')
        expected_strata.update((role, arm, name) for name in np.unique(names))
    require(len(strata) == len(expected_strata) and set(strata[['role', 'arm', 'elapsed_regime']].itertuples(index=False, name=None)) == expected_strata, 'ELAPSED_METRIC_SET')
    for _, r in strata.iterrows():
        g = f[f.role.eq(r.role) & f.arm.eq(r.arm) & f.state.eq('RUNNING')]
        e = g.elapsed_seconds / 3600
        regime = np.select([e < 1, e < 2, e < 4, e <= 8], ['<1h', '1-2h', '2-4h', '4-8h'], default='>8h')
        check_metric_row(r, g[regime == r.elapsed_regime])
    quantiles = pd.read_csv(ROOT / 'QUANTILE_DIAGNOSTICS.csv')
    expected_quantiles = set()
    for (role, arm, state), group in f.groupby(['role', 'arm', 'state']):
        for tau in [.5, .9, .95]:
            if np.isfinite(group['Q' + str(int(tau * 100))]).all():
                expected_quantiles.add((role, arm, state, tau))
    require(len(quantiles) == len(expected_quantiles) and set(quantiles[['role', 'arm', 'state', 'quantile']].itertuples(index=False, name=None)) == expected_quantiles, 'QUANTILE_METRIC_SET')
    for _, r in quantiles.iterrows():
        g = f[f.role.eq(r.role) & f.arm.eq(r.arm) & f.state.eq(r.state)].copy()
        g['bound_seconds'] = g['Q' + str(int(r['quantile'] * 100))]
        check_metric_row(r, g)
        error = g.actual_seconds - g.bound_seconds
        close([r.proper_pinball], [np.maximum(r['quantile'] * error, (r['quantile'] - 1) * error).mean()], 'PROPER_PINBALL')
    return dict(model_rows=len(model), elapsed_rows=len(strata), quantile_rows=len(quantiles), all_direct_metrics_recomputed=True)


def audit_uncertainty(f):
    saved = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv')
    require(not saved.duplicated(['role', 'state', 'candidate', 'reference', 'block_days', 'metric']).any(), 'DUPLICATE_CI')
    rows_checked = nonfinite = 0
    expected_groups = set()
    for (role, state), g in f.groupby(['role', 'state']):
        pairs = [('R2', 'R1'), ('R3', 'R1'), ('R3', 'R2')]
        if role == 'MAY_HISTORICAL':
            pairs += [(a, 'R0') for a in ['R1', 'R2', 'R3']]
        for candidate, reference in pairs:
            a = g[g.arm.eq(candidate)].sort_values('job_issue_id')
            b = g[g.arm.eq(reference)].sort_values('job_issue_id')
            require(np.array_equal(a.job_issue_id, b.job_issue_id) and np.array_equal(a.actual_seconds, b.actual_seconds), 'CI_PAIRING')
            require(np.array_equal(a.issue_time, b.issue_time), 'CI_DAY_ALIGNMENT')
            va = np.array([sufficient(z) for _, z in a.groupby('issue_time', sort=True)])
            vb = np.array([sufficient(z) for _, z in b.groupby('issue_time', sort=True)])
            n = len(va)
            def effect(x, y):
                sa, sb = summarize(x), summarize(y)
                return np.stack([sa[k] - sb[k] for k in METRICS[:-1]] +
                    [1 - divide(sa['missed_GPU_slots'], sb['missed_GPU_slots'])], axis=-1)
            point = effect(va.sum(0), vb.sum(0))
            for block in [1, 7]:
                expected_groups.add((role, state, candidate, reference, block))
                rng = np.random.default_rng(SEED)
                index = np.array([((rng.integers(n, size=math.ceil(n / block))[:, None] + np.arange(block)) % n).ravel()[:n] for _ in range(DRAWS)])
                samples = effect(va[index].sum(1), vb[index].sum(1))
                subset = saved[saved.role.eq(role) & saved.state.eq(state) & saved.candidate.eq(candidate) & saved.reference.eq(reference) & saved.block_days.eq(block)]
                require(set(subset.metric) == set(METRICS) and len(subset) == len(METRICS), 'CI_METRIC_SET')
                for k, metric in enumerate(METRICS):
                    finite = np.isfinite(samples[:, k])
                    low, high = np.quantile(samples[finite, k], [.025, .975]) if finite.any() else (np.nan, np.nan)
                    r = subset[subset.metric.eq(metric)].iloc[0]
                    close([r.estimate, r.CI95_low, r.CI95_high], [point[k], low, high], 'CI ' + str((role, state, candidate, reference, block, metric)))
                    require(r.nonfinite_draws == int((~finite).sum()) and r.draws == DRAWS and r.N_days == n and r.N_pairs == len(a), 'CI_COUNTS')
                    nonfinite += int((~finite).sum())
                    rows_checked += 1
    got_groups = set(saved[['role', 'state', 'candidate', 'reference', 'block_days']].itertuples(index=False, name=None))
    require(got_groups == expected_groups and rows_checked == len(saved), 'CI_GROUP_SET')
    return dict(rows=rows_checked, comparisons_and_blocks=len(expected_groups), draws=DRAWS, seed=SEED,
                nonfinite_draws=nonfinite, all_metrics_and_ratios_recomputed_each_draw=True)


def main(check_only=False):
    require((ROOT / 'EVALUATION_COMPLETE.json').exists(), 'WAIT_FOR_EVALUATION_COMPLETE; no outputs written')
    registration = load(ROOT / 'REGISTRATION.json')
    freeze = load(ROOT / 'FINAL_SELECTION_FREEZE.json')
    complete = load(ROOT / 'EVALUATION_COMPLETE.json')
    for name, digest in registration['code'].items():
        require(sha(ROOT / name) == digest == freeze['code'][name], 'FROZEN_SCIENTIFIC_CODE ' + name)
    require(sha(ROOT / 'REGISTRATION.json') == freeze['registration_sha256'], 'REGISTRATION_HASH')
    require(sha(ROOT / 'DEVELOPMENT_CALIBRATION_METRICS.csv') == freeze['selection_metrics_sha256'], 'SELECTION_HASH')
    require(sha(ROOT / 'FINAL_SELECTION_FREEZE.json') == complete['freeze_sha256'], 'FINAL_FREEZE_HASH')
    require(sha(ROOT / 'PREDICTIONS.parquet') == complete['prediction_sha256'], 'FINAL_PREDICTION_HASH')
    reg_time, freeze_time, eval_time = [pd.Timestamp(v['time']) for v in [registration, freeze, complete]]
    require(reg_time < freeze_time < eval_time, 'FREEZE_SEQUENCE')
    require(complete['evaluation_reselection'] is False and freeze['May_previously_exposed'] is True, 'EXPOSURE_OR_RESELECTION')
    issues = pd.read_csv(BASE / 'ISSUES.csv')
    jobs = pd.read_parquet(BASE / 'JOB_MEMBERSHIP.parquet')
    fits = audit_fits(issues, jobs, freeze_time, reg_time)
    print('Independent fit memberships and receipts PASS', flush=True)
    selection = audit_selection(freeze, jobs, issues)
    frame = pd.read_parquet(ROOT / 'PREDICTIONS.parquet')
    predictions = audit_predictions(frame, jobs)
    metrics = audit_metrics(frame)
    uncertainty = audit_uncertainty(frame)
    result = dict(time=pd.Timestamp.now(tz='UTC').isoformat(), PASS=True,
        audit_source_sha256=sha(Path(__file__)), scientific_source_sha256=registration['code'],
        evaluation_complete_sha256=sha(ROOT / 'EVALUATION_COMPLETE.json'),
        final_selection_freeze_sha256=sha(ROOT / 'FINAL_SELECTION_FREEZE.json'),
        fits=fits, selection=selection, predictions=predictions, metrics=metrics, uncertainty=uncertainty,
        maximum_numeric_roundtrip_error=MAX_NUMERIC_ERROR, numeric_rtol=5e-11, numeric_atol=1e-7,
        fixed_quantile=.9, May='exposed historical diagnostic; no untouched confirmation',
        proxy_boundary='D1_SCHEDULER_REQUEST_STATE_PROXY_V1 and explicitly authorized archive-conditional censor risk set',
        request_provenance='UNVERIFIED/UNOBSERVED', historical_census_completeness='UNVERIFIED',
        historical_request_exactness_claimed=False, outcome_independent_archive_inclusion_claimed=False,
        production_readiness=False, model_training_during_review=0, scientific_files_modified=False,
        review='PASS within the authorized proxy scope; reserve preference failure must not be represented as operational superiority.')
    if not check_only:
        with (ROOT / 'INDEPENDENT_REVIEW.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Verify and print the result without replacing or creating a review record.')
    main(parser.parse_args().check_only)
