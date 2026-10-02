import os,time,platform,threading
import psutil
from .common import dump,stamp
def snapshot(label):
    processes=[]
    for p in psutil.process_iter(['pid','ppid','name','cmdline','memory_info']):
        try:
            d=p.info;name=(d['name'] or '').lower();cmd=d['cmdline'] or []
            if 'python' in name or 'gurobi' in name or 'solver' in name:
                processes.append(dict(pid=d['pid'],ppid=d['ppid'],name=d['name'],command_line=cmd,
                    rss_bytes=None if d['memory_info'] is None else d['memory_info'].rss,
                    cpu_time_seconds=sum(p.cpu_times()[:2])))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    vm=psutil.virtual_memory();swap=psutil.swap_memory()
    v=dict(label=label,utc=stamp(),hardware=platform.platform(),cpu=platform.processor(),
        cpu_utilization_percent=psutil.cpu_percent(interval=1),logical_cores=psutil.cpu_count(),available_logical_cores=len(psutil.Process().cpu_affinity()),
        RAM=dict(total=vm.total,used=vm.used,free=vm.available,percent=vm.percent),swap_pagefile=swap._asdict(),
        python_solver_processes=processes,worker_pid=os.getpid(),independent_workloads_allowed=True,
        RESOURCE_CONTENTION_ABSENCE_REQUIRED=False)
    dump('RESOURCE_'+label+'.json',v)
    # Pause only for measurable immediate exhaustion; never for another Python's existence.
    assert vm.available>=3*1024**3,('RESOURCE_EXHAUSTION_RAM',vm.available)
    return v
class PeakMemory:
    def __init__(self):self.peak=0;self.done=threading.Event();self.thread=threading.Thread(target=self.loop,daemon=True)
    def loop(self):
        p=psutil.Process()
        while not self.done.wait(.2):
            try:self.peak=max(self.peak,p.memory_info().rss)
            except psutil.Error:pass
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.done.set();self.thread.join()
