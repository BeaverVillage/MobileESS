"""Same-case saved Planning resources and causal Actual occupancy.

The native A stage's cohort service and carryout are replayed unchanged.
Anonymous Q50, capacity-backed reserves and physical jobs are distinct ledgers.
This adapter has no solver, future Actual request bank or completion reader.
"""
from copy import deepcopy
import math

import numpy as np

from .actual import _require_public_metadata
from .policy import digest
from .q90_recourse import load_nominal_service
from .reservation_state import union_job_segments
from v42_final.workload import ForecastBook


IDENTITY_FIELDS=('source_sha','stage_case_sha','science_sha','initial_state_sha',
    'time_axis_sha','cc4_sha','runtime_sha')
MATRIX_FIELDS=('known_site_GPU','nominal_site_GPU','reserve_site_GPU',
    'achieved_CC4_reserve_site_GPU','achieved_runtime_reserve_site_GPU')


def audit_planning_capacity(a_result,capacities,*,required_site_count=12):
    sites=tuple(a_result.get('resource_sites',()))
    if (len(sites)!=required_site_count or len(set(sites))!=len(sites) or set(sites)!=set(capacities)):
        raise ValueError('PLANNING_RESOURCE_EXACT_SITE_AXIS_REQUIRED')
    if any(not math.isfinite(float(v)) or v<=0 or int(v)!=v for v in capacities.values()):
        raise ValueError('FINITE_POSITIVE_WHOLE_GPU_CAPACITY_REQUIRED')
    matrices={}
    for key in MATRIX_FIELDS:
        if key not in a_result or set(a_result[key])!=set(sites):
            raise ValueError('PLANNING_SAVED_RESOURCE_MATRIX_MISSING:'+key)
        array=np.asarray([a_result[key][s] for s in sites],float).T
        if array.shape!=(96,len(sites)) or not np.isfinite(array).all() or np.any(array<-1e-7):
            raise ValueError('PLANNING_SAVED_RESOURCE_MATRIX_AXIS_OR_FINITE:'+key)
        matrices[key]=array
    for key in ('CC4_reserve_shortfall_GPU_slots','runtime_reserve_shortfall_GPU_slots'):
        if key not in a_result or not math.isfinite(float(a_result[key])) or a_result[key]<-1e-7:
            raise ValueError('PLANNING_RESERVE_SHORTFALL_MUST_BE_EXPLICIT:'+key)
    # Target reserve_site_GPU is a demand allocation. Only the two achieved
    # matrices belong in the physical capacity-backed Planning inequality.
    used=sum(matrices[key] for key in ('known_site_GPU','nominal_site_GPU',
        'achieved_CC4_reserve_site_GPU','achieved_runtime_reserve_site_GPU'))
    cap=np.asarray([capacities[s] for s in sites],float)
    violation=float(max(0.,np.max(used-cap)))
    if violation>1e-5:raise ValueError('KNOWN_CC4_ACHIEVED_RESERVE_PLANNING_CAPACITY_VIOLATION')
    result=dict(status='PASS',scope='SAVED_PLANNING_RESOURCE_CAPACITY_ONLY',slots=96,sites=list(sites),
        relation='Known + Unknown_Q50_Nominal + Achieved_CC4_Reserve + Achieved_Runtime_Reserve <= Site_Capacity',
        capacity_max_violation_GPU=violation,minimum_unused_capacity_GPU=float(np.min(cap-used)),
        target_CC4_reserve_GPU_slots=float(matrices['reserve_site_GPU'].sum()),
        achieved_CC4_reserve_GPU_slots=float(matrices['achieved_CC4_reserve_site_GPU'].sum()),
        achieved_runtime_reserve_GPU_slots=float(matrices['achieved_runtime_reserve_site_GPU'].sum()),
        CC4_reserve_shortfall_GPU_slots=float(a_result['CC4_reserve_shortfall_GPU_slots']),
        runtime_reserve_shortfall_GPU_slots=float(a_result['runtime_reserve_shortfall_GPU_slots']),
        nominal_forecast_is_job_reservation=False,reserve_target_is_achieved_capacity=False,
        Actual_certified=False,Fresh_AC_certified=False)
    return matrices,result


