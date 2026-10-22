"""Independent original-coordinate and per-deletion verification.

The verifier reloads original CSR and recomputes each row implication with a
full sort. Finite witnesses are explicitly separate from formulation proof.
No producer PASS or prior DY removal mask is accepted as mathematical proof.
"""
import time,pickle
from fractions import Fraction as F
import numpy as np
import scipy.sparse as sp
from .static_common import *
from .static_pack import PACK,N_AUX
from .static_screen import CACHE,load

def original_intervals(A,d,r,C,a,nbase,t,rho_column):
    """Separate implementation: original components, full sort, all48 axes."""
    lo=nbase+t*N_AUX;non=np.flatnonzero(r['sense']!='=')
    E=A[non,lo+48:lo+N_AUX];direct=A[non,lo:lo+48]
    co=(direct+E.dot(C)).tocsr();constant=r['rhs'][non]-E.dot(a)
    rc=A[non,rho_column].toarray().ravel()
    objective=np.array([str(r['local_names'][i]).startswith('parent_line_thermal_face') for i in non])
    box=np.r_[np.full(24,300.),np.full(24,250.)]
    absolute=abs(direct).dot(box)+abs(E).dot(abs(C).dot(box)+abs(a))+abs(r['rhs'][non])
    cb=[co];rb=[constant];rho=[rc];obj=[objective];components=[absolute]
    for sign,side in ((1.,'upper'),(-1.,'lower')):
        ii=np.flatnonzero(np.isfinite(d[side][48:]))
        cb.append(sign*C[ii]);rb.append(sign*(d[side][48:][ii]-a[ii]));rho.append(np.zeros(len(ii)));obj.append(np.zeros(len(ii),dtype=bool))
        components.append(abs(C[ii]).dot(box)+abs(a[ii])+abs(d[side][48:][ii]))
    co=sp.vstack(cb,format='csr');rhs=np.concatenate(rb);rc=np.concatenate(rho);objective=np.concatenate(obj)
    dense=co.toarray();support=np.sort(abs(dense[:,:24])*300+abs(dense[:,24:])*250,axis=1)[:,-8:].sum(axis=1)
    lower=-support+np.minimum(rc,0);upper=support+np.maximum(rc,0)
    eps=np.finfo(float).eps;gamma=100*eps/(1-100*eps)
    err=np.nextafter(gamma*(1+np.concatenate(components)),np.inf)
    err+=1e-12*(1+np.maximum(abs(lower),abs(upper)))
    return np.nextafter(lower-err,-np.inf),np.nextafter(upper+err,np.inf),rc,rhs,objective,non

