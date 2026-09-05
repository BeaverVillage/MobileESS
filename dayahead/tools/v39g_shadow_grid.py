"""Diagnostic-only loader of existing May-17 D-1 planning coefficients.

No forecast retraining, Actual/Fresh loading or authority regeneration. The
static feeder compilation supplies topology and ratings; no candidate AC
simulation is performed. Only the 12 AIDC control coordinates are variable.
"""
from __future__ import annotations

from dataclasses import fields
import hashlib
import json
import math
import os
from pathlib import Path
from types import FunctionType, SimpleNamespace

import numpy as np
import pandas as pd

from dayahead.grid_lp import LINE_POLYGON_FACES, V_MIN_SQUARED, V_MAX_SQUARED
from dayahead.v28r2.electrical_subproblem import (
    SlotCoefficients, anchored_polygon_parameters, anchored_polygon_loading,
    is_dominated_mess_current_row,
)


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def prepare_grid(repo: Path, out: Path, day: str) -> dict:
    repo, out = repo.resolve(), out.resolve()
    from dayahead.v28r2.electrical_context import source_root, portable_background_paths
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead import grid_background_v16_2 as bg
    from dayahead.v37r3.voltage_authority import joint_repaired_coefficients
    from dayahead.v28r2.c1_affine import load_c1, exact_c1_pcc_kw
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v39d.evaluate import _load_capacity

    source=source_root(SOURCE_DATA_REPOSITORY)
    cache=repo/f"dayahead/cache/v37_may_locked_final/electrical/{day}/data"
    vp=cache/f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    ip=cache/f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    forecast_path=day_root(SOURCE_DATA_REPOSITORY,day)/"aemo_forecast.json"
    forecast=json.loads(forecast_path.read_text(encoding="utf-8"))
    assert str(forecast["cutoff_fixed_aest"]).startswith("2025-05-16T18:00")
    weather_path=day_root(SOURCE_DATA_REPOSITORY,day)/"gfs_d1_weather.parquet"
    weather=pd.read_parquet(weather_path)
    source_hashes={str(p):sha(p) for p in (vp,ip,forecast_path,weather_path)}
    paths=portable_background_paths(SOURCE_DATA_REPOSITORY,source)

    def verify_numeric_inputs(p):
        records={}
        for name,expected in bg.EXPECTED_SHA256.items():
            if name=="pv_reference":
                # This historical annual measured archive is not a numeric
                # input of build_authority_background_binding. Its fixed scale
                # is already the accepted module constant. Do not open it.
                records[name]={"sha256":expected,"status":"FROZEN_PROVENANCE_ONLY_NOT_OPENED"}
                continue
            path=getattr(p,name)
            actual=sha(path)
            if actual!=expected:
                raise RuntimeError(f"V39G_BACKGROUND_AUTHORITY_SHA:{name}")
            source_hashes[str(path)]=actual
            records[name]={"path":str(path),"sha256":actual,"status":"PASS"}
        return records

    # Separate function namespace: no production module or file is patched.
    ns=dict(bg.build_authority_background_binding.__globals__)
    ns["_verify_sources"]=verify_numeric_inputs
    build_bg=FunctionType(bg.build_authority_background_binding.__code__,ns)
    background=build_bg(timestamps_fixed_aest=forecast["timestamps_96"],
        demand_mw_96=forecast["demand_mw_96"],rooftop_pv_mw_96=forecast["pv_mw_96"],paths=paths)
    old_cwd=Path.cwd()
    voltage=np.load(vp,allow_pickle=False)
    current=np.load(ip,allow_pickle=False)
    try:
        anchor=np.asarray(voltage["anchor_control"])
        if anchor.shape!=(96,60) or np.count_nonzero(anchor[:,12:]):
            raise RuntimeError("V39G_ZERO_MESS_ANCHOR_REQUIRED")
        pcc=SOURCE_DATA_REPOSITORY/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss"
        source_hashes[str(pcc)]=sha(pcc)
        binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",
            demand_mw_96=forecast["demand_mw_96"],rooftop_pv_mw_96=forecast["pv_mw_96"],
            aidc_plan_kw_96x12=anchor[:,:12],pcc_asset=pcc,background_binding=background)
        electrical=SimpleNamespace(legacy_context=(None,forecast,background,binding,vp,None),
                                    voltage=voltage,current=current,voltage_path=vp)
        coefficients=joint_repaired_coefficients(repo,electrical)
        data={f.name:np.asarray([getattr(c,f.name) for c in coefficients]) for f in fields(SlotCoefficients)
              if f.name not in ("transformer_ratings",)}
        data["transformer_ratings"]=np.asarray([[np.nan if r is None else r for r in c.transformer_ratings] for c in coefficients])
        data["node_names"]=np.asarray(voltage["node_names"])
        data["anchor_v_squared"]=np.asarray(voltage["anchor_v_squared"])
        np.savez_compressed(out/"V39G_FROZEN_GRID_COEFFICIENTS.npz",**data)
        topology=dict(binding.topology_evidence)
        # Static topology/rating inputs, not outcome records.
        for parent in (source/"opendss_assets",source/"power_v70_p4f_contract"):
            for p in parent.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".dss",".csv",".json"):
                    source_hashes[str(p)]=sha(p)
    finally:
        voltage.close();current.close();os.chdir(old_cwd)
    capacity,_=_load_capacity(repo)
    c1path=repo/"dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
    source_hashes[str(c1path)]=sha(c1path)
    c1=load_c1(c1path)
    tables={}
    for site,cap in capacity.site_capacity.items():
        it=np.asarray([float(site_it_power_kw(cap,g)) for g in range(cap+1)])
        tables[site]=np.asarray([exact_c1_pcc_kw(it,float(row.t_wb_c),float(row.rh_pct),c1)
                                 for row in weather.itertuples(index=False)])
    np.savez_compressed(out/"V39G_C1_INTEGER_TABLES.npz",**tables)
    return {"source_SHA256":source_hashes,"topology":topology,
        "static_topology_compilation":True,"candidate_OpenDSS_solves":0,"Fresh_calls":0,
        "Actual_reads":0,"raw_annual_PV_measurement_archive_opened":False,
        "coefficient_sha256_by_slot":[c.coefficient_sha256 for c in coefficients],
        "C1_exact_at_all_integer_GPU_counts":True}


