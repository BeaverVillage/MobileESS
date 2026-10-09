"""F1-F5 restrictions exist only on auxiliary models; FULL gates every point."""
from pathlib import Path
import numpy as np
from v42_may_campaign_native90 import m_stage as original
from v42_b2_seed_recovery_v18.stationary_dispatch import validated_start,discrete_stationary
from v42_b2_seed_recovery_v18.initialization import analyze,sensitivity,admit
from .common import atomic,read,record,now

def status_name(code,policy_cap=False):
    return {2:'OPTIMAL',3:'INFEASIBLE',4:'INF_OR_UNBD',9:'TIME_LIMIT',12:'NUMERIC',
        10:'SOLUTION_LIMIT',11:'INTERRUPTED_AT_POLICY_CAP' if policy_cap else 'INTERRUPTED'}.get(code,'OTHER_'+str(code))

def critical_slots(rows,horizon=96):
    slots=set()
    for row in rows:
        name=row['name']
        if name.startswith(('voltage_upper[','voltage_lower[')):
            t=int(name.split('[',1)[1].split(',')[0]);slots.update(range(max(0,t-2),min(horizon,t+3)))
    return sorted(slots)

def pattern_bounds(case,baseline_low,baseline_high,*,sites=None,free_modes=(),stationary=False):
    """Candidate restrictions. All original rows, types and other bounds survive."""
    low=np.array(baseline_low,copy=True);high=np.array(baseline_high,copy=True)
    free=set(free_modes);sites=set(sites or ())
    ids,values=discrete_stationary(case);stationary_values=dict(zip(ids,values))
    excluded=[]
    for j in ids:
        name=str(case.d['names'][j])
        if name.startswith('charge_mode['):
            t=int(name[12:-1].split(',')[-1])
            if t not in free:low[j]=high[j]=0.
        elif stationary:
            low[j]=high[j]=stationary_values[j]
        elif name.startswith('arc['):
            unit,k=name[4:-1].split(',');arc=case.graph[2][int(k)]
            allowed=sites|{case.graph[1][unit]}
            energy_ok=arc[-1] is None or arc[-1].energy_kwh<=case.graph[3].maximum-case.graph[3].minimum
            if arc[0] not in allowed or arc[2] not in allowed or not energy_ok:
                low[j]=high[j]=0.;excluded.append(int(k))
            if arc[-1] is not None:arc[-1].validate(96)
        elif name.startswith('node_activity['):
            unit,site,t=name[14:-1].split(',')
            if site not in sites|{case.graph[1][unit]}:low[j]=high[j]=0.
        else:raise ValueError('UNKNOWN_ORIGINAL_DISCRETE_FAMILY:'+name)
    if np.any(low<baseline_low) or np.any(high>baseline_high) or np.any(low>high):
        raise ValueError('CANDIDATE_OUTSIDE_ORIGINAL_BOUND_DOMAIN')
    return low,high,dict(heuristic_initialization_only=True,free_mode_slots=sorted(free),
        candidate_sites=sorted(sites),stationary=stationary,excluded_arc_indices=sorted(set(excluded)),
        original_constraints_removed=0,original_Adaptive_domain_changed=False,
        energy_screen='ONE_TRAVEL_ARC_ENERGY_CANNOT_EXCEED_ORIGINAL_SOC_RANGE',
        terminal_location_policy='ORIGINAL_TERMINAL_LOCATION_ROW; NO_ADDED_RETURN_TO_ORIGIN_REQUIREMENT')

def full_point(case,model,budget,stage):
    if not model.SolCount:return None
    raw=np.asarray(model.getAttr('X'),dtype=float)
    out=case.output/'FEASIBILITY_STAGES'/stage;out.mkdir(parents=True,exist_ok=True)
    packet=out/'RAW_POINT.npz';np.savez_compressed(packet,point=raw)
    try:
        with budget.cost('integer_physical_validation',stage+'_ORIGINAL_FULL_REPLAY'):
            strict=original._strict_ub(case,packet,{})
        if strict.get('PASS') is not True:raise ValueError('FULL_REPLAY_DID_NOT_PASS')
        strict['case_sha']=case.case_sha;atomic(out/'FULL_REPLAY.json',strict)
        return raw,strict,out/'FULL_REPLAY.json'
    except ValueError as exc:
        atomic(out/'FULL_REPLAY.json',dict(PASS=False,error=str(exc),invalid_point_not_admitted=True))
        return None

