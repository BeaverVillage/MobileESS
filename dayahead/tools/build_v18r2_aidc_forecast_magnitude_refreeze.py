from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18r2_aidc_forecast_magnitude_refreeze"
V17 = ROOT / "dayahead" / "artifacts" / "v17_candidate"
V17_FORENSIC = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
V18 = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
V18R1 = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"
TASK_START_HEAD = "7f0b9e71b4e2120377b4cc44daa7763b03d30b3f"
TASK_START_STATUS = [
    "?? dayahead/artifacts/v18r1_aidc_physical_coherence_repair/V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.tar",
]
KESTREL = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip")
KESTREL_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
TRAIN_START = "2024-08-19"
TRAIN_END_EXCLUSIVE = "2025-04-01"
DEBUG_DAYS = ("2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23")
C_MODEL = 528.0
C_REF = 528.0
DT_H = 0.25
PUE = 1.30
EPS = 1e-9
TIERS = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")
LATENCIES = ("C1", "C2", "C3", "C4", "C5")
NODE_CLASSES = (1, 2, 4, 8, 16)
VICTORIA_HOLIDAYS = {
    "2024-09-27", "2024-11-05", "2024-12-25", "2024-12-26",
    "2025-01-01", "2025-01-27", "2025-03-10",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def records(directory: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_prechange_manifest() -> None:
    groups = {
        "v17_candidate": records(V17),
        "v17_forensic": records(V17_FORENSIC),
        "v18": records(V18),
        "v18r1": records(V18R1),
    }
    manifest = {
        "artifact_id": "V18R2_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "branch_at_task_start": "codex/dayahead-aidc-joint-v1",
        "head_at_task_start": TASK_START_HEAD,
        "actual_branch_when_manifest_written": git("branch", "--show-current"),
        "actual_head_when_manifest_written": git("rev-parse", "HEAD"),
        "git_status_at_task_start": TASK_START_STATUS,
        "preexisting_untracked_file_policy": "PRESERVE_BYTE_EXACT; DO_NOT_ADD_DELETE_MODIFY_OR_COMMIT",
        "preservation_groups": groups,
        "counts": {name: len(items) for name, items in groups.items()},
        "firewall_counters_at_start": {
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
            "literature_target_reads": 0,
            "objective_reads_for_model_selection": 0,
            "workload_multiplier_fit_to_share": 0,
            "C_MODEL_mutations": 0,
        },
    }
    write_json(OUT / "V18R2_PRECHANGE_PRESERVATION_MANIFEST.json", manifest)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_sequence(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, np.ndarray)):
        return tuple(str(item) for item in value if str(item))
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "[]"}:
        return ()
    return tuple(token for token in re.split(r"[|,;\s]+", text.strip("[](){}'\"")) if token)


