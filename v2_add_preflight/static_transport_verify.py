"""Independently compose original presolve and grid maps against Native CSR."""
import pickle,time
import numpy as np
import scipy.sparse as sp
from .static_common import *
from .static_pack import PACK,N_AUX
from .static_screen import CACHE,load

def verify():
    init();start=time.perf_counter()
    if not read(OUT/'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json')['PASS']:
        return put('NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json',dict(PASS=False,status='NO_COMPLETE_NATIVE_MODEL',Native_calls=0))
    with (RUN/'mobility/TRANSPORT.pkl').open('rb') as f:state=pickle.load(f)
    p,c=state['presolve'],state['compact'];nbase=c.original.shape[1];nb=p.A.shape[1]
    positions={int(j):i for i,j in enumerate(p.col_ids)};steps={s['column']:s for s in p.steps};memo={}
    def expand(j):
        if j in memo:return memo[j]
        if j in positions:out=(positions[j],0.)
        else:
            s=steps[j]
            if not s['terms']:out=(-1,float(s['constant']))
            else:
                assert len(s['terms'])==1 and next(iter(s['terms'].values()))==1. and s['constant']==0.
                out=expand(int(next(iter(s['terms']))))
        memo[j]=out;return out
    independent=np.array([expand(j)[0] for j in range(nbase)],dtype=np.int64)
    offset=np.array([expand(j)[1] for j in range(nbase)])
    with np.load(RUN/'mobility/ORIGINAL_MAP.npz') as z:
        assert np.array_equal(independent,z['column']) and np.array_equal(offset,z['constant'])
    select=np.flatnonzero(independent>=0)
    T=sp.csr_matrix((np.ones(len(select)),(select,independent[select])),shape=(nbase,nb))
    M=sp.load_npz(RUN/'native/COMPLETE_A.npz').tocsr();n=M.shape[1]
    with np.load(RUN/'native/COMPLETE_DOMAIN.npz') as z:d={k:z[k] for k in ('lower','upper','types','rhs','sense','objective','constant')}
    delta=M[:p.A.shape[0],:nb]-p.A;delta.eliminate_zeros();assert delta.nnz==0
    assert M[:p.A.shape[0],nb:].nnz==0
    for key in ('lower','upper','types','objective'):assert np.array_equal(d[key][:nb],p.d[key])
    assert np.array_equal(d['rhs'][:p.A.shape[0]],p.d['rhs']) and np.array_equal(d['sense'][:p.A.shape[0]],p.d['sense'])
    assert np.all(d['objective'][nb:]==0) and d['constant']==p.d['constant']
    allcols=[];blocks=[]
    for t in range(96):
        guard(start);A,vd,r=load(t);lo=nbase+t*N_AUX
        with np.load(CACHE/f'{t:02d}'/'STATIC_SELECTION.npz') as z:required=z['rows'];needed=z['variables']
        with np.load(RUN/'native'/f'{t:02d}_MAP.npz') as z:
            rows=z['original_rows'];axis=z['original_aux_to_native'];first=int(z['first_native_row'])
        assert np.array_equal(rows,required) and np.array_equal(np.flatnonzero(axis>=0),needed)
        used=np.flatnonzero(axis>=0);cols=axis[used];allcols.extend(map(int,cols))
        U=sp.csr_matrix((np.ones(len(used)),(used,cols)),shape=(N_AUX,n))
        left=A[rows,:nbase]@T;right=A[rows,lo:lo+N_AUX]@U
        expected=sp.hstack([left,sp.csr_matrix((len(rows),n-nb))],format='csr')+right
        shift=A[rows,:nbase]@offset
        assert np.all(shift==0.),'GRID_REFERENCES_NONZERO_FIXED_COORDINATE'
        delta=M[first:first+len(rows)]-expected;delta.eliminate_zeros();assert delta.nnz==0
        assert np.array_equal(d['rhs'][first:first+len(rows)],r['rhs'][rows])
        assert np.array_equal(d['sense'][first:first+len(rows)],r['sense'][rows])
        for key in ('lower','upper','types'):assert np.array_equal(d[key][cols],vd[key][used])
        blocks.append(dict(slot=t,rows=len(rows),all_coefficients_exact=True,original_bounds_exact=True))
        if t%12==0:print('NATIVE ORIGINAL TRANSPORT',t,flush=True)
    assert np.array_equal(np.sort(allcols),np.arange(nb,n))
    result=put('NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json',dict(PASS=True,
        original_static_presolve_map_independently_expanded=True,all96_original_grid_blocks_composed=True,
        every_actual_Native_CSR_coefficient_RHS_sense_bound_type_objective_verified=True,
        grid_and_original_mobility_presolve_commutation_verified=True,original_variable_coordinate_cover_exact=True,
        scope='Source-YY fixed-B0 M1 only',blocks=blocks,Native_calls=0,wall_seconds=time.perf_counter()-start))
    x=read(OUT/'IEEE8500_EXACT_COMPACT_EQUIVALENCE.json')
    x.update(Native0_composition_PASS=True,independent_native_composition=record(OUT/'NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json'))
    put('IEEE8500_EXACT_COMPACT_EQUIVALENCE.json',x)
    return result

if __name__=='__main__':verify()
