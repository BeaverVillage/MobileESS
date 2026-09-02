"""Rolling-origin reconstruction of the frozen V28R2 P/G/W methodology.

Only the expanding-window cutoff and its data-derived statistics vary by
target day.  Model family, features, quantiles, hyperparameters, cohort
semantics, and empirical-adapter formula remain fixed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from lightgbm import LGBMRegressor

from dayahead.authority import sha256_file
from dayahead.reproduce_nlr_authority import object_empty
from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.lightgbm_channels import (
    COMMON,
    DAILY_FEATURES,
    QUANTILES,
    SLOT_FEATURES,
    daily_features,
    enforce_quantile_integrity,
    slot_features,
)
from dayahead.v28r2.source_labels import AEST, OptimizerLabels, load_optimizer_labels
from tools.v29.run_stage3_carryin_authority import cohort, cohort_bins, source_zip

from .contracts import COHORTS, TRAINING_START


@dataclass(frozen=True)
class RollingSources:
    labels: OptimizerLabels
    w_daily: pd.Series
    w_label_available: pd.Series
    w_jobs: pd.DataFrame
    source_sha256: dict[str, str]


@dataclass(frozen=True)
class ForecastResult:
    day: str
    issue_time: str
    training_end: str
    p_quantiles: np.ndarray
    g_quantiles: np.ndarray
    w_daily_quantiles: np.ndarray
    w_quantiles: np.ndarray
    fitted_model_sha256: dict[str, dict[str, str]]
    model_training_rows: dict[str, int]
    model_spec_sha256: dict[str, str]
    feature_schema_sha256: str
    cohort_sha256: str
    source_sha256: dict[str, str]
    latest_training_feature_time: str
    latest_training_label_available_time: str
    w_mass_error_nodeh: float
    forecast_sha256: str
    diagnostics: dict[str, float]


def issue_time(day: str) -> pd.Timestamp:
    return pd.Timestamp(day, tz=AEST) - pd.Timedelta(hours=6)


def _model_spec(channel: str, repo: Path) -> dict[str, object]:
    common = {key: value for key, value in COMMON.items()}
    base = {
        "methodology": "V28R2_FROZEN_LIGHTGBM_QUANTILE",
        "estimator_class": "lightgbm.LGBMRegressor",
        "objective": "quantile",
        "quantiles": list(QUANTILES),
        "target_transform": "log1p_nonnegative_target",
        "public_integrity": "per-cell ascending rearrangement then expm1 and zero roundoff floor",
        "fixed_hyperparameters": common,
        "categorical_handling": "none",
        "normalizer_scaler": "none",
        "missing_value_behavior": "training rows require finite target and all finite features",
        "training_start": TRAINING_START,
        "only_varying_fit_input": "causal expanding-window training cutoff and causally available empirical values",
        "source_method_sha256": sha256_file(repo / "dayahead/v28r2/lightgbm_channels.py"),
    }
    if channel in {"P", "G"}:
        base.update({
            "features_in_order": list(SLOT_FEATURES),
            "adapter": "direct 96-slot prediction",
            "target": "P^IT,REF total IT active power" if channel == "P" else "G^REF H100 occupancy",
            "optimizer_statistic": "Q90",
            "optimizer_shape": [96],
        })
    else:
        base.update({
            "features_in_order": list(DAILY_FEATURES),
            "target": "W^F strict FULL-node eligible daily H100-node-hour arrivals",
            "optimizer_statistic": "Q50",
            "optimizer_shape": [96, COHORTS],
            "adapter": "causal day-of-week x slot x cohort empirical node-hour mass normalized within day-of-week; no smoothing",
            "eligibility": "H100, completed label, nodes in frozen classes, gpus=4*nodes, positive runtime, no PARTIAL/shared",
        })
    return base


def frozen_specs(repo: Path) -> dict[str, dict[str, object]]:
    result = {}
    for channel in ("P", "G", "W"):
        spec = _model_spec(channel, repo)
        spec["spec_sha256"] = canonical_sha256(spec)
        result[channel] = spec
    return result


def _load_w_jobs(repo: Path) -> tuple[pd.DataFrame, str]:
    path = source_zip()
    columns = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            normalized = name.replace("\\", "/")
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", normalized)
            if not normalized.endswith(".parquet") or not match:
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if not 202408 <= month <= 202504:
                continue
            with archive.open(name) as raw:
                table = pq.read_table(io.BytesIO(raw.read()), columns=sorted(columns))
            frame = table.to_pandas()
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            if submit.notna().any() and submit.min() < pd.Timestamp("2025-04-01", tz=AEST).tz_convert("UTC"):
                frames.append(frame.loc[submit < pd.Timestamp("2025-04-01", tz=AEST).tz_convert("UTC")].copy())
    frame = pd.concat(frames, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    request_full = frame["partition"].astype(str).str.casefold().str.contains("gpu-h100", regex=False) & nodes.isin(CONTROLLABLE_NODE_CLASSES) & np.isclose(gpus, 4.0 * nodes, equal_nan=False)
    candidates = frame.loc[request_full & submit.notna()].copy()
    candidates["submit_utc"] = submit[request_full & submit.notna()]
    candidates["start_utc"] = start[request_full & submit.notna()]
    candidates["end_utc"] = end[request_full & submit.notna()]
    candidates["nodes"] = nodes[request_full & submit.notna()]
    candidates["gpus"] = gpus[request_full & submit.notna()]
    candidates["submit_aest"] = candidates["submit_utc"].dt.tz_convert(AEST)
    candidates["submit_day"] = candidates["submit_aest"].dt.normalize()
    candidates["slot"] = candidates["submit_aest"].dt.hour * 4 + candidates["submit_aest"].dt.minute // 15
    candidates["runtime_hours"] = (candidates["end_utc"] - candidates["start_utc"]).dt.total_seconds() / 3600.0
    no_share = (
        (pd.to_numeric(candidates["shared_job_count"], errors="coerce").isna() | pd.to_numeric(candidates["shared_job_count"], errors="coerce").eq(0))
        & candidates["nodes_shared"].apply(object_empty)
        & candidates["jobs_shared"].apply(object_empty)
    )
    eligible = (
        candidates["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & candidates["start_utc"].notna() & candidates["end_utc"].notna()
        & candidates["end_utc"].gt(candidates["start_utc"])
        & candidates["runtime_hours"].gt(0) & no_share
    )
    bins = cohort_bins(repo)
    candidates["eligible"] = eligible
    candidates["nodeh"] = np.where(eligible, candidates["nodes"] * candidates["runtime_hours"], 0.0)
    candidates["cohort_id"] = ""
    selected = candidates.loc[eligible]
    candidates.loc[eligible, "cohort_id"] = [
        cohort(int(n), float(h), bins)
        for n, h in zip(selected["nodes"], selected["runtime_hours"], strict=True)
    ]
    return candidates.reset_index(drop=True), sha256_file(path)


def load_sources(repo: Path) -> RollingSources:
    labels = load_optimizer_labels(repo)
    jobs, kestrel_sha = _load_w_jobs(repo)
    daily_index = pd.date_range(labels.timestamps[0].normalize(), labels.timestamps[-1].normalize(), freq="D")
    eligible = jobs.loc[jobs["eligible"]]
    daily = eligible.groupby("submit_day")["nodeh"].sum().reindex(daily_index, fill_value=0.0).astype(float)
    # A daily W label becomes complete only after every potentially eligible
    # full-node request submitted that day has a final end record.
    grouped = jobs.groupby("submit_day")["end_utc"]
    availability = grouped.agg(lambda values: values.max() if values.notna().all() else pd.NaT).reindex(daily_index)
    candidate_days = set(jobs["submit_day"])
    day_end_utc = (daily_index + pd.Timedelta(days=1)).tz_convert("UTC")
    availability = pd.Series(
        [
            value if pd.notna(value) else (pd.Timestamp("2100-01-01", tz="UTC") if day in candidate_days else end)
            for day, value, end in zip(daily_index, availability, day_end_utc, strict=True)
        ],
        index=daily_index,
        dtype="datetime64[ns, UTC]",
    )
    return RollingSources(labels, daily, availability, jobs, {**labels.source_sha256, "kestrel_verified": kestrel_sha})


def w_target_availability_audit(sources: RollingSources, day: str) -> dict[str, object]:
    target = pd.Timestamp(day, tz=AEST)
    issue = issue_time(day)
    available = sources.w_label_available.le(issue.tz_convert("UTC"))
    features = daily_features(sources.w_daily.where(available)).loc[target]
    lag2 = target - pd.Timedelta(days=2)
    eligible = sources.w_jobs.loc[sources.w_jobs["eligible"] & sources.w_jobs["submit_day"].eq(lag2)]
    missing = [str(name) for name, value in features.items() if not np.isfinite(value)]
    return {
        "day": day,
        "issue_time": issue.isoformat(),
        "required_target_features": list(DAILY_FEATURES),
        "missing_target_features": missing,
        "lag_2d_source_day": lag2.date().isoformat(),
        "lag_2d_label_available_time": sources.w_label_available.loc[lag2].isoformat(),
        "lag_2d_eligible_job_count": int(len(eligible)),
        "lag_2d_latest_eligible_job_end": None if eligible.empty else eligible["end_utc"].max().isoformat(),
        "lag_2d_available_by_issue": bool(sources.w_label_available.loc[lag2] <= issue.tz_convert("UTC")),
        "fixed_missing_value_rule": "target feature row must be finite",
        "gate_pass": not missing,
    }


def _fit_predict(
    channel: str,
    features: pd.DataFrame,
    target: pd.Series,
    selected: np.ndarray,
    target_features: pd.DataFrame,
    model_dir: Path,
) -> tuple[np.ndarray, dict[str, str], int]:
    x, y = features.loc[selected], target.loc[selected]
    if len(y) == 0 or not np.isfinite(x.to_numpy()).all() or not np.isfinite(y.to_numpy()).all():
        raise RuntimeError(f"V33XR3R2_EMPTY_OR_NONFINITE_TRAINING:{channel}")
    if not np.isfinite(target_features.to_numpy()).all():
        raise RuntimeError(f"V33XR3R2_NONFINITE_TARGET_FEATURE:{channel}")
    model_dir.mkdir(parents=True, exist_ok=True)
    raw, hashes = [], {}
    for quantile in QUANTILES:
        label = f"q{int(quantile * 100):02d}"
        model = LGBMRegressor(objective="quantile", alpha=quantile, **COMMON)
        model.fit(x, np.log1p(y))
        content = model.booster_.model_to_string()
        path = model_dir / f"{channel}_{label}.txt"
        path.write_text(content, encoding="utf-8", newline="\n")
        hashes[label] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw.append(np.asarray(model.predict(target_features), dtype=float))
    return enforce_quantile_integrity(np.stack(raw)), hashes, int(len(y))


def _causal_w_adapter(sources: RollingSources, issue: pd.Timestamp, training_end: pd.Timestamp) -> np.ndarray:
    jobs = sources.w_jobs
    start_utc = pd.Timestamp(TRAINING_START, tz=AEST).tz_convert("UTC")
    end_exclusive_utc = (training_end + pd.Timedelta(days=1)).tz_convert("UTC")
    eligible = jobs.loc[
        jobs["eligible"]
        & jobs["submit_utc"].ge(start_utc)
        & jobs["submit_utc"].lt(end_exclusive_utc)
        & jobs["end_utc"].le(issue.tz_convert("UTC"))
    ]
    mass = np.zeros((7, 96, COHORTS), dtype=float)
    cohort_index = {name: index for index, name in enumerate(sources.labels.cohort_ids)}
    for row in eligible.itertuples(index=False):
        mass[int(row.submit_aest.dayofweek), int(row.slot), cohort_index[str(row.cohort_id)]] += float(row.nodeh)
    totals = mass.sum(axis=(1, 2))
    if np.any(totals <= 0):
        raise RuntimeError("V33XR3R2_CAUSAL_W_ADAPTER_EMPTY_DOW")
    probabilities = mass / totals[:, None, None]
    if np.any(probabilities < 0) or not np.allclose(probabilities.sum(axis=(1, 2)), 1.0, atol=1e-12, rtol=0):
        raise RuntimeError("V33XR3R2_CAUSAL_W_ADAPTER_INVALID")
    return probabilities


def fit_forecast_day(repo: Path, day: str, output: Path, sources: RollingSources, specs: dict[str, dict[str, object]]) -> ForecastResult:
    target_day = pd.Timestamp(day, tz=AEST)
    issue = issue_time(day)
    training_end = target_day - pd.Timedelta(days=2)
    labels = sources.labels
    slot_day = labels.timestamps.normalize()
    start = pd.Timestamp(TRAINING_START, tz=AEST)
    target_slots = pd.date_range(target_day, periods=96, freq="15min")
    p_features = slot_features(labels.p_it_kw, labels.timestamps)
    g_features = slot_features(labels.g_h100_gpu, labels.timestamps)
    p_target = pd.Series(labels.p_it_kw, index=labels.timestamps)
    g_target = pd.Series(labels.g_h100_gpu, index=labels.timestamps)
    slot_label_available = labels.timestamps + pd.Timedelta(minutes=15)
    base_slot_select = (slot_day >= start) & (slot_day <= training_end) & (slot_label_available <= issue)
    p_select = np.asarray(base_slot_select & np.isfinite(p_target) & np.isfinite(p_features).all(axis=1))
    g_select = np.asarray(base_slot_select & np.isfinite(g_target) & np.isfinite(g_features).all(axis=1))
    models = output / "models"
    p, p_sha, p_rows = _fit_predict("P_REF", p_features, p_target, p_select, p_features.loc[target_slots], models)
    g, g_sha, g_rows = _fit_predict("G_REF", g_features, g_target, g_select, g_features.loc[target_slots], models)

    available = sources.w_label_available.le(issue.tz_convert("UTC"))
    causal_w = sources.w_daily.where(available)
    w_features = daily_features(causal_w)
    w_select = np.asarray(
        (causal_w.index >= start) & (causal_w.index <= training_end)
        & causal_w.notna() & np.isfinite(w_features).all(axis=1)
    )
    w_daily, w_sha, w_rows = _fit_predict(
        "W_FULLNODE_DAILY", w_features, causal_w, w_select,
        w_features.loc[[target_day]], models,
    )
    probabilities = _causal_w_adapter(sources, issue, training_end)
    w = w_daily[:, None, None] * probabilities[target_day.dayofweek][None, :, :]
    mass_error = float(np.max(np.abs(w.sum(axis=(1, 2)) - w_daily)))
    if mass_error > 1e-9 or np.any(w < 0):
        raise RuntimeError("V33XR3R2_W_MASS_IDENTITY")

    spec_sha = {channel: str(specs[channel]["spec_sha256"]) for channel in ("P", "G", "W")}
    feature_schema_sha = canonical_sha256({"P": SLOT_FEATURES, "G": SLOT_FEATURES, "W": DAILY_FEATURES})
    cohort_sha = canonical_sha256(list(labels.cohort_ids))
    payload = {
        "forecast_day": day,
        "issue_time": issue.isoformat(),
        "training_start": TRAINING_START,
        "training_end": training_end.date().isoformat(),
        "P_model_spec_sha": spec_sha["P"], "G_model_spec_sha": spec_sha["G"], "W_model_spec_sha": spec_sha["W"],
        "P_fitted_model_sha": p_sha, "G_fitted_model_sha": g_sha, "W_fitted_model_sha": w_sha,
        "P_Q90": p[2].tolist(), "G_Q90": g[2].tolist(), "W_Q50": w[1].tolist(),
        "feature_schema_sha": feature_schema_sha, "cohort_sha": cohort_sha,
        "source_sha_bundle": canonical_sha256(sources.source_sha256),
    }
    forecast_sha = canonical_sha256(payload)
    actual_slice = labels.timestamps.normalize() == target_day
    actual_w = float(sources.w_daily.loc[target_day])
    diagnostics = {
        "P_Q90_coverage": float(np.mean(labels.p_it_kw[actual_slice] <= p[2])),
        "P_Q50_MAE": float(np.mean(np.abs(labels.p_it_kw[actual_slice] - p[1]))),
        "P_WAPE": float(np.sum(np.abs(labels.p_it_kw[actual_slice] - p[1])) / max(np.sum(labels.p_it_kw[actual_slice]), 1e-15)),
        "G_Q90_coverage": float(np.mean(labels.g_h100_gpu[actual_slice] <= g[2])),
        "G_Q50_MAE": float(np.mean(np.abs(labels.g_h100_gpu[actual_slice] - g[1]))),
        "G_WAPE": float(np.sum(np.abs(labels.g_h100_gpu[actual_slice] - g[1])) / max(np.sum(labels.g_h100_gpu[actual_slice]), 1e-15)),
        "W_Q50_absolute_error": abs(float(w_daily[1]) - actual_w),
        "W_daily_mass_WAPE": abs(float(w_daily[1]) - actual_w) / max(actual_w, 1e-15),
    }
    latest_feature = max(slot_label_available[p_select].max(), sources.w_label_available.loc[w_select].max().tz_convert(AEST))
    latest_label = max(slot_label_available[p_select].max(), slot_label_available[g_select].max(), sources.w_label_available.loc[w_select].max().tz_convert(AEST))
    return ForecastResult(
        day, issue.isoformat(), training_end.date().isoformat(), p, g, w_daily, w,
        {"P": p_sha, "G": g_sha, "W": w_sha}, {"P": p_rows, "G": g_rows, "W": w_rows},
        spec_sha, feature_schema_sha, cohort_sha, sources.source_sha256,
        latest_feature.isoformat(), latest_label.isoformat(), mass_error, forecast_sha, diagnostics,
    )


def write_forecast_result(result: ForecastResult, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    arrays = output / "PGW_FORECAST_ARRAYS.npz"
    temporary = output / f"PGW_FORECAST_ARRAYS.{os.getpid()}.tmp.npz"
    np.savez_compressed(
        temporary,
        P_quantiles=result.p_quantiles,
        G_quantiles=result.g_quantiles,
        W_daily_quantiles=result.w_daily_quantiles,
        W_quantiles=result.w_quantiles,
    )
    os.replace(temporary, arrays)
    authority = {
        "artifact_id": "V33XR3R2_CAUSAL_PGW_DAY_BUNDLE_V1", "status": "PASS",
        "forecast_day": result.day, "issue_time": result.issue_time,
        "training_start": TRAINING_START, "training_end": result.training_end,
        "latest_training_feature_time": result.latest_training_feature_time,
        "latest_training_label_available_time": result.latest_training_label_available_time,
        "model_spec_sha256": result.model_spec_sha256,
        "fitted_model_sha256": result.fitted_model_sha256,
        "model_training_rows": result.model_training_rows,
        "optimizer_binding": {"P": "Q90", "G": "Q90", "W": "Q50"},
        "shapes": {"P": list(result.p_quantiles.shape), "G": list(result.g_quantiles.shape), "W": list(result.w_quantiles.shape)},
        "source_sha256": result.source_sha256, "feature_schema_sha256": result.feature_schema_sha256,
        "cohort_sha256": result.cohort_sha256, "forecast_sha256": result.forecast_sha256,
        "future_feature_read_count": 0, "future_label_read_count": 0,
        "W_mass_error_nodeh": result.w_mass_error_nodeh,
        "partial_shared_controllable_W": False,
        "diagnostics_after_forecast_freeze": result.diagnostics,
    }
    authority_path = output / "PGW_FORECAST_AUTHORITY.json"
    authority_path.write_text(json.dumps(authority, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    marker = {
        "artifact_id": "V33XR3R2_CAUSAL_PGW_PASS_MARKER_V1", "status": "PASS", "day": result.day,
        "forecast_sha256": result.forecast_sha256,
        "model_spec_sha256": result.model_spec_sha256,
        "files": {
            "PGW_FORECAST_ARRAYS.npz": sha256_file(arrays),
            "PGW_FORECAST_AUTHORITY.json": sha256_file(authority_path),
            **{f"models/{path.name}": sha256_file(path) for path in sorted((output / "models").glob("*.txt"))},
        },
    }
    marker_path = output / "PASS.json"
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return authority


def validate_forecast_pass(output: Path, specs: dict[str, dict[str, object]]) -> bool:
    marker_path = output / "PASS.json"
    if not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        expected_specs = {channel: specs[channel]["spec_sha256"] for channel in ("P", "G", "W")}
        if marker.get("status") != "PASS" or marker.get("model_spec_sha256") != expected_specs:
            return False
        return all((output / name).is_file() and sha256_file(output / name) == digest for name, digest in marker["files"].items())
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def materialize_atomic(repo: Path, day: str, root: Path, sources: RollingSources, specs: dict[str, dict[str, object]]) -> dict[str, object]:
    final = root / day
    if validate_forecast_pass(final, specs):
        return json.loads((final / "PGW_FORECAST_AUTHORITY.json").read_text(encoding="utf-8"))
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{day}.", dir=root))
    try:
        result = fit_forecast_day(repo, day, temporary, sources, specs)
        authority = write_forecast_result(result, temporary)
        if final.exists():
            shutil.rmtree(final)
        os.replace(temporary, final)
        return authority
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