def load_coefficients(out: Path) -> tuple[tuple[SlotCoefficients,...],list[str]]:
    with np.load(out/"V39G_FROZEN_GRID_COEFFICIENTS.npz",allow_pickle=False) as raw:
        results=[]
        for t in range(96):
            kw={f.name:raw[f.name][t] for f in fields(SlotCoefficients)}
            kw["slot"]=int(kw["slot"])
            for field in ("control_names","branch_names"):
                kw[field]=tuple(map(str,kw[field]))
            kw["branch_limits"]=tuple(map(float,kw["branch_limits"]))
            kw["transformer_ratings"]=tuple(None if np.isnan(v) else float(v) for v in kw["transformer_ratings"])
            kw["coefficient_sha256"]=str(kw["coefficient_sha256"])
            results.append(SlotCoefficients(**kw))
        nodes=list(map(str,raw["node_names"]))
    return tuple(results),nodes


def inequalities(c: SlotCoefficients) -> tuple[np.ndarray,np.ndarray,list[str]]:
    """Every frozen planning inequality, with AIDC controls on LHS, MESS=0.

    Transformer polygon is the production 16-face INNER polygon, in addition
    to the affine phase-current ceiling (except the frozen dominated rows).
    """
    matrix=[]; rhs=[]; names=[]
    def add(a,b,n):
        matrix.append(np.asarray(a,dtype=float));rhs.append(float(b));names.append(n)
    for node,v in enumerate(c.voltage_constant):
        add(c.voltage_matrix[:12,node],V_MAX_SQUARED-v,f"voltage_upper[{c.slot},{node}]")
        add(-c.voltage_matrix[:12,node],v-V_MIN_SQUARED,f"voltage_lower[{c.slot},{node}]")
    bias,correction,_=anchored_polygon_parameters(c)
    for k,branch in enumerate(c.branch_names):
        if not branch.startswith("transformer.") and not is_dominated_mess_current_row(branch):
            apothem=c.branch_limits[k]*math.cos(math.pi/LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                theta=2*math.pi*face/LINE_POLYGON_FACES
                cp,cq=math.cos(theta)/apothem,math.sin(theta)/apothem
                a=cp*c.flow_p_matrix[k,:12]+cq*c.flow_q_matrix[k,:12]+correction[:12,k]
                constant=cp*c.flow_p_constant[k]+cq*c.flow_q_constant[k]+bias[k]-correction[:,k]@c.anchor
                add(a,1-constant,f"line_current[{c.slot},{k},{face}]")
        elif not is_dominated_mess_current_row(branch):
            add(c.current_matrix[:12,k],1-c.current_constant[k],f"transformer_current[{c.slot},{k}]")
        rating=c.transformer_ratings[k]
        if rating is not None:
            for face in range(LINE_POLYGON_FACES):
                theta=2*math.pi*face/LINE_POLYGON_FACES
                cp,cq=math.cos(theta),math.sin(theta)
                a=cp*c.flow_p_matrix[k,:12]+cq*c.flow_q_matrix[k,:12]
                constant=cp*c.flow_p_constant[k]+cq*c.flow_q_constant[k]
                add(a,rating*math.cos(math.pi/LINE_POLYGON_FACES)-constant,
                    f"transformer_kva[{c.slot},{k},{face}]")
    return np.asarray(matrix),np.asarray(rhs),names


def evaluate(coefficients: tuple[SlotCoefficients,...], nodes: list[str], pcc: np.ndarray) -> dict:
    voltage=[];line=[];txcurrent=[];txkva=[];polygon=[];maxineq=[]
    branches=coefficients[0].branch_names
    linemask=np.asarray([not b.startswith("transformer.") for b in branches])
    txmask=np.asarray([b.startswith("transformer.") and not is_dominated_mess_current_row(b) for b in branches])
    for t,c in enumerate(coefficients):
        x=np.r_[pcc[t],np.zeros(48)]
        voltage.append(np.sqrt(c.voltage_constant+c.voltage_matrix.T@x))
        line.append(anchored_polygon_loading(c,x)[linemask])
        txcurrent.append((c.current_constant+c.current_matrix.T@x)[txmask])
        pf=c.flow_p_constant+c.flow_p_matrix@x
        qf=c.flow_q_constant+c.flow_q_matrix@x
        applicable=np.asarray([v is not None for v in c.transformer_ratings])
        ratings=np.asarray([v for v in c.transformer_ratings if v is not None],dtype=float)
        txkva.append(np.hypot(pf[applicable],qf[applicable])/ratings)
        faces=np.asarray([math.cos(2*math.pi*k/16)*pf[applicable]+math.sin(2*math.pi*k/16)*qf[applicable] for k in range(16)])
        polygon.append(np.max(faces,axis=0)/(ratings*math.cos(math.pi/16)))
        a,b,_=inequalities(c)
        maxineq.append(float((a@pcc[t]-b).max()))
    v=np.asarray(voltage);l=np.asarray(line);tc=np.asarray(txcurrent);tk=np.asarray(txkva);poly=np.asarray(polygon)
    vi=np.unravel_index(np.argmax(v),v.shape)
    low=np.unravel_index(np.argmin(v),v.shape)
    result={"Vmax":float(v.max()),"Vmin":float(v.min()),"slot106_Vmax":float(v[82].max()),
        "voltage_violation_count":int(((v<.95-1e-7)|(v>1.05+1e-7)).sum()),
        "line_current_violation_count":int((l>1+1e-7).sum()),
        "transformer_current_violation_count":int((tc>1+1e-7).sum()),
        "transformer_kva_violation_count":int((tk>1+1e-7).sum()),
        "transformer_polygon_violation_count":int((poly>1+1e-7).sum()),
        "max_line_loading":float(l.max()),"max_transformer_current_loading":float(tc.max()),
        "max_transformer_kva_loading":float(tk.max()),"max_transformer_polygon_loading":float(poly.max()),
        "critical_voltage_bus_phase":nodes[vi[1]],"critical_target_slot":int(vi[0]),"critical_issue_slot":int(vi[0]+24),
        "minimum_voltage_bus_phase":nodes[low[1]],"minimum_voltage_target_slot":int(low[0]),
        "all_inequalities_max_absolute_residual":max(maxineq),
        "voltage_by_slot_max":v.max(axis=1).tolist(),"voltage_by_slot_min":v.min(axis=1).tolist()}
    result["pass"]=not any(result[k] for k in result if k.endswith("violation_count"))
    return result
