from fractions import Fraction
import pytest
from v42_a_stage_acceptance.gap import global_gap_acceptance
from v42_a_stage_domain_v2.lexstage import integer_optimality_certificate
from v42_a_stage_acceptance.policy import DAYS
def cert(L,U,**kw):
    return global_gap_acceptance('shift_magnitude',L,U,full_domain_verified=True,bound_verified=True,
        primal_verified=True,locks_verified=True,**kw)
def test_gap_is_separate_from_exact_integer_optimality():
    c=cert(948,950,native_status=11)
    assert c['PASS'] and c['gap']==float(Fraction(1,475)) and c['native_status']==11
    assert not c['exact_integer_optimum_claimed'] and not c['native_status_overridden']
    assert not integer_optimality_certificate('shift_magnitude',950,948,bound_independently_validated=True,
        primal_independently_validated=True,integrality_proven=True)['PASS']
@pytest.mark.parametrize('L,U,expected',[(199,200,True),(198,200,False),(0,0,True),(-1,0,False),(201,200,False),(None,200,False)])
def test_boundary_and_zero(L,U,expected):assert cert(L,U)['PASS']==expected
def test_restricted_bound_cannot_be_accepted():
    assert not global_gap_acceptance('shift_magnitude',948,950,bound_verified=True,primal_verified=True,locks_verified=True)['PASS']
def test_authorized_order():assert DAYS==('2025-05-19','2025-05-17','2025-05-10','2025-05-12')
