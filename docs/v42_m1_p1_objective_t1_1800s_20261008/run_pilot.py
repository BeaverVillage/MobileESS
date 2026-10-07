"""Exactly one fresh full-domain 1800s native ORIGINAL P1 minimize-rho solve."""
from support import *
from objective_identity import verify as verify_objective
import argparse, re, threading, time, traceback

def finite(v):return float(v) if math.isfinite(float(v)) and abs(float(v))<1e90 else None
def parameters(m):
    effective={};defaults={}
    for n in dir(m.Params):
        if n.startswith('_'):continue
        try:
            info=m.getParamInfo(n)
            if info is not None:effective[n]=info[2];defaults[n]=info[5]
        except (AttributeError,RuntimeError):pass
    return effective,defaults

class Resources:
    def __init__(self):
        import psutil
        self.psutil=psutil;self.process=psutil.Process();self.phase='BUILD';self.begin=time.perf_counter();self.stop=threading.Event();self.samples=[]
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def sample(self):
        p=self.process.memory_info();s=self.psutil.virtual_memory();swap=self.psutil.swap_memory()
        r=dict(UTC=stamp(),wall_seconds=time.perf_counter()-self.begin,phase=self.phase,PID=os.getpid(),RSS=p.rss,VMS=p.vms,peak_wset=getattr(p,'peak_wset',None),system_available=s.available,system_memory_percent=s.percent,swap_used=swap.used,process_page_faults=getattr(p,'num_page_faults',None));self.samples.append(r)
        table('RESOURCE_TELEMETRY.csv',self.samples)
    def run(self):
        while not self.stop.is_set():
            self.sample();self.stop.wait(2)
    def finish(self):
        self.stop.set();self.thread.join(timeout=3);self.sample()

def preflight():
    assert git('merge-base',BASE,'HEAD')==BASE and not git('status','--porcelain=v1'),'COMMIT_PREFLIGHT_BEFORE_SOLVE'
    assert not (OUT/'OPTIMIZE_ONCE.json').exists(),'ONE_SOLVE_TOKEN_ALREADY_EXISTS'
    manifest=read(PARENT/'SHA256_MANIFEST.json')['files']
    assert all(sha(PARENT/n)==h for n,h in manifest.items()),'PR173_MANIFEST_CHANGED'
    validation=read(PARENT/'CUT_VALIDATION.json');assert validation['PASS']
    for name,digest in validation['verified_inputs_SHA256'].items():assert sha(PARENT/name)==digest,'STATIC_CERTIFICATE_CHANGED'
    identity=read(OUT/'BASE_IDENTITY.json');assert protected()==identity['protected_before']
    A,d,_=hc.load();C=sparse.load_npz(PARENT/'SELECTED_CUT_MATRIX.npz').tocsr()
    with np.load(PARENT/'SELECTED_CUT_DATA.npz') as z:rhs=z['rhs'];names=z['names']
    rho=read(PARENT/'THRESHOLD_AUTHORITY.json')['rho_column'];threshold=sparse.csr_matrix(([1.],([0],[rho])),shape=(1,A.shape[1]))
    B=sparse.vstack([A,threshold,C],format='csr')
    e=dict(d,objective=d['objective'].copy(),constant=d['constant'].copy())
    identity_check=verify_objective(ROOT,e)
    write('OBJECTIVE_PREFLIGHT.json',dict(**identity_check,optimize_calls=0,stage='BEFORE_NATIVE_BUILD'))
    assert identity_check['PASS'],'OBJECTIVE_IDENTITY_FAILURE_STOP_OPTIMIZE_0'
    e.update(rhs=np.r_[d['rhs'],T1,rhs],sense=np.concatenate([d['sense'],['<'],np.full(C.shape[0],'<')]),row_names=np.concatenate([d['row_names'],['TARGET_RHO_T1'],names]))
    assert (B[:A.shape[0]]!=A).nnz==0
    for field in ('names','lower','upper','types'):assert np.array_equal(e[field],d[field])
    assert (int((e['types']=='B').sum()),int((e['types']=='C').sum()))==(9322,296718)
    assert len(names)==364 and np.count_nonzero(e['objective'])==1 and e['objective'][rho]==1.
    return A,d,B,e,rho

