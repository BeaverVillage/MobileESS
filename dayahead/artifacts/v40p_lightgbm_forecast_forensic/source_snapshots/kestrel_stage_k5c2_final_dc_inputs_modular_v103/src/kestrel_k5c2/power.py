from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class PowerParameters:
    paired_scenarios: pd.DataFrame
    main: pd.Series
    inference: dict
    audit: dict


def build_power_parameters(k4b: Path, site_workload: pd.DataFrame, site_capacities: pd.DataFrame, cfg: dict) -> PowerParameters:
    run_path = k4b / "outputs/nlr_genai_run_power_features.parquet"
    if run_path.exists():
        runs = pd.read_parquet(run_path)
    else:
        runs = pd.read_csv(k4b / "outputs/nlr_genai_run_power_features.csv")
    tr = runs[runs.family_id.astype(str).eq("training")].copy()
    for c in ["gross_mean_kw_per_gpu", "incremental_mean_kw_per_gpu"]:
        tr[c] = pd.to_numeric(tr[c], errors="coerce")
    tr = tr.dropna(subset=["gross_mean_kw_per_gpu", "incremental_mean_kw_per_gpu"])
    tr["idle_it_kw_per_gpu"] = (tr.gross_mean_kw_per_gpu - tr.incremental_mean_kw_per_gpu).clip(lower=0)

    mean_active = float(site_workload.groupby("timestamp_utc").total_avg_active_gpus.sum().mean())
    installed = float(site_capacities.installed_gpu_capacity.sum())
    u_ref = float(np.clip(mean_active / max(installed, 1e-9), 0.05, 0.95))
    tr["effective_it_kw_per_gpu_at_u_ref"] = tr.idle_it_kw_per_gpu + u_ref * tr.incremental_mean_kw_per_gpu
    tr = tr.sort_values("effective_it_kw_per_gpu_at_u_ref", kind="stable").reset_index(drop=True)
    rows = []
    for scenario, q in [("low", 0.1), ("median", 0.5), ("high", 0.9)]:
        idx = int(np.clip(round(q * (len(tr) - 1)), 0, len(tr) - 1))
        r = tr.iloc[idx]
        rows.append({
            "scenario": scenario, "quantile": q, "paired_run_id": r.run_id,
            "model_family": r.get("model_family", "unknown"), "nodes": r.get("nodes", np.nan),
            "gpu_count_configured": r.get("gpu_count_configured", np.nan),
            "gross_it_kw_per_gpu": r.gross_mean_kw_per_gpu,
            "incremental_it_kw_per_gpu": r.incremental_mean_kw_per_gpu,
            "idle_it_kw_per_gpu": r.idle_it_kw_per_gpu,
            "effective_it_kw_per_gpu_at_u_ref": r.effective_it_kw_per_gpu_at_u_ref,
            "representative_utilization": u_ref,
            "identity_error_kw_per_gpu": r.gross_mean_kw_per_gpu - r.incremental_mean_kw_per_gpu - r.idle_it_kw_per_gpu,
            "method": "paired_empirical_effective_power_order_statistic",
        })
    paired = pd.DataFrame(rows)
    # Defensive ordering check on the actual scenario ranking quantity.
    if not np.all(np.diff(paired.effective_it_kw_per_gpu_at_u_ref.to_numpy(float)) >= -1e-12):
        raise AssertionError("Corrected paired scenarios are not ordered by effective power")
    main = paired.loc[paired.scenario.eq("median")].iloc[0]

    inf_family = str(cfg["power"]["inference_family"])
    inf_scenario = str(cfg["power"]["inference_scenario"])
    inf = runs[runs.family_id.astype(str).eq(inf_family)].copy()
    inf["idle_reference_kw"] = pd.to_numeric(inf.idle_reference_kw, errors="coerce")
    idle_kw = float(inf.idle_reference_kw.dropna().median())
    req = pd.read_csv(k4b / "outputs/inference_energy_per_request_scenarios.csv")
    rr = req[(req.family_id.astype(str) == inf_family) & (req.scenario.astype(str) == inf_scenario)]
    if rr.empty:
        raise ValueError(f"Inference request energy missing for {inf_family}/{inf_scenario}")
    request_incremental_wh = float(rr.iloc[0].incremental_wh_per_request)
    request_gross_wh = float(rr.iloc[0].gross_wh_per_request)
    inference = {
        "family_id": inf_family, "scenario": inf_scenario,
        "idle_kw_per_group": idle_kw, "incremental_wh_per_request": request_incremental_wh,
        "gross_wh_per_request": request_gross_wh,
        "groups_per_site": int(cfg["power"]["inference_groups_per_site"]),
    }
    audit = {
        "training_run_count": len(tr), "representative_utilization": u_ref,
        "global_mean_active_gpus": mean_active, "global_installed_gpu_capacity": installed,
        "inference_run_count": len(inf), **inference,
    }
    return PowerParameters(paired, main, inference, audit)


def apply_token_aware_inference(annual: pd.DataFrame, inference: dict, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = annual.copy()
    e_req = float(inference["incremental_wh_per_request"])
    interval_h = float(cfg["analysis"]["interval_minutes"]) / 60.0
    scenario_rows = []
    main_weight = float(cfg["power"]["output_token_compute_weight"])
    for weight in cfg["power"]["token_weight_sensitivity"]:
        weight = float(weight)
        weighted = out.request_tokens.to_numpy(float) + weight * out.response_tokens.to_numpy(float)
        weighted = np.where(weighted > 0, weighted, np.maximum(out.total_tokens.to_numpy(float), 1.0))
        tmp = out[["timestamp_utc", "idc_id", "trace_group", "request_count"]].copy()
        tmp["token_weight"] = weight
        tmp["weighted_tokens_sensitivity"] = weighted
        # Preserve each trace group's exact request-energy total while redistributing by token work.
        group_total_energy = out.groupby("trace_group").request_count.transform("sum").to_numpy(float) * e_req
        group_total_weight = pd.Series(weighted, index=out.index).groupby(out.trace_group).transform("sum").to_numpy(float)
        energy_wh = np.divide(group_total_energy * weighted, group_total_weight, out=np.zeros_like(weighted), where=group_total_weight > 0)
        tmp["inference_request_energy_wh"] = energy_wh
        tmp["inference_request_incremental_kw"] = energy_wh / 1000.0 / interval_h
        scenario_rows.append(tmp)
        if abs(weight - main_weight) < 1e-9:
            out["token_weight"] = weight
            out["weighted_tokens_main"] = weighted
            out["inference_request_energy_wh"] = energy_wh
            out["inference_request_incremental_kw"] = energy_wh / 1000.0 / interval_h
    out["inference_idle_kw"] = float(inference["idle_kw_per_group"]) * int(inference["groups_per_site"])
    out["inference_it_kw"] = out.inference_idle_kw + out.inference_request_incremental_kw
    sensitivity = pd.concat(scenario_rows, ignore_index=True)
    conservation = sensitivity.groupby(["trace_group", "token_weight"], as_index=False).agg(
        request_count=("request_count", "sum"), energy_wh=("inference_request_energy_wh", "sum"))
    conservation["expected_energy_wh"] = conservation.request_count * e_req
    conservation["relative_error"] = (conservation.energy_wh - conservation.expected_energy_wh).abs() / conservation.expected_energy_wh.clip(lower=1e-12)
    return out, conservation
