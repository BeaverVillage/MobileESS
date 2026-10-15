from copy import deepcopy

import pytest

from v42_integration.rc02_prefix_cache import ExactPrefixProofCache
from v42_integration.actual_validation import record


def fixture(tmp_path, max_entries=8):
    material=tmp_path/'source.py';material.write_text('source-v1',encoding='utf-8')
    cache=ExactPrefixProofCache([record(material)],max_entries=max_entries)
    fields=dict(history=[dict(slot=0,start_seconds=0,end_seconds=900,GPU=[1],P=[2],Q=[3])],
        current_slot=1,current_observations={'public_current':True},source_sha='s',MESS_plan_sha='m')
    return cache,material,fields


def test_cached_physical_fail_is_preserved_and_copy_isolated(tmp_path):
    cache,material,fields=fixture(tmp_path)
    key=cache.key(**fields);cache.put(key,[dict(PASS=False,physical_sha='p',SVR_sha='v')])
    proof=cache.get(key)
    assert proof['historical_prefix_physical_PASS'] is False
    proof['physical_steps'].clear()
    assert len(cache.get(key)['physical_steps'])==1


@pytest.mark.parametrize('field,value',[('source_sha','changed'),('MESS_plan_sha','changed'),
    ('current_observations',{'public_current':False})])
def test_changed_source_or_MESS_or_observation_cannot_hit_proof(tmp_path,field,value):
    cache,material,fields=fixture(tmp_path)
    key=cache.key(**fields);cache.put(key,[dict(PASS=True)])
    fields[field]=value
    assert cache.get(cache.key(**fields)) is None


def test_prefix_PQ_or_GPU_change_cannot_hit_proof(tmp_path):
    cache,material,fields=fixture(tmp_path)
    key=cache.key(**fields);cache.put(key,[dict(PASS=True)])
    for name in ('GPU','P','Q'):
        changed=deepcopy(fields);changed['history'][0][name]=[99]
        assert cache.get(cache.key(**changed)) is None


def test_source_byte_drift_fails_even_when_self_same_key(tmp_path):
    cache,material,fields=fixture(tmp_path)
    key=cache.key(**fields);cache.put(key,[dict(PASS=True)])
    material.write_text('source-v2',encoding='utf-8')
    with pytest.raises(ValueError,match='MATERIAL_SOURCE_BYTES_DRIFT'):cache.get(key)


def test_inmemory_proof_tamper_rejected(tmp_path):
    cache,material,fields=fixture(tmp_path)
    key=cache.key(**fields);cache.put(key,[dict(PASS=False)])
    cache.entries[key]['physical_steps'][0]['PASS']=True
    with pytest.raises(ValueError,match='PROOF_BYTES_DRIFT'):cache.get(key)


def test_cache_bounded_eviction(tmp_path):
    cache,material,fields=fixture(tmp_path,max_entries=1)
    cache.put('one',[]);cache.put('two',[])
    assert cache.get('one') is None and cache.get('two') is not None


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),1800])
def test_noncontiguous_or_nonfinite_prefix_clock_rejected(tmp_path,bad):
    cache,material,fields=fixture(tmp_path)
    fields['history'][0]['end_seconds']=bad
    with pytest.raises(ValueError,match='EXACT_CAUSAL_HISTORY_REQUIRED'):cache.key(**fields)
