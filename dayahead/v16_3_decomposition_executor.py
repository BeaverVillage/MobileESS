"""Exact implementation-only Benders adapter for the frozen V16.3 B3 LP.

The resource master equations are mechanically extracted from
``final_science_solver_v16_3.solve_shadow``.  Grid coefficients come from the
same frozen H/J-I arrays and the same planning-flow coefficient factory used
by that monolithic implementation.  No OpenDSS entry point is imported.
"""

from __future__ import annotations

import hashlib,json,math,time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping,Sequence

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS,PUE_PLAN
from .aidc_power_response import GPU_PER_NODE,KAPPA_KW_PER_ACTIVE_H100_NODE
from .full_ieee123_b3_v16_2 import B3Inputs
from .grid_lp import LINE_POLYGON_FACES,V_MAX_SQUARED,V_MIN_SQUARED
from .mess_physics import E_INITIAL_KWH,E_MAX_KWH,E_MIN_KWH,E_TERMINAL_KWH,PCS_KVA,PCS_POLYGON_FACES,P_LIMIT_KW
from .run_v16_3_nonzero_validity import _aidc_limits,_planning_flow_base_and_sensitivity


GAMMA_CRIT=.98
TOLERANCE=1e-3
MAX_ITERATIONS=200
TIME_LIMIT_SECONDS=1800.0


def _sha(value)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=float).encode()).hexdigest()


def configure_model(model)->None:
    model.Params.OutputFlag=0;model.Params.Threads=1;model.Params.Seed=20260828;model.Params.Method=1
    model.Params.NumericFocus=1;model.Params.DualReductions=0;model.Params.InfUnbdInfo=1
    model.Params.FeasibilityTol=1e-6;model.Params.OptimalityTol=1e-6;model.Params.TimeLimit=1800.0


@dataclass(frozen=True)
class SlotCoefficients:
    slot:int
    control_names:tuple[str,...]
    branch_names:tuple[str,...]
    anchor:np.ndarray
    voltage_constant:np.ndarray
    voltage_matrix:np.ndarray
    current_constant:np.ndarray
    current_matrix:np.ndarray
    flow_p_constant:np.ndarray
    flow_q_constant:np.ndarray
    flow_p_matrix:np.ndarray
    flow_q_matrix:np.ndarray
    transformer_ratings:tuple[float|None,...]
    coefficient_sha256:str


def slot_coefficients(context,voltage,current,slot:int)->SlotCoefficients:
    _reference,_vintage,_background,binding,_path,_authority=context
    controls=tuple(map(str,voltage["control_names"]));branches=tuple(map(str,voltage["branch_names"]))
    if controls!=tuple(map(str,current["control_names"])) or branches!=tuple(map(str,current["branch_names"])):raise RuntimeError("DECOMP_AXIS_MISMATCH")
    anchor=np.asarray(voltage["anchor_control"][slot],dtype=float)
    h=np.asarray(voltage["sensitivity"][slot],dtype=float);v0=np.asarray(voltage["anchor_v_squared"][slot],dtype=float)
    ji=np.asarray(current["current_sensitivity_pu_per_control"][slot],dtype=float);i0=np.asarray(current["anchor_current_loading_pu"][slot],dtype=float)
    p0,q0,sp,sq=_planning_flow_base_and_sensitivity(binding,slot,anchor)
    rows=tuple(binding.factories[slot].data.branches)
    ratings=tuple(binding.factories[slot].data.transformer_limit_kva.get((row.branch_id,row.phase)) for row in rows)
    payload={"slot":slot,"controls":controls,"branches":branches,"anchor":anchor.tolist(),"v_constant":(v0-h.T@anchor).tolist(),"H":h.tolist(),"i_constant":(i0-ji.T@anchor).tolist(),"J_I":ji.tolist(),"p_constant":(p0-sp@anchor).tolist(),"q_constant":(q0-sq@anchor).tolist(),"S_P":sp.tolist(),"S_Q":sq.tolist(),"ratings":ratings}
    return SlotCoefficients(slot,controls,branches,anchor,v0-h.T@anchor,h,i0-ji.T@anchor,ji,p0-sp@anchor,q0-sq@anchor,sp,sq,ratings,_sha(payload))


