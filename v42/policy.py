"""Solver-free individual arrival/checkpoint execution.

This module deliberately has no optimizer dependency. It receives one observed
event at a time; it cannot open an Actual trace or inspect later arrivals.
"""
from dataclasses import dataclass, replace
from collections import Counter
from .contracts import require
from .semantic_adapter import NumericSemanticFeatures


@dataclass(frozen=True)
class Arrival:
    uid: str
    slot: int
    gpu: int
    safe_slots: int
    request_slots: int
    qos: str
    partition: str
    workload_class: str
    max_delay: int
    runtime_authority_sha256: str
    planning_only: bool = False
    semantic_features: NumericSemanticFeatures | None = None

    def validate(self):
        require(self.gpu>0 and self.safe_slots>0 and self.request_slots>0, 'ARRIVAL_SERVICE')
        require(self.max_delay>=0 and (self.qos=='standby' or self.max_delay==0), 'R0_UNKNOWN_DELAY')
        require(self.max_delay<=max(0,self.request_slots-self.safe_slots), 'REQUEST_SLACK_EXCEEDED')
        require(len(self.runtime_authority_sha256)==64, 'SAFE_RUNTIME_UNBOUND')
        require(self.semantic_features is None or isinstance(self.semantic_features,NumericSemanticFeatures),
                'RAW_SEMANTICS_FORBIDDEN_AT_POLICY_BOUNDARY')


@dataclass(frozen=True)
class Action:
    site: str
    delay: int = 0
    migrate: bool = False


def policy_key(event, job, critical):
    require(event in ('ARRIVAL','CHECKPOINT'), 'EVENT_TYPE')
    return (event, 'small' if job.gpu<=4 else 'large',
            'short' if job.request_slots<=16 else 'long',
            'standby' if job.qos=='standby' else 'other', bool(critical))


@dataclass(frozen=True)
class Policy:
    # Keys have no scenario, UID, future arrival, or realized runtime field.
    table: dict

    def actions(self, event, job, critical):
        key=policy_key(event,job,critical)
        require(key in self.table and len(self.table[key])>0, 'UNREGISTERED_POLICY_STATE')
        return self.table[key]


class Ledger:
    def __init__(self, site_capacities, rack_capacities, wan):
        self.sites=dict(site_capacities)
        self.racks=dict(rack_capacities)  # (site,rack): GPUs
        require(all(v>0 for v in self.sites.values()) and all(v>0 for v in self.racks.values()), 'CAPACITY_AUTHORITY')
        self.wan=wan
        self.gpu=Counter();self.rack_gpu=Counter();self.bytes=Counter()

    def available_rack(self, site, gpu, start, end):
        if site not in self.sites or start>=end:
            return None
        for (s,rack),cap in sorted(self.racks.items()):
            if s==site and all(self.gpu[s,t]+gpu<=self.sites[s] and
                              self.rack_gpu[s,rack,t]+gpu<=cap for t in range(start,end)):
                return rack
        return None

    def reserve(self, site, rack, gpu, start, end, sign=1):
        for t in range(start,end):
            self.gpu[site,t]+=sign*gpu
            self.rack_gpu[site,rack,t]+=sign*gpu
            require(0<=self.gpu[site,t]<=self.sites[site] and
                    0<=self.rack_gpu[site,rack,t]<=self.racks[site,rack], 'CAPACITY_VIOLATION')


