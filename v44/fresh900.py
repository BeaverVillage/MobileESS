"""User-authorized new Joint trial: K48 only, 900s measured from zero."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
from types import FunctionType,SimpleNamespace
from unittest.mock import patch
import argparse
import subprocess
from . import cap300
from .common import read,record,verify,atomic,digest,now,RUNTIME

POLICY='V44_JOINT_CALL300_FRESH900_FROM_COMPLETED_K48_V1'
PERMIT=RUNTIME/'v43_planning_svr12_actual_v1/FRESH900_EXECUTION_PERMIT.json'

def overlay():
    return dict(policy=POLICY,source=record(__file__),Joint_call_cap=300.,Joint_new_total=900.,
        Joint_prior_Runtime_imported=False,K48_recalculation=False,
        restart_days=['2025-05-01','2025-05-02'],new_attempt='attempt003',old_ledgers_modified=False)

def validate(path=PERMIT):
    value=cap300.validate(path)
    if value.get('fresh_joint_overlay')!=overlay() or value.get('fresh_policy_sha')!=digest(overlay()):
        raise PermissionError('EXACT_USER_AUTHORIZED_FRESH900_POLICY_REQUIRED')
    return value

def make_permit():
    value=cap300.validate();value=dict(value,UTC=now(),fresh_joint_overlay=overlay(),fresh_policy_sha=digest(overlay()),
        fresh_joint_direct_instruction='900초 예산 처음부터 0초부터 줘야지.. 반영해.',
        Joint_existing_measured_Runtime_deducted=False,prior_joint_trials_preserved_separately=True)
    if PERMIT.exists():raise FileExistsError('FRESH900_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value);validate();return value

def fresh_budget(original,path,*,case,kind,destination,progress=None):
    if kind!='PLANNING_NATIVE' or not getattr(case,'fresh900_authorized',False):
        return original(path,case=case,kind=kind,destination=destination,progress=progress)
    from .budget import StageBudget
    from .checkpoints import ledger_state
    old=ledger_state(path,ceiling=900.)
    if Path(destination).exists():raise FileExistsError('FRESH900_NEW_LEDGER_REQUIRED')
    budget=StageBudget(destination,case=case,kind=kind,progress=progress)
    budget.authorization.update(new_authorized_Joint_trial=True,new_Joint_clock_started_at_zero=True,
        old_ledger_reset_or_modified=False,prior_trial_ledger=old['ledger'],
        prior_trial_Native_seconds=old['measured'],prior_calls_imported=False,
        fresh_policy=POLICY,fresh_policy_sha=case.fresh900_policy_sha)
    budget.persist();return budget

@contextmanager
def install(path=PERMIT):
    permit=validate(path)
    from . import campaign,budget,m_restore,execution,checkpoints
    with cap300.install(path):
        old_stage=campaign.stage_result;old_resume=budget.resume;old_restore=m_restore.restore
        old_guard=execution.assert_current;old_envelope=checkpoints.envelope
        def guard():
            value=old_guard();validate(path)
            if value['request'].get('fresh_policy_sha')!=permit['fresh_policy_sha']:
                raise PermissionError('FRESH900_WORKER_POLICY_REQUIRED')
            return value
        def restore(*args,**kwargs):
            case=old_restore(*args,**kwargs)
            request=args[2] if len(args)>2 else kwargs['request']
            case.fresh900_authorized=bool(request.get('new_Joint_trial_from_zero'))
            case.fresh900_policy_sha=permit['fresh_policy_sha'];return case
        def stage(case,name,function):
            if (case.get('resume_of') and name=='M1' and case['arm']=='B2'
                    and case['day'] in overlay()['restart_days'] and Path(case['case_root']).name=='attempt003'):
                from .checkpoints import crash_admission
                parent=Path(case['scientific_case_root'])/'M1';request=campaign.stage_request(case,name)
                crash_admission(parent,request)
                if not (parent/'LOWER_STAGE_RESULT.json').exists():raise PermissionError('COMPLETED_K48_REQUIRED')
                request.update(resume_parent=str(parent),new_Joint_trial_from_zero=True,
                    fresh_policy_sha=permit['fresh_policy_sha'],Joint_call_cap_seconds=300.)
                return function(request)
            return old_stage(case,name,function)
        def envelope(*args,**kwargs):
            value=old_envelope(*args,**kwargs)
            value.update(fresh_joint_overlay=permit['fresh_joint_overlay'],fresh_policy_sha=permit['fresh_policy_sha'])
            value['checkpoint_sha']=digest({k:v for k,v in value.items() if k!='checkpoint_sha'});return value
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',guard))
            stack.enter_context(patch.object(m_restore,'restore',restore))
            stack.enter_context(patch.object(budget,'resume',lambda *a,**kw:fresh_budget(old_resume,*a,**kw)))
            stack.enter_context(patch.object(campaign,'stage_result',stage))
            stack.enter_context(patch.object(checkpoints,'envelope',envelope))
            yield permit

def coordinator_run(root,path=PERMIT):
    from . import campaign
    permit=validate(path);original_atomic=campaign.atomic
    def write(path,value):
        if Path(path).parent.name=='requests' and isinstance(value,dict) and 'case_root' in value:
            value=dict(value,fresh_joint_overlay=permit['fresh_joint_overlay'],fresh_policy_sha=permit['fresh_policy_sha'])
        original_atomic(path,value)
    def launch(command,**kwargs):
        command=list(command);index=command.index('-m')+1
        if command[index]!='v44.cap300':raise PermissionError('FRESH900_ONLY_CAP300_WORKER')
        command[index]='v44.fresh900';return subprocess.Popen(command,**kwargs)
    fn=cap300.coordinator_run
    ns=dict(fn.__globals__,validate=validate,install=install,
        subprocess=SimpleNamespace(Popen=launch,CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    run=FunctionType(fn.__code__,ns,fn.__name__,fn.__defaults__,fn.__closure__)
    with patch.object(campaign,'atomic',write):return run(root,path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--permit',type=Path,default=PERMIT)
    p.add_argument('--worker',type=Path);p.add_argument('--resume',action='store_true')
    p.add_argument('--root',type=Path,default=RUNTIME/'v43_planning_svr12_actual_v1/campaign001');a=p.parse_args()
    if a.worker:
        with install(a.permit):
            request=read(a.worker)
            from .campaign import run_case
            run_case(request)
        return
    if not a.resume:raise PermissionError('EXPLICIT_FRESH900_RESUME_REQUIRED')
    coordinator_run(a.root,a.permit)

if __name__=='__main__':main()
