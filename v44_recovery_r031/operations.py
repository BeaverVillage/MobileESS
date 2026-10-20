"""Switch after the running case exits, then retain r030 with next-date P1."""
from contextlib import contextmanager
from pathlib import Path
import argparse
import time
from v44.common import read, record, verify, atomic, digest, now
from v44.locks import alive, exclusive_lock, process_identity
from v44_recovery_r030 import operations as previous
from . import p1_expansion

base = previous.base
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
ENTRY = 'v44_recovery_r031.operations'
ALGORITHM = previous.ALGORITHM
AMENDMENT = OPS/'R031_P1_PERFORMANCE_AUTHORIZATION.json'
latest = base.latest


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    value = read(AMENDMENT)
    verify(value['sources'] + [value['previous_authorization'], value['validation']])
    if (value['sources'] != sources() or value['policy'] != p1_expansion.POLICY
            or value['previous_authorization'] != record(previous.AMENDMENT)
            or not read(value['validation']['path'])['PASS']):
        raise PermissionError('R031_PERFORMANCE_AUTHORITY_DRIFT')
    previous.authority()
    return value


def validate():
    value = previous.validate()
    authority()
    return dict(value, active_performance_authorization=record(AMENDMENT))


def command(args):
    if not isinstance(args, (list, tuple)):
        return args
    result = list(args)
    if (len(result) >= 5 and result[1:3] == ['-u', '-m']
            and result[3] in (ALGORITHM, previous.ENTRY)
            and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        if '--algorithm' not in result:
            result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import handover, conditional_campaign
    with previous.install():
        decorate, popen, activate = base.decorate, base.subprocess.Popen, handover.activate
        original_case = conditional_campaign.run_case

        def improved_case(request):
            # The sealed voltage adapter first inspects worker.a_stage. Install
            # only after that adapter and the original rebuild routing exist.
            with p1_expansion.install():
                return original_case(request)

        def decorate_case(case, permit):
            authority()
            case = decorate(case, permit)
            case['R031_P1_performance_authorization'] = record(AMENDMENT)
            case['sources'] = list({r['path']: r for r in case['sources'] + sources() + [record(AMENDMENT)]}.values())
            case['source_sha'] = digest(case['sources'])
            return case

        def launch(args, *a, **kw):
            return popen(command(args), *a, **kw)

        def activated(lease):
            activate(lease)
            path = OPS/'CURRENT_HANDOFF.json'
            value = read(path)
            value.update(UTC=now(), active_revision='v44_recovery_r031',
                active_operational_entry=ENTRY, active_operational_permit=record(AMENDMENT),
                pending_revision=None, pending_permit=None, pending_validation=None,
                windows_task='MobileESS_V44_Campaign004_Recovery_R031',
                collector=str(OPS/'collect_watchdog_r031.py'),
                active_source_auditor=str(OPS/'audit_active_revision_r031.py'),
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='Apply P1 repeat-class improvement from next date; preserve May02 and running May03 B1.',
                next='B3 A2 P1 May03 onward bounded complete native graphs after repeated negative pricing; all full pricing and acceptance checks retained')
            atomic(path, value)

        base.decorate, base.subprocess.Popen, handover.activate = decorate_case, launch, activated
        conditional_campaign.run_case = improved_case
        try:
            yield
        finally:
            base.decorate, base.subprocess.Popen, handover.activate = decorate, popen, activate
            conditional_campaign.run_case = original_case


def states(root):
    with install():
        return base.states(root)


def handover_ready(authorization):
    protected = Path(authorization['protected_case_root'])
    return ((protected/'RESULT.json').exists() and not base.workers()
            and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json')))


def handover():
    """Never kill a worker; keep the dispatch hold until all old owners exit."""
    with exclusive_lock(OPS/'R031_HANDOVER.lock'):
        authorization = authority()
        while True:
            stop = OPS/'STOP_AUTONOMY.json'
            # On reboot/resume, an already completed handover runs normally.
            if not stop.exists():
                if not (OPS/'R031_HANDOVER_APPLIED.json').exists():
                    raise PermissionError('R031_OWN_DISPATCH_HOLD_REQUIRED')
                break
            value = read(stop)
            if value.get('reason') != 'R031_NEXT_CASE_HANDOVER' or value.get('user_stop'):
                atomic(OPS/'R031_HANDOVER_BLOCKED.json', dict(UTC=now(), reason='OTHER_OR_USER_STOP_PRESERVED'))
                return
            if handover_ready(authorization):
                # The previous watchdog wakes every 30 seconds. Its OS lock
                # must be released before clearing the old dispatch hold.
                with exclusive_lock(OPS/'SUPERVISOR.lock'):
                    validate()
                    atomic(OPS/'R031_HANDOVER_APPLIED.json', dict(UTC=now(), PASS=True,
                        protected_case_result=record(Path(authorization['protected_case_root'])/'RESULT.json'),
                        authorization=record(AMENDMENT), no_worker_terminated=True))
                    stop.rename(OPS/'R031_DISPATCH_HOLD_PRESERVED.json')
                break
            atomic(OPS/'R031_HANDOVER_HEARTBEAT.json', dict(UTC=now(), **process_identity(),
                protected_case=authorization['protected_case_root'],
                active_workers=[p['pid'] for p in base.workers()], active_worker_untouched=True))
            time.sleep(15.)
    with install():
        base.watchdog()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--coordinator', action='store_true')
    parser.add_argument('--handover', action='store_true')
    parser.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    args = parser.parse_args()
    if sum((bool(args.worker), args.coordinator, args.handover)) != 1:
        raise PermissionError('R031_ONE_OPERATION_REQUIRED')
    validate()
    if args.handover:
        return handover()
    with install():
        if args.worker:
            request = read(args.worker)
            previous.authorize(request)
            if request.get('R031_P1_performance_authorization') != record(AMENDMENT):
                raise PermissionError('R031_EXPLICIT_WORKER_AUTHORIZATION_REQUIRED')
            base.worker(request)
        else:
            base.run()


if __name__ == '__main__':
    main()
