"""One causal, sealed scalar ML authority shared by every daily policy."""
from pathlib import Path
import json
import numpy as np

from .data import RUNTIME, SOURCE_REPO, causal_history, pending_features, fit_runtime, issue_time, atomic_json
from .preflight import record
from .reserve import require, cap_reserve, validate_snapshot, OBJECTIVE_HIERARCHY
from .scalars import project


def capacity_authority():
    from dayahead.v41r2.authority import capacity,CAP,RACK
    cap,_=capacity()
    return cap,list(cap.aidc_ids),dict(source_variable='CapacityAuthority.site_capacity',files=[record(CAP),record(RACK)],rack_limits_added_to_capacity=False)


def legacy_capacity_authority():
    from dayahead.v39d.evaluate import _load_capacity
    capacity, details = _load_capacity(SOURCE_REPO)
    sites = [s for s in capacity.aidc_ids if capacity.eligible_racks(s, 1)]
    require(len(sites) == len(capacity.aidc_ids), 'FUTURE_SERVICE_SITE_ELIGIBILITY_NOT_CLOSED')
    # Frozen V39C equivalent-GPU service capacity; logical racks are nonadditive.
    files = [SOURCE_REPO / 'dayahead/artifacts' / folder / name for folder, name in (
        ('v39c_aidc_gpu_capacity_refreeze', 'V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json'),
        ('v39c_aidc_gpu_capacity_refreeze', 'V39C_CAPACITY_FREEZE_CERTIFICATE.json'),
        ('v39d_independent_daily_temporal_first_migration', 'V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json'),
        ('v39d_independent_daily_temporal_first_migration', 'V39D_RACK_FREEZE_CERTIFICATE.json'))]
    authority = dict(source_variable='CapacityAuthority.site_capacity',
        eligible_sites=sites, eligibility='Existing equivalent-GPU site service domain with compatible nonadditive logical racks',
        rack_limits_added_to_capacity=False, files=[record(p) for p in files])
    return capacity, sites, authority


def create(day):
    from dayahead.v41r2.authority import snapshot
    return snapshot(day)


def legacy_create_disabled(day):
    raise RuntimeError('V41R2_NO_ML_RETRAINING_OR_PREDICTION')
    folder = RUNTIME / 'inputs' / day
    path = folder / f'V41_ML_SNAPSHOT_{day}.json'
    capacity, sites, authority = capacity_authority()
    if path.exists():
        seal = json.loads((folder / 'ML_SNAPSHOT_RECEIPT.json').read_text(encoding='utf-8'))
        require(seal['snapshot'] == record(path), 'ML_SNAPSHOT_SEAL_DRIFT')
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        validate_snapshot(snapshot, capacity)
        require(seal['optimizer_scalar_sha256'] == project(snapshot).sha256, 'SCALAR_SEAL_DRIFT')
        return path, seal
    h, bins, work, history_receipt = causal_history(day)
    pending, pending_record = pending_features(day)
    runtime_path = folder / 'runtime_model/RUNTIME_AUTHORITY.json'
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
        for key in ('model', 'preprocessing'):
            require(runtime[key] == record(runtime[key]['path']), 'RUNTIME_MODEL_FILE_DRIFT')
        from dayahead.v40s5r1.common import ids
        require(runtime['runtime_training_membership_hash'] == ids(h.job_uid), 'RUNTIME_TRAINING_MEMBERSHIP_DRIFT')
        require(set(runtime['PENDING_JOB_Q90_SECONDS']) == set(pending.job_uid), 'PENDING_PREDICTION_MEMBERSHIP_DRIFT')
    else:
        runtime = fit_runtime(day, h, pending, folder / 'runtime_model')
    require(runtime['issue_time'] == issue_time(day).isoformat(), 'RUNTIME_ISSUE_DRIFT')
    from .workload import predict
    workload, pool = predict(day, bins, work)
    atomic_json(folder / 'H4_AUTHORITY.json', workload)
    atomic_json(folder / 'H4_CAP_POOL.json', pool)
    cap = np.tile([capacity.site_capacity[s] for s in sites], (96, 1)).astype(float)
    snapshot = dict(schema='V41_ML_SNAPSHOT_V1', target_day=day, **runtime,
        **workload,
        **cap_reserve(workload['H4_raw_predictions'], pool, cap),
        H24_OFF=True, H1_optimizer_OFF=True, H8_optimizer_OFF=True, burst15_optimizer_OFF=True,
        future_service_eligible_sites=sites, future_service_eligibility_authority=authority,
        future_service_capacity_gpu=cap.tolist(), objective_hierarchy=list(OBJECTIVE_HIERARCHY),
        optimizer_output_semantics='SCALAR_Q90_SECONDS_AND_SCALAR_CAPPED_H4_GPUh',
        H4_registered_service_level_metadata_only=.85,
        input_authority=dict(causal_history=record(folder / 'CAUSAL_INPUT_RECEIPT.json'),
                             pending_features_source=pending_record, H4_cap_pool=record(folder / 'H4_CAP_POOL.json')))
    validate_snapshot(snapshot, capacity)
    atomic_json(path, snapshot)
    seal = dict(snapshot=record(path), optimizer_scalar_sha256=project(snapshot).sha256,
        policies=['B0', 'B1', 'B2', 'B3'], stages=['REFERENCE', 'A0', 'A1'],
        policy_specific_forecasts=False, optimizer_probability_fields=[], actual_inputs_opened=False)
    atomic_json(folder / 'ML_SNAPSHOT_RECEIPT.json', seal)
    return path, seal


if __name__ == '__main__':
    import sys
    path, seal = create(sys.argv[1])
    print('ML_SNAPSHOT_READY', str(path), seal['snapshot']['sha256'], flush=True)
