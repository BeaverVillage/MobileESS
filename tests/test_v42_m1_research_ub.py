"""No optimize: original checker mutations and the real 9,322-binary axis."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from v42_m1_research.check_ub import matrix_replay, vector_sha
from v42_m1_research.ub import binary_inventory, select_neighborhood


def data(types=('C', 'B')):
    return dict(rhs=np.array([1., 0.]), sense=np.array(['<', '=']),
                lower=np.array([0., 0.]), upper=np.array([2., 1.]),
                types=np.array(types), objective=np.array([1., 0.]), constant=np.array(0.))


@pytest.mark.parametrize('mutation', ['grid', 'route', 'bound', 'integrality', 'nan'])
def test_original_checker_rejects_independent_physical_matrix_mutations(mutation):
    A = sparse.csr_matrix([[1., 0.], [0., 1.]])
    d = data()
    point = np.array([.5, 0.])
    assert matrix_replay(A, d, point)['PASS']
    if mutation == 'grid':
        point[0] = 1.01
    elif mutation == 'route':
        d['rhs'][1] = 1.
    elif mutation == 'bound':
        d['upper'][0] = .49
    elif mutation == 'integrality':
        point[1] = .5
        d['rhs'][1] = .5
    else:
        point[0] = np.nan
    assert not matrix_replay(A, d, point)['PASS']


def test_integrality_tolerance_reported_separately_from_exact_integer_pattern():
    A = sparse.csr_matrix([[1., 0.], [0., 1.]])
    d = data()
    d['rhs'][1] = 1e-10
    replay = matrix_replay(A, d, np.array([.5, 1e-10]))
    assert replay['PASS']
    assert replay['max_integrality_violation'] == 1e-10
    assert not replay['integer_pattern_exact']
    assert not replay['exact_binary_0_1']
    assert replay['integrality_tolerance'] == 1e-8


def test_exact_dyadic_boundary_replay_does_not_round_candidate():
    # High cancellation makes the outward enclosure cross the threshold.
    A = sparse.csr_matrix([[1e12, -1e12]])
    d = dict(rhs=np.array([0.]), sense=np.array(['=']), lower=np.array([0., 0.]),
             upper=np.array([2., 2.]), types=np.array(['C', 'C']),
             objective=np.array([1., 0.]), constant=np.array(0.))
    point = np.array([1., 1.])
    before = vector_sha(point)
    replay = matrix_replay(A, d, point)
    assert replay['PASS'] and replay['close_exact_dyadic_checks'] == 1
    assert before == vector_sha(point)
    point[1] = np.nextafter(1., 0.)
    assert not matrix_replay(A, d, point)['PASS']


@pytest.fixture(scope='module')
def frozen_case():
    root = Path(__file__).resolve().parents[1]
    out = root/'docs/v42_m1_ultracompact_exact_20261006'
    with np.load(out/'C3A_DATA.npz') as z:
        d = {k: z[k].copy() for k in z.files}
    with np.load(out/'C3A_VALID_START.npz') as z:
        point = z['point'].copy()
    return SimpleNamespace(d=d, point=point, critical_sites=['IDC07'])


def test_every_frozen_c3a_binary_is_mapped_and_classified(frozen_case):
    inventory = binary_inventory(frozen_case.d)
    assert len(inventory) == 9322
    assert len({r['column'] for r in inventory}) == 9322
    assert sum(r['family'] == 'charge_mode' for r in inventory) == 384
    assert sum(r['family'] == 'node_activity' for r in inventory) == 8938
    assert {r['unit'] for r in inventory} == {'MESS01', 'MESS02', 'MESS03', 'MESS04'}


@pytest.mark.parametrize('label,unit_count', [('U1', 2), ('U2', 4)])
def test_neighborhood_preserves_outside_window_and_all_binary_decisions(frozen_case, label, unit_count):
    inventory = binary_inventory(frozen_case.d)
    by_column = {r['column']: r for r in inventory}
    spec = select_neighborhood(frozen_case, frozen_case.point, label)
    free = set(map(int, spec['free_binary_columns']))
    fixed = set(map(int, spec['fixed_binary_columns']))
    assert not free & fixed
    assert free | fixed == set(by_column)
    assert all(66 <= by_column[j]['slot'] <= 95 for j in free)
    assert len(spec['active_units']) == unit_count
    assert spec['entire_96_slot_route_SOC_rows_preserved']
    assert spec['full_horizon'] == 96
    assert not spec['all_charge_modes_forced_zero']
    assert 'NOT_GLOBAL_LB' in spec['bound_scope']
    for u in spec['active_units']:
        modes = {r['slot'] for r in inventory if r['unit'] == u and
                 r['family'] == 'charge_mode' and r['column'] in free}
        assert modes == set(range(66, 96))
    if label == 'U2':
        occupied = {r['site'] for r in inventory if r['family'] == 'node_activity' and
                    66 <= r['slot'] <= 95 and frozen_case.point[r['column']] > .5}
        assert occupied <= set(spec['allowed_sites'])
        assert 'IDC07' in spec['allowed_sites']


def test_unknown_neighborhood_does_not_create_parameter_sweep(frozen_case):
    with pytest.raises(ValueError, match='LIMITED_REGISTERED'):
        select_neighborhood(frozen_case, frozen_case.point, 'U3')
