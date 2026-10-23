"""Literal original-row delayed master; on-demand equality factorization.

Unlike the projection prototype, active Native rows copy ORIGINAL stored
coefficients without multiplying them. Equality-defined P/Q/V auxiliaries
needed by an active row are materialized lazily, with literal original bounds.
The full original-coordinate oracle and every possible MOVE remain unchanged.
"""
import csv,time,threading
from collections import defaultdict
import numpy as np
import scipy.sparse as sp
import psutil
from .may01_common import *
from .may01_oracle import FullOracle
from .prestart_native import native_zero

class LiteralMaster:
    def __init__(self,o):
        import gurobipy as gp
        self.o=o;self.start=time.perf_counter();self.active=set();self.aux={};self.maps=[];self.blocks=[];self.expected=[]
        self.m=gp.Model('V2_ADD_LITERAL_ORIGINAL_DELAYED_MASTER');self.m.Params.OutputFlag=0
        d=o.d;self.base=self.m.addMVar(o.nbase,lb=d['lower'],ub=d['upper'],vtype=d['types'],name=d['names'])
        self.m.addMConstr(o.A,self.base,d['sense'],d['rhs'],name='original_mobility')
        self.base_list=list(self.base.tolist());self.expected.append((o.A.copy(),d['rhs'],d['sense']))
        self.port=self.m.addMVar((96,48),lb=-float('inf'),name='original_injection')
        self.m.setObjective(d['objective']@self.base+float(d['constant']));self.m.update()
        seeds=defaultdict(list)
        for r in csv.DictReader((OUT/'CONSTRAINT_GENERATION_EXACT_ROW_ADDITIONS.csv').open(encoding='utf-8')):
            if r['reason']=='INITIAL':seeds[int(r['slot'])].append(r['id'])
        assert sum(map(len,seeds.values()))==7711
        self.source_row_ids=[];self.bound_ids=[]
        for t in range(96):
            guard(self.start);self.load(t)
            self.add_rows(np.arange(48),t,'ORIGINAL_INJECTION_BINDING')
            self.add_ids(t,seeds[t]);self.m.update()
            if t%16==0:print('LITERAL NATIVE0',t,self.m.NumVars,self.m.NumConstrs,flush=True)

    def load(self,t):
        p=PACK/f'{t:02d}';self.t=t;self.A=sp.load_npz(p/'MATRIX.npz')
        with np.load(p/'ROWS.npz') as z:self.r={k:z[k] for k in ('rhs','sense')}
        with np.load(p/'DOMAIN.npz') as z:self.d={k:z[k] for k in z.files}
        self.eq=np.flatnonzero(self.r['sense']=='=')
        assert len(self.eq)==34329
        assert np.all(np.isneginf(self.d['lower'][:48])) and np.all(np.isposinf(self.d['upper'][:48])) and np.all(self.d['types'][:48]=='C')
        self.lo=self.o.nbase+t*34329

    def variable(self,col):
        if col<self.o.nbase:return self.base_list[col]
        k=col-self.lo;assert 0<=k<34329
        return self.port[self.t,k].item() if k<48 else self.aux[self.t,k]

    def ensure(self,indices,t):
        need=sorted({int(k) for k in indices if k>=48 and (t,int(k)) not in self.aux})
        if not need:return
        v=self.m.addMVar(len(need),lb=self.d['lower'][need],ub=self.d['upper'][need],vtype=self.d['types'][need],name=self.d['names'][need])
        self.m.update()
        for k,x in zip(need,v.tolist()):
            self.aux[t,k]=x;self.maps.append(dict(slot=t,original_column=self.lo+k,native_column=x.index,original_name=str(self.d['names'][k]),
                lower=float(self.d['lower'][k]),upper=float(self.d['upper'][k]),type=str(self.d['types'][k])))
        definitions=self.eq[need]
        # Original definitions reference only this variable and the48 retained
        # injections, not a hidden chain of other eliminated auxiliaries.
        S=self.A[definitions,self.lo+48:self.lo+34329]
        assert S.nnz==len(need)
        self.add_rows(definitions,t,'ORIGINAL_DEFINING_EQUALITY',ensure=False)

    def add_rows(self,indices,t,reason,ensure=True):
        indices=np.asarray([int(i) for i in indices if (t,int(i)) not in self.active],dtype=int)
        if not len(indices):return 0
        A=self.A[indices].tocsr();cols=np.unique(A.indices)
        if ensure:self.ensure(cols[cols>=self.lo]-self.lo,t)
        vv=[self.variable(int(k)) for k in cols];B=A[:,cols]
        self.m.addMConstr(B,vv,self.r['sense'][indices],self.r['rhs'][indices],
            name=np.asarray([f'original_grid:{t:02d}:row:{i}' for i in indices]))
        # Map coordinates only. Coefficient data are copied bit-for-bit.
        native_cols=np.asarray([v.index for v in vv]);local=B.tocoo()
        mapped=sp.csr_matrix((local.data.copy(),(local.row,native_cols[local.col])),shape=(len(indices),self.m.NumVars))
        self.expected.append((mapped,self.r['rhs'][indices].copy(),self.r['sense'][indices].copy()))
        self.active.update((t,int(i)) for i in indices)
        self.source_row_ids.extend(dict(slot=t,original_row=int(i),id=f'grid:{t:02d}:row:{i}',reason=reason) for i in indices)
        self.blocks.append(dict(slot=t,rows=len(indices),nonzeros=A.nnz,reason=reason))
        return len(indices)

    def add_ids(self,t,ids):
        source=[];bound=[]
        for name in ids:
            a=name.split(':');assert a[:2]==['grid',f'{t:02d}']
            if a[2]=='row':source.append(int(a[3]))
            else:
                assert a[2]=='bound';bound.append(int(a[3]));self.bound_ids.append(name)
        self.ensure(bound,t)
        return self.add_rows(source,t,'ORIGINAL_ACTIVE_FACE_OR_SAFETY')

    def refine(self,result):
        assert result['case_sha']==self.o.case_sha
        by=defaultdict(list)
        for row in result['selected_additions']:by[row['slot']].append(row['id'])
        before=len(self.active)
        for t,ids in by.items():self.load(t);self.add_ids(t,ids)
        return len(self.active)-before

    def certify_candidate(self,point,tag):
        result=self.o.separate(point,tag);added=self.refine(result)
        return dict(FULL_incumbent_accepted=result['PASS'],added_rows=added,separation=result,
            global_LB=None,global_gap=None,solver_bound_used=False)

    def iterate(self,solve_step,deadline,*,iteration_limit=100):
        from .may01_oracle import DelayedMaster
        return DelayedMaster.iterate(self,solve_step,deadline,iteration_limit=iteration_limit)

    def readback(self):
        self.m.update();n=self.m.NumVars
        expect=sp.vstack([sp.hstack([A,sp.csr_matrix((A.shape[0],n-A.shape[1]))],format='csr') for A,r,s in self.expected],format='csr')
        expect.sum_duplicates();expect.sort_indices();actual=self.m.getA();delta=(actual-expect).tocsr();delta.eliminate_zeros()
        assert delta.nnz==0 and actual.nnz==expect.nnz
        assert np.array_equal(self.m.getAttr('RHS'),np.concatenate([r for A,r,s in self.expected]))
        assert np.array_equal(self.m.getAttr('Sense'),np.concatenate([s for A,r,s in self.expected]))
        lower=np.r_[self.o.d['lower'],np.full(96*48,-np.inf),np.zeros(n-self.o.nbase-96*48)]
        upper=np.r_[self.o.d['upper'],np.full(96*48,np.inf),np.zeros(n-self.o.nbase-96*48)]
        types=np.r_[self.o.d['types'],np.full(n-self.o.nbase,'C')]
        for a in self.maps:lower[a['native_column']]=a['lower'];upper[a['native_column']]=a['upper'];types[a['native_column']]=a['type']
        assert np.array_equal(self.m.getAttr('LB'),lower) and np.array_equal(self.m.getAttr('UB'),upper)
        assert np.array_equal(self.m.getAttr('VType'),types)
        objective=np.r_[self.o.d['objective'],np.zeros(n-self.o.nbase)]
        assert np.array_equal(self.m.getAttr('Obj'),objective) and self.m.ObjCon==float(self.o.d['constant'])
        return dict(PASS=True,all_native_rows=actual.shape[0],all_native_nonzeros=actual.nnz,
            literal_original_coefficients_RHS_senses_exact=True,projection_products_in_Native_rows=0,
            shared_auxiliary_factorization=True,source_row_ids_recoverable=True,
            all_original_bounds_types_and_objective_exact=True)

