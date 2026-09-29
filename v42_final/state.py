"""Observed execution truth and conditional waiting budget."""
from dataclasses import dataclass,field
import math
import numpy as np
from .common import require


def conditional_wait(state,protected,age_seconds,historical_waits,*,support=100):
    require(support==100 and np.isfinite(age_seconds) and age_seconds>=0,'WAIT_AUTHORITY')
    require(state in ('PENDING','RUNNING'),'OBSERVED_STATE')
    if state!='PENDING' or protected:return False,0,0,None
    w=np.asarray(historical_waits,float);require(np.isfinite(w).all() and (w>=0).all(),'TRAIN_WAIT_SECONDS')
    residual=w[w>age_seconds]-age_seconds;n=len(residual)
    if n<support:return False,0,n,None
    budget=float(np.quantile(residual,.5));slots=math.floor(budget/900)
    return slots>=1,slots,n,budget


def planning_remaining(q50,elapsed,*,state):
    require(state in ('PENDING','RUNNING') and np.isfinite(q50) and q50>=0 and np.isfinite(elapsed) and elapsed>=0,'NOMINAL_SECONDS')
    if state=='PENDING':require(elapsed==0,'PENDING_HAS_NO_EXECUTION_ELAPSED')
    seconds=q50 if state=='PENDING' else max(q50-elapsed,0.)
    return dict(nominal_remaining_seconds=seconds,nominal_slots=math.ceil(seconds/900),
        observed_running_hard=state=='RUNNING',overrun_uncertainty=state=='RUNNING' and elapsed>=q50,
        synthetic_completion=False,actual_runtime_reserve_GPU=0.)


@dataclass
class EpisodeLedger:
    capacities: dict
    jobs: dict=field(default_factory=dict)
    used_receipts: set=field(default_factory=set)
    last_time: float=field(default=-float('inf'))

    def _time(self,t):
        require(t>=self.last_time,'NONCAUSAL_STATE_UPDATE');self.last_time=t

    def submit(self,job_id,submit_time,event_time,gpu,metadata,provider,forecast=None):
        require(submit_time<=event_time and job_id not in self.jobs,'SUBMISSION_AUTHORITY')
        require(gpu>0 and int(gpu)==gpu,'WHOLE_GANG')
        # Both formerly-known and formerly-unknown callers use this same method.
        q=float(provider.predict_total(metadata,submit_time=submit_time,event_time=event_time))
        require(np.isfinite(q) and q>=0,'FINITE_Q50_SECONDS')
        self._time(event_time)
        if forecast is not None:forecast.submit(job_id,submit_time,event_time,gpu,q)
        self.jobs[job_id]=dict(job_id=job_id,episode_id=None,initial_site=None,current_site=None,
            submit_time=submit_time,start_time=None,latest_observed_state='PENDING',gpu=gpu,q50_seconds=q,
            completion_observed_time=None,release_control_time=None,migration_receipt=None)
        return self.jobs[job_id]

    def physical(self,t):
        require(t>=self.last_time,'PAST_PHYSICAL_STATE')
        use={s:0 for s in self.capacities}
        for j in self.jobs.values():
            active=(j['latest_observed_state']=='RUNNING' or
                    (j['latest_observed_state']=='COMPLETED' and t<j['release_control_time']))
            if active:
                require(j['current_site'] in use,'UNASSIGNED_OVERLAPPING_RUNNING')
                use[j['current_site']]+=j['gpu']
        return use  # no runtime reserve term, no Q50-expiry test

    def start(self,job_id,site,event_time,episode_id):
        require(site in self.capacities,'SOURCE_BACKED_SITE')
        j=self.jobs[job_id];require(j['latest_observed_state']=='PENDING' and episode_id,'PRESTART_ONLY')
        require(event_time>=j['submit_time'],'START_BEFORE_SUBMISSION')
        use=self.physical(event_time);require(use[site]+j['gpu']<=self.capacities[site],'PHYSICAL_CAPACITY_RUNNING_RETAINED')
        self._time(event_time);j.update(latest_observed_state='RUNNING',initial_site=site,current_site=site,start_time=event_time,episode_id=episode_id)

    def observe_running(self,job_id,site,event_time):
        j=self.jobs[job_id];require(j['latest_observed_state']=='RUNNING' and site==j['current_site'],'RUNNING_SITE_CHANGE_REQUIRES_RECEIPT')
        self._time(event_time)

    def complete(self,job_id,observed_time,event_time):
        j=self.jobs[job_id];require(j['latest_observed_state']=='RUNNING' and j['start_time']<=observed_time<=event_time,'OBSERVED_COMPLETION_REQUIRED')
        self._time(event_time);j['completion_observed_time']=observed_time;j['latest_observed_state']='COMPLETED'
        j['release_control_time']=math.ceil(event_time/900)*900

    def migrate(self,job_id,destination,event_time,receipt,validate_receipt):
        j=self.jobs[job_id]
        require(j['latest_observed_state']=='RUNNING' and j['migration_receipt'] is None,'ONE_AUTHORIZED_CHECKPOINT_MIGRATION')
        require(destination!=j['current_site'],'MIGRATION_REQUIRES_DIFFERENT_SITE')
        require(receipt['id'] not in self.used_receipts and callable(validate_receipt),'MIGRATION_RECEIPT_IDENTITY')
        require(receipt['job_id']==job_id and receipt['episode_id']==j['episode_id'] and receipt['source']==j['current_site']
                and receipt['destination']==destination and receipt['completed_at']<=event_time,'MIGRATION_RECEIPT_MATCH')
        require(validate_receipt(receipt,j) is True,'FROZEN_CHECKPOINT_WAN_RECEIPT_VALIDATION')
        use=self.physical(event_time);require(destination in use and use[destination]+j['gpu']<=self.capacities[destination],'DESTINATION_PHYSICAL_CAPACITY')
        self._time(event_time);j['current_site']=destination;j['migration_receipt']=dict(receipt);self.used_receipts.add(receipt['id'])


def legacy_unassigned(rows,active_begin=24):
    unresolved=[r for r in rows if not r['planning_eligible'] and r['state']=='RUNNING']
    require(all(r['reference_end']<=active_begin for r in unresolved),'UNASSIGNED_OVERLAPPING_RUNNING')
    return unresolved
