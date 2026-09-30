"""Each lock requires an optimal RMP and exact pricing of every movable job."""
from time import perf_counter
import gurobipy as gp
from .pricing import PricingSweep
from .common import RC_TOL,PHASE1_TOL,require

def generate(master,check=lambda:None,remaining=lambda:1e8,receipt=lambda value:None,include_tie=True,solve_audit=lambda:None,progress=lambda value:None):
    start=perf_counter();iterations=[];profiles=[];solves=[];levels=[];iteration=0;converged=False;infeasible=False
    stages=[('PHASE_I',master.artificial_expr)]+master.levels
    if not include_tie:stages=stages[:-1]
    all_jobs=sorted(uid for uid,g in master.factory.graphs.items() if not g.fixed)
    for level,expr in stages:
        if level!='PHASE_I':require(master.phase1_zero,'SCIENTIFIC_OBJECTIVE_WITH_ARTIFICIAL')
        while True:
            check();iteration+=1;m=master.m;m.setObjective(expr)
            m.Params.TimeLimit=max(.001,remaining()-3.)
            row=dict(iteration=iteration,objective_level=level,master_LP_objective=None,master_solve_seconds=None,
                pricing_total_seconds=0.,pricing_max_job_seconds=0.,jobs_priced=0,jobs_negative_RC=0,
                minimum_reduced_cost=None,mean_negative_RC=None,columns_attempted=0,columns_added=0,duplicate_rediscoveries=0,
                artificial_objective=None,artificial_count=len(master.artificial),complete_pricing=False,status='MASTER_RUNNING')
            row.update(master.size());iterations.append(row)
            receipt(dict(iterations=iterations,profiles=profiles,solves=solves,levels=levels,phase1_zero=master.phase1_zero,converged=False,infeasible=False))
            t=perf_counter();last_progress=[-10.]
            def callback(model,where):
                elapsed=perf_counter()-t
                if elapsed-last_progress[0]<5.:return
                diagnostic=dict(iteration=iteration,objective_level=level,master_elapsed_seconds=elapsed,
                    cumulative_wall_seconds=perf_counter()-start,status='MASTER_RUNNING')
                if where==gp.GRB.Callback.PRESOLVE:
                    diagnostic.update(presolve_rows_removed=int(model.cbGet(gp.GRB.Callback.PRE_ROWDEL)),presolve_columns_removed=int(model.cbGet(gp.GRB.Callback.PRE_COLDEL)))
                elif where==gp.GRB.Callback.SIMPLEX:
                    diagnostic.update(simplex_iterations=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF))
                elif where==gp.GRB.Callback.BARRIER:
                    diagnostic.update(barrier_iterations=model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),primal_infeasibility=model.cbGet(gp.GRB.Callback.BARRIER_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.BARRIER_DUALINF))
                else:return
                row['master_last_observation_seconds']=elapsed;row['cumulative_wall_seconds']=perf_counter()-start
                progress(diagnostic);last_progress[0]=elapsed
            m.optimize(callback);elapsed=perf_counter()-t
            row.update(master_solve_seconds=elapsed,master_status=m.Status,master_LP_objective=m.ObjVal if m.SolCount else None,
                artificial_objective=master.artificial_expr.getValue() if m.SolCount else None,status='PRICING_RUNNING')
            solves.append(dict(iteration=iteration,objective_level=level,seconds=elapsed,status=m.Status,**master.size()))
            receipt(dict(iterations=iterations,profiles=profiles,solves=solves,levels=levels,phase1_zero=master.phase1_zero,converged=False,infeasible=False))
            if m.Status!=gp.GRB.OPTIMAL:row['status']='NONOPTIMAL_MASTER';break
            solve_audit()
            dual=master.duals();negative=[];minimum=None;price_start=perf_counter();pending=[];proposed_profiles=[]
            sweep=PricingSweep(master.factory,dual)
            for uid in all_jobs:
                check();c,rc,p=sweep.price(uid,check)
                p.update(iteration=iteration,objective_level=level,generated=0);profiles.append(p)
                row['jobs_priced']+=1;row['pricing_max_job_seconds']=max(row['pricing_max_job_seconds'],p['seconds'])
                minimum=rc if minimum is None else min(minimum,rc)
                row['minimum_reduced_cost']=minimum
                if rc < -RC_TOL:
                    negative.append(rc);row['columns_attempted']+=1
                    if c.signature in master.columns:row['duplicate_rediscoveries']+=1
                    else:pending.append(c);p['proposed']=1;proposed_profiles.append(p)
                row.update(jobs_negative_RC=len(negative),mean_negative_RC=sum(negative)/len(negative) if negative else None)
                row.update(pricing_total_seconds=perf_counter()-price_start,cumulative_wall_seconds=perf_counter()-start)
                if row['jobs_priced']%25==0:
                    receipt(dict(iterations=iterations,profiles=profiles,solves=solves,levels=levels,phase1_zero=master.phase1_zero,converged=False,infeasible=False))
            # Add only after the complete immutable-dual pricing sweep.
            for c in pending:require(master.add(c),'DUPLICATE_INSERTION')
            for p in proposed_profiles:p['generated']=1
            row.update(complete_pricing=True,jobs_negative_RC=len(negative),mean_negative_RC=sum(negative)/len(negative) if negative else None,
                columns_added=len(pending),status='COMPLETE',**master.size())
            if not negative:
                levels.append(dict(level=level,value=m.ObjVal,minimum_reduced_cost=minimum,all_jobs_priced=len(all_jobs),converged=True))
                if level=='PHASE_I':
                    if row['artificial_objective']>PHASE1_TOL:infeasible=True
                    else:master.disable_artificial()
                else:master.lock(level,expr,m.ObjVal)
            elif not pending:
                # Numerical duplicate is never a convergence certificate.
                row['status']='NEGATIVE_RC_DUPLICATE_STALL'
            receipt(dict(iterations=iterations,profiles=profiles,solves=solves,levels=levels,phase1_zero=master.phase1_zero,converged=False,infeasible=infeasible))
            if not negative or not pending:break
        if infeasible or not levels or levels[-1]['level']!=level:break
    converged=not infeasible and len(levels)==len(stages)
    result=dict(iterations=iterations,profiles=profiles,solves=solves,levels=levels,phase1_zero=master.phase1_zero,converged=converged,infeasible=infeasible)
    receipt(result);return result