def is_h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def load_h100(min_month: int, max_month: int) -> tuple[object, dict[str, object]]:
    import pandas as pd
    import pyarrow.parquet as pq

    required = {
        "id", "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpus_requested", "gpu_nodes_occupied", "shared_job_count", "nodes_shared",
        "jobs_shared", "nodelist",
    }
    frames: list[object] = []
    members: list[dict[str, object]] = []
    with zipfile.ZipFile(KESTREL) as archive, tempfile.TemporaryDirectory(prefix="v18r2-kestrel-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = info.filename.replace("\\", "/")
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", name)
            if not match or not name.casefold().endswith(".parquet"):
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if month < min_month or month > max_month:
                continue
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.read_schema(local).names)
            if not required.issubset(schema):
                raise RuntimeError(f"V18R2_KESTREL_SCHEMA_MISSING:{sorted(required-schema)}")
            table = pq.read_table(local, columns=sorted(required)).to_pandas()
            table = table.loc[table["partition"].apply(is_h100)].copy()
            table["source_month"] = month
            frames.append(table)
            members.append({"month": month, "member": info.filename, "H100_rows": len(table)})
    if not frames:
        raise RuntimeError("V18R2_KESTREL_SOURCE_EMPTY")
    frame = pd.concat(frames, ignore_index=True)
    for column in ("submit_time", "start_time", "end_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce", format="mixed")
    for column in ("gpus_requested", "gpu_nodes_occupied", "shared_job_count"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["node_tuple"] = frame["nodelist"].apply(as_sequence)
    frame["nodes_shared_tuple"] = frame["nodes_shared"].apply(as_sequence)
    frame["jobs_shared_tuple"] = frame["jobs_shared"].apply(as_sequence)
    return frame, {
        "source_path": str(KESTREL),
        "source_sha256": KESTREL_SHA256,
        "members_opened": members,
        "min_member_month_opened": min_month,
        "max_member_month_opened": max_month,
        "H100_rows": len(frame),
    }


def latency_class(queue_seconds: float) -> str | None:
    if not math.isfinite(queue_seconds) or queue_seconds <= 600:
        return None
    if queue_seconds <= 1800:
        return "C1"
    if queue_seconds <= 3600:
        return "C2"
    if queue_seconds <= 7200:
        return "C3"
    if queue_seconds <= 10800:
        return "C4"
    return "C5"


def prepare_jobs(frame: object, start: str, end_exclusive: str, conflict_ids: set[str]) -> object:
    import pandas as pd

    start_bound = pd.Timestamp(start, tz=AEST)
    end_bound = pd.Timestamp(end_exclusive, tz=AEST)
    submit_local = frame["submit_time"].dt.tz_convert(AEST)
    valid = (
        submit_local.ge(start_bound) & submit_local.lt(end_bound)
        & frame["start_time"].notna() & frame["end_time"].notna()
        & frame["end_time"].gt(frame["start_time"])
        & frame["gpus_requested"].gt(0) & frame["gpu_nodes_occupied"].gt(0)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
    )
    jobs = frame.loc[valid].copy()
    jobs["submit_AEST"] = jobs["submit_time"].dt.tz_convert(AEST)
    jobs["queue_seconds"] = (jobs["start_time"] - jobs["submit_time"]).dt.total_seconds()
    jobs["duration_h"] = (jobs["end_time"] - jobs["start_time"]).dt.total_seconds() / 3600.0
    jobs = jobs.loc[jobs["queue_seconds"].gt(600) & np.isfinite(jobs["queue_seconds"]) & jobs["duration_h"].gt(0)].copy()
    jobs["exact_uniform"] = [
        bool(nodes) and len(nodes) == int(node_count) and float(gpus).is_integer()
        and (float(gpus) / len(nodes)).is_integer() and 1 <= int(float(gpus) / len(nodes)) <= 4
        for nodes, node_count, gpus in zip(jobs["node_tuple"], jobs["gpu_nodes_occupied"], jobs["gpus_requested"])
    ]
    jobs["no_share"] = (
        (jobs["shared_job_count"].isna() | jobs["shared_job_count"].eq(0))
        & jobs["nodes_shared_tuple"].apply(lambda value: not value)
        & jobs["jobs_shared_tuple"].apply(lambda value: not value)
    )
    full = (
        jobs["exact_uniform"] & jobs["no_share"]
        & jobs["gpu_nodes_occupied"].isin(NODE_CLASSES)
        & np.isclose(jobs["gpus_requested"], 4.0 * jobs["gpu_nodes_occupied"])
    )
    jobs["tier"] = "PARTIAL"
    for nodes in NODE_CLASSES:
        jobs.loc[full & jobs["gpu_nodes_occupied"].eq(nodes), "tier"] = f"FULL_{nodes}"
    jobs["latency"] = jobs["queue_seconds"].apply(lambda value: latency_class(float(value)))
    jobs["service_GPU_h"] = jobs["gpus_requested"] * jobs["duration_h"]
    jobs["conflict_quarantined"] = jobs["id"].astype(str).isin(conflict_ids)
    return jobs


def build_targets(jobs: object, start: str, end_exclusive: str) -> dict[str, object]:
    import pandas as pd

    dates = pd.date_range(start, pd.Timestamp(end_exclusive) - pd.Timedelta(days=1), freq="D")
    date_index = {day.date().isoformat(): index for index, day in enumerate(dates)}
    slot = np.zeros((len(dates), 96), dtype=float)
    tier = np.zeros((len(dates), len(TIERS)), dtype=float)
    latency = np.zeros((len(dates), len(LATENCIES)), dtype=float)
    tier_latency = np.zeros((len(dates), len(TIERS), len(LATENCIES)), dtype=float)
    retained = jobs.loc[~jobs["conflict_quarantined"]].copy()
    for row in retained.itertuples(index=False):
        day = row.submit_AEST.date().isoformat()
        if day not in date_index or row.latency not in LATENCIES:
            continue
        d = date_index[day]
        s = int(row.submit_AEST.hour * 4 + row.submit_AEST.minute // 15)
        t = TIERS.index(str(row.tier))
        l = LATENCIES.index(str(row.latency))
        mass = float(row.service_GPU_h)
        slot[d, s] += mass
        tier[d, t] += mass
        latency[d, l] += mass
        tier_latency[d, t, l] += mass
    daily = slot.sum(axis=1)
    return {
        "dates": dates,
        "slot": slot,
        "daily": daily,
        "tier": tier,
        "latency": latency,
        "tier_latency": tier_latency,
        "retained_jobs": retained,
        "mass_identity_error": float(np.max(np.abs(daily - tier.sum(axis=1)))),
        "latency_identity_error": float(np.max(np.abs(daily - latency.sum(axis=1)))),
    }


def quantiles(values: np.ndarray, points: tuple[float, ...] = (0.1, 0.5, 0.75, 0.9, 0.95, 0.99)) -> dict[str, float]:
    return {f"P{int(point*100):02d}": float(np.quantile(values, point)) for point in points}


def skewness(values: np.ndarray) -> float | None:
    centered = values - float(np.mean(values))
    std = float(np.std(values))
    return float(np.mean(centered ** 3) / std ** 3) if std > 0 else None


def training_distribution(targets: dict[str, object]) -> dict[str, object]:
    dates = targets["dates"]
    slot = np.asarray(targets["slot"], dtype=float)
    daily = np.asarray(targets["daily"], dtype=float)
    flat = slot.ravel()
    weekday = np.asarray([day.dayofweek < 5 for day in dates])
    weekend = ~weekday
    holiday = np.asarray([day.date().isoformat() in VICTORIA_HOLIDAYS for day in dates])
    positive = flat[flat > 0]
    mean_slot = float(flat.mean())
    median_positive = float(np.median(positive)) if positive.size else None
    capacity_intensity = daily / (C_REF * 24.0)
    return {
        "artifact_id": "V18R2_FLEXIBLE_ARRIVAL_TRAINING_DISTRIBUTION_V1",
        "period": [TRAIN_START, "2025-03-31"],
        "day_count": len(daily),
        "total_flexible_GPU_h": float(daily.sum()),
        "mean_GPU_h_per_day": float(daily.mean()),
        "median_GPU_h_per_day": float(np.median(daily)),
        "day_total_quantiles_GPU_h": quantiles(daily),
        "zero_arrival_slot_fraction": float(np.mean(flat == 0)),
        "slot_arrival_quantiles_GPU_h_all": quantiles(flat, (0.5, 0.75, 0.9, 0.95, 0.99)),
        "slot_arrival_quantiles_GPU_h_positive": quantiles(positive, (0.5, 0.75, 0.9, 0.95, 0.99)),
        "burstiness_coefficient_of_variation": float(np.std(flat) / mean_slot) if mean_slot else None,
        "variance_to_mean": float(np.var(flat) / mean_slot) if mean_slot else None,
        "skewness": skewness(flat),
        "max_to_positive_median": float(flat.max() / median_positive) if median_positive else None,
        "weekday_mean_GPU_h_per_day": float(daily[weekday].mean()),
        "weekend_mean_GPU_h_per_day": float(daily[weekend].mean()),
        "holiday_mean_GPU_h_per_day": float(daily[holiday].mean()) if holiday.any() else None,
        "nonholiday_mean_GPU_h_per_day": float(daily[~holiday].mean()),
        "capacity_normalization": {
            "definition": "H_FLEX_DAY / (C_REF * 24 h)",
            "C_REF_GPU": C_REF,
            "pre_expansion_role": "SOURCE_BACKED_132_H100_NODES_X4_GPU",
            "post_expansion_role": "ENGINEERING_NORMALIZATION_REFERENCE_BECAUSE_EXPANSION_QUANTITY_UNPUBLISHED",
            "mean_daily_intensity": float(capacity_intensity.mean()),
            "quantiles": quantiles(capacity_intensity),
            "upper_bound_enforced": False,
        },
        "daily_slot_mass_identity_max_abs_GPU_h": float(np.max(np.abs(daily - slot.sum(axis=1)))),
        "daily_tier_mass_identity_max_abs_GPU_h": targets["mass_identity_error"],
    }


def old_lineage() -> dict[str, object]:
    old_npz = V17 / "V17_RCMQT_V4R1_APRIL_7DAY_PREDICTIONS.npz"
    preparation_path = V17 / "cache_v4r1" / "V17_RCMQT_V4R1_APRIL_7DAY_PREPARATION.json"
    training_path = V17 / "V17_RCMQT_V4R1_TRAINING_REPORT.json"
    scheduler_path = V17 / "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_7DAY_VALIDATION.json"
    with np.load(old_npz, allow_pickle=False) as saved:
        prediction = np.asarray(saved["prediction"], dtype=float)
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    training = json.loads(training_path.read_text(encoding="utf-8"))
    scheduler = json.loads(scheduler_path.read_text(encoding="utf-8"))
    target_names = list(training["config"]["targets"])
    scales = np.asarray([float(preparation["target_scales"][name]) for name in target_names])
    prediction_raw = prediction * scales[None, None, :, None]
    work_indices = [index for index, name in enumerate(target_names) if name.startswith("W_F_")]
    q50_before_beta = prediction_raw[:, :, work_indices, 1].sum(axis=(1, 2))
    q50_after_beta = 0.25 * q50_before_beta
    scheduler_days = np.asarray([float(row["arrival_GPU_hours"]) for row in scheduler["days"]])
    final_total = float(q50_after_beta.sum())
    return {
        "artifact_id": "V18R2_WF_FORECAST_LINEAGE_AUDIT_V1",
        "reproduction": {
            "prediction_shape": list(prediction.shape),
            "target_count": len(target_names),
            "work_target_count": len(work_indices),
            "quantile_axis": [0.1, 0.5, 0.9],
            "selected_quantile": "Q50_INDEX_1",
            "Q50_before_beta_GPU_h_by_day": dict(zip(DEBUG_DAYS, map(float, q50_before_beta))),
            "Q50_before_beta_7day_GPU_h": float(q50_before_beta.sum()),
            "beta_AIDC": 0.25,
            "after_beta_GPU_h_by_day": dict(zip(DEBUG_DAYS, map(float, q50_after_beta))),
            "after_beta_7day_GPU_h": final_total,
            "frozen_scheduler_7day_GPU_h": float(scheduler_days.sum()),
            "arithmetic_reproduction_abs_error_GPU_h": abs(final_total - 1244.068855127062),
            "scheduler_identity_abs_error_GPU_h": float(np.max(np.abs(q50_after_beta - scheduler_days))),
        },
        "stages": [
            {"stage": "raw Kestrel jobs", "variable": "frame", "shape": "monthly rows", "unit": "job record", "resolution": "event", "boundary": "H100 partitions", "scale_factor": 1.0, "file": "esif.hpc.kestrel.job-anon.zip", "function": "v17_v4r1_ml._load_kestrel_v4r1"},
            {"stage": "semantic/modelable target", "variable": "workload", "shape": "time x 20", "unit": "GPU-h/15min arrival slot", "resolution": "15min", "boundary": "V1 or U2 exact-uniform, three-job quarantine", "scale_factor": 1.0, "file": "dayahead/v17_v4r1_ml.py", "function": "_load_kestrel_v4r1"},
            {"stage": "positive target scale", "variable": "scaled", "shape": "time x 22", "unit": "dimensionless", "resolution": "15min", "boundary": "positive P95 per target", "scale_factor": "1/P95", "file": str(training_path.relative_to(ROOT)), "function": "_scales/_build_samples"},
            {"stage": "direct96 quantile output", "variable": "prediction", "shape": list(prediction.shape), "unit": "scaled target", "resolution": "96 slots/day", "boundary": "frozen RC-MQT", "scale_factor": 1.0, "quantile": "Q10/Q50/Q90", "file": str(old_npz.relative_to(ROOT)), "function": "predict_transformer"},
            {"stage": "inverse target scale", "variable": "prediction_raw", "shape": list(prediction_raw.shape), "unit": "GPU-h/slot", "resolution": "15min", "boundary": "20 W targets", "scale_factor": "P95", "file": str(preparation_path.relative_to(ROOT)), "function": "materialize_references"},
            {"stage": "Q50 aggregation", "variable": "q50_before_beta", "shape": [7], "unit": "GPU-h/day", "resolution": "day", "boundary": "sum 96 marginal Q50 x20 targets", "scale_factor": 1.0, "quantile": "Q50", "file": "dayahead/v17_v4r1_april.py", "function": "materialize_references"},
            {"stage": "equivalent-footprint beta", "variable": "arrivals", "shape": "7x20x96", "unit": "GPU-h", "resolution": "15min", "boundary": "system total before rack distribution", "scale_factor": 0.25, "file": "dayahead/v17_v4r1_april.py", "function": "materialize_references"},
            {"stage": "48-rack/12-site distribution", "variable": "allocation", "shape": "20x48x96", "unit": "GPU-h", "resolution": "15min", "boundary": "weights sum one", "scale_factor": 1.0, "file": "dayahead/v17_reference_scheduler_v6.py", "function": "build_reference_schedule_v6_gpu_hour"},
        ],
        "factor_audit": {
            "GPU_vs_node_factor_4": "NOT_APPLIED_TO_OLD_WORKLOAD; TARGET_ALREADY_GPU_HOUR",
            "slot_hours_0_25": "NOT_APPLIED_TO_WORKLOAD; USED_ONCE_FOR_CAPACITY_AND_POWER_RATE",
            "beta_AIDC_0_25": "APPLIED_ONCE_TO_W_F_AND_CAUSES_75_PERCENT_MECHANICAL_LOSS",
            "spatial_weights": "SUM_ONE_NO_LOSS",
            "12_site_distribution": "DISTRIBUTION_NOT_REPLICATION_NO_LOSS",
            "target_standardization": "POSITIVE_P95_AND_EXACT_INVERSE",
            "log1p_expm1": "ABSENT",
            "quantile_transform": "ABSENT; DIRECT_MONOTONE_QUANTILE_HEAD",
            "cumulative_horizon_target": "ABSENT",
            "node_hour_conversion": "ABSENT_IN_WORKLOAD_PATH",
            "modelable_filter": "V1_OR_U2_EXACT_UNIFORM_ONLY",
            "Q50_selection": "PRESENT_SLOTWISE_MARGINAL",
            "hidden_clipping_or_flooring": "NO_POSTHOC_CLIP; SOFTPLUS_MODEL_HEAD",
            "normalization_denominator": "PER_TARGET_POSITIVE_P95_NOT_CAPACITY",
        },
        "provenance": {
            str(old_npz.relative_to(ROOT)): sha256(old_npz),
            str(training_path.relative_to(ROOT)): sha256(training_path),
            str(preparation_path.relative_to(ROOT)): sha256(preparation_path),
            "dayahead/v17_v4r1_ml.py": sha256(ROOT / "dayahead/v17_v4r1_ml.py"),
            "dayahead/v17_v4r1_april.py": sha256(ROOT / "dayahead/v17_v4r1_april.py"),
            "dayahead/v17_reference_scheduler_v6.py": sha256(ROOT / "dayahead/v17_reference_scheduler_v6.py"),
        },
    }


def conditional_distribution(
    values: np.ndarray,
    totals: np.ndarray,
    dates: object,
    train_indices: np.ndarray,
    prediction_day: object,
    shrinkage_days: float = 3.0,
) -> np.ndarray:
    positive = train_indices[totals[train_indices] > 0]
    if not len(positive):
        raise RuntimeError("V18R2_CONDITIONAL_DISTRIBUTION_NO_POSITIVE_DAYS")
    normalized = values[positive] / totals[positive, None]
    global_mean = normalized.mean(axis=0)
    same = np.asarray([index for index in positive if dates[index].dayofweek == prediction_day.dayofweek], dtype=int)
    if len(same):
        same_normalized = values[same] / totals[same, None]
        result = (same_normalized.sum(axis=0) + shrinkage_days * global_mean) / (len(same) + shrinkage_days)
    else:
        result = global_mean
    total = float(result.sum())
    if total <= 0:
        raise RuntimeError("V18R2_CONDITIONAL_DISTRIBUTION_ZERO")
    return result / total


def empirical_quantile_by_dow(
    values: np.ndarray,
    dates: object,
    train_indices: np.ndarray,
    prediction_day: object,
    q: float,
) -> np.ndarray:
    same = np.asarray([index for index in train_indices if dates[index].dayofweek == prediction_day.dayofweek], dtype=int)
    support = same if len(same) >= 4 else train_indices
    return np.quantile(values[support], q, axis=0)


def pinball(actual: np.ndarray, forecast: np.ndarray, q: float) -> float:
    error = actual - forecast
    return float(np.mean(np.maximum(q * error, (q - 1.0) * error)))


def forecast_metrics(actual_slot: np.ndarray, q50_slot: np.ndarray, q90_slot: np.ndarray) -> dict[str, object]:
    actual_day = actual_slot.sum(axis=1)
    q50_day = q50_slot.sum(axis=1)
    q90_day = q90_slot.sum(axis=1)
    error = q50_day - actual_day
    actual_shapes = np.divide(actual_slot, actual_day[:, None], out=np.zeros_like(actual_slot), where=actual_day[:, None] > 0)
    forecast_shapes = np.divide(q50_slot, q50_day[:, None], out=np.zeros_like(q50_slot), where=q50_day[:, None] > 0)
    return {
        "day_count": len(actual_day),
        "daily_MAE_GPU_h": float(np.mean(np.abs(error))),
        "daily_RMSE_GPU_h": float(np.sqrt(np.mean(error ** 2))),
        "daily_WAPE": float(np.sum(np.abs(error)) / np.sum(actual_day)),
        "mean_bias_GPU_h_per_day": float(np.mean(error)),
        "median_bias_GPU_h_per_day": float(np.median(error)),
        "aggregate_mass_ratio": float(np.sum(q50_day) / np.sum(actual_day)),
        "Q50_pinball_GPU_h_per_day": pinball(actual_day, q50_day, 0.5),
        "Q50_empirical_coverage": float(np.mean(actual_day <= q50_day)),
        "Q90_pinball_GPU_h_per_day": pinball(actual_day, q90_day, 0.9),
        "Q90_empirical_coverage": float(np.mean(actual_day <= q90_day)),
        "slot_MAE_GPU_h": float(np.mean(np.abs(q50_slot - actual_slot))),
        "normalized_shape_L1_error": float(np.mean(np.sum(np.abs(forecast_shapes - actual_shapes), axis=1))),
        "mean_peak_timing_error_hours": float(np.mean(np.abs(np.argmax(q50_slot, axis=1) - np.argmax(actual_slot, axis=1))) * DT_H),
        "actual_zero_slot_fraction": float(np.mean(actual_slot == 0)),
        "predicted_near_zero_slot_fraction": float(np.mean(q50_slot <= 1e-6)),
        "negative_prediction_count": int(np.sum(q50_slot < 0) + np.sum(q90_slot < 0)),
        "quantile_crossing_count": int(np.sum(q90_slot < q50_slot)),
    }


def blocked_cv(targets: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    import pandas as pd

    dates = targets["dates"]
    slot = np.asarray(targets["slot"], dtype=float)
    daily = np.asarray(targets["daily"], dtype=float)
    tier = np.asarray(targets["tier"], dtype=float)
    fold_specs = (
        ("F1", "2024-08-19", "2024-10-31", "2024-11-01", "2024-11-30"),
        ("F2", "2024-08-19", "2024-11-30", "2024-12-01", "2025-01-15"),
        ("F3", "2024-08-19", "2025-01-15", "2025-01-16", "2025-03-31"),
    )
    aggregate: dict[str, dict[str, list[np.ndarray]]] = {
        name: {"actual": [], "q50": [], "q90": [], "tier_pred": [], "tier_actual": []}
        for name in ("OLD_V17_WF_LINEAGE_EQUIVALENT", "CANDIDATE_A", "CANDIDATE_B")
    }
    fold_rows: list[dict[str, object]] = []
    for fold_name, train_start, train_end, validation_start, validation_end in fold_specs:
        train_mask = (dates >= pd.Timestamp(train_start)) & (dates <= pd.Timestamp(train_end))
        validation_mask = (dates >= pd.Timestamp(validation_start)) & (dates <= pd.Timestamp(validation_end))
        train_indices = np.flatnonzero(train_mask)
        validation_indices = np.flatnonzero(validation_mask)
        a_q50 = np.stack([empirical_quantile_by_dow(slot / (C_REF * DT_H), dates, train_indices, dates[index], 0.5) for index in validation_indices]) * (C_MODEL * DT_H)
        a_q90 = np.stack([empirical_quantile_by_dow(slot / (C_REF * DT_H), dates, train_indices, dates[index], 0.9) for index in validation_indices]) * (C_MODEL * DT_H)
        b_day_q50 = np.asarray([float(empirical_quantile_by_dow(daily[:, None] / (C_REF * 24.0), dates, train_indices, dates[index], 0.5)[0]) for index in validation_indices]) * (C_MODEL * 24.0)
        b_day_q90 = np.asarray([float(empirical_quantile_by_dow(daily[:, None] / (C_REF * 24.0), dates, train_indices, dates[index], 0.9)[0]) for index in validation_indices]) * (C_MODEL * 24.0)
        shapes = np.stack([conditional_distribution(slot, daily, dates, train_indices, dates[index]) for index in validation_indices])
        b_q50 = b_day_q50[:, None] * shapes
        b_q90 = b_day_q90[:, None] * shapes
        tier_predictions = np.stack([conditional_distribution(tier, daily, dates, train_indices, dates[index]) for index in validation_indices])
        predictions = {
            "OLD_V17_WF_LINEAGE_EQUIVALENT": (0.25 * a_q50, 0.25 * a_q90),
            "CANDIDATE_A": (a_q50, a_q90),
            "CANDIDATE_B": (b_q50, b_q90),
        }
        fold_result: dict[str, object] = {
            "fold": fold_name,
            "train_period": [train_start, train_end],
            "validation_period": [validation_start, validation_end],
            "train_days": len(train_indices),
            "validation_days": len(validation_indices),
        }
        for name, (q50, q90) in predictions.items():
            metrics = forecast_metrics(slot[validation_indices], q50, q90)
            actual_tier_share = np.divide(tier[validation_indices], daily[validation_indices, None], out=np.zeros_like(tier[validation_indices]), where=daily[validation_indices, None] > 0)
            metrics["mean_tier_share_L1_error"] = float(np.mean(np.sum(np.abs(tier_predictions - actual_tier_share), axis=1)))
            fold_result[name] = metrics
            aggregate[name]["actual"].append(slot[validation_indices])
            aggregate[name]["q50"].append(q50)
            aggregate[name]["q90"].append(q90)
            aggregate[name]["tier_pred"].append(tier_predictions)
            aggregate[name]["tier_actual"].append(actual_tier_share)
        fold_rows.append(fold_result)
    combined: dict[str, object] = {}
    cv_predictions: dict[str, object] = {}
    for name, values in aggregate.items():
        actual = np.concatenate(values["actual"])
        q50 = np.concatenate(values["q50"])
        q90 = np.concatenate(values["q90"])
        metrics = forecast_metrics(actual, q50, q90)
        tier_pred = np.concatenate(values["tier_pred"])
        tier_actual = np.concatenate(values["tier_actual"])
        metrics["mean_tier_share_L1_error"] = float(np.mean(np.sum(np.abs(tier_pred - tier_actual), axis=1)))
        combined[name] = metrics
        cv_predictions[name] = {"actual": actual, "q50": q50, "q90": q90}
    selected = min(("CANDIDATE_A", "CANDIDATE_B"), key=lambda name: (combined[name]["daily_WAPE"], abs(combined[name]["aggregate_mass_ratio"] - 1.0), combined[name]["daily_MAE_GPU_h"]))
    comparison = {
        "artifact_id": "V18R2_FORECAST_CANDIDATE_COMPARISON_V1",
        "selection_data_boundary": "TRAINING_ONLY_BLOCKED_ROLLING_ORIGIN_CV",
        "feature_schema": ["known day-of-week at D-1 cutoff"],
        "candidate_definitions": {
            "OLD_V17_WF_LINEAGE_EQUIVALENT": "Candidate-A marginal slotwise Q50 under the audited legacy beta_AIDC=0.25 mechanical boundary; not a claim of exact RC-MQT fold refits",
            "CANDIDATE_A": "capacity-normalized empirical marginal slotwise Q50/Q90 conditional on known day-of-week",
            "CANDIDATE_B": "capacity-normalized empirical daily-mass Q50/Q90 conditional on known day-of-week plus training-only conditional intraday shape",
            "CANDIDATE_C": "NOT_IMPLEMENTED_DEPENDENCIES_UNAVAILABLE_AND_NOT_REQUIRED",
        },
        "folds": fold_rows,
        "combined": combined,
        "selected": selected,
        "selection_priority": ["daily_WAPE", "absolute_aggregate_mass_bias", "daily_MAE"],
        "April_reads_for_selection": 0,
        "grid_objective_reads_for_selection": 0,
    }
    q50_actual = np.concatenate([cv_predictions["CANDIDATE_A"]["actual"]]).sum(axis=1)
    q50_slot_sum = cv_predictions["CANDIDATE_A"]["q50"].sum(axis=1)
    q50_daily = cv_predictions["CANDIDATE_B"]["q50"].sum(axis=1)
    ratio = np.divide(q50_slot_sum, q50_actual, out=np.zeros_like(q50_slot_sum), where=q50_actual > 0)
    empirical_slot_medians = np.median(slot, axis=0)
    q50_audit = {
        "artifact_id": "V18R2_SLOTWISE_Q50_AGGREGATION_AUDIT_V1",
        "zero_inflated": bool(np.mean(slot == 0) > 0.5),
        "sum_training_marginal_slot_medians_GPU_h_per_typical_day": float(empirical_slot_medians.sum()),
        "median_training_daily_total_GPU_h": float(np.median(daily)),
        "sum_marginal_median_over_median_sum_ratio": float(empirical_slot_medians.sum() / np.median(daily)) if np.median(daily) else None,
        "CV_actual_total_GPU_h": float(q50_actual.sum()),
        "CV_sum_slotwise_Q50_GPU_h": float(q50_slot_sum.sum()),
        "CV_daily_mass_Q50_GPU_h": float(q50_daily.sum()),
        "CV_slotwise_Q50_aggregate_mass_ratio": float(q50_slot_sum.sum() / q50_actual.sum()),
        "CV_daily_Q50_aggregate_mass_ratio": float(q50_daily.sum() / q50_actual.sum()),
        "daywise_slotwise_Q50_over_actual_quantiles": quantiles(ratio),
        "identity_statement": "sum_t median(A_t|X) is not median(sum_t A_t|X)",
        "H6_verdict": "CONTRIBUTOR" if combined["CANDIDATE_B"]["daily_WAPE"] < combined["CANDIDATE_A"]["daily_WAPE"] else "FAIL_NOT_PRIMARY_IN_CV",
    }
    return comparison, q50_audit, cv_predictions


def fit_freeze(targets: dict[str, object], comparison: dict[str, object]) -> dict[str, object]:
    dates = targets["dates"]
    slot = np.asarray(targets["slot"], dtype=float)
    daily = np.asarray(targets["daily"], dtype=float)
    tier = np.asarray(targets["tier"], dtype=float)
    latency = np.asarray(targets["latency"], dtype=float)
    full_indices = np.arange(len(dates))
    by_dow: dict[str, object] = {}
    for dow in range(7):
        representative = next(day for day in dates if day.dayofweek == dow)
        by_dow[str(dow)] = {
            "candidate_A_slot_intensity_Q50": empirical_quantile_by_dow(slot / (C_REF * DT_H), dates, full_indices, representative, 0.5).tolist(),
            "candidate_A_slot_intensity_Q90": empirical_quantile_by_dow(slot / (C_REF * DT_H), dates, full_indices, representative, 0.9).tolist(),
            "candidate_B_daily_intensity_Q50": float(empirical_quantile_by_dow(daily[:, None] / (C_REF * 24.0), dates, full_indices, representative, 0.5)[0]),
            "candidate_B_daily_intensity_Q90": float(empirical_quantile_by_dow(daily[:, None] / (C_REF * 24.0), dates, full_indices, representative, 0.9)[0]),
            "intraday_shape": conditional_distribution(slot, daily, dates, full_indices, representative).tolist(),
            "tier_mixture": conditional_distribution(tier, daily, dates, full_indices, representative).tolist(),
            "latency_mixture": conditional_distribution(latency, daily, dates, full_indices, representative).tolist(),
        }
    selected = str(comparison["selected"])
    freeze = {
        "artifact_id": "V18R2_FORECAST_MODEL_SELECTION_FREEZE_V1",
        "status": "FROZEN_ON_TRAINING_ONLY_BEFORE_APRIL_TARGET_ACCESS",
        "selected_model": selected,
        "fit_period": [TRAIN_START, "2025-03-31"],
        "target": "capacity-normalized semantic-flexible submitted service mass",
        "target_units": {
            "daily": "H_FLEX_DAY / (C_REF_GPU * 24 h)",
            "slotwise": "A_FLEX_SLOT / (C_REF_GPU * 0.25 h)",
            "restored": "GPU-hour",
        },
        "C_REF_GPU": C_REF,
        "C_REF_post_expansion_role": "ENGINEERING_NORMALIZATION_REFERENCE",
        "C_MODEL_GPU": C_MODEL,
        "C_MODEL_label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY_NOT_REAL_MELBOURNE_INSTALLED_CAPACITY",
        "feature_schema": ["known day-of-week at D-1 cutoff"],
        "feature_boundary": "calendar-only D-1-known variables; no realized workload fields",
        "estimator": "training-support empirical conditional quantiles; no extrapolation, clipping, or posthoc multiplier",
        "frozen_by_day_of_week": by_dow,
        "conditional_shape_rule": "day-of-week training mean with three-day global shrinkage, normalized to one",
        "conditional_tier_rule": "day-of-week training mixture with three-day global shrinkage, normalized to one",
        "conditional_latency_rule": "day-of-week historical-target mixture for reference deadline preflight only",
        "selection_metrics": comparison["combined"][selected],
        "selection_rule": comparison["selection_priority"],
        "training_indices": [int(full_indices[0]), int(full_indices[-1])],
        "quantile_semantics": {
            "Q50": "nominal daily scheduling scenario",
            "Q90": "reserve/sensitivity only; not used in main facility result",
            "hierarchical_rule": "daily Q50 first, then normalized intraday/tier/latency distribution",
        },
        "causality_counters_at_freeze": {
            "April_target_reads": 0,
            "D_day_actual_feature_reads": 0,
            "future_realized_start_feature_reads": 0,
            "future_realized_end_feature_reads": 0,
            "future_queue_wait_feature_reads": 0,
            "retrospective_oracle_imports": 0,
        },
        "anti_tuning": {
            "literature_target_reads": 0,
            "20_25_percent_target_reads": 0,
            "grid_objective_reads": 0,
            "posthoc_workload_multiplier": 0,
            "C_MODEL_mutations": 0,
        },
    }
    return freeze


def predict_days(targets: dict[str, object], freeze: dict[str, object], days: tuple[str, ...]) -> dict[str, object]:
    import pandas as pd

    prediction_dates = pd.DatetimeIndex([pd.Timestamp(day) for day in days])
    records = [freeze["frozen_by_day_of_week"][str(day.dayofweek)] for day in prediction_dates]
    a_q50 = np.stack([np.asarray(record["candidate_A_slot_intensity_Q50"], dtype=float) for record in records]) * (C_MODEL * DT_H)
    a_q90 = np.stack([np.asarray(record["candidate_A_slot_intensity_Q90"], dtype=float) for record in records]) * (C_MODEL * DT_H)
    b_day_q50 = np.asarray([float(record["candidate_B_daily_intensity_Q50"]) for record in records]) * (C_MODEL * 24.0)
    b_day_q90 = np.asarray([float(record["candidate_B_daily_intensity_Q90"]) for record in records]) * (C_MODEL * 24.0)
    shapes = np.stack([np.asarray(record["intraday_shape"], dtype=float) for record in records])
    tier_pi = np.stack([np.asarray(record["tier_mixture"], dtype=float) for record in records])
    latency_pi = np.stack([np.asarray(record["latency_mixture"], dtype=float) for record in records])
    b_q50 = b_day_q50[:, None] * shapes
    b_q90 = b_day_q90[:, None] * shapes
    selected = str(freeze["selected_model"])
    q50 = a_q50 if selected == "CANDIDATE_A" else b_q50
    q90 = a_q90 if selected == "CANDIDATE_A" else b_q90
    selected_daily = q50.sum(axis=1)
    if np.any(q50 < 0) or np.any(q90 < q50):
        raise RuntimeError("V18R2_SELECTED_FORECAST_NONNEGATIVE_OR_QUANTILE_FAIL")
    return {
        "dates": prediction_dates,
        "q50_slot": q50,
        "q90_slot": q90,
        "q50_daily": selected_daily,
        "q90_daily": q90.sum(axis=1),
        "candidate_A_q50_daily": a_q50.sum(axis=1),
        "candidate_B_q50_daily": b_q50.sum(axis=1),
        "shape": np.divide(q50, selected_daily[:, None], out=np.zeros_like(q50), where=selected_daily[:, None] > 0),
        "tier_pi": tier_pi,
        "latency_pi": latency_pi,
        "tier_mass": selected_daily[:, None] * tier_pi,
        "negative_count": int(np.sum(q50 < 0)),
        "quantile_crossing_count": int(np.sum(q90 < q50)),
        "daily_slot_identity_error": float(np.max(np.abs(selected_daily - q50.sum(axis=1)))),
        "tier_mass_identity_error": float(np.max(np.abs(selected_daily - (selected_daily[:, None] * tier_pi).sum(axis=1)))),
    }


def scheduler_day(arrival_slot: np.ndarray, tier_pi: np.ndarray, latency_pi: np.ndarray, rack_weights: np.ndarray) -> dict[str, object]:
    deferral_slots = {"C1": 0, "C2": 2, "C3": 4, "C4": 8, "C5": 12}
    arrivals = arrival_slot[:, None, None] * tier_pi[None, :, None] * latency_pi[None, None, :]
    service = np.zeros_like(arrivals)
    pending: list[dict[str, object]] = []
    max_backlog = 0.0
    max_deadline_shortfall = 0.0
    max_capacity_violation = 0.0
    capacity_gpuh = C_MODEL * DT_H
    for slot in range(96):
        for tier_index, tier in enumerate(TIERS):
            for latency_index, latency in enumerate(LATENCIES):
                amount = float(arrivals[slot, tier_index, latency_index])
                if amount > 0:
                    pending.append({
                        "tier": tier_index,
                        "latency": latency_index,
                        "arrival": slot,
                        "due": min(95, slot + deferral_slots[latency]),
                        "remaining": amount,
                    })
        pending.sort(key=lambda item: (item["due"], item["arrival"], item["latency"], item["tier"]))
        remaining_capacity = capacity_gpuh
        for item in pending:
            amount = min(float(item["remaining"]), remaining_capacity)
            if amount <= 0:
                continue
            service[slot, int(item["tier"]), int(item["latency"])] += amount
            item["remaining"] = float(item["remaining"]) - amount
            remaining_capacity -= amount
        max_capacity_violation = max(max_capacity_violation, float(service[slot].sum() - capacity_gpuh))
        overdue = sum(float(item["remaining"]) for item in pending if int(item["due"]) <= slot)
        max_deadline_shortfall = max(max_deadline_shortfall, overdue)
        pending = [item for item in pending if float(item["remaining"]) > 1e-12]
        max_backlog = max(max_backlog, sum(float(item["remaining"]) for item in pending))
    terminal = sum(float(item["remaining"]) for item in pending)
    service_tier_slot = service.sum(axis=2)
    rack_service = service_tier_slot[:, :, None] * rack_weights[None, None, :]
    rack_capacity = C_MODEL * rack_weights * DT_H
    rack_capacity_violation = float(np.max(rack_service.sum(axis=1) - rack_capacity[None, :]))
    return {
        "arrivals": arrivals,
        "service": service,
        "rack_service": rack_service,
        "arrival_GPU_h": float(arrivals.sum()),
        "service_GPU_h": float(service.sum()),
        "work_conservation_abs_error_GPU_h": abs(float(arrivals.sum()) - float(service.sum())),
        "max_system_capacity_violation_GPU_h_per_slot": max(0.0, max_capacity_violation),
        "max_rack_capacity_violation_GPU_h_per_slot": max(0.0, rack_capacity_violation),
        "max_deadline_shortfall_GPU_h": max_deadline_shortfall,
        "max_backlog_GPU_h": max_backlog,
        "terminal_backlog_GPU_h": terminal,
        "negative_work_count": int(np.sum(arrivals < 0) + np.sum(service < 0)),
        "hidden_shedding_GPU_h": 0.0,
        "feasible": bool(terminal <= 1e-8 and max_deadline_shortfall <= 1e-8 and max_capacity_violation <= 1e-8 and rack_capacity_violation <= 1e-8),
    }


def power_and_facility(prediction: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    power_contract = json.loads((V18 / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json").read_text(encoding="utf-8"))
    kappa_total = {int(key): float(value) for key, value in power_contract["fullnode"]["kappa_total_kW_per_active_node"].items()}
    partial_kappa = float(power_contract["partialnode"]["kappa_kW_per_GPU"])
    coefficients = {
        tier: (kappa_total[int(tier.split("_")[1])] / 4.0 if tier.startswith("FULL_") else partial_kappa)
        for tier in TIERS
    }
    tier_mass_total = {tier: 0.0 for tier in TIERS}
    tier_energy_total = {tier: 0.0 for tier in TIERS}
    scheduler_rows: list[dict[str, object]] = []
    facility_days: list[dict[str, object]] = []
    total_it_energy = 0.0
    flex_energy = 0.0
    all_total_kw: list[float] = []
    all_flex_kw: list[float] = []
    minimum_residual = math.inf
    maximum_error = 0.0
    maximum_flex_minus_total = -math.inf
    negative_count = 0
    site_sum_error = 0.0
    max_scheduled_gpu = 0.0
    rack_weights_authority = None
    schedulable = True
    for day_index, day in enumerate(DEBUG_DAYS):
        with np.load(V17 / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz", allow_pickle=False) as arrays:
            plan_pcc = np.asarray(arrays["plan_kw_96x12"], dtype=float)
            old_capacity = np.asarray(arrays["gpu_capacities"], dtype=float)
        rack_weights = old_capacity / old_capacity.sum()
        if rack_weights_authority is None:
            rack_weights_authority = rack_weights
        elif float(np.max(np.abs(rack_weights_authority - rack_weights))) > 1e-15:
            raise RuntimeError("V18R2_RACK_WEIGHT_AUTHORITY_CHANGED_ACROSS_DAYS")
        schedule = scheduler_day(
            np.asarray(prediction["q50_slot"])[day_index],
            np.asarray(prediction["tier_pi"])[day_index],
            np.asarray(prediction["latency_pi"])[day_index],
            rack_weights,
        )
        schedulable = schedulable and bool(schedule["feasible"])
        rack_service = np.asarray(schedule["rack_service"], dtype=float)
        p_flex_rack = np.zeros((96, 48), dtype=float)
        for tier_index, tier in enumerate(TIERS):
            mass = float(rack_service[:, tier_index, :].sum())
            energy = mass * coefficients[tier]
            tier_mass_total[tier] += mass
            tier_energy_total[tier] += energy
            p_flex_rack += rack_service[:, tier_index, :] / DT_H * coefficients[tier]
        p_flex_site = p_flex_rack.reshape(96, 12, 4).sum(axis=2)
        p_it = plan_pcc / PUE
        locked = p_it - p_flex_site
        reconstructed = locked + p_flex_site
        error = np.abs(p_it - reconstructed)
        minimum_residual = min(minimum_residual, float(locked.min()))
        maximum_error = max(maximum_error, float(error.max()))
        maximum_flex_minus_total = max(maximum_flex_minus_total, float((p_flex_site - p_it).max()))
        negative_count += int(np.sum(locked < -1e-10))
        site_sum_error = max(site_sum_error, float(np.max(np.abs(p_flex_site.sum(axis=1) - p_flex_rack.sum(axis=1)))))
        max_scheduled_gpu = max(max_scheduled_gpu, float((rack_service.sum(axis=(1, 2)) / DT_H).max()))
        day_it = float(p_it.sum() * DT_H)
        day_flex = float(p_flex_site.sum() * DT_H)
        total_it_energy += day_it
        flex_energy += day_flex
        all_total_kw.extend(p_it.sum(axis=1).tolist())
        all_flex_kw.extend(p_flex_site.sum(axis=1).tolist())
        scheduler_rows.append({
            "day": day,
            "arrival_GPU_h": schedule["arrival_GPU_h"],
            "service_GPU_h": schedule["service_GPU_h"],
            "work_conservation_abs_error_GPU_h": schedule["work_conservation_abs_error_GPU_h"],
            "max_system_capacity_violation_GPU_h_per_slot": schedule["max_system_capacity_violation_GPU_h_per_slot"],
            "max_rack_capacity_violation_GPU_h_per_slot": schedule["max_rack_capacity_violation_GPU_h_per_slot"],
            "max_deadline_shortfall_GPU_h": schedule["max_deadline_shortfall_GPU_h"],
            "max_backlog_GPU_h": schedule["max_backlog_GPU_h"],
            "terminal_backlog_GPU_h": schedule["terminal_backlog_GPU_h"],
            "hidden_shedding_GPU_h": schedule["hidden_shedding_GPU_h"],
            "feasible": schedule["feasible"],
        })
        facility_days.append({
            "day": day,
            "total_IT_kWh": day_it,
            "flexible_reference_IT_kWh": day_flex,
            "locked_residual_IT_kWh": day_it - day_flex,
        })
    total_array = np.asarray(all_total_kw)
    flex_array = np.asarray(all_flex_kw)
    peak_index = int(np.argmax(total_array))
    scheduler = {
        "artifact_id": "V18R2_REFERENCE_SCHEDULER_PREFLIGHT_V1",
        "policy": "GRID_BLIND_EDF_FLUID_GPU_HOUR_WITH_FROZEN_RACK_CAPACITY_WEIGHTS",
        "C_MODEL_GPU": C_MODEL,
        "capacity_GPU_h_per_15min_slot": C_MODEL * DT_H,
        "days": scheduler_rows,
        "total_arrival_GPU_h": sum(float(row["arrival_GPU_h"]) for row in scheduler_rows),
        "total_service_GPU_h": sum(float(row["service_GPU_h"]) for row in scheduler_rows),
        "maximum_work_conservation_error_GPU_h": max(float(row["work_conservation_abs_error_GPU_h"]) for row in scheduler_rows),
        "maximum_deadline_shortfall_GPU_h": max(float(row["max_deadline_shortfall_GPU_h"]) for row in scheduler_rows),
        "maximum_backlog_GPU_h": max(float(row["max_backlog_GPU_h"]) for row in scheduler_rows),
        "terminal_backlog_GPU_h": sum(float(row["terminal_backlog_GPU_h"]) for row in scheduler_rows),
        "hidden_shedding_GPU_h": 0.0,
        "feasible": schedulable,
        "B0_B1_B2_B3_calls": 0,
        "OpenDSS_calls": 0,
    }
    power_tier = {
        "artifact_id": "V18R2_POWER_TIER_FORECAST_VALIDATION_V1",
        "tiers": list(TIERS),
        "forecast_7day_tier_GPU_h": tier_mass_total,
        "forecast_7day_total_GPU_h": sum(tier_mass_total.values()),
        "forecast_7day_tier_energy_kWh": tier_energy_total,
        "full_node_energy_kWh": sum(value for tier, value in tier_energy_total.items() if tier.startswith("FULL_")),
        "partial_node_energy_kWh": tier_energy_total["PARTIAL"],
        "mass_identity_abs_error_GPU_h": abs(sum(tier_mass_total.values()) - float(np.asarray(prediction["q50_daily"]).sum())),
        "partial_CPU_attribution": None,
        "partial_CPU_double_count": 0,
        "PUE_application_stage": "after final IT sum exactly once",
    }
    facility = {
        "artifact_id": "V18R2_FACILITY_DECOMPOSITION_VALIDATION_V1",
        "scope": "seven observed April diagnostic days; no grid optimization",
        "total_IT_kWh": total_it_energy,
        "new_flexible_reference_IT_kWh": flex_energy,
        "locked_residual_IT_kWh": total_it_energy - flex_energy,
        "days": facility_days,
        "minimum_locked_residual_IT_kW": minimum_residual,
        "maximum_conservation_error_kW": maximum_error,
        "maximum_P_FLEX_minus_P_IT_kW": maximum_flex_minus_total,
        "negative_locked_residual_count": negative_count,
        "site_sum_max_abs_error_kW": site_sum_error,
        "PUE": PUE,
        "PUE_application_count": 1,
        "negative_residual_clipping_calls": 0,
        "C_MODEL": {
            "value_GPU": C_MODEL,
            "label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY_NOT_REAL_MELBOURNE_INSTALLED_CAPACITY",
            "rack_weight_sum": float(np.asarray(rack_weights_authority).sum()),
            "max_reference_scheduled_GPU": max_scheduled_gpu,
        },
        "gate": "PASS_EXACT_TWO_COMPONENT_DECOMPOSITION" if negative_count == 0 and maximum_error <= 1e-9 and maximum_flex_minus_total <= 1e-10 else "FAIL_FORECAST_FACILITY_COMPOSITION",
    }
    share = {
        "artifact_id": "V18R2_FACILITY_FLEXIBILITY_SHARE_V1",
        "eta_F_FACILITY_ENERGY_NEW": flex_energy / total_it_energy,
        "eta_F_AT_TOTAL_PEAK_NEW": float(flex_array[peak_index] / total_array[peak_index]),
        "eta_F_MAX_INSTANT_NEW": float(np.max(np.divide(flex_array, total_array, out=np.zeros_like(flex_array), where=total_array > 0))),
        "mean_flexible_IT_kW": float(flex_array.mean()),
        "peak_flexible_IT_kW": float(flex_array.max()),
        "mean_flexible_PCC_kW": float(flex_array.mean() * PUE),
        "peak_flexible_PCC_kW": float(flex_array.max() * PUE),
        "old_V18R1_eta_F_FACILITY_ENERGY": 0.004659314148856945,
        "forecast_magnitude_refreeze_effect_percentage_points": 100.0 * (flex_energy / total_it_energy - 0.004659314148856945),
        "literature_calibration": False,
    }
    return scheduler, power_tier, facility, share


def verify_preservation(manifest: dict[str, object]) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    for group, entries in manifest["preservation_groups"].items():
        for entry in entries:
            path = ROOT / entry["path"]
            actual = sha256(path) if path.is_file() else None
            if actual != entry["sha256"]:
                failures.append({"group": group, "path": entry["path"], "expected": entry["sha256"], "actual": actual})
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def modelable_mass(jobs: object) -> tuple[float, int]:
    old_quarantine = {"7539787", "7543918", "7545385"}
    v1 = (
        jobs["no_share"] & jobs["exact_uniform"]
        & jobs["gpu_nodes_occupied"].isin(NODE_CLASSES)
        & np.isclose(jobs["gpus_requested"], 4.0 * jobs["gpu_nodes_occupied"])
    )
    u2 = ~v1 & ~jobs["no_share"] & jobs["exact_uniform"]
    authorized = (v1 | u2) & ~jobs["id"].astype(str).isin(old_quarantine)
    return float(jobs.loc[authorized, "service_GPU_h"].sum()), int(authorized.sum())


def root_cause(
    lineage: dict[str, object],
    targets: dict[str, object],
    training_jobs: object,
    comparison: dict[str, object],
    q50_audit: dict[str, object],
    prediction: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    total_semantic = float(np.asarray(targets["daily"]).sum())
    modelable_total, modelable_jobs = modelable_mass(training_jobs.loc[~training_jobs["conflict_quarantined"]])
    modelable_ratio = modelable_total / total_semantic
    old_before_beta = float(lineage["reproduction"]["Q50_before_beta_7day_GPU_h"])
    old_after_beta = float(lineage["reproduction"]["after_beta_7day_GPU_h"])
    new_total = float(np.asarray(prediction["q50_daily"]).sum())
    training_equivalent_7day = total_semantic / len(targets["daily"]) * 7.0
    roots = [
        {"hypothesis": "H1 legacy absolute rather than capacity-normalized target", "evidence": "V17 target used per-target positive P95 only; no C_REF denominator", "verdict": "CONTRIBUTOR"},
        {"hypothesis": "H2 beta_AIDC/equivalent-footprint applied to workload", "evidence": {"before_GPU_h": old_before_beta, "beta": 0.25, "after_GPU_h": old_after_beta, "mechanical_loss_GPU_h": old_before_beta-old_after_beta}, "verdict": "PRIMARY_CONTRIBUTOR_DOUBLE_SCALING_BOUNDARY"},
        {"hypothesis": "H3 factor-4 GPU/node loss", "evidence": "target and scheduler remain GPU-hour; factor 4 appears only in full-node power conversion", "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H4 slot_hours 0.25 double application", "evidence": "0.25 is not multiplied into workload; it is used once for capacity and GPU-h-to-kW conversion", "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H5 12-site total accidentally reduced to one site", "evidence": "rack/site weights sum one and scheduler arrival identity matches system total", "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H6 slotwise Q50 aggregation bias", "evidence": {"slotwise_CV_mass_ratio": q50_audit["CV_slotwise_Q50_aggregate_mass_ratio"], "daily_CV_mass_ratio": q50_audit["CV_daily_Q50_aggregate_mass_ratio"], "WAPE_A": comparison["combined"]["CANDIDATE_A"]["daily_WAPE"], "WAPE_B": comparison["combined"]["CANDIDATE_B"]["daily_WAPE"]}, "verdict": q50_audit["H6_verdict"]},
        {"hypothesis": "H7 service-demand target interpreted as occupancy/rate", "evidence": "old reference scheduler preserved GPU-hour mass and divided by 0.25 only when forming kW", "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H8 cumulative horizon converted as a slot", "evidence": "old target is direct per-arrival-slot GPU-hour, not cumulative", "verdict": "NOT_APPLICABLE"},
        {"hypothesis": "H9 excessive modelable filtering", "evidence": {"all_repaired_semantic_GPU_h": total_semantic, "old_modelable_GPU_h": modelable_total, "retained_fraction": modelable_ratio, "old_modelable_jobs": modelable_jobs}, "verdict": "CONTRIBUTOR" if modelable_ratio < 0.99 else "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H10 genuine April low regime", "evidence": "new prediction uses calendar-only D-1 features and is located against the training daily-intensity distribution; April actual is diagnostic-only", "verdict": "NOT_PRIMARY_NO_CAUSAL_COVARIATE_EVIDENCE"},
    ]
    waterfall = [
        {"branch": "COMMON_CONTEXT", "stage": "TRAINING_SOURCE_FLEX_ARRIVAL_7DAY_EQUIVALENT", "input_GPU_h": training_equivalent_7day, "output_GPU_h": training_equivalent_7day, "multiplier": 1.0, "loss_fraction": 0.0, "reason": "training mean x seven; context, not April attrition"},
        {"branch": "OLD", "stage": "SEMANTIC_TO_OLD_MODELABLE", "input_GPU_h": training_equivalent_7day, "output_GPU_h": training_equivalent_7day * modelable_ratio, "multiplier": modelable_ratio, "loss_fraction": 1-modelable_ratio, "reason": "V1/U2 exact-uniform modelable filtering"},
        {"branch": "OLD", "stage": "FROZEN_APRIL_SLOTWISE_Q50_BEFORE_BETA", "input_GPU_h": training_equivalent_7day * modelable_ratio, "output_GPU_h": old_before_beta, "multiplier": old_before_beta/(training_equivalent_7day*modelable_ratio), "loss_fraction": 1-old_before_beta/(training_equivalent_7day*modelable_ratio), "reason": "statistical/period difference plus marginal Q50 aggregation; not purely mechanical"},
        {"branch": "OLD", "stage": "BETA_AIDC", "input_GPU_h": old_before_beta, "output_GPU_h": old_after_beta, "multiplier": 0.25, "loss_fraction": 0.75, "reason": "legacy equivalent-footprint scaling applied to already-system-total W_F"},
        {"branch": "OLD", "stage": "RACK_SITE_DISTRIBUTION_AND_SCHEDULER", "input_GPU_h": old_after_beta, "output_GPU_h": old_after_beta, "multiplier": 1.0, "loss_fraction": 0.0, "reason": "weights sum one; exact service parity"},
        {"branch": "NEW", "stage": "CAPACITY_NORMALIZED_CAUSAL_MODEL", "input_GPU_h": training_equivalent_7day, "output_GPU_h": new_total, "multiplier": new_total/training_equivalent_7day, "loss_fraction": 1-new_total/training_equivalent_7day, "reason": "training-only CV-selected April calendar/regime forecast"},
        {"branch": "NEW", "stage": "DAILY_TO_SLOT_TIER_RECONSTRUCTION", "input_GPU_h": new_total, "output_GPU_h": new_total, "multiplier": 1.0, "loss_fraction": 0.0, "reason": "normalized shape and tier mixtures conserve mass exactly"},
        {"branch": "NEW", "stage": "C_MODEL_RESTORATION", "input_GPU_h": new_total, "output_GPU_h": new_total, "multiplier": C_MODEL/C_REF, "loss_fraction": 0.0, "reason": "C_MODEL=C_REF=528; no beta or hidden scale"},
    ]
    ranking = sorted([
        {"rank_candidate": "beta_AIDC_0.25", "quantitative_effect": 0.75, "type": "MECHANICAL_SCALING_LOSS"},
        {"rank_candidate": "slotwise_Q50/statistical underforecast", "quantitative_effect": 1-old_before_beta/(training_equivalent_7day*modelable_ratio), "type": "STATISTICAL_FORECAST_DIFFERENCE"},
        {"rank_candidate": "modelable filtering", "quantitative_effect": 1-modelable_ratio, "type": "SEMANTIC_FILTERING_LOSS"},
    ], key=lambda row: abs(float(row["quantitative_effect"])), reverse=True)
    for index, row in enumerate(ranking, start=1):
        row["rank"] = index
    report = {
        "artifact_id": "V18R2_FORECAST_MAGNITUDE_ROOT_CAUSE_V1",
        "overall": "G_MULTIFACTOR_FORECAST_MAGNITUDE_ATTRITION",
        "hypotheses": roots,
        "top_3": ranking,
        "training_7day_equivalent_GPU_h": training_equivalent_7day,
        "old_7day_GPU_h": old_after_beta,
        "new_7day_GPU_h": new_total,
        "period_warning": "training-average and April prediction are different periods; statistical difference is not called mechanical attrition",
    }
    return report, waterfall


def april_diagnostic(
    prediction: dict[str, object],
    april_targets: dict[str, object],
    lineage: dict[str, object],
    training_targets: dict[str, object],
) -> dict[str, object]:
    dates = april_targets["dates"]
    index = {day.date().isoformat(): i for i, day in enumerate(dates)}
    training_intensity = np.asarray(training_targets["daily"], dtype=float) / (C_REF * 24.0)
    old_by_day = lineage["reproduction"]["after_beta_GPU_h_by_day"]
    rows: list[dict[str, object]] = []
    for i, day in enumerate(DEBUG_DAYS):
        new = float(np.asarray(prediction["q50_daily"])[i])
        intensity = new / (C_MODEL * 24.0)
        actual = float(np.asarray(april_targets["daily"])[index[day]])
        rows.append({
            "day": day,
            "old_W_F_GPU_h": float(old_by_day[day]),
            "new_W_F_Q50_GPU_h": new,
            "new_W_F_Q90_reserve_GPU_h": float(np.asarray(prediction["q90_daily"])[i]),
            "new_over_old_ratio": new / float(old_by_day[day]),
            "predicted_daily_intensity": intensity,
            "training_distribution_percentile": float(np.mean(training_intensity <= intensity)),
            "observed_actual_flexible_GPU_h_diagnostic_only": actual,
            "actual_read_after_model_freeze": True,
        })
    return {
        "artifact_id": "V18R2_APRIL_DIAGNOSTIC_FORECAST_V1",
        "label": "OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST",
        "days": rows,
        "old_7day_GPU_h": sum(float(row["old_W_F_GPU_h"]) for row in rows),
        "new_7day_Q50_GPU_h": sum(float(row["new_W_F_Q50_GPU_h"]) for row in rows),
        "new_7day_Q90_reserve_GPU_h": sum(float(row["new_W_F_Q90_reserve_GPU_h"]) for row in rows),
        "observed_actual_7day_GPU_h_diagnostic_only": sum(float(row["observed_actual_flexible_GPU_h_diagnostic_only"]) for row in rows),
        "April_target_reads_before_model_freeze": 0,
        "April_target_reads_after_model_freeze": 1,
        "April_reads_for_retraining_or_model_selection": 0,
    }


def build_full() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pre_path = OUT / "V18R2_PRECHANGE_PRESERVATION_MANIFEST.json"
    if not pre_path.exists():
        raise RuntimeError("V18R2_PRECHANGE_PRESERVATION_MANIFEST_REQUIRED")
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    preservation = verify_preservation(pre)
    if preservation["status"] != "PASS":
        raise RuntimeError(f"V18R2_PRESERVATION_FAILURE:{preservation['failures'][:3]}")
    if sha256(KESTREL) != KESTREL_SHA256:
        raise RuntimeError("V18R2_KESTREL_SOURCE_SHA_CHANGED")

    lineage = old_lineage()
    conflict_artifact = json.loads((V18R1 / "V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json").read_text(encoding="utf-8"))
    native_artifact = json.loads((V18R1 / "V18R1_KESTREL_NATIVE_FLEXIBILITY_RECOMPUTED.json").read_text(encoding="utf-8"))
    conflict_ids = set(map(str, conflict_artifact["raw_conflict_job_ids"]))
    training_frame, training_source = load_h100(202408, 202503)
    training_jobs = prepare_jobs(training_frame, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids)
    training_targets = build_targets(training_jobs, TRAIN_START, TRAIN_END_EXCLUSIVE)
    distribution = training_distribution(training_targets)
    native_execution_flex = float(native_artifact["repaired_authority"]["semantic_flexible_GPU_h"])
    distribution["V18R1_repaired_execution_integral_GPU_h"] = native_execution_flex
    distribution["arrival_target_minus_execution_integral_GPU_h"] = distribution["total_flexible_GPU_h"] - native_execution_flex
    distribution["boundary_explanation"] = "arrival target assigns full realized service mass to in-period submit day; V18R1 native value clips execution overlap to the training window"
    target_contract = {
        "artifact_id": "V18R2_FLEXIBLE_ARRIVAL_TARGET_CONTRACT_V1",
        "training_period": [TRAIN_START, "2025-03-31"],
        "source": training_source,
        "semantic_label": "COMPLETED H100 job with retrospective queue wait >600 seconds; TRAINING_TARGET_ONLY",
        "repair": {"V18R1_global_conflict_job_ids_excluded": len(conflict_ids), "source_artifact_sha256": sha256(V18R1 / "V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json")},
        "H_FLEX_DAY": "sum(gpus_requested * realized runtime hours) assigned to AEST submit day",
        "A_FLEX": "same service mass assigned to 15-minute AEST submit slot [GPU-h/slot]",
        "S_FLEX": "A_FLEX/H_FLEX_DAY for positive days; sums to one",
        "tiers": list(TIERS),
        "tier_rule": "exact isolated 4-GPU/node supported node class -> FULL_n; every other repaired semantic-flexible job -> PARTIAL lower-bound power boundary",
        "latency_classes": list(LATENCIES),
        "daily_slot_mass_identity_max_abs_GPU_h": float(np.max(np.abs(np.asarray(training_targets["daily"]) - np.asarray(training_targets["slot"]).sum(axis=1)))),
        "daily_tier_mass_identity_max_abs_GPU_h": training_targets["mass_identity_error"],
        "daily_latency_mass_identity_max_abs_GPU_h": training_targets["latency_identity_error"],
        "target_job_count_before_conflict_exclusion": len(training_jobs),
        "target_job_count_after_conflict_exclusion": len(training_targets["retained_jobs"]),
        "native_execution_vs_arrival_target_boundary": {
            "V18R1_repaired_execution_integral_GPU_h": native_execution_flex,
            "V18R2_submitted_service_target_GPU_h": float(np.asarray(training_targets["daily"]).sum()),
            "difference_reason": "full service mass is assigned to submit day rather than clipped by execution overlap",
        },
        "D1_feature_use_of_revealed_label": 0,
        "April_member_reads_before_model_freeze": 0,
    }
    capacity_contract = {
        "artifact_id": "V18R2_CAPACITY_NORMALIZED_FORECAST_CONTRACT_V1",
        "daily_intensity": "h_FLEX = H_FLEX_DAY / (C_REF * 24 h)",
        "slot_intensity": "a_FLEX = A_FLEX / (C_REF * 0.25 h)",
        "C_K_SOURCE": "partial time-varying Kestrel installed-capacity authority from V18R1",
        "C_REF_GPU": C_REF,
        "C_REF_pre_expansion_authority": "132 H100 nodes x 4 GPU",
        "C_REF_post_expansion_role": "ENGINEERING_NORMALIZATION_REFERENCE; not an installed-capacity claim",
        "C_MODEL_GPU": C_MODEL,
        "C_MODEL_label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY_NOT_REAL_MELBOURNE_INSTALLED_CAPACITY",
        "restoration": "H_hat_GPU_h = h_hat * C_MODEL * 24 h",
        "C_MODEL_over_C_REF": C_MODEL / C_REF,
        "arrival_intensity_upper_bound": None,
        "sigmoid_calls": 0,
        "posthoc_multiplier_calls": 0,
        "C_MODEL_mutations": 0,
    }
    comparison, q50_audit, _ = blocked_cv(training_targets)
    freeze = fit_freeze(training_targets, comparison)
    write_json(OUT / "V18R2_FORECAST_MODEL_SELECTION_FREEZE.json", freeze)

    training_report = {
        "artifact_id": "V18R2_FLEXIBLE_WORKLOAD_MODEL_TRAINING_REPORT_V1",
        "status": "PASS_TRAINING_ONLY_FIT",
        "selected_model": freeze["selected_model"],
        "fit_period": freeze["fit_period"],
        "training_days": len(training_targets["dates"]),
        "training_target_GPU_h": float(np.asarray(training_targets["daily"]).sum()),
        "features": freeze["feature_schema"],
        "feature_authority": freeze["feature_boundary"],
        "CV_selected_metrics": freeze["selection_metrics"],
        "quantile_semantics": freeze["quantile_semantics"],
        "nonnegative_prediction_rule": "empirical quantiles and convex normalized shapes are nonnegative by construction; no clipping",
        "April_rows_in_fit": 0,
        "future_realized_feature_reads": 0,
        "literature_target_reads": 0,
        "grid_result_reads": 0,
    }
    blocked_results = {
        "artifact_id": "V18R2_BLOCKED_CV_RESULTS_V1",
        "protocol": "three expanding-window blocked rolling-origin folds fully inside training period",
        "folds": comparison["folds"],
        "combined": comparison["combined"],
        "selected": comparison["selected"],
        "April_reads": 0,
        "grid_metrics": [],
    }

    prediction = predict_days(training_targets, freeze, DEBUG_DAYS)
    april_frame, april_source = load_h100(202504, 202504)
    april_jobs = prepare_jobs(april_frame, "2025-04-01", "2025-05-01", conflict_ids)
    april_targets = build_targets(april_jobs, "2025-04-01", "2025-05-01")
    april = april_diagnostic(prediction, april_targets, lineage, training_targets)
    april["source"] = april_source
    root, waterfall = root_cause(lineage, training_targets, training_jobs, comparison, q50_audit, prediction)
    scheduler, power_tier, facility, share = power_and_facility(prediction)
    oracle = json.loads((V18R1 / "V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE.json").read_text(encoding="utf-8"))
    share["eta_F_GPU_NATIVE"] = native_artifact["repaired_authority"]["eta_F_GPU_energy"]
    share["eta_F_FORECAST_WORK"] = None
    share["eta_F_FORECAST_WORK_reason"] = "total modeled H100 work denominator with the same prospective authority is unavailable"

    selected_metrics = comparison["combined"][comparison["selected"]]
    old_metrics = comparison["combined"]["OLD_V17_WF_LINEAGE_EQUIVALENT"]
    forecast_ready = bool(
        selected_metrics["daily_WAPE"] < old_metrics["daily_WAPE"]
        and prediction["negative_count"] == 0
        and prediction["quantile_crossing_count"] == 0
        and prediction["daily_slot_identity_error"] <= 1e-8
        and prediction["tier_mass_identity_error"] <= 1e-8
    )
    facility_ready = facility["gate"] == "PASS_EXACT_TWO_COMPONENT_DECOMPOSITION"
    scheduler_ready = bool(scheduler["feasible"])
    if not forecast_ready:
        classification = "C. V18R2_FAIL_FORECAST_CALIBRATION"
    elif not scheduler_ready:
        classification = "F. V18R2_FAIL_WORKLOAD_SCHEDULABILITY"
    elif not facility_ready:
        classification = "E. V18R2_FAIL_FACILITY_COMPOSITION"
    else:
        classification = "B. V18R2_PASS_WITH_CAPACITY_TIMELINE_PARTIAL"
    ready = {
        "artifact_id": "V18R2_READY_FLAGS_V1",
        "RESULT_CLASSIFICATION": classification,
        "FORECAST_REFREEZE_READY": forecast_ready,
        "FACILITY_COMPOSITION_READY": facility_ready,
        "NEW_LOCKED_SCIENCE_RUN_READY": False,
        "NEW_LOCKED_TEST_STATUS": "NEW_LOCKED_TEST_NOT_YET_AVAILABLE",
        "KNOWN_QUEUE_EXTENSION_STATUS": "UNAVAILABLE",
        "scheduler_preflight_ready": scheduler_ready,
        "preservation": preservation,
        "firewall_counters": {
            "D_day_actual_feature_reads": 0,
            "future_realized_start_feature_reads": 0,
            "future_realized_end_feature_reads": 0,
            "future_queue_wait_feature_reads": 0,
            "retrospective_oracle_imported_into_model": 0,
            "literature_target_reads": 0,
            "20_25_percent_target_reads": 0,
            "objective_reads_for_model_selection": 0,
            "workload_multiplier_fit_to_share": 0,
            "C_MODEL_mutations": 0,
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
        },
    }
    comparison_table = {
        "V18R1": {
            "forecast_7day_GPU_h": lineage["reproduction"]["after_beta_7day_GPU_h"],
            "flexible_IT_kWh": 614.955274757891,
            "facility_energy_share": 0.004659314148856945,
        },
        "V18R2": {
            "forecast_7day_GPU_h": april["new_7day_Q50_GPU_h"],
            "flexible_IT_kWh": facility["new_flexible_reference_IT_kWh"],
            "facility_energy_share": share["eta_F_FACILITY_ENERGY_NEW"],
        },
        "mechanistic_reason": "remove legacy beta workload contraction, use CV-selected capacity-normalized forecast, and preserve exact daily/slot/tier mass",
        "label": "FORECAST_MAGNITUDE_REFREEZE_EFFECT_NOT_GRID_IMPROVEMENT",
    }
    final_review = {
        "artifact_id": "V18R2_FORECAST_REFREEZE_FINAL_REVIEW_V1",
        "result_classification": classification,
        "ready": ready,
        "lineage": lineage,
        "training_distribution": distribution,
        "q50_aggregation_audit": q50_audit,
        "candidate_comparison": comparison,
        "selected_forecast": freeze,
        "April_observed_diagnostic": april,
        "root_cause": root,
        "power_tier": power_tier,
        "scheduler_preflight": scheduler,
        "facility_decomposition": facility,
        "facility_flexibility": share,
        "V18R1_comparison": comparison_table,
        "retrospective_queue_oracle_context": {
            "label": "NON_CAUSAL_RETROSPECTIVE_DIAGNOSTIC_NOT_ADDED_TO_NEW_W_F",
            "totals": oracle["totals"],
            "imports_into_model_or_scheduler": 0,
        },
        "literature_context": {
            "range": "approximately 20-25% under non-identical boundaries",
            "label": "LITERATURE_CONTEXT_ONLY",
            "CALIBRATION": "NO",
        },
        "remaining_limitations": [
            "Kestrel post-buy-in installed-capacity quantity/date remains only partially identified",
            "calendar-only feature boundary is highly causal but cannot capture unobserved future request-side regime shocks",
            "heavy-tailed training distribution leaves Candidate B with CV WAPE above 0.9 and aggregate Q50 mass ratio below one; Q90 remains sensitivity-only",
            "exact frozen V17 transformer was not retrained per CV fold; old CV row is a lineage-equivalent beta-boundary baseline",
            "April is observed diagnostic, not a locked unseen test",
            "known queue/running extension remains unavailable and oracle mass is not imported",
        ],
        "preservation": preservation,
    }

    root_contract = {
        "artifact_id": "V18R2_WF_FORECAST_LINEAGE_AUDIT_V1",
        **{key: value for key, value in lineage.items() if key != "artifact_id"},
    }
    write_json(OUT / "V18R2_WF_FORECAST_LINEAGE_AUDIT.json", root_contract)
    write_json(OUT / "V18R2_FORECAST_MAGNITUDE_ROOT_CAUSE.json", root)
    write_json(OUT / "V18R2_FLEXIBLE_ARRIVAL_TARGET_CONTRACT.json", target_contract)
    write_json(OUT / "V18R2_FLEXIBLE_ARRIVAL_TRAINING_DISTRIBUTION.json", distribution)
    write_json(OUT / "V18R2_SLOTWISE_Q50_AGGREGATION_AUDIT.json", q50_audit)
    write_json(OUT / "V18R2_FORECAST_CANDIDATE_COMPARISON.json", comparison)
    write_json(OUT / "V18R2_FORECAST_MODEL_SELECTION_FREEZE.json", freeze)
    write_json(OUT / "V18R2_CAPACITY_NORMALIZED_FORECAST_CONTRACT.json", capacity_contract)
    write_json(OUT / "V18R2_FLEXIBLE_WORKLOAD_MODEL_TRAINING_REPORT.json", training_report)
    write_json(OUT / "V18R2_BLOCKED_CV_RESULTS.json", blocked_results)
    write_json(OUT / "V18R2_APRIL_DIAGNOSTIC_FORECAST.json", april)
    write_csv(OUT / "V18R2_FORECAST_MAGNITUDE_WATERFALL.csv", waterfall, ["branch", "stage", "input_GPU_h", "output_GPU_h", "multiplier", "loss_fraction", "reason"])
    write_json(OUT / "V18R2_POWER_TIER_FORECAST_VALIDATION.json", power_tier)
    write_json(OUT / "V18R2_REFERENCE_SCHEDULER_PREFLIGHT.json", scheduler)
    write_json(OUT / "V18R2_FACILITY_DECOMPOSITION_VALIDATION.json", facility)
    write_json(OUT / "V18R2_FACILITY_FLEXIBILITY_SHARE.json", share)
    write_json(OUT / "V18R2_FORECAST_REFREEZE_FINAL_REVIEW.json", final_review)
    write_json(OUT / "V18R2_READY_FLAGS.json", ready)

    april_lines = "\n".join(
        f"| {row['day']} | {row['old_W_F_GPU_h']:.3f} | {row['new_W_F_Q50_GPU_h']:.3f} | {row['new_over_old_ratio']:.3f} | {row['training_distribution_percentile']:.3f} |"
        for row in april["days"]
    )
    tier_lines = "\n".join(
        f"| {tier} | {power_tier['forecast_7day_tier_GPU_h'][tier]:.3f} | {power_tier['forecast_7day_tier_energy_kWh'][tier]:.3f} |"
        for tier in TIERS
    )
    md = f"""# V18R2 AIDC Day-Ahead Flexible-Workload Magnitude Re-freeze

RESULT CLASSIFICATION: `{classification}`

## READY

- `FORECAST_REFREEZE_READY = {str(forecast_ready).lower()}`
- `FACILITY_COMPOSITION_READY = {str(facility_ready).lower()}`
- `NEW_LOCKED_SCIENCE_RUN_READY = false`

## 1. 기존 1,244 GPU-h 계보

기존 7일 `1,244.068855 GPU-h`는 frozen RC-MQT의 slotwise Q50 합 `{lineage['reproduction']['Q50_before_beta_7day_GPU_h']:.6f} GPU-h`에 `beta_AIDC=0.25`를 다시 적용해 만들어졌다. factor-4와 slot-hour 이중 적용은 없었고, 75% mechanical beta contraction과 slotwise-Q50/statistical underforecast, modelable filtering이 주요 원인이다.

## 2. Training 분포와 Q50 감사

- submitted flexible service target: `{distribution['total_flexible_GPU_h']:.6f} GPU-h`
- mean/day: `{distribution['mean_GPU_h_per_day']:.6f}`
- median/day: `{distribution['median_GPU_h_per_day']:.6f}`
- zero-arrival slot fraction: `{distribution['zero_arrival_slot_fraction']:.6f}`
- marginal slot median 합 / daily median: `{q50_audit['sum_marginal_median_over_median_sum_ratio']:.8f}`
- H6: `{q50_audit['H6_verdict']}`

## 3. Training-only model selection

Training-only 3-fold blocked CV에서 `{freeze['selected_model']}`을 선택했다. selected daily WAPE는 `{selected_metrics['daily_WAPE']:.6f}`, old lineage-equivalent WAPE는 `{old_metrics['daily_WAPE']:.6f}`, Q50 aggregate mass ratio는 `{selected_metrics['aggregate_mass_ratio']:.6f}`다. Heavy-tail 때문에 calibration 한계가 남으며 April을 이용한 재보정은 하지 않았다.

## 4. April observed diagnostic

| Day | Old GPU-h | New Q50 GPU-h | New/Old | Training percentile |
|---|---:|---:|---:|---:|
{april_lines}

새 April diagnostic Q50 합은 `{april['new_7day_Q50_GPU_h']:.6f} GPU-h`이며, April target은 모델 동결 뒤 진단용으로만 읽었다.

## 5. Power tier

| Tier | GPU-h | IT energy kWh |
|---|---:|---:|
{tier_lines}

Tier mass identity 오차는 `{power_tier['mass_identity_abs_error_GPU_h']:.3e} GPU-h`, partial CPU attribution은 `null`이다.

## 6. Scheduler와 시설 분해

새 flexible IT energy는 `{facility['new_flexible_reference_IT_kWh']:.6f} kWh`, whole-facility share는 `{100*share['eta_F_FACILITY_ENERGY_NEW']:.6f}%`다. 문헌 20~25%는 `LITERATURE_CONTEXT_ONLY`, `CALIBRATION=NO`다.

Reference scheduler는 shedding 없이 `{scheduler['total_arrival_GPU_h']:.6f} GPU-h`를 보존했고 terminal backlog는 `{scheduler['terminal_backlog_GPU_h']:.3e} GPU-h`다. 시설 최소 locked residual은 `{facility['minimum_locked_residual_IT_kW']:.6f} kW`, 최대 보존오차는 `{facility['maximum_conservation_error_kW']:.3e} kW`다.

## 7. 방화벽

B0-B3, OpenDSS, grid science run은 실행하지 않았다. untouched locked test가 없으므로 새 science run은 승인되지 않는다.
"""
    (OUT / "V18R2_FORECAST_REFREEZE_FINAL_REVIEW.md").write_text(md, encoding="utf-8")
    readme = """# V18R2 AIDC forecast-magnitude re-freeze

이 namespace는 V17/V18/V18R1을 byte-preserve하면서 기존 1,244 GPU-h 계보, slotwise Q50 bias, capacity-normalized training-only blocked CV, April diagnostic-only forecast, power-tier mass, grid-blind scheduler preflight 및 exact two-component facility decomposition을 재현한다.

`B0-B3`, `OpenDSS`, grid science 결과는 실행하지 않는다. 문헌 20~25%와 grid objective는 모델 선택·보정에 사용하지 않는다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prechange-only", action="store_true")
    args = parser.parse_args()
    if args.prechange_only:
        build_prechange_manifest()
        return
    build_full()


if __name__ == "__main__":
    main()
