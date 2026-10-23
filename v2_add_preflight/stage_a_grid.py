"""Variable-AIDC Source-YY grid adapter, all original rows before screening.

Twelve independent real-power deviations are coupled to source C1; Q follows
the original PF=.95 contract. Fixed M1 power is accepted only as an explicit
24-site x 96-slot parameter. No fixed-B0 prescreen mask is reused.
"""
import math, re
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_pack import PACK,N_AUX

PF=math.tan(math.acos(.95))

def component(t, p_bounds, mess):
    """Literal raw IEEE8500 factor rows, augmented by variable AIDC columns."""
    with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:a={k:z[k] for k in z.files}
    with np.load(PACK/f'{t:02d}/ROWS.npz') as z:r={k:z[k] for k in z.files}
    with np.load(PACK/f'{t:02d}/DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    raw=sp.load_npz(PACK/f'{t:02d}/MATRIX.npz')
    nbase=raw.shape[1]-96*N_AUX;lo=nbase+t*N_AUX
    # Keep rho and every response helper; fixed MESS injection is substituted
    # exactly into RHS. Its source mobility is validated separately upstream.
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:rho=int(np.flatnonzero(z['objective'])[0])
    keep=np.arange(48,raw.shape[0]);inp=raw[keep,lo:lo+48]
    B=raw[keep][:,np.r_[rho,np.arange(lo+48,lo+N_AUX)]].tocsr()
    rhs=r['rhs'][keep]-inp@mess
    J=lambda name:a[name+'_J'][:12]+PF*a[name+'_J'][12:24]
    axes=read(OUT/'SOURCE_YY_GRID_AXES.json');par=np.flatnonzero(axes['parent_mask']);sec=np.flatnonzero(axes['security_mask'])
    cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
    ap=np.asarray(axes['line_phase_kVA'])[par]*math.cos(math.pi/16)
    active=((a['lp'][par,None]*cos+a['lq'][par,None]*sin)/ap[:,None]).argmax(axis=1)
    corr=J('line')[:,par]-(J('lp')[:,par]*cos[active]+J('lq')[:,par]*sin[active])/ap
    C=np.vstack((J('v').T,J('lp')[:,par].T,J('lq')[:,par].T,corr.T,J('tp').T,J('tq').T))
    assert C.shape==(N_AUX-48,12)
    D=np.zeros((len(keep),12));eq=np.flatnonzero(r['sense'][keep]=='=')
    assert len(eq)==len(C)
    E=B[eq,1:].tocsr();assert E.nnz==len(C) and np.array_equal(E.indices,np.arange(len(C)))
    D[eq]=-E.data[:,None]*C
    direct={}
    port=np.array([i for i,v in enumerate(axes['transformer_current']) if v['winding']==2 and
        v['element'].lower().startswith(('transformer.high_mv_sta','transformer.full_mobile_idc'))])
    for family,old,new in (
        ('line_both_end_current',a['line_J'][24:,sec].T,J('line')[:,sec].T),
        ('transformer_all_winding_current',a['tc_J'][24:].T,J('tc').T),
        ('mobile_port_current',a['tc_J'][24:,port].T,J('tc')[:,port].T)):
        ids=np.flatnonzero(np.char.startswith(r['local_names'][keep].astype(str),family+'_'))
        assert len(ids)==len(old)
        # Recover and verify every dyadic raw row scale. Never infer a new
        # coefficient threshold from a tiny IEEE8500 sensitivity.
        O=inp[ids].toarray();scale=np.ones(len(ids))
        for k in range(len(ids)):
            nz=np.flatnonzero(old[k])
            if len(nz):scale[k]=O[k,nz[0]]/old[k,nz[0]]
        assert np.all(np.frexp(scale)[0]==.5) and np.array_equal(O,old*scale[:,None])
        D[ids]=new*scale[:,None];direct[family]=dict(rows=len(ids),dyadic_scaling_exact=True)
    A=sp.hstack((sp.csr_matrix(D),B),format='csr')
    lower=np.r_[p_bounds[:,0]-a['anchor'][:12],0.,d['lower'][48:]]
    upper=np.r_[p_bounds[:,1]-a['anchor'][:12],1.,d['upper'][48:]]
    names=np.r_[[f'AIDC_delta_P[AIDC{k+1:02d},{t}]' for k in range(12)],['rho_max'],d['names'][48:]].astype(object)
    data=dict(names=names,lower=lower,upper=upper,rhs=rhs,sense=r['sense'][keep],row_names=r['local_names'][keep],
        types=np.full(A.shape[1],'C'),objective=np.r_[np.zeros(12),1.,np.zeros(N_AUX-48)],constant=np.asarray(0.))
    # Reconstruction is inherited from exact defining diagonal, not from a
    # newly evaluated approximate projection used as a Native row.
    E=A[eq,13:];diag=E.data
    H=(-sp.diags(1/diag)@A[eq,:12]).tocsr();c=rhs[eq]/diag
    assert np.array_equal(c*diag,rhs[eq])
    assert (-(sp.diags(diag)@H)-A[eq,:12]).nnz==0
    return A,data,eq,H,c,dict(slot=t,source_coefficient=record(RUN/'coefficients'/f'{t:02d}.npz'),
        direct_families=direct,PF=PF,anchor=a['anchor'][:12].tolist(),MESS_parameter_sha=digest(mess.tolist()))

def intervals(A,d,eq,H,c):
    non=np.flatnonzero(d['sense']!='=');E=A[non,13:];D=A[non,:12]
    P=(D+E@H).tocsr();r=d['rhs'][non]-E@c;rho=A[non,12].toarray().ravel()
    ids=[];sides=[];mat=[P];right=[r];rc=[rho]
    for sign,side in ((1,'upper'),(-1,'lower')):
        bound=np.flatnonzero(np.isfinite(d[side][13:]));ids.extend(bound);sides.extend([side]*len(bound))
        mat.append(sign*H[bound]);right.append(sign*(d[side][13:][bound]-c[bound]));rc.append(np.zeros(len(bound)))
    P=sp.vstack(mat,format='csr');rhs=np.concatenate(right);rho=np.concatenate(rc)
    l=d['lower'][:12];u=d['upper'][:12];positive=P.maximum(0);negative=P.minimum(0)
    low=positive@l+negative@u;high=positive@u+negative@l
    # Conservative forward error includes original components before
    # cancellation, exact helper scales, 12 dot products and RHS subtraction.
    box=np.maximum(abs(l),abs(u));mag=abs(D)@box+abs(E)@(abs(H)@box+abs(c))+abs(d['rhs'][non])
    magnitude=[mag]
    for sign,side in ((1,'upper'),(-1,'lower')):
        bound=np.flatnonzero(np.isfinite(d[side][13:]));magnitude.append(abs(H[bound])@box+abs(c[bound])+abs(d[side][13:][bound]))
    error=100*np.finfo(float).eps/(1-100*np.finfo(float).eps)*(1+np.concatenate(magnitude))
    error+=1e-12*(1+np.maximum(abs(low),abs(high)))
    low=np.nextafter(low-error,-np.inf);high=np.nextafter(high+error,np.inf)
    obj=np.r_[np.char.startswith(d['row_names'][non].astype(str),'parent_line_thermal_face'),np.zeros(len(ids),dtype=bool)]
    return non,np.asarray(ids),low,high,rho,rhs,obj

def prepare_grid(tag,p_bounds,mess):
    folder=WORK/tag/'grid';folder.mkdir(parents=True,exist_ok=True);start=time.perf_counter();rows=[]
    assert p_bounds.shape==(96,12,2) and mess.shape==(96,48)
    for t in range(96):
        guard(start);A,d,eq,H,c,proof=component(t,p_bounds[t],mess[t])
        non,bounds,low,high,rho,rhs,obj=intervals(A,d,eq,H,c)
        L=np.where(obj,(-low+rhs)/np.where(rho!=0,rho,1),-np.inf)
        witness=int(np.argmax(L));lower=max(0.,float(np.nextafter(L[witness],-np.inf)))
        dest=folder/f'{t:02d}';dest.mkdir(exist_ok=True)
        sp.save_npz(dest/'RAW.npz',A);np.savez_compressed(dest/'DOMAIN.npz',**dict(d,names=d['names'].astype(str)))
        np.savez_compressed(dest/'PROOF.npz',non=non,bounds=bounds,low=low,high=high,rho=rho,rhs=rhs,obj=obj,eq=eq)
        sp.save_npz(dest/'RECONSTRUCTION.npz',H);np.save(dest/'CONSTANT.npy',c)
        rows.append(dict(**proof,implied_rho=lower,witness=witness,raw_rows=A.shape[0],raw_nnz=A.nnz))
        if t%8==0:print('VARIABLE AIDC GRID',tag,t,flush=True)
    # New variable-domain witness, derived before Native. Verify it with
    # exact fractions against the original defining equations and P box.
    from fractions import Fraction as F
    w=max(rows,key=lambda r:r['implied_rho']);L=w['implied_rho'];dest=folder/f"{w['slot']:02d}"
    A=sp.load_npz(dest/'RAW.npz');H=sp.load_npz(dest/'RECONSTRUCTION.npz');c=np.load(dest/'CONSTANT.npy')
    with np.load(dest/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    with np.load(dest/'PROOF.npz') as z:p={k:z[k] for k in z.files}
    i=int(p['non'][w['witness']]);co=[F(0) for _ in range(12)];right=F(float(d['rhs'][i]));rc=F(0)
    for j,v in zip(A[i].indices,A[i].data):
        v=F(float(v));j=int(j)
        if j<12:co[j]+=v
        elif j==12:rc+=v
        else:
            right-=v*F(float(c[j-13]))
            for k,value in zip(H[j-13].indices,H[j-13].data):co[int(k)]+=v*F(float(value))
    exact=(sum((min(v*F(float(d['lower'][k])),v*F(float(d['upper'][k]))) for k,v in enumerate(co)),F(0))-right)/(-rc)
    assert rc<0 and F(L)<=exact
    witness=dict(slot=w['slot'],raw_row=i,exact_rational_bound=str(exact),used=L,exact_comparison_PASS=True)
    total=0;nnz=0;variables=0
    for t in range(96):
        guard(start);dest=folder/f'{t:02d}';A=sp.load_npz(dest/'RAW.npz')
        with np.load(dest/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
        with np.load(dest/'PROOF.npz') as z:p={k:z[k] for k in z.files}
        margin=1e-7*(1+abs(p['rhs']));safe=(p['high']<=p['rhs']-margin)&~p['obj']
        dominant=p['obj']&(p['high']<=p['rhs']-p['rho']*L-margin)
        n=len(p['non']);keep=p['non'][~(safe[:n]|dominant[:n])]
        needed=set(map(int,A[keep].indices[A[keep].indices>=13]-13))
        needed.update(map(int,p['bounds'][~safe[n:]]));needed=np.array(sorted(needed),dtype=int)
        selected=np.sort(np.r_[keep,p['eq'][needed]]);cols=np.r_[np.arange(13),13+needed]
        B=A[selected][:,cols].tocsr();sd=dict(d)
        for k in ('names','lower','upper','types','objective'):sd[k]=d[k][cols]
        for k in ('rhs','sense','row_names'):sd[k]=d[k][selected]
        sp.save_npz(dest/'SELECTED.npz',B);np.savez_compressed(dest/'SELECTED_DOMAIN.npz',**sd)
        np.savez_compressed(dest/'MAP.npz',rows=selected,columns=cols,safe=safe,dominant=dominant)
        total+=B.shape[0];nnz+=B.nnz;variables+=len(needed)
    receipt=dict(PASS=True,tag=tag,slots=96,rows=total,nonzeros=nnz,auxiliary_variables=variables,
        variable_AIDC_controls=12,PF_fixed=.95,all_unresolved_rows_retained=True,
        fixed_B0_screen_reused=False,Native_optimize_calls=0,records=rows,
        domain_P_bounds=p_bounds.tolist(),MESS_parameter_sha=digest(mess.tolist()),new_domain_rho_witness=witness,
        independent_removal_verifier_PASS=False,Native0_monolithic_PASS=False)
    (folder/'RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt
