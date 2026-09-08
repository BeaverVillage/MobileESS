"""Actual-only entry point using the frozen numerical worker without editing it."""
from binding import *
import time, traceback, inspect, shutil
import numpy as np
verify_method()
EXECUTION_START_SHA=sha(OUT/'EXECUTION_BINDING.json')
import worker as frozen
import robust_search
frozen.run_qsafe=robust_search.run_qsafe
from input_adapter import configure_read_only, prepare
frozen.configure=configure_read_only

def input_for(day,policy,ctx,eta,da):
    p=OUT/'common_inputs'/day/policy
    old=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_v1/common_inputs'/day/policy
    if not p.exists() and (old/'READY.json').exists():
        upstream=read(old/'DA_FRESH_INPUT_SNAPSHOT.json');assert all(sha(k)==v for k,v in upstream.items())
        source_files={str(x.relative_to(old)):sha(x) for x in old.rglob('*') if x.is_file()}
        shutil.copytree(old,p)
        assert all(sha(p/name)==h and sha(old/name)==h for name,h in source_files.items())
        save(p/'V1_COMMON_INPUT_REUSE.json',dict(status='PASS',source=str(old),files=source_files,Actual_AC_replayed_under_new_method=True))
    if (p/'READY.json').exists():
        before=read(p/'DA_FRESH_INPUT_SNAPSHOT.json')
        assert all(sha(k)==v for k,v in before.items())
        return p
    return prepare(day,policy,ctx,eta,da,frozen.independent_audit)

source=inspect.getsource(frozen.main)
replacements=[
    ("assert day in read(OUT/'START_COHORT.json')['days'];eta,da=authority()", "assert day in read(OUT/'METHOD_FREEZE.json')['all_days'];eta,da=authority()"),
    ("for stage in ('ACTUAL','DAYAHEAD'):","for stage in ('DAYAHEAD',):"),
    ("folder.mkdir(parents=True,exist_ok=True);root=RUN/day/policy;ac=root/'actual'", "folder.mkdir(parents=True,exist_ok=True);root=RUN/day/policy;historical=root/'actual';has_original=(historical/'ACTUAL_RECEIPT.json').exists();ac=input_for(day,policy,ctx,eta,da)"),
    ("identity=read(ac/'grid/OPENDSS_SUMMARY.json')['schedule_sha256']", "identity=read(ac/'READY.json')['identity']"),
    ("save(folder/'ORIGINAL_ACTUAL/REFERENCE.json',dict(namespace='ORIGINAL_ACTUAL',authoritative_root=str(ac),grid_SHA=sha(ac/'grid/OPENDSS_PHASE_ARRAYS.npz'),receipt_SHA=sha(ac/'ACTUAL_RECEIPT.json')))", "save(folder/'ORIGINAL_ACTUAL/REFERENCE.json',dict(namespace='ORIGINAL_ACTUAL',available=has_original,authoritative_root=str(historical),grid_SHA=sha(historical/'grid/OPENDSS_PHASE_ARRAYS.npz') if has_original else None,receipt_SHA=sha(historical/'ACTUAL_RECEIPT.json') if has_original else None))"),
    ("original=arrays(ac/'grid/OPENDSS_PHASE_ARRAYS.npz');new=arrays(bpath/'OPENDSS_PHASE_ARRAYS.npz')", "new=arrays(bpath/'OPENDSS_PHASE_ARRAYS.npz');original=arrays(historical/'grid/OPENDSS_PHASE_ARRAYS.npz') if has_original else new"),
    ("kind='CONTROL_REUSE_VERIFIED'", "kind='CONTROL_REUSE_VERIFIED' if has_original else 'CONTROL_NEW_COMMON_BINDING'"),
    ("all_grid_arrays_bit_identical=identical", "all_grid_arrays_bit_identical=identical if has_original else None,historical_Actual_available=has_original"),
    ("run_qsafe(act,ctx.electrical.voltage,ctrajectory,values(f,'connected'),da,cpath)", "run_qsafe(act,ctx.electrical.voltage,ctrajectory,values(f,'connected'),da,cpath,q_da=values(f,'Q_CMD'))"),
]
for old,new in replacements:
    assert source.count(old)==1, ('ADAPTER_ANCHOR_MISMATCH',old)
    source=source.replace(old,new)
