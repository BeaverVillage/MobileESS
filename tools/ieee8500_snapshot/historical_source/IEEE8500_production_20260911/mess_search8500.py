"""Joint full route-domain MESS search and dedicated fixed-route P/Q recourse."""
import time,math,copy
from pathlib import Path
from dataclasses import replace
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import ac8500 as ac
from non_electrical_inputs import service_alias
from grid8500 import GridRows,controls,TAN
from run_support import Metrics,Oracle,atomic
from dayahead.v33m.mess_mobility_milp import add_mess_mobility_block
from dayahead.v33m.mess_trajectory import MessTrajectory,MessTrajectorySlot,extract_mess_trajectory
from dayahead.v40h.recourse import validate_physics
from dayahead.v40a.invariants import route_sha

def zero_trajectory(ctx):
    a=ctx.electrical
    return MessTrajectory(tuple(MessTrajectorySlot(mid,t,'CONNECTED',site,None,None,(),None,0.,0.,0.,0.,0,None,0.,0.,0.,0.,a.initial_energy_kwh,a.initial_energy_kwh/a.capacity_kwh) for mid,site in sorted(ctx.initial.items()) for t in range(96)))
def arrays(trajectory):
    p=np.zeros((96,24));q=p.copy()
    for r in trajectory.slots:
        if r.service_id is not None:
            j=ac.SERVICES.index(service_alias(r.service_id));p[r.slot,j]+=r.p_kw;q[r.slot,j]+=r.q_kvar
    return p,q
def route_audit(ctx,trajectory):
    check=validate_physics(trajectory,ctx.electrical);assert check['status']=='PASS',check
    assert len(trajectory.slots)==384
    for mid,initial in ctx.initial.items():
        rs=sorted([r for r in trajectory.slots if r.mess_id==mid],key=lambda r:r.slot);assert [r.slot for r in rs]==list(range(96));location=initial;t=0
        while t<96:
            r=rs[t]
            if r.mode=='CONNECTED':assert r.service_id==location;t+=1;continue
            assert r.departure_slot==t and r.origin_service_id==location
            native=ctx.route_table[t,location,r.destination_service_id];ready=t+native.connection_ready_slots_15min;assert ready<=96
            for s in range(t,ready):
                rr=rs[s];assert rr.route_link_ids==native.route_link_ids and rr.destination_service_id==native.destination_service_id and rr.origin_service_id==location and rr.connection_ready_slot==ready and rr.departure_slot==t and rr.mode==('TRANSIT' if s<t+native.travel_slots_15min else 'CONNECTION_DELAY')
                for k in ['route_q10_eta_sec','route_q50_eta_sec','route_q90_eta_sec','route_safe_eta_sec','energy_nominal_kwh','energy_safe_kwh']:assert abs(getattr(rr,k)-getattr(native,k))<1e-6
            location=native.destination_service_id;t=ready
    return dict(status='PASS',physics=check,route_SHA=route_sha(trajectory.slots),traffic_route_inputs_unchanged=True,electrical_service_count=24)
def configured(folder,label):
    m=gp.Model(label);m.Params.OutputFlag=0;m.Params.LogFile=str((folder/'SOLVER.log').resolve());m.Params.Threads=4;m.Params.Seed=20260911;m.Params.MIPGap=.001;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.OptimalityTol=1e-9;m.Params.MIPFocus=1;m.Params.Method=1;m.Params.NodefileStart=.5;m.Params.NodefileDir=str(folder.resolve());return m
def set_start(block,trajectory):
    by={(r.mess_id,r.slot):r for r in trajectory.slots};selected={(r.mess_id,r.departure_slot,r.origin_service_id,r.destination_service_id) for r in trajectory.slots if r.departure_slot==r.slot and r.mode=='TRANSIT'}
    for key,var in block.move.items():var.Start=float(key in selected)
    for (mid,t,s),var in block.stay.items():var.Start=float(by[mid,t].mode=='CONNECTED' and by[mid,t].service_id==s)
    for (mid,t,s),var in block.occupancy.items():
        if t==0:val=s==block.inputs.initial_service_by_mess[mid]
        elif by[mid,t-1].mode=='CONNECTED':val=s==by[mid,t-1].service_id
        else:val=by[mid,t-1].connection_ready_slot==t and by[mid,t-1].destination_service_id==s
        var.Start=float(val)
    for (mid,t),var in block.discharge_mode.items():var.Start=float(by[mid,t].p_kw>0)
    for (mid,t,s),var in block.p_discharge.items():var.Start=max(by[mid,t].p_kw,0) if by[mid,t].service_id==s else 0
    for (mid,t,s),var in block.p_charge.items():var.Start=max(-by[mid,t].p_kw,0) if by[mid,t].service_id==s else 0
    for (mid,t,s),var in block.q.items():var.Start=by[mid,t].q_kvar if by[mid,t].service_id==s else 0
    for (mid,t),var in block.energy.items():var.Start=by[mid,t].battery_energy_kwh if t<96 else block.inputs.electrical_authority.terminal_energy_kwh

