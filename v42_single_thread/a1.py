"""One full-authority A1 attempt with inherited explicit P1/P2 locks."""
import json
import time
from .common import ROOT,OUT,LOCAL,NORMALAMPS,configure,sha,write
from .resources import Timeline,exclusive_gate

def run():
    configure()
    choice=OUT/'A1_LEXICOGRAPHIC_EXECUTION_AUTHORITY.json'
    if not choice.exists():raise ValueError('A1_OPTIMIZE_CALL_INTERPRETATION_PENDING')
    authority=json.loads(choice.read_text(encoding='utf8'))
    if authority['mode']!='PR133_EXPLICIT_SEQUENTIAL_LOCKS':raise ValueError('UNSUPPORTED_A1_EXECUTION_MODE')
    import gurobipy as gp
    import numpy as np
    import pandas as pd
    from v42_integrated.contract import physical_authority,all_transformer_rows,evaluate,grid_audit
    from v42_root.data import prepare
    from v42_root.native import build
    from v42_root.common import Context
    from v42_root.certify import certificate
    from v42_two.contract import aidc_groups,passes,P1_EPS,COMPONENT_EPS
    from v42_bootstrap.grid import coefficients
    from v42_native.voltage import Stage,authority_sha
    import v42_boundary.model as boundary
    gp.setParam('Threads',1)
    exclusive_gate('A1_before_build')
    marker=LOCAL/'A1_ATTEMPT_STARTED.json'
    if marker.exists():raise ValueError('A1_SINGLE_ATTEMPT_NO_RETRY')
    marker.write_text(json.dumps(dict(attempts=1,Method=1,Threads=1,TimeLimit=3600)),encoding='utf8')
    telemetry=Timeline('A1');m=None;rows=[];physical=None;error=None;spent=0.;groups=[];first_incumbent=None
    result=dict(accepted=False,A1_ACCEPTED=False,source_regenerated=False,old_A1_freeze_reused=False,optimization_calls=0)
    try:
        with physical_authority() as thermal:
            assert thermal['transformer_current_authority_sha256']==NORMALAMPS
            print('A1_FULL_SOURCE_REGENERATION',flush=True)
            started=time.perf_counter();data=prepare();bundle=data[0]
            assert len(data[1])==1499 and bundle['day']=='2025-05-01'
            issue=pd.Timestamp(bundle['issue_time'])
            assert all(r['known_at_issue'] and pd.Timestamp(r['submit_time'])<=issue and pd.Timestamp(r['issue_time'])==issue for r in bundle['known_population'])
            assert bundle['RUNTIME_PROVIDER_READY'] is True
            from v42_capacity.common import resolve
            from v42_boundary.common import OLD
            sources=[]
            def walk(value):
                if isinstance(value,dict):
                    if 'path' in value and 'sha256' in value:
                        p=resolve(value);sources.append(dict(path=str(p),sha256=sha(p)))
                    for x in value.values():walk(x)
                elif isinstance(value,list):
                    for x in value:walk(x)
            walk(bundle)
            write('SOURCE_DATA_HASH_AUDIT.json',dict(PASS=True,bundle_path=str(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),bundle_sha256=sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),sources=sources,source_data_cache_sha256=sha(LOCAL/'DATA.pkl'),known_jobs=1499,horizon=96,future_actual_reads=0,Runtime_refit=0,CC4_refit=0,source_available_before_issue=True,source_regenerated=True))
            original=boundary.add_grid;boundary.add_grid=all_transformer_rows(original)
            try:m,units,legacy,controls,bindings=build(Context(),data,'F2-CRA')
            finally:boundary.add_grid=original
            m.update();result['source_regenerated']=True
            census=dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs,build_seconds=time.perf_counter()-started,voltage_band=[.95,1.05],margin_pu=0,NormalAmps_authority=NORMALAMPS,formulation='PR133 F2-CRA unchanged',horizon=96,jobs=1499,domain_shortened=False,candidate_pruning_added=False)
            write('A1_SINGLE_THREAD_MATRIX_CENSUS.json',census)
            reference=json.loads((ROOT/'docs/v42_integrated_normalamps_zero_margin_m1/A1_MODEL_CENSUS.json').read_text(encoding='utf8'))
            assert all(census[k]==reference[k] for k in ('rows','columns','binaries','nnz')),'A1_MODEL_CENSUS_DRIFT'
            telemetry.sample('after_model_build')
            groups=passes(aidc_groups(legacy,units,data));m.Params.Method=1;m.Params.Threads=1;m.Params.MIPGap=.005;m.Params.Seed=20260929
            defaults={k:m.getParamInfo(k)[2] for k in ('Cuts','Presolve','Heuristics','NumericFocus')}
            assert defaults==dict(Cuts=-1,Presolve=-1,Heuristics=.05,NumericFocus=0)
            m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/'A1_SINGLE_THREAD_SOLVE.log')
            from v42_integrated.monitor import Monitor
            callback_errors=[];events=[];last=[-30.];component=['rho'];seen=set()
            def callback(model,where):
                nonlocal first_incumbent
                if where==gp.GRB.Callback.POLLING:return
                try:
                    t=float(model.cbGet(gp.GRB.Callback.RUNTIME))
                    if where==gp.GRB.Callback.MESSAGE:
                        line=model.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                        label=None
                        if line.startswith('Presolve time:'):label='after_presolve'
                        elif line.startswith('Root relaxation:'):label='root_relaxation_completion'
                        elif line.startswith('Barrier solved model'):label='barrier_completion'
                        elif line.startswith('Crossover time:'):label='crossover_completion'
                        if label and (component[0],label) not in seen:
                            seen.add((component[0],label));events.append(dict(component=component[0],phase=label,solver_seconds=t,literal=line))
                            telemetry.sample(component[0]+':'+label,t)
                    elif where==gp.GRB.Callback.MIPSOL and first_incumbent is None:
                        first_incumbent=dict(component=component[0],solver_seconds=t)
                        telemetry.sample(component[0]+':first_incumbent',t)
                    if t-last[0]>=30:
                        last[0]=t;state=dict(component=component[0],solver_seconds=t,completed_passes=len(rows))
                        if where==gp.GRB.Callback.MIP:state.update(nodes=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT)))
                        write('A1_LIVE.json',state);print('A1_SINGLE_THREAD_PROGRESS',state,flush=True)
                except Exception as exception:
                    callback_errors.append(repr(exception));model.terminate()
            print('A1_SINGLE_THREAD_MODEL_READY',census,flush=True)
            telemetry.active_model=m
            for group,name,expr in groups:
                if spent>=3600:break
                exclusive_gate('A1_before_'+name)
                component[0]=name;last[0]=-30.
                m.setObjective(expr);m.Params.TimeLimit=3600-spent
                telemetry.sample(name+':before_optimize');result['optimization_calls']+=1
                try:m.optimize(callback)
                finally:telemetry.sample(name+':immediately_after_optimize')
                spent+=m.Runtime
                row=dict(group=group,component=name,status=m.Status,objective=m.ObjVal if m.SolCount else None,bound=m.ObjBound,runtime=m.Runtime,gap=m.MIPGap if m.SolCount else None)
                rows.append(row)
                result.update(passes=rows,total_runtime=spent,first_incumbent=first_incumbent,callback_errors=callback_errors)
                write('A1_SINGLE_THREAD_SOLVE_RESULT.json',result)
                if not m.SolCount or callback_errors or telemetry.policy_violations:break
                point=np.array(m.getAttr('X'))
                physical,selected,values,_=certificate(m,units,data,controls,bindings,legacy,point,m.MaxVio)
                _,coeff=coefficients(bundle)
                physical['all_phase_grid']=grid_audit(coeff,values,evaluate(legacy[0][1],point))
                physical['PASS']=physical['PASS'] and physical['all_phase_grid']['PASS']
                write('A1_SINGLE_THREAD_PHYSICAL_AUDIT.json',physical)
                if not physical['PASS'] or m.Status!=gp.GRB.OPTIMAL:break
                m.addConstr(expr<=m.ObjVal+(P1_EPS if name=='rho' else COMPONENT_EPS),name='single_thread_A1_lock_'+name)
            accepted=len(rows)==len(groups) and all(r['status']==gp.GRB.OPTIMAL for r in rows) and physical is not None and physical['PASS'] and not callback_errors and not telemetry.policy_violations
            result.update(accepted=bool(accepted),A1_ACCEPTED=bool(accepted),passes=rows,total_runtime=spent,status='ACCEPTED' if accepted else 'INFEASIBLE' if m.Status==gp.GRB.INFEASIBLE else 'A1_NOT_ACCEPTED',terminal_solver_status=m.Status,objective=rows[0]['objective'] if rows else None,physical=physical,first_incumbent=first_incumbent,callback_errors=callback_errors,settings=dict(Method=1,Threads=1,MIPGap=.005,Seed=20260929,total_TimeLimit=3600,defaults=defaults),single_attempt=True,parameter_sweep=False,events=events)
            if accepted:
                anchor=dict(control_names=list(coeff[0].control_names),controls=values,voltage_authority_sha256=authority_sha(Stage.A1),transformer_current_authority_sha256=NORMALAMPS,source_stage='A1',fixed_AIDC_control_columns=[i for i,n in enumerate(coeff[0].control_names) if n.startswith('aidc_load_kw')])
                freeze=dict(PASS=True,accepted=True,physical=physical,anchor=anchor,selected_jobs=selected,source_data_sha256=sha(LOCAL/'DATA.pkl'),objective=rows[0]['objective'],freeze_before_M1=True,result=result)
                np.savez_compressed(LOCAL/'A1_FINAL_POINT.npz',values=point,names=np.array(m.getAttr('VarName')))
            else:freeze=dict(PASS=False,accepted=False,status='NOT_FROZEN',reason=result['status'],M1_construction_authorized=False)
    except Exception as exception:
        memory=isinstance(exception,MemoryError) or getattr(exception,'errno',None)==10001
        error=dict(type=type(exception).__name__,error_code=getattr(exception,'errno',None),message=str(exception),memory_failure=memory,infeasibility_proven=False)
        result.update(status='NATIVE_OUT_OF_MEMORY' if memory else 'EXECUTION_STOP',accepted=False,A1_ACCEPTED=False,error=error,passes=rows,total_runtime=spent,objective=None,valid_global_bound=None)
        write('A1_SINGLE_THREAD_ROOT_CAUSE.json',error)
        freeze=dict(PASS=False,accepted=False,status='NOT_FROZEN',reason=result['status'],M1_construction_authorized=False,error=error)
        print('A1_SINGLE_THREAD_STOP',error,flush=True)
    finally:
        telemetry.active_model=None
        summary=telemetry.close(result.get('status','EXECUTION_STOP'))
        result['resources']=summary
        write('A1_SINGLE_THREAD_SOLVE_RESULT.json',result)
        write('INTEGRATED_A1_FREEZE_SINGLE_THREAD.json',freeze)
        write('INTEGRATED_A1_FREEZE.json',freeze)
        if m is not None:m.dispose()
    print('A1_SINGLE_THREAD_FINISHED',result['status'],result['A1_ACCEPTED'],flush=True)
    return result['A1_ACCEPTED']

if __name__=='__main__':run()
