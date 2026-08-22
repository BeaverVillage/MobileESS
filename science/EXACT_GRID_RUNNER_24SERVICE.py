#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import multiprocessing as mp
import os
import shutil
import tarfile
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from opendss_metrics_common import (
    TOL, V_MIN_PU, V_MAX_PU, LOADING_LIMIT_PU,
    get_error, cmd, set_named_load, set_named_generator,
    collect_voltage_rows, collect_line_rows, collect_transformer_rows,
    collect_control_state,
)

TOTAL_STEPS=105933
PRIMARY_STEPS=105120
TAIL_STEPS=813
CHUNK_STEPS=288
WORKERS=8
RUNNER_SHA="b3c47127b82ec652ac99f93a10636cefdc112645ead953799bd137026cce4b14"
V2038_PARENT_NAME="Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038_20260806T1951KST.zip"
V2038_PARENT_SHA="de89f122f2c56c25c268cef114f24188e9fdce452f24d07f8117a4b97d06c72e"
TAIL_SHA="3009e7c37c156c191d951718abba2fa66c1b8a9178b4c7ea0601e4c58f52163b"
PARENT_R10R1_SHA="77d2bcccc4b68909bfc23458ce59256461fd44e763fe41d9e58b9743c33341af"
PRIMARY_ARRAY_SHA={
 "background_p_kw.npy":"713a278a8f3e037ef04e3c5b25dfe0d3d8d325a01c107ae0daccd8e70002cfc9",
 "background_q_kvar.npy":"ec2f53613e85903184e70343f5691ae615ed318929431419268caecf0f00baaf",
 "pv_available_kw.npy":"d56e45a8b8990fe25e47b164008ffec3826b7bc7b3ad4c922446e16ab53b462f",
 "time_index_utc_ns.npy":"494686d0e989b34de0246607c23525ccb3115a320c6a0de50784c334a1a857a9",
}
IDCS=[f"IDC{i:02d}" for i in range(1,13)]
MESS=[f"MESS{i:02d}" for i in range(1,5)]
METRIC_KEYS=[
 "step_index","timestamp_utc_ns","converged","command_error_count",
 "voltage_min_pu","voltage_max_pu","voltage_violation_count",
 "line_max_loading_pu","line_violation_count",
 "transformer_max_kva_loading_pu","transformer_kva_violation_count",
 "transformer_max_current_loading_pu","transformer_current_violation_count",
 "root_import_p_kw","root_import_q_kvar","root_sign_pass","hard_constraint_pass"
]

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def jwrite(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")

def cwrite(path:Path,rows:list[dict[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys()) if rows else METRIC_KEYS
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def verify_checksum_manifest(root:Path)->int:
    p=root/"CHECKSUMS.sha256"
    if not p.is_file():
        raise RuntimeError(f"CHECKSUMS missing: {root}")
    n=0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        exp,rel=line.split(None,1)
        fp=root/rel.strip().lstrip("*")
        n+=1
        if not fp.is_file() or sha256(fp)!=exp:
            raise RuntimeError(f"checksum mismatch: {rel}")
    return n

def safe_extract_tar(archive:Path,dst:Path)->Path:
    with tarfile.open(archive,"r:gz") as tf:
        tf.extractall(dst,filter="data")
    roots=[x for x in dst.iterdir() if x.is_dir()]
    if len(roots)!=1:
        raise RuntimeError(f"unexpected tar root count={len(roots)}")
    return roots[0]

def safe_extract_zip(archive:Path,dst:Path)->Path:
    with zipfile.ZipFile(archive) as zf:
        bad=zf.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failure: {bad}")
        base=dst.resolve()
        for info in zf.infolist():
            target=(dst/info.filename).resolve()
            if base!=target and base not in target.parents:
                raise RuntimeError(f"ZIP path traversal: {info.filename}")
        zf.extractall(dst)
    roots=[x for x in dst.iterdir() if x.is_dir()]
    return roots[0] if len(roots)==1 else dst

def locate_v2038_package(explicit:str|None=None)->Path:
    candidates=[]
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path("/mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package"))
    dl=Path("/mnt/c/Users/kjw39/Downloads")
    if dl.exists():
        for p in dl.glob("**/run_opendss_v2038_case.py"):
            if p.parent not in candidates:
                candidates.append(p.parent)
    for root in candidates:
        p=root/"run_opendss_v2038_case.py"
        parent=root/"bundled_parent"/V2038_PARENT_NAME
        if p.is_file() and parent.is_file() and sha256(p)==RUNNER_SHA and sha256(parent)==V2038_PARENT_SHA:
            return root.resolve()
    raise RuntimeError("exact V2038 package with runner+parent hashes not found")

def locate_primary_root(explicit:str|None=None)->Path:
    candidates=[]
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.getenv("MOBILE_ESS_POWER_V70_ROOT"):
        candidates.append(Path(os.environ["MOBILE_ESS_POWER_V70_ROOT"]).expanduser())
    candidates += [
        Path("/home/jaewon/mobile_ess_work/processed/power_v70_3ph"),
        Path("/mnt/c/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/processed/power_v70_3ph"),
    ]
    for root in candidates:
        arr=root/"runtime_arrays"
        if arr.is_dir() and all((arr/n).is_file() for n in PRIMARY_ARRAY_SHA):
            if all(sha256(arr/n)==h for n,h in PRIMARY_ARRAY_SHA.items()):
                return root.resolve()
    raise RuntimeError("authoritative primary power_v70 runtime with exact hashes not found")

def prepare_sources(package_root:Path,work:Path,v2038_root:str|None=None,primary_root:str|None=None)->dict[str,str]:
    # R10R1 precondition.
    r10=package_root/"inputs/PARENT_R10R1_AUTHORITATIVE.tar.gz"
    if sha256(r10)!=PARENT_R10R1_SHA:
        raise RuntimeError("R10R1 parent SHA mismatch")
    r10tmp=work/"r10r1"; r10tmp.mkdir()
    r10root=safe_extract_tar(r10,r10tmp)
    verify_checksum_manifest(r10root)
    rr=json.loads((r10root/"_RESULT.json").read_text(encoding="utf-8"))
    if not str(rr.get("status","")).startswith("PASS_V2044R10R1"):
        raise RuntimeError("R10R1 not PASS")
    fc=json.loads((r10root/"forecast/ANNUAL_CAUSAL_FORECAST_CONTRACT.json").read_text(encoding="utf-8"))
    tr=json.loads((r10root/"transformer/IDC_TRANSFORMER_FINALIZATION_AUDIT.json").read_text(encoding="utf-8"))
    if fc.get("status")!="FROZEN" or tr.get("status")!="FROZEN":
        raise RuntimeError("R10R1 forecast/transformer prerequisites not frozen")

    # Tail.
    tail_arc=package_root/"inputs/TAIL_R9R3R1_AUTHORITATIVE.tar.gz"
    if sha256(tail_arc)!=TAIL_SHA:
        raise RuntimeError("R9R3R1 tail SHA mismatch")
    ttmp=work/"tail"; ttmp.mkdir()
    tailroot=safe_extract_tar(tail_arc,ttmp)
    verify_checksum_manifest(tailroot)

    # Original exact V2038 assets + contract.
    pkg=locate_v2038_package(v2038_root)
    pzip=pkg/"bundled_parent"/V2038_PARENT_NAME
    ptmp=work/"v2038_parent"; ptmp.mkdir()
    parent=safe_extract_zip(pzip,ptmp)
    if verify_checksum_manifest(parent)!=52:
        raise RuntimeError("V2038 parent checksum row count !=52")

    primary=locate_primary_root(primary_root)
    return {
      "v2038_package":str(pkg),
      "v2038_parent":str(parent),
      "assets":str(parent/"reference/opendss_assets"),
      "contract":str(parent/"reference/power_v70_p4f_contract"),
      "primary":str(primary/"runtime_arrays"),
      "tail":str(tailroot/"runtime_arrays"),
    }

class PowerStore:
    def __init__(self,primary_arrays:Path,tail_arrays:Path):
        self.pp=np.load(primary_arrays/"background_p_kw.npy",mmap_mode="r",allow_pickle=False)
        self.pq=np.load(primary_arrays/"background_q_kvar.npy",mmap_mode="r",allow_pickle=False)
        self.pv=np.load(primary_arrays/"pv_available_kw.npy",mmap_mode="r",allow_pickle=False)
        self.pt=np.load(primary_arrays/"time_index_utc_ns.npy",mmap_mode="r",allow_pickle=False).astype(np.int64)
        self.tp=np.load(tail_arrays/"background_p_kw.npy",mmap_mode="r",allow_pickle=False)
        self.tq=np.load(tail_arrays/"background_q_kvar.npy",mmap_mode="r",allow_pickle=False)
        self.tv=np.load(tail_arrays/"pv_available_kw.npy",mmap_mode="r",allow_pickle=False)
        self.tt=np.load(tail_arrays/"time_index_utc_ns.npy",mmap_mode="r",allow_pickle=False).astype(np.int64)
        if self.pp.shape!=(PRIMARY_STEPS,131,3) or self.pq.shape!=self.pp.shape or self.pv.shape!=self.pp.shape:
            raise RuntimeError("primary power shape mismatch")
        if self.tp.shape!=(TAIL_STEPS,131,3) or self.tq.shape!=self.tp.shape or self.tv.shape!=self.tp.shape:
            raise RuntimeError("tail power shape mismatch")
        if self.pt.shape!=(PRIMARY_STEPS,) or self.tt.shape!=(TAIL_STEPS,):
            raise RuntimeError("time shape mismatch")
        if int(self.tt[0])-int(self.pt[-1])!=300_000_000_000:
            raise RuntimeError("primary-tail time boundary !=300 seconds")
        full=np.concatenate([np.asarray(self.pt),np.asarray(self.tt)])
        if np.any(np.diff(full)!=300_000_000_000):
            raise RuntimeError("combined time axis is not strict 5-min")
    def step(self,k:int)->tuple[np.ndarray,np.ndarray,np.ndarray,int]:
        if not 0<=k<TOTAL_STEPS:
            raise IndexError(k)
        if k<PRIMARY_STEPS:
            return (np.asarray(self.pp[k],dtype=np.float64),np.asarray(self.pq[k],dtype=np.float64),
                    np.asarray(self.pv[k],dtype=np.float64),int(self.pt[k]))
        j=k-PRIMARY_STEPS
        return (np.asarray(self.tp[j],dtype=np.float64),np.asarray(self.tq[j],dtype=np.float64),
                np.asarray(self.tv[j],dtype=np.float64),int(self.tt[j]))

def apply_background(odd:Any,bp:np.ndarray,bq:np.ndarray,pv:np.ndarray,contract_dir:Path)->dict[str,float]:
    adapter=json.loads((contract_dir/"opendss_runtime_adapter.json").read_text(encoding="utf-8"))
    mask=np.load(contract_dir/"compiled_bus_phase_mask.npy",allow_pickle=False).astype(bool)
    if bp.shape!=(131,3) or bq.shape!=(131,3) or pv.shape!=(131,3) or mask.shape!=(131,3):
        raise RuntimeError("background/contract shape mismatch")
    if np.any(np.abs(bp[~mask])>1e-9) or np.any(np.abs(bq[~mask])>1e-9) or np.any(np.abs(pv[~mask])>1e-9):
        raise RuntimeError("nonzero background on nonexistent compiled phase")
    native_p=np.asarray(adapter["native_bus_p_kw"],dtype=float)
    native_q=np.asarray(adapter["native_bus_q_kvar"],dtype=float)
    reconp=np.zeros((131,3),dtype=float)
    reconq=np.zeros((131,3),dtype=float)
    for row in adapter["loads"]:
        bi=int(row["bus_index"]); phases=[int(x) for x in row["phases"]]
        target_p=float(bp[bi].sum()); target_q=float(bq[bi].sum())
        basep=float(row["base_p_kw"]); baseq=float(row["base_q_kvar"])
        if abs(native_p[bi])<1e-12:
            if abs(target_p)>1e-8: raise RuntimeError(f"nonzero P on zero-native bus index {bi}")
            kw=0.0
        else:
            kw=basep*target_p/native_p[bi]
        if abs(native_q[bi])<1e-12:
            if abs(target_q)>1e-8: raise RuntimeError(f"nonzero Q on zero-native bus index {bi}")
            kvar=0.0
        else:
            kvar=baseq*target_q/native_q[bi]
        set_named_load(odd,str(row["load_name"]),kw,kvar)
        for ph in phases:
            reconp[bi,ph-1]+=kw/len(phases)
            reconq[bi,ph-1]+=kvar/len(phases)
    pres=float(np.max(np.abs(reconp-bp))); qres=float(np.max(np.abs(reconq-bq)))
    if pres>0.01+1e-8 or qres>0.01+1e-8:
        raise RuntimeError(f"frozen adapter reconstruction failed P={pres} Q={qres}")
    reconpv=np.zeros((131,3),dtype=float)
    for row in adapter["pv_generators"]:
        bi=int(row["bus_index"]); pi=int(row["phase_index"]); kw=float(pv[bi,pi])
        set_named_generator(odd,str(row["generator_name"]),kw,0.0)
        reconpv[bi,pi]+=kw
    pvres=float(np.max(np.abs(reconpv-pv)))
    if pvres>1e-8:
        raise RuntimeError(f"PV reconstruction failed {pvres}")
    return {"p_residual_kw":pres,"q_residual_kvar":qres,"pv_residual_kw":pvres}

def validate_step_state(fac_p:np.ndarray,fac_q:np.ndarray,loc:np.ndarray,mp:np.ndarray,mq:np.ndarray,
                        parked:np.ndarray,plugged:np.ndarray,connected:np.ndarray,transit:np.ndarray)->None:
    services={f"IDC{i:02d}" for i in range(1,13)}|{f"STA{i:02d}" for i in range(1,13)}
    if fac_p.shape!=(12,) or fac_q.shape!=(12,) or any(x.shape!=(4,) for x in [loc,mp,mq,parked,plugged,connected,transit]):
        raise RuntimeError("schedule step shape mismatch")
    if not np.isfinite(fac_p).all() or not np.isfinite(fac_q).all() or np.any(fac_p<0) or np.any(fac_q<0):
        raise RuntimeError("invalid facility P/Q")
    if np.any(np.sqrt(fac_p*fac_p+fac_q*fac_q)>750.0+1e-8):
        raise RuntimeError("IDC 750-kVA transformer facility-side schedule violation")
    for m in range(4):
        sid=str(loc[m]).upper()
        if transit[m]:
            if parked[m] or plugged[m] or connected[m] or abs(mp[m])>TOL or abs(mq[m])>TOL:
                raise RuntimeError(f"MESS{m+1:02d} transit must have P=Q=0 and disconnected")
        if not connected[m] and (abs(mp[m])>TOL or abs(mq[m])>TOL):
            raise RuntimeError(f"MESS{m+1:02d} non-connected has nonzero P/Q")
        if connected[m]:
            if not parked[m] or not plugged[m] or transit[m] or sid not in services:
                raise RuntimeError(f"MESS{m+1:02d} connection/location contract failure service={sid}")
        if abs(mp[m])>550.0+TOL or mp[m]*mp[m]+mq[m]*mq[m]>700.0*700.0+1e-6:
            raise RuntimeError(f"MESS{m+1:02d} P550/S700 violation")

def transformer_current_rows(odd:Any)->list[dict[str,Any]]:
    rows=[]
    for name in odd.Transformers.AllNames():
        odd.Transformers.Name(str(name))
        nwind=int(odd.Transformers.NumWindings())
        odd.Circuit.SetActiveElement(f"Transformer.{name}")
        ncond=int(odd.CktElement.NumConductors())
        nterm=int(odd.CktElement.NumTerminals())
        vals=[float(x) for x in odd.CktElement.CurrentsMagAng()]
        for t in range(min(nwind,nterm)):
            odd.Transformers.Wdg(t+1)
            kva=float(odd.Transformers.kVA())
            kv=float(odd.Transformers.kV())
            try:
                phases=int(odd.CktElement.NumPhases())
            except Exception:
                phases=3 if ncond>=3 else 1
            rated = kva/(math.sqrt(3.0)*kv) if phases>=3 else kva/kv
            mags=[]
            for c in range(min(phases,ncond)):
                idx=2*(t*ncond+c)
                if idx < len(vals):
                    mags.append(vals[idx])
            mx=max(mags) if mags else 0.0
            loading=mx/rated if rated>0 else float("inf")
            rows.append({
              "transformer":str(name),"terminal":t+1,"winding":t+1,"num_phases":phases,
              "rated_kva":kva,"rated_kv":kv,"rated_phase_current_a":rated,
              "max_phase_current_a":mx,"current_loading_pu":loading,
              "hard_violation":loading>1.0+TOL
            })
    return rows

def solve_step(paths:dict[str,str],step:int,state:dict[str,list[Any]])->dict[str,Any]:
    import opendssdirect as odd
    store=PowerStore(Path(paths["primary"]),Path(paths["tail"]))
    bp,bq,pv,tns=store.step(step)
    forecast_override="background_p_kw" in state
    if forecast_override:
        bp=np.asarray(state["background_p_kw"],dtype=float)
        bq=np.asarray(state["background_q_kvar"],dtype=float)
        pv=np.asarray(state["pv_available_kw"],dtype=float)
        if bp.shape!=(131,3) or bq.shape!=(131,3) or pv.shape!=(131,3):
            raise RuntimeError("forecast background override must be 131x3")
        if not np.isfinite(bp).all() or not np.isfinite(bq).all() or not np.isfinite(pv).all():
            raise RuntimeError("forecast background override contains nonfinite values")
    fac_p=np.asarray(state["facility_p_kw"],dtype=float)
    fac_q=np.asarray(state["facility_q_kvar"],dtype=float)
    if "mess_location_service_id" in state:
        loc=np.asarray([str(x).upper() for x in state["mess_location_service_id"]],dtype=object)
    elif "mess_location_idc" in state:
        loc=np.asarray([f"IDC{int(x):02d}" for x in state["mess_location_idc"]],dtype=object)
    else:
        raise RuntimeError("missing MESS location service identity")
    mpow=np.asarray(state["mess_p_kw"],dtype=float)
    mq=np.asarray(state["mess_q_kvar"],dtype=float)
    parked=np.asarray(state["mess_parked"],dtype=bool)
    plugged=np.asarray(state["mess_plugged"],dtype=bool)
    connected=np.asarray(state["mess_grid_connected"],dtype=bool)
    transit=np.asarray(state["mess_in_transit"],dtype=bool)
    validate_step_state(fac_p,fac_q,loc,mpow,mq,parked,plugged,connected,transit)

    command_audit=[]
    odd.Basic.ClearAll()
    assets=Path(paths["assets"]); contract=Path(paths["contract"])
    if forecast_override:
        adapter=json.loads((contract/"opendss_runtime_adapter.json").read_text(encoding="utf-8"))
        native_p=np.asarray(adapter["native_bus_p_kw"],dtype=float)
        native_q=np.asarray(adapter["native_bus_q_kvar"],dtype=float)
        pweights=np.zeros((131,3),dtype=float)
        qweights=np.zeros((131,3),dtype=float)
        for row in adapter["loads"]:
            for phase in row["phases"]:
                bi=int(row["bus_index"]); pi=int(phase)-1; count=len(row["phases"])
                if abs(native_p[bi])>1e-12:
                    pweights[bi,pi]+=float(row["base_p_kw"])/native_p[bi]/count
                if abs(native_q[bi])>1e-12:
                    qweights[bi,pi]+=float(row["base_q_kvar"])/native_q[bi]/count
        def align_load_phases(values:np.ndarray,weights:np.ndarray)->np.ndarray:
            totals=values.sum(axis=1)
            if np.any((np.abs(weights).sum(axis=1)<1e-12)&(np.abs(totals)>1e-9)):
                raise RuntimeError("forecast override has load on a bus without compiled phases")
            return totals[:,None]*weights
        bp=align_load_phases(bp,pweights)
        bq=align_load_phases(bq,qweights)
    cmd(odd,f'Compile "{assets/"IEEE123Master.dss"}"',command_audit)
    cmd(odd,"MakeBusList",command_audit)
    base_bus_count=int(odd.Circuit.NumBuses())
    if base_bus_count!=132:
        raise RuntimeError(f"base bus count {base_bus_count} !=132")
    cmd(odd,f'Redirect "{assets/"Generated_ThreePhase_PCC_v3.dss"}"',command_audit)
    cmd(odd,"MakeBusList",command_audit)
    cmd(odd,"CalcVoltageBases",command_audit)
    if int(odd.Circuit.NumBuses())!=168:
        raise RuntimeError("augmented bus count !=168")
    cmd(odd,f'Redirect "{assets/"Generated_Planning_Line_Ratings_u080.dss"}"',command_audit)
    cmd(odd,f'Redirect "{contract/"Generated_PhasePV.dss"}"',command_audit)
    native_control_value=paths.get("native_grid_control")
    native_control_path=Path(native_control_value) if native_control_value else None
    if native_control_path is not None:
        if not native_control_path.is_file():
            raise RuntimeError("common native grid-control overlay is missing")
        cmd(odd,f'Redirect "{native_control_path}"',command_audit)
    native_control_mode=str(
      state.get("native_grid_control_mode","LEGACY_SOURCE_STATE")
    ).upper()
    initial_native_states={
      str(name).lower():[int(value) for value in values]
      for name,values in state.get("native_capacitor_initial_states",{}).items()
    }
    available_capacitors={str(name).lower() for name in odd.Capacitors.AllNames()}
    missing_capacitors=sorted(set(initial_native_states)-available_capacitors)
    if missing_capacitors:
        raise RuntimeError(
          f"native capacitor state references missing assets: {missing_capacitors}"
        )
    for name,values in sorted(initial_native_states.items()):
        odd.Capacitors.Name(name)
        if len(values)!=int(odd.Capacitors.NumSteps()):
            raise RuntimeError(f"native capacitor state width changed for {name}")
        odd.Capacitors.States(values)
    locked_native_capacitors={
      str(name).lower() for name in state.get("native_capacitor_locked",())
    }
    if not locked_native_capacitors.issubset(available_capacitors):
        raise RuntimeError("native capacitor dwell lock references a missing asset")
    if native_control_path is not None:
        control_to_capacitor={
          "pfr_native_c83":"c83",
          "pfr_native_c88a":"c88a",
          "pfr_native_c90b":"c90b",
          "pfr_native_c92c":"c92c",
        }
        if native_control_mode=="FIXED_STATE_VERIFICATION":
            disabled=set(control_to_capacitor)
        elif native_control_mode=="EVALUATE_TRANSITION":
            disabled={
              control for control,capacitor in control_to_capacitor.items()
              if capacitor in locked_native_capacitors
            }
        else:
            raise RuntimeError(f"unsupported native grid-control mode {native_control_mode}")
        for control in sorted(disabled):
            cmd(odd,f"Edit CapControl.{control} Enabled=No",command_audit)
    bind=apply_background(odd,bp,bq,pv,contract)

    for i,idc in enumerate(IDCS):
        set_named_load(odd,f"IDC_{idc}",float(fac_p[i]),float(fac_q[i]))

    # Clear all MESS elements before applying this step.
    for name in list(odd.Generators.AllNames()):
        if str(name).lower().startswith("mess_dis_"):
            set_named_generator(odd,str(name),0.0,0.0)
    for name in list(odd.Loads.AllNames()):
        if str(name).lower().startswith("mess_chg_"):
            set_named_load(odd,str(name),0.0,0.0)

    for m in range(4):
        if not connected[m]:
            continue
        sid=str(loc[m]).upper()
        p=float(mpow[m]); q=float(mq[m])
        set_named_generator(odd,f"MESS_DIS_{sid}",max(p,0.0),max(q,0.0))
        set_named_load(odd,f"MESS_CHG_{sid}",max(-p,0.0),max(-q,0.0))

    cmd(odd,"Set Mode=Snapshot",command_audit)
    cmd(odd,"Set ControlMode=Static",command_audit)
    cmd(odd,"Set MaxControlIter=100",command_audit)
    cmd(odd,"Set MaxIterations=100",command_audit)
    cmd(odd,"Set Tolerance=0.0001",command_audit)
    odd.Solution.Solve()
    solve_err=get_error(odd)
    command_audit.append({"command":"Solution.Solve()","error_number":solve_err["number"],"error_description":solve_err["description"]})

    converged=bool(odd.Solution.Converged())
    voltage=collect_voltage_rows(odd)
    lines,_=collect_line_rows(odd)
    tx=collect_transformer_rows(odd)
    txi=transformer_current_rows(odd)
    raw=[float(x) for x in odd.Circuit.TotalPower()]
    rawp=raw[0] if raw else 0.0; rawq=raw[1] if len(raw)>1 else 0.0
    root_import_p=max(-rawp,0.0); root_import_q=max(-rawq,0.0)
    root_export_p=max(rawp,0.0)
    root_sign=root_export_p<=1e-6 and root_import_p>0

    cerr=sum(1 for r in command_audit if int(r.get("error_number") or 0)!=0)
    vviol=sum(1 for r in voltage if r["hard_violation"])
    lviol=sum(1 for r in lines if r["hard_violation"])
    tviol=sum(1 for r in tx if r["hard_violation"])
    tcviol=sum(1 for r in txi if r["hard_violation"])
    vmin=min((float(r["voltage_pu"]) for r in voltage),default=float("nan"))
    vmax=max((float(r["voltage_pu"]) for r in voltage),default=float("nan"))
    lmax=max((float(r["loading_pu"]) for r in lines),default=float("nan"))
    tkmax=max((float(r["loading_pu"]) for r in tx),default=float("nan"))
    tcmax=max((float(r["current_loading_pu"]) for r in txi),default=float("nan"))
    native_control=collect_control_state(odd)
    native_capacitor_states={
      str(row["name"]):list(row.get("states",()))
      for row in native_control.get("capacitors",())
    }
    native_regulator_taps={
      str(row["name"]):row.get("tap_number")
      for row in native_control.get("regcontrols",())
    }
    hard=bool(converged and cerr==0 and vviol==0 and lviol==0 and tviol==0 and tcviol==0 and root_sign)
    return {
      "step_index":int(step),"timestamp_utc_ns":int(tns),
      "converged":converged,"command_error_count":cerr,
      "voltage_min_pu":vmin,"voltage_max_pu":vmax,"voltage_violation_count":vviol,
      "line_max_loading_pu":lmax,"line_violation_count":lviol,
      "transformer_max_kva_loading_pu":tkmax,"transformer_kva_violation_count":tviol,
      "transformer_max_current_loading_pu":tcmax,"transformer_current_violation_count":tcviol,
      "root_import_p_kw":root_import_p,"root_import_q_kvar":root_import_q,
      "root_sign_pass":root_sign,"hard_constraint_pass":hard,
      "background_binding_p_residual_kw":bind["p_residual_kw"],
      "background_binding_q_residual_kvar":bind["q_residual_kvar"],
      "background_binding_pv_residual_kw":bind["pv_residual_kw"],
      "native_grid_control_authority":(
        "COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1"
        if native_control_path is not None
        else "LEGACY_FIXED_CAPACITOR_NO_CAPCONTROL"
      ),
      "native_capcontrol_count":int(odd.CapControls.Count()),
      "native_grid_control_mode":native_control_mode,
      "native_capacitor_binary_state_frozen":bool(
        native_control_mode=="FIXED_STATE_VERIFICATION"
      ),
      "native_capacitor_locked":sorted(locked_native_capacitors),
      "native_capacitor_states":native_capacitor_states,
      "native_regulator_tap_numbers":native_regulator_taps,
    }

def read_h6b2_state(package_root:Path)->dict[str,list[Any]]:
    fac=[]
    with (package_root/"inputs/H6B2_OFFSET0_FACILITY_PQ.csv").open("r",encoding="utf-8-sig",newline="") as f:
        fac=list(csv.DictReader(f))
    mess=[]
    with (package_root/"inputs/H6B2_OFFSET0_MESS_STATE.csv").open("r",encoding="utf-8-sig",newline="") as f:
        mess=list(csv.DictReader(f))
    fac.sort(key=lambda r:r["idc_id"]); mess.sort(key=lambda r:r["mess_id"])
    return {
      "facility_p_kw":[float(r["facility_active_power_kw"]) for r in fac],
      "facility_q_kvar":[float(r["facility_reactive_power_kvar"]) for r in fac],
      "mess_location_idc":[int(r["location_idc_id"].replace("IDC","")) for r in mess],
      "mess_p_kw":[float(r["p_kw"]) for r in mess],
      "mess_q_kvar":[float(r["q_kvar"]) for r in mess],
      "mess_parked":[str(r["parked"]).lower()=="true" for r in mess],
      "mess_plugged":[str(r["plugged"]).lower()=="true" for r in mess],
      "mess_grid_connected":[str(r["grid_connected"]).lower()=="true" for r in mess],
      "mess_in_transit":[str(r["in_transit"]).lower()=="true" for r in mess],
    }

def canonical_scientific_result(row:dict[str,Any])->dict[str,Any]:
    out={}
    for k in METRIC_KEYS:
        v=row[k]
        if isinstance(v,float):
            out[k]=round(v,12)
        else:
            out[k]=v
    return out

def result_hash(rows:list[dict[str,Any]])->str:
    data=[canonical_scientific_result(r) for r in sorted(rows,key=lambda x:int(x["step_index"]))]
    blob=json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(blob).hexdigest()

def run_regression(package_root:Path,out:Path,v2038_root:str|None=None,primary_root:str|None=None)->dict[str,Any]:
    work=out/"_runtime_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    paths=prepare_sources(package_root,work,v2038_root,primary_root)
    state=read_h6b2_state(package_root)
    indices=[0,1,287,288,105119,105120,105932]

    # Sequential reference.
    seq=[]
    for k in indices:
        seq.append(solve_step(paths,k,state))
    cwrite(out/"REGRESSION_SEQUENTIAL.csv",seq)

    # Offset-0 exact V2038/H6B2 identity gate.
    exp=json.loads((package_root/"inputs/H6B2_OFFSET0_EXACT_SUMMARY.json").read_text(encoding="utf-8"))
    r0=next(r for r in seq if r["step_index"]==0)
    compare={
      "converged_equal":bool(r0["converged"]==exp["converged"]),
      "command_error_count_equal":bool(r0["command_error_count"]==exp["command_error_count"]),
      "voltage_min_abs_error":abs(r0["voltage_min_pu"]-float(exp["voltage_min_pu"])),
      "voltage_max_abs_error":abs(r0["voltage_max_pu"]-float(exp["voltage_max_pu"])),
      "line_max_abs_error":abs(r0["line_max_loading_pu"]-float(exp["line_max_loading_pu"])),
      "transformer_kva_max_abs_error":abs(r0["transformer_max_kva_loading_pu"]-float(exp["transformer_max_loading_pu"])),
      "root_import_p_abs_error_kw":abs(r0["root_import_p_kw"]-float(exp["root_power"]["root_import_p_kw"])),
      "root_import_q_abs_error_kvar":abs(r0["root_import_q_kvar"]-float(exp["root_power"]["root_import_q_kvar"])),
      "hard_constraint_pass_equal":bool(r0["hard_constraint_pass"]==exp["hard_constraint_pass"]),
    }
    compare["PASS"]=(
      compare["converged_equal"] and compare["command_error_count_equal"] and compare["hard_constraint_pass_equal"]
      and max(compare["voltage_min_abs_error"],compare["voltage_max_abs_error"],
              compare["line_max_abs_error"],compare["transformer_kva_max_abs_error"])<=1e-10
      and compare["root_import_p_abs_error_kw"]<=1e-7
      and compare["root_import_q_abs_error_kvar"]<=1e-7
    )
    if not compare["PASS"]:
        raise RuntimeError("offset0 exact regression mismatch: "+json.dumps(compare))
    jwrite(out/"OFFSET0_V2038_H6B2_EXACT_REGRESSION_AUDIT.json",compare)

    # Worker-order invariance with 8 independent processes.
    ctx=mp.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=8,mp_context=ctx) as ex:
        futs=[ex.submit(solve_step,paths,k,state) for k in reversed(indices)]
        par=[f.result(timeout=900) for f in futs]
    cwrite(out/"REGRESSION_PARALLEL_REVERSED.csv",sorted(par,key=lambda r:r["step_index"]))
    hs=result_hash(seq); hp=result_hash(par)
    inv={"sequential_hash":hs,"parallel_reversed_hash":hp,"hash_equal":hs==hp,"workers":8,"indices":indices}
    if hs!=hp:
        raise RuntimeError("worker-order/hash invariance failed")
    jwrite(out/"WORKER_ORDER_HASH_INVARIANCE_AUDIT.json",inv)

    # Boundary and arbitrary-index interface gates. Hard pass is not required because this
    # regression intentionally holds H6B2 facility/MESS controls fixed away from offset-0.
    by={int(r["step_index"]):r for r in seq}
    boundary={
      "step_105119_timestamp_ns":by[105119]["timestamp_utc_ns"],
      "step_105120_timestamp_ns":by[105120]["timestamp_utc_ns"],
      "delta_seconds":(by[105120]["timestamp_utc_ns"]-by[105119]["timestamp_utc_ns"])/1e9,
      "both_converged":bool(by[105119]["converged"] and by[105120]["converged"]),
      "both_command_error_free":bool(by[105119]["command_error_count"]==0 and by[105120]["command_error_count"]==0),
    }
    boundary["PASS"]=boundary["delta_seconds"]==300.0 and boundary["both_converged"] and boundary["both_command_error_free"]
    if not boundary["PASS"]:
        raise RuntimeError("primary-tail electrical interface regression failed")
    jwrite(out/"PRIMARY_TAIL_ELECTRICAL_INTERFACE_AUDIT.json",boundary)

    # Annual schedule and chunk contracts.
    chunks=[]
    cid=0
    for start in range(0,PRIMARY_STEPS,CHUNK_STEPS):
        end=min(PRIMARY_STEPS,start+CHUNK_STEPS)
        chunks.append({"chunk_id":cid,"start":start,"end_exclusive":end,"steps":end-start,"region":"primary"})
        cid+=1
    for start in range(PRIMARY_STEPS,TOTAL_STEPS,CHUNK_STEPS):
        end=min(TOTAL_STEPS,start+CHUNK_STEPS)
        chunks.append({"chunk_id":cid,"start":start,"end_exclusive":end,"steps":end-start,"region":"carry_out"})
        cid+=1
    if len(chunks)!=368 or chunks[-1]["steps"]!=237:
        raise RuntimeError("chunk partition mismatch")
    jwrite(out/"ANNUAL_CHUNK_PARTITION.json",{"chunk_count":len(chunks),"chunks":chunks})
    jwrite(out/"ANNUAL_SCHEDULE_INPUT_SCHEMA.json",{
      "status":"FROZEN_INTERFACE_SCHEMA",
      "total_steps":TOTAL_STEPS,
      "time_index_utc_ns":[TOTAL_STEPS],
      "facility_p_kw":[TOTAL_STEPS,12],
      "facility_q_kvar":[TOTAL_STEPS,12],
      "mess_location_idc":[TOTAL_STEPS,4],
      "mess_p_kw":[TOTAL_STEPS,4],
      "mess_q_kvar":[TOTAL_STEPS,4],
      "mess_parked":[TOTAL_STEPS,4],
      "mess_plugged":[TOTAL_STEPS,4],
      "mess_grid_connected":[TOTAL_STEPS,4],
      "mess_in_transit":[TOTAL_STEPS,4],
      "rules":{
        "in_transit_implies_P_Q_zero":True,
        "not_grid_connected_implies_P_Q_zero":True,
        "connected_implies_parked_and_plugged_and_valid_IDC":True,
        "MESS_P_limit_kw":550.0,
        "MESS_S_limit_kva":700.0,
        "IDC_transformer_nameplate_kva":750.0,
        "phase_binding":"C00/A020"
      }
    })
    jwrite(out/"ANNUAL_RUNNER_EXECUTION_CONTRACT.json",{
      "status":"IMPLEMENTED_AND_REGRESSION_PASS",
      "total_steps":TOTAL_STEPS,"primary_steps":PRIMARY_STEPS,"carry_out_steps":TAIL_STEPS,
      "chunk_steps":CHUNK_STEPS,"chunk_count":368,"workers":8,
      "numeric_threads_per_worker":1,
      "fresh_compile_each_committed_step":True,
      "resume_by_atomic_chunk_certificate":True,
      "deterministic_result_order":True,
      "worker_order_hash_invariance":True,
      "transformer_current_and_kva_checked_separately":True,
      "required_step_outputs":METRIC_KEYS,
      "annual_replay_started":False
    })
    shutil.rmtree(work,ignore_errors=True)
    return {"offset0":compare,"invariance":inv,"boundary":boundary,"regression_rows":len(seq)}

def load_schedule(npz_path:Path,store:PowerStore)->dict[str,np.ndarray]:
    z=np.load(npz_path,allow_pickle=False)
    required={
      "time_index_utc_ns":(TOTAL_STEPS,),
      "facility_p_kw":(TOTAL_STEPS,12),"facility_q_kvar":(TOTAL_STEPS,12),
      "mess_location_idc":(TOTAL_STEPS,4),"mess_p_kw":(TOTAL_STEPS,4),"mess_q_kvar":(TOTAL_STEPS,4),
      "mess_parked":(TOTAL_STEPS,4),"mess_plugged":(TOTAL_STEPS,4),
      "mess_grid_connected":(TOTAL_STEPS,4),"mess_in_transit":(TOTAL_STEPS,4)
    }
    out={}
    for k,shape in required.items():
        if k not in z or z[k].shape!=shape:
            raise RuntimeError(f"schedule {k} shape mismatch")
        out[k]=np.asarray(z[k])
    full_time=np.concatenate([np.asarray(store.pt),np.asarray(store.tt)])
    if not np.array_equal(out["time_index_utc_ns"].astype(np.int64),full_time.astype(np.int64)):
        raise RuntimeError("schedule time axis mismatch")
    # Full vectorized physical checks.
    p=out["mess_p_kw"].astype(float); q=out["mess_q_kvar"].astype(float)
    if np.max(np.abs(p))>550.0+TOL or np.max(p*p+q*q)>700.0*700.0+1e-6:
        raise RuntimeError("schedule global P550/S700 violation")
    tr=out["mess_in_transit"].astype(bool); conn=out["mess_grid_connected"].astype(bool)
    parked=out["mess_parked"].astype(bool); plugged=out["mess_plugged"].astype(bool)
    loc=out["mess_location_idc"].astype(np.int64)
    pq_nonzero=(np.abs(p)>TOL)|(np.abs(q)>TOL)
    # Parent R11R1 annual-mode bug fix: parenthesize P/Q disjunction before transit mask.
    if np.any(pq_nonzero & tr):
        raise RuntimeError("schedule transit P/Q violation")
    if np.any(pq_nonzero & (~conn)):
        raise RuntimeError("schedule disconnected P/Q violation")
    if np.any(tr & (parked|plugged|conn)):
        raise RuntimeError("schedule transit state must be unparked/unplugged/disconnected")
    if np.any(conn & ((~parked)|(~plugged)|tr)):
        raise RuntimeError("schedule connected state must be parked+plugged+not-transit")
    if np.any(conn & ((loc<1)|(loc>12))):
        raise RuntimeError("schedule connected MESS location outside IDC01..IDC12")
    facp=out["facility_p_kw"].astype(float); facq=out["facility_q_kvar"].astype(float)
    if not np.isfinite(facp).all() or not np.isfinite(facq).all() or np.any(facp<0):
        raise RuntimeError("schedule invalid/nonfinite facility P/Q")
    if np.max(np.sqrt(facp*facp+facq*facq))>750.0+1e-8:
        raise RuntimeError("schedule IDC 750-kVA facility-side violation")
    return out

def chunk_certificate_valid(cert_path:Path,csv_path:Path,input_hash:str)->bool:
    if not cert_path.is_file() or not csv_path.is_file():
        return False
    try:
        c=json.loads(cert_path.read_text(encoding="utf-8"))
        return c.get("status")=="PASS_ATOMIC_CHUNK" and c.get("input_hash")==input_hash and c.get("result_csv_sha256")==sha256(csv_path)
    except Exception:
        return False

def run_annual(package_root:Path,out:Path,schedule_npz:Path,v2038_root:str|None=None,primary_root:str|None=None,
               workers:int=WORKERS)->dict[str,Any]:
    work=out/"_runtime_work"
    work.mkdir(parents=True,exist_ok=True)
    paths=prepare_sources(package_root,work,v2038_root,primary_root)
    store=PowerStore(Path(paths["primary"]),Path(paths["tail"]))
    sched=load_schedule(schedule_npz,store)
    input_hash=hashlib.sha256((
      sha256(schedule_npz)+TAIL_SHA+"".join(PRIMARY_ARRAY_SHA.values())+RUNNER_SHA
    ).encode()).hexdigest()

    chunks=[]
    cid=0
    for start in range(0,PRIMARY_STEPS,CHUNK_STEPS):
        chunks.append((cid,start,min(PRIMARY_STEPS,start+CHUNK_STEPS))); cid+=1
    for start in range(PRIMARY_STEPS,TOTAL_STEPS,CHUNK_STEPS):
        chunks.append((cid,start,min(TOTAL_STEPS,start+CHUNK_STEPS))); cid+=1

    cdir=out/"chunks"; cdir.mkdir(parents=True,exist_ok=True)
    pending=[]
    for cid,start,end in chunks:
        csvp=cdir/f"chunk_{cid:04d}.csv"; cert=cdir/f"chunk_{cid:04d}.certificate.json"
        if not chunk_certificate_valid(cert,csvp,input_hash):
            pending.append((cid,start,end))

    # Run chunks in independent processes. Each individual step fresh-compiles the exact DSS assets.
    def make_state(k:int)->dict[str,list[Any]]:
        return {
          "facility_p_kw":sched["facility_p_kw"][k].tolist(),
          "facility_q_kvar":sched["facility_q_kvar"][k].tolist(),
          "mess_location_idc":sched["mess_location_idc"][k].tolist(),
          "mess_p_kw":sched["mess_p_kw"][k].tolist(),
          "mess_q_kvar":sched["mess_q_kvar"][k].tolist(),
          "mess_parked":sched["mess_parked"][k].astype(bool).tolist(),
          "mess_plugged":sched["mess_plugged"][k].astype(bool).tolist(),
          "mess_grid_connected":sched["mess_grid_connected"][k].astype(bool).tolist(),
          "mess_in_transit":sched["mess_in_transit"][k].astype(bool).tolist(),
        }

    # Keep orchestration deterministic by submitting chunks in ascending id.
    ctx=mp.get_context("spawn")
    for cid,start,end in pending:
        rows=[]
        # One chunk is atomic. Its 288 steps are parallelized with at most `workers` fresh processes.
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers,mp_context=ctx) as ex:
            futs=[ex.submit(solve_step,paths,k,make_state(k)) for k in range(start,end)]
            for fut in futs:
                rows.append(fut.result(timeout=900))
        rows.sort(key=lambda r:r["step_index"])
        tmpcsv=cdir/f".chunk_{cid:04d}.csv.tmp"
        cwrite(tmpcsv,rows)
        finalcsv=cdir/f"chunk_{cid:04d}.csv"
        os.replace(tmpcsv,finalcsv)
        cert={
          "status":"PASS_ATOMIC_CHUNK","chunk_id":cid,"start":start,"end_exclusive":end,
          "steps":end-start,"input_hash":input_hash,"result_csv_sha256":sha256(finalcsv),
          "all_converged":all(bool(r["converged"]) for r in rows),
          "all_command_error_free":all(int(r["command_error_count"])==0 for r in rows),
          "all_hard_constraint_pass":all(bool(r["hard_constraint_pass"]) for r in rows)
        }
        tmpp=cdir/f".chunk_{cid:04d}.certificate.tmp"
        jwrite(tmpp,cert); os.replace(tmpp,cdir/f"chunk_{cid:04d}.certificate.json")

    # Aggregate deterministically.
    allrows=[]
    for cid,start,end in chunks:
        cp=cdir/f"chunk_{cid:04d}.csv"
        cert=cdir/f"chunk_{cid:04d}.certificate.json"
        if not chunk_certificate_valid(cert,cp,input_hash):
            raise RuntimeError(f"chunk {cid} certificate invalid after run")
        with cp.open("r",encoding="utf-8",newline="") as f:
            allrows.extend(list(csv.DictReader(f)))
    if len(allrows)!=TOTAL_STEPS:
        raise RuntimeError(f"annual rows {len(allrows)} != {TOTAL_STEPS}")
    # Numeric order.
    allrows.sort(key=lambda r:int(r["step_index"]))
    cwrite(out/"ANNUAL_EXACT_GRID_SHADOW.csv",allrows)
    hard=sum(str(r["hard_constraint_pass"]).lower()=="true" for r in allrows)
    conv=sum(str(r["converged"]).lower()=="true" for r in allrows)
    cerr=sum(int(r["command_error_count"]) for r in allrows)
    summary={
      "stage":"ANNUAL_EXACT_GRID_SHADOW",
      "status":"COMPLETE" if hard==TOTAL_STEPS and conv==TOTAL_STEPS and cerr==0 else "COMPLETE_WITH_HARD_REJECTIONS",
      "total_steps":TOTAL_STEPS,"converged_steps":conv,"command_error_total":cerr,
      "hard_constraint_pass_steps":hard,"hard_constraint_rejection_steps":TOTAL_STEPS-hard,
      "chunk_count":len(chunks),"input_hash":input_hash,
      "result_sha256":sha256(out/"ANNUAL_EXACT_GRID_SHADOW.csv")
    }
    jwrite(out/"ANNUAL_EXACT_GRID_SHADOW_SUMMARY.json",summary)
    return summary

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--package-root",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--mode",choices=["regression","annual"],required=True)
    ap.add_argument("--schedule-npz")
    ap.add_argument("--v2038-package-root")
    ap.add_argument("--primary-root")
    ap.add_argument("--workers",type=int,default=WORKERS)
    args=ap.parse_args()
    package_root=Path(args.package_root).resolve()
    out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    try:
        if args.mode=="regression":
            result=run_regression(package_root,out,args.v2038_package_root,args.primary_root)
            jwrite(out/"_RESULT.json",{
              "stage":"V2044R11R2",
              "status":"PASS_V2044R11R2_ANNUAL_EXACT_RUNNER_HARDENED_PARENT_R11R1_REGRESSION_PRESERVED",
              "annual_runner_implemented":True,
              "offset0_exact_regression_pass":True,
              "worker_order_hash_invariance_pass":True,
              "primary_tail_interface_pass":True,
              "annual_replay_started":False,
              "next_stage":"V2044R12_ANNUAL_SELECTED_RACK_POOL_AND_RUNTIME_MESS_LOCATION_PLUG_PQ_SCHEDULE"
            })
        else:
            if not args.schedule_npz:
                raise RuntimeError("--schedule-npz required for annual mode")
            result=run_annual(package_root,out,Path(args.schedule_npz).resolve(),args.v2038_package_root,args.primary_root,args.workers)
            jwrite(out/"_RESULT.json",{"stage":"ANNUAL_EXACT_GRID_SHADOW","status":result["status"],"annual_replay_started":True})
        print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
        return 0
    except Exception as e:
        jwrite(out/"_FAILURE.json",{"error":repr(e),"traceback":traceback.format_exc(),"mode":args.mode})
        print(json.dumps({"status":"FAIL_CLOSED","error":repr(e)},ensure_ascii=False))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
