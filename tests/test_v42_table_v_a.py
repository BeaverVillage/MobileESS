"""Named A acceptance fixtures; no model builder or native method is called."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import vector_sha
from v42_integration.table_v_a import accept_current_a


def fixture_a():
    identity = dict(case_sha='new-e1-common-case', science_sha='new-full-flex-science')
    context = dict(manifest=dict(identity=identity, source_sha='new-source'),
        input_audit=dict(a_input_sha='new-full-e1-input'))
    case = SimpleNamespace(stage='A1', arm='B1', case_sha='new-a1-stage-case',
                           grid=SimpleNamespace(fixed_mess={'plan_sha': 'MESS-OFF'}))
    point = np.array([.25, .75], dtype=np.float64)
    full = dict(PASS=True, rows=5, columns=2, FULL_max_residual=1e-12,
                point_sha256=vector_sha(point))
    result = dict(stage='A1', arm='B1', case_sha=case.case_sha, source_identity=identity,
        D0_input_sha='new-full-e1-input', input_MESS_anchor='MESS-OFF', P2_calls=0,
        FULL_feasible=True, FULL_point_replay=deepcopy(full), objective=.6, bound=.6, gap=0.,
        selected_jobs={}, AIDC_P_by_site={}, AIDC_Q_by_site={}, CC4_service={},
        CC4_carryout={}, anonymous_resource_envelope=[])
    keys = ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
    result['aidc_anchor'] = digest({key: result[key] for key in keys})
    binding = dict(rows=5, columns=2, objective_sense=1)
    result['native_binding'] = deepcopy(binding)
    return context, case, point, full, result, binding


def accept(values):
    context, case, point, full, result, binding = values
    return accept_current_a(result, context=context, case=case, binding=binding, point=point, full=full)


def test_current_full_e1_numeric_closure_is_not_unpriced_joint_certificate():
    receipt = accept(fixture_a())
    assert receipt['status'] == 'FULL_PASS'
    assert receipt['domain_scope'] == 'ORIGINAL_SOURCE_AUTHORIZED_E1_FLEX30_FULL_DOMAIN'
    assert receipt['native_matrix_target_met'] is True
    assert receipt['whole_original_unpriced_domain_global_optimality'] is False
    assert receipt['AIDC_MESS_joint_Global_LB'] is None and receipt['K48_Global_LB'] is None
    assert receipt['P2_calls'] == 0 and receipt['P2_optimized'] is False


def test_missed_a_optimality_target_does_not_remove_full_feasible_handoff():
    values = fixture_a(); values[4]['gap'] = .2
    receipt = accept(values)
    assert receipt['status'] == 'FULL_PASS'
    assert receipt['optimality_status'] == 'OPTIMALITY_TARGET_UNMET'


@pytest.mark.parametrize('field,value', [('stage','A2'), ('arm','B3'), ('case_sha','old-basic-a1'),
    ('source_identity',{'case_sha':'old-basic-case'}), ('D0_input_sha','old-input'),
    ('input_MESS_anchor','historical-M2')])
def test_result_cannot_be_relabelled_current_e1_or_another_arm(field, value):
    values = fixture_a(); values[4][field] = value
    with pytest.raises(ValueError): accept(values)


def test_point_and_full_certificate_must_be_for_the_literal_native_point():
    values = fixture_a(); values[2][0] += .01
    with pytest.raises(ValueError): accept(values)


def test_p2_result_is_rejected_even_if_p1_full_point_passes():
    values = fixture_a(); values[4]['P2_calls'] = 1
    with pytest.raises(ValueError, match='P2'): accept(values)


def test_result_false_full_replay_cannot_hide_behind_separate_true_certificate():
    values = fixture_a(); values[4]['FULL_point_replay']['PASS'] = False
    with pytest.raises(ValueError): accept(values)
