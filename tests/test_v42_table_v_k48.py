"""Tiny algebra fixtures only; no Gurobi model or optimization is constructed."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_integration.a_engine import digest
from v42_integration.table_v_k48 import (
    _data, _matrix, exact_cut, identity, physical_axes, prepare_k16,
    verify_packet, append_cuts, separate, ORIGINAL_CALL_CAP, replay, summarize_current_k48)
from v42_integration.table_v_gap_contract import AIDC_GLOBAL_GAP_TARGET, MESS_GLOBAL_GAP_TARGET
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha


def source_fixture():
    names = np.array(['arc[MESS01,0]', 'charge_mode[MESS01,0]', 'SOC[MESS01,0]',
        'Pch[MESS01,IDC00,0]', 'Pdis[MESS01,IDC00,0]', 'Q[MESS01,IDC00,0]',
        'injection_P[IDC00,0]', 'response_P[0]', 'rho_max'])
    rows, sense, rhs, entries = [], [], [], []
    def add(name, terms, bound, s='<'):
        i = len(rows); rows.append(name); sense.append(s); rhs.append(bound)
        entries.extend((i, j, v) for j, v in terms.items())
    add('flow[MESS01,0]', {0: 1.}, 1., '=')
    add('SOC_limit[MESS01,0]', {2: 1.}, 1.)
    add('connected_Pch[MESS01,0]', {3: 1., 0: -1.}, 0.)
    add('injection_P_binding[IDC00,0]', {6: 1., 3: 1., 4: -1.}, 0., '=')
    add('response_P_binding[0]', {7: 1., 6: -.3, 5: -.1}, 0., '=')
    for slot in range(96):
        add(f'line_thermal_face[{slot},0,0]', {7: .1, 8: -1.}, -.6+slot*1e-4)
    ii, jj, vv = zip(*entries)
    A = sparse.coo_matrix((vv, (ii, jj)), shape=(len(rows), len(names))).tocsr()
    d = dict(names=names, lower=np.array([0, 0, 0, 0, 0, -1, -2, -2, 0.], float),
        upper=np.array([1, 1, 1, 1, 1, 1, 2, 2, 1.], float),
        objective=np.array([0]*8+[1.]), constant=np.array(0.),
        types=np.array(['B', 'B']+['C']*7), rhs=np.array(rhs), sense=np.array(sense), row_names=np.array(rows))
    x = np.array([1, 0, .5, 0, 0, 0, 0, 0, .6], float)
    ident = dict(day='2025-05-01',original_matrix_sha=matrix_sha(A), original_domain_sha=_domain_sha(d),
        D0_source_sha='current-source', D0_parent_case_sha='current-E1-common', arm='B2', stage='M1',
        aidc_anchor='current-reference-anchor')
    coeff = SimpleNamespace(node_names=('n1.1',), branch_names=('line.test::1',), transformer_ratings=(100.,))
    case = SimpleNamespace(original_A=A, original_d=d, identity=ident, case_sha=digest(ident),bundle=dict(day=ident['day']),
        lift=lambda y: y.copy(), coefficients=[coeff])
    return case, x


def test_current_full_k16_identity_projection_and_independent_geometry(tmp_path):
    case, x = source_fixture()
    packet, cert = prepare_k16(case, x, tmp_path/'K16')
    assert cert['PASS'] and cert['independent_original_geometry_replayed']
    assert cert['original_domain_projection_included']
    assert cert['original_FULL_start_replay']['raw_integer_pattern_exact']
    assert cert['K'] == 16 and cert['current_FULL_UB'] == .6
    assert packet['A'].shape == (19, 7)
    assert cert['historical_LB_or_UB_transferred'] is False
    assert cert['Native_optimize_calls'] == 0
    assert [c['original_row'] for c in packet['cuts']] == list(range(5, 21))


@pytest.mark.parametrize('mutation', ['grid-coefficient', 'physical-row', 'rhs', 'bound', 'type', 'objective', 'anchor', 'start'])
def test_source_or_packet_tampering_rejected(tmp_path, mutation):
    case, x = source_fixture(); packet, _ = prepare_k16(case, x, tmp_path/'K16')
    p = deepcopy(packet)
    if mutation == 'grid-coefficient': p['A'].data[-1] *= 1.01
    if mutation == 'physical-row': p['A'].data[0] = .9
    if mutation == 'rhs': p['d']['rhs'][-1] += .01
    if mutation == 'bound': p['d']['upper'][0] = .5
    if mutation == 'type': p['d']['types'][0] = 'C'
    if mutation == 'objective': p['d']['objective'][0] = 1
    if mutation == 'anchor': p['source']['aidc_anchor'] = 'old-M2-anchor'
    if mutation == 'start': p['start'][-1] = .1
    with pytest.raises(ValueError): verify_packet(case, p)


def test_original_selection_quotas_refill_and_nested_k32_k48(tmp_path):
    case, x = source_fixture(); packet, _ = prepare_k16(case, x, tmp_path/'K16')
    search = packet['start'].copy(); search[-1] = .1
    cuts, report = separate(case, packet, search)
    assert report['selected_count'] == 16 and report['exact_completeness_claim'] is False
    p32, cert = append_cuts(case, packet, cuts, tmp_path/'K32')
    assert cert['K'] == 32
    assert np.array_equal(packet['A'].toarray(), p32['A'][:packet['A'].shape[0]].toarray())
    cuts48, _ = separate(case, p32, search)
    _, cert48 = append_cuts(case, p32, cuts48, tmp_path/'K48')
    assert cert48['K'] == 48 and cert48['PASS']


def test_full_point_never_repaired_or_clipped(tmp_path):
    case, x = source_fixture(); x[0] = np.nextafter(1., 0.)
    with pytest.raises(ValueError, match='INTEGER_POINT'):
        prepare_k16(case, x, tmp_path/'K16')


def test_original_native_nominal_caps_not_invented_equal_splits():
    assert ORIGINAL_CALL_CAP == {16: 90., 32: 180., 48: 180.}


def test_historical_full_matrix_identity_not_accepted_by_string_only():
    case, _ = source_fixture(); case.identity['original_domain_sha'] = 'historical-domain'
    case.case_sha = digest(case.identity)
    with pytest.raises(ValueError, match='DOMAIN_DRIFT'): identity(case)


def test_k48_source_records_same_date_without_promoting_another_days_case():
    case,_=source_fixture()
    case.identity['day']='2025-05-31';case.bundle['day']='2025-05-31';case.case_sha=digest(case.identity)
    assert identity(case)['day']=='2025-05-31'
    case.bundle['day']='2025-05-01'
    with pytest.raises(ValueError,match='CURRENT_DATE_NATIVE_SOURCE'):
        identity(case)


def bound_result(source, k, lb, *, valid=True):
    return dict(source=source, K=k, Global_LB=lb, numerical_global_bound_contract=valid)


def test_mess_three_percent_and_prepared_k32_do_not_relabel_k16_bound():
    source = dict(stage_case_sha='current-M1', aidc_anchor='current-fixed-A')
    summary = summarize_current_k48(dict(source=source, K=32), dict(current_FULL_UB=.6),
        [bound_result(source, 16, .59)])
    assert AIDC_GLOBAL_GAP_TARGET == .005 and MESS_GLOBAL_GAP_TARGET == .03
    assert .005 < summary['relative_global_gap'] < .03
    assert summary['global_gap_certified'] and summary['optimality_status'] == 'TARGET_MET'
    assert summary['K_reached'] == 32 and summary['K_solved'] == 16
    assert summary['Global_LB_valid_K'] == [16] and summary['Global_LB_best_K'] == [16]
    assert summary['Global_LB_scope'] == 'CURRENT_ORIGINAL_FULL_WITH_FIXED_AIDC_ANCHOR'
    assert not summary['K48_completed'] and not summary['K48_Global_LB_valid']
    assert summary['K48_Global_LB'] is None


def test_k48_execution_and_k48_bound_validity_are_separate():
    source = dict(stage_case_sha='current-M1')
    summary = summarize_current_k48(dict(source=source, K=48), dict(current_FULL_UB=.6),
        [bound_result(source, 16, .58), bound_result(source, 32, .59),
         bound_result(source, 48, None, valid=False)])
    assert summary['K48_completed'] and summary['K48_cuts_reached']
    assert summary['K_solved'] == 48 and summary['Global_LB_valid_K'] == [16, 32]
    assert summary['Global_LB'] == .59 and not summary['K48_Global_LB_valid']


@pytest.mark.parametrize('history', [[], [dict(K=16, Global_LB=.6, numerical_global_bound_contract=False)]])
def test_missing_certified_lb_remains_null_and_full_actual_stays_allowed(history):
    source = dict(stage_case_sha='current-M1')
    rows = [dict(r, source=source) for r in history]
    summary = summarize_current_k48(dict(source=source, K=16), dict(current_FULL_UB=.6), rows)
    assert summary['Global_LB'] is None and summary['relative_global_gap'] is None
    assert not summary['global_gap_certified'] and summary['optimality_status'] == 'NOT_CERTIFIED'
    assert summary['physical_evaluation_allowed'] and not summary['missed_gap_blocks_FULL_feasible_Actual']


def test_unmet_mess_gap_keeps_valid_bound_and_full_actual_permission():
    source = dict(stage_case_sha='current-M1')
    summary = summarize_current_k48(dict(source=source, K=48), dict(current_FULL_UB=.6),
        [bound_result(source, 48, .57)])
    assert summary['K48_Global_LB_valid'] and summary['K48_Global_LB'] == .57
    assert summary['relative_global_gap'] > .03 and not summary['global_gap_certified']
    assert summary['optimality_status'] == 'OPTIMALITY_TARGET_UNMET'
    assert summary['physical_evaluation_allowed']


def test_bound_from_different_current_anchor_is_rejected():
    with pytest.raises(ValueError, match='HISTORY_CURRENT_CASE_DRIFT'):
        summarize_current_k48(dict(source={'stage_case_sha':'now'}, K=16), dict(current_FULL_UB=.6),
            [bound_result({'stage_case_sha':'other'}, 16, .59)])
