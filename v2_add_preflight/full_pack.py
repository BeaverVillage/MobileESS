"""Complete96 FULL matrix/domain pack from real bounded Native0 components.

The isolated whole Gurobi build remains a separate result. These components
retain all rows/columns and exactly substitute only the temporary port aliases;
they are not restricted-route models or an optimizer/constraint-generation loop.
"""
import math,time,re,types,json,threading
import numpy as np
import scipy.sparse as sp
import psutil
from .full_common import *
from .full_native import FullGrid,stats
from .prestart_native import inputs,original_solve,native_zero

PACK=RUN/'FULL96_MATRIX_PORT_PACK'

def domain(m):
    return {k:np.asarray(m.getAttr(a)) for k,a in [('names','VarName'),('lower','LB'),('upper','UB'),('types','VType')]}

def numerical(A,rhs,sense,point,d):
    r=A@point-rhs
    violation=np.maximum(0.,np.where(sense=='=',abs(r),np.where(sense=='<',r,-r)))
    bound=max(float(np.max(d['lower']-point,initial=0)),float(np.max(point-d['upper'],initial=0)),0.)
    integer=d['types']!='C';iv=float(np.max(abs(point[integer]-np.rint(point[integer])),initial=0))
    maximum=float(violation.max(initial=0))
    return dict(PASS=maximum<=1e-5 and bound<=1e-5 and iv<=1e-5 and bool(np.isfinite(point).all()),
        max_row_violation=maximum,max_bound_violation=bound,max_integer_violation=iv,rows=A.shape[0],columns=A.shape[1],nonzeros=A.nnz)

