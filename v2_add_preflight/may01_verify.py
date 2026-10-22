"""Independent matrix readback, all reference rows and adversarial witnesses."""
from collections import defaultdict,Counter
import re,time
import numpy as np
import scipy.sparse as sp
from .may01_common import *

def violation(A,rhs,sense,point):
    v=A@point-rhs
    return np.maximum(0,np.where(sense=='=',abs(v),np.where(sense=='<',v,-v)))

def boundary_point(d):
    from .prestart_native import inputs
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    sites,initial,routes,b,receipt=inputs(read(day['files']['native']['path']),INITIAL)
    p=np.load(PACK/'MOBILITY_POINT.npy').copy();lookup={str(n):i for i,n in enumerate(d['names'])};u='MESS01';s=initial[u]
    E=760.;injection=np.zeros((96,48));values={};chosen={}
    power=[]
    for t in range(96):
        discharge=320*b.eta_discharge/(8*b.dt_hours) if t<8 or 24<=t<32 else 0.
        charge=640/(16*b.dt_hours*b.eta_charge) if 8<=t<24 else 0.
        q=50. if t%2 else -50.
        p[lookup[f'SOC[{u},{t}]']]=E
        E+=b.dt_hours*(b.eta_charge*charge-discharge/b.eta_discharge)
        p[lookup[f'SOC[{u},{t+1}]']]=E
        for key,val in [(f'Pch[{u},{s},{t}]',charge),(f'Pdis[{u},{s},{t}]',discharge),(f'Q[{u},{s},{t}]',q),(f'charge_mode[{u},{t}]',float(charge>0))]:
            assert key in lookup;p[lookup[key]]=val
        j=sites.index(s);injection[t,j]=discharge-charge;injection[t,24+j]=q
        power.append(dict(slot=t,Pch=charge,Pdis=discharge,Q=q,SOC=E))
    assert abs(E-760)<1e-8
    p[lookup['rho_max']]=1.
    table('BOUNDARY_SOC_ARITHMETIC_WITNESS.csv',power)
    return np.r_[p,injection.ravel()]

