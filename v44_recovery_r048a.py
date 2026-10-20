"""Eagerly capture the original reference before installing its scoped adapter."""
import v44_recovery_r047
from v44_recovery_r045 import reference as reference_helper
from v44_recovery_r048 import operations as op
from pathlib import Path
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
import argparse,inspect,textwrap
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity,EXTERNAL_LOCKS

AUTH=op.HOME/'R048A_REFERENCE_FIX_AUTHORIZATION.json'
ENTRY='v44_recovery_r048a'
_authority=op.authority
_authorize=op.authorize_case
_new_request=op.new_request
_run=op.run


def authority():
    old=_authority();v=read(AUTH);verify([v['source'],v['previous_authorization'],v['validation']]+v['failed_results'])
    if v['source']!=record(__file__) or v['previous_authorization']!=record(op.AUTH) or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R048A_EXACT_TESTED_REFERENCE_FIX_REQUIRED')
    return dict(old,reference_fix=v)


def planned_root(day):
    repair=next((p for p in authority()['reference_fix']['repairs'] if p['day']==day),None)
    return repair['new_case_root'] if repair else str(op.campaign_for(day)/day/'B0/attempt001')


def authorize_case(r):
    v=authority()
    if r.get('R048a_authorization')!=record(AUTH):raise PermissionError('R048A_REQUEST_FIX_AUTHORITY_REQUIRED')
    if r['arm']=='B0':
        if Path(r['case_root'])!=Path(planned_root(r['day'])):raise PermissionError('R048A_EXACT_FRESH_ATTEMPT_REQUIRED')
        return _authorize(dict(r,case_root=str(op.campaign_for(r['day'])/r['day']/'B0/attempt001')))
    return _authorize(r)


def request_function():
    source=textwrap.dedent(inspect.getsource(_new_request))
    assert source.count("case_root=f['case_root']")==1
    source=source.replace("case_root=f['case_root']","case_root=_r048a_root(job['day'])")
    target='    authorize_case(r);path='
    assert source.count(target)==1
    source=source.replace(target,"    r['R048a_authorization']=record(_r048a_auth);r['sources']+=[record(_r048a_source),record(_r048a_auth)];r['source_sha']=digest(r['sources'])\n"+target)
    ns=dict(op.__dict__,_r048a_root=planned_root,_r048a_auth=AUTH,_r048a_source=__file__)
    exec(compile(source,__file__+'.requests.generated','exec'),ns);return ns['new_request']


def continuation():
    source=textwrap.dedent(inspect.getsource(_run));target='        running=[];main_lease=None'
    assert source.count(target)==1
    tail=textwrap.dedent(source[source.index(target):])
    body='def _r048a_continue(state,lease,locks):\n'+textwrap.indent(tail,'    ')
    exec(compile(body,__file__+'.run.generated','exec'),op.__dict__);return op._r048a_continue


def run():
    v=authority();state=read(op.STATE)
    if alive(state['lease']) or state.get('workers'):raise PermissionError('R048A_OLD_MONTH_OWNER_MUST_DRAIN')
    stop=read(op.core.seq.STOP)
    if stop.get('reason')!='R048_REFERENCE_RECURSION_FIX_DRAIN':raise PermissionError('R048A_FOREIGN_STOP_PRESERVED')
    with exclusive_lock(op.HOME/'CONTROLLER.lock'),ExitStack() as locks:
        atomic(op.HOME/'R048A_STATE_BEFORE_REPAIR.json',state)
        for day in v['reference_fix'].get('unstarted_admission_failures',[]):
            job=next(j for j in state['jobs'] if j['day']==day)
            if job['status']!='INFRASTRUCTURE_BLOCKED' or Path(job['case_root']).exists():raise PermissionError('R048A_ONLY_UNSTARTED_ADMISSION_FAILURE')
            for key in ('process_exit','prepare_request','exclusion_reason'):job.pop(key,None)
            job['status']='BASELINE_QUEUED'
        for repair in v['reference_fix']['repairs']:
            job=next(j for j in state['jobs'] if j['day']==repair['day'])
            if job['status']!='EXCLUDED' or Path(repair['new_case_root']).exists():raise PermissionError('R048A_ONLY_FAILED_FRESH_ATTEMPTS')
            for key in ('result','process_exit','prepare_request','exclusion_reason'):job.pop(key,None)
            job.update(status='BASELINE_QUEUED',case_root=repair['new_case_root'])
            ref=op.campaign_for(job['day'])/'references'/job['day']
            if ref.exists() and not (ref/'AIDC_REFERENCE.json').exists():
                assert ref.resolve().parent==(op.campaign_for(job['day'])/'references').resolve()
                ref.rename(op.HOME/('R048A_INCOMPLETE_REFERENCE_'+job['day']))
        lease=dict(**process_identity(),UTC=now(),root=str(op.HOME),external_locks=[str(p) for p in EXTERNAL_LOCKS],shared_parent=v['parent_lease'])
        atomic(op.LEASE,lease);atomic(op.OWNER,dict(mode='SHARED_PARENT',UTC=now(),lease=lease,parent=v['parent_lease']))
        atomic(op.core.seq.STOP,dict(UTC=now(),reason=op.REASON,authorization=record(op.AUTH),operational_transition=True,user_stop=False,current_workers_must_finish=True))
        state.update(phase='B0_MONTH_PARALLEL',lease=lease,R048a_authorization=record(AUTH));state.pop('error',None)
        return continuation()(state,lease,locks)


@contextmanager
def bindings():
    # This import precedes reference.project monkeypatching in every process.
    if reference_helper._original_project is op.project:raise PermissionError('R048A_ORIGINAL_REFERENCE_CAPTURE_REQUIRED')
    with patch.object(op,'ENTRY',ENTRY),patch.object(op,'authority',authority),patch.object(op,'authorize_case',authorize_case),patch.object(op,'new_request',request_function()):yield


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    with bindings():
        if a.worker:
            r=read(a.worker)
            with op.bindings(r):return op.worker(a.worker,a.entry_check)
        if a.run:
            with op.bindings():return run()
        p.error('Choose --run or --worker')

if __name__=='__main__':main()
