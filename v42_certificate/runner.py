"""One preregistered certificate strategy, with complete validated MIP starts."""
import re,threading
import gurobipy as gp
import psutil
from .common import *

def finite(x):return float(x) if abs(x)<1e90 else None
def acceptance(log,first,solcount,final):
    loaded=bool(re.search(r'Loaded user MIP start with objective',log))
    firstok=bool(first and first['objective']<=START_UB+OBJ_TOL)
    return dict(PASS=loaded and firstok and solcount>0 and final<=START_UB+OBJ_TOL,
        loaded_user_start_log=loaded,first_incumbent=first,final_incumbent=final,SolCount=solcount,
        old_UB_fallback=False,authority_UB=START_UB,objective_tolerance=OBJ_TOL,
        rejection_log_lines=[line for line in log.splitlines() if 'start' in line.lower() and any(s in line.lower() for s in ['violates','did not produce','rejected'])])

def run(arm):
    assert arm in ['B1','B2','B3'],'SCOPE_CORRECTION_CERTIFICATE_ARMS_ONLY'
    marker=LOCAL/(arm+'_OPTIMIZE_STARTED.json');assert not marker.exists(),'ONE_PREREGISTERED_RUN_ONLY'
    assert read(OUT/'MIP_START_IMPORT_AUDIT.json')['PASS']
    assert read(OUT/'NESTING_DOMAIN_VALIDATION.json')['PASS']
    if arm=='B3':assert read(OUT/'SCOPE_CORRECTION_ADDENDUM.json')['before_any_new_optimization']
    if arm=='B2':assert read(OUT/'B3_BUFFER_CERTIFICATE.json')['material']
    if arm=='B1':assert read(OUT/'B2_ROUTE_MODE_CERTIFICATE.json')['material']
    begin_build=time.perf_counter();axis=load_axis();names,values=load_start();routearcs=arcs()
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'F3.mps'),env=env)
    assert m.getAttr('VarName')==list(names)
    restored=[str(n) for n,k in zip(names,axis['original_types']) if restore(str(n),str(k),arm,routearcs)]
    types=['B' if restore(str(n),str(k),arm,routearcs) else 'C' for n,k in zip(names,axis['original_types'])]
    m.setAttr('VType',types);m.update()
    assert m.NumConstrs==954560 and m.NumVars==316743 and m.NumNZs==8282350
    assert np.array_equal(m.getAttr('LB'),axis['lower']) and np.array_equal(m.getAttr('UB'),axis['upper'])
    with np.load(OUT/'MPS_ROW_ALIAS_AXIS.npz',allow_pickle=False) as z:assert m.getAttr('ConstrName')==list(z['mps_names'])
    assert np.count_nonzero(m.getAttr('Obj'))==1 and m.getVarByName('rho_max').Obj==1 and m.ModelSense==1
    m.NumStart=1;m.Params.StartNumber=0;m.setAttr('Start',list(values));m.update()
    assert m.NumStart==1 and np.array_equal(m.getAttr('Start'),values)
    check=matrix_validation(m,values);assert check['PASS']
    binary=np.flatnonzero(np.asarray(types)=='B');assert float(np.max(abs(values[binary]-np.rint(values[binary]))))<=TOL
    logpath=LOCAL/(arm+'.log');assert not logpath.exists()
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(logpath)
    settings=dict(SETTINGS)
    if arm=='NATIVE_START':settings.update(TimeLimit=30.,Heuristics=0.,SolutionLimit=1,MIPGap=.005)
    if arm=='PRODUCTION':settings.update(MIPGap=.005,MIPGapAbs=0.)
    for k,v in settings.items():setattr(m.Params,k,v)
    (OUT/(arm+'_DOMAIN.json.gz')).write_bytes(gzip.compress(json.dumps(dict(restored=restored,fixed=[],removed_rows=[],new_rows=[],windows=WINDOWS.get(arm))).encode(),mtime=0))
    marker.write_text(json.dumps(dict(arm=arm,execution_commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),scope_addendum_sha256=sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json'),settings=settings))+'\n',encoding='utf8')
    build=time.perf_counter()-begin_build;events={};first=[];first_values=[];progress=[];last=[-10.];reason=[None];vars=m.getVars()
    process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();beg=time.perf_counter()
    live={'phase':'MIP_START','bound':None,'incumbent':None,'nodes':0.}
    def monitor():
        last_print=time.perf_counter()
        while not stop.wait(.5):
            peak[0]=max(peak[0],process.memory_info().rss)
            if time.perf_counter()-last_print>=60:
                print('PROGRESS',arm,round(time.perf_counter()-beg,1),dict(live),flush=True);last_print=time.perf_counter()
    def cb(model,where):
        if where==gp.GRB.Callback.POLLING:return
        if where==gp.GRB.Callback.MESSAGE:return
        seconds=model.cbGet(gp.GRB.Callback.RUNTIME)
        if where==gp.GRB.Callback.PRESOLVE:live['phase']='PRESOLVE'
        elif where==gp.GRB.Callback.BARRIER:live['phase']='ROOT_BARRIER';events.setdefault('barrier_first_seconds',seconds)
        elif where==gp.GRB.Callback.SIMPLEX:live['phase']='SIMPLEX';events.setdefault('simplex_first_seconds',seconds)
        elif where==gp.GRB.Callback.MIPSOL:
            obj=model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)
            if not first:
                first.append(dict(seconds=seconds,objective=obj));first_values.append(np.asarray(model.cbGetSolution(vars)))
            if live['incumbent'] is None or obj<live['incumbent']:live['incumbent']=obj
            if arm.startswith('B') and obj<=S2+MATERIAL-OBJ_TOL:
                reason[0]='NEGATIVE_UPPER_CANDIDATE';model.terminate()
        elif where==gp.GRB.Callback.MIP:
            bound=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND));inc=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBST));nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT)
            live.update(phase='BRANCH_AND_CUT',bound=bound,incumbent=inc,nodes=nodes)
            if seconds-last[0]>=10:
                progress.append(dict(seconds=seconds,BestBd=bound,incumbent=inc,node_count=nodes));last[0]=seconds
            if arm.startswith('B') and bound is not None and bound>=S2+MATERIAL+OBJ_TOL:
                reason[0]='POSITIVE_BOUND_CANDIDATE';model.terminate()
        elif where==gp.GRB.Callback.MIPNODE:
            if model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)>0:events.setdefault('first_non_root_node_seconds',seconds)
            elif model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL:events.setdefault('root_complete_seconds',seconds)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    print('START',arm,'B',len(restored),'build',round(build,2),'settings',settings,flush=True)
    try:m.optimize(cb)
    finally:stop.set();thread.join(2)
    wall=time.perf_counter()-beg;status=int(m.Status);upper=float(m.ObjVal) if m.SolCount else None;bound=finite(m.ObjBound)
    m.Params.LogFile='';log=logpath.read_text(encoding='utf8');(OUT/(arm+'_SOLVER.log.gz')).write_bytes(gzip.compress(log.encode(),mtime=0))
    accepted=acceptance(log,first[0] if first else None,int(m.SolCount),upper)
    assert accepted['PASS'],('STOP_MIP_START_REJECTED_OR_OLD_UB_FALLBACK',arm,accepted)
    assert status not in [gp.GRB.INFEASIBLE,gp.GRB.INF_OR_UNBD,gp.GRB.UNBOUNDED,gp.GRB.NUMERIC],(arm,status)
    vv=np.asarray(m.getAttr('X'));matrix=matrix_validation(m,vv);assert matrix['PASS']
    frac=float(np.max(abs(vv[binary]-np.rint(vv[binary]))));assert frac<=TOL
    assert abs(vv[list(names).index('rho_max')]-upper)<=OBJ_TOL
    np.savez_compressed(OUT/(arm+'_SOLUTION.npz'),names=names,values=vv)
    full=original_validation(names,vv)
    root=re.findall(r'Root relaxation:.*?([0-9.]+) seconds',log);presolve=re.findall(r'Presolve time: ([0-9.]+)s',log)
    partial=arm.startswith('B');old_name={'B1':'R_ROUTE_ONLY','B2':'R_ACTIVE','B3':'R_BUFFER'}[arm]
    inherited_lb=read(PRIOR/(old_name+'_OPTIMIZATION.json'))['certified_global_LB']
    lower=max(F3,inherited_lb,bound) if bound is not None else max(F3,inherited_lb)
    result=dict(arm=arm,solver_status=status,solver_optimal=status==2,SolCount=int(m.SolCount),raw_BestBd=bound,
        valid_partial_LB=lower if partial else None,original_global_LB=max(S2,lower) if partial else max(S2,bound) if bound is not None else S2,
        solver_incumbent=upper,validated_original_UB=upper if full['valid_new_UB'] else None,
        direct_interval=interval(lower,upper,status) if partial else None,
        initial_start_acceptance=accepted,build_seconds=build,optimize_wall_seconds=wall,native_seconds=m.Runtime,
        settings=settings,Seed=settings['Seed'],GPU=False,node_count=float(m.NodeCount),events=events,
        root_complete=bool(root),root_relaxation_seconds=float(root[-1]) if root else None,presolve_seconds=float(presolve[-1]) if presolve else None,
        peak_RSS_bytes=peak[0],stop_reason=reason[0],matrix_validation=matrix,restored_binary_fractionality=frac,
        original_integer_validation=full,rows=m.NumConstrs,columns=m.NumVars,nonzeros=m.NumNZs,
        restored_binaries=len(restored),continuous_variables=m.NumVars-m.NumIntVars,
        template_sha256=sha(LOCAL/'F3.mps'),start_sha256=sha(OUT/'MIP_START_EXACT.npz'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        raw_log_sha256=sha(OUT/(arm+'_SOLVER.log.gz')),optimize_calls=1,custom_cuts=0,no_pruning=True,
        original_physics_preserved=True,terminal_equality_retained=True,objective='MAX_LINE_LOADING',
        production=arm=='PRODUCTION',acceptance_probe=arm=='NATIVE_START',P2_run=False)
    dump(arm+'_OPTIMIZATION.json',result);table(arm+'_PROGRESS.csv',progress,['seconds','BestBd','incumbent','node_count'])
    if arm=='B3':
        initial_validation=original_validation(names,first_values[0]);assert initial_validation['valid_new_UB']
        assert matrix_validation(m,first_values[0])['PASS']
        np.savez_compressed(OUT/'MIP_START_NATIVE_ACCEPTED.npz',names=names,values=first_values[0])
        dump('MIP_START_NATIVE_ACCEPTANCE.json',dict(accepted,solver_status=status,root_complete=bool(root),node_count=float(m.NodeCount),
            production=False,separate_acceptance_probe=False,folded_into_B3=True,optimize_calls=1,original_full_binary_model=False,
            original_full_physical_matrix=True,initial_point_all_original_binaries_integer=True,
            accepted_initial_objective=first[0]['objective'],initial_original_integer_validation=initial_validation,
            raw_log_sha256=result['raw_log_sha256'],matrix_validation=matrix_validation(m,first_values[0]),physical_and_grid_PASS=True,
            start_axis_exact=True,complete_native_start_values=True,start_values_changed_by_solver_max=float(np.max(abs(first_values[0]-values)))))
    print('COMPLETE',arm,'status',status,'UB',upper,'bound',bound,'seconds',round(wall,2),flush=True)
    m.dispose();env.dispose();return result

def all_diagnostics():
    from .certificates import analyze
    certs={};executed=set()
    while (arm:=next_certificate_arm(certs,executed)) is not None:
        run(arm);runs,certs,_=analyze();executed=set(runs)
if __name__=='__main__':
    import sys
    all_diagnostics() if sys.argv[1]=='all' else run(sys.argv[1])