def mobility():
    import gurobipy as gp
    from v42_integrated.matrix import arrays
    day=day_input('2025-05-01');bundle=read(day['files']['native']['path']);sites,initial,routes,battery,receipt=inputs(bundle,INITIAL)
    started=time.perf_counter();result={}
    class Deadline:
        stage='M1';last=0.
        def check(self):
            now=time.perf_counter()
            if now-self.last>.25:self.last=now;guard(started)
    def grid(m,p,q):return [('rho',m.addVar(lb=0,ub=1,name='rho_max')),('reserve_shortfall',0.)]
    def hook(m,c):
        for s in sites:
            for t in range(96):m.addConstr(gp.quicksum(c.x[u,c.stay[s,t]] for u in initial)<=1,name='all24_mobile_port_occupancy')
    def capture(m,obj,*a,**kw):
        m.setObjective(obj[0][1]);m.update();A,d=arrays(m)
        sp.save_npz(PACK/'MOBILITY.npz',A,compressed=True);np.savez_compressed(PACK/'MOBILITY_DOMAIN.npz',**d)
        objectives={}
        for name,expr in obj:
            if isinstance(expr,gp.Var):objectives[name]=dict(indices=[expr.index],coefficients=[1.],constant=0.)
            elif isinstance(expr,gp.LinExpr):objectives[name]=dict(indices=[expr.getVar(i).index for i in range(expr.size())],coefficients=[expr.getCoeff(i) for i in range(expr.size())],constant=expr.getConstant())
            else:objectives[name]=dict(indices=[],coefficients=[],constant=float(expr))
        point=np.zeros(m.NumVars);lookup={n:i for i,n in enumerate(d['names'])}
        for u,s in INITIAL.items():
            for t in range(97):point[lookup[f'SOC[{u},{t}]']]=760.
            for t in range(96):point[lookup[f'arc[{u},{sites.index(s)*96+t}]']]=1.
        rho=max(float(r['rho_global']) for r in __import__('csv').DictReader((OUT/'GRID_PLANNING_ANCHOR.csv').open(encoding='utf-8')))
        point[lookup['rho_max']]=rho
        v={n:float(point[i]) for i,n in enumerate(d['names'])}
        for u in INITIAL:
            for s in sites:
                for t in range(96):
                    for name in ('Pch','Pdis','Q'):v.setdefault(f'{name}[{u},{s},{t}]',0.)
        from v42_native.mess import validate
        physics=validate(dict(values=v,chosen_arcs={u:[sites.index(s)*96+t for t in range(96)] for u,s in INITIAL.items()},initial_sites=INITIAL,mode='MILP'),sites,routes,battery,96)
        witness=numerical(A,d['rhs'],d['sense'],point,d);assert witness['PASS'] and physics['PASS']
        np.save(PACK/'MOBILITY_POINT.npy',point)
        (PACK/'OBJECTIVES.json').write_text(json.dumps(objectives),encoding='utf-8')
        result.update(stats=stats(m),receipt=receipt,physics=physics,witness=witness,sites=sites,
            rho=rho,objectives=record(PACK/'OBJECTIVES.json'),wall_seconds=time.perf_counter()-started)
        return None,dict(Native_calls=0,Native_seconds=0.)
    with native_zero():
        fn=original_solve(capture);fn=types.FunctionType(fn.__code__,dict(fn.__globals__,size=stats),argdefs=fn.__defaults__,closure=fn.__closure__);fn.__kwdefaults__=original_solve(capture).__kwdefaults__
        fn('M1',Deadline(),sites,initial,routes,battery,96,grid,strengthening_hook=hook)
    (PACK/'MOBILITY_RECEIPT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def local_point(d,a,axes,rho):
    p=np.zeros(len(d['names']));par=np.flatnonzero(axes['parent_mask'])
    lookup={'node_voltage_squared':a['v'],'parent_line_P':a['lp'][par],'parent_line_Q':a['lq'][par],
        'parent_line_current_correction':np.zeros(len(par)),'transformer_winding_P':a['tp'],'transformer_winding_Q':a['tq']}
    for j,name in enumerate(d['names']):
        if name=='rho_max':p[j]=rho
        for prefix,values in lookup.items():
            if name.startswith(prefix+'_'):p[j]=values[int(name.split('[')[1][:-1])];break
    return p

def build():
    init();res=resources();PACK.mkdir(exist_ok=True);started=time.perf_counter();proc=psutil.Process();peak=[proc.memory_info().rss];done=threading.Event()
    # Reuse identical actual Source mobility data from the preserved earlier
    # pack attempt. No original route/domain/row or byte is regenerated here.
    prior=RUN/'FULL96_MATRIX_PACK'
    if not (PACK/'MOBILITY_RECEIPT.json').exists() and (prior/'MOBILITY_RECEIPT.json').exists():
        import shutil
        for name in ('MOBILITY.npz','MOBILITY_DOMAIN.npz','MOBILITY_POINT.npy','OBJECTIVES.json','MOBILITY_RECEIPT.json'):
            shutil.copy2(prior/name,PACK/name)
    def sample():
        while not done.wait(.1):peak[0]=max(peak[0],proc.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    import gurobipy as gp
    from v42_integrated.matrix import arrays
    mob=read(PACK/'MOBILITY_RECEIPT.json') if (PACK/'MOBILITY_RECEIPT.json').exists() else mobility()
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
    mp=np.load(PACK/'MOBILITY_POINT.npy');names={n:i for i,n in enumerate(md['names'])};nbase=len(mp)
    manifest=read(OUT/'GRID_COEFFICIENT_MANIFEST.json');axes=read(OUT/'GRID_AXES.json');naux=34329;nfull=nbase+96*naux
    full_point=np.lib.format.open_memmap(PACK/'FULL_POINT.npy',mode='w+',dtype=np.float64,shape=(nfull,));full_point[:nbase]=mp
    blocks=[];error=None
    try:
        for t,rec in enumerate(manifest['records']):
            guard(started);folder=PACK/f'{t:02d}';folder.mkdir(exist_ok=True)
            if (folder/'RECEIPT.json').exists():
                rr=read(folder/'RECEIPT.json');full_point[nbase+t*naux:nbase+(t+1)*naux]=np.load(folder/'POINT.npy');blocks.append(rr);continue
            g=FullGrid(started);g.manifest=dict(manifest,records=[rec]);m=gp.Model('V2_ADD_FULL_GRID_COMPONENT');m.Params.OutputFlag=0
            # Temporary aggregate variables are eliminated by exact substitution
            # into the original eight-vehicle Pdis-Pch and Q expressions below.
            sites=list(mob['sites']);p={(s,0):m.addVar(lb=-gp.GRB.INFINITY,name='port_P_'+s) for s in sites};q={(s,0):m.addVar(lb=-gp.GRB.INFINITY,name='port_Q_'+s) for s in sites}
            with native_zero():
                objectives=g.build(m,p,q);m.setObjective(objectives[0][1]);m.update();A,d=arrays(m)
            assert len(d['names'])==34378 and d['names'][48]=='rho_max'
            with np.load(rec['path']) as z:a={k:z[k] for k in z.files}
            point=local_point(d,a,axes,mob['rho']);local=numerical(A,d['rhs'],d['sense'],point,d)
            assert local['PASS']
            ii=[];jj=[];vv=[]
            for k,s in enumerate(sites):
                for u in INITIAL:
                    for prefix,sign in [('Pdis',1.),('Pch',-1.)]:
                        key=f'{prefix}[{u},{s},{t}]'
                        if key in names:ii.append(k);jj.append(names[key]);vv.append(sign)
                    key=f'Q[{u},{s},{t}]'
                    if key in names:ii.append(24+k);jj.append(names[key]);vv.append(1.)
            ii.append(48);jj.append(names['rho_max']);vv.append(1.)
            for k in range(naux):ii.append(49+k);jj.append(nbase+t*naux+k);vv.append(1.)
            S=sp.csr_matrix((vv,(ii,jj)),shape=(A.shape[1],nfull));B=(A@S).tocsr();B.eliminate_zeros();B.sort_indices()
            full_point[nbase+t*naux:nbase+(t+1)*naux]=point[49:]
            # Verify the actual mapped matrix against the local Native matrix
            # and independent source STAY/PQ/SOC witness, all rows/columns.
            lifted=np.asarray(S@full_point);assert np.array_equal(lifted,point)
            residual=B@full_point-d['rhs'];sense=d['sense'];violation=np.maximum(0,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
            worst=float(violation.max(initial=0));assert worst<=1e-5
            # The only expanded rows are 48 exact injection bindings (unit
            # weights). There is no floating-point coefficient rounding there.
            exact_alias=bool(np.all(np.isin(S.data,[-1.,1.])))
            assert exact_alias and B.shape==(210617,nfull)
            sp.save_npz(folder/'MATRIX.npz',B,compressed=True)
            np.savez_compressed(folder/'DOMAIN.npz',names=d['names'][49:],lower=d['lower'][49:],upper=d['upper'][49:],types=d['types'][49:])
            np.savez_compressed(folder/'ROWS.npz',rhs=d['rhs'],sense=d['sense'],local_names=d['row_names'])
            np.save(folder/'POINT.npy',point[49:]);m.dispose()
            rr=dict(slot=t,rows=B.shape[0],global_columns=nfull,nonzeros=B.nnz,aux_columns=naux,local_Native0=local,
                global_full_row_max_violation=worst,exact_unit_alias_substitution=exact_alias,
                temporary_port_alias_variables_retained=False,coefficient=rec,files={p.name:record(p) for p in folder.iterdir() if p.is_file()},
                all_constraint_blocks=g.blocks)
            (folder/'RECEIPT.json').write_text(json.dumps(rr,indent=2),encoding='utf-8');blocks.append(rr)
            put('FULL96_MATRIX_PACK_PROGRESS.json',dict(completed=len(blocks),total=96,wall_seconds=time.perf_counter()-started,RSS_bytes=proc.memory_info().rss))
            if t%8==0:print('FULL96 MATRIX PACK',t,round(time.perf_counter()-started,1),flush=True)
    except Exception as exc:error=repr(exc)
    finally:full_point.flush();done.set();th.join(timeout=1)
    full=len(blocks)==96 and error is None
    identity=dict(source=SOURCE,day='2025-05-01',stage='M1',scenario=read(OUT/'CAMPAIGN_EXECUTION_HOLD.json')['candidate'],
        input=day_input('2025-05-01')['files']['native'],windows=day_input('2025-05-01')['files']['windows'],
        coefficients=record(OUT/'GRID_COEFFICIENT_MANIFEST.json'),mobility=record(PACK/'MOBILITY.npz'),mobility_domain=record(PACK/'MOBILITY_DOMAIN.npz'),
        blocks=[dict(slot=b['slot'],matrix=b['files']['MATRIX.npz'],domain=b['files']['DOMAIN.npz'],rows=b['files']['ROWS.npz']) for b in blocks],
        objectives=record(PACK/'OBJECTIVES.json'),variable_substitution='Exact unit-weight temporary port aliases only; original binary/continuous mobility domains preserved',
        mobile_ports=dict(count=24,interface_kVA=600,phase_current_A=600/(math.sqrt(3)*.48),occupancy=1,explicit_current_and_16face_kVA_rows=True),
        control_signs=dict(aidc='positive building load kW, originalPF.95',MESS='positive P/Q injection; actual Load command is the negative pair'))
    put('FULL96_MATRIX_PACK_CERTIFICATION.json',dict(status='COMPLETE_FULL96_MATRIX_DOMAIN_AND_STAY_WITNESS' if full else 'MATRIX_PACK_INCOMPLETE',
        matrix_domain_pack_PASS=full,error=error,identity=identity,case_sha=digest(identity),
        original8_MESS_physics=mob['physics'],mobility_native_matrix=mob['stats'],mobility_witness=mob['witness'],
        matrix=dict(rows=mob['stats']['linear_constraints']+sum(b['rows'] for b in blocks),columns=nfull,binary=417296,
            continuous=nfull-417296,nonzeros=mob['stats']['nonzeros']+sum(b['nonzeros'] for b in blocks)),
        all_rows_independent_STAY_PQ0_point_PASS=full and all(b['global_full_row_max_violation']<=1e-5 for b in blocks),
        witness_rho=mob['rho'],witness_is_optimizer_result=False,STAY_MOVE_domain_free=True,
        full_point=record(PACK/'FULL_POINT.npy'),grid_slots=len(blocks),Native_optimize_calls=0,
        monolithic_full_Gurobi_build_PASS=False,K48_Beam_Joint_stage_connected=False,Actual120_voltage_certified=False,
        representation='Real Native0 mobility and96 real Native0 grid components, exact global alias substitution, complete matrix/domain/point pack. Not a completed monolithic Native0 build or campaign acceptance.',
        wall_seconds=time.perf_counter()-started,peak_RSS_bytes=peak[0],resources=res))
    print('FULL96 PACK DONE',full,error,flush=True)

if __name__=='__main__':build()
