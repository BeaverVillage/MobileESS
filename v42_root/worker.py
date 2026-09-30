"""One frozen six-level A1 protocol; cumulative optimize-only budget."""
from time import perf_counter,monotonic
import re,numpy as np,gurobipy as gp,psutil
from .common import *
from .data import prepare
from .native import build
from .start import validate_source
from .certify import certificate,dense_value

def source_freeze():
    frozen();manifest=read(OUT/'SOURCE_MANIFEST.json')
    for row in manifest['sources']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('SUCCESSOR_SOURCE_DRIFT:'+row['path'])
    if sha(OUT/'PREREGISTRATION.json')!=manifest['preregistration_sha256']:raise ValueError('PREREGISTRATION_DRIFT')
    for filename in ('SCIENTIFIC_AGGREGATION_EQUIVALENCE.json','NATIVE_REAL_EQUIVALENCE.json'):
        d=read(OUT/filename)
        if d['PASS'] is not True:raise ValueError('EXACTNESS_FAILED')
        if any(sha(ROOT/n)!=h for n,h in d['source_sha256'].items()):raise ValueError('EXACTNESS_SOURCE_DRIFT')

def optimize(m,units,levels,controls,bindings,data,start_receipt):
    if (LOCAL/'PRIMARY_STARTED.json').exists():raise ValueError('NO_PRIMARY_RETRY')
    phases=[];telemetry=[];spent=0.;first=[None];primary_cert=None;targets=[60,300,600,1200,1800,3600];next_target=[0];latest={};begin_all=perf_counter();peak=[psutil.Process().memory_info().rss]
    m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005;m.Params.OutputFlag=1;m.Params.LogFile=str(LOCAL/'A1_GUROBI.log')
    atomic(LOCAL/'PRIMARY_STARTED.json',dict(started_monotonic=monotonic(),budget=3600,exactly_one_primary=True))
    for name,expr in levels:
        remaining=3600-spent
        if remaining<=0:break
        m.setObjective(expr);m.Params.TimeLimit=remaining;m.update();last=[-1.];begin=perf_counter()
        atomic(LOCAL/'ACTIVE_OPTIMIZATION.json',dict(active=True,started_monotonic=monotonic(),remaining_budget_seconds=remaining,spent_before_call_seconds=spent,level=name))
        def cb(model,where):
            elapsed=spent+perf_counter()-begin;state={};peak[0]=max(peak[0],psutil.Process().memory_info().rss)
            if where==gp.GRB.Callback.PRESOLVE:state=dict(phase='PRESOLVE',presolve_rows_removed=model.cbGet(gp.GRB.Callback.PRE_ROWDEL),presolve_columns_removed=model.cbGet(gp.GRB.Callback.PRE_COLDEL))
            elif where==gp.GRB.Callback.SIMPLEX:state=dict(phase='SIMPLEX',simplex_objective=model.cbGet(gp.GRB.Callback.SPX_OBJVAL),simplex_iterations=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),simplex_primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),simplex_dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF))
            elif where in (gp.GRB.Callback.MIP,gp.GRB.Callback.MIPSOL):
                prefix='MIP_' if where==gp.GRB.Callback.MIP else 'MIPSOL_'
                inc=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBST if prefix=='MIP_' else gp.GRB.Callback.MIPSOL_OBJ));bound=clean(model.cbGet(getattr(gp.GRB.Callback,prefix+'OBJBND')));nodes=model.cbGet(getattr(gp.GRB.Callback,prefix+'NODCNT'))
                gap=abs(inc-bound)/abs(inc) if inc is not None and bound is not None and inc!=0 else 0 if inc==bound==0 else None
                if where==gp.GRB.Callback.MIPSOL and first[0] is None:first[0]=elapsed
                state=dict(phase='MIP',incumbent=inc,best_bound=bound,gap=gap,nodes=nodes,root_status='BRANCH_TREE' if nodes>1 else 'ROOT')
            if not state:return
            hit=next_target[0]<len(targets) and elapsed>=targets[next_target[0]]
            if elapsed-last[0]>=5 or hit or where==gp.GRB.Callback.MIPSOL:
                row=clean(dict(elapsed_optimize_seconds=elapsed,objective_level=name,first_incumbent_seconds=first[0],RSS_bytes=psutil.Process().memory_info().rss,**state));atomic(LOCAL/'A1_PROGRESS.json',row);latest.clear();latest.update(row);last[0]=elapsed
                if hit:
                    row['target_seconds']=targets[next_target[0]];next_target[0]+=1;telemetry.append(row);atomic(LOCAL/'A1_TELEMETRY.json',telemetry)
        m.optimize(cb);call_wall=perf_counter()-begin;spent+=call_wall
        atomic(LOCAL/'ACTIVE_OPTIMIZATION.json',dict(active=False,total_optimize_seconds=spent,level=name))
        phase=clean(dict(level=name,status=m.Status,incumbent=m.ObjVal if m.SolCount else None,best_bound=m.ObjBound,gap=m.MIPGap if m.SolCount else None,nodes=m.NodeCount,native_Runtime_seconds=m.Runtime,optimize_call_wall_seconds=call_wall));phases.append(phase)
        atomic(LOCAL/'A1_PARTIAL_RESULT.json',dict(passes=phases,optimization_wall_seconds=spent,first_incumbent_seconds=first[0]))
        if not m.SolCount:break
        # Validation is explicitly outside the cumulative optimize-only clock.
        if name=='rho' or m.Status!=gp.GRB.OPTIMAL or len(phases)==len(levels):
            dense=np.asarray(m.getAttr('X'),dtype=float);cert,selected,ctrl,snap=certificate(m,units,data,controls,bindings,levels,dense,m.MaxVio)
            dump('MAY_A1_PHYSICAL_VALIDATION.json',cert);atomic(LOCAL/'A1_SELECTED_PHYSICAL.json',selected);atomic(LOCAL/'A1_CONTROLS.json',ctrl)
            if name=='rho':
                primary_cert=cert;dump('P1_PHYSICAL_VALIDATION.json',cert)
                if cert['PASS'] and phase['gap'] is not None and phase['gap']<=.005:atomic(LOCAL/'P1_ACCEPTED_A1.json',dict(physical=selected,controls=ctrl,P1=phase,validation=cert))
            if not cert['PASS']:break
        if m.Status!=gp.GRB.OPTIMAL:break
        if len(phases)<len(levels):m.addConstr(expr<=m.ObjVal+(1e-7 if name=='rho' else 1e-8))
    atomic(LOCAL/'PRIMARY_FINISHED.json',dict(total_optimize_seconds=spent,total_protocol_wall_seconds=perf_counter()-begin_all))
    if not (OUT/'MAY_A1_PHYSICAL_VALIDATION.json').exists():dump('MAY_A1_PHYSICAL_VALIDATION.json',dict(PASS=False,status='NOT_RUN_NO_INCUMBENT',incumbent=None))
    log=(LOCAL/'A1_GUROBI.log').read_text(encoding='utf8');root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log);presolve=re.search(r'Presolve time: ([\d.]+)s\nPresolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
    accepted=bool(primary_cert and primary_cert['PASS'] and phases[0]['gap'] is not None and phases[0]['gap']<=.005)
    start_receipt['accepted_by_Gurobi']=True if re.search(r'Loaded user MIP start|User MIP start produced solution',log) else False if start_receipt['available'] else None;dump('MIP_START_RECEIPT.json',start_receipt)
    receipt=dict(passes=phases,optimization_wall_seconds=spent,total_protocol_wall_seconds=perf_counter()-begin_all,first_incumbent_seconds=first[0],peak_observed_RSS_bytes=peak[0],lex_complete=len(phases)==len(levels) and phases[-1]['status']==gp.GRB.OPTIMAL,P1_A1_ACCEPTED=accepted,settings=read(OUT/'PREREGISTRATION.json')['solver'],MIP_start=start_receipt,root_relaxation=dict(objective_rounded=float(root[1]),iterations=int(root[2]),seconds=float(root[3])) if root else None,presolve=dict(seconds=float(presolve[1]),rows=int(presolve[2]),columns=int(presolve[3]),nonzeros=int(presolve[4])) if presolve else None,globality='P1 bounds cover the complete original PR102 physical integer feasible set; later bounds apply only under inherited scientific lexicographic locks; no restricted columns',build_and_validation_excluded=True,exactly_one_primary=True,latest_callback=latest)
    receipt['cuts_log_sections']=[s.strip() for s in re.findall(r'Cutting planes:\s*\n(.*?)(?:\n\s*\n|\nExplored)',log,re.S)]
    if m.SolCount:
        receipt['final_incumbent_P1_rho']=dense_value(levels[0][1],np.asarray(m.getAttr('X')))
        receipt['original_P1_global_gap']=(abs(receipt['final_incumbent_P1_rho']-phases[0]['best_bound'])/abs(receipt['final_incumbent_P1_rho'])) if phases[0]['best_bound'] is not None and receipt['final_incumbent_P1_rho'] else (0 if receipt['final_incumbent_P1_rho']==phases[0]['best_bound']==0 else None)
    else:receipt.update(final_incumbent_P1_rho=None,original_P1_global_gap=None)
    dump('MAY_A1_OPTIMIZATION.json',receipt)
    telemetry.append(dict(target_seconds=3600,elapsed_optimize_seconds=spent,phase='FINAL',objective_level=phases[-1]['level'],**{k:phases[-1].get(k) for k in ('incumbent','best_bound','gap','nodes')}))
    keys=sorted(set().union(*(row.keys() for row in telemetry)));table('MAY_A1_PROGRESS.csv',[{key:row.get(key) for key in keys} for row in telemetry])

def main():
    source_freeze();data=prepare();selection=read(OUT/'FORMULATION_SELECTION.json');kind=selection['selected'];context=Context()
    m,units,levels,controls,bindings=build(context,data,kind);m.update()
    stats=read(context.folder/'F2_MODEL_COMPLETE.json') if kind=='F2' else read(OUT/(kind+'_MODEL_STATS.json'))
    stats.update(columns=m.NumVars)
    dump('MAY_SELECTED_MODEL_BUILD.json',dict(PASS=True,selected=kind,stats=stats,full_jobs=1499,electrical_slots=96,build_excluded_from_A1_budget=True))
    dump('MAY_SELECTED_ROOT_LP.json',read(OUT/(kind+'_ROOT_LP.json')))
    if len(data[1])!=1499 or m.NumQConstrs or m.NumQNZs or m.NumSOS or m.NumGenConstrs:raise ValueError('FULL_NATIVE_MILP_PREOPT_GATE')
    start_receipt=validate_source(m,units,data,controls,bindings,levels);source_freeze()
    atomic(LOCAL/'PREOPT_VALIDATION.json',dict(PASS=True,full_jobs=1499,electrical_slots=96,selection_frozen=True,start_choice_frozen=True,source_freeze=True,complete_physical_domains=True,no_DW=True))
    try:optimize(m,units,levels,controls,bindings,data,start_receipt)
    finally:m.dispose()
if __name__=='__main__':main()
