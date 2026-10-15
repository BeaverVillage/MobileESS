from copy import deepcopy
import pytest
from v42_integration.release_ac_contract import validate_settled_fresh,VIOLATIONS,CONTRACT,require_current_settled_evidence


def fixture(slots=96):
    receipt=dict(day='2025-05-01',evaluation_case_sha='CURRENT',common_initial_state_sha='INIT',
        MESS_plan_sha='CURRENT_M2',actual_power_trace={'sha256':'CURRENT_TRACE'},executed_actual_slots=slots,
        supplied_actual_trace_slots=slots,original_compiler_clock_SVR_and_measurement_reused=True,
        global_reoptimization=0,MESS_PQ_repair=0,full96_Actual_AC_established=slots==96,
        evidence_kind='REAL_DATA',status='PASS',PASS=True)
    rows=[]
    for slot in range(slots):
        physical=dict(all_original_and_added_axes_checked=True,native_NormalAmps_and_winding_kVA_unchanged=True,
            original_transformer_current_authority='COMPILED_NORMALAMPS_ONLY',PASS=True,
            nodes=[dict(node_phase='N.1',voltage_pu=1.)],
            currents=[dict(element='line.l1',terminal=1,phase=1,loading_pu=.6)],
            transformers=[dict(element='transformer.t',terminal=1,loading_pu=.6)],**{k:0 for k in VIOLATIONS})
        rows.append(dict(slot=slot,MESS_plan_sha='CURRENT_M2',PASS=True,physical=physical,
            SVR=dict(original_seven_AUTO=True,devices=[{}]*11,hardware_PASS=True,added_nodes_voltage_PASS=True),
            clock=dict(schema='V42_NATIVE_TIME_SLOT_V1',day='2025-05-01',namespace='ACTUAL',slot=slot,
                start_seconds=slot*900,end_seconds=(slot+1)*900,physical_elapsed_seconds=900,PASS=True,
                iteration_to_seconds_conversion=False,manual_tap_or_cap_actions=0,last_solve_seconds=slot*900+50,
                diagnostic_substep_voltage_min_pu=.92,diagnostic_substep_PASS=False)))
    return receipt,rows


def validate(r,rows,slots=96):
    return validate_settled_fresh(r,rows,day='2025-05-01',case_sha='CURRENT',initial_state_sha='INIT',
        mess_plan_sha='CURRENT_M2',trace_record={'sha256':'CURRENT_TRACE'},slots=slots)


def test_substep_diagnostic_fail_does_not_block_official_settled_pass():
    r,rows=fixture();result=validate(r,rows)
    assert result['status']=='PASS' and result['Gate_contract']==CONTRACT
    assert result['official_Full96'] and not result['continuous_time_voltage_safety_certified']


def test_historical_or_other_case_pass_cannot_transfer():
    r,rows=fixture();r['evaluation_case_sha']='PR223_HISTORICAL'
    with pytest.raises(ValueError,match='CURRENT_CASE'):
        validate(r,rows)


def test_16_slot_pass_cannot_be_promoted_to_96():
    r,rows=fixture(16)
    assert validate(r,rows,16)['official_Full96'] is False
    with pytest.raises(ValueError,match='FULL_SCOPE'):
        validate(r,rows)


def test_one_slot_voltage_failure_preserved_in_original_scope():
    r,rows=fixture();rows[23]['physical']['nodes'][0]['voltage_pu']=.94
    rows[23]['physical'].update(PASS=False,voltage_violation_cells=1);rows[23]['PASS']=False
    r.update(status='PHYSICAL_FAIL',PASS=False)
    result=validate(r,rows)
    assert result['status']=='PHYSICAL_FAIL' and result['failing_slots']==[23]


def test_false_summary_pass_and_missing_axes_rejected():
    r,rows=fixture();rows[4]['physical']['currents'][0]['loading_pu']=1.1
    with pytest.raises(ValueError,match='SUMMARY_STATUS'):
        validate(r,rows)
    r,rows=fixture();rows[4]['physical']['nodes']=[]
    with pytest.raises(ValueError,match='AXIS_DRIFT'):
        validate(r,rows)


def test_legacy_raw_pass_with_forged_current_header_is_not_gate(tmp_path):
    import json
    from v42_integration.m_engine import file_record
    r,_=fixture(16)
    p=tmp_path/'PR223_RAW_RESULT.json';p.write_text(json.dumps(r),encoding='utf8')
    with pytest.raises(ValueError,match='RAW_BODY_SOURCE_CASE'):
        require_current_settled_evidence(file_record(p),source_case=dict(day='2025-05-01',
            source_sha='CURRENT',source_identity={'initial_state_sha':'INIT'}),ancestors={},slots=16)


