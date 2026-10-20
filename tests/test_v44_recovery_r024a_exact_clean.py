import json,math
from fractions import Fraction
from pathlib import Path
import numpy as np
import pytest
from v44_recovery_r024a.exact_clean import install,cleaner
from v42_pr134_b1.common import clean

@pytest.mark.parametrize('value',[None,True,17,-0.0,float('inf'),float('-inf'),float('nan'),
    {'한글':[1,2.,None,True,{'x':np.float64(1.25),'y':np.int64(7)}],3:(Path('a/b'),)},
    np.array([[-0.,1.],[np.nan,np.inf]]),np.array([np.int64(3),'a'],dtype=object)])
def test_cleaned_JSON_bytes_exact(value):
    expected=json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)
    with install():actual=json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)
    assert actual==expected

def test_imported_alias_restores_and_unknown_type_error_kept():
    import v42_pr134_b1.common as common
    alias=common.clean;code=alias.__code__
    with pytest.raises(RuntimeError):
        with install():
            assert alias is common.clean and clean({'a':np.int64(2)})=={'a':2}
            with pytest.raises(TypeError):json.dumps(clean(Fraction(1,3)))
            raise RuntimeError('original')
    assert alias.__code__ is code

def test_subclasses_and_string_key_collision_order_exact():
    class List(list):pass
    class Dict(dict):pass
    value=Dict({1:'integer','1':'string','nested':List([np.int64(4),np.float32(2)])})
    before=clean(value)
    with install():after=clean(value)
    assert list(before)==list(after) and json.dumps(before)==json.dumps(after)

def test_duplicate_scope_rejected_without_restoring_outer_early():
    with install():
        with pytest.raises(AssertionError):
            with install():pass
        assert clean([np.float64(1)])==[1.]
