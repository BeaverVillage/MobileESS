"""Four strict objective passes on ONE joint temporal/spatial/migration model."""
from collections import defaultdict, Counter
from copy import deepcopy
from pathlib import Path
import time, math, gc
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.v40a.grid import add_grid, evaluate_grid
from dayahead.v40a.invariants import BEGIN, H, digest
from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters
from dayahead.paper_analysis.storage import write_json
from .domain import Option, options, segments, deviation, materialize, audit


def solve(reference_jobs, reference_pcc, context, output, *, temporal_only=False, work_limits=(60,180,300), inject_reference=False, factorize=True, build_only=False, event_load=None, diagnostic_work_limit=None):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    if (output/'ACCEPTED_AIDC.json').exists(): raise RuntimeError('PRESERVE_COMPLETED_SOLVE')
    from dayahead.v41r1.migration_memory import process_measure
    memory_before_build=process_measure()
    started=time.perf_counter(); refs={r['job_uid']:deepcopy(r) for r in reference_jobs}
    assert len(refs)==len(reference_jobs)
    sites=tuple(context.capacity.aidc_ids); T=len(context.coefficients)
    from dayahead.v41r1.migration import active,model_boundary
    revision=any(active(r) for r in reference_jobs)
    if event_load is None:event_load=revision
    if revision and T!=96:raise ValueError('SCIENTIFIC_DAY_MUST_HAVE_96_SLOTS')
    if revision and getattr(context,'day',None)=='2025-05-01' and factorize and not build_only:
        from dayahead.v41r1.migration_factor import verify_gate
        verify_gate()
    wan=getattr(context,'wan',None); elapsed=getattr(context,'elapsed',{})
    def occupancy(rows):
        result=np.zeros((T,len(sites)),dtype=int)
        for row in rows:
            for s,a,b in segments(row):
                lo,hi=max(BEGIN,a),min(BEGIN+T,b)
                if lo<hi: result[lo-BEGIN:hi-BEGIN,sites.index(s)]+=row['requested_GPU']
        return result
    def evaluate(pcc):
        controls=np.zeros((T,len(context.coefficients[0].control_names))); controls[:,:len(sites)]=pcc
        return evaluate_grid(context.coefficients,controls,context.nodes)
    ref_gpu=occupancy(reference_jobs); before=evaluate(reference_pcc)
    assert before['status']=='PASS'
    groups=defaultdict(list); uid_options={}; domain_counts=Counter()
    for uid,row in sorted(refs.items()):
        opts=options(row,context.capacity,wan,elapsed,temporal_only)
        assert Option(row['AIDC_site'],row['start_slot'],row['end_slot']) in opts
        costs=tuple(deviation(row,opt) for opt in opts)
        # UID is retained for RUNNING migration serial order. Pending cohorts
        # have identical full choices, per-choice service and reference costs.
        key=(row['requested_GPU'],row['safe_duration_slots'],opts,costs,
             uid if any(o.migrated for o in opts) else '',row['AIDC_site'] if row['state_at_issue']=='RUNNING' else '')
        groups[key].append(uid); uid_options[uid]=opts
        domain_counts['options']+=len(opts)
        domain_counts['migration_options']+=sum(o.migrated for o in opts)
        domain_counts['jobs_with_migration_options']+=any(o.migrated for o in opts)
        domain_counts['jobs_with_spatial_options']+=len({o.site for o in opts})>1
        domain_counts['jobs_with_temporal_options']+=len({o.start for o in opts})>1
    keys=sorted(groups,key=lambda k:tuple(groups[k])); model=gp.Model('V40G_JOINT_AIDC')
    model.Params.OutputFlag=1; model.Params.LogToConsole=0; model.Params.Threads=4; model.Params.Seed=20260905
    model.Params.MIPGap=0; model.Params.MIPGapAbs=0; model.Params.FeasibilityTol=1e-9
    model.Params.IntFeasTol=1e-9; model.Params.OptimalityTol=1e-9
    model.Params.MemLimit=GRB.INFINITY; model.Params.SoftMemLimit=GRB.INFINITY; model.Params.NodefileStart=.5
    model.Params.Method=1  # One dual-simplex root LP; avoid concurrent LP copies across four days.
    nodefile_dir=(output/'gurobi_nodefiles').resolve();nodefile_dir.mkdir(exist_ok=True)
    model.Params.NodefileDir=str(nodefile_dir)
    model.Params.LogFile=str((output/'SOLVER.log').resolve())
    stages=[]; events=[]; primary=None; numerical_cut_keys=set()
    def callback(m,where):
        if where==GRB.Callback.MIPSOL:
            e={'stage':len(stages),'objective':m.cbGet(GRB.Callback.MIPSOL_OBJ),'bound':m.cbGet(GRB.Callback.MIPSOL_OBJBND),'runtime':m.cbGet(GRB.Callback.RUNTIME)}
            events.append(e); print('V40G incumbent '+str(e),flush=True)
    def optimize(label):
        tier=0
        while True:
            limit=work_limits[min(tier,len(work_limits)-1)]*3**max(0,tier-len(work_limits)+1)
            model.Params.WorkLimit=limit; model.optimize(callback)
            from dayahead.v41r1.migration_memory import measure
            entry={'stage':label,'status':int(model.Status),'OPTIMAL':model.Status==GRB.OPTIMAL,
                   'incumbent':float(model.ObjVal) if model.SolCount else None,'bound':float(model.ObjBound),
                   'work':float(model.Work),'runtime_seconds':float(model.Runtime),'work_limit':limit,
                   'memory':measure(model,output/'SOLVER.log')}
            stages.append(entry); write_json(output/'SOLVER_STAGES.json',{'stages':stages,'events':events})
            print('V40G '+str(entry),flush=True)
            if model.Status==GRB.OPTIMAL:
                if primary is not None:
                    actual=np.array([[context.tables[s][t,int(round(gpu_variables[t,s].X))] for s in sites] for t in range(T)])
                    metric=evaluate(actual)
                    if metric['rho_max']>primary+1e-10:
                        t=metric['critical_slot'];k=context.coefficients[t].branch_names.index(metric['critical_line'])
                        if (t,k) in numerical_cut_keys:raise RuntimeError('STRICT_PRIMARY_NUMERICAL_CAP_NOT_ENFORCED')
                        numerical_cut_keys.add((t,k));c=context.coefficients[t]
                        bias,correction,_=anchored_polygon_parameters(c)
                        apothem=c.branch_limits[k]*math.cos(math.pi/LINE_POLYGON_FACES)
                        for face in range(LINE_POLYGON_FACES):
                            angle=2*math.pi*face/LINE_POLYGON_FACES
                            weights=(math.cos(angle)*c.flow_p_matrix[k]+math.sin(angle)*c.flow_q_matrix[k])/apothem+correction[:,k]
                            constant=(math.cos(angle)*c.flow_p_constant[k]+math.sin(angle)*c.flow_q_constant[k])/apothem+float(bias[k])-correction[:,k]@c.anchor
                            # Algebraically identical original row, expressed
                            # directly and rescaled to retain tiny primary gains.
                            expr=float(constant)+gp.quicksum(float(weights[i])*controls[t][i] for i in range(len(weights)) if weights[i])
                            model.addConstr(1e6*expr<=1e6*primary,name=f'EXACT_PRIMARY_NUMERIC_ROW[{t},{k},{face}]')
                        return optimize(label+'_NUMERICAL_CAP_RECHECK')
                return entry
            if model.Status==GRB.WORK_LIMIT:
                tier+=1
                continue
            break
        raise RuntimeError(label+'_OPTIMUM_NOT_CERTIFIED')
    try:
        variables={}; factors={}; load=defaultdict(gp.LinExpr); wan_active=defaultdict(gp.LinExpr)
        from dayahead.v41r1.migration_load import add_interval
        def interval(site,start,end,weight):
            add_interval(load,site,start,end,weight,T,event_form=event_load)
        migration=gp.LinExpr(); dev=gp.LinExpr(); tie=gp.LinExpr(); migration_groups=[]
        for i,key in enumerate(keys):
            gpu,duration,opts,costs,_,_=key; members=groups[key]; row=refs[members[0]]; n=len(members)
            from dayahead.v41r1.migration_factor import eligible,compile as compile_factor
            if revision and factorize and eligible(row,opts):
                assert n==1
                factor=compile_factor(model,row,opts,costs,i,load,wan_active,inject_reference=inject_reference,interval=interval)
                factors[i]=factor;migration+=factor['migration'];dev+=factor['deviation'];tie+=factor['tie']
                migration_groups.append((members[0],factor['migration'],factor['start'],factor['length']))
                continue
            counts=Counter(Option(refs[u]['AIDC_site'],refs[u]['start_slot'],refs[u]['end_slot']) for u in members)
            vs=[]; mig=gp.LinExpr(); transfer_start=gp.LinExpr(); transfer_length=gp.LinExpr()
            for k,opt in enumerate(opts):
                if revision and len(opts)==1:
                    v=n;variables[i,k]=v
                else:
                    v=model.addVar(vtype=GRB.INTEGER,lb=0,ub=n,name=f'choice[{i},{k}]');variables[i,k]=v;vs.append(v)
                    v.Start=counts[opt]
                    if inject_reference:v.LB=counts[opt];v.UB=counts[opt]
                for s,a,b in opt.segments(row):
                    interval(s,a,b,gpu*v)
                dev+=costs[k]*v; tie+=(i+1)*(k+1)*v
                if opt.migrated:
                    mig+=v; migration+=v; transfer_start+=opt.transfer_start*v
                    transfer_length+=(opt.transfer_end-opt.transfer_start)*v
                    for t in range(opt.transfer_start,opt.transfer_end):wan_active[t]+=v
            if vs:model.addConstr(gp.quicksum(vs)==n,name=f'common_service[{i}]')
            if any(o.migrated for o in opts):migration_groups.append((members[0],mig,transfer_start,transfer_length))
        # Existing UID-serial full-rate transfer construction, jointly coupled
        # to migration choices; no temporal feasibility prerequisite.
        cursor=BEGIN+2
        for uid,mig,start,length in sorted(migration_groups):
            if revision:
                # Existing V39C binder: cursor=max(cursor,first_checkpoint).
                # Late releases were absent from the legacy issue-RUNNING set.
                cp=next(o.checkpoint for o in uid_options[uid] if o.migrated)
                ready=model.addVar(vtype=GRB.INTEGER,lb=BEGIN+2,ub=H-1,name='WAN_ready_'+uid)
                if isinstance(cursor,int):model.addConstr(ready==max(cursor,cp))
                else:model.addGenConstrMax(ready,[cursor],constant=cp,name='WAN_release_'+uid)
                selected_flag=model.addVar(vtype=GRB.BINARY,name='WAN_selected_'+uid)
                model.addConstr(selected_flag==mig)
                after=model.addVar(vtype=GRB.INTEGER,lb=BEGIN+2,ub=H-1,name='WAN_cursor_'+uid)
                model.addGenConstrIndicator(selected_flag,True,start==ready)
                model.addGenConstrIndicator(selected_flag,True,after==start+length)
                model.addGenConstrIndicator(selected_flag,False,after==cursor)
                cursor=after
            else:
                model.addConstr(start>=cursor-H*(1-mig),name='WAN_serial_start_lb_'+uid)
                model.addConstr(start<=cursor+H*(1-mig),name='WAN_serial_start_ub_'+uid)
                cursor=cursor+length
        for t,expr in wan_active.items():model.addConstr(expr<=1,name=f'WAN_one_active[{t}]')
        controls=[[0.0]*len(c.control_names) for c in context.coefficients];gpu_variables={}
        for t in range(T):
            for k,s in enumerate(sites):
                cap=int(context.capacity.site_capacity[s]); vals=context.tables[s][t]
                assert reference_pcc[t,k]==vals[int(ref_gpu[t,k])]
                g=model.addVar(vtype=GRB.INTEGER,lb=0,ub=cap,name=f'GPU[{t},{s}]')
                gpu_variables[t,s]=g
                p=model.addVar(lb=float(vals.min()),ub=float(vals.max()),name=f'PCC[{t},{s}]')
                rhs=load[t,s]+(gpu_variables[t-1,s] if event_load and t else 0)
                model.addConstr(g==rhs);model.addGenConstrPWL(g,p,list(range(cap+1)),vals.tolist())
                controls[t][k]=p
        rho,grid_rows=add_grid(model,context.coefficients,controls,min(1.,before['rho_max']+1e-6))
        reserve_mean = None
        if hasattr(context, 'v41_ml_snapshot'):
            from dayahead.v41.reserve import add_constraints
            reserve_mean, reserve_xi = add_constraints(model, context, gpu_variables)
        model.setObjective(rho,GRB.MINIMIZE);model.update()
        objective=[(v.VarName,float(v.Obj)) for v in model.getVars() if v.Obj]
        assert objective==[('rho_max',1.)]
        write_json(output/'PRIMARY_STRUCTURE.json',{'method':'JOINT_TEMPORAL_SPATIAL_AIDC_GRID_OPTIMIZATION',
            'diagnostic_only':build_only or temporal_only or inject_reference or not factorize,'reference_injected':inject_reference,
            'objective':objective,'grid_rows':grid_rows,'domain_counts':dict(domain_counts),
            'cohort_count':len(keys),'factored_cohorts':len(factors),
            'factorization_exact_original_options':sum(f['original_option_count'] for f in factors.values()),
            'factorization_choice_variables':sum(f['factored_choice_count'] for f in factors.values()),
            'model_variables':model.NumVars,'model_constraints':model.NumConstrs,
            'binary_variables':model.NumBinVars,'integer_variables_including_binary':model.NumIntVars,
            'general_constraints':model.NumGenConstrs,'build_only':build_only,
            'continuous_variables':model.NumVars-model.NumIntVars,
            'matrix_nonzeros':model.NumNZs,'event_load_recurrence':event_load,
            'TEMPORAL_FIRST_HARD_HIERARCHY':'NO','TEMPORAL_AND_SPATIAL_AIDC_PRIMARY_JOINT':not temporal_only,
            'reference_candidate_included':True,'migration_penalty_in_primary':0,'MESS_variables':0,
            'WAN_policy':'Existing first checkpoint / fixed OD / UID serial / full frozen path budget / one restart slot',
            'all_migration_options_present_before_first_solve':True})
        if revision:write_json(output/'DAY_BOUNDARY_AUDIT.json',model_boundary(model,reference_jobs,uid_options,T))
        from dayahead.v41r1.migration_memory import persist_model
        persist_model(model,output)
        from dayahead.v41r1.migration_memory import measure
        build_memory=measure(model,output/'SOLVER.log')
        # Persisted boundary/candidate counts are sufficient audit evidence.
        # Factored decisions reconstruct an Option from route and arrival;
        # the multi-million-column reference enumeration is no longer needed.
        decode=[(tuple(groups[key]),() if i in factors else key[2]) for i,key in enumerate(keys)]
        del groups,keys,uid_options,load,wan_active,migration_groups
        del key,opts,costs,members,row
        gc.collect()
        write_json(output/'MODEL_BUILD_MEMORY.json',dict(before_build=memory_before_build,
            after_model_build=build_memory,after_builder_release=measure(model,output/'SOLVER.log'),
            explicit_candidate_diagnostics_released=True,one_model_reused_for_P1_P5=True))
        print(f'V40G model {model.NumVars} variables {model.NumConstrs} rows {dict(domain_counts)}',flush=True)
        if build_only:
            if diagnostic_work_limit is not None:
                model.Params.WorkLimit=diagnostic_work_limit;model.optimize()
                write_json(output/'INFRASTRUCTURE_SOLVE_MEMORY.json',dict(scientific_result=False,
                    status=int(model.Status),work=float(model.Work),memory=measure(model,output/'SOLVER.log')))
            from dayahead.paper_analysis.storage import read
            return read(output/'PRIMARY_STRUCTURE.json')
        pstage=optimize('PRIMARY_MIN_RHO'); primary=float(rho.X); bound=float(model.ObjBound)
        # NO tolerance allowance for lower priorities. Only solver feasibility
        # roundoff remains; a 1e-6 rho degradation is explicitly not permitted.
        model.addConstr(1000*rho<=1000*primary,name='PRIMARY_EXACT_VALUE_LOCK')
        if reserve_mean is not None:
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='PRIMARY_EXACT_VALUE_LOCK', sense='<=',
                scale=1000, bound=primary, intentional_degradation=0., feasibility_tolerance=model.Params.FeasibilityTol)
        reserve_stage = None
        if reserve_mean is not None:
            model.setObjective(reserve_mean, GRB.MINIMIZE)
            reserve_stage = optimize('V41_SECONDARY_MIN_MEAN_H4_SHORTFALL')
            reserve_optimum = float(reserve_mean.getValue())
            model.addConstr(reserve_mean <= reserve_optimum + model.Params.FeasibilityTol,
                            name='V41_MEAN_H4_SHORTFALL_LOCK')
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='V41_MEAN_H4_SHORTFALL_LOCK', sense='<=',
                bound=reserve_optimum + model.Params.FeasibilityTol, feasibility_tolerance=model.Params.FeasibilityTol)
        model.setObjective(migration,GRB.MINIMIZE); optimize('SECONDARY_MIN_MIGRATIONS')
        secondary=int(round(migration.getValue()));model.addConstr(migration==secondary,name='MIGRATION_EXACT_LOCK')
        if reserve_mean is not None:
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='MIGRATION_EXACT_LOCK', sense='=', bound=secondary)
        model.setObjective(dev,GRB.MINIMIZE);optimize('TERTIARY_COMPLETE_REFERENCE_DEVIATION')
        tertiary=int(round(dev.getValue()));model.addConstr(dev==tertiary,name='REFERENCE_DEVIATION_EXACT_LOCK')
        if reserve_mean is not None:
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='REFERENCE_DEVIATION_EXACT_LOCK', sense='=', bound=tertiary)
        model.setObjective(tie,GRB.MINIMIZE);optimize('QUATERNARY_STABLE_TIE')
        selected=[]; materialized_dev=0
        for i,(members,opts) in enumerate(decode):
            places=[]
            if i in factors:
                from dayahead.v41r1.migration_factor import selected as selected_factor
                places=[selected_factor(factors[i],refs[members[0]])]
            else:
                for k,opt in enumerate(opts):places.extend([opt]*int(round(variables[i,k] if isinstance(variables[i,k],int) else variables[i,k].X)))
            assert len(places)==len(members)
            for uid,opt in zip(sorted(members),places):
                selected.append(materialize(refs[uid],opt,context.capacity,wan));materialized_dev+=deviation(refs[uid],opt)
        selected.sort(key=lambda r:r['job_uid']); assert materialized_dev==tertiary
        terminal=audit(reference_jobs,selected,context.capacity,wan)
        gpu=occupancy(selected);pcc=np.column_stack([context.tables[s][np.arange(T),gpu[:,i]] for i,s in enumerate(sites)])
        grid=evaluate(pcc)
        assert grid['status']=='PASS' and grid['rho_max']<=before['rho_max']+1e-6
        if grid['rho_max']>primary+1e-10:raise RuntimeError('PRIMARY_SACRIFICED_IN_LOWER_PRIORITY')
        assert sum(bool(r.get('migration_selected')) for r in selected)==secondary
        value={'status':'PASS','jobs':selected,'PCC':pcc,'GPU':gpu,'grid':grid,'reference_grid':before,
               'primary_optimum':primary,'primary_bound':bound,'primary_value_lock':primary,
               'primary_degradation_allowance':0.,'solver_feasibility_tolerance':1e-9,
               'secondary_migration_optimum':secondary,'tertiary_reference_deviation_optimum':tertiary,
               'quaternary_tie_optimum':float(tie.getValue()),'solver_stages':stages,'terminal_audit':terminal,
               'final_decision_SHA':digest(selected),'diagnostic_only':temporal_only or inject_reference or not factorize,
               'reference_injected':inject_reference,'domain_counts':dict(domain_counts),
               'TEMPORAL_FIRST_HARD_HIERARCHY':'NO','TEMPORAL_AND_SPATIAL_AIDC_PRIMARY_JOINT':'NO' if temporal_only else 'YES',
               'MIGRATION_PENALTY_LEVEL':'SECONDARY_ONLY','PRIMARY_GRID_OBJECTIVE_SACRIFICED_FOR_MIGRATION_AVOIDANCE':'NO',
               'FULL_MAY_AUTHORIZED':'NO','B2_B3_AUTHORIZED':'NO','wallclock_seconds':time.perf_counter()-started}
        if reserve_mean is not None:
            from dayahead.v41.reserve import diagnostics, OBJECTIVE_HIERARCHY
            reserve_report = diagnostics(context.v41_ml_snapshot, context.capacity, gpu)
            if reserve_report['mean_xi_GPUh'] > reserve_optimum + 2 * model.Params.FeasibilityTol:
                raise RuntimeError('V41_RESERVE_PRIORITY_SACRIFICED')
            value.update(ML_snapshot_sha256=context.v41_ml_snapshot_sha256, reserve_interface_version='V41',
                objective_hierarchy=list(OBJECTIVE_HIERARCHY), reserve_diagnostics=reserve_report,
                reserve_optimum=reserve_optimum, reserve_stage=reserve_stage,
                OBJECTIVE_VECTOR=[grid['rho_max'], reserve_report['mean_xi_GPUh'], secondary,
                                  tertiary, float(tie.getValue())])
        write_json(output/'ACCEPTED_AIDC.json',value); return value
    finally:model.dispose()
