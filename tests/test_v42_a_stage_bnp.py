from fractions import Fraction
import pytest
from v42_a_stage_bnp.queue import Queue,gap

def test_best_bound_preserves_both_children_and_refuses_unclosed_global_bound():
    q=Queue();root=q.add(None);q.close_lp(root.id,1,row_closed=True,column_closed=True)
    assert q.global_bound()==1
    a,b=q.split(root.id,7,Fraction(3,2))
    assert a.restrictions==((7,'UPPER',1),) and b.restrictions==((7,'LOWER',2),)
    assert q.global_bound() is None
    q.close_lp(a.id,2,row_closed=True,column_closed=True);q.close_lp(b.id,Fraction(3,2),row_closed=True,column_closed=True)
    assert q.best().id==b.id and q.global_bound()==Fraction(3,2)
    with pytest.raises(ValueError,match='BOTH_CLOSURES'):q.close_lp(a.id,10,row_closed=True,column_closed=False)

def test_global_gap_is_an_integer_UB_plus_valid_full_domain_LB():
    assert gap(Fraction(995,1000),1)==Fraction(5,1000)
    with pytest.raises(ValueError,match='EXCEEDS'):gap(2,1)
