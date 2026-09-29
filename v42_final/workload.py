"""GPUh conservation and causal replacement of anonymous arrival work."""
from dataclasses import dataclass,field
import numpy as np
from .common import require

SLOT_SECONDS=900


def execution_lag_kernel(submit,start,end,gpu):
    """Exact GPU-second overlaps in relative 15-minute bins, full support."""
    submit,start,end,gpu=map(lambda x:np.asarray(x,float),(submit,start,end,gpu))
    require(submit.ndim==start.ndim==end.ndim==gpu.ndim==1 and submit.shape==start.shape==end.shape==gpu.shape,'EXECUTION_AXES')
    require(len(submit)>0 and all(np.isfinite(x).all() for x in (submit,start,end,gpu)),'FINITE_EXECUTION_INPUTS')
    require(((start>=submit)&(end>=start)&(gpu>0)).all(),'EXECUTION_ORDER_OR_GANG')
    a=(start-submit)/900;b=(end-submit)/900
    count=int(np.ceil(b.max()))+1;mass=np.zeros(count);diff=np.zeros(count+1)
    ia=np.floor(a).astype(int);ib=np.floor(b).astype(int);same=ia==ib
    np.add.at(mass,ia[same],(b[same]-a[same])*gpu[same])
    cross=~same
    np.add.at(mass,ia[cross],(ia[cross]+1-a[cross])*gpu[cross])
    np.add.at(mass,ib[cross],(b[cross]-ib[cross])*gpu[cross])
    np.add.at(diff,ia[cross]+1,gpu[cross]);np.add.at(diff,ib[cross],-gpu[cross])
    mass+=np.cumsum(diff[:-1]);mass[np.abs(mass)<1e-10]=0
    expected=float(np.sum((end-start)*gpu)/900)
    require(expected>0 and np.all(mass>=0) and np.isclose(mass.sum(),expected,rtol=1e-10),'GPU_SECOND_CONSERVATION')
    last=np.flatnonzero(mass>0)[-1];mass=mass[:last+1]
    return mass/mass.sum(),mass*.25


def profile(workload_gpu_hours,kernel):
    work=np.asarray(workload_gpu_hours,float);k=np.asarray(kernel,float)
    require(work.size>0 and k.size>0,'NONEMPTY_PROFILE')
    require(work.ndim==k.ndim==1 and np.isfinite(work).all() and np.isfinite(k).all(),'FINITE_PROFILE')
    require((work>=0).all() and (k>=0).all() and np.isclose(k.sum(),1,rtol=0,atol=1e-10),'NORMALIZED_KERNEL')
    arrivals=np.zeros((len(work)-1)*4+1);arrivals[::4]=work
    occupancy=np.convolve(arrivals,k)/.25
    require(np.isclose(occupancy.sum()*.25,work.sum(),rtol=1e-10,atol=1e-9),'FULL_COHORT_MASS_PRESERVED')
    return occupancy


@dataclass
class ForecastBook:
    q50: tuple
    q90: tuple
    day_start: float
    consumed: dict=field(default_factory=dict)
    submissions: dict=field(default_factory=dict)
    last_event: float=field(default=-float('inf'))

    def __post_init__(self):
        require(len(self.q50)==len(self.q90)==24,'HOURLY_FORECAST_AXIS')
        require(all(np.isfinite(a) and np.isfinite(b) and 0<=a<=b for a,b in zip(self.q50,self.q90)),'QUANTILE_ORDER')

    def submit(self,job_id,submit_time,event_time,gpu,q50_seconds):
        require(submit_time<=event_time and event_time>=self.last_event,'NONCAUSAL_SUBMISSION')
        require(job_id not in self.submissions,'DUPLICATE_JOB_SUBMISSION')
        require(gpu>0 and int(gpu)==gpu and np.isfinite(q50_seconds) and q50_seconds>=0,'JOB_WORK_UNITS')
        h=int((submit_time-self.day_start)//3600);require(0<=h<24,'D_DAY_SUBMISSION_REQUIRED')
        # Delayed observation can still register an explicit job, but cannot
        # revive an anonymous cohort whose submission hour has already closed.
        mass=gpu*q50_seconds/3600
        self.consumed[h]=self.consumed.get(h,0.)+mass
        self.submissions[job_id]=dict(hour=h,nominal_GPUh=mass,submit_time=submit_time)
        self.last_event=event_time
        return self.row(h,event_time)

    def row(self,h,event_time):
        require(type(h) is int and 0<=h<24,'FORECAST_HOUR')
        require(event_time>=self.last_event,'NONCAUSAL_FORECAST_STATE')
        spent=self.consumed.get(h,0.);closed=event_time>=self.day_start+(h+1)*3600
        a=0. if closed else max(self.q50[h]-spent,0.)
        b=0. if closed else max(self.q90[h]-spent,0.)
        return dict(hour=h,observed_at=event_time,realized_submitted_nominal_work_GPUh=spent,
            remaining_CC4_Q50_GPUh=a,remaining_CC4_Q90_GPUh=b,remaining_CC4_reserve_GPUh=max(b-a,0.),
            cohort_closed=closed,explicit_plus_anonymous_nominal_GPUh=spent+a,
            expired_unsubmitted_Q50_GPUh=max(self.q50[h]-spent,0.) if closed else 0.)

    def profiles(self,event_time,kernel):
        rows=[self.row(h,event_time) for h in range(24)]
        return profile([r['remaining_CC4_Q50_GPUh'] for r in rows],kernel),profile([r['remaining_CC4_reserve_GPUh'] for r in rows],kernel)
