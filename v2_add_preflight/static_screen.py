"""Pre-solver screening, retaining every unresolved original row.

Physical safety and the loading epigraph have DIFFERENT proofs. A safety
bound can never delete an objective face. Objective removal requires an
implication from a retained full-grid face and the physical control domain.
All transformations occur before Native MILP construction, without a solver.
"""
import time, types, threading, re
from collections import Counter
import numpy as np
import scipy.sparse as sp
import psutil
from .static_common import *
from .static_pack import PACK,N_AUX
from . import may01_compact as historical

CACHE=RUN/'screen'
load=types.FunctionType(historical.load.__code__,dict(historical.load.__globals__,PACK=PACK))
projection=types.FunctionType(historical.projection.__code__,dict(historical.projection.__globals__,load=load))

def interval(x,*,independent=False):
    H=x['H'];box=np.r_[np.full(24,300.),np.full(24,250.)]
    term=300*abs(H[:,:24]).toarray()+250*abs(H[:,24:48]).toarray()
    s=(np.sort(term,axis=1)[:,-8:].sum(axis=1) if independent else np.partition(term,16,axis=1)[:,16:].sum(axis=1))
    rho=np.asarray(H[:,48].toarray()).ravel()
    lower=-s+np.minimum(rho,0);upper=s+np.maximum(rho,0)
    A=x['A'];r=x['rows'];d=x['domain'];C=x['C'];a=x['a']
    n=len(x['original_inequalities']);lo=A.shape[1]-96*N_AUX+x['slot']*N_AUX
    non=x['original_inequalities'];E=abs(A[non,lo+48:lo+N_AUX]);assert np.diff(E.indptr).max(initial=0)<=3
    components=abs(A[non,lo:lo+48])@box+E@(abs(C)@box)+E@abs(a)+abs(r['rhs'][non])
    eps=np.finfo(float).eps;gamma=100*eps/(1-100*eps)
    budgets=[gamma*(1+components)]
    for which,bound in [(np.flatnonzero(np.isfinite(d['upper'][48:])),d['upper'][48:]),
                        (np.flatnonzero(np.isfinite(d['lower'][48:])),d['lower'][48:])]:
        budgets.append(gamma*(1+abs(C[which])@box+abs(a[which])+abs(bound[which])))
    error=np.nextafter(np.concatenate(budgets),np.inf)
    # Gamma100 covers the <=48 controls, <=3 original auxiliary terms,
    # RHS subtraction, support sum and outward arithmetic, including cancellation.
    error+=1e-12*(1+np.maximum(abs(lower),abs(upper)))
    return np.nextafter(lower-error,-np.inf),np.nextafter(upper+error,np.inf),rho,error

