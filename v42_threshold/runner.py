"""Two bounded witness generators followed by one unrestricted decision solve."""
import threading,re
import gurobipy as gp
import psutil
from .common import *
from .validate import validate_point

def freeze():
    assert not list(LOCAL.glob('*_STARTED.json'))
    files=[p for folder in [ROOT/'v42_threshold',ROOT/'tests/v42_threshold'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    dump('EXECUTION_FREEZE.json',dict(BASE_HEAD=BASE,created_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),source_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(files)],
        root_candidates_sha256=sha(OUT/'ROUTE_WITNESS_CANDIDATES.json'),template_sha256=sha(LOCAL/'F3.mps'),before_any_new_optimization=True))

def seed(m,candidate,complete=None):
    m.NumStart=1;m.Params.StartNumber=0
    names=m.getAttr('VarName')
    if complete is not None:
        m.setAttr('Start',complete.tolist());m.update();return 'complete independently validated threshold witness'
    r,_=root(candidate['source']);paths={u:set(chosen) for u,chosen in candidate['routes'].items()}
    values=[gp.GRB.UNDEFINED]*len(names)
    for i,n in enumerate(names):
        if not domains()[i]:continue
        if n.startswith('arc['):u,k=n[4:-1].split(',');values[i]=int(int(k) in paths[u])
        elif n.startswith('charge_mode['):values[i]=int(r[n]>=.5)
    m.setAttr('Start',values);m.update();return 'B3-only integral route plus rounded-root mode partial start; continuous/outside undefined'

