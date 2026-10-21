"""Original r043 Native0 builds. Partial models never certify FULL readiness."""
import ast,gzip,inspect,textwrap,time,types,threading
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import psutil
from .prestart import ROOT,OUT,RUN,read,put,record,INITIAL,resources,digest

@contextmanager
def native_zero():
    import gurobipy as gp
    old={k:getattr(gp.Model,k) for k in ('optimize','presolve')};attempts=[]
    def denied(*a,**kw):
        attempts.append('NATIVE0_OPTIMIZE_OR_PRESOLVE_DENIED');raise PermissionError(attempts[-1])
    for k in old:setattr(gp.Model,k,denied)
    try:yield attempts
    finally:
        for k,v in old.items():setattr(gp.Model,k,v)

def inputs(bundle,initial):
    """One exact dimension-guard change, without regenerating/filtering routes."""
    from v42_bootstrap.m1 import native_inputs
    text=inspect.getsource(native_inputs)
    old="len(bundle['initial_MESS_sites'])==4"
    assert text.count(old)==1
    text=text.replace(old,"len(bundle['initial_MESS_sites'])==len(expected_initial)")
    ns=dict(native_inputs.__globals__,expected_initial=initial)
    exec(compile(text,native_inputs.__code__.co_filename,'exec'),ns)
    b=dict(bundle,initial_MESS_sites=initial)
    result=ns['native_inputs'](b)
    assert result[1]==initial and len(result[0])==24
    return result

def q250(original):
    """Execute the unmodified original V44 overlay definition in a small namespace."""
    p=ROOT/'v44/q250_m4.py';tree=ast.parse(p.read_text(encoding='utf-8'))
    node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='native_adapter')
    ns=dict(inspect=inspect,textwrap=textwrap)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),ns)
    return ns['native_adapter'](original)

def original_solve(optimizer):
    from v42_native.mess import solve
    clone=q250(solve)
    result=types.FunctionType(clone.__code__,dict(clone.__globals__,optimize=optimizer),argdefs=clone.__defaults__,closure=clone.__closure__)
    result.__kwdefaults__=clone.__kwdefaults__
    return result

def build():
    resource=resources();day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    bundle=read(day['files']['native']['path']);reports=[];process=psutil.Process()
    from v42_native.solver import size
    for count in (4,8):
        initial=dict(list(INITIAL.items())[:count]);sites,initial,routes,battery,receipt=inputs(bundle,initial)
        started=time.perf_counter();peak=[process.memory_info().rss];stop=threading.Event()
        def sample():
            while not stop.wait(.1):peak[0]=max(peak[0],process.memory_info().rss)
        th=threading.Thread(target=sample,daemon=True);th.start()
        class Deadline:
            stage='M1'
            last_resource_check=0.
            def check(self):
                now=time.perf_counter()
                if now-self.last_resource_check<.25:return
                self.last_resource_check=now
                if process.memory_info().rss>4*1024**3 or psutil.virtual_memory().available<6*1024**3:
                    raise MemoryError('PROTECTED_WORKER_RESOURCE_RESERVE')
                if now-started>900:raise TimeoutError('NATIVE0_BUILD_WALL_GUARD_900S')
        stats={};context={}
        def grid(m,p,q):
            # Capture the entire original graph/PQ/SOC block before rejecting
            # the missing IEEE8500 coefficient authority. No fake line rows.
            stats.update(size(m));stats.update(PQ_site_time_axes=len(p),all_24_services_retained=True)
            rho=m.addVar(lb=0,ub=1,name='rho_max_UNBOUND_DIAGNOSTIC')
            return [('rho',rho),('reserve_shortfall',0.)]
        def hook(m,c):
            context['reachable_move_columns_by_unit']={u:sum(not isinstance(c.x[u,k],float) for k,a in enumerate(c.arcs) if a[-1] is not None) for u in initial}
            context['reachable_stay_columns_by_unit']={u:sum(not isinstance(c.x[u,k],float) for k,a in enumerate(c.arcs) if a[-1] is None) for u in initial}
            # The physical STA occupancy is explicit and does not delete routes.
            import gurobipy as gp
            for s in sites:
                if not s.startswith('STA'):continue
                for t in range(96):m.addConstr(gp.quicksum(c.x[u,c.stay[s,t]] for u in initial)<=1,name='STA_port_occupancy')
        def capture(m,objectives,deadline,*a,**kw):
            m.setObjective(objectives[0][1]);m.update();stats.update(size(m))
            context['objectives']=[n for n,e in objectives]
            context['Q_bounds_PASS']=all(v.LB==-250 and v.UB==250 for v in m.getVars() if v.VarName.startswith('Q['))
            from v42_m1_hybrid.blocks import matrix_sha
            A=m.getA();context['mobility_matrix_sha256']=matrix_sha(A)
            context['model_scope']='COMPLETE_ORIGINAL_MOBILITY_PLUS_Q250_AND_STA_OCCUPANCY_ONLY_NO_GRID_ROWS'
            return None,dict(Native_calls=0,Native_seconds=0.)
        with native_zero() as denied:
            try:
                fn=original_solve(capture)
                fn('M1',Deadline(),sites,initial,routes,battery,96,grid,strengthening_hook=hook)
                status='MOBILITY_NATIVE0_BUILT_FULL_IEEE8500_GRID_NOT_BOUND'
            except (MemoryError,TimeoutError) as e:status=str(e)
            finally:stop.set();th.join(timeout=1)
        reports.append(dict(units=count,status=status,wall_seconds=time.perf_counter()-started,peak_RSS_bytes=peak[0],
            model=stats,context=context,Native_calls=0,denied_attempts=denied,input_receipt=receipt,
            binary_continuous_counts_measured=True,IEEE8500_FULL_build_PASS=False))
        put('MESS8_NATIVE0_BUILD_REPORT.json',dict(status='PARTIAL_NATIVE0_NOT_FULL_EQUIVALENCE',builds=reports,
            resources=resource,original_source='affc7226a519adbe072d7debbc3ae25ea71c3487',
            adapter=record(Path(__file__)),
            source_native=record(ROOT/'v42_native/mess.py'),source_Q250=record(ROOT/'v44/q250_m4.py'),
            Native_optimize_calls=0,IEEE8500_full96_affine_response='NOT_BOUND',
            K48_root_pricing_seconds=None,Joint_FULL_preparation_seconds=None,full_native_time_estimate_seconds=None,
            missing='Certified IEEE8500 Planning96 FULL coefficient/current/transformer authority and original K48/Beam/Joint/FULL-case binding; existing wrappers explicitly require IEEE123/7-Reg/120-current-row authorities.',
            original_routes_pruned=False,original_stage_budget_or_gap_changed=False,
            route_PQ_at_IDC='Original24-service domain includes IDC ports; current8500 adapter has only12 STA480V facilities. IDC charging hardware not certified. Do not energize mobile PCS directly at12.47kV.'))
        print('NATIVE0',count,status,stats.get('binary'),stats.get('linear_constraints'),flush=True)

