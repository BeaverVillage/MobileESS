"""LP and one-root diagnostics, followed by one frozen optimize-only production."""
import argparse,re,threading
from time import perf_counter
from collections import Counter
import gurobipy as gp
import numpy as np
import psutil
from v42_root.common import *
from v42_bootstrap.m1 import OptimizeOnlyBudget
from v42_bootstrap.grid import grid_report
from v42_bootstrap.attribution import supplemental_physical,analyze
from v42_two.contract import mess_groups,passes,P1_EPS,COMPONENT_EPS,relative_gap,integer_certificate
from v42_native.solver import assert_milp
from .build import inputs
from .grid import compressed_grid,map_bindings,evaluate

def parsed(log):
    ps=re.findall(r'Presolve time: ([\d.]+)s',log)
    sz=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
    roots=re.findall(r'Root relaxation: (objective ([\deE+.-]+)|time limit|infeasible|cutoff), (\d+) iterations, ([\d.]+) seconds',log)
    root=None
    if roots:
        r=roots[-1];root=dict(status=r[0],objective_rounded=float(r[1]) if r[1] else None,iterations=int(r[2]),seconds=float(r[3]),LP_complete=r[0].startswith('objective'))
    return dict(presolve_seconds=float(ps[-1]) if ps else None,presolved=dict(rows=int(sz[-1][0]),columns=int(sz[-1][1]),nonzeros=int(sz[-1][2])) if sz else None,root=root,warnings=[s.strip() for s in log.splitlines() if 'Warning' in s],cut_report=[s.strip() for s in log.splitlines() if re.match(r'\s+(Gomory|MIR|Flow cover|Zero half|RLT|Implied bound|Clique|Cover|StrongCG|Mod-K|Relax-and-lift|Mixing):',s)],MIP_start_accepted=bool(re.search(r'(Loaded user MIP start|User MIP start produced solution) with objective',log)))

