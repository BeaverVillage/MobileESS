import pytest
from v42_may12_rescue.contract import decide

def good():
    return ({'PASS':True},{'PASS':True,'classes':130,'complete_STAY_and_migration_coverage':True},
        {'PASS':True,'exact_LB':'999/1000'},
        {'PASS':True,'exact_UB':'1','original_integer_types_restored':True},
        {'PASS':True,'original_job_population_verified':True})

def test_p1_only_is_separate_from_four_objective_contract():
    r=decide(*good());assert r['A1_P1_ONLY_ACCEPTED'] and r['A1_ACCEPTED'] is False

@pytest.mark.parametrize('index',range(5))
def test_each_missing_independent_certificate_rejected(index):
    a=good();a[index]['PASS']=False;assert not decide(*a)['PASS']

def test_restricted_class_domain_rejected():
    a=good();a[1]['classes']=129;assert not decide(*a)['PASS']

def test_incomplete_migration_coverage_rejected():
    a=good();a[1]['complete_STAY_and_migration_coverage']=False;assert not decide(*a)['PASS']

def test_gap_boundary_is_exact():
    a=good();a[2]['exact_LB']='199/200';assert decide(*a)['PASS']
    a[2]['exact_LB']='9949/10000';assert not decide(*a)['PASS']

def test_conflicting_bound_rejected():
    a=good();a[2]['exact_LB']='1001/1000'
    with pytest.raises(ValueError):decide(*a)