def pq_block(model,ctx,seed):
    a=ctx.electrical;by={(r.mess_id,r.slot):r for r in seed.slots};p={};q={};energy={};pp={(s,t):gp.LinExpr() for s in ctx.route_table.service_ids for t in range(96)};qq={k:gp.LinExpr() for k in pp}
    for mid in sorted(ctx.initial):
        for t in range(97):energy[mid,t]=model.addVar(lb=a.energy_min_kwh,ub=a.energy_max_kwh,name=f'E[{mid},{t}]');energy[mid,t].Start=by[mid,t].battery_energy_kwh if t<96 else a.terminal_energy_kwh
        model.addConstr(energy[mid,0]==a.initial_energy_kwh);model.addConstr(energy[mid,96]==a.terminal_energy_kwh)
        for t in range(96):
            r=by[mid,t];connected=int(r.mode=='CONNECTED');direction=model.addVar(vtype=GRB.BINARY,ub=connected);dis=model.addVar(lb=0,ub=a.active_power_limit_kw*connected);ch=model.addVar(lb=0,ub=a.active_power_limit_kw*connected);q[mid,t]=model.addVar(lb=-a.pcs_kva*connected,ub=a.pcs_kva*connected);p[mid,t]=dis-ch
            direction.Start=float(r.p_kw>0);dis.Start=max(r.p_kw,0);ch.Start=max(-r.p_kw,0);q[mid,t].Start=r.q_kvar
            model.addConstr(dis<=a.active_power_limit_kw*direction);model.addConstr(ch<=a.active_power_limit_kw*(1-direction));model.addConstr(dis+ch<=a.active_power_limit_kw*connected)
            for f in range(a.pcs_polygon_faces):
                angle=2*math.pi*f/a.pcs_polygon_faces;model.addConstr(math.cos(angle)*p[mid,t]+math.sin(angle)*q[mid,t]<=a.pcs_kva*math.cos(math.pi/a.pcs_polygon_faces)*connected)
            travel=r.energy_safe_kwh if r.departure_slot==t and r.mode=='TRANSIT' else 0.;model.addConstr(energy[mid,t]>=a.energy_min_kwh+travel);model.addConstr(energy[mid,t+1]==energy[mid,t]+a.charge_efficiency*.25*ch-.25*dis/a.discharge_efficiency-travel)
            if connected:pp[r.service_id,t]+=p[mid,t];qq[r.service_id,t]+=q[mid,t]
    def extract():return MessTrajectory(tuple(replace(r,p_kw=float(p[r.mess_id,r.slot].getValue()),q_kvar=float(q[r.mess_id,r.slot].X),battery_energy_kwh=float(energy[r.mess_id,r.slot].X),soc_fraction=float(energy[r.mess_id,r.slot].X)/a.capacity_kwh) for r in seed.slots))
    return pp,qq,extract