source=source.replace('Q_ONLY_INFEASIBLE','ROBUST_Q_ONLY_UNRESOLVED').replace("kind='DIAGNOSTIC_CANDIDATE'","kind='FROZEN_ROBUST_ACTUAL'")
namespace={**vars(frozen),'input_for':input_for}
exec(compile(source,__file__+'::frozen_worker_adapter','exec'),namespace)

def main(day,policies):
    from v41r4_loop_runtime import verify_old_or_current
    method=verify_method()
    for policy in policies:
        assert read(RUN/'audit'/day/f'PHASE_{policy}_DA.json')['status']=='PASS'
        verify_old_or_current(day,policy)
    started=time.time()
    namespace['main'](day,policies)
    assert sha(OUT/'EXECUTION_BINDING.json')==EXECUTION_START_SHA, 'EXECUTION_BINDING_CHANGED_DURING_REPLAY'
    for policy in policies:
        folder=OUT/'replays'/day/policy
        before=read(OUT/'common_inputs'/day/policy/'DA_FRESH_INPUT_SNAPSHOT.json')
        assert all(sha(p)==h for p,h in before.items())
        stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
        execution=arrays(folder/stage/'EXECUTION.npz');p=execution['P_EXEC'];q=execution['Q_EXEC']
        angles=2*np.pi*np.arange(16)/16
        pcs=float(np.max(np.hypot(p,q)/400));polygon=float(np.max((p[:,:,None]*np.cos(angles)+q[:,:,None]*np.sin(angles))/(400*np.cos(np.pi/16))));pu=float(np.max(np.abs(p))/300)
        assert pcs<=1+1e-9 and polygon<=1+1e-9 and pu<=1+1e-9
        done=read(folder/'COMPLETE.json');done.update(maximum_PCS_norm_utilization=pcs,maximum_PCS_polygon_utilization=polygon,maximum_active_power_utilization=pu,method_version=method['version'])
        old_b=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_v1/replays'/day/policy/('CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_ACTUAL')/'EXECUTION.npz'
        if old_b.exists():
            prior=arrays(old_b);baseline=arrays(folder/('CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_ACTUAL')/'EXECUTION.npz')
            unchanged={k:bool(np.array_equal(prior[k],baseline[k])) for k in prior}
            assert all(unchanged.values()),('ETA95_BASELINE_DRIFT',day,policy,unchanged)
            save(folder/'V1_ETA95_BASELINE_IDENTITY.json',dict(status='PASS',source=str(old_b),bit_identical=unchanged))
            done['previous_ETA95_baseline_bit_identical']=True
        save(folder/'COMPLETE.json',done)
        outputs={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file() and p.name!='CANDIDATE_RECEIPT.json'}
        save(folder/'CANDIDATE_RECEIPT.json',dict(status='COMPLETE',day=day,policy=policy,cohort='development' if day in method['development_days'] else 'holdout',method_SHA=sha(OUT/'METHOD_FREEZE.json'),execution_binding_SHA=sha(OUT/'EXECUTION_BINDING.json'),files=outputs,DA_Fresh_preserved=True,scheduling_optimizer_calls=0,started_at=started,completed_at=time.time()))
    verify_method()

if __name__=='__main__':
    day=sys.argv[1];policies=sys.argv[2:]
    assert len(policies)==1 and all(p in ('B0','B1','B2','B3') for p in policies)
    try:main(day,policies)
    except BaseException as e:
        save(OUT/'failures'/f'{day}_{"_".join(policies)}_{time.time_ns()}.json',dict(day=day,policies=policies,status='TECHNICAL_FAILURE',error=repr(e),traceback=traceback.format_exc()))
        raise
