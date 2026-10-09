"""Grid-blind screening with unchanged V42 reference/queue/C1 functions.

Expansion is an explicitly unqualified engineering assumption. Kestrel jobs and
forecast GPUh are never multiplied, and logical gang pools are not real racks.
"""
from __future__ import annotations

from dataclasses import asdict
import importlib.util
import sys
import numpy as np
import pandas as pd

from .common import DATA, ROOT, REPORT, read, sha, write, table

CAPACITY_SCALES = (1.0, 1.25, 1.5)
FIXED_AIDC = dict(zip((f'AIDC{i:02d}' for i in range(1, 13)), (
    'l3234149', 'e182733', 'm1027055', 'm1069411', 'l2688693', 'm1142814',
    'm1026690', 'l3123452', 'l2728247', 'l2973833', 'm1047763', 'e192258')))


def load_c1_module():
    # This is an exact source snapshot with its sole external scalar imported
    # from a pinned original thermal module; no import of an old solver/runner.
    path = DATA / 'v42_inputs/c1_affine.py'
    source = read(DATA / 'v42_inputs/INPUT_SOURCE_MANIFEST.json')
    if sha(path) != source['c1_copy_sha256']:
        raise ValueError('C1_SOURCE_IDENTITY_DRIFT')
    original = DATA / 'v42_inputs/source/dayahead/v28/thermal.py'
    if sha(original) != source['thermal_copy_sha256']:
        raise ValueError('C1_NORMALIZATION_SOURCE_IDENTITY_DRIFT')
    sys.path.insert(0, str(original.parents[2]))
    spec = importlib.util.spec_from_file_location('ieee8500_v42_frozen_c1', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_candidate(scale):
    if scale not in CAPACITY_SCALES:
        raise ValueError('UNREGISTERED_CAPACITY_SCALE')
    from v42_capacity.reference import build_reference
    from v42_capacity.queue import allocate, conservation
    from v42_modelable.power import known_occupancy
    bundle = read(DATA / 'v42_inputs/PLANNING_INPUT_BUNDLE.json')
    power = read(DATA / 'v42_inputs/POWER_AUTHORITY.json')
    sites = sorted(bundle['capacities'])
    capacities = {s: int(bundle['capacities'][s] * scale) for s in sites}
    if any(capacities[s] != bundle['capacities'][s] * scale for s in sites):
        raise ValueError('NONINTEGER_GPU_EXPANSION')
    # Existing whole-gang compatibility is preserved; extra installed capacity
    # does not license larger gangs or fabricate additional physical rack limits.
    rows, audit = build_reference(bundle['known_population'], capacities,
                                 bundle['rack_compatibility'], issue_time=bundle['issue_time'])
    if not audit['full_reference_ready']:
        raise ValueError('KNOWN_REFERENCE_BLOCKED')
    known = known_occupancy(rows, sites)
    cc4 = bundle['forecast_inputs']['current_CC4']
    if cc4['future_job_ids'] or bundle['future_actual_arrival_IDs_present']:
        raise ValueError('FUTURE_JOB_LEAKAGE')
    cap = np.array([capacities[s] for s in sites])
    anon, incoming, outgoing = allocate(known, cc4['nominal_unknown_GPU_96'], cap)
    conserved = conservation(sum(cc4['Q50_GPUh']), anon, outgoing[-1], cc4['full_tail_nominal_GPUh'])
    total = known + anon
    original = pd.read_csv(DATA / 'v42_inputs/C1_PLANNING_COEFFICIENTS.csv')
    module = load_c1_module()
    params = module.load_c1(DATA / 'v42_inputs/C1_MODEL.json')
    idle = power['current_IT_idle_kW_per_installed_GPU']
    swing = power['current_IT_swing_kW_per_active_GPU']
    it = idle * cap + swing * total
    p = np.zeros_like(it)
    coeffs = []
    for t in range(96):
        weather = original[original.slot.eq(t)].iloc[0]
        for k, site in enumerate(sites):
            c = module.endpoint_secant(site, t, idle * cap[k], (idle + swing) * cap[k],
                                       float(weather.wetbulb_c), float(weather.rh_pct), params)
            coeffs.append(asdict(c))
            p[t, k] = c.slope * it[t, k] + c.intercept_kw
    q = p * np.tan(np.arccos(power['PF_AIDC']))
    baseline = np.load(DATA / 'v42_inputs/PLANNING_PHYSICAL.npz', allow_pickle=False)
    baseline_match = None
    if scale == 1.0:
        errors = {name: float(np.max(np.abs(value - baseline[name])))
                  for name, value in [('known_gpu', known), ('cc4_served_gpu', anon),
                                      ('total_gpu', total), ('IT_kw', it),
                                      ('PCC_P_kw', p), ('PCC_Q_kvar', q)]}
        baseline_match = dict(maximum_absolute_errors=errors, PASS=max(errors.values()) < 1e-10)
        if not baseline_match['PASS']:
            raise ValueError('CURRENT_V42_B0_REPRODUCTION_FAILED')
    candidate = dict(scale=scale, sites=sites, capacities=capacities, P_kw=p, Q_kvar=q,
                     total_gpu=total, known_gpu=known, anonymous_gpu=anon,
                     reference_audit=audit, conservation=conserved,
                     baseline_reproduction=baseline_match)
    tag = str(scale).replace('.', 'p')
    dest = REPORT / 'diagnostics' / ('capacity_' + tag)
    dest.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest / 'V42_WORKLOAD_POWER.npz', sites=np.array(sites), capacities=cap,
                        known_gpu=known, cc4_served_gpu=anon, total_gpu=total, IT_kw=it,
                        PCC_P_kw=p, PCC_Q_kvar=q, backlog_in=incoming, backlog_out=outgoing)
    write(dest / 'WORKLOAD_RECEIPT.json', dict(
        scope='PRESELECTION_DIAGNOSTIC_NOT_PRODUCTION', scale=scale,
        installed_GPU=int(cap.sum()), original_jobs_preserved=True,
        original_job_population_SHA256=audit['population_sha256'], workload_multiplier=1.0,
        rack_compatibility_unchanged=True, expansion_equipment_evidence='MISSING' if scale != 1 else 'LOGICAL_AUTHORITY_ONLY',
        physical_rack_server_cooling_ratings_verified=False, dedicated_AIDC_transformer_verified=False,
        reference_audit=audit, conservation=conserved, baseline_reproduction=baseline_match,
        maximum_total_GPU=float(total.sum(1).max()),
        minimum_total_P_kW=float(p.sum(1).min()), maximum_total_P_kW=float(p.sum(1).max()),
        capacity_violation_cells=int(np.sum(total > cap + 1e-9)), Native_optimize_calls=0))
    return candidate


