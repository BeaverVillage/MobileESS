"""Versioned stage adapters. Entry requires a live V44 case lease and permit."""
from contextlib import contextmanager
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import ast
import inspect
import textwrap
import time
import numpy as np

from .common import ROOT,DOC,read,record,atomic,verify,digest,now,NotReady
from .daily import day_inputs,load_aidc,export_a,ActualBinding,corrective_binding,clone
from .execution import assert_current,native_stage
from .config import axis
from .svr11_grid import stage_scope


@stage_scope
def reference(day,output):
    from v43_arms.reference import project
    from v42_temporal.native import load_power
    from v42_integrated.contract import physical_authority
    row=day_inputs(day);native=read(row['files']['native']['path']);output=Path(output)
    if (output/'AIDC_REFERENCE.json').exists():return load_aidc(output,day)[0]
    output.mkdir(parents=True,exist_ok=False)
    sites,caps,known,anon,selected,x,carry,cons=project(native)
    with physical_authority():_,power,idle,swing=load_power(native)
    gpu=known+anon;it=idle*caps+swing*gpu
    pcc=np.array([[power[s,t].slope*it[t,j]+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
    arrays=dict(sites=np.array(sites),capacities=caps,known_gpu=known,cc4_served_gpu=anon,GPU=gpu,IT_kw=it,
        PCC_P_kw=pcc,PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    np.savez_compressed(output/'PLANNING_PHYSICAL.npz',**arrays)
    aidc=dict(selected_jobs=selected,CC4_service=x,CC4_carryout=carry,
        AIDC_P_by_site={s:pcc[:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    identity=dict(day=day,arm='B0',stage='REFERENCE',parent_case_sha=row['files']['native']['sha256'],
        aidc_anchor=digest(aidc),input=row['files']['native'],windows=row['files']['windows'],reference=native['reference'],
        physical=record(output/'PLANNING_PHYSICAL.npz'),source=assert_current()['request']['sources'],
        conservation=cons,AIDC_optimization_calls=0,MESS_optimization_calls=0,
        rule='EXACT_PR189_R0_Q50',B1_optimized_commands_read=False)
    atomic(output/'AIDC_REFERENCE.json',dict(identity=identity,**aidc));return load_aidc(output,day)[0]


def reuse_golden(request):
    if (DOC/'svr11_revision01/EPOCH12_SOURCE_PIN.json').exists():
        raise PermissionError('GOLDEN003_SEVEN_REG_GRID_CANNOT_CERTIFY_SVR11')
    from v43_actual.case import accepted
    certificate,freeze,native,windows,arrays=accepted()
    row=day_inputs(request['day'])
    if request['day']!='2025-05-01' or row['files']['native']['sha256']!=freeze['scientific_input']['NATIVE_INPUT.json']['sha256']:
        raise ValueError('GOLDEN003_EXACT_MAY01_INPUT_ONLY')
    verify([certificate[k] for k in ('source_freeze','result','planning_freeze','planning_arrays')])
    result=read(certificate['result']['path'])
    # The original result has the same PR189 UB/LB/gap acceptance fields.
    result.update(freeze=certificate['planning_freeze'],planning=certificate['planning_arrays'])
    return result


@stage_scope
def a_stage(request,*,m1=None):
    assert_current()
    from v42_may_campaign_native90.budget import DateBudget
    from v42_may_campaign_native90.a_stage import run
    from v43_followup.physical_cache import cache_scope
    root=Path(request['root']);root.mkdir(parents=True,exist_ok=False)
    from .locks import process_identity
    atomic(root/'START.json',dict(process_identity(),UTC=now(),request=request))
    atomic(root/'request.json',request)
    budget=None
    try:
        budget=DateBudget(root/'NATIVE_RUNTIME_LEDGER.json',native_limit=5400.)
        with native_stage(request):
            if m1 is None:
                with cache_scope(request):result=run(request,budget)
            else:
                from .a2 import scope
                with scope(request,m1) as original:result=original(request,budget)
        result.update(day=request['day'],arm=request['arm'],stage=request['stage'],finished_UTC=now(),P2_calls=0,
            source_sha=request['source_sha'],Native_seconds=budget.used() if budget else 0.,
            independent_Global_LB_validated=bool(result.get('PASS')),FULL_feasible=bool(result.get('PASS')))
        if m1 is not None:result.update(fixed_M1_plan_sha=m1['MESS_plan']['plan_sha'],M1_UB_LB_transferred=False)
        atomic(root/'RESULT.json',result)
        if result.get('PASS'):
            folder=export_a(result,request,root/'AIDC_FROZEN',request['stage'])
            result['AIDC_reference']=record(folder/'AIDC_REFERENCE.json')
        atomic(root/'RESULT.json',result)
        return result
    except BaseException as error:
        import traceback
        result=dict(PASS=False,day=request['day'],arm=request['arm'],stage=request['stage'],
            finished_UTC=now(),source_sha=request['source_sha'],error=repr(error),traceback=traceback.format_exc())
        if m1 is not None:result['fixed_M1_plan_sha']=m1['MESS_plan']['plan_sha']
        atomic(root/'RESULT.json',result);return result
    finally:
        atomic(root/'RECONCILIATION.json',dict(UTC=now(),inflight=None if budget is None else budget.inflight,
            Native_seconds=0 if budget is None else budget.used()))
        if (root/'RESULT.json').exists():
            from .checkpoints import seal_stage
            seal_stage(root,request,read(root/'RESULT.json'))


@stage_scope
def m_stage(request,aidc):
    assert_current()
    from v42_may_campaign_native90.preflight import native_zero
    from .runtime import build,load
    from .budget import StageBudget
    from .frozen.v43_mess.prepared import run_prepared_k48
    from .frozen.v43_mess.performance import install,record_caches
    from .stages import m_outcome
    out=Path(request['output']);out.mkdir(parents=True,exist_ok=False);began=time.perf_counter()
    from .locks import process_identity
    from .checkpoints import save_binary,seal_stage
    from .budget import resume as resume_budget
    parent=Path(request['resume_parent']) if request.get('resume_parent') else None
    atomic(out/'START.json',dict(process_identity(),UTC=now(),request=request))
    atomic(out/'request.json',request)
    def progress(value):atomic(out/'progress.json',dict(value,UTC=now()))
    with native_stage(request):
        with native_zero() as denied:
            modules=load();k=modules['table_v_k48'];m=modules['m_engine']
            if parent is None:
                case=build(aidc,request,progress);install(case,modules)
                packet,proof=k.prepare_k16(case,None,out/'NATIVE0_K16')
                if not proof.get('PASS'):raise ValueError('ORIGINAL_M_NATIVE0_PROOF')
                save_binary(case,request)
            else:
                from .m_restore import restore
                case=restore(parent,out,request,aidc,modules);install(case,modules)
            if denied:raise ValueError('ORIGINAL_M_NATIVE0_OPTIMIZE_FORBIDDEN')
        build_wall=time.perf_counter()-began;control_module=modules['table_v_global_control']
        control=control_module.GlobalGapControl(control_module.mess_scope(case),.03,out/'GLOBAL_CONTROL')
        case.global_gap_control=control
        try:
            def budget_for(name,kind):
                if parent is not None and (parent/name).exists():
                    return resume_budget(parent/name,case=case,kind=kind,destination=out/name,progress=progress)
                return StageBudget(out/name,case=case,kind=kind,progress=progress)
            lower=budget_for('K48_NATIVE_LEDGER.json','K48_SEPARATE')
            if parent is None:lb=run_prepared_k48(k,case,packet,proof,lower,out/'K48_EXECUTION')
            elif (parent/'LOWER_STAGE_RESULT.json').exists():
                lb=read(parent/'LOWER_STAGE_RESULT.json')
                for row in lb['history']:control_module.mess_lower(control,case,row,same_stage_restore=True)
            else:
                from .m_restore import continue_k48
                lb=continue_k48(parent,case,k,lower,out/'K48_EXECUTION',control_module)
            atomic(out/'LOWER_STAGE_RESULT.json',lb)
            upper=budget_for('JOINT_NATIVE_LEDGER.json','PLANNING_NATIVE')
            inherited=[]
            if parent is not None:
                from .m_restore import registry
                inherited=registry(parent,case,m)
            ub,point=m.optimize_mess(case,None,inherited,upper)
            atomic(out/'UPPER_STAGE_RESULT.json',ub);record_caches(case,out/'CURRENT_CASE_CACHE_METRICS.json')
            from v42_may_campaign_native90.m_model import verify_case
            if parent is None:verify_case(case)
            else:
                from .m_restore import verify_restored
                verify_restored(case)
            if point is not None:
                np.savez_compressed(out/'ACCEPTED_M_POINT.npz',point=point)
                # Also retain a certified UB when a restored budget is already
                # exhausted and the adaptive search correctly makes no call.
                if parent is not None and control.bounds().get('Global_UB') is None:
                    certificate=read(out/'COMMON_M_PR222/BEST_GLOBAL_INCUMBENT.REPLAY.json')
                    bank=m.IncumbentBank(case);bank.offer(point,certificate)
                    control_module.mess_upper(control,case,bank,same_stage_restore=True)
            bounds=control.bounds();search=ub.get('adaptive_search',{})
            health=dict(M_stage_execution_PASS=search.get('termination_reason')!='IMPLEMENTATION_OR_NUMERICAL_FAILURE',
                implementation_errors=[r.get('error') for r in search.get('history',[]) if r.get('error')])
            result=dict(**bounds,**health,day=request['day'],arm=request['arm'],stage=request['stage'],
                case_sha=case.case_sha,source_sha=request['source_sha'],fixed_AIDC=aidc['identity'],
                lower=lb,upper=ub,MESS_plan=ub['mess'],finished_UTC=now(),P2_calls=0,
                global_LB=bounds['Global_LB'],global_UB=bounds['Global_UB'],
                independent_Global_LB_validated=bool(lb.get('Global_LB_valid')),LB_origin='K48_INDEPENDENT_GLOBAL',
                K48_Native_seconds=lower.used(),Joint_Native_seconds=upper.used(),
                timeout=upper.remaining()<=10,build_wall_seconds=build_wall,wall_seconds=time.perf_counter()-began,
                Native_seconds=lower.used()+upper.used(),Native_calls=len(lower.calls)+len(upper.calls),
                same_stage_checkpoint_restored=parent is not None,B_and_B_search_state='NOT_SUPPORTED',
                Native_clock_reset=False)
            result.update(m_outcome(result));result['PASS']=result['allow_downstream']
            atomic(out/'RESULT.json',result);atomic(out/'RECONCILIATION.json',dict(inflight=None,Native_seconds=result['Native_seconds']))
            seal_stage(out,request,result)
            return result
        finally:control.close()


def driver(function,output):
    """Port only shared-lock ownership and historical single-worker admission."""
    text=textwrap.dedent(inspect.getsource(function))
    old='from v42_may_campaign.common import exclusive_lock'
    if text.count(old)!=1:raise ValueError('ORIGINAL_SHARED_LOCK_BOUNDARY_DRIFT')
    text=text.replace(old,'from v44.execution import shared_lease_scope as exclusive_lock')
    text=text.replace('from v43.golden import no_heavy_peer','from v44.execution import assert_current as no_heavy_peer')
    text=text.replace('FRESH_ORIGINAL7_AC.json','FRESH_SVR11_TIME_AC.json')
    text=text.replace('PR189_SNAPSHOT_STATIC_7REG_NO_ADDED_SVR','V44_EPOCH12_SVR11_AUTO_NATIVE_TIME')
    path=Path(output);path.write_text(text,encoding='utf8')
    ns=dict(function.__globals__,heavy_peers=lambda:[]);exec(compile(text,str(path),'exec'),ns)
    return ns[function.__name__]


@stage_scope
def actual(request,aidc_folder,mess):
    """Actual and independent Fresh remain in the existing sequential driver."""
    assert_current()
    out=Path(request['output']);day=request['day'];arm=request['arm']
    observations=__import__('v43_actual.observations',fromlist=['load_observations']).load_observations
    bundle=Path(day_inputs(day)['actual_bundle'])
    if arm in ('B0','B2'):
        import v43_baseline.worker as original
        binding=ActualBinding(arm,aidc_folder,mess,day)
        function=driver(original.run,out.with_name(out.name+'.DRIVER.py'))
        function=clone(function,ArmBinding=lambda *a,**kw:binding,
            load_observations=lambda **kw:observations(bundle=bundle,**kw),
            FullPrefixReferenceAC=lambda **kw:__import__('v44.svr11_ac',fromlist=['SVR11CurrentAC']).SVR11CurrentAC(arm=arm,**kw))
        result=function(arm,out,reference_folder=aidc_folder,mess_result=request.get('MESS_result'))
    else:
        import v43_corrective.compare as original
        import v43_actual.compare as shared
        from .config import KNOWN_POLICY
        # The verified C1 uses the existing case-specific affine/AC correction.
        # Missing evidence must not silently reactivate its older affine gate.
        proof=request.get('correction_proof')
        if not proof:raise NotReady('EXACT_CASE_C1_AFFINE_AC_CORRECTION_PROOF_REQUIRED')
        verify([proof]);proof_path=proof['path']
        binding=corrective_binding(arm,aidc_folder,mess,day)
        shared_run=driver(shared.run,out.with_name(out.name+'.SHARED_DRIVER.py'))
        namespace=dict(shared.__dict__);namespace.update(run=shared_run,
            load_observations=lambda **kw:observations(bundle=bundle,**kw))
        # The existing corrective worker builds its private function namespace
        # from this module-like object and retains its independent Fresh path.
        proxy=SimpleNamespace(**namespace)
        from .svr11_actual import corrective_driver
        function=corrective_driver(original.run,proxy,binding,axis(day)['day_start_seconds'])
        cert=DOC/'svr11_revision01/CURRENT_AC_CERTIFICATION.json'
        result=function(arm,out,reference_folder=aidc_folder,mess_result=request.get('MESS_result'),
            control_slots=120,ac_mode='FAST',ac_certification=str(cert),variants=('C1',),
            correction_proof=proof_path,known_window_policy=KNOWN_POLICY)
    result.update(day=day,arm=arm,stage='ACTUAL_FRESH',Known_policy_status='EXECUTED_RESEARCH_ASSUMPTION' if arm in ('B1','B3') else 'NOT_APPLICABLE')
    result.update(hardware_revision='V44_SVR11_REVISION01',SVR_banks=11,RegControl_count=40,
        Planning_tap_queue_transfer=0,Native_TIME_controls=True)
    atomic(out/'RESULT.json',result)
    from .checkpoints import seal_stage
    seal_stage(out,request,result)
    return result
