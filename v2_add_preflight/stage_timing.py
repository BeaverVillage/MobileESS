"""Observed stage wall/CPU/Native costs and OS telemetry; no admission rules."""
from contextlib import contextmanager
from pathlib import Path
import time,threading,json,psutil
from .stage_common import read
from .stage_resources import sample
from .prestart_execution import atomic

@contextmanager
def telemetry(root):
    root=Path(root).resolve();done=threading.Event();process=psutil.Process()
    def collect():
        while not done.is_set():
            try:
                row=sample();cpu=process.cpu_times();io=process.io_counters()
                row.update(CPU_user_seconds=cpu.user,CPU_system_seconds=cpu.system,
                    process_CPU_percent=process.cpu_percent(),system_CPU_percent=psutil.cpu_percent(),
                    process_disk_read_bytes=io.read_bytes,process_disk_write_bytes=io.write_bytes,
                    workspace_disk_free_bytes=psutil.disk_usage(root.anchor).free,
                    observation_only=True,memory_information_only=True,automatic_resource_rejection=False)
                with (root/'OS_RESOURCE_TELEMETRY.jsonl').open('a',encoding='utf8') as f:
                    f.write(json.dumps(row,allow_nan=False)+'\n')
            except Exception as error:
                atomic(root/'RESOURCE_TELEMETRY_ERROR.json',dict(error=repr(error),observation_only=True))
            done.wait(5.)
    thread=threading.Thread(target=collect,daemon=True);thread.start()
    try:yield
    finally:done.set();thread.join(2.)

@contextmanager
def stage(request):
    root=Path(request['output']);wall=time.perf_counter();cpu=time.process_time();error=None;value={}
    names=('NATIVE_RUNTIME_LEDGER.json','K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json')
    old={}
    if request.get('resume_parent'):
        for name in names:
            path=Path(request['resume_parent'])/name
            if path.exists():
                data=read(path);old[name]=(len(data['calls']),len(data['costs']))
    try:yield value
    except BaseException as exc:error=repr(exc);raise
    finally:
        elapsed=time.perf_counter()-wall;Native=0.;Native_wall=0.;external=0.;preparation=0.;ledgers=[];unknown=0
        for name in names:
            path=root/name
            if not path.exists():continue
            data=read(path);n,c=old.get(name,(0,0));calls=data['calls'][n:];costs=data['costs'][c:]
            Native+=sum(r.get('Native_Runtime') or 0. for r in calls)
            unknown+=sum(r.get('runtime_unavailable') is True or r.get('Native_Runtime') is None for r in calls)
            Native_wall+=sum(r.get('optimize_wall_seconds') or 0. for r in calls)
            external+=sum(r.get('wall_seconds',0.) for r in costs if r.get('kind')=='OTHER_SOLVER')
            preparation+=sum(r.get('exclusive_non_native_wall_seconds',r.get('wall_seconds',0.))
                for r in costs if r.get('kind')=='model_preparation')
            ledgers.append(dict(path=str(path),cumulative_measured_Native_seconds=data['measured_Native_Runtime'],
                old_paid_calls_retained=n,this_attempt_calls=len(calls),inflight=data['inflight'],
                Native_ceiling_seconds=data['Native_ceiling_seconds']))
        value.update(stage_wall_seconds=elapsed,stage_CPU_seconds=time.process_time()-cpu,
            this_attempt_measured_Native_seconds=Native,this_attempt_Native_optimize_wall_seconds=Native_wall,
            non_Native_preparation_validation_IO_and_score_wall_seconds=max(0.,elapsed-Native_wall),
            A_model_preparation_wall_seconds=preparation,external_score_solver_wall_seconds=external,
            Native_runtime_measurement_complete=unknown==0,unavailable_Runtime_calls=unknown,
            budget_basis='MEASURED_NATIVE_RUNTIME_ONLY',ledgers=ledgers,error=error)
        atomic(root/'STAGE_COSTS.json',value)
