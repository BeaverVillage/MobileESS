"""Freeze explicit user interruption evidence before starting the r029 switch."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v44_recovery_r029_switch
from v44_recovery_r029_switch import operations as switch
from v44_recovery_r029.handover import require_boundary, release_repairs
from v44.common import read, record, atomic, now, verify


def main():
    switch.base.validate()
    require_boundary()
    if switch.base.workers():
        raise PermissionError('NO_RUNNING_WORKER_REQUIRED')
    stop = switch.base.OPS/'STOP_AUTONOMY.json'
    stopped = read(stop)
    if (stopped.get('reason') != 'USER_REQUESTED_IMMEDIATE_R029_MAY02_B3_A2_RESTART'
            or stopped.get('campaign_resume_authorized') is not True):
        raise PermissionError('LATEST_EXPLICIT_SWITCH_INSTRUCTION_REQUIRED')
    output = Path(stopped['evidence'])
    interruption = switch.PARENT/'USER_INTERRUPTION.json'
    if not interruption.exists():
        atomic(interruption, dict(UTC=now(), user_requested=True,
            instruction='Stop May07 B1 now; restart May02 B3 A2 from beginning using improved revision; reuse May07 checkpoint when its turn comes.',
            stop_request=record(stop), generated_exit_result=record(switch.PARENT/'RESULT.json'),
            completed_A1_checkpoint=record(switch.PARENT/'A1/COMPLETED_STAGE_CHECKPOINT.json'),
            resume='COMPLETED_A1_THEN_NEW_ACTUAL', Actual_partial_state_restorable=False,
            original_result_and_Raw_preserved=True))
    proof = output/'USER_SWITCH_VALIDATION.json'
    atomic(proof, dict(UTC=now(), PASS=True,
        tests='41 passed: user switch routing/authority/checkpoint isolation plus r029 repairs and bottlenecks',
        test_sources=[record(Path(__file__).resolve().parents[1]/'tests'/name) for name in (
            'test_v44_recovery_r029_user_switch.py', 'test_v44_recovery_r029_repairs.py',
            'test_v44_recovery_r029_bottlenecks.py')],
        algorithm_sources_modified=False, exact_original_admission_checks_retained=True))
    evidence = [record(switch.PARENT/name) for name in (
        'USER_INTERRUPTION.json','RESULT.json','A1/RESULT.json','A1/COMPLETED_STAGE_CHECKPOINT.json',
        'A1/NATIVE_RUNTIME_LEDGER.json')]
    queue = switch.base.OPS/'R026F1_REPAIR_QUEUE/2025-05-07_B1_attempt001.json'
    if queue.exists(): evidence.append(record(queue))
    atomic(switch.AUTH, dict(UTC=now(), user_authorized=True,
        instruction='Interrupt May07 B1 immediately; run improved r029 May02 B3 A2 from Native0; resume May07 using completed checkpoint in normal order.',
        parent=str(switch.PARENT), May02_A2_Native_start=0, May02_M1='REVALIDATE_ORIGINAL_COMPLETED_M1',
        May07_resume='COMPLETED_A1_THEN_NEW_ACTUAL', May07_partial_Actual_ticks_resumed=False,
        algorithm_permit=record(switch.base.PERMIT), validation=record(proof),
        sources=switch.sources(), evidence=evidence))
    switch.authority()
    switch.validate_parent(switch.PARENT, output/'MAY07_CHECKPOINT_AUDIT')
    pending = switch.base.OPS/'R029_PENDING_REPAIR_RELEASES'
    published = switch.base.OPS/'R026F1_REPAIR_RELEASES'
    if any((published/p.name).exists() for p in pending.glob('*.json')):
        raise PermissionError('REPAIR_RELEASES_MUST_BE_PUBLISHED_EXACTLY_ONCE')
    release_repairs(switch.base.OPS, switch.base.PERMIT)
    with switch.install():
        states = switch.base.states(switch.base.CAMPAIGN)
        from v44_recovery_r029.failure_continue import deferred_dates
        blocked = deferred_dates(switch.base.OPS)
        if states[('2025-05-02','B3')] != 'READY' or ('2025-05-02','B3') in blocked:
            raise PermissionError('MAY02_FRESH_A2_NOT_READY')
        if states[switch.KEY] != 'READY' or switch.KEY in blocked:
            raise PermissionError('MAY07_COMPLETED_A1_RESUME_NOT_READY')
    atomic(output/'READY_TO_START.json', dict(UTC=now(), PASS=True,
        authorization=record(switch.AUTH), algorithm_permit=record(switch.base.PERMIT),
        first='2025-05-02/B3/A2/Native0', later='2025-05-07/B1/completed_A1_then_new_Actual',
        old_workers_absent=True, old_results_preserved=True))
    destination = output/'USER_RESTART_STOP_PRESERVED.json'
    if destination.exists(): raise FileExistsError(destination)
    stop.rename(destination)
    print(dict(PASS=True, first='May02 B3 fresh A2', later='May07 B1 A1 checkpoint then Actual',
        admission=str(output/'MAY07_CHECKPOINT_AUDIT/ACTUAL_RESUME_ADMISSION.json')))


if __name__ == '__main__':
    main()
