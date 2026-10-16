"""Explicit operational overlay: 300s Joint calls, unchanged frozen science.

The base 140s source/case receipts stay immutable and verifiable. This module
has its own source SHA and permit, recorded separately in every new attempt.
It changes no matrix, candidate generator, physical source or total budget.
"""
from contextlib import contextmanager,ExitStack
from pathlib import Path
from types import FunctionType,SimpleNamespace
from unittest.mock import patch
import argparse
import inspect
import os
import subprocess
import textwrap

from .common import DOC,ROOT,RUNTIME,read,record,verify,atomic,digest,now

POLICY='V44_JOINT_CALL300_COMPLETED_K48_RESUME_V1'
PERMIT=RUNTIME/'v43_planning_svr12_actual_v1/CAP300_EXECUTION_PERMIT.json'
CALL_CAP=300.

def validate(path=PERMIT):
    from .prepare import require_execution_permit
    permit=require_execution_permit(path,read(DOC/'PREEXECUTION_CERTIFICATION.json'))
    overlay=permit.get('operational_overlay',{})
    expected=dict(policy=POLICY,Joint_call_cap=300.,K48_total=300.,Joint_total=900.,Threads=1,
        Native_clock_reset=False,source=record(__file__))
    if overlay!=expected:raise PermissionError('EXACT_CAP300_OPERATIONAL_OVERLAY_REQUIRED')
    verify([overlay['source'],permit['base_source_freeze']])
    if permit.get('execution_policy_sha')!=digest(overlay):raise PermissionError('CAP300_POLICY_SHA_DRIFT')
    return permit

