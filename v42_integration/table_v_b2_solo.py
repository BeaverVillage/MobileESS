"""B2-only staged production, using original Reference/M1/K48/Actual engines.

Formal launch files bind the direct user request, current release and exact
date/stage ledgers. Completed canary planning is reused only with its original
FULL proof and immutable point; prefix Actual never becomes Full96 evidence.
"""
from copy import deepcopy
import csv
import gc
import json
import math
import os
from pathlib import Path
import shutil
from time import perf_counter,time
import traceback
import uuid

from .a_engine import digest
from .m_engine import _write,file_record
from .table_v_b2_gate import B2_SCOPES,REPRESENTATIVES,MAY_DATES
from .table_v_budget import TableVStageBudget,MAIN_CAPS,K48_CAPS,SCHEMA
from .table_v_launch import release_identity
from .table_v_launch_evidence import REFERENCE_POLICY,validate_arm_full96,validate_arm_canary16
from .table_v_run import HISTORY,adapters,load_context,verify_adapters,require_arm_launch

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2)
    return file_record(path)


def initial_predecessors():
    head=read(ROOT/'docs/v42_source18r_phase_20261015/DIAGNOSTIC_HEAD.json')
    if head.get('state')!='COMPLETE' or file_record(head['ledger']['path'])!=head['ledger']:
        raise RuntimeError('LATEST_B1_NATIVE_DESCENDANT_REQUIRES_RECONCILIATION')
    e08=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION08'
    return dict(PLANNING=head['ledger'],K48=file_record(e08/'K48_NATIVE_LEDGER.json'))


def prepare_date(day,execution,authority):
    """Compile current typed inputs once; never build a MESS model here."""
    from .release_date_case import compile_date_case
    from .table_v_flex_planning import compile_table_v_flex_context
    from .table_v_reference import make_reference,require_reference_acceptance
    execution=Path(execution)
    if execution.exists():
        receipt=read(execution/'B2_PREPARATION_COMPLETE.json');verify_adapters(execution)
        if receipt['day']!=day or receipt['release']!=release_identity():
            raise PermissionError('B2_EXISTING_PREPARATION_DIFFERENT_RELEASE_OR_DATE')
        for r in receipt['inputs']:
            if file_record(r['path'])!=r:raise ValueError('B2_PREPARED_INPUT_BYTES_DRIFT')
        return receipt
    execution.mkdir(parents=True);start=perf_counter()
    basic=compile_date_case(day,output=execution/'INPUTS/BASIC',call_cap=5400.)
    context=compile_table_v_flex_context(basic,output=execution/'INPUTS/FULL_FLEX',call_cap=5400.)
    ref,acceptance=make_reference(context,output=execution/'REFERENCE')
    manifest=context['manifest'];require_reference_acceptance(acceptance,identity=manifest['identity'],result=ref)
    write_new(execution/'REFERENCE_RESULT.json',ref);write_new(execution/'REFERENCE_ACCEPTANCE.json',acceptance)
    expected=dict(day=day,source_sha=manifest['source_sha'],source_identity=manifest['identity'])
    predecessors=initial_predecessors() if day=='2025-05-01' else {}
    for name,kind,caps,stage in [('PLANNING','PLANNING_NATIVE',MAIN_CAPS,'B2:M1'),('K48','K48_SEPARATE',K48_CAPS,'B2:K48_M1')]:
        carried=[predecessors[name]] if name in predecessors else []
        authorization=dict(schema=SCHEMA,approved=True,budget_kind=kind,
            authorization_id='B2_SOLO_'+digest(dict(execution=str(execution.resolve()),day=day,kind=kind,authority=authority)),
            authorized_ledger_path=str((execution/(name+'_NATIVE_LEDGER.json')).resolve()),
            stage_caps_seconds=caps,total_limit_seconds=None,total_limit_enabled=False,
            timeout_basis='CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE',P2_calls=0,Worker=1,Threads=1,
            human_approval_reference=authority,source_cases=[expected],authorized_arm_stages=[stage],carry_forward_ledgers=carried)
        write_new(execution/(name+'_AUTHORIZATION.json'),authorization)
        TableVStageBudget(authorization['authorized_ledger_path'],authorization=authorization,historical_ledgers=HISTORY)
    sources=release_identity()
    write_new(execution/'EXECUTION_SOURCE_FREEZE.json',dict(files=sources['release_sources'],source_sha=digest(sources['release_sources'])))
    inputs=[file_record(p) for p in sorted((execution/'INPUTS').rglob('*')) if p.is_file()]
    inputs += [file_record(execution/p) for p in ('REFERENCE_RESULT.json','REFERENCE_ACCEPTANCE.json')]
    receipt=dict(day=day,scope='B2_ONLY_TYPED_INPUTS_AND_REFERENCE_NOT_A1_OPTIMIZATION',
        release=sources,source_case=expected,inputs=inputs,Native_calls=0,Original_M_model_builds=0,
        wall_seconds=perf_counter()-start,prior_day_state_imported=False,P2_calls=0)
    write_new(execution/'B2_PREPARATION_COMPLETE.json',receipt)
    del context,basic;gc.collect()
    return receipt


