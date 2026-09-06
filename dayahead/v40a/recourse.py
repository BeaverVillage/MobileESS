"""MESS P/Q recourse over an immutable, already selected mobility trajectory.

No route table, candidate enumerator, K search or beam driver is accepted by
this API. Charge/discharge direction remains the existing electrical binary.
"""
from __future__ import annotations
from dataclasses import replace
import math
import time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v34.integrated_mess import _configured_model
from .grid import add_grid, controls_from_trajectory, evaluate_grid
from .invariants import route_sha


def validate_physics(trajectory, authority=None, tolerance=1e-6):
    a=authority or MessElectricalAuthority.from_repository();by={}
    for r in trajectory.slots:
        if (r.mess_id,r.slot) in by:raise ValueError('DUPLICATE_MESS_SLOT')
        by[r.mess_id,r.slot]=r
    ids=sorted({k[0] for k in by});violations=[]
    horizon=max((k[1] for k in by),default=-1)+1
    if not ids or horizon <= 0:
        raise ValueError('EMPTY_MESS_TRAJECTORY')
    for mid in ids:
        if {(mid,t) for t in range(horizon)}-set(by):raise ValueError('INCOMPLETE_MESS_SLOT_AXIS')
        if abs(by[mid,0].battery_energy_kwh-a.initial_energy_kwh)>tolerance:violations.append('INITIAL_ENERGY')
        for t in range(horizon):
            r=by[mid,t];connected=r.mode=='CONNECTED'
            if connected!=(r.service_id is not None):violations.append('CONNECTION_IDENTITY')
            if not connected and (abs(r.p_kw)>tolerance or abs(r.q_kvar)>tolerance):violations.append('TRANSIT_PQ')
            if abs(r.p_kw)>a.active_power_limit_kw+tolerance:violations.append('ACTIVE_POWER')
            if not a.energy_min_kwh-tolerance<=r.battery_energy_kwh<=a.energy_max_kwh+tolerance:violations.append('ENERGY_BOUNDS')
            if abs(r.soc_fraction-r.battery_energy_kwh/a.capacity_kwh)>tolerance:violations.append('SOC_IDENTITY')
            for f in range(a.pcs_polygon_faces):
                angle=2*math.pi*f/a.pcs_polygon_faces
                if math.cos(angle)*r.p_kw+math.sin(angle)*r.q_kvar>a.pcs_kva*math.cos(math.pi/a.pcs_polygon_faces)*connected+tolerance:violations.append('PCS')
            travel=r.energy_safe_kwh if r.departure_slot==t and r.mode=='TRANSIT' else 0
            if r.battery_energy_kwh<a.energy_min_kwh+travel-tolerance:violations.append('DEPARTURE_ENERGY')
            expected=r.battery_energy_kwh+a.charge_efficiency*a.interval_hours*max(-r.p_kw,0)-a.interval_hours*max(r.p_kw,0)/a.discharge_efficiency-travel
            actual=by[mid,t+1].battery_energy_kwh if t+1<horizon else a.terminal_energy_kwh
            if abs(expected-actual)>tolerance:violations.append('ENERGY_RECURRENCE')
    return {'status':'PASS' if not violations else 'FAIL','violations':sorted(set(violations)),
            'route_sha256':route_sha(trajectory.slots),'horizon_slots':horizon,'fleet':ids}


