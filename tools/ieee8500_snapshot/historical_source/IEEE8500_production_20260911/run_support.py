import sys,time,os,json,threading,hashlib
from pathlib import Path
import numpy as np
import psutil
import ac8500 as ac
sys.dont_write_bytecode=True
def atomic(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');ac.save(tmp,value);os.replace(tmp,p)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def key_arrays(*arrays):
    h=hashlib.sha256()
    for a in arrays:h.update(np.ascontiguousarray(a,dtype=np.float64).tobytes())
    return h.hexdigest()
class Metrics:
    def __init__(self):self.solve=[];self.ac=[];self.candidate_seconds=0.;self.candidate_evaluations=0;self.incumbent_updates=0;self.peak_ram=0;self.lock=threading.Lock();self.started=time.perf_counter()
    def sample(self):
        p=psutil.Process();rss=p.memory_info().rss
        for c in p.children(recursive=True):
            try:rss+=c.memory_info().rss
            except psutil.Error:pass
        self.peak_ram=max(self.peak_ram,rss)
    def summary(self):
        self.sample()
        def stats(x):return dict(count=len(x),median_seconds=float(np.median(x)) if x else None,p95_seconds=float(np.quantile(x,.95)) if x else None,total_seconds=sum(x))
        elapsed=time.perf_counter()-self.started
        return dict(neighborhood_LP_MILP=stats(self.solve),exact_AC_validation=stats(self.ac),candidate_generation_ranking_seconds=self.candidate_seconds,candidate_evaluations=self.candidate_evaluations,candidate_evaluations_per_second=self.candidate_evaluations/elapsed,candidate_ranking_throughput_per_second=self.candidate_evaluations/self.candidate_seconds if self.candidate_seconds else None,incumbent_updates=self.incumbent_updates,peak_RAM_bytes=self.peak_ram,elapsed_seconds=elapsed)
class Oracle:
    def __init__(self,folder,metrics):self.folder=Path(folder);self.metrics=metrics;self.cache={};self.counter=0
    def validate(self,p,mp=None,mq=None,tag='candidate'):
        mp=np.zeros((96,24)) if mp is None else mp;mq=np.zeros((96,24)) if mq is None else mq;q=p*.3286841051788632;k=key_arrays(p,q,mp,mq)
        if k in self.cache:return self.cache[k]
        self.counter+=1;f=self.folder/f'{self.counter:05d}_{tag}';start=time.perf_counter();r=ac.replay(f,aidc_p=p,aidc_q=q,mess_p=mp,mess_q=mq,independent=True);self.metrics.ac.append(time.perf_counter()-start);self.metrics.sample()
        np.savez_compressed(f/'DECISION_POWER.npz',aidc_p=p,aidc_q=q,mess_p=mp,mess_q=mq)
        ans=dict(feasible=bool(r['feasible']),P1=float(r['max_phase_line_loading_pu']),summary=r,evidence=str(f.resolve()),power_SHA256=k);self.cache[k]=ans;return ans
class Deadline:
    def __init__(self,folder,metrics,initial):
        self.folder=Path(folder);self.metrics=metrics;self.started=time.perf_counter();self.duration=14400.;self.end=self.started+self.duration;self.current=initial;self.lock=threading.Lock();self.stop=threading.Event();self.checkpoints=[];self.best_at=0.;self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
    @property
    def remaining(self):return max(0.,self.end-time.perf_counter())
    def accept(self,value):
        with self.lock:
            if value['AC']['P1']<self.current['AC']['P1']-1e-8:self.best_at=time.perf_counter()-self.started
            self.current=value;self.metrics.incumbent_updates+=1
    def checkpoint(self,target):
        with self.lock:current=self.current;best=self.best_at
        payload=dict(checkpoint_seconds=target,actual_elapsed_seconds=time.perf_counter()-self.started,incumbent=current,P1=current['AC']['P1'],time_to_best_P1_seconds=best,metrics=self.metrics.summary(),continuous_loop_budget_seconds=14400.,independently_AC_validated=True)
        atomic(self.folder/'checkpoints'/f'{target:05d}s.json',payload);self.checkpoints.append(dict(seconds=target,P1=current['AC']['P1'],incumbent_SHA=digest(current)))
    def watch(self):
        targets=[1800,3600,7200,14400];last=-60.
        while not self.stop.is_set():
            elapsed=time.perf_counter()-self.started;self.metrics.sample()
            if targets and elapsed>=targets[0]:self.checkpoint(targets.pop(0))
            if elapsed-last>=60:
                with self.lock:cur=self.current
                atomic(self.folder/'LIVE_STATUS.json',dict(elapsed_seconds=elapsed,remaining_seconds=self.remaining,P1=cur['AC']['P1'],incumbent_updates=self.metrics.incumbent_updates,metrics=self.metrics.summary()));print(self.folder.name,'LOOP',round(elapsed,1),'P1',cur['AC']['P1'],'updates',self.metrics.incumbent_updates,flush=True);last=elapsed
            if not targets:return
            self.stop.wait(.5)
    def finish(self):
        assert time.perf_counter()>=self.end,'FOUR_HOUR_LOOP_NOT_COMPLETED'
        self.thread.join(3)
        if not any(r['seconds']==14400 for r in self.checkpoints):self.checkpoint(14400)
        self.stop.set();return dict(continuous_loop_seconds=time.perf_counter()-self.started,checkpoints=self.checkpoints,time_to_best_P1_seconds=self.best_at)