def verify():
    init();start=time.perf_counter();ma=sp.load_npz(PACK/'MOBILITY.npz')
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
    ref=read(OUT/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json');screen=read(OUT/'IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json')
    nbase=ma.shape[1];L=screen['implied_global_rho_lower_bound'];w=screen['objective_implication_witness']
    proofs=[];counts={'SAFE_REMOVE':0,'EXACT_REDUNDANT':0,'EXACT_SUBSTITUTION':0,'RETAIN':0}
    proof_errors=[];witness_verified=False;exact_witness=None
    from v42_m1_research.check_ub import matrix_replay
    basepoint=np.load(PACK/'MOBILITY_POINT.npy');rho=int(np.flatnonzero(md['objective'])[0]);basepoint[rho]=1.
    # Existing real multi-MOVE trajectory and SOC boundary arithmetic are
    # input witnesses only. Their DY feasibility certificate is NOT reused.
    move=np.load(HIST_RUN/'MOVE_COMPACT_POINT.npy').copy();move[rho]=1.
    import types
    from .may01_verify import boundary_point
    boundary=types.FunctionType(boundary_point.__code__,dict(boundary_point.__globals__,PACK=PACK,table=table))(md)
    points={'STAY':np.r_[basepoint,np.zeros(96*48)],'MULTI_MOVE_PQ_REBOUND':move,'SOC440_1080_CHARGE_DISCHARGE_BOTH_Q':boundary}
    full={k:np.zeros(nbase+96*N_AUX) for k in points}
    results={k:dict(PASS=True,rows=0,nnz=0,max_row_violation=0.,max_bound_violation=0.) for k in points}
    for k,p in points.items():
        full[k][:nbase]=p[:nbase]
        z=matrix_replay(ma,md,p[:nbase]);results[k].update(PASS=z['PASS'],rows=ma.shape[0],nnz=ma.nnz,
            max_row_violation=z['maximum_observed_row_violation'],max_bound_violation=z['max_bound_violation'],
            integer_pattern_exact=z['integer_pattern_exact'])
    for t in range(96):
        guard(start);p=CACHE/f'{t:02d}';A,d,r=load(t);lo=nbase+t*N_AUX
        with np.load(p/'STATIC_SELECTION.npz') as z:s={k:z[k] for k in z.files}
        with np.load(p/'PROOF.npz') as z:q={k:z[k] for k in z.files}
        C=sp.load_npz(p/'RECONSTRUCTION.npz');a=np.load(p/'CONSTANT.npy')
        eq=np.flatnonzero(r['sense']=='=');assert len(eq)==N_AUX
        E=A[eq[48:],lo+48:lo+N_AUX].tocsr();diag=E.data
        assert E.nnz==N_AUX-48 and np.array_equal(E.indices,np.arange(N_AUX-48))
        assert np.all(np.frexp(diag)[0]==.5)
        # Round-trip exact positive power2 scaling of every stored coefficient
        # and RHS verifies defining relations without any FD regeneration.
        T=(-sp.diags(diag)@C).tocsr();orig=A[eq[48:],lo:lo+48]
        delta=T-orig;delta.eliminate_zeros();assert delta.nnz==0
        assert np.array_equal(a*diag,r['rhs'][eq[48:]])
        lower,upper,rc,rhs,objective,independent_ids=original_intervals(A,d,r,C,a,nbase,t,rho)
        assert np.array_equal(independent_ids,q['inequality_ids'])
        assert np.all(rc[objective]<0) and np.all(rc[~objective]==0)
        safe=(upper<=rhs-q['margin'])&~objective
        redundant=objective&(upper<=rhs-rc*L-q['margin'])
        # FULL sort may round its last sum differently; certify the stored
        # selectors by independent inequalities, never by identical masks.
        n=len(q['inequality_ids']);cls=s['classification'];non=q['inequality_ids']
        safe_rows=cls[non]=='SAFE_REMOVE';dom_rows=cls[non]=='EXACT_REDUNDANT'
        assert np.all(safe[:n][safe_rows]) and np.all(redundant[:n][dom_rows])
        assert not np.any(safe_rows&objective[:n])
        assert np.all(safe[n:][s['safe_bounds']])
        if t==w['slot']:
            wi=w['witness_projected_row'];bound=(lower[wi]-rc[wi]-rhs[wi])/(-rc[wi])
            assert objective[wi]
            # One exact rational witness certifies the global rho tightening;
            # no floating tolerance is used for this implication.
            original_row=int(non[wi]);a0,b0=A.indptr[original_row:original_row+2]
            coeff=[F(0) for _ in range(48)];right=F(float(r['rhs'][original_row]));rh=F(0)
            for j,weight in zip(A.indices[a0:b0],A.data[a0:b0]):
                weight=F(float(weight));j=int(j)
                if j==rho:rh+=weight
                elif lo<=j<lo+48:coeff[j-lo]+=weight
                else:
                    k=j-lo-48;assert 0<=k<C.shape[0]
                    right-=weight*F(float(a[k]))
                    aa,bb=C.indptr[k:k+2]
                    for col,val in zip(C.indices[aa:bb],C.data[aa:bb]):coeff[int(col)]+=weight*F(float(val))
            terms=sorted([300*abs(coeff[k])+250*abs(coeff[24+k]) for k in range(24)],reverse=True)
            exact_lower=(-sum(terms[:8],F(0))-right)/(-rh)
            assert rh<0 and F(L)<=exact_lower
            exact_witness=dict(slot=t,original_row=original_row,exact_rational_lower_bound=str(exact_lower),
                conservative_used_bound=L,exact_dyadic_comparison_PASS=True)
            assert cls[non[wi]]=='RETAIN';witness_verified=True
        required=set(non[~(safe_rows|dom_rows)])
        required.update(eq[s['variables']]);assert required==set(s['rows'])
        unused=np.setdiff1d(np.arange(N_AUX),s['variables'])
        assert np.all(cls[eq[unused]]=='EXACT_SUBSTITUTION')
        for kind in counts:counts[kind]+=int(np.sum(cls==kind))
        proofs.append(dict(slot=t,all_original_rows=A.shape[0],exact_definitions=N_AUX-48,
            safe_original_rows=int(safe_rows.sum()),implied_objective_rows=int(dom_rows.sum()),
            omitted_bounds=int(s['safe_bounds'].sum()),all_unresolved_rows_retained=True))
        nz=np.unique(A.indices);assert np.all((nz<nbase)|((nz>=lo)&(nz<lo+N_AUX)))
        local_A=A[:,nz].tocsr()
        local_domain=dict(rhs=r['rhs'],sense=r['sense'],names=np.array([]),
            lower=np.full(len(nz),-np.inf),upper=np.full(len(nz),np.inf),types=np.full(len(nz),'C'),
            objective=np.zeros(len(nz)),constant=0.)
        for name,cp in points.items():
            u=cp[nbase:].reshape(96,48)[t];f=full[name];f[lo:lo+N_AUX]=np.r_[u,a+C@u]
            raw=matrix_replay(local_A,local_domain,f[nz],tolerance=1e-6,
                row_tolerances=np.where(r['sense']=='=',1e-6,1e-8))
            # Only current block values have been initialized. Each slot CSR
            # references current block+base exclusively (asserted by producer
            # and rechecked here), so no future value can authorize feasibility.
            bv=max(0.,float(np.max(d['lower']-f[lo:lo+N_AUX])),float(np.max(f[lo:lo+N_AUX]-d['upper'])))
            z=results[name];z['PASS'] &= bool(raw['PASS'] and bv<=1e-8)
            z['rows']+=A.shape[0];z['nnz']+=A.nnz
            z['max_row_violation']=max(z['max_row_violation'],raw['maximum_observed_row_violation'])
            z['max_bound_violation']=max(z['max_bound_violation'],bv)
        if t%8==0:print('STATIC INDEPENDENT PROOF',t,flush=True)
        del A
    assert witness_verified
    # Check original graph/SOC/PCS physics for all finite trajectories.
    with (RUN/'mobility/TRANSPORT.pkl').open('rb') as f:transport=pickle.load(f)
    from v42_m1_research.check_ub import physical_replay
    from types import SimpleNamespace
    case=SimpleNamespace(graph=transport['graph'],original_d=md)
    for k,p in points.items():
        phy=physical_replay(case,p[:nbase]);results[k]['physical_replay']=phy
        results[k]['PASS'] &= phy['PASS']
        np.save(RUN/(k+'_SOURCE_YY_FULL_POINT.npy'),full[k])
    put('STATIC_FULL_WITNESS_VALIDATION.json',dict(results=results,source_case_sha=ref['case_sha'],
        finite_witnesses_are_not_equivalence_proof=True,Native_calls=0))
    return put('IEEE8500_EXACT_COMPACT_EQUIVALENCE.json',dict(PASS=True,
        scope='Source-YY fixed-B0 M1 only',original_case_sha=ref['case_sha'],
        per_original_row_classification_verified=True,all96_original_blocks_reloaded=True,
        dyadic_power2_definition_reconstruction_exact=True,shared_sparse_affine_equalities=True,
        eliminated_auxiliary_bounds_proven_or_retained=True,all_unknown_rows_retained=True,
        objective_faces_removed_only_by_retained_row_implication=True,
        exact_rational_objective_implication_witness=exact_witness,
        original_16face_physics_preserved=True,LP_relaxation_preserved=True,
        node_flow_and_static_presolve=record(OUT/'ORIGINAL_STATIC_PRESOLVE_MESS8.json'),
        per_row_counts=counts,blocks=proofs,witnesses=record(OUT/'STATIC_FULL_WITNESS_VALIDATION.json'),
        Native_calls=0,Global_LB=None,Global_UB=None,Global_Gap=None,
        A1_A2_M2_and_actual_nonlinear_AC_equivalence_claimed=False,
        wall_seconds=time.perf_counter()-start))

if __name__=='__main__':verify()