def run(ctx,grid,pcc,folder,seed=None,fixed_route=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);start=time.perf_counter();metrics=Metrics();oracle=Oracle(folder/'AC',metrics);seed=zero_trajectory(ctx) if seed is None else seed;route_audit(ctx,seed);mp,mq=arrays(seed);valid=oracle.validate(pcc,mp,mq,'seed');assert valid['feasible'];best=seed;bestvalid=valid;solves=[];model=configured(folder,'IEEE8500_MF_FIXED_ROUTE_PQ' if fixed_route else 'IEEE8500_FULL_MESS_ROUTE_DOMAIN');route_count=0
    try:
        generation=time.perf_counter()
        if fixed_route:pp,qq,extract=pq_block(model,ctx,seed)
        else:
            block=add_mess_mobility_block(model,ctx.mobility_inputs);set_start(block,seed);pp,qq=block.p_injection_by_service_slot,block.q_injection_by_service_slot;extract=lambda:extract_mess_trajectory(block);route_count=len(block.move)
        metrics.candidate_seconds+=time.perf_counter()-generation;metrics.candidate_evaluations+=route_count
        alias={service_alias(s):s for s in ctx.route_table.service_ids};x=[[v for p in pcc[t] for v in (float(p),float(p*TAN))]+[v for s in ac.SERVICES for v in (pp[alias[s],t],qq[alias[s],t])] for t in range(96)]
        rho=model.addVar(lb=0,ub=1.,name='rho_max');xseed=controls(pcc,mp,mq);rho.Start=grid.report(xseed)['P1'];rows=GridRows(grid,model,x,rho,xseed,4);model.setObjective(rho);model.update()
        atomic(folder/'FULL_DOMAIN_MODEL.json',dict(route_variables=route_count,route_records=len(ctx.route_table.records),fleet=len(ctx.initial),service_count=24,all_feasible_horizon_arcs_present=not fixed_route,fixed_route=fixed_route,variables=model.NumVars,constraints=model.NumConstrs,grid_constraint_generation='All-axis separation; no physical axis removed',seed_AC=valid))
        for attempt in range(8):
            model.Params.TimeLimit=600. if attempt==0 and not fixed_route else 180.;model.Params.WorkLimit=[60.,180.,300.][min(attempt,2)];st=time.perf_counter();model.optimize();duration=time.perf_counter()-st;metrics.solve.append(duration);metrics.sample();info=dict(attempt=attempt,status=int(model.Status),solutions=int(model.SolCount),seconds=duration,work=float(model.Work),surrogate_bound=float(model.ObjBound) if model.SolCount else None);solves.append(info)
            if not model.SolCount:break
            candidate=extract()
            try:audit=route_audit(ctx,candidate)
            except (AssertionError,ValueError) as ex:info['physics_rejection']=str(ex);continue
            cp,cq=arrays(candidate);cx=controls(pcc,cp,cq);added,report=rows.separate(cx,float(rho.X));info.update(added_grid_rows=added,surrogate=report);metrics.candidate_evaluations+=1
            if added:continue
            exact=oracle.validate(pcc,cp,cq,f'proposal_{attempt:02d}');info['AC']=exact
            if exact['feasible'] and exact['P1']<bestvalid['P1']-1e-8:
                best,bestvalid=candidate,exact;metrics.incumbent_updates+=1;atomic(folder/'accepted'/f'{attempt:02d}.json',dict(trajectory=[r.to_dict() for r in best.slots],AC=exact,audit=audit))
            if exact['feasible']:break
            # Surrogate-only defect correction at this exact AC candidate. No physical parameter changes.
            with np.load(Path(exact['evidence'])/'AC_PHASE_ARRAYS.npz') as zz:
                predictions=grid.values(cx)
                for t in range(96):
                    for k,key in enumerate(ac.KEYS):grid.anchor[t][k]=grid.anchor[t][k]+(zz[key][t]-np.abs(predictions[t][k]))*np.exp(1j*np.angle(predictions[t][k]))
            # Rebuild all surrogate rows after the recorded numerical correction.
            model.remove([c for c in model.getConstrs() if c.ConstrName.startswith(('vmin_','upper_'))]);model.update();rows=GridRows(grid,model,x,rho,cx,4);info['surrogate_AC_defect_correction']=True
        bp,bq=arrays(best)
        if fixed_route:assert route_sha(best.slots)==route_sha(seed.slots)
        final_started=time.perf_counter();final=ac.replay(folder/'FINAL_INDEPENDENT_AC',aidc_p=pcc,aidc_q=pcc*TAN,mess_p=bp,mess_q=bq,independent=True);metrics.ac.append(time.perf_counter()-final_started);assert final['feasible'];assert abs(final['max_phase_line_loading_pu']-bestvalid['P1'])<1e-10
        result=dict(status='PASS',trajectory=[r.to_dict() for r in best.slots],AC=final,physics=route_audit(ctx,best),metrics=metrics.summary(),solver_calls=solves,wall_seconds=time.perf_counter()-start,full_route_domain=not fixed_route,fixed_route=fixed_route,route_candidate_count=route_count,global_optimality_claimed=False)
        atomic(folder/'FINAL_MESS.json',result);np.savez_compressed(folder/'FINAL_POWER.npz',mess_p=bp,mess_q=bq);return result,best,bp,bq
    finally:model.dispose()