def run():
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_integrated.matrix import arrays
    build_begin=time.perf_counter();A,d,B,e,rho=preflight();resources=Resources();model=build(B,e)
    model.ModelName='FULL_ORIGINAL_C3A_TARGET_RHO_T1_FEASIBILITY'
    for k,v in SETTINGS.items():model.setParam(k,v)
    model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(OUT/'NATIVE_SOLVER.log');model.update()
    variables=model.getVars();assert all(v.Start==gp.GRB.UNDEFINED for v in variables),'NO_INCUMBENT_START_ALLOWED'
    assert model.NumStart==0 and model.Params.NodeLimit>=gp.GRB.INFINITY
    native,nd=arrays(model)
    assert native.shape==B.shape and (native!=B).nnz==0,'NATIVE_COEFFICIENT_TRANSPORT_FAILED'
    for k in e:assert np.array_equal(nd[k],e[k]),'NATIVE_FIELD_CHANGED_'+k
    native_identity=verify_objective(ROOT,nd,int(model.ModelSense))
    write('OBJECTIVE_IDENTITY.json',dict(**native_identity,optimize_calls=0,verified_before_optimize=True,stage='NATIVE_ORIGINAL_P1_OBJECTIVE'))
    assert native_identity['PASS'],'NATIVE_OBJECTIVE_IDENTITY_FAILURE_STOP_OPTIMIZE_0'
    effective,defaults=parameters(model);assert all(effective[k]==v for k,v in SETTINGS.items())
    expected=read(PR175/'SOLVER_PARAMETERS.json')['all_effective_before_optimize'].copy()
    expected.update(TimeLimit=1800.,LogFile=str(OUT/'NATIVE_SOLVER.log'))
    assert clean(effective)==expected,'PARAMETER_CHANGED_VS_PR175'
    prior_model=read(PR175/'MODEL_TRANSPORT_AUTHORITY.json')
    assert (native!=B).nnz==0
    assert native_identity['PASS']
    assert B.shape==(prior_model['native_rows'],prior_model['original_columns']) and B.nnz==prior_model['native_nnz']
    build_seconds=time.perf_counter()-build_begin
    authority=dict(PASS=True,UTC=stamp(),full_C3A_rows_present=A.shape[0],original_columns=A.shape[1],B=9322,C=296718,original_nnz=A.nnz,native_rows=B.shape[0],native_nnz=B.nnz,threshold_rows=1,selected_valid_cuts=B.shape[0]-A.shape[0]-1,native_matrix_and_all_fields_bit_identical=True,original_bounds_and_types_identical=True,original_P1_objective_bit_identical=True,objective_identity_SHA256=sha(OUT/'OBJECTIVE_IDENTITY.json'),ObjCon=float(d['constant']),start_supplied=False,all_Start_UNDEFINED=True,no_domain_restriction=True,no_pruning=True,Fingerprint=int(model.Fingerprint),build_seconds=build_seconds,static_source_commit=git('rev-parse','HEAD'),cut_validation_SHA256=sha(PARENT/'CUT_VALIDATION.json'))
    write('MODEL_TRANSPORT_AUTHORITY.json',authority)
    write('SOLVER_PARAMETERS.json',dict(PASS=True,settings=SETTINGS,all_effective_before_optimize=effective,defaults=defaults,solver_version=list(gp.gurobi.version()),nondefault={k:v for k,v in effective.items() if v!=defaults[k]},objective='ORIGINAL_P1_MINIMIZE_RHO',start_supplied=False,sweep=False,parameters_changed_during_solve=False,all_effective_parameters_match_PR175_except_LogFile=True,TimeLimit_old=1800,TimeLimit_new=1800,LogFile_path_only_change=True))
    times=dict.fromkeys(['presolve_end','barrier_start','barrier_end','crossover_start','crossover_end','root_relaxation_complete','first_MIPNODE','first_nonroot_node','first_branch_evidence','first_feasible']);events=[];barrier=[];errors=[];traces=[];presolve_records=[];last_live=-30;trajectory=[];simplex=[];last_trajectory=-5;last_simplex=-5;last_nodes=-1
    saved=OUT/'incumbents';saved.mkdir(exist_ok=True)
    cut_matrix=B[A.shape[0]+1:];cut_rhs=e['rhs'][A.shape[0]+1:]
    cut_names=e['row_names'][A.shape[0]+1:];cut_families={c['id']:c['family'] for c in read(PARENT/'CUT_PROOFS.json')['cuts']}
    write('CUT_ACTIVITY.json',dict(available=False,reason='No completed native root LP observation yet',added_static_cuts=cut_matrix.shape[0],callback_cuts_added=0))
    fields=['event','UTC','native_Runtime','Work','original_rho','native_objective','node_count','point','SHA256']
    stream=(OUT/'INCUMBENT_TRACE.csv').open('w',encoding='utf-8',newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader();stream.flush()
    def cb(m,where):
        nonlocal last_live,last_trajectory,last_simplex,last_nodes
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=float(m.cbGet(gp.GRB.Callback.RUNTIME));work=float(m.cbGet(gp.GRB.Callback.WORK))
            if where==gp.GRB.Callback.MESSAGE:
                line=m.cbGet(gp.GRB.Callback.MSG_STRING).strip();ev=None
                if line.startswith('Presolve time:'):ev='presolve_end'
                elif 'barrier log' in line.lower() or line.startswith('Barrier statistics:'):ev='barrier_start'
                elif line.startswith('Barrier solved model'):ev='barrier_end'
                elif 'crossover log' in line.lower():ev='crossover_start'
                elif line.startswith('Crossover time:'):ev='crossover_end'
                elif line.startswith('Root relaxation:') and ('objective' in line or 'infeasible' in line):ev='root_relaxation_complete'
                if ev and times[ev] is None:
                    times[ev]=t;events.append(dict(event=ev,Runtime=t,Work=work,literal=line))
                    resources.phase={'presolve_end':'ROOT_SETUP','barrier_start':'ROOT_BARRIER','barrier_end':'ROOT_POST_BARRIER','crossover_start':'CROSSOVER','crossover_end':'ROOT_POST_CROSSOVER','root_relaxation_complete':'ROOT_MIP_PROCESSING'}[ev]
                if line.startswith(('Presolve removed','Presolve time:','Presolved:','Barrier statistics:')) or 'Factor NZ' in line or 'Factor Ops' in line or 'memory' in line.lower():presolve_records.append(dict(Runtime=t,literal=line))
            elif where==gp.GRB.Callback.BARRIER:
                # Save barrier progress at every exposed native barrier event.
                barrier.append(dict(Runtime=t,Work=work,iteration=int(m.cbGet(gp.GRB.Callback.BARRIER_ITRCNT)),primal_objective=finite(m.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ)),dual_objective=finite(m.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ)),primal_infeasibility=finite(m.cbGet(gp.GRB.Callback.BARRIER_PRIMINF)),dual_infeasibility=finite(m.cbGet(gp.GRB.Callback.BARRIER_DUALINF))))
            elif where==gp.GRB.Callback.SIMPLEX:
                if t-last_simplex>=5:
                    last_simplex=t;simplex.append(dict(Runtime=t,Work=work,phase=resources.phase,iterations=float(m.cbGet(gp.GRB.Callback.SPX_ITRCNT)),objective=finite(m.cbGet(gp.GRB.Callback.SPX_OBJVAL)),primal_infeasibility=finite(m.cbGet(gp.GRB.Callback.SPX_PRIMINF)),dual_infeasibility=finite(m.cbGet(gp.GRB.Callback.SPX_DUALINF))))
            elif where==gp.GRB.Callback.MIP:
                nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT))
                if nodes>1 and times['first_branch_evidence'] is None:
                    times['first_branch_evidence']=t;events.append(dict(event='first_branch_evidence',Runtime=t,Work=work,nodes=nodes,exact_branch_timestamp=False,authority='Earliest MIP callback observing more than one processed node; branching occurred by this time'))
                    resources.phase='POST_ROOT_SEARCH'
                if t-last_trajectory>=5 or nodes!=last_nodes:
                    last_trajectory=t;last_nodes=nodes
                    trajectory.append(dict(Runtime=t,Work=work,node_count=nodes,nodes_left=float(m.cbGet(gp.GRB.Callback.MIP_NODLFT)),solution_count=int(m.cbGet(gp.GRB.Callback.MIP_SOLCNT)),native_ObjBst=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),native_ObjBnd=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),simplex_iterations=float(m.cbGet(gp.GRB.Callback.MIP_ITRCNT)),cut_count=int(m.cbGet(gp.GRB.Callback.MIP_CUTCNT))))
                    table('BOUND_NODE_TRAJECTORY.csv',trajectory)
            elif where==gp.GRB.Callback.MIPNODE:
                nodes=float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))
                if times['first_MIPNODE'] is None:
                    times['first_MIPNODE']=t;events.append(dict(event='first_MIPNODE',Runtime=t,Work=work,nodes=nodes,status=int(m.cbGet(gp.GRB.Callback.MIPNODE_STATUS))))
                if nodes>0 and times['first_nonroot_node'] is None:
                    times['first_nonroot_node']=t;events.append(dict(event='first_nonroot_node',Runtime=t,Work=work,nodes=nodes));resources.phase='POST_ROOT_SEARCH'
                if nodes==0 and int(m.cbGet(gp.GRB.Callback.MIPNODE_STATUS))==gp.GRB.OPTIMAL and not (OUT/'NATIVE_ROOT_FEASIBILITY_LP_POINT.npz').exists():
                    point=np.asarray(m.cbGetNodeRel(variables));np.savez_compressed(OUT/'NATIVE_ROOT_FEASIBILITY_LP_POINT.npz',x=point)
                    residual=cut_matrix@point-cut_rhs;rows=[dict(id=str(n),family=cut_families[str(n)],residual=float(r),active_within_1e8=abs(r)<=1e-8) for n,r in zip(cut_names,residual)]
                    table('ROOT_CUT_ACTIVITY.csv',rows)
                    write('CUT_ACTIVITY.json',dict(available=True,source='First OPTIMAL native MIPNODE at node count0; original minimize-rho LP with T1; restricted bound never promoted to global LB',Runtime=t,Work=work,active_count=sum(r['active_within_1e8'] for r in rows),maximum_violation=float(np.max(residual)),added_static_cuts=cut_matrix.shape[0],callback_cuts_added=0))
            elif where==gp.GRB.Callback.MIPSOL:
                point=np.asarray(m.cbGetSolution(variables));index=len(traces)+1;path=saved/f'MIPSOL_{index:04d}.npz';np.savez_compressed(path,x=point)
                event=dict(event=index,UTC=stamp(),native_Runtime=t,Work=work,original_rho=float(point[rho]),native_objective=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),node_count=float(m.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)),point=path.relative_to(OUT).as_posix(),SHA256=sha(path));traces.append(event);writer.writerow(event);stream.flush()
                if times['first_feasible'] is None:times['first_feasible']=t
            if t-last_live>=30:
                last_live=t;write('LIVE_TIMELINE.json',dict(UTC=stamp(),Runtime=t,Work=work,times=times,MIPSOL_events=len(traces),callback_errors=errors));print('T1_PROGRESS',round(t,3),round(work,3),dict(times),len(traces),flush=True)
        except BaseException:
            errors.append(traceback.format_exc());m.terminate()
    calls=0;original_optimize=gp.Model.optimize
    def guard(m,*args,**kwargs):
        nonlocal calls
        assert calls==0 and m is model,'SECOND_OPTIMIZE_FORBIDDEN'
        assert read(OUT/'OBJECTIVE_IDENTITY.json')['PASS'],'OBJECTIVE_IDENTITY_FAILURE_STOP_OPTIMIZE_0'
        assert verify_objective(ROOT,dict(names=np.array(m.getAttr('VarName')),objective=np.array(m.getAttr('Obj')),constant=np.array(m.ObjCon)),int(m.ModelSense))['PASS'],'LAST_MOMENT_OBJECTIVE_FAILURE_STOP_OPTIMIZE_0'
        token=dict(objective_identity_SHA256=sha(OUT/'OBJECTIVE_IDENTITY.json'),PID=os.getpid(),UTC=stamp(),source_commit=git('rev-parse','HEAD'),exact_base=BASE,settings=SETTINGS,optimize_calls=1,full_domain=True,objective='ORIGINAL_P1_MINIMIZE_RHO',T1=T1)
        with (OUT/'OPTIMIZE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(token,f,ensure_ascii=False,indent=2)
        calls+=1;return original_optimize(m,*args,**kwargs)
    def forbidden(*args,**kwargs):raise AssertionError('SEPARATE_PRESOLVE_FORBIDDEN')
    gp.Model.optimize=guard;gp.Model.presolve=forbidden
    exception=None;begin=time.perf_counter();resources.phase='NATIVE_OPTIMIZE';print('P1_ORIGINAL_OBJECTIVE_T1_EXACT_ONE_FRESH_NATIVE_1800_START',flush=True)
    try:model.optimize(cb)
    except BaseException:exception=traceback.format_exc()
    finally:stream.close();resources.phase='REPLAY'
    report=dict(UTC=stamp(),optimize_calls=calls,Status=int(model.Status),native_status={2:'OPTIMAL',3:'INFEASIBLE',9:'TIME_LIMIT',11:'INTERRUPTED',12:'NUMERIC'}.get(int(model.Status),str(model.Status)),Runtime=float(model.Runtime),Work=float(model.Work),NodeCount=float(model.NodeCount),SolCount=int(model.SolCount),IterCount=float(model.IterCount),BarIterCount=int(model.BarIterCount),native_ObjVal=finite(model.ObjVal) if model.SolCount else None,native_ObjBound=finite(model.ObjBound),optimize_wall_seconds=time.perf_counter()-begin,build_seconds=build_seconds,callback_errors=errors,solver_exception=exception,MIPSOL_events=len(traces),first_feasible_time=times['first_feasible'])
    if model.SolCount:np.savez_compressed(OUT/'NATIVE_FINAL_POINT.npz',x=np.asarray(model.getAttr('X')))
    after,_=parameters(model);assert after==effective
    write('NATIVE_RECEIPT.json',report);write('ROOT_TIMELINE.json',dict(times=times,events=events,presolve_and_factor_records=presolve_records,barrier_progress=barrier,simplex_progress=simplex,first_branch_native_exact=None,first_branch_observed_evidence_is_upper_bound=True,root_completion_direct=times['root_relaxation_complete'] is not None,root_processing_completion_implied_by_nonroot=times['first_nonroot_node'] is not None,first_branch_time=None,missing_times_are_unobserved=True))
    table('BOUND_NODE_TRAJECTORY.csv',trajectory,['Runtime','Work','node_count','nodes_left','solution_count','native_ObjBst','native_ObjBnd','simplex_iterations','cut_count'])
    table('SIMPLEX_TRAJECTORY.csv',simplex,['Runtime','Work','phase','iterations','objective','primal_infeasibility','dual_infeasibility'])
    model.dispose()
    log=(OUT/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
    warnings=[l for l in log.splitlines() if re.search(r'warning|numerical trouble|numeric error|unstable|unscaled.*violation|quad precision',l,re.I)]
    audits=[];paths=[]
    if (OUT/'NATIVE_FINAL_POINT.npz').exists():paths.append(OUT/'NATIVE_FINAL_POINT.npz')
    paths.extend(OUT/e['point'] for e in traces);seen=set();reader=None;best=None
    for path in paths:
        with np.load(path) as z:point=z['x'].copy()
        key=hashlib.sha256(point.tobytes()).hexdigest()
        if key in seen:continue
        seen.add(key);raw=hc.replay(A,d,point,True);target=bool(point[rho]<=T1);aug=hc.replay(B,e,point,True);physical=None
        if raw['PASS'] and target and aug['PASS']:
            if reader is None:reader=hc.physical_reader()
            physical=reader.check(point,A,d)
        passing=bool(raw['PASS'] and target and aug['PASS'] and physical and physical['PASS'])
        audit=dict(point=path.relative_to(OUT).as_posix(),SHA256=sha(path),PASS=passing,rho=float(point[rho]),strict_T1_check=target,threshold_violation=float(point[rho]-T1),original_C3A=raw,augmented_feasibility=aug,full_physical=physical,no_repairs=True);audits.append(audit)
        if passing and (best is None or audit['rho']<best['rho']):best=audit
    write('CANDIDATE_REPLAYS.json',dict(audits=audits,all_MIPSOL_saved_before_validation=True,all_unique_saved_candidates_audited=True))
    inherited=read(PARENT/'NUMERICAL_AUTHORITY.json')['inherited_advisory_warnings']
    actual_warnings=[w for w in warnings if w not in inherited]
    assert inherited==['Warning: Model contains large matrix coefficient range']
    numerical=dict(PASS=not actual_warnings and not errors and exception is None,invalidating_warnings=actual_warnings,inherited_advisory_warnings=[w for w in warnings if w in inherited],inherited_warning_authority_SHA256=sha(PARENT/'NUMERICAL_AUTHORITY.json'),warnings=warnings,tolerances=SETTINGS,native_authority='Existing repository native floating status convention plus exact model transport, exact cut validity and frozen inverse/physical replay; not a rational branch-tree certificate.',Kappa=None,KappaExact=None,no_extra_solve=True)
    write('NUMERICAL_AUTHORITY.json',numerical)
    valid=bool(read(PARENT/'CUT_VALIDATION.json')['PASS'] and authority['PASS'] and calls==1 and not errors and exception is None and protected()==read(OUT/'BASE_IDENTITY.json')['protected_before'])
    new_lb=LB;new_ub=UB
    if not valid:classification='P1_ORIGINAL_T1_IMPLEMENTATION_INVALID'
    elif report['Status']==3 and numerical['PASS']:
        classification='P1_ORIGINAL_T1_INFEASIBLE_LB_IMPROVED';new_lb=T1
        write('INFEASIBILITY_AUTHORITY.json',dict(PASS=True,native_Status=3,full_model_transport=authority,original_objective_identity=native_identity,cut_validation_SHA256=sha(PARENT/'CUT_VALIDATION.json'),numerical_authority=numerical,all_original_rows_and_domain_present=True,threshold_exact=True,no_user_cut_callbacks=True,no_MIP_start=True,no_parameter_sweep=True,floating_native_authority_not_exact_tree_proof=True))
        write('LB_UPDATE.json',dict(old_LB=LB,new_LB=T1,valid_UB=UB,reason='Native INFEASIBLE on exact original-objective full model plus T1 and globally valid existing cuts'))
    elif best is not None:
        classification='P1_ORIGINAL_T1_REPLAY_PASS_UB_IMPROVED';new_ub=best['rho'];write('BEST_FULL_REPLAY.json',best)
        with np.load(OUT/best['point']) as z:np.savez_compressed(OUT/'BEST_VALID_POINT.npz',x=z['x'])
        write('UB_UPDATE.json',dict(old_UB=UB,new_UB=new_ub,valid_LB=LB,absolute_improvement=UB-new_ub,T1=T1,full_replay_PASS=True,point_SHA256=sha(OUT/'BEST_VALID_POINT.npz'),native_Status=report['Status'],valid_witness_accepted_even_at_TIME_LIMIT=True))
    elif not numerical['PASS']:classification='P1_ORIGINAL_T1_NUMERICAL_INCONCLUSIVE'
    elif report['Status'] in (9,11):classification='P1_ORIGINAL_T1_TIME_LIMIT_NO_VALID_WITNESS'
    else:classification='P1_ORIGINAL_T1_NO_VALID_PROOF_OR_WITNESS'
    resources.finish();peaks=max(r['RSS'] for r in resources.samples)
    report.update(classification=classification,global_LB_old=LB,global_UB_old=UB,global_LB_new=new_lb,global_UB_new=new_ub,global_gap=(new_ub-new_lb)/new_ub,T1=T1,feasible_witness=best is not None,full_replay_PASS=bool(best),root_relaxation_completed=times['root_relaxation_complete'] is not None,root_processing_finished_evidence=times['first_nonroot_node'] is not None,peak_RSS=peaks,numerical_warnings=warnings,full_domain_preserved=True,start_supplied=False,parameters_unchanged=True,post_root_search_seconds=(report['Runtime']-times['root_relaxation_complete']) if times['root_relaxation_complete'] is not None else None,first_MIPNODE=times['first_MIPNODE'],first_branch_exact=None,first_branch_evidence=times['first_branch_evidence'],node_trajectory_samples=len(trajectory),fresh_solve=True,checkpoint_resume=False,native_ObjBound_not_promoted_to_global_LB=True,selected_cuts=authority['selected_valid_cuts'])
    write('RESULT.json',report)
    write('VERIFICATION.json',dict(PASS=valid,exactly_one_optimize=calls==1,full_domain_original_types_and_bounds=True,all_original_rows_present=True,threshold_identity=True,original_P1_objective_identity_PASS=True,independent_cuts_PASS=True,numerical_authority_PASS=numerical['PASS'],native_result_accepted_for_global_bound=classification in ('P1_ORIGINAL_T1_INFEASIBLE_LB_IMPROVED','P1_ORIGINAL_T1_REPLAY_PASS_UB_IMPROVED'),feasible_original_full_replay_PASS=bool(best),stored_LP_not_rerun=True,old_hull_DW_BP_rerun=False,scientific_physics_changed=False,sweep=False,other_workers_untouched=True,historical_evidence_unchanged=protected()==read(OUT/'BASE_IDENTITY.json')['protected_before'],no_auto_next_solve=True))
    print('T1_COMPLETE',classification,report['native_status'],report['Runtime'],new_lb,new_ub,flush=True)
if __name__=='__main__':
    try:run()
    except BaseException:
        if not (OUT/'OPTIMIZE_ONCE.json').exists():write('STOPPED_BEFORE_OPTIMIZE.json',dict(optimize_calls=0,STOP=True,error=traceback.format_exc(),no_retry=True))
        raise
