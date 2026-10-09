"""Bounded candidate generation from this day's original graph and voltages.

Candidates restrict only auxiliary LPs. They never alter Adaptive/MILP domains.
"""
from pathlib import Path
import numpy as np
from scipy import sparse
from v42_may_campaign_native90 import m_stage as original
from .common import atomic,read,record,now


def analyze(case):
    receipt=read(case.output/'SAME_DAY_STATIONARY_CANDIDATE.json')
    replay=receipt.get('replay',{})
    rows=[]
    for domain,data in (('original_FULL',case.original_d),('C3A',case.d)):
        key='original_full_matrix' if domain=='original_FULL' else 'C3A'
        for i in sorted(set(replay.get(key,{}).get('failing_rows',[]))):
            rows.append(dict(domain=domain,index=i,name=str(data['row_names'][i]),
                sense=str(data['sense'][i]),rhs=float(data['rhs'][i]),
                LP_failure_row_residual='UNKNOWN_WITHOUT_FEASIBLE_LP_POINT'))
    value=dict(UTC=now(),case_sha=case.case_sha,original_stationary_background_failures=rows,
        original_max_row_violation=replay.get('original_full_matrix',{}).get('maximum_observed_row_violation'),
        fixed_candidate_infeasible_does_not_prove_FULL_MILP_infeasible=True)
    atomic(case.output/'INITIALIZATION_FAILURE_CONSTRAINT_ANALYSIS.json',value)
    return rows


