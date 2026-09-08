"""Local GPUh reserve interface; P1 electrical objective remains unchanged."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

H4_SLOTS = 16
DT_HOURS = 0.25
OBJECTIVE_HIERARCHY = ('MIN_RHO_MAX', 'MIN_MEAN_H4_SHORTFALL', 'MIN_MIGRATIONS',
                       'MIN_COMPLETE_REFERENCE_DEVIATION', 'STABLE_TIE')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def order_statistic(values, numerator=99, denominator=100):
    x = np.asarray(values, dtype=float)
    require(x.ndim == 1 and len(x) > 0 and np.isfinite(x).all(), 'HISTORICAL_CAP_REQUIRES_FINITE_SUPPORT')
    require(0 < numerator <= denominator, 'INVALID_ORDER_STATISTIC_QUANTILE')
    k = min(max((numerator * (len(x) + 1) + denominator - 1) // denominator, 1), len(x))
    return float(np.partition(x, k - 1)[k - 1]), k


def windows(values):
    values = np.asarray(values, dtype=float)
    require(values.ndim == 1 and len(values) == 96 and np.isfinite(values).all(), 'EXPECTED_96_FINITE_GPU_SLOTS')
    return DT_HOURS * np.lib.stride_tricks.sliding_window_view(values, H4_SLOTS).sum(axis=1)


def cap_reserve(raw, historical_pool, capacity_gpu):
    raw = np.asarray(raw, dtype=float)
    capacity_gpu = np.asarray(capacity_gpu, dtype=float)
    require(raw.shape == (81,) and np.isfinite(raw).all() and (raw >= 0).all(), 'INVALID_H4_RAW')
    require(capacity_gpu.ndim == 2 and capacity_gpu.shape[0] == 96 and capacity_gpu.shape[1] > 0
            and np.isfinite(capacity_gpu).all() and (capacity_gpu >= 0).all(), 'INVALID_FUTURE_SERVICE_CAPACITY')
    historical, rank = order_statistic(historical_pool)
    require(historical >= 0, 'NEGATIVE_HISTORICAL_WORK')
    physical = windows(capacity_gpu.sum(axis=1))
    actionable = np.minimum(raw, np.minimum(historical, physical))
    return {'H4_RAW_R85_B2_GPUh': raw.tolist(), 'H4_CAP_HIST': historical,
            'H4_CAP_HIST_order_rank': rank, 'H4_CAP_PHYS': physical.tolist(),
            'H4_ACTIONABLE_RESERVE_GPUh': actionable.tolist()}


def validate_snapshot(snapshot, capacity):
    from .scalars import project
    project(snapshot)
    require(snapshot['runtime_model_id'] == 'ROLLING_Q90_TRACK_P_L2' and
            snapshot['H4_model_id'] == 'H4_R85_B2' and snapshot['H24_OFF'] is True, 'V41_MODEL_INTERFACE_DRIFT')
    require(snapshot['objective_hierarchy'] == list(OBJECTIVE_HIERARCHY), 'V41_OBJECTIVE_HIERARCHY_DRIFT')
    sites = tuple(snapshot['future_service_eligible_sites'])
    require(sites and len(sites) == len(set(sites)) and set(sites) <= set(capacity.aidc_ids), 'INVALID_FUTURE_SERVICE_SITES')
    require(snapshot.get('future_service_eligibility_authority'), 'FUTURE_SERVICE_ELIGIBILITY_AUTHORITY_REQUIRED')
    cap = np.asarray(snapshot['future_service_capacity_gpu'], dtype=float)
    require(cap.shape == (96, len(sites)) and np.isfinite(cap).all(), 'FUTURE_CAPACITY_AXIS')
    require(all(np.all((cap[:, i] >= 0) & (cap[:, i] <= capacity.site_capacity[s])) for i, s in enumerate(sites)), 'FUTURE_CAPACITY_EXCEEDS_AUTHORITY')
    raw = np.asarray(snapshot['H4_RAW_R85_B2_GPUh'], dtype=float)
    physical = np.asarray(snapshot['H4_CAP_PHYS'], dtype=float)
    actionable = np.asarray(snapshot['H4_ACTIONABLE_RESERVE_GPUh'], dtype=float)
    historical = float(snapshot['H4_CAP_HIST'])
    require(raw.shape == physical.shape == actionable.shape == (81,), 'H4_WINDOW_AXIS')
    require(np.isfinite(raw).all() and (raw >= 0).all() and math.isfinite(historical) and historical >= 0, 'H4_NONFINITE_OR_NEGATIVE')
    require(np.array_equal(physical, windows(cap.sum(axis=1))), 'H4_PHYSICAL_CAP_DRIFT')
    require(np.array_equal(actionable, np.minimum(raw, np.minimum(historical, physical))), 'H4_ACTIONABLE_CAP_DRIFT')
    return sites, cap, actionable


def bind(context, path, expected_sha):
    data = Path(path).read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected_sha, 'ML_SNAPSHOT_HASH_MISMATCH')
    snapshot = json.loads(data)
    validate_snapshot(snapshot, context.capacity)
    context.v41_ml_snapshot = snapshot
    context.v41_ml_snapshot_sha256 = expected_sha
    context.v41_ml_snapshot_path = str(Path(path).resolve())
    from .scalars import project
    context.v41_optimizer_scalars = project(snapshot)
    return snapshot


def add_constraints(model, context, known_load):
    """known_load is the existing candidate-schedule GPU occupancy expression."""
    import gurobipy as gp
    snapshot = context.v41_ml_snapshot
    sites, cap, reserve = validate_snapshot(snapshot, context.capacity)
    # Re-read the sealed bytes at each A0/A1 entry, without re-running ML.
    from .scalars import validate_bound
    scalar_inputs = validate_bound(context)
    xi = []
    for k in range(81):
        v = model.addVar(lb=0., name=f'V41_H4_shortfall_GPUh[{k}]')
        headroom = DT_HOURS * gp.quicksum(float(cap[t, i]) - known_load[t, s]
                    for t in range(k, k + H4_SLOTS) for i, s in enumerate(sites))
        model.addConstr(headroom + v >= scalar_inputs.actionable_h4_gpuh[k], name=f'V41_H4_reserve[{k}]')
        xi.append(v)
    return gp.quicksum(xi) / len(xi), xi


def diagnostics(snapshot, capacity, known_gpu):
    sites, cap, reserve = validate_snapshot(snapshot, capacity)
    known_gpu = np.asarray(known_gpu, dtype=float)
    require(known_gpu.shape == (96, len(capacity.aidc_ids)) and np.isfinite(known_gpu).all(), 'KNOWN_GPU_AXIS')
    require((known_gpu >= 0).all(), 'NEGATIVE_KNOWN_OCCUPANCY')
    columns = [tuple(capacity.aidc_ids).index(s) for s in sites]
    available = windows((cap - known_gpu[:, columns]).sum(axis=1))
    require((available >= -1e-8).all(), 'KNOWN_OCCUPANCY_EXCEEDS_FUTURE_HEADROOM')
    xi = np.maximum(reserve - available, 0.)
    return {'H_available_GPUh': available.tolist(), 'xi_GPUh': xi.tolist(), 'sum_xi_GPUh': float(xi.sum()),
            'mean_xi_GPUh': float(xi.mean()), 'P90_xi_GPUh': float(np.quantile(xi, .9)), 'max_xi_GPUh': float(xi.max()),
            'scalar_penalty_coefficient': None, 'objective_rank': 2}


def lexicographic_compare(left, right, tolerances):
    require(len(left) == len(right) == len(tolerances) == 5, 'OBJECTIVE_VECTOR_AXIS')
    require(all(math.isfinite(float(v)) for v in (*left, *right, *tolerances)) and min(tolerances) >= 0,
            'NONFINITE_OBJECTIVE_VECTOR')
    for a, b, tol in zip(left, right, tolerances):
        if a < b - tol:
            return -1
        if a > b + tol:
            return 1
    return 0
