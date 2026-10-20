"""Restore verified original r023 configuration without dispatching a case."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import v44_recovery_r023
from v44.common import read, record, atomic, now, verify
from v44.locks import coordinator, alive
from v44_recovery_r023 import operations as ops, handover


def run():
    destination = Path('D:/MobileESS_V44/development/r023/rollback_20261018')
    applied = destination / 'APPLIED.json'
    assert not applied.exists(), 'ROLLBACK_RECEIPT_ALREADY_EXISTS'
    permit = ops.validate()
    handover.require_boundary()
    assert not ops.workers()
    assert not alive(read(ops.CAMPAIGN / 'COORDINATOR_LEASE.json'))
    stop = read(ops.OPS / 'STOP_AUTONOMY.json')
    assert stop['user_stop']
    tests = ET.parse(destination / 'regressions.xml').getroot()
    suites = [tests] if tests.tag == 'testsuite' else list(tests)
    assert sum(int(s.get('tests', 0)) for s in suites) == 250
    assert not any(int(s.get('failures', 0)) + int(s.get('errors', 0)) for s in suites)
    case = ops.CAMPAIGN / '2025-05-02/B3/attempt010'
    frozen = [record(case / name) for name in ('RESULT.json', 'A2/RESULT.json', 'A2/NATIVE_RUNTIME_LEDGER.json')]
    account = read(case / 'A2/NATIVE_RUNTIME_LEDGER.json')
    assert account['inflight'] is None
    assert abs(account['measured_Native_Runtime'] - 555.2489993572235) < 1e-6
    atomic(destination / 'PREVIOUS_USER_STOP.json', stop)
    atomic(ops.OPS / 'STOP_AUTONOMY.json', dict(UTC=now(), user_stop=True,
        reason='USER_R023_ROLLBACK_KEEP_CAMPAIGN_STOPPED', scope='NO_AUTOMATIC_CAMPAIGN_DISPATCH',
        instruction='Latest user requests rollback to original r023, before r024 adaptive pricing. Earlier explicit May02 stop remains in force; do not resume without user instruction.',
        configured_revision='v44_recovery_r023', May02_Native_preserved=account['measured_Native_Runtime']))
    original_atomic = handover.atomic
    def preserve(path, value):
        if Path(path).name == 'R023_PRE_ACTIVATION_HANDOFF_PRESERVED.json':
            path = destination / 'PREVIOUS_HANDOFF.json'
        return original_atomic(path, value)
    with coordinator(ops.CAMPAIGN) as lease:
        with patch.object(handover, 'atomic', preserve):
            handover.activate(lease)
        current = read(ops.OPS / 'CURRENT_HANDOFF.json')
        current.update(UTC=now(), active_revision='v44_recovery_r023', algorithm_revision='v44_recovery_r023',
            original_operational_revision='v44_recovery_r023', operational_patch_revision='v44_recovery_r023',
            active_operational_entry='v44_recovery_r023.operations',
            performance_revision_state='R023_ROLLBACK_VERIFIED_USER_HOLD',
            revision_selection='Original sealed r023 restored. No r024 adaptive pricing, gain-feedback selection or 15-percent expansion. r023 row generation, stability and Native5400 retained.',
            latest_user_instruction='Rollback to r023 before adaptive expansion. Preserve earlier explicit May02 execution stop.',
            dispatch_hold_reason='USER_EXPLICIT_STOP_REQUIRES_EXPLICIT_RESUME',
            protected_case=str(case), protected_case_finished_receipt=record(case / 'RESULT.json'),
            protected_worker_pid=None, pending_windows_task=None,
            rollback_verification=record(destination / 'regressions.xml'),
            next='Remain stopped with r023 configured; no automatic retry, checkpoint replay or Native reset is authorized by this configuration rollback.')
        atomic(ops.OPS / 'CURRENT_HANDOFF.json', current)
    verify(frozen)
    ops.validate()
    receipt = dict(UTC=now(), PASS=True, configured_revision='v44_recovery_r023',
        original_sealed_sources=ops.sources(), original_permit=record(ops.PERMIT),
        regression_tests=250, regressions=record(destination / 'regressions.xml'),
        no_adaptive_pricing_module=not (Path(ops.__file__).parent / 'adaptive_pricing.py').exists(),
        Native_total=5400, Phase_I_separate_timeout=None,
        r023_original_basic_candidate_expansion_retained=True,
        r024_adaptive_gain_expansion_enabled=False,
        configuration_only=True, campaign_stays_stopped=True, new_Native_calls=0,
        May02_preserved=frozen, May02_Native_seconds=account['measured_Native_Runtime'],
        previous_handoff=record(destination / 'PREVIOUS_HANDOFF.json'),
        current_handoff=record(ops.OPS / 'CURRENT_HANDOFF.json'),
        stop=record(ops.OPS / 'STOP_AUTONOMY.json'))
    atomic(applied, receipt)
    atomic(ops.OPS / 'R023_USER_ROLLBACK_20261018_APPLIED.json', receipt)
    diagnostic = ops.OPS / 'MAY01_PHASEI_DIAGNOSTIC_STATUS.json'
    value = read(diagnostic)
    result_path = Path(value['diagnostic_directory']) / 'RESULT.json'
    result = read(result_path)
    assert result['PASS'] and result['activation_rounds'] == 0
    value.update(UTC=now(), status='COMPLETE_PHASE_I_PASS_AFTER_DIAGNOSTIC_INIT_FIX',
        result=record(result_path), Native_seconds=result['Native_seconds'], activation_rounds=0,
        limitation='No adaptive candidate expansion occurred, so convergence of repeated <15% pricing rounds is not demonstrated.',
        configured_production_revision='v44_recovery_r023', automatic_resume_authorized=False)
    atomic(diagnostic, value)
    print(dict(PASS=True, revision='r023', regressions=250, campaign_stopped=True,
               new_Native=0, May02_Native=account['measured_Native_Runtime']))


if __name__ == '__main__':
    run()
