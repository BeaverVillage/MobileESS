"""Reuse original calculations without changing any candidate or constraint."""
from contextlib import contextmanager
from dataclasses import asdict
from time import perf_counter
import threading
from .common import atomic, now

class CheckpointMemo:
    def __init__(self, original):
        self.original=original;self.values={};self.calls=0;self.hits=0;self.compute_seconds=0.;self.total_seconds=0.
    def __call__(self, job, start, end):
        begin=perf_counter();self.calls+=1
        # All dependencies of the original function, including its constants.
        g=self.original.__globals__
        key=(job.state,job.elapsed_seconds,job.event,start,end,g['SLOT_SECONDS'],g['CHECKPOINT_SECONDS'])
        if key in self.values:
            self.hits+=1;result=self.values[key]
        else:
            t=perf_counter();result=self.original(job,start,end);self.compute_seconds+=perf_counter()-t
            self.values[key]=result
        self.total_seconds+=perf_counter()-begin
        return result
    def report(self):
        return dict(calls=self.calls,hits=self.hits,unique_conditions=len(self.values),
            original_compute_seconds=self.compute_seconds,total_wrapper_seconds=self.total_seconds,
            key_dependencies=['state','elapsed_seconds','event','start','end','SLOT_SECONDS','CHECKPOINT_SECONDS'])

@contextmanager
def checkpoint_memo():
    import v42_job_capability as capability
    import v42_a_stage_domain_v2.domain as domain
    original=capability.checkpoint_records;old_domain=domain.checkpoint_records
    memo=CheckpointMemo(original)
    capability.checkpoint_records=domain.checkpoint_records=memo
    try:yield memo
    finally:capability.checkpoint_records=original;domain.checkpoint_records=old_domain

class BuildObserver:
    def __init__(self,output,progress):
        self.output=output;self.progress=progress;self.start=perf_counter();self.stop=threading.Event()
        self.fields=dict(build_function='fresh_DATA',physical_classes_complete=0,Native_calls=0)
        self.costs=[];self.mutex=threading.RLock()
        self.last_stage_progress_UTC=now()
    def publish(self):
        with self.mutex:
            value=dict(self.fields,phase='A_BUILD_DETAIL',model_preparation_seconds=perf_counter()-self.start,
                build_detail_UTC=now(),stage_costs=list(self.costs))
        atomic(self.output/'MODEL_BUILD_DETAIL.json',value)
        atomic(self.output/'BUILD_STAGE_TIMES.json',dict(stage_costs=list(self.costs),
            current_function=self.fields['build_function'],last_stage_progress_UTC=self.last_stage_progress_UTC))
        if self.progress:self.progress(value)
    def ticker(self):
        while not self.stop.wait(2):self.publish()
    def __enter__(self):
        self.thread=threading.Thread(target=self.ticker,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(5);self.publish()
    @contextmanager
    def stage(self,label):
        start=perf_counter()
        with self.mutex:self.fields['build_function']=label
        self.last_stage_progress_UTC=now()
        self.publish()
        try:yield
        finally:
            self.costs.append(dict(function=label,wall_seconds=perf_counter()-start))
            self.last_stage_progress_UTC=now()
            self.publish()

def domain_hash(job,bound,domain):
    from v42_a_stage_domain_v2.domain import digest,AUTHORITY
    return digest(dict(authority=AUTHORITY,resources=domain.cache.identity,
        job={k:v for k,v in asdict(job).items() if k!='uid'},completion=bound.latest_completion,
        stays=domain.stays,blocks=domain.blocks))