@dataclass
class ResourceMaster:
    model:object
    eta:object
    control_expressions:tuple[tuple[object,...],...]
    x:Mapping[tuple[str,str,int],object]
    backlog:Mapping[tuple[str,int],object]
    mess_p:Mapping[tuple[str,int],object]
    mess_q:Mapping[tuple[str,int],object]
    mess_e:Mapping[tuple[str,int],object]

    def controls(self)->np.ndarray:
        def value(expr):
            if hasattr(expr,"getValue"):return float(expr.getValue())
            if hasattr(expr,"X"):return float(expr.X)
            return float(expr)
        return np.asarray([[value(expr) for expr in row] for row in self.control_expressions])


def build_resource_master(*,inputs:B3Inputs,context,voltage,rho:float=.1)->ResourceMaster:
    """Exact B3 non-grid master extracted from the active final monolithic."""
    import gurobipy as gp
    from gurobipy import GRB
    reference,_vintage,_background,_binding,_path,authority=context
    model=gp.Model("v16_3_exact_b3_decomposition_master");configure_model(model)
    cohorts=inputs.cohorts;racks=inputs.rack_ids;rack_index={r:i for i,r in enumerate(racks)}
    aidc_racks={f"AIDC{i:02d}":tuple(r for r,a in zip(racks,inputs.rack_aidc) if a==f"AIDC{i:02d}") for i in range(1,13)}
    x={(c,r,t):model.addVar(lb=0.0,name=f"workload[{c},{r},{t}]") for c in cohorts for r in racks for t in range(96)}
    backlog={(c,b):model.addVar(lb=0.0,name=f"backlog[{c},{b}]") for c in cohorts for b in range(97)}
    for c in cohorts:
        model.addConstr(backlog[(c,0)]==0,name=f"service_initial[{c}]")
        for t in range(96):model.addConstr(backlog[(c,t+1)]==backlog[(c,t)]+inputs.arrivals[c][t]-gp.quicksum(x[(c,r,t)] for r in racks),name=f"service_balance[{c},{t}]")
        model.addConstr(backlog[(c,96)]==0,name=f"service_terminal_parity[{c}]")
    for t in range(96):
        for rack in racks:
            r=rack_index[rack];model.addConstr(inputs.g_res_rack[t][r]+GPU_PER_NODE/DT_HOURS*gp.quicksum(x[(c,rack,t)] for c in cohorts)<=inputs.gpu_capacity[r],name=f"rack_gpu_hard[{rack},{t}]")
    aidc_load={}
    for t in range(96):
        for index in range(1,13):
            aidc=f"AIDC{index:02d}";flex=gp.quicksum(KAPPA_KW_PER_ACTIVE_H100_NODE[int(c[1:3])]/DT_HOURS*x[(c,r,t)] for c in cohorts for r in aidc_racks[aidc])
            aidc_load[(aidc,t)]=PUE_PLAN*(inputs.p_res_aidc_kw[t][index-1]+flex)
    mess_p={};mess_q={};mess_e={};service_to_mess={str(v["service_site"]):k for k,v in inputs.mess_records.items()}
    for mid,record in sorted(inputs.mess_records.items()):
        transit=set(map(int,record["transit_slots"]))
        for b in range(97):mess_e[(mid,b)]=model.addVar(lb=E_MIN_KWH,ub=E_MAX_KWH,name=f"mess_soc_kwh[{mid},{b}]")
        model.addConstr(mess_e[(mid,0)]==E_INITIAL_KWH,name=f"mess_initial_soc[{mid}]")
        for t in range(96):
            connected=t not in transit
            mess_p[(mid,t)]=model.addVar(lb=-rho*P_LIMIT_KW if connected else 0,ub=rho*P_LIMIT_KW if connected else 0,name=f"mess_p_kw[{mid},{t}]")
            mess_q[(mid,t)]=model.addVar(lb=-rho*PCS_KVA if connected else 0,ub=rho*PCS_KVA if connected else 0,name=f"mess_q_kvar[{mid},{t}]")
            mobility=float(record["safe_mobility_energy_kwh"])/len(transit) if t in transit else 0
            model.addConstr(mess_e[(mid,t+1)]==mess_e[(mid,t)]-DT_HOURS*mess_p[(mid,t)]-mobility,name=f"mess_soc_balance[{mid},{t}]")
            apothem=PCS_KVA*math.cos(math.pi/PCS_POLYGON_FACES)
            for face in range(PCS_POLYGON_FACES):
                angle=2*math.pi*face/PCS_POLYGON_FACES;model.addConstr(math.cos(angle)*mess_p[(mid,t)]+math.sin(angle)*mess_q[(mid,t)]<=apothem,name=f"mess_pcs_hard[{mid},{t},{face}]")
        model.addConstr(mess_e[(mid,96)]==E_TERMINAL_KWH,name=f"mess_terminal_soc[{mid}]")
    controls=tuple(map(str,voltage["control_names"]));control_rows=[]
    for t in range(96):
        expressions=[]
        for name in controls:
            if name.startswith("aidc_load_kw["):expressions.append(aidc_load[(name[13:-1],t)])
            elif name.startswith("mess_p_kw["):
                service=name[10:-1];expressions.append(mess_p[(service_to_mess[service],t)] if service in service_to_mess else 0.0)
            elif name.startswith("mess_q_kvar["):
                service=name[12:-1];expressions.append(mess_q[(service_to_mess[service],t)] if service in service_to_mess else 0.0)
            else:raise RuntimeError(f"DECOMP_UNKNOWN_CONTROL:{name}")
        anchor=np.asarray(voltage["anchor_control"][t],dtype=float);down,up,_=_aidc_limits(reference,authority,t)
        for i in range(12):
            delta=expressions[i]-float(anchor[i]);model.addConstr(delta>=-rho*float(down[i]),name=f"trust_aidc_low[{t},{i}]");model.addConstr(delta<=rho*float(up[i]),name=f"trust_aidc_high[{t},{i}]")
        control_rows.append(tuple(expressions))
    eta=model.addVar(lb=0,name="max_normalized_phase_line_current");model.setObjective(eta,GRB.MINIMIZE);model.update()
    return ResourceMaster(model,eta,tuple(control_rows),x,backlog,mess_p,mess_q,mess_e)


