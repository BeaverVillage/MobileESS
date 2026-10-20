"""Resume May02 A2 first and reuse the interrupted May07 completed A1 later."""
from contextlib import contextmanager
from pathlib import Path
from fractions import Fraction
import argparse
import sys

from v44.common import read, record, verify, atomic, digest, now
from v44.locks import alive
from v44_recovery_r029 import operations as base

ENTRY = 'v44_recovery_r029_switch.operations'
ALGORITHM = 'v44_recovery_r029.operations'
AUTH = base.OPS/'R029_USER_SWITCH_AUTHORIZATION.json'
PARENT = base.CAMPAIGN/'2025-05-07/B1/attempt001'
KEY = ('2025-05-07', 'B1')


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    value = read(AUTH)
    verify([value['algorithm_permit'], value['validation']] + value['sources'] + value['evidence'])
    if (value['algorithm_permit'] != record(base.PERMIT) or value['sources'] != sources()
            or value.get('parent') != str(PARENT)
            or value.get('May02_A2_Native_start') != 0
            or value.get('May07_resume') != 'COMPLETED_A1_THEN_NEW_ACTUAL'
            or value.get('user_authorized') is not True
            or read(value['validation']['path']).get('PASS') is not True):
        raise PermissionError('R029_USER_SWITCH_AUTHORITY_DRIFT')
    return value


def validate_parent(parent, output):
    """Preserve every original B1 FULL, source, exact gap and AIDC check."""
    from v44_recovery_r029 import wall_resume
    from v44.checkpoints import checked
    from v44.daily import load_aidc
    parent, output = Path(parent), Path(output)
    if parent.resolve() != PARENT.resolve():
        return wall_resume_original(parent, output)
    authority()
    start = read(parent/'START.json')
    if (start['day'], start['arm']) != KEY or alive(start):
        raise PermissionError('USER_INTERRUPTED_SAME_DATE_DEAD_B1_REQUIRED')
    if not read(parent/'USER_INTERRUPTION.json').get('user_requested'):
        raise PermissionError('EXPLICIT_USER_INTERRUPTION_REQUIRED')
    verify(start['sources'])
    request = dict(day=KEY[0], arm=KEY[1], stage='A1', source_sha=start['source_sha'], case_root=str(parent))
    checked(parent/'A1/COMPLETED_STAGE_CHECKPOINT.json', request, 'COMPLETED')
    result = read(parent/'A1/RESULT.json')
    if (not result.get('PASS') or not result.get('FULL_feasible')
            or not result.get('independent_Global_LB_validated')
            or not 0 <= result.get('certified_gap', 1) <= .005):
        raise PermissionError('ORIGINAL_FULL_A1_AND_INDEPENDENT_GAP_REQUIRED')
    exact = (Fraction(result['exact_UB'])-Fraction(result['exact_LB']))/abs(Fraction(result['exact_UB']))
    if not 0 <= exact <= Fraction(5, 1000) or abs(float(exact)-result['certified_gap']) > 1e-12:
        raise PermissionError('INDEPENDENT_EXACT_A1_GAP_REPLAY_FAILED')
    folder = Path(result['AIDC_reference']['path']).parent
    payload, doc = load_aidc(folder, KEY[0])
    identity = doc['identity']
    if ((identity['day'], identity['arm']) != KEY or not identity['FULL_feasible']
            or not identity['independent_Global_LB_validated']):
        raise PermissionError('ORIGINAL_A1_AXIS_OR_CERTIFICATE_DRIFT')
    verify([result['AIDC_reference']])
    atomic(output/'ACTUAL_RESUME_ADMISSION.json', dict(UTC=now(), PASS=True,
        day=KEY[0], arm=KEY[1], parent=record(parent/'A1/RESULT.json'),
        completed_stage_checkpoint=record(parent/'A1/COMPLETED_STAGE_CHECKPOINT.json'),
        interruption=record(parent/'USER_INTERRUPTION.json'), original_failure=record(parent/'RESULT.json'),
        AIDC_reference=result['AIDC_reference'], independent_Global_LB_validated=True,
        certified_gap=result['certified_gap'], FULL_feasible=True, new_optimization_calls=0,
        original_failure_preserved=True, source_initial_tap_queue='NEW_INDEPENDENT_CONTEXT_NO_PARTIAL_REUSE',
        partial_Actual_ticks_resumed=False, authorization=record(AUTH)))
    return folder, None, None


