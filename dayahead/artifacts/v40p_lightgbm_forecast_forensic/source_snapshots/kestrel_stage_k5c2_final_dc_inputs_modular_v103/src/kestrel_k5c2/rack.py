from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .utils import round_up_multiple, stable_largest_remainder


def derive_site_capacities(site: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    q = float(cfg["power"]["training_utilization_quantile"])
    target = float(cfg["power"]["installed_capacity_target_utilization"])
    multiple = int(cfg["power"]["capacity_rounding_gpus"])
    rows = []
    for idc, g in site.groupby("idc_id"):
        peak = float(g.total_avg_active_gpus.quantile(q))
        minimum_capacity = multiple * int(cfg["analysis"]["rack_pool_count"])
        cap = int(round_up_multiple([max(peak / target, minimum_capacity)], multiple)[0])
        rows.append({
            "idc_id": str(idc), "active_gpu_quantile": q, "active_gpu_at_quantile": peak,
            "target_utilization": target, "installed_gpu_capacity": cap,
            "observed_max_active_gpu": float(g.total_avg_active_gpus.max()),
        })
    return pd.DataFrame(rows).sort_values("idc_id").reset_index(drop=True)


def build_rack_parameters(k4d: Path, capacities: pd.DataFrame, power_main: pd.Series, paired: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    factors = pd.read_csv(k4d / "allnodes/rack_equivalent_pool_factors.csv")
    pool_count = int(cfg["analysis"]["rack_pool_count"])
    factors = factors[factors.pool_count.astype(int).eq(pool_count)].sort_values("pool_id").copy()
    if len(factors) != pool_count:
        raise ValueError(f"Expected {pool_count} rack pool factors, found {len(factors)}")
    cap_share = factors.node_count_share.to_numpy(float)
    cap_proxy = factors.cap_proxy_share.to_numpy(float)
    idle_proxy = factors.idle_proxy_share.to_numpy(float)
    blend = float(cfg["power"]["rack_idle_share_blend"])
    idle_share = blend * idle_proxy + (1 - blend) * cap_share
    idle_share = idle_share / idle_share.sum()
    cap_proxy = cap_proxy / cap_proxy.sum()
    high = paired.loc[paired.scenario.eq("high")].iloc[0]
    rows = []
    for r in capacities.itertuples(index=False):
        gpu_caps = stable_largest_remainder(int(r.installed_gpu_capacity), cap_share, int(cfg["power"]["capacity_rounding_gpus"]))
        total_idle = float(r.installed_gpu_capacity) * float(power_main.idle_it_kw_per_gpu)
        total_cap = float(r.installed_gpu_capacity) * float(high.gross_it_kw_per_gpu) * float(cfg["power"]["rack_cap_margin"])
        rack_idle = total_idle * idle_share
        rack_power_cap_proxy = total_cap * cap_proxy
        # Keep Eagle cap heterogeneity while guaranteeing that each virtual pool can
        # operate at 90% of its assigned H100 capacity under the main coefficient.
        cap_floor = rack_idle + gpu_caps * float(power_main.incremental_it_kw_per_gpu) * 0.90
        rack_power_cap = np.maximum(rack_power_cap_proxy, cap_floor)
        for j in range(pool_count):
            power_limited = max((rack_power_cap[j] - rack_idle[j]) / max(float(power_main.incremental_it_kw_per_gpu), 1e-9), 0)
            rows.append({
                "idc_id": r.idc_id, "pool_id": int(factors.iloc[j].pool_id),
                "installed_gpu_capacity": int(gpu_caps[j]),
                "idle_it_kw": float(rack_idle[j]), "rack_power_cap_kw": float(rack_power_cap[j]),
                "power_limited_active_gpu": float(power_limited),
                "deliverable_active_gpu_capacity": float(min(gpu_caps[j], power_limited)),
                "eagle_node_count_share": cap_share[j], "eagle_idle_share_blended": idle_share[j],
                "eagle_cap_proxy_share": cap_proxy[j], "power_cap_proxy_kw_before_floor": float(rack_power_cap_proxy[j]),
                "power_cap_floor_kw": float(cap_floor[j]), "source_cluster": factors.iloc[j].cluster,
                "source": "Eagle relative rack heterogeneity scaled to Kestrel/NLR H100 absolute power",
            })
    out = pd.DataFrame(rows)
    return out


def rack_envelope(site: pd.DataFrame, rack_params: pd.DataFrame, inference: pd.DataFrame, power_main: pd.Series, cfg: dict) -> pd.DataFrame:
    main_pue = float(cfg["power"]["main_pue"])
    other_frac = float(cfg["power"]["other_static_fraction_of_idle"])
    cap = rack_params.groupby("idc_id", as_index=False).agg(
        training_idle_kw=("idle_it_kw", "sum"),
        deliverable_max_active_gpus=("deliverable_active_gpu_capacity", "sum"),
        rack_power_cap_kw=("rack_power_cap_kw", "sum"),
    )
    cols = ["timestamp_utc", "idc_id", "total_avg_active_gpus", "fixed_avg_active_gpus_F30", "flexible_avg_active_gpus_F30"]
    x = site[cols].copy()
    x["timestamp_utc"] = pd.to_datetime(x.timestamp_utc, utc=True)
    x = x.merge(cap, on="idc_id", how="left").merge(
        inference[["timestamp_utc", "idc_id", "inference_idle_kw", "inference_request_incremental_kw", "inference_it_kw"]],
        on=["timestamp_utc", "idc_id"], how="left")
    x[["inference_idle_kw", "inference_request_incremental_kw", "inference_it_kw"]] = x[["inference_idle_kw", "inference_request_incremental_kw", "inference_it_kw"]].fillna(0)
    inc = float(power_main.incremental_it_kw_per_gpu)
    x["other_static_kw"] = other_frac * (x.training_idle_kw + x.inference_idle_kw)
    x["training_incremental_realized_kw"] = x.total_avg_active_gpus * inc
    x["training_incremental_fixed_kw"] = x.fixed_avg_active_gpus_F30 * inc
    x["training_it_realized_kw"] = x.training_idle_kw + x.training_incremental_realized_kw
    x["it_power_realized_kw"] = x.training_it_realized_kw + x.inference_it_kw + x.other_static_kw
    x["it_power_min_deliverable_kw"] = x.training_idle_kw + x.training_incremental_fixed_kw + x.inference_it_kw + x.other_static_kw
    x["it_power_max_deliverable_kw"] = x.training_idle_kw + x.deliverable_max_active_gpus * inc + x.inference_it_kw + x.other_static_kw
    x["facility_power_realized_kw"] = main_pue * x.it_power_realized_kw
    x["facility_power_min_deliverable_kw"] = main_pue * x.it_power_min_deliverable_kw
    x["facility_power_max_deliverable_kw"] = main_pue * x.it_power_max_deliverable_kw
    x["available_downward_flex_kw"] = (x.it_power_realized_kw - x.it_power_min_deliverable_kw).clip(lower=0)
    x["available_upward_flex_kw"] = (x.it_power_max_deliverable_kw - x.it_power_realized_kw).clip(lower=0)
    x["observed_active_exceeds_deliverable"] = x.total_avg_active_gpus > x.deliverable_max_active_gpus + 1e-9
    return x