def capacity_audit(candidates):
    rows = []
    for c in candidates:
        for k, site in enumerate(c['sites']):
            rows.append(dict(
                scale=c['scale'], aidc_id=site, fixed_bus=FIXED_AIDC[site],
                installed_GPU=c['capacities'][site], maximum_active_GPU=float(c['total_gpu'][:, k].max()),
                maximum_P_kW=float(c['P_kw'][:, k].max()), maximum_Q_kvar=float(c['Q_kvar'][:, k].max()),
                maximum_PCC_kVA=float(np.hypot(c['P_kw'][:, k], c['Q_kvar'][:, k]).max()), PF=0.95,
                whole_gang_compatibility='ORIGINAL_NON_ADDITIVE_LOGICAL_POOLS',
                physical_rack_server_max_kW='', physical_cooling_capacity_kW='',
                historical_overlay_transformer_kVA=1500, original_feeder_AIDC_transformer='ABSENT',
                new_transformer_created=False, expansion_equipment_evidence='NOT_VERIFIED',
                flexibility='ORIGINAL_JOB_MASKS_UNCHANGED_NO_OPTIMIZATION',
                QoS_deadline_WAN='ORIGINAL_INPUT_RETAINED_FULL_MODEL_NOT_RUN',
                status='UNQUALIFIED_MV_HOST_EQUIVALENT_DIAGNOSTIC'))
    table(REPORT / 'AIDC_CAPACITY_AUDIT.csv', rows)

