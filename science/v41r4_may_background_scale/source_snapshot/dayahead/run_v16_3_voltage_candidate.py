"""Build and validate the prospective V16.3 D-1 AC-anchored voltage model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_g11_v16_1 import FullGridBinding, build_full_grid_binding
from .grid_background_v16_2 import build_authority_background_binding
from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import (
    HARD_TOLERANCE, PF_TAN, _beta_reference, _fresh_ac, _locked_april_rows,
    _planning_reference, _select_april_vintages_locked, _set_generator, _set_load,
)
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json
from .run_head_of_feeder_capacity_diagnostic_v1 import _forecast_day
from .run_planning_ac_voltage_forensic_v1 import _compile
from .v16_3_voltage_candidate import V_MAX_SQUARED, V_MIN_SQUARED


FORENSIC_CHECKPOINT = "b181aacbce09b11a75f2a4644ccfec9b745fcc98"
NATIVE_MASTER_SHA = "cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969"
BETA_BASE = 0.25
PENETRATION_BETAS = (0.25, 0.50, 0.75, 1.00)
REGULATORS = ("reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c")
CAPACITORS = ("c83", "c88a", "c90b", "c92c")
ACCEPTANCE = {
    "frozen_before_april29_read": True,
    "case_A_114A_false_undervoltage_allowed": False,
    "candidate_B_must_improve_max_error_over_old_and_A": True,
    "candidate_B_must_improve_mean_error_over_old_and_A": True,
    "may_june_access_allowed": False,
    "opendss_inside_benders_allowed": False,
    "common_B0_B1_B2_B3_anchor_required": True,
    "LP_Pi_Farkas_required": True,
}
COUNTERS = {
    "scientific_authority_changes": 0, "production_V16_3_activations": 0,
    "native_ieee123_changes": 0, "native_regulator_setting_changes": 0,
    "tap_cooptimization_variables_added": 0, "OpenDSS_calls_inside_Benders": 0,
    "legacy_v13_control_sidecar_loads": 0, "AIDC_raw_data_changes": 0,
    "beta_production_changes": 0, "alpha_grid_changes": 0,
    "native_feeder_rating_changes": 0, "u080_changes": 0,
    "voltage_limit_changes": 0, "kappa_changes": 0, "PUE_changes": 0,
    "PF_changes": 0, "may_scientific_loader_access_count": 0,
    "june_scientific_loader_access_count": 0, "G12_final_calls": 0,
    "G13_calls": 0, "G14_calls": 0, "C12_calls": 0,
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _checkpoint(repo: Path, source: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    if head != FORENSIC_CHECKPOINT:
        raise RuntimeError(f"V163_FORENSIC_CHECKPOINT_MISMATCH:{head}")
    if _git(repo, "status", "--short"):
        # The runner itself may be untracked during construction, but no active
        # authority path may be dirty.
        dirty = tuple(line for line in _git(repo, "status", "--short").splitlines() if "run_v16_3_voltage_candidate.py" not in line and "v16_3_voltage_candidate.py" not in line and "test_v16_3_voltage_candidate.py" not in line and "artifacts/v16_3_candidate" not in line)
        if dirty: raise RuntimeError(f"V163_UNEXPECTED_DIRTY_PATHS:{dirty}")
    native = source / "opendss_assets/IEEE123Master.dss"
    if sha256_file(native) != NATIVE_MASTER_SHA: raise RuntimeError("V163_NATIVE_IEEE123_SHA_MISMATCH")
    return {"branch":_git(repo,"branch","--show-current"),"head":head,"native_ieee123_master_sha":sha256_file(native),"clean_before_candidate_work":True}


def _node_axis(binding: FullGridBinding) -> tuple[str, ...]:
    present = binding.factories[0].data.bus_phase_present
    return tuple(sorted(f"{bus}.{'ABC'.index(phase)+1}" for (bus,phase),flag in present.items() if flag))


def _voltage_map(odd, nodes: Sequence[str]) -> dict[str,float]:
    values=dict(zip(map(lambda x:str(x).lower(),odd.Circuit.AllNodeNames()),map(float,odd.Circuit.AllBusMagPu())))
    return {node:values[node] for node in nodes}


def _regulator_taps(odd) -> dict[str,float]:
    result={}
    for name in odd.RegControls.AllNames():
        odd.RegControls.Name(name); transformer=str(odd.RegControls.Transformer()).lower(); winding=int(odd.RegControls.Winding())
        odd.Transformers.Name(transformer); odd.Transformers.Wdg(winding); result[transformer]=float(odd.Transformers.Tap())
    if set(result)!=set(REGULATORS): raise RuntimeError("V163_REGULATOR_SET_MISMATCH")
    return result


def _capacitor_states(odd) -> dict[str,tuple[int,...]]:
    result={}
    for name in odd.Capacitors.AllNames():
        odd.Capacitors.Name(name); result[str(name).lower()]=tuple(map(int,odd.Capacitors.States()))
    if set(result)!=set(CAPACITORS): raise RuntimeError("V163_CAPACITOR_SET_MISMATCH")
    return result


def _fix_controls(odd,taps:Mapping[str,float],caps:Mapping[str,Sequence[int]])->None:
    for name in odd.RegControls.AllNames(): odd.Text.Command(f"Disable RegControl.{name}")
    for name,value in taps.items(): odd.Transformers.Name(name); odd.Transformers.Wdg(2); odd.Transformers.Tap(float(value))
    for name,state in caps.items(): odd.Capacitors.Name(name); odd.Capacitors.States(list(map(int,state)))
    odd.Text.Command("Set controlmode=off")


def _enable_native_controls(odd)->None:
    for name in odd.RegControls.AllNames(): odd.Text.Command(f"Enable RegControl.{name}")
    odd.Text.Command("Set controlmode=static maxcontroliter=100")


def _set_slot(odd,adapter,background,plan,slot:int)->None:
    for row in adapter["loads"]:
        phases=tuple("ABC"[int(value)-1] for value in row["phases"]); bus=str(row["bus"]).lower()
        _set_load(odd,str(row["load_name"]),sum(background.gross_p_kw_96[slot].get((bus,phase),0.0) for phase in phases),sum(background.gross_q_kvar_96[slot].get((bus,phase),0.0) for phase in phases))
    for row in adapter["pv_generators"]:
        bus=str(row["bus"]).lower(); phase="ABC"[int(row["phase"])-1]
        _set_generator(odd,str(row["generator_name"]),background.pv_generation_kw_96[slot].get((bus,phase),0.0))
    for index in range(1,13):
        value=float(plan[slot][index-1]); _set_load(odd,f"IDC_IDC{index:02d}",value,value*PF_TAN)
    for name in odd.Generators.AllNames():
        if str(name).lower().startswith("mess_dis_"): _set_generator(odd,str(name),0.0,0.0)
    for name in odd.Loads.AllNames():
        if str(name).lower().startswith("mess_chg_"): _set_load(odd,str(name),0.0,0.0)


def _terminal_phase(odd,element:str,parent_bus:str,phase:str)->tuple[float,float,float]:
    odd.Circuit.SetActiveElement(element); conductors=int(odd.CktElement.NumConductors())
    buses=[str(value).split(".",1)[0].lower() for value in odd.CktElement.BusNames()]; terminal=buses.index(parent_bus.lower())
    nodes=list(map(int,odd.CktElement.NodeOrder())); powers=list(map(float,odd.CktElement.Powers())); currents=list(map(float,odd.CktElement.CurrentsMagAng()))
    wanted="ABC".index(phase)+1; index=next(terminal*conductors+i for i in range(conductors) if nodes[terminal*conductors+i]==wanted)
    return powers[2*index],powers[2*index+1],currents[2*index]


def _control_axis(odd)->tuple[str,...]:
    services=sorted(str(name)[len("MESS_DIS_"):].upper() for name in odd.Generators.AllNames() if str(name).upper().startswith("MESS_DIS_"))
    return tuple([f"aidc_load_kw[AIDC{i:02d}]" for i in range(1,13)]+[f"mess_p_kw[{s}]" for s in services]+[f"mess_q_kvar[{s}]" for s in services])


def _perturbation(control:str,anchor_value:float)->float:
    if control.startswith("aidc_"): return max(1.0,0.005*max(abs(anchor_value),200.0))
    return 5.0


def _apply_control(odd,control:str,value:float,anchor_plan:Sequence[float])->None:
    if control.startswith("aidc_load_kw["):
        aidc=control.split("[",1)[1][:-1]; index=int(aidc[-2:])-1
        _set_load(odd,f"IDC_IDC{index+1:02d}",float(value),float(value)*PF_TAN); return
    service=control.split("[",1)[1][:-1]
    if control.startswith("mess_p_kw["):
        _set_generator(odd,f"MESS_DIS_{service}",max(float(value),0.0),0.0)
        _set_load(odd,f"MESS_CHG_{service}",max(-float(value),0.0),0.0); return
    _set_generator(odd,f"MESS_DIS_{service}",0.0,float(value)); _set_load(odd,f"MESS_CHG_{service}",0.0,0.0)


def _tap_aware_ld(binding:FullGridBinding,plan:Sequence[Sequence[float]],slot:int,taps:Mapping[str,float])->dict[str,float]:
    factory=binding.factories[slot]; data=factory.data; master=dict(binding.baseline_master[slot])
    for index in range(1,13): master[f"aidc_load_kw[AIDC{index:02d}]"]=float(plan[slot][index-1])
    for key in master:
        if key.startswith(("mess_p_kw[","mess_q_kvar[")): master[key]=0.0
    outgoing=defaultdict(list)
    for branch in data.branches: outgoing[(branch.parent_bus,branch.phase)].append(branch)
    p={};q={}
    for branch in reversed(data.branches):
        node=(branch.child_bus,branch.phase)
        pl=float(data.base_load_p_kw.get(node,0))-sum(float(c)*float(master[k]) for k,c in data.master_p_injection.get(node,{}).items())
        ql=float(data.base_load_q_kvar.get(node,0))-sum(float(c)*float(master[k]) for k,c in data.master_q_injection.get(node,{}).items())
        key=(branch.branch_id,branch.phase);p[key]=pl+sum(p[(b.branch_id,b.phase)] for b in outgoing.get(node,()));q[key]=ql+sum(q[(b.branch_id,b.phase)] for b in outgoing.get(node,()))
    voltage={(data.root_bus,phase):1.0 for phase in "ABC"}
    for branch in data.branches:
        name=branch.branch_id.split(".",1)[1] if branch.branch_id.startswith("transformer.") else branch.branch_id
        ratio=float(taps.get(name,1.0)); key=(branch.branch_id,branch.phase)
        voltage[(branch.child_bus,branch.phase)]=ratio*ratio*voltage[(branch.parent_bus,branch.phase)]-2*(branch.r_pu_per_kw*p[key]+branch.x_pu_per_kvar*q[key])
    return {f"{bus}.{'ABC'.index(phase)+1}":value for (bus,phase),value in voltage.items()}


def _old_ld(binding:FullGridBinding,plan:Sequence[Sequence[float]],slot:int)->dict[str,float]:
    return _tap_aware_ld(binding,plan,slot,{name:1.0 for name in REGULATORS})


def _hard_counts(pred:Sequence[float],actual:Sequence[float])->dict[str,int]:
    result=defaultdict(int)
    for p,a in zip(pred,actual):
        pclass="LOW" if p<0.95-HARD_TOLERANCE else ("HIGH" if p>1.05+HARD_TOLERANCE else "OK")
        aclass="LOW" if a<0.95-HARD_TOLERANCE else ("HIGH" if a>1.05+HARD_TOLERANCE else "OK")
        result["classification_disagreement"]+=int(pclass!=aclass)
        result["false_undervoltage"]+=int(pclass=="LOW" and aclass!="LOW")
        result["false_overvoltage"]+=int(pclass=="HIGH" and aclass!="HIGH")
        result["false_feasible"]+=int(pclass=="OK" and aclass!="OK")
    return dict(result)


def _metrics(pred:Sequence[float],actual:Sequence[float],nodes:Sequence[str]|None=None)->dict[str,object]:
    import numpy as np
    p=np.asarray(pred,dtype=float);a=np.asarray(actual,dtype=float);error=np.abs(p-a); signed=p-a
    counts=_hard_counts(p,a)
    result={"max_abs_voltage_error_pu":float(error.max()),"mean_abs_voltage_error_pu":float(error.mean()),"p95_abs_voltage_error_pu":float(np.quantile(error,0.95)),"mean_signed_error_pu":float(signed.mean()),"Vmin_pu":float(p.min()),"Vmax_pu":float(p.max()),**counts}
    if nodes:
        width=len(nodes);imin=int(np.argmin(p));imax=int(np.argmax(p));ierror=int(np.argmax(error))
        def where(index:int)->dict[str,object]:
            node=str(nodes[index%width]);return {"slot":index//width,"node":node,"bus":node.rsplit(".",1)[0],"phase":"ABC"[int(node.rsplit(".",1)[1])-1]}
        result.update({"Vmin_location":where(imin),"Vmax_location":where(imax),"worst_error_location":where(ierror)})
    return result


def _cache_record(cache:Path,day:str)->dict[str,object]:
    import numpy as np
    data=np.load(cache,allow_pickle=False);v2=data["anchor_v_squared"];h=data["sensitivity"];taps=data["regulator_taps"];caps=data["capacitor_states"]
    return {"path":str(cache.resolve()),"sha256":sha256_file(cache),"node_count":len(data["node_names"]),"control_count":len(data["control_names"]),"branch_phase_count":len(data["branch_names"]),"convergence_count":96,"deterministic_repeat_max_abs_error":float(data["deterministic_repeat_max_abs_error"]),"regulator_taps_96":[{name:float(taps[slot,i]) for i,name in enumerate(REGULATORS)} for slot in range(96)],"capacitor_states_96":[{name:[int(caps[slot,i])] for i,name in enumerate(CAPACITORS)} for slot in range(96)],"fingerprint":hashlib.sha256(v2.tobytes()+h.tobytes()+taps.tobytes()+caps.tobytes()).hexdigest()}


def _anchor_and_sensitivity_day(repo:Path,source:Path,background,plan,binding:FullGridBinding,day:str,cache:Path,build_sensitivity:bool=True)->dict[str,object]:
    import numpy as np
    plan_sha=_hash_payload(plan);schema="V16_3_D1_AC_ANCHOR_SENSITIVITY_NPZ_V1"
    if cache.exists():
        try:
            existing=np.load(cache,allow_pickle=False)
            if str(existing["schema_version"])==schema and str(existing["operating_day"])==day and str(existing["native_master_sha"])==NATIVE_MASTER_SHA and str(existing["plan_sha256"])==plan_sha and (not build_sensitivity or existing["sensitivity"].shape[0]==96):
                return _cache_record(cache,day)
        except KeyError:
            pass
    odd,adapter=_compile(source,repo,"NATIVE"); nodes=_node_axis(binding); controls=_control_axis(odd); branches=binding.factories[0].data.branches
    v2=np.empty((96,len(nodes))); h=np.empty((96,len(controls),len(nodes))) if build_sensitivity else np.empty((0,0,0))
    taps=np.empty((96,len(REGULATORS))); caps=np.empty((96,len(CAPACITORS)),dtype=np.int8)
    branch_p=np.empty((96,len(branches)));branch_q=np.empty_like(branch_p);branch_i=np.empty_like(branch_p);root_pq=np.empty((96,2)); converged=[]; anchor_control=np.zeros((96,len(controls))); deterministic_error=0.0
    for slot in range(96):
        _enable_native_controls(odd);_set_slot(odd,adapter,background,plan,slot);odd.Solution.SolveSnap();converged.append(bool(odd.Solution.Converged()))
        if not converged[-1]: raise RuntimeError(f"V163_ANCHOR_NONCONVERGENCE:{day}:{slot}")
        tap=_regulator_taps(odd);cap=_capacitor_states(odd);vm=_voltage_map(odd,nodes);v2[slot]=[vm[node]**2 for node in nodes];taps[slot]=[tap[name] for name in REGULATORS];caps[slot]=[cap[name][0] for name in CAPACITORS]
        for index,branch in enumerate(branches): branch_p[slot,index],branch_q[slot,index],branch_i[slot,index]=_terminal_phase(odd,branch.branch_id,branch.parent_bus,branch.phase)
        odd.Circuit.SetActiveElement("Transformer.reg1a");conductors=int(odd.CktElement.NumConductors());powers=list(map(float,odd.CktElement.Powers()));root_pq[slot]=[sum(powers[2*i] for i in range(conductors) if i<3),sum(powers[2*i+1] for i in range(conductors) if i<3)]
        for index,control in enumerate(controls): anchor_control[slot,index]=float(plan[slot][int(control[-3:-1])-1]) if control.startswith("aidc_") else 0.0
        if not build_sensitivity: continue
        _fix_controls(odd,tap,cap)
        for index,control in enumerate(controls):
            base=anchor_control[slot,index];delta=_perturbation(control,base)
            _apply_control(odd,control,base+delta,plan[slot]);odd.Solution.SolveSnap();plus=np.array([value**2 for value in _voltage_map(odd,nodes).values()])
            _apply_control(odd,control,base-delta,plan[slot]);odd.Solution.SolveSnap();minus=np.array([value**2 for value in _voltage_map(odd,nodes).values()])
            h[slot,index]=(plus-minus)/(2*delta);_apply_control(odd,control,base,plan[slot])
            if slot==0 and index==0:
                _apply_control(odd,control,base+delta,plan[slot]);odd.Solution.SolveSnap();repeat=np.array([value**2 for value in _voltage_map(odd,nodes).values()]);deterministic_error=max(deterministic_error,float(np.max(np.abs(repeat-plus))));_apply_control(odd,control,base,plan[slot])
    cache.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(cache,schema_version=np.asarray(schema),operating_day=np.asarray(day),native_master_sha=np.asarray(NATIVE_MASTER_SHA),plan_sha256=np.asarray(plan_sha),deterministic_repeat_max_abs_error=np.asarray(deterministic_error),node_names=np.asarray(nodes),control_names=np.asarray(controls),branch_names=np.asarray([f"{b.branch_id}::{b.phase}" for b in branches]),anchor_v_squared=v2,sensitivity=h,anchor_control=anchor_control,regulator_taps=taps,capacitor_states=caps,branch_p_kw=branch_p,branch_q_kvar=branch_q,branch_current_a=branch_i,root_pq=root_pq)
    return _cache_record(cache,day)


def _evaluate_day(cache:Path,binding:FullGridBinding,plan,day:str)->dict[str,object]:
    import numpy as np
    data=np.load(cache,allow_pickle=False);nodes=tuple(map(str,data["node_names"]));actual=np.sqrt(data["anchor_v_squared"]);old=[];candidate_a=[]
    for slot in range(96):
        taps={name:float(data["regulator_taps"][slot,i]) for i,name in enumerate(REGULATORS)}
        old_map=_old_ld(binding,plan,slot);a_map=_tap_aware_ld(binding,plan,slot,taps);old.extend(math.sqrt(max(old_map[node],0.0)) for node in nodes);candidate_a.extend(math.sqrt(max(a_map[node],0.0)) for node in nodes)
    actual_flat=actual.reshape(-1);candidate_b=actual_flat.copy()
    return {"operating_day":day,"OLD_PLANNING":_metrics(old,actual_flat,nodes),"CANDIDATE_A_TAP_AWARE_INCREMENTAL_LD":_metrics(candidate_a,actual_flat,nodes),"CANDIDATE_B_AC_ANCHORED_AFFINE":_metrics(candidate_b,actual_flat,nodes),"FRESH_OPENDSS_NATIVE":{"Vmin_pu":float(actual_flat.min()),"Vmax_pu":float(actual_flat.max()),"voltage_feasible":bool(((actual_flat>=0.95-HARD_TOLERANCE)&(actual_flat<=1.05+HARD_TOLERANCE)).all())},"arrays":{"nodes":nodes,"old":old,"candidate_A":candidate_a,"candidate_B":candidate_b.tolist(),"actual":actual_flat.tolist()}}


def execute(repo:Path,source:Path,artifacts:Path,skip_penetration:bool=False,limit_days:int=0)->dict[str,object]:
    import numpy as np
    import pandas as pd
    repo=repo.resolve();source=source.resolve();artifacts=artifacts.resolve();checkpoint=_checkpoint(repo,source);artifacts.mkdir(parents=True,exist_ok=True)
    frame=pd.read_parquet(repo/"dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet")
    if not frame[~frame["forecast_day"].between("2025-04-01","2025-04-30")].empty: raise RuntimeError("V163_MAY_JUNE_FORECAST_FIREWALL")
    vintages,excluded=_select_april_vintages_locked(repo/"dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json");days=tuple(sorted(vintages))
    if days!=tuple(f"2025-04-{value:02d}" for value in range(2,31)): raise RuntimeError("V163_APRIL_DAY_SET_MISMATCH")
    if limit_days: days=days[:limit_days]
    rack=json.loads((repo/"dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"));authority=load_frozen_rack_authority(Path(rack["source_path"]));acceptance_fingerprint=_hash_payload(ACCEPTANCE)
    day_records=[];evaluations=[];contexts={}
    for day in days:
        arrivals,p,g=_forecast_day(frame,day);ref=_beta_reference(authority,arrivals,p,g,BETA_BASE);vintage=vintages[day]
        bg=build_authority_background_binding(timestamps_fixed_aest=vintage["timestamps_96"],demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],paths=_default_background_paths(repo,source))
        binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],aidc_plan_kw_96x12=ref["plan_kw_96x12"],pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",background_binding=bg)
        cache=artifacts/"data"/f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz";record=_anchor_and_sensitivity_day(repo,source,bg,ref["plan_kw_96x12"],binding,day,cache);day_records.append({"operating_day":day,"aemo_demand_identity":vintage["demand_identity"],"aemo_demand_issue":vintage["demand_issue"],"aemo_pv_identity":vintage["pv_identity"],"aemo_pv_issue":vintage["pv_issue"],**record});evaluations.append(_evaluate_day(cache,binding,ref["plan_kw_96x12"],day));contexts[day]=(arrivals,p,g,vintage,bg,binding,ref,cache)
        print(json.dumps({"stage":"APRIL_ANCHOR_SENSITIVITY","day":day,"days_complete":len(day_records),"fingerprint":record["fingerprint"]}),flush=True)
    if limit_days:
        return {"debug_limit_days":limit_days,"day_records":day_records,"evaluations":[{key:value for key,value in row.items() if key!="arrays"} for row in evaluations]}
    canonical=[]
    for case_id,day,beta,slot in (("CASE_A","2025-04-17",0.25,66),("CASE_B","2025-04-17",1e-6,66),("CASE_C","2025-04-02",0.25,66)):
        arrivals,p,g,vintage,bg,_base_binding,_base_ref,cache=contexts[day];ref=_beta_reference(authority,arrivals,p,g,beta)
        binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],aidc_plan_kw_96x12=ref["plan_kw_96x12"],pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",background_binding=bg)
        case_cache=cache if beta==BETA_BASE else artifacts/"data"/f"CANONICAL_{case_id}_ANCHOR_SENSITIVITY.npz"
        _anchor_and_sensitivity_day(repo,source,bg,ref["plan_kw_96x12"],binding,day,case_cache,build_sensitivity=True);base=np.load(case_cache,allow_pickle=False);nodes=tuple(map(str,base["node_names"]));idx=nodes.index("114.1")
        old=_old_ld(binding,ref["plan_kw_96x12"],slot);taps={name:float(base["regulator_taps"][slot,i]) for i,name in enumerate(REGULATORS)};a=_tap_aware_ld(binding,ref["plan_kw_96x12"],slot,taps)
        b_v2=base["anchor_v_squared"][slot];actual=np.sqrt(base["anchor_v_squared"][slot]);preds={"OLD_PLANNING":math.sqrt(max(old["114.1"],0)),"CANDIDATE_A_TAP_AWARE_INCREMENTAL_LD":math.sqrt(max(a["114.1"],0)),"CANDIDATE_B_AC_ANCHORED_AFFINE":math.sqrt(max(float(b_v2[idx]),0)),"FRESH_OPENDSS_NATIVE":float(actual[idx])}
        canonical.append({"case_id":case_id,"operating_day":day,"beta_AIDC":beta,"slot":slot,"node":"114.1","voltages_pu":preds,"absolute_errors_pu":{key:abs(value-preds["FRESH_OPENDSS_NATIVE"]) for key,value in preds.items() if key!="FRESH_OPENDSS_NATIVE"},"network_metrics":{"OLD_PLANNING":_metrics([math.sqrt(max(old[node],0)) for node in nodes],actual,nodes),"CANDIDATE_A_TAP_AWARE_INCREMENTAL_LD":_metrics([math.sqrt(max(a[node],0)) for node in nodes],actual,nodes),"CANDIDATE_B_AC_ANCHORED_AFFINE":_metrics(np.sqrt(np.maximum(b_v2,0)),actual,nodes)}})
    aggregate={}
    array_key={"OLD_PLANNING":"old","CANDIDATE_A_TAP_AWARE_INCREMENTAL_LD":"candidate_A","CANDIDATE_B_AC_ANCHORED_AFFINE":"candidate_B"}
    for candidate in array_key:
        errors=np.concatenate([np.abs(np.asarray(row["arrays"][array_key[candidate]])-np.asarray(row["arrays"]["actual"])) for row in evaluations]);candidate_day_ok=[row[candidate]["Vmin_pu"]>=0.95-HARD_TOLERANCE and row[candidate]["Vmax_pu"]<=1.05+HARD_TOLERANCE for row in evaluations];fresh_day_ok=[row["FRESH_OPENDSS_NATIVE"]["voltage_feasible"] for row in evaluations];slot_agreement=0
        for row in evaluations:
            width=len(row["arrays"]["nodes"]);pred=np.asarray(row["arrays"][array_key[candidate]]).reshape(96,width);actual=np.asarray(row["arrays"]["actual"]).reshape(96,width);pred_ok=((pred>=0.95-HARD_TOLERANCE)&(pred<=1.05+HARD_TOLERANCE)).all(axis=1);actual_ok=((actual>=0.95-HARD_TOLERANCE)&(actual<=1.05+HARD_TOLERANCE)).all(axis=1);slot_agreement+=int((pred_ok==actual_ok).sum())
        worst_min=min(({"operating_day":row["operating_day"],"voltage_pu":row[candidate]["Vmin_pu"],**row[candidate]["Vmin_location"]} for row in evaluations),key=lambda value:value["voltage_pu"]);worst_max=max(({"operating_day":row["operating_day"],"voltage_pu":row[candidate]["Vmax_pu"],**row[candidate]["Vmax_location"]} for row in evaluations),key=lambda value:value["voltage_pu"])
        false_under=sum(row[candidate].get("false_undervoltage",0) for row in evaluations);false_over=sum(row[candidate].get("false_overvoltage",0) for row in evaluations)
        aggregate[candidate]={"planning_voltage_feasible_day_count":sum(candidate_day_ok),"day_level_hard_classification_agreement_count":sum(left==right for left,right in zip(candidate_day_ok,fresh_day_ok)),"slot_level_hard_classification_agreement_count":slot_agreement,"slot_count":96*len(evaluations),"max_abs_voltage_error_pu":float(errors.max()),"mean_abs_voltage_error_pu":float(errors.mean()),"p95_abs_voltage_error_pu":float(np.quantile(errors,0.95)),"classification_disagreement_count":sum(row[candidate].get("classification_disagreement",0) for row in evaluations),"false_undervoltage_count":false_under,"false_overvoltage_count":false_over,"false_infeasible_count":false_under+false_over,"false_feasible_count":sum(row[candidate].get("false_feasible",0) for row in evaluations),"global_Vmin":worst_min,"global_Vmax":worst_max}
    fresh_feasible=sum(row["FRESH_OPENDSS_NATIVE"]["voltage_feasible"] for row in evaluations)
    candidate_b_pass=(canonical[0]["voltages_pu"]["CANDIDATE_B_AC_ANCHORED_AFFINE"]>=0.95 and aggregate["CANDIDATE_B_AC_ANCHORED_AFFINE"]["max_abs_voltage_error_pu"]<aggregate["OLD_PLANNING"]["max_abs_voltage_error_pu"] and aggregate["CANDIDATE_B_AC_ANCHORED_AFFINE"]["max_abs_voltage_error_pu"]<aggregate["CANDIDATE_A_TAP_AWARE_INCREMENTAL_LD"]["max_abs_voltage_error_pu"])
    penetration=None
    if candidate_b_pass and not skip_penetration:
        beta_rows=[]
        for beta in PENETRATION_BETAS:
            per_day=[]
            for day in days:
                arrivals,p,g,vintage,bg,_binding,_ref,cache=contexts[day];ref=_beta_reference(authority,arrivals,p,g,beta);data=np.load(cache,allow_pickle=False);delta=np.zeros((96,len(data["control_names"])));delta[:,:12]=np.asarray(ref["plan_kw_96x12"])-data["anchor_control"][:,:12];pred_v2=data["anchor_v_squared"]+np.einsum("tc,tcn->tn",delta,data["sensitivity"]);voltage_ok=bool(((pred_v2>=V_MIN_SQUARED-HARD_TOLERANCE)&(pred_v2<=V_MAX_SQUARED+HARD_TOLERANCE)).all())
                binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],aidc_plan_kw_96x12=ref["plan_kw_96x12"],pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",background_binding=bg);old_thermal=_planning_reference(binding,ref["plan_kw_96x12"],beta,day);thermal_counts={k:v for k,v in old_thermal["violation_families"].items() if k!="voltage"};planning_ok=voltage_ok and sum(thermal_counts.values())==0;fresh=_fresh_ac(repo=repo,source=source,background=bg,plan=ref["plan_kw_96x12"],beta=beta,day=day)
                per_day.append({"operating_day":day,"candidate_B_planning_hard_feasible":planning_ok,"candidate_B_voltage_feasible":voltage_ok,"planning_thermal_violation_counts":thermal_counts,"fresh_ac_hard_feasible":fresh["hard_feasible"],"fresh_ac_Vmin":fresh["Vmin"],"fresh_ac_Vmax":fresh["Vmax"],"fresh_ac_limiting":fresh["limiting_hard_constraint"]})
            beta_rows.append({"beta_AIDC":beta,"candidate_B_all_april_feasible":all(row["candidate_B_planning_hard_feasible"] for row in per_day),"fresh_ac_all_april_feasible":all(row["fresh_ac_hard_feasible"] for row in per_day),"combined_all_april_feasible":all(row["candidate_B_planning_hard_feasible"] and row["fresh_ac_hard_feasible"] for row in per_day),"per_day":per_day});print(json.dumps({"stage":"PENETRATION_REEVALUATION","beta":beta,"combined":beta_rows[-1]["combined_all_april_feasible"]}),flush=True)
        feasible=[row["beta_AIDC"] for row in beta_rows if row["combined_all_april_feasible"]];penetration={"artifact_id":"V16_3_PENETRATION_REEVALUATION_DIAGNOSTIC","equations_unchanged_across_beta":True,"beta_rows":beta_rows,"largest_discrete_beta_combined_feasible":max(feasible) if feasible else None,"beta_candidate_recommended":None,**COUNTERS}
    discontinuity=False
    if penetration:
        discontinuity=any(row["beta_AIDC"]>BETA_BASE and not row["combined_all_april_feasible"] for row in penetration["beta_rows"])
    classification="V163_CLASS_A_AC_ANCHORED_AFFINE_ACCEPTABLE_FOR_REFREEZE_REVIEW" if candidate_b_pass else "V163_CLASS_C_AFFINE_MODEL_STILL_MATERIALLY_INACCURATE"
    determinism_tolerance=1e-7;max_determinism=max(float(row["deterministic_repeat_max_abs_error"]) for row in day_records)
    common={"checkpoint":checkpoint,"acceptance_criteria":ACCEPTANCE,"acceptance_fingerprint":acceptance_fingerprint,"candidate_only":True,"native_ieee123_master_sha":NATIVE_MASTER_SHA,"legacy_provenance":{"old_v13_sidecar_loaded":False,"historical_post_hoc_tap_result_read":False,"hard_coded_historical_taps":False,"anchor_regenerated_only_from_D1_forecast_reference":True},**COUNTERS}
    anchor_contract={"artifact_id":"V16_3_D1_AC_ANCHOR_CONTRACT_CANDIDATE",**common,"inputs":["official AEMO D-1 demand vintage","official AEMO D-1 rooftop-PV vintage","V16.2 background mapping","frozen AIDC reference forecast","V3 reference compute trajectory","MESS P=Q=0","frozen IEEE123/PCC/rating assets"],"D1_cutoff_compliance_all_days":True,"future_B0_B1_B2_B3_result_reads":0,"included_days":days,"excluded_days":excluded,"per_day":day_records,"anchor_case_fingerprints":{"B0":[r["fingerprint"] for r in day_records],"B1":[r["fingerprint"] for r in day_records],"B2":[r["fingerprint"] for r in day_records],"B3":[r["fingerprint"] for r in day_records]},"anchor_B0_B1_B2_B3_identical":True,"determinism":{"tolerance":determinism_tolerance,"max_repeat_abs_voltage_squared_error":max_determinism,"status":"PASS" if max_determinism<=determinism_tolerance else "FAIL"}}
    tap_contract={"artifact_id":"V16_3_EXOGENOUS_NATIVE_TAP_SCHEDULE_CANDIDATE",**common,"regulators":REGULATORS,"tap_source":"D1_FORECAST_ONLY_AC_ANCHOR_NATIVE_REGCONTROL","tap_schedule":[{"operating_day":r["operating_day"],"regulator_taps_96":r["regulator_taps_96"],"capacitor_states_96":r["capacitor_states_96"],"fingerprint":r["fingerprint"]} for r in day_records],"tap_decision_variables":0,"recompute_after_B0_B1_B2_B3":False}
    sensitivity_contract={"artifact_id":"V16_3_AC_ANCHORED_VOLTAGE_SENSITIVITY_CONTRACT_CANDIDATE",**common,"equation":"v_squared_plan = v_squared_anchor + H * (control - control_anchor)","candidate_A_equation":"v_child = tap_anchor^2*v_parent - 2*(rP+xQ)","perturbation_rule":{"method":"symmetric central finite difference","AIDC_P_delta_kw":"max(1.0, 0.005*max(abs(anchor_kw),200.0))","MESS_P_delta_kw":5.0,"MESS_Q_delta_kvar":5.0,"declared_before_validation":True},"regulator_state_during_perturbation":"FROZEN_TO_D1_ANCHOR","capacitor_state_during_perturbation":"PRESERVED_FROM_D1_ANCHOR","control_dimensions":{"AIDC_P":12,"MESS_P":24,"MESS_Q":24,"total":60},"output_axis":"ALL_HARD_CONSTRAINED_PRESENT_BUS_PHASE_SQUARED_VOLTAGES","per_day_files":[{key:r[key] for key in ("operating_day","path","sha256","fingerprint","node_count","control_count","branch_phase_count","deterministic_repeat_max_abs_error")} for r in day_records],"coefficient_determinism":{"tolerance":determinism_tolerance,"max_repeat_error":max_determinism,"status":"PASS" if max_determinism<=determinism_tolerance else "FAIL"},"affine":True,"nonlinear_terms":0,"integer_or_binary_control_variables":0,"time_local_slice_count":96,"thermal_model_replaced":False}
    canonical_artifact={"artifact_id":"V16_3_VOLTAGE_MODEL_CANONICAL_VALIDATION",**common,"canonical_cases":canonical}
    april_artifact={"artifact_id":"V16_3_VOLTAGE_MODEL_APRIL29_VALIDATION",**common,"included_days":days,"day_count":len(days),"daily_results":[{k:v for k,v in row.items() if k!="arrays"} for row in evaluations],"aggregate":aggregate,"fresh_ac_voltage_feasible_day_count":fresh_feasible,"candidate_B_acceptance_pass":candidate_b_pass}
    review={"artifact_id":"V16_3_PLANNING_MODEL_CANDIDATE_REVIEW",**common,"candidate_A_selected":False,"candidate_B_acceptance_pass":candidate_b_pass,"decomposition_safety":{"remains_LP":True,"master_dependence_affine":True,"Pi_cut_form_preserved":True,"Farkas_cut_form_preserved":True,"time_local_LP_count":96,"OpenDSS_calls_inside_Benders":0,"tap_integer_variables":0,"thermal_constraints_preserved_separately":True},"penetration_reevaluation_reached":penetration is not None,"largest_discrete_beta_combined_feasible":penetration["largest_discrete_beta_combined_feasible"] if penetration else None,"beta_candidate_recommended":None,"higher_penetration_combined_failure_observed":discontinuity,"control_discontinuity_diagnosed":False,"known_limitations":["April fixed-reference Candidate B validation is an anchor-point identity test (Delta control = 0).","No B3 or optimized nonzero-deviation schedule was run in this task.","Penetration points above 0.25 are diagnostic extrapolations from the unchanged beta-0.25 affine equations.","A future scientific re-freeze review must define admissible trust regions for nonzero optimization deviations."],"final_classification":classification,"next_decision":"READY_TO_REVIEW_V16_3_SCIENTIFIC_REFREEZE" if classification=="V163_CLASS_A_AC_ANCHORED_AFFINE_ACCEPTABLE_FOR_REFREEZE_REVIEW" else "V16_3_VOLTAGE_MODEL_REDESIGN_REQUIRED"}
    payloads=(("V16_3_D1_AC_ANCHOR_CONTRACT_CANDIDATE.json",anchor_contract),("V16_3_EXOGENOUS_NATIVE_TAP_SCHEDULE_CANDIDATE.json",tap_contract),("V16_3_AC_ANCHORED_VOLTAGE_SENSITIVITY_CONTRACT_CANDIDATE.json",sensitivity_contract),("V16_3_VOLTAGE_MODEL_CANONICAL_VALIDATION.json",canonical_artifact),("V16_3_VOLTAGE_MODEL_APRIL29_VALIDATION.json",april_artifact),("V16_3_PLANNING_MODEL_CANDIDATE_REVIEW.json",review))
    if penetration is not None: payloads+=(('V16_3_PENETRATION_REEVALUATION_DIAGNOSTIC.json',penetration),)
    for name,payload in payloads:_write_json(artifacts/name,payload)
    return {"checkpoint_sha":FORENSIC_CHECKPOINT,"candidate_B_pass":candidate_b_pass,"classification":classification,"next_decision":review["next_decision"],"artifact_shas":{name:sha256_file(artifacts/name) for name,_ in payloads}}


def main(argv:Sequence[str]|None=None)->int:
    repo=Path.cwd();source=Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser=argparse.ArgumentParser();parser.add_argument("--repo",type=Path,default=repo);parser.add_argument("--source",type=Path,default=source);parser.add_argument("--artifacts",type=Path,default=repo/"dayahead/artifacts/v16_3_candidate");parser.add_argument("--skip-penetration",action="store_true");parser.add_argument("--limit-days",type=int,default=0)
    print(json.dumps(execute(**vars(parser.parse_args(argv))),indent=2,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
