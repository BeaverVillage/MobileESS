from datetime import datetime,timezone
from time import time
from v42_pr134_b1.common import read,atomic,record
from v42_a_stage_early.native import BudgetStop
from .policy import OUT,POLICY

def establish():
    p=OUT/'CONTINUATION_BUDGET.json'
    if p.exists():return read(p)
    start=time();r=dict(PASS=True,start_unix=start,deadline_unix=start+POLICY['continuation_wall_guard_seconds'],
        actual_start_UTC=datetime.fromtimestamp(start,timezone.utc).isoformat(),immutable=True,budget_resets=0,
        per_day_native_seconds=3600,total_native_seconds=14400,practical_wall_target_seconds=1800,
        wall_guard_seconds=28800,wall_guard_is_overhead_safety_cap_not_30_minute_acceptance=True,
        authority=[record(OUT.parents[1]/'v42_pr134_b1/common.py'),
                   record(OUT.parent/'v42_single_worker_single_thread_a1_m1/A1_SINGLE_THREAD_SOLVE_RESULT.json')],
        old_PR180_budget_not_reset=True,new_authorization='CONTINUATION TASK — A-STAGE ACCEPTANCE AND FOUR-DAY VALIDATION')
    atomic(p,r);return r

class Budget:
    def __init__(self,day):
        self.record=establish();self.day=day;self.native_seconds=0.;self.started=time()
    def remaining(self):
        value=min(self.record['deadline_unix']-time(),3600-self.native_seconds)
        if value<=0:raise BudgetStop('NEW_CONTINUATION_DAY_NATIVE_OR_WALL_BUDGET_EXHAUSTED')
        return value
    def charge(self,seconds):
        self.native_seconds+=seconds
        atomic(OUT/self.day/'NATIVE_BUDGET_LEDGER.json',dict(PASS=True,charged_native_seconds=self.native_seconds,
            limit=3600,immutable_parent=record(OUT/'CONTINUATION_BUDGET.json')))
    def accounted(self):return time()-self.started
    def allocation(self,seconds):return Allocation(self,seconds)

class Allocation:
    def __init__(self,parent,seconds):self.parent=parent;self.limit=seconds;self.used=0.;self.record=parent.record
    def remaining(self):
        r=min(self.parent.remaining(),self.limit-self.used)
        if r<=0:raise BudgetStop('CONTINUATION_COMPONENT_ALLOCATION_EXHAUSTED')
        return r
    def charge(self,seconds):self.used+=seconds;self.parent.charge(seconds)
    def accounted(self):return self.parent.accounted()