def run(kind,candidate=None,witness=None):
    assert kind in ['W1','W2','DIRECT']
    marker=LOCAL/(kind+'_STARTED.json');assert not marker.exists(),'ONE_SHOT_ONLY'
    freeze_data=read(OUT/'EXECUTION_FREEZE.json')
    for f in freeze_data['source_files']:assert sha(ROOT/f['path'])==f['sha256'],f['path']
    assert sha(OUT/'PREREGISTRATION.json')==freeze_data['preregistration_sha256']
    assert sha(OUT/'ROUTE_WITNESS_CANDIDATES.json')==freeze_data['root_candidates_sha256']
    assert sha(LOCAL/'F3.mps')==freeze_data['template_sha256']
    if kind=='DIRECT':
        assert (OUT/'WITNESS_SEARCH_COMPLETE.json').exists()
        candidate=read(OUT/'ROUTE_WITNESS_CANDIDATES.json')['candidates'][0]
    before=resource_snapshot();dump(kind+'_RESOURCE_BEFORE.json',before)
    # Register one resource-aware policy, not a performance experiment.
    registered=settings(kind)
    if before['other_heavy_solve'] and registered['Threads']==4:raise AssertionError('RESOURCE_CONTENTION_BEFORE_START: registered4 cannot launch beside observed heavy solve')
    build_begin=time.perf_counter();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=threshold_model(env)
    fixed=[]
    if kind!='DIRECT':
        paths={u:set(ks) for u,ks in candidate['routes'].items()}
        for i,v in enumerate(m.getVars()):
            if domains()[i] and v.VarName.startswith('arc['):
                u,k=v.VarName[4:-1].split(',');v.LB=v.UB=int(int(k) in paths[u]);fixed.append(v.VarName)
        m.update()
    assert not fixed if kind=='DIRECT' else len(fixed)==85592
    start_policy=seed(m,candidate,witness)
    logpath=LOCAL/(kind+'.log');assert not logpath.exists()
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(logpath)
    for k,v in registered.items():setattr(m.Params,k,v)
    dump(kind+'_DOMAIN.json',dict(restored_binary_count=85744,fixed_route_bounds=len(fixed),full_direct_unrestricted=kind=='DIRECT',
        outside_B3_variables_free=True,mode_bounds_not_fixed=True,removed_rows=0,new_rows=['B3_THRESHOLD_RHO'],route_pruning=0))
    payload=dict(kind=kind,created_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),execution_commit=git('rev-parse','HEAD'),
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),execution_freeze_sha256=sha(OUT/'EXECUTION_FREEZE.json'),settings=registered)
    marker.write_text(json.dumps(payload)+'\n',encoding='utf8');dump(kind+'_EXECUTION_MARKER.json',payload)
    build=time.perf_counter()-build_begin;begin=time.perf_counter();events={};progress=[];live=dict(phase='START',zero_objective_bound=None,zero_objective_incumbent=None,nodes=0.);peak=[psutil.Process().memory_info().rss]
    stop=threading.Event();callback_errors=[];first=[None]
    def cb(model,where):
        try:
            if where==gp.GRB.Callback.POLLING:return
            if where==gp.GRB.Callback.MESSAGE:return
            seconds=model.cbGet(gp.GRB.Callback.RUNTIME)
            if where==gp.GRB.Callback.PRESOLVE:live['phase']='PRESOLVE'
            elif where==gp.GRB.Callback.SIMPLEX:live['phase']='SIMPLEX';events.setdefault('simplex_first_seconds',seconds)
            elif where==gp.GRB.Callback.BARRIER:live['phase']='BARRIER';events.setdefault('barrier_first_seconds',seconds)
            elif where==gp.GRB.Callback.MIPSOL:
                live['phase']='MIPSOL';first[0]=first[0] or dict(seconds=seconds,zero_objective=model.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
            elif where==gp.GRB.Callback.MIP:
                live.update(phase='BRANCH_AND_CUT',zero_objective_bound=model.cbGet(gp.GRB.Callback.MIP_OBJBND),zero_objective_incumbent=model.cbGet(gp.GRB.Callback.MIP_OBJBST),nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT))
        except Exception as exc:callback_errors.append(str(exc));model.terminate()
    def monitor():
        previous=0.
        while not stop.wait(1):
            seconds=time.perf_counter()-begin;peak[0]=max(peak[0],psutil.Process().memory_info().rss)
            if seconds-previous>=10:
                row=dict(seconds=seconds,**{k:v if not isinstance(v,float) or abs(v)<1e90 else None for k,v in live.items()},RSS_bytes=psutil.Process().memory_info().rss)
                progress.append(row);previous=seconds
            if int(seconds)%60==0:print('PROGRESS',kind,round(seconds,1),live,flush=True)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    print('START',kind,'threshold',T,'zero objective','fixed route bounds',len(fixed),'build',round(build,2),'settings',registered,flush=True)
    try:m.optimize(cb)
    finally:stop.set();thread.join(2)
    wall=time.perf_counter()-begin;status=int(m.Status);m.Params.LogFile='';raw=logpath.read_text(encoding='utf8')
    (OUT/(kind+'_SOLVER.raw.gz')).write_bytes(gzip.compress(raw.encode(),mtime=0))
    result=dict(kind=kind,solver_status=status,SolCount=int(m.SolCount),zero_objective=float(m.ObjVal) if m.SolCount else None,
        zero_objective_BestBd=float(m.ObjBound) if m.IsMIP and abs(m.ObjBound)<1e90 else None,
        zero_objective_bound_not_B3_rho_LB=True,proven_infeasible=status==3 and kind=='DIRECT',
        candidate_infeasibility_not_full_B3_certificate=kind!='DIRECT',settings=registered,build_seconds=build,optimize_seconds=wall,native_seconds=m.Runtime,
        nodes=float(m.NodeCount),root_completed='Root relaxation:' in raw,root_relaxation_seconds=(re.findall(r'Root relaxation:.*?([0-9.]+) seconds',raw) or [None])[-1],
        events=events,first_incumbent=first[0],peak_RSS_bytes=peak[0],callback_errors=callback_errors,resource_before=before,
        start_policy=start_policy,start_log_lines=[line.strip() for line in raw.splitlines() if 'start' in line.lower()],
        inherited_original_complete_start_rho=ORIGINAL_UB,inherited_start_violates_threshold=True,inherited_start_not_passed_as_feasible=True,
        raw_log_sha256=sha(OUT/(kind+'_SOLVER.raw.gz')),optimize_calls=1,production=False,P2=False,B1=False,B2=False,
        matrix_identity=sha(OUT/'B3_THRESHOLD_MATRIX_IDENTITY.json'),fixed_route_bounds=len(fixed),validation=None,
        solver_infeasibility_proof='Native overall status INFEASIBLE for unrestricted threshold MIP; full branch-and-bound proof at registered tolerances' if status==3 and kind=='DIRECT' else None,
        rational_arithmetic_proof=False,Farkas_dual_available_for_full_MIP=False,IIS_api_available=True,IIS_computed=False,
        IIS_reason='Full MIP IIS can require additional expensive search; raw native status retained without automatic IIS/decomposition solve.')
    if m.SolCount:
        names=np.asarray(m.getAttr('VarName'));values=np.asarray(m.getAttr('X'))
        np.savez_compressed(OUT/(kind+'_SOLUTION.npz'),names=names,values=values)
        validation,slots=validate_point(m,names,values)
        dump(kind+'_POINT_VALIDATION.json',validation);table(kind+'_RECOMPUTED_P1.csv',slots);result['validation']=validation
    dump(kind+'_SOLVER.json',result)
    table(kind+'_PROGRESS.csv',progress,['seconds','phase','zero_objective_bound','zero_objective_incumbent','nodes','RSS_bytes'])
    print('COMPLETE',kind,'status',status,'SolCount',m.SolCount,'seconds',round(wall,2),'valid witness',bool(result['validation'] and result['validation']['threshold_certificate_PASS']),flush=True)
    m.dispose();env.dispose();assert not callback_errors,callback_errors
    return result

