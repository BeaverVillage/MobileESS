"""Named public/physical algebra fixtures; no solver or Actual execution."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record, vector_sha
from v42_integration.table_v_launch_evidence import validate_arm_full96, validate_arm_canary16, REFERENCE_POLICY
from v42_integration.table_v_reference import ANCHOR_FIELDS, SCHEMA as REFERENCE_SCHEMA
from v42_integration.release_p1_acceptance import SCHEMA as A_SCHEMA
from v42_integration.release_ac_contract import CONTRACT, validate_settled_fresh


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')
    return file_record(path)


def fixture(root, arm, *, day='2025-05-01', slots=96):
    from v42_integration.table_v_flex_planning import compile_public_reference
    from v42_integration.production_case import initial_mess
    from test_v42_release_ac_contract import fixture as physical_fixture
    begin=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
    sites=[f'AIDC{n:02d}' for n in range(1,13)];caps=dict.fromkeys(sites,65)
    state=dict(day=day,begin_epoch_seconds=begin,capacities=caps,running=[],pending=[],historical_completed=[])
    state['initial_state_payload_keys']=list(state)
    state['common_initial_state_sha']=digest({k:state[k] for k in state['initial_state_payload_keys']})
    state['freeze_sha']=digest(state)
    initial=write(root/'INITIAL.json',state)
    module_root=Path(__file__).resolve().parents[1]
    sources=[file_record(module_root/name) for name in ('v42_integration/table_v_reference.py',
        'v42_integration/production_case.py','v42_integration/qos.py','v42_native/service.py')]
    static_policy=dict(policy_id='TABLE_V_CURRENT_E1',scenario='E1',participation='FLEX30',R2='HOLD')
    science_derivation=dict(source_records=sources,policy=static_policy,public_records={})
    case_derivation=dict(science=digest(science_derivation),initial=state['common_initial_state_sha'])
    identity=dict(science_sha=digest(science_derivation),case_sha=digest(case_derivation),initial_state_sha=state['common_initial_state_sha'])
    expected=dict(day=day,source_sha=digest(sources),source_identity=identity)
    scheduler,_=compile_public_reference(state)
    reference=dict(selected_jobs={},AIDC_P_by_site={s:[0.]*96 for s in sites},AIDC_Q_by_site={s:[0.]*96 for s in sites},
        known_site_GPU={s:[0.]*96 for s in sites},nominal_site_GPU={s:[0.]*96 for s in sites},
        CC4_service={'reference':0.},CC4_carryout={'reference':0.},anonymous_resource_envelope=[],
        source_nominal_forecast_GPUh=0.,source_identity=identity,source_sha=expected['source_sha'],
        initial_state_sha=identity['initial_state_sha'],initial_record=initial,resource_sites=sites,capacities=caps,
        FULL_feasible=False,P2_calls=0,reference_sources=sources,reference_service_proof={'PASS':True},
        reference_sha=scheduler.reference_sha,public_reference_records=scheduler.assigned,
        fixed_Q50_expired_running_holds={},service_obligations={})
    reference['aidc_anchor']=digest({k:reference[k] for k in ANCHOR_FIELDS})
    reference['reference_artifact_sha']=digest(reference)
    rr=dict(schema=REFERENCE_SCHEMA,status='REFERENCE_VALIDATED',source_identity=identity,source_sha=expected['source_sha'],
        result_sha=digest(reference),AIDC_anchor=reference['aidc_anchor'],reference_service_obligations_validated=True,
        FULL_optimization_claimed=False,P2_calls=0)
    rr['acceptance_sha']=digest(rr)
    write(root/'REFERENCE_RESULT.json',reference);write(root/'REFERENCE_ACCEPTANCE.json',rr)
    service_ids=sites+[f'STA{n:02d}' for n in range(1,13)]
    route=root/'ROUTES.json.gz';route.parent.mkdir(parents=True,exist_ok=True)
    route.write_bytes(gzip.compress(json.dumps({'routes':[],'service_ids':service_ids}).encode(),mtime=0))
    native=dict(day=day,capacities=caps,route_table=file_record(route),traffic_forecast_sha=digest('traffic'),
        initial_MESS_sites={f'MESS{n:02d}':sites[n-1] for n in range(1,5)},
        battery=dict(minimum=0.,maximum=100.,initial=50.,terminal=50.,p_limit=10.,pcs_kva=10.,eta_charge=1.,eta_discharge=1.))
    native_record=write(root/'NATIVE_INPUT.json',native);off=initial_mess(native)
    parent_payload=dict(native_source=native_record)
    case_derivation['parent_case']=digest(parent_payload)
    identity['case_sha']=digest(case_derivation)
    reference['source_identity']=identity
    reference['reference_artifact_sha']=digest({k:v for k,v in reference.items() if k!='reference_artifact_sha'})
    rr.update(source_identity=identity,result_sha=digest(reference))
    rr['acceptance_sha']=digest({k:v for k,v in rr.items() if k!='acceptance_sha'})
    write(root/'REFERENCE_RESULT.json',reference);write(root/'REFERENCE_ACCEPTANCE.json',rr)
    audit=dict(a_input_sha=digest('full-flex-input'),backlog_contract_sha=digest('backlog'))
    manifest=dict(day=day,identity=identity,source_sha=expected['source_sha'],source_native_record=native_record,
        full_flex_input_sha=audit['a_input_sha'],science_derivation=science_derivation,case_derivation=case_derivation,
        source_freeze={'files':sources,'source_sha':expected['source_sha']},initial_record=initial)
    manifest['parent_basic_manifest']=dict(source_native_record=native_record,case_payload=parent_payload,
        identity={'case_sha':digest(parent_payload)})
    write(root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',manifest)
    write(root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_INPUT_AUDIT.json',audit)
    folder=root/arm;stages={}
    def a_stage(stage, fixed, parent=None):
        point=np.array([.6,1.]);sha=vector_sha(point)
        binding=dict(rows=7,columns=2,objective_sense=1)
        full=dict(PASS=True,FULL_max_residual=0.,point_sha256=sha,rows=7,columns=2)
        result={k:deepcopy(reference[k]) for k in ANCHOR_FIELDS}
        result['AIDC_P_by_site'][sites[0]]=[1.]*96
        result.update(stage=stage,arm=arm,case_sha=digest(dict(parent=identity['case_sha'],stage=stage,
            input_MESS_anchor=fixed,backlog_contract=audit['backlog_contract_sha'])),source_identity=identity,
            D0_input_sha=audit['a_input_sha'],input_MESS_anchor=fixed,FULL_feasible=True,FULL_point_replay=full,
            native_binding=binding,P2_calls=0)
        result['aidc_anchor']=digest({k:result[k] for k in ANCHOR_FIELDS})
        receipt=dict(schema=A_SCHEMA,status='FULL_PASS',stage=stage,arm=arm,stage_case_sha=result['case_sha'],
            source_identity=identity,source_sha=expected['source_sha'],D0_input_sha=audit['a_input_sha'],
            AIDC_anchor=result['aidc_anchor'],MESS_anchor=fixed,result_sha=digest(result),native_binding=binding,
            point_sha256=sha,Original_FULL=full,P1_only=True,P2_calls=0,P2_optimized=False,fixture=False,
            evidence_scope='REAL_PRODUCTION',parent_acceptance_sha=None if parent is None else parent['acceptance_sha'])
        receipt['acceptance_sha']=digest(receipt)
        write(folder/stage/'P1_ONLY_RESULT.json',result);write(folder/stage/'P1_ONLY_ACCEPTANCE.json',receipt)
        np.savez_compressed(folder/stage/'P1_ONLY_POINT.npz',point=point)
        stages[stage]=dict(result=result,acceptance=receipt)
        return result,receipt
    def m_stage(stage,aidc,parent):
        point=np.array([.6]);sha=vector_sha(point)
        current=dict(day=day,arm=arm,stage=stage,science_sha=identity['science_sha'],
            D0_source_sha=expected['source_sha'],D0_parent_case_sha=identity['case_sha'],aidc_anchor=aidc['aidc_anchor'],
            **{key:digest(stage+key) for key in ('original_matrix_sha','original_domain_sha','selected_matrix_sha','selected_domain_sha')})
        case_sha=digest(current)
        write(folder/stage/'SCIENTIFIC_CASE_IDENTITY.json',dict(current,case_sha=case_sha))
        raw=folder/stage/'RAW.npz';np.savez_compressed(raw,point=point)
        full=dict(PASS=True,strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            original_matrix_and_96_slot_physical_replay={'PASS':True,'case_sha':case_sha},
            point_path=str(raw.resolve()),point_file_sha256=file_record(raw)['sha256'],point_vector_sha256=sha)
        replay=write(folder/stage/'RAW.REPLAY.json',full)
        plan={k:deepcopy(v) for k,v in off.items() if k!='plan_sha'}
        plan.update(case_sha=case_sha,point_vector_sha256=sha,MESS_control='ON')
        plan['plan_sha']=digest(plan)
        result=dict(day=day,arm=arm,stage=stage,case_sha=case_sha,FULL_validated=True,P2_calls=0,mess=plan,
            D0_source_identity=identity,D0_fixed_AIDC_anchor=aidc['aidc_anchor'],binding=dict(aidc_anchor=aidc['aidc_anchor'],
                **{key:current[key] for key in ('original_matrix_sha','original_domain_sha','selected_matrix_sha','selected_domain_sha')}))
        receipt=dict(schema='TABLE_V_M_P1_FULL_ACCEPTANCE_V1',status='FULL_PASS',arm=arm,stage=stage,
            stage_case_sha=case_sha,source_identity=identity,source_sha=expected['source_sha'],result_sha=digest(result),
            P1_only=True,P2_calls=0,P2_optimized=False,fixture=False,evidence_scope='REAL_PRODUCTION',
            AIDC_anchor=aidc['aidc_anchor'],MESS_anchor=plan['plan_sha'],Original_FULL=full,
            raw_point=file_record(raw),raw_replay=replay,parent_acceptance_sha=parent['acceptance_sha'])
        receipt['acceptance_sha']=digest(receipt)
        write(folder/stage/'TABLE_V_M_RESULT.json',result);write(folder/stage/'TABLE_V_M_ACCEPTANCE.json',receipt)
        stages[stage]=dict(result=result,acceptance=receipt)
        return result,receipt
    aidc,aa,m,ma,mess=reference,rr,None,None,off
    if arm in ('B1','B3'):aidc,aa=a_stage('A1',off['plan_sha'])
    if arm in ('B2','B3'):m,ma=m_stage('M1',aidc,aa);mess=m['mess']
    if arm=='B3':aidc,aa=a_stage('A2',mess['plan_sha'],ma);m,ma=m_stage('M2',aidc,aa);mess=m['mess']
    write(folder/'PLANNING_STAGE_RESULTS.json',stages)
    policy=(REFERENCE_POLICY if arm in ('B0','B2') else dict(arm=arm,policy=static_policy,R2='HOLD',
        MESS_plan_sha=mess['plan_sha'],command_sha=digest({})))
    payload=dict(schema='TABLE_V_ACTUAL_EVALUATION_CASE_V1' if arm in ('B0','B2') else 'TABLE_V_FULL_FLEX_ACTUAL_EVALUATION_CASE_V1',
        day=day,arm=arm,source_identity=identity,source_sha=expected['source_sha'],initial_state_sha=identity['initial_state_sha'],
        reference_result_sha=digest(reference),reference_acceptance_sha=digest(rr),A_result_sha=digest(aidc),
        A_acceptance_sha=aa['acceptance_sha'],M_result_sha=None if m is None else digest(m),
        M_acceptance_sha=None if ma is None else ma['acceptance_sha'],AIDC_anchor=aidc['aidc_anchor'],MESS_plan_sha=mess['plan_sha'],
        final_AIDC_stage='REFERENCE' if arm in ('B0','B2') else 'A1' if arm=='B1' else 'A2',
        final_MESS_stage='OFF' if arm in ('B0','B1') else 'M1' if arm=='B2' else 'M2',
        slots=slots,clock_contract=CONTRACT,policy=policy,policy_sha=digest(policy))
    if arm in ('B1','B3'):payload.update(actual_policy=policy,actual_policy_sha=digest(policy))
    trace=folder/'ACTUAL96/ACTUAL_OCCUPANCY_POWER_TRACE.npz';trace.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(trace,sites=sites,timestamps_start_epoch_seconds=begin+np.arange(slots)*900,
        GPU=np.zeros((slots,12)),compute_GPU=np.zeros((slots,12)),IT_kw=np.zeros((slots,12)),PCC_P_kw=np.zeros((slots,12)),
        PCC_Q_kvar=np.zeros((slots,12)),authority_sha='NAMED_PHYSICAL_FIXTURE',IT_recomputed_from_actual_occupation=True)
    actual=dict(schema='TABLE_V_ACTUAL_EXECUTION_V1',fixture=False,Actual_stage_PASS=True,status='FULL_PASS',
        day=day,arm=arm,source_identity=identity,source_sha=expected['source_sha'],initial_state_sha=identity['initial_state_sha'],
        evaluation_case_payload=payload,evaluation_case_sha=digest(payload),AIDC_anchor=aidc['aidc_anchor'],
        MESS_plan_sha=mess['plan_sha'],policy_sha=digest(policy),executed_actual_slots=slots,actual_trace=file_record(trace),Gate_contract=CONTRACT)
    raw_receipt,rows=physical_fixture(slots)
    raw_receipt.update(day=day,evaluation_case_sha=actual['evaluation_case_sha'],common_initial_state_sha=identity['initial_state_sha'],
        MESS_plan_sha=mess['plan_sha'],actual_power_trace=file_record(trace))
    for row in rows:
        row.update(MESS_plan_sha=mess['plan_sha'],PCC_P_kw=[0.]*12,PCC_Q_kvar=[0.]*12)
        row['clock']['day']=day
    raw=write(folder/'FRESH_AC96/FRESH_PHYSICAL_RESULT.json',raw_receipt)
    row_record=write(folder/'FRESH_AC96/FRESH_PHYSICAL_SLOTS.json',rows)
    certificate=validate_settled_fresh(raw_receipt,rows,day=day,case_sha=actual['evaluation_case_sha'],
        initial_state_sha=identity['initial_state_sha'],mess_plan_sha=mess['plan_sha'],trace_record=file_record(trace),slots=slots)
    fresh=dict(status='FULL_PASS',arm=arm,executed_slots=slots,official_contract=CONTRACT,official_certificate=certificate,
        raw_receipt=raw,raw_slot_rows=row_record)
    save_chain(folder,actual,fresh)
    return folder,expected,digest(policy),actual,fresh


def save_chain(folder,actual,fresh):
    actual_record=write(folder/'ACTUAL96/TABLE_V_ACTUAL_EXECUTION.json',actual)
    fresh['actual_record']=actual_record
    fresh_record=write(folder/'FRESH_AC96/TABLE_V_SETTLED_FRESH.json',fresh)
    aw=dict(status='FULL_PASS',result=actual,raw_records=[actual_record,actual['actual_trace']])
    fw=dict(status='FULL_PASS',result=fresh,raw_records=[fresh_record])
    write(folder/'ACTUAL_RESULT.json',aw);write(folder/'FRESH_AC_RESULT.json',fw)
    return write(folder/'ARM_OUTCOME.json',dict(status='FULL_PASS',day=actual['day'],arm=actual['arm'],
        executed_actual_slots=actual['executed_actual_slots'],executed_fresh_slots=fresh['executed_slots'],actual=aw,fresh=fw))


@pytest.mark.parametrize('arm',['B0','B1','B2','B3'])
def test_current_complete_ancestry_and_original_settled96_pass_native0(tmp_path,monkeypatch,arm):
    import gurobipy as gp
    monkeypatch.setattr(gp.Model,'__init__',lambda *args,**kwargs:pytest.fail('native model built'))
    folder,expected,policy,_,_=fixture(tmp_path,arm)
    cert=validate_arm_full96(file_record(folder/'ARM_OUTCOME.json'),expected,arm,expected_policy_sha=policy)
    assert cert['status']=='PASS' and cert['official_Full96'] and not cert['old_PR223_PASS_transferred']


@pytest.mark.parametrize('mutation',['science','case','source','policy','AIDC_anchor','MESS_plan_sha','A_result_sha',
    'M_result_sha','missing-ancestor','old-PR223','false-physical-header','trace-bytes','physical-row','applied-PQ'])
def test_header_resealing_cannot_promote_old_or_tampered_evidence(tmp_path,mutation):
    folder,expected,policy,actual,fresh=fixture(tmp_path,'B3')
    payload=actual['evaluation_case_payload']
    if mutation in ('science','case'):
        payload['source_identity']=dict(payload['source_identity'],**{mutation+'_sha':digest('OLD')})
    elif mutation=='source':payload['source_sha']=digest('OLD')
    elif mutation=='policy':payload['policy_sha']=digest('UNAPPROVED')
    elif mutation in ('AIDC_anchor','MESS_plan_sha','A_result_sha','M_result_sha'):payload[mutation]=digest('FORGED')
    elif mutation=='missing-ancestor':payload.pop('M_acceptance_sha')
    elif mutation=='old-PR223':payload['schema']='PR223_HISTORICAL_PASS'
    elif mutation=='false-physical-header':actual['Actual_stage_PASS']=False
    elif mutation=='trace-bytes':
        with Path(actual['actual_trace']['path']).open('ab') as stream:stream.write(b'ALTERED')
    elif mutation in ('physical-row','applied-PQ'):
        path=Path(fresh['raw_slot_rows']['path']);rows=json.loads(path.read_text())
        if mutation=='physical-row':rows[8]['physical']['nodes'][0]['voltage_pu']=.9
        else:rows[8]['PCC_P_kw'][0]=12.
        fresh['raw_slot_rows']=write(path,rows)
    actual['evaluation_case_sha']=digest(payload)
    record=save_chain(folder,actual,fresh)
    with pytest.raises((ValueError,KeyError,PermissionError)):
        validate_arm_full96(record,expected,'B3',expected_policy_sha=policy)


@pytest.mark.parametrize('stage,field',[('A2','AIDC_P_by_site'),('M2','Q_by_site')])
def test_final_stage_header_cannot_hide_changed_plan_values(tmp_path,stage,field):
    folder,expected,policy,_,_=fixture(tmp_path,'B3')
    stages=json.loads((folder/'PLANNING_STAGE_RESULTS.json').read_text())
    result=stages[stage]['result']
    target=result if stage.startswith('A') else result['mess']
    target[field]['AIDC01'][0]+=1.
    name='P1_ONLY_RESULT.json' if stage.startswith('A') else 'TABLE_V_M_RESULT.json'
    write(folder/stage/name,result);write(folder/'PLANNING_STAGE_RESULTS.json',stages)
    with pytest.raises(ValueError):
        validate_arm_full96(file_record(folder/'ARM_OUTCOME.json'),expected,'B3',expected_policy_sha=policy)


def test_b2_missing_reference_original_source_authority_is_not_accepted(tmp_path):
    folder,expected,policy,_,_=fixture(tmp_path,'B2')
    reference=json.loads((tmp_path/'REFERENCE_RESULT.json').read_text())
    receipt=json.loads((tmp_path/'REFERENCE_ACCEPTANCE.json').read_text())
    reference['reference_sources']=[]
    reference['reference_artifact_sha']=digest({k:v for k,v in reference.items() if k!='reference_artifact_sha'})
    receipt['result_sha']=digest(reference)
    receipt['acceptance_sha']=digest({k:v for k,v in receipt.items() if k!='acceptance_sha'})
    write(tmp_path/'REFERENCE_RESULT.json',reference);write(tmp_path/'REFERENCE_ACCEPTANCE.json',receipt)
    with pytest.raises(ValueError,match='ORIGINAL_REFERENCE_SOURCE_AUTHORITY'):
        validate_arm_full96(file_record(folder/'ARM_OUTCOME.json'),expected,'B2',expected_policy_sha=policy)


def test_approved_whole_policy_cannot_change_the_frozen_e1_policy(tmp_path):
    folder,expected,_,actual,fresh=fixture(tmp_path,'B1')
    payload=actual['evaluation_case_payload']
    payload['policy']['policy']['participation']='ALL_UIDS'
    payload['actual_policy']=payload['policy']
    approved=digest(payload['policy']);payload['policy_sha']=payload['actual_policy_sha']=approved
    actual['policy_sha']=approved;actual['evaluation_case_sha']=digest(payload)
    with pytest.raises(ValueError,match='CURRENT_FULL_FLEX_POLICY'):
        validate_arm_full96(save_chain(folder,actual,fresh),expected,'B1',expected_policy_sha=approved)


def test_binary_evidence_is_not_sent_to_the_json_reader(tmp_path):
    from v42_integration.table_v_launch_evidence import _json
    raw=tmp_path/'RAW.npz';np.savez_compressed(raw,point=np.array([1.]))
    with pytest.raises(ValueError,match='JSON_READER_REJECTS_BINARY'):
        _json(None,record=file_record(raw))


@pytest.mark.parametrize('day',['2025-05-02','2025-05-10','2025-05-12'])
def test_representative_canary_has_real_raw_prefix_scope_and_cannot_be_full96(tmp_path,day):
    folder,expected,policy,_,_=fixture(tmp_path,'B3',day=day,slots=16)
    record=file_record(folder/'ARM_OUTCOME.json')
    cert=validate_arm_canary16(record,expected,'B3',expected_policy_sha=policy)
    assert cert['status']=='PASS' and cert['slots']==16 and not cert['official_Full96']
    with pytest.raises(ValueError):
        validate_arm_full96(record,expected,'B3',expected_policy_sha=policy)
