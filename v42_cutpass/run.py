"""One controlled P1; conditional inherited P2 only. Campaign calls stay zero."""
import gc,re,time,subprocess
import numpy as np
import gurobipy as gp
from .common import ROOT,OUT,REF,SCIENCE,LOCAL,SOURCE,BASE,POLICY,sha,read,write,finite
from .resources import Resources,gate
from .monitor import Monitor,root_pass,start_receipt
from v42_degen.identity import inputs,model,signature
from v42_integrated.matrix import arrays
from v42_postsolve.contract import audit_point,feasible,contract

def physical(point,d,solve):
    result=solve.physical(point,d);units=solve.grid_point(point,d)
    return dict(PHYSICAL_AUDIT_PASS=bool(result['PASS'] and units['PASS']),independent_physical_audit=result,original_unit_grid_audit=units,physical_limits_changed=False,A1_fixed_identity=True,repair_calls=0,Fresh_AC=False)

def profile(monitor,path,label):
    log=path.read_text(encoding='utf8');found=re.findall(r'User-callback calls (\d+), time in user-callback ([\d.]+) sec',log)
    return dict(component=label,handler_calls=monitor.calls,handler_body_wall_seconds=monitor.body_wall,handler_body_CPU_seconds=monitor.body_CPU,native_callback_calls=int(found[-1][0]) if found else None,native_callback_seconds=float(found[-1][1]) if found else None,PR135_native_callback_seconds=108.67,callback_filesystem_writes=0,callback_process_scans=0,callback_full_matrix_audits=0,all_numerical_physical_audits_after_optimize=True)

def audited_points(m,monitor,A,d,solve,label):
    # SolutionNumber is a terminal-only pool read selector, not an algorithm trial.
    pool=[];previous=m.Params.SolutionNumber
    try:
        for i in range(m.SolCount):
            m.Params.SolutionNumber=i;pool.append(np.asarray(m.getAttr('PoolNX'),dtype=float))
    finally:m.Params.SolutionNumber=previous
    terminal=np.asarray(m.getAttr('X'),dtype=float) if m.SolCount else None
    candidates=list(monitor.solutions)
    for i,p in enumerate(pool):
        if not any(np.array_equal(p,r['point']) for r in candidates):candidates.append(dict(time=None,objective=None,point=p,pool_index=i))
    records=[];best=None;ub=None;terminal_audit=None
    for i,row in enumerate(candidates):
        point=row['point'];before=point.tobytes();n=audit_point('M1',A,d,point);p=physical(point,d,solve)
        accepted=any(np.array_equal(point,x) for x in pool);passed=feasible(n,p,solver_accepted=accepted)
        assert point.tobytes()==before,'POINT_REPAIR_FORBIDDEN'
        file=OUT/'RAW_POINTS'/f'{label}_{i}.npz';file.parent.mkdir(exist_ok=True);np.savez_compressed(file,names=d['names'],values=point)
        record=dict(index=i,time=row['time'],reported_objective=row['objective'],P1_rho=n['objective'],solver_accepted=accepted,solver_acceptance_evidence='Exact numeric vector match to terminal native solution pool',point_sha256=sha(file),point_path=file.relative_to(ROOT).as_posix(),NUMERICAL_AUDIT_PASS=n['NUMERICAL_AUDIT_PASS'],PHYSICAL_AUDIT_PASS=p['PHYSICAL_AUDIT_PASS'],PASS=passed,numerical=n,physical=p,rounding_clipping_repair_calls=0)
        records.append(record)
        if terminal is not None and np.array_equal(point,terminal):terminal_audit=record
        if passed and (ub is None or n['objective']<ub):best=point.copy();ub=n['objective']
    write(label+'_ALL_INCUMBENT_AUDITS.json',dict(all_MIPSOL_points_audited=True,MIPSOL_count=len(monitor.solutions),native_pool_solution_count=m.SolCount,records=records,accepted=sum(r['PASS'] for r in records),old_points_read=0,terminal_only_pool_selector=True))
    return best,ub,records,terminal,terminal_audit

