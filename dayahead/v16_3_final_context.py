"""Build frozen per-day V16.3 contexts after final eligibility release."""

from __future__ import annotations

import json
from pathlib import Path

from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_b3_v16_2 import B3Inputs
from .full_ieee123_g11_v16_1 import build_full_grid_binding
from .grid_background_v16_2 import build_authority_background_binding
from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import _beta_reference
from .run_authority_semantic_g11_v16_2 import _default_background_paths
from .run_v16_3_correction import _generate_current_day
from .run_v16_3_voltage_candidate import _anchor_and_sensitivity_day


def reference_delta_diagnostic(repo: Path, output: Path, day: str) -> dict[str, object]:
    """Reproduce a frozen reference construction failure without repairing it."""
    import pandas as pd
    from .aidc_boundary_v16_1 import build_reference_schedule_v3

    forecast_path = output / "cache/V16_3_FINAL_AIDC_DA_FORECAST.parquet"
    arrivals, p_ref, g_ref = final_forecast_day(pd.read_parquet(forecast_path), day)
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    scaled_arrivals = {cohort: tuple(.25 * value for value in values) for cohort, values in arrivals.items()}
    capacities = {rack.rack_id: .25 * rack.deliverable_gpu_capacity for rack in authority.racks}
    reference = build_reference_schedule_v3(tuple(capacities), capacities, scaled_arrivals)
    p_res = tuple(.25 * p_ref[t] - sum(reference.flexible_power_kw[t]) for t in range(96))
    g_res = tuple(.25 * g_ref[t] - sum(reference.flexible_gpu[t]) for t in range(96))
    return {
        "day": day,
        "status": "FROZEN_REFERENCE_CONSTRUCTION_INFEASIBLE",
        "reason": "PENETRATION_REFERENCE_RESIDUAL_NEGATIVE",
        "power_residual": {"min": min(p_res), "max": max(p_res), "negative_slot_count": sum(v < -1e-6 for v in p_res)},
        "gpu_residual": {
            "min": min(g_res), "max": max(g_res),
            "negative_slot_count": sum(v < -1e-6 for v in g_res),
            "first_negative_slot": next((t for t, v in enumerate(g_res) if v < -1e-6), None),
            "first_negative_value": next((v for v in g_res if v < -1e-6), None),
            "worst_slot": min(range(96), key=g_res.__getitem__),
        },
        "clipping_calls": 0, "redistribution_calls": 0, "optimization_calls": 0,
    }


def final_forecast_day(frame, operating_day: str):
    selected=frame[(frame["model"]=="Proposed AIDC RC-MQT")&(frame["namespace"]=="V16_3_FINAL_OUT_OF_SAMPLE")&(frame["forecast_day"]==operating_day)]
    targets=tuple(sorted(map(str,selected["target"].unique())))
    if len(targets)!=17: raise RuntimeError(f"FINAL_FORECAST_TARGET_AXIS:{operating_day}")
    def values(target:str,q:float):
        rows=selected[(selected["target"]==target)&(selected["quantile"]==q)].sort_values("slot")
        if tuple(map(int,rows["slot"]))!=tuple(range(96)): raise RuntimeError(f"FINAL_DIRECT96:{operating_day}:{target}:{q}")
        return tuple(map(float,rows["prediction"]))
    for target in targets:
        q10=values(target,.1);q50=values(target,.5);q90=values(target,.9)
        if any(a>b+1e-12 or b>c+1e-12 for a,b,c in zip(q10,q50,q90)): raise RuntimeError("FINAL_QUANTILE_ORDER")
    cohorts=tuple(target.split("::",1)[1] for target in targets if target.startswith("W_F::"))
    return {c:values(f"W_F::{c}",.5) for c in cohorts},values("P_IT_REF",.9),values("G_REF",.9)


def build_context(repo:Path,source:Path,output:Path,day:str,*,prepare:bool):
    import numpy as np
    import pandas as pd
    forecast_path=output/"cache/V16_3_FINAL_AIDC_DA_FORECAST.parquet"
    vintages=json.loads((output/"cache/V16_3_FINAL_AEMO_VINTAGES.json").read_text(encoding="utf-8"))
    eligibility=json.loads((output/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json").read_text(encoding="utf-8"))
    if day not in {row["operating_day"] for row in eligibility["included"]}: raise RuntimeError(f"FINAL_DAY_NOT_ELIGIBLE:{day}")
    arrivals,p_ref,g_ref=final_forecast_day(pd.read_parquet(forecast_path),day)
    rack_contract=json.loads((repo/"dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority=load_frozen_rack_authority(Path(rack_contract["source_path"]))
    reference=_beta_reference(authority,arrivals,p_ref,g_ref,.25)
    vintage=vintages[day]
    background=build_authority_background_binding(timestamps_fixed_aest=vintage["timestamps_96"],demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],paths=_default_background_paths(repo,source))
    binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",demand_mw_96=vintage["demand_mw_96"],rooftop_pv_mw_96=vintage["pv_mw_96"],aidc_plan_kw_96x12=reference["plan_kw_96x12"],pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",background_binding=background)
    data=output/"cache/data";data.mkdir(parents=True,exist_ok=True)
    voltage_path=data/f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    context=(reference,vintage,background,binding,voltage_path,authority)
    records={}
    if prepare:
        records["voltage"]=_anchor_and_sensitivity_day(repo,source,background,reference["plan_kw_96x12"],binding,day,voltage_path)
        records["current"]=_generate_current_day(repo,source,output/"cache",day,context)
    current_path=data/f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    if not voltage_path.is_file() or not current_path.is_file(): raise RuntimeError(f"FINAL_D1_CACHE_MISSING:{day}")
    c7=json.loads((repo/"dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    inputs=B3Inputs(cohorts=tuple(sorted(reference["arrivals"])),arrivals={k:tuple(map(float,v)) for k,v in reference["arrivals"].items()},rack_ids=tuple(r.rack_id for r in authority.racks),rack_aidc=tuple(r.aidc_id for r in authority.racks),gpu_capacity=tuple(map(float,reference["gpu_capacities"])),p_res_aidc_kw=tuple(tuple(map(float,row)) for row in reference["p_res_aidc"]),g_res_rack=tuple(tuple(map(float,row)) for row in reference["g_res_rack"]),mess_records=c7["mess_invariants"]["records"],evidence={"operating_day":day,"beta":.25,"forecast_sha256":sha256_file(forecast_path),"reference_service_parity":reference["evidence"]["service_parity_max_abs_nodeh"]})
    return context,inputs,records
