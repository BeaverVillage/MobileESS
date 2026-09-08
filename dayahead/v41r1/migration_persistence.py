"""Runtime audit schema for zero-PENDING days; electrical persistence is unchanged.

The established nonempty-day entry point remains authoritative. The empty-day
branch repeats its same checks and tables, with explicit typed runtime columns.
"""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.data import RUNTIME,issue_time
from dayahead.v41.preflight import record
from dayahead.v41.reserve import require,bind,validate_snapshot
from dayahead.v41.scalars import policy_inputs
from dayahead.v41.persistence import table,verify_table,SERVICE_LEVEL

RUNTIME_COLUMNS=dict(job_id='object',Q90_seconds='float64',Q90_duration_slots='int64',
    model_sha256='object',preprocessing_sha256='object',training_N='int64',training_membership_hash='object')


def pre_solve(day,snapshot_path,capacity):
    snapshot=read(snapshot_path)
    if snapshot['PENDING_JOB_Q90_SECONDS']:
        from dayahead.v41.persistence import pre_solve as existing
        return existing(day,snapshot_path,capacity)
    return _empty_pending_pre_solve(day,snapshot_path,capacity)


def _empty_pending_pre_solve(day, snapshot_path, capacity):
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
        for uid in sorted(seconds)], columns=list(RUNTIME_COLUMNS)).astype(RUNTIME_COLUMNS)
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

