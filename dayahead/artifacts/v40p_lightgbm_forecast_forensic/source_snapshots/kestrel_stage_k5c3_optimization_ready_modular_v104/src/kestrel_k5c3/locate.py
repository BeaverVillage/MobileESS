from __future__ import annotations
from pathlib import Path
from .context import Inputs
from .utils import latest_parent_with_file, read_json


def _explicit_or_latest(explicit: str, root: Path, rel: str, token: str) -> Path:
    if str(explicit).strip():
        p=Path(explicit)
        if not p.exists(): raise FileNotFoundError(f"Explicit {token} path does not exist: {p}")
        return p
    p=latest_parent_with_file(root, rel, token) or latest_parent_with_file(root, rel, None)
    if p is None: raise FileNotFoundError(f"Could not locate {token} containing {rel} under {root}")
    return p


def locate_inputs(cfg: dict, logger) -> Inputs:
    root=Path(cfg["paths"]["processed_root"])
    ex=cfg["paths"].get("explicit",{})
    k5c2=_explicit_or_latest(ex.get("k5c2_run",""),root,"reports/validation.json","stage_k5c2")
    val=read_json(k5c2/"reports/validation.json")
    if val.get("status")!="success": raise ValueError(f"K5-C2 validation is not success: {k5c2}")
    meta=read_json(k5c2/"reports/input_metadata.json") if (k5c2/"reports/input_metadata.json").exists() else {}
    k5a=Path(ex.get("k5a_run") or meta.get("k5a") or "")
    k5b3=Path(ex.get("k5b3_run") or meta.get("k5b3") or "")
    if not k5a.exists(): k5a=_explicit_or_latest("",root,"outputs/kestrel_12idc_5min_workload.parquet","stage_k5a")
    if not k5b3.exists(): k5b3=_explicit_or_latest("",root,"predictions/validation_oof_dl.parquet","stage_k5b3")
    required=[
      k5c2/"outputs/idc_fixed_forecast_2025_long.parquet",
      k5c2/"outputs/idc_inference_token_aware_2025_5min.parquet",
      k5c2/"outputs/rack_equivalent_4pool_parameters.csv",
      k5c2/"outputs/paired_h100_power_scenarios_corrected.csv",
      k5c2/"scenarios/flexible_positive_mark_library.parquet",
      k5b3/"predictions/validation_oof_dl.parquet",
      k5b3/"predictions/test_2025_frozen_dl.parquet",
      k5a/"outputs/kestrel_12idc_5min_workload.parquet",
    ]
    missing=[str(p) for p in required if not p.exists()]
    if missing: raise FileNotFoundError("Missing required inputs:\n"+"\n".join(missing))
    logger.info("Located K5-C2: %s",k5c2); logger.info("Located K5-A: %s",k5a); logger.info("Located K5-B3: %s",k5b3)
    return Inputs(k5c2,k5a,k5b3)