def all_runs():
    assert not (OUT/'B3_THRESHOLD_SOLVER.json').exists()
    candidates=read(OUT/'ROUTE_WITNESS_CANDIDATES.json')['candidates'];results=[];witness=None;seen=set()
    for c in candidates:
        signature=tuple((u,tuple(k for k in chosen if arcs()[k][1]<=95 and arcs()[k][3]>58 or 58<=arcs()[k][1]<=95)) for u,chosen in sorted(c['routes'].items()))
        if witness is not None:
            results.append(dict(candidate=c['id'],execution='NOT_RUN_CERTIFICATE_ALREADY_FOUND',status=None,rho=None,threshold_slack=None,validated_witness=False,optimize_calls=0));continue
        if signature in seen:
            results.append(dict(candidate=c['id'],execution='NOT_RUN_EXACT_DUPLICATE_ROUTE_BOUNDS',status=None,rho=None,threshold_slack=None,validated_witness=False,optimize_calls=0));continue
        seen.add(signature);r=run(c['id'],c);v=r['validation']
        results.append(dict(candidate=c['id'],execution='RUN',status=r['solver_status'],rho=v['rho'] if v else None,
            threshold_slack=v['threshold_slack'] if v else None,validated_witness=bool(v and v['threshold_certificate_PASS']),optimize_calls=1))
        if v and v['threshold_certificate_PASS']:
            with np.load(OUT/(c['id']+'_SOLUTION.npz'),allow_pickle=False) as z:witness=z['values']
    table('B3_WITNESS_SEARCH_RESULTS.csv',results)
    dump('WITNESS_SEARCH_COMPLETE.json',dict(candidates=results,validated_safe_witness_found=witness is not None,candidate_count_preregistered=2,
        original_B3_scientific_model_not_restricted=True,failed_candidate_not_negative_evidence=True))
    direct=run('DIRECT',witness=witness);dump('B3_THRESHOLD_SOLVER.json',direct)
    for source,target in [('DIRECT_SOLVER.raw.gz','B3_THRESHOLD_SOLVER.raw.gz'),('DIRECT_PROGRESS.csv','B3_THRESHOLD_PROGRESS.csv')]:
        (OUT/target).write_bytes((OUT/source).read_bytes())
    print('THRESHOLD ALL RUNS FINISHED',flush=True)

if __name__=='__main__':
    import sys
    freeze() if sys.argv[1]=='freeze' else all_runs()
