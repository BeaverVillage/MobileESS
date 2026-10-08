"""Reuse audited native machinery, with an independent D: budget/permit."""
from time import perf_counter
import os
from .policy import OUT,STATIC,DAY
from .execution import verify,native_scope
from .audit import processes
from v42_pr134_b1.common import atomic,read
from v42_a_stage_early.native import BudgetStop

class Budget:
    def __init__(self):self.used=0.;self.native=None;self.call_cap=None;self.call_start=0.
    def accounted(self):return self.used
    def remaining(self):
        live=0.
        if self.native is not None and getattr(self.native,'live_model',None) is not None:
            try:live=float(self.native.live_model.Runtime)
            except Exception:pass
        remaining=3600-self.used-live
        if self.call_cap is not None:remaining=min(remaining,self.call_cap-(self.used-self.call_start)-live)
        if remaining<=0:raise BudgetStop('MAY12_NEW_CUMULATIVE_NATIVE_BUDGET_EXHAUSTED')
        return remaining
    def charge(self,seconds):
        self.used+=seconds
        atomic(OUT/'NEW_NATIVE_BUDGET_LEDGER.json',dict(native_limit=3600,actual_Runtime=self.used,old_budget_not_modified=True))

def sample():
    import psutil
    me=psutil.Process();v=psutil.virtual_memory()
    return dict(A_process_RSS_bytes=me.memory_info().rss,system_available_bytes=v.available,
        system_memory_percent=v.percent,telemetry_only=True,memory_cap=False)

def start_gate():
    other=[]
    for p in processes():
        if p['pid']==os.getpid():continue
        args=' '.join(p['argv'] or [])
        if not is_read_only_host_monitor(p) and any(x in args for x in ('v42_', 'm1-', 'mess-')):other.append(p)
    atomic(OUT/'RESOURCE_START_GATE.json',dict(PASS=not other,other_possible_native_workers=other,
        no_processes_modified=True,RAM_threshold=False,own_PID=os.getpid(),observed=processes()))
    if other:raise BudgetStop('MAY12_RESOURCE_PENDING_OTHER_NATIVE_WORKERS')

def is_read_only_host_monitor(process):
    argv=process.get('argv') or []
    try:i=argv.index('-m')
    except ValueError:return False
    return argv[i+1:i+3]==['v42_pr134_b1.host','monitor']

def create():
    import v42_a_stage_acceptance.native as inherited
    inherited.OUT=OUT;inherited.STATIC=STATIC;inherited.verify=verify;inherited.native_scope=native_scope
    inherited.active_freeze=lambda:OUT/'SOURCE_FREEZE.json';inherited.sample=sample
    b=Budget()
    class Native(inherited.Native):
        def solve(self,snapshot,folder,component):
            if component not in ('ORIGINAL_P1','LOCAL_PRICING','INTEGER_CONTROL'):raise PermissionError('P1_ONLY_NATIVE_COMPONENTS')
            start_gate();b.call_start=b.used
            b.call_cap=60 if component=='LOCAL_PRICING' else 600 if component=='ORIGINAL_P1' else max(0.,3600-b.used-30)
            started=perf_counter()
            try:return super().solve(snapshot,folder,component)
            finally:
                b.call_cap=None
                atomic(OUT/'NEW_NATIVE_CALLS.json',dict(calls=self.calls,actual_Runtime=b.used,
                    actual_Work=sum(c.get('Work') or 0 for c in self.calls),sequential=True,old_native_Runtime=233.89299654960632,
                    latest_native_build_solve_and_persist_wall=perf_counter()-started))
    n=Native(b,DAY);b.native=n
    return n
