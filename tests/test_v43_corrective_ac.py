"""Native0 cache binding/state/candidate guards, not real DSS equivalence."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from v43_corrective.current_ac import CertifiedPrefixAC,FullPrefixReferenceAC,assert_equivalent


def test_native_state_arrays_are_compared_without_ambiguous_numpy_truth():
    p=CertifiedPrefixAC.__new__(CertifiedPrefixAC);p.performance={'verified_history_reuses':0}
    state=(np.array([1.,1.00625]),np.array([1,1]))
    cached=dict(converged=True,native_state=FullPrefixReferenceAC._native_state(state))
    source=dict(native_state=lambda odd:state)
    p._reuse_verified_history(None,source,cached,True)
    assert p.performance['verified_history_reuses']==1
    with pytest.raises(ValueError,match='TAP_OR_CAP_STATE_DRIFT'):
        p._reuse_verified_history(None,dict(native_state=lambda odd:([1.,1.],[1,1])),cached,True)
    with pytest.raises(ValueError,match='CONVERGENCE_DRIFT'):
        p._reuse_verified_history(None,source,cached,False)


def step():
    return dict(PASS=True,converged=True,violations={},native_state=dict(taps=[1.],caps=[1]),
        voltage_min_pu=.98,voltage_max_pu=1.02,maximum_phase_line_loading=.5,
        voltage_vector_pu=[.98,1.02],branch_measurement_rows=[[50.,.5,None]])


@pytest.mark.parametrize('key,value',[('PASS',False),('native_state',dict(taps=[1.00625],caps=[1])),
    ('voltage_vector_pu',[.98,1.02000001]),('branch_measurement_rows',[[50.00001,.5,None]])])
def test_independent_equality_rejects_hidden_tap_voltage_or_current_changes(key,value):
    a=dict(PASS=True,physical_steps=[step()]);b=deepcopy(a)
    assert assert_equivalent(a,b)['PASS']
    b['physical_steps'][0][key]=value
    with pytest.raises(ValueError,match='PREFIX_EQUIVALENCE'):assert_equivalent(a,b)


def test_canonical_unrated_line_kva_is_preserved_as_none_not_fabricated_zero():
    assert FullPrefixReferenceAC._measurements(np.array([[50.,.5,float('nan')]]))==[[50.,.5,None]]


def test_new_candidate_can_never_match_a_cached_past_slot_key():
    p=CertifiedPrefixAC.__new__(CertifiedPrefixAC)
    p._authority='NAMED_SOURCE_MESS_POWER';p._observed_keys=[];p.history=[]
    a=dict(slot=0,GPU=[1]);b=dict(slot=0,GPU=[2])
    assert p._keys_for_probe([a])!=p._keys_for_probe([b])
    p._authority='DIFFERENT_MESS_OR_C1_SOURCE'
    assert p._keys_for_probe([a])
