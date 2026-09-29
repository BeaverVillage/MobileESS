"""Causal 30-minute events, site-only arrival interface and fixed-discrete P/Q LP."""
from dataclasses import dataclass
from math import isfinite
import gurobipy as gp
from .contracts import require,digest,Deadline
from .mess import pcs_rows
from .solver import optimize

PAPER_POLICIES=('M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE','M2_FIXED30_MOBILE',
    'M3_EVENT30_NO_LOCAL_REPAIR_MOBILE','M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION')
OPTIMIZATION_STAGES=('A1','M1','A2','M2')


@dataclass(frozen=True)
class KernelAnchor:
    service_sha:str
    reference_sha:str
    pq_sha:str
    grid_sha:str

    def require_same(self,current):
        require(self==current and all(len(x)==64 for x in vars(self).values()),'STALE_RESPONSE_KERNEL_ANCHOR')


def event_due(slot,policy,observed_deviation,*,threshold):
    require(policy in PAPER_POLICIES and type(slot) is int and slot>=0 and isfinite(threshold) and threshold>=0,'EVENT_CONTRACT')
    if slot%2:return False
    return policy=='M2_FIXED30_MOBILE' or observed_deviation>threshold


def unknown_arrival(job,event_time,provider,anchor,current_anchor,site_policy,physical_state):
    job.validate(event_time);estimate=provider.predict_total(job,event_time)
    try:estimate.require_production(event_time)
    except ValueError:
        return dict(status='RUNTIME_PROVIDER_UNPROMOTED',job_uid=job.uid,observed=True,
            capability_masks=None,action=None,global_MILP_calls=0,physical_workload_unresolved=True)
    anchor.require_same(current_anchor)
    # Policy must return a site-only reservation; explicit post-validation blocks
    # accidental temporal/migration activation. No solver dependency on this path.
    result=site_policy(job,estimate,physical_state)
    require(result.get('temporal_shift',0)==0 and result.get('migration_count',0)==0,'UNKNOWN_CAPABILITY_AUTHORITY')
    require(result.get('full_service_preserved') is True and result.get('capacity_feasible') is True,'UNKNOWN_RESOURCE_CERTIFICATE')
    return dict(status='SITE_POLICY_PROPOSAL',job_uid=job.uid,action=result,global_MILP_calls=0)


def require_fresh_ac(receipt,schedule_sha,grid_sha):
    require(receipt.get('engine')=='OpenDSS' and receipt.get('fresh_run') is True and receipt.get('synthetic') is False,'FRESH_OPENDSS_REQUIRED')
    require(receipt.get('schedule_sha')==schedule_sha and receipt.get('grid_sha')==grid_sha,'FRESH_AC_IDENTITY')
    require(receipt.get('converged') is True and all(receipt.get(k)==0 for k in
        ('voltage_violations','line_current_violations','transformer_current_violations','transformer_kVA_violations')),'FRESH_AC_PHYSICS')
    return True


def repair_pq(plan,battery,grid_builder,*,max_delta_kw,max_delta_kvar,seconds=10.,policy_id=PAPER_POLICIES[0]):
    """Continuous LP on an explicitly authorized short suffix of frozen plan.

    Plan includes fixed connection, charge mode, mobility energy, initial/terminal
    energy. Current rows may use current measurements; future rows only frozen
    forecasts. Future compensating P is allowed only through supplied delta
    reserves. The caller cannot execute until Fresh AC passes.
    """
    require(0<seconds<=10 and max_delta_kw>=0 and max_delta_kvar>=0,'LOCAL_REPAIR_BUDGET')
    require(policy_id in PAPER_POLICIES and policy_id!=PAPER_POLICIES[2],'POLICY_LOCAL_REPAIR_DISABLED')
    deadline=Deadline('M2',seconds)
    battery.validate();require(plan['unit']=='kW_kvar_kWh' and plan['causal_inputs_verified'],'ACTUAL_UNITS_CAUSALITY')
    n=len(plan['P']);require(0<n<=16 and all(len(plan[k])==n for k in ('Q','connected','charge_mode','mobility_kwh')),'LOCAL_SUFFIX_AXIS')
    require(all(isfinite(v) for k in ('P','Q','mobility_kwh') for v in plan[k])
        and all(v>=0 for v in plan['mobility_kwh']),'FROZEN_PLAN_PHYSICAL_VALUES')
    require(all(isfinite(plan[k]) and battery.minimum<=plan[k]<=battery.maximum
        for k in ('initial_kwh','terminal_kwh')),'FROZEN_PLAN_SOC_AUTHORITY')
    model=gp.Model('V42_LOCAL_PQ_LP');model.Params.OutputFlag=0;E={};p={};q={};p_dev=[];q_dev=[]
    try:
        for t in range(n+1):E[t]=model.addVar(lb=battery.minimum,ub=battery.maximum,name=f'SOC[{t}]')
        model.addConstr(E[0]==plan['initial_kwh']);model.addConstr(E[n]==plan['terminal_kwh'])
        for t in range(n):
            deadline.check()
            require(plan['connected'][t] in (0,1) and plan['charge_mode'][t] in (0,1),'FROZEN_DISCRETE_STATE')
            connected=int(plan['connected'][t]);charge=int(plan['charge_mode'][t])
            lo,hi=(-battery.p_limit,0) if charge else (0,battery.p_limit)
            lo=max(lo*connected,plan['P'][t]-max_delta_kw);hi=min(hi*connected,plan['P'][t]+max_delta_kw)
            p[t]=model.addVar(lb=lo,ub=hi,name=f'P[{t}]')
            q[t]=model.addVar(lb=max(-battery.pcs_kva*connected,plan['Q'][t]-max_delta_kvar),
                ub=min(battery.pcs_kva*connected,plan['Q'][t]+max_delta_kvar),name=f'Q[{t}]')
            pcs_rows(model,p[t],q[t],connected,battery.pcs_kva)
            delta=-battery.dt_hours*(battery.eta_charge*p[t] if charge else p[t]/battery.eta_discharge)
            model.addConstr(E[t+1]==E[t]+delta-plan['mobility_kwh'][t],name='repair_energy')
            for expr,base,collection in ((p[t],plan['P'][t],p_dev),(q[t],plan['Q'][t],q_dev)):
                d=model.addVar(lb=0);model.addConstr(d>=expr-base);model.addConstr(d>=base-expr);collection.append(d)
        rho=grid_builder(model,p,q)
        # Q-first preference: at locked electrical quality use as little P
        # intervention as possible, then minimize Q intervention. No weights.
        result,receipt=optimize(model,[('rho',rho),('P_change',gp.quicksum(p_dev)),('Q_change',gp.quicksum(q_dev))],deadline)
        require(model.NumIntVars==0,'ACTUAL_DISCRETE_OPTIMIZATION_FORBIDDEN')
        if result:result.update(status='PROPOSAL_REQUIRES_FRESH_AC',fixed_discrete_sha=digest({k:plan[k] for k in ('connected','charge_mode','mobility_kwh')}))
        return result,receipt
    finally:model.dispose()