def accepted(case,found,budget,stage):
    point,strict,path=found
    point=admit(case,point,strict,path,budget,stage)
    receipt_path=case.output/'SEED_BYPASS_CERTIFIED_DISPATCH.json';receipt=read(receipt_path)
    receipt.update(first_initialization_stage=stage,LP_initialization_Native_Runtime=sum(c['Native_Runtime']
        for c in budget.calls if c['component']=='FEASIBILITY_LP'),
        initialization_total_Native_Runtime=budget.used(),unrestricted_F5_calls=sum(c['track']=='F5' for c in budget.calls),
        seed_bypass_means_no_unrestricted_seed_not_no_auxiliary_MILP=True)
    receipt.update(event='FULL_VALIDATED_FEASIBILITY_INITIAL_POINT' if stage=='F5' else 'SEED_BYPASS_CERTIFIED_DISPATCH',
        M_SEED_optimize_calls=receipt['unrestricted_F5_calls'],unnecessary_seed_MILP_omitted=stage!='F5')
    atomic(receipt_path,receipt);return point

def repaired_dispatch(case,model,variables,budget,peak,baseline_low,baseline_high,progress):
    """The old fixed LPs failed because slot-96 occupancy was all zero.

    Correct that actual bug before trying progressively larger free-mode MILPs.
    Every original row/objective is retained, and only FULL gates admission.
    """
    from .fixed_pattern import values_for
    sites,initial,arcs,_,_=case.graph
    stay={(a[0],a[1]):k for k,a in enumerate(arcs) if a[-1] is None}
    paths={unit:[stay[site,t] for t in range(96)] for unit,site in initial.items()}
    for name,charge in (('F1_TERMINAL_REPAIRED_BEFORE_PEAK',lambda u,t:t<peak),
                        ('F1_TERMINAL_REPAIRED_AFTER_PEAK',lambda u,t:t>=peak)):
        if budget.remaining()<=300.:break
        ids,values=values_for(case,paths,charge)
        low=baseline_low.copy();high=baseline_high.copy();low[ids]=values;high[ids]=values
        if np.any(low<baseline_low) or np.any(high>baseline_high):raise ValueError('REPAIRED_PATTERN_OUTSIDE_ORIGINAL_BOUNDS')
        model.reset();model.setAttr('LB',variables,low.tolist());model.setAttr('UB',variables,high.tolist())
        model.setAttr('VType',variables,['C']*len(variables));model.Params.Method=1;model.update()
        out=case.output/'FEASIBILITY_STAGES'/name;out.mkdir(parents=True,exist_ok=True)
        atomic(out/'MODEL_POLICY.json',dict(stage=name,terminal_slot=96,
            terminal_activity_matches_last_original_arc=True,all_original_rows_and_objective_retained=True,
            fixed_original_integer_count=len(ids),restriction_applies_only_to_initialization=True))
        if progress:progress(dict(phase=name))
        budget.native_optimize(model,component='FEASIBILITY_LP',track=name,label=name,
            requested_seconds=min(60.,max(0.,budget.remaining()-300.)))
        atomic(out/'STATUS.json',dict(raw_status=int(model.Status),status=status_name(int(model.Status),True),
            SolCount=int(model.SolCount),restricted_candidate_only=True,FULL_MILP_infeasibility_claimed=False))
        found=full_point(case,model,budget,name)
        if found is not None:return accepted(case,found,budget,name)
    return None

