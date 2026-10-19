import v44_recovery_r045
from pathlib import Path
import os,sys,subprocess,json
from v44_recovery_r045 import operations as op
from v44.common import read,record,atomic,now
from v44.locks import alive

with op.week.bindings():
    op.seq.authority();state=read(op.STATE)
    if op.PERMIT.exists() or op.seq.STOP.exists() or alive(state.get('lease')):raise PermissionError('R045_EXISTING_AUTHORITY_STOP_OR_LIVE_OWNER_PRESERVED')
    validation=read(op.VALIDATION)
    if not validation['PASS'] or validation['sources']!=op.sources():raise PermissionError('R045_TESTED_SOURCE_REQUIRED')
    plan=read(op.OPS/'R045_RESTART_PLAN.json')['plan']
    atomic(op.PERMIT,dict(UTC=now(),explicit_user_approved=True,
        user_instruction='2026-10-19 user: 날짜별 캠페인과 데이터 연결 확인, 오류 해결 후 캠페인 재개.',
        campaign_root=str(op.CAMPAIGN),sources=op.sources(),previous_authorization=record(op.repair.PERMIT),
        validation=record(op.VALIDATION),date_audit=record(op.OPS/'R045_DATE_AND_FAILURE_AUDIT.json'),
        plan=plan,prepare_workers=1,actual_workers=7,baseline_workers=1,baseline_full_case_per_worker=True,
        original_historical_boundary_preserved=True,live_current_campaign_workers_explicitly_admitted=True,
        prepared_handoffs_reused=3,Native_clocks_reset=False,scientific_tolerances_unchanged=True,
        infrastructure_failures_cannot_mark_campaign_COMPLETE=True))
    with op.bindings():op.authority()
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (op.OPS/'r045_controller.log').open('ab') as stream:
        process=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',op.ENTRY,'--run'],cwd=op.week.RUNNER_ROOT,
            env=env,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R045_CONTROLLER_LAUNCH.json',dict(UTC=now(),pid=process.pid,
        process_created=__import__('psutil').Process(process.pid).create_time(),authorization=record(op.PERMIT)))
    print(json.dumps(dict(PASS=True,pid=process.pid,plan_cases=28,reused_prepared=3),indent=2))
