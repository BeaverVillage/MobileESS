import numpy as np
from v42_integration.experimental_grid import ExperimentalGridPacket
from v42_integration.sensitivity_policy import OriginalGridPacket


def test_vectorized_ratings_equal_original_signed_expressions_and_order():
    from test_v42_integration_sensitivity_policy import fixture
    reference=fixture(kva_rating=.1)[0]
    fast=object.__new__(ExperimentalGridPacket)
    fast.__dict__.update(reference.__dict__)
    fast._batch_tables=None
    import math
    fast._rated=[]
    for c in fast.coefficients:
        indices=np.array([i for i,r in enumerate(c.transformer_ratings) if r is not None],dtype=int)
        limits=np.array([float(c.transformer_ratings[i])*math.cos(math.pi/16) for i in indices])
        fast._rated.append((indices,limits))
    for t in (0,5,95):
        for scale in (-100.,0.,.125,1.,10.,100.):
            delta=np.full(len(reference.sites),scale)
            assert fast._at_slot(t,delta)==OriginalGridPacket._at_slot(reference,t,delta)


def test_batch_hard_rows_and_exact_objective_match_original_remaining_horizon():
    from test_v42_integration_sensitivity_policy import fixture
    from copy import deepcopy
    import math
    for options in ({},{'voltage_slope':.1},{'transformer_slope':.4},{'kva_rating':.1}):
        reference=fixture(**options)[0]
        fast=object.__new__(ExperimentalGridPacket);fast.__dict__.update(deepcopy(reference.__dict__))
        fast._batch_tables=None;fast._rated=[]
        for c in fast.coefficients:
            indices=np.array([i for i,r in enumerate(c.transformer_ratings) if r is not None],dtype=int)
            fast._rated.append((indices,np.array([float(c.transformer_ratings[i])*math.cos(math.pi/16) for i in indices])))
        for slot in (0,5,95):
            for magnitude in (-5.,0.,.5,5.):
                a=np.full((96,2),magnitude)
                old=reference.evaluate(a,remaining_slot=slot);new=fast.evaluate(a,remaining_slot=slot)
                assert old['hard_feasible']==new['hard_feasible']
                assert old['violations']==new['violations']
                assert old['peak_score']==new['peak_score']
                np.testing.assert_allclose(old['per_slot_peak'],new['per_slot_peak'],rtol=0,atol=1e-12)


def cached_fixture(**options):
    from test_v42_integration_sensitivity_policy import fixture
    from copy import deepcopy
    import math
    reference=fixture(**options)[0]
    fast=object.__new__(ExperimentalGridPacket)
    fast.__dict__.update(deepcopy(reference.__dict__))
    fast._batch_tables=None;fast._rated=[]
    for c in fast.coefficients:
        indices=np.array([i for i,r in enumerate(c.transformer_ratings) if r is not None],dtype=int)
        fast._rated.append((indices,np.array([float(c.transformer_ratings[i])*math.cos(math.pi/16) for i in indices])))
    return reference,fast


def test_scalar_cache_is_exact_and_returned_violations_do_not_poison_future_guard():
    reference,fast=cached_fixture(kva_rating=.1)
    delta=np.array([10.,10.])
    expected=OriginalGridPacket._at_slot(reference,5,delta)
    first=fast._at_slot(5,delta)
    assert first==expected
    first[1].clear()
    assert fast._at_slot(5,delta)==expected
    assert fast.slot_cache_hits==1 and fast.slot_cache_misses==1
    fast.slot_cache_enabled=False
    assert fast._at_slot(5,delta)==expected


def test_scalar_cache_has_no_quantization_or_cross_slot_packet_reuse():
    reference,fast=cached_fixture(voltage_slope=.1)
    for slot,delta in [(0,np.array([.125,.125])),(1,np.array([.125,.125])),
                       (1,np.array([np.nextafter(.125,1),.125])),(1,np.array([1,1],dtype=int))]:
        assert fast._at_slot(slot,delta)==OriginalGridPacket._at_slot(reference,slot,delta)
    assert fast.slot_cache_misses==4
    other_ref,other=cached_fixture(transformer_slope=.4)
    assert other._at_slot(1,np.array([1,1]))==OriginalGridPacket._at_slot(other_ref,1,np.array([1,1]))
    assert other.slot_cache_misses==1


def test_scalar_cache_stays_bounded_and_evicted_inputs_recompute_exactly():
    reference,fast=cached_fixture()
    for i in range(1030):fast._at_slot(i%96,np.array([i/10.,i/10.]))
    assert len(fast._slot_cache)==1024
    before=fast.slot_cache_misses
    assert fast._at_slot(0,np.array([0.,0.]))==OriginalGridPacket._at_slot(reference,0,np.array([0.,0.]))
    assert fast.slot_cache_misses==before+1