def p2(A,d,B,e,identity,solve,point,ub,resources,profiles):
    from v42_two.contract import COMPONENT_EPS
    gate('P2_before_model');m,_=model(B,e,identity);variables={v.VarName:v for v in m.getVars()}
    m.addConstr(variables['rho_max']<=ub,name='CutPasses_P2_exact_P1_lock')
    objective=read(SCIENCE/'M1_OBJECTIVE_CONTRACT.json');coeff=objective['movement_energy_coefficients']
    energy=gp.LinExpr(list(coeff.values()),[variables[n] for n in coeff]);count=gp.quicksum(variables[n] for n in objective['movement_count_variables'])
    m.setAttr('Start',m.getVars(),point.tolist());passes=[];accepted=False;resources.model=m
    try:
        for label,expr in (('movement_energy',energy),('movement_count',count)):
            gate('P2_'+label)
            for key,value in POLICY.items():m.setParam(key,value)
            path=OUT/f'P2_{label}.log';m.Params.LogFile=str(path);m.setObjective(expr);monitor=Monitor(m.getVars(),checkpoint=False)
            resources.sample('P2_'+label+'_before_optimize');m.optimize(monitor);resources.sample('P2_'+label+'_after_optimize');profiles.append(profile(monitor,path,label))
            _,_,records,terminal,audited=audited_points(m,monitor,A,d,solve,'P2_'+label)
            row=dict(component=label,status=m.Status,objective=finite(m.ObjVal) if m.SolCount else None,LB=finite(m.ObjBound),gap=finite(m.MIPGap) if m.SolCount else None,runtime=m.Runtime,callback_errors=monitor.errors,terminal_audit=audited,P1_rho=audited['P1_rho'] if audited else None)
            row['P1_no_degradation']=bool(audited and audited['P1_rho']<=ub+1e-8);passes.append(row)
            if m.Status!=gp.GRB.OPTIMAL or not audited or not audited['PASS'] or not row['P1_no_degradation'] or monitor.errors or resources.violations:break
            m.addConstr(expr<=m.ObjVal+COMPONENT_EPS,name='CutPasses_P2_lock_'+label)
            if label=='movement_count':accepted=True
        phys=passes[-1]['terminal_audit']['physical']['independent_physical_audit'] if passes and passes[-1]['terminal_audit'] else {}
        result=dict(status='ACCEPTED' if accepted else 'NOT_ACCEPTED',accepted=accepted,optimization_calls=len(passes),passes=passes,movement_energy=phys.get('movement_energy'),movement_count=phys.get('movement_count'),P1_UB_lock=ub,P1_lock_slack=0.,energy_lock_slack=COMPONENT_EPS,settings=POLICY)
        write('M1_P2_RESULT.json',result);return result
    finally:resources.model=None;m.dispose()

