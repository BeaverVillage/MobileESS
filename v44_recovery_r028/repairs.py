"""Explicitly release only diagnosed implementation errors and dependencies."""
from pathlib import Path
from v44.common import read,record,verify


def legacy_retry(parent,result,ops,permit):
    parent=Path(parent);token='_'.join((parent.parent.parent.name,parent.parent.name,parent.name))
    release=Path(ops)/'R026F1_REPAIR_RELEASES'/(token+'.json')
    if not release.exists():return False
    r=read(release)
    verify([r['repair_validation'],r['execution_permit'],r['failed_result']])
    if r['execution_permit']!=record(permit) or r['failed_result']!=record(parent/'RESULT.json'):
        raise ValueError('R028_LEGACY_REPAIR_IDENTITY_DRIFT')
    proof=read(r['repair_validation']['path'])
    if not proof.get('PASS') or not r.get('allow_new_attempt') or not r.get('diagnosed_cause_fixed'):return False
    return (result.get('error')=="TypeError(\"a_stage() missing 1 required keyword-only argument: 'm1'\")"
        or result.get('status')=='BLOCKED_DEPENDENCY')
