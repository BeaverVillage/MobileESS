"""Real-data, Native0 cache and native-context lifecycle validation."""
from pathlib import Path
from time import perf_counter
import gzip,pickle,json,gc,weakref
import v44_recovery_r029
from v44.common import read,record,atomic,now
from v44_recovery_r029.compressed_cache import pack,unpack
from v44_recovery_r029.phase_rebuild import ExactCache
from v44_recovery_r029.context_gc import scope as gc_scope,finish

root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
source=root/'2025-05-02/B3/attempt012/A2/OUTPUT/STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'
with gzip.open(source,'rb') as stream:state=pickle.load(stream)
from v42_a_stage_phase1.producer import native_block
from v42_may_campaign_native90.preflight import native_zero
classes=sorted(state['data'][7]['classes'])
chosen=[classes[0],classes[len(classes)//2],classes[-1]];records=[]
with native_zero() as denied:
    for key in chosen:
        uid=state['data'][7]['classes'][key][0];graph=state['data'][5][uid]
        t=perf_counter();value=native_block(state['data'],key,graph,tuple(state['axes']));build=perf_counter()-t
        raw=pickle.dumps(value,protocol=5);t=perf_counter();packed=pack(raw);encode=perf_counter()-t
        t=perf_counter();decoded=unpack(packed);decode=perf_counter()-t
        assert decoded==raw
        cache=ExactCache(max(100000,len(raw)*2));cache.call(key,lambda:value)
        first=cache.call(key,lambda:(_ for _ in ()).throw(AssertionError('cache miss')))
        assert first[0].fingerprint()==value[0].fingerprint()
        # Every byte of the cached payload is lossless, including sparse order.
        records.append(dict(class_id=key,Native0_build_wall=build,raw_bytes=len(raw),packed_bytes=len(packed),
            ratio=len(packed)/len(raw),pack_wall=encode,unpack_wall=decode,cache=cache.report(),
            exact_payload_bytes_equal=True,snapshot_fingerprint_equal=True))
    assert not denied

from v44.svr12 import scope as hardware_scope
from types import SimpleNamespace
with hardware_scope():
    import opendssdirect as odd
    import v42_svr11.context_lifecycle as life
    from dss import CffiApiUtil
    from dss_python_backend.events import EventCallbackManager
    life.flush_completed_probes()
    owners=type(odd.NewContext.__self__)._ctx_to_dss
    baseline=(len(owners),len(CffiApiUtil._ctx_to_util),len(EventCallbackManager._ctx_to_manager))
    # A retained ordinary graph reproduces the full-heap scan cost without
    # retaining any engine, utility, callback or native pointer.
    ordinary_heap=[dict(row=[j,j+1],metadata={'source':'unchanged'}) for j in range(80000)]
    gc.collect()
    measurements=[]
    for deferred in (False,True):
        oracle=SimpleNamespace(_independent_fresh=False);refs=[];began=perf_counter()
        for i in range(24):
            engine=odd.NewContext();refs.append(weakref.ref(engine))
            life.retire_completed_probe(engine);del engine
            if deferred:
                with gc_scope(oracle):life.flush_completed_probes()
            else:life.flush_completed_probes()
        finish()
        elapsed=perf_counter()-began
        assert not life._completed and all(ref() is None for ref in refs)
        current=(len(owners),len(CffiApiUtil._ctx_to_util),len(EventCallbackManager._ctx_to_manager))
        assert current==baseline,(current,baseline)
        measurements.append(dict(deferred=deferred,contexts=24,wall_seconds=elapsed,
            pending=0,all_owners_finalized=True,registries_equal_baseline=True,
            collector=oracle._r029_context_gc.report() if deferred else None))
    del ordinary_heap

result=dict(UTC=now(),PASS=True,Native_optimization_calls=0,source_state=record(source),cache_blocks=records,
    lifecycle=measurements,profile=record(Path('D:/MobileESS_V44/development/R029_CURRENT_ACTUAL_PROFILE_20261018.json')),
    actual_case_speedup_or_PASS_claimed=False,physical_measurements_or_NATIVE_solves_skipped=0)
destination=Path('D:/MobileESS_V44/development/R029_REAL_BENCHMARK_20261018.json');atomic(destination,result)
print(json.dumps(result))