def sensitivity(case,rows):
    sites=case.graph[0];scores={s:0. for s in sites};slots=[];records=[]
    for r in rows:
        if r['domain']!='C3A' or not r['name'].startswith(('voltage_upper[','voltage_lower[')):continue
        t,node=map(int,r['name'].split('[',1)[1][:-1].split(','));slots.append(t)
        c=case.coefficients[t]
        for site in sites:
            names=list(c.control_names)
            p=names.index('mess_p_kw['+site+']');q=names.index('mess_q_kvar['+site+']')
            pc,qc=float(c.voltage_matrix[p,node]),float(c.voltage_matrix[q,node])
            score=abs(pc)*case.graph[3].p_limit+abs(qc)*case.graph[3].pcs_kva
            scores[site]+=score
            records.append(dict(slot=t,node=node,site=site,P_sensitivity=pc,Q_sensitivity=qc,
                candidate_ranking_score=score,attainable_dispatch_claimed=False))
    return scores,(sorted(slots)[len(slots)//2] if slots else 48),records


def route_paths(graph,peak,scores,limit=2):
    from bisect import bisect_left
    sites,initial,arcs,battery,_=graph
    stay={(a[0],a[1]):k for k,a in enumerate(arcs) if a[-1] is None}
    base={u:[stay[site,t] for t in range(96)] for u,site in initial.items()}
    ranked=[];outgoing={};returning={}
    for k,a in enumerate(arcs):
        if a[-1] is None:continue
        outgoing.setdefault(a[0],[]).append(k)
        returning.setdefault((a[0],a[2]),[]).append(k)
    for pair,indices in returning.items():indices.sort(key=lambda k:(arcs[k][1],arcs[k][3],arcs[k][-1].energy_kwh))
    depart_times={pair:[arcs[k][1] for k in indices] for pair,indices in returning.items()}
    for unit,origin in sorted(initial.items()):
        candidates=[k for k in outgoing.get(origin,[]) if arcs[k][3]<=peak]
        candidates.sort(key=lambda k:(-scores.get(arcs[k][2],0.),abs(arcs[k][3]-peak),arcs[k][-1].energy_kwh))
        # Bound heuristic enumeration only. The original complete path domain
        # remains present in every subsequent unrestricted model.
        for k in candidates[:128]:
            a=arcs[k];pair=(a[2],origin);indices=returning.get(pair,[])
            start=bisect_left(depart_times.get(pair,[]),max(a[3],peak+1))
            for back in indices[start:start+32]:
                b=arcs[back]
                if b[3]>=96:continue
                energy=float(a[-1].energy_kwh+b[-1].energy_kwh)
                charging_slots=a[1]+96-b[3]
                recharge=max(0.,battery.terminal-battery.initial+energy)
                if recharge>charging_slots*battery.dt_hours*battery.p_limit*battery.eta_charge:continue
                if energy>battery.maximum-battery.minimum:continue
                score=scores.get(a[2],0.)-scores.get(origin,0.)
                ranked.append((-score,energy,abs(a[3]-peak),b[1]-peak,unit,k,back))
    candidates=[];seen=set()
    for _,energy,_,_,unit,k,back in sorted(ranked):
        a,b=arcs[k],arcs[back];key=(unit,a[2])
        if key in seen:continue
        seen.add(key);paths={u:list(v) for u,v in base.items()}
        paths[unit]=([stay[a[0],t] for t in range(a[1])]+[k]+
            [stay[a[2],t] for t in range(a[3],b[1])]+[back]+
            [stay[b[2],t] for t in range(b[3],96)])
        candidates.append(dict(kind='CURRENT_DAY_LEGAL_RETURN_ROUTE',paths=paths,
            unit=unit,route_ids=[a[-1].route_id,b[-1].route_id],route_energy_kwh=energy,
            charging_return_slot=b[3],ETA_authority=[a[-1].authority_sha256,b[-1].authority_sha256],
            initial_SOC=battery.initial,terminal_SOC=battery.terminal))
        if len(candidates)>=limit:break
    return candidates


def values_for(case,paths,charge):
    chosen={u:set(p) for u,p in paths.items()};connected={}
    for unit,path in paths.items():
        site,time=case.graph[1][unit],0
        for k in path:
            a=case.graph[2][k]
            if a[0]!=site or a[1]!=time or not a[1]<a[3]<=96:raise ValueError('CANDIDATE_ORIGINAL_PATH_FLOW_OR_ETA')
            if a[-1] is None:connected[unit,a[0],a[1]]=1.
            else:a[-1].validate(96)
            site,time=a[2],a[3]
        if time!=96:raise ValueError('CANDIDATE_ORIGINAL_PATH_NOT_COMPLETE')
    ids=np.flatnonzero(case.d['types']!='C');values=[]
    for j in ids:
        name=str(case.d['names'][j])
        if name.startswith('arc['):
            unit,k=name[4:-1].split(',');value=float(int(k) in chosen[unit])
        elif name.startswith('node_activity['):
            unit,site,t=name[14:-1].split(',');value=connected.get((unit,site,int(t)),0.)
        elif name.startswith('charge_mode['):
            unit,t=name[12:-1].split(',');value=float(charge(unit,int(t)))
        else:raise ValueError('CANDIDATE_UNKNOWN_ORIGINAL_INTEGER_FAMILY:'+name)
        values.append(value)
    return ids,np.asarray(values,dtype=float)


def candidate_lp(case,budget,ids,values,name,description,progress):
    out=case.output/'INITIALIZATION_CANDIDATES'/name;out.mkdir(parents=True,exist_ok=True)
    model,identity=original._model(case,continuous=True)
    try:
        fix=sparse.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),ids)),shape=(len(ids),case.A.shape[1]))
        model.addMConstr(fix,model.getVars(),'=',values,name='INITIALIZATION_ONLY_FIXED_ORIGINAL_INTEGERS')
        model.Params.Method=1;model.update()
        atomic(out/'CANDIDATE.json',dict(description,model_identity=identity,
            integer_columns_fixed=len(ids),candidate_only=True,Adaptive_domain_changed=False))
        if progress:progress(dict(phase='M_DISCRETE_CANDIDATE_LP',candidate=name))
        budget.native_optimize(model,component='FEASIBILITY_LP',track='M_CANDIDATE',label=name,requested_seconds=60.)
        if not model.SolCount:
            atomic(out/'FULL_REPLAY.json',dict(PASS=False,Native_status=int(model.Status),
                reason='NO_CANDIDATE_LP_POINT',FULL_MILP_infeasibility_claimed=False))
            return None
        point=np.asarray(model.getAttr('X'),dtype=float);packet=out/'RAW_POINT.npz';np.savez_compressed(packet,point=point)
        try:
            with budget.cost('integer_physical_validation',name+'_FULL_replay'):
                receipt=original._strict_ub(case,packet,{})
            atomic(out/'FULL_REPLAY.json',dict(receipt,case_sha=case.case_sha));return point,receipt,out/'FULL_REPLAY.json'
        except ValueError as exc:
            atomic(out/'FULL_REPLAY.json',dict(PASS=False,reason=str(exc),
                original_row_replay=original.validate_candidate(case,point),invalid_point_not_admitted=True))
            return None
    finally:model.dispose()