from v44_recovery_r029.wall_resume import validate_parent as wall_resume_original


def command(args):
    """Route only the sealed coordinator's campaign child processes."""
    if not isinstance(args, (list, tuple)):
        return args
    result = list(args)
    if (len(result) >= 5 and result[1:4] == ['-u', '-m', ALGORITHM]
            and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import failure_continue, wall_resume, handover
    retry, decorate = base.needs_retry, base.decorate
    deferred, popen, activate = failure_continue.deferred_dates, base.subprocess.Popen, handover.activate

    def needs_retry(parent, result):
        if parent is not None and Path(parent).resolve() == PARENT.resolve():
            authority()
            return not result.get('PASS') and (PARENT/'USER_INTERRUPTION.json').exists()
        return retry(parent, result)

    def deferred_dates(ops):
        blocked = deferred(ops)
        if base.latest(base.CAMPAIGN, *KEY) == PARENT:
            authority()
            blocked.discard(KEY)
        return blocked

    def decorate_case(case, permit):
        authority()
        case = decorate(case, permit)
        extra = sources() + [record(AUTH)] + read(AUTH)['evidence']
        case['sources'] = list({r['path']: r for r in case['sources'] + extra}.values())
        case['source_sha'] = digest(case['sources'])
        case['user_switch_authorization'] = record(AUTH)
        if (case['day'], case['arm']) == KEY and base.latest(base.CAMPAIGN, *KEY) == PARENT:
            case['wall_resume_parent'] = str(PARENT)
            case['resume_completed_A1_only'] = True
        return case

    def launch(args, *a, **kw):
        return popen(command(args), *a, **kw)

    def activate_switch(lease):
        activate(lease)
        p = base.OPS/'CURRENT_HANDOFF.json'
        value = read(p)
        value.update(UTC=now(), active_operational_entry=ENTRY, user_switch_authorization=record(AUTH),
            windows_task='MobileESS_V44_Campaign004_Recovery_R029_UserSwitch',
            entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
            next='May02 B3 fresh A2 Native0 first; May07 B1 completed A1 then fresh Actual in normal order')
        atomic(p, value)

    base.needs_retry, base.decorate = needs_retry, decorate_case
    failure_continue.deferred_dates = deferred_dates
    base.subprocess.Popen = launch
    wall_resume.validate_parent = validate_parent
    handover.activate = activate_switch
    try:
        yield
    finally:
        base.needs_retry, base.decorate = retry, decorate
        failure_continue.deferred_dates, base.subprocess.Popen = deferred, popen
        wall_resume.validate_parent, handover.activate = wall_resume_original, activate


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', type=Path)
    p.add_argument('--coordinator', action='store_true')
    p.add_argument('--watchdog', action='store_true')
    p.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    a = p.parse_args()
    if sum((bool(a.worker), a.coordinator, a.watchdog)) != 1:
        raise PermissionError('ONE_EXPLICIT_OPERATION_REQUIRED')
    base.validate()
    authority()
    with install():
        if a.worker:
            request = read(a.worker)
            if request.get('user_switch_authorization') != record(AUTH):
                raise PermissionError('WORKER_USER_SWITCH_REQUEST_IDENTITY_DRIFT')
            base.worker(request)
        elif a.coordinator:
            base.run()
        else:
            base.watchdog()


if __name__ == '__main__':
    main()