class Executor:
    ACTUAL_AIDC_GUROBI_CALLS = 0

    def __init__(self, policy, ledger, planning=False):
        self.policy,self.ledger,self.planning=policy,ledger,planning
        self.jobs={};self.log=[];self.last_slot=-10**12

    def _event(self, slot):
        require(slot>=self.last_slot, 'NONCAUSAL_EVENT_ORDER')
        self.last_slot=slot

    def arrival(self, observed, critical):
        observed.validate()
        require(self.planning or not observed.planning_only, 'PSEUDO_JOB_IN_ACTUAL')
        require(observed.uid not in self.jobs, 'DUPLICATE_REALIZED_JOB')
        self._event(observed.slot)
        for rank,action in enumerate(self.policy.actions('ARRIVAL',observed,critical)):
            if action.migrate or not 0<=action.delay<=observed.max_delay:
                continue
            start=observed.slot+action.delay
            end=start+observed.safe_slots
            rack=self.ledger.available_rack(action.site,observed.gpu,start,end)
            if rack is None:
                continue
            self.ledger.reserve(action.site,rack,observed.gpu,start,end)
            self.jobs[observed.uid]=dict(observed=observed,site=action.site,rack=rack,
                start=start,end=end,migrated=False,segments=[(action.site,start,end)],completed=False)
            self.log.append(dict(event='ARRIVAL',uid=observed.uid,slot=observed.slot,
                                 action=action, fallback_rank=rank,key=policy_key('ARRIVAL',observed,critical)))
            return self.jobs[observed.uid]
        raise ValueError('NO_FEASIBLE_ARRIVAL_ACTION:'+observed.uid)

    def checkpoint(self, uid, slot, critical):
        self._event(slot)
        current=self.jobs[uid];job=current['observed']
        require(not current['completed'] and current['start']<slot<current['end'], 'CHECKPOINT_OUTSIDE_SERVICE')
        require((slot-current['start'])%2==0, 'NOT_A_VALID_CHECKPOINT')
        # At most one migration. A later checkpoint cannot undo the first one.
        if current['migrated']:
            return current
        for rank,action in enumerate(self.policy.actions('CHECKPOINT',job,critical)):
            if not action.migrate:
                self.log.append(dict(event='CHECKPOINT',uid=uid,slot=slot,action=action,fallback_rank=rank,
                                     key=policy_key('CHECKPOINT',job,critical)))
                return current
            if action.site==current['site'] or action.delay!=0:
                continue
            path=tuple(self.ledger.wan.path(current['site'],action.site))
            require(path, 'MISSING_WAN_PATH')
            remaining=self.ledger.wan.payload_bytes(job.gpu)
            te=slot;usage=[]
            while remaining>0 and te<95:
                n=min(remaining,*(self.ledger.wan.capacity_bytes(link,te)-self.ledger.bytes[link,te] for link in path))
                require(n>=0,'WAN_OVERBOOKED')
                usage.extend((link,te,n) for link in path if n)
                remaining-=n;te+=1
            if remaining>0 or te+1>=96:
                continue
            restart=te+1
            end=restart+(current['end']-slot)
            rack=self.ledger.available_rack(action.site,job.gpu,restart,end)
            if rack is None:
                continue
            self.ledger.reserve(current['site'],current['rack'],job.gpu,slot,current['end'],sign=-1)
            self.ledger.reserve(action.site,rack,job.gpu,restart,end)
            for link,t,n in usage:
                self.ledger.bytes[link,t]+=n
            current.update(site=action.site,rack=rack,end=end,migrated=True,
                           segments=[(current['site'],current['start'],slot),(action.site,restart,end)])
            require(sum(b-a for _,a,b in current['segments'])==job.safe_slots,'SERVICE_MASS')
            self.log.append(dict(event='CHECKPOINT',uid=uid,slot=slot,action=action,fallback_rank=rank,
                                 key=policy_key('CHECKPOINT',job,critical)))
            return current
        raise ValueError('NO_FEASIBLE_CHECKPOINT_ACTION:'+uid)

    def complete(self, uid, slot, observed_processed_slots):
        """Completion enters only when observed; cannot be used at arrival."""
        self._event(slot)
        current=self.jobs[uid]
        require(not current['completed'], 'DUPLICATE_COMPLETION')
        processed=sum(max(0,min(slot,b)-a) for _,a,b in current['segments'] if slot>a)
        require(processed==observed_processed_slots and 0<processed<=current['observed'].safe_slots,
                'REALIZED_SERVICE_OR_SAFE_RUNTIME_VIOLATION')
        # A reservation overrun is a failure, never silently dropped service.
        require(slot<=current['end'], 'SAFE_RUNTIME_OVERRUN')
        for site,a,b in current['segments']:
            if b>slot:
                require(site==current['site'], 'COMPLETION_DURING_TRANSFER')
                self.ledger.reserve(site,current['rack'],current['observed'].gpu,max(a,slot),b,sign=-1)
        current['completed']=True
        self.log.append(dict(event='COMPLETE',uid=uid,slot=slot,processed=processed))

    def metrics(self):
        events=[r for r in self.log if 'fallback_rank' in r]
        arrivals=[r for r in events if r['event']=='ARRIVAL']
        return dict(unknown_jobs_handled=len(arrivals),policy_events=len(events),
                    policy_fallback_rate=sum(r['fallback_rank']>0 for r in events)/len(events) if events else None,
                    ACTUAL_AIDC_GUROBI_CALLS=0,
                    completed_jobs=sum(r['completed'] for r in self.jobs.values()),
                    outstanding_jobs=sum(not r['completed'] for r in self.jobs.values()))
