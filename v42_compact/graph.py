"""Sparse event sets without checkpoint x destination x transfer-start products."""
from dataclasses import dataclass,asdict
from collections import defaultdict,Counter
import hashlib,json
from v42_boundary.generator import Generator,checkpoints
from v42_job_capability import Option,validate
from .common import require

@dataclass
class Graph:
    events:dict
    states:dict
    compatible:dict
    physical:dict
    transfers:dict
    fixed:object=None
    sha:str=''
    def counts(self):return {n:len(v) for n,v in {**self.events,**self.states}.items()}

class GraphFactory:
    def __init__(self,resources,max_slot):
        self.cache=Generator(resources,max_slot);self.templates={};self.hits=0
    def graph(self,j,b):
        b.require();r=self.cache.r;g=self.cache
        key=repr(([(k,v) for k,v in asdict(j).items() if k!='uid'],asdict(b)))
        if key in self.templates:self.hits+=1;return self.templates[key]
        initial,dests=g.static_sites(j);starts=sorted(set(b.allowed_starts))
        if j.state!='PENDING' or j.protected or j.qos in ('high','urgent') or j.unknown_arrival:starts=[j.reference_start]
        starts=[s for s in starts if s>=max(j.submit,j.event,j.reference_start) and s<b.latest_completion]
        y=[(k,s) for k in initial for s in starts];compat=defaultdict(list);physical={}
        if j.checkpoint_authorized and not j.unknown_arrival and not j.migrations_used:
            for k,s in y:
                for c,p in checkpoints(j,s,min(s+j.service_slots,r.control_end)):
                    if j.service_slots-(c-s)>0 and g.fits(k,s,c-s,j.gpu):
                        compat[k,c].append(s);physical[k,c,s]=p
        # Prefix maximum completed work proves a necessary remaining-work bound
        # for each WAN event; no checkpoint/transfer pairs are materialized.
        w=[];transfers={}
        for k in initial:
            qs=sorted(c for site,c in compat if site==k)
            if not qs:continue
            idx=0;maxdone=-1
            for tau in range(min(qs),r.control_end):
                while idx<len(qs) and qs[idx]<=tau:
                    c=qs[idx];maxdone=max(maxdone,max(c-s for s in compat[k,c]));idx+=1
                remaining=j.service_slots-maxdone
                for d in dests:
                    if d==k:continue
                    transfer=g.transfer(k,d,j.gpu,tau)
                    if transfer.feasible and transfer.restart+remaining<=b.latest_completion and g.fits(d,transfer.restart,1,j.gpu):
                        wk=(k,d,tau);w.append(wk);transfers[wk]=transfer
        # Remove checkpoints with no later source transfer at all (hard reachability).
        last={k:max((t for a,d,t in w if a==k),default=-1) for k in initial}
        compat={kc:tuple(sorted(ss)) for kc,ss in compat.items() if kc[1]<=last[kc[0]]}
        f0=sorted({(k,s+j.service_slots) for k,s in y if s+j.service_slots<=b.latest_completion})
        f1=[];r0=[];h=[];r1=[]
        for k in initial:
            ends=[t for site,t in f0 if site==k]+[c for site,c in compat if site==k]
            if ends:r0.extend((k,t) for t in range(min(starts),max(ends)))
            cs=[c for site,c in compat if site==k]
            if cs:h.extend((k,t) for t in range(min(cs),last[k]))
        for d in dests:
            entries=[q.restart for (k,site,t),q in transfers.items() if site==d]
            if not entries:continue
            lo=min(entries);hi=min(b.latest_completion,max(entries)+j.service_slots)
            f1.extend((d,t) for t in range(lo+1,hi+1));r1.extend((d,t) for t in range(lo,hi))
        events=dict(y=tuple(sorted(y)),q=tuple(sorted(compat)),w=tuple(sorted(w)),f0=tuple(f0),f1=tuple(f1))
        states=dict(r0=tuple(r0),h=tuple(h),r1=tuple(r1));fixed=None
        if len(y)==1 and not compat and not w:
            k,s=y[0];candidate=Option(s,k,((k,s,s+j.service_slots),))
            try:validate(j,candidate,b,r);fixed=candidate
            except ValueError:pass
        graph=Graph(events,states,compat,physical,transfers,fixed)
        graph.sha=hashlib.sha256(repr((events,states,compat,physical,transfers,g.identity)).encode()).hexdigest()
        self.templates[key]=graph;return graph

def old_to_compact(o):
    out={n:{} for n in ('y','q','w','f0','f1','r0','h','r1')}
    out['y'][o.initial_site,o.start]=1
    for i,(k,a,b) in enumerate(o.segments):
        for t in range(a,b):out['r'+str(i)][k,t]=1
    if o.migrated:
        out['q'][o.initial_site,o.checkpoint]=1;out['w'][o.initial_site,o.destination,o.transfer_start]=1
        for t in range(o.checkpoint,o.transfer_start):out['h'][o.initial_site,t]=1
        out['f1'][o.destination,o.segments[-1][2]]=1
    else:out['f0'][o.initial_site,o.segments[-1][2]]=1
    return out

def reconstruct(j,b,r,graph,assignment):
    if graph.fixed:return graph.fixed
    def chosen(name):return [key for key,x in assignment[name].items() if x>.5]
    ys=chosen('y');qs=chosen('q');ws=chosen('w');f0=chosen('f0');f1=chosen('f1')
    require(len(ys)==1 and len(qs)==len(ws)==len(f1)<=1 and len(f0)+len(qs)==1,'EVENT_CARDINALITY')
    k,s=ys[0]
    if not qs:
        site,end=f0[0];require(site==k,'FINISH_SITE');o=Option(s,k,((k,s,end),))
    else:
        source,c=qs[0];a,d,tau=ws[0];site,end=f1[0]
        require(source==a==k and site==d and s in graph.compatible[k,c] and tau>=c,'STATE_PATH')
        tr=graph.transfers[a,d,tau]
        o=Option(s,k,((k,s,c),(d,tr.restart,end)),c,graph.physical[k,c,s],d,tau,tr.end,tr.restart,tr.wan)
    validate(j,o,b,r)
    expected=old_to_compact(o)
    for n,keys in {**graph.events,**graph.states}.items():
        require(all(abs(assignment[n].get(key,0)-expected[n].get(key,0))<1e-5 for key in set(keys)|set(expected[n])),'NONPHYSICAL_STATE:'+n)
    return o
