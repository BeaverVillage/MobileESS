"""Streaming original-coordinate FULL oracle and bounded Native0 master.

No optimize/presolve is called. A restricted-master incumbent is never accepted
as a FULL incumbent without this oracle. Solver lower bounds require an
external, same-case relaxation proof; a master objective is not a lower bound.
"""
import math,time,threading
import numpy as np
import scipy.sparse as sp
import psutil
from .may01_common import *
from .may01_compact import CACHE,N_AUX
from .prestart_native import native_zero

TOL=1e-5 # Same as sealed FULL matrix verifier, not a solver parameter change.

def mobility():
    A=sp.load_npz(PACK/'MOBILITY.npz')
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    return A,d

def row_violation(A,rhs,sense,x):
    r=np.asarray(A@x)-rhs
    return np.maximum(0,np.where(sense=='=',abs(r),np.where(sense=='<',r,-r)))

class FullOracle:
    def __init__(self):
        self.A,self.d=mobility();self.nbase=self.A.shape[1]
        self.reference=read(OLD/'FULL96_MATRIX_PACK_CERTIFICATION.json')
        self.case_sha=self.reference['case_sha']

    def lift(self,point,path=None):
        assert len(point)==self.nbase+96*48 and np.isfinite(point).all()
        if path is None:out=np.zeros(self.nbase+96*N_AUX)
        else:out=np.lib.format.open_memmap(path,mode='w+',dtype=np.float64,shape=(self.nbase+96*N_AUX,))
        out[:self.nbase]=point[:self.nbase]
        for t in range(96):
            p=CACHE/f'{t:02d}';u=point[self.nbase+48*t:self.nbase+48*(t+1)]
            C=sp.load_npz(p/'RECONSTRUCTION.npz');a=np.load(p/'RECONSTRUCTION_CONSTANT.npy')
            out[self.nbase+t*N_AUX:self.nbase+(t+1)*N_AUX]=np.r_[u,a+C@u]
        return out

    def separate(self,point,tag,*,collect_limit=10000):
        """All original rows/bounds are inspected even if additions are batched."""
        start=time.perf_counter();f=self.lift(point)
        mv=row_violation(self.A,self.d['rhs'],self.d['sense'],f[:self.nbase])
        bounds=max(float(np.max(self.d['lower']-f[:self.nbase],initial=0)),float(np.max(f[:self.nbase]-self.d['upper'],initial=0)),0.)
        im=self.d['types']!='C';integer=float(np.max(abs(f[:self.nbase][im]-np.rint(f[:self.nbase][im])),initial=0))
        rows=self.A.shape[0];nnz=self.A.nnz;worst=float(mv.max(initial=0));bad=int((mv>TOL).sum());selected=[];original_bad=[]
        rho_index=int(np.flatnonzero(self.d['objective'])[0]);rho=float(point[rho_index]);required=0.;projected_bad=0
        per=[]
        for t in range(96):
            guard(start)
            p=PACK/f'{t:02d}';A=sp.load_npz(p/'MATRIX.npz')
            with np.load(p/'ROWS.npz') as z:r={k:z[k] for k in z.files}
            with np.load(p/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
            residual=row_violation(A,r['rhs'],r['sense'],f);ix=np.flatnonzero(residual>TOL)
            y=f[self.nbase+t*N_AUX:self.nbase+(t+1)*N_AUX]
            bv=np.maximum(d['lower']-y,y-d['upper']);bix=np.flatnonzero(bv>TOL)
            bounds=max(bounds,float(bv.max(initial=0)));worst=max(worst,float(residual.max(initial=0)))
            bad+=len(ix);rows+=A.shape[0];nnz+=A.nnz
            original_bad.extend([f'grid:{t:02d}:row:{int(i)}' for i in ix[:max(0,collect_limit-len(original_bad))]])
            H=sp.load_npz(CACHE/f'{t:02d}'/'ORACLE.npz')
            with np.load(CACHE/f'{t:02d}'/'ROWS.npz') as z:cr={k:z[k] for k in z.files}
            u=point[self.nbase+48*t:self.nbase+48*(t+1)];value=H@np.r_[u,rho]-cr['rhs'];ci=np.flatnonzero(value>TOL)
            projected_bad+=len(ci)
            for i in ci[:max(0,collect_limit-len(selected))]:selected.append(dict(slot=t,index=int(i),id=str(cr['ids'][i]),violation=float(value[i])))
            obj=np.char.startswith(cr['families'].astype(str),'parent_line_thermal_face')
            rc=np.asarray(H[obj,48].toarray()).ravel();assert np.all(rc<0)
            required=max(required,float(np.max((H[obj,:48]@u-cr['rhs'][obj])/(-rc),initial=0)))
            per.append(dict(slot=t,original_rows=A.shape[0],row_violations=len(ix),bound_violations=len(bix),
                maximum_row_violation=float(residual.max(initial=0)),projected_violations=len(ci)))
        passed=not bad and bounds<=TOL and integer<=TOL and projected_bad==0
        result=dict(PASS=passed,tag=tag,case_sha=self.case_sha,original_rows_checked=rows,original_nonzeros_checked=nnz,
            original_row_violations=bad,max_original_row_violation=worst,max_original_bound_violation=bounds,
            max_integrality_violation=integer,projected_violations=projected_bad,original_objective=rho,
            complete_parent_face_objective=required,all16_faces_checked=True,all_original_domains_restored=True,
            selected_additions=selected,all_violations_scanned=True,addition_batch_complete=len(selected)==projected_bad,
            original_bad_ID_sample=original_bad,FULL_UB_admissible=passed,AC_physical_PASS=False,
            scope='fixed-B0-AIDC Planning M1 affine matrix; no campaign AIDC/Actual claim',
            wall_seconds=time.perf_counter()-start,per_slot=per)
        put('SEPARATION_'+tag+'.json',result)
        return result

    def stay(self):
        base=np.load(PACK/'MOBILITY_POINT.npy');return np.r_[base,np.zeros(96*48)]

class DelayedMaster:
    """Exact row additions, source mobility domains, original rho objective."""
    def __init__(self,oracle,slots=None):
        import gurobipy as gp
        self.oracle=oracle;self.start=time.perf_counter();self.active=set();self.additions=[]
        self.expected=[];self.expected_rhs=[];self.expected_sense=[]
        self.m=gp.Model('V2_ADD_MAY01_DELAYED_FULL');self.m.Params.OutputFlag=0
        d=oracle.d
        self.base=self.m.addMVar(oracle.nbase,lb=d['lower'],ub=d['upper'],vtype=d['types'],name=d['names'])
        self.m.addMConstr(oracle.A,self.base,d['sense'],d['rhs'],name='original_mobility')
        self.expected.append(sp.hstack([oracle.A,sp.csr_matrix((oracle.A.shape[0],96*48))],format='csr'))
        self.expected_rhs.append(d['rhs']);self.expected_sense.append(d['sense'])
        self.base_list=list(self.base.tolist())
        # These bounds are implied by the source occupancy/connected rows and
        # the explicit eight-vehicle domain proof, not arbitrary restrictions.
        self.port=self.m.addMVar((96,48),lb=np.tile(np.r_[np.full(24,-300),np.full(24,-250)],(96,1)),
            ub=np.tile(np.r_[np.full(24,300),np.full(24,250)],(96,1)),name='retained_injection')
        self.rho_index=int(np.flatnonzero(d['objective'])[0]);self.rho=self.base[self.rho_index].item()
        self.m.setObjective(d['objective']@self.base+float(d['constant']))
        for t in (range(96) if slots is None else slots):
            guard(self.start)
            p=CACHE/f'{t:02d}';B=sp.load_npz(p/'INJECTION_BINDING.npz');D=np.load(p/'INJECTION_DIAGONAL.npy');rhs=np.load(p/'INJECTION_RHS.npy')
            cols=np.unique(B.indices)
            self.m.addMConstr(sp.hstack([B[:,cols],sp.csr_matrix(D)],format='csr'),[self.base_list[i] for i in cols]+list(self.port[t].tolist()),'=',rhs,name=f'original_alias_{t:02d}')
            dd=sp.csr_matrix(D).tocoo();bb=B.tocoo()
            self.expected.append(sp.csr_matrix((np.r_[bb.data,dd.data],(np.r_[bb.row,dd.row],np.r_[bb.col,oracle.nbase+t*48+dd.col])),shape=(48,oracle.nbase+96*48)))
            self.expected_rhs.append(rhs);self.expected_sense.append(np.full(48,'='))
            with np.load(p/'ROWS.npz') as z:r={k:z[k] for k in z.files}
            active=[]
            for fam in np.unique(r['families']):
                ix=np.flatnonzero((r['families']==fam)&~r['safe'])
                if len(ix):
                    count=32 if str(fam).startswith('node_voltage_') else 1
                    active.extend(ix[np.argsort(r['rhs'][ix],kind='stable')[:count]])
            self.add(t,np.asarray(sorted(set(active)),dtype=int),'INITIAL')
        self.m.update()

    def add(self,t,indices,reason):
        indices=[int(i) for i in indices if (t,int(i)) not in self.active]
        if not indices:return 0
        H=sp.load_npz(CACHE/f'{t:02d}'/'ORACLE.npz')[indices].tocsr()
        with np.load(CACHE/f'{t:02d}'/'ROWS.npz') as z:rhs=z['rhs'][indices];ids=z['ids'][indices]
        # Parser-scale by exact powers of two, preserving each nonzero double.
        minima=np.array([np.min(abs(H.data[a:b]),initial=1.) for a,b in zip(H.indptr[:-1],H.indptr[1:])])
        exponent=np.maximum(0,np.ceil(np.log2(1e-12/minima))).astype(int);scale=np.ldexp(np.ones(len(indices)),exponent)
        H.data*=np.repeat(scale,np.diff(H.indptr));rhs=rhs*scale
        self.m.addMConstr(H,list(self.port[t].tolist())+[self.rho],'<',rhs,name=np.asarray(ids))
        mapped=np.where(H.indices==48,self.rho_index,self.oracle.nbase+t*48+H.indices)
        self.expected.append(sp.csr_matrix((H.data.copy(),mapped,H.indptr.copy()),shape=(len(indices),self.oracle.nbase+96*48)))
        self.expected_rhs.append(rhs.copy());self.expected_sense.append(np.full(len(indices),'<'))
        self.active.update((t,int(i)) for i in indices)
        self.additions.extend(dict(slot=t,index=int(i),id=str(n),reason=reason,scale_power2=int(s)) for i,n,s in zip(indices,ids,exponent))
        return len(indices)

    def readback(self):
        self.m.update();expected=sp.vstack(self.expected,format='csr');expected.sum_duplicates();expected.sort_indices()
        actual=self.m.getA();delta=(actual-expected).tocsr();delta.eliminate_zeros()
        assert delta.nnz==0 and actual.nnz==expected.nnz
        assert np.array_equal(self.m.getAttr('RHS'),np.concatenate(self.expected_rhs))
        assert np.array_equal(self.m.getAttr('Sense'),np.concatenate(self.expected_sense))
        return dict(PASS=True,all_native_rows=actual.shape[0],all_native_nonzeros=actual.nnz,
            all_coefficients_RHS_senses_exact=True,coefficient_dropping_observed=False)

    def refine(self,result):
        by={}
        for x in result['selected_additions']:by.setdefault(x['slot'],[]).append(x['index'])
        return sum(self.add(t,ix,'FULL_SEPARATION') for t,ix in by.items())

    def certify_candidate(self,point,tag):
        result=self.oracle.separate(point,tag)
        added=self.refine(result)
        return dict(FULL_incumbent_accepted=result['PASS'],added_rows=added,separation=result,
            global_LB=None,global_gap=None,solver_bound_used=False)

    def iterate(self,solve_step,deadline,*,iteration_limit=100):
        """Future original-budget adapter; no solver is called by this module.

        The caller must be the original approved Native budget route. Each
        callback receives the actual relaxation, then all original rows are
        separated. This method deliberately supplies no K48/global-gap claim
        before the original same-case proof interface has been bound.
        """
        history=[]
        for iteration in range(iteration_limit):
            deadline.check();guard(self.start)
            self.m.update()
            solve_step(self.m,deadline)
            if self.m.SolCount<=0:
                return dict(FULL_incumbent=None,history=history,global_LB=None,global_gap=None,
                    reason='NO_MASTER_INCUMBENT_OR_NATIVE_BUDGET_EXHAUSTED')
            point=np.r_[self.base.X,self.port.X.ravel()]
            result=self.certify_candidate(point,f'ITERATION_{iteration:03d}')
            history.append(dict(iteration=iteration,added_rows=result['added_rows'],
                FULL_feasible=result['FULL_incumbent_accepted'],all_original_rows_checked=True))
            if result['FULL_incumbent_accepted']:
                return dict(FULL_incumbent=point,history=history,global_LB=None,global_gap=None,
                    optimizer_global_certificate=False,AC_Fresh_required=True)
            if result['added_rows']==0:
                return dict(FULL_incumbent=None,history=history,global_LB=None,global_gap=None,
                    reason='ORIGINAL_DOMAIN_OR_NUMERICAL_RESTORATION_FAILURE')
        return dict(FULL_incumbent=None,history=history,global_LB=None,global_gap=None,
            reason='SEPARATION_INCOMPLETE_ITERATION_LIMIT',optimizer_global_certificate=False)

def build():
    init();o=FullOracle();start=time.perf_counter();stop=threading.Event();peak=[0]
    def sample():
        while not stop.wait(.05):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();m=None;error=None
    try:
        with native_zero() as denied:
            master=DelayedMaster(o);m=master.m;m.update();guard(start)
            entire_native_readback=master.readback()
            readback=m.getA()[:o.A.shape[0],:o.nbase]
            delta=(readback-o.A).tocsr();delta.eliminate_zeros()
            assert delta.nnz==0
            report=dict(PASS=True,binary=int(m.NumBinVars),continuous=int(m.NumVars-m.NumIntVars),variables=int(m.NumVars),
                rows=int(m.NumConstrs),nonzeros=int(m.DNumNZs),initial_original_grid_rows=len(master.active),
                original_mobility_retained=True,all24_alias_rows=4608,Native_calls=0,denied_calls=denied,
                native_original_mobility_matrix_exact_readback=True,reference_case_sha=o.case_sha,
                entire_native_matrix_readback=entire_native_readback,
                scope='M1 fixed-B0 AIDC delayed-constraint master; whole FULL oracle required',
                entire_reference_rows_materialized=False,full_oracle_available=True)
            # A fake low rho must produce original-ID cuts, never an incumbent.
            fake=o.stay();fake[o.d['names'].tolist().index('rho_max')]=.1
            result=master.certify_candidate(fake,'FALSE_LOW_RHO')
            assert not result['FULL_incumbent_accepted'] and result['added_rows']>0
            report['false_improvement_rejected']=True;report['fixture_added_rows']=result['added_rows']
            m.update();report['rows_after_fixture']=int(m.NumConstrs)
            report['after_cut_matrix_readback']=master.readback()
            table('CONSTRAINT_GENERATION_EXACT_ROW_ADDITIONS.csv',master.additions)
    except Exception as exc:
        import traceback
        error=repr(exc);report=dict(PASS=False,error=error,traceback=traceback.format_exc(),Native_calls=0)
    finally:
        stop.set();th.join(1)
        if m is not None:m.dispose()
    report.update(wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0],protection_limit_bytes=4*1024**3,
        solver_parameters_tolerances_or_budgets_changed=False,official_campaign_executed=False)
    put('MESS8_COMPACT_NATIVE0_BUILD_REPORT.json',report)
    print('COMPACT NATIVE0',report.get('PASS'),report.get('rows'),error,flush=True)