def initialize(case,budget,progress):
    from .stationary_dispatch import validated_start
    start=validated_start(case,budget,progress)
    if start is not None:
        return admit(case,start,read(case.output/'STATIONARY_DISPATCH_REPLAY.json'),
            case.output/'STATIONARY_DISPATCH_REPLAY.json',budget,'STATIONARY_DISPATCH')
    rows=analyze(case);scores,peak,sens=sensitivity(case,rows)
    atomic(case.output/'INITIALIZATION_VOLTAGE_SENSITIVITY.json',dict(case_sha=case.case_sha,
        scores=scores,peak_slot=peak,original_P_Q_sensitivities=sens,ranking_only=True))
    sites,initial,arcs,_,_=case.graph
    stay={(a[0],a[1]):k for k,a in enumerate(arcs) if a[-1] is None}
    stationary={u:[stay[site,t] for t in range(96)] for u,site in initial.items()}
    candidates=[(dict(kind='STATIONARY_CHARGE_BEFORE_PEAK',paths=stationary),lambda u,t:t<peak),
        (dict(kind='STATIONARY_CHARGE_AFTER_PEAK',paths=stationary),lambda u,t:t>=peak)]
    for description in route_paths(case.graph,peak,scores):
        candidates.append((description,lambda u,t,d=description:t<16 or t>=d['charging_return_slot']))
    for i,(description,charge) in enumerate(candidates):
        # Preserve room for the 900s last-resort seed plus independent LB stage.
        if budget.remaining()<1260:break
        ids,values=values_for(case,description['paths'],charge)
        found=candidate_lp(case,budget,ids,values,f'{i:02d}',description,progress)
        if found is not None:
            point,receipt,path=found;return admit(case,point,receipt,path,budget,description['kind'])
    atomic(case.output/'INITIALIZATION_CANDIDATES_EXHAUSTED.json',dict(PASS=False,
        reason='NO_FULL_VERIFIED_CANDIDATE_WITHIN_EXISTING_DATE_BUDGET',
        FULL_MILP_infeasibility_claimed=False,fallback='UNRESTRICTED_ORIGINAL_MILP_SEED',
        cumulative_Native_Runtime=budget.used(),remaining_native_seconds=budget.remaining()))
    return None


def admit(case,point,receipt,path,budget,kind):
    from v42_m1_research.check_ub import vector_sha
    from .common import sha
    replay=receipt.get('original_matrix_and_96_slot_physical_replay',{})
    if (receipt.get('PASS') is not True or receipt.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
            or replay.get('PASS') is not True or replay.get('case_sha')!=case.case_sha
            or vector_sha(point)!=receipt.get('point_vector_sha256')
            or sha(receipt['point_path'])!=receipt.get('point_file_sha256')):
        raise ValueError('DIRECT_DISPATCH_REQUIRES_ORIGINAL_FULL_STRICT_REPLAY')
    calls=getattr(budget,'calls',[])
    atomic(case.output/'SEED_BYPASS_CERTIFIED_DISPATCH.json',dict(PASS=True,UTC=now(),
        event='SEED_BYPASS_CERTIFIED_DISPATCH',case_sha=case.case_sha,source=kind,
        original_FULL_replay=record(path),point_path=receipt['point_path'],
        point_file_sha256=receipt['point_file_sha256'],point_vector_sha256=receipt['point_vector_sha256'],
        exact_Global_UB=receipt['exact_Global_UB'],Global_UB=receipt['Global_UB'],
        M_SEED_optimize_calls=0,unnecessary_seed_MILP_omitted=True,
        LP_initialization_Native_Runtime=sum(r['Native_Runtime'] for r in calls if r.get('track') in ('M_START','M_CANDIDATE')),
        first_FULL_verified_wall_seconds=getattr(budget,'wall',lambda:None)(),
        seed_Runtime_saved_not_assumed=900.6959998607635 if case.bundle['day']=='2025-05-01' else 'NOT_MEASURED_SAME_DAY_V17_SEED',
        cumulative_Native_Runtime=budget.used(),remaining_native_seconds=budget.remaining(),
        historical_date_point_reused=False,original_Adaptive_and_full_decision_space_unchanged=True))
    return point
