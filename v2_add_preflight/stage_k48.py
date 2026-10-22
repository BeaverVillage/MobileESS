"""Source K48 representation adapter, with independent exact original Geometry.

This module changes coordinates and positive dyadic equality scales only.
It neither selects a new constraint family nor changes source quota/pricing.
Streaming per-slot admission keeps the original 20M-row authority off heap.
"""
from fractions import Fraction as F
import re
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_pack import PACK, N_AUX
from .prestart_native import native_zero

def slot_view(t, md=None):
    if md is None:
        with np.load(PACK/'MOBILITY_DOMAIN.npz') as z: md={k:z[k] for k in z.files}
    nbase=len(md['names']); lo=nbase+t*N_AUX
    raw=sp.load_npz(PACK/f'{t:02d}/MATRIX.npz')
    # Exact coordinate permutation: local block follows the original mobility.
    A=sp.hstack((raw[:,:nbase],raw[:,lo:lo+N_AUX]),format='csr')
    with np.load(PACK/f'{t:02d}/DOMAIN.npz') as z:vd={k:z[k] for k in z.files}
    with np.load(PACK/f'{t:02d}/ROWS.npz') as z:r={k:z[k] for k in z.files}
    d=dict(names=np.r_[md['names'],vd['names']].astype(object),lower=np.r_[md['lower'],vd['lower']],
        upper=np.r_[md['upper'],vd['upper']],types=np.r_[md['types'],vd['types']],
        objective=np.r_[md['objective'],np.zeros(N_AUX)],constant=np.asarray(0.),
        rhs=r['rhs'].copy(),sense=r['sense'].copy(),row_names=r['local_names'].astype(object))
    original=A.copy(); scales=np.ones(A.shape[0]); eq=np.flatnonzero(d['sense']=='=')
    assert len(eq)==N_AUX
    for ordinal,i in enumerate(eq):
        a,b=A.indptr[i:i+2]
        if ordinal<48:
            js=A.indices[a:b]; own=js[(js>=nbase)&(js<nbase+48)]
            assert len(own)==1;j=int(own[0]);k=j-nbase
            site=('IDC' if k%24<12 else 'STA')+f'{k%12+1:02d}'
            family='injection_P' if k<24 else 'injection_Q'
            axis=f'{site},{t}'
        else:
            j=nbase+ordinal;k=ordinal
            family='response_'+str(d['names'][j]).split('[',1)[0].rsplit('_',1)[0]
            axis=f'{t},{k}'
        pos=np.flatnonzero(A.indices[a:b]==j);assert len(pos)==1
        pivot=float(A.data[a+pos[0]]);assert pivot>0 and np.frexp(pivot)[0]==.5
        scales[i]=1/pivot;A.data[a:b]*=scales[i];d['rhs'][i]*=scales[i]
        assert np.array_equal(A.data[a:b]*pivot,original.data[a:b])
        assert d['rhs'][i]*pivot==r['rhs'][i]
        d['names'][j]=f'{family}[{axis}]';d['row_names'][i]=f'{family}_binding[{axis}]'
    # Recover Native's exact positive row scales BEFORE source row ranking.
    # In particular every thermal face must have literal rho coefficient -1,
    # as assumed by original prepare_k16 and the signed Beam score context.
    axes=read(OUT/'SOURCE_YY_GRID_AXES.json');security=np.flatnonzero(axes['security_mask'])
    port=np.array([i for i,v in enumerate(axes['transformer_current']) if v['winding']==2 and
        v['element'].lower().startswith(('transformer.high_mv_sta','transformer.full_mobile_idc'))])
    with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:
        reference={'line_both_end_current':z['line_J'][24:,security].T,
            'transformer_all_winding_current':z['tc_J'][24:].T,'mobile_port_current':z['tc_J'][24:,port].T}
    physical=np.ones(A.shape[0]);rho=int(np.flatnonzero(md['objective'])[0])
    for family,J in reference.items():
        ids=np.flatnonzero(np.char.startswith(r['local_names'].astype(str),family+'_'))
        assert len(ids)==len(J)
        observed=original[ids,nbase:nbase+48].toarray()
        for k,i in enumerate(ids):
            nz=np.flatnonzero(J[k])
            if len(nz):physical[i]=observed[k,nz[0]]/J[k,nz[0]]
        assert np.array_equal(observed,J*physical[ids,None])
    for i,name in enumerate(r['local_names']):
        s=str(name)
        if s.startswith('parent_line_thermal_face'):
            physical[i]=-float(original[i,rho])
        elif s.startswith(('transformer_nameplate_face','mobile_port_kVA_face')):
            m=re.fullmatch(r'(transformer_nameplate|mobile_port_kVA)_face(\d+)_00\[(\d+)\]',s);assert m
            f,j=int(m[2]),int(m[3]);co,si=np.cos(2*np.pi*f/16),np.sin(2*np.pi*f/16)
            if m[1]=='transformer_nameplate':col=nbase+(27119 if abs(co)>=abs(si) else 30724)+j
            else:col=nbase+(0 if abs(co)>=abs(si) else 24)+j
            physical[i]=float(original[i,col])/(co if abs(co)>=abs(si) else si)
    assert np.all(physical>0) and np.all(np.frexp(physical)[0]==.5)
    factor=1/physical;A.data*=np.repeat(factor,np.diff(A.indptr));d['rhs']*=factor;scales*=factor
    # Exhaustive bit-exact inverse, including coefficients far below Gurobi's
    # parser floor. This view is read-only and is not sent back to Native.
    assert np.array_equal(A.data/np.repeat(scales,np.diff(A.indptr)),original.data)
    assert np.array_equal(d['rhs']/scales,r['rhs'])
    # Names expose the original physical family/asset/phase grammar; no
    # objective, NormalAmps or port row is removed from this authority view.
    for i,n in enumerate(r['local_names']):
        s=str(n)
        m=re.fullmatch(r'parent_line_thermal_face(\d+)_00\[(\d+)\]',s)
        if m:d['row_names'][i]=f'line_thermal_face[{t},{m[2]},{m[1]}]';continue
        m=re.fullmatch(r'transformer_nameplate_face(\d+)_00\[(\d+)\]',s)
        if m:d['row_names'][i]=f'transformer_kVA[{t},{6156+int(m[2])},{m[1]}]';continue
        m=re.fullmatch(r'mobile_port_kVA_face(\d+)_00\[(\d+)\]',s)
        if m:d['row_names'][i]=f'transformer_kVA[{t},{6156+3605+int(m[2])},{m[1]}]';continue
        if d['sense'][i]!='=':
            m=re.fullmatch(r'(line_both_end_current|transformer_all_winding_current|mobile_port_current)_00\[(\d+)\]',s);assert m,s
            k=int(m[2]);family=m[1]
            if family=='line_both_end_current':
                axis=axes['line'][security[k]];asset=axis['element'];phase=str(axis['physical_phase'])
            else:
                axis=axes['transformer_current'][port[k] if family=='mobile_port_current' else k]
                asset=axis['element']+'/W'+str(axis['winding'])+('/port600' if family=='mobile_port_current' else '')
                phase='node'+str(axis['node'])+'_conductor'+str(axis['conductor'])
            d['row_names'][i]=f'NormalAmps[{t},{asset}::{phase}]'
    # Source projection/pricing enumerates voltage inequalities, whereas the
    # raw producer encodes these as helper bounds. Add the exact same bounds
    # as read-only authority rows; the Native model keeps its original bounds.
    ids=np.flatnonzero(np.isfinite(vd['upper']))
    assert len(ids)==8603 and np.array_equal(ids,np.arange(48,48+8603))
    B=sp.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),nbase+ids)),shape=(len(ids),A.shape[1]))
    names=np.array([f'voltage_upper[{t},{k}]' for k in range(len(ids))]+[f'voltage_lower[{t},{k}]' for k in range(len(ids))],dtype=object)
    d['rhs']=np.r_[d['rhs'],vd['upper'][ids],vd['lower'][ids]]
    d['sense']=np.r_[d['sense'],np.full(len(ids),'<'),np.full(len(ids),'>')]
    d['row_names']=np.r_[d['row_names'],names]
    A=sp.vstack((A,B,B),format='csr')
    return A,d,dict(slot=t,original_rows=raw.shape[0],bound_view_rows=2*len(ids),
        all_original_nonzeros=raw.nnz,unit_helper_pivots=len(eq),
        coefficient_RHS_roundtrip_exact=True,Native_changed=False,
        physical_inequality_scales_exactly_inverted=True,nontrivial_inequality_scales=int(np.sum(physical!=1)),
        raw_component=record(PACK/f'{t:02d}/MATRIX.npz'))

