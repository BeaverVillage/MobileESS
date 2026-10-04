"""Observed one-second telemetry and graceful safety termination."""
from .common import *
import psutil,threading
from datetime import datetime,timezone
class Monitor:
    def __init__(self,pids,stop_event):
        self.pids=pids;self.stop_event=stop_event;self.rows=[];self.phase='build';self.begin=time.perf_counter();self.failed=[];self.baseline=psutil.swap_memory().used;self.done=threading.Event();self.lock=threading.Lock()
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
    def sample(self):
        v=psutil.virtual_memory();s=psutil.swap_memory();children=[]
        for pid in list(self.pids):
            try:p=psutil.Process(pid);children.append(dict(pid=pid,RSS=p.memory_info().rss))
            except psutil.NoSuchProcess:pass
        allowed=set(self.pids)|{os.getpid()};external=[]
        for p in psutil.process_iter(['pid','ppid','name']):
            if p.info['pid'] not in allowed and p.info['ppid']!=os.getpid() and any(n in (p.info['name'] or '').lower() for n in ('python','gurobi')):external.append(p.info)
        r=dict(UTC=datetime.now(timezone.utc).isoformat(),perf=time.perf_counter(),elapsed=time.perf_counter()-self.begin,phase=self.phase,parent_RSS=psutil.Process().memory_info().rss,pricing_RSS=sum(x['RSS'] for x in children),pricing_processes=children,available_RAM=v.available,total_RAM=v.total,swap_used=s.used,swap_growth=s.used-self.baseline,CPU_percent=psutil.cpu_percent(),external=external)
        with self.lock:
            self.rows.append(r)
            path=OUT/'DW_RESOURCE_TIMELINE.csv';exists=path.exists()
            with path.open('a',encoding='utf8',newline='') as f:
                flat=dict(r,pricing_processes=json.dumps(r['pricing_processes']),external=json.dumps(r['external']));writer=csv.DictWriter(f,fieldnames=list(flat))
                if not exists:writer.writeheader()
                writer.writerow(flat)
        # The preregistered safety gate applies throughout worker residency.
        reasons=[]
        if v.available<resource_threshold(v.total):reasons.append('AVAILABLE_RAM_BELOW_GATE')
        if s.used-self.baseline>2*1024**3:reasons.append('SEVERE_PAGEFILE_GROWTH_OVER_2_GIB')
        if external:reasons.append('EXTERNAL_HEAVY_PROCESS')
        if STOP.exists():reasons.append('USER_STOP_REQUEST')
        if reasons:self.failed.extend(reasons);self.stop_event.set()
        return r
    def watch(self):
        while not self.done.wait(1):self.sample()
    def close(self):
        self.done.set();self.thread.join();self.sample()
    def summary(self,rows):
        return dict(observed_per_process_peak_RSS={str(pid):max((p['RSS'] for r in rows for p in r['pricing_processes'] if p['pid']==pid),default=0) for pid in self.pids},observed_total_pricing_peak_RSS=max((r['pricing_RSS'] for r in rows),default=0),observed_parent_peak_RSS=max((r['parent_RSS'] for r in rows),default=0),min_available_RAM=min((r['available_RAM'] for r in rows),default=None),physical_RAM=rows[0]['total_RAM'] if rows else None,max_pagefile_growth=max((r['swap_growth'] for r in rows),default=None),max_CPU_percent=max((r['CPU_percent'] for r in rows),default=None),sample_period_seconds=1,exact_unsampled_peak_not_claimed=True)
