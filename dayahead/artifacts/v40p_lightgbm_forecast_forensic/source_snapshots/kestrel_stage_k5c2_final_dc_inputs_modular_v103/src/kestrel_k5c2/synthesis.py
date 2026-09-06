from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def load_k5a(k5a: Path, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    site = pd.read_parquet(k5a / "outputs/kestrel_12idc_5min_workload.parquet")
    global_df = pd.read_parquet(k5a / "outputs/kestrel_global_5min_workload.parquet")
    for x in [site, global_df]:
        x["timestamp_utc"] = pd.to_datetime(x.timestamp_utc, utc=True)
    site["idc_id"] = site.idc_id.astype(str)
    return site.sort_values(["timestamp_utc", "idc_id"]).reset_index(drop=True), global_df.sort_values("timestamp_utc").reset_index(drop=True)


def _target_horizon(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"_h(\d+)$")[0].astype(int)


def load_k5b2_predictions(k5b2: Path) -> pd.DataFrame:
    p = pd.read_parquet(k5b2 / "predictions/test_2025_frozen_k5b2.parquet")
    p["timestamp_utc"] = pd.to_datetime(p.timestamp_utc, utc=True)
    p["horizon_steps"] = _target_horizon(p.target_column)
    return p


def _fixed_site_shares(site: pd.DataFrame, year: int) -> pd.DataFrame:
    sites = sorted(site.idc_id.unique())
    pre = site[site.timestamp_utc.dt.year < year]
    hist = pre.groupby("idc_id").fixed_avg_active_gpus_F30.mean().reindex(sites).fillna(0)
    hist = (hist + 1e-3) / (hist.sum() + 1e-3 * len(hist))
    cur = site[site.timestamp_utc.dt.year == year].pivot(index="timestamp_utc", columns="idc_id", values="fixed_avg_active_gpus_F30").reindex(columns=sites).fillna(0)
    smooth = cur + 0.10 * hist.to_numpy()[None, :] * max(float(cur.sum(axis=1).median()), 1.0)
    denom = smooth.sum(axis=1)
    shares = smooth.div(denom.replace(0, np.nan), axis=0)
    zero_rows = denom <= 0
    if zero_rows.any():
        shares.loc[zero_rows, :] = hist.to_numpy()[None, :]
    shares = shares.fillna(0)
    out = shares.stack().rename("fixed_site_share").reset_index()
    return out


def _flex_site_shares(site: pd.DataFrame, year: int, timezone: str) -> pd.DataFrame:
    pre = site[site.timestamp_utc.dt.year < year].copy()
    local = pre.timestamp_utc.dt.tz_convert(timezone)
    pre["local_hour"] = local.dt.hour
    pre["weekend"] = (local.dt.dayofweek >= 5).astype(int)
    metric = "arriving_flexible_gpu_hours_F30"
    agg = pre.groupby(["local_hour", "weekend", "idc_id"])[metric].sum().rename("value").reset_index()
    totals = agg.groupby(["local_hour", "weekend"]).value.transform("sum")
    agg["flex_site_share"] = np.where(totals > 0, agg.value / totals, np.nan)
    global_share = pre.groupby("idc_id")[metric].sum()
    global_share = (global_share + 1e-6) / (global_share.sum() + 1e-6 * len(global_share))
    sites = sorted(site.idc_id.unique())
    full = pd.MultiIndex.from_product([range(24), [0, 1], sites], names=["local_hour", "weekend", "idc_id"]).to_frame(index=False)
    full = full.merge(agg[["local_hour", "weekend", "idc_id", "flex_site_share"]], on=["local_hour", "weekend", "idc_id"], how="left")
    full["flex_site_share"] = full.apply(lambda r: global_share.get(r.idc_id, 1 / len(sites)) if pd.isna(r.flex_site_share) else r.flex_site_share, axis=1)
    full["flex_site_share"] = full.groupby(["local_hour", "weekend"]).flex_site_share.transform(lambda x: x / x.sum())
    return full


def build_site_forecasts(site: pd.DataFrame, k5b2_pred: pd.DataFrame, event_prob: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    year = int(cfg["analysis"]["year"])
    sites = sorted(site.idc_id.unique())
    fixed_shares = _fixed_site_shares(site, year)
    flex_shares = _flex_site_shares(site, year, cfg["analysis"]["local_timezone"])
    p = k5b2_pred.copy()
    p["family"] = np.where(p.target_column.astype(str).str.contains("fixed_avg_active_gpus"), "fixed", "flexible")
    if "event_probability" in p.columns:
        p = p.drop(columns=["event_probability"])
    ep = event_prob[["timestamp_utc", "horizon_steps", "event_probability"]].copy()
    p = p.merge(ep, on=["timestamp_utc", "horizon_steps"], how="left")
    fixed = p[p.family == "fixed"].merge(fixed_shares, on="timestamp_utc", how="left")
    fixed["idc_id"] = fixed.idc_id.astype(str)
    for c in ["selected_prediction", "prediction_p10", "prediction_p50", "prediction_p90", "actual"]:
        if c in fixed:
            fixed[f"fixed_{c}"] = fixed[c] * fixed.fixed_site_share
    keepf = ["timestamp_utc", "idc_id", "horizon_steps", "target_column", "selected_method", "fixed_site_share"] + [
        c for c in fixed.columns if c.startswith("fixed_") and c != "fixed_site_share"
    ]
    if len(keepf) != len(set(keepf)):
        duplicates = sorted({c for c in keepf if keepf.count(c) > 1})
        raise ValueError(f"Internal fixed-forecast column selection created duplicates: {duplicates}")
    fixed = fixed.loc[:, keepf]

    flex = p[p.family == "flexible"].copy()
    local = flex.timestamp_utc.dt.tz_convert(cfg["analysis"]["local_timezone"])
    flex["local_hour"] = local.dt.hour
    flex["weekend"] = (local.dt.dayofweek >= 5).astype(int)
    flex = flex.merge(flex_shares, on=["local_hour", "weekend"], how="left")
    for c in ["selected_prediction", "prediction_p10", "prediction_p50", "prediction_p90", "actual"]:
        if c in flex:
            flex[f"flexible_{c}"] = flex[c] * flex.flex_site_share
    keepx = ["timestamp_utc", "idc_id", "horizon_steps", "target_column", "selected_method", "flex_site_share", "event_probability"] + [c for c in flex.columns if c.startswith("flexible_")]
    flex = flex[keepx]
    return fixed.sort_values(["timestamp_utc", "horizon_steps", "idc_id"]), flex.sort_values(["timestamp_utc", "horizon_steps", "idc_id"])


def add_power_to_fixed_forecast(fixed: pd.DataFrame, incremental_kw_per_gpu: float, pue_values: list[float]) -> pd.DataFrame:
    x = fixed.copy()
    for c in [c for c in x if c.startswith("fixed_") and c not in {"fixed_site_share"}]:
        if c.endswith(("selected_prediction", "prediction_p10", "prediction_p50", "prediction_p90", "actual")):
            power = c.replace("fixed_", "fixed_training_incremental_") + "_kw"
            x[power] = x[c] * incremental_kw_per_gpu
    return x


def pue_sensitivity(envelope: pd.DataFrame, pue_values: list[float]) -> pd.DataFrame:
    rows = []
    base_cols = ["it_power_realized_kw", "it_power_min_deliverable_kw", "it_power_max_deliverable_kw"]
    for pue in pue_values:
        f = envelope[["timestamp_utc", "idc_id"] + base_cols].copy()
        f["pue"] = float(pue)
        f["facility_power_realized_kw"] = f.it_power_realized_kw * pue
        f["facility_power_min_deliverable_kw"] = f.it_power_min_deliverable_kw * pue
        f["facility_power_max_deliverable_kw"] = f.it_power_max_deliverable_kw * pue
        rows.append(f[["timestamp_utc", "idc_id", "pue", "facility_power_realized_kw", "facility_power_min_deliverable_kw", "facility_power_max_deliverable_kw"]])
    return pd.concat(rows, ignore_index=True)
