"""Join the unchanged event engine to frozen Known reservations/current AC."""
import math
from time import perf_counter

import numpy as np

from .vendor.actual import JobEventController
from .vendor.reservation_state import ContractReservationLedger
from .vendor.trajectory_tracking import require_tracking_public
from .presite import PendingPresitePolicy


class IssueContinuityPolicy(PendingPresitePolicy):
    def __init__(self,*args,oracle,**kwargs):
        self.oracle=oracle
        super().__init__(*args,current_ac_guard=oracle.guard,**kwargs)

    def current_guard(self,metadata,segments,now,observed):
        self.observe(now,observed,self.metadata)
        if now < self.reference.begin:
            return self.oracle.guard(metadata,segments,now,observed)
        return super().current_guard(metadata,segments,now,observed)

    def select(self,metadata,receipt,now,reservations,**kwargs):
        if now >= self.reference.begin:
            return super().select(metadata,receipt,now,reservations,**kwargs)
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if metadata.get('state') != 'PENDING' or metadata['submit_seconds'] > now:
            return dict(uid=metadata['uid'],action='QUEUE',status='OBSERVED_PENDING_REQUIRED')
        start=math.ceil(max(now,receipt.reference_start_seconds,
            metadata.get('release_seconds') or -math.inf,
            metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        # The same issue prefix is common to C0 and C1. The accepted signed
        # response covers D00..24; no new prefix response is synthesized.
        return dict(uid=metadata['uid'],action='START',site=metadata['reference_site'],
            start_seconds=start,nominal_end_seconds=start+max(metadata['t50_seconds'],1e-9),
            additional_start_delay_seconds=0.,status='COMMON_PREFIX_BASIC_NO_PRESITE',
            policy_sha=self.sha,online_global_optimizer_calls=0)


class V43EventController(JobEventController):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.reservations=V43Reservations(self,capacities=self.ledger.capacities,
            wan_capacities=kwargs.get('wan_capacities'))
        self.prefix_history=[]
        self.tick_wall_times=[]

    def _observed_prefix(self,now):
        oracle=self.policy.oracle
        wanted=int((now-oracle.issue)/900)
        for slot in range(len(self.prefix_history),wanted):
            begin=oracle.issue+slot*900;end=begin+900
            gpu=np.zeros(len(oracle.sites))
            for uid,job in self.ledger.jobs.items():
                start=job.get('start_time')
                if start is None:
                    continue
                completed=job.get('completion_observed_time')
                if completed is not None and completed > now:
                    raise ValueError('FUTURE_COMPLETION_IN_PUBLIC_PREFIX')
                release=job.get('release_control_time') if completed is not None else now
                overlap=max(0.,min(end,release)-max(begin,start))
                if overlap:
                    gpu[oracle.sites.index(job['current_site'])]+=self.requests[uid].gpu*overlap/900
            obs=oracle.observations.at(begin,observed_now=now)
            power=oracle.model.recompute(gpu[None,:],oracle.sites,[obs['weather']['values']])
            self.prefix_history.append(dict(slot=slot,start_seconds=begin,end_seconds=end,
                GPU=gpu.tolist(),P=power['PCC_P_kw'][0].tolist(),Q=power['PCC_Q_kvar'][0].tolist(),observations=obs,
                authority='OBSERVED_PHYSICAL_HOLD_INTERVAL_INTEGRAL'))
        return self.prefix_history

    def admit(self,now):
        if now % 900:
            return []
        began=perf_counter()
        self.policy.oracle.observe(now,self._observed_prefix(now))
        self.policy.observe(now,self.ledger.physical(now),self.metadata)
        result=super().admit(now)
        # Each started gang must receive a new exact current guard; the next
        # candidate cannot reuse the tick's pre-admission GPU vector.
        self.policy.observe(now,self.ledger.physical(now),self.metadata)
        wall=perf_counter()-began
        self.tick_wall_times.append(dict(time_seconds=now,wall_seconds=wall,starts=len(result)))
        callback=getattr(self.policy,'on_tick',None)
        if callback:callback(now,wall,len(result))
        if wall>=900:
            raise RuntimeError('V43_CONTROLLER_EXCEEDED_900_SECOND_SLOT')
        return result


class V43Reservations(ContractReservationLedger):
    def activate(self,uid):
        super().activate(uid)
        policy=self.owner.policy
        now=policy.oracle.now
        policy.observe(now,self.owner.ledger.physical(now),self.owner.metadata)
