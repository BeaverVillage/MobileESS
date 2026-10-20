"""Pause the unchanged case chain immediately before its Actual call."""
from pathlib import Path
import inspect,textwrap,linecache,traceback
from types import FunctionType
from v44.common import read,record,verify,atomic,digest,now

def prepare_actual(request,folder,mess):
    from v44.checkpoints import checked
    from v44.campaign import stage_file
    from v44.daily import load_aidc
    from v44.execution import assert_current
    context=assert_current();case=context['request'];root=Path(case['case_root'])
    if case.get('r038_phase')!='PREPARE_SERIAL':raise PermissionError('R038_PREPARE_PHASE_REQUIRED')
    if any(request[k]!=case[k] for k in ('day','arm','case_root','source_sha')):raise PermissionError('R038_PREPARE_CASE_DRIFT')
    if (root/'ACTUAL').exists():raise PermissionError('R038_PREPARE_MUST_NOT_RUN_ACTUAL')
    load_aidc(folder,case['day'])
    stages=('A1',) if case['arm']=='B1' else ('M1','A2','M2')
    refs=[record(Path(folder)/'AIDC_REFERENCE.json')]
    for stage in stages:
        result_path=stage_file(case,stage);stage_root=result_path.parent
        checkpoint=stage_root/'COMPLETED_STAGE_CHECKPOINT.json'
        checked(checkpoint,read(stage_root/'request.json'),'COMPLETED')
        refs.extend([record(result_path),record(checkpoint)])
        reconciliation=stage_root/'RECONCILIATION.json'
        if reconciliation.exists():
            value=read(reconciliation)
            if value.get('inflight') is not None:raise PermissionError('R038_PREPARATION_NATIVE_INFLIGHT')
            refs.append(record(reconciliation))
    if request.get('MESS_result'):
        result=read(request['MESS_result'])
        if result['MESS_plan']!=mess:raise PermissionError('R038_FROZEN_MESS_PLAN_DRIFT')
        refs.append(record(request['MESS_result']))
    value=dict(schema='V44_R038_PRE_ACTUAL_HANDOFF_V1',UTC=now(),ready=True,
        day=case['day'],arm=case['arm'],case_root=str(root),source_sha=case['source_sha'],
        sources=case['sources'],evidence=refs,aidc_folder=str(folder),MESS_plan=mess,
        MESS_result=request.get('MESS_result'),actual_started=False,Native_clocks_reset=False)
    value['handoff_sha']=digest(value)
    target=root/'PRE_ACTUAL_READY.json';atomic(target,value)
    return dict(PASS=False,preparation_PASS=True,Actual_Fresh_not_run=True,pre_actual_handoff=record(target))

def compiled_prepare_case():
    from v44 import campaign
    source=textwrap.dedent(inspect.getsource(campaign.run_case))
    old="result.update(stage_result(request,'ACTUAL',lambda r:worker.actual(dict(r,MESS_result=a['MESS_result']),folder,mess)))"
    new="result.update(_r038_prepare_actual(dict(a,MESS_result=a['MESS_result']),folder,mess))"
    if source.count(old)!=1:raise ValueError('R038_ACTUAL_CALL_BOUNDARY_DRIFT')
    source=source.replace(old,new)
    old="result['status']='COMPLETE' if result.get('PASS') else 'FAILED'"
    if source.count(old)!=1:raise ValueError('R038_PREPARE_RESULT_BOUNDARY_DRIFT')
    source=source.replace(old,"result['status']='PRE_ACTUAL_READY'")
    filename=__file__+'.prepare.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(campaign.run_case.__globals__,_r038_prepare_actual=prepare_actual)
    exec(compile(source,filename,'exec'),namespace)
    function=namespace['run_case']
    # Inherited Q/thread/stage adapters resolve globals at call time. Preserve
    # that live module dictionary instead of freezing pre-install bindings.
    return FunctionType(function.__code__,campaign.run_case.__globals__,function.__name__,function.__defaults__,function.__closure__)

def load_handoff(request):
    from v44.daily import load_aidc
    from v44.locks import alive
    ref=request['R038_pre_actual_handoff'];verify([ref]);value=read(ref['path'])
    if value.get('schema')!='V44_R038_PRE_ACTUAL_HANDOFF_V1' or value.get('ready') is not True:
        raise PermissionError('R038_VERIFIED_PRE_ACTUAL_HANDOFF_REQUIRED')
    if value['handoff_sha']!=digest({k:v for k,v in value.items() if k!='handoff_sha'}):raise PermissionError('R038_HANDOFF_SHA_DRIFT')
    if any(value[k]!=request[k] for k in ('day','arm','case_root','source_sha')) or value['sources']!=request['sources']:
        raise PermissionError('R038_SAME_CASE_SOURCE_REQUIRED')
    root=Path(request['case_root'])
    if alive(read(root/'START.json')):raise PermissionError('R038_PREPARATION_WORKER_STILL_ALIVE')
    verify(value['sources']+value['evidence']);load_aidc(value['aidc_folder'],request['day'])
    if value['MESS_result'] and read(value['MESS_result'])['MESS_plan']!=value['MESS_plan']:
        raise PermissionError('R038_MESS_PLAN_CHANGED_AFTER_PREPARATION')
    return value

def actual_case(request):
    from . import operations as op
    from .cpu import actual_slot
    from v44 import worker,campaign
    from v44.execution import case_scope
    from v44.locks import process_identity
    root=Path(request['case_root']);who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1,
        parallel_actual_slot=request['parallel_actual_slot'])
    if (root/'RESULT.json').exists() and read(root/'RESULT.json').get('PASS') is True:
        raise PermissionError('R038_COMPLETED_PASS_MUST_NOT_BE_OVERWRITTEN')
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with actual_slot(request,op.OPS,op.authority()['cpu_placement']) as cpu,case_scope(request,request['lease'],who):
        try:
            value=load_handoff(request)
            if (root/'ACTUAL').exists():raise PermissionError('R038_ACTUAL_CONTEXT_CANNOT_BE_RESTARTED_OR_OVERWRITTEN')
            atomic(root/'ACTUAL_START.json',dict(who,UTC=now(),source_sha=request['source_sha'],sources=request['sources'],
                cpu=cpu,pre_actual_handoff=request['R038_pre_actual_handoff']))
            atomic(root/'progress.json',dict(UTC=now(),stage='ACTUAL_FRESH',status='RUNNING',pid=who['pid'],
                parallel_actual_slot=request['parallel_actual_slot']))
            stage=campaign.stage_request(request,'ACTUAL');stage['MESS_result']=value['MESS_result']
            result.update(worker.actual(stage,Path(value['aidc_folder']),value['MESS_plan']))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',
                R038_pre_actual_handoff=request['R038_pre_actual_handoff'],new_Planning_or_M_Native_calls_in_actual_worker=0)
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:
            result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
