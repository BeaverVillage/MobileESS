"""Causal arrival interface and immutable Actual replay; local P/Q repair removed."""
from dataclasses import dataclass
from math import isfinite
from copy import deepcopy
from pathlib import Path
from typing import Protocol
from .contracts import require,digest,write_once
from .planning import FrozenDayAheadPlan,require_sha
from .voltage import ACTUAL_LOWER_PU, ACTUAL_UPPER_PU

PAPER_POLICIES=('M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE','M2_FIXED30_MOBILE',
    'M3_EVENT30_NO_LOCAL_REPAIR_MOBILE','M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION')
OPTIMIZATION_STAGES=('A1','M1','A2','M2')


@dataclass(frozen=True)
class KernelAnchor:
    service_sha:str
    reference_sha:str
    pq_sha:str
    grid_sha:str

    def require_same(self,current):
        require(self==current and all(len(x)==64 for x in vars(self).values()),'STALE_RESPONSE_KERNEL_ANCHOR')


def event_due(slot,policy,observed_deviation,*,threshold):
    require(policy in PAPER_POLICIES and type(slot) is int and slot>=0 and isfinite(threshold) and threshold>=0,'EVENT_CONTRACT')
    if slot%2:return False
    return policy=='M2_FIXED30_MOBILE' or observed_deviation>threshold


def unknown_arrival(job,event_time,provider,anchor,current_anchor,site_policy,physical_state):
    job.validate(event_time);estimate=provider.predict_total(job,event_time)
    try:estimate.require_production(event_time)
    except ValueError:
        return dict(status='RUNTIME_PROVIDER_UNPROMOTED',job_uid=job.uid,observed=True,
            capability_masks=None,action=None,global_MILP_calls=0,physical_workload_unresolved=True)
    anchor.require_same(current_anchor)
    # Policy must return a site-only reservation; explicit post-validation blocks
    # accidental temporal/migration activation. No solver dependency on this path.
    result=site_policy(job,estimate,physical_state)
    require(result.get('temporal_shift',0)==0 and result.get('migration_count',0)==0,'UNKNOWN_CAPABILITY_AUTHORITY')
    require(result.get('full_service_preserved') is True and result.get('capacity_feasible') is True,'UNKNOWN_RESOURCE_CERTIFICATE')
    return dict(status='SITE_POLICY_PROPOSAL',job_uid=job.uid,action=result,global_MILP_calls=0)


def require_fresh_ac(receipt,schedule_sha,grid_sha):
    if 'transformer_current_contract' in receipt:
        from v42_thermal.authority import require_certificate
        require_certificate(receipt)
    require(receipt.get('PASS',True) is True,'FRESH_AC_REPORTED_FAIL')
    require(receipt.get('voltage_lower_pu',ACTUAL_LOWER_PU)==ACTUAL_LOWER_PU and receipt.get('voltage_upper_pu',ACTUAL_UPPER_PU)==ACTUAL_UPPER_PU,'ACTUAL_PHYSICAL_VOLTAGE_AUTHORITY')
    require(receipt.get('engine')=='OpenDSS' and receipt.get('fresh_run') is True and receipt.get('synthetic') is False,'FRESH_OPENDSS_REQUIRED')
    require(receipt.get('schedule_sha')==schedule_sha and receipt.get('grid_sha')==grid_sha,'FRESH_AC_IDENTITY')
    require(receipt.get('converged') is True and all(receipt.get(k)==0 for k in
        ('voltage_violations','line_current_violations','transformer_current_violations','transformer_kVA_violations')),'FRESH_AC_PHYSICS')
    return True


def repair_pq(*args, **kwargs):
    """Removed production API. Historical implementation is preserved in PR104."""
    raise ValueError('ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42')


def require_frozen_replay(frozen_plan, replay_plan):
    """Physical replay cannot change the frozen route, movement, P or Q."""
    require(digest(frozen_plan)==digest(replay_plan),'ACTUAL_FROZEN_PLAN_CHANGED')
    return True


