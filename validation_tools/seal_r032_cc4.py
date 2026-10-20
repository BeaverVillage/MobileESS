"""Seal the repaired calendar and release the user's completed-M1 restart."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r032
from v44.common import read, record, atomic, digest, now
from v44.locks import alive
from v44_recovery_r032 import operations as op, cc4_date

op.previous.validate()
if op.base.workers() or alive(read(op.CAMPAIGN/'COORDINATOR_LEASE.json')):
    raise PermissionError('R032_USER_STOP_BOUNDARY_REQUIRED')
if op.AMENDMENT.exists():raise FileExistsError(op.AMENDMENT)
stop=op.OPS/'STOP_AUTONOMY.json';held=read(stop)
if held.get('reason')!='R032_USER_STOP_FIX_CC4_RESUME_MAY02' or not held.get('campaign_resume_authorized'):
    raise PermissionError('R032_EXPLICIT_USER_STOP_AND_RESTART_REQUIRED')
native0=Path('D:/MobileESS_V44/development/r032_cc4_native0_20261018_sealed/VALIDATION.json')
proof=read(native0)
if not proof['PASS'] or proof['Native_optimization_calls'] or proof['sources']!=op.sources():
    raise PermissionError('R032_CURRENT_SOURCE_NATIVE0_REQUIRED')
log=Path('D:/MobileESS_V44/development/R032_REGRESSION_FINAL_20261018.log')
if '98 passed' not in log.read_text(encoding='utf-8-sig'):raise PermissionError('R032_REGRESSIONS_REQUIRED')
evidence=Path(held['evidence'])
atomic(evidence/'USER_AUTHORIZED_STOP_PRESERVED.json',held)
validation=op.OPS/'R032_CHANGE_AND_VALIDATION.json'
atomic(validation,dict(UTC=now(),PASS=True,sources=op.sources(),regressions=98,
    regression_log=record(log),Native0=record(native0),
    diagnosed_cause='Fixed-M1 A2 AST rebuild resets CC4 date to May01 and falsely marks it dynamically routed',
    corrected_CC4_rows_equal_original_dated_A1=True,pre_native_all_hour_conservation_guard=True,
    same_completed_tight_M1_FULL_replay=proof['same_completed_M1_full_replay'],
    A2_from_scratch=True,old_A2_P1_LB_point_or_Native_clock_reused=False,
    physical_equations_and_tolerances_not_weakened=True,
    R031_P1_performance_May03_onward_retained=True))
atomic(op.AMENDMENT,dict(UTC=now(),policy=cc4_date.POLICY,user_authorized=True,
    user_instruction='아그럼 A2처음부터 재개해 M1 끝난시점이네 그럼',
    previous_user_instruction='해결해서 5월 2일 B3 체크포인트부터 재개해. 지금 실행되고 있는 건 중단하고.',
    sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
    completed_M1=record(op.PARENT/'M1/RESULT.json'),failed_A2=record(op.PARENT/'A2/RESULT.json'),
    interrupted_B1_result=record(op.INTERRUPTED/'RESULT.json'),
    interruption=record(op.INTERRUPTED/'USER_INTERRUPTION.json'),
    user_stop=record(evidence/'USER_AUTHORIZED_STOP_PRESERVED.json'),
    resumed_M1_plan_sha=read(op.PARENT/'M1/RESULT.json')['MESS_plan']['plan_sha'],
    A2_native_start=0.,A2_native_ceiling=5400.,old_A2_state_point_bound_or_native_clock_reused=False,
    all_future_B3_A2_use_current_day_CC4=True,only_failed_or_interrupted_exact_attempts_released=True))
op.validate()
with op.install():
    from v44.config import B2_ORDER,MAIN_ORDER
    from v44_recovery_r029.failure_continue import deferred_dates
    states=op.base.states(op.CAMPAIGN);blocked=deferred_dates(op.OPS)
    first=next((key for key in (*B2_ORDER,*MAIN_ORDER) if states.get(key)=='READY' and key not in blocked),None)
    if first!=('2025-05-02','B3'):raise PermissionError('R032_MAY02_MUST_RESUME_FIRST:'+str(first))
    case=op.base.decorate(dict(day='2025-05-02',arm='B3',sources=[]),op.previous.validate())
    if Path(case['fresh_a2_parent']).resolve()!=op.PARENT.resolve():raise PermissionError('R032_COMPLETED_M1_ROUTING_FAILED')
    if states[('2025-05-07','B1')]!='READY':raise PermissionError('R032_MAY07_A1_REUSE_REQUIRED')
for name in ('collect_watchdog','audit_active_revision'):
    source=(op.OPS/(name+'_r031.py')).read_text(encoding='utf-8-sig')
    old="'v44_recovery_r031')"
    if old not in source:raise ValueError('R032_MONITOR_ALLOWLIST_DRIFT')
    source=source.replace(old,"'v44_recovery_r031','v44_recovery_r032')")
    if name=='audit_active_revision':
        anchor="if pending:\n    handover=read"
        assert source.count(anchor)==1
        source=source.replace(anchor,"if revision=='v44_recovery_r032':\n    value.update(active_CC4_date_repair=record(module.AMENDMENT),active_CC4_date_source_sha=digest(module.sources()),B3_M1_voltage_band=[.955,1.045])\n"+anchor)
    (op.OPS/(name+'_r032.py')).write_text(source,encoding='utf-8')
atomic(evidence/'R032_SEALED.json',dict(UTC=now(),PASS=True,source_sha=digest(op.sources()),
    sources=op.sources(),authorization=record(op.AMENDMENT),first_case=first,
    completed_M1_plan_sha=read(op.PARENT/'M1/RESULT.json')['MESS_plan']['plan_sha']))
stop.rename(evidence/'R032_STOP_DISPATCH_HOLD_RELEASED.json')
for name in ('R032_CHANGE_AND_VALIDATION.json','R032_CC4_DATE_REPAIR_AUTHORIZATION.json'):
    atomic(Path(__file__).resolve().parents[1]/'docs/v44'/name,read(op.OPS/name))
print(dict(PASS=True,first=first,source_sha=digest(op.sources())))
