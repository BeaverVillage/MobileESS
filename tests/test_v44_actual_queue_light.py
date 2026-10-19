from copy import deepcopy
from types import SimpleNamespace
import pytest
import v44_recovery_r029
from v44_actual_queue_light import build
from v44.svr12 import scope

def exercise(optimized,callback=None):
    with scope():
        from v42_voltage_control.timecontrol import CommonClock
        source=CommonClock.settle_slot
        counts=dict(queue=0,solves=0);time=[0];events=[dict(absolute_seconds=5,handle=1)]
        def clockpart(divisor):
            def value(*args):
                if args:time[0]=(int(args[0])*3600+time[0]%3600 if divisor==3600 else int(time[0]//3600)*3600+float(args[0]))
                return int(time[0]//3600) if divisor==3600 else time[0]%3600
            return value
        def solve():
            counts['solves']+=1
            events[:]=[r for r in events if r['absolute_seconds']>time[0]]
        def queue(e):counts['queue']+=1;return sorted(deepcopy(events),key=lambda r:r['absolute_seconds'])
        def callback_action(*args):
            if not any(r['handle']==2 for r in events) and time[0]<10:
                events.append(dict(absolute_seconds=10,handle=2))
        solution=SimpleNamespace(Hour=clockpart(3600),Seconds=clockpart(1),ControlMode=lambda:2,
            MaxControlIterations=lambda:100,MaxIterations=lambda:15,Converged=lambda:True,
            ControlActionsDone=lambda:True,EventLog=lambda:[],ControlIterations=lambda:1,
            Iterations=lambda:1,SolveSnap=solve)
        e=SimpleNamespace(Solution=solution);c=CommonClock('ACTUAL','2025-05-02');c.engine=e
        # Copy globals: keep the live implementation untouched for other tests.
        from types import FunctionType
        adapted=FunctionType(source.__code__,dict(source.__globals__,queue=queue),source.__name__,source.__defaults__)
        adapted.__kwdefaults__=source.__kwdefaults__
        # build() reads the original source; put the same fake queue in its copied namespace.
        if optimized:
            adapted=build(source);adapted.__globals__['queue']=queue
        bank=SimpleNamespace(observe_at=callback_action) if callback=='bank' else None
        observer=callback_action if callback=='observer' else None
        result=adapted(c,e,0,bank=bank,observer=observer)
        return result,counts

def test_no_callback_reuses_only_unchanged_immediate_queue_read():
    old,oc=exercise(False);new,nc=exercise(True)
    assert old==new and oc['solves']==nc['solves']==2
    assert nc['queue']<oc['queue']

@pytest.mark.parametrize('callback',['observer','bank'])
def test_callback_queue_changes_keep_original_reads_and_extra_solves(callback):
    old,oc=exercise(False,callback);new,nc=exercise(True,callback)
    assert old==new and oc==nc
    assert nc['solves']==3
