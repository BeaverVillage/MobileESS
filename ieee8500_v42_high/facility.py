"""Unchanged workload, integer GPU installation scenarios and strict QoS audit.

This adapter never creates extra jobs, admits additional forecast service, changes
job placement or emits a fictitious flexible dispatch. Installation expansion
adds installed idle IT only; the frozen C1 response is recomputed without fitting.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from ieee8500_v42_aemo.common import read, write, table, sha, digest, receipt
from ieee8500_v42.capacity import load_c1_module
from ieee8500_v42.workload_flexibility import occupancy_by_job
from v42_capacity.queue import allocate, conservation

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/ieee8500_v42_high_impact_scenario'
DATA = ROOT / 'ieee8500_v42_high/data/facility'
OLD = ROOT / 'ieee8500_v42_aemo/data'
INPUT = ROOT / 'ieee8500_v42/data/v42_inputs'
PR193 = ROOT / 'docs/ieee8500_v42_single_case'
CAPACITY_CANDIDATES = {'C0': (780, 1.), 'C1': (1170, 1.5), 'C2': (1560, 2.)}
HARDWARE_URL = 'https://natlabrockies.github.io/HPC/Documentation/Systems/Kestrel/Running/'
HARDWARE_2024_URL = 'https://www.nrel.gov/docs/gen/fy24/90033.pdf'
QOS_URL = 'https://nrel.sitefinity.cloud/hpc/system-resource-allocation-unit'
TRACE_URL = 'https://data.openei.org/submissions/8643'


def load_inputs(capacity='C0', source='PLANNING'):
    """Return independently frozen arrays with identical E1 input conventions."""
    if capacity not in CAPACITY_CANDIDATES or source not in ('PLANNING', 'ACTUAL'):
        raise ValueError('UNREGISTERED_FACILITY_CASE')
    with np.load(DATA / f'{capacity}_{source}_INPUTS.npz', allow_pickle=False) as z:
        return {name: z[name].copy() for name in z.files}


def load_recomputed_inputs(capacity='C0', source='PLANNING'):
    """Capacity-specific common FCFS/queue replay; fixed files remain separate."""
    if capacity not in CAPACITY_CANDIDATES or source not in ('PLANNING', 'ACTUAL'):
        raise ValueError('UNREGISTERED_FACILITY_CASE')
    with np.load(DATA / 'recomputed' / f'{capacity}_{source}_INPUTS.npz', allow_pickle=False) as z:
        return {name: z[name].copy() for name in z.files}


def save_frozen_npz(path, arrays):
    """Keep already-consumed input bytes stable on deterministic audit reruns."""
    path = Path(path)
    if path.exists():
        with np.load(path, allow_pickle=False) as saved:
            assert set(saved.files) == set(arrays), 'FROZEN_ARRAY_KEYS_CHANGED'
            for key, value in arrays.items():
                np.testing.assert_array_equal(saved[key], value)
        return
    np.savez_compressed(path, **arrays)


def integer_installation(original, tag):
    target, scale = CAPACITY_CANDIDATES[tag]
    candidate = np.asarray(original, float) * scale
    if not np.equal(candidate, np.floor(candidate)).all() or int(candidate.sum()) != target:
        raise ValueError('NONINTEGER_OR_INCORRECT_TOTAL_GPU')
    return candidate.astype(int)


def actual_known_unknown(original, known_uids):
    """Retrospective ledger decomposition; no private event enters Planning."""
    ledger = pd.read_csv(OLD / 'derived/ACTUAL_QUEUE_LEDGER.csv', keep_default_na=False)
    sites = list(map(str, original['sites']))
    known = np.zeros((96, 12))
    unknown = np.zeros_like(known)
    starts = np.arange(96) * 900. + 21600.
    for row in ledger.to_dict('records'):
        if row['admitted_time'] == '':
            continue
        uid = str(row['job_uid'])
        left = float(row['admitted_time'])
        right = float(row['release_control_time']) if row['release_control_time'] != '' else 108000.
        overlap = np.maximum(0., np.minimum(starts + 900., right) - np.maximum(starts, left))
        target = known if uid in known_uids else unknown
        target[:, sites.index(row['site'])] += float(row['GPU_gang']) * overlap / 900.
    np.testing.assert_allclose(known + unknown, original['total_gpu'], atol=1e-9, rtol=0)
    return known, unknown, ledger


def power_arrays(source, original, capacities, power, module, params, weather, eligible):
    arrays = {name: value.copy() for name, value in original.items()}
    idle = float(power['current_IT_idle_kW_per_installed_GPU'])
    swing = float(power['current_IT_swing_kW_per_active_GPU'])
    it = idle * capacities[None, :] + swing * arrays['total_gpu']
    P = np.zeros_like(it)
    slopes = np.zeros_like(it)
    intercepts = np.zeros_like(it)
    secant_error = np.zeros_like(it)
    for t in range(96):
        wb = float(weather.iloc[t].t_wb_c)
        rh = float(weather.iloc[t].rh_pct)
        for k, site in enumerate(arrays['sites']):
            coeff = module.endpoint_secant(str(site), t, idle * capacities[k],
                (idle + swing) * capacities[k], wb, rh, params)
            slopes[t, k] = coeff.slope
            intercepts[t, k] = coeff.intercept_kw
            secant_error[t, k] = coeff.maximum_error_kw
            P[t, k] = (coeff.slope * it[t, k] + coeff.intercept_kw if source == 'PLANNING'
                        else module.exact_c1_pcc_kw(it[t, k], wb, rh, params))
    arrays.update(capacities=capacities, IT_kw=it, PCC_P_kw=P,
        PCC_Q_kvar=P * np.tan(np.arccos(power['PF_AIDC'])), C1_slope=slopes,
        C1_intercept_kw=intercepts, C1_maximum_secant_error_kw=secant_error,
        installed_idle_IT_kw=np.broadcast_to(idle * capacities[None, :], it.shape).copy(),
        workload_IT_kw=swing * arrays['total_gpu'], cooling_and_facility_kw=P - it)
    # Eligible masks are only projected on frozen Planning known-UID reference.
    # No realized future duration/arrival is promoted into a Planning actuator.
    if source == 'PLANNING':
        arrays.update(eligible_gpu=eligible.copy(),
            source_mask_P_upper_bound_kw=eligible * swing * slopes,
            source_mask_Q_upper_bound_kvar=eligible * swing * slopes * np.tan(np.arccos(power['PF_AIDC'])),
            fixed_IT_kw=idle * capacities[None, :] + swing * (arrays['total_gpu'] - eligible),
            source_mask_flexible_IT_kw=swing * eligible)
    arrays.update(certified_reducible_P_kw=np.zeros_like(P), certified_reducible_Q_kvar=np.zeros_like(P))
    assert np.isfinite(P).all() and (P >= it - 1e-10).all()
    assert (arrays['total_gpu'] <= capacities[None, :] + 1e-10).all()
    return arrays


def qos_audit(bundle, reference, original_plan, eligible, old_audit):
    """Prove conservation and retain current masks without converting proxies to SLAs."""
    native = read(ROOT / 'ieee8500_v42/data/workload_flexibility/NATIVE_INPUT.json')
    windows = read(ROOT / 'ieee8500_v42/data/workload_flexibility/WINDOWS.json')
    masks = pd.read_csv(PR193 / 'FLEXIBLE_WORKLOAD_JOB_MASKS.csv', keep_default_na=False)
    nby = {str(row['job_uid']): row for row in native['known_population']}
    pby = {str(row['job_uid']): row for row in bundle['known_population']}
    rby = {str(row['job_uid']): row for row in reference['rows']}
    wby = {str(row['job_id']): row for row in windows}
    mby = {str(row['job_uid']): row for row in masks.to_dict('records')}
    assert set(nby) == set(pby) == set(rby) == set(mby) and len(nby) == 1649
    active = occupancy_by_job(reference['rows'])
    recomputed = np.zeros((96, 12))
    sites = list(map(str, original_plan['sites']))
    rows = []
    for uid in sorted(nby):
        n, p, r, m = nby[uid], pby[uid], rby[uid], mby[uid]
        assert n['GPU_gang'] == p['GPU_gang'] == r['GPU_gang']
        assert n['service_slots'] == p['service_slots'] == r['service_slots']
        assert n['state'] == p['state'] == r['state']
        assert abs(float(n['exact_service_seconds']) - float(r['nominal_remaining_seconds'])) < 1e-9
        assert p['submit_time'] == r['submit_time']
        recomputed[:, sites.index(r['reference_site'])] += active[uid]
        win = wby.get(uid)
        current_in_window = bool(win and r['reference_start'] in win['allowed_starts'])
        rows.append(dict(job_uid=uid, state=r['state'], original_submit_time=r['submit_time'],
            original_GPU_gang=r['GPU_gang'], original_service_slots=r['service_slots'],
            original_Q50_nominal_service_seconds=r['nominal_remaining_seconds'],
            nominal_Dday_GPUh=float(active[uid].sum() / 4), original_raw_service_not_cloned=True,
            runtime_authority=r['runtime_authority'], raw_future_completion_used_for_planning=False,
            QoS=m['qos'], protected=m['protected'], planning_eligible=n['planning_eligible'],
            original_can_timeshift=n['can_timeshift'], effective_current_WINDOW_TS=m['effective_TS'],
            original_prestart_place=m['source_can_prestart_place'], original_checkpoint_migrate=m['source_can_checkpoint_migrate'],
            source_mask_candidate_MG=m['effective_MG_checkpoint_candidate'],
            reference_start=r['reference_start'], original_native_start=n['reference_start_if_authorized'],
            reference_site=r['reference_site'], original_native_site=n['planning_site'],
            reference_start_in_original_WINDOW=current_in_window,
            WINDOW_allowed_starts=win['allowed_starts'] if win else [],
            original_maximum_WAN_transfers=native['WAN']['maximum_active_transfers'],
            original_WAN_bytes_per_GPU=native['WAN']['bytes_per_gpu'],
            QoS_deadline_authority='EMPIRICAL_WAIT_PROXY_NOT_USER_SLA',
            checkpoint_application_support='SOURCE_MODEL_CANDIDATE_NOT_JOB_IMPLEMENTATION_PROOF',
            enlarged_facility_creates_more_service=False,
            full96_timeshift_migration_QoS_WAN_feasible='NOT_CERTIFIED',
            blocker='REFERENCE_WINDOW_SITE_START_AND_FULL_OPTION_COUPLING_UNBOUND'))
    np.testing.assert_allclose(recomputed, original_plan['known_gpu'], atol=1e-10, rtol=0)
    table(REPORT / 'AIDC_FLEXIBILITY_QOS_AUDIT.csv', rows)
    gpu = original_plan['known_gpu'] + original_plan['cc4_gpu']
    np.testing.assert_array_equal(gpu, original_plan['total_gpu'])
    source = bundle['forecast_inputs']['current_CC4']
    anon, incoming, outgoing = allocate(original_plan['known_gpu'], source['nominal_unknown_GPU_96'],
                                        original_plan['capacities'])
    np.testing.assert_array_equal(anon, original_plan['cc4_gpu'])
    cc4_conserved = conservation(sum(source['Q50_GPUh']), anon, outgoing[-1], source['full_tail_nominal_GPUh'])
    np.savez_compressed(DATA / 'SOURCE_B0_REPLAY_ONLY.npz', sites=original_plan['sites'],
        known_gpu=original_plan['known_gpu'], cc4_gpu=anon, total_gpu=gpu,
        backlog_in=incoming, backlog_out=outgoing, original_reference_job_uid=np.array(sorted(rby)),
        action_P_reduction_kw=np.zeros_like(gpu), action_Q_reduction_kvar=np.zeros_like(gpu))
    table(REPORT / 'AIDC_SOURCE_B0_REPLAY_96.csv', [dict(slot=t,
        known_GPUh=float(original_plan['known_gpu'][t].sum() / 4), CC4_GPUh=float(anon[t].sum() / 4),
        total_GPUh=float(gpu[t].sum() / 4), original_CC4_backlog_in_GPUh=float(incoming[t] / 4),
        original_CC4_backlog_out_GPUh=float(outgoing[t] / 4), AIDC_control_reduction_kw=0.,
        relocation_or_timeshift=False, migration_WAN_payload_bytes=0,
        source_reference_replay='SOURCE_B0_REPLAY_ONLY', V42_full_QoS_feasible_dispatch='NOT_CERTIFIED') for t in range(96)])
    queue = read(ROOT / 'docs/ieee8500_v42_aemo_voltage_rebuild/ACTUAL_Kestrel_QUEUE_AUDIT.json')
    uid_receipt = dict(original_1649_UID_set_equal=True, original_UID_and_arrival_GPU_service_identity=True,
        Planning_known_Dday_GPUh=float(recomputed.sum() / 4),
        Planning_CC4_Dday_GPUh=float(anon.sum() / 4), Planning_total_Dday_GPUh=float(gpu.sum() / 4),
        CC4_conservation=cc4_conserved,
        C0_C1_C2_known_gpu_occupancy_identical=True, C0_C1_C2_CC4_gpu_occupancy_identical=True,
        C0_C1_C2_service_GPUh_change=0., C0_C1_C2_terminal_backlog_change=0.,
        original_raw_UID_duplication=0, added_synthetic_jobs=0, workload_multiplier=1.,
        Actual_submitted_jobs=queue['submitted_jobs'], Actual_admitted_jobs=queue['admitted_jobs'],
        Actual_terminal_carryout_jobs=queue['carryout_jobs'], Actual_capacity_wait_jobs=queue['queued_jobs'],
        Actual_terminal_unadmitted_jobs=queue['submitted_jobs'] - queue['admitted_jobs'],
        Actual_private_RAW_archive=queue['raw_archive'],
        Actual_future_duration_controller_reads=queue['future_duration_controller_reads'],
        effective_CURRENT_WINDOW_TS_job_count=old_audit['effective_current_WINDOW_TS_job_count'],
        current_B0_vs_Native_start_mismatches=old_audit['B0_reference_start_mismatch_count'],
        current_B0_vs_Native_site_mismatches=old_audit['B0_reference_site_mismatch_count'],
        admitted_B0_outside_original_WINDOW_count=old_audit['B0_reference_outside_source_window_count'],
        effective_PS_job_count=old_audit['effective_source_PS_job_count'],
        source_Q50_checkpoint_candidate_count=old_audit['current_Q50_source_checkpoint_candidate_count'],
        eligible_Dday_GPUh=float(eligible.sum() / 4),
        eligible_mask_scope='SOURCE_CANDIDATE_PROJECTION_RELAXATION_NOT_EXECUTABLE_DISPATCH',
        actual_QoS_contract_deadline_proof='UNVERIFIED', research_WAIT_proxy_is_SLA=False,
        nonzero_AIDC_full96_control_schedule='FAIL_NOT_CERTIFIED',
        executable_artifact='SOURCE_B0_REPLAY_ONLY.npz',
        executable_artifact_certifies='UNCHANGED_OCCUPANCY_SERVICE_BACKLOG_ZERO_ACTION_ONLY',
        independent_QoS_window_feasibility_of_source_B0='NOT_CERTIFIED',
        controls_with_claimed_certified_reduction_kw=0., Native_solver_calls=0, Gurobi_calls=0)
    write(REPORT / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json', uid_receipt)
    return uid_receipt


def build_all():
    """Create all three installation scenarios before any AC/B policy results."""
    DATA.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    source_paths = [INPUT / 'POWER_AUTHORITY.json', INPUT / 'PLANNING_INPUT_BUNDLE.json',
        INPUT / 'C1_MODEL.json', INPUT / 'c1_affine.py', INPUT / 'source/dayahead/v28/thermal.py',
        OLD / 'derived/PLANNING_INPUTS.npz', OLD / 'derived/ACTUAL_INPUTS.npz',
        OLD / 'derived/REFERENCE.json', OLD / 'sources/GFS_D1_WEATHER.parquet',
        OLD / 'derived/NOAA_ACTUAL_96.parquet', PR193 / 'FLEXIBLE_WORKLOAD_AUDIT.json',
        PR193 / 'KNOWN_JOB_FLEXIBILITY_BOUND.npz', PR193 / 'FLEXIBLE_WORKLOAD_JOB_MASKS.csv',
        ROOT / 'ieee8500_v42/data/workload_flexibility/NATIVE_INPUT.json',
        ROOT / 'ieee8500_v42/data/workload_flexibility/WINDOWS.json',
        ROOT / 'docs/ieee8500_v42_aemo_voltage_rebuild/ACTUAL_Kestrel_QUEUE_AUDIT.json',
        OLD / 'derived/ACTUAL_QUEUE_LEDGER.csv']
    before = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
    bundle = read(INPUT / 'PLANNING_INPUT_BUNDLE.json')
    reference = read(OLD / 'derived/REFERENCE.json')
    power = read(INPUT / 'POWER_AUTHORITY.json')
    module = load_c1_module()
    params = module.load_c1(INPUT / 'C1_MODEL.json')
    old_audit = read(PR193 / 'FLEXIBLE_WORKLOAD_AUDIT.json')
    originals = {}
    for source in ('PLANNING', 'ACTUAL'):
        with np.load(OLD / f'derived/{source}_INPUTS.npz', allow_pickle=False) as z:
            originals[source] = {name: z[name].copy() for name in z.files}
    actual_known, actual_unknown, actual_ledger = actual_known_unknown(originals['ACTUAL'],
        {str(row['job_uid']) for row in bundle['known_population']})
    originals['ACTUAL'].update(known_at_issue_gpu=actual_known, post_issue_arrival_gpu=actual_unknown)
    with np.load(PR193 / 'KNOWN_JOB_FLEXIBILITY_BOUND.npz', allow_pickle=False) as z:
        eligible = z['eligible_gpu'].copy()
        np.testing.assert_array_equal(z['known_gpu'], originals['PLANNING']['known_gpu'])
    weather = {'PLANNING': pd.read_parquet(OLD / 'sources/GFS_D1_WEATHER.parquet'),
               'ACTUAL': pd.read_parquet(OLD / 'derived/NOAA_ACTUAL_96.parquet')}
    mapping = pd.read_csv(PR193 / 'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv')
    mby = {r.location_id: r for r in mapping.itertuples() if r.role == 'AIDC'}
    capacity_rows = []
    slot_rows = []
    results = {}
    summaries = []
    original_capacity = originals['PLANNING']['capacities']
    np.testing.assert_array_equal(original_capacity, originals['ACTUAL']['capacities'])
    for tag, (target, scale) in CAPACITY_CANDIDATES.items():
        cap = integer_installation(original_capacity, tag)
        results[tag] = {}
        for source in ('PLANNING', 'ACTUAL'):
            arrays = power_arrays(source, originals[source], cap, power, module, params, weather[source], eligible)
            for key in ('total_gpu', 'demand_mw', 'pv_mw', 'gross_factor', 'pv_factor'):
                np.testing.assert_array_equal(arrays[key], originals[source][key])
            if tag == 'C0':
                for key in ('IT_kw', 'PCC_P_kw', 'PCC_Q_kvar'):
                    np.testing.assert_allclose(arrays[key], originals[source][key], atol=1e-10, rtol=0)
            np.savez_compressed(DATA / f'{tag}_{source}_INPUTS.npz', **arrays)
            results[tag][source] = arrays
            summaries.append(dict(capacity_case=tag, source=source, installed_GPU=target,
                total_workload_GPUh=float(arrays['total_gpu'].sum() / 4),
                source_workload_GPUh_change=float((arrays['total_gpu'] - originals[source]['total_gpu']).sum() / 4),
                installed_idle_IT_energy_kWh=float(arrays['installed_idle_IT_kw'].sum() / 4),
                PCC_energy_kWh=float(arrays['PCC_P_kw'].sum() / 4),
                source_PCC_energy_kWh_change=float((arrays['PCC_P_kw'] - originals[source]['PCC_P_kw']).sum() / 4),
                minimum_system_PCC_kw=float(arrays['PCC_P_kw'].sum(1).min()),
                maximum_system_PCC_kw=float(arrays['PCC_P_kw'].sum(1).max()),
                maximum_source_mask_P_bound_kw=float(arrays.get('source_mask_P_upper_bound_kw', np.zeros((96, 12))).sum(1).max()),
                certified96_control_reduction_kw=0., job_clone_count=0, hardware_nameplate='UNVERIFIED'))
            for t in range(96):
                for k, site in enumerate(map(str, arrays['sites'])):
                    is_plan = source == 'PLANNING'
                    slot_rows.append(dict(capacity_case=tag, source=source, slot=t, aidc_id=site,
                        installed_GPU=int(cap[k]), total_active_GPU=float(arrays['total_gpu'][t, k]),
                        known_active_GPU=float(arrays['known_gpu'][t, k] if is_plan else arrays['known_at_issue_gpu'][t, k]),
                        post_issue_actual_arrival_GPU=float(arrays['post_issue_arrival_gpu'][t, k]) if not is_plan else '',
                        anonymous_CC4_GPU=float(arrays['cc4_gpu'][t, k]) if is_plan else 0,
                        eligible_known_GPU=float(eligible[t, k]) if is_plan else '',
                        installed_idle_IT_kw=float(arrays['installed_idle_IT_kw'][t, k]),
                        workload_IT_kw=float(arrays['workload_IT_kw'][t, k]),
                        source_mask_fixed_IT_kw=float(arrays['fixed_IT_kw'][t, k]) if is_plan else '',
                        source_mask_flexible_IT_kw=float(arrays['source_mask_flexible_IT_kw'][t, k]) if is_plan else '',
                        cooling_and_other_facility_kw=float(arrays['cooling_and_facility_kw'][t, k]),
                        PCC_P_kw=float(arrays['PCC_P_kw'][t, k]), PCC_Q_kvar=float(arrays['PCC_Q_kvar'][t, k]),
                        source_mask_reducible_P_upper_bound_kw=float(arrays['source_mask_P_upper_bound_kw'][t, k]) if is_plan else '',
                        certified_QoS_WAN_reducible_P_kw=0.,
                        exact_workload_service_preserved=True,
                        installed_idle_claimed_flexible=False, CC4_claimed_flexible=False,
                        source_mask_upper_bound_is_dispatch=False))
        for k, site in enumerate(map(str, originals['PLANNING']['sites'])):
            plan, actual = results[tag]['PLANNING'], results[tag]['ACTUAL']
            capacity_rows.append(dict(capacity_case=tag, capacity_scale=scale, aidc_id=site,
                fixed_MV_bus=mby[site].candidate_bus, original_installed_GPU=int(original_capacity[k]),
                proposed_installed_GPU=int(cap[k]), whole_GPU_integer_PASS=True,
                original_logical_single_gang_limit=bundle['rack_compatibility'][site][0],
                logical_gang_limit_increased=False, logical_rack_pool_is_physical_rack=False,
                physical_server_reference_GPUs_per_node=4, exact_four_GPU_server_count=float(cap[k] / 4),
                exact_four_GPU_server_integer_PASS=bool(cap[k] % 4 == 0),
                homogeneous_four_GPU_build_status='ARITHMETIC_ONLY_NOT_BOM' if cap[k] % 4 == 0 else 'FAIL_EXACT_4GPU_PACKING',
                physical_server_reference_source=HARDWARE_2024_URL,
                physical_server_PSU_kW='UNVERIFIED', physical_rack_power_kW='UNVERIFIED',
                physical_cooling_capacity_kW='UNVERIFIED', actual_GPU_SKU_inventory='UNVERIFIED',
                dedicated_AIDC_connection_transformer_kVA='ABSENT_IN_ORIGINAL_DSS_UNVERIFIED_DESIGN',
                original_nominal_1500kVA_PCC_overlay_claimed_as_real=False,
                original_model_idle_IT_kw=float(power['current_IT_idle_kW_per_installed_GPU'] * cap[k]),
                model_full_active_IT_kw=float((power['current_IT_idle_kW_per_installed_GPU'] + power['current_IT_swing_kW_per_active_GPU']) * cap[k]),
                frozen_Planning_max_PCC_kw=float(plan['PCC_P_kw'][:, k].max()),
                frozen_Actual_max_PCC_kw=float(actual['PCC_P_kw'][:, k].max()),
                frozen_max_PCC_kVA=float(max(np.hypot(plan['PCC_P_kw'][:, k], plan['PCC_Q_kvar'][:, k]).max(),
                                             np.hypot(actual['PCC_P_kw'][:, k], actual['PCC_Q_kvar'][:, k]).max())),
                max_full_installation_Planning_PCC_kw=float((plan['C1_slope'][:, k]
                    * (power['current_IT_idle_kW_per_installed_GPU'] + power['current_IT_swing_kW_per_active_GPU']) * cap[k]
                    + plan['C1_intercept_kw'][:, k]).max()),
                frozen_active_GPU_occupancy_unchanged=True, additional_service_GPUh=0.,
                physical_facility_nameplates='UNVERIFIED', physical_deployment_qualified=False,
                status='ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED'))
    table(REPORT / 'AIDC_FACILITY_CAPACITY_AUDIT.csv', capacity_rows)
    table(REPORT / 'AIDC_POWER_FLEXIBILITY_96SLOT.csv', slot_rows)
    table(REPORT / 'AIDC_FACILITY_SCENARIO_ENERGY.csv', summaries)
    qos = qos_audit(bundle, reference, originals['PLANNING'], eligible, old_audit)
    qos.update(Actual_known_at_issue_UID_count=int(actual_ledger.job_uid.astype(str).isin(
                   {str(row['job_uid']) for row in bundle['known_population']}).sum()),
               Actual_post_issue_arrival_UID_count=int((~actual_ledger.job_uid.astype(str).isin(
                   {str(row['job_uid']) for row in bundle['known_population']})).sum()),
               Actual_known_at_issue_Dday_GPUh=float(actual_known.sum() / 4),
               Actual_post_issue_arrival_Dday_GPUh=float(actual_unknown.sum() / 4),
               Actual_total_Dday_GPUh=float(originals['ACTUAL']['total_gpu'].sum() / 4),
               Actual_population_partition_scope='RETROSPECTIVE_LEDGER_AUDIT_NOT_PLANNING_INPUT',
               Actual_known_unknown_exact_reconstruction=True)
    write(REPORT / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json', qos)
    after = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
    assert before == after, 'SOURCE_IDENTITY_DRIFT'
    write(REPORT / 'AIDC_FACILITY_SOURCE_RECEIPT.json', dict(source_files_sha256=before,
        source_files_unchanged=True, original_population_sha256=digest(bundle['known_population']),
        hardware_sources=[HARDWARE_URL, HARDWARE_2024_URL], QoS_sources=[QOS_URL, TRACE_URL],
        source_type='PRIMARY_PUBLIC_HARDWARE_DOCUMENTATION_NOT_SITE_AS_BUILT',
        installation_expansion_rule='EXACT_SITE_MULTIPLIER_C1=1.5_C2=2.0_INTEGER_GPU_NO_ROUNDING',
        expansion_additional_active_GPU=0., expansion_additional_Job_UID=0,
        unchanged_job_service_backlog=True, changed_power='ADDITIONAL_INSTALLED_IDLE_IT_AND_FROZEN_C1_RESPONSE',
        original_C1_thermal_model_refit=False, power_model_full_nameplate_authority='UNVERIFIED',
        physical_full_QoS_rack_server_cooling_transformer_certificate=False,
        Native_solver_calls=0, Gurobi_calls=0, independent_Field_proof=False,
        arrays={f'{tag}_{source}': receipt(DATA / f'{tag}_{source}_INPUTS.npz')
                for tag in CAPACITY_CANDIDATES for source in ('PLANNING', 'ACTUAL')},
        QoS_receipt=qos))
    (REPORT / 'AIDC_FACILITY_QOS_METHOD_KO.md').write_text(
        '# AIDC 설치 규모·Job 서비스·유연성의 분리\n\n'
        'C0=780, C1=1170, C2=1560 GPU는 각 사이트의 원본 설치 수에 정확히 1/1.5/2를 '
        '곱한 연구 설계다. 정수 GPU와 사이트 합계는 검증했다. 12곳의 버스와 원본 logical single-gang '
        'compatibility envelope는 유지했다. 기존 4개 logical pool/site는 합산 가능한 실물 rack이 아니다. '
        '확장 설비의 서버·전원·rack·냉각·접속변압기 정격은 UNVERIFIED다.\n\n'
        'Planning 1649개 원본 UID/arrival/GPU/service와 원본 grid-blind reference·CC4 served/backlog를 '
        '세 후보에 동일하게 사용했다. Actual 2498개 원본 UID의 frozen causal queue 점유율도 동일하다. '
        '확장은 idle IT를 늘리고 원본 C1을 새 설치범위에서 재계산하며 Job 수나 service GPU-h를 늘리지 않는다. '
        'PCC−IT는 원본 C1의 냉각과 기타 시설 전력 합계이고 실측 냉각 정격이 아니다.\n\n'
        f'[2024 Kestrel 사양]({HARDWARE_2024_URL})은 4 GPU/node를 설명한다. C0/C2는 4-GPU 단위 '
        '정수 분할이 가능하지만 C1의 AIDC05=150은 37.5 node여서 정확한 동종 4-GPU 설비는 실패한다. '
        'GPU SKU·혼합 서버·부분 탑재 증거가 없으므로 1172개 GPU를 1170으로 이름 바꾸거나 서버를 '
        '임의 추가하지 않는다. 이 산술 사례가 다른 시설의 현장 전기·냉각 적격성을 증명하지 않는다.\n\n'
        f'[Kestrel QoS 문서]({QOS_URL})의 normal/high는 scheduling priority와 charge factor이다. '
        f'[원본 데이터 메타데이터]({TRACE_URL})의 queue wait/runtime는 실제 사용자 deadline·'
        'application checkpoint/restart 계약을 제공하지 않는다. 원본 코드도 wait quantile을 '
        'Empirical historical additional-delay budget; not SLA or user tolerance로 명시한다. '
        '20/30/40% flexible share를 신규 실측 계약으로 만들지 않았다.\n\n'
        f'기존 B0와 Native reference는 site {qos["current_B0_vs_Native_site_mismatches"]}개, start '
        f'{qos["current_B0_vs_Native_start_mismatches"]}개가 다르며 admitted B0 start '
        f'{qos["admitted_B0_outside_original_WINDOW_count"]}개가 원본 WINDOW 밖이다. '
        'source-mask upper bound는 이 reference에 투영한 완화이며 동시에 제거한 일을 다른 시점/사이트에서 '
        '수행하는 실제 schedule이 아니다. WAN 1 active transfer, 80 GB/GPU payload와 '
        'destination capacity, checkpoint/restart, deadline, post-H tail을 묶는 adapter가 검증되지 않았다. '
        'SOURCE_B0_REPLAY_ONLY는 96-slot 원본 occupancy·service·backlog와 zero action을 재현한다. '
        '원본 B0의 Native QoS window 적격성을 새로 인증하거나 nonzero control을 증명하지 않는다. '
        '따라서 nonzero AIDC 96-slot 실행 가능 제어는 FAIL_NOT_CERTIFIED이며 certified 감소는 0 kW다.\n',
        encoding='utf-8')
    return results


def capacity_reference_eligibility(reference_rows, native, windows, sites):
    """Reproject original masks on each new reference; no new capability rights."""
    from ieee8500_v42.workload_flexibility import compatible_sites, make_job
    from v42_job_capability import checkpoint_records
    native_by = {str(r['job_uid']): r for r in native['known_population']}
    window_by = {str(r['job_id']): r for r in windows}
    activity = occupancy_by_job(reference_rows)
    eligibility = np.zeros((96, 12))
    records = []
    for row in reference_rows:
        uid = str(row['job_uid'])
        source = native_by[uid]
        win = window_by.get(uid)
        compatible = compatible_sites(native, source)
        admitted = bool(source['planning_eligible'])
        ts = bool(admitted and win and win['can_timeshift'])
        ps = bool(admitted and source['can_prestart_place'] and source['state'] == 'PENDING' and len(compatible) > 1)
        cps = ()
        native_cps = ()
        if admitted and source['can_checkpoint_migrate'] and source['service_slots'] > 0:
            native_job = make_job(source, source['reference_start_if_authorized'], source['planning_site'], compatible)
            native_cps = tuple(cp for cp, _ in checkpoint_records(native_job, native_job.reference_start,
                min(native_job.reference_start + native_job.service_slots, 120)) if 24 <= cp < 118)
            job = make_job(source, row['reference_start'], row['reference_site'], compatible)
            cps = tuple(cp for cp, _ in checkpoint_records(job, job.reference_start,
                min(job.reference_start + job.service_slots, 120)) if 24 <= cp < 118)
        mg = bool(native_cps and cps and len(compatible) > 1)
        mature = np.arange(24, 120) >= min(cps) if mg else np.zeros(96, dtype=bool)
        enabled = np.logical_or(ts or ps, mature)
        active = activity[uid]
        eligibility[:, sites.index(row['reference_site'])] += active * enabled
        seconds = float(row['nominal_remaining_seconds'])
        begin = int(row['reference_start']) * 900.
        end = begin + seconds
        gang = int(row['GPU_gang'])
        prefix = gang * max(0., min(end, 21600.) - max(begin, 0.)) / 3600.
        dday = gang * max(0., min(end, 108000.) - max(begin, 21600.)) / 3600.
        tail = gang * max(0., end - max(begin, 108000.)) / 3600.
        expected = gang * seconds / 3600.
        assert abs(prefix + dday + tail - expected) < 1e-9
        records.append(dict(job_uid=uid, submit_time=row['submit_time'], GPU_gang=gang,
            runtime_authority=row['runtime_authority'], unchanged_nominal_remaining_seconds=seconds,
            unchanged_service_slots=row['service_slots'], exact_nominal_required_GPUh=expected,
            prefix_processed_GPUh=prefix, Dday_processed_GPUh=dday, post96_tail_GPUh=tail,
            exact_service_conservation_error_GPUh=prefix + dday + tail - expected,
            reference_start=row['reference_start'], reference_site=row['reference_site'],
            original_Native_start=source['reference_start_if_authorized'], original_Native_site=source['planning_site'],
            reference_start_in_original_WINDOW=bool(win and row['reference_start'] in win['allowed_starts']),
            planning_eligible=admitted, original_WINDOW_TS=ts, original_PS=ps,
            source_checkpoint_candidate=mg, eligible_Dday_GPUh=float((active * enabled).sum() / 4),
            actual_user_deadline='UNVERIFIED', original_WINDOW_is_empirical_not_SLA=True,
            certified_full96_flexible_dispatch=False,
            status='ORIGINAL_CAPABILITY_MASK_REFERENCE_PROJECTION_ONLY'))
    return eligibility, records


def recompute_actual(capacities, reference, plan, actual, source_truth):
    """Same original submissions and private runtime, separate causal FCFS replay."""
    from v42_capacity.actual import Request, Environment, replay
    issue = pd.Timestamp(plan['issue_time'])
    seconds = lambda value: (pd.Timestamp(value) - issue).total_seconds()
    known_ids = {str(j['job_uid']) for j in plan['known_population']}
    jobs = plan['known_population'] + actual['post_issue_arrivals']
    by_uid = {str(j['job_uid']): j for j in jobs}
    assert len(by_uid) == len(jobs) == 2498 and set(by_uid) == set(source_truth)
    requests, running, durations, completions = [], [], {}, {}
    rby = {str(r['job_uid']): r for r in reference}
    authority_rows = []
    for uid, job in by_uid.items():
        private = source_truth[uid]
        assert pd.Timestamp(private['submit_time']) == pd.Timestamp(job['submit_time'])
        assert int(private['immutable_requested_GPU']) == int(job['GPU_gang'])
        duration = (pd.Timestamp(private['end_time']) - pd.Timestamp(private['start_time'])).total_seconds()
        assert abs(duration - float(private['realized_seconds'])) < 1e-6
        request = Request(uid, seconds(job['submit_time']), int(job['GPU_gang']),
                          tuple(job['compatible_sites']), float(job['Q50_total_seconds']), job['source_site'])
        durations[uid] = duration
        if job['state_at_D1_cutoff'] == 'RUNNING':
            begin, end = seconds(private['start_time']), seconds(private['end_time'])
            assert begin <= 0 < end
            running.append((request, rby[uid]['reference_site'], begin))
            completions[uid] = end
        else:
            requests.append(request)
        authority_rows.append(dict(job_uid=uid, immutable_submit_time=private['submit_time'],
            immutable_GPU_gang=job['GPU_gang'], immutable_realized_runtime_seconds=duration,
            immutable_required_realized_GPUh=duration * job['GPU_gang'] / 3600.,
            known_at_issue=uid in known_ids, controller_future_duration_reads=0,
            clone_count=0, source_member=private['source_member'], source_row=private['source_row']))
    gpu, ledger, audit = replay(capacities, requests, Environment(durations, completions), running=running)
    sites = sorted(capacities)
    known, unknown = np.zeros_like(gpu), np.zeros_like(gpu)
    starts = 21600. + np.arange(96) * 900.
    for row in ledger:
        if row['admitted_time'] is None:
            continue
        end = row['release_control_time'] if row['release_control_time'] is not None else 108000.
        overlap = np.maximum(0., np.minimum(starts + 900., end) - np.maximum(starts, row['admitted_time']))
        (known if row['job_uid'] in known_ids else unknown)[:, sites.index(row['site'])] += row['GPU_gang'] * overlap / 900.
    np.testing.assert_allclose(known + unknown, gpu, atol=1e-9, rtol=0)
    ledger_by = {str(r['job_uid']): r for r in ledger}
    executed = np.zeros_like(gpu)
    for row in authority_rows:
        event = ledger_by[row['job_uid']]
        duration = float(row['immutable_realized_runtime_seconds'])
        gang = int(row['immutable_GPU_gang'])
        if event['admitted_time'] is None:
            before, prefix, dday = 0., 0., 0.
        else:
            begin = float(event['admitted_time'])
            end = begin + duration
            before = gang * max(0., min(end, 0.) - begin) / 3600.
            prefix = gang * max(0., min(end, 21600.) - max(begin, 0.)) / 3600.
            dday = gang * max(0., min(end, 108000.) - max(begin, 21600.)) / 3600.
            overlap = np.maximum(0., np.minimum(starts + 900., end) - np.maximum(starts, begin))
            executed[:, sites.index(event['site'])] += gang * overlap / 900.
        remaining = row['immutable_required_realized_GPUh'] - before - prefix - dday
        assert remaining >= -1e-9
        residual = before + prefix + dday + remaining - row['immutable_required_realized_GPUh']
        assert abs(residual) < 1e-9
        row.update(already_executed_before_issue_GPUh=before, prefix_executed_GPUh=prefix,
                   Dday_executed_GPUh=dday, required_service_remaining_after96_GPUh=max(0., remaining),
                   exact_realized_service_conservation_error_GPUh=residual)
    audit.update(executed_Dday_GPUh=float(executed.sum() / 4), physical_occupied_Dday_GPUh=float(gpu.sum() / 4),
                 release_rounding_reserved_Dday_GPUh=float((gpu - executed).sum() / 4),
                 immutable_total_full_realized_GPUh=sum(r['immutable_required_realized_GPUh'] for r in authority_rows),
                 already_executed_before_issue_GPUh=sum(r['already_executed_before_issue_GPUh'] for r in authority_rows),
                 prefix_executed_GPUh=sum(r['prefix_executed_GPUh'] for r in authority_rows),
                 required_service_remaining_after96_GPUh=sum(r['required_service_remaining_after96_GPUh'] for r in authority_rows),
                 exact_realized_service_conservation_error_GPUh=sum(r['exact_realized_service_conservation_error_GPUh'] for r in authority_rows))
    return gpu, known, unknown, ledger, audit, authority_rows


def recompute_all():
    """Recompute every capacity without looking at electrical/Actual outcomes."""
    from v42_capacity.reference import build_reference
    from v42_modelable.power import known_occupancy
    out = DATA / 'recomputed'
    out.mkdir(parents=True, exist_ok=True)
    old_report = REPORT / 'facility_fixed_occupancy_preserved'
    old_report.mkdir(parents=True, exist_ok=True)
    for name in ('AIDC_FACILITY_CAPACITY_AUDIT.csv', 'AIDC_FLEXIBILITY_QOS_AUDIT.csv',
                 'AIDC_POWER_FLEXIBILITY_96SLOT.csv', 'AIDC_FACILITY_SCENARIO_ENERGY.csv',
                 'AIDC_FLEXIBILITY_QOS_RECEIPT.json', 'AIDC_FACILITY_SOURCE_RECEIPT.json',
                 'AIDC_FACILITY_QOS_METHOD_KO.md', 'AIDC_SOURCE_B0_REPLAY_96.csv'):
        previous = REPORT / name
        saved = old_report / name
        if not saved.exists() and previous.exists():
            saved.write_bytes(previous.read_bytes())
    bundle = read(INPUT / 'PLANNING_INPUT_BUNDLE.json')
    private_bundle = ROOT / 'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE/DAY_20250501/ACTUAL_INPUT_BUNDLE.json'
    actual_bundle = read(private_bundle)
    native = read(ROOT / 'ieee8500_v42/data/workload_flexibility/NATIVE_INPUT.json')
    windows = read(ROOT / 'ieee8500_v42/data/workload_flexibility/WINDOWS.json')
    raw_join_path = OLD / 'sources/PRIVATE_ACTUAL_Kestrel_UID_JOIN.csv'
    truth_rows = pd.read_csv(raw_join_path, keep_default_na=False).to_dict('records')
    truth = {str(row['job_uid']): row for row in truth_rows}
    power = read(INPUT / 'POWER_AUTHORITY.json')
    module = load_c1_module()
    params = module.load_c1(INPUT / 'C1_MODEL.json')
    originals = {}
    for source in ('PLANNING', 'ACTUAL'):
        with np.load(OLD / f'derived/{source}_INPUTS.npz', allow_pickle=False) as z:
            originals[source] = {key: z[key].copy() for key in z.files}
    weather = {'PLANNING': pd.read_parquet(OLD / 'sources/GFS_D1_WEATHER.parquet'),
               'ACTUAL': pd.read_parquet(OLD / 'derived/NOAA_ACTUAL_96.parquet')}
    sites = list(map(str, originals['PLANNING']['sites']))
    old_reference = read(OLD / 'derived/REFERENCE.json')['rows']
    old_ref_by = {str(r['job_uid']): r for r in old_reference}
    source_paths = [INPUT / 'PLANNING_INPUT_BUNDLE.json', private_bundle, raw_join_path,
                    INPUT / 'POWER_AUTHORITY.json', INPUT / 'C1_MODEL.json',
                    OLD / 'derived/PLANNING_INPUTS.npz', OLD / 'derived/ACTUAL_INPUTS.npz']
    source_before = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    results, summaries, qos_rows, slots = {}, [], [], []
    facility_rows = pd.read_csv(old_report / 'AIDC_FACILITY_CAPACITY_AUDIT.csv', keep_default_na=False).to_dict('records')
    for tag, (target, _) in CAPACITY_CANDIDATES.items():
        cap = integer_installation(originals['PLANNING']['capacities'], tag)
        capacities = {site: int(cap[k]) for k, site in enumerate(sites)}
        refs, ref_audit = build_reference(bundle['known_population'], capacities,
            bundle['rack_compatibility'], issue_time=bundle['issue_time'])
        assert ref_audit['full_reference_ready'] and ref_audit['blocked_jobs'] == 0
        assert ref_audit['population_sha256'] == digest(bundle['known_population'])
        for row in refs:
            old = old_ref_by[str(row['job_uid'])]
            for key in ('job_uid', 'submit_time', 'GPU_gang', 'service_slots', 'nominal_remaining_seconds',
                        'Q50_total_seconds', 'runtime_authority'):
                assert row[key] == old[key], f'IMMUTABLE_JOB_FIELD_CHANGED:{key}'
        known = known_occupancy(refs, sites)
        cc4 = bundle['forecast_inputs']['current_CC4']
        anonymous, backlog_in, backlog_out = allocate(known, cc4['nominal_unknown_GPU_96'], cap)
        conserved = conservation(sum(cc4['Q50_GPUh']), anonymous, backlog_out[-1], cc4['full_tail_nominal_GPUh'])
        eligible, job_audit = capacity_reference_eligibility(refs, native, windows, sites)
        assert np.all(eligible <= known + 1e-9)
        plan_input = dict(originals['PLANNING'], capacities=cap, known_gpu=known, cc4_gpu=anonymous,
                          total_gpu=known + anonymous, backlog_in=backlog_in, backlog_out=backlog_out)
        arrays = power_arrays('PLANNING', plan_input, cap, power, module, params, weather['PLANNING'], eligible)
        results[tag] = {'PLANNING': arrays}
        save_frozen_npz(out / f'{tag}_PLANNING_INPUTS.npz', arrays)
        write(out / f'{tag}_REFERENCE.json', dict(rows=refs, audit=ref_audit))
        table(out / f'{tag}_JOB_SERVICE_AUDIT.csv', job_audit)
        for row in job_audit:
            old = old_ref_by[row['job_uid']]
            qos_rows.append(dict(capacity_case=tag, **row,
                baseline_C0_reference_start=old['reference_start'], baseline_C0_reference_site=old['reference_site'],
                changed_start_from_C0=row['reference_start'] != old['reference_start'],
                changed_site_from_C0=row['reference_site'] != old['reference_site'],
                required_GPUh_changed=False, installed_GPU_increase_creates_new_JOB=False))
        print(tag, 'recomputed Planning ready; knownGPUh=', known.sum() / 4,
              'totalPmax=', arrays['PCC_P_kw'].sum(1).max(), flush=True)
        actual_gpu, actual_known, actual_unknown, ledger, queue_audit, immutable_actual = recompute_actual(
            capacities, refs, bundle, actual_bundle, truth)
        actual_input = dict(originals['ACTUAL'], capacities=cap, total_gpu=actual_gpu,
            known_at_issue_gpu=actual_known, post_issue_arrival_gpu=actual_unknown)
        actual_arrays = power_arrays('ACTUAL', actual_input, cap, power, module, params, weather['ACTUAL'], eligible)
        results[tag]['ACTUAL'] = actual_arrays
        save_frozen_npz(out / f'{tag}_ACTUAL_INPUTS.npz', actual_arrays)
        table(out / f'{tag}_ACTUAL_QUEUE_LEDGER.csv', ledger)
        table(out / f'{tag}_ACTUAL_IMMUTABLE_JOB_AUDIT.csv', immutable_actual)
        write(out / f'{tag}_ACTUAL_QUEUE_RECEIPT.json', queue_audit)
        source_exact_known = sum(r['exact_nominal_required_GPUh'] for r in job_audit)
        source_reserved_known = sum(r['GPU_gang'] * r['service_slots'] / 4 for r in refs)
        actual_required = sum(r['immutable_required_realized_GPUh'] for r in immutable_actual)
        original_in_window = sum(not r['reference_start_in_original_WINDOW']
                                 for r in job_audit if r['planning_eligible'])
        for source, arr in results[tag].items():
            base = originals[source]
            if tag == 'C0':
                for key in ('total_gpu', 'IT_kw', 'PCC_P_kw', 'PCC_Q_kvar'):
                    np.testing.assert_allclose(arr[key], base[key], atol=1e-10, rtol=0)
            for key in ('demand_mw', 'pv_mw', 'gross_factor', 'pv_factor'):
                np.testing.assert_array_equal(arr[key], base[key])
            frozen_case = load_inputs(tag, source)
            processed = float(arr['total_gpu'].sum() / 4)
            eligible_mass = float(eligible.sum() / 4) if source == 'PLANNING' else None
            summary = dict(capacity_case=tag, source=source, installed_GPU=target,
                installed_GPU_increase=target - 780, same_original_UID_count=1649 if source == 'PLANNING' else 2498,
                same_original_exact_required_nominal_GPUh=source_exact_known if source == 'PLANNING' else actual_required,
                same_original_reserved_nominal_GPUh=source_reserved_known if source == 'PLANNING' else '',
                job_UID_submit_GPU_runtime_service_immutable=True, job_clone_count=0,
                processed_Dday_GPUh=processed, processed_Dday_GPUh_change_from_C0=float((arr['total_gpu'] - base['total_gpu']).sum() / 4),
                processed_Dday_GPUh_metric='EXACT_NOMINAL_KNOWN_PLUS_CC4_GPUh' if source == 'PLANNING' else 'PHYSICAL_OCCUPIED_GPUh_INCLUDES_RELEASE_ROUNDING',
                known_processed_Dday_GPUh=float(known.sum() / 4) if source == 'PLANNING' else float(actual_known.sum() / 4),
                unknown_processed_Dday_GPUh=float(anonymous.sum() / 4) if source == 'PLANNING' else float(actual_unknown.sum() / 4),
                eligible_source_mask_Dday_GPUh=eligible_mass if source == 'PLANNING' else '',
                certified_flexible_GPUh=0., certified_PCC_flexible_kw_increase=0.,
                PCC_energy_kWh=float(arr['PCC_P_kw'].sum() / 4),
                PCC_energy_change_from_C0_kWh=float((arr['PCC_P_kw'] - base['PCC_P_kw']).sum() / 4),
                maximum_system_PCC_kw=float(arr['PCC_P_kw'].sum(1).max()),
                maximum_PCC_difference_from_fixed_occupancy_case_kw=float(np.max(np.abs(arr['PCC_P_kw'] - frozen_case['PCC_P_kw']))),
                reference_start_changed_count=sum(r['reference_start'] != old_ref_by[str(r['job_uid'])]['reference_start'] for r in refs),
                reference_site_changed_count=sum(r['reference_site'] != old_ref_by[str(r['job_uid'])]['reference_site'] for r in refs),
                current_reference_outside_original_WINDOW_count=original_in_window,
                planning_reference_reads_Actual=0, planning_reference_reads_grid=0,
                nonzero_full96_AIDC_dispatch_certified=False,
                terminal_CC4_backlog_GPUh=float(backlog_out[-1] / 4) if source == 'PLANNING' else '',
                terminal_Actual_unadmitted_jobs=queue_audit['submitted_jobs'] - queue_audit['admitted_jobs'] if source == 'ACTUAL' else '',
                terminal_Actual_carryout_jobs=queue_audit['carryout_jobs'] if source == 'ACTUAL' else '',
                interpretation='CAPACITY_SPECIFIC_FCFS_AND_POWER_RECOMPUTED_ORIGINAL_SERVICE_NOT_CLONED')
            if source == 'PLANNING':
                summary.update(known_prefix_GPUh=sum(r['prefix_processed_GPUh'] for r in job_audit),
                    known_post96_tail_GPUh=sum(r['post96_tail_GPUh'] for r in job_audit),
                    known_exact_service_conservation_error_GPUh=sum(r['exact_service_conservation_error_GPUh'] for r in job_audit),
                    CC4_conservation_error_GPUh=conserved['conservation_error'],
                    CC4_original_post96_tail_GPUh=conserved['original_post96_tail_GPUh'])
            else:
                summary.update(executed_realized_Dday_GPUh=queue_audit['executed_Dday_GPUh'],
                    occupied_release_rounding_Dday_GPUh=queue_audit['release_rounding_reserved_Dday_GPUh'],
                    already_executed_before_issue_GPUh=queue_audit['already_executed_before_issue_GPUh'],
                    prefix_executed_GPUh=queue_audit['prefix_executed_GPUh'],
                    required_service_remaining_after96_GPUh=queue_audit['required_service_remaining_after96_GPUh'],
                    exact_realized_service_conservation_error_GPUh=queue_audit['exact_realized_service_conservation_error_GPUh'])
            summaries.append(summary)
            for t in range(96):
                for k, site in enumerate(sites):
                    slots.append(dict(capacity_case=tag, source=source, slot=t, aidc_id=site,
                        installed_GPU=int(cap[k]), active_GPU=float(arr['total_gpu'][t, k]),
                        known_GPU=float(known[t, k]) if source == 'PLANNING' else float(actual_known[t, k]),
                        anonymous_CC4_GPU=float(anonymous[t, k]) if source == 'PLANNING' else 0.,
                        actual_post_issue_GPU=float(actual_unknown[t, k]) if source == 'ACTUAL' else '',
                        source_mask_eligible_known_GPU=float(eligible[t, k]) if source == 'PLANNING' else '',
                        IT_idle_kw=float(arr['installed_idle_IT_kw'][t, k]),
                        IT_workload_kw=float(arr['workload_IT_kw'][t, k]),
                        cooling_and_other_facility_kw=float(arr['cooling_and_facility_kw'][t, k]),
                        PCC_P_kw=float(arr['PCC_P_kw'][t, k]), PCC_Q_kvar=float(arr['PCC_Q_kvar'][t, k]),
                        source_mask_P_upper_bound_kw=float(arr['source_mask_P_upper_bound_kw'][t, k]) if source == 'PLANNING' else '',
                        certified_reducible_P_kw=0., source_mask_is_feasible_dispatch=False))
        for row in facility_rows:
            if row['capacity_case'] != tag:
                continue
            k = sites.index(row['aidc_id'])
            row.update(frozen_active_GPU_occupancy_unchanged=tag == 'C0',
                source_original_UID_arrival_runtime_required_service_unchanged=True,
                capacity_specific_reference_queue_recomputed=True,
                Planning_processed_Dday_GPUh=float(arrays['total_gpu'][:, k].sum() / 4),
                Actual_physical_occupied_Dday_GPUh=float(actual_arrays['total_gpu'][:, k].sum() / 4),
                frozen_Planning_max_PCC_kw=float(arrays['PCC_P_kw'][:, k].max()),
                frozen_Actual_max_PCC_kw=float(actual_arrays['PCC_P_kw'][:, k].max()),
                frozen_max_PCC_kVA=float(max(np.hypot(arrays['PCC_P_kw'][:, k], arrays['PCC_Q_kvar'][:, k]).max(),
                    np.hypot(actual_arrays['PCC_P_kw'][:, k], actual_arrays['PCC_Q_kvar'][:, k]).max())),
                certified_flexible_GPUh_increase=0., certified_PCC_flex_power_kw_increase=0.)
        write(out / f'{tag}_REPLAY_RECEIPT.json', dict(capacity_case=tag, installed_GPU=target,
            Planning_reference=ref_audit, CC4_conservation=conserved, Actual_queue=queue_audit,
            source_original_jobs_preserved=True, initial_RUNNING_site_authority='ORIGINAL_RESEARCH_FALLBACK_NOT_MEASURED_GIS_PLACEMENT',
            QoS_WAN_restart_full96='NOT_CERTIFIED', added_native_solver_calls=0,
            planning_arrays=receipt(out / f'{tag}_PLANNING_INPUTS.npz'), actual_arrays=receipt(out / f'{tag}_ACTUAL_INPUTS.npz')))
        print(tag, 'recomputed Actual ready; GPUh=', actual_gpu.sum() / 4,
              'totalPmax=', actual_arrays['PCC_P_kw'].sum(1).max(), flush=True)
    for summary in summaries:
        if summary['source'] == 'PLANNING':
            c0 = next(r for r in summaries if r['capacity_case'] == 'C0' and r['source'] == 'PLANNING')
            summary['eligible_source_mask_GPUh_change_from_C0'] = summary['eligible_source_mask_Dday_GPUh'] - c0['eligible_source_mask_Dday_GPUh']
    table(REPORT / 'AIDC_FACILITY_SCENARIO_ENERGY.csv', summaries)
    table(REPORT / 'AIDC_FACILITY_CAPACITY_AUDIT.csv', facility_rows)
    table(REPORT / 'AIDC_FLEXIBILITY_QOS_AUDIT.csv', qos_rows)
    table(REPORT / 'AIDC_POWER_FLEXIBILITY_96SLOT.csv', slots)
    write(REPORT / 'AIDC_CAPACITY_RECOMPUTATION_RECEIPT.json', dict(
        candidates=summaries, source_files_before_sha256=source_before,
        source_files_after_sha256={str(p.relative_to(ROOT)): sha(p) for p in source_paths},
        source_files_unchanged=all(sha(p) == source_before[str(p.relative_to(ROOT))] for p in source_paths),
        fixed_occupancy_files_preserved=True, fixed_occupancy_namespace=str(DATA),
        authoritative_recomputed_namespace=str(out),
        source_runtime_refit=False, source_Job_clone_count=0, synthetic_workload_count=0,
        original_QoS_WIN_WAN_limits_changed=False, nonzero_AIDC96_dispatch='FAIL_NOT_CERTIFIED',
        Actual_outcomes_used_to_tune_QoS_or_reference=0, native_solver_calls=0))
    original_qos = read(old_report / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json')
    original_qos.update(C0_C1_C2_known_gpu_occupancy_identical=False,
        C0_C1_C2_CC4_gpu_occupancy_identical=False,
        C0_C1_C2_service_GPUh_change='REQUIRED_TOTAL_SERVICE_UNCHANGED_DDAY_PROCESSED_GPUh_CAPACITY_SPECIFIC',
        C0_C1_C2_terminal_backlog_change='SEE_CAPACITY_SPECIFIC_REFERENCE_QUEUE_RECEIPTS',
        authoritative_occupancy_mode='CAPACITY_SPECIFIC_ORIGINAL_FCFS_REFERENCE_AND_QUEUE_RECOMPUTED',
        legacy_single_case_numeric_fields_scope='C0_SOURCE_BASELINE_ONLY',
        zero_certified_volume_interpretation='NO_PROVEN_NONZERO_DISPATCH_NOT_ZERO_PHYSICAL_POTENTIAL',
        eligible_Dday_GPUh_by_capacity={r['capacity_case']: r['eligible_source_mask_Dday_GPUh']
                                      for r in summaries if r['source'] == 'PLANNING'},
        certified_PCC_flexible_power_increase_by_capacity={tag: 0. for tag in CAPACITY_CANDIDATES},
        capacity_case_source_mask_projection='UNCHANGED_SOURCE_RIGHTS_NEW_REFERENCE_ATTRIBUTION_RELAXATION',
        original_fixed_occupancy_receipt_preserved=str(old_report / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json'))
    write(REPORT / 'AIDC_FLEXIBILITY_QOS_RECEIPT.json', original_qos)
    old_source_receipt = read(old_report / 'AIDC_FACILITY_SOURCE_RECEIPT.json')
    old_source_receipt.update(authoritative_occupancy_mode='CAPACITY_SPECIFIC_FCFS_QUEUE_AND_C1_RECOMPUTATION',
        changed_power='INSTALLED_IDLE_PLUS_CAPACITY_SPECIFIC_QUEUE_OCCUPANCY_AND_FROZEN_C1_RESPONSE',
        arrays={f'{tag}_{source}': receipt(out / f'{tag}_{source}_INPUTS.npz')
                for tag in CAPACITY_CANDIDATES for source in ('PLANNING', 'ACTUAL')},
        original_fixed_occupancy_arrays_preserved=True, original_service_required_total_unchanged=True,
        unchanged_job_service_backlog='REQUIRED_JOB_SERVICE_UNCHANGED_QUEUE_BACKLOG_CAPACITY_SPECIFIC',
        all_capacity_processed_occupancy_equal=False, QoS_receipt=original_qos)
    write(REPORT / 'AIDC_FACILITY_SOURCE_RECEIPT.json', old_source_receipt)
    (REPORT / 'AIDC_CAPACITY_RECOMPUTATION_METHOD_KO.md').write_text(
        '# 설치용량별 원본 Job Reference·Queue 재계산\n\n'
        '사용자 추가 지시에 따라 기존 fixed-occupancy 진단은 byte 그대로 보존하고, C0/C1/C2 각각 원본 '
        '1649 known UID와 동일 CC4 service의 FCFS Reference·queue·96-slot occupancy·C1/PCC를 다시 계산했다. '
        'Actual은 동일한 2498 UID의 submit/GPU/runtime를 private event 환경에 그대로 넣고 causal FCFS를 재실행했다. '
        '각 capacity의 필요한 service와 원본 runtime는 동일하며 더 많은 GPU가 신규 Job을 만들지 않는다.\n\n'
        'Reference는 issue부터 시작하며 운영일은 issue+6시간이다. 증가한 capacity는 같은 일을 prefix에서 더 일찍 '
        '실행하여 Dday GPU-h를 줄이거나 post-H tail을 당길 수 있다. 따라서 처리 GPU-h는 prefix·96-slot·tail로 '
        '나누어 audit하며 전체 required service 보존과 구별한다. C1/C2의 Actual 추가 admission/queue/carryout 역시 '
        '설비 효과이며 유연 dispatch 또는 알고리즘 성능 개선이 아니다.\n\n'
        '공통 FCFS 초기 RUNNING fallback site는 원본 실측 AIDC 위치가 없는 연구용 placement다. 확장 시 이를 '
        '재계산한 것은 가정된 초기 배치를 바꾼 별도 시나리오이며 실제 운영 중 checkpoint migration으로 표현하지 않는다. '
        '원본 Native WINDOW와 새 Reference의 start/site 불일치, 실측 QoS deadline 부재, WAN/restart/full-option '
        'adapter 미검증은 남는다. eligible source-mask GPU-h 변화는 인증된 flexible GPU-h 변화가 아니며 '
        'certified PCC flexible power 증가와 실행 가능한 비영 96-slot AIDC 효과는 여전히 NOT_CERTIFIED다.\n',
        encoding='utf-8')
    (REPORT / 'AIDC_FACILITY_QOS_METHOD_KO.md').write_text(
        (REPORT / 'AIDC_CAPACITY_RECOMPUTATION_METHOD_KO.md').read_text(encoding='utf-8')
        + '\n실제 compute service는 completion 순간까지이며 원본 전기 power adapter는 control release '
          '시간까지 GPU 자원을 유지한다. Actual CSV의 physical_occupied GPU-h는 이 최대 15분 '
          'release rounding을 포함한다. executed_realized_Dday_GPUh와 reserved rounding을 분리했고 '
          '이미 실행된 service +prefix +Dday +terminal remaining으로 원본 실제 GPU-h를 보존했다. '
          '예약 GPU-h 증가를 추가 compute 서비스로 과장하지 않는다.\n\n'
        + f'[2024 Kestrel 4-GPU node 사양]({HARDWARE_2024_URL})을 기준으로 C1 AIDC05=150 GPU는 '
          '동종4-GPU 서버37.5개이므로 exact homogeneous packing FAIL이다. '
          'C0/C2의 정수 가능성은 BOM·PSU·rack·냉각·전기접속 정격 증명이 아니다. 이들 정격은 '
          'UNVERIFIED이며 현장 시설 적격성을 승격하지 않았다. '
        + f'[Kestrel QoS 문서]({QOS_URL})의 normal/high는 queue priority이며 '
          '실제 사용자 deadline/체크포인트 지원 계약을 증명하지 않는다.\n', encoding='utf-8')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixed-occupancy', action='store_true', help='Reproduce preserved first diagnostic only')
    args = parser.parse_args()
    result = build_all() if args.fixed_occupancy else recompute_all()
    for tag, sources in result.items():
        print(tag, int(sources['PLANNING']['capacities'].sum()),
              'GPU; Planning max P=', sources['PLANNING']['PCC_P_kw'].sum(1).max(),
              'Actual max P=', sources['ACTUAL']['PCC_P_kw'].sum(1).max(), flush=True)


if __name__ == '__main__':
    main()
