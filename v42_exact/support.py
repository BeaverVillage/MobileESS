"""Complete local path projections using duration masks; no complete Options.

For fixed restart R, full immutable fit is monotone in remaining duration.
Thus the largest reachable completed prefix is an exact existential w test.
Other projections use vector queries by (source,destination,remaining,c).
"""
from collections import defaultdict
from dataclasses import asdict
from time import perf_counter
import hashlib
import numpy as np
from v42_compact.graph import Graph, GraphFactory

def prune(j,b,old,cache):
    start=perf_counter();r=cache.r
    events={n:set() for n in old.events};states={n:set() for n in old.states}
    compat=defaultdict(set);transfers={};physical={};queries=0
    # Full nonmigrated paths, including post-H service.
    for k,s in old.events['y']:
        end=s+j.service_slots
        if end<=b.latest_completion and cache.fits(k,s,j.service_slots,j.gpu):
            events['y'].add((k,s));events['f0'].add((k,end))
            states['r0'].update((k,t) for t in range(s,end))
    # One sorted sweep per source. maxdone proves exact EXISTENCE, not that
    # every checkpoint is compatible with every retained w.
    candidates=defaultdict(list)
    for key in old.events['w']: candidates[key[0]].append(key)
    initial=set()
    for k,keys in candidates.items():
        cps=sorted(c for site,c in old.compatible if site==k);i=0;done=-1
        for key in sorted(keys,key=lambda x:(x[2],x[1])):
            _,d,tau=key
            while i<len(cps) and cps[i]<=tau:
                c=cps[i];done=max(done,max(c-s for s in old.compatible[k,c]));i+=1
            rem=j.service_slots-done;tr=old.transfers[key];queries+=1
            if rem>0 and tr.restart+rem<=b.latest_completion and cache.fits(d,tr.restart,rem,j.gpu):initial.add(key)
    preprocessing=perf_counter()-start;query_start=perf_counter()
    series={}
    for k,d,tau in initial:
        series.setdefault((k,d),[]).append((tau,old.transfers[k,d,tau].restart))
    arrays={key:np.array(sorted(items),dtype=np.int64) for key,items in series.items()}
    duration_tables={}
    # No s*c*d*tau records: a small vector of timestamps is queried and
    # immediately projected into sets. Cache only one bool mask per duration.
    for (k,c),ss in sorted(old.compatible.items()):
        for s in ss:
            rem=j.service_slots-(c-s);supported=False
            for (source,d),a in arrays.items():
                if source!=k:continue
                key=(k,d,rem)
                if key not in duration_tables:
                    duration_tables[key]=(a[:,1]+rem<=b.latest_completion)&cache.mask(rem,j.gpu,d)[a[:,1]]
                good=duration_tables[key]&(a[:,0]>=c);queries+=1
                matched=a[good]
                if not len(matched):continue
                supported=True
                events['w'].update((k,d,int(t)) for t in matched[:,0])
                events['f1'].update((d,int(R)+rem) for R in matched[:,1])
                states['h'].update((k,t) for t in range(c,int(matched[-1,0])))
                # Union intervals exactly, retaining holes when immutable
                # collisions split the supported post-run state envelope.
                for R in np.unique(matched[:,1]):states['r1'].update((d,t) for t in range(int(R),int(R)+rem))
            if supported:
                events['y'].add((k,s));events['q'].add((k,c));compat[k,c].add(s)
                physical[k,c,s]=old.physical[k,c,s];states['r0'].update((k,t) for t in range(s,c))
    events={n:tuple(sorted(a)) for n,a in events.items()};states={n:tuple(sorted(a)) for n,a in states.items()}
    transfers={key:old.transfers[key] for key in events['w']}
    compat={key:tuple(sorted(a)) for key,a in compat.items()}
    result=Graph(events,states,compat,physical,transfers,old.fixed)
    result.sha=hashlib.sha256(repr((events,states,compat,physical,transfers,cache.identity)).encode()).hexdigest()
    audit=dict(before=old.counts(),after=result.counts(),candidate_w=len(old.events['w']),retained_w=len(events['w']),
        preprocessing_seconds=preprocessing,query_seconds=perf_counter()-query_start,query_count=queries,
        support_array_bytes=sum(a.nbytes for a in arrays.values())+sum(a.nbytes for a in duration_tables.values()),
        complete_options_materialized=0,initial_exact_w=len(initial),complete_path_projection=True)
    return result,audit

class ExactFactory:
    def __init__(self,r,max_slot):self.original=GraphFactory(r,max_slot);self.templates={};self.audits={};self.hits=0
    def graph(self,j,b):
        old=self.original.graph(j,b);key=repr(([(k,v) for k,v in asdict(j).items() if k!='uid'],asdict(b)))
        if key in self.templates:self.hits+=1;return self.templates[key]
        current,audit=prune(j,b,old,self.original.cache)
        # Pruning removes exactly components absent from ALL complete paths;
        # applying that operator a second time must be an identical fixed point.
        again,second=prune(j,b,current,self.original.cache)
        if again.sha!=current.sha:raise ValueError('SUPPORT_FIXED_POINT_NOT_IDEMPOTENT')
        audit.update(fixed_point=True,passes=2,second_pass_removed=0,second_pass_seconds=second['preprocessing_seconds']+second['query_seconds'])
        self.templates[key]=current;self.audits[key]=audit
        return current
