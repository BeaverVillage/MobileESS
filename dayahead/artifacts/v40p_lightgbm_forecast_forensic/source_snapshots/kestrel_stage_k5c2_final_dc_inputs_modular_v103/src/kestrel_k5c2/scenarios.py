from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class ScenarioArtifacts:
    mark_library: pd.DataFrame
    event_hazard_wide: pd.DataFrame
    representative_scenarios: pd.DataFrame
    calibration_audit: pd.DataFrame


def build_mark_library(site_workload: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    main = cfg["analysis"]["main_flexibility_case"]
    gh = f"arriving_flexible_gpu_hours_{main}"
    jc = f"arriving_flexible_job_count_{main}"
    x = site_workload[["timestamp_utc", "idc_id", gh, jc]].copy()
    x["timestamp_utc"] = pd.to_datetime(x.timestamp_utc, utc=True)
    x = x[x.timestamp_utc.dt.year < int(cfg["analysis"]["year"])].copy()
    x[gh] = pd.to_numeric(x[gh], errors="coerce").fillna(0).clip(lower=0)
    x[jc] = pd.to_numeric(x[jc], errors="coerce").fillna(0).clip(lower=0)
    x = x[(x[gh] > 0) & (x[jc] > 0)].copy()
    if x.empty:
        raise ValueError("No positive development flexible marks")
    local = x.timestamp_utc.dt.tz_convert(cfg["analysis"]["local_timezone"])
    x["local_hour"] = local.dt.hour
    x["weekend"] = (local.dt.dayofweek >= 5).astype(int)
    x["gpu_hours_per_job"] = x[gh] / x[jc]
    x["sampling_weight"] = x[jc]
    x.rename(columns={gh: "slot_flexible_gpu_hours", jc: "slot_flexible_job_count"}, inplace=True)
    return x[["timestamp_utc", "idc_id", "local_hour", "weekend", "slot_flexible_gpu_hours", "slot_flexible_job_count", "gpu_hours_per_job", "sampling_weight"]].reset_index(drop=True)


def build_hazard(probabilities: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    horizons = list(map(int, cfg["analysis"]["horizons_steps"]))
    max_h = int(cfg["scenarios"]["max_horizon_steps"])
    p = probabilities.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability").sort_index()
    missing = set(horizons) - set(p.columns)
    if missing:
        raise KeyError(f"Event probabilities missing horizons: {sorted(missing)}")
    parr = np.maximum.accumulate(np.clip(p[horizons].to_numpy(float), 1e-6, 1 - 1e-6), axis=1)
    cum_intensity_knots = -np.log1p(-parr)
    grid = np.arange(max_h + 1)
    knots = np.array([0] + horizons, dtype=float)
    wide = np.zeros((len(p), max_h), dtype=np.float32)
    audits = []
    for i in range(len(p)):
        vals = np.r_[0.0, cum_intensity_knots[i]]
        cum = np.interp(grid, knots, vals)
        lam = np.diff(cum)
        lam = np.clip(lam, 0, None)
        wide[i] = lam
        recovered = 1 - np.exp(-np.cumsum(lam))
        for j, h in enumerate(horizons):
            audits.append({"timestamp_utc": p.index[i], "horizon_steps": h, "input_probability": parr[i, j], "recovered_probability": recovered[h - 1], "absolute_error": abs(parr[i, j] - recovered[h - 1])})
    out = pd.DataFrame(wide, columns=[f"lambda_step_{i:02d}" for i in range(1, max_h + 1)])
    out.insert(0, "timestamp_utc", p.index)
    for j, h in enumerate(horizons):
        out[f"event_probability_h{h:02d}"] = parr[:, j]
    return out.reset_index(drop=True), pd.DataFrame(audits)


def _hour_bin(hour: int, edges: list[int]) -> str:
    for a, b in zip(edges[:-1], edges[1:]):
        if a <= hour < b:
            return f"h{a:02d}_{b:02d}"
    return f"h{edges[-2]:02d}_{edges[-1]:02d}"


def _sample_marks(rng, lib: pd.DataFrame, n: int) -> tuple[np.ndarray, np.ndarray]:
    if n <= 0:
        return np.empty(0), np.empty(0, dtype=object)
    w = lib.sampling_weight.to_numpy(float)
    w = w / w.sum()
    idx = rng.choice(len(lib), size=n, replace=True, p=w)
    return lib.gpu_hours_per_job.to_numpy(float)[idx], lib.idc_id.astype(str).to_numpy()[idx]


def representative_scenarios(hazard: pd.DataFrame, mark_library: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rng = np.random.default_rng(int(cfg["scenarios"]["random_seed"]))
    edges = list(map(int, cfg["scenarios"]["representative_hour_bins"]))
    nsc = int(cfg["scenarios"]["representative_scenarios_per_stratum"])
    tz = cfg["analysis"]["local_timezone"]
    max_h = int(cfg["scenarios"]["max_horizon_steps"])
    h = hazard.copy()
    local = pd.to_datetime(h.timestamp_utc, utc=True).dt.tz_convert(tz)
    h["hour_bin"] = [_hour_bin(x, edges) for x in local.dt.hour]
    h["weekend"] = (local.dt.dayofweek >= 5).astype(int)
    mark = mark_library.copy()
    mark["hour_bin"] = [_hour_bin(x, edges) for x in mark.local_hour]
    rows = []
    lambda_cols = [f"lambda_step_{i:02d}" for i in range(1, max_h + 1)]
    for (hour_bin, weekend), g in h.groupby(["hour_bin", "weekend"]):
        lam = g[lambda_cols].median().to_numpy(float)
        lib = mark[(mark.hour_bin == hour_bin) & (mark.weekend == weekend)]
        if len(lib) < int(cfg["scenarios"]["minimum_positive_marks_per_stratum"]):
            lib = mark[mark.weekend == weekend]
        if lib.empty:
            lib = mark
        for s in range(nsc):
            counts = rng.poisson(lam)
            for step, count in enumerate(counts, start=1):
                marks, sites = _sample_marks(rng, lib, int(count))
                if count == 0:
                    rows.append({"hour_bin": hour_bin, "weekend": weekend, "scenario_id": s, "horizon_step": step, "event_count": 0, "flexible_gpu_hours": 0.0, "idc_allocations": ""})
                else:
                    alloc = pd.DataFrame({"idc_id": sites, "gpu_hours": marks}).groupby("idc_id").gpu_hours.sum()
                    rows.append({"hour_bin": hour_bin, "weekend": weekend, "scenario_id": s, "horizon_step": step, "event_count": int(count), "flexible_gpu_hours": float(marks.sum()), "idc_allocations": ";".join(f"{k}:{v:.6f}" for k, v in alloc.items())})
    return pd.DataFrame(rows)


def build(probabilities: pd.DataFrame, site_workload: pd.DataFrame, cfg: dict) -> ScenarioArtifacts:
    marks = build_mark_library(site_workload, cfg)
    hazard, audit = build_hazard(probabilities, cfg)
    reps = representative_scenarios(hazard, marks, cfg)
    return ScenarioArtifacts(marks, hazard, reps, audit)


def generate_for_origin(hazard_row: pd.Series, mark_library: pd.DataFrame, n_scenarios: int, cfg: dict, seed: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(int(cfg["scenarios"]["random_seed"] if seed is None else seed))
    max_h = int(cfg["scenarios"]["max_horizon_steps"])
    lam = np.array([hazard_row[f"lambda_step_{i:02d}"] for i in range(1, max_h + 1)], dtype=float)
    ts = pd.Timestamp(hazard_row.timestamp_utc)
    local = ts.tz_convert(cfg["analysis"]["local_timezone"])
    weekend = int(local.dayofweek >= 5)
    hour_bin = _hour_bin(int(local.hour), list(map(int, cfg["scenarios"]["representative_hour_bins"])))
    mark = mark_library.copy()
    if "hour_bin" not in mark.columns:
        mark["hour_bin"] = [_hour_bin(int(x), list(map(int, cfg["scenarios"]["representative_hour_bins"]))) for x in mark.local_hour]
    lib = mark[(mark.weekend == weekend) & (mark.hour_bin == hour_bin)]
    if len(lib) < int(cfg["scenarios"]["minimum_positive_marks_per_stratum"]):
        lib = mark[mark.weekend == weekend]
    if lib.empty:
        lib = mark
    rows = []
    for s in range(n_scenarios):
        counts = rng.poisson(lam)
        for step, count in enumerate(counts, start=1):
            marks, sites = _sample_marks(rng, lib, int(count))
            if count:
                alloc = pd.DataFrame({"idc_id": sites, "gpu_hours": marks}).groupby("idc_id").gpu_hours.sum()
                alloc_text = ";".join(f"{k}:{v:.6f}" for k, v in alloc.items())
            else:
                alloc_text = ""
            rows.append({"origin_timestamp_utc": ts, "origin_hour_bin": hour_bin, "origin_weekend": weekend, "scenario_id": s, "horizon_step": step, "event_count": int(count), "flexible_gpu_hours": float(marks.sum()) if count else 0.0, "idc_allocations": alloc_text})
    return pd.DataFrame(rows)