def run(label,mode,threads=1,method=1):
    assert mode in ('lp','canary','production')
    if mode=='production':
        selection=read(OUT/'FORMULATION_SELECTION.json');assert selection['frozen'] and selection['candidate']==label and selection['threads']==threads and selection['method']==method
        assert not (LOCAL/'M1/STARTED.json').exists(),'ONE_PRODUCTION_ONLY'
    bundle,anchor,prior,sites,initial,routes,battery=inputs();values=prior['values'].copy();bindings=[];controls=[];cost=[]
    folder=LOCAL/('M1' if mode=='production' else f'{mode}_{label}_T{threads}');folder.mkdir(exist_ok=True)
    if (folder/'STARTED.json').exists():raise ValueError('NO_SOLVE_RETRY:'+str(folder))
    atomic(folder/'STARTED.json',dict(candidate=label,mode=mode,threads=threads,method=method,one_production=mode=='production'))
    budget=OptimizeOnlyBudget();receipt={};telemetry=[];state={};peak=[psutil.Process().memory_info().rss];stop=threading.Event();process=psutil.Process();active={'start':None,'spent':0.,'component':None}
    def sample():
        while not stop.wait(5):
            rss=process.memory_info().rss;peak[0]=max(peak[0],rss)
            if active['start'] is not None:
                elapsed=perf_counter()-active['start'];r=clean(dict(component=active['component'],optimize_seconds=active['spent']+elapsed,component_seconds=elapsed,RSS_bytes=rss,**state));telemetry.append(r);atomic(folder/'PROGRESS.json',r)
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    def builder(m,p,q):
        levels,ctrl=compressed_grid(m,bundle,anchor,p,q,label,bindings,cost);controls.extend(ctrl);return levels
    def optimizer(m,legacy,deadline,incumbent=None,**kwargs):
        m.update();map_bindings(bindings,values);stats=assert_milp(m)
        source=read(OUT/'census'/(label+'.json'));assert source['start']['PASS']
        assert (stats['binary'],stats['continuous'],stats['linear_constraints'],stats['nonzeros'])==tuple(source['stats'][k] for k in ('binary','continuous','linear_constraints','nonzeros'))
        stats.update(family_columns=dict(Counter(n.split('[')[0] for n in m.getAttr('VarName'))),candidate=label,AIDC_decision_variables=0)
        m.Params.Threads=threads;m.Params.Method=method;m.Params.Seed=20260929;m.Params.MIPGap=.005
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(folder/'GUROBI.log')
        chosen=passes(mess_groups(legacy)) if mode=='production' else [('MAX_LINE_LOADING','rho',legacy[0][1])]
        if mode=='lp':
            lower=m.getAttr('LB');upper=m.getAttr('UB');m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars);m.setAttr('LB',lower);m.setAttr('UB',upper);m.update()
            assert m.NumIntVars==0
        else:
            names=m.getAttr('VarName');m.setAttr('Start',[values[n] for n in names]);m.update()
            if mode=='canary':m.Params.NodeLimit=1
            if mode=='production':
                dump('M1_MIP_START_VALIDATION.json',dict(PASS=True,mapped_variables=len(names),source_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),cross_formulation=source['start'],auxiliary_mapping=True,bounds_fixed=False,domain_restricted=False))
                dump('M1_MODEL_STATS.json',stats)
        records=[];best=None
        for group,component,obj in chosen:
            remaining=deadline.remaining if mode=='production' else 600.
            if remaining<=0:break
            m.setObjective(obj);m.Params.TimeLimit=remaining;m.update();messages=[];first=[None];begin=perf_counter()
            active.update(start=begin,spent=deadline.spent,component=component);state.clear();state.update(phase='OPTIMIZE_START',solver_state_age_seconds=0.)
            def callback(model,where):
                now=perf_counter()-begin
                if where==gp.GRB.Callback.MESSAGE:
                    msg=model.cbGet(gp.GRB.Callback.MSG_STRING);messages.append(msg)
                    if msg.strip():state.update(last_solver_message=msg.strip(),solver_timestamp_seconds=now)
                    if 'Presolve' in msg:state['phase']='PRESOLVE'
                    if 'Root relaxation' in msg or 'Root simplex' in msg or 'Root barrier' in msg:state['phase']='ROOT'
                elif where==gp.GRB.Callback.MIPSOL:
                    if first[0] is None:first[0]=now
                    state.update(phase='INCUMBENT',incumbent=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),bound=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT),solver_timestamp_seconds=now)
                elif where==gp.GRB.Callback.MIP:
                    state.update(phase='MIP',incumbent=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBST)),bound=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT),solver_timestamp_seconds=now)
                elif where==gp.GRB.Callback.SIMPLEX:
                    state.update(phase='SIMPLEX',iterations=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF),solver_timestamp_seconds=now)
                elif where==gp.GRB.Callback.BARRIER:
                    state.update(phase='BARRIER',iterations=model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),solver_timestamp_seconds=now)
            m.optimize(callback);wall=perf_counter()-begin;deadline.spent+=wall;active['start']=None;log=''.join(messages)
            inc=float(m.ObjVal) if m.SolCount else None
            bound=float(m.ObjBound) if mode!='lp' else inc if m.Status==gp.GRB.OPTIMAL else None
            gap=relative_gap(inc,bound);quality=bool(inc is not None and gap is not None and gap<=.005+1e-12)
            if mode=='lp':quality=m.Status==gp.GRB.OPTIMAL
            record=clean(dict(group=group,component=component,status=m.Status,incumbent=inc,bound=bound,relative_gap=gap,quality_PASS=quality,solve_wall_seconds=wall,native_runtime_seconds=m.Runtime,iterations=m.IterCount,barrier_iterations=m.BarIterCount,nodes=m.NodeCount if mode!='lp' else None,first_incumbent_seconds=first[0],**parsed(log)))
            if mode!='lp':
                record['root_processing_wall_seconds']=max(0.,wall-(record['presolve_seconds'] or 0.))
                record['root_processing_complete']=m.Status in (gp.GRB.OPTIMAL,gp.GRB.NODE_LIMIT)
            records.append(record);atomic(folder/'PARTIAL_RESULT.json',dict(passes=records,total_optimize_seconds=deadline.spent))
            if mode=='lp':break
            if m.SolCount:
                vv=dict(zip(m.getAttr('VarName'),m.getAttr('X')));best=dict(values=vv,objectives=[evaluate(e,vv) for _,_,e in chosen],scientific_objective_count=2)
                ctrl=[[evaluate(x,vv) for x in row] for row in controls]
                fixed=max(abs(ctrl[t][i]-anchor['controls'][t][i]) for t in range(96) for i in anchor['fixed_AIDC_control_columns']);assert fixed==0.
                grid=grid_report(bundle,ctrl,vv['rho_max']);assert grid['PASS'],grid
                atomic(folder/'CONTROLS.json',ctrl);atomic(folder/'INCUMBENT.json',best)
                if mode=='production':dump('M1_ROBUST_VOLTAGE_REPORT.json',grid)
            if not quality or mode!='production':break
            if component=='movement_count':record['integer_exact_certificate']=integer_certificate(inc,bound)
            if len(records)<len(chosen):m.addConstr(obj<=inc+(P1_EPS if component=='rho' else COMPONENT_EPS),name='M1_lock_'+component)
        complete=mode=='production' and len(records)==3 and all(r['quality_PASS'] for r in records)
        receipt.update(candidate=label,mode=mode,passes=records,complete=complete,total_optimize_seconds=deadline.spent,settings=dict(Threads=threads,Method=method,Seed=20260929,MIPGap=.005,TimeLimit=1800 if mode=='production' else 600,NodeLimit=1 if mode=='canary' else None,GPU=False,optimize_only=True),peak_RSS_bytes=peak[0],A1_optimize_calls=0,scientific_groups=['MAX_LINE_LOADING','MIN_INTERVENTION'],reserve_optimized=False,CC4_optimized=False,tie_optimized=False)
        return best,receipt
    import v42_native.mess as native
    old=native.optimize;native.optimize=optimizer
    try:best,r=native.solve('M1',budget,sites,initial,routes,battery,96,builder,incumbent=prior if mode!='lp' else None)
    finally:native.optimize=old;stop.set();thread.join(1)
    receipt.update(r,peak_RSS_bytes=peak[0])
    if best:atomic(folder/'FINAL_PLAN.json',best)
    if mode=='production':
        physical=best['physical_audit'] if best else dict(PASS=False,violations=['NO_INCUMBENT'])
        if best:
            extra=supplemental_physical(best,sites,battery);physical.update(extra)
            initial_pass=all(abs(best['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
            physical.update(initial_SOC_PASS=initial_pass);physical['PASS']=physical['PASS'] and extra['charge_mode_and_connection_PASS'] and initial_pass
        grid=read(OUT/'M1_ROBUST_VOLTAGE_REPORT.json') if best else dict(PASS=False)
        receipt.update(physical_PASS=physical['PASS'],robust_grid_PASS=grid['PASS'],accepted=receipt['complete'] and physical['PASS'] and grid['PASS'])
        dump('M1_OPTIMIZATION.json',receipt);dump('M1_PHYSICAL_VALIDATION.json',physical)
        analyze(bundle,anchor,best,sites,routes,battery)
        blocker=read(OUT/'PR105_BLOCKER_M1_RESOLUTION.json');blocker['M1_ACCEPTED']=receipt['accepted'];dump('PR105_BLOCKER_FINAL_CHECK.json',blocker)
        stats=read(OUT/'M1_MODEL_STATS.json');stats.update(model_build_seconds=receipt['model_build_seconds'],peak_RSS_bytes=peak[0]);dump('M1_MODEL_STATS.json',stats)
        if telemetry:
            keys=sorted(set().union(*(r.keys() for r in telemetry)));table('M1_PROGRESS.csv',[{k:r.get(k) for k in keys} for r in telemetry])
    else:atomic(OUT/f'{mode}_{label}_T{threads}.json',receipt)
    atomic(folder/'FINISHED.json',receipt);frozen();print('FINISHED',mode,label,threads,receipt['passes'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('mode');p.add_argument('--threads',type=int,default=1);p.add_argument('--method',type=int,default=1);a=p.parse_args();run(a.candidate,a.mode,a.threads,a.method)
