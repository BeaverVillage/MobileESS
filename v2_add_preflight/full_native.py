"""Resource-bounded FULL96 Native0; original mobility and exact grid responses.

Response equalities are algebraic factorization, not row screening. Each
original parent line has 16 faces, both ends retain independent ampacity,
and every node and transformer winding is retained. No optimization call.
"""
import time,types,threading,math
from collections import Counter
import numpy as np
import scipy.sparse as sp
import psutil
from .full_common import *
from .prestart_native import inputs,original_solve,native_zero

def stats(m):
    m.update()
    return dict(binary=int(m.NumBinVars),integer=int(m.NumIntVars),continuous=int(m.NumVars-m.NumIntVars),
        variables=int(m.NumVars),linear_constraints=int(m.NumConstrs),nonzeros=int(m.DNumNZs),
        quadratic_constraints=int(m.NumQConstrs),SOS=int(m.NumSOS),general_constraints=int(m.NumGenConstrs))

class FullGrid:
    def __init__(self,started,*,one_slot_fixture=False):
        self.started=started;self.blocks=[];self.slots=[];self.equivalence=[]
        self.axes=read(OUT/'GRID_AXES.json')
        if one_slot_fixture:self.manifest={'records':[dict(slot=0,**record(RUN/'grid_text_pq/00.npz'))]}
        else:
            self.manifest=read(OUT/'GRID_COEFFICIENT_MANIFEST.json')
            assert self.manifest['coefficient_horizon_PASS'] and len(self.manifest['records'])==96
        self.parent=np.flatnonzero(self.axes['parent_mask']);self.security=np.flatnonzero(self.axes['security_mask'])
        self.cos=np.cos(2*np.pi*np.arange(16)/16);self.sin=np.sin(2*np.pi*np.arange(16)/16)

    def add(self,m,A,variables,sense,rhs,family,t):
        import gurobipy as gp
        guard(self.started);A=sp.csr_matrix(A);A.eliminate_zeros();A.sort_indices()
        rhs=np.asarray(rhs,dtype=float);assert A.shape==(len(rhs),len(variables))
        # Gurobi silently discards coefficients below1e-13. Never drop a finite
        # DSS derivative to accommodate that parser. A positive binary-power
        # row scaling preserves every double's mantissa and the exact feasible
        # halfspace, including the RHS. Ill-conditioning is reported separately.
        minima=np.ones(A.shape[0])
        for i in range(A.shape[0]):
            lo,hi=A.indptr[i:i+2]
            if hi>lo:minima[i]=np.abs(A.data[lo:hi]).min()
        exponents=np.maximum(0,np.ceil(np.log2(1e-12/minima))).astype(int)
        scale=np.ldexp(np.ones(len(rhs)),exponents)
        A.data*=np.repeat(scale,np.diff(A.indptr));rhs=rhs*scale
        assert np.isfinite(A.data).all() and np.isfinite(rhs).all()
        mc=m.addMConstr(A,list(variables),sense,rhs,name=f'{family}_{t:02d}');m.update()
        # Native readback uses independently retrieved rows/variables, not the
        # original scipy object. All rows remain in the actual Gurobi model.
        maxerr=0.
        for r in sorted({0,len(rhs)//2,len(rhs)-1}):
            c=mc[r].item();row=m.getRow(c)
            actual={row.getVar(j).index:row.getCoeff(j) for j in range(row.size())}
            expected={variables[j].index:float(v) for j,v in zip(A[r].indices,A[r].data)}
            if actual.keys()!=expected.keys():raise ValueError('NATIVE_MATRIX_AXIS_READBACK:'+str(dict(family=family,slot=t,row=r,missing=len(expected.keys()-actual.keys()),extra=len(actual.keys()-expected.keys()))))
            maxerr=max(maxerr,max([abs(actual[j]-v) for j,v in expected.items()]+[abs(c.RHS-rhs[r])]))
            assert c.Sense==sense
        assert maxerr<1e-10
        self.blocks.append(dict(slot=t,family=family,rows=A.shape[0],columns=A.shape[1],nonzeros=A.nnz,
            matrix_sha=digest(dict(indptr=sha(A.indptr.tobytes()),indices=sha(A.indices.tobytes()),values=sha(A.data.tobytes()),rhs=sha(rhs.tobytes()),sense=sense)),
            native_readback_rows=min(3,len(rhs)),native_readback_max_error=maxerr,
            positive_power2_scaled_rows=int(np.count_nonzero(exponents)),maximum_scale_exponent=int(exponents.max(initial=0)),
            maximum_absolute_coefficient=float(np.max(abs(A.data),initial=0))))
        return mc

    def response(self,m,x,J,y,family,t,lb=None,ub=None):
        import gurobipy as gp
        lo=-gp.GRB.INFINITY if lb is None else lb;hi=gp.GRB.INFINITY if ub is None else ub
        v=m.addMVar(len(y),lb=lo,ub=hi,name=f'{family}_{t:02d}');m.update();vv=list(v.tolist())
        A=sp.hstack([-sp.csr_matrix(J.T),sp.eye(len(y),format='csr')],format='csr')
        self.add(m,A,x+vv,'=',y,family+'_binding',t)
        return vv

    def build(self,m,p,q):
        import gurobipy as gp
        rho=m.addVar(lb=0,ub=1,name='rho_max');sites=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
        for t,rec in enumerate(self.manifest['records']):
            guard(self.started);path=Path(rec['path']);assert sha(path.read_bytes())==rec['sha256']
            with np.load(path) as z:a={k:z[k] for k in z.files}
            x=m.addMVar(48,lb=-gp.GRB.INFINITY,name=f'injection_{t:02d}');m.update();xx=list(x.tolist())
            for k,s in enumerate(sites):
                m.addConstr(xx[k]==p[s,t],name='injection_P_binding');m.addConstr(xx[24+k]==q[s,t],name='injection_Q_binding')
            # Fixed AIDC remains the original Planning B0 anchor for M1. A1/A2
            # require their own original C1 GPU affine controls, never this float.
            self.response(m,xx,a['v_J'][12:],a['v'],'node_voltage_squared',t,.95**2,1.05**2)
            sec=self.security
            self.add(m,a['line_J'][12:,sec].T,xx,'<',1-a['line'][sec],'line_both_end_current',t)
            self.add(m,a['tc_J'][12:].T,xx,'<',1-a['tc'],'transformer_all_winding_current',t)
            port=np.array([i for i,v in enumerate(self.axes['transformer_current']) if v['winding']==2 and
                v['element'].lower().startswith(('transformer.high_mv_sta','transformer.full_mobile_idc'))],dtype=int)
            assert len(port)==96
            # Dedicated600kVA/721.6878A port is distinct from750kVA winding.
            self.add(m,a['tc_J'][12:,port].T,xx,'<',.8-a['tc'][port],'mobile_port_current',t)
            eye24=sp.eye(24,format='csr')
            for f in range(16):
                self.add(m,sp.hstack([self.cos[f]*eye24,self.sin[f]*eye24],format='csr'),xx,'<',
                    np.full(24,600*math.cos(math.pi/16)),'mobile_port_kVA_face'+str(f),t)
            par=self.parent;ap=np.asarray(self.axes['line_phase_kVA'])[par]*math.cos(math.pi/16)
            assert np.all(ap>0)
            P=a['lp'][par];Q=a['lq'][par];JP=a['lp_J'][12:,par];JQ=a['lq_J'][12:,par]
            raw=(P[:,None]*self.cos+Q[:,None]*self.sin)/ap[:,None];active=raw.argmax(axis=1)
            corr=a['line_J'][12:,par]-(JP*self.cos[active]+JQ*self.sin[active])/ap
            bias=a['line'][par]-raw.max(axis=1)
            pv=self.response(m,xx,JP,P,'parent_line_P',t);qv=self.response(m,xx,JQ,Q,'parent_line_Q',t)
            cv=self.response(m,xx,corr,np.zeros(len(par)),'parent_line_current_correction',t)
            n=len(par);eye=sp.eye(n,format='csr');ones=sp.csr_matrix(-np.ones((n,1)))
            for f in range(16):
                A=sp.hstack([sp.diags(self.cos[f]/ap),sp.diags(self.sin[f]/ap),eye,ones],format='csr')
                self.add(m,A,pv+qv+cv+[rho],'<',-bias,'parent_line_thermal_face'+str(f),t)
            tvp=self.response(m,xx,a['tp_J'][12:],a['tp'],'transformer_winding_P',t)
            tvq=self.response(m,xx,a['tq_J'][12:],a['tq'],'transformer_winding_Q',t)
            n=len(tvp);eye=sp.eye(n,format='csr');ratings=np.asarray(self.axes['tx_kVA'])
            for f in range(16):
                self.add(m,sp.hstack([self.cos[f]*eye,self.sin[f]*eye],format='csr'),tvp+tvq,'<',ratings*math.cos(math.pi/16),'transformer_nameplate_face'+str(f),t)
            # Independent substitution check of all 16 original unfactored
            # faces at deterministic interior perturbations, every slot/row.
            worst=0.
            for seed in (1,2,3):
                dx=np.random.default_rng(100*t+seed).uniform(-3,3,48)
                for f in range(16):
                    direct=(self.cos[f]*(P+dx@JP)+self.sin[f]*(Q+dx@JQ))/ap+dx@corr+bias
                    combined=(self.cos[f]*P+self.sin[f]*Q)/ap+bias+dx@((self.cos[f]*JP+self.sin[f]*JQ)/ap+corr)
                    worst=max(worst,float(np.max(abs(direct-combined))))
            assert worst<1e-10
            self.equivalence.append(dict(slot=t,all_parent_rows=len(par),all_faces=16,substitutions=3,max_projection_error=worst))
            self.slots.append(t);current=stats(m)
            put('MESS8_FULL_NATIVE0_PROGRESS.json',dict(completed_grid_slots=len(self.slots),model=current,RSS_bytes=psutil.Process().memory_info().rss,wall_seconds=time.perf_counter()-self.started))
            if t%4==0:print('FULL NATIVE0 GRID',t,current['linear_constraints'],current['nonzeros'],flush=True)
        return [('rho',rho),('reserve_shortfall',0.)]

def build():
    init();res=resources();start=time.perf_counter();proc=psutil.Process();peak=[proc.memory_info().rss];done=threading.Event()
    def sample():
        while not done.wait(.1):peak[0]=max(peak[0],proc.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    grid=FullGrid(start);measured={};mobility={};route={};error=None;capture_reached=False
    bundle=read(day_input('2025-05-01')['files']['native']['path']);sites,initial,routes,battery,receipt=inputs(bundle,INITIAL)
    def hook(m,c):
        for u in initial:
            route[u]=dict(MOVE=sum(not isinstance(c.x[u,k],float) for k,a in enumerate(c.arcs) if a[-1] is not None),
                STAY=sum(not isinstance(c.x[u,k],float) for k,a in enumerate(c.arcs) if a[-1] is None))
    class Deadline:
        stage='M1'
        last_check=0.
        def check(self):
            now=time.perf_counter()
            if now-self.last_check>=.25:self.last_check=now;guard(start)
    def callback(m,p,q):
        import gurobipy as gp
        m.update()
        # Exact Source STAY-arc order, before grid construction so a resource
        # failure cannot leave this physical family absent from a partial build.
        for j,s in enumerate(sites):
            for t in range(96):
                vv=[m.getVarByName(f'arc[{u},{j*96+t}]') for u in initial]
                m.addConstr(gp.quicksum(v for v in vv if v is not None)<=1,name='all24_mobile_port_occupancy')
        mobility.update(stats(m))
        try:return grid.build(m,p,q)
        except BaseException:
            measured.update(stats(m));raise
    def capture(m,obj,*a,**kw):
        nonlocal capture_reached
        m.setObjective(obj[0][1])
        measured.update(stats(m));capture_reached=True
        return None,dict(Native_calls=0,Native_seconds=0.)
    with native_zero() as denied:
        try:
            fn=original_solve(capture)
            # Source size enumerates all row names; replacing this observer by
            # Num* attributes leaves construction/equations/domain unchanged.
            fn=types.FunctionType(fn.__code__,dict(fn.__globals__,size=stats),argdefs=fn.__defaults__,closure=fn.__closure__);fn.__kwdefaults__=original_solve(capture).__kwdefaults__
            fn('M1',Deadline(),sites,initial,routes,battery,96,callback,strengthening_hook=hook)
        except Exception as exc:error=repr(exc)
        finally:done.set();th.join(timeout=1)
    table('FULL_MATRIX_BLOCKS.csv',grid.blocks)
    if grid.equivalence:table('FULL_MATRIX_INDEPENDENT_PROJECTION.csv',grid.equivalence)
    full=bool(capture_reached and len(grid.slots)==96 and not error)
    put('MESS8_FULL_NATIVE0_REPORT.json',dict(status='FULL96_GRID_AND_MOBILITY_BUILT' if full else 'FULL_BUILD_BLOCKED_WITH_MEASURED_PARTIAL_MODEL',
        full96_Native0_build_PASS=full,independent_whole_FULL_matrix_domain_certificate=False,
        error=error,model=measured,mobility_before_grid=mobility,grid_slots=len(grid.slots),all24_occupancy_added=bool(mobility),
        objective_materialized_only_on_complete_build=capture_reached,
        counts_measured_not_projected=True,route_domain=receipt,reachable_by_unit=route,source=SOURCE,
        original24_services_retained=True,mobile_port_occupancy_rows=2304 if mobility else 0,
        source_mobility=record(ROOT/'v42_native/mess.py'),source_Q250=record(ROOT/'v44/q250_m4.py'),grid_coefficients=record(OUT/'GRID_COEFFICIENT_MANIFEST.json'),
        response_factorization='Lossless equality extension of source 16-face/current-correction equations; no constraint screening',
        physical_families=dict(Counter({f:sum(b['rows'] for b in grid.blocks if b['family']==f) for f in {b['family'] for b in grid.blocks}})),
        wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0],resources=res,Native_calls=0,denied_attempts=denied,
        K48_Beam_DirectJoint_connected=False,AIDC_variable_grid_connected=False,Actual_SVR3_rating_authority='Independent Actual/Fresh AC, separate from Planning S0'))
    print('FULL NATIVE0 DONE',full,error,measured,flush=True)

def fixture():
    import gurobipy as gp
    init();resources();g=FullGrid(time.perf_counter(),one_slot_fixture=True)
    m=gp.Model('V2_ADD_ONE_SLOT_GRID_FIXTURE');m.Params.OutputFlag=0
    sites=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
    p={(s,0):m.addVar(lb=-300,ub=300) for s in sites};q={(s,0):m.addVar(lb=-250,ub=250) for s in sites}
    error=None
    with native_zero():
        try:g.build(m,p,q)
        except Exception as exc:error=repr(exc)
        finally:
            put('ONE_SLOT_NATIVE0_GRID_FIXTURE.json',dict(PASS=error is None,error=error,model=stats(m),
                blocks=g.blocks,equivalence=g.equivalence,Native_calls=0,whole96_and_mobility_certified=False))
            m.dispose()
    print('NATIVE0 ONE SLOT',error,flush=True)

if __name__=='__main__':
    import sys
    fixture() if len(sys.argv)>1 and sys.argv[1]=='fixture' else build()
