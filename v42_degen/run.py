import gc
import hashlib
import re
import time
import numpy as np
import gurobipy as gp
from .common import ROOT,OUT,LOCAL,REF,BASE,POLICY,sha,read,write,finite
from .resources import Resources,gate
from .identity import inputs,model,signature
from .physics import adapter,full
from .start import zero
from .monitor import Monitor
from v42_integrated.matrix import arrays

def profile(monitor,log,component):
    text=log.read_text(encoding='utf8') if log.exists() else ''
    native=re.findall(r'User-callback calls (\d+), time in user-callback ([\d.]+) sec',text)
    return dict(component=component,handler_calls=monitor.calls,handler_body_wall_seconds=monitor.body_wall,handler_body_thread_CPU_seconds=monitor.body_CPU,Gurobi_reported_callback_calls=int(native[-1][0]) if native else None,Gurobi_reported_callback_seconds=float(native[-1][1]) if native else None,Python_callback_filesystem_writes=0,per_callback_process_scans=0,full_rows_checks_per_MIPSOL_only=len(monitor.solutions),major_phase_and_30s_memory_trace_only=True,all_artifacts_written_after_optimize=True,reference_Gurobi_callback_seconds=66.91,callback_scope_comparison='Native Gurobi reported callback time paired with native PR134 66.91 s; body CPU/wall shown separately. Profiling probes and one full-row audit per MIPSOL are included.')

def certified_points(monitor,m,A,d,solve,label):
    candidates=list(monitor.solutions)
    if m.SolCount:
        point=np.array(m.getAttr('X'))
        if not any(np.array_equal(c['point'],point) for c in candidates):candidates.append(dict(time=None,objective=m.ObjVal,point=point,terminal_only=True))
    records=[];best=None;best_value=None
    for i,c in enumerate(candidates):
        point=c['point'];checked=full(point,A,d,solve)
        value=float(d['objective']@point+float(d['constant']))
        cache=LOCAL/(label+'_INCUMBENT_'+str(i)+'.npz');np.savez_compressed(cache,names=d['names'],values=point)
        record=dict(index=i,callback_time=c['time'],reported_objective=c['objective'],P1_rho=value,PASS=checked['PASS'],point_sha256=sha(cache),validation=checked)
        records.append(record)
        if checked['PASS'] and (best_value is None or value<best_value):best=point;best_value=value
    write(label+'_ALL_INCUMBENT_AUDITS.json',dict(all_reported_points_audited=True,reported_MIPSOL_points=len(monitor.solutions),audited_points=len(records),passed=sum(r['PASS'] for r in records),rejected=sum(not r['PASS'] for r in records),records=records,invalid_points_never_used_as_scientific_UB=True,old_Start_or_solution_reads=0))
    return best,best_value,records

def p2(A,d,B,e,identity,solve,p1_point,p1_ub,resources,profiles):
    from v42_two.contract import COMPONENT_EPS
    gate('P2_before_model')
    m,pair=model(B,e,identity);variables={v.VarName:v for v in m.getVars()}
    m.addConstr(variables['rho_max']<=p1_ub,name='P2_exact_P1_UB_lock')
    objective=read(REF/'M1_OBJECTIVE_CONTRACT.json')
    coefficients=objective['movement_energy_coefficients']
    energy=gp.LinExpr(list(coefficients.values()),[variables[name] for name in coefficients])
    count=gp.quicksum(variables[name] for name in objective['movement_count_variables'])
    m.setAttr('Start',m.getVars(),p1_point.tolist());passes=[];accepted=False
    resources.model=m
    try:
        for name,expression in (('movement_energy',energy),('movement_count',count)):
            gate('P2_'+name)
            for key,value in POLICY.items():m.setParam(key,value)
            path=OUT/('P2_'+name+'.log');m.Params.LogFile=str(path);m.setObjective(expression);m.update()
            monitor=Monitor(A,d,m.getVars(),checkpoint=False);resources.sample('before_P2_'+name)
            m.optimize(monitor);resources.sample('after_P2_'+name)
            profiles.append(profile(monitor,path,name))
            _,_,audits=certified_points(monitor,m,A,d,solve,'P2_'+name)
            row=dict(component=name,status=m.Status,runtime=m.Runtime,objective=finite(m.ObjVal) if m.SolCount else None,LB=finite(m.ObjBound),gap=finite(m.MIPGap) if m.SolCount else None,callback_errors=monitor.errors,incumbent_audits=audits)
            if m.SolCount:
                point=np.array(m.getAttr('X'));checked=full(point,A,d,solve)
                rho=float(point[variables['rho_max'].index]);row.update(physical_audit=checked,P1_rho=rho,P1_no_degradation=rho<=p1_ub+1e-8)
            passes.append(row)
            if not m.SolCount or m.Status!=gp.GRB.OPTIMAL or monitor.errors or not checked['PASS'] or not row['P1_no_degradation'] or resources.violations:break
            m.addConstr(expression<=m.ObjVal+COMPONENT_EPS,name='P2_lexicographic_lock_'+name)
            if name=='movement_count':
                accepted=True;np.savez_compressed(LOCAL/'P2_FINAL_POINT.npz',names=d['names'],values=point)
        physical=passes[-1].get('physical_audit',{}).get('independent_physical_audit',{}) if passes else {}
        result=dict(accepted=accepted,optimization_calls=len(passes),passes=passes,movement_energy=physical.get('movement_energy'),movement_count=physical.get('movement_count'),P1_UB_lock=p1_ub,P1_lock_slack=0.,energy_lock_slack=COMPONENT_EPS,P1_certificate_preserved=True,settings=POLICY)
        write('M1_P2_RESULT.json',result);return result
    finally:resources.model=None;m.dispose()

