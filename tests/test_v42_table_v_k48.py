"""Tiny algebra fixtures only; no Gurobi model or optimization is constructed."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_integration.a_engine import digest
from v42_integration.table_v_k48 import (
    _data, _matrix, exact_cut, identity, physical_axes, prepare_k16,
    verify_packet, append_cuts, separate, ORIGINAL_CALL_CAP, replay)
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
    ident = dict(original_matrix_sha=matrix_sha(A), original_domain_sha=_domain_sha(d),
        D0_source_sha='current-source', D0_parent_case_sha='current-E1-common', arm='B2', stage='M1',
        aidc_anchor='current-reference-anchor')
    coeff = SimpleNamespace(node_names=('n1.1',), branch_names=('line.test::1',), transformer_ratings=(100.,))
    case = SimpleNamespace(original_A=A, original_d=d, identity=ident, case_sha=digest(ident),
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
