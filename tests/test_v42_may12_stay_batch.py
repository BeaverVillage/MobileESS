from types import SimpleNamespace
from fractions import Fraction as F
import numpy as np
import scipy.sparse as sp
import pytest
from v42_may12_rescue.stay_batch import admit_histograms

def fixture():
    s=SimpleNamespace(matrix=sp.csr_matrix([[1.,1.,1.]]),lower=np.zeros(3),upper=np.full(3,2.),
        senses=np.array(['=']),rhs=np.array([2.]))
    B=sp.csr_matrix([[2.,4.,0.]])
    units=[dict(stay_count=True,v={'y':{('A',0):('v',0),('A',1):('v',1)}})]
    return s,B,units

def admit(s,B,u,baseline=-3,already=frozenset(),allowed=frozenset({(0,'A'),(1,'A')}),pi=None):
    return admit_histograms(s,B,u,2,np.array([1.]) if pi is None else pi,baseline,allowed,already,2)

def test_exact_negative_concrete_histograms_and_original_boxes():
    s,B,u=fixture();r=admit(s,B,u)
    assert [x['column'] for x in r]==[0,1]
    assert [F(x['exact_improvement']) for x in r]==[-1,-5]
    for x in r:
        p=np.zeros(3);p[x['column']]=2
        assert np.array_equal(s.matrix@p,s.rhs)
    s.upper[1]=1
    assert [x['column'] for x in admit(s,B,u)]==[0]

def test_active_option_and_nonnegative_option_not_reactivated():
    s,B,u=fixture()
    assert [x['column'] for x in admit(s,B,u,already={('A',0)})]==[1]
    assert admit(s,B,u,baseline=-9)==[]

def test_missing_original_physical_membership_rejected():
    s,B,u=fixture()
    with pytest.raises(ValueError,match='OUTSIDE_ORIGINAL_PHYSICAL_DOMAIN'):admit(s,B,u,allowed=set())

def test_extra_hard_rows_and_nonzero_other_lower_bound_are_not_ignored():
    s,B,u=fixture();s.matrix=sp.csr_matrix([[1.,1.,1.],[1.,0.,0.]])
    s.senses=np.array(['=','<']);s.rhs=np.array([2.,1.])
    assert [x['column'] for x in admit(s,B,u)]==[1]
    s.lower[2]=.1
    assert admit(s,B,u)==[]

def test_exact_price_detects_float_cancellation():
    s,B,u=fixture();B=sp.csr_matrix([[1e16,4.,0.],[1.,0.,0.],[-1e16,0.,0.]])
    r=admit(s,B,u,baseline=1,pi=np.ones(3))
    assert F(r[0]['exact_price'])==-2

def test_original_strict_negative_threshold_is_preserved():
    s,B,u=fixture();B=sp.csr_matrix([[.5,.5,0.]])
    assert admit(s,B,u,baseline=-1+F(1,100000000))==[]

def test_completed_master_can_be_reused_without_new_charge(tmp_path,monkeypatch):
    from test_v42_may12_cached_native_reuse import prepare
    native,folder,snapshot=prepare(tmp_path,monkeypatch)
    rec,raw=native.solve(snapshot,folder,'ORIGINAL_P1')
    assert rec['status']==2 and native.native_seconds==.77 and native.budget.used==.77
