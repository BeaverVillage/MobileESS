"""Seal the legacy-handoff sequence labels at adoption; preserve its source SHA."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import inspect,textwrap,linecache
import v44_recovery_r045
from v44_recovery_r045 import operations as core
from v44.common import read,record,verify

ENTRY='v44_week2_restart_r045a'
AUTH=core.OPS/'R045A_PREPARED_HANDOFF_ADOPTION_AUTHORIZATION.json'
_authority=core.authority


def authority():
    v=read(AUTH);verify([v['source'],v['previous_authorization'],v['validation']])
    if v['source']!=record(__file__) or v['previous_authorization']!=record(core.PERMIT) or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R045A_SEALED_ADOPTION_REPAIR_REQUIRED')
    return _authority()


def restored():
    body=textwrap.dedent(inspect.getsource(core.restore_state))
    old="r.update(lease=lease,R045_authorization=record(PERMIT),R038_pre_actual_handoff=job['handoff'])"
    new="r.update(lease=lease,R045_authorization=record(PERMIT),R038_pre_actual_handoff=job['handoff'],sequence_mode='MAIN',sequence_authorization=record(seq.AUTH),r038_phase='PREPARE_SERIAL')"
    if body.count(old)!=1:raise ValueError('R045A_EXACT_ADOPTION_LABEL_BOUNDARY_DRIFT')
    body=body.replace(old,new);filename=__file__+'.restore.generated'
    linecache.cache[filename]=(len(body),None,body.splitlines(True),filename)
    ns=dict(core.restore_state.__globals__);exec(compile(body,filename,'exec'),ns)
    return ns['restore_state']


@contextmanager
def install(validate=True):
    if validate:authority()
    fn=restored()
    with patch.object(core,'ENTRY',ENTRY),patch.object(core,'authority',authority if validate else _authority),patch.object(core,'restore_state',fn):yield


def main():
    with core.week.bindings(),install():core.main()

if __name__=='__main__':main()
