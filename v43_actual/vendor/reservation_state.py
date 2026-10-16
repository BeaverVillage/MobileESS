"""Hard observed/committed occupancy versus anonymous and nominal forecasts.

Running truth is extended at every observed event/control before admission.
Its unknown future duration remains a forecast, never authority to evict a gang.
Known plans and other committed Unknown commands remain hard future bookings.
"""
from copy import deepcopy
from types import SimpleNamespace
from .policy import ReservationLedger


def union_job_segments(segments):
    """Same UID/resource holds use their maximum, not duplicate occupation."""
    out=[]
    for resource in sorted({s['resource'] for s in segments}):
        rows=[s for s in segments if s['resource']==resource]
        points=sorted({v for s in rows for v in (s['begin'],s['end'])})
        for a,b in zip(points,points[1:]):
            active=[s for s in rows if s['begin']<b and s['end']>a]
            if not active:continue
            quantity=max(s['quantity'] for s in active)
            if out and out[-1]['resource']==resource and out[-1]['end']==a and out[-1]['quantity']==quantity:
                out[-1]['end']=b
            else:out.append(dict(resource=resource,begin=a,end=b,quantity=quantity,scope='physical'))
    return out


class ContractReservationLedger(ReservationLedger):
    def __init__(self,owner,**kwargs):
        super().__init__(**kwargs);self.owner=owner
        self.known_plans={};self.nominal_running_forecasts={};self.role_audit=[]
        for uid,command in owner.known_schedule.items():
            segments=command.get('protected_segments')
            if segments:self.known_plans[uid]=deepcopy(segments)

    def install_known(self,uid,segments):
        if uid in self.known_plans:return
        self.known_plans[uid]=deepcopy(segments)

    def _fits(self,segments,*,exclude=None,envelope=None,scope='physical'):
        with self._lock:
            rows={}
            for uid in list(self.reservations)+[u for u in self.known_plans if u not in self.reservations]:
                if uid==exclude:continue
                booking=self.reservations.get(uid,{})
                active=[] if booking.get('status')=='RELEASED' else booking.get('segments',[])
                merged=union_job_segments(active+self.known_plans.get(uid,[]))
                if merged:rows[uid]=dict(status='ACTIVE',segments=merged)
            reason=ReservationLedger._fits(SimpleNamespace(capacities=self.capacities,reservations=rows),
                segments,exclude=None,envelope=envelope,scope=scope)
            self.last_conflict=None
            if reason=='NO_CAPACITY':
                for incoming in segments:
                    resource=incoming['resource'];peers=[dict(s,uid=u,role='KNOWN_FROZEN' if u in self.known_plans else self.reservations[u].get('role','COMMITTED'))
                        for u,r in rows.items() for s in r['segments'] if s['resource']==resource]
                    points=sorted({incoming['begin'],incoming['end']}|{v for s in peers
                        if s['end']>incoming['begin'] and s['begin']<incoming['end']
                        for v in (max(incoming['begin'],s['begin']),min(incoming['end'],s['end']))})
                    for a,b in zip(points,points[1:]):
                        occupied=[s for s in peers if s['begin']<b and s['end']>a]
                        offered=sum(s['quantity'] for s in segments if s['resource']==resource and s['begin']<b and s['end']>a)
                        if offered+sum(s['quantity'] for s in occupied)>self.capacities[resource]+1e-9:
                            self.last_conflict=dict(resource=resource,begin=a,end=b,capacity=self.capacities[resource],
                                candidate_quantity=offered,conflicting_UIDs_roles_intervals=occupied)
                            break
                    if self.last_conflict:break
            return reason

    def reserve(self,uid,segments,**kwargs):
        with self._lock:
            ok,reason=super().reserve(uid,segments,**kwargs)
            if ok:
                self.reservations[uid]['role']='KNOWN_FROZEN' if uid in self.owner.known_schedule else 'UNKNOWN_COMMITTED'
                self.role_audit.append(dict(uid=uid,event='ATOMIC_COMMIT_OR_REBIND',role=self.reservations[uid]['role'],
                    replaced=kwargs.get('replace',False),other_committed_reservations_displaced=False))
            return ok,reason

    def retain_running(self,uid,site,now,next_control,gpu):
        with self._lock:
            if uid in self.known_plans and self.owner.known_schedule[uid]['site']!=site and not self.owner.metadata[uid].get('migration_count'):
                self.known_plans.pop(uid)
                self.role_audit.append(dict(uid=uid,event='KNOWN_SOURCE_EXECUTION_DEVIATION',at_seconds=now,
                    reason='OBSERVED_RUNNING_SOURCE_DIFFERS_FROM_FROZEN_PLAN',frozen_schedule_modified=False))
            old=self.reservations.get(uid,{})
            if uid not in self.nominal_running_forecasts:
                if old.get('segments'):self.nominal_running_forecasts[uid]=deepcopy(old['segments'])
                else:
                    remaining=max(0.,self.owner.requests[uid].q50-self.owner.metadata[uid].get('accumulated_compute_seconds',0))
                    self.nominal_running_forecasts[uid]=[dict(resource='gpu:'+site,begin=now,end=now+remaining,quantity=gpu,
                        role='PUBLIC_Q50_PREDICTION_ONLY_NOT_HARD_OCCUPATION')] if remaining>0 else []
            # Only currently observed occupancy is hard for a running Unknown.
            # The EpisodeLedger retains it again before every later admission.
            segments=[s for s in old.get('segments',[]) if not s['resource'].startswith('gpu:') and s['end']>now]
            segments.append(dict(resource='gpu:'+site,begin=now,end=next_control,quantity=gpu,scope='physical'))
            self.reservations[uid]=dict(uid=uid,status='ACTIVE',scope='physical',role='RUNNING_OBSERVED',segments=segments)

    def release(self,uid,now):
        with self._lock:
            super().release(uid,now)
            if self.owner.metadata.get(uid,{}).get('state')=='COMPLETED':
                self.known_plans.pop(uid,None)

    def snapshot(self):
        result=super().snapshot()
        result.update(known_frozen_hard_reservations=deepcopy(self.known_plans),
            nominal_running_soft_forecasts=deepcopy(self.nominal_running_forecasts),role_audit=deepcopy(self.role_audit),
            anonymous_Q50_physical_reservations=0,unselected_Unknown_hard_reservations=0)
        return result
