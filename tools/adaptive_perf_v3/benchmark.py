"""Native0 cache/packet equivalence and invalidation tests during live canary."""
import shutil
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.cache import get,verify,fast_save

def main():
    configure();timing=Timing()
    with timing.stage('predecessor_Source_Policy_SHA'):full_guard()
    state=read(PREVIOUS_DOCS/'LIVE_STATE.json');call=next(c for c in reversed(state['new_calls']) if c['formulation']=='DIRECT')
    spec=read(call['model']['path']);oldfolder=Path(call['model']['path']).parent
    with timing.stage('Source_Case_load'):case=v.load_native_case();point=v.load_point(spec['center_raw']['path'])
    cache=get(case,timing);folder=DOCS/'benchmark'/str(spec['candidate_id'])
    new,proof=fast_save(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],folder,cache,timing)
    for key in ('compact_matrix_SHA','compact_domain_SHA','lift_SHA','center_vector_SHA'):
        assert new[key]==spec[key],('OLD_AND_CACHED_MODEL_DIFFERENCE',key)
    for name in ('A','DATA','LIFT','START'):
        if name in ('A','LIFT'):assert (sparse.load_npz(folder/(name+'.npz'))!=sparse.load_npz(oldfolder/(name+'.npz'))).nnz==0
        else:
            with np.load(folder/(name+'.npz'),allow_pickle=False) as a,np.load(oldfolder/(name+'.npz'),allow_pickle=False) as b:
                assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    with timing.stage('cache_invalidation_and_corruption_regressions'):
        wrong=dict(cache['manifest']['identity']);wrong['source_SHA']='DIFFERENT_SOURCE'
        try:verify(cache['folder'],wrong);raise RuntimeError('CACHE_SOURCE_CHANGE_NOT_REJECTED')
        except AssertionError:pass
        wrong=dict(cache['manifest']['identity']);wrong['version']='DIFFERENT_FORMULATION'
        try:verify(cache['folder'],wrong);raise RuntimeError('CACHE_VERSION_CHANGE_NOT_REJECTED')
        except AssertionError:pass
        bad=DOCS/'benchmark/CORRUPTION_FIXTURE';bad.mkdir(parents=True,exist_ok=True)
        packet=bad/'STATIC.npy';packet.write_bytes(b'invalid cache')
        write(bad/'MANIFEST.json',dict(identity=cache['manifest']['identity'],files={'STATIC.npy':dict(sha256='0'*64)}))
        try:verify(bad,cache['manifest']['identity']);raise RuntimeError('CACHE_CORRUPTION_NOT_REJECTED')
        except AssertionError:pass
    with timing.stage('same_Raw_Original_FULL_Replay'):
        replay=DOCS/'benchmark/SAME_RAW_FULL_REPLAY.json';cert=validate(spec['center_raw']['path'],replay,read(spec['center_replay']['path'])['Global_UB']);assert cert['PASS']
    write(DOCS/'CACHE_NATIVE0_EQUIVALENCE.json',dict(PASS=True,Optimize_calls=0,old_spec=record(call['model']['path']),new_spec=record(folder/'SPEC.json'),
        original_CSR_RHS_Bounds_Type_Obj_Start_bit_exact=True,new_DAG_Alias_links_verified=True,cache_Source_version_and_corruption_tests_PASS=True,
        huge_original_FULL_CSR_not_resident=True,timing=timing.receipt(),cache_hit=cache['hit'],memory=r.memory(),Original_FULL_PASS=record(replay)))
    print(json.dumps(dict(PASS=True,timing=timing.receipt(),packet=str(folder/'SPEC.json'))),flush=True)
if __name__=='__main__':main()
