"""Step 1–3: exactly one original C3A native canary; no external solve."""
from support import *
from objective_identity import verify
import argparse,re,threading,traceback

def prepare():
    assert git('merge-base',BASE,'HEAD')==BASE
    assert not (OUT/'NATIVE_ONCE.json').exists()
    A,d,_=hc.load();identity=verify(ROOT,d);assert identity['PASS']
    point=PREVIOUS/'BEST_VALID_POINT.npz';assert sha(point)=='32fbc2036ef1fb874097d4dc38623818238510aaffd3b5b58f992e5ce519f2e3'
    with np.load(point) as z:x=z['x'].copy()
    result=full_replay(A,d,x);assert result['PASS'] and x[239826]==UB
    np.savez_compressed(OUT/'START_POINT.npz',x=x)
    write('CENTER_VALIDATION.json',dict(**result,UTC=stamp(),rho=float(x[239826]),source=point.relative_to(ROOT).as_posix(),source_SHA256=sha(point),point_SHA256=sha(OUT/'START_POINT.npz'),complete_variables=len(x)))
    write('OBJECTIVE_PREFLIGHT.json',identity)
    write('BASE_IDENTITY.json',dict(base=BASE,scientific=SCIENTIFIC,protected_before=protected(),original_rows=A.shape[0],original_columns=A.shape[1],original_nnz=A.nnz,T1_rows=0,diagnostic_rows=0))
    print('PREPARE_PASS_ORIGINAL_C3A_FULL_REPLAY',len(x),x[239826],flush=True)

class Resources:
    def __init__(self):
        import psutil
        self.process=psutil.Process();self.psutil=psutil;self.start=time.perf_counter();self.rows=[];self.stop=threading.Event();self.phase='BUILD';self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.is_set():
            self.sample();self.stop.wait(2)
    def sample(self):
        m=self.process.memory_info();s=self.psutil.virtual_memory()
        self.rows.append(dict(UTC=stamp(),wall_seconds=time.perf_counter()-self.start,phase=self.phase,RSS=m.rss,VMS=m.vms,peak_wset=getattr(m,'peak_wset',None),system_available=s.available,system_memory_percent=s.percent))
        table('NATIVE_RESOURCE_TELEMETRY.csv',self.rows)
    def finish(self):self.stop.set();self.thread.join(timeout=3);self.sample()

