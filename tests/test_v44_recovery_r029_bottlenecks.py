import gc,pickle,os,sys,types
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from v44_recovery_r029.compressed_cache import pack,unpack
from v44_recovery_r029.phase_rebuild import ExactCache
from v44_recovery_r029.context_gc import RetirementCollector,scope,finish


@pytest.mark.parametrize('raw',[b'',b'a',b'hello'*100,os.urandom(65536),b'x'*200000],ids=['empty','small','medium','random','compressible'])
def test_lossless_payload_roundtrip_including_empty_and_incompressible(raw):
    assert unpack(pack(raw))==raw


def test_repetitive_large_payload_is_compressed_and_invalid_tag_fails():
    raw=pickle.dumps(dict(matrix=np.zeros((300,300)),rows=['physical']*300),protocol=5)
    payload=pack(raw)
    assert len(payload)<len(raw)*.1 and payload[:1]==b'\1'
    with pytest.raises(ValueError,match='PAYLOAD_TAG'):unpack(b'?garbage')


def test_compressed_cache_retains_more_realistic_arrays_and_keeps_outputs_independent():
    cache=ExactCache(40000);calls=[]
    def compute(k):calls.append(k);return {'a':np.full((128,128),k,dtype=float)}
    for k in range(12):cache.call(k,lambda k=k:compute(k))
    assert cache.evictions==0 and cache.size<=40000
    assert cache.resident_uncompressed_bytes>1000000
    answer=cache.call(3,lambda:pytest.fail('unnecessary model rebuild'));answer['a'][0,0]=-1
    assert cache.call(3,lambda:None)['a'][0,0]==3 and len(calls)==12


def test_compressed_eviction_keeps_accounting_exact():
    cache=ExactCache(800)
    for k in range(30):cache.call(k,lambda k=k:dict(k=k,random=os.urandom(160)))
    assert cache.size==sum(map(len,cache.values.values()))<=800
    assert cache.resident_uncompressed_bytes==sum(cache.raw_sizes.values())
    assert set(cache.raw_sizes)==set(cache.values) and cache.evictions>0


def test_gc_full_scan_is_periodic_or_pending_driven_and_young_scan_keeps_running():
    pending=[];calls=[];collector=RetirementCollector(pending,lambda gen:calls.append(gen) or 0)
    for _ in range(8):collector.run()
    assert calls==[1]*7+[2]
    pending.extend([None]*16);collector.run()
    assert calls[-1]==2 and collector.report()['max_pending_retired_contexts']==16


def test_gc_does_not_replace_global_collector_or_change_original_retirement_checks(monkeypatch):
    module=types.ModuleType('v42_svr11.context_lifecycle');module._completed=[1]
    module.gc=gc;module.checked=[]
    exec('def flush_completed_probes():\n    gc.collect()\n    checked.append(tuple(_completed))\n    return len(_completed)\n',module.__dict__)
    package=types.ModuleType('v42_svr11');package.__path__=[];package.context_lifecycle=module
    monkeypatch.setitem(sys.modules,'v42_svr11',package)
    monkeypatch.setitem(sys.modules,'v42_svr11.context_lifecycle',module)
    original=module.flush_completed_probes;global_collect=gc.collect;oracle=SimpleNamespace(_independent_fresh=False)
    with scope(oracle) as collector:
        assert module.flush_completed_probes()==1
        assert module.checked==[(1,)] and gc.collect is global_collect
    assert module.flush_completed_probes is original
    assert collector.young_collections==1 and collector.full_collections==0


def test_fresh_cannot_use_deferred_gc_and_missing_lifecycle_finalizer_is_noop(monkeypatch):
    with pytest.raises(PermissionError,match='CURRENT_CONTEXT_GC_ONLY'):
        with scope(SimpleNamespace(_independent_fresh=True)):pass
    monkeypatch.delitem(sys.modules,'v42_svr11.context_lifecycle',raising=False)
    assert finish()==0
