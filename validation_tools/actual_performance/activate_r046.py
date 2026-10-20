import v44_recovery_r046
from v44_recovery_r046 import operations as op
from v44.common import read,record,verify,atomic,now
from pathlib import Path
import os,sys,subprocess,json

with op.core.week.bindings():
    if op.AUTH.exists():raise FileExistsError('R046_IMMUTABLE_AUTHORITY_ALREADY_EXISTS')
    stop=read(op.core.seq.STOP)
    if stop.get('reason')!=op.REASON or stop.get('authorization')!=record(op.DRAIN):raise PermissionError('R046_OWN_DRAIN_REQUEST_REQUIRED')
    v=read(op.VALIDATION)
    if not v['PASS'] or v['sources']!=op.sources():raise PermissionError('R046_TESTED_SOURCE_REQUIRED')
    checks=[record(op.OPS/name) for name in ('R046_A1_STAGE_ROUTING_VERIFIED.json','R046_A2_PIPELINE_VERIFIED.json')]
    if not all(read(r['path'])['PASS'] for r in checks):raise PermissionError('R046_REAL_NATIVE0_ROUTING_REQUIRED')
    plan=read(op.OPS/'R046_RESTART_PLAN.json')['plan']
    if len(plan)!=28 or {op.core.seq.key(j) for j in plan}!={(d,a) for d in op.core.week.DAYS for a in op.core.week.ARMS}:
        raise PermissionError('R046_ALL_28_PLAN_MEMBERS_REQUIRED')
    atomic(op.AUTH,dict(UTC=now(),explicit_user_approved=True,sources=op.sources(),helper_sources=op.helpers(),
        previous_authorization=record(op.previous.AUTH),validation=record(op.VALIDATION),user_request=record(op.DRAIN),
        diagnosis=record(op.OPS/'R046_NUMERICAL_DIAGNOSIS.json'),additional_checks=checks,plan=plan,
        repairs=[list(k) for k in op.REPAIRS],prepare_workers=1,actual_workers=7,baseline_workers=1,
        current_Actual_must_finish_before_Planning=True,pending_Actual_handoffs_preserved=4,
        expected_next_Actual_ready_cases=7,completed_Actual_not_relaunched=True,
        Native_clocks_reset=False,scientific_tolerances_unchanged=True,
        user_instruction='2026-10-20 user: 현재 오류/실패 해결, 현재 Actual 끝나면 Planning 재개, Planning 끝나면 Actual 최대 7worker로 계속 진행.'))
    with op.bindings():op.authority()
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (op.OPS/'r046_transition.log').open('ab') as stream:
        p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',op.ENTRY,'--transition'],cwd=op.core.week.RUNNER_ROOT,
            env=env,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R046_TRANSITION_LAUNCH.json',dict(UTC=now(),pid=p.pid,
        process_created=__import__('psutil').Process(p.pid).create_time(),authorization=record(op.AUTH)))
    pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');value=read(pointer)
    value.update(pending_operational_recovery=record(op.AUTH),pending_operational_entry=op.ENTRY,
        next_after_current_Actual='Repair May11 B1/B3 and May12 B3 Planning with 1 worker, then ready Actual with up to 7 workers.')
    atomic(pointer,value)
    print(json.dumps(dict(PASS=True,pid=p.pid,current_Actual_preserved=True,repair_Planning=3,next_Actual_expected=7),indent=2))
