"""AIDC-only MIN_RHO using the unchanged full A1 Planning electrical rows."""
from collections import defaultdict,Counter
from copy import deepcopy
from pathlib import Path
import math,time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.v40a.feedback import authorized_options,pcc_from_jobs
from dayahead.v40a.grid import add_grid,controls_from_trajectory,evaluate_grid
from dayahead.v40a.invariants import occupancy_deviation,terminal_audit,digest,tail,BEGIN,H
from dayahead.paper_analysis.storage import write_json,reference


def solve(reference_jobs,seed_jobs,reference_pcc,context,output,*,tolerance=1e-6,work_limit=60):
    """One common service requirement; RW is an ordinary feasible decision.

    Cohorts only aggregate interchangeable variables with exactly identical
    feasible choices and reference costs. UID materialization remains stable.
    MESS controls are numeric zero constants, with no mobility input or variable.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    refs={str(r['job_uid']):deepcopy(r) for r in reference_jobs}
    seeds={str(r['job_uid']):deepcopy(r) for r in seed_jobs}
    assert len(refs)==len(reference_jobs)==len(seeds)==len(seed_jobs) and refs.keys()==seeds.keys()
    for uid in refs:
        for field in ('requested_GPU','state_at_issue','qos','safe_duration_slots','safe_duration_seconds','duration_authority'):
            if refs[uid][field]!=seeds[uid][field]:raise ValueError('CASE_DEPENDENT_DA_SERVICE:'+uid+':'+field)
        if tail(refs[uid])!=tail(seeds[uid]):raise ValueError('CASE_DEPENDENT_TERMINAL_OBLIGATION:'+uid)
    sites=tuple(context.capacity.aidc_ids);T=len(context.coefficients)
    if np.asarray(reference_pcc).shape!=(T,len(sites)):raise ValueError('REFERENCE_PCC_AXIS')
    # Production is 96 slots. Reduced toy tests use the same interval origin.
    def occupancy(rows):
        result=np.zeros((T,len(sites)),dtype=int)
        for r in rows:
            lo,hi=max(BEGIN,int(r['start_slot'])),min(BEGIN+T,int(r['end_slot']))
            if lo<hi:
                if r['AIDC_site'] not in sites:raise ValueError('UNASSIGNED_ACTIVE_REFERENCE')
                result[lo-BEGIN:hi-BEGIN,sites.index(r['AIDC_site'])]+=int(r['requested_GPU'])
        return result
    ref_gpu=occupancy(refs.values())
    for k,s in enumerate(sites):assert np.all(ref_gpu[:,k]<=context.capacity.site_capacity[s])
    def evaluate(p):
        controls=np.zeros((T,len(context.coefficients[0].control_names)))
        controls[:,:len(sites)]=p
        return evaluate_grid(context.coefficients,controls,context.nodes)
    before=evaluate(reference_pcc)
    if before['status']!='PASS':raise ValueError('REFERENCE_PLANNING_NOT_FEASIBLE')
    groups=defaultdict(list);options_per_uid={};ungrouped=0
    for uid in sorted(seeds):
        row=seeds[uid];ref=refs[uid]
        assert row['requested_GPU']==ref['requested_GPU'] and row['state_at_issue']==ref['state_at_issue']
        opts=tuple(authorized_options(ref,context.capacity));options_per_uid[uid]=opts;ungrouped+=len(opts)
        if (ref['AIDC_site'],ref['start_slot']) not in opts:raise ValueError('B0_REFERENCE_IN_COMMON_DOMAIN_FAIL:'+uid)
        if (row['AIDC_site'],row['start_slot']) not in opts:raise ValueError('SEED_OUTSIDE_AUTHORIZED_DOMAIN:'+uid)
        costs=tuple(occupancy_deviation(ref,{**row,'AIDC_site':s,'start_slot':start,'end_slot':start+row['safe_duration_slots']}) for s,start in opts)
        key=(int(row['requested_GPU']),int(row['safe_duration_slots']),opts,costs)
        groups[key].append(uid)
    keys=sorted(groups,key=lambda k:tuple(groups[k]));model=gp.Model('V40F_B1_A0_MIN_RHO');model.Params.OutputFlag=0
    model.Params.Threads=4;model.Params.Seed=20260905;model.Params.MIPGap=0;model.Params.MIPGapAbs=0
    model.Params.FeasibilityTol=1e-8;model.Params.IntFeasTol=1e-9;model.Params.OptimalityTol=1e-8
    model.Params.WorkLimit=work_limit;model.Params.SoftMemLimit=8;model.Params.NodefileStart=1
    model.Params.LogFile=str((output/'MIN_RHO_SOLVER.log').resolve())
    stages=[];events=[]
    def callback(m,where):
        if where==GRB.Callback.MIPSOL:
            row={'stage':len(stages),'runtime':m.cbGet(GRB.Callback.RUNTIME),'objective':m.cbGet(GRB.Callback.MIPSOL_OBJ),'bound':m.cbGet(GRB.Callback.MIPSOL_OBJBND)}
            events.append(row);print('AIDC incumbent '+str(row),flush=True)
    try:
        variables={};load=defaultdict(gp.LinExpr);deviation=gp.LinExpr();tie=gp.LinExpr()
        for i,key in enumerate(keys):
            gpu,duration,opts,costs=key;n=len(groups[key]);vs=[]
            for k,(site,start) in enumerate(opts):
                v=model.addVar(vtype=GRB.INTEGER,lb=0,ub=n,name=f'cohort[{i},{k}]');variables[i,k]=v;vs.append(v)
                if site in sites:
                    for t in range(max(BEGIN,start),min(BEGIN+T,start+duration)):load[t-BEGIN,site]+=gpu*v
                elif max(BEGIN,start)<min(BEGIN+T,start+duration):raise ValueError('UNASSIGNED_ACTIVE_OPTION')
                deviation+=costs[k]*v;tie+=(i+1)*(k+1)*v
            model.addConstr(gp.quicksum(vs)==n,name=f'common_service_cohort[{i}]')
        controls=[[0.0]*len(c.control_names) for c in context.coefficients]
        for t in range(T):
            for k,site in enumerate(sites):
                cap=int(context.capacity.site_capacity[site]);values=context.tables[site][t]
                g=model.addVar(vtype=GRB.INTEGER,lb=0,ub=cap,name=f'GPU[{t},{site}]')
                p=model.addVar(lb=float(values.min()),ub=float(values.max()),name=f'C1_PCC[{t},{site}]')
                model.addConstr(g==load[t,site],name=f'GPU_binding[{t},{site}]')
                model.addGenConstrPWL(g,p,list(range(cap+1)),values.tolist())
                offset=float(reference_pcc[t,k])-float(values[int(ref_gpu[t,k])])
                if offset!=0:raise ValueError('REFERENCE_MUST_USE_SAME_COMMON_C1_POWER_MAPPING')
                controls[t][k]=p
        rho,grid_rows=add_grid(model,context.coefficients,controls,min(1.0,before['rho_max']+tolerance))
        model.setObjective(rho,GRB.MINIMIZE);model.update()
        assert model.NumObj==1 and model.ModelSense==GRB.MINIMIZE
        objective_variables=[(v.VarName,float(v.Obj)) for v in model.getVars() if v.Obj!=0]
        assert objective_variables==[('rho_max',1.0)]
        # Exact B0 decisions with the same T_DA are the feasible MIP start.
        for i,key in enumerate(keys):
            counts=Counter((refs[u]['AIDC_site'],refs[u]['start_slot']) for u in groups[key])
            for k,opt in enumerate(key[2]):variables[i,k].Start=counts[opt]
        model.write(str((output/'PRIMARY_MIN_RHO_MODEL.mps').resolve()))
        write_json(output/'PRIMARY_OBJECTIVE_STRUCTURE.json',{'B1_PRIMARY_OBJECTIVE':'MIN_RHO_MAX','ZERO_FEASIBILITY_FINAL_OBJECTIVE':'NO',
            'objective_variables':objective_variables,'NumObj':model.NumObj,'sense':'MINIMIZE','grid_rows':grid_rows,
            'MESS_variable_count':0,'MESS_control_nonzero_count':0,'ungrouped_option_count':ungrouped,
            'cohort_count':len(keys),'cohort_option_count':len(variables),'reference_complete_candidate_included':True,
            'COMMON_DURATION_IDENTITY':'PASS','different_duration_candidate_union':False,
            'cohort_equivalence':'Same GPU, duration, complete option set and per-option RW deviation costs; integral counts materialized by UID, no relaxation of gang constraints'})
        def record(label):
            entry={'stage':label,'status':int(model.Status),'solutions':int(model.SolCount),'work':float(model.Work),'runtime_seconds':float(model.Runtime),
                'incumbent':float(model.ObjVal) if model.SolCount else None,'bound':float(model.ObjBound) if model.SolCount else None,
                'OPTIMAL':model.Status==GRB.OPTIMAL}
            stages.append(entry);write_json(output/'SOLVER_STAGES.json',{'stages':stages,'incumbent_events':events});print('AIDC stage '+str(entry),flush=True)
        def chosen():return {key:[int(round(variables[i,k].X)) for k in range(len(key[2]))] for i,key in enumerate(keys)}
        print(f'MIN_RHO model: {model.NumVars} vars / {model.NumConstrs} rows / {len(keys)} cohorts',flush=True)
        model.optimize(callback);record('PRIMARY_MIN_RHO')
        if not model.SolCount:raise RuntimeError('PRIMARY_NO_INCUMBENT')
        model.write(str((output/'PRIMARY_INCUMBENT.sol').resolve()))
        # Additional proof effort only. The model, MIP gap settings, primary
        # objective and scientific tolerance remain unchanged. Persist every
        # bound and incumbent; never call a WorkLimit incumbent an optimum.
        for proof_work in (180,300):
            if float(rho.X)-float(model.ObjBound)<=tolerance:break
            model.Params.WorkLimit=proof_work
            model.optimize(callback);record('PRIMARY_MIN_RHO_PROOF_WORK_'+str(proof_work))
            if model.SolCount:model.write(str((output/'PRIMARY_INCUMBENT.sol').resolve()))
        primary=float(rho.X);bound=float(model.ObjBound);selection=chosen()
        if primary-bound>tolerance:
            write_json(output/'PRIMARY_NOT_CERTIFIED.json',{'status':'STOP','incumbent':primary,'bound':bound,'gap':primary-bound,
                'required_gap':tolerance,'no_secondary_or_physical_campaign_started':True})
            raise RuntimeError('PRIMARY_OPTIMAL_WITHIN_TOLERANCE_NOT_CERTIFIED')
        model.Params.WorkLimit=300
        model.addConstr(rho<=min(before['rho_max']+tolerance,primary+tolerance,bound+tolerance),name='PRIMARY_OPTIMUM_TOLERANCE_LOCK')
        model.setObjective(deviation,GRB.MINIMIZE);model.optimize(callback);record('SECONDARY_RW_OCCUPANCY_DEVIATION')
        if not model.SolCount or model.Status!=GRB.OPTIMAL:raise RuntimeError('REFERENCE_DEVIATION_OPTIMUM_NOT_CERTIFIED')
        secondary=int(round(deviation.getValue()));selection=chosen()
        model.addConstr(deviation<=secondary,name='REFERENCE_DEVIATION_EXACT_INTEGER_LOCK')
        model.setObjective(tie,GRB.MINIMIZE);model.optimize(callback);record('TERTIARY_STABLE_TIE')
        if not model.SolCount or model.Status!=GRB.OPTIMAL:raise RuntimeError('STABLE_TIE_OPTIMUM_NOT_CERTIFIED')
        counts=chosen();selected=[]
        for key in keys:
            places=[]
            for opt,n in zip(key[2],counts[key]):places.extend([opt]*n)
            assert len(places)==len(groups[key])
            for uid,(site,start) in zip(sorted(groups[key]),places):
                row=deepcopy(refs[uid]);row.update(AIDC_site=site,start_slot=start,end_slot=start+row['safe_duration_slots'])
                if row['state_at_issue']!='RUNNING' and site!='UNASSIGNED':row['Rack_label']=sorted(p.rack_pool_id for p in context.capacity.eligible_racks(site,row['requested_GPU']))[0]
                selected.append(row)
        selected.sort(key=lambda r:r['job_uid'])
        selected_reference=all((r['AIDC_site'],r['start_slot'],r['end_slot'])==(refs[r['job_uid']]['AIDC_site'],refs[r['job_uid']]['start_slot'],refs[r['job_uid']]['end_slot']) for r in selected)
        if selected_reference:
            selected=deepcopy(reference_jobs);pcc=np.asarray(reference_pcc).copy();gpu=ref_gpu
            terminal=terminal_audit(reference_jobs,selected)
            terminal.update(authority='EXACT_RW_DECISIONS_COMMON_T_DA',decision_exact_equal=digest(selected)==digest(reference_jobs))
        else:
            gpu=occupancy(selected)
            pcc=np.column_stack([context.tables[s][np.arange(T),gpu[:,i]] for i,s in enumerate(sites)])
            terminal=terminal_audit(reference_jobs,selected)
            if terminal['status']!='PASS':raise RuntimeError('COORDINATED_TERMINAL_AUTHORITY_MUTATED')
        result=evaluate(pcc)
        if result['status']!='PASS' or result['rho_max']>before['rho_max']+tolerance:raise RuntimeError('B1_PLANNING_NONWORSENING_OR_FEASIBILITY_FAIL')
        actual_deviation=sum(occupancy_deviation(refs[x['job_uid']],x) for x in selected)
        assert actual_deviation==secondary
        if result['rho_max']>primary+tolerance+1e-7:raise RuntimeError('PRIMARY_SOLUTION_MATERIALIZATION_DRIFT')
        result={'status':'PASS','jobs':selected,'PCC':pcc,'GPU':gpu,'grid':result,'reference_grid':before,
            'primary_optimum_incumbent':primary,'primary_bound':bound,'secondary_reference_deviation_GPU_slots':secondary,
            'complete_RW_reference_selected':selected_reference,'terminal_audit':terminal,'solver_stages':stages,
            'B1_PRIMARY_OBJECTIVE':'MIN_RHO_MAX','ZERO_FEASIBILITY_FINAL_OBJECTIVE':'NO','B1_MESS_ENABLED':'NO',
            'B1_REFERENCE_CANDIDATE_INCLUDED':'PASS','B1_PLANNING_NONWORSENING':'PASS',
            'COMMON_DURATION_IDENTITY':'PASS','B1_SECONDARY_OBJECTIVE':'MIN_DEVIATION_FROM_B0',
            'primary_gain_vs_reference':before['rho_max']-result['rho_max'],
            'final_decision_SHA':digest(sorted(selected,key=lambda r:r['job_uid'])),'grid_rows':grid_rows,
            'wallclock_seconds':time.perf_counter()-started,'tolerance':tolerance,'FULL_MAY_AUTHORIZED':'NO'}
        write_json(output/'MIN_RHO_ACCEPTED_AIDC.json',result);return result
    finally:model.dispose()
