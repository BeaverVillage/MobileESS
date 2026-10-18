"""Seal the explicit scientific amendment after Native0/row-difference proof."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r030
from v44.common import read, record, atomic, digest, now
from v44_recovery_r030 import operations as op
from v44_recovery_r029_switch import operations as previous
from v44_recovery_r029.handover import require_boundary

base=op.base
base.validate();previous.authority();require_boundary()
if base.workers():raise PermissionError('R030_NO_OLD_WORKERS_REQUIRED')
if op.AMENDMENT.exists():raise FileExistsError('R030_AMENDMENT_ALREADY_SEALED')
stop=base.OPS/'STOP_AUTONOMY.json'; stopped=read(stop)
if (stopped.get('reason')!='USER_REQUESTED_B3_M1_TIGHT_VOLTAGE_0955_1045_RESTART'
        or not stopped.get('campaign_resume_authorized')):
    raise PermissionError('R030_EXPLICIT_USER_MODEL_CHANGE_REQUIRED')
native0=Path(sys.argv[1]); proof=read(native0)
if not proof['PASS'] or proof['source_records']!=op.sources():raise PermissionError('R030_CURRENT_SOURCE_NATIVE0_PROOF_REQUIRED')
testlog=Path('D:/MobileESS_V44/development/R030_REGRESSION_20261018.log')
if '58 passed' not in testlog.read_text(encoding='utf-8-sig'):raise PermissionError('R030_REGRESSIONS_REQUIRED')
auth=base.OPS/'R030_USER_AUTHORIZATION.json'
atomic(auth,dict(UTC=now(),user_authorized=True,request='그럼 B3의 M1만 전압제약을 0.95 1.05가 아니라 0.955 1.045로 빡빡하게 하고 5월 2일 M1 A2 M2 스케줄링 시도해보자. 지금 실행 중단하고 이렇게 실행해.앞으로 B3의 M1의 전압 제약은 0.955 1.045야. 이렇게 바꿔. 다른 날짜들도.',
    arm='B3',stage='M1',all_future_dates=True,band=[.955,1.045],
    immediate_stop_receipt=record(stop),May02_restart='NEW_M1_THEN_NEW_A2_THEN_NEW_M2',
    previous_May02_M1_reuse_superseded=True,existing_completed_results_preserved=True,
    May07_B1_completed_A1_reuse_retained=True))
validation=base.OPS/'R030_CHANGE_AND_VALIDATION.json'
atomic(validation,dict(UTC=now(),PASS=True,regressions=58,regression_log=record(testlog),
    actual_May02_M1_Native0_validation=record(native0),source_records=op.sources(),
    changes=['ONLY_B3_M1_VOLTAGE_LOWER_0955_UPPER_1045_ALL_FUTURE_DATES',
        'FRESH_M1_A2_M2_FROM_SAME_DATE_CERTIFIED_A1',
        'FULL_VOLTAGE_ROW_AND_EXPORTED_PLAN_REVALIDATION'],
    base_algorithm_permit=record(base.PERMIT),A2_conditional_relaxation_pu=.005,
    downstream_M2_Actual_Fresh_band=[.95,1.05],new_actual_case_PASS_claimed=False))
atomic(op.AMENDMENT,dict(UTC=now(),policy=op.POLICY,arm='B3',stage='M1',
    voltage_band_pu=[.955,1.045],squared_band=[.912025,1.092025],all_future_campaign_dates=True,
    science_parameter_amendment=True,only_original_voltage_RHS_changed=True,
    user_authorization=record(auth),validation=record(validation),algorithm_permit=record(base.PERMIT),
    previous_operational_authorization=record(previous.AUTH),sources=op.sources(),
    preserved_completed_comparisons=True,old_M1_A2_M2_points_bounds_or_native_times_inherited=False,
    Native_budgets_changed=False,new_M1_K48_seconds=300,new_M1_Joint_seconds=900,
    A2_total_seconds=5400,A2_PhaseI_seconds=1500,A2_conditional_relaxation_pu=.005,
    M2_Actual_Fresh_voltage_band=[.95,1.05]))
op.authority()
for name in ('collect_watchdog','audit_active_revision'):
    source=(base.OPS/(name+'_r029.py')).read_text(encoding='utf-8-sig')
    old="'v44_recovery_r029')"
    if old not in source:raise ValueError('R030_MONITOR_ACTIVE_ALLOWLIST_BOUNDARY_DRIFT')
    source=source.replace(old,"'v44_recovery_r029','v44_recovery_r030')")
    if name=='audit_active_revision':
        anchor="if pending:\n    handover=read"
        if source.count(anchor)!=1:raise ValueError('R030_MONITOR_AMENDMENT_BOUNDARY_DRIFT')
        source=source.replace(anchor,"if revision=='v44_recovery_r030':\n    value.update(active_model_amendment=record(module.AMENDMENT),active_model_source_sha=digest(module.sources()),B3_M1_voltage_band=[.955,1.045])\n"+anchor)
    (base.OPS/(name+'_r030.py')).write_text(source,encoding='utf-8')
with op.install():
    states=base.states(base.CAMPAIGN)
    from v44_recovery_r029.failure_continue import deferred_dates
    blocked=deferred_dates(base.OPS)
    from v44.config import B2_ORDER,MAIN_ORDER
    first=next((key for key in (*B2_ORDER,*MAIN_ORDER) if states.get(key)=='READY' and key not in blocked),None)
    if first!=('2025-05-02','B3'):raise PermissionError('R030_MAY02_M1_MUST_RUN_FIRST:'+str(first))
    if states[('2025-05-07','B1')]!='READY':raise PermissionError('R030_MAY07_A1_RESUME_MUST_BE_RETAINED')
    ready=[dict(day=d,arm=a) for (d,a),s in states.items() if s=='READY']
evidence=Path(stopped['evidence'])
atomic(evidence/'R030_SEALED.json',dict(UTC=now(),PASS=True,source_sha=digest(op.sources()),
    sources=op.sources(),amendment=record(op.AMENDMENT),validation=record(validation),
    first_case=first,ready_cases=ready,interrupted_case_result=record(Path(stopped['stopped_case'])/'RESULT.json')))
stop.rename(evidence/'USER_MODEL_CHANGE_STOP_PRESERVED.json')
for name in ('R030_CHANGE_AND_VALIDATION.json','R030_B3_M1_VOLTAGE_AMENDMENT.json'):
    atomic(Path(__file__).resolve().parents[1]/'docs/v44'/name,read(base.OPS/name))
print(dict(PASS=True,first=first,ready_cases=ready,amendment=str(op.AMENDMENT)))
