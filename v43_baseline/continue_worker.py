"""User-authorized B2 continuation of a healthy, FULL-validated timed-out M1.

There is no gap gate or optimization here. The original FCFS/Fresh worker
consumes the exact final same-case MESS plan, preserving every M-stage raw file.
"""
from pathlib import Path
import argparse

from v43.common import read,record,verify_records,atomic,now
from v42_native.contracts import digest


def handoff(parent):
    parent=Path(parent);result=read(parent/'RESULT.json');request=read(parent/'request.json')
    start=read(parent/'START.json');reconciliation=read(parent/'RECONCILIATION.json')
    import psutil
    try:
        process=psutil.Process(start['pid'])
        if process.create_time()==start['process_created'] and process.is_running():
            raise ValueError('M_STAGE_PARENT_STILL_LIVE')
    except psutil.NoSuchProcess:pass
    if (result.get('arm'),result.get('stage'),result.get('day'))!=('B2','M1','2025-05-01'):
        raise ValueError('EXACT_MAY01_B2_M1_REQUIRED')
    if (result.get('FULL_feasible') is not True or result.get('upper',{}).get('FULL_validated') is not True
            or result.get('M_stage_execution_PASS') is not True or result.get('error')
            or result.get('implementation_errors') or not result.get('finished_UTC')
            or result.get('inflight') is not None or reconciliation.get('inflight') is not None):
        raise ValueError('HEALTHY_RECONCILED_ORIGINAL_FULL_M_INCUMBENT_REQUIRED')
    plan=result['MESS_plan']
    if (digest({k:v for k,v in plan.items() if k!='plan_sha'})!=plan['plan_sha']
            or plan.get('case_sha')!=result['case_sha'] or plan!=result['upper']['mess']):
        raise ValueError('EXACT_FINAL_VALIDATED_PLAN_REQUIRED')
    binding=plan['case_binding']
    if any(binding.get(k)!=v for k,v in dict(arm='B2',stage='M1',day='2025-05-01',
            case_sha=result['case_sha'],source_sha=request['source_sha']).items()):
        raise ValueError('PLAN_PARENT_SOURCE_CASE_BINDING')
    reference=Path(request['fixed_AIDC_reference']);fixed=read(reference/'AIDC_REFERENCE.json')['identity']
    if (fixed.get('arm'),fixed.get('day'),fixed.get('stage'))!=('B0','2025-05-01','REFERENCE'):
        raise ValueError('SAME_DAY_B0_R0_REFERENCE_REQUIRED')
    if fixed['aidc_anchor']!=binding['aidc_anchor'] or fixed!=result['fixed_AIDC']:
        raise ValueError('FIXED_AIDC_ANCHOR_DRIFT')
    verify_records(start['sources'])
    verify_records(fixed['source']+[fixed[k] for k in ('input','windows','reference','physical')])
    return result,reference


def run(parent,output):
    parent=Path(parent);output=Path(output)
    if output.exists():raise ValueError('NEW_ACTUAL_ATTEMPT_ONLY')
    result,reference=handoff(parent)
    receipt=output.with_name(output.name+'.M_HANDOFF.json')
    if receipt.exists():raise ValueError('IMMUTABLE_NEW_HANDOFF_RECEIPT_REQUIRED')
    atomic(receipt,dict(UTC=now(),authority='USER_EXPLICIT_CONTINUE_B2_WITH_CURRENT_FULL_INCUMBENT',
        status='TIME_LIMIT_FULL_FEASIBLE_GAP_NOT_CERTIFIED',parent_result=record(parent/'RESULT.json'),
        parent_reconciliation=record(parent/'RECONCILIATION.json'),MESS_plan_sha=result['MESS_plan']['plan_sha'],
        Global_UB=result['Global_UB'],Global_LB=result['Global_LB'],Global_Gap=result['Global_Gap'],
        global_gap_certified=result['global_gap_certified'],optimization_restarted=False,
        new_optimization_calls=0,reference=str(reference),Source_authority_promoted=False,
        algorithm='UNCHANGED_ORIGINAL_B2_FCFS_AND_FROZEN_MESS_THEN_INDEPENDENT_FRESH'))
    from .worker import run as original
    actual=original('B2',output,reference_folder=reference,mess_result=parent/'RESULT.json')
    atomic(output/'B2_CONTINUATION_RECEIPT.json',dict(UTC=now(),M_handoff=record(receipt),
        Actual_result=record(output/'RESULT.json'),M_global_gap_certified=result['global_gap_certified'],
        M_global_gap=result['Global_Gap'],M_original_FULL_feasible=True,
        Actual_execution_PASS=actual['Actual96_execution_PASS'],Fresh_physical_PASS=actual['Fresh96_physical_PASS'],
        optimization_restarted=False,new_optimization_calls=0))
    print({k:actual.get(k) for k in ('PASS','Actual96_execution_PASS','Fresh96_physical_PASS','error','wall_seconds')},flush=True)
    return actual


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('parent');p.add_argument('output');a=p.parse_args();run(a.parent,a.output)
