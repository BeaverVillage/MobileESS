from time import perf_counter,monotonic
from dataclasses import asdict
from collections import Counter
import gc,sys
import gurobipy as gp
import psutil
from .common import *
from .audit import prepare
from .native import build
from .factor import reconstruct
from v42_compact.formulation import values
from .validation import check,snapshot

def freeze_check():
    for row in read(OUT/'SOURCE_MANIFEST.json')['sources']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('SOURCE_DRIFT:'+row['path'])
    for row in read(OUT/'LEGACY_PRESERVATION_AUDIT.json')['files']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('BASE_DRIFT:'+row['path'])
    if any(n=='v42_dw' or n.startswith('v42_dw.') for n in sys.modules):raise ValueError('DW_IMPORTED')

def optimize(m,variables,objectives,controls,bindings,data):
    from v42_a_stage_domain_v2.execution import require_action_authorized
    require_action_authorized(data[0],'A1')
    phases=[];telemetry=[];events={};first=[None];last=[-1.];next_checkpoint=[0];targets=[60,300,600,1800,3600]
    m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005;m.Params.TimeLimit=3600
    m.Params.OutputFlag=1;m.Params.LogFile=str(LOCAL/'gurobi.log')
    process=psutil.Process();started=perf_counter()
    def callback(model,where):
        elapsed=perf_counter()-started
        state={}
        if where==gp.GRB.Callback.PRESOLVE:
            events.update(presolve_rows_removed=int(model.cbGet(gp.GRB.Callback.PRE_ROWDEL)),presolve_columns_removed=int(model.cbGet(gp.GRB.Callback.PRE_COLDEL)),last_presolve_seconds=elapsed)
            state['phase']='PRESOLVE'
        elif where in (gp.GRB.Callback.MIP,gp.GRB.Callback.MIPSOL):
            prefix='MIP_' if where==gp.GRB.Callback.MIP else 'MIPSOL_'
            inc=model.cbGet(getattr(gp.GRB.Callback,prefix+'OBJBST')) if prefix=='MIP_' else model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)
            bound=model.cbGet(getattr(gp.GRB.Callback,prefix+'OBJBND'));nodes=model.cbGet(getattr(gp.GRB.Callback,prefix+'NODCNT'))
            inc=clean(inc);bound=clean(bound)
            if where==gp.GRB.Callback.MIPSOL and first[0] is None:first[0]=elapsed
            gap=abs(inc-bound)/abs(inc) if inc is not None and bound is not None and inc!=0 else (0. if inc==bound==0 else None)
            state.update(phase='MIP',incumbent=inc,best_bound=bound,gap=gap,nodes=nodes,root_status='BRANCH_TREE' if nodes>1 else 'ROOT')
        elif where==gp.GRB.Callback.MIPNODE:
            state.update(phase='MIPNODE',root_status=int(model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)))
        if not state:return
        hit=next_checkpoint[0]<len(targets) and elapsed>=targets[next_checkpoint[0]]
        if elapsed-last[0]>=5 or hit or where==gp.GRB.Callback.MIPSOL:
            row=dict(elapsed_seconds=elapsed,objective_level=objectives[len(phases)][0],first_incumbent_seconds=first[0],RSS_bytes=process.memory_info().rss,**events,**state)
            atomic(LOCAL/'solver_progress.json',row);last[0]=elapsed
            if hit:
                row['target_seconds']=targets[next_checkpoint[0]];telemetry.append(row);next_checkpoint[0]+=1
                atomic(LOCAL/'telemetry.json',telemetry)
    for name,expr in objectives:
        elapsed=perf_counter()-started if phases else 0
        remaining=3600-elapsed
        if remaining<=0:break
        m.setObjective(expr);m.Params.TimeLimit=3600 if not phases else remaining
        if not phases:
            # This receipt is written before the timer; parent observes the
            # immediately following monotonic boundary through the next file.
            atomic(LOCAL/'OPTIMIZER_READY.json',dict(optimizer_called=True,Threads=1,Seed=20260929,MIPGap=.005,TimeLimit=3600))
            started=perf_counter();atomic(LOCAL/'OPTIMIZER_STARTED.json',dict(started_monotonic=monotonic(),budget_seconds=3600))
        m.optimize(callback)
        phase=dict(level=name,status=m.Status,incumbent=m.ObjVal if m.SolCount else None,best_bound=clean(m.ObjBound),gap=m.MIPGap if m.SolCount else None,nodes=m.NodeCount,solve_seconds=m.Runtime)
        phases.append(clean(phase))
        atomic(LOCAL/'OPTIMIZATION.json',dict(passes=phases,optimization_wall_seconds=perf_counter()-started,first_incumbent_seconds=first[0],events=events,optimizer_called=True))
        if not m.SolCount or m.Status!=gp.GRB.OPTIMAL:break
        if len(phases)<len(objectives):m.addConstr(expr<=m.ObjVal+(1e-7 if name=='rho' else 1e-8))
    elapsed=perf_counter()-started
    atomic(LOCAL/'OPTIMIZATION_FINISHED.json',dict(finished_monotonic=monotonic(),optimization_wall_seconds=elapsed))
    telemetry.append(dict(elapsed_seconds=elapsed,target_seconds=3600,objective_level=phases[-1]['level'],phase='FINAL',**{k:phases[-1].get(k) for k in ('incumbent','best_bound','gap','nodes')},RSS_bytes=process.memory_info().rss,**events))
    atomic(LOCAL/'telemetry.json',telemetry)
    receipt=dict(passes=phases,optimization_wall_seconds=elapsed,first_incumbent_seconds=first[0],events=events,optimizer_called=True,lex_complete=len(phases)==len(objectives),
        globality='complete original PR99 physical MILP; P1 global bound on original full problem; subsequent levels use unchanged inherited lexicographic locks',settings=read(OUT/'PREREGISTRATION.json')['solver'])
    dump('MAY_A1_OPTIMIZATION.json',receipt)
    if not m.SolCount:
        dump('MAY_A1_PHYSICAL_VALIDATION.json',dict(PASS=False,status='NOT_RUN_NO_INCUMBENT',incumbent=None));return
    bundle,jobs,bounds,r,raw,graphs,original,prep=data;selected={}
    for uid,j in jobs.items():selected[uid]=asdict(reconstruct(j,bounds[uid],r,graphs[uid],values(variables[uid])))
    control_values=[[float(gp.LinExpr(x).getValue()) for x in row] for row in controls]
    cert=check(selected,data,control_values,snapshot(bindings,m),float(gp.LinExpr(objectives[0][1]).getValue()))
    linear_vio=0.
    # Independent evaluation of reserve/headroom target rows (including
    # anonymous allocation vars whose names are inherited/unnamed).
    for c in m.getConstrs():
        if c.ConstrName in ('nominal_and_compute_headroom','CC4_reserve_target','RT_reserve_target'):
            lhs=m.getRow(c).getValue();v=lhs-c.RHS if c.Sense=='<' else c.RHS-lhs if c.Sense=='>' else abs(lhs-c.RHS)
            linear_vio=max(linear_vio,v)
    known_vio=max(abs(x.X-(sum(jobs[u].gpu for u,o in selected.items() for site,a,b in o['segments'] if site==k and a<=t<b)+r.fixed_gpu.get((k,t),0))) for (k,t),x in bindings['known'].items())
    cert.update(independent_reserve_row_max_violation=linear_vio,independent_known_GPU_max_violation=known_vio,solver_max_violation=m.MaxVio)
    cert['PASS']=cert['PASS'] and max(linear_vio,known_vio,m.MaxVio)<=1e-5
    dump('MAY_A1_PHYSICAL_VALIDATION.json',cert);atomic(LOCAL/'SELECTED_PHYSICAL.json',selected)
    atomic(LOCAL/'CONTROLS.json',control_values)
    quality=all(p['gap'] is not None and p['gap']<=.005+1e-10 for p in phases)
    if cert['PASS'] and quality:atomic(LOCAL/'ACCEPTED_A1.json',dict(selected=selected,controls=control_values,certificate=cert,passes=phases,lex_complete=receipt['lex_complete']))