def prepare():
    res=init();start=time.perf_counter();CACHE.mkdir(exist_ok=True);peak=[0];done=threading.Event()
    def sample():
        while not done.wait(.1):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
    ma=sp.load_npz(PACK/'MOBILITY.npz');nbase=ma.shape[1]
    domain=historical.verify_port_domain(ma,md)
    put('STATIC_M1_CONTROL_DOMAIN.json',dict(**domain,
        LP_relaxation_valid=True,LP_reason='Each connected STAY occupancy is <=1, summed across eight unit flows <=8. Fractional occupancy maximizes linear nonnegative site support by taking eight largest rectangular supports.',
        applies_to='Fixed B0 AIDC M1 only; not A1/A2 or changed A2 anchor'))
    receipts=[]
    try:
        for t in range(96):
            guard(start);p=CACHE/f'{t:02d}';p.mkdir(exist_ok=True)
            if (p/'RECEIPT.json').exists():receipts.append(read(p/'RECEIPT.json'));continue
            while not (PACK/f'{t:02d}'/'RECEIPT.json').exists():guard(start);time.sleep(3)
            x=projection(t,nbase);x['slot']=t
            lower,upper,rho,error=interval(x);objective=np.char.startswith(x['families'].astype(str),'parent_line_thermal_face')
            assert np.all(rho[objective]<0) and np.all(rho[~objective]==0)
            margin=1e-7*(1+abs(x['rhs']))
            safe=(upper<=x['rhs']-margin)&~objective
            low=np.full(len(lower),-np.inf);low[objective]=(lower[objective]-rho[objective]*1.-x['rhs'][objective])/(-rho[objective])
            # interval lower includes rho*[0,1]; remove rho contribution to get
            # the minimum controls-only side of a physical epigraph inequality.
            low=np.nextafter(low,-np.inf);w=int(np.argmax(low));L=float(low[w])
            sp.save_npz(p/'RECONSTRUCTION.npz',x['C']);np.save(p/'CONSTANT.npy',x['a'])
            np.savez_compressed(p/'PROOF.npz',lower=lower,upper=upper,rho=rho,error=error,rhs=x['rhs'],
                margin=margin,objective=objective,safe=safe,inequality_ids=x['original_inequalities'],
                families=x['families'],definitions=x['definitions'])
            rr=dict(slot=t,raw_rows=x['A'].shape[0],raw_nnz=x['A'].nnz,
                controls_only_rho_lower_bound=L,witness_projected_row=w,witness_original_id=str(x['ids'][w]),
                safe_physical_rows=int(safe.sum()),proof=record(p/'PROOF.npz'),
                reconstruction=record(p/'RECONSTRUCTION.npz'),constant=record(p/'CONSTANT.npy'))
            (p/'RECEIPT.json').write_text(__import__('json').dumps(rr,indent=2),encoding='utf-8');receipts.append(rr)
            put('STATIC_SCREEN_PROGRESS.json',dict(completed=t+1,wall_seconds=time.perf_counter()-start))
            if t%4==0:print('STATIC SCREEN',t,'safe',safe.sum(),'rho lower',L,flush=True)
            del x
        witness=max(receipts,key=lambda r:r['controls_only_rho_lower_bound']);L=max(0.,witness['controls_only_rho_lower_bound'])
        families=Counter();totals=Counter();blocks=[]
        for t in range(96):
            guard(start);p=CACHE/f'{t:02d}';A,d,r=load(t);lo=nbase+t*N_AUX
            with np.load(p/'PROOF.npz') as z:q={k:z[k] for k in z.files}
            # Control-only maximum removes the maximum rho contribution (0).
            # A retained witness implies rho>=L for every feasible control,
            # so these faces follow for the LP as well as the integer domain.
            dominant=q['objective']&(q['upper']<=q['rhs']-q['rho']*L-q['margin'])
            safe=q['safe'];non=q['inequality_ids'];n=len(non)
            keep_non=non[~(safe[:n]|dominant[:n])]
            needed=set(map(int,A[keep_non].indices[A[keep_non].indices>=lo]-lo))
            # Unsafe eliminated-variable bounds must remain literal Native
            # bounds with their exact defining equalities.
            bound_ids=[]
            for which,side in [(np.flatnonzero(np.isfinite(d['upper'][48:]))+48,'upper'),
                               (np.flatnonzero(np.isfinite(d['lower'][48:]))+48,'lower')]:
                bound_ids.extend(map(int,which))
            bound_ids=np.asarray(bound_ids,dtype=int)
            needed.update(map(int,bound_ids[~safe[n:]]));needed.update(range(48))
            needed=np.asarray(sorted(needed),dtype=int)
            eq=np.flatnonzero(r['sense']=='=');assert len(eq)==N_AUX
            keep_rows=np.sort(np.r_[eq[needed],keep_non])
            cls=np.full(A.shape[0],'UNRESOLVED',dtype='<U20')
            cls[eq]='EXACT_SUBSTITUTION';cls[keep_rows]='RETAIN'
            cls[non[safe[:n]]]='SAFE_REMOVE';cls[non[dominant[:n]]]='EXACT_REDUNDANT'
            np.savez_compressed(p/'STATIC_SELECTION.npz',rows=keep_rows,variables=needed,
                classification=cls,safe_bounds=safe[n:],bound_variables=bound_ids,dominant=dominant,
                rho_lower_bound=L)
            for fam in np.unique(q['families'][:n]):
                mask=q['families'][:n]==fam
                families[str(fam),'before']+=int(mask.sum())
                families[str(fam),'after']+=int((mask&~(safe[:n]|dominant[:n])).sum())
                families[str(fam),'safe']+=int((mask&safe[:n]).sum())
                families[str(fam),'dominant']+=int((mask&dominant[:n]).sum())
            c=Counter(map(str,cls));totals.update(c)
            rr=dict(slot=t,rows=len(keep_rows),nonzeros=A[keep_rows].nnz,variables=len(needed),
                classification=dict(c),selection=record(p/'STATIC_SELECTION.npz'))
            blocks.append(rr)
        table('FULL_CONSTRAINT_FAMILY_BEFORE_AFTER.csv',[
            dict(family=f,before_rows=families[f,'before'],after_rows=families[f,'after'],
                SAFE_REMOVE=families[f,'safe'],EXACT_REDUNDANT=families[f,'dominant'])
            for f in sorted({f for f,k in families})]+[
                dict(family='MOBILITY_ALL_UNCHANGED',before_rows=ma.shape[0],after_rows=ma.shape[0],SAFE_REMOVE=0,EXACT_REDUNDANT=0)])
        put('IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json',dict(PASS=True,scope='Source-YY fixed-B0 AIDC M1',
            source_case=record(OUT/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json'),
            classification=dict(totals),all_unresolved_rows_retained=True,
            objective_ampacity_conflation=False,objective_implication_witness=witness,implied_global_rho_lower_bound=L,
            LP_domain_implication=True,Native_calls=0,no_post_solver_additions=True,
            blocks=blocks,wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0],resources=res,
            A1_A2_and_M2_fixed_A2_proofs_PASS=False))
        print('STATIC SCREEN COMPLETE',dict(totals),'rho lower',L,flush=True)
    finally:done.set();th.join(1)

if __name__=='__main__':prepare()
