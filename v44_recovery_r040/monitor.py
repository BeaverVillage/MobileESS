"""Include exclusions as terminal case decisions, never as whole-wave failure."""
from . import operations as op
from v44_recovery_r039 import monitor as previous
from v44.common import read,record,verify,atomic,now

def collect():
    op.authority();value=previous.collect()
    state=read(op.STATE);value.update(case_isolation_authorization=record(op.AMENDMENT),r040_exclusions=[j for j in state['jobs'] if j['status']=='EXCLUDED'],
        r040_resolved_manifest=read(op.MANIFEST) if op.MANIFEST.exists() else None)
    atomic(op.CAMPAIGN/'V44_30MIN_WATCHDOG_RECEIPT.json',value);return value

def audit():
    op.authority();value=previous.audit();extra=[]
    for w in op.base.workers():
        args=w['cmdline']
        if op.ENTRY not in args:continue
        path=args[args.index('--worker')+1];request=read(path);op.authorize(request)
        extra.append(dict(pid=w['pid'],request=record(path)))
    value.update(authorization=record(op.AMENDMENT),r040_workers=extra,failed_case_cannot_block_healthy_Actual=True)
    atomic(op.OPS/'R040_ACTIVE_SOURCE_AUDIT.json',value);return value
