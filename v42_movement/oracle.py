"""Factored exact dyadic elimination and certified interval PCS supports.

The exact object is the original coefficient DAG, not a rounded dense matrix.
Expanded dense coefficients carry lower/upper enclosures. All bounds use the
lower enclosure; midpoint coefficients are never scientific authorities.
"""
from .common import *
import re,time
import numpy as np
from fractions import Fraction as F
from collections import defaultdict
from v42_degen.identity import inputs,digest
from v42_strengthening.analysis import graph_inputs
from v42_disjunctive.certificate import down,up

def lower(x):return np.nextafter(x,-np.inf)
def upper(x):return np.nextafter(x,np.inf)
def mul(lo,hi,a,b):
    return lower(np.minimum(np.minimum(lo*a,lo*b),np.minimum(hi*a,hi*b))),upper(np.maximum(np.maximum(lo*a,lo*b),np.maximum(hi*a,hi*b)))

def polygon_vertices(normals,mode):
    """Exact dyadic halfspace intersections, including mode-specific P bounds."""
    rows=[tuple(F(float(x)) for x in r) for r in normals]
    rows += [(F(1),F(0),F(300 if mode==0 else 0)),(F(-1),F(0),F(0 if mode==0 else 300)),
             (F(0),F(1),F(400)),(F(0),F(-1),F(400))]
    points=set()
    for i,(a,b,h) in enumerate(rows):
        for c,d,k in rows[i+1:]:
            det=a*d-b*c
            if not det:continue
            p=(h*d-b*k)/det;q=(a*k-h*c)/det
            if all(u*p+v*q<=w for u,v,w in rows):points.add((p,q))
    assert points and all(any(a*p+b*q==h for a,b,h in rows) for p,q in points)
    return sorted(points)

def local_polygon(B,e,sites,initial):
    names=list(map(str,e['names']));index={n:j for j,n in enumerate(names)};template=None;group=[];groups=0
    for i in np.flatnonzero(e['row_names']=='PCS16'):
        a,b=B.indptr[i:i+2];row=dict(zip(map(int,B.indices[a:b]),map(float,B.data[a:b])))
        pq=[j for j in row if names[j].startswith(('Q[','Pch[','Pdis['))];assert pq
        u,s,t=names[pq[0]].split('[',1)[1][:-1].split(',');t=int(t);j=index[f'Q[{u},{s},{t}]']
        pch=next(k for k in row if names[k]==f'Pch[{u},{s},{t}]') if any(names[k]==f'Pch[{u},{s},{t}]' for k in row) else None
        pdis=next(k for k in row if names[k]==f'Pdis[{u},{s},{t}]') if any(names[k]==f'Pdis[{u},{s},{t}]' for k in row) else None
        ys=[k for k in row if names[k].startswith('arc[')];assert len(ys)==1
        assert names[ys[0]]==f'arc[{u},{sites.index(s)*96+t}]' and e['sense'][i]=='<' and e['rhs'][i]==0
        p=row.get(pdis,0.);assert row.get(pch,0.)==-p
        assert set(row)<=set([j,ys[0],pch,pdis])
        group.append((p,row.get(j,0.),-row[ys[0]]))
        if len(group)==16:
            candidate=np.asarray(group)
            if template is None:template=candidate
            assert np.array_equal(candidate,template),'LOCAL_PCS_PAYLOAD_DRIFT'
            group=[];groups+=1
    assert groups==8942 and not group
    for n,lo,hi in zip(names,e['lower'],e['upper']):
        if n.startswith(('Pch[','Pdis[')):assert lo==0 and hi==300
        if n.startswith('Q['):assert lo==-400 and hi==400
    # Verify every original local connected/mode inequality as a signed row.
    index={n:j for j,n in enumerate(names)};counts=defaultdict(int)
    prefixes={'connected_Pch':'Pch','connected_Pdis':'Pdis','connected_Qmax':'Q','connected_Qmin':'Q',
              'no_simultaneous_charge':'Pch','no_simultaneous_discharge':'Pdis'}
    for i in range(B.shape[0]):
        family=str(e['row_names'][i])
        if family not in prefixes:continue
        a,b=B.indptr[i:i+2];row=dict(zip(map(int,B.indices[a:b]),map(float,B.data[a:b])))
        js=[j for j in row if names[j].startswith(prefixes[family]+'[')];assert len(js)==1
        j=js[0];u,s,t=names[j].split('[',1)[1][:-1].split(',');t=int(t)
        if family.startswith('connected_'):
            y=index[f'arc[{u},{sites.index(s)*96+t}]'];limit=300 if prefixes[family]!='Q' else 400
            expected={j:1.,y:-float(limit)};rhs=0.;sense='<'
            if family=='connected_Qmin':expected={j:1.,y:400.};sense='>'
        else:
            mode=index[f'charge_mode[{u},{t}]'];expected={j:1.,mode:-300. if family.endswith('charge') and not family.endswith('discharge') else 300.}
            rhs=0. if family=='no_simultaneous_charge' else 300.;sense='<'
        assert row==expected and e['rhs'][i]==rhs and e['sense'][i]==sense,(family,i)
        counts[family]+=1
    assert all(counts[f]==8942 for f in prefixes)
    return template,dict(groups=groups,local_rows=dict(counts),all_PQ_bounds_exact=True)

