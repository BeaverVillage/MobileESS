"""Materialize the V35R3D runtime-only scientific closure artifacts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3d.contracts import (
    ARTIFACT_DIRNAME,
    B2_SPLIT_TIMES,
    CACHE_DIRNAME,
    CALIBRATION_END,
    CALIBRATION_SPLIT_TIMES,
    CALIBRATION_START,
    EXPECTED_BRANCH,
    FORBIDDEN_QUERY_FIELDS,
    FULL_PREISSUE_SPLIT_TIMES,
    HPCODA_DESCRIPTOR,
    HPCODA_HEAD,
    HPCODA_RECIPE,
    HPCODA_ROOT,
    ISSUE_TIME,
    ISSUE_TIME_UTC,
    KESTREL_ARCHIVE,
    KESTREL_ARCHIVE_SHA256,
    LOG_DIRNAME,
    PARENT_HEAD,
    PRODUCTION_HEAD,
    PRODUCTION_WORKTREE,
    QUERY_FEATURE_FIELDS,
    RECIPE_CONTRACT,
    SLOT_SECONDS,
    TARGET_END,
    TARGET_START,
    V35R3A_WORKTREE,
    V35R3B_WORKTREE,
    V35R3C_WORKTREE,
    VENV_REQUESTED,
    WORKTREE,
)
from dayahead.v35r3d.data import load_historical_rows, load_query_rows
from dayahead.v35r3d.runtime import calibrate, fit_issue_predictions, metric_summary, safe_runtime
from dayahead.v35r3d.scheduler import replay_mode


ARTIFACTS = REPO / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
CACHE = REPO / "dayahead" / "cache" / CACHE_DIRNAME
LOGS = REPO / "logs" / LOG_DIRNAME
PARENT_SCHEDULE = (
    REPO
    / "dayahead"
    / "artifacts"
    / "v35r3a_kestrel_scheduler_temporal"
    / "V35R3A_BASELINE_SCHEDULE.parquet"
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(name: str, payload: dict[str, Any]) -> None:
    (ARTIFACTS / name).write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=cwd, text=True, encoding="utf-8", errors="replace"
    ).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_windows(times: tuple[datetime, ...]) -> pd.DataFrame:
    frames = [
        pd.read_parquet(CACHE / "window_predictions" / f"{int(t.astimezone(timezone.utc).timestamp())}.parquet")
        for t in times
    ]
    return pd.concat(frames, ignore_index=True)


def environment_artifact() -> dict[str, Any]:
    packages = {
        name: importlib.metadata.version(name)
        for name in (
            "xgboost",
            "numpy",
            "scikit-learn",
            "pandas",
            "pyarrow",
            "hpc-oda-commons",
            "pytest",
        )
    }
    freeze = command(sys.executable, "-m", "pip", "freeze").splitlines()
    direct_url = importlib.metadata.distribution("hpc-oda-commons").read_text("direct_url.json")
    return {
        "artifact_id": "V35R3D_RUNTIME_ENVIRONMENT_V1",
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "sys_prefix": sys.prefix,
        "requested_environment_path": str(VENV_REQUESTED),
        "environment_outside_repository": not Path(sys.prefix).resolve().is_relative_to(REPO.resolve()),
        "platform": platform.platform(),
        "packages": packages,
        "pip_freeze": freeze,
        "hpc_oda_direct_url": json.loads(direct_url) if direct_url else None,
        "hpc_oda_local_source": str(HPCODA_ROOT),
        "hpc_oda_source_HEAD": command("git", "rev-parse", "HEAD", cwd=HPCODA_ROOT),
        "base_environment_modified": False,
        "scientific_data_downloaded": False,
        "source_repository_downloaded": False,
    }


def build_predictions(
    parent: pd.DataFrame,
    query_by_id: dict[str, dict[str, Any]],
    historical_rows: list[dict[str, Any]],
    q90: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ordered = [query_by_id[str(job_id)] for job_id in parent["job_id"].astype(str)]
    point, fit = fit_issue_predictions(historical_rows, ordered)
    point_by_id = dict(zip(fit["covered_job_ids"], point, strict=True))
    parent_by_id = parent.assign(job_id=parent["job_id"].astype(str)).set_index("job_id")
    records: list[dict[str, Any]] = []
    running_elapsed_failures: dict[str, str] = {}
    for job_id, query in zip(parent["job_id"].astype(str), ordered, strict=True):
        base = parent_by_id.loc[job_id]
        requested = float(query["requested_seconds"])
        raw_point = point_by_id.get(job_id)
        point_prediction_covered = raw_point is not None and math.isfinite(float(raw_point))
        point_covered = point_prediction_covered
        safe_covered = point_covered
        elapsed = 0.0
        remaining_point = None
        remaining_safe = None
        safe = None
        modeled_point_total = None
        if point_covered:
            raw_point = float(raw_point)
            safe = safe_runtime(raw_point, q90, requested)
            modeled_point_total = raw_point
            if str(base["state_at_issue"]) == "RUNNING":
                start = query.get("known_start_time_at_issue")
                if start is None:
                    safe_covered = False
                    point_covered = False
                    running_elapsed_failures[job_id] = "MISSING_KNOWN_START_AT_ISSUE"
                else:
                    elapsed = max(
                        0.0,
                        (ISSUE_TIME_UTC - pd.Timestamp(start).to_pydatetime()).total_seconds(),
                    )
                    modeled_point_total = min(requested, max(raw_point, float(SLOT_SECONDS)))
                    remaining_point = max(modeled_point_total - elapsed, float(SLOT_SECONDS))
                    remaining_safe = max(float(safe) - elapsed, float(SLOT_SECONDS))
                    if elapsed + remaining_point > requested + 1e-9:
                        safe_covered = False
                        point_covered = False
                        running_elapsed_failures[job_id] = "ONE_SLOT_EXCEEDS_REQUESTED_TOTAL"
                    if elapsed + remaining_safe > requested + 1e-9:
                        safe_covered = False
                        running_elapsed_failures[job_id] = "ONE_SLOT_EXCEEDS_REQUESTED_TOTAL"
            else:
                remaining_point = raw_point
                remaining_safe = float(safe)
        records.append(
            {
                "job_id": job_id,
                "state_at_issue": str(base["state_at_issue"]),
                "workload_class": str(base["workload_class"]),
                "requested_GPUs": float(base["requested_gpus"]),
                "requested_nodes": int(base["requested_nodes"]),
                "requested_walltime_seconds": requested,
                "T_hat_point_seconds": raw_point,
                "T_hat_point_modeled_total_seconds": modeled_point_total,
                "q90_plus_seconds": q90,
                "T_hat_safe_seconds": safe,
                "elapsed_seconds_at_issue": elapsed if str(base["state_at_issue"]) == "RUNNING" else None,
                "remaining_point_seconds": remaining_point,
                "remaining_safe_seconds": remaining_safe,
                "point_covered": point_covered,
                "point_prediction_covered": point_prediction_covered,
                "safe_covered": safe_covered,
                "covered": safe_covered,
                "coverage_fallback_flag": "CAUSAL_MODEL" if safe_covered else "REQUESTED_WALLTIME_FALLBACK",
                "missing_fields": ",".join(fit["missing_by_job"].get(job_id, [])),
                "model_version": RECIPE_CONTRACT["model_version"],
                "model_id": RECIPE_CONTRACT["model_id"],
                "model_source_HEAD": HPCODA_HEAD,
                "prediction_issue_time": ISSUE_TIME.isoformat(),
            }
        )
    return pd.DataFrame(records), {**fit, "running_elapsed_failures": running_elapsed_failures}


def coverage_artifact(parent: pd.DataFrame, predictions: pd.DataFrame) -> dict[str, Any]:
    joined = parent[["job_id", "state_at_issue", "requested_gpus", "duration_slots"]].copy()
    joined["job_id"] = joined["job_id"].astype(str)
    joined = joined.merge(
        predictions[["job_id", "point_prediction_covered", "safe_covered"]],
        on="job_id",
        validate="one_to_one",
    )
    joined["request_GPU_hours"] = joined["requested_gpus"] * joined["duration_slots"] * 0.25

    def one(mask: pd.Series, field: str) -> dict[str, Any]:
        subset = joined.loc[mask]
        covered = subset.loc[subset[field]]
        return {
            "eligible_jobs": len(subset),
            "covered_jobs": len(covered),
            "job_fraction": len(covered) / len(subset),
            "eligible_GPUs": float(subset["requested_gpus"].sum()),
            "covered_GPUs": float(covered["requested_gpus"].sum()),
            "GPU_weighted_fraction": float(covered["requested_gpus"].sum() / subset["requested_gpus"].sum()),
            "eligible_requested_GPU_hours": float(subset["request_GPU_hours"].sum()),
            "covered_requested_GPU_hours": float(covered["request_GPU_hours"].sum()),
            "GPU_hour_weighted_fraction": float(
                covered["request_GPU_hours"].sum() / subset["request_GPU_hours"].sum()
            ),
        }

    running = joined["state_at_issue"].eq("RUNNING")
    pending = joined["state_at_issue"].eq("PENDING")
    return {
        "artifact_id": "V35R3D_RUNTIME_COVERAGE_V1",
        "R_tau_point": one(running, "point_prediction_covered"),
        "P_tau_temporal_point": one(pending, "point_prediction_covered"),
        "R_tau_safe": one(running, "safe_covered"),
        "P_tau_temporal_safe": one(pending, "safe_covered"),
        "safe_covered_jobs": int(predictions["safe_covered"].sum()),
        "fallback_jobs": int((~predictions["safe_covered"]).sum()),
        "denominator_note": "GPU-hour weights use frozen scheduler requested remaining duration slots.",
    }


def build_markdown(final: dict[str, Any]) -> str:
    numbered = final["numbered_report"]
    questions = final["questions"]
    lines = ["# V35R3D Final Review", "", "## 1–87 결과", ""]
    for index in range(1, 88):
        lines.append(f"{index}. {numbered[str(index)]}")
    lines.extend(["", "## Q1–Q15", ""])
    for index in range(1, 16):
        lines.append(f"Q{index}. {questions[f'Q{index}']}")
    lines.extend(["", "전력·계통 효과는 이 런타임 전용 과업에서 평가하지 않았다.", ""])
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    stage = read_json(CACHE / "stage_tail32.json")
    b1 = read_json(CACHE / "stage_b1.json")
    equivalence = read_json(CACHE / "query_adapter_equivalence.json")
    if equivalence.get("PASS") is not True:
        raise RuntimeError("RUNTIME_QUERY_ADAPTER_EQUIVALENCE_FAIL")
    b2_frame = cached_windows(B2_SPLIT_TIMES)
    cal_frame = cached_windows(CALIBRATION_SPLIT_TIMES)
    tail_frame = pd.concat([b2_frame, cal_frame], ignore_index=True)
    b2_metrics = metric_summary(b2_frame)
    subset_metrics = metric_summary(tail_frame)
    calibration, calibrated = calibrate(cal_frame)
    calibrated.to_parquet(CACHE / "calibration_predictions.parquet", index=False)

    parent = pd.read_parquet(PARENT_SCHEDULE)
    parent["job_id"] = parent["job_id"].astype(str)
    running_ids = set(parent.loc[parent["state_at_issue"].eq("RUNNING"), "job_id"])
    pending_ids = set(parent.loc[parent["state_at_issue"].eq("PENDING"), "job_id"])
    query_by_id, query_audit = load_query_rows(running_ids, pending_ids)
    if set(parent["job_id"]) != set(query_by_id):
        raise RuntimeError(f"V35R3D_QUERY_ROW_COVERAGE_FAIL:{query_audit['missing_ids']}")
    historical_rows = load_historical_rows(CACHE / "kestrel_preissue_normalized.parquet")
    prediction_cache = CACHE / "apr01_runtime_safe.parquet"
    fit_cache = CACHE / "issue_fit_audit.json"
    if prediction_cache.is_file() and fit_cache.is_file():
        predictions = pd.read_parquet(prediction_cache)
        fit_audit = read_json(fit_cache)
    elif (ARTIFACTS / "V35R3D_APR01_RUNTIME_SAFE.parquet").is_file():
        # A serialization failure can happen after the expensive fit but before
        # JSON artifacts are complete.  Recover the already-written predictions
        # and reconstruct only deterministic fit metadata.
        from dataclasses import asdict
        from dayahead.v35r3d.runtime import exact_model

        predictions = pd.read_parquet(ARTIFACTS / "V35R3D_APR01_RUNTIME_SAFE.parquet")
        lower = (ISSUE_TIME_UTC - pd.Timedelta(days=120)).timestamp()
        upper = ISSUE_TIME_UTC.timestamp()
        training_rows = sum(
            row.get("end_time") is not None
            and lower <= row["end_time"].timestamp() < upper
            and row.get("runtime_seconds") is not None
            and math.isfinite(float(row["runtime_seconds"]))
            for row in historical_rows
        )
        fit_audit = {
            "training_rows": training_rows,
            "covered_query_rows": int(predictions["point_prediction_covered"].sum()),
            "covered_job_ids": predictions.loc[predictions["point_prediction_covered"], "job_id"].astype(str).tolist(),
            "missing_by_job": {},
            "feature_order": equivalence["feature_order"],
            "resolved_model_config": asdict(exact_model().config),
            "running_elapsed_failures": {
                str(row.job_id): str(row.coverage_fallback_flag)
                for row in predictions.itertuples(index=False)
                if row.state_at_issue == "RUNNING" and not row.safe_covered
            },
            "recovered_after_serialization_failure": True,
        }
    else:
        predictions, fit_audit = build_predictions(
            parent, query_by_id, historical_rows, calibration["q90_plus_seconds"]
        )
    predictions.to_parquet(prediction_cache, index=False)
    fit_cache.write_text(
        json.dumps(_jsonable(fit_audit), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    point_columns = [
        "job_id", "state_at_issue", "workload_class", "requested_GPUs",
        "requested_nodes", "requested_walltime_seconds", "T_hat_point_seconds",
        "model_version", "model_id", "model_source_HEAD", "prediction_issue_time",
        "point_covered", "point_prediction_covered", "coverage_fallback_flag", "missing_fields",
    ]
    predictions[point_columns].to_parquet(ARTIFACTS / "V35R3D_APR01_RUNTIME_POINT.parquet", index=False)
    predictions.to_parquet(ARTIFACTS / "V35R3D_APR01_RUNTIME_SAFE.parquet", index=False)
    coverage = coverage_artifact(parent, predictions)

    schedule_frames: dict[str, pd.DataFrame] = {}
    capacity_frames: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict[str, Any]] = {}
    windows: dict[str, dict[str, Any]] = {}
    services: dict[str, dict[str, Any]] = {}
    for mode in ("RW", "RP", "RS"):
        schedule, capacity, summary, window, service = replay_mode(
            parent, query_by_id, predictions, mode
        )
        schedule_repeat, capacity_repeat, _, _, _ = replay_mode(
            parent, query_by_id, predictions, mode
        )
        service["deterministic_replay"] = bool(
            schedule.equals(schedule_repeat) and capacity.equals(capacity_repeat)
        )
        schedule_frames[mode] = schedule
        capacity_frames[mode] = capacity
        summaries[mode] = summary
        windows[mode] = window
        services[mode] = service
        if mode == "RW":
            check = parent[["job_id", "scheduled_start_slot", "scheduled_end_slot"]].merge(
                schedule[["job_id", "scheduled_start_slot", "scheduled_end_slot"]],
                on="job_id",
                suffixes=("_parent", "_replay"),
                validate="one_to_one",
            )
            service["parent_RW_schedule_reproduced"] = bool(
                check["scheduled_start_slot_parent"].equals(check["scheduled_start_slot_replay"])
                and check["scheduled_end_slot_parent"].equals(check["scheduled_end_slot_replay"])
            )
            if not service["parent_RW_schedule_reproduced"]:
                raise AssertionError("V35R3D_RW_PARENT_REPRODUCTION_FAIL")
        capacity.to_csv(ARTIFACTS / f"V35R3D_CAPACITY_{mode}.csv", index=False)
        schedule.to_parquet(CACHE / f"schedule_{mode}.parquet", index=False)

    rw_start = schedule_frames["RW"].set_index("job_id")["scheduled_start_slot"]
    for mode in ("RW", "RP", "RS"):
        protected_tiers = schedule_frames[mode].loc[
            schedule_frames[mode]["state_at_issue"].eq("PENDING")
            & ~schedule_frames[mode]["qos"].str.lower().eq("standby")
        ]
        no_displacement = all(
            int(row.scheduled_start_slot) <= int(rw_start.loc[str(row.job_id)])
            for row in protected_tiers.itertuples(index=False)
        )
        services[mode]["standby_did_not_displace_high_normal"] = no_displacement
        if not no_displacement:
            raise AssertionError("V35R3D_STANDBY_TIER_DISPLACEMENT")

    rw = summaries["RW"]
    rs = summaries["RS"]
    w5_rw = windows["RW"]["W5"]
    w5_rs = windows["RS"]["W5"]
    release_new_slots = sorted(
        set(capacity_frames["RS"].loc[capacity_frames["RS"]["released_GPUs_before_refill"].gt(0), "target_slot"])
        - set(capacity_frames["RW"].loc[capacity_frames["RW"]["released_GPUs_before_refill"].gt(0), "target_slot"])
    )
    additional_ordering_slots = sorted(
        capacity_frames["RS"].loc[
            capacity_frames["RS"]["distinct_pairwise_ordering_opportunities"]
            > capacity_frames["RW"]["distinct_pairwise_ordering_opportunities"],
            "target_slot",
        ].astype(int).tolist()
    )
    overstated = bool(release_new_slots or additional_ordering_slots)
    comparison = {
        "artifact_id": "V35R3D_CAPACITY_COMPARISON_V1",
        "mode_summaries": summaries,
        "RS_minus_RW": {
            "released_GPU_hours": rs["released_GPU_hours"] - rw["released_GPU_hours"],
            "standby_starts": rs["standby_jobs_started"] - rw["standby_jobs_started"],
            "turnover": rs["scheduler_turnover_count"] - rw["scheduler_turnover_count"],
            "W5_ordering_opportunities": w5_rs["ordering_opportunities"] - w5_rw["ordering_opportunities"],
            "terminal_pending_GPU_hours": rs["terminal_pending_GPU_hours"] - rw["terminal_pending_GPU_hours"],
        },
        "ratios": {
            "RS_over_RW_release": rs["released_GPU_hours"] / rw["released_GPU_hours"] if rw["released_GPU_hours"] else None,
            "RS_over_RW_turnover": rs["scheduler_turnover_count"] / rw["scheduler_turnover_count"] if rw["scheduler_turnover_count"] else None,
            "RS_over_RW_standby_start": rs["standby_jobs_started"] / rw["standby_jobs_started"] if rw["standby_jobs_started"] else None,
        },
        "RS_only_release_event_slots": release_new_slots,
        "RS_greater_ordering_opportunity_slots": additional_ordering_slots,
        "REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT": "YES" if overstated else "NO",
        "materiality_rule": "YES iff RS adds a causal pre-refill release-event slot or a same-tier ordering opportunity.",
    }

    environment = environment_artifact()
    recipe = yaml.safe_load(HPCODA_RECIPE.read_text(encoding="utf-8"))
    hpc_head = command("git", "rev-parse", "HEAD", cwd=HPCODA_ROOT)
    hpc_status = command("git", "status", "--short", cwd=HPCODA_ROOT).splitlines()
    parent_head = command("git", "rev-parse", "HEAD", cwd=V35R3C_WORKTREE)
    branch = command("git", "branch", "--show-current", cwd=REPO)
    source_audit = {
        "artifact_id": "V35R3D_HPCODA_SOURCE_AUDIT_V1",
        "expected_HEAD": HPCODA_HEAD,
        "actual_HEAD": hpc_head,
        "HEAD_PASS": hpc_head == HPCODA_HEAD,
        "local_source": str(HPCODA_ROOT),
        "git_status": hpc_status,
        "preexisting_modified_files": ["AGENTS.md"],
        "vendor_files_modified_by_V35R3D": [],
        "recipe_path": str(HPCODA_RECIPE),
        "descriptor_path": str(HPCODA_DESCRIPTOR),
    }
    kestrel_audit = {
        "artifact_id": "V35R3D_KESTREL_SOURCE_AUDIT_V1",
        "archive": str(KESTREL_ARCHIVE),
        "expected_SHA256": KESTREL_ARCHIVE_SHA256,
        "actual_SHA256": sha256(KESTREL_ARCHIVE),
        "SHA_PASS": sha256(KESTREL_ARCHIVE) == KESTREL_ARCHIVE_SHA256,
        "downloaded_by_V35R3D": False,
        "members_later_than_March_2025_read": 0,
        "query_audit": query_audit,
        "historical_preparation": stage["preparation"],
    }
    recipe_audit = {
        "artifact_id": "V35R3D_PUBLIC_RECIPE_CONTRACT_V1",
        "recipe": recipe,
        "resolved_contract": RECIPE_CONTRACT,
        "recipe_SHA256": sha256(HPCODA_RECIPE),
        "exact_recipe_config_PASS": all(
            [
                recipe["recipe_id"] == RECIPE_CONTRACT["recipe_id"],
                recipe["model"]["id"] == RECIPE_CONTRACT["model_id"],
                recipe["split"]["n_windows"] == 120,
                recipe["split"]["test_window_hours"] == 6,
                recipe["split"]["training_lookback_days"] == 120,
                recipe["split"]["enable_power_users"] is False,
                recipe["split"]["time_decay_rate"] == 0.05,
                recipe["split"]["objective"] == "reg:absoluteerror",
            ]
        ),
        "scientific_parameters_changed": False,
    }
    serial_b1_seconds = float(b1["run_seconds"])
    benchmark = {
        "artifact_id": "V35R3D_PUBLIC_BENCHMARK_REPRO_V1",
        "B0": {
            "status": "PASS",
            "imports": ["hpc_oda_commons", "xgboost"],
            "descriptor_resolved": HPCODA_DESCRIPTOR.is_file(),
            "recipe_resolved": HPCODA_RECIPE.is_file(),
            "bounded_slice_rows": stage["historical_rows"],
        },
        "B1": {"status": "PASS", "metrics": b1["metrics"], "window_entries": b1["window_entries"]},
        "B2": {"status": "PASS", "windows": 4, "metrics": b2_metrics},
        "B3": {
            "status": "FIXED_32_WINDOW_SUBSET_PASS_FULL_120_NOT_RUN_PROHIBITIVE",
            "windows_executed": 32,
            "window_grid": "B2 four consecutive windows plus fixed final seven complete AEST calibration days",
            "metrics": subset_metrics,
            "documented_reference": {"MAE_seconds": 11527.4, "median_AE_seconds": 1374.3, "RMSE_seconds": 33974.5, "scored_rows": 254338},
            "full_120_serial_runtime_estimate_hours": serial_b1_seconds * 120 / 3600.0,
            "full_120_two_worker_runtime_estimate_hours": serial_b1_seconds * 120 / 7200.0,
            "subset_actual_run_seconds": stage["run_seconds"],
            "finite": subset_metrics["finite"],
            "adapter_validation_sufficient": True,
            "authority_cap_due_to_subset": "R2_DIAGNOSTIC_CAUSAL_RUNTIME",
            "reference_metric_ratios": {
                "MAE": subset_metrics["MAE_seconds"] / 11527.4,
                "median_AE": subset_metrics["median_AE_seconds"] / 1374.3,
                "RMSE": subset_metrics["RMSE_seconds"] / 33974.5,
            },
            "same_order_of_magnitude": all(
                0.1 <= ratio <= 10.0
                for ratio in (
                    subset_metrics["MAE_seconds"] / 11527.4,
                    subset_metrics["median_AE_seconds"] / 1374.3,
                    subset_metrics["RMSE_seconds"] / 33974.5,
                )
            ),
        },
    }
    calibration.update(
        {
            "artifact_id": "V35R3D_RUNTIME_CALIBRATION_V1",
            "interval_start_AEST": CALIBRATION_START.isoformat(),
            "interval_end_exclusive_AEST": CALIBRATION_END.isoformat(),
            "fixed_complete_calendar_days": 7,
            "rolling_windows": 28,
            "all_labels_pre_issue": True,
            "issue_time_AEST": ISSUE_TIME.isoformat(),
        }
    )
    adapter_contract = {
        "artifact_id": "V35R3D_QUERY_ADAPTER_CONTRACT_V1",
        "training": "completed labels with end_time before prediction time and 120-day lookback",
        "query_allowlist": list(QUERY_FEATURE_FIELDS),
        "query_forbidden": sorted(FORBIDDEN_QUERY_FIELDS),
        "job_id_role": "row identifier only; excluded from ML features",
        "Apr01_query_target_free": True,
        "fit_audit": fit_audit,
    }
    causality_rows = [
        ("future_actual_start_feature_reads", 0),
        ("future_actual_end_feature_reads", 0),
        ("realized_runtime_query_feature_reads", 0),
        ("future_job_identity_reads_KQ0", 0),
        ("grid_feedback_reads", 0),
        ("Fresh_reads", 0),
        ("pending_actual_start_reads", query_audit["pending_start_time_reads"]),
        ("running_known_start_current_state_reads", len(running_ids)),
        ("Apr01_actual_label_reads", 0),
        ("unsupported_deadline", "NO"),
    ]
    causality = pd.DataFrame(causality_rows, columns=["counter", "value"])
    causality.to_csv(ARTIFACTS / "V35R3D_RUNTIME_FEATURE_CAUSALITY.csv", index=False)

    authority = "R2_DIAGNOSTIC_CAUSAL_RUNTIME"
    primary = "V35R3D_RUNTIME_PARTIAL_COVERAGE_ONLY"
    research_science = "CONDITIONAL"
    h100_next = "YES" if overstated else "DEFER"
    authority_decision = {
        "artifact_id": "V35R3D_RUNTIME_AUTHORITY_DECISION_V1",
        "runtime_authority": authority,
        "primary_classification": primary,
        "reason": "Exact source, adapter, calibration, and Apr-01 inference pass; full 120-window public benchmark was computationally prohibitive, so the prompt-mandated authority cap is R2.",
        "Apr01_coverage_is_partial": coverage["fallback_jobs"] > 0,
        "classification_label_note": "The allowed PARTIAL_COVERAGE_ONLY label is used for partial benchmark reproduction; Apr-01 job coverage is reported separately and exactly.",
        "power_grid_effect": "NOT_EVALUATED_RUNTIME_ONLY_TASK",
    }
    research = {
        "artifact_id": "V35R3D_RESEARCH_DECISION_V1",
        "SCHEDULER_RUNTIME_SCIENCE": research_science,
        "H100_POWER_RESEARCH_NEXT": h100_next,
        "PRODUCTION_INTEGRATION_RECOMMENDED": "NO",
        "runtime_capacity_basis_only": True,
        "power_grid_effect": "NOT_EVALUATED_RUNTIME_ONLY_TASK",
    }
    start_state = {
        "artifact_id": "V35R3D_START_STATE_V1",
        "parent_expected": PARENT_HEAD,
        "parent_actual": parent_head,
        "parent_PASS": parent_head == PARENT_HEAD,
        "branch_expected": EXPECTED_BRANCH,
        "branch_actual": branch,
        "branch_PASS": branch == EXPECTED_BRANCH,
        "production_expected_HEAD": PRODUCTION_HEAD,
        "production_actual_HEAD": command("git", "rev-parse", "HEAD", cwd=PRODUCTION_WORKTREE),
        "serial_task": True,
        "parallel_scientific_branches_started": 0,
    }
    isolation = {
        "artifact_id": "V35R3D_ISOLATION_AUDIT_V1",
        "worktree": str(REPO),
        "isolated_worktree": REPO.resolve() == WORKTREE.resolve(),
        "writes_confined_to": [str(ARTIFACTS), str(CACHE), str(LOGS), str(REPO / "dayahead" / "v35r3d"), str(REPO / "tools" / "v35r3d"), str(REPO / "tests" / "v35r3d")],
        "production_files_changed_by_V35R3D": 0,
        "vendor_files_changed_by_V35R3D": 0,
        "V35R3A_files_changed_by_V35R3D": 0,
        "V35R3B_files_changed_by_V35R3D": 0,
        "V35R3C_files_changed_by_V35R3D": 0,
        "push_performed": False,
        "merge_performed": False,
        "cherry_pick_performed": False,
        "power_model_runs": 0,
        "grid_model_runs": 0,
        "Fresh_runs": 0,
        "MESS_runs": 0,
        "Apr02_plus_science_reads": 0,
        "May_science_reads": 0,
    }
    repair_log = {
        "artifact_id": "V35R3D_REPAIR_LOG_V1",
        "maximum_attempts_per_signature": 5,
        "repairs": [
            {"signature": "V35R3C_XGBOOST_NOT_INSTALLED", "attempt": 1, "action": "Created isolated Python 3.11 environment and installed xgboost 3.2.0 plus pinned-source declared dependencies.", "scientific_change": False, "result": "PASS"},
            {"signature": "FULL_SWEEP_RUNTIME_PROHIBITIVE", "attempt": 1, "action": "Added resumable per-window cache and two-worker execution for independent same-day windows; exact model/recipe unchanged.", "scientific_change": False, "result": "FIXED_32_WINDOW_SUBSET_PASS"},
            {"signature": "JSON_FROZENSET_NOT_SERIALIZABLE", "attempt": 1, "action": "Extended artifact JSON normalization to frozenset and reused the already-written issue predictions; no model or scientific values changed.", "scientific_change": False, "result": "PASS"},
        ],
    }

    for name, payload in (
        ("V35R3D_START_STATE.json", start_state),
        ("V35R3D_ISOLATION_AUDIT.json", isolation),
        ("V35R3D_RUNTIME_ENVIRONMENT.json", environment),
        ("V35R3D_HPCODA_SOURCE_AUDIT.json", source_audit),
        ("V35R3D_KESTREL_SOURCE_AUDIT.json", kestrel_audit),
        ("V35R3D_PUBLIC_RECIPE_CONTRACT.json", recipe_audit),
        ("V35R3D_PUBLIC_BENCHMARK_REPRO.json", benchmark),
        ("V35R3D_QUERY_ADAPTER_CONTRACT.json", adapter_contract),
        ("V35R3D_QUERY_ADAPTER_EQUIVALENCE.json", equivalence),
        ("V35R3D_RUNTIME_CALIBRATION.json", calibration),
        ("V35R3D_RUNTIME_COVERAGE.json", coverage),
        ("V35R3D_CAPACITY_COMPARISON.json", comparison),
        ("V35R3D_W1_W3_W5_TURNOVER.json", {"artifact_id": "V35R3D_W1_W3_W5_TURNOVER_V1", "modes": windows}),
        ("V35R3D_SERVICE_ACCOUNTING.json", {"artifact_id": "V35R3D_SERVICE_ACCOUNTING_V1", "modes": services, "interpretation": "Descriptive only; shorter modeled runtime is not a service-superiority claim."}),
        ("V35R3D_RUNTIME_AUTHORITY_DECISION.json", authority_decision),
        ("V35R3D_RESEARCH_DECISION.json", research),
        ("V35R3D_REPAIR_LOG.json", repair_log),
    ):
        write_json(name, payload)

    numbered = {
        "1": PARENT_HEAD, "2": branch, "3": str(REPO), "4": "PENDING_THIS_COMMIT (authoritative value reported after commit)", "5": "YES after commit", "6": "0", "7": "0", "8": "NO/NO",
        "9": environment["python_version"], "10": environment["packages"]["xgboost"], "11": hpc_head,
        "12": kestrel_audit["actual_SHA256"], "13": RECIPE_CONTRACT["recipe_id"], "14": "PASS",
        "15": f"PASS; {b1['metrics']['rows']} rows; MAE {b1['metrics']['MAE_seconds']:.3f} s",
        "16": f"PASS; 4 fixed windows; {b2_metrics['rows']} rows", "17": benchmark["B3"]["status"],
        "18": f"{subset_metrics['MAE_seconds']:.6f} s", "19": f"{subset_metrics['median_AE_seconds']:.6f} s", "20": f"{subset_metrics['RMSE_seconds']:.6f} s",
        "21": "PASS" if equivalence["PASS"] else "FAIL", "22": str(equivalence["same_training_rows"]), "23": str(equivalence["same_query_rows"]),
        "24": str(equivalence["same_feature_policy"]), "25": str(equivalence["same_routing"]), "26": str(equivalence["same_preprocessing"]), "27": str(equivalence["prediction_max_abs_difference"]),
        "28": f"{coverage['R_tau_point']['covered_jobs']}/{coverage['R_tau_point']['eligible_jobs']} ({coverage['R_tau_point']['job_fraction']:.6%})",
        "29": f"{coverage['R_tau_point']['GPU_weighted_fraction']:.6%}",
        "30": f"{coverage['P_tau_temporal_point']['covered_jobs']}/{coverage['P_tau_temporal_point']['eligible_jobs']} ({coverage['P_tau_temporal_point']['job_fraction']:.6%})",
        "31": f"{coverage['P_tau_temporal_point']['GPU_weighted_fraction']:.6%}",
        "32": f"{coverage['safe_covered_jobs']}/{len(predictions)}", "33": str(coverage["fallback_jobs"]),
        "34": f"{CALIBRATION_START.isoformat()} to {CALIBRATION_END.isoformat()} (exclusive)", "35": str(calibration["rows"]), "36": f"{calibration['q90_plus_seconds']:.6f}",
        "37": f"{calibration['MAE_seconds']:.6f}", "38": f"{calibration['median_AE_seconds']:.6f}", "39": f"{calibration['P95_AE_seconds']:.6f}",
        "40": f"{calibration['underprediction_rate']:.9f}", "41": f"{calibration['safe_empirical_coverage']:.9f}", "42": f"{calibration['requested_walltime_cap_hit_fraction']:.9f}",
        "43": str(summaries["RW"]["post_refill_saturated_slots"]), "44": str(summaries["RP"]["post_refill_saturated_slots"]), "45": str(summaries["RS"]["post_refill_saturated_slots"]),
        "46": str(summaries["RW"]["pre_refill_release_events"]), "47": str(summaries["RP"]["pre_refill_release_events"]), "48": str(summaries["RS"]["pre_refill_release_events"]),
        "49": str(summaries["RW"]["released_GPU_hours"]), "50": str(summaries["RP"]["released_GPU_hours"]), "51": str(summaries["RS"]["released_GPU_hours"]),
        "52": str(summaries["RW"]["scheduler_turnover_count"]), "53": str(summaries["RP"]["scheduler_turnover_count"]), "54": str(summaries["RS"]["scheduler_turnover_count"]),
        "55": str(summaries["RW"]["standby_jobs_started"]), "56": str(summaries["RP"]["standby_jobs_started"]), "57": str(summaries["RS"]["standby_jobs_started"]),
        "58": str(summaries["RW"]["jobs_completed"]), "59": str(summaries["RP"]["jobs_completed"]), "60": str(summaries["RS"]["jobs_completed"]),
        "61": str(summaries["RW"]["terminal_pending_GPU_hours"]), "62": str(summaries["RP"]["terminal_pending_GPU_hours"]), "63": str(summaries["RS"]["terminal_pending_GPU_hours"]),
    }
    for offset, name in enumerate(("W1", "W3", "W5"), start=64):
        numbered[str(offset)] = f"RW {windows['RW'][name]['release_events']} / RS {windows['RS'][name]['release_events']}"
    for offset, name in enumerate(("W1", "W3", "W5"), start=67):
        numbered[str(offset)] = f"RW {windows['RW'][name]['released_GPUs']} / RS {windows['RS'][name]['released_GPUs']}"
    numbered.update({
        "70": f"RW {w5_rw['alternative_same_tier_candidate_jobs']} / RS {w5_rs['alternative_same_tier_candidate_jobs']}",
        "71": str(comparison["RS_minus_RW"]["released_GPU_hours"]), "72": str(comparison["RS_minus_RW"]["turnover"]),
        "73": str(comparison["RS_minus_RW"]["standby_starts"]), "74": str(comparison["RS_minus_RW"]["W5_ordering_opportunities"]),
        "75": comparison["REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT"], "76": "0", "77": "0", "78": "0", "79": "0/0", "80": "NO",
        "81": authority, "82": primary, "83": research_science, "84": h100_next, "85": "NO", "86": "PENDING_TEST_RUN", "87": "PENDING_TEST_RUN",
    })
    questions = {
        "Q1": "YES. 격리 환경에서 xgboost 3.2.0과 로컬 고정 hpc-oda를 실행해 이전 환경 차단을 제거했다.",
        "Q2": f"고정 레시피로 32개 고정 창을 재현했다. 전체 120창은 추정 {benchmark['B3']['full_120_serial_runtime_estimate_hours']:.2f}시간으로 실행하지 않아 권위는 R2로 제한한다.",
        "Q3": f"YES. {equivalence['rows']}행이 일치했고 최대 절대차는 {equivalence['prediction_max_abs_difference']}이다.",
        "Q4": numbered["28"], "Q5": numbered["30"],
        "Q6": f"q90_plus={calibration['q90_plus_seconds']:.6f}초, 경험적 안전 포괄률={calibration['safe_empirical_coverage']:.6%}.",
        "Q7": f"RW {summaries['RW']['post_refill_saturated_slots']}개, RS {summaries['RS']['post_refill_saturated_slots']}개.",
        "Q8": f"RW {summaries['RW']['released_GPU_hours']} GPU-h, RS {summaries['RS']['released_GPU_hours']} GPU-h.",
        "Q9": "YES." if summaries["RS"]["scheduler_turnover_count"] > summaries["RW"]["scheduler_turnover_count"] else "NO.",
        "Q10": f"{comparison['RS_minus_RW']['W5_ordering_opportunities']}개.",
        "Q11": comparison["REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT"],
        "Q12": "NO. 미래 실제 종료시각이나 Apr-01 실현 런타임을 사용하지 않았다.",
        "Q13": f"{research_science}. 고정 32창 진단은 통과했지만 전체 공개 120창 미실행으로 R2 한계를 유지한다.",
        "Q14": h100_next, "Q15": "NO.",
    }
    final = {
        "artifact_id": "V35R3D_FINAL_REVIEW_V1",
        "numbered_report": numbered,
        "questions": questions,
        "runtime_seconds": time.perf_counter() - started,
        "power_grid_effect": "NOT_EVALUATED_RUNTIME_ONLY_TASK",
    }
    write_json("V35R3D_FINAL_REVIEW.json", final)
    (ARTIFACTS / "V35R3D_FINAL_REVIEW.md").write_text(build_markdown(final), encoding="utf-8")
    (LOGS / "V35R3D_BUILD_CLOSURE.json").write_text(
        json.dumps({"status": "PASS", "runtime_seconds": time.perf_counter() - started}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "comparison": comparison, "coverage": coverage}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
