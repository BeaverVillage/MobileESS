from copy import deepcopy
from types import SimpleNamespace
import sys
import json
from contextlib import nullcontext
import numpy as np

import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record, vector_sha
from v42_integration.table_v_mess import (
    AIDC_KEYS, REFERENCE_SCHEMA, payload_for_m, require_aidc_anchor,
    require_build_admission, require_parent, require_m_acceptance, require_full_plan_axes)
from v42_integration.table_v_gap_contract import restricted_joint_diagnostic


@pytest.fixture(autouse=True)
def named_fixture_reference_producer(monkeypatch):
    """Only these algebra fixtures replace Source IO; production has no hook."""
    module = SimpleNamespace(require_reference_acceptance=lambda receipt, **kwargs: receipt)
    monkeypatch.setitem(sys.modules, 'v42_integration.table_v_reference', module)


def reference_fixture():
    sites = [f'IDC{i:02}' for i in range(12)]
    identity = dict(case_sha='current-e1-case', science_sha='e1-science')
    context = dict(manifest=dict(day='2025-05-01',identity=identity, source_sha='current-source'),
        data=[dict(capacities=dict.fromkeys(sites, 65), day='2025-05-01')],
        backlog=dict(contract_sha='cc4-current'))
    result = dict(selected_jobs={'known': dict(start=0)},
        AIDC_P_by_site={s: [float(i)]*96 for i, s in enumerate(sites)},
        AIDC_Q_by_site={s: [float(i)/10]*96 for i, s in enumerate(sites)},
        CC4_service={'gpuH': 100}, CC4_carryout={'gpuH': 20},
        anonymous_resource_envelope=[dict(slot=0, gpu=4)],
        reference_schedule_only=True, reference_FULL_optimization_not_claimed=True,
        FULL_feasible=False, P2_calls=0)
    result['aidc_anchor'] = digest({k: result[k] for k in AIDC_KEYS})
    receipt = dict(schema=REFERENCE_SCHEMA, status='REFERENCE_VALIDATED',
        source_identity=identity, source_sha='current-source', result_sha=digest(result),
        AIDC_anchor=result['aidc_anchor'], reference_service_obligations_validated=True,
        FULL_optimization_claimed=False, P2_calls=0)
    receipt['acceptance_sha'] = digest(receipt)
    return context, result, receipt


def test_reference_enters_original_m_payload_without_fake_a1_full():
    context, result, receipt = reference_fixture()
    payload = payload_for_m(context, 'B2', 'M1', result, receipt)
    assert result['FULL_feasible'] is False
    assert 'stage' not in result
    assert payload['identity']['reference_schedule_only'] is True
    assert payload['planning']['PCC_P_kw'][95] == list(map(float, range(12)))
    assert payload['planning']['PCC_Q_kvar'][0] == [i/10 for i in range(12)]
    assert payload['planning']['complete_AIDC_anchor'] == result['aidc_anchor']


@pytest.mark.parametrize('day',['2025-05-02','2025-05-31'])
def test_mess_payload_uses_current_date_and_rejects_other_day_native_bundle(day):
    context,result,receipt=reference_fixture()
    context['manifest']['day']=day;context['data'][0]['day']=day
    assert payload_for_m(context,'B2','M1',result,receipt)['identity']['day']==day
    context['data'][0]['day']='2025-05-01'
    with pytest.raises(ValueError,match='DATE_STATE_AND_NATIVE_SOURCE'):
        payload_for_m(context,'B2','M1',result,receipt)


@pytest.mark.parametrize('mutation', ['source', 'parent', 'pq', 'service', 'fake-full', 'p2'])
def test_reference_mismatches_and_fake_full_rejected(mutation):
    context, result, receipt = reference_fixture()
    if mutation == 'source': receipt['source_sha'] = 'historical-source'
    if mutation == 'parent': receipt['source_identity'] = {'case_sha': 'basic-case'}
    if mutation == 'pq': result['AIDC_Q_by_site']['IDC00'][20] = 99.
    if mutation == 'service': receipt['reference_service_obligations_validated'] = False
    if mutation == 'fake-full': receipt['FULL_optimization_claimed'] = True
    if mutation == 'p2': result['P2_calls'] = 1
    with pytest.raises(ValueError):
        require_parent(context, 'B2', 'M1', result, receipt)


def test_reference_not_transferred_to_b3_or_m2():
    context, result, receipt = reference_fixture()
    for arm, stage in [('B3', 'M1'), ('B2', 'M2'), ('B1', 'M1')]:
        with pytest.raises(ValueError): payload_for_m(context, arm, stage, result, receipt)


