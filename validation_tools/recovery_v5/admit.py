"""Explicit, one-time continuation admission after all independent gates pass."""
from copy import deepcopy
from pathlib import Path
import shutil,json,subprocess
from v42_pr134_b1.common import ROOT,read,record,sha,atomic,now,same_process,digest
from v42_may_recovery_v5.policy import VERSION,MANIFEST,ATTEMPT,RETRY_DATES,PRECISION,source_files,verify_policy
from .preflight import RUN,DOC,caches


def main():
    if (RUN/MANIFEST).exists():
        raise PermissionError('IMMUTABLE_CONTINUATION_ALREADY_ADMITTED')
    base=read(RUN/'CAMPAIGN_MANIFEST.json')
    gates=dict(MAY11_NUMERICAL=DOC/'MAY11_PRECISION_VERIFICATION.json',
        MAY19_FROZEN_PHASE_WEIGHTS=ROOT/'docs/v42_may_phase_v4_20261009/VALIDATION.json',
        FRESH_ORIGINAL_MODELS=DOC/'BUILD_EQUIVALENCE.json',
        ORDER_ISOLATION_MONITOR_REGRESSION=DOC/'REGRESSION_VERIFICATION.json',
        WINDOWS_PROCESS_QUERY=DOC/'PROCESS_QUERY_VERIFICATION.json',
        MAY22_RUNTIME=DOC/'MAY22_RUNTIME_VERIFICATION.json',
        OS_PERSISTENCE=DOC/'OS_PERSISTENCE_VERIFICATION.json',
        MONITOR_UI=DOC/'MONITOR_UI_VERIFICATION.json')
    for name,path in gates.items():
        if read(path).get('PASS') is not True:raise PermissionError('ADMISSION_GATE_FAILED:'+name)
    hold=read(RUN/'HOLD.json')
    if hold.get('stop_live_worker') is not False or not hold.get('block_new_dispatch_only'):
        raise PermissionError('ORIGINAL_COORDINATOR_NOT_SAFELY_HELD')
    owner=read(RUN/'COORDINATOR_HOST.json').get('process',{})
    if same_process(owner):raise PermissionError('ORIGINAL_COORDINATOR_STILL_OWNS_RUN')
    originals={}
    for day in (*RETRY_DATES,'2025-05-22'):
        folder=RUN/'dates/B1'/day
        result=read(folder/'RESULT.json')
        if day=='2025-05-22' and result['status']!='PASS':raise PermissionError('MAY22_PASS_BOUNDARY_REQUIRED')
        if day in RETRY_DATES and result['status']=='PASS':raise PermissionError('UNAUTHORIZED_COMPLETED_DATE_RETRY')
        originals[day]=dict(result=record(folder/'RESULT.json'),ledger=record(folder/'NATIVE_RUNTIME_LEDGER.json'),
                           status=result['status'],Native_Runtime=result.get('Native_Runtime'))
    boundary=RUN/'BASE_CHECKPOINT_BOUNDARY_V5.json'
    if boundary.exists():raise PermissionError('ORIGINAL_BOUNDARY_ALREADY_FROZEN')
    shutil.copyfile(RUN/'CHECKPOINT.json',boundary)
    manifest=deepcopy(base)
    manifest.update(schema=VERSION,base_manifest=record(RUN/'CAMPAIGN_MANIFEST.json'),
        base_checkpoint=record(boundary),attempt_id=ATTEMPT,precision=PRECISION,
        authorized_recovery_dates=list(RETRY_DATES),input_cache_sources=caches(),
        monitor_port=8793,tasks={role:'MobileESS_V42_B1B2_P1_'+base['run_id']+'_RecoveryV5_'+role.title()
                               for role in ('coordinator','monitor','watchdog')},
        implementation=dict(version=VERSION,sources=source_files(),source_SHA=digest(source_files())),
        validation={name:record(path) for name,path in gates.items()},
        inherited_original_attempts=originals,source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        authority=dict(explicit_user_requested_recovery_dates=list(RETRY_DATES),
            after_current_date_terminal=True,May22_original_PASS_preserved=True,
            recovery_order=['2025-05-11','2025-05-19',*('2025-05-%02d'%d for d in range(23,32))],
            B1_parallel_workers=1,B2_parallel_workers=3,automatic_failed_date_retries=0,
            original_failed_points_bounds_and_budgets_transferred=False,
            scientific_acceptance_and_domains_unchanged=True,Heuristics=.05,
            wall_ceiling_seconds=None,Native_ceiling_seconds=5400),UTC=now())
    atomic(RUN/MANIFEST,manifest)
    verify_policy(RUN)
    from v42_may_recovery_v5.coordinator import load_checkpoint
    checkpoint=load_checkpoint(RUN,manifest)
    if any(checkpoint['dates']['B1/'+d]['status']!='PENDING' for d in RETRY_DATES):
        raise PermissionError('AUTHORIZED_RECOVERY_QUEUE_NOT_PENDING')
    report=dict(PASS=True,UTC=now(),run_id=base['run_id'],version=VERSION,
        Native_calls=0,P2_calls=0,manifest=record(RUN/MANIFEST),
        original_attempts=originals,original_manifest=record(RUN/'CAMPAIGN_MANIFEST.json'),
        original_checkpoint_boundary=record(boundary),implementation=manifest['implementation'],
        old_HOLD_retained=True,May22_retry_required=False,all_validation_gates=manifest['validation'],
        recovery_order=manifest['authority']['recovery_order'],real_recovery_status='NOT_YET_STARTED')
    atomic(DOC/'CONTINUATION_ADMISSION.json',report)
    print(json.dumps(dict(PASS=True,version=VERSION,manifest_SHA=sha(RUN/MANIFEST),queued=list(RETRY_DATES))))


if __name__=='__main__':main()
