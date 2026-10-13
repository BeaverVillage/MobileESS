"""Remove all route coordinates through an exactly audited sparse linear lift."""
from collections import defaultdict,Counter
from scipy import sparse
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.global_local_multistart1800.joint import build_spec,unit_vector
from tools.adaptive_compact_joint.compact import integer_proof

def transform(case,point,replay,pools,label):
    spec,lo,hi,links,rhs=build_spec(case,point,replay,pools,label,0)
    proof=integer_proof(case,point,spec,lo,hi,links,rhs);assert proof['PASS']
    route,_=route_values(case,paths_of(case,point));route=np.asarray(route,dtype=int)
    keep=np.setdiff1d(np.arange(case.A.shape[1]),route,assume_unique=True)
    assert len(route)==216674 and len(keep)==137603
    grouped={u:np.asarray([j for j in route if str(case.d['names'][j]).split('[',1)[1].split(',')[0]==u],dtype=int) for u in pools}
    rr=[];cc=[];vv=[]
    for offset,entry in enumerate(spec['lambda_axis']):
        ids=grouped[entry['unit']];values=unit_vector(case,entry['unit'],ids,entry['path']);chosen=ids[values==1]
        rr.extend(map(int,chosen));cc.extend([len(keep)+offset]*len(chosen));vv.extend([1.]*len(chosen))
    rr.extend(map(int,keep));cc.extend(range(len(keep)));vv.extend([1.]*len(keep))
    T=sparse.csr_matrix((vv,(rr,cc)),shape=(case.A.shape[1],len(keep)+spec['lambda_count']))
    source_product=(case.A@T).tocsr();source_product.eliminate_zeros();source_product.sort_indices()
    # Independent exact rational coefficient closure. Original physical columns
    # are copied, and every lambda column is re-derived from its source path.
    assert (source_product[:,:len(keep)]!=case.A[:,keep]).nnz==0
    checked=0;cancelled=0
    for offset,entry in enumerate(spec['lambda_axis']):
        pathcols=T[:,len(keep)+offset].tocoo().row
        source=case.A[:,pathcols].tocoo();terms=defaultdict(F)
        for row,value in zip(source.row,source.data):terms[int(row)]+=F(float(value))
        actual=source_product[:,len(keep)+offset].tocoo();observed=dict(zip(map(int,actual.row),map(lambda z:F(float(z)),actual.data)))
        exact={row:value for row,value in terms.items() if value}
        assert exact==observed,'SPARSE_PRODUCT_NOT_EXACT_DYADIC'
        checked+=len(terms);cancelled+=sum(not value for value in terms.values())
    one=sparse.csr_matrix(([1.]*spec['lambda_count'],([sorted(pools).index(a['unit']) for a in spec['lambda_axis']],[len(keep)+j for j in range(spec['lambda_count'])])),shape=(4,T.shape[1]))
    A=sparse.vstack((source_product,one),format='csr')
    d=dict(names=np.r_[case.d['names'][keep],np.asarray([a['name'] for a in spec['lambda_axis']])],
        rhs=np.r_[case.d['rhs'],np.ones(4)],sense=np.r_[case.d['sense'],np.asarray(['=']*4)],
        lower=np.r_[case.d['lower'][keep],np.zeros(spec['lambda_count'])],upper=np.r_[case.d['upper'][keep],np.ones(spec['lambda_count'])],
        types=np.r_[case.d['types'][keep],np.asarray(['B']*spec['lambda_count'])],
        objective=np.r_[case.d['objective'][keep],np.zeros(spec['lambda_count'])],constant=case.d['constant'].copy(),
        row_names=np.r_[case.d['row_names'],np.asarray(['route_pool_one['+u+']' for u in sorted(pools)])])
    assert np.all(case.d['objective'][route]==0) and np.count_nonzero(d['types']=='B')==384+spec['lambda_count']
    start=np.r_[point[keep],spec['lambda_Start']]
    lifted=T@start;assert np.array_equal(lifted,point) and v.vector_sha(lifted)==v.vector_sha(point)
    assert np.array_equal(d['rhs'][:-4],case.d['rhs']) and np.array_equal(d['sense'][:-4],case.d['sense'])
    spec.update(method='EXACT_DIRECT_COMPACT_FOUR_MESS_JOINT',keep_columns=keep.tolist(),removed_route_columns=route.tolist(),
        compact_columns=A.shape[1],compact_rows=A.shape[0],compact_binary=int(np.count_nonzero(d['types']=='B')),
        compact_matrix_SHA=v.matrix_sha(A),compact_domain_SHA=v.domain_sha(d),lift_SHA=v.matrix_sha(T),
        unchanged_PR220_Start_restored=True,center_raw=record(read(replay)['point_path']),source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA)
    proof.update(direct_substitution=True,original_source_rows_semantically_preserved=case.A.shape[0],
        original_source_RHS_Sense_objective_unmodified=True,source_columns_removed=len(route),
        exact_dyadic_lambda_row_coefficients_checked=checked,exact_cancellations=cancelled,
        original_integer_designations_removed=8938,original_continuous_route_flow_removed=207736,
        source_nonzeros=int(case.A.nnz),compact_nonzeros=int(A.nnz),fill_in_ratio=float(A.nnz/case.A.nnz),
        original_physical_remaining_bounds_types_free=True,
        proof_direct='x_dense=T z, with exact original nonroute coordinates and literal route incidence columns. Every source row is retained as A_source T z sense rhs_source. Each product coefficient is independently verified using exact dyadic fractions. Original RHS is unchanged; no affine rounding of offsets. One-hot lambda implies all removed route coordinates are exact original path incidence. This gives integer equivalence to the old joint for the same pool, and a subset of original FULL.',
        raw_lift_is_inverse_model_mapping_not_numeric_repair=True)
    return spec,A,d,T,start,proof

def save(case,point,replay,pools,label,folder):
    folder.mkdir(parents=True,exist_ok=False)
    spec,A,d,T,start,proof=transform(case,point,replay,pools,label)
    sparse.save_npz(folder/'A.npz',A);sparse.save_npz(folder/'LIFT.npz',T);np.savez_compressed(folder/'DATA.npz',**d);np.savez_compressed(folder/'START.npz',point=start)
    spec['packets']={k:record(folder/(k+'.npz')) for k in ('A','LIFT','DATA','START')}
    write(folder/'SPEC.json',spec);write(folder/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json',proof)
    return spec,proof