def test_all_twelve_sites_and_all_96_slots_required():
    context, result, _ = reference_fixture()
    sites = sorted(context['data'][0]['capacities'])
    result['AIDC_P_by_site']['IDC00'].pop()
    result['aidc_anchor'] = digest({k: result[k] for k in AIDC_KEYS})
    with pytest.raises(ValueError, match='96_SLOT'):
        require_aidc_anchor(result, sites)


def test_build_requires_matching_supervisor_arm_stage_serial_admission():
    good = dict(status='PASS', operation='CURRENT_M_NATIVE0_BUILD', arm='B2', stage='M1',
                concurrent_heavy_solver=False, supervisor_serial_window=True)
    require_build_admission(good, arm='B2', stage='M1')
    for key, value in [('arm', 'B3'), ('stage', 'M2'), ('supervisor_serial_window', False)]:
        bad = dict(good, **{key: value})
        with pytest.raises(ValueError): require_build_admission(bad, arm='B2', stage='M1')


def test_m_acceptance_full_feasible_is_independent_of_k48_optimality(tmp_path):
    raw = tmp_path/'RAW.npz'; point = np.array([1., .6])
    np.savez_compressed(raw, point=point)
    full = dict(PASS=True, strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha='stage-case'),
        point_path=str(raw),point_file_sha256=file_record(raw)['sha256'],point_vector_sha256=vector_sha(point))
    replay = tmp_path/'RAW.REPLAY.json'; replay.write_text(json.dumps(full),encoding='utf8')
    plan = dict(routes={},P_by_site={},Q_by_site={},SOC={},Mode={},case_sha='stage-case',point_vector_sha256=vector_sha(point))
    plan['plan_sha'] = digest(plan)
    result = dict(FULL_validated=True,case_sha='stage-case',stage='M1',arm='B2',mess=plan,
        D0_source_identity={'case_sha':'now'},D0_fixed_AIDC_anchor='aidc',binding={'aidc_anchor':'aidc'})
    receipt = dict(schema='TABLE_V_M_P1_FULL_ACCEPTANCE_V1', status='FULL_PASS',
        arm='B2', stage='M1', source_identity={'case_sha': 'now'}, result_sha=digest(result),
        P2_calls=0, P2_optimized=False, physical_evaluation_allowed=True,
        global_optimality_status='K48_TARGET_UNMET',stage_case_sha='stage-case',AIDC_anchor='aidc',
        MESS_anchor=plan['plan_sha'],Original_FULL=full,raw_point=file_record(raw),raw_replay=file_record(replay),
        evidence_scope='REAL_PRODUCTION',fixture=False)
    receipt['acceptance_sha'] = digest(receipt)
    require_m_acceptance(receipt, result=result, arm='B2', stage='M1')
    receipt['P2_calls'] = 1
    with pytest.raises(ValueError): require_m_acceptance(receipt, result=result)


def test_sta_injections_cannot_be_silently_dropped_from_mess_handoff():
    sites = [f'IDC{i:02}' for i in range(12)] + [f'STA{i:02}' for i in range(12)]
    units = [f'MESS{i:02}' for i in range(4)]
    case = SimpleNamespace(graph=(sites, dict.fromkeys(units, 'IDC00')))
    plan = dict(P_by_site={s: [0.]*96 for s in sites}, Q_by_site={s: [0.]*96 for s in sites},
        SOC={u: [100.]*97 for u in units}, Mode={u: [0.]*96 for u in units},
        routes={u: [0] for u in units})
    plan['P_by_site']['STA07'][20] = 25.
    require_full_plan_axes(case, plan)
    del plan['P_by_site']['STA07']
    with pytest.raises(ValueError, match='STA_PQ'):
        require_full_plan_axes(case, plan)


def test_restricted_joint_gap_is_diagnostic_and_its_solver_target_is_unchanged():
    from v42_integration.m_engine import APPROVED_JOINT_PARAMETERS
    row = restricted_joint_diagnostic(dict(native_call=dict(current_pool_ObjVal=.6,
        restricted_ObjBound_diagnostic=.599)))
    assert row['restricted_joint_relative_gap'] < .005
    assert row['restricted_joint_gap_target'] == APPROVED_JOINT_PARAMETERS['MIPGap'] == .005
    assert not row['restricted_joint_gap_is_global']
    assert restricted_joint_diagnostic({})['restricted_joint_relative_gap'] is None


