"""Continuous compute authority and independent-day carry-out reconciliation.

Midnight never imposes a completion constraint. Reservation slots are distinct
from exact compute seconds, including the final partial slot.
"""
from dataclasses import dataclass
from math import ceil,isfinite
from v42_job_capability import ServiceBoundary
from .contracts import require,digest

CONTRACT='V42_CONTINUOUS_SERVICE_INDEPENDENT_SNAPSHOT_V1'


@dataclass(frozen=True)
class NativeServiceBoundary(ServiceBoundary):
    window_authority_sha256:str=''
    duration_authority_sha256:str=''

    def require(self):
        require(self.authority_id==CONTRACT and self.finalized,'SERVICE_CONTRACT_UNBOUND')
        require(len(self.window_authority_sha256)==len(self.duration_authority_sha256)==64,'SERVICE_INPUT_LINEAGE')
        require(self.allowed_starts and all(type(t) is int for t in self.allowed_starts),'FINITE_AUTHORIZED_STARTS')


def boundary(job,starts,window_sha,duration_sha,H=96):
    starts=tuple(sorted(set(starts)))
    require(job.reference_start in starts and all(t>=job.event for t in starts),'REFERENCE_WINDOW')
    # Representation ceiling, NOT a job deadline. Migration restarts before H;
    # full remaining work can finish after H. Every possible tail is included.
    limit=max(max(starts),H)+job.service_slots
    return NativeServiceBoundary(CONTRACT,True,False,starts,limit,window_sha,duration_sha)


def service_identity(seconds,gpu,segments,H=96):
    require(isfinite(seconds) and seconds>0 and gpu>0,'SERVICE_AMOUNT')
    slots=ceil(seconds/900)
    require(sum(b-a for _,a,b in segments)==slots and all(b>=a for _,a,b in segments),'RESERVATION_MASS')
    require(all(segments[i][2]<=segments[i+1][1] for i in range(len(segments)-1)),'COMPUTE_OVERLAP')
    left=seconds;prefix=tail=0.
    for _,a,b in segments:
        delivered=min(left,(b-a)*900)
        inside=min(delivered,max(0,H-a)*900)
        prefix+=inside;tail+=delivered-inside;left-=delivered
    require(abs(left)<1e-8 and abs(prefix+tail-seconds)<1e-8,'EXACT_COMPUTE_IDENTITY')
    return dict(PASS=True,exact_compute_seconds=seconds,allocated_slots=slots,
        unused_final_reservation_seconds=slots*900-seconds,prefix_compute_seconds=prefix,
        tail_compute_seconds=tail,tail_compute_GPUh=tail*gpu/3600,
        reserved_GPUh=slots*gpu/4,exact_compute_GPUh=seconds*gpu/3600,
        post_H_electrical_security_claimed=False)


def reconcile(previous,current,event_seconds,*,completion_receipt=None):
    """No requeue or pending reservation movement is inferred from a snapshot.

    Prior reservation is a counterfactual plan, not evidence of execution.
    RUNNING observation replaces that plan in a new independent snapshot view,
    retaining the old plan in history and preserving site identity.
    """
    require(current['observed_seconds']<=event_seconds,'FUTURE_SNAPSHOT')
    require(previous['episode_id']==current['episode_id'],'EPISODE_IDENTITY')
    require(previous['site']==current['site'],'CONTINUING_SITE_REWRITE')
    if completion_receipt is not None:
        require(current['state']=='COMPLETED' and current['observed_seconds']<=completion_receipt['observed_seconds']<=event_seconds
                and completion_receipt['episode_id']==current['episode_id']
                and len(completion_receipt['source_sha256'])==64,'COMPLETION_AUTHORITY')
        return dict(status='OBSERVED_COMPLETED_RELEASE',release_previous=True,delete_history=False)
    if current['state']=='RUNNING':
        require(current.get('known_start_seconds') is not None and current['known_start_seconds']<=event_seconds,'CAUSAL_START')
        return dict(status='CURRENT_RUNNING_SNAPSHOT_REPLACES_PRIOR_COUNTERFACTUAL_VIEW',release_previous=True,
                    delete_history=False,service_reduced=False,site_changed=False,sequential_propagation=False)
    if current['state']=='PENDING' and previous['absolute_start_seconds']<event_seconds:
        return dict(status='UNRESOLVED_EXPIRED_COUNTERFACTUAL_PENDING_START',release_previous=False,
                    delete_history=False,service_reduced=False,site_changed=False,sequential_propagation=False)
    return dict(status='RETAIN_EXISTING_RESERVATION',release_previous=False,delete_history=False)
