from fractions import Fraction as F
from itertools import product
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_may10_prestart_rescue.compression import compress
from v42_may10_prestart_rescue.isolation import assert_write_path, OUT, require_large_resource_isolation, ResourceIsolationPending


def fixture():
    A = sp.csr_matrix([[0,1,8], [1,1,0], [1,1,0], [0,0,0], [F(1,2),0,0]], dtype=float)
    return LinearSnapshot(A,np.zeros(3),np.array([2.,7.,3.]),np.array(['=','<','<','=','<']),
        np.array([7.,9.,9.,0.,1.]),np.array(['I','I','I']),
        (Objective('rho',((0,F(1,2)),),F(3,2)), Objective('migration_count',()),
         Objective('shift_magnitude',((1,F(1)),(2,F(8)))), Objective('prestart_relocation',((0,F(1)),(2,F(1))),F(2)))).require()


def feasible(s,x):
    activity=s.matrix @ x
    return np.all(x>=s.lower) and np.all(x<=s.upper) and all(a==b if sense=='=' else a<=b if sense=='<' else a>=b for a,b,sense in zip(activity,s.rhs,s.senses))


def objective(o,x):
    return F(o.constant)+sum(c*int(x[j]) for j,c in o.coefficients().items())


def test_bidirectional_integer_set_and_all_four_objectives():
    s=fixture();c=compress(s,0,expected_shift=7)
    assert list(c.fixed_zero)==[2]
    assert c.compact.matrix.shape==(3,2)
    original={x for x in product(range(3),range(8),range(4)) if feasible(s,np.array(x))}
    restored={tuple(c.inverse(np.array(x))) for x in product(range(3),range(8)) if feasible(c.compact,np.array(x))}
    assert len(original)==3
    assert original==restored
    for x in original:
        compact=c.forward(np.array(x))
        assert np.array_equal(c.inverse(compact),x)
        assert [objective(o,x) for o in s.objectives]==[objective(o,compact) for o in c.compact.objectives]


def test_wrong_shift_axis_and_nonzero_zero_point_are_rejected():
    with pytest.raises(ValueError):compress(fixture(),1,expected_shift=7)
    c=compress(fixture(),0,expected_shift=7)
    with pytest.raises(ValueError):c.forward([0,7,F(1,1000000)])


def test_tiny_original_coefficient_is_retained():
    from dataclasses import replace
    s=fixture();A=s.matrix.copy();A.data[A.data==.5]=1e-13
    c=compress(replace(s,matrix=A),0,expected_shift=7)
    assert 1e-13 in c.compact.matrix.data


def test_false_infeasibility_is_not_inferred_from_nonzero_zero_row():
    from dataclasses import replace
    s=fixture();rhs=s.rhs.copy();rhs[3]=1e-13
    c=compress(replace(s,rhs=rhs),0,expected_shift=7)
    assert 3 in c.kept_rows


def test_independent_namespace_and_protected_process_gate(monkeypatch):
    assert assert_write_path(OUT/'fixture.json').is_relative_to(OUT)
    with pytest.raises(PermissionError):assert_write_path(OUT.parent/'old.json')
    monkeypatch.setattr('v42_may10_prestart_rescue.isolation.protected_process_active',lambda:True)
    with pytest.raises(ResourceIsolationPending):require_large_resource_isolation()
