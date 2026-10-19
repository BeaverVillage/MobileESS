"""Add exact audit encoding after a natural case boundary."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import argparse
import time

from v44.common import read, record, verify, atomic, digest, now
from v44.locks import alive, exclusive_lock, process_identity
from v44_recovery_r032 import operations as previous
from v44_actual_audit_encoding import ExactImmutableEncoding

base = previous.base
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
ENTRY = 'v44_recovery_r033.operations'
ALGORITHM = previous.ALGORITHM
POLICY = 'R033_EXACT_IMMUTABLE_JSON_ENCODING_NO_NATIVE_STATE_RESTORE'
AMENDMENT = OPS/'R033_EXACT_AUDIT_ENCODING_AUTHORIZATION.json'
HOLD_REASON = 'R033_EXACT_ENCODING_NATURAL_BOUNDARY'
latest = base.latest


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))] + [
        record(Path(__file__).resolve().parents[1]/'v44_actual_audit_encoding.py')]


def authority():
    value = read(AMENDMENT)
    verify(value['sources']+[value['previous_authorization'], value['validation']])
    if (value['sources'] != sources() or value['policy'] != POLICY or
            value['previous_authorization'] != record(previous.AMENDMENT) or
            value.get('native_checkpoint_fast_path') is not False or
            not read(value['validation']['path'])['PASS']):
        raise PermissionError('R033_EXACT_ENCODING_AUTHORITY_DRIFT')
    previous.authority()
    return value


def validate():
    result = previous.validate()
    authority()
    return dict(result, exact_audit_encoding=record(AMENDMENT))


def command(args):
    if not isinstance(args, (list, tuple)):
        return args
    result = list(args)
    entries = (ALGORITHM, previous.ENTRY, previous.previous.ENTRY,
               previous.previous.previous.ENTRY)
    if (len(result) >= 5 and result[1:3] == ['-u', '-m'] and
            result[3] in entries and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        if '--algorithm' not in result:
            result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import current_ac_performance, handover
    with previous.install(), patch.object(current_ac_performance, 'ExactAuditEncoding', ExactImmutableEncoding):
        decorate, popen, activate = base.decorate, base.subprocess.Popen, handover.activate

        def decorate_case(case, permit):
            authority()
            case = decorate(case, permit)
            case['R033_exact_audit_encoding'] = record(AMENDMENT)
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
            value.update(UTC=now(), active_revision='v44_recovery_r033',
                active_operational_entry=ENTRY, active_operational_permit=record(AMENDMENT),
                pending_revision=None, pending_permit=None, pending_validation=None,
                collector=str(OPS/'collect_watchdog_r033.py'),
                active_source_auditor=str(OPS/'audit_active_revision_r033.py'),
                windows_task='MobileESS_V44_Campaign004_Recovery_R032',
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='응 한번 확인해봐. 속도 높이고 문제 없는지.',
                next='All inherited scheduling and physics unchanged. Only byte-identical immutable audit JSON encoding is reused; native checkpoint restoration rejected.')
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
    previous.model.authorize(request)
    if request.get('R032_CC4_date_repair') != record(previous.AMENDMENT):
        raise PermissionError('R033_INHERITED_CC4_AUTHORIZATION_REQUIRED')
    if (request.get('fresh_a2_parent') and
            Path(request['fresh_a2_parent']).resolve() != previous.PARENT.resolve()):
        raise PermissionError('R033_INHERITED_EXACT_M1_PARENT_REQUIRED')
    if request.get('R033_exact_audit_encoding') != record(AMENDMENT):
        raise PermissionError('R033_EXPLICIT_ENCODING_AUTHORIZATION_REQUIRED')


def handover():
    """The running worker exits naturally; no process is killed or suspended."""
    from v42_may_campaign.common import LockBusy
    with exclusive_lock(OPS/'R033_HANDOVER.lock'):
        authority()
        while True:
            stop = OPS/'STOP_AUTONOMY.json'
            if not stop.exists():
                if not (OPS/'R033_HANDOVER_APPLIED.json').exists():
                    raise PermissionError('R033_OWN_DISPATCH_HOLD_REQUIRED')
                break
            value = read(stop)
            if value.get('reason') != HOLD_REASON or value.get('user_stop'):
                atomic(OPS/'R033_HANDOVER_BLOCKED.json', dict(UTC=now(), reason='OTHER_OR_USER_STOP_PRESERVED'))
                return
            if ready():
                try:
                    with exclusive_lock(OPS/'SUPERVISOR.lock'):
                        validate()
                        atomic(OPS/'R033_HANDOVER_APPLIED.json', dict(UTC=now(), PASS=True,
                            authorization=record(AMENDMENT), no_worker_terminated=True,
                            native_checkpoint_fast_path=False))
                        stop.rename(OPS/'R033_DISPATCH_HOLD_PRESERVED.json')
                    break
                except LockBusy:
                    pass
            atomic(OPS/'R033_HANDOVER_HEARTBEAT.json', dict(UTC=now(), **process_identity(),
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
    parser.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    args = parser.parse_args()
    if sum((bool(args.worker), args.coordinator, args.watchdog, args.handover)) != 1:
        raise PermissionError('R033_ONE_OPERATION_REQUIRED')
    validate()
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
