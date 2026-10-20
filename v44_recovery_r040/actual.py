"""Original Actual/Fresh call from a verified, independently admitted handoff."""
from pathlib import Path
import traceback
from v44.common import read,record,verify,atomic,now
from v44.locks import process_identity
from v44_recovery_r038.phases import load_handoff
from v44_recovery_r038.cpu import actual_slot
from . import operations as op

def actual_case(request):
    from v44 import worker,campaign
    from v44.execution import case_scope
    root=Path(request['case_root']);plan=op.subset(request)['cpu_placement']
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1,parallel_actual_slot=request['parallel_actual_slot'])
    if (root/'RESULT.json').exists() and read(root/'RESULT.json').get('PASS') is True:raise PermissionError('R040_COMPLETED_PASS_PROTECTED')
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with actual_slot(request,op.OPS,plan) as selected,case_scope(request,request['lease'],who):
        try:
            handoff=load_handoff(request)
            if (root/'ACTUAL').exists():raise PermissionError('R040_EXISTING_ACTUAL_CONTEXT_PROTECTED')
            atomic(root/'ACTUAL_START.json',dict(who,UTC=now(),source_sha=request['source_sha'],sources=request['sources'],
                R039_sources=request['R039_sources'],R040_sources=request['R040_sources'],cpu=selected,
                pre_actual_handoff=request['R038_pre_actual_handoff'],resolved_manifest=request['R040_resolved_manifest']))
            atomic(root/'progress.json',dict(UTC=now(),stage='ACTUAL_FRESH',status='RUNNING',pid=who['pid'],parallel_actual_slot=request['parallel_actual_slot']))
            stage=campaign.stage_request(request,'ACTUAL');stage['MESS_result']=handoff['MESS_result']
            result.update(worker.actual(stage,Path(handoff['aidc_folder']),handoff['MESS_plan']))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',new_Planning_or_M_Native_calls_in_actual_worker=0,
                R040_authorization=record(op.AMENDMENT),R040_resolved_manifest=request['R040_resolved_manifest'])
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
