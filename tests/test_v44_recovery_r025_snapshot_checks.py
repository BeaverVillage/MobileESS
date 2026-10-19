from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v44_recovery_r025.snapshot_checks import valid_labels,adapted_require,require_scope

def model():
    return LinearSnapshot(sp.csr_matrix(np.eye(256)),np.zeros(256),np.ones(256),
        np.array(['<']*256),np.ones(256),np.array(['C']*256),(Objective('rho',((0,Fraction(1)),),0),))

@pytest.mark.parametrize('kind,allowed',[('senses',('=','<','>')),('vtypes',('B','I','C'))])
def test_every_label_and_in_place_mutation_checked_each_call(kind,allowed):
    values=np.array(list(allowed)*100);before=values.copy()
    assert valid_labels(values,allowed);assert np.array_equal(values,before)
    for location in [0,150,299]:
        values[location]='X';assert not valid_labels(values,allowed);values[location]=before[location]
        assert valid_labels(values,allowed)

@pytest.mark.parametrize('values',[[],['<','>','='],np.array([b'<'],dtype='S1'),np.array(['<'],dtype=object),np.array(['bad']*200)])
def test_fallback_and_unicode_semantics_match_original(values):
    assert valid_labels(values,('=','<','>'))==(not any(v not in ('=','<','>') for v in values))

def test_full_require_fingerprint_exact_and_scope_restores():
    m=model();before=m.fingerprint();original=LinearSnapshot.require
    with require_scope():assert m.require() is m and m.fingerprint()==before
    assert LinearSnapshot.require is original

@pytest.mark.parametrize('change,message',[
    ('sense','LINEAR_ROW_SENSE'),('type','LINEAR_VARIABLE_TYPE'),('rhs','NONFINITE_STAGE_COEFFICIENT'),
    ('lower','NONFINITE_STAGE_BOUND'),('bounds','INCONSISTENT_STAGE_BOUNDS')])
def test_all_original_failures_remain_same(change,message):
    m=model()
    if change=='sense':m.senses[170]='X'
    elif change=='type':m.vtypes[170]='X'
    elif change=='rhs':m.rhs[170]=np.nan
    elif change=='lower':m.lower[170]=np.nan
    else:m.lower[170]=2.
    for function in [LinearSnapshot.require,adapted_require(LinearSnapshot.require)]:
        with pytest.raises(ValueError,match=message):function(m)

def test_changed_source_fails_closed():
    def changed(self):return self
    with pytest.raises(ValueError,match='SOURCE_DRIFT'):adapted_require(changed)

def test_exception_restores_original_validator():
    original=LinearSnapshot.require
    with pytest.raises(RuntimeError):
        with require_scope():raise RuntimeError('test')
    assert LinearSnapshot.require is original
