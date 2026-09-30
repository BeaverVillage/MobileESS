"""Exact DAG label DP. Merge only prefixes with identical future decisions.

At time tau, label (source, work_done) stores the cheapest checkpoint prefix
ready at/before tau. Future WAN/restart, remaining service, completion risk
depend only on source, work_done, tau, destination. WAIT is zero occupancy.
"""
from collections import defaultdict
from time import perf_counter
from v42_job_capability import Option
from .column import PricingCosts
from .common import require

def price(factory,uid,dual,check=lambda:None):
    started=perf_counter();j=factory.jobs[uid];b=factory.bounds[uid];g=factory.graphs[uid]
    require(not g.fixed,'PRICE_CONSTANT_JOB')
    cost=PricingCosts(factory,uid,dual);best=None;choice=None
    nodes=1;arcs=0;wan_arcs=0;migration_arcs=0
    def offer(value,key):
        nonlocal best,choice
        # Exact numeric minimization; tie by ordered physical decision tuple.
        if best is None or (value,key)<(best,choice):best,choice=value,key
    cache=factory.fit_cache
    for k,s in g.events['y']:
        end=s+j.service_slots;arcs+=1;nodes+=1
        if end<=b.latest_completion and cache.fits(k,s,j.service_slots,j.gpu):
            offer(cost.start(k,s)+cost.run(k,s,end)+cost.terminal(k,end)+cost.tie('f0',(k,end)),(0,k,s))
    arrivals=defaultdict(list)
    for (k,c),starts in sorted(g.compatible.items()):
        for s in starts:
            u=c-s
            val=cost.start(k,s)+cost.run(k,s,c)+cost.metric['migration_count']+cost.tie('q',(k,c))
            arrivals[c].append((k,u,val,s,c));arcs+=1;nodes+=1
    transfers=defaultdict(list)
    for wk,tr in g.transfers.items():transfers[wk[2]].append((wk,tr))
    labels=defaultdict(dict)
    for tau in range(factory.r.control_end):
        check()
        for k,u,val,s,c in arrivals.get(tau,()):
            previous=labels[k].get(u)
            label=(val,s,c)
            if previous is None or label<previous:labels[k][u]=label
        nodes+=sum(map(len,labels.values()))
        arcs+=sum(map(len,labels.values())) # WAIT propagation
        for (k,d,_),tr in transfers.get(tau,()):
            wan_arcs+=1;trcost=cost.transfer(k,d,tau,tr)
            for u,(val,s,c) in sorted(labels[k].items()):
                end=tr.restart+j.service_slots-u;migration_arcs+=1;arcs+=1
                if end>b.latest_completion or not cache.fits(d,tr.restart,j.service_slots-u,j.gpu):continue
                value=val+trcost+cost.run(d,tr.restart,end)+cost.terminal(d,end)+cost.tie('f1',(d,end))
                offer(value,(1,k,s,c,d,tau))
    require(choice is not None,'EMPTY_LOCAL_PHYSICAL_SET:'+uid)
    if choice[0]==0:
        _,k,s=choice;o=Option(s,k,((k,s,s+j.service_slots),))
    else:
        _,k,s,c,d,tau=choice;tr=g.transfers[k,d,tau]
        o=Option(s,k,((k,s,c),(d,tr.restart,tr.restart+j.service_slots-(c-s))),c,g.physical[k,c,s],d,tau,tr.end,tr.restart,tr.wan)
    column=factory.make(uid,o);rc=column.reduced_cost(dual)
    require(abs(rc-(best+cost.convexity))<=1e-7*max(1.,abs(rc)),'DP_REGISTRY_COST_MISMATCH')
    return column,rc,dict(job_id=uid,seconds=perf_counter()-started,nodes=nodes,arcs=arcs,
        migration_transitions=migration_arcs,WAN_transitions=wan_arcs,minimum_reduced_cost=rc)

def initial_columns(factory,check=lambda:None):
    movable={};fixed={};audit=[]
    for uid,j in sorted(factory.jobs.items()):
        check();g=factory.graphs[uid]
        if g.fixed:c=factory.make(uid,g.fixed);fixed[uid]=c;method='PR99_TRUE_SINGLETON'
        else:
            try:
                c=factory.make(uid,Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),)))
                method='REFERENCE_STAY'
            except ValueError:
                c,_,_=price(factory,uid,{},check);method='EXACT_ZERO_DUAL_FALLBACK'
            movable[uid]=c
        audit.append(dict(job_id=uid,method=method,columns=0 if g.fixed else 1,signature=c.signature))
    return movable,fixed,audit

class PricingSweep:
    """Exact template reuse within ONE immutable-dual sweep.

    A convexity dual is a trajectory-independent constant. Two jobs sharing
    the PR99 graph and frozen completion-risk offset have identical path
    costs except for that constant. Tie offsets are included when nonzero.
    No cache is shared across dual snapshots or objective levels.
    """
    def __init__(self,factory,dual):
        from types import MappingProxyType
        self.factory=factory;self.dual=MappingProxyType(dict(dual));self.cache={}

    def price(self,uid,check=lambda:None):
        from dataclasses import asdict
        f=self.factory;g=f.graphs[uid]
        offset=(f.raw[uid]['risk_nominal_completion_issue_slot']-f.raw[uid]['reference_end']) if f.bundle else None
        tie=f.offsets[uid] if self.dual.get(('METRIC','deterministic_tie'),0.) else 0
        physical_job=tuple((k,repr(v)) for k,v in asdict(f.jobs[uid]).items() if k!='uid')
        key=(g.sha,physical_job,offset,tie)
        if key not in self.cache:
            c,rc,p=price(f,uid,self.dual,check);self.cache[key]=(c.option,p)
            p=dict(p,template_cache_hit=False)
            return c,rc,p
        check();started=perf_counter();o,original=self.cache[key];c=f.make(uid,o);rc=c.reduced_cost(self.dual)
        p=dict(original,job_id=uid,seconds=perf_counter()-started,minimum_reduced_cost=rc,template_cache_hit=True)
        return c,rc,p

def structure_counts(graph,control_end):
    """Complete implicit-DAG work counts, independent of duals or trajectory scan."""
    arrivals=defaultdict(list);wan=defaultdict(lambda:defaultdict(int));labels=defaultdict(set)
    prefixes=0
    for (k,c),starts in graph.compatible.items():
        for s in starts:arrivals[c].append((k,c-s));prefixes+=1
    for k,d,tau in graph.transfers:wan[tau][k]+=1
    waits=0;migration=0
    for tau in range(control_end):
        for k,u in arrivals.get(tau,()):labels[k].add(u)
        waits+=sum(map(len,labels.values()))
        migration+=sum(n*len(labels[k]) for k,n in wan.get(tau,{}).items())
    return dict(nodes=1+len(graph.events['y'])+prefixes+waits,
        arcs=len(graph.events['y'])+prefixes+waits+migration,WAN_transitions=len(graph.transfers),migration_transitions=migration)
