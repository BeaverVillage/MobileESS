"""Quarantine one failed date while the next eligible date keeps running."""
from pathlib import Path
from v44.common import read,record,atomic,now


def defer(ops, case_root, result):
    case_root=Path(case_root);ops=Path(ops)
    if result.get('PASS') is True:raise ValueError('R023_CANNOT_DEFER_PASS')
    token='_'.join((case_root.parent.parent.name,case_root.parent.name,case_root.name))
    queue=ops/'R023_REPAIR_QUEUE';queue.mkdir(exist_ok=True)
    target=queue/(token+'.json')
    if not target.exists():
        ledgers=[record(p) for p in case_root.rglob('*LEDGER.json')]
        atomic(target,dict(UTC=now(),day=case_root.parent.parent.name,arm=case_root.parent.name,
            case_root=str(case_root),status='DEFERRED_FOR_DIAGNOSED_REPAIR',
            error=result.get('error',result.get('reason')),result=record(case_root/'RESULT.json'),
            Native_ledgers_at_failure=ledgers,original_results_modified=False,
            next_action='CONTINUE_NEXT_DATE; HOURLY_CODEX_DIAGNOSE_FIX_AND_RESUME_FAILED_DATE_WITH_NEW_RECEIPT'))
    marker=case_root/'R023_FAILURE_DEFERRED.json'
    if not marker.exists():atomic(marker,dict(UTC=now(),repair_queue=record(target),retry_without_diagnosed_fix=False))
    return target


def deferred_dates(ops):
    result=set()
    for p in (Path(ops)/'R023_REPAIR_QUEUE').glob('*.json'):
        value=read(p)
        # A separate release must be backed by a new validated revision/repair.
        release=Path(ops)/'R023_REPAIR_RELEASES'/p.name
        if release.exists():
            r=read(release)
            from v44.common import verify
            verify([r['repair_validation'],r['failed_queue_receipt']])
            if r['failed_queue_receipt']!=record(p):raise ValueError('R023_REPAIR_RELEASE_QUEUE_DRIFT')
            proof=read(r['repair_validation']['path'])
            if not proof.get('PASS') or not r.get('diagnosed_cause_fixed'):
                raise ValueError('R023_REPAIR_RELEASE_WITHOUT_VALIDATION')
            continue
        result.add(value['day'])
    return result


def technical_hold(stop,guard):
    return (stop.get('user_stop') is False
        and stop.get('reason')=='R022_A2_CONTINUATION_TECHNICAL_ERROR_HOLD'
        and Path(stop.get('failed_case','')).resolve()==Path(guard['protected_case_root']).resolve())


def authorized_retry(ops,parent,permit):
    marker=read(Path(parent)/'R023_FAILURE_DEFERRED.json')
    from v44.common import verify
    verify([marker['repair_queue']])
    queue=Path(marker['repair_queue']['path'])
    release=Path(ops)/'R023_REPAIR_RELEASES'/queue.name
    if not release.exists():return False
    value=read(release)
    verify([value['repair_validation'],value['failed_queue_receipt'],value['execution_permit']])
    if value['failed_queue_receipt']!=record(queue) or value['execution_permit']!=record(permit):
        raise ValueError('R023_REPAIR_RETRY_IDENTITY_DRIFT')
    return (value.get('diagnosed_cause_fixed') is True and value.get('allow_new_attempt') is True
        and read(value['repair_validation']['path']).get('PASS') is True)