def solve_fixed_route(pcc, m1, context, *, tolerance=1e-6):
    start=time.perf_counter();physics=validate_physics(m1)
    if physics['status']!='PASS':raise ValueError('MF_REQUIRES_VALID_M1_PHYSICS:'+str(physics))
    route=route_sha(m1.slots);a=MessElectricalAuthority.from_repository()
    before=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,m1.slots),context.nodes)
    if before['status']!='PASS':raise ValueError('MF_REQUIRES_FEASIBLE_A1_M1_STATE')
    model=_configured_model('V40A_FIXED_ROUTE_PQ');rows={(r.mess_id,r.slot):r for r in m1.slots}
    ids=sorted({r.mess_id for r in m1.slots});horizon=len(context.coefficients)
    names=context.coefficients[0].control_names
    controls=[[float(v) for v in row] for row in np.c_[pcc,np.zeros((horizon,len(names)-12))]]
    p={};q={};energy={}
    try:
        for mid in ids:
            for t in range(horizon+1):
                energy[mid,t]=model.addVar(lb=a.energy_min_kwh,ub=a.energy_max_kwh,name=f'energy[{mid},{t}]')
                energy[mid,t].Start=rows[mid,t].battery_energy_kwh if t<horizon else a.terminal_energy_kwh
            model.addConstr(energy[mid,0]==a.initial_energy_kwh);model.addConstr(energy[mid,horizon]==a.terminal_energy_kwh)
            for t in range(horizon):
                r=rows[mid,t];connected=int(r.mode=='CONNECTED')
                direction=model.addVar(vtype=GRB.BINARY,ub=connected,name=f'discharge_mode[{mid},{t}]')
                discharge=model.addVar(lb=0,ub=a.active_power_limit_kw*connected,name=f'P_discharge[{mid},{t}]')
                charge=model.addVar(lb=0,ub=a.active_power_limit_kw*connected,name=f'P_charge[{mid},{t}]')
                q[mid,t]=model.addVar(lb=-a.pcs_kva*connected,ub=a.pcs_kva*connected,name=f'Q[{mid},{t}]')
                p[mid,t]=discharge-charge
                model.addConstr(discharge<=a.active_power_limit_kw*direction)
                model.addConstr(charge<=a.active_power_limit_kw*(1-direction))
                model.addConstr(discharge+charge<=a.active_power_limit_kw*connected)
                direction.Start=float(r.p_kw>1e-9);discharge.Start=max(r.p_kw,0);charge.Start=max(-r.p_kw,0);q[mid,t].Start=r.q_kvar
                for f in range(a.pcs_polygon_faces):
                    angle=2*math.pi*f/a.pcs_polygon_faces
                    model.addConstr(math.cos(angle)*p[mid,t]+math.sin(angle)*q[mid,t]<=a.pcs_kva*math.cos(math.pi/a.pcs_polygon_faces)*connected)
                travel=r.energy_safe_kwh if r.departure_slot==t and r.mode=='TRANSIT' else 0.0
                model.addConstr(energy[mid,t]>=a.energy_min_kwh+travel)
                model.addConstr(energy[mid,t+1]==energy[mid,t]+a.charge_efficiency*a.interval_hours*charge-a.interval_hours*discharge/a.discharge_efficiency-travel)
                if connected:
                    controls[t][names.index(f'mess_p_kw[{r.service_id}]')]+=p[mid,t]
                    controls[t][names.index(f'mess_q_kvar[{r.service_id}]')]+=q[mid,t]
        rho,grid_rows=add_grid(model,context.coefficients,controls,min(1,before['rho_max']+tolerance))
        model.setObjective(rho,GRB.MINIMIZE);model.optimize()
        info={'status_code':int(model.Status),'incumbent':float(model.ObjVal) if model.SolCount else None,
              'bound':float(model.ObjBound) if model.SolCount else None,'solver_runtime_seconds':float(model.Runtime),'work':float(model.Work),
              'global_optimality_certified':model.Status==GRB.OPTIMAL,'Gurobi_optimize_calls':1}
        if not model.SolCount:return {'status':'NO_INCUMBENT','trajectory':m1,'solver':info,'wallclock_seconds':time.perf_counter()-start}
        final=MessTrajectory(tuple(replace(r,p_kw=float(p[r.mess_id,r.slot].getValue()),q_kvar=float(q[r.mess_id,r.slot].X),
                                      battery_energy_kwh=float(energy[r.mess_id,r.slot].X),soc_fraction=float(energy[r.mess_id,r.slot].X)/a.capacity_kwh) for r in m1.slots))
        if route_sha(final.slots)!=route:raise ValueError('MF_ROUTE_IDENTITY_CHANGED')
        result=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,final.slots),context.nodes)
        check=validate_physics(final)
        return {'status':'PASS' if result['status']=='PASS' and check['status']=='PASS' else 'FAIL','trajectory':final,'grid':result,
                'physics':check,'solver':info,'grid_rows':grid_rows,'route_search_calls':0,'wallclock_seconds':time.perf_counter()-start}
    finally:model.dispose()
