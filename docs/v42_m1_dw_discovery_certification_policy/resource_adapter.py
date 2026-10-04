"""Preregistered resource-gate continuation; frozen scientific code unchanged."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v42_dw_policy.common import *
from v42_dw_policy.run import Experiment as Frozen
class Experiment(Frozen):
    def __init__(self):
        freeze=read(OUT/'RESOURCE_ADAPTER_FREEZE.json');assert sha(Path(__file__))==freeze['adapter_SHA']
        self.is_resume='--resume' in sys.argv;self.initial_selection_done=False
        super().__init__()
        if not self.is_resume:
            old=read(OUT/'worker4_memory_gate/DW_POLICY_CANARY_FINAL.json');prior=read(OUT/'RMP_RECEIPT_0001.json');assert prior['status']==11 and prior['dual_SHA'] is None and old['new_pricing_calls']==0
            self.rmps.insert(0,prior);self.intervals.insert(0,tuple(prior['interval']));self.current_round=1;self.carried_elapsed=old['total_elapsed_including_build_audit'];self.canaries.insert(0,read(OUT/'RESOURCE_GATE4_PRESERVED.json'))
        self.commit=subprocess.check_output(['git','log','-1','--format=%H','--','docs/v42_m1_dw_discovery_certification_policy/resource_adapter.py'],cwd=ROOT,text=True).strip();self.save()
    def launch_with_downgrade(self,count):
        if not self.initial_selection_done:count=min(count,2);self.initial_selection_done=True
        while True:
            first=len(self.monitor.rows)
            try:
                self.start_workers(count);self.monitor.sample()
                if self.cancel.is_set() or self.monitor.failed:raise RuntimeError('RESOURCE_GATE_DURING_WORKER_BUILD:'+repr(self.monitor.failed))
                return
            except Exception as error:
                stats=self.monitor.summary(self.monitor.rows[first:]);self.canaries.append(dict(round=self.current_round,workers=count,PASS=False,stage='WORKER_BUILD',error=repr(error),**stats));write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=count,resource_PASS=False));self.cancel.set();self.close_workers()
                if count==1:raise
                count//=2
    def solve_master(self,kind):
        while True:
            value=super().solve_master(kind)
            if value is not None:return value
            if STOP.exists() or not self.monitor.failed or self.workers==1:return None
            count=self.workers;self.canaries.append(dict(round=self.current_round,workers=count,PASS=False,stage='RMP_RESOURCE_GATE',failures=list(set(self.monitor.failed)),**self.monitor.summary(self.monitor.rows)));write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=count,resource_PASS=False));self.close_workers();self.stop=None;self.launch_with_downgrade(count//2)
if __name__=='__main__':Experiment().run()
