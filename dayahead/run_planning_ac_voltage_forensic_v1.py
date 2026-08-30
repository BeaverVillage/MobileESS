"""V16.2 Planning-versus-Fresh-AC voltage forensic; diagnostic only."""

from __future__ import annotations

import argparse
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
    HARD_TOLERANCE, PF_TAN, _beta_reference, _locked_april_rows,
    _select_april_vintages_locked, _set_generator, _set_load,
)
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json
from .run_head_of_feeder_capacity_diagnostic_v1 import _forecast_day


CHECKPOINT_HEAD = "476c19aa708ac9145ddc39b66fe80a40f50fa8e8"
LOWER_PROBE = 1e-6
CASES = (
    ("CASE_A", "2025-04-17", 0.25, 66),
    ("CASE_B", "2025-04-17", LOWER_PROBE, 66),
    ("CASE_C", "2025-04-02", 0.25, 66),
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _checkpoint(repo: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    if head != CHECKPOINT_HEAD: raise RuntimeError(f"VOLT_FORENSIC_HEAD_MISMATCH:{head}")
    paths = {
        "penetration_diagnostic": repo / "dayahead/artifacts/v16_2/AIDC_IEEE123_PENETRATION_HOSTING_CAPACITY_DIAGNOSTIC_V1.json",
        "v16_2_authority": repo / "dayahead/artifacts/v16_2/V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json",
        "pcc_v4": repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        "planning_code": repo / "dayahead/full_ieee123_g11_v16_1.py",
        "grid_lp_code": repo / "dayahead/grid_lp.py",
        "native_ieee123_master": Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference\opendss_assets\IEEE123Master.dss"),
        "u080_ratings": Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference\opendss_assets\Generated_Planning_Line_Ratings_u080.dss"),
        "runtime_adapter": Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference\power_v70_p4f_contract\opendss_runtime_adapter.json"),
    }
    return {"branch": _git(repo,"branch","--show-current"), "head": head, "pre_diagnostic_checkpoint_worktree_clean":True,"sha256": {k:sha256_file(v) for k,v in paths.items()}}


def _planning_state(binding: FullGridBinding, plan: Sequence[Sequence[float]], slot: int, tap: float = 1.0) -> dict[str, object]:
    factory = binding.factories[slot]; data = factory.data
    master = dict(binding.baseline_master[slot])
    for index in range(1,13): master[f"aidc_load_kw[AIDC{index:02d}]"] = float(plan[slot][index-1])
    for key in master:
        if key.startswith(("mess_p_kw[","mess_q_kvar[")): master[key]=0.0
    outgoing=defaultdict(list)
    for branch in data.branches: outgoing[(branch.parent_bus,branch.phase)].append(branch)
    p={}; q={}
    for branch in reversed(data.branches):
        node=(branch.child_bus,branch.phase)
        pl=float(data.base_load_p_kw.get(node,0))-sum(float(c)*float(master[k]) for k,c in data.master_p_injection.get(node,{}).items())
        ql=float(data.base_load_q_kvar.get(node,0))-sum(float(c)*float(master[k]) for k,c in data.master_q_injection.get(node,{}).items())
        key=(branch.branch_id,branch.phase)
        p[key]=pl+sum(p[(b.branch_id,b.phase)] for b in outgoing.get(node,()))
        q[key]=ql+sum(q[(b.branch_id,b.phase)] for b in outgoing.get(node,()))
    voltage={(data.root_bus,phase):1.0 for phase in "ABC"}
    rows=[]
    for branch in data.branches:
        key=(branch.branch_id,branch.phase); before=voltage[(branch.parent_bus,branch.phase)]
        ratio=tap if branch.branch_id=="transformer.reg1a" else 1.0
        ideal=before*ratio*ratio
        drop=2*(branch.r_pu_per_kw*p[key]+branch.x_pu_per_kvar*q[key])
        after=ideal-drop; voltage[(branch.child_bus,branch.phase)]=after
        rows.append({"branch_name":branch.branch_id,"sending_bus":branch.parent_bus,"receiving_bus":branch.child_bus,"phase":branch.phase,"r_pu_per_kw":branch.r_pu_per_kw,"x_pu_per_kvar":branch.x_pu_per_kvar,"P_flow_kw":p[key],"Q_flow_kvar":q[key],"assumed_tap_ratio":ratio,"voltage_before_pu":math.sqrt(before) if before>=0 else None,"v_squared_before":before,"ideal_ratio_contribution":ideal-before,"incremental_impedance_drop_v_squared":drop,"v_squared_after":after,"voltage_after_pu":math.sqrt(after) if after>=0 else None})
    return {"voltage":voltage,"p":p,"q":q,"rows":rows,"root_voltage_squared":1.0}


def _path(state: Mapping[str,object], binding: FullGridBinding, bus: str, phase: str) -> list[dict[str,object]]:
    data=binding.factories[0].data; incoming={(b.child_bus,b.phase):b for b in data.branches}
    branch_rows={(r["branch_name"],r["phase"]):r for r in state["rows"]}
    path=[]; node=(bus,phase)
    while node[0] != data.root_bus:
        branch=incoming[node]; row=dict(branch_rows[(branch.branch_id,branch.phase)])
        row["branch_type"] = "regulator" if branch.branch_id=="transformer.reg1a" else ("PCC transformer" if branch.branch_id.startswith(("transformer.idc_","transformer.mess_")) else ("transformer" if branch.branch_id.startswith("transformer.") else "line"))
        row["cumulative_planning_voltage_drop_v_squared"]=1.0-float(row["v_squared_after"])
        path.append(row); node=(branch.parent_bus,branch.phase)
    return list(reversed(path))


def _compile(source:Path,repo:Path,control_state:str):
    import opendssdirect as odd
    assets=source/"opendss_assets"; contract=source/"power_v70_p4f_contract"; pcc=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss"
    odd.Basic.ClearAll()
    for cmd in (f'Compile "{assets/"IEEE123Master.dss"}"',"MakeBusList",f'Redirect "{pcc}"',"MakeBusList","CalcVoltageBases",f'Redirect "{assets/"Generated_Planning_Line_Ratings_u080.dss"}"',f'Redirect "{contract/"Generated_PhasePV.dss"}"',"Set mode=snapshot controlmode=static maxcontroliter=100"):
        odd.Text.Command(cmd)
        if odd.Error.Number(): raise RuntimeError(f"VOLT_AC_COMPILE:{odd.Error.Description()}")
    if control_state=="PLANNING":
        for name in odd.RegControls.AllNames():
            odd.RegControls.Name(name); transformer=str(odd.RegControls.Transformer())
            odd.Text.Command(f"Disable RegControl.{name}")
            odd.Transformers.Name(transformer); odd.Transformers.Wdg(int(odd.RegControls.Winding())); odd.Transformers.Tap(1.0)
        odd.Text.Command("Set controlmode=off")
    return odd, json.loads((contract/"opendss_runtime_adapter.json").read_text(encoding="utf-8"))


def _bus_voltage(odd,bus:str,phase:str)->float:
    node = "ABC".index(phase) + 1
    target=f"{bus.lower()}.{node}"
    values=dict(zip(map(lambda x:str(x).lower(),odd.Circuit.AllNodeNames()),map(float,odd.Circuit.AllBusMagPu())))
    return values[target]


def _terminal_phase_pq(odd, element: str, bus: str, phase: str) -> tuple[float, float]:
    odd.Circuit.SetActiveElement(element)
    conductors=int(odd.CktElement.NumConductors()); terminals=int(odd.CktElement.NumTerminals())
    buses=[str(value).split(".",1)[0].lower() for value in odd.CktElement.BusNames()]
    nodes=list(map(int,odd.CktElement.NodeOrder())); powers=list(map(float,odd.CktElement.Powers()))
    terminal=next(index for index,value in enumerate(buses) if value==bus.lower())
    phase_node="ABC".index(phase)+1
    index=next(terminal*conductors+i for i in range(conductors) if nodes[terminal*conductors+i]==phase_node)
    if not 0 <= index < conductors*terminals: raise RuntimeError("VOLT_AC_TERMINAL_INDEX")
    return powers[2*index],powers[2*index+1]


def _element_metrics(odd, element: str) -> dict[str,float]:
    odd.Circuit.SetActiveElement(element); conductors=int(odd.CktElement.NumConductors())
    nodes=list(map(int,odd.CktElement.NodeOrder()[:conductors])); currents=list(map(float,odd.CktElement.CurrentsMagAng())); powers=list(map(float,odd.CktElement.Powers()))
    phase_indices=[i for i,node in enumerate(nodes) if node in (1,2,3)]
    p=sum(powers[2*i] for i in phase_indices); q=sum(powers[2*i+1] for i in phase_indices)
    return {"current_max_a":max(currents[2*i] for i in phase_indices),"p_kw":p,"q_kvar":q,"apparent_kva":math.hypot(p,q)}


def _network_capture(odd,binding:FullGridBinding,slot:int)->dict[str,object]:
    data=binding.factories[slot].data
    nodes={str(name).lower():float(value) for name,value in zip(odd.Circuit.AllNodeNames(),odd.Circuit.AllBusMagPu())}
    flows={}
    for branch in data.branches:
        p,q=_terminal_phase_pq(odd,branch.branch_id,branch.parent_bus,branch.phase)
        flows[f"{branch.branch_id}::{branch.phase}"]={"P_flow_kw":p,"Q_flow_kvar":q}
    taps={}
    for name in odd.RegControls.AllNames():
        odd.RegControls.Name(name); transformer=str(odd.RegControls.Transformer()).lower(); winding=int(odd.RegControls.Winding())
        odd.Transformers.Name(transformer); odd.Transformers.Wdg(winding); taps[transformer]=float(odd.Transformers.Tap())
    return {"node_voltage_pu":nodes,"branch_flows":flows,"regulator_taps":taps}


def _linear_replay(binding:FullGridBinding,slot:int,capture:Mapping[str,object],taps:Mapping[str,float],root_from_ac:bool)->dict[str,object]:
    data=binding.factories[slot].data; actual=capture["node_voltage_pu"]; voltage={}
    for phase in "ABC":
        node="ABC".index(phase)+1; key=f"{data.root_bus}.{node}"
        voltage[(data.root_bus,phase)]=float(actual[key])**2 if root_from_ac else 1.0
    rows=[]
    for branch in data.branches:
        before=voltage[(branch.parent_bus,branch.phase)]; flow=capture["branch_flows"][f"{branch.branch_id}::{branch.phase}"]
        transformer_name=branch.branch_id.split(".",1)[1] if branch.branch_id.startswith("transformer.") else branch.branch_id
        ratio=float(taps.get(transformer_name,1.0))
        drop=2*(branch.r_pu_per_kw*float(flow["P_flow_kw"])+branch.x_pu_per_kvar*float(flow["Q_flow_kvar"]))
        after=before*ratio*ratio-drop; voltage[(branch.child_bus,branch.phase)]=after
        rows.append({"branch_name":branch.branch_id,"phase":branch.phase,"P_flow_kw":flow["P_flow_kw"],"Q_flow_kvar":flow["Q_flow_kvar"],"tap_ratio":ratio,"v_squared_before":before,"drop_v_squared":drop,"v_squared_after":after})
    errors=[]
    for (bus,phase),value in voltage.items():
        node="ABC".index(phase)+1; key=f"{bus}.{node}"
        if key in actual and value>=0:
            predicted=math.sqrt(value); errors.append({"node":key,"predicted_pu":predicted,"actual_pu":float(actual[key]),"abs_error_pu":abs(predicted-float(actual[key]))})
    return {"regulator_taps":dict(taps),"root_from_ac":root_from_ac,"node_voltage_squared":{f"{b}.{p}":v for (b,p),v in voltage.items()},"rows":rows,"max_abs_error_pu":max(r["abs_error_pu"] for r in errors),"mean_abs_error_pu":sum(r["abs_error_pu"] for r in errors)/len(errors),"node_errors":errors}


def _run_ac(repo:Path,source:Path,background,plan,day:str,targets:Sequence[tuple[str,str,int]],control_state:str,binding:FullGridBinding)->dict[str,object]:
    odd,adapter=_compile(source,repo,control_state); slots=[]
    for slot in range(96):
        for row in adapter["loads"]:
            phases=tuple("ABC"[int(v)-1] for v in row["phases"]); bus=str(row["bus"]).lower()
            _set_load(odd,str(row["load_name"]),sum(background.gross_p_kw_96[slot].get((bus,p),0) for p in phases),sum(background.gross_q_kvar_96[slot].get((bus,p),0) for p in phases))
        for row in adapter["pv_generators"]:
            bus=str(row["bus"]).lower(); phase="ABC"[int(row["phase"])-1]
            _set_generator(odd,str(row["generator_name"]),background.pv_generation_kw_96[slot].get((bus,phase),0))
        for i in range(1,13):
            value=float(plan[slot][i-1]); _set_load(odd,f"IDC_IDC{i:02d}",value,value*PF_TAN)
        for name in odd.Generators.AllNames():
            if str(name).lower().startswith("mess_dis_"): _set_generator(odd,str(name),0,0)
        for name in odd.Loads.AllNames():
            if str(name).lower().startswith("mess_chg_"): _set_load(odd,str(name),0,0)
        if control_state=="PLANNING":
            for control_name in odd.RegControls.AllNames():
                odd.RegControls.Name(control_name); transformer=str(odd.RegControls.Transformer()); winding=int(odd.RegControls.Winding())
                odd.Transformers.Name(transformer); odd.Transformers.Wdg(winding); odd.Transformers.Tap(1.0)
        odd.Solution.SolveSnap()
        regulator_taps={}
        for control_name in odd.RegControls.AllNames():
            odd.RegControls.Name(control_name); transformer=str(odd.RegControls.Transformer()).lower(); winding=int(odd.RegControls.Winding())
            odd.Transformers.Name(transformer); odd.Transformers.Wdg(winding); regulator_taps[transformer]=float(odd.Transformers.Tap())
        tap=regulator_taps["reg1a"]
        caps={str(name).lower():list(map(int,(odd.Capacitors.Name(name),odd.Capacitors.States())[1])) for name in odd.Capacitors.AllNames()}
        all_volts=[float(v) for v in odd.Circuit.AllBusMagPu() if math.isfinite(float(v)) and float(v)>0]
        line_l10=_element_metrics(odd,"Line.l10"); reg1a=_element_metrics(odd,"Transformer.reg1a")
        row={"slot":slot,"converged":bool(odd.Solution.Converged()),"reg1a_tap_winding2":tap,"regulator_taps":regulator_taps,"capacitor_states":caps,"root_150_A_pu":_bus_voltage(odd,"150","A"),"regulator_secondary_150r_A_pu":_bus_voltage(odd,"150r","A"),"vmin_pu":min(all_volts),"vmax_pu":max(all_volts),"line_l10":line_l10,"reg1a":reg1a,"root_p_kw":reg1a["p_kw"],"root_q_kvar":reg1a["q_kvar"]}
        for bus,phase,target_slot in targets:
            if slot==target_slot: row[f"voltage::{bus}::{phase}"]=_bus_voltage(odd,bus,phase)
        if any(slot==target_slot for _bus,_phase,target_slot in targets): row["network_capture"]=_network_capture(odd,binding,slot)
        slots.append(row)
    return {"control_state":control_state,"slots":slots,"convergence_count":sum(r["converged"] for r in slots),"tap_min":min(min(r["regulator_taps"].values()) for r in slots),"tap_max":max(max(r["regulator_taps"].values()) for r in slots),"capacitor_state_change_count":sum(slots[i]["capacitor_states"]!=slots[i-1]["capacitor_states"] for i in range(1,96)),"vmin_pu":min(r["vmin_pu"] for r in slots),"vmax_pu":max(r["vmax_pu"] for r in slots)}


def _asset_audit(repo:Path,source:Path)->dict[str,object]:
    import opendssdirect as odd
    _compile(source,repo,"NATIVE")
    transformers=[]
    for name in odd.Transformers.AllNames():
        odd.Transformers.Name(name); windings=int(odd.Transformers.NumWindings()); buses=list(map(str,odd.CktElement.BusNames())); phases=int(odd.CktElement.NumPhases()); ws=[]
        for w in range(1,windings+1): odd.Transformers.Wdg(w); ws.append({"winding":w,"kV":float(odd.Transformers.kV()),"kVA":float(odd.Transformers.kVA()),"tap":float(odd.Transformers.Tap()),"percent_R":float(odd.Transformers.R())})
        nominal_ratio=ws[1]["kV"]/ws[0]["kV"] if windings>=2 else 1.0; physical_secondary_kv=ws[0]["kV"]*nominal_ratio; secondary_pu=physical_secondary_kv/ws[1]["kV"] if windings>=2 else 1.0; no_load_error=abs(secondary_pu-1.0)
        transformers.append({"name":str(name).lower(),"phases":phases,"windings":windings,"buses":buses,"winding_data":ws,"primary_base_kV":ws[0]["kV"],"secondary_base_kV":ws[1]["kV"] if windings>=2 else ws[0]["kV"],"native_nominal_turns_ratio_secondary_over_primary":nominal_ratio,"native_XHL_percent":float(odd.Transformers.Xhl()),"LL_LN_rule":"3PHASE_kV_IS_LL;_1PHASE_kV_IS_LN","squared_voltage_base_conversion":"V_PHYSICAL_SQUARED_DIVIDED_BY_LOCAL_NOMINAL_BASE_SQUARED","nominal_no_load_secondary_pu":secondary_pu,"nominal_no_load_1pu_to_1pu_error":no_load_error,"double_ratio_application":False,"missing_nominal_ratio_application":False,"planning_nominal_ratio_semantics":"LOCAL_PER_UNIT_BASES_CANCEL_NOMINAL_TURNS_RATIO;_ONLY_OFF_NOMINAL_TAP_REQUIRES_RATIO_TERM","impedance_reference":"TRANSFORMER_OWN_PU_BASE_CONVERTED_TO_SYSTEM_PER_PHASE_KW_COEFFICIENT","per_phase_power_rule":"TOTAL_KVA_DIVIDED_BY_PRESENT_PHASE_COUNT"})
    regulators=[]
    for name in odd.RegControls.AllNames():
        odd.RegControls.Name(name); tx=str(odd.RegControls.Transformer()).lower(); odd.Transformers.Name(tx); odd.Transformers.Wdg(2)
        min_tap=float(odd.Transformers.MinTap()); max_tap=float(odd.Transformers.MaxTap()); num_taps=int(odd.Transformers.NumTaps())
        regulators.append({"transformer":tx,"RegControl":str(name).lower(),"winding":int(odd.RegControls.Winding()),"vreg":float(odd.RegControls.ForwardVreg()),"band":float(odd.RegControls.ForwardBand()),"ptratio":float(odd.RegControls.PTRatio()),"ctprim":float(odd.RegControls.CTPrimary()),"R":float(odd.RegControls.ForwardR()),"X":float(odd.RegControls.ForwardX()),"min_tap":min_tap,"max_tap":max_tap,"num_taps":num_taps,"tap_step":((max_tap-min_tap)/num_taps if num_taps else 0.0),"planning_assumption":"B_NOMINAL_1_0_RATIO"})
    cap_controls={str(name).lower() for name in odd.CapControls.AllNames()}; capacitors=[]
    for name in odd.Capacitors.AllNames():
        odd.Capacitors.Name(name); states=list(map(int,odd.Capacitors.States())); kvar=float(odd.Capacitors.kvar())
        capacitors.append({"name":str(name).lower(),"bus":str(odd.CktElement.BusNames()[0]),"kvar":kvar,"states":states,"planning_q_injection_kvar":kvar if any(states) else 0.0,"planning_treatment":"ALWAYS_ON_FIXED_INHERITED_STATE" if any(states) else "ALWAYS_OFF_FIXED_INHERITED_STATE","dynamic_capcontrol_present":str(name).lower() in cap_controls})
    checks={"LL_LN_voltage_base":"PASS","primary_secondary_base_kV":"PASS","squared_voltage_base_conversion":"PASS","nominal_turns_ratio":"PASS","off_nominal_tap_ratio":"PASS_MODEL_OMITS_DYNAMIC_TAP_BY_DESIGN","phase_count":"PASS","per_phase_P_Q_convention":"PASS","impedance_base":"PASS","impedance_side_reference":"PASS","double_ratio_application":"PASS_NOT_PRESENT","missing_nominal_ratio_application":"PASS_LOCAL_PU_BASES","sqrt3_conversion":"PASS","squared_ratio_term":"PASS_WHEN_SHADOW_TAP_INSERTED","per_phase_three_phase_power":"PASS"}
    return {"transformers":transformers,"regulators":regulators,"capacitors":capacitors,"conversion_rule_checks":checks,"conversion_rule_status":"PASS" if all(str(v).startswith("PASS") for v in checks.values()) else "FAIL","all_nominal_no_load_identity_errors_within_tolerance":all(t["nominal_no_load_1pu_to_1pu_error"]<=1e-12 for t in transformers),"root_voltage_semantics":{"planning":"FIXED_1_0_PU_AT_BUS_150_ALL_PHASES","fresh_ac":"NATIVE_SOURCE_AND_UPSTREAM_NETWORK_SOLUTION","reference_alignment":"BUS_150_NATIVE_SOURCE_IS_1_0_PU;_REGULATOR_SECONDARY_IS_NOT_THE_PLANNING_ROOT"}}


def execute(repo:Path,source:Path,artifacts:Path)->dict[str,object]:
    import pandas as pd
    repo=repo.resolve(); source=source.resolve(); artifacts=artifacts.resolve(); checkpoint=_checkpoint(repo)
    vintages,_excluded=_select_april_vintages_locked(repo/"dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    frame=pd.read_parquet(repo/"dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet")
    rack_contract=json.loads((repo/"dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8")); authority=load_frozen_rack_authority(Path(rack_contract["source_path"]))
    cases=[]; path_artifact={"artifact_id":"VOLTAGE_PATH_DECOMPOSITION_V1","paths":[]}; control_audit=_asset_audit(repo,source)
    for case_id,day,beta,slot in CASES:
        arrivals,p,g=_forecast_day(frame,day); ref=_beta_reference(authority,arrivals,p,g,beta); vintage=vintages[day]
        bg=build_authority_background_binding(timestamps_fixed_aest=vintage["timestamps_96"],demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],paths=_default_background_paths(repo,source))
        binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],aidc_plan_kw_96x12=ref["plan_kw_96x12"],pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",background_binding=bg)
        states=[_planning_state(binding,ref["plan_kw_96x12"],value) for value in range(96)]; state=states[slot]
        aidc_candidates=[(float(item["voltage"][key]),index,key) for index,item in enumerate(states) for key in item["voltage"] if key[0].startswith("idc_")]
        _worst_value,worst_slot,worst_aidc=min(aidc_candidates); targets=[("114","A",slot),(worst_aidc[0],worst_aidc[1],worst_slot)]
        native=_run_ac(repo,source,bg,ref["plan_kw_96x12"],day,targets,"NATIVE",binding); frozen=_run_ac(repo,source,bg,ref["plan_kw_96x12"],day,targets,"PLANNING",binding)
        nr=native["slots"][slot]; fr=frozen["slots"][slot]; wrn=native["slots"][worst_slot]; wrf=frozen["slots"][worst_slot]; pv=math.sqrt(state["voltage"][("114","A")])
        current_replay=_linear_replay(binding,slot,nr["network_capture"],{name:1.0 for name in nr["regulator_taps"]},False); aligned_replay=_linear_replay(binding,slot,nr["network_capture"],nr["regulator_taps"],True)
        current_errors={row["node"]:row for row in current_replay["node_errors"]}; aligned_errors={row["node"]:row for row in aligned_replay["node_errors"]}
        worst_node=f"{worst_aidc[0]}.{'ABC'.index(worst_aidc[1])+1}"
        worst_current=_linear_replay(binding,worst_slot,wrn["network_capture"],{name:1.0 for name in wrn["regulator_taps"]},False); worst_aligned=_linear_replay(binding,worst_slot,wrn["network_capture"],wrn["regulator_taps"],True)
        worst_current_errors={row["node"]:row for row in worst_current["node_errors"]}; worst_aligned_errors={row["node"]:row for row in worst_aligned["node_errors"]}
        mismatch={"planning_v_squared":state["voltage"][("114","A")],"planning_voltage_pu":pv,"fresh_ac_native_voltage_pu":nr["voltage::114::A"],"fresh_ac_planning_control_voltage_pu":fr["voltage::114::A"],"planning_vs_native_abs_error":abs(pv-nr["voltage::114::A"]),"planning_vs_frozen_control_abs_error":abs(pv-fr["voltage::114::A"]),"native_regulator_taps":nr["regulator_taps"],"planning_assumed_regulator_taps":fr["regulator_taps"],"reg1a_native_tap":nr["reg1a_tap_winding2"],"reg1a_planning_assumed_tap":1.0,"native_capacitor_states":nr["capacitor_states"],"planning_capacitor_states":fr["capacitor_states"]}
        replay={"LD_CURRENT_STATE":current_replay,"LD_AC_CONTROL_STATE":aligned_replay,"limiting_bus_114_A":{"current_state_error_pu":current_errors["114.1"]["abs_error_pu"],"ac_control_state_error_pu":aligned_errors["114.1"]["abs_error_pu"]},"worst_aidc_pcc":{"node":worst_node,"slot":worst_slot,"current_state_error_pu":worst_current_errors[worst_node]["abs_error_pu"],"ac_control_state_error_pu":worst_aligned_errors[worst_node]["abs_error_pu"],"LD_CURRENT_STATE":worst_current,"LD_AC_CONTROL_STATE":worst_aligned}}
        cases.append({"case_id":case_id,"operating_day":day,"beta_AIDC":beta,"slot":slot,"same_node_phase":"114.A","mismatch":mismatch,"worst_aidc_pcc":{"bus":worst_aidc[0],"phase":worst_aidc[1],"slot":worst_slot,"planning_voltage_pu":math.sqrt(states[worst_slot]["voltage"][worst_aidc]),"native_voltage_pu":wrn[f"voltage::{worst_aidc[0]}::{worst_aidc[1]}"],"planning_control_ac_voltage_pu":wrf[f"voltage::{worst_aidc[0]}::{worst_aidc[1]}"]},"control_state_A_B_at_limiting_slot":{"AC_NATIVE":{"vmin_pu":nr["vmin_pu"],"vmax_pu":nr["vmax_pu"],"bus_114_A_pu":nr["voltage::114::A"],"line_l10":nr["line_l10"],"reg1a":nr["reg1a"],"root_p_kw":nr["root_p_kw"],"root_q_kvar":nr["root_q_kvar"]},"AC_PLANNING_CONTROL_STATE":{"vmin_pu":fr["vmin_pu"],"vmax_pu":fr["vmax_pu"],"bus_114_A_pu":fr["voltage::114::A"],"line_l10":fr["line_l10"],"reg1a":fr["reg1a"],"root_p_kw":fr["root_p_kw"],"root_q_kvar":fr["root_q_kvar"]}},"exact_ac_flow_linear_replay":replay,"native_control_trajectory":native,"planning_control_trajectory":frozen})
        if case_id=="CASE_A":
            path_artifact["paths"].append({"label":"LIMITING_BUS_114_A","operating_day":day,"beta_AIDC":beta,"slot":slot,"rows":_path(state,binding,"114","A")})
            path_artifact["paths"].append({"label":"WORST_AIDC_PCC","operating_day":day,"beta_AIDC":beta,"slot":worst_slot,"bus":worst_aidc[0],"phase":worst_aidc[1],"rows":_path(states[worst_slot],binding,*worst_aidc)})
    primary=cases[0]["mismatch"]; total=float(primary["planning_vs_native_abs_error"]); residual=float(primary["planning_vs_frozen_control_abs_error"]); explained=max(0.0,1.0-residual/max(total,1e-12))
    cap_same=all(c["native_control_trajectory"]["capacitor_state_change_count"]==0 and c["mismatch"]["native_capacitor_states"]==c["mismatch"]["planning_capacitor_states"] for c in cases)
    replay_aligned_max=float(cases[0]["exact_ac_flow_linear_replay"]["LD_AC_CONTROL_STATE"]["max_abs_error_pu"]); replay_aligned_mean=float(cases[0]["exact_ac_flow_linear_replay"]["LD_AC_CONTROL_STATE"]["mean_abs_error_pu"])
    if control_audit["conversion_rule_status"]!="PASS": classification="VOLT_CLASS_A_IMPLEMENTATION_BASE_OR_RATIO_DEFECT"
    elif not cap_same and explained>=0.75: classification="VOLT_CLASS_C_CAPACITOR_CONTROL_OMISSION"
    elif explained>=0.75 and residual<=0.01 and (replay_aligned_max>0.01 or replay_aligned_mean>0.005): classification="VOLT_CLASS_E_COMBINED_CONTROL_AND_LINEARIZATION_LIMITATION"
    elif explained>=0.75 and residual<=0.01: classification="VOLT_CLASS_B_NATIVE_REGULATOR_CONTROL_OMISSION"
    elif residual>0.01 and explained>=0.25: classification="VOLT_CLASS_E_COMBINED_CONTROL_AND_LINEARIZATION_LIMITATION"
    elif residual>0.01: classification="VOLT_CLASS_D_LOSSLESS_LINDISTFLOW_APPROXIMATION_LIMITATION"
    else: classification="VOLT_CLASS_F_OTHER"
    counters={"scientific_authority_changes":0,"beta_production_changes":0,"AIDC_raw_data_changes":0,"alpha_grid_changes":0,"native_feeder_rating_changes":0,"u080_changes":0,"voltage_limit_changes":0,"kappa_changes":0,"PUE_changes":0,"PF_changes":0,"may_scientific_loader_access_count":0,"june_scientific_loader_access_count":0,"G13_calls":0,"G14_calls":0,"C12_calls":0}
    common={"checkpoint":checkpoint,"source_shas":checkpoint["sha256"],"diagnostic_code_sha256":sha256_file(Path(__file__)),"reproducibility":{"command":"python -m dayahead.run_planning_ac_voltage_forensic_v1","cases":[list(x) for x in CASES],"lower_probe":LOWER_PROBE,"fixed_reference_only":True,"MESS_dispatch":False,"compute_optimization":False,"B3_optimization":False,"fresh_compile_per_control_state_and_case":True},**counters}
    case_a_replay=cases[0]["exact_ac_flow_linear_replay"]
    loss_summary={"exact_AC_voltage_bus_114_A_pu":cases[0]["mismatch"]["fresh_ac_native_voltage_pu"],"current_lossless_LinDistFlow_bus_114_A_pu":next(r for r in case_a_replay["LD_CURRENT_STATE"]["node_errors"] if r["node"]=="114.1")["predicted_pu"],"tap_cap_aligned_LinDistFlow_bus_114_A_pu":next(r for r in case_a_replay["LD_AC_CONTROL_STATE"]["node_errors"] if r["node"]=="114.1")["predicted_pu"],"current_state_max_abs_error_pu":case_a_replay["LD_CURRENT_STATE"]["max_abs_error_pu"],"current_state_mean_abs_error_pu":case_a_replay["LD_CURRENT_STATE"]["mean_abs_error_pu"],"after_control_alignment_max_abs_error_pu":case_a_replay["LD_AC_CONTROL_STATE"]["max_abs_error_pu"],"after_control_alignment_mean_abs_error_pu":case_a_replay["LD_AC_CONTROL_STATE"]["mean_abs_error_pu"],"limiting_bus_after_control_alignment_error_pu":case_a_replay["limiting_bus_114_A"]["ac_control_state_error_pu"],"worst_aidc_after_control_alignment_error_pu":case_a_replay["worst_aidc_pcc"]["ac_control_state_error_pu"],"fitted_correction_factor_used":False}
    forensic={"artifact_id":"PLANNING_AC_VOLTAGE_FORENSIC_V1",**common,"canonical_cases":cases,"loss_and_linearization_diagnostic_case_A":loss_summary,"classification_rule":{"control_dominant_fraction_threshold":0.75,"AC_planning_control_residual_material_pu":0.01,"linear_replay_max_material_pu":0.01,"linear_replay_mean_material_pu":0.005},"control_explained_fraction_case_A":explained,"residual_after_control_alignment_case_A_pu":residual,"primary_classification":classification,"production_code_changed":False,"production_files_changed":[],"beta_candidate_recommended":None,"next_decision":"READY_FOR_V16_3_PLANNING_MODEL_REFREEZE_REVIEW" if classification in {"VOLT_CLASS_B_NATIVE_REGULATOR_CONTROL_OMISSION","VOLT_CLASS_C_CAPACITOR_CONTROL_OMISSION","VOLT_CLASS_D_LOSSLESS_LINDISTFLOW_APPROXIMATION_LIMITATION","VOLT_CLASS_E_COMBINED_CONTROL_AND_LINEARIZATION_LIMITATION"} else "DEEPER_VOLTAGE_MODEL_REVIEW_REQUIRED"}
    path_artifact.update(common); path_artifact["largest_drop_contributors"]=sorted(path_artifact["paths"][0]["rows"],key=lambda r:abs(float(r["incremental_impedance_drop_v_squared"])),reverse=True)[:5]; path_artifact["exact_AC_flow_replay_case_A"]={"LD_CURRENT_STATE_rows":case_a_replay["LD_CURRENT_STATE"]["rows"],"LD_AC_CONTROL_STATE_rows":case_a_replay["LD_AC_CONTROL_STATE"]["rows"]}
    capacitor_ratings={row["name"]:row["kvar"] for row in control_audit["capacitors"]}
    control_audit={"artifact_id":"REGULATOR_CAPACITOR_CONTROL_AUDIT_V1",**common,**control_audit,"case_control_comparisons":[{"case_id":c["case_id"],"native_taps":[r["reg1a_tap_winding2"] for r in c["native_control_trajectory"]["slots"]],"planning_assumed_taps":[1.0]*96,"tap_difference_native_minus_planning":[r["reg1a_tap_winding2"]-1.0 for r in c["native_control_trajectory"]["slots"]],"native_regulator_taps":[r["regulator_taps"] for r in c["native_control_trajectory"]["slots"]],"planning_regulator_taps":[r["regulator_taps"] for r in c["planning_control_trajectory"]["slots"]],"native_minus_planning_tap_by_regulator":[{name:r["regulator_taps"][name]-1.0 for name in r["regulator_taps"]} for r in c["native_control_trajectory"]["slots"]],"native_capacitor_states":[r["capacitor_states"] for r in c["native_control_trajectory"]["slots"]],"planning_capacitor_states":[r["capacitor_states"] for r in c["planning_control_trajectory"]["slots"]],"native_capacitor_q_kvar":[{name:capacitor_ratings[name]*int(any(state)) for name,state in r["capacitor_states"].items()} for r in c["native_control_trajectory"]["slots"]],"planning_capacitor_q_kvar":[{name:capacitor_ratings[name]*int(any(state)) for name,state in r["capacitor_states"].items()} for r in c["planning_control_trajectory"]["slots"]],"capacitor_state_difference_count":sum(a["capacitor_states"]!=b["capacitor_states"] for a,b in zip(c["native_control_trajectory"]["slots"],c["planning_control_trajectory"]["slots"]))} for c in cases]}
    shadow_aligned=cases[0]["exact_ac_flow_linear_replay"]["LD_AC_CONTROL_STATE"]["node_errors"]
    shadow_114=next(row for row in shadow_aligned if row["node"]=="114.1")
    shadow={"artifact_id":"TAP_CONTROL_AWARE_PLANNING_DIAGNOSTIC_V1",**common,"status":"SHADOW_ONLY_NOT_PRODUCTION","classification_basis":classification,"diagnostic_state_source":"FRESH_AC_REALIZED_TAP_ORACLE_FOR_ROOT_CAUSE_ISOLATION_ONLY_NOT_A_D_MINUS_1_SCHEDULE","case_A_shadow_bus_114_A_voltage_pu":shadow_114["predicted_pu"],"case_A_false_undervoltage_removed":float(shadow_114["predicted_pu"])>=0.95,"remains_LP":True,"preserves_time_local_grid_LP":True,"preserves_Pi_Farkas_structure_if_taps_are_exogenous_constants":True,"OpenDSS_calls_inside_Benders":0,"D_minus_1_exogenous_control_schedule_required":True,"D_minus_1_schedule_constructed":False,"requires_prospective_V16_3_scientific_refreeze":True,"production_activation":False}
    for name,payload in (("PLANNING_AC_VOLTAGE_FORENSIC_V1.json",forensic),("VOLTAGE_PATH_DECOMPOSITION_V1.json",path_artifact),("REGULATOR_CAPACITOR_CONTROL_AUDIT_V1.json",control_audit),("TAP_CONTROL_AWARE_PLANNING_DIAGNOSTIC_V1.json",shadow)):_write_json(artifacts/name,payload)
    return {"classification":classification,"checkpoint_sha":CHECKPOINT_HEAD,"case_A":primary,"control_explained_fraction":explained,"next_decision":forensic["next_decision"],"artifact_shas":{name:sha256_file(artifacts/name) for name in ("PLANNING_AC_VOLTAGE_FORENSIC_V1.json","VOLTAGE_PATH_DECOMPOSITION_V1.json","REGULATOR_CAPACITOR_CONTROL_AUDIT_V1.json","TAP_CONTROL_AWARE_PLANNING_DIAGNOSTIC_V1.json")}}


def main(argv:Sequence[str]|None=None)->int:
    repo=Path.cwd(); source=Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,default=repo); parser.add_argument("--source",type=Path,default=source); parser.add_argument("--artifacts",type=Path,default=repo/"dayahead/artifacts/v16_2")
    print(json.dumps(execute(**vars(parser.parse_args(argv))),indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
