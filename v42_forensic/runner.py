"""One-shot original-F3 counterfactual, partial MIPs and exact UB subsets."""
import math,os,threading,time
import gurobipy as gp
import psutil
from .common import *

def configure(m,name,original,start,arcs,window,units):
    modes=name in ['R_ACTIVE','R_BUFFER'] or name.startswith('U')
    partial=name.startswith('R_') or name.startswith('U')
    restored=[];fixed=[];removed=[]
    for v,kind,value in zip(m.getVars(),original,start):
        if kind!='B':continue
        n=v.VarName;restore=not partial
        if partial:
            restore=False
            if n.startswith('arc['):
                u,k=n[4:-1].split(',');restore=u in units and selected_arc(arcs[int(k)],*window)
            elif n.startswith('charge_mode['):
                u,t=n[12:-1].split(',');restore=modes and u in units and window[0]<=int(t)<=window[1]
        if name in ['TERM_RELAX','P_FIXED_ALL']:restore=False
        v.VType=gp.GRB.BINARY if restore else gp.GRB.CONTINUOUS
        if restore:restored.append(n)
        fix=name=='P_FIXED_ALL' or name=='P_FIXED_ROUTE' and n.startswith('arc[')
        if name=='P_LATE_ROUTE_NEIGHBORHOOD' and n.startswith('arc['):
            u,k=n[4:-1].split(',');fix=not selected_arc(arcs[int(k)],*window)
        if fix:
            assert abs(value-round(value))<=TOL
            v.LB=v.UB=round(value);fixed.append(n)
    m.update();return restored,fixed

def numeric_validate(m,values):
    A=m.getA();v=np.asarray(values);rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'));r=A@v-rhs
    error=np.where(sense=='=',abs(r),np.where(sense=='<',r,-r))
    maximum=max(0.,float(error.max()),float((np.asarray(m.getAttr('LB'))-v).max()),float((v-np.asarray(m.getAttr('UB'))).max()))
    return dict(PASS=maximum<=TOL,matrix_max_violation=maximum)

def validate_full_plan(names,values,original):
    binary=np.flatnonzero(original=='B');integrality=float(np.max(abs(values[binary]-np.rint(values[binary]))))
    if integrality>TOL:return dict(full_original_integer=False,max_original_binary_fractionality=integrality,valid_new_UB=False)
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    from v42_bootstrap.grid import grid_report
    from v42_m1_sparse.post_validate import controls_from_plan
    bundle,anchor,inc,sites,initial,routes,b=inputs();arcs=arcs_for(sites,routes);v=inc['values'].copy();v.update(dict(zip(map(str,names),map(float,values))))
    plan=dict(inc);plan['values']=v;plan['chosen_arcs']={u:[k for k in range(len(arcs)) if v.get(f'arc[{u},{k}]',0.)>.5] for u in initial}
    physical=validate(plan,sites,routes,b,96);extra=supplemental_physical(plan,sites,b);grid=grid_report(bundle,controls_from_plan(plan,anchor),v['rho_max'])
    initialpass=all(abs(v[f'SOC[{u},0]']-b.initial)<=TOL for u in initial)
    ok=physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS'] and initialpass
    return dict(full_original_integer=True,max_original_binary_fractionality=integrality,valid_new_UB=bool(ok),
        objective=v['rho_max'],physical=physical,extra=extra,robust_grid=grid,initial_SOC_PASS=initialpass,AIDC_anchor_unchanged=True)

