"""Prepared row-shared audit layout; user storage-review hold always wins."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import argparse
from v44_recovery_r036 import operations as previous
from v44.common import read,record,verify,atomic,digest,now
from v44_audit_chunk_store import install as chunks

base=previous.base
CAMPAIGN,OPS,PERMIT=base.CAMPAIGN,base.OPS,base.PERMIT
RAW_ROOT=previous.RAW_ROOT
ENTRY='v44_recovery_r037.operations'
ALGORITHM=previous.ALGORITHM
POLICY='R037_SHARED_HISTORICAL_RAW_ROWS_BYTE_EXACT_RECONSTRUCTION'
AMENDMENT=OPS/'R037_ROW_SHARED_STORAGE_AUTHORIZATION.json'
latest=base.latest

def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]+[
        record(Path(__file__).resolve().parents[1]/'v44_audit_chunk_store.py')]

def authority():
    value=read(AMENDMENT)
    verify(value['sources']+[value['previous_authorization'],value['validation']]+value['monitoring_sources'])
    if (value['sources']!=sources() or value['policy']!=POLICY or
            value['previous_authorization']!=record(previous.AMENDMENT) or not read(value['validation']['path'])['PASS']):
        raise PermissionError('R037_EXACT_STORAGE_AUTHORITY_DRIFT')
    previous.authority();return value

def validate():
    result=previous.validate();authority()
    return dict(result,row_shared_raw_storage=record(AMENDMENT))

def command(args):
    if not isinstance(args,(list,tuple)):return args
    result=list(args)
    if (len(result)>=5 and result[1:3]==['-u','-m'] and
            result[3] in tuple(f'v44_recovery_r{n:03d}.operations' for n in range(29,37)) and
            result[4] in ('--worker','--coordinator')):
        result[3]=ENTRY
        if '--algorithm' not in result:result+=['--algorithm',ALGORITHM]
    return result

def require_user_resume():
    stop=OPS/'STOP_AUTONOMY.json'
    if stop.exists() and read(stop).get('user_dispatch_pause'):
        raise PermissionError('R037_USER_STORAGE_REVIEW_HOLD_NO_DISPATCH')
    if (OPS/'USER_STORAGE_REVIEW_AUTHORIZATION.json').exists():
        release=OPS/'USER_STORAGE_REVIEW_RELEASE.json'
        if (not release.exists() or read(release).get('user_authorized') is not True or
                read(release).get('action')!='RESUME_CAMPAIGN_AFTER_STORAGE_REVIEW'):
            raise PermissionError('R037_EXPLICIT_USER_RESUME_REQUIRED')

@contextmanager
def install():
    from v44_recovery_r029 import handover
    with previous.install(),chunks(RAW_ROOT):
        decorate,popen,activate=base.decorate,base.subprocess.Popen,handover.activate
        def decorated(case,permit):
            authority();case=decorate(case,permit);case['R037_row_shared_storage']=record(AMENDMENT)
            case['sources']=list({r['path']:r for r in case['sources']+sources()+[record(AMENDMENT)]}.values())
            case['source_sha']=digest(case['sources']);return case
        def launch(args,*a,**kw):return popen(command(args),*a,**kw)
        def activated(lease):
            activate(lease);path=OPS/'CURRENT_HANDOFF.json';value=read(path)
            value.update(UTC=now(),active_revision='v44_recovery_r037',active_operational_entry=ENTRY,
                active_operational_permit=record(AMENDMENT),pending_revision=None,pending_permit=None,
                collector=str(OPS/'collect_watchdog_r037.py'),active_source_auditor=str(OPS/'audit_active_revision_r037.py'),
                next='Shared lossless historical raw rows; manifests restore original JSON bytes. Fresh still writes independent complete raw.')
            atomic(path,value)
        with patch.object(base,'decorate',decorated),patch.object(base.subprocess,'Popen',launch),patch.object(handover,'activate',activated):yield

def states(root):
    with install():return base.states(root)

def authorize(request):
    previous.authorize(request)
    if request.get('R037_row_shared_storage')!=record(AMENDMENT):raise PermissionError('R037_EXPLICIT_STORAGE_AUTHORIZATION_REQUIRED')

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true');p.add_argument('--watchdog',action='store_true')
    p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);a=p.parse_args()
    if sum((bool(a.worker),a.coordinator,a.watchdog))!=1:raise PermissionError('R037_ONE_OPERATION_REQUIRED')
    require_user_resume();validate()
    with install():
        if a.worker:
            request=read(a.worker);authorize(request);base.worker(request)
        elif a.coordinator:base.run()
        else:base.watchdog()

if __name__=='__main__':main()
