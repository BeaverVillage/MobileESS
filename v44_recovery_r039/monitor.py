"""Inspect the running r038 preparation and the additional Actual together."""
from . import operations as op
from v44_recovery_r038 import monitor as inherited
from v44.common import read,record,verify,atomic,now
from v44.locks import alive

def collect():
    op.authority();value=inherited.collect()
    value.update(latency_authorization=record(op.AMENDMENT),slot_wall_limit_seconds=None,
        latency_is_PASS_criterion=False,r039_resource_owner=read(op.OWNER) if op.OWNER.exists() else None,
        r039_dispatch=read(op.OPS/'R039_HANDOVER_HEARTBEAT.json'))
    atomic(op.CAMPAIGN/'V44_30MIN_WATCHDOG_RECEIPT.json',value);return value

def audit():
    op.authority();value=inherited.audit();extra=[]
    for worker in op.base.workers():
        cmd=worker['cmdline']
        if op.ENTRY not in cmd:continue
        path=cmd[cmd.index('--worker')+1];request=read(path)
        verify(request['R039_sources'])
        if request['R039_latency_authorization']!=record(op.AMENDMENT):raise PermissionError('R039_AUDIT_REQUEST_AUTHORITY_DRIFT')
        extra.append(dict(pid=worker['pid'],request=record(path),latency_overlay=True))
    value.update(authorization=record(op.AMENDMENT),r039_workers=extra,wall_latency_limit_removed=True)
    atomic(op.OPS/'R039_ACTIVE_SOURCE_AUDIT.json',value);return value
