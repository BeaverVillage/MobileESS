"""Production native runner with a payload-free POLLING deadline/stall guard.

One optimize per named run, no fake tree resume, original minimize-rho identity.
"""
from practical_support import *
import argparse,re,threading,traceback

class Resources:
    def __init__(self,folder):
        import psutil
        self.p=psutil.Process();self.psutil=psutil;self.folder=folder;self.start=time.perf_counter();self.rows=[];self.stop=threading.Event();self.phase='PREFLIGHT';self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.is_set():self.sample();self.stop.wait(5)
    def sample(self):
        mem=self.p.memory_info();v=self.psutil.virtual_memory()
        self.rows.append(dict(UTC=stamp(),wall=time.perf_counter()-self.start,RSS=mem.rss,VMS=mem.vms,system_available=v.available,phase=self.phase))
        table(self.folder/'RESOURCE_TELEMETRY.csv',self.rows)
    def finish(self):self.stop.set();self.thread.join(timeout=6);self.sample()

def neighborhood(A,d,center,radius):
    b=np.flatnonzero(d['types']=='B');free=[]
    for j in b:
        name=str(d['names'][j]);t=int(name.rsplit(',',1)[-1][:-1])
        if 64<=t<=84:free.append(int(j))
    free=np.asarray(free,int);fixed=np.setdiff1d(b,free)
    with np.load(ROOT/'docs/v42_m1_hamming48_600s_20261007/NEIGHBORHOOD_RESTRICTION.npz') as z:assert np.array_equal(free,z['free']) and np.array_equal(fixed,z['fixed'])
    assert len(free)==2100 and np.array_equal(center[b],np.rint(center[b]))
    e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy());e['lower'][fixed]=center[fixed];e['upper'][fixed]=center[fixed]
    weights=np.where(center[free]>.5,-1.,1.);rhs=int(radius)-int((center[free]>.5).sum())
    row=sparse.csr_matrix((weights,(np.zeros(len(free),int),free)),shape=(1,A.shape[1]));B=sparse.vstack([A,row],format='csr')
    e.update(rhs=np.r_[d['rhs'],rhs],sense=np.concatenate([d['sense'],['<']]),row_names=np.concatenate([d['row_names'],[f'PRIMAL_HAMMING_{radius}']]))
    return B,e,free,fixed,weights,rhs