def decompose(B,e,sites):
    names=list(map(str,e['names']));rho=names.index('rho_max');R=np.asarray(B[:,rho].nonzero()[0],dtype=np.int64)
    assert len(R)==402433 and all(e['row_names'][R]=='line_thermal_face')
    bindings={};native_binding_rows=[];injections={};injection_rows=[]
    for j,n in enumerate(names):
        if n.startswith('injection_'):
            fam,args=n.split('[',1);s,t=args[:-1].split(',');injections[j]=(int(t),sites.index(s)*2+(fam=='injection_Q'))
    # Exact Pdis-Pch / Q mappings; all eliminated leaf expressions verified.
    for i in np.flatnonzero(np.char.endswith(e['row_names'].astype(str),'_binding')):
        a,b=B.indptr[i:i+2];row=dict(zip(map(int,B.indices[a:b]),map(float,B.data[a:b])))
        outputs=[j for j in row if names[j].startswith(('response_','injection_'))]
        if str(e['row_names'][i]).startswith('injection_'):
            assert len(outputs)==1;out=outputs[0];assert row[out]==1 and e['rhs'][i]==0 and e['sense'][i]=='='
            t,k=injections[out];s=sites[k//2]
            for j,c in row.items():
                if j==out:continue
                fam,args=names[j].split('[',1);u,s2,t2=args[:-1].split(',');assert s2==s and int(t2)==t
                assert (fam,c) in ([('Q',-1.)] if k%2 else [('Pch',1.),('Pdis',-1.)])
            injection_rows.append(int(i));continue
        if not str(e['row_names'][i]).startswith('response_'):continue
        out=[j for j in outputs if names[j].startswith('response_')];assert len(out)==1
        out=out[0];scale=row.pop(out);assert abs(scale)==1 and e['sense'][i]=='='
        # These exact operations are only sign changes, so no rounding occurs.
        constant=float(e['rhs'][i]/scale);coeff={j:-c/scale for j,c in row.items()}
        assert all(j in injections for j in coeff)
        assert all(scale*v+row[j]==0 for j,v in coeff.items())
        assert scale*constant==e['rhs'][i]
        t=int(names[out].split('[',1)[1].split(',')[0]);assert all(injections[j][0]==t for j in coeff)
        vec=np.zeros(2*len(sites))
        for j,c in coeff.items():vec[injections[j][1]]=c
        bindings[out]=(constant,vec,t,int(i));native_binding_rows.append(int(i))
    n=len(R);cl=np.zeros((n,2*len(sites)));ch=cl.copy();bl=np.zeros(n);bh=bl.copy();times=np.full(n,-1,dtype=np.int16)
    factor_out=[];factor_values=[];factor_indptr=[0]
    for k,i in enumerate(R):
        a,b=B.indptr[i:i+2];row=dict(zip(map(int,B.indices[a:b]),map(float,B.data[a:b])))
        assert e['sense'][i]=='<' and row.pop(rho)==-1.
        bl[k]=bh[k]=-e['rhs'][i]
        for j,c in row.items():
            assert j in bindings,'UNEXPECTED_UNCHANGED_TERM'
            const,vec,t,_=bindings[j];assert times[k] in (-1,t);times[k]=t
            vlow,vhigh=mul(vec,vec,c,c);cl[k]=lower(cl[k]+vlow);ch[k]=upper(ch[k]+vhigh)
            l,h=mul(const,const,c,c);bl[k]=lower(bl[k]+l);bh[k]=upper(bh[k]+h)
            factor_out.append(j);factor_values.append(c)
        factor_indptr.append(len(factor_out))
    # Exact reconstruction is in factored form: all original epigraph terms
    # and all binding factors are retained verbatim. Dense enclosures are not
    # claimed to equal a rounded symbolic expansion.
    np.savez_compressed(OUT/'GRID_EPIGRAPH_ROW_COEFFICIENTS.npz',rows=R,times=times,coefficient_lower=cl,coefficient_upper=ch,
                        fixed_lower=bl,fixed_upper=bh,factor_indptr=np.asarray(factor_indptr),factor_columns=np.asarray(factor_out),factor_values=np.asarray(factor_values),
                        binding_rows=np.asarray(native_binding_rows),injection_rows=np.asarray(injection_rows),rho_column=np.asarray(rho),native_rhs=e['rhs'][R],sites=np.asarray(sites))
    write('GRID_EPIGRAPH_ROW_DECOMPOSITION.json',dict(PASS=True,exact_reconstruction_PASS=True,rows=n,
          every_rho_linked_row_extracted=True,no_unchanged_non_grid_terms=True,bindings_checked=len(bindings),injection_bindings_checked=len(injection_rows),
          exact_representation='Native dyadic factored DAG: g_r=-RHS_r+sum_j native_face_coefficient_j * (binding_RHS_j/scale_j - sum_k binding_coefficient_k/scale_j * injection_k). Each injection is exactly sum(Pdis-Pch) or sum(Q).',
          reconstruction='Each binding output scale is +/-1. Sign inversion reproduces every original coefficient/RHS exactly, not within a tolerance. Substitution is formal over dyadic rationals. All original face coefficients are retained verbatim. Empty constant row retained.',
          expanded_coefficients='Certified IEEE outward lower/upper enclosures of the exact factored rational expression; not rounded coefficient identities.',
          native_model_signature=read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['reference'],
          coefficient_archive_SHA=sha(OUT/'GRID_EPIGRAPH_ROW_COEFFICIENTS.npz'),full_M1_optimize_calls=0))
    return R,times,cl,ch,bl,bh

def run():
    gate('support_oracle');begin=time.perf_counter()
    assert read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['PASS']
    _,_,B,e,*_=inputs();sites,initial,arcs,battery,receipt=graph_inputs()
    normals,local=local_polygon(B,e,sites,initial)
    vertices_by_mode=[polygon_vertices(normals,m) for m in (0,1)]
    vertices=sorted(set(sum(vertices_by_mode,[])))
    vl=np.asarray([[down(p),down(q)] for p,q in vertices]);vh=np.asarray([[up(p),up(q)] for p,q in vertices])
    R,t,cl,ch,bl,bh=decompose(B,e,sites)
    phi_lo=np.full((len(R),len(sites)),np.inf);phi_hi=phi_lo.copy()
    for i in range(len(vertices)):
        pl,ph=mul(cl[:,0::2],ch[:,0::2],vl[i,0],vh[i,0]);ql,qh=mul(cl[:,1::2],ch[:,1::2],vl[i,1],vh[i,1])
        phi_lo=np.minimum(phi_lo,lower(pl+ql));phi_hi=np.minimum(phi_hi,upper(ph+qh))
    assert np.all(phi_lo<=phi_hi) and np.all(phi_lo<=0)
    reachable=np.zeros((len(initial),96,len(sites)),bool);names=set(map(str,e['names']))
    for m,u in enumerate(initial):
        for ti in range(96):
            for si,s in enumerate(sites):reachable[m,ti,si]=f'Pch[{u},{s},{ti}]' in names
    psi_lo=np.zeros((len(R),len(initial)));psi_hi=psi_lo.copy()
    for m in range(len(initial)):
        for ti in range(96):
            ix=np.flatnonzero(t==ti);available=np.flatnonzero(reachable[m,ti])
            # Transit zero included in every relaxation, including no sites.
            if len(available):
                psi_lo[ix,m]=np.minimum(0,np.min(phi_lo[np.ix_(ix,available)],axis=1))
                psi_hi[ix,m]=np.minimum(0,np.min(phi_hi[np.ix_(ix,available)],axis=1))
    rowlo=bl.copy();rowhi=bh.copy()
    for m in range(len(initial)):rowlo=lower(rowlo+psi_lo[:,m]);rowhi=upper(rowhi+psi_hi[:,m])
    global_lb=float(np.max(rowlo));assert global_lb<=BASE_LB+1e-8,'UNEXPLAINED_SUPPORT_ABOVE_ROOT_STOP'
    np.savez_compressed(OUT/'PCS_GRID_SUPPORT_VALUES.npz',rows=R,times=t,phi_lower=phi_lo,phi_upper=phi_hi,
                        psi_lower=psi_lo,psi_upper=psi_hi,row_lower=rowlo,row_upper=rowhi,reachable=reachable,
                        vertex_lower=vl,vertex_upper=vh,native_normals=normals,units=np.asarray(list(initial)))
    write('PCS_GRID_SUPPORT_ORACLE_PROOF.json',dict(PASS=True,original_local_payload_audit=local,
          native_normals_SHA=digest(normals),vertices_by_mode=[len(v) for v in vertices_by_mode],
          exact_vertices=[dict(P=[str(p.numerator),str(p.denominator)],Q=[str(q.numerator),str(q.denominator)]) for p,q in vertices],
          proof=['With connected=1 and mode=0, Pch=0, P=Pdis in [0,300]. With mode=1, Pdis=0, P=-Pch in [-300,0]. Original Q bounds and 16 native dyadic PCS faces complete each bounded polygon.',
                 'Every pairwise nonparallel boundary intersection is enumerated with Fraction exact arithmetic and retained only if every rational halfspace holds. A linear functional attains its minimum at one of these vertices.',
                 'Removing SOC, travel energy, route and cross-time coupling enlarges the feasible set. The resulting minimum is optimistic and cannot overestimate any feasible local contribution.',
                 'phi_lower <= exact minimum <= phi_upper follows outward multiplication/addition of coefficient and rational-vertex enclosures. min sites and transit zero preserves this ordering.'],
          exact_local_support_method='Two original integer modes, exact rational native polygon vertex enumeration; evaluated with certified outward interval arithmetic.',
          new_physical_limits=False,full_M1_optimize_calls=0,conditional_full_LP_calls=0,support_archive_SHA=sha(OUT/'PCS_GRID_SUPPORT_VALUES.npz')))
    r=int(np.argmax(rowlo));write('GRID_SUPPORT_GLOBAL_LB.json',dict(PASS=True,L_support_global=global_lb,
          responsible_reduced_row=int(R[r]),responsible_slot=int(t[r]),exact_support_global_upper=float(np.max(rowhi)),
          L0=BASE_LB,below_root_reference=global_lb<=BASE_LB+1e-8,comparison_tolerance=1e-8,
          formula='max_r [fixed_r + sum_m min(0,min_reachable_sites phi_rms)]',
          proof='For any feasible integer trajectory each unit contributes either zero in transit or a connected-site local feasible P/Q. Each contribution is >= optimistic site/mode support. Summing and taking max of original epigraph inequalities gives a global lower bound.',
          runtime_seconds=time.perf_counter()-begin,full_M1_optimize_calls=0,conditional_full_LP_calls=0))
    print('SUPPORT_DONE',len(R),global_lb,time.perf_counter()-begin,flush=True)
if __name__=='__main__':run()