def fixture_calls():
    """Reach all four original native stage builders with Optimize forbidden."""
    import gurobipy as gp
    from v42_native import aidc,mess
    from v42_job_capability import Job,Resources
    from v42_native.service import boundary
    results=[]
    class Deadline:
        def __init__(self,stage):self.stage=stage
        def check(self):pass
    def capture(m,obj,d,*a,**kw):
        m.setObjective(obj[0][1]);m.update()
        results.append(dict(stage=d.stage,called_original_native_builder=True,rows=m.NumConstrs,columns=m.NumVars,objectives=[n for n,e in obj],Native_calls=0))
        return None,dict(Native_calls=0)
    def grid(m,*a):return [('rho',m.addVar(lb=0,ub=1,name='rho_max')),('reserve_shortfall',0.)]
    with native_zero() as denied:
        j=Job('TEST','PENDING',0,0,0,'AIDC01',2,2,initial_sites=('AIDC01','AIDC02'),duration_authority='EXPLICIT_TEST_SERVICE')
        r=Resources({'AIDC01':4,'AIDC02':4},{'AIDC01':(4,),'AIDC02':(4,)},{}, {},4,80*10**9,{}, {}, {})
        w=boundary(j,(0,1),'1'*64,'2'*64,H=4)
        for stage in ('A1','A2'):
            fn=types.FunctionType(aidc.solve.__code__,dict(aidc.solve.__globals__,optimize=capture),argdefs=aidc.solve.__defaults__)
            fn.__kwdefaults__=aidc.solve.__kwdefaults__
            fn(stage,Deadline(stage),{'TEST':j},{'TEST':w},r,grid,seconds_authority={'TEST':1800.})
        for stage in ('M1','M2'):
            fn=original_solve(capture)
            fn(stage,Deadline(stage),('STA01','STA02'),{'MESS01':'STA01','MESS02':'STA02'},(),mess.Battery(440,1080,760,760,300,400,.95,.95),4,grid)
        assert not denied
    return put('ORIGINAL_NATIVE_STAGE_FIXTURE_CALLS.json',dict(PASS=len(results)==4,calls=results,
        scope='Original native A/M builders only; no K48/Beam/DirectJoint entry or actual8500 FULL certificate',
        optimization_calls=0,full_stage_integration_certified=False))

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
