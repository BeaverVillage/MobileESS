from copy import deepcopy
from types import SimpleNamespace
import sys
import json
import numpy as np

import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record, vector_sha
from v42_integration.table_v_mess import (
    AIDC_KEYS, REFERENCE_SCHEMA, payload_for_m, require_aidc_anchor,
    require_build_admission, require_parent, require_m_acceptance, require_full_plan_axes)


@pytest.fixture(autouse=True)
def named_fixture_reference_producer(monkeypatch):
    """Only these algebra fixtures replace Source IO; production has no hook."""
    module = SimpleNamespace(require_reference_acceptance=lambda receipt, **kwargs: receipt)
    monkeypatch.setitem(sys.modules, 'v42_integration.table_v_reference', module)


def reference_fixture():
    sites = [f'IDC{i:02}' for i in range(12)]
    identity = dict(case_sha='current-e1-case', science_sha='e1-science')
    context = dict(manifest=dict(identity=identity, source_sha='current-source'),
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