def run():
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_integrated.matrix import arrays
    assert not git('status','--porcelain=v1'),'COMMIT_BEFORE_NATIVE'
    assert not (OUT/'NATIVE_ONCE.json').exists()
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    cv=read(OUT/'CENTER_VALIDATION.json');assert cv['PASS'] and sha(OUT/'START_POINT.npz')==cv['point_SHA256']
    A,d,_=hc.load();assert verify(ROOT,d)['PASS']
    with np.load(OUT/'START_POINT.npz') as z:x=z['x'].copy()
    assert hc.replay(A,d,x,True)['PASS']
    resources=Resources();begin=time.perf_counter();m=build(A,d);m.ModelName='ORIGINAL_C3A_P1_BRANCH_SOONER_CANARY'
    for k,v in SETTINGS.items():m.setParam(k,v)
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/'NATIVE_SOLVER.log')
    variables=m.getVars();m.NumStart=1;m.setAttr('Start',variables,x.tolist());m.update()
    assert np.array_equal(np.asarray(m.getAttr('Start')),x) and m.NumStart==1
    B,e=arrays(m);assert B.shape==A.shape and (B!=A).nnz==0
    assert all(np.asarray(e[k]).dtype==np.asarray(d[k]).dtype and np.asarray(e[k]).tobytes()==np.asarray(d[k]).tobytes() for k in d if k!='row_names')
    assert np.array_equal(e['row_names'],d['row_names']) # Native string transport drops unused Unicode padding only.
    identity=verify(ROOT,e,int(m.ModelSense));write('OBJECTIVE_IDENTITY.json',identity);assert identity['PASS']
    effective=parameters(m);assert all(effective[k]==v for k,v in SETTINGS.items())
    build_seconds=time.perf_counter()-begin
    write('SOLVER_PARAMETERS.json',dict(settings=SETTINGS,all_effective_before=effective,start_complete=True,start_variable_count=len(x)))
    write('MODEL_TRANSPORT_AUTHORITY.json',dict(PASS=True,rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,binaries=m.NumBinVars,T1_rows=0,diagnostic_rows=0,all_numeric_fields_and_variable_axis_raw_bytes_match=True,row_names_identical=True,row_name_storage_padding=dict(source=str(d['row_names'].dtype),native=str(e['row_names'].dtype)),Fingerprint=int(m.Fingerprint),build_seconds=build_seconds,objective_identity_SHA256=sha(OUT/'OBJECTIVE_IDENTITY.json'),Start_SHA256=sha(OUT/'START_POINT.npz')))
    times=dict.fromkeys(['presolve_end','barrier_start','barrier_end','crossover_start','crossover_end','root_relaxation_complete','first_MIPNODE','first_nonroot_node','first_branch_evidence','first_incumbent'])
    events=[];trajectory=[];barrier=[];nonroot_counts=set();errors=[];incumbents=[];last=-5.;live=-30.;last_nodes=-1.
    def cb(model,where):
        nonlocal last,live,last_nodes
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=float(model.cbGet(gp.GRB.Callback.RUNTIME));w=float(model.cbGet(gp.GRB.Callback.WORK))
            if where==gp.GRB.Callback.MESSAGE:
                line=model.cbGet(gp.GRB.Callback.MSG_STRING).strip();ev=None
                if line.startswith('Presolve time:'):ev='presolve_end'
                elif line.startswith('Barrier statistics:') or 'barrier log' in line.lower():ev='barrier_start'
                elif line.startswith('Barrier solved model'):ev='barrier_end'
                elif 'crossover log' in line.lower():ev='crossover_start'
                elif line.startswith('Crossover time:'):ev='crossover_end'
                elif line.startswith('Root relaxation:') and ('objective' in line or 'infeasible' in line):ev='root_relaxation_complete'
                if ev and times[ev] is None:times[ev]=t;events.append(dict(event=ev,Runtime=t,Work=w,literal=line));resources.phase=ev
            elif where==gp.GRB.Callback.BARRIER:
                barrier.append(dict(Runtime=t,Work=w,iteration=int(model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT)),primal=finite(model.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ)),dual=finite(model.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ))))
            elif where==gp.GRB.Callback.MIP:
                n=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT));left=float(model.cbGet(gp.GRB.Callback.MIP_NODLFT))
                if n>1 and times['first_branch_evidence'] is None:times['first_branch_evidence']=t;events.append(dict(event='first_branch_evidence',Runtime=t,Work=w,node_count=n,exact_timestamp=False))
                if t-last>=5 or n!=last_nodes:
                    last=t;last_nodes=n;trajectory.append(dict(Runtime=t,Work=w,node_count=n,nodes_left=left,solutions=int(model.cbGet(gp.GRB.Callback.MIP_SOLCNT)),ObjBst=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBST)),BestBd=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND)),simplex_iterations=float(model.cbGet(gp.GRB.Callback.MIP_ITRCNT)),cut_count=int(model.cbGet(gp.GRB.Callback.MIP_CUTCNT))));table('NATIVE_NODE_TRAJECTORY.csv',trajectory)
            elif where==gp.GRB.Callback.MIPNODE:
                n=float(model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))
                if times['first_MIPNODE'] is None:times['first_MIPNODE']=t
                if n>0:
                    nonroot_counts.add(n)
                    if times['first_nonroot_node'] is None:times['first_nonroot_node']=t
                if n==0 and model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL and not (OUT/'NATIVE_ROOT_POINT.npz').exists():np.savez_compressed(OUT/'NATIVE_ROOT_POINT.npz',x=np.asarray(model.cbGetNodeRel(variables)))
            elif where==gp.GRB.Callback.MIPSOL:
                point=np.asarray(model.cbGetSolution(variables));i=len(incumbents)+1;p=OUT/'native_incumbents'/f'{i:04d}.npz';p.parent.mkdir(exist_ok=True);np.savez_compressed(p,x=point)
                incumbents.append(dict(event=i,Runtime=t,Work=w,node_count=float(model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)),objective=float(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),rho=float(point[239826]),point=p.relative_to(OUT).as_posix(),SHA256=sha(p)));table('NATIVE_INCUMBENT_TRACE.csv',incumbents)
                if times['first_incumbent'] is None:times['first_incumbent']=t
            if t-live>=30:
                live=t;write('NATIVE_LIVE.json',dict(Runtime=t,Work=w,times=times,incumbents=len(incumbents),errors=errors));print('CANARY_PROGRESS',round(t,2),round(w,2),last_nodes,flush=True)
        except BaseException:errors.append(traceback.format_exc());model.terminate()
    # Guard is scoped to this process. LP benchmark is a separate process.
    original_optimize=gp.Model.optimize;calls=0
    def guarded(model,*args,**kwargs):
        nonlocal calls
        assert calls==0 and model is m
        assert verify(ROOT,dict(names=np.array(m.getAttr('VarName')),objective=np.array(m.getAttr('Obj')),constant=np.array(m.ObjCon)),int(m.ModelSense))['PASS']
        with (OUT/'NATIVE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(UTC=stamp(),settings=SETTINGS,source_commit=git('rev-parse','HEAD'),optimize_calls=1,base=BASE),f,indent=2)
        calls+=1;return original_optimize(model,*args,**kwargs)
    gp.Model.optimize=guarded
    def forbidden(*args,**kwargs):raise AssertionError('SEPARATE_PRESOLVE_FORBIDDEN')
    gp.Model.presolve=forbidden
    resources.phase='NATIVE_OPTIMIZE';error=None;start=time.perf_counter();print('CANARY_ONE_NATIVE_600_START',flush=True)
    try:m.optimize(cb)
    except BaseException:error=traceback.format_exc()
    receipt=dict(Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),NodeCount=float(m.NodeCount),SolCount=int(m.SolCount),IterCount=float(m.IterCount),BarIterCount=int(m.BarIterCount),native_ObjVal=finite(m.ObjVal) if m.SolCount else None,native_ObjBound=finite(m.ObjBound),wall_seconds=time.perf_counter()-start,build_seconds=build_seconds,optimize_calls=calls,callback_errors=errors,exception=error)
    if m.SolCount:np.savez_compressed(OUT/'NATIVE_FINAL_POINT.npz',x=np.asarray(m.getAttr('X')))
    after=parameters(m);assert after==effective;m.dispose();gp.Model.optimize=original_optimize
    resources.phase='REPLAY';audits=[];best=dict(rho=UB,point='START_POINT.npz',full_replay=cv);seen=set();reader=None
    paths=[OUT/e['point'] for e in incumbents]+([OUT/'NATIVE_FINAL_POINT.npz'] if receipt['SolCount'] else [])
    for p in paths:
        with np.load(p) as z:point=z['x'].copy()
        h=hashlib.sha256(point.tobytes()).hexdigest()
        if h in seen:continue
        seen.add(h)
        if reader is None:reader=hc.physical_reader()
        replay=full_replay(A,d,point,reader);audit=dict(point=p.relative_to(OUT).as_posix(),SHA256=sha(p),rho=float(point[239826]),**replay);audits.append(audit)
        if replay['PASS'] and audit['rho']<best['rho']:best=dict(rho=audit['rho'],point=audit['point'],full_replay=audit)
    with np.load(OUT/best['point']) as z:np.savez_compressed(OUT/'BEST_VALID_POINT.npz',x=z['x'])
    write('BEST_FULL_REPLAY.json',best['full_replay']);write('NATIVE_CANDIDATE_REPLAYS.json',dict(audits=audits,every_event_saved_before_replay=True))
    resources.finish();log=(OUT/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
    warnings=[l for l in log.splitlines() if re.search(r'warning|numerical trouble|numeric error|unstable|unscaled.*violation',l,re.I)]
    material=times['first_nonroot_node'] is not None and receipt['NodeCount']>=10 and len(nonroot_counts)>=5
    valid=calls==1 and not errors and error is None and protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    assessment=dict(PASS=valid,material_nonroot_progress=material,assessment='NATIVE_BRANCH_SOONER_PROMISING' if material else 'MONOLITHIC_ROOT_PROCESSING_BOTTLENECK',distinct_nonroot_callback_counts=sorted(nonroot_counts),root_LP_completed=times['root_relaxation_complete'] is not None,first_branch_exact=None,first_branch_observed_upper_bound=times['first_branch_evidence'],proceed_step4=True,production_run_executed=False)
    receipt.update(UTC=stamp(),times=times,events=events,warnings=warnings,peak_RSS=max(r['RSS'] for r in resources.rows),global_LB=LB,global_UB=best['rho'],global_gap=(best['rho']-LB)/best['rho'],native_bound_promoted=False,complete_start_supplied=True,start_acceptance_lines=[l for l in log.splitlines() if 'start' in l.lower() and ('objective' in l.lower() or 'violat' in l.lower())])
    write('NATIVE_RESULT.json',receipt);write('NATIVE_ASSESSMENT.json',assessment);write('NATIVE_ROOT_TIMELINE.json',dict(times=times,events=events,barrier_progress=barrier,exact_first_branch_unavailable=True))
    print('CANARY_COMPLETE',receipt['Status'],receipt['NodeCount'],best['rho'],assessment['assessment'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    try:prepare() if args.prepare else run()
    except BaseException:
        if not (OUT/'NATIVE_ONCE.json').exists():write('STOPPED_BEFORE_NATIVE.json',dict(optimize_calls=0,error=traceback.format_exc()))
        raise
