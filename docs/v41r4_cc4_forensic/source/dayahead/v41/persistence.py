"""Row-level numerical evidence and exact reopen checks around the DA seal."""
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pandas as pd

from dayahead.paper_analysis.storage import read, write_json, write_parquet
from .data import RUNTIME, issue_time
from .preflight import record
from .reserve import require, bind, validate_snapshot
from .scalars import policy_inputs

SERVICE_LEVEL = 0.85


def table(path, frame):
    """Preserve any previous numerical table and verify exact typed read-back."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_parquet(path, frame)
    reopened = pd.read_parquet(path)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), reopened, check_exact=True)
    return {**record(path), 'rows': len(frame), 'columns': list(frame.columns), 'readback_exact_equal': True}


def verify_table(entry):
    require({k: entry[k] for k in ('path', 'sha256', 'bytes')} == record(entry['path']), 'PERSISTED_TABLE_SHA256_DRIFT')
    frame = pd.read_parquet(entry['path'])
    require(len(frame) == entry['rows'] and list(frame.columns) == entry['columns'], 'PERSISTED_TABLE_SHAPE_DRIFT')
    return frame


def pre_solve(day, snapshot_path, capacity):
    snapshot_path = Path(snapshot_path); folder = RUNTIME / 'inputs' / day
    seal = read(folder / 'ML_SNAPSHOT_RECEIPT.json')
    require(seal['snapshot'] == record(snapshot_path), 'ML_SNAPSHOT_HASH_MISMATCH')
    snapshot = read(snapshot_path); validate_snapshot(snapshot, capacity)
    require(snapshot['H4_registered_service_level_metadata_only'] == SERVICE_LEVEL, 'H4_SERVICE_LEVEL_MUST_EQUAL_085')
    paths = list(folder.glob('V41_ML_SNAPSHOT_*.json'))
    require(paths == [snapshot_path], 'EXACTLY_ONE_DAILY_ML_SNAPSHOT_REQUIRED')
    audit_path = folder / 'PRE_SOLVE_PERSISTENCE_AUDIT.json'
    if audit_path.exists():
        previous = read(audit_path)
        require(previous['snapshot'] == record(snapshot_path), 'PERSISTENCE_SNAPSHOT_DRIFT')
        for entry in previous['tables'].values(): verify_table(entry)
    history_path = folder / 'runtime_history.parquet'
    history = pd.read_parquet(history_path, columns=['job_id', 'end_time'])
    require(history.end_time.lt(issue_time(day)).all() and history.job_id.is_unique, 'TRAINING_MEMBERSHIP_NOT_CAUSAL')
    from dayahead.v40s5r1.common import ids
    require(len(history) == snapshot['runtime_training_N'] and ids(history.job_id) == snapshot['runtime_training_membership_hash'],
            'TRAINING_MEMBERSHIP_REOPEN_MISMATCH')
    membership = history.sort_values(['end_time', 'job_id'], kind='mergesort').reset_index(drop=True)
    seconds = snapshot['PENDING_JOB_Q90_SECONDS']; durations = snapshot['PENDING_JOB_DURATION_SLOTS']
    predictions = pd.DataFrame([dict(job_id=uid, Q90_seconds=seconds[uid], Q90_duration_slots=durations[uid],
        model_sha256=snapshot['model']['sha256'], preprocessing_sha256=snapshot['preprocessing']['sha256'],
        training_N=snapshot['runtime_training_N'], training_membership_hash=snapshot['runtime_training_membership_hash'])
        for uid in sorted(seconds)])
    if day == '2025-05-01':
        require(len(predictions) == 1395, 'MAY01_PENDING_AUTHORITY_CHANGED_FROM_1395')
    raw = np.asarray(snapshot['H4_RAW_R85_B2_GPUh']); physical = np.asarray(snapshot['H4_CAP_PHYS'])
    hist = snapshot['H4_CAP_HIST']; actionable = np.asarray(snapshot['H4_ACTIONABLE_RESERVE_GPUh'])
    begin = issue_time(day) + pd.Timedelta(hours=6)
    start = pd.date_range(begin, periods=81, freq='15min')
    h4 = pd.DataFrame(dict(window_start=start, window_end=start + pd.Timedelta(hours=4),
        B2_base_GPUh=snapshot['H4_BASE_L0_upper'], delta85=snapshot['H4_delta85'], RAW_R85_B2_GPUh=raw,
        HIST_CAP_GPUh=hist, PHYS_CAP_GPUh=physical, ACTIONABLE_H4_GPUh=actionable,
        hist_cap_binding=(hist == actionable) & (actionable < raw),
        phys_cap_binding=(physical == actionable) & (actionable < raw),
        residual_support_days=snapshot['H4_calibration_support']['days'],
        residual_support_rows=snapshot['H4_calibration_support']['rows'], service_level=SERVICE_LEVEL))
    require(len(h4) == 81 and (h4.service_level == .85).all(), 'H4_PERSISTENCE_AXIS_OR_SERVICE_LEVEL')
    tables = dict(runtime_predictions=table(folder / 'PENDING_RUNTIME_PREDICTIONS.parquet', predictions),
        training_membership=table(folder / 'RUNTIME_TRAINING_MEMBERSHIP.parquet', membership),
        h4_windows=table(folder / 'H4_WINDOW_PREDICTIONS.parquet', h4))
    for key in ('model', 'preprocessing'):
        require(record(snapshot[key]['path']) == snapshot[key], 'FROZEN_RUNTIME_MODEL_HASH_DRIFT')
    bindings = []
    for policy in ('B0', 'B1', 'B2', 'B3'):
        for stage in ('A0', 'A1'):
            context = SimpleNamespace(capacity=capacity)
            bind(context, snapshot_path, seal['snapshot']['sha256'])
            scalar = policy_inputs(context.v41_ml_snapshot, policy, stage)
            bindings.append(dict(policy=policy, stage=stage, snapshot_hash=context.v41_ml_snapshot_sha256,
                                 optimizer_scalar_sha256=scalar.sha256))
    require(len({b['snapshot_hash'] for b in bindings}) == len({b['optimizer_scalar_sha256'] for b in bindings}) == 1,
            'POLICY_OR_A0_A1_SCALAR_BINDING_MISMATCH')
    audit = dict(status='PASS', day=day, snapshot=record(snapshot_path), snapshot_count=1, tables=tables,
        binding_status='PRE_SOLVE_ENTRYPOINT_BINDING_CHECK', bindings=bindings,
        service_level=.85, historical_CAL_coverage_used_as_parameter=False,
        historical_EXPOSED_coverage_used_as_parameter=False, May_coverage='UNKNOWN_UNTIL_POST_FREEZE_ACTUAL',
        raw_and_actionable_separate=True, binding_definition='cap equals actionable and actionable < raw; ties may bind both caps',
        row_counts_SHA256_and_exact_reopen_checked=True)
    write_json(audit_path, audit)
    # Reopen the receipt itself as well as the tables.
    require(read(audit_path) == audit, 'PERSISTENCE_RECEIPT_READBACK_MISMATCH')
    return audit


def optimizer_rows(output, snapshot, snapshot_hash, report):
    reserve = np.asarray(snapshot['H4_ACTIONABLE_RESERVE_GPUh'])
    available = np.asarray(report['H_available_GPUh']); xi = np.asarray(report['xi_GPUh'])
    slack = available + xi - reserve
    require(reserve.shape == available.shape == xi.shape == (81,) and np.min(slack) >= -1e-8, 'H4_CONSTRAINT_PERSISTENCE')
    start = pd.date_range(issue_time(snapshot['target_day']) + pd.Timedelta(hours=6), periods=81, freq='15min')
    frame = pd.DataFrame(dict(window_start=start, window_end=start + pd.Timedelta(hours=4),
        snapshot_hash=snapshot_hash, ACTIONABLE_H4_GPUh=reserve, available_headroom_GPUh=available,
        reserve_shortfall_xi_GPUh=xi, constraint_slack=slack, constraint_slack_GPUh=slack,
        RAW_R85_B2_GPUh=snapshot['H4_RAW_R85_B2_GPUh'], HIST_CAP_GPUh=snapshot['H4_CAP_HIST'],
        PHYS_CAP_GPUh=snapshot['H4_CAP_PHYS'], service_level=SERVICE_LEVEL))
    frame['hist_cap_binding'] = (frame.HIST_CAP_GPUh == reserve) & (reserve < frame.RAW_R85_B2_GPUh)
    frame['phys_cap_binding'] = (frame.PHYS_CAP_GPUh == reserve) & (reserve < frame.RAW_R85_B2_GPUh)
    return table(Path(output) / 'H4_OPTIMIZER_WINDOWS.parquet', frame)


def actual_rows(output, snapshot, actual_values):
    raw = np.asarray(snapshot['H4_RAW_R85_B2_GPUh']); capped = np.asarray(snapshot['H4_ACTIONABLE_RESERVE_GPUh'])
    actual = np.asarray(actual_values, float)
    require(actual.shape == raw.shape == capped.shape == (81,) and np.isfinite(actual).all() and (actual >= 0).all(),
            'ACTUAL_H4_WINDOW_AXIS')
    start = pd.date_range(issue_time(snapshot['target_day']) + pd.Timedelta(hours=6), periods=81, freq='15min')
    frame = pd.DataFrame(dict(window_start=start, window_end=start + pd.Timedelta(hours=4),
        RAW_R85_B2_GPUh=raw, ACTIONABLE_H4_GPUh=capped, ACTUAL_H4_GPUh=actual,
        RAW_COVERED=actual <= raw, ACTIONABLE_COVERED=actual <= capped,
        RAW_UNDER_GPUh=np.maximum(actual - raw, 0), RAW_OVER_GPUh=np.maximum(raw - actual, 0),
        ACTIONABLE_UNDER_GPUh=np.maximum(actual - capped, 0), ACTIONABLE_OVER_GPUh=np.maximum(capped - actual, 0),
        CLIPPED_GPUh=raw - capped))
    persisted = table(Path(output) / 'H4_ACTUAL_WINDOW_EVALUATION.parquet', frame)
    summary = dict(raw_H4_coverage=float(frame.RAW_COVERED.mean()), actionable_H4_coverage=float(frame.ACTIONABLE_COVERED.mean()),
        raw_under_GPUh=float(frame.RAW_UNDER_GPUh.sum()), raw_over_GPUh=float(frame.RAW_OVER_GPUh.sum()),
        actionable_under_GPUh=float(frame.ACTIONABLE_UNDER_GPUh.sum()), actionable_over_GPUh=float(frame.ACTIONABLE_OVER_GPUh.sum()),
        clipped_GPUh=float(frame.CLIPPED_GPUh.sum()), registered_service_level=.85,
        aggregation_note='Sums over overlapping rolling windows; not distinct workload mass',
        actionable_performance_is_raw_ML_accuracy=False, persisted=persisted)
    write_json(Path(output) / 'H4_RAW_VS_ACTIONABLE_COVERAGE.json', summary)
    return summary


if __name__ == '__main__':
    import sys
    from .snapshot import capacity_authority
    day = sys.argv[1]
    audit = pre_solve(day, RUNTIME / 'inputs' / day / f'V41_ML_SNAPSHOT_{day}.json', capacity_authority()[0])
    print('PERSISTENCE_AUDIT', audit['status'], {k: v['rows'] for k, v in audit['tables'].items()}, flush=True)
