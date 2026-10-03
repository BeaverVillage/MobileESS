import csv
import json
import threading
import time
import os
from .common import OUT,ENV,write
from v42_single_thread.resources import snapshot

def gate(label):
    import psutil
    psutil.cpu_percent(interval=.1)
    value=snapshot();value['environment']={k:os.environ.get(k) for k in ENV}
    value['PASS']=all(value['environment'][k]=='1' for k in ENV) and not any(not p['self'] for p in value['heavy_processes'])
    write('RESOURCE_GATE_'+label+'.json',value)
    if not value['PASS']:raise RuntimeError('SINGLE_WORKER_GATE_BLOCKED:'+label)
    return value

class Resources:
    """Memory buffer only while optimization is active; no callback process scans."""
    def __init__(self):
        self.begin=time.perf_counter();self.rows=[];self.errors=[];self.violations=[];self.stop=threading.Event();self.model=None
        self.sample('before_model_read');self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
    def sample(self,phase):
        value=snapshot();value.update(phase=phase,wall_seconds=time.perf_counter()-self.begin)
        external=[p for p in value['heavy_processes'] if not p['self']]
        if external:
            self.violations.append(dict(UTC=value['UTC'],external=external))
            if self.model is not None:self.model.terminate()
        self.rows.append(value)
    def watch(self):
        while not self.stop.wait(5):
            try:self.sample('periodic')
            except Exception as error:self.errors.append(repr(error))
    def close(self,status,phase_events):
        self.model=None;self.stop.set();self.thread.join(timeout=2);self.sample('after_terminal_and_audits')
        fields=list(self.rows[0])
        with (OUT/'M1_DEGENMOVES0_RESOURCE_TIMELINE.csv').open('w',encoding='utf8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            for row in self.rows:writer.writerow(dict(row,heavy_processes=json.dumps(row['heavy_processes'],ensure_ascii=False)))
        result=dict(status=status,observed_peak_RSS=max(r['process_RSS'] for r in self.rows),observed_minimum_free_RAM=min(r['system_RAM_free'] for r in self.rows),observed_maximum_swap_used=max(r['swap_used'] for r in self.rows),sample_count=len(self.rows),sample_period_seconds=5,exact_peak_not_claimed=True,worker_processes=1,Gurobi_Threads=1,external_heavy_processes=self.violations,errors=self.errors,sequential_policy_PASS=not self.violations and not self.errors,OS_support_threads_not_solver_workers=True,phase_events=phase_events,callback_resource_scans=0,resource_rows_written_after_terminal_only=True)
        write('M1_DEGENMOVES0_RESOURCE_SUMMARY.json',result);return result
