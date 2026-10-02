"""Causal FCFS controller separated from private retrospective realization.

Only Submission and Completion events cross the environment boundary. Duration
and future source completion never enter a controller request or site decision.
"""
from dataclasses import dataclass
import heapq
import math
import numpy as np
from v42_final.state import EpisodeLedger


@dataclass(frozen=True)
class Request:
    uid: str
    submit: float
    gpu: int
    compatible: tuple
    q50: float
    source_site: str | None = None


class CachedProvider:
    def predict_total(self, metadata, **kwargs): return metadata['q50']


class Controller:
    def __init__(self, capacities):
        self.ledger=EpisodeLedger(capacities)
        self.pending=[]; self.requests={}; self.audit={}

    def submit(self, request, now):
        if request.submit > now: raise ValueError('FUTURE_SUBMISSION')
        self.ledger.submit(request.uid,request.submit,now,request.gpu,{'q50':request.q50},CachedProvider())
        self.requests[request.uid]=request
        heapq.heappush(self.pending,(request.submit,request.uid))
        self.audit[request.uid]=dict(job_uid=request.uid,submit_time=request.submit,initial_admission_attempt=now,
            admitted_time=None,capacity_wait_seconds=None,capacity_wait_slots=None,site=None,GPU_gang=request.gpu,
            queue_position=sorted(self.pending).index((request.submit,request.uid))+1,completion_observed_time=None,release_control_time=None,
            grid_reads=0,future_end_reads=0,future_duration_reads=0,optimizer_calls=0,
            timeshift_optimization=False,migration_optimization=False)

    def admit(self, now):
        starts=[]
        while self.pending:
            _,uid=self.pending[0]; r=self.requests[uid]; a=self.audit[uid]
            if a['initial_admission_attempt'] is None:
                a['initial_admission_attempt']=now; a['queue_position']=1
            use=self.ledger.physical(now)
            eligible=sorted(s for s in r.compatible if s in use and (r.source_site is None or s==r.source_site))
            site=next((s for s in eligible if use[s]+r.gpu<=self.ledger.capacities[s]),None)
            if site is None: break  # strict FCFS: never backfill a later small request
            heapq.heappop(self.pending)
            self.ledger.start(uid,site,now,'B0:'+uid)
            wait=now-max(r.submit,0.)
            a.update(admitted_time=now,capacity_wait_seconds=wait,capacity_wait_slots=math.ceil(wait/900),site=site)
            starts.append(uid)
        return starts

    def completion(self, uid, now):
        self.ledger.complete(uid,now,now)
        j=self.ledger.jobs[uid]
        self.audit[uid].update(completion_observed_time=now,release_control_time=j['release_control_time'])
        return j['release_control_time']


class Environment:
    """Private service realization; controller only sees events at the clock."""
    def __init__(self, durations, running_completions=None):
        self.__durations=dict(durations)
        self.__running_completions=dict(running_completions or {})
        if any(not math.isfinite(x) or x<0 for x in self.__durations.values()):
            raise ValueError('SOURCE_REALIZED_SERVICE_REQUIRED')

    def started(self, uid, now): return now+self.__durations[uid]
    def running_completion(self,uid): return self.__running_completions[uid]


def replay(capacities, requests, environment, *, running=(), begin=0., end=108000., active_begin=21600.):
    controller=Controller(capacities); events=[]; counter=0
    def event(t,kind,payload=None):
        nonlocal counter
        counter+=1
        if t<=end: heapq.heappush(events,(float(t),kind,counter,payload))
    # The environment emits each request only when its submission is observable.
    for r in requests: event(max(begin,r.submit),2,r)
    for r,site,start in running:
        controller.submit(r,begin)
        controller.pending.remove((r.submit,r.uid)); heapq.heapify(controller.pending)
        controller.ledger.start(r.uid,site,begin,'OBSERVED:'+r.uid)
        controller.ledger.jobs[r.uid]['start_time']=start
        controller.audit[r.uid].update(initial_admission_attempt=begin,admitted_time=start,
            capacity_wait_seconds=0.,capacity_wait_slots=0,site=site,queue_position=0)
        event(environment.running_completion(r.uid),0,r.uid)
    for t in np.arange(begin,end+1,900.): event(t,3)
    occupancy=np.zeros((96,len(capacities))); sites=sorted(capacities); last=begin
    max_site=np.zeros(len(sites)); max_total=0
    def integrate(a,b):
        nonlocal max_total
        physical=controller.ledger.physical(a)
        use=np.array([physical[s] for s in sites],float)
        max_site[:]=np.maximum(max_site,use); max_total=max(max_total,float(use.sum()))
        assert (use<=np.array([capacities[s] for s in sites])).all()
        left=max(a,active_begin); right=min(b,end)
        if right<=left: return
        for t in range(max(0,int((left-active_begin)//900)),min(96,int(math.ceil((right-active_begin)/900)))):
            overlap=max(0.,min(right,active_begin+(t+1)*900)-max(left,active_begin+t*900))
            occupancy[t]+=use*overlap/900.
    while events:
        now=events[0][0]; integrate(last,now); last=now
        # Publish all contemporaneous completion/submission receipts first.
        batch=[]
        while events and events[0][0]==now: batch.append(heapq.heappop(events))
        for _,kind,_,payload in batch:
            if kind==0: event(controller.completion(payload,now),1)
            elif kind==2: controller.submit(payload,now)
        for uid in controller.admit(now): event(environment.started(uid,now),0,uid)
    integrate(last,end)
    assert len(controller.requests)==len(requests)+len(running)
    carry=[j for j in controller.ledger.jobs.values() if j['latest_observed_state']=='PENDING' or
           (j['latest_observed_state']=='RUNNING') or (j['release_control_time'] is not None and j['release_control_time']>end)]
    rows=list(controller.audit.values())
    for a in rows:
        if a['admitted_time'] is None:
            a['capacity_wait_seconds']=end-max(controller.requests[a['job_uid']].submit,begin)
            a['capacity_wait_slots']=math.ceil(a['capacity_wait_seconds']/900)
        a['capacity_wait_censored_at_horizon']=a['admitted_time'] is None
        a['capacity_wait']=a['admitted_time'] is None or a['capacity_wait_seconds']>0
        a['carryout']=a['job_uid'] in {j['job_id'] for j in carry}
        a['latest_state']=controller.ledger.jobs[a['job_uid']]['latest_observed_state']
    return occupancy,rows,dict(max_per_site_GPU=dict(zip(sites,max_site.tolist())),max_total_GPU=max_total,
        capacity_violations=0,dropped_jobs=0,queued_jobs=sum(a['capacity_wait'] for a in rows),carryout_jobs=len(carry),
        submitted_jobs=len(rows),admitted_jobs=sum(a['admitted_time'] is not None for a in rows),
        grid_reads=0,optimizer_calls=0,future_end_controller_reads=0,future_duration_controller_reads=0,
        Actual_CC4_physical_GPU=0,Actual_PQ_repair=0,Actual_global_reoptimization=0)
