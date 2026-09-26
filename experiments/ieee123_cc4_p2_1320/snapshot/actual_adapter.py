"""Exact original final ETA95/QSAFE V2 worker, new accepted joint/output paths."""
from pathlib import Path
import json
import os
import sys
import time
import traceback
import runtime_environment as env
from authority_recovery import sha,install_validator

PRODUCTION=env.ROOT
ORIGINAL=env.ORIGINAL/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
OUT=PRODUCTION/'actual'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(v,indent=2,default=str),encoding='utf-8')

def stage():
    OUT.mkdir(parents=True,exist_ok=True);copied=[]
    candidates=list(ORIGINAL.glob('*.py'))+list((ORIGINAL/'frozen_code').rglob('*'))+list((ORIGINAL/'evidence').rglob('*'))
    candidates += [ORIGINAL/n for n in ['METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','PERFORMANCE_FREEZE.json','BATTERY_EFFICIENCY_AUTHORITY.json']]
    for p in candidates:
        if not p.is_file():continue
        target=OUT/p.relative_to(ORIGINAL);target.parent.mkdir(parents=True,exist_ok=True)
        if not env.exists(target):target.write_bytes(p.read_bytes())
        assert sha(p)==sha(target)
        copied.append(dict(original=str(p),copy=str(target),sha256=sha(target)))
    save(OUT/'ROUND2_EXACT_CODE_COPIES.json',dict(status='PASS',files=copied,numerical_code_changes=0))

def main(day,case,runs):
    env.install('ACTUAL');stage()
    # No DA processes or subsequent days inherit the Actual phase.
    os.environ.pop('B3_2R_DAY',None)
    acceptance=read(PRODUCTION/'closure'/day/'ACCEPTANCE.json');assert acceptance['status']=='PASS'
    da=Path(acceptance['final_dayahead']);runs=da.parents[2]
    receipt=read(da/'DAYAHEAD_RECEIPT.json');assert receipt['status']=='COMPLETE'
    frozen=read(da/'FROZEN_JOINT_DECISION.json');h=sha(da/'FROZEN_JOINT_DECISION.json')
    assert frozen['decision_SHA']==receipt['decision_SHA']
    assert not read(da/'FRESH_RESULT.json')['summary']['physical_violation']
    from native_runtime_paths import install
    install(OUT/'native'/day)
    # The sealed adapter computes ROOT from its old directory depth; relocate
    # those path globals before importing any numeric worker.
    sys.path.insert(0,str(OUT))
    import binding
    binding.ROOT=env.ORIGINAL;binding.RUN=runs
    import common
    common.ROOT=env.ORIGINAL;common.RUN=runs
    # common.save checks resolved ancestry, so use the same physical alias.
    common.OUT=OUT.resolve();binding.OUT=OUT.resolve()
    # Retain a strict write audit over this complete extension namespace,
    # including native scratch and transport receipts outside Actual's subdir.
    def protect_extension():
        def check(p):
            if isinstance(p,(str,bytes,os.PathLike)):
                key=env.norm(p)
                if not any(key==r or key.startswith(r+os.sep) for r in env.WRITE_ROOTS):
                    if key!=env.norm('NUL'):raise PermissionError('ROUND2_WRITE_OUTSIDE_EXTENSION:'+str(p))
        def hook(event,args):
            if event=='open':
                p,mode,flags=args
                if (mode and any(c in mode for c in 'wax+')) or (flags and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):check(p)
            elif event in ('os.remove','os.rmdir','os.mkdir'):check(args[0])
            elif event in ('os.rename','os.replace'):check(args[0]);check(args[1])
        sys.addaudithook(hook)
    common.protect=protect_extension
    import performance_worker
    worker=performance_worker.install()
    import input_adapter
    input_adapter.RUN=runs
    import v41r4_loop_runtime as runtime
    def verified_decision(d,p,expected_current=None):
        assert (d,p)==(day,'B3')
        assert sha(da/'FROZEN_JOINT_DECISION.json')==h
        return frozen['decision'],receipt
    runtime.verify_old_or_current=verified_decision
    def input_for(d,p,ctx,eta,authority):
        assert (d,p)==(day,'B3')
        ready=OUT/'common_inputs'/d/p/'READY.json'
        if ready.exists():
            assert read(ready)['decision_SHA']==frozen['decision_SHA']
            before=common.read(ready.parent/'DA_FRESH_INPUT_SNAPSHOT.json')
            assert all(common.sha(k)==v for k,v in before.items())
            return ready.parent
        return input_adapter.prepare(d,p,ctx,eta,authority,worker.frozen.independent_audit)
    worker.namespace.update(RUN=runs,ROOT=env.ORIGINAL,input_for=input_for)
    from actual_numerical_recovery import install as numerical_recovery
    numerical_recovery(worker,common,OUT,day)
    started=time.time();status=PRODUCTION/'status'/f'{day}_Actual.json'
    save(status,dict(status='RUNNING',started_at=started,source_joint_sha256=h))
    try:
        worker.namespace['main'](day,['B3'])
        folder=OUT/'replays'/day/'B3';done=common.read(folder/'COMPLETE.json')
        assert done['status']=='PASS'
        import numpy as np
        x=common.arrays(folder/'ETA95_QSAFE_ACTUAL/EXECUTION.npz');p=x['P_EXEC'];q=x['Q_EXEC'];angles=2*np.pi*np.arange(16)/16
        norm=float(np.max(np.hypot(p,q)/400));poly=float(np.max((p[:,:,None]*np.cos(angles)+q[:,:,None]*np.sin(angles))/(400*np.cos(np.pi/16))));active=float(np.max(np.abs(p))/300)
        assert max(norm,poly,active)<=1+1e-9
        for k,v in common.read(OUT/'common_inputs'/day/'B3/DA_FRESH_INPUT_SNAPSHOT.json').items():assert common.sha(k)==v
        worker.verify_method()
        save(status,dict(status='COMPLETE',wall_seconds=time.time()-started,source_joint_sha256=h,
            method_sha256=sha(OUT/'METHOD_FREEZE.json'),summary=done,maximum_PCS_norm_utilization=norm,
            maximum_PCS_polygon_utilization=poly,maximum_active_power_utilization=active,scheduling_optimizer_calls=0))
    except BaseException as e:
        save(status,dict(status='FAILED',error=repr(e),traceback=traceback.format_exc(),wall_seconds=time.time()-started));raise
    finally:env.save_audit(PRODUCTION/'io'/f'{day}_Actual.json')