def run(name):
    target=OUT/(name+'_OPTIMIZATION.json');assert not target.exists(),'ONE_SHOT_RESULT_ALREADY_EXISTS'
    marker=LOCAL/(name+'_OPTIMIZE_STARTED.json');assert not marker.exists(),'ONE_SHOT_OPTIMIZATION_ALREADY_STARTED'
    assert read(OUT/'BASE_F3_IDENTITY.json')['PASS']
    if name.startswith('R_') or name.startswith('U'):assert read(OUT/'WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')['PASS']
    window=read(OUT/'WINDOW_DEFINITION.json');w=window['W_BUFFER'] if name in ['R_BUFFER','P_LATE_ROUTE_NEIGHBORHOOD'] else window['W_ACTIVE']
    _,_,_,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes);units=sorted(initial)
    if name.startswith('U'):units=[sorted(initial)[int(name[1])-1]]
    with np.load(OUT/'F3_MODEL_AXIS.npz',allow_pickle=False) as z:
        names=z['names'];original=z['original_types'];lower=z['lower'];upper=z['upper'];start=z['start'];term=z['terminal_rows']
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'F3.mps'),env=env)
    assert list(names)==m.getAttr('VarName') and np.array_equal(lower,m.getAttr('LB')) and np.array_equal(upper,m.getAttr('UB'))
    # Base receipt seals exact matrix. Only VTypes and authorized fixed bounds change.
    restored,fixed=configure(m,name,original,start,arcs,w,units)
    if name=='TERM_RELAX':m.remove([m.getConstrs()[int(i)] for i in term]);m.update()
    m.setAttr('Start',list(start));m.update()
    startcheck=numeric_validate(m,start);assert startcheck['PASS']
    with gzip.open(OUT/(name+'_DOMAIN.json.gz'),'wt',encoding='utf8') as f:json.dump(dict(restored=restored,fixed=fixed,terminal_rows_removed=list(map(int,term)) if name=='TERM_RELAX' else []),f)
    limit=600 if name.startswith('R_') or name=='P_LATE_ROUTE_NEIGHBORHOOD' else 300 if name=='P_FIXED_ROUTE' or name.startswith('U') else None
    m.Params.Method=2;m.Params.Threads=1;m.Params.OutputFlag=1;m.Params.LogToConsole=0
    if m.IsMIP:
        m.Params.Heuristics=0;m.Params.MIPFocus=3;m.Params.MIPGap=.005;m.Params.Seed=20260929
    if limit is not None:m.Params.TimeLimit=limit
    process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();messages=[];progress=[];events={};snapshots={};begin=time.perf_counter();last=[-10.];last_notice=[0.];first=[]
    def monitor():
        while not stop.wait(.25):peak[0]=max(peak[0],process.memory_info().rss)
    def cb(model,where):
        if where==gp.GRB.Callback.POLLING:return
        elapsed=model.cbGet(gp.GRB.Callback.RUNTIME)
        if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING))
        elif where==gp.GRB.Callback.PRESOLVE:events['presolve_last_seconds']=elapsed
        elif where in [gp.GRB.Callback.BARRIER,gp.GRB.Callback.SIMPLEX]:events.setdefault('root_optimizer_first_seconds',elapsed)
        elif where==gp.GRB.Callback.MIPSOL:
            objective=model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)
            if not first:first.append(dict(seconds=elapsed,objective=objective))
        elif where==gp.GRB.Callback.MIP:
            node=model.cbGet(gp.GRB.Callback.MIP_NODCNT);incumbent=model.cbGet(gp.GRB.Callback.MIP_OBJBST);bound=model.cbGet(gp.GRB.Callback.MIP_OBJBND)
            if node>0:events.setdefault('first_positive_processed_node_count_seconds',elapsed)
            for threshold in [300,600]:
                if elapsed>=threshold and threshold not in snapshots:snapshots[threshold]=dict(seconds=elapsed,BestBd=bound)
            if elapsed-last[0]>=5:
                progress.append(dict(seconds=elapsed,incumbent=incumbent if abs(incumbent)<1e90 else None,BestBd=bound if abs(bound)<1e90 else None,node_count=node));last[0]=elapsed
            if elapsed-last_notice[0]>=60:
                print('PROGRESS',name,round(elapsed,1),'BestBd',bound,'incumbent',incumbent,'nodes',node,flush=True);last_notice[0]=elapsed
        elif where==gp.GRB.Callback.MIPNODE:
            node=model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
            if node>0:events.setdefault('first_non_root_node_seconds',elapsed)
            elif model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL:events.setdefault('root_relaxation_complete_seconds',elapsed)
    marker.write_text(json.dumps(dict(name=name,settings=dict(Method=2,Threads=1,TimeLimit=limit),window=w))+'\n',encoding='utf8')
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    print('START',name,'restored',len(restored),'fixed',len(fixed),'TimeLimit',limit,flush=True)
    try:m.optimize(cb)
    finally:stop.set();thread.join(1)
    elapsed=time.perf_counter()-begin;status=int(m.Status);upper_value=float(m.ObjVal) if m.SolCount else None
    rawbound=float(m.ObjBound) if m.IsMIP else float(m.ObjVal) if status==gp.GRB.OPTIMAL else None
    if rawbound is not None and abs(rawbound)>=1e90:rawbound=None
    validated=None;full=None
    if m.SolCount:
        vv=np.asarray(m.getAttr('X'));validated=numeric_validate(m,vv);assert validated['PASS']
        binary_indices=np.flatnonzero(np.asarray(m.getAttr('VType'))=='B')
        maxrestored=float(np.max(abs(vv[binary_indices]-np.rint(vv[binary_indices])))) if len(binary_indices) else 0.
        assert maxrestored<=TOL
        np.savez_compressed(OUT/(name+'_SOLUTION.npz'),names=names,values=vv)
        if name!='TERM_RELAX':full=validate_full_plan(names,vv,original)
    assert status not in [gp.GRB.INFEASIBLE,gp.GRB.INF_OR_UNBD,gp.GRB.UNBOUNDED],(name,status)
    if name=='TERM_RELAX':assert status==gp.GRB.OPTIMAL,'TERM_RELAX_REQUIRES_LP_OPTIMALITY'
    partial=name.startswith('R_') or name.startswith('U');certified=max(F3,rawbound) if partial and rawbound is not None else F3 if partial else rawbound
    negative=bool(partial and validated and upper_value-F3<=.001)
    log=''.join(messages);(OUT/(name+'_SOLVER.log.gz')).write_bytes(gzip.compress(log.encode(),mtime=0))
    # Completed early => final bound at later checkpoints; missing callbacks near
    # a time-limit boundary are explicitly marked, not invented observations.
    checkpoints={str(t):(snapshots[t] if t in snapshots else dict(seconds=elapsed,BestBd=rawbound,source='completed_before_checkpoint') if elapsed<t else dict(seconds=None,BestBd=None,source='no_callback_observation_at_checkpoint')) for t in [300,600]}
    result=dict(name=name,status=status,run=True,optimize_calls=1,solver_optimal=status==gp.GRB.OPTIMAL,window=w,units=units,
        restored_binaries=len(restored),fixed_binary_bounds=len(fixed),binary_variables=m.NumBinVars,continuous_variables=m.NumVars-m.NumIntVars,
        rows=m.NumConstrs,columns=m.NumVars,nonzeros=m.NumNZs,settings=dict(Method=2,Threads=1,Heuristics=0 if m.IsMIP else None,MIPFocus=3 if m.IsMIP else None,MIPGap=.005 if m.IsMIP else None,Seed=20260929 if m.IsMIP else None,GPU=False,TimeLimit=limit),
        first_incumbent=first[0] if first else None,incumbent_objective=upper_value,final_BestBd=rawbound,certified_global_LB=certified if partial else None,
        LB_gain=certified-F3 if partial else None,partial_gap=float(m.MIPGap) if m.IsMIP and m.SolCount else None,
        checkpoints=checkpoints,node_count=float(m.NodeCount) if m.IsMIP else 0.,events=events,
        root_relaxation_seconds=events['root_relaxation_complete_seconds']-events.get('root_optimizer_first_seconds',0.) if 'root_relaxation_complete_seconds' in events else None,
        root_processing_seconds_estimate=events.get('first_non_root_node_seconds',elapsed)-events.get('root_optimizer_first_seconds',0.),
        presolve_seconds=events.get('root_optimizer_first_seconds',events.get('presolve_last_seconds')),wall_seconds=elapsed,native_seconds=m.Runtime,peak_RSS=peak[0],
        inherited_start_matrix_validation=startcheck,solution_matrix_validation=validated,full_original_integer_validation=full,
        original_feasible_UB=upper_value if full and full['valid_new_UB'] else None,
        negative_certificate=negative,negative_certificate_type='matrix-validated partial feasible upper-F3<=0.001' if negative else None,
        classification='CERTIFIED_NONMATERIAL' if negative else 'DETECTABLE_LB_CONTRIBUTION' if partial and certified-F3>=.001 else 'COMPUTATIONALLY_INCONCLUSIVE' if partial else 'UB_DIAGNOSTIC' if name.startswith('P_') else 'COUNTERFACTUAL_DIAGNOSTIC',
        no_arc_pruning=True,scientific_physics_changed=name=='TERM_RELAX',diagnostic_only=True,production=False,template_sha256=sha(LOCAL/'F3.mps'))
    if name=='TERM_RELAX':result.update(rho_TERM_RELAX=upper_value,delta_terminal=F3-upper_value,production_valid=False)
    dump(name+'_OPTIMIZATION.json',result);table(name+'_PROGRESS.csv',progress,['seconds','incumbent','BestBd','node_count'])
    print('COMPLETE',name,'status',status,'UB',upper_value,'BestBd',rawbound,'LBgain',result['LB_gain'],'negative',negative,'seconds',round(elapsed,2),flush=True)
    m.dispose();env.dispose();return result

def all_arms():
    run('TERM_RELAX')
    remaining()

def remaining():
    for n in ['R_ROUTE_ONLY','R_ACTIVE','R_BUFFER']:run(n)
    conditional_and_primal()

def after_active():
    run('R_BUFFER')
    conditional_and_primal()

def conditional_and_primal():
    if read(OUT/'R_ACTIVE_OPTIMIZATION.json')['LB_gain']>=.001:
        for i in range(1,5):run(f'U{i}_ACTIVE')
    for n in ['P_FIXED_ALL','P_FIXED_ROUTE','P_LATE_ROUTE_NEIGHBORHOOD']:run(n)
if __name__=='__main__':
    import sys
    if sys.argv[1]=='all':all_arms()
    elif sys.argv[1]=='remaining':remaining()
    elif sys.argv[1]=='after_active':after_active()
    else:run(sys.argv[1])
