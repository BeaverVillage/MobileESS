"""Persistent r030 campaign entry: new B3 M1 -> A2 -> M2, all future dates."""
from contextlib import contextmanager
from pathlib import Path
import argparse
from v44.common import read, record, verify, atomic, digest, now
from v44_recovery_r029 import operations as base
from v44_recovery_r029_switch import operations as previous
from .m1_voltage import POLICY, LOWER, UPPER

ENTRY = 'v44_recovery_r030.operations'
ALGORITHM = previous.ALGORITHM
AMENDMENT = base.OPS/'R030_B3_M1_VOLTAGE_AMENDMENT.json'
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
latest = base.latest


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    value = read(AMENDMENT)
    verify([value['algorithm_permit'], value['user_authorization'], value['validation'],
            value['previous_operational_authorization']] + value['sources'])
    if (value['policy'] != POLICY or value['arm'] != 'B3' or value['stage'] != 'M1'
            or value['voltage_band_pu'] != [LOWER, UPPER]
            or value['algorithm_permit'] != record(base.PERMIT)
            or value['sources'] != sources() or not read(value['validation']['path'])['PASS']
            or value['previous_operational_authorization'] != record(previous.AUTH)):
        raise PermissionError('R030_MODEL_AMENDMENT_IDENTITY_DRIFT')
    previous.authority()
    return value


def authorize(request):
    authority()
    if request.get('B3_M1_voltage_amendment') != record(AMENDMENT):
        raise PermissionError('R030_EXPLICIT_B3_M1_MODEL_AMENDMENT_REQUIRED')


def validate():
    value = base.validate()
    authority()
    return dict(value, active_model_amendment=record(AMENDMENT), active_model_sources=sources())


def states(root):
    with install():
        return base.states(root)


def started_under_amendment(parent):
    path = Path(parent)/'START.json'
    if not path.exists(): return False
    return record(AMENDMENT) in read(path).get('sources', [])


def model_restart(parent, result):
    # One new model per pending B3 case. Preserve already completed comparisons.
    return (parent is not None and Path(parent).parent.name == 'B3'
        and not result.get('PASS') and result.get('status') != 'COMPLETE'
        and not started_under_amendment(parent))


def command(args):
    if not isinstance(args, (list, tuple)): return args
    result = list(args)
    if (len(result) >= 5 and result[1:4] == ['-u', '-m', ALGORITHM]
            and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import failure_continue, handover, conditional_campaign
    from .m1_voltage import install as m1_install
    # Install the model scope only after sealed r029 has compiled its own
    # runtime adapters; those adapters inspect the original function source.
    with previous.install():
        retry, decorate = base.needs_retry, base.decorate
        deferred, popen, activate = failure_continue.deferred_dates, base.subprocess.Popen, handover.activate
        run_case = conditional_campaign.run_case

        def amended_case(request):
            with m1_install(authorize):
                return run_case(request)

        def needs_retry(parent, result):
            if model_restart(parent, result):
                authority()
                return True
            return retry(parent, result)

        def deferred_dates(ops):
            blocked = deferred(ops)
            for day, arm in list(blocked):
                parent = base.latest(base.CAMPAIGN, day, arm)
                if parent is not None and (parent/'RESULT.json').exists() and model_restart(parent, read(parent/'RESULT.json')):
                    authority()
                    blocked.discard((day, arm))
            return blocked

        def decorate_case(case, permit):
            authority()
            case = decorate(case, permit)
            case['B3_M1_voltage_amendment'] = record(AMENDMENT)
            case['sources'] = list({r['path']: r for r in case['sources'] + sources() + [record(AMENDMENT)]}.values())
            case['source_sha'] = digest(case['sources'])
            if case['arm'] == 'B3':
                for key in ('fresh_a2_parent', 'a2_checkpoint_parent', 'wall_resume_parent', 'actual_resume_parent', 'resume_of', 'resume_parent'):
                    case.pop(key, None)
                case['B3_new_M1_A2_M2_required'] = True
            return case

        def launch(args, *a, **kw):
            return popen(command(args), *a, **kw)

        def activate_r030(lease):
            path = base.OPS/'CURRENT_HANDOFF.json'; value = read(path)
            value.update(UTC=now(), active_revision='v44_recovery_r030', algorithm_revision='v44_recovery_r029',
                active_operational_entry=ENTRY, active_operational_permit=record(AMENDMENT),
                permit=record(base.PERMIT), pending_revision=None, pending_permit=None, pending_validation=None,
                dispatch_hold_reason=None, active_lease=lease,
                windows_task='MobileESS_V44_Campaign004_Recovery_R030',
                collector=str(base.OPS/'collect_watchdog_r030.py'),
                active_source_auditor=str(base.OPS/'audit_active_revision_r030.py'),
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='All future B3 M1 voltage bounds are 0.955..1.045 pu; stop current May02 and rerun M1 A2 M2.',
                next='May02 B3 new tight M1 then A2 then M2; future B3 M1 all dates same tight band; May07 B1 completed A1 reuse retained')
            atomic(path, value)

        base.needs_retry, base.decorate = needs_retry, decorate_case
        failure_continue.deferred_dates, base.subprocess.Popen = deferred_dates, launch
        handover.activate = activate_r030
        conditional_campaign.run_case = amended_case
        try:
            yield
        finally:
            base.needs_retry, base.decorate = retry, decorate
            failure_continue.deferred_dates, base.subprocess.Popen = deferred, popen
            handover.activate = activate
            conditional_campaign.run_case = run_case


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', type=Path); p.add_argument('--coordinator', action='store_true')
    p.add_argument('--watchdog', action='store_true'); p.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    args = p.parse_args()
    if sum((bool(args.worker), args.coordinator, args.watchdog)) != 1:
        raise PermissionError('R030_ONE_OPERATION_REQUIRED')
    base.validate(); authority()
    with install():
        if args.worker:
            request = read(args.worker); authorize(request)
            if request['arm'] == 'B3' and any(request.get(k) for k in ('fresh_a2_parent','a2_checkpoint_parent','wall_resume_parent','actual_resume_parent','resume_of','resume_parent')):
                raise PermissionError('R030_FRESH_B3_M1_A2_M2_REQUIRED')
            base.worker(request)
        elif args.coordinator: base.run()
        else: base.watchdog()


if __name__ == '__main__': main()
