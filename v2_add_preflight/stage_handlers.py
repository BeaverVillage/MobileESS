"""Concrete Source-YY stage callables, entered only by an approved worker.

Optimization, pricing, candidate search and acceptance arithmetic are the
original source entrypoints. This module supplies dated IO and receipts.
"""
from contextlib import ExitStack
from pathlib import Path
import numpy as np
from .stage_common import ROOT,OUT,WORK,read,record,day_inputs
from .prestart_execution import atomic
from .stage_authority import current
from v44.common import now
from v42_native.contracts import digest


def reference(request,parents):
    current()
    from .stage_reference import prepare
    folder=Path(request['output'])/'AIDC';payload=prepare(folder)
    return dict(PASS=True,AIDC_reference=record(folder/'AIDC_REFERENCE.json'),Native_seconds=0.)


def aidc(parents,stage=None):
    order=[stage] if stage else ['A2','A1_REUSE','A1','REFERENCE']
    for name in order:
        if name in parents and parents[name].get('AIDC_reference'):
            from v44.daily import load_aidc
            receipt=parents[name]['AIDC_reference']
            if record(receipt['path'])!=receipt:raise ValueError('PARENT_AIDC_FILE_DRIFT')
            return load_aidc(Path(receipt['path']).parent,'2025-05-01')[0]
    raise ValueError('CURRENT_ACCEPTED_AIDC_PARENT_REQUIRED')


def a(request,parents):
    current()
    from .stage_a_casefactory import run
    from v42_may_campaign_native90.budget import DateBudget
    from v44.daily import export_a
    out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    budget=DateBudget(out/'NATIVE_RUNTIME_LEDGER.json',native_limit=5400.)
    m1=parents.get('M1') if request['stage']=='A2' else None
    if m1 is not None:request=dict(request,M1_result=m1)
    result=run(request,budget,m1_result=m1)
    result.update(day=request['day'],arm=request['arm'],stage=request['stage'],finished_UTC=now(),
        source_sha=request['source_sha'],P2_calls=0,Native_seconds=budget.used(),
        FULL_feasible=result.get('PASS') is True,independent_Global_LB_validated=result.get('PASS') is True)
    if m1 is not None:result['fixed_M1_plan_sha']=m1['MESS_plan']['plan_sha']
    if result.get('PASS'):
        folder=export_a(result,request,out/'AIDC_FROZEN',request['stage'])
        result['AIDC_reference']=record(folder/'AIDC_REFERENCE.json')
    atomic(out/'RESULT.json',result);return result


def reuse(request,parents,b1):
    current()
    if b1 is None or b1.get('PASS') is not True:raise ValueError('SAME_DATE_ACCEPTED_B1_A1_REQUIRED')
    result=dict(b1);receipt=result['AIDC_reference']
    if record(receipt['path'])!=receipt:raise ValueError('B1_A1_ACCEPTANCE_FILE_DRIFT')
    doc=read(receipt['path']);i=doc['identity'];files=day_inputs()['files']
    if ((i['day'],i['arm'],i['stage'],i.get('reused_exact_A1'))!=('2025-05-01','B1','A1',True)
            or i['source_sha']!=request['source_sha'] or i['source']!=request['sources'] or i['input']['sha256']!=files['native']['sha256']
            or i['windows']['sha256']!=files['windows']['sha256']
            or not i.get('FULL_feasible') or not i.get('independent_Global_LB_validated') or not 0<=i.get('certified_gap',1)<=.005):
        raise ValueError('A1_REUSE_SAME_CASE_FULL_ACCEPTANCE_REQUIRED')
    return dict(result,reused_exact_A1=True,Native_seconds=0.,B1_A1_result_sha=digest(b1))


