"""Read-only resource admission; no inherited foreign-solve override."""
from .common import *
from .resources import resource_failures
from v42_m1_accel_vnext.native_state import inspect_live

def wait_admission(exp,phase):
    start=time.perf_counter();waited=False
    while True:
        sample=exp.monitor.sample();observed,blocked=inspect_live(exp.pids)
        failures=resource_failures(sample,exp.monitor.rows)
        write('DW_CONTINUATION_WAIT_RESOURCE.json',dict(status='WAIT_RESOURCE' if blocked or failures else 'ADMITTED',
            phase=phase,observed=observed,blocked=blocked,failures=failures,
            elapsed_wait=time.perf_counter()-start,native_wait_debit=0,foreign_control_calls=0))
        if not blocked and not failures:break
        if STOP.exists():raise InterruptedError('USER_STOP_AT_WAIT_RESOURCE')
        if not waited:
            waited=True
            if getattr(exp,'master',None) is not None and hasattr(exp,'persistent_adapter'):exp.suspend_models()
        exp.active_start=None;exp.cancel.clear();exp.monitor.failed.clear();time.sleep(2)
    exp.cancel.clear();exp.monitor.failed.clear()
    if getattr(exp,'runtime_suspended',False):
        exp.restore_models()
        if phase!='PRICING_MODEL_BUILD':exp.start_workers(4)
    return sample
