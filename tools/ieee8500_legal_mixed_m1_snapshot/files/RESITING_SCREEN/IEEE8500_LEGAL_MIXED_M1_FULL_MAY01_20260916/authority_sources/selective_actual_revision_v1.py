"""Versioned input routing only; exact unchanged Actual V2 numerical worker."""
from pathlib import Path
import sys,shutil,json,time,hashlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import restoration_revision_v1 as revision
OUT=revision.NEWAC

def stage():
    OUT.mkdir(parents=True,exist_ok=True)
    original=revision.OLDAC
    for p in original.glob('*.py'):
        if not (OUT/p.name).exists():shutil.copy2(p,OUT/p.name)
        assert revision.sha(p)==revision.sha(OUT/p.name)
    for name in ('METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','PERFORMANCE_FREEZE.json','BATTERY_EFFICIENCY_AUTHORITY.json'):
        if not (OUT/name).exists():shutil.copy2(original/name,OUT/name)
        assert revision.sha(original/name)==revision.sha(OUT/name)
    for name in ('frozen_code','evidence'):
        if not (OUT/name).exists():shutil.copytree(original/name,OUT/name)
    revision.save(OUT/'RESTORATION_EXECUTION_BINDING.json',dict(status='FROZEN',rule=revision.record(revision.OUT/'RULE_FREEZE.json'),adapter=revision.record(__file__),
        numerical_method=revision.record(OUT/'METHOD_FREEZE.json'),numerical_implementation=revision.record(OUT/'EXECUTION_BINDING.json'),
        scope='Only accepted DA input path and new output namespace routing; numerical Actual V2 files copied byte-exact',frozen_at=time.time()))

def main(day,policy):
    revision.seal_check()
    unit=revision.read(revision.OUT/day/policy/'ACCEPTANCE.json')
    assert unit['status']=='PASS' and unit['actual_disposition'] in ('RERUN_ACTUAL_REQUIRED','NEW_ACTUAL_REQUIRED')
    revision.verify(unit['new_joint']);original_joint=Path(unit['new_joint']['path'])
    # A virtual input tree contains only this accepted policy-day. Originals remain immutable.
    overlay=OUT/'accepted_inputs';da=overlay/day/policy/'dayahead'
    if not da.exists():shutil.copytree(original_joint.parent,da)
    assert revision.sha(da/'FROZEN_JOINT_DECISION.json')==unit['new_joint']['sha256']
    receipt=revision.read(da/'FROZEN_JOINT_DECISION.json')
    start=time.time()
    sys.path.insert(0,str(OUT))
    import performance_worker
    worker=performance_worker.install()
    import input_adapter,common,binding
    input_adapter.RUN=overlay
    import v41r4_loop_runtime
    def verified_decision(d,p,expected_current=None):
        assert (d,p)==(day,policy)
        revision.verify(unit['new_joint'])
        assert revision.sha(da/'FROZEN_JOINT_DECISION.json')==unit['new_joint']['sha256']
        return receipt['decision'],dict(status='COMPLETE',decision_SHA=receipt['decision_SHA'],restoration_acceptance=revision.record(revision.OUT/day/policy/'ACCEPTANCE.json'))
    v41r4_loop_runtime.verify_old_or_current=verified_decision
    def input_for(d,p,ctx,eta,authority):
        ready=OUT/'common_inputs'/d/p/'READY.json'
        if ready.exists():
            before=common.read(ready.parent/'DA_FRESH_INPUT_SNAPSHOT.json')
            assert all(common.sha(k)==v for k,v in before.items())
            return ready.parent
        return input_adapter.prepare(d,p,ctx,eta,authority,worker.frozen.independent_audit)
    worker.namespace.update(RUN=overlay,input_for=input_for)
    # main's reused outer verifier is replaced by the new closure's exact identity verifier;
    # the frozen numeric main, causal Q controller, actuator and independent audit stay identical.
    worker.namespace['main'](day,[policy])
    import numpy as np
    folder=OUT/'replays'/day/policy
    done=common.read(folder/'COMPLETE.json')
    x=common.arrays(folder/'ETA95_QSAFE_ACTUAL/EXECUTION.npz');p=x['P_EXEC'];q=x['Q_EXEC'];angles=2*np.pi*np.arange(16)/16
    norm=float(np.max(np.hypot(p,q)/400));poly=float(np.max((p[:,:,None]*np.cos(angles)+q[:,:,None]*np.sin(angles))/(400*np.cos(np.pi/16))));active=float(np.max(np.abs(p))/300)
    assert norm<=1+1e-9 and poly<=1+1e-9 and active<=1+1e-9
    done.update(maximum_PCS_norm_utilization=norm,maximum_PCS_polygon_utilization=poly,maximum_active_power_utilization=active,method_version=common.read(OUT/'METHOD_FREEZE.json')['version'])
    common.save(folder/'COMPLETE.json',done)
    for k,h in common.read(OUT/'common_inputs'/day/policy/'DA_FRESH_INPUT_SNAPSHOT.json').items():assert common.sha(k)==h
    worker.verify_method()
    common.save(folder/'CANDIDATE_RECEIPT.json',dict(status='COMPLETE',day=day,policy=policy,actual_disposition='NEW' if unit['actual_disposition']=='NEW_ACTUAL_REQUIRED' else 'RERUN',
        parent_acceptance=revision.record(revision.OUT/day/policy/'ACCEPTANCE.json'),source_joint=unit['new_joint'],method_SHA=common.sha(OUT/'METHOD_FREEZE.json'),execution_binding_SHA=common.sha(OUT/'EXECUTION_BINDING.json'),
        adapter_SHA=revision.sha(__file__),files={str(f.relative_to(folder)):common.sha(f) for f in folder.rglob('*') if f.is_file() and f.name!='CANDIDATE_RECEIPT.json'},scheduling_optimizer_calls=0,started_at=start,completed_at=time.time()))
    print('SELECTIVE_ACTUAL_COMPLETE',day,policy,flush=True)

if __name__=='__main__':
    if sys.argv[1]=='stage':stage()
    else:main(sys.argv[1],sys.argv[2])