def main():
    freeze_check();context=Context();data=prepare();comparison=[]
    # F0's complete measured PR99 build receipt remains untouched.
    comparison.append(dict(formulation='F0',eligible=True,source='PR99 frozen full build receipt',binaries=9802075,continuous=2759286,constraints=4070611,nonzeros=119775457,model_build_seconds=408.759))
    for kind in ('F1','F2'):
        if kind=='F1' and (OUT/'F1_BUILD_CACHE_PROOF.json').exists():
            import inspect
            from .factor import tie_expression
            proof=read(OUT/'F1_BUILD_CACHE_PROOF.json')
            if proof['base']!=BASE or any(sha(ROOT/n)!=h for n,h in proof['sources'].items()) or digest(inspect.getsource(tie_expression))!=proof['tie_expression_sha256']:raise ValueError('F1_CACHE_SOURCE_DRIFT')
            comparison.append(dict(proof['stats'],eligible=True,cached_complete_build=True));continue
        print('full build',kind,flush=True);m,variables,objectives,controls,bindings=build(context,data,kind)
        stats=read(LOCAL/(kind+'_MODEL_COMPLETE.json'));comparison.append(dict(stats,eligible=True))
        if kind=='F1':m.dispose();del m,variables,objectives,controls,bindings;gc.collect()
    # Require final diverse-real receipt after building, before selection/solve.
    import time
    gate_names=('SYNTHETIC_EXHAUSTIVE_EQUIVALENCE.json','ADVERSARIAL_WAN_TESTS.json','WAN_TEMPLATE_EQUIVALENCE.json','REAL_SUBSET_EQUIVALENCE.json')
    expected_factor=sha(ROOT/'v42_exact/factor.py')
    while True:
        receipts=[read(OUT/filename) for filename in gate_names]
        if all(p.get('factor_source_sha256')==expected_factor and p.get('PASS') is True for p in receipts):break
        atomic(LOCAL/'EXACTNESS_GATE_PENDING.json',dict(optimizer_called=False,expected_factor_sha256=expected_factor,pending=[n for n,p in zip(gate_names,receipts) if p.get('factor_source_sha256')!=expected_factor or p.get('PASS') is not True]))
        time.sleep(1)
    real=read(OUT/'REAL_SUBSET_EQUIVALENCE.json')
    if not all(c['result']['native_grid'] and c['domain_scope'].startswith('complete') for c in real['cases']):raise ValueError('COMPLETE_REAL_DOMAINS_REQUIRED')
    comparison.append(dict(formulation='F3',eligible=False,reason='Aggregation not implemented; no interchangeable class under all objectives'))
    eligible=[x for x in comparison if x['eligible']]
    selected=min(eligible,key=lambda x:(x['binaries'],x['nonzeros'],x['model_build_seconds'],{'F1':0,'F2':1,'F3':2,'F0':3}[x['formulation']]))
    dump('FORMULATION_COMPARISON.json',dict(PASS=True,candidates=comparison,all_integer_physical_domains_identical=True))
    dump('FORMULATION_SELECTION.json',dict(selected=selected['formulation'],rule=read(OUT/'PREREGISTRATION.json')['selection'],scientific_objective_values_used=False,May_optimization_not_yet_started=True))
    if selected['formulation']!='F2':raise ValueError('UNEXPECTED_SELECTION_REQUIRES_SELECTED_MODEL_BUILD')
    dump('MAY_SELECTED_MODEL_STATS.json',selected);dump('MAY_SELECTED_MODEL_BUILD.json',dict(PASS=True,stats=selected,build_excluded_from_optimization_budget=True))
    freeze_check();m.update()
    if m.NumQConstrs or m.NumQNZs or m.NumSOS or m.NumGenConstrs or len(data[1])!=1499:raise ValueError('PREOPT_FULL_MILP_GATE')
    atomic(LOCAL/'PREOPT_VALIDATION.json',dict(PASS=True,all_jobs=1499,electrical_slots=96,pure_linear_MILP=True,source_freeze_PASS=True,DW_imported=False,exactness_gates_PASS=True))
    try:optimize(m,variables,objectives,controls,bindings,data)
    finally:m.dispose()

if __name__=='__main__':main()
