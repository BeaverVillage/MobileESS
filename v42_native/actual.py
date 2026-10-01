"""Causal arrival interface and immutable Actual replay; local P/Q repair removed."""
from dataclasses import dataclass
from math import isfinite
from .contracts import require,digest
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