@pytest.mark.parametrize('fail_after_copy',[False,True])
def test_native0_construction_copy_disposed_when_producer_scope_fails(fail_after_copy):
    from v42_may_campaign_native90.m_model import _captured_model_scope
    copied=[];events=[]
    model=SimpleNamespace(dispose=lambda:events.append('copy-disposed'))
    def construct():
        with _captured_model_scope(copied):
            copied.append(model)
            events.append('copy-created')
            if fail_after_copy:raise RuntimeError('producer scope exit failed')
            events.append('arrays-extracted')
    if fail_after_copy:
        with pytest.raises(RuntimeError,match='producer scope exit failed'):construct()
    else:construct()
    assert events[0]=='copy-created' and events[-1]=='copy-disposed'
    assert events.count('copy-disposed')==1


@pytest.mark.parametrize('day',['2025-05-01','2025-05-31'])
def test_k48_appends_assessment_link_without_rewriting_m_full_receipt(tmp_path, monkeypatch,day):
    from v42_integration import table_v_mess as adapter
    from v42_integration import table_v_k48 as k48
    factory = adapter.TableVMessStages.__new__(adapter.TableVMessStages)
    factory.budget = object()
    factory.manifest = dict(day=day,identity={'case_sha':'current-E1'}, source_sha='current-source')
    factory.context = dict(manifest=factory.manifest)
    monkeypatch.setattr(factory, '_context', lambda: None)
    monkeypatch.setattr(adapter, 'require_real_budget', lambda *args: None)
    monkeypatch.setattr(adapter, 'require_m_acceptance', lambda *args, **kwargs: None)
    source = dict(day=day,stage_case_sha='current-M1', arm='B2', stage='M1', aidc_anchor='fixed-A')
    case = SimpleNamespace(case_sha='current-M1', identity=dict(day=day,arm='B2',stage='M1',aidc_anchor='fixed-A'))
    result = dict(FULL_validated=True, BEST_GLOBAL_UB=.6)
    point = np.array([.6])
    receipt = dict(stage_case_sha='current-M1',AIDC_anchor='fixed-A',MESS_anchor='full-M',acceptance_sha='full-proof',
        Original_FULL=dict(point_vector_sha256=vector_sha(point)))
    before = deepcopy((result, receipt))
    raw = tmp_path/'TABLE_V_M_ACCEPTANCE.json'
    raw.write_text(json.dumps(receipt), encoding='utf8')
    raw_before = raw.read_bytes()
    def native0_result(case, point, budget, output):
        output.mkdir()
        summary = k48.summarize_current_k48(dict(source=source,K=16), dict(current_FULL_UB=.6),
            [dict(source=source,K=16,Global_LB=.57,numerical_global_bound_contract=True)])
        (output/'CURRENT_K48_RESULT.json').write_text(json.dumps(summary),encoding='utf8')
        return summary
    monkeypatch.setattr(k48, 'run_current_k48', native0_result)
    phases=[]
    def phase(*args,**kwargs):phases.append(kwargs);return nullcontext()
    budget = SimpleNamespace(bind_table_v_case=lambda **kwargs: None,
        arm_context=lambda *args: nullcontext(), phase=phase,
        capture_native_methods=lambda: nullcontext())
    output = tmp_path/'K48'
    summary = factory.execute_k48('B2','M1',case,result,receipt,point,k48_budget=budget,output=output,
        build_admission=dict(status='PASS',operation='CURRENT_K48_NATIVE_BUILD',arm='B2',stage='M1',
            supervisor_serial_window=True,concurrent_heavy_solver=False))
    assessment = json.loads((output/'TABLE_V_M_K48_ASSESSMENT.json').read_text(encoding='utf8'))
    assert assessment['parent_M_result_sha'] == digest(result)
    assert assessment['parent_M_acceptance_sha'] == receipt['acceptance_sha']
    assert assessment['K48_result'] == file_record(output/'CURRENT_K48_RESULT.json')
    assert assessment['global_gap_target'] == .03 and not assessment['global_gap_certified']
    assert assessment['day']==day and phases==[{'day':day}]
    assert assessment['physical_evaluation_allowed']
    assert summary['M_stage_assessment'] == assessment
    assert (result,receipt) == before and raw.read_bytes() == raw_before
    with pytest.raises(ValueError, match='SAME_ACCEPTED_FULL_INCUMBENT'):
        factory.execute_k48('B2','M1',case,result,receipt,np.array([.61]),k48_budget=budget,
            output=tmp_path/'DIFFERENT',build_admission=dict(status='PASS',operation='CURRENT_K48_NATIVE_BUILD',
                arm='B2',stage='M1',supervisor_serial_window=True,concurrent_heavy_solver=False))