def make_permit():
    old=read(RUNTIME/'v43_planning_svr12_actual_v1/APPROVED_EXECUTION_PERMIT.json')
    overlay=dict(policy=POLICY,Joint_call_cap=300.,K48_total=300.,Joint_total=900.,Threads=1,
        Native_clock_reset=False,source=record(__file__))
    value=dict(old,UTC=now(),operational_overlay=overlay,execution_policy_sha=digest(overlay),
        base_source_freeze=record(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json'),
        direct_user_instruction='140초 호출 제한 필요해? 300초 호출 제한으로 바꾸고 K48 끝나는 시점부터 재개해.',
        Joint_existing_measured_Runtime_deducted=True,K48_recalculation=False)
    if PERMIT.exists():raise FileExistsError('CAP300_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value);validate();return value

def coefficient_loader(certificate,day):
    """Same original 7-Reg coefficient constructor used by build_case."""
    from .planning import check_native
    from v42_pr134_b1.native import original_coefficients_for_day
    import v42_may01.prepare as original
    if certificate.get('model_regenerated') or 'SVR' in certificate.get('model_version',''):
        raise PermissionError('CAP300_RESTORE_REQUIRES_ORIGINAL_V43_GRID')
    return original_coefficients_for_day(original,certificate,day)

def restore_adapter(original):
    # Repair only the stale SVR11 loader/metadata binding in the resume adapter.
    # Matrix bytes, inverse, graph and all original FULL checks stay unchanged.
    source=textwrap.dedent(inspect.getsource(original))
    replacements={
        'from v42_svr11.model import load_coefficients':'load_coefficients=_cap300_coefficients',
        "['output']['path']":"['outputs']['planning_coefficients']['path']",
        "case._v43_coefficient_metadata={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}":
            "case._v43_coefficient_metadata={k:z[k].copy() for k in ('node_names','branch_names')}\n"
            "        case._v43_coefficient_metadata['transformer_ratings']=np.asarray(coefficients[0].transformer_ratings)",
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('CAP300_ORIGINAL_GRID_RESTORE_BOUNDARY_DRIFT:'+old)
        source=source.replace(old,new)
    ns=dict(original.__globals__,_cap300_coefficients=coefficient_loader)
    exec(compile(source,original.__code__.co_filename,'exec'),ns)
    return ns[original.__name__]

def resumed_stage(original,case,stage,function):
    if case.get('resume_of') and stage=='M1' and case['arm']=='B2' and case['day'] in ('2025-05-01','2025-05-02'):
        from .campaign import stage_request
        from .checkpoints import crash_admission,assert_dead
        parent=Path(case['resume_of'])/stage
        request=stage_request(case,stage);assert_dead(parent)
        admission=crash_admission(parent,request)
        if admission['status']!='RESTORABLE_M_BINARY' or not (parent/'LOWER_STAGE_RESULT.json').exists():
            raise PermissionError('COMPLETED_K48_BINARY_AND_RECONCILED_NATIVE_LEDGERS_REQUIRED')
        # An intentional stop was sealed as a failed completed M stage. Reopen
        # its binary case, rather than treating that stopped result as final.
        request.update(resume_parent=str(parent),operational_policy=POLICY,
            Joint_call_cap_seconds=300.,K48_completed_reused=True)
        return function(request)
    return original(case,stage,function)

@contextmanager
def install(path=PERMIT):
    permit=validate(path);overlay=permit['operational_overlay']
    from . import config,budget,execution,checkpoints,m_restore,campaign
    from .frozen.v43_mess.library import load
    modules=load();adaptive=modules['m_adaptive']
    original_guard=execution.assert_current;old_stage=campaign.stage_result;old_envelope=checkpoints.envelope
    def guard():
        result=original_guard();validate(path)
        declared=result['request'].get('execution_policy_sha')
        if declared!=permit['execution_policy_sha']:raise PermissionError('CAP300_WORKER_POLICY_IDENTITY_REQUIRED')
        return result
    def envelope(*args,**kwargs):
        value=old_envelope(*args,**kwargs)
        value.update(operational_overlay=overlay,execution_policy_sha=permit['execution_policy_sha'])
        value['checkpoint_sha']=digest({k:v for k,v in value.items() if k!='checkpoint_sha'})
        return value
    with ExitStack() as stack:
        stack.enter_context(patch.object(config,'JOINT_CALL_CAP',CALL_CAP))
        stack.enter_context(patch.object(budget,'JOINT_CALL_CAP',CALL_CAP))
        stack.enter_context(patch.object(adaptive,'JOINT_CAP_SECONDS',CALL_CAP))
        stack.enter_context(patch.object(execution,'assert_current',guard))
        stack.enter_context(patch.object(m_restore,'restore',restore_adapter(m_restore.restore)))
        stack.enter_context(patch.object(campaign,'stage_result',lambda c,s,f:resumed_stage(old_stage,c,s,f)))
        stack.enter_context(patch.object(checkpoints,'envelope',envelope))
        yield permit

def coordinator_run(root,permit_path=PERMIT):
    from . import campaign
    permit=validate(permit_path);original_atomic=campaign.atomic
    def write(path,value):
        p=Path(path)
        if p.parent.name=='requests' and isinstance(value,dict) and 'case_root' in value:
            value=dict(value,execution_policy_sha=permit['execution_policy_sha'],
                operational_overlay=permit['operational_overlay'],Joint_call_cap_seconds=CALL_CAP)
        original_atomic(path,value)
    def launch(command,**kwargs):
        command=list(command)
        if '-m' not in command or command[command.index('-m')+1]!='v44.campaign':
            raise PermissionError('CAP300_ONLY_ORIGINAL_CAMPAIGN_WORKER_LAUNCH')
        command[command.index('-m')+1]='v44.cap300'
        command+=['--permit',str(permit_path)]
        return subprocess.Popen(command,**kwargs)
    fn=campaign.run
    ns=dict(fn.__globals__,atomic=write,subprocess=SimpleNamespace(Popen=launch,
        CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    run=FunctionType(fn.__code__,ns,fn.__name__,fn.__defaults__,fn.__closure__)
    run.__kwdefaults__=fn.__kwdefaults__
    with install(permit_path):return run(root,permit_path,resume=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--permit',type=Path,default=PERMIT)
    p.add_argument('--worker',type=Path);p.add_argument('--resume',action='store_true')
    p.add_argument('--root',type=Path,default=RUNTIME/'v43_planning_svr12_actual_v1/campaign001')
    a=p.parse_args()
    if a.worker:
        with install(a.permit) as permit:
            request=read(a.worker)
            if request.get('execution_policy_sha')!=permit['execution_policy_sha']:
                raise PermissionError('CAP300_REQUEST_POLICY_DRIFT')
            atomic(Path(request['case_root']).with_suffix('.CAP300_POLICY.json'),dict(
                UTC=now(),policy=permit['operational_overlay'],execution_policy_sha=permit['execution_policy_sha']))
            from .campaign import run_case
            run_case(request)
        return
    if not a.resume:raise PermissionError('EXPLICIT_CAP300_RESUME_REQUIRED')
    coordinator_run(a.root,a.permit)

if __name__=='__main__':main()
