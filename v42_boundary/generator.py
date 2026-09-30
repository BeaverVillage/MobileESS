"""Exact physical domains with cached interval masks and lazy Option objects.

Full STAY failure never prunes a migration that escapes a later collision.
All caches belong to one immutable Resources snapshot.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
from math import ceil,floor
from time import perf_counter
import hashlib,json
import numpy as np
from v42_job_capability import Option
from .common import require

@dataclass(frozen=True)
class Transfer:
    end:int
    restart:int
    wan:tuple
    feasible:bool
    reason:str=''

def checkpoints(job,start,end):
    if job.state=='RUNNING':
        if job.elapsed_seconds is None:return ()
        elapsed,origin=job.elapsed_seconds,job.event
    else:elapsed,origin=0.,start
    scan=job.event-1;at_scan=elapsed+(scan-origin)*900
    k0=max(1,floor(at_scan/1800)+1)
    # Same physical expression and ceiling as legacy, evaluated arithmetically.
    limit=ceil((end*900-(scan*900-at_scan))/1800)+1
    values=[]
    for k in range(k0,limit):
        physical=scan*900+k*1800-at_scan;control=ceil(physical/900)
        if control>=end:break
        if control>=max(job.event,start):values.append((control,physical))
    return tuple(values)

class Domain:
    def __init__(self,stays,blocks,cache,duration):
        self.stays=tuple(stays);self.blocks=tuple(blocks);self.cache=cache;self.duration=duration
        self.count=len(self.stays)+sum(len(b[-1]) for b in self.blocks)
        self.sha=hashlib.sha256(json.dumps([cache.identity,duration,self.stays,self.blocks],separators=(',',':')).encode()).hexdigest()
    def __len__(self):return self.count
    def __iter__(self):
        # Exact legacy Option ordering: s,source,source-segment end, then
        # destination/restart. Unmigrated source segment ends last.
        groups=defaultdict(list)
        for b in self.blocks:groups[b[0],b[1]].append(b)
        keys=sorted(set(groups)|set(self.stays))
        for s,site in keys:
            for _,_,cp,physical,dest,g,starts in sorted(groups[s,site],key=lambda b:(b[2],b[4])):
                for ts in starts:
                    q=self.cache.transfer(site,dest,g,ts)
                    yield Option(s,site,((site,s,cp),(dest,q.restart,q.restart+self.duration-(cp-s))),cp,physical,dest,ts,q.end,q.restart,q.wan)
            if (s,site) in self.stays:yield Option(s,site,((site,s,s+self.duration),))
    def option(self,index):
        require(0<=index<len(self),'OPTION_INDEX')
        for i,o in enumerate(self):
            if i==index:return o
        raise IndexError(index)

class Generator:
    def __init__(self,resources,max_slot,check=lambda:None):
        from copy import deepcopy
        self.r=deepcopy(resources);self.max_slot=max(max_slot,resources.control_end,max((t+1 for _,t in resources.fixed_gpu),default=0))
        self.check=check;self.counts=Counter();self.times=Counter();self.masks={};self.prefix={};self.transfers={};self.templates={}
        self.site_audit=[];self.per_job=[];self.series={}
        self.identity=hashlib.sha256(repr(asdict(resources)).encode()).hexdigest()
    def mask(self,d,g,site):
        key=(d,g,site)
        if key in self.masks:self.counts['start_mask_hits']+=1;return self.masks[key]
        t0=perf_counter();pkey=(g,site)
        if pkey not in self.prefix:
            cap=self.r.capacities.get(site,0)
            bad=np.zeros(self.max_slot,dtype=np.int64) if cap>=g else np.ones(self.max_slot,dtype=np.int64)
            for (s,t),used in self.r.fixed_gpu.items():
                if s==site and 0<=t<self.max_slot:bad[t]=int(cap-used<g-1e-9)
            self.prefix[pkey]=np.r_[0,np.cumsum(bad)]
        pref=self.prefix[pkey];starts=np.arange(self.max_slot+1)
        end=np.minimum(starts+d,self.max_slot)
        mask=(pref[end]-pref[starts])==0
        if self.r.capacities.get(site,0)<g:mask[:]=False
        self.masks[key]=mask;self.counts['start_mask_misses']+=1;self.times['start_mask_seconds']+=perf_counter()-t0
        return mask
    def fits(self,site,start,d,g):
        require(start>=0 and start+d<=self.max_slot,'MASK_AUTHORIZED_AXIS')
        return bool(self.mask(d,g,site)[start])
    def static_sites(self,j):
        possible=set(j.initial_sites)|{j.reference_site}
        initial=possible if j.state=='PENDING' else {j.reference_site}
        good=[]
        for s in sorted(possible):
            reason='PASS'
            if s not in self.r.capacities:reason='MISSING_SITE_AUTHORITY'
            elif j.gpu>self.r.capacities[s]:reason='SITE_GANG_CAPACITY'
            elif j.gpu>max(self.r.rack_limits.get(s,(0,))):reason='RACK_GANG_CAPACITY'
            self.site_audit.append(dict(job_id=j.uid,site=s,initial_authorized=s in initial,reason=reason))
            if reason=='PASS':good.append(s)
            else:self.counts['static_site_removals']+=1
        return [s for s in good if s in initial],[s for s in good if s in j.initial_sites]
    def transfer(self,src,dst,g,ts):
        key=(src,dst,g,ts)
        if key in self.transfers:self.counts['WAN_cache_hits']+=1;return self.transfers[key]
        t0=perf_counter();r=self.r;path=r.paths.get((src,dst),());left=r.bytes_per_gpu*g;te=ts;usage=[];reason=''
        if not path or len(set(path))!=len(path):reason='WAN_PATH'
        else:
            while left>0 and te<r.control_end:
                amount=min(left,*(max(0,r.wan_capacities.get((link,te),0)) for link in path))
                if amount:usage.extend((link,te,amount) for link in path)
                left-=amount;te+=1
            if left:reason='WAN_TRANSFER_IMPOSSIBLE'
            elif te+r.restart_slots>=r.control_end:reason='WAN_RESTART'
            elif any(n>r.wan_capacities.get((l,t),0)-r.fixed_wan.get((l,t),0)+1e-9 for l,t,n in usage):reason='IMMUTABLE_WAN'
            elif any(1>r.max_active_transfers-r.fixed_transfers.get(t,0)+1e-9 for t in range(ts,te)):reason='IMMUTABLE_ACTIVE_TRANSFERS'
        result=Transfer(te,te+r.restart_slots,tuple(usage),not reason,reason)
        self.transfers[key]=result;self.counts['WAN_cache_misses']+=1;self.times['WAN_template_seconds']+=perf_counter()-t0
        return result
    def transfer_series(self,src,dst,g):
        key=(src,dst,g)
        if key not in self.series:
            values=[self.transfer(src,dst,g,t) for t in range(self.r.control_end)]
            self.series[key]=(np.asarray([q.feasible for q in values]),np.asarray([q.restart for q in values]))
        else:self.counts['WAN_series_hits']+=1
        return self.series[key]
    def domain(self,j,b):
        self.check();b.require();require(j.admitted and self.r.restart_slots>=1 and self.r.bytes_per_gpu>0,'DOMAIN_AUTHORITY')
        # UID never changes physical feasibility. Every other job/boundary field
        # and the full immutable resource identity participates in template keys.
        key=(tuple((k,repr(v)) for k,v in asdict(j).items() if k!='uid'),repr(asdict(b)),self.identity)
        if key in self.templates:
            d,a=self.templates[key];self.counts['job_template_hits']+=1
            self.per_job.append(dict(a,job_id=j.uid,template_reused=True,generation_seconds=0.));return d
        started=perf_counter();before=self.counts.copy();s0=perf_counter();initial,dests=self.static_sites(j);self.times['static_site_seconds']+=perf_counter()-s0
        starts=sorted(set(b.allowed_starts))
        if j.state!='PENDING' or j.protected or j.qos in ('high','urgent') or j.unknown_arrival:starts=[j.reference_start]
        starts=[s for s in starts if s>=max(j.submit,j.event,j.reference_start)]
        self.counts['raw_start_opportunities']+=len(b.allowed_starts);self.counts['boundary_retained_starts']+=len(starts)
        stays=[];blocks=[];seen=set()
        for s in starts:
            self.check()
            for site in initial:
                self.counts['start_site_skeletons']+=1
                if s+j.service_slots<=b.latest_completion and self.fits(site,s,j.service_slots,j.gpu):stays.append((s,site))
                else:self.counts['immutable_or_terminal_STAY_removals']+=1
                if not j.checkpoint_authorized or j.unknown_arrival or j.migrations_used or not dests:
                    self.counts['checkpoint_capability_removals']+=1;continue
                p0=perf_counter();points=checkpoints(j,s,min(s+j.service_slots,self.r.control_end));self.times['checkpoint_seconds']+=perf_counter()-p0
                if not points:self.counts['checkpoint_empty_removals']+=1
                for cp,physical in points:
                    self.counts['checkpoint_branches']+=1
                    rem=j.service_slots-(cp-s)
                    if rem<=0 or not self.fits(site,s,cp-s,j.gpu):self.counts['checkpoint_prefix_removals']+=1;continue
                    for dst in dests:
                        if dst==site or not self.r.paths.get((site,dst)):
                            self.counts['destination_removals']+=1;continue
                        # At least one transfer slot and r restart slots; final
                        # service must fit the exact representation boundary.
                        latest=min(self.r.control_end-self.r.restart_slots-2,b.latest_completion-rem-self.r.restart_slots-1)
                        self.counts['WAN_latest_start_pruned']+=max(0,self.r.control_end-max(cp,latest+1))
                        ids=np.arange(cp,latest+1,dtype=int)
                        feasible,restarts=self.transfer_series(site,dst,j.gpu)
                        good=feasible[ids] & (restarts[ids]+rem<=b.latest_completion)
                        good &= self.mask(rem,j.gpu,dst)[np.minimum(restarts[ids],self.max_slot)]
                        valid=ids[good].tolist()
                        self.counts['WAN_start_branches']+=len(ids)
                        self.counts['WAN_or_destination_removals']+=len(ids)-len(valid)
                        if valid:
                            signature=(s,site,cp,physical,dst,j.gpu,tuple(valid))
                            if signature in seen:self.counts['exact_duplicates_removed']+=len(valid)
                            else:seen.add(signature);blocks.append(signature)
        d=Domain(stays,blocks,self,j.service_slots);self.counts['job_template_misses']+=1
        a=dict(job_id=j.uid,template_reused=False,generation_seconds=perf_counter()-started,complete_options=len(d),
            lazy_blocks=len(blocks),counters=dict(self.counts-before),domain_sha=d.sha)
        self.per_job.append(a);self.templates[key]=(d,a);self.times['domain_seconds']+=a['generation_seconds']
        return d