def certify():
    from v44.frozen.v43_mess.library import load
    with measured('K48_WHOLE96_INTERFACE_CERTIFICATION.json') as (report,start), native_zero() as denied:
        k=load()['table_v_k48'];rows=[]
        with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={a:z[a] for a in z.files}
        physical=np.flatnonzero([str(n).split('[',1)[0] in k.PHYSICAL or n=='rho_max' for n in md['names']])
        counts={};cuts=[]
        for t in range(96):
            guard(start);A,d,proof=slot_view(t,md)
            folder=WORK/'M1/view'/f'{t:02d}';folder.mkdir(parents=True,exist_ok=True)
            sp.save_npz(folder/'A.npz',A)
            local={k:d[k][len(md['names']):] for k in ('names','lower','upper','types','objective')}
            local.update({k:d[k] for k in ('row_names','rhs','sense')})
            for name in ('names','row_names'):local[name]=local[name].astype(str)
            np.savez_compressed(folder/'D.npz',**local)
            proof.update(view_matrix=record(folder/'A.npz'),view_domain=record(folder/'D.npz'),producer=record(__file__))
            g=k.original_oracle.Geometry(A,d)
            independent=k.independent.Geometry(A,k.independent.canonical_data(d))
            assert len(g.definitions)==N_AUX and g.definitions==independent.definitions
            selected=[]
            for fam in k.FAMILIES:
                ids=[i for i,n in enumerate(d['row_names']) if str(n).startswith(fam+'[')]
                assert ids;counts[fam]=counts.get(fam,0)+len(ids)
                # Beginning, middle, end exercise real axes and all families;
                # helper constructors above inspect EVERY defining equation.
                selected.extend(ids[x] for x in sorted({0,len(ids)//2,len(ids)-1}))
            for i in selected:
                rhs,const,terms=independent.security(i)
                if not terms:
                    assert rhs>=0,'INFEASIBLE_CONSTANT_PHYSICAL_ROW'
                    continue # Source exact_cut is only called for violated rows;
                    # a valid constant row cannot enter its pricing candidates.
                cut=k.exact_cut(A,d,i,physical,g)
                assert str(rhs)==cut['exact_rhs'] and str(const)==cut['helper_constant']
                assert {str(j):str(v) for j,v in sorted(terms.items())}==cut['original_terms']
                assert cut['source_row_sha']==k.independent.original_row_sha(A,k.independent.canonical_data(d),i)
                # Independently replay source outward coefficient rounding.
                error=F(0)
                for j,v in terms.items():
                    delta=F(float(v))-v;error+=max(delta*F(float(d['lower'][j])),delta*F(float(d['upper'][j])))
                assert str(error)==cut['coefficient_box_error']
                assert F(cut['native_rhs'])==F(k.independent.upward(rhs+error))*F(cut['native_row_scale'])
                if str(d['row_names'][i]).startswith('line_thermal_face'):
                    cuts.append(dict(slot=t,name=cut['name'],source_row_sha=cut['source_row_sha']))
            rows.append(dict(**proof,independent_all_helper_definitions_PASS=True,exact_security_cuts=len(selected)))
            (folder/'COMMITTED.json').write_text(json.dumps(rows[-1]),encoding='utf-8')
            put('STAGE_K48_PROGRESS.json',dict(completed=t+1,wall_seconds=__import__('time').perf_counter()-start))
            if t%8==0:print('STAGE K48 WHOLE96',t,flush=True)
        report.update(PASS=False,representation_all96_PASS=True,records=rows,
            independent_security_cuts=sum(r['exact_security_cuts'] for r in rows),security_family_rows=counts,
            dual_scale_contract='view_row = raw_row / positive_pivot; raw_dual = view_dual / positive_pivot; exact dyadic identity',
            equality_LP_and_integer_domain_unchanged=True,all_original_rows_and_helper_bounds_represented=True,
            K16_K32_K48_solver_calls=0,Global_LB=None,denied_attempts=denied,
            scope='Whole96 representation and independent symbolic admission. Global source packet/pricing execution binding is a separate required test.',
            whole_case_packet_binding_PASS=False,original_algorithm_edited=False)

if __name__=='__main__':certify()
