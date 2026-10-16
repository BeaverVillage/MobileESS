"""Owned stage receipts, completed-stage replay, and reconciled crash admission.

No Gurobi B&B tree or live Native clock is reconstructed. A restored M stage
replays its original FULL incumbent and retains each measured budget separately.
"""
from pathlib import Path
import math

from .common import read,record,verify,atomic,digest,now,NotReady
from .locks import alive
from .stages import case_key


def key(request):
    case_key(request['day'],request['arm'],request['stage'])
    return dict({k:request[k] for k in ('day','arm','stage','source_sha')},
        case_root=request.get('scientific_case_root',request['case_root']))


def receipts(value):
    if isinstance(value,dict):
        if all(k in value for k in ('path','sha256','bytes')):yield value
        else:
            for child in value.values():yield from receipts(child)
    elif isinstance(value,list):
        for child in value:yield from receipts(child)


def envelope(request,kind,files,**data):
    from .svr11_hardware import HARDWARE
    sources=request['sources'];verify(sources);verify(files)
    value=dict(schema='V44_RECONCILED_STAGE_CHECKPOINT_V1',kind=kind,UTC=now(),
        key=key(request),hardware=record(HARDWARE/'HARDWARE.json'),sources=sources,files=files,**data)
    value['checkpoint_sha']=digest(value);return value


def checked(path,request,kind):
    from .svr11_hardware import HARDWARE
    value=read(path)
    if value.get('checkpoint_sha')!=digest({k:v for k,v in value.items() if k!='checkpoint_sha'}):
        raise ValueError('STAGE_CHECKPOINT_SHA_CORRUPT')
    if value['key']!=key(request) or value['kind']!=kind or value['hardware']!=record(HARDWARE/'HARDWARE.json'):
        raise ValueError('RESUME_DAY_ARM_STAGE_ATTEMPT_SOURCE_HARDWARE_DRIFT')
    verify(value['sources']+value['files']+[value['hardware']]);return value


def assert_dead(root):
    path=Path(root)/'START.json'
    if path.exists() and alive(read(path)):raise NotReady('RESUME_OLD_WORKER_STILL_LIVE')


def seal_stage(root,request,result):
    root=Path(root)
    if result.get('error'):return None
    result_path=root/'RESULT.json'
    if not result_path.exists():atomic(result_path,result)
    refs=list(receipts(result));refs.append(record(result_path))
    for name in ('K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json','NATIVE_RUNTIME_LEDGER.json',
            'RECONCILIATION.json','BINARY_STAGE_CHECKPOINT.json','ACCEPTED_M_POINT.npz'):
        p=root/name
        if p.exists():refs.append(record(p))
    unique={r['path']:r for r in refs};value=envelope(request,'COMPLETED',list(unique.values()),result=record(result_path),
        scientific_PASS=result.get('PASS'),B_and_B_search_state='NOT_SUPPORTED',Native_clock_reset=False)
    path=root/'COMPLETED_STAGE_CHECKPOINT.json';atomic(path,value);return record(path)


def load_completed(root,request):
    root=Path(root);assert_dead(root)
    checkpoint=checked(root/'COMPLETED_STAGE_CHECKPOINT.json',request,'COMPLETED')
    result=read(checkpoint['result']['path'])
    if any(result.get(k,request[k])!=request[k] for k in ('day','arm')):
        raise ValueError('COMPLETED_STAGE_RESULT_AXIS_DRIFT')
    return result


def ledger_state(path,*,ceiling,context=None):
    value=read(path)
    if value.get('inflight') is not None:raise NotReady('RESUME_UNRECONCILED_NATIVE_INFLIGHT')
    if value.get('Native_ceiling_seconds')!=ceiling:raise ValueError('RESUME_NATIVE_CEILING_DRIFT')
    if context is not None and value.get('stage_context')!=context:raise ValueError('RESUME_LEDGER_SOURCE_CASE_DRIFT')
    calls=value['calls']
    if any(r.get('runtime_unavailable') or r.get('status') not in ('FINISHED','FAILED')
            or not isinstance(r.get('Native_Runtime'),(int,float))
            or not math.isfinite(r['Native_Runtime']) or r['Native_Runtime']<0 for r in calls):
        raise ValueError('RESUME_NATIVE_CALL_RUNTIME_UNRECONCILED')
    measured=sum(r['Native_Runtime'] for r in calls)
    if not math.isfinite(value['measured_Native_Runtime']) or abs(measured-value['measured_Native_Runtime'])>1e-7:
        raise ValueError('RESUME_NATIVE_TOTAL_UNRECONCILED')
    return dict(measured=measured,remaining=max(0.,ceiling-measured),calls=len(calls),ledger=record(path))


def save_binary(case,request):
    """Persist the missing inverse proof fields; matrices already exist verbatim."""
    out=Path(case.output)
    from v42_pr134_b1.common import clean
    # Use the original extended-bound serializer (including infinite original
    # boxes). Its storage digest is also the transport proof's authority.
    atomic(out/'CURRENT_C2_BOUND_PROOFS.json',clean(case.presolve.bound))
    names=('FULL_A.npz','FULL_DATA.npz','C3A_A.npz','C3A_DATA.npz','CURRENT_C2_AXES.npz',
        'CURRENT_C2_ALIASES.json','CURRENT_C2_ROW_PROOFS.json','CURRENT_C2_BOUND_PROOFS.json',
        'SCIENTIFIC_CASE_IDENTITY.json','FIXED_AIDC_ANCHOR.json','ORIGINAL_DOMAIN_EQUIVALENCE.json')
    value=envelope(request,'M_BINARY',[record(out/n) for n in names],case_sha=case.case_sha,
        fixed_AIDC=case.identity['aidc_anchor'],B_and_B_search_state='NOT_SUPPORTED',
        reentry='SAME_CASE_ORIGINAL_FULL_INCUMBENT_REPLAY_WITH_REMAINING_MEASURED_BUDGET')
    atomic(out/'BINARY_STAGE_CHECKPOINT.json',value);return value


def crash_admission(root,request):
    root=Path(root);assert_dead(root)
    if request['stage'] not in ('M1','M2'):
        return dict(status='NOT_SUPPORTED',stage=request['stage'],
            reason='LIVE_A_BRANCH_AND_BOUND_OR_ACTUAL_NATIVE_CONTROL_QUEUE_NOT_PERSISTED',
            Native_clock_reset=False,failed_attempt_preserved=True)
    checkpoint=checked(root/'BINARY_STAGE_CHECKPOINT.json',request,'M_BINARY')
    ledgers={}
    for name,kind,cap in [('K48_NATIVE_LEDGER.json','K48_SEPARATE',300.),('JOINT_NATIVE_LEDGER.json','PLANNING_NATIVE',900.)]:
        if (root/name).exists():
            context=dict(arm=request['arm'],stage=('K48_' if kind=='K48_SEPARATE' else '')+request['stage'],
                stage_case_sha=checkpoint['case_sha'],source_sha=request['source_sha'])
            ledgers[kind]=ledger_state(root/name,ceiling=cap,context=context)
    return dict(status='RESTORABLE_M_BINARY',checkpoint=record(root/'BINARY_STAGE_CHECKPOINT.json'),
        ledgers=ledgers,B_and_B_search_state='NOT_SUPPORTED',Native_clock_reset=False,
        optimizer_restart_is_same_stage=True,case_sha=checkpoint['case_sha'])