def initialize(case,budget,progress):
    start=validated_start(case,budget,progress)
    atomic(case.output/'F1_STATUS.json',dict(stage='F1',raw_status=budget.calls[-1].get('Native_status') if budget.calls else None,
        status=status_name(int(budget.calls[-1].get('Native_status',0)),True) if budget.calls else 'NO_CALL',
        accepted=start is not None,TIME_LIMIT_is_not_INFEASIBLE=True))
    if start is not None:
        return accepted(case,(start,read(case.output/'STATIONARY_DISPATCH_REPLAY.json'),
            case.output/'STATIONARY_DISPATCH_REPLAY.json'),budget,'F1_STATIONARY_LP')
    rows=analyze(case);scores,peak,sens=sensitivity(case,rows);critical=critical_slots(rows)
    ranked=sorted((s for s in case.graph[0] if s.startswith('STA')),key=lambda s:(-scores[s],s))
    atomic(case.output/'FEASIBILITY_INITIALIZATION_PLAN.json',dict(critical_slots=critical,STA_ranking=ranked,
        sensitivity=sens,ranking_does_not_prove_feasibility=True,all_96_slot_rows_retained=True,
        initialization_native_limit_seconds=budget.native_limit,F5_requested_seconds=300.,
        partial_mode_policy='ZERO_OUTSIDE_CRITICAL_SLOTS_THEN_FREE_ALL_96',objective='AUXILIARY_F2_F3_FEASIBILITY_ZERO; ORIGINAL_FULL_UB_REPLAY'))
    model,identity=original._model(case)
    original_method=model.Params.Method
    variables=model.getVars();baseline_low=np.asarray(model.getAttr('LB'));baseline_high=np.asarray(model.getAttr('UB'))
    original_types=model.getAttr('VType');original_obj=model.getAttr('Obj')
    stages=[('F2_CRITICAL_MODES',120.,dict(stationary=True,free_modes=critical)),
            ('F2_ALL_96_MODES',180.,dict(stationary=True,free_modes=range(96)))]
    seen=set()
    for count,seconds in ((4,120.),(8,180.),(len(ranked),240.)):
        chosen=tuple(ranked[:count])
        if chosen in seen:continue
        seen.add(chosen);stages.append((f'F3_STA_{len(chosen):02d}',seconds,dict(sites=chosen,free_modes=range(96))))
    stages.append(('F3_ALL_ORIGINAL_SITES',120.,dict(sites=case.graph[0],free_modes=range(96))))
    import gurobipy as gp
    try:
        repaired=repaired_dispatch(case,model,variables,budget,peak,baseline_low,baseline_high,progress)
        if repaired is not None:return repaired
        model.Params.Method=original_method
        for stage,seconds,restriction in stages:
            if budget.remaining()<=300:break
            low,high,description=pattern_bounds(case,baseline_low,baseline_high,**restriction)
            model.reset();model.setAttr('LB',variables,low.tolist());model.setAttr('UB',variables,high.tolist())
            model.setAttr('VType',variables,original_types);model.setAttr('Start',variables,[gp.GRB.UNDEFINED]*len(variables))
            model.setObjective(0.,gp.GRB.MINIMIZE);model.Params.MIPGap=.03
            model.Params.MIPFocus=1;model.Params.SolutionLimit=1;model.Params.Presolve=2;model.update()
            out=case.output/'FEASIBILITY_STAGES'/stage;out.mkdir(parents=True,exist_ok=True)
            atomic(out/'MODEL_POLICY.json',dict(description,original_model_identity=identity,
                stage=stage,auxiliary_objective=0.,original_objective_replayed_for_UB=True,
                unverified_MIP_Start_supplied=False,TimeLimit_requested=seconds))
            if progress:progress(dict(phase=stage))
            began=budget.used()
            budget.native_optimize(model,component='P1',track=stage,label=stage,
                requested_seconds=min(seconds,max(0.,budget.remaining()-300.)))
            status=int(model.Status)
            atomic(out/'STATUS.json',dict(raw_status=status,status=status_name(status,status==11),
                SolCount=int(model.SolCount),Native_Runtime=budget.used()-began,restricted_candidate_only=True,
                FULL_MILP_infeasibility_claimed=False,Native_solver_objective_not_original_Global_UB=True))
            found=full_point(case,model,budget,stage)
            if found is not None:return accepted(case,found,budget,stage)
            if status==3:
                from .diagnostics import diagnose_model
                diagnose_model(case,model,budget,out,original_types,seconds=15.)
        # F5 restores every original bound/type/objective before unrestricted solve.
        model.reset();model.setAttr('LB',variables,baseline_low.tolist());model.setAttr('UB',variables,baseline_high.tolist())
        model.setAttr('VType',variables,original_types);model.setAttr('Obj',variables,original_obj)
        model.setAttr('Start',variables,[gp.GRB.UNDEFINED]*len(variables));model.update()
        model.Params.MIPGap=.03;model.Params.MIPFocus=1;model.Params.SolutionLimit=1
        if budget.remaining()>0:
            if progress:progress(dict(phase='F5_UNRESTRICTED_INITIALIZATION_ONLY'))
            budget.native_optimize(model,component='P1',track='F5',label='F5_UNRESTRICTED_ORIGINAL_MILP',requested_seconds=300.)
            found=full_point(case,model,budget,'F5')
            if found is not None:return accepted(case,found,budget,'F5')
        atomic(case.output/'INITIALIZATION_FAILURE.json',dict(PASS=False,
            reason='NO_ORIGINAL_FULL_VALID_INTEGER_POINT_WITHIN_INITIALIZATION_CAP',
            Native_Runtime=budget.used(),initialization_native_cap=budget.native_limit,
            FULL_MILP_infeasibility_claimed=False,automatic_retry=False))
        return None
    finally:model.dispose()
