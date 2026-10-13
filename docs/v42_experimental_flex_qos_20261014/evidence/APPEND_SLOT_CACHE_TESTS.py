from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'tests/test_v42_experimental_grid.py'
assert 'test_scalar_cache_is_exact' not in p.read_text(encoding='utf8')
extra='''

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
'''
p.write_bytes(p.read_bytes()+extra.encode('utf8'))
print('THREE_EXACT_CACHE_BOUNDARY_TESTS_ADDED')