def evaluation_fixture(tmp_path):
    import json
    from v42_integration.m_engine import file_record
    from v42_integration.policy import digest
    from v42_integration.research_presite_contract import make_spec
    raw=tmp_path/'NAMED_SOURCE_ONLY.json';raw.write_text('NAMED_FIXTURE',encoding='utf8')
    spec=make_spec(scenario='R1',source_records=[file_record(raw)],native_wan_sha=digest({}),shared_sites=['A','B'])
    contract=tmp_path/'NAMED_R1_CONTRACT.json';contract.write_text(json.dumps(spec),encoding='utf8')
    source=dict(source_sha='PLANNING_SOURCE',source_identity=dict(case_sha='PLANNING_CASE',initial_state_sha='D0'))
    ancestors=dict(A2_result={'stage':'A2'},M2_result={'stage':'M2'},
        A2_acceptance={'acceptance_sha':'A2_FULL'},M2_acceptance={'acceptance_sha':'M2_FULL'})
    return source,ancestors,dict(mode='R1',variant='C1',research_contract=file_record(contract)),raw


def test_actual_science_and_scope_have_distinct_canonical_cases(tmp_path):
    from v42_integration.release_ac_contract import actual_evaluation_case_payload
    from v42_integration.policy import digest
    source,ancestors,policy,_=evaluation_fixture(tmp_path)
    original=deepcopy((source,ancestors,policy))
    payload16=actual_evaluation_case_payload(source,ancestors,policy,16)
    payload96=actual_evaluation_case_payload(source,ancestors,policy,96)
    c0=actual_evaluation_case_payload(source,ancestors,dict(policy,variant='C0'),16)
    strict=actual_evaluation_case_payload(source,ancestors,dict(mode='SOURCE_STRICT',variant='C1',research_contract=None),16)
    assert len({digest(payload16),digest(payload96),digest(c0),digest(strict),'PLANNING_CASE'})==5
    assert payload16['research_spec_sha'] and strict['research_spec_sha'] is None
    assert payload16['planning_identity']==source['source_identity']
    assert (source,ancestors,policy)==original


def test_research_contract_cannot_be_relabelled_or_raw_source_mutated(tmp_path):
    from v42_integration.release_ac_contract import actual_evaluation_case_payload
    source,ancestors,policy,raw=evaluation_fixture(tmp_path)
    with pytest.raises(ValueError,match='SCENARIO_OR_SOURCE_CONTRACT_DRIFT'):
        actual_evaluation_case_payload(source,ancestors,dict(policy,mode='R2'),16)
    raw.write_text('ALTERED_SOURCE',encoding='utf8')
    with pytest.raises(ValueError,match='SCENARIO_OR_SOURCE_CONTRACT_DRIFT'):
        actual_evaluation_case_payload(source,ancestors,policy,16)


def test_source_strict_cannot_silently_use_research_contract(tmp_path):
    from v42_integration.release_ac_contract import actual_evaluation_case_payload
    source,ancestors,policy,_=evaluation_fixture(tmp_path)
    with pytest.raises(ValueError,match='MUST_NOT_IMPORT_RESEARCH'):
        actual_evaluation_case_payload(source,ancestors,dict(policy,mode='SOURCE_STRICT'),16)
    with pytest.raises(ValueError,match='EXPLICIT_R1_R2_RESEARCH_CONTRACT'):
        actual_evaluation_case_payload(source,ancestors,dict(policy,research_contract=None),16)


def test_date_specific_research_contract_cannot_cross_planning_case(tmp_path):
    import json
    from pathlib import Path
    from v42_integration.m_engine import file_record
    from v42_integration.release_ac_contract import actual_evaluation_case_payload
    source,ancestors,policy,_=evaluation_fixture(tmp_path);source['day']='2025-05-02'
    path=Path(policy['research_contract']['path']);spec=json.loads(path.read_text(encoding='utf8'))
    spec['date_contract']=dict(day=source['day'],planning_identity=source['source_identity'],
        planning_source_sha=source['source_sha'],future_UID_roster_in_contract=False)
    path.write_text(json.dumps(spec),encoding='utf8');policy['research_contract']=file_record(path)
    assert actual_evaluation_case_payload(source,ancestors,policy,16)['research_spec_sha']
    with pytest.raises(ValueError,match='DATE_PLANNING_CONTRACT_DRIFT'):
        actual_evaluation_case_payload(dict(source,day='2025-05-03'),ancestors,policy,16)
