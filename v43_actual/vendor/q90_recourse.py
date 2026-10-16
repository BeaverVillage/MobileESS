"""Source-bound aggregate Q90-minus-Q50 service recourse, without an optimizer.

The frozen A-stage nominal schedule remains the physical Q50 baseline. The
additional quantile demand is work, not guaranteed GPU occupation. An unmet
TRAIN CDF lower bound is an explicit timing risk; no job QoS or AC certificate
is produced by this divisible aggregate approximation.
"""
import ast
from copy import deepcopy
import hashlib
import json

import numpy as np


SLOTS = 96
DT_H = .25
AUDIT_TOL = 1e-7  # Numerical source replay, not a new model constraint.
GRID_TOL = 1e-9  # Exact OriginalGridPacket scalar hard guard.
POLICY_ID = 'Q90_EXTRA_ORIGINAL_CDF_GRID_ADMITTED_RECOURSE_V1'


def _array(value, shape=None):
    a = np.asarray(value, dtype=float)
    if not np.isfinite(a).all() or (shape is not None and a.shape != shape):
        raise ValueError('FINITE_EXPLICIT_RECOURSE_AXIS_REQUIRED')
    return a


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _cdf(lower, upper):
    lo, hi = _array(lower), _array(upper)
    if (lo.ndim != 1 or not len(lo) or hi.shape != lo.shape or np.any(lo < 0)
            or np.any(hi > 1) or np.any(lo > hi) or np.any(np.diff(lo) < -1e-12)
            or np.any(np.diff(hi) < -1e-12)):
        raise ValueError('ORIGINAL_TRAIN_CDF_ENVELOPE_REQUIRED')
    return lo, hi


def _authority(authority, q50, q90=None, packet=None):
    a = deepcopy(dict(authority))
    if (a.get('model_id') != 'LGBM_weighted_c1_s20260924'
            or any(not a.get(k) for k in ('prediction_sha', 'kernel_sha', 'timing_envelope_sha'))
            or a.get('future_Actual_or_UID_inputs_used', False)
            or a.get('forecast_modifications', 0)):
        raise ValueError('UNCHANGED_CC4_MODEL_KERNEL_TRAIN_CDF_AUTHORITY_REQUIRED')
    for name, value in (('q50_hourly_GPUh', q50), ('q90_hourly_GPUh', q90)):
        if value is not None and name in a and not np.array_equal(_array(a[name], (24,)), value):
            raise ValueError('LITERAL_SOURCE_HOURLY_QUANTILE_CHANGED')
    if packet is not None and a['prediction_sha'] != packet.bindings['cc4_sha']:
        raise ValueError('CC4_PACKET_PREDICTION_BINDING_DRIFT')
    return a


