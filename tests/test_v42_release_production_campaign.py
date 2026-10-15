"""Named fixtures test serialization/return gates, never production physics."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from v42_integration.a_engine import digest
from v42_integration.release_production_campaign import (
    STAGES,PLANNING_STAGES,fixture_checkpoint_loop,preflight,production_sources,run_production,run_planning_p1,read,_validate_row)


@pytest.fixture(autouse=True)
def forbid_real_native_model_or_solver(monkeypatch):
    import gurobipy as gp
    attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append('REAL_NATIVE_MODEL_OR_SOLVER_ENTRY')
        raise AssertionError('NAMED_CHECKPOINT_FIXTURES_NATIVE0_ONLY')
    for name in ('__init__','optimize','presolve','computeIIS'):
        monkeypatch.setattr(gp.Model,name,forbidden)
    yield
    assert attempts==[]


def fixture_answer(day,stage,*,status='FULL_PASS'):
    return dict(status=status,result=dict(day=day,stage=stage,fixture=True),acceptance=None)


def test_date_failure_does_not_fabricate_tail_or_abort_later_date(tmp_path):
    calls=[]
    def dispatch(*,day,stage,**kwargs):
        calls.append((day,stage))
        return fixture_answer(day,stage,status='TIME_LIMIT_NO_FEASIBLE' if day=='2025-05-01' and stage=='M1' else 'FULL_PASS')
    reports=fixture_checkpoint_loop(dates=['2025-05-01','2025-05-02'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert reports[0]['status']=='TIME_LIMIT_NO_FEASIBLE' and reports[1]['status']=='FULL_PASS'
    first=read(tmp_path/'2025-05-01/DATE_LEDGER.json')
    assert all(not first['stages'][s]['executed'] and first['stages'][s]['status']=='NOT_RUN' for s in STAGES[3:])
    assert ('2025-05-01','A2') not in calls and ('2025-05-02','FRESH_AC') in calls


def test_missing_input_skips_all_solves_and_continues(tmp_path):
    def dispatch(*,day,stage,**kwargs):
        if day=='2025-05-02':raise FileNotFoundError('RAW_INPUT_UNAVAILABLE')
        return fixture_answer(day,stage)
    reports=fixture_checkpoint_loop(dates=['2025-05-02','2025-05-03'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert [x['status'] for x in reports]==['INPUT_UNAVAILABLE','FULL_PASS']


def test_resume_completed_stage_never_reexecutes_optimizer(tmp_path):
    count=[]
    def dispatch(*,day,stage,**kwargs):count.append(stage);return fixture_answer(day,stage)
    kwargs=dict(dates=['2025-05-01'],folder=tmp_path,dispatch=dispatch,evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    fixture_checkpoint_loop(**kwargs);before=list(count);restored=[]
    fixture_checkpoint_loop(**kwargs,restore=lambda d,s,r:restored.append(s))
    assert count==before and restored==list(STAGES)


def test_resume_source_or_authorization_identity_drift_rejected(tmp_path):
    kwargs=dict(dates=['2025-05-01'],folder=tmp_path,dispatch=lambda **k:fixture_answer(k['day'],k['stage']),
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    fixture_checkpoint_loop(**kwargs,identity={'source':'old','authorization':'one'})
    with pytest.raises(ValueError,match='SOURCE_PLAN_OR_AUTHORIZATION_DRIFT'):
        fixture_checkpoint_loop(**kwargs,identity={'source':'changed','authorization':'one'})


def test_result_sha_mutation_on_resume_blocks_tail_without_retry(tmp_path):
    calls=[]
    def dispatch(**k):calls.append(k['stage']);return fixture_answer(k['day'],k['stage'])
    kwargs=dict(dates=['2025-05-01'],folder=tmp_path,dispatch=dispatch,evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    fixture_checkpoint_loop(**kwargs);path=tmp_path/'2025-05-01/DATE_LEDGER.json';state=read(path)
    state['stages']['M1']['result']['changed']=True;path.write_text(json.dumps(state),encoding='utf-8')
    old=len(calls);reports=fixture_checkpoint_loop(**kwargs)
    assert reports[0]['status']=='NOT_CERTIFIED' and len(calls)==old
    assert 'RESULT_OR_P2_DRIFT' in read(path)['resume_error']


def test_raw_point_byte_tamper_detected_independently_of_result_json(tmp_path):
    from v42_integration.m_engine import file_record
    raw=tmp_path/'RAW_POINT.bin';raw.write_bytes(b'original-point')
    def dispatch(**k):return dict(fixture_answer(k['day'],k['stage']),raw_records=[file_record(raw)])
    kwargs=dict(dates=['2025-05-01'],folder=tmp_path/'run',dispatch=dispatch,evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    fixture_checkpoint_loop(**kwargs);raw.write_bytes(b'mutated-point')
    assert fixture_checkpoint_loop(**kwargs)[0]['status']=='NOT_CERTIFIED'


def test_interrupted_attempt_requires_reconciliation_not_automatic_retry(tmp_path):
    attempt=tmp_path/'2025-05-01/INPUT';attempt.mkdir(parents=True)
    (attempt/'ATTEMPT_STARTED.json').write_text('{}')
    def forbidden(**kwargs):raise AssertionError('must not re-enter unknown attempt')
    reports=fixture_checkpoint_loop(dates=['2025-05-01'],folder=tmp_path,dispatch=forbidden,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    state=read(tmp_path/'2025-05-01/DATE_LEDGER.json')
    assert reports[0]['status']=='NOT_CERTIFIED' and state['interruption'].endswith(':INPUT')
    assert all(s['status']=='NOT_RUN' for s in state['stages'].values())


def test_solver_exception_preserved_then_next_day_continues(tmp_path):
    def dispatch(**k):
        if k['day']=='2025-05-10' and k['stage']=='A2':raise RuntimeError('ORIGINAL_SOLVER_ERROR')
        return fixture_answer(k['day'],k['stage'])
    reports=fixture_checkpoint_loop(dates=['2025-05-10','2025-05-12'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert [x['status'] for x in reports]==['NOT_CERTIFIED','FULL_PASS']
    state=read(tmp_path/'2025-05-10/DATE_LEDGER.json')
    assert state['stages']['A2']['result']['raw_preserved']
    assert not state['stages']['M2']['executed']


def test_p2_counter_cannot_enter_a_stage_checkpoint(tmp_path):
    def dispatch(**k):return dict(fixture_answer(k['day'],k['stage']),P2_calls=1)
    reports=fixture_checkpoint_loop(dates=['2025-05-01'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert reports[0]['status']=='INPUT_UNAVAILABLE'
    assert all(r['P2_calls']==0 for r in read(tmp_path/'2025-05-01/DATE_LEDGER.json')['stages'].values() if r['executed'])


def test_forged_next_stage_parent_sha_rejected():
    row=dict(stage='M1',day='2025-05-01',status='FULL_PASS',P2_calls=0,input_result_sha='wrong',result={})
    row['result_sha']=digest({})
    with pytest.raises(ValueError,match='PARENT_RESULT'):_validate_row(row,stage='M1',day='2025-05-01',parent_sha='expected')


def test_named_dummy_fixture_cannot_be_called_as_production(tmp_path):
    with pytest.raises(ValueError,match='DUMMY_ONLY_NAMED_FIXTURE'):
        fixture_checkpoint_loop(dates=[],folder=tmp_path,dispatch=lambda **k:{},evidence_scope='REAL_PRODUCTION')
    with pytest.raises(ValueError,match='DUMMY_EXECUTOR_FORBIDDEN'):
        run_production({},authorization={},gate={},folder=tmp_path,budget_ledger=tmp_path/'l.json',backend='DUMMY')
    with pytest.raises(ValueError,match='INJECTED_OR_DUMMY_EXECUTORS'):
        run_production({},authorization={},gate={},folder=tmp_path,budget_ledger=tmp_path/'l.json',executors={})


def test_no_new_stage_approval_fails_before_output_or_ledger_creation(tmp_path):
    with pytest.raises(PermissionError,match='NEW_EXPLICIT.*STAGE_BUDGET'):
        run_production({},authorization={'approved':False},gate={},folder=tmp_path/'run',budget_ledger=tmp_path/'l.json')
    assert not list(tmp_path.iterdir())


def test_preflight_exposes_settled_canary_and_k48_blockers():
    plan=dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',Worker=1,Threads=1,P2_calls=0,
        dates=['2025-05-01'],automatic_start=False,source_snapshot=production_sources())
    result=preflight(plan,{},dict(GateA_physical_time_voltage='FAIL'))
    assert 'ORIGINAL_SLOTTED_SETTLED_GATE_CONTRACT_REQUIRED' in result['blockers']
    assert 'GATE_A_PHYSICAL_TIME_VOLTAGE_NOT_PASS' not in result['blockers']
    assert 'CURRENT_CASE_K48_INCLUSION_AND_EXECUTOR_NOT_CERTIFIED' in result['blockers']
    assert result['Native_calls']==result['model_builds']==0
    assert not result['static_wiring_is_execution_certificate']


def settled_gate_fixture(tmp_path,monkeypatch):
    """Named readiness-only fixture; no production function is executed."""
    from types import SimpleNamespace
    from v42_integration import release_production_campaign as mod
    from v42_integration.m_engine import file_record
    monkeypatch.setattr(mod,'_actual_factory',lambda:SimpleNamespace(SUPPORTED_PRODUCTION_DAYS=['2025-05-01']))
    monkeypatch.setattr(mod.OriginalP1Stages,'execute_current_k48',lambda:None,raising=False)
    checkpoint,authority,ancestors=planning_checkpoint_fixture(tmp_path)
    auth=dict(schema='RELEASE_PRODUCTION_P1_SEPARATE_AUTHORIZATION_V1',approved=True,
        scope='NEW_RELEASE_P1_ONLY_HEAVY',P2_calls=0,Worker=1,Threads=1,
        human_approval_reference='NAMED_READINESS_FIXTURE_ONLY',authorization_id='NAMED_FIXTURE_ONLY',
        authorized_ledger_path=str(tmp_path/'NO_LEDGER_CREATED.json'),policy_sha='named-policy',
        stage_caps_seconds={'M1':1.,'A2':1.,'M2':1.,'K48_M2':1.},
        stage_cap_scope='PER_DATE_STAGE',return_reserve_seconds=30.,limit_seconds=34.,
        authorized_date_cases=[authority])
    plan=dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',Worker=1,Threads=1,P2_calls=0,
        dates=['2025-05-01'],automatic_start=False,source_snapshot=production_sources(),policy_sha='named-policy',
        planning_checkpoints={'2025-05-01':checkpoint})
    raw=settled_body_fixture(tmp_path,authority,ancestors)
    gate=dict(Gate_contract=mod.GATE_CONTRACT,May01_16slot_GPU_QoS_Fresh='PASS',
        settled_source_case=authority,planning_checkpoint=checkpoint,physical_evidence=raw,future_information_leak_count=0,
        actual_policy=dict(mode='SOURCE_STRICT',variant='C1',research_contract=None))
    return plan,auth,gate


def planning_checkpoint_fixture(tmp_path):
    """Synthetic M1/A2/M2 + real saved input/A1; no model or actual execution."""
    from v42_integration.release_p1_acceptance import saved_a1,accept_a,accept_m
    from v42_integration.m_engine import file_record,_write
    saved=saved_a1();identity=saved['manifest']['identity'];source=saved['manifest']['source_sha']
    authority=dict(day='2025-05-01',source_sha=source,source_identity=identity)
    def put(name,value):
        path=tmp_path/name;_write(path,value);return file_record(path)
    raw=put('NAMED_POINT_BYTES.json',dict(named_fixture=True))
    rows={};calls=[]
    def add(stage,result,acceptance=None,raws=None):
        parent=None if not rows else digest(rows[list(rows)[-1]]['result'])
        row=dict(day='2025-05-01',stage=stage,status='FULL_PASS',executed=True,P2_calls=0,input_result_sha=parent,
            result=result,result_sha=digest(result),raw_records=raws or [raw],acceptance=acceptance)
        if acceptance:row['acceptance_sha']=digest(acceptance)
        rows[stage]=row
    add('INPUT',dict(day='2025-05-01',identity=identity,source_sha=source,manifest_sha=saved['manifest']['manifest_sha'],
        initial_state_sha=identity['initial_state_sha'],input_sha=saved['input_audit']['a_input_sha']),raws=[saved['immutable_records'][5]])
    add('A1',saved['result'],saved['acceptance'],saved['immutable_records'])
    def native(stage,case,parent):
        row=dict(label='RELEASE_P1:'+stage+':NAMED_FIXTURE_ONLY',solver='GUROBI',charged_seconds=.1,
            Native_Runtime=.1,P2_call=False,stage_context=dict(day='2025-05-01',stage=stage,stage_case_sha=case,
                source_sha=source,parent_result_sha=digest(parent)),
            native_binding=dict(Threads=1,objective_sense=1,matrix_sha='named-matrix',domain_sha='named-domain'))
        calls.append(row);return row
    def m(stage,parent):
        case='NAMED_'+stage+'_CASE';plan=dict(routes={'u':[0]},P_by_site={'s':[0]},Q_by_site={'s':[0]},
            SOC={'u':[1,1]},Mode={'u':[0]},case_sha=case);plan['plan_sha']=digest(plan)
        result=dict(stage=stage,case_sha=case,FULL_validated=True,mess=plan,P2_calls=0,D0_source_identity=identity,
            D0_fixed_AIDC_anchor=parent['acceptance']['AIDC_anchor'],binding=dict(aidc_anchor=parent['acceptance']['AIDC_anchor']))
        cert=dict(PASS=True,original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case),
            strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True)
        receipt=accept_m(result,stage=stage,source_identity=identity,source_sha=source,parent_a=parent['acceptance'],
            parent_result=parent['result'],stage_case_sha=case,full_certificate=cert)
        native(stage,case,parent['result']);add(stage,result,receipt);rows[stage]['prepared_case']=raw
    m('M1',rows['A1'])
    case='NAMED_A2_CASE';full=dict(PASS=True,FULL_max_residual=0.,point_sha256='named-point',rows=1,columns=1)
    result=dict(stage='A2',case_sha=case,source_identity=identity,D0_input_sha=saved['input_audit']['a_input_sha'],
        input_MESS_anchor=rows['M1']['acceptance']['MESS_anchor'],FULL_feasible=True,FULL_point_replay=full,
        P2_calls=0,objective=.6,bound=.6,gap=0.,selected_jobs={'j':{'start':24}},AIDC_P_by_site={'s':[1.]},
        AIDC_Q_by_site={'s':[.2]},CC4_service={},CC4_carryout={},anonymous_resource_envelope=[])
    result['aidc_anchor']=digest({k:result[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site',
        'CC4_service','CC4_carryout','anonymous_resource_envelope')})
    result['Native_call']=native('A2',case,rows['M1']['result'])
    receipt=accept_a(result,stage='A2',stage_case_sha=case,source_identity=identity,source_sha=source,input_sha=saved['input_audit']['a_input_sha'],
        input_mess_anchor=result['input_MESS_anchor'],native_binding=dict(objective_sense=1,rows=1,columns=1),
        point_sha='named-point',original_full=full,parent_acceptance=rows['M1']['acceptance'])
    add('A2',result,receipt);m('M2',rows['A2'])
    old=[put('NAMED_HISTORICAL_ONE.json',{}),put('NAMED_HISTORICAL_TWO.json',{})]
    ledger=tmp_path/'NAMED_CONSUMED_PLANNING_NATIVE.json'
    approval=dict(schema='RELEASE_PRODUCTION_P1_SEPARATE_AUTHORIZATION_V1',approved=True,scope='NEW_RELEASE_P1_ONLY_HEAVY',
        P2_calls=0,Worker=1,Threads=1,human_approval_reference='NAMED_CHECKPOINT_FIXTURE_ONLY',policy_sha='named-policy',
        authorization_id='NAMED_CHECKPOINT_ONLY',authorized_ledger_path=str(ledger.resolve()),
        stage_caps_seconds=dict(M1=1.,A2=1.,M2=1.),stage_cap_scope='PER_DATE_STAGE',return_reserve_seconds=30.,
        limit_seconds=33.,authorized_date_cases=[authority])
    claim=put('NAMED_AUTHORIZATION_CLAIM.json',dict(authorization_sha=digest(approval),authorized_ledger_path=str(ledger.resolve())))
    budget=dict(authorization_document=approval,release_identity=dict(authorization_sha=digest(approval),
        historical_read_only=old,authorization_claim=claim),calls=calls,conservative_solve_seconds=.3,
        inflight=None,active_stage_context=None)
    budget_record=put(ledger.name,budget)
    state=dict(day='2025-05-01',status='FULL_PASS',evidence_scope='REAL_PRODUCTION',stages=rows,
        identity=dict(required_stages=list(PLANNING_STAGES),production_sources=production_sources(),historical_read_only=old,
            authorization_sha=digest(approval),native_budget_ledger_path=str(ledger.resolve())),completed_native_budget=budget_record)
    checkpoint=put('NAMED_COMPLETED_PLANNING_DATE_LEDGER.json',state)
    ancestors={stage+'_'+kind:rows[stage][kind] for stage in ('A2','M2') for kind in ('result','acceptance')}
    return checkpoint,authority,ancestors


def settled_body_fixture(tmp_path,authority,ancestors,slots=16):
    from v42_integration.release_ac_contract import (VIOLATIONS,validate_settled_fresh,EVIDENCE_SCHEMA,
        FULL96_EVIDENCE_SCHEMA,CONTRACT,actual_evaluation_case_payload)
    from v42_integration.m_engine import file_record,_write
    def put(name,value):
        path=tmp_path/name;_write(path,value);return file_record(path)
    ma=ancestors['M2_acceptance'];plan=ma['MESS_anchor'];identity=authority['source_identity'];source=authority['source_sha']
    policy=dict(mode='SOURCE_STRICT',variant='C1',research_contract=None)
    evaluation_payload=actual_evaluation_case_payload(authority,ancestors,policy,slots)
    evaluation_sha=digest(evaluation_payload)
    trace=put('NAMED_ACTUAL_TRACE_'+str(slots)+'.json',dict(named_fixture=True))
    fresh=dict(day='2025-05-01',evaluation_case_sha=evaluation_sha,common_initial_state_sha=identity['initial_state_sha'],
        MESS_plan_sha=plan,actual_power_trace=trace,executed_actual_slots=slots,supplied_actual_trace_slots=slots,
        original_compiler_clock_SVR_and_measurement_reused=True,global_reoptimization=0,MESS_PQ_repair=0,
        full96_Actual_AC_established=slots==96,evidence_kind='REAL_DATA',status='PASS',PASS=True)
    rows=[]
    for slot in range(slots):
        physical=dict(all_original_and_added_axes_checked=True,native_NormalAmps_and_winding_kVA_unchanged=True,
            original_transformer_current_authority='COMPILED_NORMALAMPS_ONLY',PASS=True,
            nodes=[dict(node_phase='N.1',voltage_pu=1.)],currents=[dict(element='line.l1',terminal=1,phase=1,loading_pu=.6)],
            transformers=[dict(element='transformer.t',terminal=1,loading_pu=.6)],**{k:0 for k in VIOLATIONS})
        rows.append(dict(slot=slot,MESS_plan_sha=plan,PASS=True,physical=physical,
            SVR=dict(original_seven_AUTO=True,devices=[{}]*11,hardware_PASS=True,added_nodes_voltage_PASS=True),
            clock=dict(schema='V42_NATIVE_TIME_SLOT_V1',day='2025-05-01',namespace='ACTUAL',slot=slot,start_seconds=slot*900,
                end_seconds=(slot+1)*900,physical_elapsed_seconds=900,PASS=True,iteration_to_seconds_conversion=False,
                manual_tap_or_cap_actions=0,last_solve_seconds=slot*900+50)))
    files=production_sources()
    freeze=put('NAMED_ACTUAL_SOURCE_'+str(slots)+'.json',dict(files=files,source_sha=digest(files),planning_identity=identity,planning_source_sha=source))
    hashes={key+'_sha':value['acceptance_sha'] if key.endswith('acceptance') else digest(value) for key,value in ancestors.items()}
    execution=dict(schema='RELEASE_PRODUCTION_ACTUAL_EXECUTION_V1',fixture=False,Actual_global_MILP_calls=0,
        private_Environment_identity_preserved=True,Original_event_driver_reused=True,source_identity=identity,source_sha=source,
        evaluation_case_sha=evaluation_sha,evaluation_case_payload=evaluation_payload,actual_policy=policy,research_contract=None,
        initial_state_sha=identity['initial_state_sha'],MESS_plan_sha=plan,
        actual_trace=trace,actual_specific_source_freeze=freeze,**hashes)
    body=dict(schema=EVIDENCE_SCHEMA if slots==16 else FULL96_EVIDENCE_SCHEMA,Gate_contract=CONTRACT,status='PASS',day='2025-05-01',
        source_identity=identity,source_sha=source,evaluation_case_sha=evaluation_sha,evaluation_case_payload=evaluation_payload,
        actual_policy=policy,research_contract=None,executed_actual_slots=slots,
        raw_fresh_receipt=put('NAMED_FRESH_'+str(slots)+'.json',fresh),raw_slot_rows=put('NAMED_ROWS_'+str(slots)+'.json',rows),
        raw_actual_trace=trace,raw_actual_execution_receipt=put('NAMED_EXECUTION_'+str(slots)+'.json',execution),
        official_certificate=validate_settled_fresh(fresh,rows,day='2025-05-01',case_sha=evaluation_sha,
            initial_state_sha=identity['initial_state_sha'],mess_plan_sha=plan,trace_record=trace,slots=slots),**hashes)
    body['canary_proof_sha' if slots==16 else 'full96_proof_sha']=digest(body)
    return put('NAMED_SETTLED_BODY_'+str(slots)+'.json',body)


def test_asof_substep_failure_cannot_veto_current_source_settled_canary(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    gate.update(GateA_physical_time_voltage='FAIL',ASOF_substep_diagnostic='FAIL')
    result=preflight(plan,auth,gate)
    assert result['blockers']==[]
    assert result['status']=='READY_TO_REQUEST_EXPLICIT_EXECUTION'
    assert result['Native_calls']==result['model_builds']==result['Actual_runs']==0
    assert not result['ASOF_substep_diagnostic_is_global_gate']
    assert not (tmp_path/'NO_LEDGER_CREATED.json').exists()


def test_historical_pr223_settled_pass_does_not_certify_current_d0(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    gate['settled_source_case']=dict(gate['settled_source_case'],source_identity={'case_sha':'historical-PR223'})
    assert 'CURRENT_D0_SETTLED_CANARY_SOURCE_CASE_BINDING_REQUIRED' in preflight(plan,auth,gate)['blockers']


def test_31day_requires_current_full96_settled_pass_without_circular_may01_gate(tmp_path,monkeypatch):
    from v42_integration import release_production_campaign as mod
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    assert 'MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED' not in preflight(plan,auth,gate)['blockers']
    plan['dates']=mod.may_dates()
    assert 'MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED' in preflight(plan,auth,gate)['blockers']
    gate['May01_integrated_Full96_Fresh']='PASS'
    assert 'MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED' not in preflight(plan,auth,gate)['blockers']


def test_settled_pass_never_bypasses_causality_or_raw_bytes(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    gate['future_information_leak_count']=1
    Path(gate['physical_evidence']['path']).write_text('mutated')
    blockers=preflight(plan,auth,gate)['blockers']
    assert 'CAUSAL_CONTROLLER_GATE_REQUIRED' in blockers and 'PHYSICAL_GATE_RAW_BYTES_DRIFT' in blockers


def test_historical_raw_fresh_file_cannot_be_relabelled_by_current_gate_header(tmp_path,monkeypatch):
    from v42_integration.m_engine import file_record
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    old=tmp_path/'PR223_HISTORICAL_FRESH.json'
    old.write_text(json.dumps(dict(status='PASS',PASS=True,evaluation_case_sha='historical-PR223')))
    gate['physical_evidence']=file_record(old)
    assert any(b.startswith('PHYSICAL_GATE_RAW_BODY_NOT_CERTIFIED:') for b in preflight(plan,auth,gate)['blockers'])


def test_resealed_body_cannot_replace_current_ancestor_with_old_mess_anchor(tmp_path,monkeypatch):
    from v42_integration.m_engine import file_record,_write
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    record=gate['physical_evidence'];body=read(record['path']);body['M2_acceptance_sha']='old-PR223'
    body['canary_proof_sha']=digest({k:v for k,v in body.items() if k!='canary_proof_sha'})
    _write(record['path'],body);gate['physical_evidence']=file_record(record['path'])
    assert any('ANCESTOR_CHAIN' in b for b in preflight(plan,auth,gate)['blockers'])


def test_actual_source_bytes_are_rechecked_after_current_header_and_valid_fresh(tmp_path,monkeypatch):
    from v42_integration.m_engine import file_record,_write
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    record=gate['physical_evidence'];body=read(record['path']);execution=read(body['raw_actual_execution_receipt']['path'])
    source_record=execution['actual_specific_source_freeze'];source=read(source_record['path'])
    source['files'][0]['sha256']='0'*64;source['source_sha']=digest(source['files']);_write(source_record['path'],source)
    execution['actual_specific_source_freeze']=file_record(source_record['path'])
    _write(body['raw_actual_execution_receipt']['path'],execution)
    body['raw_actual_execution_receipt']=file_record(body['raw_actual_execution_receipt']['path'])
    body['canary_proof_sha']=digest({k:v for k,v in body.items() if k!='canary_proof_sha'})
    _write(record['path'],body);gate['physical_evidence']=file_record(record['path'])
    assert any('SOURCE_BYTES_DRIFT' in b for b in preflight(plan,auth,gate)['blockers'])


def test_full31_pass_string_cannot_replace_current_raw_full96_proof(tmp_path,monkeypatch):
    from v42_integration import release_production_campaign as mod
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch);plan['dates']=mod.may_dates()
    gate['May01_integrated_Full96_Fresh']='PASS'
    assert 'CURRENT_D0_FULL96_SETTLED_RAW_EVIDENCE_REQUIRED' in preflight(plan,auth,gate)['blockers']
    gate['full96_evidence']=gate['physical_evidence']
    assert any(b.startswith('FULL96_SETTLED_RAW_BODY_NOT_CERTIFIED:') for b in preflight(plan,auth,gate)['blockers'])


def test_distinct_full96_schema_and_raw_rows_are_replayed(tmp_path):
    from v42_integration.release_ac_contract import require_current_settled_evidence
    _,authority,ancestors=planning_checkpoint_fixture(tmp_path)
    record=settled_body_fixture(tmp_path,authority,ancestors,slots=96)
    certificate=require_current_settled_evidence(record,source_case=authority,ancestors=ancestors,slots=96)
    assert certificate['status']=='PASS' and certificate['official_Full96'] and certificate['slots']==96


def test_resealed_historical_evaluation_case_cannot_replace_canonical_payload(tmp_path,monkeypatch):
    from v42_integration.m_engine import _write,file_record
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch);record=gate['physical_evidence'];body=read(record['path'])
    body['evaluation_case_sha']='historical-PR223-case'
    body['canary_proof_sha']=digest({k:v for k,v in body.items() if k!='canary_proof_sha'})
    _write(record['path'],body);gate['physical_evidence']=file_record(record['path'])
    assert any('CANONICAL_ACTUAL_EVALUATION_CASE' in b for b in preflight(plan,auth,gate)['blockers'])


def test_gate_actual_variant_must_match_raw_evaluation_policy(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    gate['actual_policy']['variant']='C0'
    assert any('EXPECTED_ACTUAL_POLICY_DRIFT' in b for b in preflight(plan,auth,gate)['blockers'])


def test_authenticated_import_exempts_only_completed_stages_from_new_caps(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    auth['stage_caps_seconds']={'K48_M2':1.}
    result=preflight(plan,auth,gate)
    assert result['blockers']==[] and result['verified_planning_import_dates']==['2025-05-01']
    plan['planning_checkpoints']={}
    assert 'REQUIRED_STAGE_BUDGET_CAPS_MISSING:A2,M1,M2' in preflight(plan,auth,gate)['blockers']


def test_completed_planning_checkpoint_authenticates_ancestors_without_models(tmp_path):
    from v42_integration.release_production_campaign import require_planning_checkpoint
    record,authority,ancestors=planning_checkpoint_fixture(tmp_path)
    result=require_planning_checkpoint(record,source_case=authority)
    assert result['ancestors']==ancestors and result['Native_calls']==result['model_builds']==0


def edit_checkpoint_budget(record,change):
    from v42_integration.m_engine import _write,file_record
    state=read(record['path']);budget_record=state['completed_native_budget'];budget=read(budget_record['path'])
    change(budget);_write(budget_record['path'],budget);state['completed_native_budget']=file_record(budget_record['path'])
    _write(record['path'],state);return file_record(record['path'])


@pytest.mark.parametrize('mutation,error',[
    (lambda b:b.update(inflight={'unknown_call':True}),'INFLIGHT_DRIFT'),
    (lambda b:b['calls'][0]['stage_context'].update(parent_result_sha='old-parent'),'PARENT_BINDING_DRIFT'),
    (lambda b:b['calls'][0]['native_binding'].update(Threads=2),'MODEL_BINDING_DRIFT'),
    (lambda b:b['calls'][0].update(Native_Runtime=100.),'RUNTIME_AND_CHARGE_DRIFT'),
    (lambda b:b.update(conservative_solve_seconds=.01),'TOTAL_COST_DRIFT')])
def test_import_does_not_bypass_consumed_native_ledger_checks(tmp_path,mutation,error):
    from v42_integration.release_production_campaign import require_planning_checkpoint
    record,authority,_=planning_checkpoint_fixture(tmp_path)
    record=edit_checkpoint_budget(record,mutation)
    with pytest.raises(ValueError,match=error):require_planning_checkpoint(record,source_case=authority)


def test_import_rechecks_raw_point_and_source_bytes(tmp_path):
    from v42_integration.release_production_campaign import require_planning_checkpoint
    record,authority,_=planning_checkpoint_fixture(tmp_path)
    state=read(record['path']);Path(state['stages']['M1']['raw_records'][0]['path']).write_text('changed raw point')
    with pytest.raises(ValueError,match='RAW_BYTES_DRIFT'):require_planning_checkpoint(record,source_case=authority)


def test_import_cannot_hide_missing_original_full_with_resealed_receipt(tmp_path):
    from v42_integration.release_production_campaign import require_planning_checkpoint
    from v42_integration.m_engine import _write,file_record
    record,authority,_=planning_checkpoint_fixture(tmp_path);state=read(record['path'])
    receipt=state['stages']['A2']['acceptance'];receipt['Original_FULL']['PASS']=False
    receipt['acceptance_sha']=digest({k:v for k,v in receipt.items() if k!='acceptance_sha'})
    state['stages']['A2']['acceptance_sha']=digest(receipt);_write(record['path'],state)
    with pytest.raises(ValueError,match='ORIGINAL_FULL_CERTIFICATE'):
        require_planning_checkpoint(file_record(record['path']),source_case=authority)


def test_imported_planning_stages_restore_without_a_second_dispatch(tmp_path):
    from v42_integration.release_production_campaign import require_planning_checkpoint,_seed_planning_import
    record,authority,_=planning_checkpoint_fixture(tmp_path);proof=require_planning_checkpoint(record,source_case=authority)
    identity=dict(named_fixture=True);folder=tmp_path/'NAMED_CONTINUATION';_seed_planning_import(folder,'2025-05-01',proof,identity)
    calls=[];restored=[]
    def dispatch(**k):calls.append(k['stage']);return fixture_answer(k['day'],k['stage'])
    fixture_checkpoint_loop(dates=['2025-05-01'],folder=folder,identity=identity,dispatch=dispatch,
        restore=lambda d,s,r:restored.append(s),evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert calls==list(STAGES[len(PLANNING_STAGES):])
    assert restored==list(PLANNING_STAGES)


def test_normal_a2_full_releases_large_m1_before_m2_preparation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import weakref
    from v42_integration import release_production_campaign as mod
    class NamedPayload:pass
    payload=NamedPayload();reference=weakref.ref(payload)
    budget=SimpleNamespace(authorization={'stage_caps_seconds':{'A2':1.}},bind_accepted_parent=lambda **k:None)
    dispatcher=mod._RealDispatcher({},budget,{})
    case=SimpleNamespace(case_sha='named-A2',output=tmp_path)
    def execute(*args,**kwargs):
        assert reference() is not None
        return {'named_fixture':True},{'named_fixture_acceptance':True}
    engine=SimpleNamespace(source_sha='named-source',identity={},prepare_a2=lambda *args:case,execute_a2=execute)
    dispatcher.contexts['2025-05-01']={};dispatcher.engines['2025-05-01']=engine
    dispatcher.cases['2025-05-01','M1']=payload;del payload
    monkeypatch.setattr(mod,'_build_admission',lambda *a,**k:{})
    dispatcher(day='2025-05-01',stage='A2',previous={'result':{},'acceptance':{}},output=tmp_path)
    assert reference() is None and ('2025-05-01','M1') not in dispatcher.cases


def test_release_day_clears_all_retained_collections_and_preserves_other_day():
    from v42_integration.release_production_campaign import _RealDispatcher
    import weakref
    class NamedPayload:pass
    d=_RealDispatcher({},None,{})
    first=NamedPayload();second=NamedPayload();old=weakref.ref(first);keep=weakref.ref(second)
    for values in (d.contexts,d.engines,d.results):values['2025-05-01']=first;values['2025-05-02']=second
    d.cases['2025-05-01','M1']=first;d.cases['2025-05-01','M2']=first;d.cases['2025-05-02','M1']=second
    del first,second;d.release_day('2025-05-01')
    assert old() is None and keep() is not None
    assert all('2025-05-01' not in values for values in (d.contexts,d.engines,d.results))
    assert set(d.cases)=={('2025-05-02','M1')}


@pytest.mark.parametrize('status',['FULL_PASS','NOT_CERTIFIED'])
def test_date_close_callback_runs_after_success_or_failure_before_next_date(tmp_path,status):
    closed=[]
    def dispatch(**k):
        if k['day']=='2025-05-02':assert closed==['2025-05-01']
        return fixture_answer(k['day'],k['stage'],status=status if k['stage']=='M1' else 'FULL_PASS')
    fixture_checkpoint_loop(dates=['2025-05-01','2025-05-02'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE',close_day=closed.append)
    assert closed==['2025-05-01','2025-05-02']


def test_date_close_callback_runs_after_restore_failure_or_identity_error(tmp_path):
    kwargs=dict(dates=['2025-05-01'],folder=tmp_path,dispatch=lambda **k:fixture_answer(k['day'],k['stage']),
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    fixture_checkpoint_loop(**kwargs);closed=[]
    def fail(*args):raise ValueError('NAMED_RESTORE_ERROR')
    fixture_checkpoint_loop(**kwargs,restore=fail,close_day=closed.append)
    assert closed==['2025-05-01']
    closed=[]
    with pytest.raises(ValueError,match='SOURCE_PLAN_OR_AUTHORIZATION_DRIFT'):
        fixture_checkpoint_loop(**kwargs,identity={'changed':True},close_day=closed.append)
    assert closed==['2025-05-01']


def test_reordered_full_month_cannot_bypass_full96_gate(tmp_path,monkeypatch):
    from v42_integration import release_production_campaign as mod
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    plan['dates']=list(reversed(mod.may_dates()))
    blockers=preflight(plan,auth,gate)['blockers']
    assert 'MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED' in blockers
    assert 'CURRENT_D0_FULL96_SETTLED_RAW_EVIDENCE_REQUIRED' in blockers


def test_dated_actual_policy_is_selected_without_requiring_daily_canary():
    from v42_integration.release_production_campaign import _RealDispatcher
    policies={'2025-05-01':{'mode':'R1','variant':'C1','research_contract':{'sha256':'may01'}},
        '2025-05-02':{'mode':'R1','variant':'C1','research_contract':{'sha256':'may02'}}}
    gate=dict(actual_policy=policies['2025-05-01'],full96_evidence={'sha256':'may01full96'},
        physical_evidence={'sha256':'may01canary16'})
    dispatcher=_RealDispatcher({'dates':list(policies),'Actual_policy_by_day':policies},None,gate)
    local=dispatcher._day_gate('2025-05-02')
    assert local['actual_policy']==policies['2025-05-02']
    assert local['may01_actual_policy']==policies['2025-05-01']
    assert local['full96_evidence']==gate['full96_evidence']
    assert 'physical_evidence_by_day' not in local
    local['actual_policy']['variant']='C0'
    assert gate['actual_policy']['variant']=='C1' and policies['2025-05-02']['variant']=='C1'


def test_full96_aliases_and_dated_policies_cannot_disagree():
    from v42_integration.release_production_campaign import _resolved_actual_gate
    errors=[]
    _resolved_actual_gate({'dates':['2025-05-01'],'Actual_policy_by_day':{'2025-05-01':{'mode':'R1'}}},
        {'actual_policy_by_day':{'2025-05-01':{'mode':'R2'}},'full96_evidence':{'sha256':'one'},
         'may01_full96_evidence':{'sha256':'different'}},errors)
    assert 'PLAN_AND_GATE_DATED_ACTUAL_POLICY_MAPPING_DRIFT' in errors
    assert 'MAY01_FULL96_EVIDENCE_ALIASES_MUST_MATCH' in errors


def test_other_date_launch_requires_prior_may01_full96_even_for_partial_campaign(tmp_path,monkeypatch):
    plan,auth,gate=settled_gate_fixture(tmp_path,monkeypatch)
    plan['dates']=['2025-05-02'];plan['planning_checkpoints']={}
    blockers=preflight(plan,auth,gate)['blockers']
    assert 'MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED' in blockers
    assert 'CURRENT_D0_FULL96_SETTLED_RAW_EVIDENCE_REQUIRED' in blockers


def test_explicit_policy_document_is_bound_by_bytes_and_content_hash(tmp_path,monkeypatch):
    from v42_integration.m_engine import file_record,_write
    plan,auth,_=settled_gate_fixture(tmp_path,monkeypatch);plan.pop('planning_checkpoints')
    policy=tmp_path/'NAMED_POLICY.json';_write(policy,{'named_policy_fixture':True})
    record=file_record(policy);plan['policy_record']=record;auth['policy_record']=record
    plan['policy_sha']=auth['policy_sha']=digest(read(policy))
    assert preflight(plan,auth,{},planning_only=True)['blockers']==[]
    _write(policy,{'changed':True})
    assert any(b.startswith('APPROVED_POLICY_DOCUMENT_BYTES_NOT_VERIFIED:')
        for b in preflight(plan,auth,{},planning_only=True)['blockers'])


def test_approved_plan_sha_rejects_later_plan_or_source_list_mutation(tmp_path,monkeypatch):
    plan,auth,_=settled_gate_fixture(tmp_path,monkeypatch);plan.pop('planning_checkpoints')
    auth['approved_plan_sha']=digest(plan)
    assert preflight(plan,auth,{},planning_only=True)['blockers']==[]
    plan['source_snapshot']=list(reversed(plan['source_snapshot']))
    assert 'APPROVAL_BOUND_EXACT_PLAN_SHA_DRIFT' in preflight(plan,auth,{},planning_only=True)['blockers']


def test_planning_native_has_no_circular_actual_fresh_or_k48_gate(tmp_path,monkeypatch):
    from v42_integration import release_production_campaign as mod
    plan,auth,_=settled_gate_fixture(tmp_path,monkeypatch)
    plan.pop('planning_checkpoints')
    del auth['stage_caps_seconds']['K48_M2']
    monkeypatch.setattr(mod,'_actual_factory',lambda:None)
    monkeypatch.delattr(mod.OriginalP1Stages,'execute_current_k48')
    result=preflight(plan,auth,{},planning_only=True)
    assert result['blockers']==[] and result['required_stages']==list(PLANNING_STAGES)
    assert result['K48_not_certified_does_not_block_planning']
    assert result['K48_current_case_Global_LB'] is None
    assert result['Actual_runs']==result['Native_calls']==result['model_builds']==0


def test_planning_still_requires_new_approval_before_any_output(tmp_path):
    with pytest.raises(PermissionError,match='NEW_EXPLICIT.*STAGE_BUDGET'):
        run_planning_p1({},authorization={'approved':False},folder=tmp_path/'run',budget_ledger=tmp_path/'ledger.json')
    assert not list(tmp_path.iterdir())


def test_planning_rejects_dummy_or_injected_executor(tmp_path):
    with pytest.raises(ValueError,match='DUMMY_EXECUTOR_FORBIDDEN'):
        run_planning_p1({},authorization={},folder=tmp_path,budget_ledger=tmp_path/'l.json',backend='DUMMY')
    with pytest.raises(ValueError,match='INJECTED_OR_DUMMY_EXECUTORS'):
        run_planning_p1({},authorization={},folder=tmp_path,budget_ledger=tmp_path/'l.json',executor=lambda:None)


def test_planning_checkpoint_never_dispatches_actual_fresh_or_k48(tmp_path):
    calls=[]
    def dispatch(**k):calls.append(k['stage']);return fixture_answer(k['day'],k['stage'])
    fixture_checkpoint_loop(dates=['2025-05-01'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE',planning_only=True)
    assert calls==list(PLANNING_STAGES)
    assert set(read(tmp_path/'2025-05-01/DATE_LEDGER.json')['stages'])==set(PLANNING_STAGES)


def test_planning_full_failure_blocks_a2_and_preserves_next_day(tmp_path):
    calls=[]
    def dispatch(**k):
        calls.append((k['day'],k['stage']))
        return fixture_answer(k['day'],k['stage'],status='NOT_CERTIFIED' if k['day']=='2025-05-01' and k['stage']=='M1' else 'FULL_PASS')
    rows=fixture_checkpoint_loop(dates=['2025-05-01','2025-05-02'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE',planning_only=True)
    assert [r['status'] for r in rows]==['NOT_CERTIFIED','FULL_PASS']
    assert ('2025-05-01','A2') not in calls and ('2025-05-02','M2') in calls
    assert not any(stage in ('K48_M2','ACTUAL','FRESH_AC') for _,stage in calls)


def test_positive_time_limits_are_not_authorization():
    result=preflight({},dict(approved=False,limit_seconds=900,stage_caps_seconds={'M1':180}),{})
    assert any('NEW_EXPLICIT' in b and 'STAGE_BUDGET' in b for b in result['blockers'])


def test_native_gap_target_unmet_and_physical_fail_remain_distinct(tmp_path):
    def dispatch(**k):return fixture_answer(k['day'],k['stage'],
        status=('OPTIMALITY_TARGET_UNMET' if k['day']=='2025-05-10' else 'PHYSICAL_FAIL') if k['stage']=='AUDIT' else 'FULL_PASS')
    reports=fixture_checkpoint_loop(dates=['2025-05-10','2025-05-12'],folder=tmp_path,dispatch=dispatch,
        evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert [x['status'] for x in reports]==['OPTIMALITY_TARGET_UNMET','PHYSICAL_FAIL']


def test_fixture_status_never_claimed_real_execution(tmp_path):
    fixture_checkpoint_loop(dates=['2025-05-01'],folder=tmp_path,
        dispatch=lambda **k:fixture_answer(k['day'],k['stage']),evidence_scope='NAMED_CHECKPOINT_FIXTURE')
    assert read(tmp_path/'2025-05-01/DATE_LEDGER.json')['evidence_scope']=='NAMED_CHECKPOINT_FIXTURE'
