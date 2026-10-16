"""Fresh PR189 B1 solve. No scientific producer or numerical policy is changed.

V43 owns its permit, byte freeze, OS locks and output ledger. Shared ContextVars
are the existing extension point for a versioned campaign permit. Original
model guards remain in force; V43 adds sealed byte and live-worker checks.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import os
import sys
import threading
import time
import traceback
import psutil
from .common import *

def no_heavy_peer():
    conflicts = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.pid == os.getpid() or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe','python'): continue
            cmd = ' '.join(p.info['cmdline'] or []).lower()
            if any(x in cmd for x in ('v43.golden', 'audit_v42', 'native0', '.worker', 'm_stage', 'solve_v42')):
                conflicts.append(p.info)
        except psutil.Error: pass
    if conflicts: raise PermissionError('HEAVY_WORKER_CONFLICT:' + repr(conflicts))

def verified_freeze():
    freeze = read(DOC/'V43_BASELINE_AND_SOURCE_FREEZE.json')
    assert freeze['base_commit'] == BASE and freeze['Worker'] == freeze['Threads'] == 1
    verify_records(freeze['sources'] + freeze['support'] + freeze['scientific_inputs'])
    for row in freeze['baseline_execution_sources']:
        verify_records([row['current']])
        assert row['current']['sha256'] == row['historical']['sha256']
    return freeze

@contextmanager
def permit(request):
    from v42_may_campaign import execution as legacy
    from v42_may_campaign_native90 import execution as inherited
    from v42_may_campaign_native90 import budget as inherited_budget
    from v42_may_campaign.common import exclusive_lock
    if request['arm'] != 'B1' or request['day'] != '2025-05-01' or request['Threads'] != 1:
        raise PermissionError('GOLDEN_B1_MAY01_ONLY')
    verified_freeze()
    no_heavy_peer()
    original_guard = inherited.guard
    def guard(model):
        verified_freeze()
        no_heavy_peer()
        original_guard(model)
    with ExitStack() as stack:
        # The original Native90 workers use the same global slots. V43 owns all
        # three, preventing a legacy B2 dispatch while this Worker is live.
        locks = [Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'), RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks: stack.enter_context(exclusive_lock(path))
        token = legacy._active.set(dict(request=request, manifest=dict(schema='V43_GOLDEN_PR189_V1'),
            manifest_sha=sha(DOC/'V43_BASELINE_AND_SOURCE_FREEZE.json'), worker_slot=None))
        prior = (legacy.guard,inherited.guard,inherited_budget.guard)
        legacy.guard = inherited.guard = inherited_budget.guard = guard
        try: yield
        finally:
            legacy.guard,inherited.guard,inherited_budget.guard = prior
            legacy._active.reset(token)

def run():
    from v42_may_campaign_native90.a_stage import run as original_run
    from v42_may_campaign_native90.budget import DateBudget
    req = read(DOC/'GOLDEN_REQUEST.json')
    attempt = Path(req['root'])
    if attempt.exists(): raise PermissionError('FRESH_INDEPENDENT_ATTEMPT_REQUIRED')
    verified_freeze()
    no_heavy_peer()
    attempt.mkdir(parents=True)
    tmp=attempt/'tmp'; tmp.mkdir()
    os.environ.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE='1')
    __import__('tempfile').tempdir=str(tmp)
    atomic(attempt/'request.json',req)
    active = dict(state='RUNNING_GATE_A',pid=os.getpid(),process_created=psutil.Process().create_time(),
        started_UTC=now(),request=record(attempt/'request.json'),Source=record(DOC/'V43_BASELINE_AND_SOURCE_FREEZE.json'),
        source_commit=git('rev-parse','HEAD').decode().strip(), Worker=1, Threads=1,
        Gate_A_PASS=False,Gate_B_PASS=False,Gate_C_PASS=False,Gate_D_PASS=False,May31_PASS=False)
    atomic(attempt/'START.json',active);atomic(DOC/'CHECKPOINT.json',active)
    latest = {}
    finished = threading.Event()
    def progress(value):
        latest.update(value)
        atomic(attempt/'progress.json',dict(latest,UTC=now(),pid=os.getpid()))
        if (attempt/'STOP_REQUESTED.json').exists():
            from v42_may_campaign import execution
            scope=execution._model.get()
            if scope is not None: scope['model'].terminate()
    def heartbeat():
        while not finished.wait(10):
            p=psutil.Process()
            atomic(attempt/'HEARTBEAT.json',dict(UTC=now(),pid=os.getpid(),RSS_bytes=p.memory_info().rss,
                CPU_seconds=sum(p.cpu_times()[:2]), latest=dict(latest), source_commit=active['source_commit']))
    class Budget(DateBudget):
        def check(self,reserve=0):
            if (attempt/'STOP_REQUESTED.json').exists(): raise RuntimeError('V43_OFFICIAL_STOP_REQUESTED')
            return super().check(reserve)
    budget=Budget(attempt/'NATIVE_RUNTIME_LEDGER.json',progress=progress,native_limit=5400,wall_limit=None)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    result = dict(PASS=False, state='FAILED',Native_seconds=0)
    try:
        with permit(req):
            from .causal import check as causal_check
            causal=causal_check(req,attempt/'CAUSAL_NATIVE0')
            result=original_run(req,budget,progress)
            atomic(attempt/'PLANNING_RESULT.json',result)
            if result.get('PASS'):
                progress(dict(phase='GOLDEN_ORIGINAL_FIXED_REPLAY_FRESH_AC96'))
                from v42_may_campaign_native90.operations import run as original_operations
                ops=original_operations(req,result,progress)
                atomic(attempt/'GOLDEN_OPERATIONS.json',ops)
                result=dict(result,Fresh_AC96_PASS=ops['PASS'],Original_fixed_replay_only=True,
                    reproduction_numerical_PASS=bool(ops['PASS']),
                    Gate_A_PASS=bool(ops['PASS'] and causal['complete_causal_certification']),
                    Actual_event_prefix_continuity='NOT_CERTIFIED',
                    Gate_B_PASS=False,Gate_C_PASS=False,Gate_D_PASS=False)
            else: result['Gate_A_PASS']=False
    except BaseException as error:
        result=dict(result,PASS=False,Gate_A_PASS=False,error=repr(error),traceback=traceback.format_exc())
    finally:
        finished.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),Native_seconds=budget.native_used,total_wall_seconds=budget.wall(),
            ledger=record(attempt/'NATIVE_RUNTIME_LEDGER.json'),past_attempts_preserved=True)
        atomic(attempt/'RESULT.json',result)
        state=dict(active,state='GATE_A_PASS' if result.get('Gate_A_PASS') else 'GATE_A_FAILED_REPAIR_REQUIRED',
            finished_UTC=now(),active_PID=None,result=record(attempt/'RESULT.json'),Gate_A_PASS=result.get('Gate_A_PASS',False))
        atomic(DOC/'CHECKPOINT.json',state)
        atomic(attempt/'RECONCILIATION.json',dict(UTC=now(),Native_seconds=budget.native_used,
            inflight=budget.inflight,Native_runtime_known=not any(c.get('runtime_unavailable') for c in budget.calls),
            calls=len(budget.calls),source_editing_locked=False,raw_preserved=True))
    print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__': run()