class ActualBackend(Protocol):
    """Trusted physical adapter, with no planning or optimizer entrypoint.

    Reconstruction may use only the supplied existing frozen causal interface
    for observed unknown arrivals. It must preserve all planned controls.
    """
    def reconstruct_physical(self, schedule: dict, realized_inputs: dict) -> dict: ...
    def fresh_ac(self, physical_arrays: dict) -> dict: ...


def run_dday_actual(frozen_day_ahead_plan, realized_inputs, backend: ActualBackend,
                    output, *, local_p_repair=False, local_q_repair=False,
                    full_reoptimization=False):
    """Replay realized physics and call Fresh OpenDSS once; never rescue FAIL.

    Test adapters are control-flow evidence only. This API does not promote an
    unaccepted M1, runtime provider, policy, or kernel into production authority.
    """
    require(local_p_repair is False, 'ACTUAL_LOCAL_P_REPAIR_FORBIDDEN')
    require(local_q_repair is False, 'ACTUAL_LOCAL_Q_REPAIR_FORBIDDEN')
    require(full_reoptimization is False, 'ACTUAL_FULL_REOPTIMIZATION_FORBIDDEN')
    require(isinstance(frozen_day_ahead_plan,FrozenDayAheadPlan), 'VERIFIED_DAYAHEAD_FREEZE_REQUIRED')
    from v42_a_stage_domain_v2.execution import require_action_authorized
    require_action_authorized(frozen_day_ahead_plan.plan,'ACTUAL',require_day=False)
    frozen=frozen_day_ahead_plan
    frozen.verify()
    require(isinstance(realized_inputs,dict) and
            all(k in realized_inputs and realized_inputs[k] is not None
                for k in ('load','pv','aidc_state')), 'REALIZED_PHYSICAL_INPUTS_REQUIRED')
    realized_sha=digest(realized_inputs)
    schedule=frozen.plan
    realized=deepcopy(realized_inputs)
    output=Path(output)
    # Reserve this run before physical execution, preventing duplicate execution
    # into an existing output directory (including a prior failed run).
    write_once(output/'DDAY_ACTUAL_INPUT.json',dict(
        DAYAHEAD_PLAN_SHA=frozen.plan_sha,POLICY_SHA=frozen.policy_sha,
        GRID_SHA=frozen.grid_sha,realized_inputs_sha=realized_sha,
        local_p_repair=False,local_q_repair=False,full_reoptimization=False))
    physical=backend.reconstruct_physical(schedule,realized)
    require_frozen_replay(frozen.plan,schedule)
    require(digest(realized)==realized_sha,'ACTUAL_REALIZED_INPUTS_CHANGED')
    require(isinstance(physical,dict) and
            set(physical)=={'schedule','load','pv','aidc_state','execution_controls'} and
            all(k in physical and physical[k] is not None
                for k in ('schedule','load','pv','aidc_state','execution_controls')),
            'ACTUAL_PHYSICAL_RECONSTRUCTION_REQUIRED')
    require_frozen_replay(frozen.plan,physical['schedule'])
    require(physical['execution_controls']==dict(local_p_repair=False,
            local_q_repair=False,full_reoptimization=False,global_MILP_calls=0),
            'ACTUAL_EXECUTION_CONTROLS_FORBIDDEN')
    # These identities belong to the caller, never a mutable backend receipt.
    physical=deepcopy(physical)
    physical.update(schedule_sha=frozen.plan_sha,grid_sha=frozen.grid_sha,
                    policy_sha=frozen.policy_sha,realized_inputs_sha=realized_sha,
                    execution_layer='DDAY_ACTUAL',voltage_lower_pu=ACTUAL_LOWER_PU,
                    voltage_upper_pu=ACTUAL_UPPER_PU)
    physical_sha=digest(physical)
    write_once(output/'ACTUAL_PHYSICAL_ARRAYS.json',physical)
    ac=None
    try:
        ac=backend.fresh_ac(physical)
        require(digest(physical)==physical_sha,'ACTUAL_PHYSICAL_ARRAYS_CHANGED')
        frozen.verify()
        require(isinstance(ac,dict),'FRESH_AC_RECEIPT_REQUIRED')
        require(ac.get('execution_layer')=='DDAY_ACTUAL' and
                ac.get('physical_arrays_sha')==physical_sha and
                ac.get('realized_inputs_sha')==realized_sha and
                ac.get('policy_sha')==frozen.policy_sha,'FRESH_AC_ACTUAL_INPUT_IDENTITY')
        require(ac.get('voltage_lower_pu')==ACTUAL_LOWER_PU and
                ac.get('voltage_upper_pu')==ACTUAL_UPPER_PU,'ACTUAL_PHYSICAL_VOLTAGE_AUTHORITY')
        require_fresh_ac(ac,frozen.plan_sha,frozen.grid_sha)
        result=dict(PASS=True,status='PASS',failure=None)
    except Exception as error:
        # Preserve the raw failure; never retry, repair, optimize or create kernel.
        result=dict(PASS=False,status='FAIL',failure=f'{type(error).__name__}:{error}')
    result.update(execution_layer='DDAY_ACTUAL',DAYAHEAD_PLAN_SHA=frozen.plan_sha,
                  POLICY_SHA=frozen.policy_sha,GRID_SHA=frozen.grid_sha,
                  realized_inputs_sha=realized_sha,physical_arrays_sha=physical_sha,
                  fresh_ac=deepcopy(ac),fresh_ac_calls=1,global_MILP_calls=0,
                  local_p_repair=False,local_q_repair=False,final_kernel_created=False)
    write_once(output/'DDAY_ACTUAL_RESULT.json',result)
    return result


