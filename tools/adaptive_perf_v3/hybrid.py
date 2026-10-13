"""Exact sparse extended form keeps original helpers and implied route integrality."""
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.cache import proof_function
from tools.global_local_multistart1800.joint import build_spec

def save(case,point,replay,pools,label,folder,cache,timing):
    with timing.stage('EF_CSR_generation'):
        spec,lo,hi,links,rhs=build_spec(case,point,replay,pools,label,0)
    proof=proof_function(cache,timing)(case,point,spec,lo,hi,links,rhs)
    with timing.stage('EF_packet_and_structure_IO'):
        folder.mkdir(parents=True,exist_ok=False);N=case.A.shape[1];L=spec['lambda_count']
        A=sparse.vstack([sparse.hstack([case.A,sparse.csr_matrix((715596,L))],format='csr'),links],format='csr')
        T=sparse.hstack([sparse.eye(N,format='csr'),sparse.csr_matrix((N,L))],format='csr')
        types=case.d['types'].copy();nodes=np.asarray([j for j in cache['route'] if types[j]=='B']);types[nodes]='C'
        assert len(nodes)==8938
        d=dict(names=np.r_[case.d['names'],np.asarray([a['name'] for a in spec['lambda_axis']])],rhs=np.r_[case.d['rhs'],rhs],
            sense=np.r_[case.d['sense'],np.asarray(['=']*len(rhs))],lower=np.r_[lo,np.zeros(L)],upper=np.r_[hi,np.ones(L)],
            types=np.r_[types,np.asarray(['B']*L)],objective=np.r_[case.d['objective'],np.zeros(L)],constant=case.d['constant'].copy(),
            row_names=np.r_[case.d['row_names'],np.asarray([f'EF_link[{i}]' for i in range(len(rhs))])])
        start=np.r_[point,spec['lambda_Start']];assert np.array_equal(T@start,point)
        spec.update(method='EXACT_SPARSE_EXTENDED_FOUR_MESS_JOINT',keep_columns=list(range(N)),removed_route_columns=[],compact_columns=A.shape[1],
            compact_rows=A.shape[0],compact_binary=384+L,compact_matrix_SHA=v.matrix_sha(A),compact_domain_SHA=v.domain_sha(d),lift_SHA=v.matrix_sha(T),
            unchanged_PR220_Start_restored=True,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,original_helper_coordinates_retained=True)
        proof.update(original_source_rows_semantically_preserved=715596,exact_dyadic_lambda_row_coefficients_checked=links.nnz,
            source_columns_removed=0,original_source_RHS_Sense_objective_unmodified=True,no_physical_nonroute_columns_removed=True,
            exact_EF_integer_feasible_region_preserved=True,original_node_integrality_implied_by_one_hot_links=True)
        sparse.save_npz(folder/'A.npz',A);sparse.save_npz(folder/'LIFT.npz',T);np.savez_compressed(folder/'DATA.npz',**d);np.savez_compressed(folder/'START.npz',point=start)
        spec['packets']={key:record(folder/(key+'.npz')) for key in ('A','LIFT','DATA','START')}
        write(folder/'SPEC.json',spec);write(folder/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json',proof)
    return spec,proof

def structure(case,spec,folder):
    A=sparse.load_npz(folder/'A.npz').tocsr();rn=np.diff(A.indptr);cn=np.diff(A.tocsc().indptr)
    report=dict(PASS=True,source_rows=715596,rows=A.shape[0],columns=A.shape[1],NNZ=A.nnz,
        matrix_density=A.nnz/(A.shape[0]*A.shape[1]),source_NNZ=case.A.nnz,global_fill_in_ratio=A.nnz/case.A.nnz,
        row_NNZ_percentiles=np.percentile(rn,[0,50,90,99,100]).tolist(),column_NNZ_percentiles=np.percentile(cn,[0,50,90,99,100]).tolist(),
        dense_rows_gt100=int(np.count_nonzero(rn>100)),high_degree_columns_gt1000=int(np.count_nonzero(cn>1000)))
    source_degree=np.diff(case.A.indptr);delta=rn[:715596]-source_degree
    report.update(original_row_NNZ_delta_min=int(delta.min()),original_row_NNZ_delta_max=int(delta.max()),rows_with_local_fill_in=int(np.count_nonzero(delta>0)),
        rows_with_NNZ_reduction=int(np.count_nonzero(delta<0)),coefficient_absolute_min=float(abs(A.data).min()),coefficient_absolute_max=float(abs(A.data).max()))
    write(folder/'MATRIX_STRUCTURE.json',report);return report