def load_nominal_service(a2, q50_hourly, timing_lower, timing_upper, *, source_authority):
    """Replay original x[h,t]/carry and site projection; never make a new Q50 plan."""
    q50 = _array(q50_hourly, (24,))
    if np.any(q50 < 0):
        raise ValueError('NONNEGATIVE_HOURLY_Q50_REQUIRED')
    lo, hi = _cdf(timing_lower, timing_upper)
    authority = _authority(source_authority, q50)
    sites = tuple(a2.get('resource_sites') or sorted(a2['nominal_site_GPU']))
    if len(set(sites)) != len(sites) or not sites:
        raise ValueError('EXPLICIT_ORIGINAL_SITE_AXIS_REQUIRED')
    nominal = _array([a2['nominal_site_GPU'][s] for s in sites], (len(sites), SLOTS)).T
    known = _array([a2['known_site_GPU'][s] for s in sites], (len(sites), SLOTS)).T
    if np.any(nominal < -AUDIT_TOL) or np.any(known < -AUDIT_TOL):
        raise ValueError('NONNEGATIVE_ORIGINAL_SITE_GPU_REQUIRED')
    x = np.zeros((24, SLOTS))
    seen = set()
    for key, value in a2['CC4_service'].items():
        index = ast.literal_eval(key) if isinstance(key, str) else key
        if (not isinstance(index, tuple) or len(index) != 2
                or any(not isinstance(n, int) for n in index)):
            raise ValueError('ORIGINAL_COHORT_SLOT_INDEX_REQUIRED')
        h, t = index
        if not 0 <= h < 24 or not 0 <= t < SLOTS or not 4*h <= t < 4*h+len(lo):
            raise ValueError('NOMINAL_SERVICE_OUTSIDE_SOURCE_CDF_DOMAIN')
        if index in seen:
            raise ValueError('DUPLICATE_ORIGINAL_COHORT_SLOT_INDEX')
        seen.add(index)
        x[h, t] = float(value)
    carry = _array([a2['CC4_carryout'].get(str(h), a2['CC4_carryout'].get(h, 0.))
                    for h in range(24)], (24,))
    if np.any(x < -AUDIT_TOL) or np.any(carry < -AUDIT_TOL):
        raise ValueError('NONNEGATIVE_ORIGINAL_X_CARRY_REQUIRED')
    mass_error = x.sum(axis=1)+carry-q50
    site_error = nominal.sum(axis=1)-x.sum(axis=0)/DT_H
    timing_error = 0.
    for h in range(24):
        cumulative = np.cumsum(x[h])
        for t in range(4*h, min(SLOTS, 4*h+len(lo))):
            timing_error = max(timing_error, lo[t-4*h]*q50[h]-cumulative[t],
                               cumulative[t]-hi[t-4*h]*q50[h])
    if (np.max(np.abs(mass_error)) > AUDIT_TOL or np.max(np.abs(site_error)) > AUDIT_TOL
            or timing_error > AUDIT_TOL):
        raise ValueError('ORIGINAL_A_STAGE_NOMINAL_SOURCE_REPLAY_FAILED')
    result = dict(schema='FROZEN_A_STAGE_NOMINAL_SERVICE_V1', site_axis=list(sites),
        x_GPUh=x.tolist(), carryout_GPUh_by_hour=carry.tolist(),
        nominal_site_GPU=nominal.tolist(), known_site_GPU=known.tolist(),
        q50_hourly_GPUh=q50.tolist(), aidc_anchor=a2['aidc_anchor'],
        source_authority=authority, nominal_schedule_reused_without_modification=True,
        kernel_is_fixed_execution_schedule=False,
        replay=dict(per_cohort_mass_max_error_GPUh=float(np.max(np.abs(mass_error))),
                    site_projection_max_error_GPU=float(np.max(np.abs(site_error))),
                    CDF_max_violation_GPUh=float(max(0., timing_error)),
                    audit_numerical_tolerance=AUDIT_TOL,
                    original_model_hard_constraint_tolerance_changed=False))
    result['nominal_service_sha'] = _digest(result)
    return result


