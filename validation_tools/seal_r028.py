"""Seal validated sources and explicit, bounded repair releases."""
from pathlib import Path
import json
import v44_recovery_r028
from v44.common import read,record,verify,atomic,digest,now
from v44_recovery_r028 import operations as op
from v44_recovery_r028.failure_continue import defer
from v44_recovery_r028.voltage_policy import authority

ops=op.OPS;root=op.CAMPAIGN
assert not op.PERMIT.exists()
log=Path('D:/MobileESS_V44/development/R028_REGRESSION_20261018.log')
assert '298 passed' in log.read_text(encoding='utf8')
native0=Path('D:/MobileESS_V44/development/r028_native0_20261018_fix1/VALIDATION.json')
assert read(native0)['PASS']
authorization=dict(UTC=now(),explicit_user_request=True,
    user_messages=['오류 다 해결해. 그리고 왜 5월 2일 B3는 한도 도달했어?',
        '5월 2일 B3 P1잘안되는 원인도 찾아서 해결해.',
        '그럼 오류 수정하고 B1들 actual에서부터 돌리면 돼? planning은 재사용할 수 있어?',
        '그리고 조건부 전압 완화를 ㅅㅏㅇ하한 0.1이 아니라 0.05로 줄이도록 수정해.',
        '±0.005 pu로 축소: 0.945~1.055 pu'],
    explicit_resume_May02_B3_A2_Native0=True,supersedes_pending_r027=True,
    revised_voltage_band=[.945,1.055],maximum_relaxation_pu=.005,
    approved_P1_repairs=['VERIFIED_FEASIBLE_PSTART','SAME_MATRIX_LOCAL_LP_BASIS','ALL_CERTIFIED_NEGATIVE_BLOCKS_PER_ACTIVATION'],
    A_total_Native_seconds=5400,PhaseI_Native_seconds=1500,physical_tolerances_unchanged=True,
    old_attempts_PASS_Raw_and_Native_preserved=True,P1_restore_original_Barrier_policy=True,May06_reuse_accepted_Planning_decisions_and_P1_closure=True,
    May06_fixed_integer_continuous_repair_and_full_validation_required=True,
    same_time_limit_without_technical_fix_retry_forbidden=True)
atomic(ops/'R028_USER_AUTHORIZATION.json',authorization)
status=read(root/'CAMPAIGN_STATUS.json');workers=op.workers()
assert len(workers)==1 and workers[0]['pid']==status['workers'][0]['pid']
active=status['workers'][0];target=op.latest(root,active['day'],active['arm'])
lease=read(root/'COORDINATOR_LEASE.json');superseded=read(ops/'R027_HANDOVER_HEARTBEAT.json')
atomic(ops/'R028_HANDOVER_GUARD.json',dict(UTC=now(),protected_case_root=str(target),
    protected_worker=dict(pid=workers[0]['pid'],process_created=workers[0]['create_time']),
    protected_coordinator=lease,superseded_handover=dict(pid=superseded['pid'],process_created=superseded['process_created']),
    superseded_handover_stop=record(ops/'STOP_AUTONOMY.json'),authorization=record(ops/'R028_USER_AUTHORIZATION.json'),
    natural_full_case_terminal_required=True,current_worker_source_unchanged=True))
