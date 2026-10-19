"""Retain exact raw bytes with duplicate storage reuse and background LZX compression."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import argparse
import time

from v44.common import read, record, verify, atomic, digest, now
from v44.locks import alive, exclusive_lock, process_identity
from v44_recovery_r035 import operations as previous
import sys
import v44_audit_storage_maintenance as storage_maintenance

base = previous.base
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
ENTRY = 'v44_recovery_r036.operations'
ALGORITHM = previous.ALGORITHM
POLICY = 'R036_EXACT_RAW_STORAGE_WITH_BYTE_VERIFIED_BACKGROUND_LZX'
AMENDMENT = OPS/'R036_STORAGE_MAINTENANCE_AUTHORIZATION.json'
HOLD_REASON = 'R036_EXACT_STORAGE_AFTER_MAY02_B3'
latest = base.latest
RAW_ROOT = CAMPAIGN.parent/'AC_AUDIT'/'svr11_revision01'
CLEANUP_CASE = CAMPAIGN/'2025-05-02'/'B3'/'attempt015'


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))] + [
        record(Path(__file__).resolve().parents[1]/name) for name in
        ('v44_audit_storage_maintenance.py',)]


def authority():
    value = read(AMENDMENT)
    verify(value['sources']+[value['previous_authorization'], value['validation']])
    if (value['sources'] != sources() or value['policy'] != POLICY or
            value['previous_authorization'] != record(previous.AMENDMENT) or
            value.get('native_checkpoint_fast_path') is not False or
            not read(value['validation']['path'])['PASS']):
        raise PermissionError('R036_LIGHTWEIGHT_AUTHORITY_DRIFT')
    previous.authority()
    return value


def validate():
    result = previous.validate()
    authority()
    return dict(result, exact_raw_storage=record(AMENDMENT))


def command(args):
    if not isinstance(args, (list, tuple)):
        return args
    result = list(args)
    entries = tuple(f'v44_recovery_r{n:03d}.operations' for n in range(29,36))
    if (len(result) >= 5 and result[1:3] == ['-u', '-m'] and
            result[3] in entries and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        if '--algorithm' not in result:
            result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import current_ac_performance, handover
    with previous.install():
        decorate, popen, activate = base.decorate, base.subprocess.Popen, handover.activate

        def decorate_case(case, permit):
            authority()
            case = decorate(case, permit)
            case['R036_storage_maintenance'] = record(AMENDMENT)
            case['sources'] = list({r['path']: r for r in
                case['sources']+sources()+[record(AMENDMENT)]}.values())
            case['source_sha'] = digest(case['sources'])
            return case

        def launch(args, *a, **kw):
            return popen(command(args), *a, **kw)

        def activated(lease):
            activate(lease)
            path = OPS/'CURRENT_HANDOFF.json'
            value = read(path)
            value.update(UTC=now(), active_revision='v44_recovery_r036',
                active_operational_entry=ENTRY, active_operational_permit=record(AMENDMENT),
                pending_revision=None, pending_permit=None, pending_validation=None,
                collector=str(OPS/'collect_watchdog_r036.py'),
                active_source_auditor=str(OPS/'audit_active_revision_r036.py'),
                windows_task='MobileESS_V44_Campaign004_Recovery_R032',
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='캠페인에서 저장하는 것도 효율화가 필요할 것 같아. 수정해. 기존 중복 정리는 5월 2일 B3 종료 후.',
                next='Inherited exact shared storage plus low priority byte-verified compression of closed audits. Duplicate removal stays after May02 B3; no unique raw path or record removed.')
            atomic(path, value)

        base.decorate, base.subprocess.Popen, handover.activate = decorate_case, launch, activated
        try:
            yield
        finally:
            base.decorate, base.subprocess.Popen, handover.activate = decorate, popen, activate


def ready():
    return not base.workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))


def states(root):
    with install():
        return base.states(root)


def authorize(request):
    previous.authorize(request)
    if request.get('R036_storage_maintenance') != record(AMENDMENT):
        raise PermissionError('R036_EXPLICIT_LIGHTWEIGHT_AUTHORIZATION_REQUIRED')


def cleanup_after_case():
    value=previous.cleanup_after_case()
    storage_maintenance.start(sys.modules[__name__])
    return value


def handover():
    """The running worker exits naturally; no process is killed or suspended."""
    from v42_may_campaign.common import LockBusy
    with exclusive_lock(OPS/'R036_HANDOVER.lock'):
        authority()
        while True:
            stop = OPS/'STOP_AUTONOMY.json'
            if not stop.exists():
                if not (OPS/'R036_HANDOVER_APPLIED.json').exists():
                    raise PermissionError('R036_OWN_DISPATCH_HOLD_REQUIRED')
                break
            value = read(stop)
            if value.get('reason') != HOLD_REASON or value.get('user_stop'):
                atomic(OPS/'R036_HANDOVER_BLOCKED.json', dict(UTC=now(), reason='OTHER_OR_USER_STOP_PRESERVED'))
                return
            if ready():
                try:
                    with exclusive_lock(OPS/'SUPERVISOR.lock'):
                        validate()
                        cleanup_after_case()
                        atomic(OPS/'R036_HANDOVER_APPLIED.json', dict(UTC=now(), PASS=True,
                            authorization=record(AMENDMENT), no_worker_terminated=True,
                            native_checkpoint_fast_path=False))
                        stop.rename(OPS/'R036_DISPATCH_HOLD_PRESERVED.json')
                    break
                except LockBusy:
                    pass
            atomic(OPS/'R036_HANDOVER_HEARTBEAT.json', dict(UTC=now(), **process_identity(),
                active_workers=[p['pid'] for p in base.workers()], active_worker_untouched=True))
            time.sleep(15.)
    with install():
        base.watchdog()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--coordinator', action='store_true')
    parser.add_argument('--watchdog', action='store_true')
    parser.add_argument('--handover', action='store_true')
    parser.add_argument('--storage-maintenance', action='store_true')
    parser.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    args = parser.parse_args()
    if sum((bool(args.worker), args.coordinator, args.watchdog, args.handover, args.storage_maintenance)) != 1:
        raise PermissionError('R036_ONE_OPERATION_REQUIRED')
    validate()
    if args.storage_maintenance:
        return storage_maintenance.run(sys.modules[__name__])
    if args.handover:
        return handover()
    with install():
        if args.worker:
            request = read(args.worker)
            authorize(request)
            base.worker(request)
        elif args.coordinator:
            base.run()
        else:
            base.watchdog()


if __name__ == '__main__':
    main()
