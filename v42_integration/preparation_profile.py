"""Wall/CPU and sampled memory telemetry outside native Optimize budgets."""
from contextlib import contextmanager
from functools import wraps
import json
from pathlib import Path
import threading
from time import perf_counter, process_time

_write_lock = threading.Lock()


@contextmanager
def measure(folder, stage):
    import psutil
    from .table_v_memory import memory_sample
    process=psutil.Process();stop=threading.Event();samples=[]
    def sample():
        while True:
            current=memory_sample()
            samples.append((current.get('RSS_bytes') or 0,current.get('private_bytes') or 0,
                            current.get('system_committed_bytes') or 0))
            if stop.wait(.2):break
    wall=perf_counter();cpu=process_time();before=memory_sample()
    thread=threading.Thread(target=sample,name='preparation-memory-sampler',daemon=True);thread.start()
    error=None
    try:yield
    except BaseException as exc:
        error=type(exc).__name__;raise
    finally:
        stop.set();thread.join(timeout=1.)
        after=memory_sample();peaks=list(zip(*samples)) if samples else [[],[],[]]
        row=dict(stage=stage,wall_seconds=perf_counter()-wall,CPU_seconds=process_time()-cpu,
                 peak_RSS_sampled_bytes=max(peaks[0],default=0),
                 peak_private_sampled_bytes=max(peaks[1],default=0),
                 peak_system_commit_sampled_bytes=max(peaks[2],default=0),
                 memory_before=before,memory_after=after,sample_period_seconds=.2,
                 process_lifetime_peak_RSS_bytes=getattr(process.memory_info(),'peak_wset',None),
                 Native_optimize_included=False,error=error)
        path=Path(folder)/'PREPARATION_PROFILE.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        with _write_lock,path.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(row,allow_nan=False)+'\n')


def profile_joint(function):
    @wraps(function)
    def wrapped(case,*args,**kwargs):
        with measure(case.output,'M_DIRECT_JOINT_CONSTRUCTION'):
            return function(case,*args,**kwargs)
    return wrapped
