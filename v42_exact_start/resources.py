import os,platform,psutil
from v42_monolithic.resources import PeakMemory
from .common import *

def snapshot(label):
    processes=[]
    for p in psutil.process_iter(['pid','ppid','name','cmdline','memory_info']):
        try:
            d=p.info
            if any(s in (d['name'] or '').lower() for s in ['python','solver','gurobi']):
                processes.append(dict(pid=d['pid'],ppid=d['ppid'],name=d['name'],command_line=d['cmdline'],RSS=d['memory_info'].rss))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    ram=psutil.virtual_memory();swap=psutil.swap_memory()
    receipt=dict(label=label,utc=stamp(),worker_pid=os.getpid(),hardware=platform.platform(),cpu=platform.processor(),
        cpu_utilization_percent=psutil.cpu_percent(interval=1),logical_cores=psutil.cpu_count(),available_logical_cores=len(psutil.Process().cpu_affinity()),
        RAM=dict(total=ram.total,used=ram.used,available=ram.available,percent=ram.percent),swap_pagefile=swap._asdict(),
        active_Python_solver_processes=processes,process_threadpool_environment={k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},
        independent_workloads_allowed=True,RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,Gurobi_Threads=4)
    dump('RESOURCE_'+label+'.json',receipt)
    assert ram.available>=3*1024**3,('ACTUAL_RAM_EXHAUSTION',ram.available)
    assert all(v=='1' for v in receipt['process_threadpool_environment'].values())
    return receipt