class _Admission:
    """Positive site-GPU interval from every original signed affine hard row."""
    def __init__(self, packet):
        self.p = packet
        self.calls = 0
        self.backoffs = 0
        self.roundoff_repairs = 0
        self.vectorized_calls = 0
        self.cols = [packet.control_names.index('aidc_load_kw['+s+']') for s in packet.sites]
        key=('ORIGINAL_SIGNED_DERIVATIVE_TABLE_V2',packet.controls.tobytes(),packet.p_slope.tobytes(),
             tuple(c.coefficient_sha256 for c in packet.coefficients))
        cached=getattr(packet,'_q90_original_derivatives',None)
        if cached is None or cached[0] != key:
            tables=[]
            for t,c in enumerate(packet.coefficients):
                slope=packet.p_slope[t,:,None]
                dv=c.voltage_matrix[self.cols]*slope
                di=c.current_matrix[self.cols]*slope
                dp=c.flow_p_matrix[:,self.cols].T*slope
                dq=c.flow_q_matrix[:,self.cols].T*slope
                dc=packet.correction[t][:,self.cols].T*slope
                df=(c.flow_p_matrix[:,self.cols].T[:,:,None]*packet.cos+
                    c.flow_q_matrix[:,self.cols].T[:,:,None]*packet.sin)*slope[:,:,None]
                dl=df/packet.ap[t][None,:,None]+packet.correction[t][:,self.cols].T[:,:,None]*slope[:,:,None]
                rated=np.array([b for b,r in enumerate(c.transformer_ratings) if r is not None],dtype=int)
                ratings=np.array([float(c.transformer_ratings[b]) for b in rated])*np.cos(np.pi/16)+GRID_TOL
                control=packet.controls[t]
                base=(c.voltage_constant+c.voltage_matrix.T@control,
                    c.flow_p_constant+c.flow_p_matrix@control,c.flow_q_constant+c.flow_q_matrix@control,
                    c.current_constant+c.current_matrix.T@control,
                    packet.correction[t]@(control-c.anchor)+packet.bias[t])
                tables.append((dv,di,df,dl,rated,ratings,dp,dq,dc,base))
            packet._q90_original_derivatives=(key,tables)
        self.tables=packet._q90_original_derivatives[1]

    @staticmethod
    def _limit(current, derivative, upper):
        current, derivative = np.asarray(current), np.asarray(derivative)
        mask = derivative > 0
        if not np.any(mask):
            return float('inf')
        return float(np.min((np.asarray(upper)-current)[mask]/derivative[mask]))

    def _point(self,t,delta):
        p,c=self.p,self.p.coefficients[t]
        dv,di,_,_,_,_,dp,dq,dc,base=self.tables[t]
        v=base[0]+delta@dv
        flow_p=base[1]+delta@dp
        flow_q=base[2]+delta@dq
        faces=flow_p[:,None]*p.cos+flow_q[:,None]*p.sin
        line=faces/p.ap[t][:,None]
        line+=(base[4]+delta@dc)[:,None]
        current=base[3]+delta@di
        return v,faces,line,current

    def safe(self, t, delta, *, scalar=False):
        if scalar:
            self.calls+=1
            return not self.p._at_slot(t,delta)[1]
        self.vectorized_calls+=1
        p=self.p;v,faces,line,current=self._point(t,delta)
        rated,ratings=self.tables[t][4:6]
        # Same original matrix products and faces. Only the per-branch Python
        # loop is reduced to a broadcast Boolean predicate; bounds unchanged.
        hard=bool(not (np.any(v<p.voltage_lower-GRID_TOL) or np.any(v>p.voltage_upper+GRID_TOL)
            or max(0.,float(np.max(line[p.line_indices])))>1+GRID_TOL
            or (len(p.transformer_indices) and np.any(current[p.transformer_indices]>1+GRID_TOL))
            or (len(rated) and np.any(np.max(faces[rated],axis=1)>ratings))))
        # Cached affine grouping may differ by floating point roundoff. Near
        # any hard boundary the literal source scalar decides, never a looser
        # physical threshold. This margin only selects the fallback path.
        near=(np.min(np.abs(v-(p.voltage_lower-GRID_TOL)))<1e-10
            or np.min(np.abs(v-(p.voltage_upper+GRID_TOL)))<1e-10
            or np.min(np.abs(line[p.line_indices]-(1+GRID_TOL)))<1e-10
            or (len(p.transformer_indices) and np.min(np.abs(current[p.transformer_indices]-(1+GRID_TOL)))<1e-10)
            or (len(rated) and np.min(np.abs(np.max(faces[rated],axis=1)-ratings))<1e-8))
        return self.safe(t,delta,scalar=True) if near else hard

    def amount(self, t, j, delta, maximum):
        p, c = self.p, self.p.coefficients[t]
        if maximum<=0:return 0.
        v,faces,line,current=self._point(t,delta)
        dv_all,di_all,df_all,dl_all,rated,ratings=self.tables[t][:6]
        dv,df,dl=dv_all[j],df_all[j],dl_all[j]
        limits = [maximum,
            self._limit(v, dv, np.full_like(v, p.voltage_upper+GRID_TOL)),
            self._limit(-v, -dv, np.full_like(v, -p.voltage_lower+GRID_TOL)),
            self._limit(line[p.line_indices], dl[p.line_indices],
                        np.ones_like(line[p.line_indices])+GRID_TOL)]
        if len(p.transformer_indices):
            dcurrent = di_all[j]
            ids = p.transformer_indices
            limits.append(self._limit(current[ids], dcurrent[ids], np.ones(len(ids))+GRID_TOL))
        if len(rated):
            limits.append(self._limit(faces[rated],df[rated],np.broadcast_to(ratings[:,None],faces[rated].shape)))
        grant = max(0., min(limits))
        if grant == 0:
            return 0.
        proposed = delta.copy(); proposed[j] += grant
        grid_boundary=grant<maximum
        if self.safe(t, proposed,scalar=grid_boundary):
            return grant
        # Floating point boundary repair retains the original scalar guard.
        self.backoffs += 1
        # Most failures are last-bit grouping at an affine boundary. A small
        # conservative floating point decrement avoids 32 scalar probes; it
        # changes admitted service only, never source demand or a hard bound.
        slope=abs(p.p_slope[t,j])
        control_gpu=abs(p.controls[t,self.cols[j]])/slope if slope>0 else 0.
        repair=max(abs(grant),abs(delta[j]),control_gpu,1.)*np.finfo(float).eps*(len(p.control_names)+len(p.sites)+16)
        repaired=max(0.,grant-repair)
        proposed=delta.copy();proposed[j]+=repaired
        if self.safe(t,proposed,scalar=True):
            self.roundoff_repairs+=1
            return repaired
        low, high = 0., grant
        for _ in range(32):
            mid = (low+high)/2
            proposed = delta.copy(); proposed[j] += mid
            if self.safe(t, proposed,scalar=True): low = mid
            else: high = mid
        return low