class PlanningActualResourceBridge:
    def __init__(self,a_result,*,identity,expected_identity,capacities,q50,q90,
            timing_lower,timing_upper,cc4_source_authority,begin_seconds,required_site_count=12):
        for key in IDENTITY_FIELDS:
            value=identity.get(key)
            if (not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value)
                    or value!=expected_identity.get(key)):
                raise ValueError('SAME_CASE_PLANNING_ACTUAL_IDENTITY_REQUIRED:'+key)
        if a_result.get('case_sha')!=identity['stage_case_sha']:
            raise ValueError('SAME_CASE_A_STAGE_CASE_SHA_REQUIRED')
        residual=a_result.get('FULL_max_residual',math.inf)
        if (a_result.get('FULL_feasible') is not True or not math.isfinite(float(residual))
                or residual<0 or residual>1e-5):
            raise ValueError('SAME_CASE_A1_NOT_CERTIFIED')
        if cc4_source_authority.get('prediction_sha')!=identity['cc4_sha']:
            raise ValueError('SAME_CASE_CC4_SOURCE_SHA_REQUIRED')
        if a_result.get('aidc_anchor')!=cc4_source_authority.get('aidc_anchor'):
            raise ValueError('SAME_CASE_CC4_KNOWN_ANCHOR_REQUIRED')
        self.matrices,self.capacity_audit=audit_planning_capacity(a_result,capacities,
            required_site_count=required_site_count)
        self.nominal=load_nominal_service(a_result,q50,timing_lower,timing_upper,
            source_authority=cc4_source_authority)
        self.source=deepcopy(a_result);self.source_sha=digest(a_result)
        self.capacities=dict(capacities)
        self.identity=deepcopy(identity);self.sites=tuple(a_result['resource_sites']);self.begin=float(begin_seconds)
        self.book=ForecastBook(tuple(q50),tuple(q90),self.begin)
        self.observed={};self.transition_rows=[];self.snapshots=[];self.last_event=-math.inf
        x=np.asarray(self.nominal['x_GPUh'],float);site=self.matrices['nominal_site_GPU']
        weights=np.divide(site,site.sum(axis=1)[:,None],out=np.zeros_like(site),where=site.sum(axis=1)[:,None]>0)
        self.cohort_site_GPU=4*x[:,:,None]*weights[None,:,:]
        if not np.allclose(self.cohort_site_GPU.sum(axis=0),site,atol=1e-7,rtol=0):
            raise ValueError('SAVED_CC4_COHORT_SITE_MARGINAL_DRIFT')

    def _frozen(self,now):
        if digest(self.source)!=self.source_sha:raise ValueError('PLANNING_SAVED_RESOURCE_SOURCE_DRIFT')
        if now<self.last_event:raise ValueError('NONCAUSAL_RESOURCE_BRIDGE_EVENT')
        self.last_event=float(now)

    def observe(self,metadata,now):
        _require_public_metadata(metadata);self._frozen(now)
        uid=metadata['uid']
        if not metadata.get('is_observed',True) or metadata['submit_seconds']>now:
            raise ValueError('FORECAST_BRIDGE_OBSERVED_SUBMISSION_REQUIRED')
        if uid in self.observed:raise ValueError('CC4_OBSERVED_UID_MUST_BE_DEBITED_ONCE')
        self.observed[uid]=deepcopy(metadata)
        row=dict(uid=uid,event_seconds=float(now),state='OBSERVED',origin_unknown=metadata['origin_unknown'],
            physical_GPU_added=0,forecast_GPU_added_to_physical=0,forecast_debit_count=0)
        submit=metadata['submit_seconds']
        if (metadata['origin_unknown'] and metadata.get('cc4_eligible',True)
                and self.begin<=submit<self.begin+86400):
            state=self.book.submit(uid,submit,now,metadata['gpu'],metadata['t50_seconds'])
            row.update(forecast_debit_count=1,observed_nominal_GPUh=metadata['gpu']*metadata['t50_seconds']/3600,
                CC4_hour=state['hour'],remaining_CC4_Q50_GPUh=state['remaining_CC4_Q50_GPUh'])
        self.transition_rows.append(row)
        return deepcopy(row)

    def snapshot(self,now,metadata,reservations):
        self._frozen(now)
        rows=[self.book.row(h,now) for h in range(24)]
        remaining=np.asarray([r['remaining_CC4_Q50_GPUh'] for r in rows])
        q50=np.asarray(self.book.q50,float);ratio=np.divide(remaining,q50,out=np.zeros(24),where=q50>0)
        residual=(self.cohort_site_GPU*ratio[:,None,None]).sum(axis=0)
        carry=np.asarray(self.nominal['carryout_GPUh_by_hour'])*ratio
        mass=float(residual.sum()/4+carry.sum())
        if abs(mass-remaining.sum())>1e-7:raise ValueError('CC4_REMAINING_SERVICE_AND_CARRY_MASS_DRIFT')
        running={s:0. for s in self.sites};committed={s:0. for s in self.sites}
        completed_GPUh=0.;carry_GPUh=0.
        for uid,m in metadata.items():
            if uid not in self.observed:raise ValueError('PHYSICAL_UID_HAS_NO_OBSERVATION_BRIDGE')
            if m['state']=='RUNNING':running[m['current_site']]+=m['gpu']
            work=m.get('accumulated_compute_seconds',0)*m['gpu']/3600
            if m['origin_unknown']:
                if m['state']=='COMPLETED':completed_GPUh+=work
                else:carry_GPUh+=work
            booking=reservations.reservations.get(uid,{})
            if m['state']=='PENDING' and booking.get('status')!='RELEASED':
                for s in union_job_segments(booking.get('segments',[])):
                    if s['resource'].startswith('gpu:') and s['begin']<=now<s['end']:
                        committed[s['resource'][4:]]+=s['quantity']
        slot=int((now-self.begin)//900)
        planning={key:(None if not 0<=slot<96 else dict(zip(self.sites,array[slot].tolist())))
            for key,array in self.matrices.items()}
        result=dict(event_seconds=float(now),status='PASS',scope='CAUSAL_RESOURCE_ACCOUNTING_ONLY',
            planning=planning,actual_Running_GPU=running,actual_Committed_GPU=committed,
            not_yet_arrived_forecast_GPU_96=residual.tolist(),remaining_CC4_Q50_GPUh=float(remaining.sum()),
            remaining_CC4_in_day_GPUh=float(residual.sum()/4),remaining_CC4_carryout_GPUh=float(carry.sum()),
            expired_unsubmitted_Q50_GPUh=sum(r['expired_unsubmitted_Q50_GPUh'] for r in rows),
            observed_Unknown_nominal_GPUh=sum(s['nominal_GPUh'] for s in self.book.submissions.values()),
            observed_Unknown_completed_actual_GPUh=completed_GPUh,observed_Unknown_carry_computed_actual_GPUh=carry_GPUh,
            carry_remaining_actual_GPUh=None,carry_remaining_status='PRIVATE_FUTURE_RUNTIME_NOT_READ',
            physical_GPU_includes_forecast=False,planning_power_target_enforced=False,
            Original_C1_actual_PQ_recompute_required=True,source_service_preserved=True,
            mathematical_cohort_site_coupling='CANONICAL_TRANSPORT_PRESERVES_BOTH_SAVED_NATIVE_MARGINALS')
        self.snapshots.append(result)
        return deepcopy(result)

    def export(self):
        return dict(schema='AIDC_PLANNING_ACTUAL_RESOURCE_BRIDGE_V1',status='PASS',
            scope='SAME_CASE_SAVED_PLANNING_AND_CAUSAL_ACCOUNTING_ONLY',identity=deepcopy(self.identity),
            planning_result_sha=self.source_sha,capacity_audit=deepcopy(self.capacity_audit),
            nominal_service_replay=deepcopy(self.nominal['replay']),transitions=deepcopy(self.transition_rows),
            snapshots=deepcopy(self.snapshots),Native_calls=0,Actual_global_MILP_calls=0,
            Actual_performance_status='NOT_CERTIFIED',Fresh_AC_status='NOT_RUN')