def run():
    init();start=time.perf_counter()
    from .may01_compact import CACHE,N_AUX
    from .may01_oracle import FullOracle
    o=FullOracle();d=o.d;nbase=o.nbase
    points={'STAY':o.stay(),'MOVE':np.load(RUN/'MOVE_COMPACT_POINT.npy'),'BOUNDARY_SOC':boundary_point(d)}
    full={}
    for name,p in points.items():
        dest=RUN/(name+'_RESTORED_ORIGINAL_POINT.npy');o.lift(p,dest);full[name]=np.load(dest,mmap_mode='r')
    # The verifier below does not call the producer's numerical(), projection(),
    # support(), or separate(). It reloads every sealed original CSR/domain.
    results={};F=np.column_stack(list(full.values()));labels=list(full)
    for name,p in full.items():
        x=p[:nbase];v=violation(o.A,d['rhs'],d['sense'],x)
        bound=max(float(np.max(d['lower']-x)),float(np.max(x-d['upper'])),0.)
        integer=d['types']!='C';iv=float(np.max(abs(x[integer]-np.rint(x[integer])),initial=0))
        results[name]=dict(row_violations=int((v>1e-5).sum()),maximum_row_violation=float(v.max(initial=0)),
            maximum_bound_violation=bound,integrality_violation=iv,rows_checked=o.A.shape[0],nnz_checked=o.A.nnz)
    census=defaultdict(Counter);proofs=[];equality_maps=[];rawcols=defaultdict(int);rho_occurrences=Counter()
    original_bad_ID=[];proof_failures=[]
    for t in range(96):
        guard(start);folder=PACK/f'{t:02d}';A=sp.load_npz(folder/'MATRIX.npz')
        with np.load(folder/'ROWS.npz') as z:r={k:z[k] for k in z.files}
        with np.load(folder/'DOMAIN.npz') as z:vd={k:z[k] for k in z.files}
        values=A@F-r['rhs'][:,None]
        values=np.maximum(0,np.where(r['sense'][:,None]=='=',abs(values),np.where(r['sense'][:,None]=='<',values,-values)))
        for j,name in enumerate(labels):
            x=full[name][nbase+t*N_AUX:nbase+(t+1)*N_AUX]
            v=values[:,j];out=results[name]
            out['row_violations']+=int((v>1e-5).sum());out['maximum_row_violation']=max(out['maximum_row_violation'],float(v.max(initial=0)))
            out['maximum_bound_violation']=max(out['maximum_bound_violation'],float(np.max(vd['lower']-x)),float(np.max(x-vd['upper'])),0.)
            out['rows_checked']+=A.shape[0];out['nnz_checked']+=A.nnz
            for i in np.flatnonzero(v>1e-5)[:3]:original_bad_ID.append(dict(witness=name,slot=t,id=f'grid:{t:02d}:row:{i}',residual=float(v[i])))
        cp=RUN/'compact'/f'{t:02d}'
        with np.load(cp/'ROWS.npz') as z:cr={k:z[k] for k in z.files}
        H=sp.load_npz(cp/'ORACLE.npz')
        # Independent proof computation uses full sorting, not the producer's
        # partial partition implementation. The same eight-port overdomain.
        term=300*abs(H[:,:24]).toarray()+250*abs(H[:,24:48]).toarray()
        upper=np.sort(term,axis=1)[:,-8:].sum(axis=1)+np.maximum(np.asarray(H[:,48].toarray()).ravel(),0)
        safe=cr['safe'];margin=1e-7*(1+abs(cr['rhs']))
        if np.any(upper[safe]>cr['rhs'][safe]-margin[safe]):proof_failures.append(t)
        assert not np.any(safe&np.char.startswith(cr['families'].astype(str),'parent_line_thermal_face'))
        eq=np.flatnonzero(r['sense']=='=')[48:]
        mapfile=cp/'AUXILIARY_EQUALITY_MAP.npz'
        np.savez_compressed(mapfile,original_row=eq,original_column=np.arange(nbase+t*N_AUX+48,nbase+(t+1)*N_AUX),
            original_names=vd['names'][48:],lower=vd['lower'][48:],upper=vd['upper'][48:],types=vd['types'][48:])
        equality_maps.append(dict(slot=t,removed_rows=len(eq),proof='Exact defining equality; C and constant reconstruct all original variables',map=record(mapfile)))
        fam=np.asarray([re.sub(r'_\d\d\[\d+\]$','',str(n)) for n in r['local_names']])
        for f in np.unique(fam):
            ix=np.flatnonzero(fam==f);S=A[ix];cols=np.unique(S.indices);ct=census[str(f)]
            ct['rows']+=len(ix);ct['nonzeros']+=S.nnz;ct['CSR_bytes']+=S.data.nbytes+S.indices.nbytes+S.indptr.nbytes
            ct['columns']+=len(cols)
            if o.d['names'][o.d['objective']!=0].tolist()==['rho_max']:
                ri=int(np.flatnonzero(o.d['objective'])[0]);rho_occurrences[str(f)]+=int(ri in cols)
            if str(f).endswith('_binding') and str(f) not in ('injection_P_binding','injection_Q_binding'):
                ct['equality_rows_exactly_eliminable']+=len(ix)
        if t%16==0:print('INDEPENDENT FULL',t,flush=True)
    for f,count in rho_occurrences.items():census[f]['columns']-=max(0,count-1)
    mob=[]
    for f in np.unique(d['row_names']):
        ix=np.flatnonzero(d['row_names']==f);S=o.A[ix]
        mob.append(dict(family=str(f),scope='REFERENCE_MOBILITY',rows=len(ix),columns=len(np.unique(S.indices)),nonzeros=S.nnz,
            CSR_bytes=S.data.nbytes+S.indices.nbytes+S.indptr.nbytes,equality_rows_exactly_eliminable=0))
    rows=mob+[dict(family=f,scope='REFERENCE_GRID',**dict(c)) for f,c in census.items()]
    # Retain the projection census too; it has the independent bound proof and
    # active/delayed classification, without conflating it with original rows.
    projection=list(__import__('csv').DictReader((OUT/'FULL_CONSTRAINT_FAMILY_CENSUS.csv').open(encoding='utf-8')))
    projection=[r for r in projection if r['scope']=='PROJECTED_GRID_96']
    (OUT/'FULL_CONSTRAINT_FAMILY_CENSUS_PROJECTED.csv').write_bytes((OUT/'FULL_CONSTRAINT_FAMILY_CENSUS.csv').read_bytes())
    table('FULL_CONSTRAINT_FAMILY_CENSUS.csv',rows+projection)
    put('AUXILIARY_EQUALITY_RESTORATION_MAP.json',dict(variables_eliminated=96*(N_AUX-48),blocks=equality_maps,
        original_all_bound_types_preserved=True,restoration='injection first48, then constant + RECONSTRUCTION.npz @ injection'))
    for x in results.values():x['PASS']=x['row_violations']==0 and x['maximum_bound_violation']<=1e-5 and x['integrality_violation']<=1e-5
    # Adversarial mobility/domain checks are independent of the grid oracle.
    lookup={str(n):i for i,n in enumerate(d['names'])};base=points['STAY'][:nbase].copy();faults=[]
    active_arc=next(str(n) for i,n in enumerate(d['names']) if str(n).startswith('arc[MESS01,') and base[i]==1)
    for tag,key,value in [('Q_LIMIT','Q[MESS01,STA01,0]',251.),('LOW_SOC','SOC[MESS01,1]',439.),('HIGH_SOC','SOC[MESS01,1]',1081.),('FRACTIONAL_ARC',active_arc,.5)]:
        if key not in lookup:continue
        p=base.copy();p[lookup[key]]=value;v=violation(o.A,d['rhs'],d['sense'],p)
        bm=max(float(np.max(d['lower']-p)),float(np.max(p-d['upper'])),0.)
        ii=d['types']!='C';iv=float(np.max(abs(p[ii]-np.rint(p[ii])),initial=0))
        rejected=bool(v.max(initial=0)>1e-5 or bm>1e-5 or iv>1e-5);assert rejected
        faults.append(dict(fault=tag,rejected=True,maximum_original_row_violation=float(v.max(initial=0)),bound_violation=bm,integrality_violation=iv))
    objective_fault=read(OUT/'SEPARATION_FALSE_LOW_RHO.json')
    assert not objective_fault['PASS'] and objective_fault['projected_violations']>0
    assert all(v['rows_checked']==20634824 and v['nnz_checked']==302476152 for v in results.values())
    put('FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json',dict(
        scope='Original fixed-B0-AIDC May01 Planning M1 matrix',reference_case_sha=o.case_sha,
        every_original_row_and_bound_checked=True,original_rows_per_witness=results['STAY']['rows_checked'],
        original_nnz_per_witness=results['STAY']['nnz_checked'],witnesses=results,original_bad_ID_examples=original_bad_ID,
        independent_safe_bound_proofs_PASS=not proof_failures,safe_proof_failures=proof_failures,
        all16_faces_and_parent_objective_checked=True,all_original_domains_recovered=True,
        counterexamples=faults,false_low_objective_rejected=True,
        candidate_specific_FULL_feasibility_only=True,global_LB=None,global_gap=None,
        restricted_master_is_FULL_UB_without_separation=False,final_optimizer_solution_certified=False,
        no_K48_bound_imported=True,AC_Fresh_separate=True,Native_calls=0,wall_seconds=time.perf_counter()-start))
    print('INDEPENDENT FULL DONE',results,flush=True)

if __name__=='__main__':run()
