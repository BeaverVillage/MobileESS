from fractions import Fraction as F
from itertools import product
import pytest
from v42_may10_prestart_rescue.proofs import shift_count_bounds, relocation_window_bound, cutoff_global_bound


def test_shift_implications_preserve_all_original_integer_points():
    costs = [0, 1, 3, 8]
    bounds, _ = shift_count_bounds(dict(enumerate(costs)), 7, [0]*4, [4]*4, ['I']*4)
    assert bounds == {2: 2, 3: 0}
    original = {x for x in product(range(5), repeat=4) if sum(c*v for c,v in zip(costs,x)) <= 7}
    strengthened = {x for x in product(range(5), repeat=4) if all(x[j] <= u for j,u in bounds.items()) and sum(c*v for c,v in zip(costs,x)) <= 7}
    assert original == strengthened


def test_continuous_finish_semantics_are_not_integerized():
    bounds, _ = shift_count_bounds({0: F(3, 2), 1: 8}, 7, [0, 0], [10, 10], ['C', 'I'])
    assert bounds == {1: 0}


@pytest.mark.parametrize('cost,lower', [(-1, 0), (2, -1)])
def test_negative_terms_cannot_supply_shift_certificate(cost, lower):
    with pytest.raises(ValueError):
        shift_count_bounds({0: cost}, 7, [lower], [10], ['I'])


def test_complete_window_cut_exhaustively_preserves_schedules():
    groups = [dict(class_id='a', cardinality=3, complete_domain=True,
                   reference_choices=[(0, F(3,2)), (3, 0)], remote_choices=[0])]
    cut = relocation_window_bound(groups, F(3,2), 3)
    assert cut['lower'] == 1
    # Every original three-job assignment uses the complete reference and
    # remote domains. Verify the theorem, not just its emitted coefficient.
    choices = [(0,F(3,2),0), (3,0,0), (0,0,1)]
    feasible = []
    for selection in product(choices, repeat=3):
        if sum(v[0] for v in selection) <= 3 and sum(v[1] for v in selection) <= F(3,2):
            feasible.append(selection)
            assert sum(v[2] for v in selection) >= cut['lower']
    assert feasible


def test_zero_shift_escape_does_not_create_false_relocation_lower_bound():
    group = dict(class_id='a', cardinality=2, complete_domain=True,
                 reference_choices=[(0, 0)], remote_choices=[])
    assert relocation_window_bound([group], 0, 0)['lower'] == 0


def test_incomplete_domain_is_rejected():
    with pytest.raises(ValueError):
        relocation_window_bound([dict(class_id='a', cardinality=2, complete_domain=False)], 1, 2)


def test_cutoff_requires_complement_partition_and_actual_bound():
    assert cutoff_global_bound(60, 59, 12, complete_domain=True, objective_integral=True) == 12
    assert cutoff_global_bound(60, 59, None, complete_domain=True, objective_integral=True) is None
    assert cutoff_global_bound(60, 59, None, complete_domain=True, objective_integral=True, subquery_infeasible=True) == 60
    with pytest.raises(ValueError):
        cutoff_global_bound(60, 59, 12, complete_domain=False, objective_integral=True)
