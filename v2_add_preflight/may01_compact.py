"""Lossless M1 electrical projection and delayed FULL separation.

The sealed reference is fixed-B0-AIDC Planning M1, not a variable-job A1/A2
model. No solver bound, AC certificate, or campaign result is manufactured.
Every original face remains in the oracle. Only equality-defined grid
auxiliaries are eliminated; the original mobility block is retained verbatim.
"""
import re, threading
from collections import Counter, defaultdict
import numpy as np
import scipy.sparse as sp
import psutil
from .may01_common import *

N_AUX=34329
N_INJ=48
CACHE=RUN/'compact'
MARGIN=1e-7

def family(name):
    return re.sub(r'_\d\d\[\d+\]$', '', str(name))

def load(t):
    p=PACK/f'{t:02d}'
    A=sp.load_npz(p/'MATRIX.npz')
    with np.load(p/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    with np.load(p/'ROWS.npz') as z:r={k:z[k] for k in z.files}
    return A,d,r

def projection(t,nbase):
    """Extract y=a+Cx from the actual reference equalities, not FD formulas."""
    A,d,r=load(t); lo=nbase+t*N_AUX; eq=np.flatnonzero(r['sense']=='=')
    assert len(eq)==N_AUX
    assert np.array_equal(eq[:48],np.arange(48))
    definitions=eq[48:];D=A[definitions,lo+48:lo+N_AUX].tocsr()
    assert D.shape==(N_AUX-48,N_AUX-48) and D.nnz==N_AUX-48
    assert np.array_equal(D.indices,np.arange(N_AUX-48))
    diagonal=D.data.copy()
    assert np.all(diagonal>0) and np.all(np.frexp(diagonal)[0]==.5)
    assert A[definitions,:lo].nnz==0 and A[definitions,lo+N_AUX:].nnz==0
    C=(-sp.diags(1/diagonal)@A[definitions,lo:lo+48]).tocsr()
    a=r['rhs'][definitions]/diagonal
    non=np.flatnonzero(r['sense']!='=')
    assert np.all(r['sense'][non]=='<')
    # One-slot sparse multiplication only. All exact nonzero values retained.
    E=A[non,lo+48:lo+N_AUX]
    B=(A[non,lo:lo+48]+E@C).tocsr();B.sum_duplicates();B.eliminate_zeros();B.sort_indices()
    rho=A[non,:nbase]
    nz=np.unique(rho.indices);assert len(nz)==1
    rho_col=int(nz[0]); rc=np.asarray(rho[:,rho_col].toarray()).ravel()
    H=sp.hstack([B,sp.csr_matrix(rc[:,None])],format='csr')
    rhs=r['rhs'][non]-np.asarray(E@a).ravel()
    # Eliminated variable bounds are original constraints too.
    ids=[f'grid:{t:02d}:row:{int(i)}' for i in non]
    names=[str(r['local_names'][i]) for i in non]
    extra=[];erhs=[]
    for sign,which,bounds,label in ((1.,np.flatnonzero(d['upper'][48:]<1e90),d['upper'][48:],'UB'),
                                   (-1.,np.flatnonzero(d['lower'][48:]>-1e90),d['lower'][48:],'LB')):
        extra.append(sp.hstack([sign*C[which],sp.csr_matrix((len(which),1))],format='csr'))
        erhs.append(sign*(bounds[which]-a[which]))
        ids += [f'grid:{t:02d}:bound:{int(k+48)}:{label}' for k in which]
        names += ['node_voltage_'+label for k in which]
    H=sp.vstack([H]+extra,format='csr');rhs=np.concatenate([rhs]+erhs)
    H.sum_duplicates();H.eliminate_zeros();H.sort_indices()
    return dict(A=A,domain=d,rows=r,C=C,a=a,H=H,rhs=rhs,
        ids=np.asarray(ids),families=np.asarray([family(x) for x in names]),
        definitions=definitions,original_inequalities=non,rho_col=rho_col)

def support(H):
    """Certified overdomain: <=8 occupied ports, P300/Q250 each.

    Taking the sum of the eight greatest rectangular per-port supports is an
    upper bound even when SOC, ETA, PCS16, and mode further restrict controls.
    All those restrictions remain in the untouched reference mobility block.
    No assumption of eight independent injections at every port is needed.
    """
    p=abs(H[:,:24]).toarray();q=abs(H[:,24:48]).toarray()
    s=300*p+250*q
    eight=np.partition(s,16,axis=1)[:,16:].sum(axis=1)
    rho=np.asarray(H[:,48].toarray()).ravel()
    # rho in [0,1], exactly as in the sealed domain.
    upper=eight+np.maximum(rho,0)
    lower=-eight+np.minimum(rho,0)
    # Outward error bound, deliberately much larger than IEEE double dot error.
    error=1e-12*(1+np.maximum(abs(lower),abs(upper)))
    return lower-error,upper+error

def verify_port_domain(A,d):
    """Read numerical source rows, not an asserted P/Q capability label."""
    names=d['names'];rows=d['row_names'];sense=d['sense'];rhs=d['rhs']
    lookup={str(n):i for i,n in enumerate(names)}
    q=np.array([str(n).startswith('Q[') for n in names])
    assert np.all(d['lower'][q]==-250) and np.all(d['upper'][q]==250)
    # Every connected Pch/Pdis/Q row has the source coefficient 300/250.
    counts={}
    for fam,value in [('connected_Pch',300.),('connected_Pdis',300.),('connected_Qmax',250.),('connected_Qmin',250.)]:
        ix=np.flatnonzero(rows==fam);S=A[ix]
        assert len(ix)>0 and np.all(np.diff(S.indptr)==2)
        assert np.all(np.sort(abs(S.data).reshape(-1,2),axis=1)==np.array([1.,value]))
        assert np.all(rhs[ix]==0)
        counts[fam]=len(ix)
    ix=np.flatnonzero(rows=='all24_mobile_port_occupancy');assert len(ix)==2304
    assert np.all(A[ix].data==1) and np.all(rhs[ix]==1) and np.all(sense[ix]=='<')
    # At most one path/connected STAY per vehicle and slot is retained in the
    # original flow matrix. Eight vehicles means at most eight occupied ports.
    assert len({str(n).split(',')[0][4:] for n in names if str(n).startswith('arc[')})==8
    return dict(PASS=True,per_port_bounds=dict(P=[-300,300],Q=[-250,250]),
        at_most_8_occupied_ports=True,source_connected_rows=counts,occupancy_rows=len(ix),
        all_route_SOC_PCS_mode_flow_rows_retained=True,AIDC='fixed original B0 M1 only')

def build():
    res=init();CACHE.mkdir(exist_ok=True);start=time.perf_counter();peak=[0];stop=threading.Event()
    def sample():
        while not stop.wait(.1):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    mA=sp.load_npz(PACK/'MOBILITY.npz')
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
    nbase=mA.shape[1];proof=verify_port_domain(mA,md)
    put('PRESCREENING_CONTROL_DOMAIN_PROOF.json',proof)
    certification=read(OLD/'FULL96_MATRIX_PACK_CERTIFICATION.json')
    seal=dict(base=BASE,case_sha=certification['case_sha'],reference=record(OLD/'FULL96_MATRIX_PACK_CERTIFICATION.json'),
        mobility=record(PACK/'MOBILITY.npz'),mobility_domain=record(PACK/'MOBILITY_DOMAIN.npz'),
        objectives=record(PACK/'OBJECTIVES.json'),blocks=[])
    census=defaultdict(Counter);summaries=[];removed=[];allmetrics=Counter()
    for t in range(96):
        guard(start)
        p=CACHE/f'{t:02d}';p.mkdir(exist_ok=True)
        if (p/'RECEIPT.json').exists():
            receipt=read(p/'RECEIPT.json')
        else:
            began=time.perf_counter();x=projection(t,nbase);H=x['H'];rhs=x['rhs']
            lo,hi=support(H);margin=MARGIN*(1+abs(rhs))
            physical=x['families'].astype(str)
            objective=np.char.startswith(physical,'parent_line_thermal_face')
            safe=(hi<=rhs-margin)&~objective
            # Never remove objective faces because of ampacity screening.
            constant=np.diff(H[:,:48].indptr)==0
            impossible=(lo>rhs+margin)&~objective
            # Initial master retains unsafe voltage bounds and major B0 faces.
            active=np.zeros(len(rhs),dtype=bool)
            voltage=np.char.startswith(physical,'node_voltage_')
            active |= voltage & ~safe
            for fam in np.unique(physical):
                k=np.flatnonzero((physical==fam)&~safe)
                if len(k): active[k[np.argmin(rhs[k])]]=True
            # All alias equations are retained; no MOVE column is eliminated.
            binding=x['A'][:48,:nbase+t*N_AUX+48]
            sp.save_npz(p/'RECONSTRUCTION.npz',x['C']);np.save(p/'RECONSTRUCTION_CONSTANT.npy',x['a'])
            sp.save_npz(p/'ORACLE.npz',H)
            np.savez_compressed(p/'ROWS.npz',rhs=rhs,ids=x['ids'],families=x['families'],safe=safe,
                lower=lo,upper=hi,margin=margin,active=active,constant=constant,impossible=impossible)
            # Preserve exact aliases, equality IDs, and all eliminated domains.
            sp.save_npz(p/'INJECTION_BINDING.npz',x['A'][:48,:nbase])
            np.save(p/'INJECTION_DIAGONAL.npy',x['A'][:48,nbase+t*N_AUX:nbase+t*N_AUX+48].toarray())
            np.save(p/'INJECTION_RHS.npy',x['rows']['rhs'][:48])
            c=[]
            for fam in np.unique(x['families']):
                ix=np.flatnonzero(x['families']==fam);S=H[ix];ss=safe[ix];aa=active[ix]
                c.append(dict(family=str(fam),rows=len(ix),columns=len(np.unique(S.indices)),nonzeros=S.nnz,
                    CSR_bytes=S.data.nbytes+S.indices.nbytes+S.indptr.nbytes,
                    exact_constant_response_rows=int(constant[ix].sum()),bound_proved_safe_rows=int(ss.sum()),
                    initial_master_rows=int(aa.sum()),delayed_rows=int((~ss&~aa).sum()),
                    structurally_impossible_rows=int(impossible[ix].sum()),exact_duplicate_rows_removed=0))
            # Algebraic tests include arbitrary injection controls, not only STAY.
            err=0.
            for seed in (0,1,2):
                u=np.random.default_rng(100*t+seed).uniform(-1,1,48)*np.r_[np.full(24,300),np.full(24,250)]
                f=np.zeros(x['A'].shape[1]);f[x['rho_col']]=.8
                f[nbase+t*N_AUX:nbase+(t+1)*N_AUX]=np.r_[u,x['a']+x['C']@u]
                old=x['A'][x['original_inequalities']]@f-x['rows']['rhs'][x['original_inequalities']]
                new=H[:len(old)]@np.r_[u,.8]-rhs[:len(old)]
                err=max(err,float(np.max(abs(new-old)/(1+abs(old)))))
            assert err<1e-9
            receipt=dict(slot=t,reference_rows=x['A'].shape[0],reference_nnz=x['A'].nnz,
                equality_defined_aux_eliminated=N_AUX-48,retained_injection_variables=48,
                oracle_rows=H.shape[0],oracle_nnz=H.nnz,safe_rows=int(safe.sum()),initial_rows=int(active.sum()),
                delayed_rows=int((~safe&~active).sum()),initial_nnz=H[active].nnz,
                prescreened_nnz=H[~safe].nnz,prescreened_rows=int((~safe).sum()),
                structural_impossible_rows=int(impossible.sum()),projection_relative_error=err,census=c,
                build_seconds=time.perf_counter()-began,
                source={f:record(PACK/f'{t:02d}'/f) for f in ('MATRIX.npz','DOMAIN.npz','ROWS.npz')},
                files={q.name:record(q) for q in p.iterdir() if q.is_file()})
            (p/'RECEIPT.json').write_text(__import__('json').dumps(receipt,indent=2),encoding='utf-8')
        for row in receipt['census']:
            for k,v in row.items():
                if k!='family':census[row['family']][k]+=v
        summaries.append(receipt)
        seal['blocks'].append(dict(slot=t,**receipt['source']))
        for row in receipt['census']:
            if row['bound_proved_safe_rows']:
                removed.append(dict(slot=t,family=row['family'],removed_rows=row['bound_proved_safe_rows'],
                    original_IDs_and_bounds=record(p/'ROWS.npz')['path'],archive_sha256=record(p/'ROWS.npz')['sha256'],
                    selector='safe == true',proof='sum8_largest(300*abs(Pcoef)+250*abs(Qcoef))+max(rho_coef,0) <= RHS-margin',
                    restoration='ORACLE.npz row with matching ids; equality-defined variables via RECONSTRUCTION.npz',
                    objective_rows_removed=0))
        put('COMPACT_BUILD_PROGRESS.json',dict(completed_slots=t+1,RSS=psutil.Process().memory_info().rss,wall=time.perf_counter()-start))
        if t%8==0:print('COMPACT SLOT',t,'initial',receipt['initial_rows'],'safe',receipt['safe_rows'],flush=True)
    for fam,ct in census.items():
        ct['columns']=ct.pop('columns') # sum of slot-local incidences, not global union
    mobfamilies=Counter(map(str,md['row_names']))
    rows=[]
    for fam,count in mobfamilies.items():
        ix=np.flatnonzero(md['row_names']==fam);S=mA[ix]
        rows.append(dict(family=fam,scope='MOBILITY_UNCHANGED',rows=count,columns=len(np.unique(S.indices)),nonzeros=S.nnz,
            CSR_bytes=S.data.nbytes+S.indices.nbytes+S.indptr.nbytes,exact_duplicate_rows_removed=0,
            bound_proved_safe_rows=0,initial_master_rows=count,delayed_rows=0))
    rows += [dict(family=fam,scope='PROJECTED_GRID_96',**dict(ct)) for fam,ct in census.items()]
    table('FULL_CONSTRAINT_FAMILY_CENSUS.csv',rows)
    table('PRESCREENING_PROOF_AND_REMOVED_ROWS.csv',removed)
    stop.set();th.join(1)
    put('REFERENCE_FULL_MATRIX_SEAL.json',seal)
    ref=certification['matrix'];ncompact=nbase+96*48
    sumkey=lambda k:sum(r[k] for r in summaries)
    # Actual saved oracle is the all-face compact representation. Delayed rows
    # remain outside Native memory, with their exact original IDs retained.
    result=dict(scope='M1_FIXED_B0_AIDC_REFERENCE_ONLY',reference_case_sha=certification['case_sha'],
        binary=ref['binary'],continuous=ncompact-ref['binary'],variables=ncompact,
        base_rows=mA.shape[0],base_nnz=mA.nnz,alias_rows=96*48,
        oracle_rows=sumkey('oracle_rows'),oracle_nnz=sumkey('oracle_nnz'),safe_rows=sumkey('safe_rows'),
        prescreened_grid_rows=sumkey('prescreened_rows'),prescreened_grid_nnz=sumkey('prescreened_nnz'),
        initial_grid_rows=sumkey('initial_rows'),initial_grid_nnz=sumkey('initial_nnz'),
        delayed_rows=sumkey('delayed_rows'),eliminated_continuous=96*(N_AUX-48),
        structural_impossible_rows=sumkey('structural_impossible_rows'),
        full_projection_max_relative_error=max(r['projection_relative_error'] for r in summaries),
        wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0],resources=res,
        all_original_faces_recoverable=True,original_mobility_rows_and_columns_unchanged=True,
        all_original_variable_bounds_recoverable=True,original_solver_tolerances_changed=False,
        A1_A2_variable_jobs_bound=False,certified_global_LB=None,certified_global_UB=None,
        Native_calls=0,blocks=summaries)
    put('COMPACT_FORMULATION_EQUIVALENCE.json',result)
    print('COMPACT COMPLETE',ncompact,sumkey('initial_rows'),sumkey('safe_rows'),flush=True)

if __name__=='__main__':build()
