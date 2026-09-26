"""Exact R6 B2 L0 H4 features and R6R1 expanding residual rule at live issues."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

from dayahead.v40r6.models import predict_pair
from .data import issue_time, SLOT_NS
from .preflight import R6, record
from .reserve import order_statistic, require

R6OUT = R6 / 'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork'
R5OUT = R6 / 'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
SERVICE_LEVEL = 0.85


def history_values(bins, index, origin):
    # Exact R3/R4 history_values used by frozen R5/R6 feature generation.
    require(index.isin(bins.index).all(), 'HISTORY_OUTSIDE_COMPLETE_SOURCE_COVERAGE')
    b = bins.loc[index]
    close = b.max_observed_end.copy()
    right = pd.Series(index + pd.Timedelta(minutes=30), index=index)
    close = close.where(close.notna() & close.gt(right), right)
    mature = (close.le(origin) & b.unresolved_end_count.eq(0)).to_numpy()
    work = np.where(mature, b.work_GPUh.to_numpy(), 0.)
    age = np.where(mature, (origin - close).dt.total_seconds().to_numpy() / 3600, 0.)
    return np.column_stack([b.submit_count.to_numpy(), work, mature.astype(float), age]).astype('float32')


def features(day, bins, work):
    origin = issue_time(day); begin = origin + pd.Timedelta(hours=6)
    index = pd.date_range(origin - pd.Timedelta(days=7), periods=336, freq='30min')
    past = history_values(bins, index, origin)
    values = []; names = []
    def add(name, value):
        names.append(name)
        values.append(np.broadcast_to(value, (96,)))
    for window in (12, 48, 336):
        for col, field in enumerate(('submit_count', 'mature_GPUh', 'mature_mask', 'maturity_age_hours')):
            for stat in ('mean', 'std', 'max'):
                add(f'history_{field}_{window}_{stat}', getattr(np, stat)(past[-window:, col]))
    for col, field in enumerate(('submit_count', 'mature_GPUh', 'mature_mask', 'maturity_age_hours')):
        add(f'history_{field}_last', past[-1, col])
    slot = np.arange(96); hour = slot / 4; dow = pd.Timestamp(day).weekday()
    for name, value in dict(slot15_fraction=slot/95, minute_of_day=slot*15,
        hour_sin=np.sin(2*np.pi*hour/24), hour_cos=np.cos(2*np.pi*hour/24),
        weekday_sin=np.sin(2*np.pi*dow/7), weekday_cos=np.cos(2*np.pi*dow/7),
        weekend=float(dow >= 5), child15_position=slot % 2, lead_hours=6 + slot/4).items():
        add(name, value)
    seasonal = []
    for lag in (7, 14, 21, 28):
        starts = pd.date_range(begin - pd.Timedelta(days=lag), periods=96, freq='15min')
        parents = starts.floor('30min')
        require(parents.isin(bins.index).all(), 'SEASONAL_SOURCE_COVERAGE_MISSING')
        b = bins.loc[parents]
        right = parents + pd.Timedelta(minutes=30)
        close = b.max_observed_end.reset_index(drop=True)
        right_series = pd.Series(right)
        close = close.where(close.notna() & close.gt(right_series), right_series)
        mature = ((b.unresolved_end_count.to_numpy() == 0) & close.le(origin).to_numpy()
                  & (starts + pd.Timedelta(minutes=15) <= origin))
        subset = work[work.submit_time.ge(starts[0]) & work.submit_time.lt(starts[-1] + pd.Timedelta(minutes=15))]
        location = ((subset.submit_time.dt.as_unit('ns').astype('int64').to_numpy() - starts[0].value) // SLOT_NS).astype(int)
        gpuwork = np.bincount(location, weights=subset.work_GPUh.to_numpy(), minlength=96)
        counts = np.bincount(location, minlength=96)
        gpuwork = np.where(mature, gpuwork, 0.); counts = np.where(mature, counts, 0.)
        for field, value in [('GPUh', gpuwork), ('count', counts), ('mature', mature.astype(float))]:
            add(f'seasonal15_{lag}d_{field}', value)
        strict = mature & close.lt(origin).to_numpy()
        seasonal.append((lag, gpuwork, strict, close))
    inherited = np.stack(values, axis=1).astype('float32')
    values2 = [inherited[:81], np.column_stack([np.arange(81), np.full(81, 4.)]).astype('float32')]
    names += ['window_start_slot', 'horizon_hours']
    for lag, gpuwork, mature, close in seasonal:
        masks = np.lib.stride_tricks.sliding_window_view(mature, 16).all(axis=1)
        totals = np.lib.stride_tricks.sliding_window_view(gpuwork, 16).sum(axis=1)
        values2.append(np.column_stack([np.where(masks, totals, 0.), masks]).astype('float32'))
        names += [f'cumulative_lag_{lag}d_GPUh', f'cumulative_lag_{lag}d_mature']
    X = np.concatenate(values2, axis=1).astype('float32')
    contract = json.loads((R6OUT / 'V40R6_FEATURE_CONTRACT.json').read_text(encoding='utf-8'))
    require(names == contract['feature_names'] and X.shape == (81, 71) and np.isfinite(X).all(), 'FROZEN_R6_FEATURE_CONTRACT_DRIFT')
    return X


def base_predict(X):
    fixed, raw, repair = predict_pair(R6OUT / 'fits/L0', 'H4', X)
    require(np.isfinite(fixed[:, 1]).all() and (fixed[:, 1] >= 0).all(), 'INVALID_H4_BASE_UPPER')
    return fixed[:, 1], {'quantile_crossing_repair': repair,
        'models': [record(R6OUT / 'fits/L0' / f'H4_Q{q}.txt') for q in (50, 90)]}


def frozen_history(issue):
    """Reuse precisely the original R6 OOS arrays, never TRAIN residuals."""
    target = pd.read_parquet(R6OUT / 'V40R6_CUMULATIVE_TARGET.parquet')
    ledger = pd.read_parquet(R5OUT / 'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet').set_index('operating_day')
    residual = []; cap = []; identifiers = []; days = set()
    phases = []
    with np.load(R6OUT / 'development_baselines.npz') as z:
        phases.append((z['row_ids'].copy(), np.load(R6OUT / 'fits/L0/development_q.npy')))
    for name in ('calibration_predictions.npz', 'exposed_predictions.npz'):
        with np.load(R6OUT / name) as z:
            phases.append((z['row_ids'].copy(), z['q'].copy()))
    for ids, q in phases:
        for position, row in enumerate(target.iloc[ids].itertuples()):
            if row.horizon != 'H4':
                continue
            available = max(pd.Timestamp(ledger.loc[row.day].target_end), pd.Timestamp(ledger.loc[row.day].target_label_available_at))
            if available < issue:
                residual.append(np.log1p(row.target_GPUh) - np.log1p(max(float(q[position, 1]), 0.)))
                identifiers.append(f'R6:{row.row_id}'); days.add(row.day)
    for row in target[target.horizon == 'H4'].itertuples():
        available = max(pd.Timestamp(ledger.loc[row.day].target_end), pd.Timestamp(ledger.loc[row.day].target_label_available_at))
        if available < issue:
            cap.append(float(row.target_GPUh))
    return residual, cap, identifiers, days


def extend_history(issue, bins, work):
    residual = []; cap = []; ids = []; days = set(); audit = []
    # R6's last target is Feb26. Subsequent OOS days use the same frozen
    # predictors and origin-time features, and enter only after full maturity.
    last = (issue.tz_convert('Etc/GMT-10') - pd.Timedelta(days=1)).date()
    for date in pd.date_range('2025-02-27', str(last), freq='D'):
        day = date.strftime('%Y-%m-%d'); begin = issue_time(day) + pd.Timedelta(hours=6); end = begin + pd.Timedelta(days=1)
        if end >= issue:
            continue
        daybins = bins[(bins.index >= begin) & (bins.index < end)]
        require(len(daybins) == 48, 'HISTORICAL_DAY_SOURCE_COVERAGE_MISSING:' + day)
        if daybins.gpu_unresolved.sum() > 0:
            audit.append({'day': day, 'status': 'LABEL_NOT_FULLY_MATURE'})
            continue
        subset = work[work.submit_time.ge(begin) & work.submit_time.lt(end)]
        available = max(end, subset.end_time.max()) if len(subset) else end
        if available >= issue:
            continue
        location = ((subset.submit_time.dt.as_unit('ns').astype('int64').to_numpy() - begin.value) // SLOT_NS).astype(int)
        atomic = np.bincount(location, weights=subset.work_GPUh.to_numpy(), minlength=96)
        actual = np.lib.stride_tricks.sliding_window_view(atomic, 16).sum(axis=1)
        base, _ = base_predict(features(day, bins, work))
        residual.extend((np.log1p(actual) - np.log1p(np.maximum(base, 0))).tolist())
        cap.extend(actual.tolist()); ids.extend(f'V41:{day}:{k}' for k in range(81)); days.add(day)
        audit.append({'day': day, 'status': 'MATURE_OOS', 'label_available_at': available.isoformat(), 'rows': 81})
    return residual, cap, ids, days, audit


def predict(day, bins, work):
    issue = issue_time(day)
    residual, cap_pool, membership, days = frozen_history(issue)
    rr, cc, mm, dd, extended = extend_history(issue, bins, work)
    residual += rr; cap_pool += cc; membership += mm; days |= dd
    require(len(days) >= 20 and len(residual) >= 500, 'H4_R85_CALIBRATION_SUPPORT_INSUFFICIENT')
    require(SERVICE_LEVEL == 17 / 20, 'H4_SERVICE_LEVEL_CONFIGURATION_DRIFT')
    q, rank = order_statistic(residual, 17, 20); delta = max(0., q)
    X = features(day, bins, work); base, authority = base_predict(X)
    raw = np.expm1(np.log1p(np.maximum(base, 0.)) + delta)
    require(np.isfinite(raw).all(), 'NONFINITE_H4_R85_UPPER')
    return dict(H4_model_id='H4_R85_B2', H4_delta85=delta, H4_raw_predictions=raw.tolist(),
        H4_BASE_L0_upper=base.tolist(), H4_calibration_support=dict(rows=len(residual), days=len(days),
            order_rank=rank, membership_sha256=hashlib.sha256(('\n'.join(sorted(membership))+'\n').encode()).hexdigest(),
            maturity_rule='max(target_day_end,target_label_available_at) < issue', extension_audit=extended),
        H4_model_authority=authority, H4_features=X.tolist()), cap_pool