validation=dict(UTC=now(),PASS=True,revision='r028',regressions=298,
    regression_receipt=record(log),Native0_real_data_validation=record(native0),
    source_records=op.sources(),recovery_source_sha=digest(op.sources()),
    previous_revision='v44_recovery_r026f1',previous_seal=record(ops/'R026F1_SEALED.json'),
    comparison=record(Path('D:/MobileESS_V44/development/R028_MAY01_MAY02_COMPARISON.json')),
    pending_r027_superseded_without_execution=True,
    fixes=['RESTORE_ORIGINAL_BARRIER_NORMAL_P1_AND_PRICING_PHASEI_ROBUST_ONLY', 'LEGACY_M1_KEYWORD_DEFAULT_FAILURE_RETRY_ON_CORRECT_CURRENT_WORKER',
        'FIXED_INTEGER_CONTINUOUS_FEASIBILITY_RESTORATION_WITH_FULL_ACCEPTANCE_REPLAY',
        'MAY06_CERTIFIED_P1_AND_INTEGER_DECISION_REUSE_WITH_ORIGINAL_NATIVE_CLOCK',
        'P1_FEASIBLE_PRIMAL_CARRY_AND_EXACT_LOCAL_PRICING_BASIS_REUSE',
        'ACTIVATE_ALL_FULLY_PRICED_AND_REPLAYED_NEGATIVE_CLASS_SUPPORTS',
        'USER_CONFIRMED_HALF_A2_VOLTAGE_RECOVERY_BAND'],
    voltage_policy=authority(),actual_cases_reexecuted=False,
    actual_speedup_or_all28_PASS_claimed=False,old_sources_or_outcomes_modified=False)
atomic(ops/'R028_CHANGE_AND_VALIDATION.json',validation)
permit=op.make_permit()
for day,arm in [('2025-05-02','B3')]+[(f'2025-05-{d:02d}',a) for d in range(3,7) for a in ('B1','B3')]:
    parent=op.latest(root,day,arm)
    if parent is None:continue
    result=read(parent/'RESULT.json')
    assert not result.get('PASS')
    queue=defer(ops,parent,result)
    path=ops/'R028_PENDING_REPAIR_RELEASES'/queue.name
    assert not path.exists()
    atomic(path,dict(UTC=now(),repair_validation=record(ops/'R028_CHANGE_AND_VALIDATION.json'),
        failed_queue_receipt=record(queue),failed_result=record(parent/'RESULT.json'),
        execution_permit=record(op.PERMIT),diagnosed_cause_fixed=True,allow_new_attempt=True,
        bounded_revision='r028',retry_count=1,
        reason='NEW_VALIDATED_P1_IMPLEMENTATION_AND_USER_TIGHTER_VOLTAGE_MODEL' if day=='2025-05-02'
        else 'EXACT_INTEGER_CONTINUOUS_REPAIR_OF_PRESERVED_PLANNING' if (day,arm)==('2025-05-06','B1')
        else 'CORRECTED_CURRENT_A_STAGE_CALL_OR_SAME_DATE_B1_DEPENDENCY'))
atomic(ops/'R028_SEALED.json',dict(UTC=now(),PASS=True,source_sha=digest(op.sources()),sources=op.sources(),
    permit=record(op.PERMIT),validation=record(ops/'R028_CHANGE_AND_VALIDATION.json')))
handoff=read(ops/'CURRENT_HANDOFF.json')
handoff.update(UTC=now(),pending_revision='v44_recovery_r028',pending_permit=record(op.PERMIT),
    pending_validation=record(ops/'R028_CHANGE_AND_VALIDATION.json'),
    latest_user_instruction='Fix errors and May02 B3 P1; reuse valid Planning; A2 relaxation reduced to ±0.005pu (0.945~1.055pu).',
    pending_handover_mode='NATURAL_CURRENT_MAY07_B1_COMPLETE_ACTUAL_AND_FRESH_THEN_NEW_REVISION')
atomic(ops/'CURRENT_HANDOFF.json',handoff)
for name in ('collect_watchdog','audit_active_revision'):
    old=ops/(name+'_r026f1.py');new=ops/(name+'_r028.py')
    source=old.read_text(encoding='utf8')
    source=source.replace("'v44_recovery_r026f1')","'v44_recovery_r026f1','v44_recovery_r028')")
    # Explicit pending revision allow-list is separate from active revisions.
    source=source.replace("'v44_recovery_r026f1',)","'v44_recovery_r026f1','v44_recovery_r028',)")
    new.write_text(source,encoding='utf8')
print(json.dumps(dict(PASS=True,revision='r028',regressions=298,sources=len(op.sources()),
    source_sha=digest(op.sources()),protected_case=str(target),ready_cases=[dict(day=d,arm=a) for (d,a),s in op.states(root).items() if s=='READY'])))