def run(args):
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_integrated.matrix import arrays
    assert git('merge-base',BASE,'HEAD')==BASE
    folder=OUT/'runs'/args.name;folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'OPTIMIZE_ONCE.json').exists(),'THIS_NAMED_SOLVE_ALREADY_STARTED'
    immutable_sha=sha(OUT/'IMMUTABLE_DEADLINE.json');source_sha=sha(__file__)
    if args.kind=='control':assert args.name=='cuts0_control' and args.seconds==1800 and args.radius is None
    elif args.kind=='production':assert args.seconds<=10800 and args.radius is None
    else:assert args.seconds<=600 and args.radius in (64,96)
    A,d,_=hc.load();assert verifier.verify(ROOT,d)['PASS'];resources=Resources(folder)
    center_path=Path(args.center).resolve()
    with np.load(center_path) as z:center=z['x'].copy()
    center_check=full_replay(A,d,center);atomic(folder/'CENTER_VALIDATION.json',dict(**center_check,UTC=stamp(),source=str(center_path),SHA256=sha(center_path),rho=float(center[239826])))
    assert center_check['PASS'],'CENTER_REPLAY_FAILED_OPTIMIZE_0'
    point_save(folder/'CENTER.npz',center)
    restricted=args.kind=='primal';B,e=A,d;free=fixed=None
    if restricted:
        B,e,free,fixed,weights,rhs=neighborhood(A,d,center,args.radius)
        assert hc.replay(B,e,center,True)['PASS']
        atomic(folder/'NEIGHBORHOOD.json',dict(radius=args.radius,slots=[64,84],free=free.tolist(),fixed=fixed.tolist(),free_names=d['names'][free].tolist(),H0_start_PASS=True,continuous_bounds_original=True,restricted_bound_never_global=True))
    limit=bounded_limit(args.seconds);settings=dict(SETTINGS,TimeLimit=limit)
    if not restricted:settings.update(Cuts=0,Heuristics=0,CutPasses=0)
    if args.kind=='production':settings['VarBranch']=2 # One evidence-selected maximum-infeasibility architecture; no sweep.
    resources.phase='BUILD';begin=time.perf_counter();m=build(B,e);m.ModelName=f'ORIGINAL_C3A_P1_{args.name}'
    for k,v in settings.items():m.setParam(k,v)
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(folder/'NATIVE_SOLVER.log')
    variables=m.getVars();m.NumStart=1;m.setAttr('Start',variables,center.tolist());m.update()
    assert np.array_equal(np.array(m.getAttr('Start')),center) and m.NumStart==1
    transported,td=arrays(m);assert transported.shape==B.shape and (transported!=B).nnz==0
    assert all(np.asarray(td[k]).dtype==np.asarray(e[k]).dtype and np.asarray(td[k]).tobytes()==np.asarray(e[k]).tobytes() for k in e if k!='row_names')
    assert np.array_equal(td['row_names'],e['row_names'])
    objective=verifier.verify(ROOT,td,int(m.ModelSense));atomic(folder/'OBJECTIVE_IDENTITY.json',objective);assert objective['PASS']
    effective=parameters(m);assert all(effective[k]==v for k,v in settings.items())
    atomic(folder/'MODEL_AUTHORITY.json',dict(PASS=True,original_A_SHA256=sha(hc.PARENT/'C3A_A.npz'),original_DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),transport_bit_identical=True,row_names_identical=True,full_original_domain=not restricted,rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,binaries=m.NumBinVars,ObjCon=m.ObjCon,Fingerprint=m.Fingerprint,added_rows=1 if restricted else 0,new_user_cuts=0,objective_identity_PASS=True))
    build_seconds=time.perf_counter()-begin
    atomic(folder/'SOLVER_PARAMETERS.json',dict(settings=settings,effective=effective,immutable_deadline_SHA256=immutable_sha,deadline_UTC=deadline().isoformat(),requested_seconds=args.seconds,complete_start=True,native_tree_resume=False))
    times=dict.fromkeys(['presolve_end','barrier_start','barrier_end','crossover_start','crossover_end','root_complete','first_MIPNODE','first_nonroot','first_branch_observed','first_incumbent'])
    events=[];trace=[];incumbents=[];errors=[];node_events=[];last=-10.;live=-30.;last_nodes=-1.;stop_reason=None;baseline=None;calls=0
    def callback(model,where):
        nonlocal last,live,last_nodes,stop_reason,baseline
        if where==gp.GRB.Callback.POLLING:
            # POLLING has no cbGet payload. Use wall clock and the last observed
            # tree/bound state so a long child LP cannot bypass the 60min stop.
            elapsed=time.perf_counter()-start
            if remaining(900)<=0:
                stop_reason='IMMUTABLE_DEADLINE_PUBLICATION_RESERVE';model.terminate()
            if args.kind=='production' and elapsed>=3600 and baseline is None:
                n=trace[-1]['node_count'] if trace else 0
                bd=trace[-1]['BestBd'] if trace else None
                if n<10 and (bd is None or bd-args.initial_lb<=1e-6):
                    stop_reason='FIRST_HOUR_NO_MATERIAL_BOUND_OR_TREE_PROGRESS';model.terminate()
                baseline=(elapsed,n,bd)
            elif args.kind=='production' and baseline is not None and elapsed-baseline[0]>=3600:
                n=trace[-1]['node_count'] if trace else 0
                bd=trace[-1]['BestBd'] if trace else None
                if n-baseline[1]<10 and (bd is None or baseline[2] is None or bd-baseline[2]<=1e-6):
                    stop_reason='ROLLING_HOUR_NO_MATERIAL_BOUND_OR_TREE_PROGRESS';model.terminate()
                baseline=(elapsed,n,bd)
            return
        try:
            t=float(model.cbGet(gp.GRB.Callback.RUNTIME));w=float(model.cbGet(gp.GRB.Callback.WORK))
            if remaining(900)<=0:stop_reason='IMMUTABLE_DEADLINE_PUBLICATION_RESERVE';model.terminate()
            if where==gp.GRB.Callback.MESSAGE:
                line=model.cbGet(gp.GRB.Callback.MSG_STRING).strip();phase=None
                if line.startswith('Presolve time:'):phase='presolve_end'
                elif line.startswith('Barrier statistics:'):phase='barrier_start'
                elif line.startswith('Barrier solved model'):phase='barrier_end'
                elif 'crossover log' in line.lower():phase='crossover_start'
                elif line.startswith('Crossover time:'):phase='crossover_end'
                elif line.startswith('Root relaxation:') and ('objective' in line or 'infeasible' in line):phase='root_complete'
                if phase and times[phase] is None:times[phase]=t;events.append(dict(event=phase,Runtime=t,Work=w,literal=line));resources.phase=phase
            elif where==gp.GRB.Callback.MIP:
                n=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT));left=float(model.cbGet(gp.GRB.Callback.MIP_NODLFT));bd=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
                if n>0:resources.phase='NONROOT_SEARCH'
                if (left>=2 or n>1) and times['first_branch_observed'] is None:times['first_branch_observed']=t;events.append(dict(event='first_branch_observed',Runtime=t,node_count=n,nodes_left=left,exact_branch_timestamp=False))
                if t-last>=10 or n!=last_nodes:
                    last=t;last_nodes=n;trace.append(dict(UTC=stamp(),Runtime=t,Work=w,node_count=n,nodes_left=left,solutions=int(model.cbGet(gp.GRB.Callback.MIP_SOLCNT)),ObjBst=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBST)),BestBd=bd,iterations=float(model.cbGet(gp.GRB.Callback.MIP_ITRCNT)),cuts=int(model.cbGet(gp.GRB.Callback.MIP_CUTCNT))));table(folder/'BOUND_NODE_TRAJECTORY.csv',trace)
                if args.kind=='production' and t>=3600:
                    if baseline is None:
                        if n<10 and (bd is None or bd-args.initial_lb<=1e-6):stop_reason='FIRST_HOUR_NO_MATERIAL_BOUND_OR_TREE_PROGRESS';model.terminate()
                        baseline=(t,n,bd)
                    elif t-baseline[0]>=3600:
                        if n-baseline[1]<10 and (bd is None or baseline[2] is None or bd-baseline[2]<=1e-6):stop_reason='ROLLING_HOUR_NO_MATERIAL_BOUND_OR_TREE_PROGRESS';model.terminate()
                        baseline=(t,n,bd)
            elif where==gp.GRB.Callback.MIPNODE:
                n=float(model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT));s=int(model.cbGet(gp.GRB.Callback.MIPNODE_STATUS))
                if times['first_MIPNODE'] is None:times['first_MIPNODE']=t
                if n>0 and times['first_nonroot'] is None:times['first_nonroot']=t
                if not node_events or node_events[-1]['node_count']!=n:
                    j=int(model.cbGet(gp.GRB.Callback.MIPNODE_BRVAR))
                    node_events.append(dict(Runtime=t,Work=w,node_count=n,LP_status=s,observed_node_callback=True,branch_variable_index=j,branch_name=str(d['names'][j]) if 0<=j<len(d['names']) else None,original_branch_type=str(d['types'][j]) if 0<=j<len(d['types']) else None));table(folder/'OBSERVED_NODE_LEDGER.csv',node_events)
                if n==0 and s==gp.GRB.OPTIMAL and not (folder/'ROOT_POINT.npz').exists():point_save(folder/'ROOT_POINT.npz',np.asarray(model.cbGetNodeRel(variables)))
            elif where==gp.GRB.Callback.MIPSOL:
                x=np.asarray(model.cbGetSolution(variables));i=len(incumbents)+1;p=folder/'incumbents'/f'{i:05d}.npz';point_save(p,x)
                incumbent=dict(event=i,UTC=stamp(),Runtime=t,Work=w,rho=float(x[239826]),node_count=float(model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)),point=p.relative_to(folder).as_posix(),SHA256=sha(p),bound_restricted_only=restricted,Hamming=int(np.count_nonzero((x[free]>.5)!=(center[free]>.5))) if restricted else None)
                incumbents.append(incumbent);table(folder/'INCUMBENT_TRACE.csv',incumbents)
                if times['first_incumbent'] is None:times['first_incumbent']=t
            if t-live>=30:
                live=t;atomic(folder/'LIVE.json',dict(UTC=stamp(),PID=os.getpid(),Runtime=t,Work=w,nodes=last_nodes,times=times,incumbents=len(incumbents),errors=errors,stop_reason=stop_reason));print('NATIVE_PROGRESS',args.name,round(t,2),round(w,2),last_nodes,flush=True)
        except BaseException:errors.append(traceback.format_exc());stop_reason='CALLBACK_ERROR';model.terminate()
    original_optimize=gp.Model.optimize
    def guarded(model,*a,**kw):
        nonlocal calls
        assert calls==0 and model is m and sha(__file__)==source_sha and sha(OUT/'IMMUTABLE_DEADLINE.json')==immutable_sha
        raw=dict(names=np.array(m.getAttr('VarName')),objective=np.array(m.getAttr('Obj')),constant=np.array(m.ObjCon))
        assert verifier.verify(ROOT,raw,int(m.ModelSense))['PASS'],'OBJECTIVE_IDENTITY_FAIL_OPTIMIZE_0'
        with (folder/'OPTIMIZE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(PID=os.getpid(),UTC=stamp(),source_commit=git('rev-parse','HEAD'),source_SHA256=source_sha,optimize_calls=1,kind=args.kind,settings=settings,deadline_SHA256=immutable_sha),f,indent=2)
        calls+=1;return original_optimize(model,*a,**kw)
    gp.Model.optimize=guarded
    def forbidden(*a,**kw):raise AssertionError('EXTRA_PRESOLVE_FORBIDDEN')
    gp.Model.presolve=forbidden;start=time.perf_counter();error=None;resources.phase='OPTIMIZE';print('ONE_NATIVE_START',args.name,limit,flush=True)
    try:m.optimize(callback)
    except BaseException:error=traceback.format_exc()
    receipt=dict(UTC=stamp(),name=args.name,kind=args.kind,Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),NodeCount=float(m.NodeCount),SolCount=int(m.SolCount),IterCount=float(m.IterCount),BarIterCount=int(m.BarIterCount),ObjVal=finite(m.ObjVal) if m.SolCount else None,ObjBound=finite(m.ObjBound),optimize_calls=calls,callback_errors=errors,exception=error,stop_reason=stop_reason,wall_optimize_seconds=time.perf_counter()-start,build_seconds=build_seconds,times=times,phase_events=events,restricted=restricted,native_tree_restart_supported=False)
    if m.SolCount:point_save(folder/'FINAL_POINT.npz',np.array(m.getAttr('X')))
    assert parameters(m)==effective
    objective_after=verifier.verify(ROOT,dict(names=np.array(m.getAttr('VarName')),objective=np.array(m.getAttr('Obj')),constant=np.array(m.ObjCon)),int(m.ModelSense));assert objective_after['PASS'];m.dispose();gp.Model.optimize=original_optimize
    atomic(folder/'NATIVE_RECEIPT.json',receipt);resources.phase='REPLAY'
    reader=hc.physical_reader();seen=set();audits=[];best=float(center[239826]);best_point=center;best_audit=center_check
    paths=[folder/r['point'] for r in incumbents]+([folder/'FINAL_POINT.npz'] if receipt['SolCount'] else [])
    for p in paths:
        with np.load(p) as z:x=z['x'].copy()
        h=hashlib.sha256(x.tobytes()).hexdigest()
        if h in seen:continue
        seen.add(h);replay=full_replay(A,d,x,reader)
        if restricted:replay['restricted_replay']=hc.replay(B,e,x,True);replay['PASS']=bool(replay['PASS'] and replay['restricted_replay']['PASS'])
        audit=dict(point=p.relative_to(folder).as_posix(),SHA256=sha(p),rho=float(x[239826]),**replay);audits.append(audit)
        atomic(folder/'CANDIDATE_REPLAYS.json',dict(audits=audits,every_event_saved_before_replay=True))
        if audit['PASS'] and audit['rho']<best:best=audit['rho'];best_point=x;best_audit=audit
    point_save(folder/'BEST_VALID_POINT.npz',best_point);atomic(folder/'BEST_FULL_REPLAY.json',dict(**best_audit,valid_UB=best,point_SHA256=sha(folder/'BEST_VALID_POINT.npz')))
    resources.finish();log=(folder/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
    eligible=native_bound_valid(receipt,objective_after['PASS'],restricted,best,log)
    receipt.update(bound_authority=eligible,global_LB=max(args.initial_lb,eligible['global_LB_candidate']) if eligible['PASS'] else args.initial_lb,valid_UB=best,old_UB=float(center[239826]),UB_improvement=float(center[239826])-best,peak_RSS=max(r['RSS'] for r in resources.rows),all_incumbent_events_saved=len(incumbents),improving_valid_candidates=sum(r['PASS'] and r['rho']<float(center[239826]) for r in audits),objective_identity_after_PASS=True,severe_numerical_warnings=severe_warnings(log),start_acceptance_evidence=[l for l in log.splitlines() if 'MIP start' in l],native_tree_not_restartable=True,available_native_node_ledger='All observed MIPNODE counts; Gurobi does not expose every internal node proof through this interface',cut_summary=[l.strip() for l in log.splitlines() if re.match(r'\s+(Implied bound|MIR|Flow cover|Gomory|Clique|Zero half|Relax-and-lift|RLT|BQP|StrongCG|Mod-K):',l)])
    if restricted:receipt.update(best_Hamming=int(np.count_nonzero((best_point[free]>.5)!=(center[free]>.5))),radius=args.radius,boundary_active=int(np.count_nonzero((best_point[free]>.5)!=(center[free]>.5)))==args.radius)
    receipt['global_gap']=(best-receipt['global_LB'])/abs(best);atomic(folder/'RESULT.json',receipt)
    print('NATIVE_COMPLETE',args.name,receipt['Status'],receipt['NodeCount'],receipt['global_LB'],best,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--kind',choices=['control','production','primal'],required=True);p.add_argument('--seconds',type=float,required=True);p.add_argument('--center',required=True);p.add_argument('--initial-lb',type=float,default=INITIAL_LB);p.add_argument('--radius',type=int);a=p.parse_args()
    assert a.name.replace('_','').isalnum(),'SAFE_RUN_NAME_REQUIRED'
    try:run(a)
    except BaseException:
        folder=OUT/'runs'/a.name
        atomic(folder/'EXECUTION_ERROR.json',dict(UTC=stamp(),optimize_started=(folder/'OPTIMIZE_ONCE.json').exists(),error=traceback.format_exc()))
        raise
