"""Separate uncached source-row derivation and original FULL start checks."""
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_compact_joint.continuation_audit import direct_check

def main():
    configure();full_guard();timer=Timing();gate=read(DOCS/'NATIVE0_STATIC_GATE.json')
    with timer.stage('Source_Case_load'):case=v.load_native_case()
    names=list(map(str,case.d['names']));route=[j for j,n in enumerate(names) if n.startswith(('route_flow[','node_activity['))]
    keep=[j for j,n in enumerate(names) if not n.startswith(('route_flow[','node_activity['))]
    direct=read(gate['models']['DIRECT']['path']);dfolder=Path(gate['models']['DIRECT']['path']).parent
    with timer.stage('uncached_direct_name_and_exact_dyadic_coefficients'):
        T=direct_check(case,direct,dfolder,keep,route);del T
    ef=read(gate['models']['EF']['path']);efolder=Path(gate['models']['EF']['path']).parent
    with timer.stage('EF_original_CSR_and_all_nonroute_domain'):
        A=sparse.load_npz(efolder/'A.npz').tocsr();assert v.matrix_sha(A[:715596,:354277].tocsr())==v.MATRIX_SHA and A[:715596,354277:].nnz==0
        with np.load(efolder/'DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
        for field in ('rhs','sense','row_names'):assert np.array_equal(d[field][:715596],case.d[field])
        for field in ('lower','upper','types','objective','names'):assert np.array_equal(d[field][keep],case.d[field][keep])
        nodes=[j for j in route if case.d['types'][j]=='B'];assert np.all(d['types'][nodes]=='C') and len(nodes)==8938
        assert np.count_nonzero(d['types']=='B')==416 and np.array_equal(d['objective'][:354277],case.d['objective'])
        assert ef['pool_signature']==direct['pool_signature'] and ef['center_vector_SHA']==direct['center_vector_SHA']
        del A,d;gc.collect()
    with timer.stage('Original_FULL_start_replay'):
        replay=DOCS/'INDEPENDENT_INITIAL_FULL_REPLAY.json';cert=validate(direct['center_raw']['path'],replay,read(direct['center_replay']['path'])['Global_UB']);assert cert['PASS']
    write(DOCS/'INDEPENDENT_NATIVE0_REVIEW.json',dict(PASS=True,Optimize_calls=0,source_rows_independently_checked=715596,
        exact_uncached_dyadic_Direct_coefficients=True,EF_Source_CSR_and_nonroute_bounds_types_objective=True,
        matched_pool_Source_case_Start=True,Original_FULL_PASS=record(replay),Source_Physics_Grid_384Mode_preserved=True,
        previous_controller_not_touched=True,timing=timer.receipt()))
    print(json.dumps(dict(PASS=True,timing=timer.receipt())),flush=True)
if __name__=='__main__':main()