def evaluate_q90_recourse(packet, nominal, q90_hourly, timing_lower, timing_upper, *,
        candidate_gpu_delta=None, remaining_slot=0, begin=0, served_before=None,
        remaining_work_GPUh=None, source_authority=None, site_priority=None):
    """Admit only extra work under CDF upper, capacity and original signed grid.

    ``remaining_slot`` selects the event's remaining physical score. With
    ``begin=0`` every variant uses the same full-day counterfactual recurrence,
    never private past service. A later ``begin`` requires explicit cohort
    history and remaining mass. CDF lower deficits are reported, not erased.
    """
    lo, hi = _cdf(timing_lower, timing_upper)
    q50, q90 = _array(nominal['q50_hourly_GPUh'], (24,)), _array(q90_hourly, (24,))
    if np.any(q90 < q50):
        raise ValueError('UNCHANGED_Q90_Q50_ORDER_REQUIRED')
    authority = _authority(source_authority or nominal['source_authority'], q50, q90, packet)
    if tuple(nominal['site_axis']) != packet.sites or nominal['aidc_anchor'] != packet.bindings['aidc_anchor']:
        raise ValueError('FROZEN_A_STAGE_SITE_OR_ANCHOR_DRIFT')
    if not 0 <= begin <= remaining_slot < SLOTS:
        raise ValueError('EXPLICIT_BEGIN_REMAINING_SLOT_REQUIRED')
    shape = (SLOTS, len(packet.sites))
    baseline = _array(nominal['known_site_GPU'], shape)+_array(nominal['nominal_site_GPU'], shape)
    if packet.known_gpu is None or not np.array_equal(_array(nominal['known_site_GPU']), packet.known_gpu):
        raise ValueError('ORIGINAL_KNOWN_PROFILE_DRIFT')
    if _digest({k:v for k,v in nominal.items() if k != 'nominal_service_sha'}) != nominal['nominal_service_sha']:
        raise ValueError('FROZEN_NOMINAL_SERVICE_RECEIPT_CHANGED')
    if 'nominal_site_GPU' in packet.aidc_plan:
        for j,s in enumerate(packet.sites):
            if not np.array_equal(_array(nominal['nominal_site_GPU'])[:,j],
                                  _array(packet.aidc_plan['nominal_site_GPU'][s])):
                raise ValueError('ORIGINAL_PACKET_NOMINAL_SITE_PROFILE_DRIFT')
    delta = np.zeros(shape) if candidate_gpu_delta is None else _array(candidate_gpu_delta, shape).copy()
    if np.any(delta[:remaining_slot] != 0):
        raise ValueError('CANDIDATE_CANNOT_CHANGE_PAST_PHYSICAL_STATE')
    capacities = _array([packet.capacities[s] for s in packet.sites])
    fixed = baseline+delta
    capacity_invalid = (fixed < -GRID_TOL) | (fixed > capacities+GRID_TOL)
    source_extra = q90-q50
    prior = {int(h): float(v) for h, v in (served_before or {}).items()}
    if any(not 0 <= h < 24 or not np.isfinite(v) or v < 0 for h, v in prior.items()):
        raise ValueError('NONNEGATIVE_EXPLICIT_PRIOR_COHORT_SERVICE_REQUIRED')
    if any(4*h >= begin and v > 0 for h,v in prior.items()):
        raise ValueError('PRIOR_SERVICE_CANNOT_PRECEDE_COHORT_ARRIVAL')
    if begin == 0:
        if prior or remaining_work_GPUh is not None:
            raise ValueError('FULL_DAY_SOURCE_RECOURSE_HAS_NO_INVENTED_PRIOR_HISTORY')
        work = source_extra.copy()
    else:
        if remaining_work_GPUh is None:
            raise ValueError('MID_COHORT_EXPLICIT_REMAINING_WORK_REQUIRED')
        work = _array(remaining_work_GPUh, (24,)).copy()
        if np.any(work < 0):
            raise ValueError('NONNEGATIVE_EXPLICIT_REMAINING_WORK_REQUIRED')
        for h in range(24):
            if 4*h < begin and source_extra[h] > 0 and h not in prior:
                raise ValueError('MID_COHORT_HISTORY_REQUIRED')
        old = np.array([prior.get(h, 0.) for h in range(24)])
        if np.max(np.abs(work+old-source_extra)) > AUDIT_TOL:
            raise ValueError('SOURCE_EXTRA_PRIOR_REMAINING_MASS_DRIFT')
    old = np.array([prior.get(h, 0.) for h in range(24)])
    total, remaining, cumulative = work+old, work.copy(), old.copy()
    priority = tuple(site_priority or packet.sites)
    if len(priority) != len(packet.sites) or set(priority) != set(packet.sites):
        raise ValueError('DETERMINISTIC_COMPLETE_SITE_PRIORITY_REQUIRED')
    indices = [packet.sites.index(s) for s in priority]
    cache_key=(POLICY_ID,'SOURCE_GUARD_CACHE_V2',nominal['nominal_service_sha'],q90.tobytes(),lo.tobytes(),hi.tobytes(),
        delta.tobytes(),remaining_slot,begin,tuple(sorted(prior.items())),work.tobytes(),
        priority,capacities.tobytes(),packet.controls.tobytes(),packet.p_slope.tobytes(),
        tuple(c.coefficient_sha256 for c in packet.coefficients),_digest(authority),
        tuple(sorted(packet.bindings.items())))
    cache=getattr(packet,'_q90_recourse_cache',None)
    if cache is not None and cache_key in cache:
        result=deepcopy(cache[cache_key])
        result['runtime_cache']=dict(hit=True,bounded_entries=len(cache),
            binding='FULL_SOURCE_NOMINAL_QUANTILES_CDF_PHYSICS_CAPACITY_HISTORY_DELTA_AND_EVENT_AXIS')
        return result
    extra = np.zeros(shape); x = np.zeros((24, SLOTS)); pending = np.zeros(SLOTS)
    timing_violations = []; blocked_slots = []; admission = _Admission(packet)
    for t in range(begin, SLOTS):
        active = [h for h in range(24) if 4*h <= t < 4*h+len(lo) and remaining[h] > 0]
        quotas = {h: max(0., min(remaining[h], hi[t-4*h]*total[h]-cumulative[h])) for h in active}
        required = {h: max(0., min(quotas[h], lo[t-4*h]*total[h]-cumulative[h])) for h in active}
        grid_safe = admission.safe(t, delta[t])
        cap_safe = not np.any(capacity_invalid[t])
        if not grid_safe or not cap_safe:
            blocked_slots.append(dict(slot=t, original_Q50_grid_hard_feasible=grid_safe,
                                      fixed_capacity_feasible=cap_safe))
        else:
            # Required CDF minima first, then FIFO optional service; fixed rule.
            allocations = np.zeros(24)
            available = float(sum(quotas.values()))
            for j in indices:
                maximum = min(max(0., capacities[j]-fixed[t, j]), available/DT_H)
                grant = admission.amount(t, j, delta[t]+extra[t], maximum)
                extra[t, j] += grant; mass = grant*DT_H; available -= mass
                for needs in (required, quotas):
                    for h in active:
                        take = min(mass, max(0., needs[h]-allocations[h]))
                        allocations[h] += take; mass -= take
                        if mass <= 0: break
                    if mass <= 0: break
                if mass > AUDIT_TOL:
                    raise ArithmeticError('RECOURSE_SITE_COHORT_ALLOCATION_MASS_ERROR')
            for h in active:
                x[h, t] = allocations[h]
                remaining[h] -= allocations[h]; cumulative[h] += allocations[h]
        for h in range(24):
            if 4*h <= t < 4*h+len(lo):
                deficit = lo[t-4*h]*total[h]-cumulative[h]
                excess = cumulative[h]-hi[t-4*h]*total[h]
                if deficit > AUDIT_TOL or excess > AUDIT_TOL:
                    timing_violations.append(dict(hour=h, slot=t, lower_deficit_GPUh=max(0., float(deficit)),
                                                  upper_excess_GPUh=max(0., float(excess))))
        pending[t] = sum(max(0., remaining[h]) for h in range(24) if 4*h <= t)
    carry = np.maximum(remaining, 0.)
    mass_error = old+x.sum(axis=1)+carry-source_extra
    site_error = extra.sum(axis=1)*DT_H-x.sum(axis=0)
    score = packet.evaluate(delta+extra, remaining_slot=remaining_slot)
    physical = fixed+extra
    cap_ok = bool(np.all(physical[remaining_slot:] >= -GRID_TOL) and
                  np.all(physical[remaining_slot:] <= capacities+GRID_TOL))
    physical_ok = bool(score['hard_feasible'] and cap_ok)
    max_lower = max((r['lower_deficit_GPUh'] for r in timing_violations), default=0.)
    timing_ok = not timing_violations
    result = dict(schema=POLICY_ID, status=('TIMING_ENVELOPE_MET_AGGREGATE_ONLY' if timing_ok and physical_ok
        else 'TIMING_INFEASIBLE' if physical_ok else 'FIXED_Q50_PHYSICAL_HARD_INFEASIBLE'),
        admitted_extra_site_GPU=extra.tolist(), physical_site_GPU=physical.tolist(),
        extra_x_GPUh=x.tolist(), extra_carryout_GPUh_by_hour=carry.tolist(),
        backlog_GPUh_by_slot=pending.tolist(), terminal_pending_GPUh=0., carryout_GPUh=float(carry.sum()),
        extra_demand_GPUh=float(source_extra.sum()), prior_served_GPUh=float(old.sum()),
        admitted_extra_service_GPUh=float(x.sum()), original_Q50_GPUh=float(q50.sum()),
        original_Q90_GPUh=float(q90.sum()), physical_hard_feasible=physical_ok,
        grid_score=score, capacity_hard_feasible=cap_ok, CDF_timing_feasible=timing_ok,
        CDF_lower_max_deficit_GPUh=float(max_lower), CDF_timing_violations=timing_violations,
        fixed_Q50_blocked_slots=blocked_slots,
        conservation=dict(per_cohort_max_error_GPUh=float(np.max(np.abs(mass_error))),
            site_projection_max_error_GPUh=float(np.max(np.abs(site_error))),
            conserved=bool(np.max(np.abs(mass_error)) <= AUDIT_TOL and np.max(np.abs(site_error)) <= AUDIT_TOL),
            equation='source_extra = prior_served + newly_admitted + terminal_carry',
            terminal_pending_reclassified_as_carry=True),
        nominal_service_sha=nominal['nominal_service_sha'], source_authority=authority,
        source_original_A2_nominal_unchanged=True, old_A2_reserve_target_is_achieved_service=False,
        same_recourse_rule_for_every_candidate=True, deterministic_site_priority=list(priority),
        service_order='CDF_REQUIRED_FIRST_THEN_ORIGINAL_HOUR_FIFO;FIXED_SITE_PRIORITY',
        hourly_arrival_origin='ORIGINAL_BIND_SERVICE_ORIGIN_4_H;NO_OBSERVED_FUTURE_UIDS',
        remaining_slot=int(remaining_slot), begin=int(begin),
        history_scope='FULL_DAY_COUNTERFACTUAL_COMMON_RULE' if begin == 0 else 'EXPLICIT_PRIOR_AND_REMAINING_COHORT_STATE',
        whole_gang_schedulability_certified=False, job_QoS_certified=False,
        Actual_executed=False, Fresh_AC_PASS_claimed=False, Native_Optimize_calls=0,
        kernel_is_fixed_execution_schedule=False, forecast_scaled_or_clipped=False,
        admission=dict(method='ALL_ORIGINAL_SIGNED_AFFINE_ROWS_WITH_ORIGINAL_SCALAR_BOUNDARY_GUARD',
                       scalar_guard_calls=admission.calls, scalar_boundary_backoffs=admission.backoffs,
                       conservative_roundoff_repairs=admission.roundoff_repairs,
                       vectorized_original_guard_calls=admission.vectorized_calls,
                       original_grid_hard_tolerance=GRID_TOL))
    if not result['conservation']['conserved']:
        raise ArithmeticError('RECOURSE_WORK_MASS_NOT_CONSERVED')
    nominal_carry = float(np.sum(nominal['carryout_GPUh_by_hour']))
    nominal_served = float(np.sum(nominal['x_GPUh']))
    lag_mass = float(sum(x[h,t]*(t-4*h)*DT_H for h in range(24)
                         for t in range(max(begin,4*h),SLOTS)))
    max_lag = max(((t-4*h)*DT_H for h in range(24) for t in range(SLOTS)
                   if x[h,t] > AUDIT_TOL), default=0.)
    result.update(original_grid_score=deepcopy(score),
        mass=dict(extra_arrived_GPUh=float(source_extra.sum()),
            extra_served_GPUh=float(old.sum()+x.sum()),
            extra_terminal_backlog_GPUh=float(carry.sum()),
            conservation_PASS=result['conservation']['conserved']),
        CDF_timing_status='MET' if timing_ok else 'LOWER_BOUND_UNMET',
        timing_violations=deepcopy(timing_violations),
        queue_area_GPUh_hours=float(pending[remaining_slot:].sum()*DT_H),
        queue_area_measure='END_OF_QUARTER_BACKLOG_RECTANGLE_OVER_REMAINING_HORIZON',
        extra_carryout_GPUh=float(carry.sum()), nominal_carryout_GPUh=nominal_carry,
        risk_total_unfinished_GPUh=nominal_carry+float(carry.sum()),
        full_Q90_mass=dict(arrived_GPUh=float(q90.sum()),
            frozen_nominal_served_GPUh=nominal_served,
            extra_prior_and_admitted_GPUh=float(old.sum()+x.sum()),
            nominal_carryout_GPUh=nominal_carry,extra_carryout_GPUh=float(carry.sum()),
            terminal_pending_GPUh=0.,
            conservation_error_GPUh=float(nominal_served+nominal_carry+old.sum()+x.sum()+carry.sum()-q90.sum())),
        service_delay=dict(admitted_extra_mean_lag_hours=lag_mass/float(x.sum()) if x.sum()>0 else None,
            admitted_extra_max_lag_hours=float(max_lag),
            scope='DIVISIBLE_AGGREGATE_HOUR_ORIGIN_LAG;NOT_INDIVIDUAL_JOB_DELAY_OR_QOS'),
        QoS_contract_violation_risk='ORIGINAL_TRAIN_CDF_LOWER_UNMET' if not timing_ok
            else 'INDIVIDUAL_JOB_QOS_UNCONFIRMED_AGGREGATE_CDF_MET',
        carryout_scope='EXTRA_ONLY;NOMINAL_CARRY_REPORTED_SEPARATELY')
    if cache is None:
        cache={};packet._q90_recourse_cache=cache
    cache[cache_key]=deepcopy(result)
    if len(cache)>32:cache.pop(next(iter(cache)))
    result['runtime_cache']=dict(hit=False,bounded_entries=len(cache),
        binding='FULL_SOURCE_NOMINAL_QUANTILES_CDF_PHYSICS_CAPACITY_HISTORY_DELTA_AND_EVENT_AXIS')
    return result