def k48(request,parents):
    current()
    from .stage_casefactory import prepare_current
    from .stage_m_case import source_binding
    from .stage_geometry_io import scope as geometry
    from .stage_checkpoint import binary_manifest,load_binary
    from v44.budget import StageBudget,resume as resume_budget
    from v44.frozen.v43_mess.prepared import run_prepared_k48
    stage=request['stage']
    if stage not in ('M1','M2'):raise ValueError('K48_UNDERLYING_CURRENT_M_STAGE_REQUIRED')
    bound=dict(request,stage=stage)
    out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    from v44.locks import process_identity
    atomic(out/'START.json',dict(process_identity(),UTC=now(),request=request))
    payload=aidc(parents,'A2' if stage=='M2' else None)
    parent=Path(request['resume_parent']) if request.get('resume_parent') else None
    if parent is None:
        case=prepare_current(payload,bound,out/'CURRENT_CASE');case.output=out
        manifest=binary_manifest(case,case._runtime_storage_root,payload['identity'])
    else:
        manifest=read(parent/'M_BINARY.json');case=load_binary(manifest,out)
        if manifest['anchor']!=payload['identity']:raise ValueError('M_REENTRY_AIDC_ANCHOR_DRIFT')
    atomic(out/'M_BINARY.json',manifest)
    with source_binding(case) as modules,geometry(case,modules):
        k=modules['table_v_k48'];g=modules['table_v_global_control']
        control=g.GlobalGapControl(g.mess_scope(case),.03,out/'GLOBAL_CONTROL');case.global_gap_control=control
        try:
            ledger=out/'K48_NATIVE_LEDGER.json'
            if parent is not None and (parent/ledger.name).exists():
                from v44.m_restore import continue_k48
                budget=resume_budget(parent/ledger.name,case=case,kind='K48_SEPARATE',destination=ledger)
                lower=continue_k48(parent,case,k,budget,out/'K48_EXECUTION',g)
            else:
                from .stage_k16_io import prepare as prepare_k16
                packet,proof=prepare_k16(k,case,out/'NATIVE0_K16')
                budget=StageBudget(ledger,case=case,kind='K48_SEPARATE')
                lower=run_prepared_k48(k,case,packet,proof,budget,out/'K48_EXECUTION')
            result=dict(PASS=True,lower=lower,M_binary=record(out/'M_BINARY.json'),fixed_AIDC=payload['identity'],
                Native_seconds=budget.used(),case_sha=case.case_sha,
                independent_Global_LB_validated=bool(lower.get('Global_LB_valid')),
                LB_origin='K48_INDEPENDENT_GLOBAL',Global_LB_numeric_required_for_UB_handoff=False)
            atomic(out/'RESULT.json',result);return result
        finally:control.close()


