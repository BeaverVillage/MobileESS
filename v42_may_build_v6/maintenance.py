"""Narrow new-run audit/recovery. Never retries a date or touches a Worker."""
from pathlib import Path
import argparse,math
from datetime import datetime,timezone
from .common import read,atomic,now,same_process,sha
from .coordinator import load_manifest,load_checkpoint,read_actives,counts,command_matches
from .windows import reuse_registered_task,run_task

def needs_build_diagnosis(alive,completed,age,elapsed,reference):
    """Warning admission only. No elapsed-time condition can stop a Worker."""
    return bool(alive and not completed and (age>=600 or
        reference is not None and elapsed is not None and elapsed>reference*1.5))

def _audit(root,recover=False):
    root=Path(root).resolve()
    manifest=load_manifest(root);checkpoint=load_checkpoint(root,manifest)
    issues=[];workers=[];actions=[];performance=[]
    for name,active in read_actives(root).items():
        request=read(active['request']);attempt=Path(active['request']).parent
        ledger=read(attempt/'NATIVE_RUNTIME_LEDGER.json') if (attempt/'NATIVE_RUNTIME_LEDGER.json').exists() else {}
        alive=same_process(active['worker'])
        if request['run_id']!=manifest['run_id'] or request['manifest_SHA']!=sha(request['manifest']):
            issues.append('WORKER_REQUEST_IDENTITY_DRIFT:'+name)
        if alive and not command_matches(request['worker_command'],active['worker']['command']):
            issues.append('WORKER_COMMAND_IDENTITY_DRIFT:'+name)
        used=0.;unknown=False
        for call in ledger.get('calls',[]):
            if abs(call['effective_TimeLimit']-max(0.,5400-used))>1e-6:issues.append('NATIVE_TIMELIMIT_CONTRACT_DRIFT:'+name)
            runtime=call.get('Native_Runtime')
            if runtime is None or not math.isfinite(runtime):unknown=True
            else:used+=runtime
        if ledger and (ledger.get('wall_ceiling_seconds') is not None or ledger.get('Native_ceiling_seconds')!=5400
                or used!=ledger.get('measured_Native_Runtime') or used>5400 or unknown):
            issues.append('NATIVE_LEDGER_REQUIRES_DIAGNOSIS:'+name)
        build=read(attempt/'output/MODEL_BUILD_DETAIL.json') if (attempt/'output/MODEL_BUILD_DETAIL.json').exists() else {}
        stage_times=read(attempt/'output/BUILD_STAGE_TIMES.json') if (attempt/'output/BUILD_STAGE_TIMES.json').exists() else {}
        completed=read(attempt/'output/A_PREPARE_RECEIPT.json') if (attempt/'output/A_PREPARE_RECEIPT.json').exists() else {}
        elapsed=build.get('model_preparation_seconds')
        reference=read(manifest['implementation_validation']['path'])['gates']['BUILD_MODEL_EQUIVALENCE']
        reference=read(reference['path'])['construction_seconds'] if request['arm']=='B1' and request['day']=='2025-05-01' else None
        last=stage_times.get('last_stage_progress_UTC',request['started_UTC'])
        age=max(0.,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(last).timestamp())
        if needs_build_diagnosis(alive,completed.get('PASS'),age,elapsed,reference):
            performance.append(dict(name=name,kind='DIAGNOSE_MODEL_PREPARATION',stage_progress_age_seconds=age,
                elapsed_seconds=elapsed,reference_seconds=reference,time_is_not_termination_reason=True))
        from .coordinator import worker_snapshot
        snapshot=worker_snapshot(active)
        workers.append(dict(name=name,alive=alive,worker=active['worker'],resource=snapshot.get('resource',{}),completed_Native_Runtime=used,
            inflight=ledger.get('inflight'),native_remaining_seconds=max(0.,5400-used),
            heartbeat=read(attempt/'HEARTBEAT.json') if (attempt/'HEARTBEAT.json').exists() else {},
            build=build,stage_times=stage_times,
            cache_hit=(attempt/'output/CURRENT_DATE_PHYSICAL_CACHE_REUSE.json').exists(),
            model_preparation_reference_seconds=reference))
    hold=(root/'HOLD_V6.json').exists()
    if recover and not issues and not hold:
        for role in ('coordinator','monitor'):
            receipt=root/('COORDINATOR_V6_HOST.json' if role=='coordinator' else 'MONITOR_PROCESS.json')
            identity=read(receipt) if receipt.exists() else {}
            identity=identity.get('process',identity)
            if not same_process(identity) and not (role=='coordinator' and checkpoint['state']=='COMPLETE'):
                task=manifest['tasks'][role]
                verified=reuse_registered_task(root,role,task,python=manifest['Python'])
                run_task(task);actions.append(dict(role=role,task=task,registration=verified))
    result=dict(PASS=not issues,run_id=manifest['run_id'],UTC=now(),issues=issues,workers=workers,
        B1=counts(checkpoint,'B1'),B2=counts(checkpoint,'B2'),state=checkpoint['state'],hold=hold,
        actions=actions,performance_diagnosis_requests=performance,
        worker_restarts=0,terminal_date_retries=2,automatic_failed_date_retries=0,Native_calls_by_maintenance=0)
    atomic(root/'MAINTENANCE_V6_STATE.json',result);return result

def run(root,recover=False,session_token=None):
    from v42_may_campaign_native90.maintenance_session import check_lock
    with check_lock(Path(root)/'hourly_maintenance',session_token):
        return _audit(root,recover)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--recover-dead-hosts',action='store_true');parser.add_argument('--session-token')
    args=parser.parse_args();print(run(args.root,args.recover_dead_hosts,args.session_token))