def run():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==BASE,'EXACT_PR135_REQUIRED'
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True);marker=LOCAL/'P1_STARTED.json'
    if marker.exists():raise RuntimeError('ONE_P1_NO_RETRY')
    gate('before_prepare')
    files=subprocess.check_output(['git','ls-files'],cwd=ROOT).decode().splitlines()
    write('PR135_BYTE_PRESERVATION.json',dict(base=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in files]))
    inherited=read(REF/'SHA256_MANIFEST.json')
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in inherited['files']+inherited['sources']),'PR135_MANIFEST_DRIFT'
    previous=read(REF/'M1_DEGENMOVES0_SOLVE_RESULT.json')['settings'];assert {k:v for k,v in POLICY.items() if k!='CutPasses'}==previous
    write('EXECUTION_PREREGISTRATION.json',dict(base=BASE,policy=POLICY,P1_calls=1,restarts=0,retries=0,Start='Exact PR135 reclassified zero-action candidate without repair; native acceptance observed separately.',checkpoint='Terminate at 600s unless first nonroot or branch <=600s, regardless of Start/incumbent.',all_audits_after_terminal=True,P2='Only if new same-solve P1 gap<=0.005 and both audits PASS; inherited energy then count locks.',campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,physical_limits_changed=False,postsolve_contract=contract()))
    gp.setParam('Threads',1);resources=Resources();m=None;monitor=None;profiles=[];error=None;status='PREPARE';p2_result=None;P1_calls=0
    try:
        from v42_integrated.import_guard import selected_imports
        from v42_integrated.contract import physical_authority
        with selected_imports(),physical_authority():
            A,d,B,e,identity,freeze=inputs();m,pair=model(B,e,identity);resources.model=m
            reference=read(REF/'M1_MODEL_IDENTITY_PR134_PAIR.json');assert pair['reference']==reference['reference'] and pair['cold_Gurobi_fingerprint']==reference['cold_Gurobi_fingerprint']
            import v42_integrated.solve as solve
            solve.OUT=OUT;solve.LOCAL=SOURCE;solve.write=write
            for name,file in [('INTEGRATED_A1_FREEZE.json',SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'),('M1_MODEL_IDENTITY.json',SCIENCE/'M1_MODEL_IDENTITY.json')]: (OUT/name).write_bytes(file.read_bytes())
            validation=read(REF/'ZERO_ACTION_START_TOLERANCE_REAUDIT.json');file=REF/'RAW_POINTS/ZERO_ACTION_CANDIDATE.npz';assert sha(file)==validation['candidate_sha256']
            with np.load(file) as z:assert np.array_equal(z['names'],d['names']);point=z['values'].copy()
            n=audit_point('M1',A,d,point);p=physical(point,d,solve)
            assert n['NUMERICAL_AUDIT_PASS'] and p['PHYSICAL_AUDIT_PASS'] and validation['primary_semantics']['PASS'],'START_PREFLIGHT_FAILED'
            assert n['objective']==0.6715884801665905
            write('M1_START_PREFLIGHT.json',dict(NUMERICAL_AUDIT_PASS=True,PHYSICAL_AUDIT_PASS=True,numerical=n,physical=p,candidate_sha256=sha(file),primary_semantics=validation['primary_semantics'],no_repair=True))
            defaults={k:m.getParamInfo(k)[2] for k in ('Presolve','Cuts','Heuristics','NumericFocus','PreSparsify')};assert defaults==dict(Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0,PreSparsify=-1)
            for key,value in POLICY.items():m.setParam(key,value)
            log=OUT/'M1_CUTPASSES1_SOLVE.log';m.Params.LogFile=str(log);m.setAttr('Start',m.getVars(),point.tolist());m.update()
            pair.update(PR135_exact_head=BASE,PR135_payload_identity_PASS=True,PR135_reference_fingerprints=reference['reference'],START_ATTEMPTED=True,Start_candidate_sha256=sha(file),with_Start_Gurobi_fingerprint=m.Fingerprint,solver_settings=POLICY,other_defaults=defaults)
            write('M1_PR135_MODEL_IDENTITY.json',pair)
            write('M1_ZERO_ACTION_START_SOLVER_BINDING.json',dict(START_ATTEMPTED=True,START_SOLVER_ACCEPTED=None,native_acceptance_pending=True,all_columns_bound=m.NumVars,candidate_sha256=sha(file),objective=n['objective'],repair_calls=0))
            write('EXECUTED_SOURCE_RECEIPT.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_cutpass').glob('*.py'))],captured_before_optimize=True))
            gate('P1_before_optimize')
            with marker.open('x',encoding='utf8') as f:__import__('json').dump(dict(base=BASE,policy=POLICY,identity_sha256=sha(OUT/'M1_PR135_MODEL_IDENTITY.json'),Start_sha256=sha(file),max_P1_calls=1),f)
            monitor=Monitor(m.getVars());resources.sample('before_P1');monitor.start_watch(m);begin=time.perf_counter();P1_calls=1
            print('CUTPASS_P1_START',POLICY,'Start attempted',flush=True)
            try:m.optimize(monitor)
            finally:monitor.finish()
            wall=time.perf_counter()-begin;resources.sample('after_P1');profiles.append(profile(monitor,log,'P1'))
            best,ub,records,terminal,terminal_audit=audited_points(m,monitor,A,d,solve,'M1_P1')
            lb=finite(m.ObjBound);status={gp.GRB.OPTIMAL:'OPTIMAL',gp.GRB.TIME_LIMIT:'TIME_LIMIT',gp.GRB.INTERRUPTED:'INTERRUPTED',gp.GRB.INFEASIBLE:'INFEASIBLE'}.get(m.Status,str(m.Status))
            valid_lb=lb is not None and status in ('OPTIMAL','TIME_LIMIT','INTERRUPTED') and not monitor.errors
            lb=lb if valid_lb else None;gap=None if ub is None or lb is None else (ub-lb)/abs(ub)
            assert gap is None or gap>=0,'LB_ABOVE_UB'
            C,f=arrays(m);post_same=signature(C,f)==pair['reference'];assert post_same,'SCIENTIFIC_MODEL_CHANGED'
            write('POST_P1_MODEL_IDENTITY_AUDIT.json',dict(PASS=post_same,pre_optimize_identity_preserved=True,scientific_payload_same=True))
            binding=start_receipt(monitor.start_messages);binding.update(all_columns_bound=m.NumVars,candidate_sha256=sha(file),candidate_reference_objective=n['objective']);write('M1_ZERO_ACTION_START_SOLVER_BINDING.json',binding)
            p1=bool(ub is not None and valid_lb and gap is not None and gap<=.005 and not resources.violations and not monitor.errors)
            result=dict(status=status,status_code=m.Status,runtime=m.Runtime,optimize_wall_seconds=wall,raw_solver_UB=finite(m.ObjVal) if m.SolCount else None,UB=ub,LB=lb,gap=gap,valid_global_LB=valid_lb,solver_incumbents=m.SolCount,node_count=m.NodeCount,START_ATTEMPTED=True,START_SOLVER_ACCEPTED=binding['START_SOLVER_ACCEPTED'],root_cut_path_fix='ACCEPTED' if root_pass(monitor.times) else 'FAILED',M1_P1_ACCEPTED=p1,early_stop=monitor.early_stop,P1_optimization_calls=1,retries=0,settings=POLICY,defaults=defaults,callback_errors=monitor.errors,old_bounds_used=False)
            write('M1_CUTPASSES1_SOLVE_RESULT.json',result);write('M1_CUTPASSES1_ROOT_TIMELINE.json',monitor.json())
            selected=next((r for r in records if r['PASS'] and r['P1_rho']==ub),None)
            write('M1_CUTPASSES1_PHYSICAL_AUDIT.json',selected or dict(PASS=False,reason='NO_VALIDATED_SOLVER_INCUMBENT'))
            certificate=dict(model_identity=pair['reference'],cold_Gurobi_fingerprint=pair['cold_Gurobi_fingerprint'],A1_freeze_sha256=pair['A1_freeze_sha256'],NormalAmps_sha256=pair['NormalAmps_authority_sha256'],source_data_sha256=pair['source_data_sha256'],solve_log_sha256=sha(log),solve_result_sha256=sha(OUT/'M1_CUTPASSES1_SOLVE_RESULT.json'),UB=ub,LB=lb,gap=gap,M1_P1_ACCEPTED=p1,M1_ACCEPTED=False,valid_global_LB=valid_lb,chosen_incumbent=selected,old_bounds_used=False,postsolve_numerical_tolerance=1e-6)
            resources.model=None;m.dispose();m=None;gc.collect()
            if p1:p2_result=p2(A,d,B,e,identity,solve,best,ub,resources,profiles)
            else:p2_result=dict(status='NOT_RUN',reason='P1_NOT_ACCEPTED',accepted=False,optimization_calls=0,movement_energy=None,movement_count=None);write('M1_P2_RESULT.json',p2_result)
            certificate.update(M1_ACCEPTED=p2_result['accepted'],P2=p2_result);write('M1_CUTPASSES1_CERTIFICATE.json',certificate)
            print('CUTPASS_TERMINAL',result,'P2',p2_result['status'],flush=True)
    except Exception as e:error=dict(type=type(e).__name__,message=str(e));status='EXECUTION_STOP';write('EXECUTION_STOP.json',error);print('CUTPASS_STOP',error,flush=True)
    finally:
        resources.model=None
        if m is not None:m.dispose()
        if monitor is not None and not (OUT/'M1_CUTPASSES1_ROOT_TIMELINE.json').exists():write('M1_CUTPASSES1_ROOT_TIMELINE.json',monitor.json())
        write('M1_CUTPASSES1_CALLBACK_AUDIT.json',dict(profiles=profiles,error=error,callback_file_IO=0,callback_full_matrix_audits=0))
        resource=resources.close(status,monitor.events if monitor else [])
        write('EXECUTION_RECEIPT.json',dict(status=status,error=error,P1_optimization_calls=P1_calls,P2_optimization_calls=p2_result['optimization_calls'] if p2_result else 0,resource_summary=resource,A1_calls=0,LP_calls=0,campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0))
    return error is None
if __name__=='__main__':raise SystemExit(0 if run() else 1)
