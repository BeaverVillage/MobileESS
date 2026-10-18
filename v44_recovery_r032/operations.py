"""Authenticated CC4 date repair and immediate May02 completed-M1 resume."""
from contextlib import contextmanager
from pathlib import Path
import argparse
from v44.common import read, record, verify, atomic, digest, now
from v44_recovery_r031 import operations as previous
from v44_recovery_r030 import operations as model
from . import cc4_date, parent_admission, fresh_a2

base = previous.base
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
ENTRY = 'v44_recovery_r032.operations'
ALGORITHM = previous.ALGORITHM
AMENDMENT = OPS/'R032_CC4_DATE_REPAIR_AUTHORIZATION.json'
PARENT = parent_admission.PARENT
INTERRUPTED = CAMPAIGN/'2025-05-03/B1/attempt002'
latest = base.latest


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    value = read(AMENDMENT)
    verify(value['sources']+[value[k] for k in ('previous_authorization','validation','completed_M1',
        'failed_A2','interrupted_B1_result','interruption','user_stop')])
    if (value['sources'] != sources() or value['policy'] != cc4_date.POLICY
            or value['previous_authorization'] != record(previous.AMENDMENT)
            or value['completed_M1'] != record(PARENT/'M1/RESULT.json')
            or not read(value['validation']['path'])['PASS']):
        raise PermissionError('R032_CC4_REPAIR_AUTHORITY_DRIFT')
    previous.authority()
    return value


def validate():
    value = previous.validate()
    authority()
    return dict(value, active_CC4_date_repair=record(AMENDMENT))


def command(args):
    if not isinstance(args, (list,tuple)): return args
    result = list(args)
    if (len(result)>=5 and result[1:3]==['-u','-m']
            and result[3] in (ALGORITHM,model.ENTRY,previous.ENTRY)
            and result[4] in ('--worker','--coordinator')):
        result[3] = ENTRY
        if '--algorithm' not in result: result += ['--algorithm',ALGORITHM]
    return result


def released(parent):
    return parent is not None and Path(parent).resolve() in (PARENT.resolve(), INTERRUPTED.resolve())


@contextmanager
def install():
    from v44_recovery_r029 import handover, failure_continue, fresh_a2_case
    # Compile before patching its original source function.
    resumed = fresh_a2.compiled()
    with previous.install(), cc4_date.install():
        retry, decorate, deferred = base.needs_retry, base.decorate, failure_continue.deferred_dates
        popen, activate, old_fresh = base.subprocess.Popen, handover.activate, fresh_a2_case.run

        def needs_retry(parent, result):
            if released(parent):
                authority()
                return not result.get('PASS')
            return retry(parent,result)

        def deferred_dates(ops):
            blocked = deferred(ops)
            for day,arm in list(blocked):
                if released(base.latest(CAMPAIGN,day,arm)):
                    authority(); blocked.discard((day,arm))
            return blocked

        def decorate_case(case, permit):
            authority(); case = decorate(case,permit)
            extra = sources()+[record(AMENDMENT)]
            case['R032_CC4_date_repair'] = record(AMENDMENT)
            if (case['day'],case['arm'])==('2025-05-02','B3'):
                case.pop('B3_new_M1_A2_M2_required',None)
                case['fresh_a2_parent'] = str(PARENT)
                case['R032_A2_from_completed_M1'] = True
                extra += [record(PARENT/name) for name in (
                    'M1/RESULT.json','M1/request.json','M1/COMPLETED_STAGE_CHECKPOINT.json',
                    'A1_REUSE.json','A2/request.json','A2/RESULT.json')]
            case['sources'] = list({r['path']:r for r in case['sources']+extra}.values())
            case['source_sha'] = digest(case['sources'])
            return case

        def launch(args,*a,**kw): return popen(command(args),*a,**kw)

        def activated(lease):
            activate(lease)
            path = OPS/'CURRENT_HANDOFF.json'; value = read(path)
            value.update(UTC=now(),active_revision='v44_recovery_r032',active_operational_entry=ENTRY,
                active_operational_permit=record(AMENDMENT),pending_revision=None,pending_permit=None,pending_validation=None,
                dispatch_hold_reason=None,windows_task='MobileESS_V44_Campaign004_Recovery_R032',
                collector=str(OPS/'collect_watchdog_r032.py'),active_source_auditor=str(OPS/'audit_active_revision_r032.py'),
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='아그럼 A2처음부터 재개해 M1 끝난시점이네 그럼',
                next='May02 B3 reuse completed tight M1; rebuild A2 with correct CC4 day; then M2 and Actual/Fresh. May03 onward r031 P1 improvement retained.')
            atomic(path,value)

        base.needs_retry,base.decorate = needs_retry,decorate_case
        failure_continue.deferred_dates,base.subprocess.Popen = deferred_dates,launch
        handover.activate,fresh_a2_case.run = activated,resumed
        try: yield
        finally:
            base.needs_retry,base.decorate = retry,decorate
            failure_continue.deferred_dates,base.subprocess.Popen = deferred,popen
            handover.activate,fresh_a2_case.run = activate,old_fresh


def states(root):
    with install(): return base.states(root)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true');p.add_argument('--watchdog',action='store_true')
    p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);args=p.parse_args()
    if sum((bool(args.worker),args.coordinator,args.watchdog))!=1: raise PermissionError('R032_ONE_OPERATION_REQUIRED')
    validate()
    with install():
        if args.worker:
            request=read(args.worker);model.authorize(request)
            if request.get('R032_CC4_date_repair')!=record(AMENDMENT):raise PermissionError('R032_EXPLICIT_REPAIR_AUTHORIZATION_REQUIRED')
            if request.get('fresh_a2_parent') and Path(request['fresh_a2_parent']).resolve()!=PARENT.resolve():raise PermissionError('R032_WRONG_M1_PARENT')
            base.worker(request)
        elif args.coordinator: base.run()
        else: base.watchdog()


if __name__=='__main__': main()
