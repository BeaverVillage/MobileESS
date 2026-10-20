"""Seal and arm next-case deployment without terminating the running case."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r031
from v44.common import read, record, atomic, now, digest
from v44_recovery_r031 import operations as op
from v44_recovery_r031 import p1_expansion as policy

op.previous.validate()
if op.AMENDMENT.exists(): raise FileExistsError(op.AMENDMENT)
stop=op.OPS/'STOP_AUTONOMY.json';hold=read(stop)
if hold.get('reason')!='R031_NEXT_CASE_HANDOVER' or hold.get('user_stop'):
    raise PermissionError('R031_OWN_TECHNICAL_DISPATCH_HOLD_REQUIRED')
native0=Path('D:/MobileESS_V44/development/r031_p1_native0_20261018_final/VALIDATION.json')
proof=read(native0)
if not proof['PASS'] or proof['Native_optimization_calls'] or proof['sources']!=op.sources():
    raise PermissionError('R031_CURRENT_SOURCE_NATIVE0_REQUIRED')
log=Path('D:/MobileESS_V44/development/R031_REGRESSION_20261018.log')
if '80 passed' not in log.read_text(encoding='utf-8-sig'):
    raise PermissionError('R031_REGRESSIONS_REQUIRED')
validation=op.OPS/'R031_CHANGE_AND_VALIDATION.json'
atomic(validation,dict(UTC=now(),PASS=True,sources=op.sources(),regressions=80,
    regression_log=record(log),Native0=record(native0),measured_speedup_claimed=False,
    changes=['P1_SECOND_NEGATIVE_CLASS_BOUNDED_COMPLETE_NATIVE_GRAPH_ADMISSION'],
    all_classes_full_pricing_retained=True,all_exact_LB_and_FULL_integer_replays_retained=True,
    physical_equations_voltage_bounds_and_Native_budgets_changed=False,
    current_May02_result_preserved=True,current_May03_B1_worker_untouched=True))
atomic(op.AMENDMENT,dict(UTC=now(),policy=policy.POLICY,
    user_instruction='아 풀렸다. 다음날짜부터 적용해',user_authorized=True,
    user_previous_instruction='응 개선해서 다음 날짜부터 적용하고 지금 냅두면 P1풀릴 것 같아? 아니면 개선해서 지금 5월 2일 B3에 적용해야될 것 같아?',
    arm='B3',stage='A2',phase='P1',first_day=policy.FIRST_DAY,
    max_classes=policy.MAX_CLASSES,max_columns_per_class=policy.MAX_COLUMNS_PER_CLASS,
    max_total_complete_native_columns=policy.MAX_TOTAL_COLUMNS,
    protected_case_root=hold['protected_case_root'],sources=op.sources(),
    previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
    May02_no_automatic_restart=True,May07_B1_completed_A1_reuse_retained=True))
op.validate()
for name in ('collect_watchdog','audit_active_revision'):
    source=(op.OPS/(name+'_r030.py')).read_text(encoding='utf-8-sig')
    old="'v44_recovery_r030')"
    if old not in source: raise ValueError('R031_MONITOR_ALLOWLIST_DRIFT')
    source=source.replace(old,"'v44_recovery_r030','v44_recovery_r031')")
    if name=='audit_active_revision':
        anchor="if pending:\n    handover=read"
        assert source.count(anchor)==1
        source=source.replace(anchor,"if revision=='v44_recovery_r031':\n    value.update(active_performance_authorization=record(module.AMENDMENT),active_performance_source_sha=digest(module.sources()),B3_M1_voltage_band=[.955,1.045])\n"+anchor)
    (op.OPS/(name+'_r031.py')).write_text(source,encoding='utf-8')
path=op.OPS/'CURRENT_HANDOFF.json';value=read(path)
value.update(UTC=now(),pending_revision='v44_recovery_r031',pending_permit=record(op.AMENDMENT),
    pending_validation=record(validation),collector=str(op.OPS/'collect_watchdog_r031.py'),
    active_source_auditor=str(op.OPS/'audit_active_revision_r031.py'),
    dispatch_hold_reason='R031 next case handover; current May03 B1 continues to completion',
    latest_user_instruction='아 풀렸다. 다음날짜부터 적용해')
atomic(path,value)
for name in ('R031_CHANGE_AND_VALIDATION.json','R031_P1_PERFORMANCE_AUTHORIZATION.json'):
    atomic(Path(__file__).resolve().parents[1]/'docs/v44'/name,read(op.OPS/name))
print(dict(PASS=True,pending_revision='r031',source_sha=digest(op.sources()),protected_case=hold['protected_case_root']))