def m(request,parents):
    current()
    from .stage_checkpoint import load_binary
    from .stage_m_case import source_binding
    from .stage_geometry_io import scope as geometry
    from .stage_native_io import readback_scope
    from v44.budget import StageBudget,resume as resume_budget
    from v44.stages import m_outcome
    out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    from v44.locks import process_identity
    atomic(out/'START.json',dict(process_identity(),UTC=now(),request=request))
    previous=parents['K48_'+request['stage']];manifest=previous['M_binary']
    if record(manifest['path'])!=manifest:raise ValueError('CURRENT_K48_BINARY_DRIFT')
    case=load_binary(read(manifest['path']),out)
    with source_binding(case) as modules,geometry(case,modules):
        g=modules['table_v_global_control'];engine=modules['m_engine']
        control=g.GlobalGapControl(g.mess_scope(case),.03,out/'GLOBAL_CONTROL');case.global_gap_control=control
        try:
            lower=previous['lower']
            for row in lower['history']:g.mess_lower(control,case,row,same_stage_restore=True)
            parent=Path(request['resume_parent']) if request.get('resume_parent') else None
            ledger=out/'JOINT_NATIVE_LEDGER.json';registry=[]
            if parent is not None and (parent/ledger.name).exists():
                from v44.m_restore import registry as old_registry
                budget=resume_budget(parent/ledger.name,case=case,kind='PLANNING_NATIVE',destination=ledger)
                registry=old_registry(parent,case,engine)
            else:budget=StageBudget(ledger,case=case,kind='PLANNING_NATIVE')
            with readback_scope(engine,out/'NATIVE_READBACK'):
                upper,point=engine.optimize_mess(case,None,registry,budget)
            if point is not None and parent is not None and control.bounds().get('Global_UB') is None:
                certificate=read(out/'COMMON_M_PR222/BEST_GLOBAL_INCUMBENT.REPLAY.json')
                bank=engine.IncumbentBank(case);bank.offer(point,certificate)
                g.mess_upper(control,case,bank,same_stage_restore=True)
            bounds=control.bounds();search=upper.get('adaptive_search',{})
            if point is not None:
                path=out/'ACCEPTED_M_POINT.npz';np.savez_compressed(path,point=point)
                case.strict_validator(case,path)
            result=dict(**bounds,day=request['day'],arm=request['arm'],stage=request['stage'],
                case_sha=case.case_sha,source_sha=request['source_sha'],fixed_AIDC=previous['fixed_AIDC'],
                lower=lower,upper=upper,MESS_plan=upper['mess'],finished_UTC=now(),P2_calls=0,
                M_stage_execution_PASS=search.get('termination_reason')!='IMPLEMENTATION_OR_NUMERICAL_FAILURE',
                implementation_errors=[r['error'] for r in search.get('history',[]) if r.get('error')],
                global_LB=bounds['Global_LB'],global_UB=bounds['Global_UB'],
                independent_Global_LB_validated=bool(lower.get('Global_LB_valid')),LB_origin='K48_INDEPENDENT_GLOBAL',
                Native_seconds=budget.used(),K48_Native_seconds=previous['Native_seconds'],timeout=budget.remaining()<=10)
            result.update(producer='v2_add_preflight.stage_handlers.m',
                accepted_point=record(out/'ACCEPTED_M_POINT.npz') if point is not None else None,
                Joint_ledger=record(budget.path),original_upper=record(out/'COMMON_M_PR222/M_STAGE_RESULT.json'))
            result.update(m_outcome(result));result['PASS']=result['allow_downstream']
            atomic(out/'RESULT.json',result);return result
        finally:control.close()


def actual(request,parents):
    current()
    from .stage_actual_handler import run
    payload=aidc(parents);folder=Path(payload['identity']['physical']['path']).parent
    plan=parents.get('M2',parents.get('M1',{})).get('MESS_plan')
    if request['arm'] in ('B2','B3'):
        from .stage_origin import require_m
        require_m(parents['M2'] if 'M2' in parents else parents['M1'])
    raw=run(arm=request['arm'],folder=folder,mess=plan,output=request['output'],with_fresh=False)
    out=Path(request['output']);arrays=raw.pop('actual');physical=arrays.pop('physical')
    np.savez_compressed(out/'ACTUAL_PHYSICAL.npz',P=physical['PCC_P_kw'],Q=physical['PCC_Q_kvar'],**physical)
    # Preserve every event/QoS/migration/carryout receipt without ndarray JSON.
    from v42_pr134_b1.common import clean
    atomic(out/'ACTUAL_EVENTS.json',clean(arrays))
    result=dict(raw,physical=record(out/'ACTUAL_PHYSICAL.npz'),events=record(out/'ACTUAL_EVENTS.json'),MESS_plan=plan,
        Native_seconds=0.,scope='Original event/Job stage; full electrical acceptance belongs to following Fresh stage')
    atomic(out/'RESULT.json',result);return result


def fresh(request,parents):
    current()
    from .stage_actual import fresh_handler
    old=parents['ACTUAL'];receipt=old['physical']
    if record(receipt['path'])!=receipt:raise ValueError('ACTUAL_PQ_FILE_DRIFT')
    with np.load(receipt['path']) as z:a={k:z[k] for k in ('P','Q')}
    result=fresh_handler(day_inputs(),a,old['MESS_plan'],request['output'])
    return dict(result,original_FULL_Job_PASS=old['original_FULL_Job_PASS'],
        full120_security_PASS=result['PASS'],Native_seconds=0.,actual_PQ=receipt)


HANDLERS={'REFERENCE':reference,'A1':a,'A1_REUSE':reuse,'K48_M1':k48,'M1':m,
    'A2':a,'K48_M2':k48,'M2':m,'ACTUAL':actual,'FRESH':fresh}