@dataclass(frozen=True)
class SubproblemResult:
    slot:int
    feasible:bool
    objective:float|None
    gradient:tuple[float,...]
    intercept:float|None
    proof:float|None
    dual_sha256:str
    dual_nonzero_count:int
    critical_branch:str|None
    critical_loading:float|None
    status:str
    runtime_seconds:float
    dual_rows:Mapping[str,float]


class ExactGridSubproblem:
    def __init__(self,coeff:SlotCoefficients):
        import gurobipy as gp
        from gurobipy import GRB
        self.coeff=coeff;self.model=gp.Model(f"v16_3_exact_grid_sp_{coeff.slot:02d}");configure_model(self.model)
        m=self.model;self.registry=[];self.i_hat=[]
        v=[m.addVar(lb=V_MIN_SQUARED,ub=V_MAX_SQUARED,name=f"v[{n}]") for n in range(len(coeff.voltage_constant))]
        ia=[m.addVar(lb=-GRB.INFINITY,name=f"i_aff[{b}]") for b in range(len(coeff.current_constant))]
        self.i_hat=[m.addVar(lb=0,ub=1,name=f"i_hat[{b}]") for b in range(len(coeff.current_constant))]
        p=[m.addVar(lb=-GRB.INFINITY,name=f"tx_p[{b}]") for b in range(len(coeff.flow_p_constant))]
        q=[m.addVar(lb=-GRB.INFINITY,name=f"tx_q[{b}]") for b in range(len(coeff.flow_q_constant))]
        self.rho=m.addVar(lb=0,name="rho_t")
        self.v_rows=[];self.i_rows=[];self.p_rows=[];self.q_rows=[]
        for n,var in enumerate(v):
            con=m.addConstr(var==float(coeff.voltage_constant[n]),name=f"voltage_affine[{n}]");self.registry.append((con,coeff.voltage_matrix[:,n]));self.v_rows.append(con)
        for b,var in enumerate(ia):
            con=m.addConstr(var==float(coeff.current_constant[b]),name=f"current_affine[{b}]");self.registry.append((con,coeff.current_matrix[:,b]));self.i_rows.append(con)
            m.addConstr(self.i_hat[b]>=var,name=f"current_epigraph[{b}]")
            if not coeff.branch_names[b].startswith("transformer."):m.addConstr(self.rho>=self.i_hat[b],name=f"line_objective[{b}]")
        for b in range(len(p)):
            pc=m.addConstr(p[b]==float(coeff.flow_p_constant[b]),name=f"flow_p_affine[{b}]");qc=m.addConstr(q[b]==float(coeff.flow_q_constant[b]),name=f"flow_q_affine[{b}]")
            self.registry.extend(((pc,coeff.flow_p_matrix[b]),(qc,coeff.flow_q_matrix[b])));self.p_rows.append(pc);self.q_rows.append(qc)
            rating=coeff.transformer_ratings[b]
            if rating is not None:
                apothem=float(rating)*math.cos(math.pi/LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    angle=2*math.pi*face/LINE_POLYGON_FACES;m.addConstr(math.cos(angle)*p[b]+math.sin(angle)*q[b]<=apothem,name=f"transformer_total_kva[{b},{face}]")
        m.setObjective(self.rho,GRB.MINIMIZE);m.update()

    def solve(self,controls:Sequence[float],iteration:int,raw_dir:Path|None=None)->SubproblemResult:
        from gurobipy import GRB
        x=np.asarray(controls,dtype=float);c=self.coeff
        for n,row in enumerate(self.v_rows):row.RHS=float(c.voltage_constant[n]+c.voltage_matrix[:,n]@x)
        for b,row in enumerate(self.i_rows):row.RHS=float(c.current_constant[b]+c.current_matrix[:,b]@x)
        for b,row in enumerate(self.p_rows):row.RHS=float(c.flow_p_constant[b]+c.flow_p_matrix[b]@x)
        for b,row in enumerate(self.q_rows):row.RHS=float(c.flow_q_constant[b]+c.flow_q_matrix[b]@x)
        self.model.optimize();runtime=float(self.model.Runtime)
        if self.model.Status==GRB.OPTIMAL:
            dual={con.ConstrName:float(con.Pi) for con,_ in self.registry};grad=sum((float(con.Pi)*np.asarray(a,dtype=float) for con,a in self.registry),start=np.zeros(60));obj=float(self.model.ObjVal)
            line=[(float(self.i_hat[b].X),c.branch_names[b]) for b in range(len(self.i_hat)) if not c.branch_names[b].startswith("transformer.")];loading,branch=max(line,key=lambda z:(z[0],z[1]))
            result=SubproblemResult(c.slot,True,obj,tuple(map(float,grad)),obj-float(grad@x),None,_sha(dual),sum(abs(v)>1e-12 for v in dual.values()),branch,loading,"OPTIMAL",runtime,dual)
        elif self.model.Status==GRB.INFEASIBLE:
            dual={con.ConstrName:float(con.FarkasDual) for con,_ in self.registry};grad=sum((float(con.FarkasDual)*np.asarray(a,dtype=float) for con,a in self.registry),start=np.zeros(60));proof=float(self.model.FarkasProof)
            result=SubproblemResult(c.slot,False,None,tuple(map(float,grad)),None,proof,_sha(dual),sum(abs(v)>1e-12 for v in dual.values()),None,None,"INFEASIBLE_FARKAS",runtime,dual)
        else:raise RuntimeError(f"GRID_SP_STATUS_{self.model.Status}_T{c.slot}")
        if raw_dir is not None:
            raw_dir.mkdir(parents=True,exist_ok=True);path=raw_dir/f"iter_{iteration:03d}_slot_{c.slot:02d}.json";path.write_text(json.dumps({"slot":c.slot,"iteration":iteration,"status":result.status,"dual":dual,"gradient":result.gradient,"objective":result.objective,"proof":result.proof},sort_keys=True)+"\n",encoding="utf-8")
        return result


def add_cut(master:ResourceMaster,result:SubproblemResult,index:int)->str:
    import gurobipy as gp
    expr=gp.quicksum(float(result.gradient[c])*master.control_expressions[result.slot][c] for c in range(60))
    if result.feasible:
        master.model.addConstr(master.eta>=float(result.intercept)+expr,name=f"optimality_cut[{index},{result.slot}]");return "OPTIMALITY"
    controls=np.asarray([float(e.getValue()) if hasattr(e,"getValue") else (float(e.X) if hasattr(e,"X") else float(e)) for e in master.control_expressions[result.slot]])
    threshold=float(np.asarray(result.gradient)@controls)+float(result.proof)
    master.model.addConstr(-expr<=-threshold,name=f"farkas_cut[{index},{result.slot}]");return "FARKAS"


def solve_benders(*,inputs:B3Inputs,context,voltage,current,method:str,raw_dir:Path|None=None,max_iterations:int=MAX_ITERATIONS,time_limit:float=TIME_LIMIT_SECONDS)->dict[str,object]:
    from gurobipy import GRB
    if method not in {"STANDARD_BD","CL_MC_BD"}:raise ValueError(method)
    started=time.perf_counter();master=build_resource_master(inputs=inputs,context=context,voltage=voltage,rho=.1)
    coeffs=[slot_coefficients(context,voltage,current,t) for t in range(96)];sps=[ExactGridSubproblem(c) for c in coeffs]
    lb=-math.inf;ub=math.inf;logs=[];optcuts=farkas=0;cut_index=0;last_controls=None
    for iteration in range(1,max_iterations+1):
        elapsed=time.perf_counter()-started
        if elapsed>=time_limit:break
        master.model.Params.TimeLimit=max(1.0,time_limit-elapsed);master.model.optimize();master_runtime=float(master.model.Runtime)
        if master.model.Status==GRB.INFEASIBLE:
            return {"method":method,"status":"INFEASIBLE_CERTIFIED","hard_feasible":False,"objective":None,"runtime_seconds":time.perf_counter()-started,"iterations":iteration-1,"optimality_cut_count":optcuts,"farkas_cut_count":farkas,"LB":None,"UB":None,"gap":None,"iteration_log":logs,"OpenDSS_calls_inside_Benders":0,"coefficient_hash_of_hashes":_sha([c.coefficient_sha256 for c in coeffs])}
        if master.model.Status!=GRB.OPTIMAL:break
        controls=master.controls();last_controls=controls;lb=max(lb,float(master.model.ObjBound));sp_started=time.perf_counter();results=[sp.solve(controls[t],iteration,raw_dir) for t,sp in enumerate(sps)];sp_runtime=time.perf_counter()-sp_started
        all_feasible=all(r.feasible for r in results)
        if all_feasible:ub=min(ub,max(float(r.objective) for r in results))
        infeasible=[r for r in results if not r.feasible];feasible=[r for r in results if r.feasible]
        selected=list(infeasible);worst=max(feasible,key=lambda r:(float(r.objective),-r.slot)) if feasible else None
        critical=[]
        if all_feasible:
            if method=="STANDARD_BD":selected.append(worst)
            else:
                threshold=GAMMA_CRIT*max(float(r.critical_loading) for r in feasible);critical=[r for r in feasible if float(r.critical_loading)>=threshold-1e-12];selected.extend(critical)
        added_opt=added_farkas=0
        for r in selected:
            cut_index+=1;kind=add_cut(master,r,cut_index);added_opt+=kind=="OPTIMALITY";added_farkas+=kind=="FARKAS"
        optcuts+=added_opt;farkas+=added_farkas
        gap=max(0.0,(ub-lb)/max(abs(ub),1e-6)) if math.isfinite(ub) and math.isfinite(lb) else math.inf
        logs.append({"iteration":iteration,"master_incumbent":float(master.eta.X),"master_ObjBound":float(master.model.ObjBound),"LB":lb,"UB":ub if math.isfinite(ub) else None,"gap":gap if math.isfinite(gap) else None,"subproblem_statuses":[r.status for r in results],"worst_time":None if worst is None else {"slot":worst.slot,"branch_phase":worst.critical_branch,"loading":worst.critical_loading,"objective":worst.objective},"critical_time_set":[{"slot":r.slot,"line_phase":r.critical_branch,"loading":r.critical_loading,"cut_origin":"ACTUAL_GUROBI_PI_FULL_LP"} for r in critical],"optimality_cuts_added":added_opt,"Farkas_cuts_added":added_farkas,"optimality_cut_count":optcuts,"Farkas_cut_count":farkas,"master_runtime_seconds":master_runtime,"subproblem_runtime_seconds":sp_runtime,"cumulative_runtime_seconds":time.perf_counter()-started,"all_96_feasible":all_feasible,"UB_update_permitted":all_feasible,"dual_sha256_by_slot":[r.dual_sha256 for r in results]})
        if gap<=TOLERANCE:break
    runtime=time.perf_counter()-started;gap=max(0.0,(ub-lb)/max(abs(ub),1e-6)) if math.isfinite(ub) and math.isfinite(lb) else math.inf
    return {"method":method,"status":"OPTIMAL_CERTIFIED" if gap<=TOLERANCE else "TIME_OR_ITERATION_LIMIT_NOT_CERTIFIED","hard_feasible":bool(math.isfinite(ub)),"objective":ub if math.isfinite(ub) else None,"runtime_seconds":runtime,"iterations":len(logs),"optimality_cut_count":optcuts,"farkas_cut_count":farkas,"LB":lb if math.isfinite(lb) else None,"UB":ub if math.isfinite(ub) else None,"gap":gap if math.isfinite(gap) else None,"LB_monotone":all(logs[i]["LB"]>=logs[i-1]["LB"]-1e-9 for i in range(1,len(logs))),"UB_nonincreasing":all(logs[i]["UB"] is None or logs[i-1]["UB"] is None or logs[i]["UB"]<=logs[i-1]["UB"]+1e-9 for i in range(1,len(logs))),"UB_only_from_all_96_feasible":all((not r["UB_update_permitted"]) or r["all_96_feasible"] for r in logs),"iteration_log":logs,"OpenDSS_calls_inside_Benders":0,"coefficient_hash_of_hashes":_sha([c.coefficient_sha256 for c in coeffs])}


def verify_preserved_schedule(*,context,voltage,current,controls:np.ndarray)->dict[str,object]:
    coeffs=[slot_coefficients(context,voltage,current,t) for t in range(96)];sps=[ExactGridSubproblem(c) for c in coeffs];results=[sp.solve(controls[t],0,None) for t,sp in enumerate(sps)]
    return {"all_96_feasible":all(r.feasible for r in results),"objective":max(float(r.objective) for r in results if r.feasible),"slot_objectives":[r.objective for r in results],"coefficient_hash_of_hashes":_sha([c.coefficient_sha256 for c in coeffs]),"actual_Pi_nonzero_total":sum(r.dual_nonzero_count for r in results),"OpenDSS_calls":0}
