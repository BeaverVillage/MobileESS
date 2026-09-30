"""Canonical coefficients used by insertion, pricing costs and audits."""
from dataclasses import dataclass, asdict
from bisect import bisect_left
from collections import defaultdict
import hashlib, json
from v42_job_capability import validate
from v42_compact.native import completion_risk
from v42_final.reserve import risk_exposure

METRICS = ('migration_count', 'shift_slots', 'prestart_changes', 'deterministic_tie')
FAMILIES = ('y', 'q', 'w', 'f0', 'f1')

class ColumnFactory:
    def __init__(self, jobs, bounds, resources, graphs, bundle=None, raw=None):
        self.jobs, self.bounds, self.r, self.graphs = jobs, bounds, resources, graphs
        self.bundle, self.raw = bundle, raw
        from v42_boundary.generator import Generator
        self.fit_cache = Generator(resources,max(b.latest_completion for b in bounds.values()))
        self.offsets = {}; self.local_offsets = {}; rank = 0
        for uid, g in sorted(graphs.items()):
            self.offsets[uid] = rank; local = {}; n = 0
            for family in FAMILIES:
                local[family] = n; n += len(g.events[family])
            self.local_offsets[uid] = local
            if not g.fixed: rank += n

    def rank(self, uid, family, key):
        keys = self.graphs[uid].events[family]
        i = bisect_left(keys, key)
        if i == len(keys) or keys[i] != key: raise ValueError('EVENT_NOT_IN_PR99_GRAPH')
        return self.offsets[uid]+self.local_offsets[uid][family]+i+1

    def risk(self, uid, site, end):
        j = self.jobs[uid]
        if self.bundle is not None:
            return completion_risk(j, self.raw[uid], site, end, self.bundle)
        return risk_exposure(j.gpu, end, site, [1., .5, .25], range(120))

    def make(self, uid, option):
        j = self.jobs[uid]; validate(j, option, self.bounds[uid], self.r)
        g=self.graphs[uid]
        if (option.initial_site,option.start) not in g.events['y']:raise ValueError('START_NOT_IN_AUTHORIZED_GRAPH')
        if option.migrated:
            key=option.initial_site,option.checkpoint,option.start
            if g.physical.get(key)!=option.physical_checkpoint_seconds:raise ValueError('CHECKPOINT_NOT_IN_GRAPH')
            tr=g.transfers.get((option.initial_site,option.destination,option.transfer_start))
            if tr is None or (tr.end,tr.restart,tr.wan)!=(option.transfer_end,option.restart_end,option.wan):raise ValueError('DETERMINISTIC_WAN_TEMPLATE_MISMATCH')
        gpu = {(k,t):j.gpu for k,a,b in option.segments for t in range(a,b)}
        wan = {(l,t):n for l,t,n in option.wan}
        active = {t:1. for t in range(option.transfer_start, option.transfer_end)} if option.migrated else {}
        site, _, end = option.segments[-1]
        tie = 0
        if not self.graphs[uid].fixed:
            tie = self.rank(uid,'y',(option.initial_site,option.start))
            if option.migrated:
                tie += self.rank(uid,'q',(option.initial_site,option.checkpoint))
                tie += self.rank(uid,'w',(option.initial_site,option.destination,option.transfer_start))
                tie += self.rank(uid,'f1',(site,end))
            else: tie += self.rank(uid,'f0',(site,end))
        metrics = dict(zip(METRICS,(int(option.migrated),option.start-j.reference_start,int(option.initial_site!=j.reference_site),tie)))
        signature = hashlib.sha256(json.dumps([uid,asdict(option)],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return PhysicalColumn(uid, option, gpu, wan, active, self.risk(uid,site,end), metrics, signature)

@dataclass(frozen=True)
class PhysicalColumn:
    job_id: str
    option: object
    gpu: dict
    wan: dict
    active: dict
    risk: dict
    metrics: dict
    signature: str

    def master_coefficients(self):
        out = {('CONVEXITY',self.job_id):1.}
        out.update({('GPU',k,t):-n for (k,t),n in self.gpu.items()})
        out.update({('RISK',k,t):-n for (k,t),n in self.risk.items() if n})
        out.update({('WAN',l,t):n for (l,t),n in self.wan.items()})
        out.update({('ACTIVE',t):n for t,n in self.active.items()})
        out.update({('METRIC',key):-n for key,n in self.metrics.items() if n})
        # Objective/lock expressions are on the balanced metric variables.
        # Thus no direct coefficient in a lock; its value enters METRIC duals.
        return out

    def reduced_cost(self, dual, objective=0.):
        return objective-sum(dual.get(key,0.)*n for key,n in self.master_coefficients().items())

    def record(self):
        o=self.option; site,_,end=o.segments[-1]
        return dict(job_id=self.job_id,start_slot=o.start,initial_site=o.initial_site,migrated=o.migrated,
            checkpoint=o.checkpoint,physical_checkpoint_seconds=o.physical_checkpoint_seconds,destination=o.destination,
            transfer_start=o.transfer_start,transfer_end=o.transfer_end,restart_end=o.restart_end,
            final_site=site,completion_slot=end,segments=o.segments,
            GPU=[(k,t,n) for (k,t),n in sorted(self.gpu.items())],WAN=[(l,t,n) for (l,t),n in sorted(self.wan.items())],
            ACTIVE=sorted(self.active.items()),RISK=[(k,t,n) for (k,t),n in sorted(self.risk.items())],
            intervention_coefficients=self.metrics,canonical_signature=self.signature)

class PricingCosts:
    """Factor the *same* registry into START, RUN, WAN, FINISH arc costs.

    No independently maintained coupling signs: probe canonical one-entry
    columns to obtain each row's coefficient and evaluate c - pi A.
    """
    def __init__(self, factory, uid, dual):
        self.factory, self.uid, self.dual = factory,uid,dual
        self.j=factory.jobs[uid]; self.prefix={}; self.terminal_cache={}
        self.metric={n:self.profile(metrics={n:1.}) for n in METRICS}
        self.convexity=self.profile(convexity=True)
        tail=factory.bounds[uid].latest_completion
        for k in factory.r.capacities:
            values=[0.]
            for t in range(tail): values.append(values[-1]+self.profile(gpu={(k,t):self.j.gpu}))
            self.prefix[k]=values

    def profile(self,gpu=None,wan=None,active=None,risk=None,metrics=None,convexity=False):
        c=PhysicalColumn(self.uid,None,gpu or {},wan or {},active or {},risk or {},metrics or {},'')
        co=c.master_coefficients()
        if not convexity: co.pop(('CONVEXITY',self.uid))
        return -sum(self.dual.get(key,0.)*v for key,v in co.items())

    def run(self,k,a,b): return self.prefix[k][b]-self.prefix[k][a]

    def start(self,k,s):
        return self.metric['shift_slots']*(s-self.j.reference_start)+self.metric['prestart_changes']*(k!=self.j.reference_site)+self.tie('y',(k,s))

    def tie(self,family,key):
        if not self.metric['deterministic_tie'] or self.factory.graphs[self.uid].fixed:return 0.
        return self.metric['deterministic_tie']*self.factory.rank(self.uid,family,key)

    def terminal(self,k,end):
        key=k,end
        if key not in self.terminal_cache:
            self.terminal_cache[key]=self.profile(risk=self.factory.risk(self.uid,k,end))
        return self.terminal_cache[key]

    def transfer(self,k,d,tau,tr):
        return self.profile(wan={(l,t):n for l,t,n in tr.wan},active={t:1. for t in range(tau,tr.end)})+self.tie('w',(k,d,tau))
