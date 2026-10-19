"""Fence every Actual entry and adapt the certified completed-A1 route."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import traceback
from v44.common import read,record,verify,atomic,now

def deny_actual(*args,**kwargs):raise PermissionError('R041_PREPARATION_WORKER_MUST_NEVER_EXECUTE_ACTUAL')

def dump_with_parent(function,case_root):
    root=Path(case_root).resolve()
    def dump(path,*args,**kwargs):
        path=Path(path).resolve()
        if not path.is_relative_to(root):raise PermissionError('R041_STATE_DUMP_OUTSIDE_OWN_CASE')
        path.parent.mkdir(parents=True,exist_ok=True)
        return function(path,*args,**kwargs)
    return dump

@contextmanager
def install(request):
    from v44 import worker
    from v44_recovery_r029 import wall_resume
    from v42_may_campaign_native90 import a_stage
    with patch.object(worker,'actual',deny_actual),patch.object(wall_resume,'run',reuse_a1_case),patch.object(a_stage,'_dump_state',dump_with_parent(a_stage._dump_state,request['case_root'])):
        yield

def publish_a1(request,parent,result):
    """Same accepted-cache proof fields as the ordinary B1 preparation path."""
    from v44.campaign import stage_request
    root=Path(request['case_root']);parent=Path(parent);campaign=Path(request['campaign_root']);day=request['day']
    a1=stage_request(request,'A1');output=Path(result.get('accepted_cache_output',str(parent/'A1/OUTPUT')))
    cache=output/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
    domain=read(cache);prepared=read(output/'A_PREPARE_RECEIPT.json')
    proof=Path(a1['root'])/'ACCEPTED_A1_CACHE_PROOF.json'
    atomic(proof,dict(schema='V44_ACCEPTED_A1_PHYSICAL_CACHE',day=day,result=record(parent/'A1/RESULT.json'),
        cache=record(cache),sources=request['sources'],inputs={n:record(Path(a1['input_folder'])/n) for n in ('NATIVE_INPUT.json','WINDOWS.json')}))
    a1.update(_current_date_physical_cache=str(output),_physical_cache_identity=record(cache),physical_cache_case_proof=record(proof),
        _expected_model_verification=prepared['verification'],_expected_complete_domain_hashes=domain['complete_domain_hashes'])
    atomic(campaign/'B1_A1'/f'{day}.json',result);atomic(campaign/'B1_A1'/f'{day}.request.json',a1)
    atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(A1=dict(root=str(parent/'A1'))))

def reuse_a1_case(request):
    from v44.locks import worker_slot,process_identity
    from v44.execution import case_scope
    from v44.campaign import stage_request
    from v44_recovery_r029 import wall_resume
    from v44_recovery_r038.phases import prepare_actual
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),source_sha=request['source_sha'],sources=request['sources']))
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with worker_slot(request['day'],request['arm'],1,root=request['campaign_root'],lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            if request['arm']!='B1' or request['day']!='2025-05-07':raise PermissionError('R041_EXPLICIT_CERTIFIED_MAY07_A1_ROUTE_ONLY')
            parent=Path(request['wall_resume_parent']);folder,mess,mess_result=wall_resume.validate_parent(parent,root/'PARENT_AUDIT')
            if mess is not None or mess_result is not None:raise PermissionError('R041_B1_MESS_MUST_BE_ABSENT')
            original=read(parent/'A1/RESULT.json');publish_a1(request,parent,original)
            stage=stage_request(request,'ACTUAL');stage['MESS_result']=None
            result.update(prepare_actual(stage,folder,None),status='PRE_ACTUAL_READY',reused_A1=record(parent/'A1/RESULT.json'),new_optimization_calls=0)
            atomic(root/'progress.json',dict(UTC=now(),stage='PRE_ACTUAL_READY',status='WAITING',Actual_started=False))
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
