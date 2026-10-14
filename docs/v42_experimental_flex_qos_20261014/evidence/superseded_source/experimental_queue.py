"""Conserved anonymous Q90 queue risk for the experimental research policy.

This is an aggregate fluid approximation.  It creates no future Job UID and
does not certify whole-gang/rack/WAN scheduling or Actual AC feasibility.
The original TRAIN execution-lag mass becomes a declared service-eligibility
release proxy; unserved or not-yet-released work remains explicit carryout.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

import numpy as np


POLICY_ID = 'V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1'
QUEUE_MODEL_ID = 'FROZEN_TRAIN_LAG_CAPACITY_BOUND_FLUID_QUEUE_V1'
SLOTS = 96
DT_HOURS = .25


def _array(value, shape=None, *, name):
    result = np.array(value, dtype=float, copy=True)
    if (shape is not None and result.shape != shape) or not np.isfinite(result).all():
        raise ValueError('EXPERIMENTAL_QUEUE_FINITE_AXIS_REQUIRED:' + name)
    return result


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode('utf8')).hexdigest()


def _source(authority, hourly, kernel):
    authority = deepcopy(dict(authority or {}))
    for field in ('prediction_sha', 'kernel_sha'):
        value = authority.get(field, '')
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('FROZEN_Q90_AND_TRAIN_KERNEL_SOURCE_SHA_REQUIRED:' + field)
    if not authority.get('model_id'):
        raise ValueError('FROZEN_CC4_MODEL_ID_REQUIRED')
    if authority.get('future_job_ids') or authority.get('future_Actual_or_UID_inputs_used', False):
        raise ValueError('ANONYMOUS_QUEUE_CANNOT_USE_FUTURE_JOB_IDENTITIES_OR_ACTUAL')
    for field in ('forecast_modifications', 'fit_calls', 'new_calibrator_calls',
                  'scaling_calls', 'clipping_calls', 'May_result_model_reselection'):
        if authority.get(field, 0) != 0:
            raise ValueError('FROZEN_Q90_OR_KERNEL_MODIFICATION_FORBIDDEN:' + field)
    # An authority with literal arrays provides an additional binding check;
    # source receipt verification itself remains the calling loader's duty.
    for field, values in (('q90_hourly_GPUh', hourly), ('kernel', kernel)):
        if field in authority and not np.array_equal(np.asarray(authority[field], float), values):
            raise ValueError('FROZEN_Q90_OR_TRAIN_KERNEL_VECTOR_DRIFT:' + field)
    return authority


def fluid_queue(hourly_gpu_h, kernel, capacities, *, known_gpu, reserved_gpu=None,
                remaining_slot=0, initial_backlog_gpu_h=0., allocation_priority=None,
                source_authority=None, causal_queue_start_slot=None):
    """Serve literal Q90 work within frozen Known/explicit reservation headroom.

    ``known_gpu`` and ``reserved_gpu`` are96-by-site physical profiles.  The
    latter must exclude anonymous Q50 forecast work: this queue uses the FULL
    Q90 lifetime work, replacing that anonymous forecast in its risk scenario.
    Past service is retained for conservation and audited; past capacity
    overflows cannot veto an action whose effective interval starts later.
    Current/future Known or explicit reservation overflows fail closed.
    In a current-state risk call, set ``causal_queue_start_slot`` to the event
    slot.  Observed backlog enters there and is never served retroactively.
    Earlier eligible remaining-forecast mass stays queued; no past service
    is invented.  The default retains the offline full-day reconstruction.
    """
    if type(remaining_slot) is not int or not 0 <= remaining_slot < SLOTS:
        raise ValueError('EXPERIMENTAL_QUEUE_REMAINING_SLOT_REQUIRED')
    start_slot = 0 if causal_queue_start_slot is None else causal_queue_start_slot
    if (type(start_slot) is not int or not 0 <= start_slot < SLOTS or
            (causal_queue_start_slot is not None and start_slot < remaining_slot)):
        raise ValueError('CAUSAL_QUEUE_START_CANNOT_PRECEDE_OBSERVED_EVENT')
    hourly = _array(hourly_gpu_h, (24,), name='hourly_Q90_GPUh')
    kappa = _array(kernel, name='TRAIN_kernel')
    if (kappa.ndim != 1 or not len(kappa) or np.any(hourly < 0) or np.any(kappa < 0)
            or not np.isclose(kappa.sum(), 1., rtol=0, atol=1e-10)):
        raise ValueError('LITERAL_NONNEGATIVE_Q90_NORMALIZED_TRAIN_KERNEL_REQUIRED')
    authority = _source(source_authority, hourly, kappa)
    sites = tuple(sorted(capacities))
    cap = _array([capacities[s] for s in sites], (len(sites),), name='site_GPU_capacity')
    if not sites or np.any(cap <= 0):
        raise ValueError('ORIGINAL_POSITIVE_SITE_GPU_CAPACITY_REQUIRED')
    order = sites if allocation_priority is None else tuple(allocation_priority)
    if len(order) != len(sites) or set(order) != set(sites):
        raise ValueError('PREREGISTERED_SITE_PRIORITY_PERMUTATION_REQUIRED')
    priority = [sites.index(s) for s in order]
    shape = (SLOTS, len(sites))
    known = _array(known_gpu, shape, name='frozen_known_GPU')
    reserved = np.zeros(shape) if reserved_gpu is None else _array(reserved_gpu, shape, name='explicit_reserved_GPU')
    if np.any(known < 0) or np.any(reserved < 0):
        raise ValueError('NONNEGATIVE_FROZEN_KNOWN_AND_EXPLICIT_RESERVATIONS_REQUIRED')
    initial = float(initial_backlog_gpu_h)
    if not math.isfinite(initial) or initial < 0:
        raise ValueError('FINITE_NONNEGATIVE_INITIAL_AGGREGATE_BACKLOG_REQUIRED')
    fixed = known + reserved
    overflow = fixed > cap + 1e-8
    if np.any(overflow[remaining_slot:]):
        raise ValueError('CURRENT_FUTURE_KNOWN_OR_RESERVED_GPU_CAPACITY_VIOLATION')
    hourly_arrivals = np.zeros(SLOTS)
    hourly_arrivals[::4] = hourly
    impulses = np.zeros(93)
    impulses[::4] = hourly
    # No normalization, truncation, clipping or scaling of forecast/kernel.
    released_full = np.convolve(impulses, kappa)
    released_day = np.zeros(SLOTS)
    released_day[:min(SLOTS, len(released_full))] = released_full[:SLOTS]
    release_tail = float(released_full[SLOTS:].sum())
    served = np.zeros(shape)
    backlog = np.zeros(SLOTS)
    waiting_for_release = np.zeros(SLOTS)
    available = 0.
    for t in range(SLOTS):
        available += float(released_day[t])
        if t == start_slot:
            available += initial
        for j in (priority if t >= start_slot else ()):
            headroom_gpu = max(0., float(cap[j] - fixed[t, j]))
            grant_gpu_h = min(available, headroom_gpu * DT_HOURS)
            served[t, j] = grant_gpu_h / DT_HOURS
            available -= grant_gpu_h
        backlog[t] = max(0., available)
        waiting_for_release[t] = max(0., float(hourly_arrivals[:t+1].sum() - released_day[:t+1].sum()))
    served_gpu_h = float(served.sum() * DT_HOURS)
    arrived_gpu_h = float(hourly.sum() + initial)
    carryout_gpu_h = float(backlog[-1] + release_tail)
    residual = arrived_gpu_h - served_gpu_h - carryout_gpu_h
    if not np.isclose(residual, 0., rtol=0, atol=max(1e-8, arrived_gpu_h * 1e-10)):
        raise ValueError('Q90_ARRIVED_SERVED_REMAINING_CONSERVATION_FAILED')
    physical = fixed + served
    if np.any(physical[remaining_slot:] > cap + 1e-8):
        raise ValueError('FLUID_ADMISSION_PHYSICAL_GPU_CAPACITY_VIOLATION')
    identity = dict(policy=POLICY_ID, queue_model=QUEUE_MODEL_ID, source_authority=authority,
        hourly_gpu_h=hourly.tolist(), kernel=kappa.tolist(), sites=list(sites), capacity=cap.tolist(),
        known_gpu=known.tolist(), reserved_gpu=reserved.tolist(), initial_backlog_gpu_h=initial,
        allocation_priority=list(order), remaining_slot=remaining_slot,
        causal_queue_start_slot=causal_queue_start_slot)
    return dict(schema='EXPERIMENTAL_Q90_QUEUE_SCENARIO_V1', policy_id=POLICY_ID,
        queue_model_id=QUEUE_MODEL_ID, source_sha=_sha(identity), source_authority=authority,
        site_axis=list(sites), remaining_slot=remaining_slot, all96=True, dt_h=DT_HOURS,
        causal_queue_start_slot=causal_queue_start_slot,initial_backlog_release_slot=start_slot,
        service_scope=('OFFLINE_FULL_DAY_RECONSTRUCTION' if causal_queue_start_slot is None
            else 'CURRENT_EVENT_FORWARD_RISK_NO_INVENTED_PAST_SERVICE'),
        served_before_causal_start_GPUh=float(served[:start_slot].sum()*DT_HOURS),
        current_observed_backlog_never_served_before_release=True,
        arrived_GPUh=arrived_gpu_h, forecast_lifetime_GPUh=float(hourly.sum()),
        initial_backlog_GPUh=initial, total_served_GPUh=served_gpu_h,
        remaining_work_GPUh=carryout_gpu_h, carryout_GPUh=carryout_gpu_h,
        queue_at_day_end_GPUh=float(backlog[-1]), outside96_release_tail_GPUh=release_tail,
        conservation_residual_GPUh=residual, conservation_PASS=True,
        hourly_arrived_work_GPUh=hourly_arrivals.tolist(),
        released_service_work_GPUh=released_day.tolist(),
        released_service_tail_GPUh=released_full[SLOTS:].tolist(),
        served_site_GPU=served.tolist(), fixed_physical_GPU=fixed.tolist(),
        total_physical_site_GPU=physical.tolist(), backlog_GPUh=backlog.tolist(),
        not_yet_service_eligible_GPUh=waiting_for_release.tolist(),
        queue_GPUh_hours=float(backlog[remaining_slot:].sum() * DT_HOURS),
        queue_area_convention='SLOT_END_BACKLOG_RECTANGLES_AGGREGATE_APPROXIMATION',
        past_fixed_capacity_violation_cells=int(overflow[:remaining_slot].sum()),
        current_future_capacity_violation_cells=int(np.sum(physical[remaining_slot:] > cap + 1e-8)),
        capacities_unchanged=True, future_individual_UIDs=0,
        forecast_clipping_or_scaling=False, model_fit_or_calibrator_calls=0,
        allocation_rule='PREREGISTERED_GRID_BLIND_SITE_PRIORITY_FLUID_SERVICE',
        allocation_priority=list(order),
        release_proxy='ORIGINAL_TRAIN_EXECUTION_LAG_SERVICE_MASS_AS_SERVICE_ELIGIBILITY_RELEASE',
        approximation='ANONYMOUS_AGGREGATE_FLUID;NOT_WHOLE_GANG_RACK_WAN_SCHEDULING_CERTIFICATE',
        scenario_is_Actual_occupancy=False, Actual_AC_certificate=False,
        demand_backlog_is_GPU_occupancy=False)


def evaluate_q90_risk(packet, queue, *, frozen_anonymous_gpu, remaining_slot=None):
    """Evaluate admitted physical service with untouched signed original rows.

    Voltage/current/transformer failures remain explicit risk diagnostics.
    They are not erased or called feasible.  An anonymous forecast risk is
    not itself a blanket veto for currently authorized physical/Q50-feasible
    actions; Actual and Q50 physical guards remain the caller's responsibility.
    """
    slot = queue['remaining_slot'] if remaining_slot is None else remaining_slot
    if type(slot) is not int or not 0 <= slot < SLOTS:
        raise ValueError('EXPERIMENTAL_QUEUE_REMAINING_SLOT_REQUIRED')
    if tuple(queue['site_axis']) != tuple(packet.sites) or packet.known_gpu is None:
        raise ValueError('FROZEN_GRID_QUEUE_SITE_KNOWN_AXIS_REQUIRED')
    shape = (SLOTS, len(packet.sites))
    anonymous = _array(frozen_anonymous_gpu, shape, name='frozen_anonymous_GPU')
    if np.any(anonymous < 0):
        raise ValueError('NONNEGATIVE_FROZEN_ANONYMOUS_PROFILE_REQUIRED')
    total = _array(queue['total_physical_site_GPU'], shape, name='Q90_admitted_physical_GPU')
    delta = total - np.asarray(packet.known_gpu) - anonymous
    score = packet.evaluate(delta, remaining_slot=slot, scenario_gpu=np.zeros(shape))
    return dict(schema='EXPERIMENTAL_Q90_ADMITTED_GRID_RISK_V1', source_sha=queue['source_sha'],
        remaining_slot=slot, served_site_GPU=deepcopy(queue['served_site_GPU']),
        arrived_GPUh=queue['arrived_GPUh'], total_served_GPUh=queue['total_served_GPUh'],
        backlog_GPUh=deepcopy(queue['backlog_GPUh']), carryout_GPUh=queue['carryout_GPUh'],
        queue_GPUh_hours=queue['queue_GPUh_hours'], peak_score=score['peak_score'],
        hard_feasible=score['hard_feasible'], violation_count=len(score['violations']),
        original_grid_result=score, original_signed_grid_rows_unchanged=True,
        Q90_demand_added_to_physical_occupancy=False,
        admitted_service_only_in_grid_delta=True, nominal_Q50_replaced_not_added_twice=True,
        backlog_hard_veto=False, hypothetical_grid_violation_not_erased=True,
        actual_candidate_physical_Q50_guards_required=True,
        whole_gang_certificate=False, Actual_Fresh_AC_certificate=False)


def rank_action_scores(rows, *, q50_tie_tolerance=1e-9):
    """Rank already guarded actions by Q50 P1, Q90 risk, then less disruption.

    Tie groups are anchored to their minimum Q50 score, so transitive near
    ties cannot promote a materially worse primary score.  This is a bounded
    selector rule, never the original A-stage P2 objective or a global bound.
    """
    tolerance = float(q50_tie_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('FINITE_NONNEGATIVE_Q50_TIE_TOLERANCE_REQUIRED')
    accepted, rejected = [], []
    for raw in rows:
        row = deepcopy(raw)
        if row.get('physical_feasible') is not True or row.get('q50_hard_feasible') is not True:
            rejected.append(dict(row, rank_reject_reason='ACTUAL_RESOURCE_OR_Q50_ORIGINAL_HARD_CONSTRAINT'))
            continue
        risk = row.get('q90_risk', {})
        required = ('carryout_GPUh', 'queue_GPUh_hours', 'peak_score', 'violation_count')
        numbers = [row.get('q50_peak_score')] + [risk.get(k) for k in required]
        numbers += [row.get('intentional_burden_seconds', 0), row.get('migration_count', 0)]
        if any(v is None or not math.isfinite(float(v)) or float(v) < 0 for v in numbers):
            raise ValueError('FINITE_COMPLETE_ACTION_Q50_Q90_RISK_REQUIRED')
        accepted.append(row)
    accepted.sort(key=lambda r: float(r['q50_peak_score']))
    ordered = []
    while accepted:
        minimum = float(accepted[0]['q50_peak_score'])
        cut = next((i for i, r in enumerate(accepted)
                    if float(r['q50_peak_score']) - minimum > tolerance), len(accepted))
        group, accepted = accepted[:cut], accepted[cut:]
        group.sort(key=lambda r: (r['q90_risk']['violation_count'], r['q90_risk']['carryout_GPUh'],
            r['q90_risk']['queue_GPUh_hours'], r['q90_risk']['peak_score'],
            r.get('migration_count', 0), r.get('intentional_burden_seconds', 0),
            str(r.get('site', '')), str(r.get('action', '')), str(r.get('candidate_id', ''))))
        ordered.extend(group)
    return dict(ordered_actions=ordered, rejected_actions=rejected,
        selected=deepcopy(ordered[0]) if ordered else None,
        Q50_primary_tie_tolerance=tolerance,
        ranking_rule='Q50_P1_FIRST;TIED_Q90_GRID_VIOLATIONS_CARRYOUT_QUEUE_PEAK;THEN_LESS_MIGRATION_DELAY',
        Q90_backlog_blanket_veto=False, original_A_stage_P2=False,
        global_bound_or_optimality_certificate=False, forced_action=False)
