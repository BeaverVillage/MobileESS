"""Raw-label reconstruction and fixed target-resolution preparation only.

No model imports or fitting. Future completion fields reconstruct supervised
labels only; feature arrays are exact slices of the pinned causal 71 features.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'cc4_v2_hourly_future_workload'
TZ = 'Etc/GMT-10'
DAY_NS = 86_400_000_000_000
RAW_SHA256 = '3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f'
HOURLY_BURST = 860.3532222222221
RESOLUTIONS = ['H1', 'H3', 'H6', 'CUM']
END_HOURS = {'H1': np.arange(24), 'H3': np.arange(2, 24, 3),
             'H6': np.arange(5, 24, 6), 'CUM': np.arange(24)}
SPANS = {'H1': np.ones(24, int), 'H3': np.full(8, 3),
         'H6': np.full(4, 6), 'CUM': np.arange(1, 25)}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_once(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def aggregate_targets(hourly):
    y = np.asarray(hourly, dtype=np.float64)
    require(y.ndim == 2 and y.shape[1] == 24 and np.isfinite(y).all() and (y >= 0).all(), 'INVALID_HOURLY_TARGET')
    return dict(H1=y.copy(), H3=y.reshape(-1, 8, 3).sum(axis=2),
                H6=y.reshape(-1, 4, 6).sum(axis=2), CUM=np.cumsum(y, axis=1))


def anchored_features(x):
    require(x.ndim == 3 and x.shape[1:] == (24, 71) and x.dtype == np.float32 and np.isfinite(x).all(), 'INVALID_BASE_FEATURES')
    return {name: x[:, indices, :].copy() for name, indices in END_HOURS.items()}


def train_thresholds(targets, ledger):
    ids = np.flatnonzero(ledger.split.eq('TRAIN') & ledger.eligible)
    require(len(ids) > 0, 'NO_TRAIN_DAYS')
    result = dict(TRAIN_day_indices=ids.tolist(), TRAIN_target_days=ledger.target_day.iloc[ids].astype(str).tolist(),
                  definition='positive TRAIN target Q95; CUM separate threshold per prefix; strict > defines high load',
                  high_load_comparator='>', quantile=.95, supports={},
                  common_TRAIN_hourly_mean_GPUh=float(targets['H1'][ids].mean()))
    require(result['common_TRAIN_hourly_mean_GPUh'] > 0, 'NORMALIZER_UNSUPPORTED')
    for name in RESOLUTIONS:
        values = targets[name][ids]
        if name == 'CUM':
            positive = [values[:, k][values[:, k] > 0] for k in range(24)]
            require(all(len(p) for p in positive), 'CUM_TRAIN_HIGH_LOAD_UNSUPPORTED')
            result[name] = [float(np.quantile(p, .95)) for p in positive]
            result['supports'][name] = [len(p) for p in positive]
        else:
            positive = values[values > 0]
            require(len(positive) > 0, 'TRAIN_HIGH_LOAD_UNSUPPORTED ' + name)
            result[name] = float(np.quantile(positive, .95))
            result['supports'][name] = len(positive)
    return result


def day_indices(submit, days):
    epochs = pd.to_datetime(submit, utc=True).dt.as_unit('ns').astype('int64').to_numpy()
    ordinal = (epochs + 36_000_000_000_000) // DAY_NS
    requested = np.asarray(days, dtype='datetime64[D]').astype(np.int64)
    require(np.all(np.diff(requested) > 0), 'TARGET_DAY_ORDER')
    indices = np.searchsorted(requested, ordinal)
    matched = (indices < len(requested)) & (requested[np.minimum(indices, len(requested)-1)] == ordinal)
    return np.where(matched, indices, -1).astype(np.int32)


def eligible(rows):
    return (np.isfinite(rows.gpus_requested) & rows.gpus_requested.gt(0) & rows.start_time.notna()
            & rows.end_time.notna() & rows.end_time.gt(rows.start_time) & rows.start_time.ge(rows.submit_time))


def rebuild_raw(raw_path, days):
    population, inventory = [], []
    unresolved = np.zeros(len(days), dtype=np.int64)
    with zipfile.ZipFile(raw_path) as archive:
        names = sorted(name for name in archive.namelist() if re.search(r'year=\d{4}/month=\d+/.*\.parquet$', name))
        for member_index, name in enumerate(names):
            with archive.open(name) as stream:
                rows = pq.ParquetFile(stream).read(columns=['id', 'submit_time', 'start_time', 'end_time', 'gpus_requested'], use_threads=False).to_pandas()
            require(rows.id.notna().all() and rows.id.is_unique, 'RAW_MEMBER_IDS_INVALID')
            for field in ['submit_time', 'start_time', 'end_time']:
                rows[field] = pd.to_datetime(rows[field], utc=True).dt.as_unit('ns')
            require(rows.submit_time.notna().all(), 'RAW_SUBMIT_UNKNOWN')
            rows['gpus_requested'] = pd.to_numeric(rows.gpus_requested, errors='raise').astype(float)
            indices = day_indices(rows.submit_time, days)
            pending = (indices >= 0) & rows.gpus_requested.gt(0).to_numpy() & rows.end_time.isna().to_numpy()
            unresolved += np.bincount(indices[pending], minlength=len(days))
            valid = eligible(rows)
            selected = rows.loc[valid].copy()
            selected['archive_member_index'] = np.int16(member_index)
            selected['archive_row_index'] = np.flatnonzero(valid).astype(np.int32)
            selected['work_GPUh'] = selected.gpus_requested * (selected.end_time - selected.start_time).dt.total_seconds() / 3600
            population.append(selected)
            inventory.append(dict(member_index=member_index, member=name, raw_jobs=len(rows), eligible_jobs=len(selected)))
            print('RAW_TARGET_SOURCE', member_index, len(rows), len(selected), flush=True)
    work = pd.concat(population, ignore_index=True)
    require(work.id.is_unique and np.isfinite(work.work_GPUh).all(), 'RAW_ELIGIBLE_POPULATION_INVALID')
    return work, unresolved, inventory


def reconstruct_hourly(work, ledger, unresolved):
    days = ledger.target_day.astype(str).to_numpy()
    work = work.copy()
    work['day_index'] = day_indices(work.submit_time, days)
    target = work.loc[work.day_index >= 0].copy()
    target['hour'] = target.submit_time.dt.tz_convert(TZ).dt.hour.astype(np.int8)
    groups = target.groupby('day_index', sort=True).indices
    y, audit = [], []
    for i, day in enumerate(days):
        rows = target.iloc[groups.get(i, np.array([], dtype=int))]
        values = np.bincount(rows.hour.to_numpy(), weights=rows.work_GPUh.to_numpy(), minlength=24)
        end = (pd.Timestamp(day, tz=TZ) + pd.Timedelta(days=1)).tz_convert('UTC')
        latest = max(end, rows.end_time.max()) if len(rows) else end
        if unresolved[i]:
            latest = pd.Timestamp.max.tz_localize('UTC')
        y.append(values)
        audit.append(dict(day_index=i, target_day=day, jobs=len(rows), daily_GPUh=float(values.sum()),
                          direct_job_GPUh=float(rows.work_GPUh.sum()),
                          absolute_mass_error_GPUh=float(abs(values.sum()-rows.work_GPUh.sum())),
                          unresolved_positive_GPU_jobs=int(unresolved[i]), label_matured_at=latest.isoformat(),
                          issue_time=str(ledger.issue_time.iloc[i]), split=str(ledger.split.iloc[i]), eligible=bool(ledger.eligible.iloc[i])))
    return np.asarray(y), target, pd.DataFrame(audit)


def prepare(base=BASE, output=ROOT):
    base, output = Path(base), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = ['TARGETS.npz', 'HIGH_LOAD_THRESHOLDS.json', 'RAW_TARGET_JOB_MEMBERSHIP.parquet',
             'RAW_SOURCE_MEMBERS.json', 'DAILY_TARGET_AUDIT.csv', 'TARGET_FEATURE_CONTRACT.json', 'RAW_TARGET_AUDIT.json']
    require(not any((output / name).exists() for name in names), 'IMMUTABLE_TARGET_PREPARATION_EXISTS')
    sources = read(base / 'SOURCE_MANIFEST.json')['sources']
    raw = next(s for s in sources if s['purpose'] == 'raw Job authority, all parquet partitions')
    cached = next(s for s in sources if s['purpose'] == 'frozen CC4 eligible job population')
    require(sha(raw['path']) == raw['sha256'] == RAW_SHA256, 'RAW_ARCHIVE_HASH_DRIFT')
    require(sha(cached['path']) == cached['sha256'], 'PINNED_RAW_WORK_HASH_DRIFT')
    ledger = pd.read_csv(base / 'DAY_LEDGER.csv')
    with np.load(base / 'DATA.npz', allow_pickle=False) as saved:
        frozen_y, original_x, days = saved['y'].copy(), saved['X'].copy(), saved['days'].astype(str)
    require(np.array_equal(days, ledger.target_day.astype(str)), 'DAY_ALIGNMENT')
    require(len(days) == 443, 'TARGET_DAY_COUNT')
    work, unresolved, inventory = rebuild_raw(raw['path'], days)
    cached_work = pd.read_parquet(cached['path'])
    require(cached_work.id.is_unique, 'CACHED_RAW_WORK_DUPLICATE')
    raw_sorted = work.set_index('id').sort_index()
    old_sorted = cached_work.set_index('id').sort_index()
    require(raw_sorted.index.equals(old_sorted.index), 'POPULATION_ID_DIFFERENCE')
    for field in ['submit_time', 'start_time', 'end_time', 'gpus_requested', 'work_GPUh']:
        require(np.array_equal(raw_sorted[field], old_sorted[field]), 'POPULATION_FIELD_DIFFERENCE ' + field)
    work['pinned_raw_work_row_index'] = pd.Index(cached_work.id).get_indexer(work.id).astype(np.int32)
    expected_population = read(base / 'POPULATION_COMPARISON.json')
    require(len(work) == expected_population['eligible_jobs'] and sum(p['raw_jobs'] for p in inventory) == expected_population['raw_jobs'], 'POPULATION_COUNT_DIFFERENCE')
    y, target_jobs, daily = reconstruct_hourly(work, ledger, unresolved)
    require(np.array_equal(y, frozen_y), 'FROZEN_HOURLY_LABEL_DIFFERENCE')
    require(np.array_equal(pd.to_datetime(daily.label_matured_at, utc=True, format='mixed'), pd.to_datetime(ledger.label_matured_at, utc=True, format='mixed')), 'DAY_MATURITY_DIFFERENCE')
    require(np.array_equal(daily.jobs, ledger.jobs), 'DAY_JOB_MEMBERSHIP_DIFFERENCE')
    require(float(daily.absolute_mass_error_GPUh.max()) < 1e-7, 'RAW_DAILY_MASS_DIFFERENCE')
    targets, features = aggregate_targets(y), anchored_features(original_x)
    thresholds = train_thresholds(targets, ledger)
    require(thresholds['H1'] == HOURLY_BURST == read(base / 'TARGET_RECONSTRUCTION_AUDIT.json')['TRAIN_positive_Q95_burst_threshold_GPUh'], 'HOURLY_THRESHOLD_CHANGED')
    mass_errors = {name: float(np.max(abs(targets[name].sum(axis=1)-y.sum(axis=1)))) for name in ['H1', 'H3', 'H6']}
    mass_errors['CUM_terminal'] = float(np.max(abs(targets['CUM'][:, -1]-y.sum(axis=1))))
    difference_error = float(np.max(abs(np.diff(np.column_stack([np.zeros(len(y)), targets['CUM']]), axis=1)-y)))
    require(max(mass_errors.values()) < 1e-7 and difference_error < 1e-7, 'AGGREGATION_IDENTITY')
    proof = pd.read_parquet(base / 'FEATURE_MATURITY_PROOF.parquet')
    require((pd.to_datetime(proof.feature_available_at, utc=True) <= pd.to_datetime(proof.issue_time, utc=True)).all(), 'INHERITED_FEATURE_AVAILABILITY')
    feature_names = read(base / 'FEATURE_CONTRACT.json')['feature_names']
    require((original_x[:, :, feature_names.index('horizon_hours')] == 1).all(), 'LEGACY_HORIZON_FEATURE_CHANGED')
    payload = dict(days=days)
    for name in RESOLUTIONS:
        payload.update({f'y_{name}': targets[name], f'X_{name}': features[name],
                        f'span_{name}': SPANS[name], f'end_hour_{name}': END_HOURS[name]})
        for k, endpoint in enumerate(END_HOURS[name]):
            require(np.array_equal(features[name][:, k], original_x[:, endpoint]), 'FEATURE_ANCHOR_DIFFERENCE')
    np.savez_compressed(output / 'TARGETS.npz', **payload)
    target_jobs.to_parquet(output / 'RAW_TARGET_JOB_MEMBERSHIP.parquet', index=False, compression='zstd')
    daily.to_csv(output / 'DAILY_TARGET_AUDIT.csv', index=False, lineterminator='\n')
    write_once(output / 'HIGH_LOAD_THRESHOLDS.json', thresholds)
    write_once(output / 'RAW_SOURCE_MEMBERS.json', dict(raw_archive=raw, pinned_raw_work=cached, members=inventory,
        target_membership_rows=len(target_jobs), archive_row_index='zero-based row within named parquet member',
        pinned_raw_work_row_index='zero-based row in the exact SHA-pinned raw_work.parquet',
        supervised_label_membership='Each job belongs to submit-time target day/hour. Its full observed lifetime requested-GPU times runtime is the label, not a feature.',
        noneligible_raw_ID_global_uniqueness='Inherited from unchanged SHA-pinned PR63 raw audit; per-member and eligible-population uniqueness rechecked here'))
    write_once(output / 'TARGET_FEATURE_CONTRACT.json', dict(feature_names=feature_names, feature_count=71,
        endpoint_hours={k: v.tolist() for k, v in END_HOURS.items()}, target_spans_hours={k: v.tolist() for k, v in SPANS.items()},
        mapping='Exact unchanged hourly feature row at target block/prefix final constituent hour; no pooling or feature transforms',
        legacy_metadata='horizon_hours=1 and window_start_slot retain the original hourly anchor meaning; true aggregation span is separate metadata, not a modified feature',
        timezone=TZ, issue='D-1 18:00 fixed UTC+10',
        membership='Identical inherited full-day label_matured_at < issue_time, historical issue_time < current issue, non-PURGE; no earlier block/prefix maturity admission',
        CUM='prefix k sums hours0..k-1; prefixes overlap; only terminal24h is daily mass; sum of prefixes is never daily reserve',
        feature_version_provenance='UNVERIFIED', ingestion_latency='UNVERIFIED', feature_completion_fields_added=False,
        feature_maturity_proof_sha256=sha(base / 'FEATURE_MATURITY_PROOF.parquet')))
    source_paths = [base / n for n in ['SOURCE_MANIFEST.json', 'DATA.npz', 'DAY_LEDGER.csv', 'POPULATION_COMPARISON.json', 'TARGET_RECONSTRUCTION_AUDIT.json', 'FEATURE_CONTRACT.json', 'FEATURE_MATURITY_PROOF.parquet']]
    audit = dict(PASS=True, time=pd.Timestamp.now(tz='UTC').isoformat(), source_sha256=sha(__file__),
        raw_archive_sha256=raw['sha256'], pinned_raw_work_sha256=cached['sha256'],
        inherited_sources={str(p): sha(p) for p in source_paths},
        raw_partitions=len(inventory), raw_jobs=sum(p['raw_jobs'] for p in inventory), exact_eligible_population_jobs=len(work),
        exact_target_job_memberships=len(target_jobs), target_days=len(days), exact_raw_hourly_labels=y.size,
        maximum_hourly_label_difference_GPUh=0.0, exact_original_daily_maturity=True, exact_original_day_job_counts=True,
        maximum_direct_job_daily_mass_difference_GPUh=float(daily.absolute_mass_error_GPUh.max()),
        aggregate_mass_maximum_errors_GPUh=mass_errors, CUM_first_difference_maximum_error_GPUh=difference_error,
        CUM_prefix_sum_claimed_daily_mass=False, base_features_unchanged=True, feature_count=71,
        feature_available_time_checks=len(proof)*24, feature_version_provenance='UNVERIFIED',
        labels_from_future_completion_used_as_features=False, models_fitted=0, model_evaluation_metrics_consulted=False,
        thresholds_fit_only_TRAIN=True, target_values_capped=False,
        artifacts={name: sha(output / name) for name in names if name != 'RAW_TARGET_AUDIT.json'})
    write_once(output / 'RAW_TARGET_AUDIT.json', audit)
    print(json.dumps(dict(PASS=True, target_days=len(days), exact_hourly_labels=y.size,
                         target_jobs=len(target_jobs), target_npz_sha256=audit['artifacts']['TARGETS.npz'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    prepare(args.base, args.output)
