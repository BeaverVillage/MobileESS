"""Resume original Actual from frozen inputs and accepted-slot checkpoint."""
import sys,time,traceback
from pathlib import Path
import actual_worker as worker
import actual_electrical_speed as speed
from actual_speed_runner import bind

def main():
    assert worker.POLICY in ('B2','B3')
    report=worker.read(worker.BASE/'ACTUAL_SPEED_PREFLIGHT_20260922/BENCHMARK_PASS.json')
    assert report['status']=='PASS' and report['source_sha256']==worker.sha(Path(speed.__file__))
    worker.verify();worker.protect()
    ns=worker.kernel();ns['independent_audit']=worker.binding.independent_audit
    import gurobipy as gp
    gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DA_OPTIMIZATION_FORBIDDEN_IN_ACTUAL'))
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    da=MessElectricalAuthority.from_repository()
    assert worker.read(worker.H/worker.POLICY/'INPUT_READY.json')['status']=='PASS'
    authority=worker.read(worker.BASE/'ACTUAL_SPEED_RESUME_AUTHORITY.json')
    assert worker.sha(worker.H/worker.POLICY/'ACTUAL_INPUTS.npz')==authority['actual_inputs_sha256']
    runner=bind(worker,ns);speed.install()
    runner(worker.POLICY,ns,da);worker.verify()
    events=worker.pd.read_parquet(worker.H/worker.POLICY/'aidc/RESOURCE_CHANGE_EVENTS.parquet');physical=events.copy()
    for col in ['GPU_delta','GPU_occupancy_before','GPU_occupancy_after','GPU_capacity','rack_single_gang_capacity']:physical[col]=2*physical[col]
    assert ((physical.GPU_occupancy_after>=0)&(physical.GPU_occupancy_after<=physical.GPU_capacity)).all()
    physical.to_parquet(worker.H/worker.POLICY/'aidc/PHYSICAL_2X_RESOURCE_CHANGE_EVENTS.parquet',index=False)
    result=worker.read(worker.H/worker.POLICY/'COMPLETE.json')
    worker.save(worker.H/'COMPLETE.json',dict(status='COMPLETE',date=worker.DAY,policy=worker.POLICY,
        source_preservation='PASS',result=worker.rec(worker.H/worker.POLICY/'COMPLETE.json'),
        summary=result['summary'],AC_feasible=result['AC_feasible'],new_scheduling_optimizer_calls=0,
        speed_runtime=worker.rec(worker.H/'SPEED_RUNTIME_BINDING.json')))
if __name__=='__main__':
    try:main()
    except BaseException as e:
        worker.save(worker.H/'FAILURE_FAST.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
