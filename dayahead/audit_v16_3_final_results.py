"""Independent planning/trust audit over frozen final schedule caches; no solves."""

from __future__ import annotations

import argparse,json,math
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from .grid_lp import V_MAX_SQUARED,V_MIN_SQUARED
from .mess_physics import PCS_KVA,P_LIMIT_KW
from .run_v16_3_nonzero_validity import _aidc_limits,_planning_flow_base_and_sensitivity
from .run_v16_3_prepare_final_days import DEFAULT_SOURCE
from .v16_3_final_context import build_context


def audit_day(repo:Path,source:Path,output:Path,day:str):
    path=output/f"cache/results/{day}.json";row=json.loads(path.read_text(encoding="utf-8"))
    if row["status"]!="COMPLETED":return row
    context,inputs,_=build_context(repo,source,output,day,prepare=False)
    reference,_vintage,_background,binding,_vp,authority=context
    voltage=np.load(output/f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz",allow_pickle=False)
    current=np.load(output/f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz",allow_pickle=False)
    names=tuple(map(str,voltage["branch_names"]));line=np.asarray([not n.startswith("transformer.") for n in names]);tx=~line
    for case,value in row["cases"].items():
        if not value.get("hard_feasible"):continue
        raw=np.load(value["raw_schedule_cache"],allow_pickle=False);controls=np.asarray(raw["controls_96x60"]);delta=controls-np.asarray(voltage["anchor_control"])
        v=np.asarray(voltage["anchor_v_squared"])+np.einsum("tcn,tc->tn",np.asarray(voltage["sensitivity"]),delta)
        cur=np.maximum(np.asarray(current["anchor_current_loading_pu"])+np.einsum("tcb,tc->tb",np.asarray(current["current_sensitivity_pu_per_control"]),delta),0.0)
        li=np.unravel_index(np.argmax(np.where(line[None,:],cur,-np.inf)),cur.shape);ti=np.unravel_index(np.argmax(np.where(tx[None,:],cur,-np.inf)),cur.shape)
        tx_kva=[]
        for t in range(96):
            anchor=np.asarray(voltage["anchor_control"][t]);p0,q0,sp,sq=_planning_flow_base_and_sensitivity(binding,t,anchor);p=p0+sp@delta[t];q=q0+sq@delta[t]
            for b,branch in enumerate(binding.factories[t].data.branches):
                rating=binding.factories[t].data.transformer_limit_kva.get((branch.branch_id,branch.phase))
                if rating is not None:tx_kva.append((math.hypot(float(p[b]),float(q[b]))/float(rating),t,b,branch.branch_id,branch.phase))
        worst_kva=max(tx_kva)
        utils=[];active_slots=set()
        for t in range(96):
            down,up,_=_aidc_limits(reference,authority,t)
            for i in range(12):
                denom=.1*(up[i] if delta[t,i]>=0 else down[i]);u=abs(delta[t,i])/denom if denom>1e-12 else (0.0 if abs(delta[t,i])<=1e-9 else math.inf);utils.append((u,t,f"aidc[{i}]") )
            for i in range(12,36): utils.append((abs(delta[t,i])/(.1*P_LIMIT_KW),t,f"mess_p[{i-12}]"))
            for i in range(36,60): utils.append((abs(delta[t,i])/(.1*PCS_KVA),t,f"mess_q[{i-36}]"))
        for u,t,_ in utils:
            if u>=1-1e-6:active_slots.add(t)
        maxu=max(utils)
        value["MESS_reactive_power_max_utilization"] = float(np.max(np.abs(raw["mess_q"])) / PCS_KVA)
        value["MESS_travel_connectivity_schedule"] = {mess_id:{"service_site":record["service_site"],"transit_slots":record["transit_slots"],"connected_slot_count":96-len(record["transit_slots"])} for mess_id,record in inputs.mess_records.items()}
        value["planning_audit"]={"Vmin_pu":float(np.sqrt(max(0,float(v.min())))),"Vmax_pu":float(np.sqrt(float(v.max()))),"maximum_normalized_phase_line_current":float(cur[li]),"critical_line_phase_slot":{"branch":names[li[1]],"slot":int(li[0])},"worst_transformer_phase_current":{"branch":names[ti[1]],"slot":int(ti[0]),"loading_pu":float(cur[ti])},"worst_transformer_total_kva":{"branch":worst_kva[3],"phase":worst_kva[4],"slot":int(worst_kva[1]),"loading_pu":float(worst_kva[0])},"trust_region_max_utilization":float(maxu[0]),"trust_region_worst_dimension":maxu[2],"trust_region_worst_slot":int(maxu[1]),"trust_region_boundary_variable_count":int(sum(u>=1-1e-6 for u,_,_ in utils)),"trust_region_active_slot_count":len(active_slots),"hard_constraint_residuals":{"voltage_lower_squared_min":float(v.min()-V_MIN_SQUARED),"voltage_upper_squared_min":float(V_MAX_SQUARED-v.max()),"phase_current_min_margin":float(1-cur.max()),"transformer_total_kva_min_margin":float(1-worst_kva[0]),"service_parity_max_abs":value["terminal_service_parity_max_abs_error"],"MESS_terminal_SOC_max_abs_kwh":value["mess_terminal_soc_max_abs_error_kwh"]},"rho_verified_le_0_10":bool(maxu[0]<=1+1e-6),"independent_solver_calls":0,"independent_OpenDSS_calls":0}
    path.write_text(json.dumps(row,indent=2,sort_keys=True)+"\n",encoding="utf-8");return row


def _worker(args):return audit_day(Path(args[0]),Path(args[1]),Path(args[2]),args[3])
def execute(repo:Path,source:Path,output:Path,workers:int):
    days=sorted(p.stem for p in (output/"cache/results").glob("2025-*.json"));done=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(_worker,(str(repo),str(source),str(output),d)):d for d in days}
        for i,f in enumerate(as_completed(fs),1):f.result();done+=1;print(json.dumps({"audit_complete":i,"total":len(days),"day":fs[f]}),flush=True)
    return {"audited_days":done,"solver_calls":0,"OpenDSS_calls":0}
def main():
    r=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=r);p.add_argument("--source",type=Path,default=DEFAULT_SOURCE);p.add_argument("--output",type=Path,default=r/"dayahead/artifacts/v16_3_final");p.add_argument("--workers",type=int,default=4);print(json.dumps(execute(**vars(p.parse_args())),indent=2))
if __name__=="__main__":main()
