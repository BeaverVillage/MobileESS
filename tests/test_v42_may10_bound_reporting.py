import pytest
from v42_may10_prestart_rescue.proofs import integer_bound_review

def test_actual_two_plus_roundoff_is_not_bound_improvement():
    r=integer_bound_review(60,2.0000000000000275)
    assert r['global_LB']==2 and not r['accepted']
    assert r['global_gap']==pytest.approx(58/60)

def test_material_valid_integer_bound_is_retained():
    assert integer_bound_review(60,2.25)['global_LB']==3
    assert integer_bound_review(60,60)['exact_integer_optimality']

def test_bound_conflicting_with_verified_ub_is_rejected():
    with pytest.raises(ValueError):integer_bound_review(60,61)