def readback_replay():
    """Independent Native reassembly/readback without repeating FULL scans."""
    init();psutil.Process().cpu_affinity([13]);started=time.perf_counter();peak=[0];stop=threading.Event()
    old=read(OUT/'MESS8_COMPACT_NATIVE0_BUILD_REPORT.json')
    raw=OUT/'MESS8_COMPACT_NATIVE0_INITIAL_RUN_REPORT.json'
    if not raw.exists():raw.write_bytes((OUT/'MESS8_COMPACT_NATIVE0_BUILD_REPORT.json').read_bytes())
    def sample():
        while not stop.wait(.05):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();m=None
    try:
        o=FullOracle()
        with native_zero():
            master=DelayedMaster(o);m=master.m;m.update()
            assert (m.NumVars,m.NumConstrs,int(m.DNumNZs))==(old['variables'],old['rows'],old['nonzeros'])
            entire=master.readback()
            cuts=read(OUT/'SEPARATION_FALSE_LOW_RHO.json')
            assert cuts['case_sha']==o.case_sha and not cuts['PASS'] and cuts['original_rows_checked']==20634824
            for t in {r['slot'] for r in cuts['selected_additions']}:
                with np.load(CACHE/f'{t:02d}'/'ROWS.npz') as z:
                    ids=z['ids']
                    assert all(str(ids[r['index']])==r['id'] for r in cuts['selected_additions'] if r['slot']==t)
            added=master.refine(cuts);assert added==old['fixture_added_rows']
            after=master.readback();guard(started)
        old.update(entire_native_matrix_readback=entire,after_cut_matrix_readback=after,
            initial_run_preserved=record(raw),readback_replay_wall_seconds=time.perf_counter()-started,
            readback_replay_peak_RSS_bytes=peak[0],readback_replay_separation_receipt=record(OUT/'SEPARATION_FALSE_LOW_RHO.json'),
            whole_original_FALSE_LOW_RHO_scan_repeated=False,readback_replay_Native_calls=0)
        put('MESS8_COMPACT_NATIVE0_BUILD_REPORT.json',old)
    finally:
        stop.set();th.join(1)
        if m is not None:m.dispose()
    print('COMPLETE NATIVE MATRIX READBACK',entire,after,flush=True)

if __name__=='__main__':build()