def require_dday_kernel(frozen_plan, actual_result, upstream):
    """Final-kernel authority begins only after this exact Actual Fresh AC PASS."""
    from v42_final.gates import require_kernel
    frozen_plan.verify()
    require_sha(actual_result.get('physical_arrays_sha'))
    require_sha(actual_result.get('realized_inputs_sha'))
    require(actual_result.get('PASS') is True and
            actual_result.get('execution_layer')=='DDAY_ACTUAL' and
            actual_result.get('DAYAHEAD_PLAN_SHA')==frozen_plan.plan_sha and
            actual_result.get('GRID_SHA')==frozen_plan.grid_sha and
            actual_result.get('POLICY_SHA')==frozen_plan.policy_sha,
            'DDAY_ACTUAL_FRESH_AC_REQUIRED_BEFORE_KERNEL')
    ac=actual_result['fresh_ac']
    require_fresh_ac(ac,frozen_plan.plan_sha,frozen_plan.grid_sha)
    require(ac.get('execution_layer')=='DDAY_ACTUAL' and
            ac.get('physical_arrays_sha')==actual_result.get('physical_arrays_sha') and
            ac.get('realized_inputs_sha')==actual_result.get('realized_inputs_sha') and
            ac.get('policy_sha')==frozen_plan.policy_sha,'KERNEL_ACTUAL_INPUT_IDENTITY')
    require(upstream.get('grid_anchor')==frozen_plan.grid_sha,'KERNEL_GRID_ANCHOR_IDENTITY')
    require(all(upstream.get(k)==frozen_plan.plan['input_authority_hashes'].get(k)
                for k in ('workload','placement','runtime','MESS_PQ')),'KERNEL_UPSTREAM_PLAN_IDENTITY')
    plan=frozen_plan.plan
    return require_kernel(dict(stage=plan.get('stage'),accepted_native_plan=plan.get('accepted_native_plan'),
                               sha256=frozen_plan.plan_sha),
                          dict(PASS=True,plan_sha=frozen_plan.plan_sha,execution_layer='DDAY_ACTUAL'),upstream)