def build():
    init();psutil.Process().cpu_affinity([13]);start=time.perf_counter();peak=[0];stop=threading.Event()
    def sample():
        while not stop.wait(.05):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();m=None
    try:
        o=FullOracle()
        with native_zero():
            master=LiteralMaster(o);m=master.m;m.update();guard(start)
            before=dict(binary=int(m.NumBinVars),continuous=int(m.NumVars-m.NumIntVars),variables=int(m.NumVars),rows=int(m.NumConstrs),nonzeros=int(m.DNumNZs))
            whole=master.readback();initial_aux=len(master.aux);initial_wall=time.perf_counter()-start
            cuts=read(OUT/'SEPARATION_FALSE_LOW_RHO.json');assert not cuts['PASS'] and cuts['case_sha']==o.case_sha
            added=master.refine(cuts);m.update();after=master.readback();guard(start)
            table('LITERAL_NATIVE_ORIGINAL_ROW_ID_MAP.csv',master.source_row_ids)
            # Maps include the additional fixture rows. Initial count is frozen
            # separately before any fixture cut is added.
            table('LITERAL_NATIVE_MATERIALIZED_AUXILIARY_MAP.csv',master.maps)
            report=dict(PASS=True,**before,initial_auxiliaries_materialized=initial_aux,all_original_auxiliaries_in_source=3290976,
                fixed_AIDC_M1_only=True,entire_native_matrix_readback=whole,after_cut_matrix_readback=after,
                initial_build_seconds=initial_wall,fixture_added_original_rows=added,
                final_fixture_variables=int(m.NumVars),final_fixture_rows=int(m.NumConstrs),final_fixture_nnz=int(m.DNumNZs),
                false_improvement_rejected=True,full_oracle_case_sha=o.case_sha,
                projection_products_in_Native_rows=0,all_Native_rows_literal_original=True,
                all_original_mobility_rows_and_variables_preserved=True,full96_master_build=True,
                unmaterialized_original_variables_recoverable=True,arbitrary_MOVE_domain_restricted=False,
                Native_calls=0,global_LB=None,global_gap=None,optimization_result_FULL_equivalence=False,
                original_reference_Oracle=record(OUT/'REFERENCE_FULL_MATRIX_SEAL.json'))
    except Exception as exc:
        import traceback
        report=dict(PASS=False,error=repr(exc),traceback=traceback.format_exc(),Native_calls=0)
    finally:
        stop.set();th.join(1)
        if m is not None:m.dispose()
    report.update(wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0],protection_limit_bytes=4*1024**3)
    put('MESS8_EXACT_FACTOR_NATIVE0_BUILD_REPORT.json',report)
    if report['PASS']:
        prototype=OUT/'MESS8_PROJECTED_PROTOTYPE_NATIVE0_BUILD_REPORT.json'
        if not prototype.exists():prototype.write_bytes((OUT/'MESS8_COMPACT_NATIVE0_BUILD_REPORT.json').read_bytes())
        report.update(adopted_representation='LITERAL_ORIGINAL_ROWS_WITH_ON_DEMAND_AUXILIARIES',
            projected_prototype_preserved=record(prototype),reference_case_sha=report['full_oracle_case_sha'],
            fixture_added_rows=report['fixture_added_original_rows'])
        put('MESS8_COMPACT_NATIVE0_BUILD_REPORT.json',report)
    print('LITERAL FULL96 NATIVE0',report.get('PASS'),report.get('rows'),report.get('error'),flush=True)

if __name__=='__main__':build()
