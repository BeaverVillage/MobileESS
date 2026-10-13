"""Common P1 A engine using the original exact local and integer formulations.

The new QoS domain is materialized completely. No old-domain LB is transferred.
This full-domain path uses the existing compressed native builder; it does not
claim that historical lazy-pricing certificates apply to the changed domain.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import hashlib
import json
import math
import numpy as np


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def scalar(value):
    return float(value.X if hasattr(value,'X') else value.getValue() if hasattr(value,'getValue') else value)


@dataclass
class PlanningGridContext:
    coefficients: tuple
    power: dict
    idle_kw: float
    swing_kw: float
    timing_lower: tuple
    timing_upper: tuple
    kernel: tuple
    authority: object
    fixed_mess: dict | None = None
    planning_arrays: dict | None = None
    alias_controls: bool = True

    def bind(self, model, bundle, known, risk, *, stage):
        import gurobipy as gp
        from v42_final.workload import ForecastBook
        from v42_final.reserve import bind_headroom
        from v42_temporal.service import bind_forecast
        from v42_native.grid import add_grid
        from datetime import datetime
        issue=datetime.fromisoformat(bundle['issue_time']).timestamp()
        midnight=datetime.fromisoformat(bundle['day']+'T00:00:00+10:00').timestamp()
        book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),midnight)
        timing=bind_forecast(model,book,issue,self.kernel,self.timing_lower,self.timing_upper)
        caps=bundle['capacities']; anonymous={}; reserve={}
        for t in range(96):
            for site in caps:
                anonymous[site,t+24]=model.addVar(lb=0,name=f'anonymous_GPU[{site},{t}]')
                reserve[site,t+24]=model.addVar(lb=0,name=f'arrival_target_GPU[{site},{t}]')
            model.addConstr(gp.quicksum(anonymous[s,t+24] for s in caps)==timing['nominal']['gpu'][t],name='CC4_site_nominal_partition')
            model.addConstr(gp.quicksum(reserve[s,t+24] for s in caps)==timing['reserve']['gpu'][t],name='CC4_site_reserve_partition')
        headroom=bind_headroom(model,known,anonymous,reserve,risk,caps,range(24,120))
        fixed=self.fixed_mess or {}; controls=[]
        for t,c in enumerate(self.coefficients):
            row=[]
            for name in c.control_names:
                site=name.split('[',1)[1][:-1]
                if name.startswith('aidc_load_kw'):
                    a=self.power[site,t]
                    it=self.idle_kw*caps[site]+self.swing_kw*(known[site,t+24]+anonymous[site,t+24])
                    expression=a.slope*it+a.intercept_kw
                    if self.alias_controls:
                        pcc=model.addVar(lb=-gp.GRB.INFINITY,name=f'PCC_affine_alias[{site},{t}]')
                        model.addConstr(pcc==expression,name=f'PCC_affine_identity[{site},{t}]')
                        row.append(pcc)
                    else:row.append(expression)
                elif name.startswith('mess_p_kw'):
                    row.append(float(fixed.get('P_by_site',{}).get(site,[0.]*96)[t]))
                elif name.startswith('mess_q_kvar') or name.startswith('mess_q_kw'):
                    row.append(float(fixed.get('Q_by_site',{}).get(site,[0.]*96)[t]))
                else:
                    raise ValueError('UNKNOWN_SIGNED_GRID_CONTROL:'+name)
            controls.append(row)
        rho=add_grid(model,self.coefficients,controls,replace(self.authority,stage=stage,require_all_transformer_currents=True))
        self.planning_arrays=dict(anonymous=anonymous,reserve=reserve,headroom=headroom,known=known,risk=risk)
        return [('rho',rho),('reserve_shortfall',headroom['CC4_shortfall']+headroom['runtime_shortfall'])],timing,controls


@dataclass
class ACase:
    data: tuple
    grid: PlanningGridContext
    output: Path
    case_sha: str
    stage: str
    arm: str
    window_slots: dict
    qos_receipts: dict
    call_cap: float = 5400.
    progress: object = None


def authorized_data(case):
    """Rebuild exact classes/graphs with policy, service and contract identity."""
    from v42_a_stage_domain_v2.domain import physical_domain
    from v42_a_stage_phase1.producer import complete_graph
    from v42_boundary.generator import Generator
    bundle,jobs,bounds,resources,raw,_,_,prep=case.data
    changed={}; domains={}; graphs={}; classes=defaultdict(list)
    shared_generator=Generator(resources,max((b.latest_completion for b in bounds.values()),default=resources.control_end))
    for uid,job in jobs.items():
        receipt=case.qos_receipts[uid]
        doc=receipt.to_dict() if hasattr(receipt,'to_dict') else dict(receipt)
        # RUNNING's native start is the current remaining-service boundary,
        # not an instruction to start its historical episode again. A past
        # s0/empty new-start window cannot remove observed running compute.
        starts=(job.reference_start,) if job.state=='RUNNING' else tuple(case.window_slots[uid])
        policy=doc.get('policy_id',doc.get('policy_version','EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1'))
        budget=float(doc.get('budget_seconds',doc.get('B_seconds',0.)))
        changed[uid]=replace(job,qos_policy_id=policy,qos_receipt_sha=digest(doc),
            qos_allowed_starts=starts,qos_budget_seconds=budget,
            is_observed=True,batch_eligible=doc.get('batch_eligible',False))
        if not starts:
            raise ValueError('EMPTY_AUTHORIZED_WINDOW:'+uid)
        newbound=replace(bounds[uid],allowed_starts=starts)
        domain=physical_domain(changed[uid],newbound,resources,gen=shared_generator)
        if not domain.stays and not domain.blocks:
            raise ValueError('NO_PHYSICAL_AUTHORIZED_OPTION:'+uid)
        domains[uid]=domain
        graphs[uid]=complete_graph(changed[uid],domain,uid in prep.get('preserve_singleton_mixed_flow',()))
        signature=dict(job={k:v for k,v in asdict(changed[uid]).items() if k not in ('uid','qos_receipt_sha')},
            boundary=asdict(newbound),hard_contract=doc.get('hard_contract',{}),
            resources=domain.cache.identity,runtime={k:raw[uid].get(k) for k in
                ('duration_authority','risk_nominal_completion_issue_slot','reference_end')})
        classes[digest(signature)].append(uid)
    newbounds={uid:replace(bounds[uid],allowed_starts=changed[uid].qos_allowed_starts) for uid in jobs}
    metadata=dict(prep,classes=dict(classes),domain_authority='EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1',
        full_migration_domain_active=True,old_domain_certificate_reused=False,
        physical_domain_hash=digest({u:d.sha for u,d in sorted(domains.items())}))
    return (bundle,changed,newbounds,resources,raw,graphs,graphs,metadata),domains


def optimize_aidc(case, fixed_mess, qos_policy, budget):
    """B1/A1 and B3/A1/A2 call this same core, with explicit fixed anchors."""
    from v42_root.native import build,reconstruct
    from v42_native.voltage import Stage
    from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
    from v42_b3_joint.numerical_policy import apply_native_precision
    from v42_job_capability import Option,validate
    import gurobipy as gp
    from .a_seed import project_reference_seed,full_replay,value_at
    from time import perf_counter
    if case.stage not in ('A1','A2') or case.arm not in ('B1','B3'):
        raise ValueError('COMMON_A_ARM_STAGE_REQUIRED')
    if case.stage=='A2' and (not fixed_mess or not all(k in fixed_mess for k in ('P_by_site','Q_by_site','routes','SOC','Mode','plan_sha'))):
        raise ValueError('A2_COMPLETE_FIXED_MESS_REQUIRED')
    if fixed_mess:
        if digest({k:v for k,v in fixed_mess.items() if k!='plan_sha'})!=fixed_mess['plan_sha']:
            raise ValueError('FIXED_MESS_PLAN_SHA_DRIFT')
    case.output=Path(case.output);case.output.mkdir(parents=True,exist_ok=False)
    case.grid.fixed_mess=fixed_mess
    data,domains=authorized_data(case)
    class Context:
        folder=case.output
        def check(self):
            if budget.remaining()<=0:raise RuntimeError('INTEGRATION_SOLVE_BUDGET_EXHAUSTED')
        def progress(self,value):
            if case.progress:case.progress(dict(stage=case.stage,**value))
    stage=Stage.A2 if case.stage=='A2' else Stage.A1
    build_begin=perf_counter()
    model,units,levels,controls,bindings=build(Context(),data,'F2-CRA',grid_context=case.grid,stage=stage)
    build_wall_seconds=perf_counter()-build_begin
    try:
        policy=solver_policy(gp);apply_policy(model,policy,gp)
        numerical=apply_native_precision(model,day=data[0]['day'],stage=case.stage,component='ORIGINAL_P1')
        model.setObjective(dict(levels)['rho'],gp.GRB.MINIMIZE)
        model.update()
        model.Params.LogFile=str(case.output/'NATIVE_SOLVER.log');model.Params.OutputFlag=1
        before=budget.remaining()
        seed,seed_plans,seed_receipt=project_reference_seed(model,units,data,budget,case.output/'REFERENCE_SEED',
            stage=case.stage,seconds=min(30.,max(.001,case.call_cap*.15)))
        charged=before-budget.remaining()
        remaining_cap=max(.001,case.call_cap-charged)
        call=budget.solve(model,label=case.stage+'_ORIGINAL_P1',cap=remaining_cap)
        result=dict(stage=case.stage,arm=case.arm,case_sha=case.case_sha,engine='v42_integration.a_engine.optimize_aidc',
            status=int(model.Status),execution_completion=True,P2_calls=0,
            Native_call=call,numerical_policy=numerical,old_LB_reused=False,global_gap_certified=False,
            full_domain=data[7]['physical_domain_hash'],domain_scope='NEW_QOS_COMPLETE_NATIVE_DOMAIN',
            lazy_pricing_calls=0,compression='ORIGINAL_F2_CRA',FULL_feasible=False,
            current_case_seed=seed_receipt,PCC_alias_exact_identity=case.grid.alias_controls,
            build_wall_seconds=build_wall_seconds,
            matrix=dict(rows=model.NumConstrs,columns=model.NumVars,nonzeros=model.NumNZs))
        x=seed;selected=seed_plans if seed is not None else None
        origin='CURRENT_CASE_REFERENCE_FEASIBILITY_SEED' if seed is not None else None
        if model.SolCount:
            candidate=np.asarray(model.getAttr('X'),float);replay=full_replay(model,candidate)
            result['main_point_replay']=replay
            rho_variable=dict(levels)['rho']
            if replay['PASS'] and (x is None or value_at(rho_variable,candidate)<=value_at(rho_variable,x)+1e-9):
                x=candidate;selected=reconstruct(units,data);origin='CURRENT_FULL_DOMAIN_NATIVE'
        if x is not None:
            replay=full_replay(model,x)
            if not replay['PASS']:raise ValueError('ORIGINAL_A_ROW_REPLAY_FAIL')
            for uid,record in selected.items():
                record=dict(record);record['segments']=tuple(tuple(r) for r in record['segments']);record['wan']=tuple(tuple(r) for r in record.get('wan',()))
                validate(data[1][uid],Option(**record),data[2][uid],data[3])
            arrays=case.grid.planning_arrays
            envelope=[dict(slot_start=t*900.,slot_end=(t+1)*900.,site=s,
                gpu_capacity=max(0.,value_at(arrays['anonymous'][s,t+24],x)),
                source_variable=f'anonymous_GPU[{s},{t}]',carryout_end=86400.) for t in range(96) for s in data[3].capacities]
            values=[[value_at(v,x) for v in row] for row in controls]
            p={s:[values[t][c.control_names.index('aidc_load_kw['+s+']')] for t,c in enumerate(case.grid.coefficients)] for s in data[3].capacities}
            result.update(FULL_feasible=True,selected_jobs=selected,controls=values,
                AIDC_P_by_site=p,AIDC_Q_by_site={s:(np.asarray(a)*np.tan(np.arccos(.95))).tolist() for s,a in p.items()},
                anonymous_resource_envelope=envelope,
                CC4_service={str(k):value_at(v,x) for k,v in bindings['timing']['nominal']['x'].items()},
                CC4_carryout={str(k):value_at(v,x) for k,v in bindings['timing']['nominal']['carryout'].items()},
                CC4_reserve_service={str(k):value_at(v,x) for k,v in bindings['timing']['reserve']['x'].items()},
                CC4_reserve_carryout={str(k):value_at(v,x) for k,v in bindings['timing']['reserve']['carryout'].items()},
                nominal_site_GPU={s:[value_at(arrays['anonymous'][s,t+24],x) for t in range(96)] for s in data[3].capacities},
                reserve_site_GPU={s:[value_at(arrays['reserve'][s,t+24],x) for t in range(96)] for s in data[3].capacities},
                known_site_GPU={s:[value_at(arrays['known'][s,t+24],x) for t in range(96)] for s in data[3].capacities},
                reserve_site_GPU_meaning='CC4_ARRIVAL_TARGET_DISTRIBUTION_NOT_CAPACITY_BACKED_ACHIEVED_RESERVE',
                achieved_CC4_reserve_site_GPU={s:[value_at(arrays['headroom']['CC4_achieved'][s,t+24],x) for t in range(96)] for s in data[3].capacities},
                achieved_runtime_reserve_site_GPU={s:[value_at(arrays['headroom']['runtime_achieved'][s,t+24],x) for t in range(96)] for s in data[3].capacities},
                CC4_reserve_shortfall_GPU_slots=value_at(arrays['headroom']['CC4_shortfall'],x),
                runtime_reserve_shortfall_GPU_slots=value_at(arrays['headroom']['runtime_shortfall'],x),
                resource_sites=list(data[3].capacities),
                rho=value_at(dict(levels)['rho'],x),local_bound=float(model.ObjBound),
                global_gap_certified=model.Status==gp.GRB.OPTIMAL and origin=='CURRENT_FULL_DOMAIN_NATIVE',
                global_gap_scope='FIXED_MESS_NEW_QOS_A_ONLY',FULL_max_residual=replay['FULL_max_residual'],
                incumbent_source=origin,FULL_point_replay=replay)
            result['aidc_anchor']=digest({k:result[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')})
            result['resource_distribution_sha']=digest({k:result[k] for k in ('nominal_site_GPU','reserve_site_GPU','known_site_GPU','resource_sites','CC4_reserve_service','CC4_reserve_carryout')})
            np.savez_compressed(case.output/'POINT.npz',point=x)
        (case.output/'A_RESULT.json').write_text(json.dumps(result,indent=2,default=str,allow_nan=False),encoding='utf8')
        return result
    finally:
        model.dispose()