def case_binding(execution):
    m=read(Path(execution)/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')
    return dict(day=m['day'],source_sha=m['source_sha'],source_identity=m['identity']),digest(m['science_derivation']['policy'])


def make_launch(scope,dates,executions,authority,output,*,may01_approval=None,representative_approvals=None):
    """Materialize a reviewable exact approval from the user's staged request."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cases={};policies={}
    for day,root in executions.items():cases[day],policies[day]=case_binding(root)
    plan=dict(schema='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1',dates=list(dates),run_arms=['B2'],
        execution_scope=scope,Worker=1,Threads=1,P2_calls=0,R2='HOLD',automatic_start=False,
        actual_slots=16 if scope==B2_SCOPES[1] else 96,
        execution_roots={d:str(Path(executions[d]).resolve()) for d in dates},case_bindings=cases,policy_bindings=policies,
        actual_policy_bindings={d:{'B2':digest(REFERENCE_POLICY)} for d in cases},
        budget_authorizations={d:{n:file_record(Path(executions[d])/(n+'_AUTHORIZATION.json')) for n in ('PLANNING','K48')} for d in dates},
        **release_identity())
    approved=dict(schema='TABLE_V_EXPLICIT_RELEASE_LAUNCH_APPROVAL_V1',approved=True,human_approval_reference=authority,
        approved_plan_sha=digest(plan),dates=list(dates),execution_scope=scope,
        approved_release_sha=plan['release_sha'],approved_release_git_sha=plan['release_git_sha'],
        approved_policy_bindings_sha=digest(policies),approved_budget_bindings_sha=digest(plan['budget_authorizations']))
    approval=write_new(output/'HUMAN_LAUNCH_AUTHORIZATION.json',approved)
    gate=dict(launch_authorization=approval)
    if may01_approval:
        gate.update(B2_May01_release=may01_approval,B2_May01_Full96=read(may01_approval['path'])['physical_evidence'])
    if representative_approvals:gate['B2_representative_canary_approvals']=representative_approvals
    write_new(output/'PRODUCTION_LAUNCH_PLAN.json',plan);write_new(output/'PRODUCTION_LAUNCH_GATE.json',gate)
    from .table_v_campaign import _launch_gate
    _launch_gate(plan,gate)
    write_new(output/'LAUNCH_VALIDATED.json',dict(PASS=True,plan_sha=digest(plan),gate_sha=digest(gate),
        B1_B0_B3_outcomes_not_required=True,Native_calls=0,model_builds=0))
    return plan,gate


def approve_completed(execution,folder,plan,authority,*,slots):
    if slots not in (16,96):raise ValueError('B2_EXACT_16_OR_96_APPROVAL_SCOPE_REQUIRED')
    expected,policy=case_binding(execution);outcome=file_record(Path(folder)/'ARM_OUTCOME.json')
    verifier=validate_arm_full96 if slots==96 else validate_arm_canary16
    verifier(outcome,expected,'B2',expected_policy_sha=digest(REFERENCE_POLICY))
    value=dict(day=expected['day'],arm='B2',approved=True,human_approval_reference=authority,
        source_case=expected,release_sha=plan['release_sha'],release_git_sha=plan['release_git_sha'],
        policy_sha=policy,actual_policy_sha=digest(REFERENCE_POLICY),physical_evidence=outcome)
    return write_new(Path(folder)/('B2_FULL96_RELEASE_APPROVAL.json' if slots==96 else 'B2_CANARY16_RELEASE_APPROVAL.json'),value)


def check_integrity(execution,outcome):
    """Scientific/date failure may continue; integrity uncertainty stops all."""
    from .table_v_control import CampaignStopped
    from .table_v_budget import require_authorization,_native_origin
    execution=Path(execution);verify_adapters(execution)
    expected,_=case_binding(execution)
    for name in ('PLANNING','K48'):
        ledger=read(execution/(name+'_NATIVE_LEDGER.json'))
        authorization=require_authorization(read(execution/(name+'_AUTHORIZATION.json')))
        if (ledger.get('authorization_document')!=authorization or ledger.get('release_identity',{}).get('authorization_sha')!=digest(authorization)
                or authorization['source_cases']!=[expected]
                or authorization.get('authorized_arm_stages')!=['B2:M1' if name=='PLANNING' else 'B2:K48_M1']):
            raise RuntimeError('B2_NATIVE_LEDGER_AUTHORIZATION_DRIFT')
        if ledger.get('inflight') or ledger.get('active_stage_context') or ledger.get('active_stage_owner_pid'):
            raise RuntimeError('B2_UNRECONCILED_NATIVE_STAGE')
        for r in ledger['release_identity'].get('historical_read_only',[]):
            if file_record(r['path'])!=r:raise RuntimeError('B2_HISTORICAL_NATIVE_LEDGER_DRIFT')
        total=0.;used={}
        for index,row in enumerate(ledger['calls']):
            if not row.get('solver','').startswith('GUROBI'):continue
            runtime=row.get('Native_Runtime');context=row.get('stage_context',{})
            if type(runtime) not in (float,int) or not math.isfinite(runtime) or runtime<0:raise RuntimeError('B2_UNKNOWN_OR_INVALID_NATIVE_RUNTIME')
            total+=runtime;key=(context.get('day'),context.get('arm'),context.get('stage'))
            stage=context.get('arm','')+':'+context.get('stage','');cap=authorization['stage_caps_seconds'].get(stage)
            if cap is None:raise RuntimeError('B2_NATIVE_UNKNOWN_STAGE_AUTHORITY')
            prior=used.get(key,0.)
            if row.get('carried_forward_from'):
                _native_origin(file_record(execution/(name+'_NATIVE_LEDGER.json')),index,row)
            else:
                requested=row.get('cap_seconds')
                if (context.get('day')!=expected['day'] or context.get('arm')!='B2' or stage not in authorization['authorized_arm_stages']
                        or context.get('source_sha')!=expected['source_sha']
                        or type(requested) not in (float,int) or not math.isfinite(requested) or not 0<requested<=max(0.,cap-prior)+1e-7
                        or abs(row.get('overshoot_seconds',0.)-max(0.,runtime-requested))>1e-6):
                    raise RuntimeError('B2_UNAUTHORIZED_NATIVE_STAGE_OR_REQUESTED_CAP')
            used[key]=prior+runtime
        recorded=ledger.get('Gurobi_Native_seconds')
        if type(recorded) not in (float,int) or not math.isfinite(recorded) or abs(recorded-total)>1e-6:
            raise RuntimeError('B2_NATIVE_LEDGER_TOTAL_MISMATCH')
    error=(outcome.get('error','')+' '+outcome.get('traceback','')).upper()
    if outcome.get('status')=='INTERRUPTED_BY_USER' or 'CAMPAIGNSTOPPED' in error or 'CAMPAIGN_STOP' in error:
        raise CampaignStopped('B2_STOP_REQUEST_PRESERVED')
    markers=('DRIFT','UNRECONCILED','WORKER','OWNERSHIP','AUTHORIZATION','NOT_AUTHORIZED','UNBUDGETED','FORGED','INTEGRITY','SOURCE_BYTES')
    if any(word in error for word in markers):raise RuntimeError('B2_FATAL_INTEGRITY_FAILURE:'+outcome.get('error',''))


def reuse_planning_actual96(execution,canary_folder,plan,gate):
    """Use genuine same-case FULL M1 planning; execute new Actual/Fresh96."""
    from .tablev_actual import run_tablev_actual,run_tablev_fresh
    from .release_ac_contract import CONTRACT
    from .table_v_control import require_running
    from .table_v_control import CampaignStopped
    execution=Path(execution);canary_folder=Path(canary_folder)
    require_arm_launch(execution,dict(plan=plan,gate=gate),actual_slots=96,arm='B2')
    expected,_=case_binding(execution)
    validate_arm_canary16(file_record(canary_folder/'ARM_OUTCOME.json'),expected,'B2',expected_policy_sha=digest(REFERENCE_POLICY))
    folder=execution/'B2/ATTEMPT_FULL96';folder.mkdir(parents=True,exist_ok=False)
    start=perf_counter();current='VERIFIED_FULL_M1_REUSE';stages=read(canary_folder/'PLANNING_STAGE_RESULTS.json')
    outcome={};context=None
    try:
        # Copy only already verified immutable JSON bodies; their original Raw
        # pointers and matrix/domain/Case SHA remain unchanged and explicit.
        (folder/'M1').mkdir()
        for name in ('TABLE_V_M_RESULT.json','TABLE_V_M_ACCEPTANCE.json','SCIENTIFIC_CASE_IDENTITY.json'):
            shutil.copy2(canary_folder/'M1'/name,folder/'M1'/name)
        write_new(folder/'PLANNING_STAGE_RESULTS.json',stages)
        write_new(folder/'PLANNING_REUSE.json',dict(scope='SAME_SOURCE_CASE_FULL96_PLANNING_FROM_REAL_CANARY16',
            donor=file_record(canary_folder/'ARM_OUTCOME.json'),source_case=expected,
            M1_result=file_record(canary_folder/'M1/TABLE_V_M_RESULT.json'),
            M1_acceptance=file_record(canary_folder/'M1/TABLE_V_M_ACCEPTANCE.json'),
            new_Native_calls=0,new_M_model_builds=0,prefix_Actual_promoted_to_Full96=False))
        context=load_context(execution);ref=read(execution/'REFERENCE_RESULT.json');ra=read(execution/'REFERENCE_ACCEPTANCE.json')
        result,acceptance=stages['M1']['result'],stages['M1']['acceptance']
        write_new(folder/'ARM_EXECUTION_SOURCE_FREEZE.json',read(execution/'EXECUTION_SOURCE_FREEZE.json'))
        require_running(execution);current='ACTUAL96';tick=perf_counter()
        actual=run_tablev_actual(context=context,arm='B2',reference_result=ref,reference_acceptance=ra,
            output=folder/current,m_result=result,m_acceptance=acceptance,
            gate=dict(Gate_contract=CONTRACT,official_contract_authorized=True),slots=96)
        write_new(folder/'ACTUAL_RESULT.json',actual);actual_wall=perf_counter()-tick
        if actual['status']!='FULL_PASS':raise RuntimeError('B2_ACTUAL96_REUSED_PLANNING_NOT_FULL_ACCEPTED')
        require_running(execution);current='FRESH_AC96';tick=perf_counter()
        fresh=run_tablev_fresh(context=context,actual_result=actual,output=folder/current,
            m_result=result,m_acceptance=acceptance,slots=96)
        write_new(folder/'FRESH_AC_RESULT.json',fresh)
        write_new(folder/'ACTUAL_FRESH_WALL.json',dict(Actual96_wall=actual_wall,Fresh96_wall=perf_counter()-tick))
        outcome=dict(status='FULL_PASS' if fresh['status']=='FULL_PASS' else 'PHYSICAL_OR_ACTUAL_FAIL',
            actual=actual,fresh=fresh,completed_planning_stages=['M1'],executed_actual_slots=96,executed_fresh_slots=96)
    except CampaignStopped as error:
        outcome=dict(status='INTERRUPTED_BY_USER',failed_stage=current,error=repr(error),traceback=traceback.format_exc(),physical_PASS_claimed=False)
    except Exception as error:
        outcome=dict(status='NOT_CERTIFIED',failed_stage=current,error=repr(error),traceback=traceback.format_exc(),physical_PASS_claimed=False)
    finally:
        context=None;gc.collect();outcome.update(day=expected['day'],arm='B2',P2_calls=0,R2='HOLD',wall_seconds=perf_counter()-start)
        write_new(folder/'ARM_OUTCOME.json',outcome)
    check_integrity(execution,outcome)
    return outcome,folder


def summarize(executions,results,output):
    """Keep scientific certification, physical success and nested costs apart."""
    rows=[];costs=[]
    for day in sorted(executions):
        found=[r for r in results if r['day']==day];last=found[-1] if found else {}
        root=executions.get(day);M=K=0.
        if root:
            for name in ('PLANNING','K48'):
                for call in read(Path(root)/(name+'_NATIVE_LEDGER.json'))['calls']:
                    if call.get('solver')=='GUROBI' and all(call.get('stage_context',{}).get(k)==v for k,v in dict(day=day,arm='B2').items()):
                        if name=='PLANNING':M+=call['Native_Runtime']
                        else:K+=call['Native_Runtime']
            for p in Path(root).rglob('PREPARATION_PROFILE.jsonl'):
                for line in p.read_text().splitlines():
                    if line:costs.append(dict(day=day,source=str(p),**json.loads(line)))
        row=dict(day=day,status=last.get('status','NOT_RUN'),phase=last.get('phase',''),M1_Native_seconds=M,K48_Native_seconds=K,
            FULL_UB=None,certified_Global_LB=None,Global_Gap=None,outcome=last.get('outcome'),failure=last.get('error'))
        if last.get('outcome'):
            folder=Path(last['outcome']['path']).parent;stages=read(folder/'PLANNING_STAGE_RESULTS.json')
            result=stages.get('M1',{}).get('result',{})
            row.update(FULL_UB=result.get('BEST_GLOBAL_UB',result.get('objective')),certified_Global_LB=result.get('certified_Global_LB'),Global_Gap=result.get('relative_global_gap'))
        rows.append(row)
    _write(Path(output)/'DATE_STATUS.json',dict(dates=rows,Native_sums_are_B2_only_not_old_B1_costs=True,stage_profiles=costs))
    with (Path(output)/'DATE_STATUS.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return rows
