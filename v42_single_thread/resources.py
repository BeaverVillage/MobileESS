"""One scientific worker; lightweight telemetry never creates solver workers."""
import csv
import json
import os
import threading
import time
from datetime import datetime, timezone
import psutil
from .common import OUT, ENV, write

def processes():
    result=[]
    for p in psutil.process_iter(['pid','ppid','name','cmdline','memory_info','num_threads']):
        try:
            info=p.info
            name=(info['name'] or '').lower()
            if 'python' not in name and 'gurobi' not in name and 'pytest' not in name:
                continue
            result.append(dict(pid=info['pid'],ppid=info['ppid'],name=info['name'],command_line=' '.join(info['cmdline'] or []),RSS=info['memory_info'].rss if info['memory_info'] else None,thread_count=info['num_threads'],self=info['pid']==os.getpid()))
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    return result

def snapshot():
    memory=psutil.virtual_memory();swap=psutil.swap_memory();p=psutil.Process()
    return dict(UTC=datetime.now(timezone.utc).isoformat(),process_RSS=p.memory_info().rss,system_RAM_total=memory.total,system_RAM_used=memory.used,system_RAM_free=memory.available,swap_total=swap.total,swap_used=swap.used,CPU_utilization_percent=psutil.cpu_percent(interval=None),logical_cores=psutil.cpu_count(),available_logical_cores=len(p.cpu_affinity()),process_thread_count=p.num_threads(),heavy_processes=processes())

def exclusive_gate(label):
    psutil.cpu_percent(interval=.1)
    value=snapshot()
    value.update(label=label,environment={k:os.environ.get(k) for k in ENV})
    external=[p for p in value['heavy_processes'] if not p['self']]
    value['external_python_or_solver_candidates']=external
    value['PASS']=not external and all(value['environment'][k]=='1' for k in ENV)
    write('RESOURCE_GATE_'+label+'.json',value)
    if not value['PASS']:
        raise RuntimeError('SINGLE_WORKER_GATE_BLOCKED:'+label)
    return value

class Timeline:
    """Sample observed peaks; callback labels are literal observations only."""
    def __init__(self, block):
        self.block=block;self.begin=time.perf_counter();self.lock=threading.Lock()
        self.rows=[];self.stop=threading.Event();self.active_model=None
        self.policy_violations=[];self.errors=[]
        self.path=OUT/(block+'_SINGLE_THREAD_RESOURCE_TIMELINE.csv')
        self.fields=['UTC','wall_seconds','phase','solver_seconds','process_RSS','system_RAM_total','system_RAM_used','system_RAM_free','swap_total','swap_used','CPU_utilization_percent','logical_cores','available_logical_cores','process_thread_count','heavy_processes']
        with self.path.open('w',encoding='utf8',newline='') as f:
            csv.DictWriter(f,fieldnames=self.fields).writeheader()
        self.sample('before_model_build')
        self.thread=threading.Thread(target=self.watch,daemon=True,name=block+'_resource_sampler')
        self.thread.start()

    def sample(self, phase, solver_seconds=None):
        with self.lock:
            row=snapshot();row.update(wall_seconds=time.perf_counter()-self.begin,phase=phase,solver_seconds=solver_seconds)
            external=[p for p in row['heavy_processes'] if not p['self']]
            if external:
                self.policy_violations.append(dict(UTC=row['UTC'],external=external))
                if self.active_model is not None:self.active_model.terminate()
            self.rows.append(row)
            with self.path.open('a',encoding='utf8',newline='') as f:
                flat=dict(row,heavy_processes=json.dumps(row['heavy_processes'],ensure_ascii=False))
                csv.DictWriter(f,fieldnames=self.fields).writerow(flat)
            return row

    def watch(self):
        while not self.stop.wait(5):
            try:self.sample('periodic')
            except Exception as error:self.errors.append(repr(error))

    def close(self, status):
        self.active_model=None;self.stop.set();self.thread.join(timeout=2)
        self.sample('after_terminal_solve')
        summary=dict(status=status,observed_peak_process_RSS=max(r['process_RSS'] for r in self.rows),observed_minimum_system_free_RAM=min(r['system_RAM_free'] for r in self.rows),observed_maximum_swap_used=max(r['swap_used'] for r in self.rows),sample_count=len(self.rows),periodic_sample_seconds=5,exact_peak_not_claimed=True,worker_processes=1,Gurobi_Threads=1,telemetry_support_thread_is_not_a_solver_worker=True,external_heavy_process_observations=self.policy_violations,telemetry_errors=self.errors,sequential_policy_PASS=not self.policy_violations)
        write(self.block+'_SINGLE_THREAD_RESOURCE_SUMMARY.json',summary)
        return summary