def run():
    gate('run_before_model');LOCAL.mkdir(parents=True,exist_ok=True)
    marker=LOCAL/'P1_STARTED.json'
    if marker.exists():raise ValueError('P1_ONE_OPTIMIZE_NO_RETRY')
    resources=Resources();m=None;monitor=None;profiles=[];status='PREPARING';error=None
    p1_accepted=False;p2_result=None
    try:
        gp.setParam('Threads',1)
        from v42_integrated.import_guard import selected_imports
        from v42_integrated.contract import physical_authority
        with selected_imports(),physical_authority():
            A,d,B,e,identity,freeze=inputs();solve=adapter()
            m,pair=model(B,e,identity);resources.model=m;resources.sample('after_model_read_and_identity')
            start,start_result=zero(A,d,solve)
            previous_policy=read(REF/'M1_SINGLE_THREAD_SOLVE_RESULT.json')['settings']
            assert {key:value for key,value in POLICY.items() if key!='DegenMoves'}==previous_policy,'PR134_PARAMETER_DRIFT'
            defaults={key:m.getParamInfo(key)[2] for key in ('Presolve','Cuts','Heuristics','NumericFocus','PreSparsify')}
            assert defaults==dict(Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0,PreSparsify=-1)
            for key,value in POLICY.items():m.setParam(key,value)
            path=OUT/'M1_DEGENMOVES0_SOLVE.log';m.Params.LogFile=str(path)
            start_used=start_result['M1_ZERO_ACTION_START_VALID']
            if start_used:m.setAttr('Start',m.getVars(),start.tolist())
            m.update();pair.update(Start_used=start_used,solver_settings=POLICY,other_defaults=defaults,with_solver_Start_Gurobi_fingerprint=m.Fingerprint,Start_cold_fingerprints_separately_qualified=True)
            write('M1_MODEL_IDENTITY_PR134_PAIR.json',pair)
            write('EXECUTED_SOURCE_RECEIPT.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_degen').glob('*.py'))],solver_policy=POLICY,source_captured_before_optimize=True))
            gate('P1_before_optimize')
            marker.write_text(__import__('json').dumps(dict(P1_calls_max=1,base=BASE,settings=POLICY,Start_used=start_used,model_pair_sha256=sha(OUT/'M1_MODEL_IDENTITY_PR134_PAIR.json'),Start_validation_sha256=sha(OUT/'M1_ZERO_ACTION_START_VALIDATION.json'))),encoding='utf8')
            monitor=Monitor(A,d,m.getVars());resources.sample('before_P1_optimize')
            print('M1_SINGLE_P1_START',POLICY,'zero_Start',start_used,flush=True)
            monitor.start_watch(m);begin=time.perf_counter()
            try:m.optimize(monitor)
            finally:monitor.finish()
            wall=time.perf_counter()-begin;resources.sample('immediately_after_P1_optimize')
            profiles.append(profile(monitor,path,'P1'))
            raw_ub=finite(m.ObjVal) if m.SolCount else None;lb=finite(m.ObjBound)
            best,ub,all_audits=certified_points(monitor,m,A,d,solve,'M1_P1')
            gap=abs(ub-lb)/abs(ub) if ub is not None and lb is not None and ub else None
            status={gp.GRB.OPTIMAL:'OPTIMAL',gp.GRB.TIME_LIMIT:'TIME_LIMIT',gp.GRB.INTERRUPTED:'INTERRUPTED',gp.GRB.INFEASIBLE:'INFEASIBLE'}.get(m.Status,str(m.Status))
            current_matrix,current_data=arrays(m)
            pair['post_P1_scientific_payload_equal']=signature(current_matrix,current_data)==pair['reference']
            assert pair['post_P1_scientific_payload_equal'],'POST_SOLVE_SCIENTIFIC_DRIFT'
            write('M1_MODEL_IDENTITY_PR134_PAIR.json',pair)
            valid_lb=lb is not None and status in ('OPTIMAL','TIME_LIMIT','INTERRUPTED') and not monitor.errors
            p1_accepted=bool(ub is not None and valid_lb and gap is not None and gap<=.005 and not resources.violations)
            result=dict(status=status,status_code=m.Status,runtime=m.Runtime,optimize_wall_seconds=wall,solver_incumbents=m.SolCount,raw_solver_UB=raw_ub,UB=ub,LB=lb if valid_lb else None,gap=gap,valid_incumbent=ub is not None,valid_global_LB=valid_lb,node_count=m.NodeCount,Start_used=start_used,early_stop=monitor.early_stop,P1_optimization_calls=1,retries=0,parameter_sweep=False,settings=POLICY,other_defaults=defaults,callback_errors=monitor.errors,model_identity_pair=pair,all_reported_points_independently_audited=True,accepted_incumbents=sum(r['PASS'] for r in all_audits),rejected_incumbents=sum(not r['PASS'] for r in all_audits),M1_P1_ACCEPTED=p1_accepted)
            write('M1_DEGENMOVES0_ROOT_TIMELINE.json',monitor.json())
            write('M1_DEGENMOVES0_SOLVE_RESULT.json',result)
            chosen_audit=next((r['validation'] for r in all_audits if r['PASS'] and r['P1_rho']==ub),None)
            write('M1_DEGENMOVES0_PHYSICAL_AUDIT.json',chosen_audit or dict(PASS=False,status='NO_VALIDATED_INCUMBENT',solver_incumbents=m.SolCount,all_points_audit_file='M1_P1_ALL_INCUMBENT_AUDITS.json'))
            certificate=dict(schema='NEW_PR134_PAIRED_M1_V1',model_identity=identity,scientific_payload_sha256=pair['reference'],source_A1_freeze_sha256=identity['A1_freeze_sha256'],UB=ub,LB=lb if valid_lb else None,gap=gap,valid_incumbent=ub is not None,valid_global_LB=valid_lb,physical_PASS=bool(chosen_audit and chosen_audit['PASS']),model_identity_PASS=pair['PASS'] and pair['post_P1_scientific_payload_equal'],M1_P1_ACCEPTED=p1_accepted,M1_ACCEPTED=False,old_bounds_used=False,old_certificate='PR126_PR131_PR134_SUPERSEDED_NOT_USED',P2_order=['movement_energy','movement_count'])
            write('M1_DEGENMOVES0_P1_CERTIFICATE.json',certificate)
            if best is not None:np.savez_compressed(LOCAL/'M1_FINAL_POINT.npz',names=d['names'],values=best)
            resources.model=None;m.dispose();m=None;gc.collect()
            if p1_accepted:
                p2_result=p2(A,d,B,e,identity,solve,best,ub,resources,profiles)
                certificate['M1_ACCEPTED']=p2_result['accepted'];certificate['P2_execution']=p2_result
            else:
                p2_result=dict(status='NOT_RUN',reason='P1_NOT_ACCEPTED',optimization_calls=0,movement_energy=None,movement_count=None,accepted=False)
                write('M1_P2_RESULT.json',p2_result);certificate['P2_execution']=p2_result
            write('M1_DEGENMOVES0_CERTIFICATE.json',certificate)
            print('M1_DEGENMOVES0_TERMINAL',status,'UB',ub,'LB',lb,'gap',gap,'P1',p1_accepted,'P2',p2_result['accepted'],flush=True)
    except Exception as exception:
        error=dict(type=type(exception).__name__,message=str(exception),error_code=getattr(exception,'errno',None),memory_failure=isinstance(exception,MemoryError) or getattr(exception,'errno',None)==10001,infeasibility_proven=False)
        status='EXECUTION_STOP';write('EXECUTION_STOP.json',error);print('M1_DEGENMOVES0_STOP',error,flush=True)
    finally:
        resources.model=None
        if m is not None:m.dispose()
        if monitor is not None and not (OUT/'M1_DEGENMOVES0_ROOT_TIMELINE.json').exists():write('M1_DEGENMOVES0_ROOT_TIMELINE.json',monitor.json())
        write('M1_CALLBACK_OVERHEAD_AUDIT.json',dict(profiles=profiles,PR134_native_P1_callback_seconds=66.91,callback_filesystem_writes=0,callback_body_wall_CPU_separate=True,artifact_writes_after_terminal=True,error=error))
        summary=resources.close(status,monitor.events if monitor else [])
        write('EXECUTION_RECEIPT.json',dict(status=status,error=error,resource_summary=summary,P1_optimization_calls=int(marker.exists()),P1_ACCEPTED=p1_accepted,P2_optimization_calls=p2_result['optimization_calls'] if p2_result else 0,A1_optimization_calls=0,new_LP_optimization_calls=0,old_bounds_used=False))
    return error is None

if __name__=='__main__':
    raise SystemExit(0 if run() else 1)
