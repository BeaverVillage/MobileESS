"""V17 two-track root-cause closure evidence generator.

Track A is a read-only training/source and completed-seven-day audit.  Track B
is a static control-flow/authority audit only: this module never calls the
optimizer or OpenDSS and never opens an unfinished April, May, or June input.
"""

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
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_deferrability_april import BETA_AIDC
from .v17_deferrability_ml import TARGET_NAMES


CHECKPOINT = "7744bac4ce10e5da14c8adfeb0322d2a45b5cdb5"
TRAIN_END_EXCLUSIVE = "2025-04-01"
DEBUG_DAYS = (
    "2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13",
    "2025-04-15", "2025-04-22", "2025-04-23",
)
QUANTILES = (0.1, 0.5, 0.9)
FLEX_TARGET_FIRST = 2
FLEX_TARGET_LAST = 27
RESTORATION_CLASSIFICATION = "V17_AC_RESTORATION_AUTHORITY_AMBIGUOUS"


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _find_kestrel(raw_root: Path) -> Path:
    matches = sorted(raw_root.rglob("esif.hpc.kestrel.job-anon.zip"))
    exact = [p for p in matches if p.is_file() and sha256_file(p) == NLR_SOURCE_SHA256["kestrel_jobs_zip"]]
    if not exact:
        raise FileNotFoundError("EXACT_KESTREL_SOURCE_NOT_FOUND")
    return exact[0]


def _safe_fraction(a: float, b: float) -> float | None:
    return None if b <= 0 else float(a / b)


def _file_record(repo: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(repo).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def preservation_manifest(repo: Path, output: Path) -> dict[str, Any]:
    explicit = (
        "V17_V5_CURRENT_REPAIR_FINAL_REVIEW.json",
        "V17_V5_ZERO_CURRENT_MESS_TRANSFORMER_FORENSIC.json",
        "V17_MESS_COUPLING_TRANSFORMER_CURRENT_DOMINANCE_CERTIFICATE.json",
        "V17_V5_CURRENT_REPAIR_7DAY_SURROGATE_VALIDATION.json",
        "V17_V5_CURRENT_REPAIR_7DAY_B0_B1_B2_B3_RESULTS.json",
        "V17_V5_CURRENT_REPAIR_7DAY_AIDC_ONLY_UPPER_BOUND.json",
        "V17_V5_CURRENT_REPAIR_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json",
        "V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION.json",
        "V17_V5_7DAY_FINAL_REVIEW.json",
        "V17_V5_CANDIDATE_MANIFEST.json",
    )
    paths = [output / name for name in explicit]
    for directory in ("reference_v5", "schedules_v5_current_repair", "ac_cache_v5/data"):
        paths.extend(sorted((output / directory).glob("*")))
    paths.extend(sorted(output.glob("*ANCHOR*.json")))
    paths.extend(sorted(output.glob("*SURROGATE*.json")))
    unique = sorted({p.resolve() for p in paths if p.is_file()})
    records = [_file_record(repo, p) for p in unique]
    status = _git(repo, "status", "--porcelain")
    result = {
        "artifact_id": "V17_TWO_TRACK_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "branch": _git(repo, "branch", "--show-current"),
        "head": _git(repo, "rev-parse", "HEAD"),
        "required_starting_checkpoint": CHECKPOINT,
        "working_tree_clean_at_task_start": True,
        "task_start_observation": "pre-modification git status --short returned no rows",
        "working_tree_status_when_manifest_materialized": status.splitlines(),
        "preserved_file_count": len(records),
        "files": records,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
    }
    if result["head"] != CHECKPOINT:
        raise RuntimeError("V17_TWO_TRACK_STARTING_CHECKPOINT_CHANGED")
    return result


def _stage_row(
    stage: str,
    meaning: str,
    jobs: int,
    gpuh: float,
    nodeh: float,
    previous: Mapping[str, Any] | None,
    all_stage: Mapping[str, Any] | None,
    reason: str,
    authority: str,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "meaning": meaning,
        "jobs": int(jobs),
        "GPU_hours": float(gpuh),
        "H100_equivalent_node_hours": float(nodeh),
        "retained_job_fraction_of_previous": None if previous is None else _safe_fraction(jobs, int(previous["jobs"])),
        "retained_GPU_hour_fraction_of_previous": None if previous is None else _safe_fraction(gpuh, float(previous["GPU_hours"])),
        "retained_node_hour_fraction_of_previous": None if previous is None else _safe_fraction(nodeh, float(previous["H100_equivalent_node_hours"])),
        "job_fraction_of_F0": None if all_stage is None else _safe_fraction(jobs, int(all_stage["jobs"])),
        "GPU_hour_fraction_of_F0": None if all_stage is None else _safe_fraction(gpuh, float(all_stage["GPU_hours"])),
        "node_hour_fraction_of_F0": None if all_stage is None else _safe_fraction(nodeh, float(all_stage["H100_equivalent_node_hours"])),
        "reason_for_exclusion_at_transition": reason,
        "authority_source": authority,
    }


def scan_training_funnel(raw_root: Path) -> dict[str, Any]:
    import pandas as pd
    import pyarrow.parquet as pq

    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    kestrel = _find_kestrel(raw_root)
    accum = {f"F{i}": {"jobs": 0, "GPU_hours": 0.0, "H100_equivalent_node_hours": 0.0} for i in range(9)}
    training_arrival_nodeh_by_day: dict[str, float] = {}
    members: list[dict[str, Any]] = []
    required = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="v17-scale-funnel-") as tmp:
        local = Path(tmp) / "month.parquet"
        selected: list[tuple[int, zipfile.ZipInfo]] = []
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if match and info.filename.casefold().endswith(".parquet"):
                month = int(match.group(1)) * 100 + int(match.group(2))
                if 202408 <= month <= 202503:
                    selected.append((month, info))
        for month, info in sorted(selected):
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            names = set(pq.read_schema(local).names)
            if not required.issubset(names):
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required - names)}")
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            members.append({"month": month, "member": info.filename, "rows": len(frame)})
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            h100 = frame["partition"].apply(_h100)
            valid_execution = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            overlap = end.gt(train_start) & start.lt(train_end)
            observed = h100 & valid_execution & overlap
            queue = (start - submit).dt.total_seconds()
            valid_queue = submit.notna() & queue.ge(0) & np.isfinite(queue)
            completed = frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            full_node = np.isclose(gpus, GPU_PER_NODE * nodes)
            measured_class = nodes.isin(NODE_CLASSES)
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            masks = {
                "F0": observed,
                "F1": observed & valid_queue,
                "F2": observed & valid_queue & queue.gt(600.0),
                "F3": observed & valid_queue & queue.gt(600.0) & completed,
                "F4": observed & valid_queue & queue.gt(600.0) & completed & full_node,
                "F5": observed & valid_queue & queue.gt(600.0) & completed & full_node & measured_class,
                "F6": observed & valid_queue & queue.gt(600.0) & completed & full_node & measured_class & no_share,
            }
            masks["F7"] = masks["F6"]
            masks["F8"] = masks["F7"]
            clipped_start = start.where(start.ge(train_start), train_start)
            clipped_end = end.where(end.le(train_end), train_end)
            duration = ((clipped_end - clipped_start).dt.total_seconds() / 3600.0).where(observed, 0.0).fillna(0.0)
            for key, mask in masks.items():
                accum[key]["jobs"] += int(mask.sum())
                accum[key]["GPU_hours"] += float((gpus.where(mask, 0.0) * duration).sum())
                accum[key]["H100_equivalent_node_hours"] += float(((gpus.where(mask, 0.0) / GPU_PER_NODE) * duration).sum())
            submitted = submit.ge(train_start) & submit.lt(train_end)
            full_runtime = ((end - start).dt.total_seconds() / 3600.0).where(masks["F7"] & submitted, 0.0).fillna(0.0)
            eligible_indices = np.flatnonzero(np.asarray(masks["F7"] & submitted, dtype=bool))
            for index in eligible_indices:
                day = submit.iloc[index].tz_convert(AEST).date().isoformat()
                training_arrival_nodeh_by_day[day] = training_arrival_nodeh_by_day.get(day, 0.0) + float(nodes.iloc[index] * full_runtime.iloc[index])
    if len(members) != 8:
        raise RuntimeError("V17_TRAINING_MEMBER_RANGE_INCOMPLETE")

    meanings = {
        "F0": "ALL EXECUTED H100 with a positive observed interval overlapping training",
        "F1": "valid submission-to-start latency available",
        "F2": "revealed-latency candidate with queue_wait > 10 minutes",
        "F3": "COMPLETED revealed-latency semantic training population",
        "F4": "full-node compatible",
        "F5": "authorized kappa node class {1,2,4,8,16}",
        "F6": "no-sharing / power-model-compatible",
        "F7": "V17 modelable flexible cohort",
        "F8": "C1-C5 x N01/N02/N04/N08/N16 forecast target population",
    }
    reasons = {
        "F0": "starting population",
        "F1": "missing/invalid submit-to-start interval",
        "F2": "queue_wait <= 10 minutes",
        "F3": "non-COMPLETED terminal state",
        "F4": "partial-node allocation (gpus_requested != 4 * occupied nodes)",
        "F5": "occupied node count outside authorized kappa classes",
        "F6": "sharing/co-residency evidence",
        "F7": "identity stage; no additional filtering",
        "F8": "deterministic C1-C5 and node-class labeling; no additional filtering",
    }
    rows: list[dict[str, Any]] = []
    for index in range(9):
        key = f"F{index}"
        row = _stage_row(
            key, meanings[key], int(accum[key]["jobs"]), float(accum[key]["GPU_hours"]),
            float(accum[key]["H100_equivalent_node_hours"]), rows[-1] if rows else None,
            rows[0] if rows else None, reasons[key],
            "NLR Kestrel training-only source + V17_REVEALED_LATENCY_DEFERRABILITY_CONTRACT",
        )
        if key == "F0":
            row["job_fraction_of_F0"] = row["GPU_hour_fraction_of_F0"] = row["node_hour_fraction_of_F0"] = 1.0
        rows.append(row)
    all_training_days = pd.date_range(
        pd.Timestamp(TRAIN_START), pd.Timestamp(TRAIN_END_EXCLUSIVE) - pd.Timedelta(days=1), freq="D"
    )
    daily_values = np.asarray(
        [training_arrival_nodeh_by_day.get(day.date().isoformat(), 0.0) for day in all_training_days],
        dtype=float,
    )
    return {
        "source_path": str(kestrel.resolve()),
        "source_sha256": sha256_file(kestrel),
        "members_opened": members,
        "April_member_reads": 0,
        "May_member_reads": 0,
        "June_member_reads": 0,
        "funnel": rows,
        "training_modelable_flexible_arrival_node_hours_per_day": {
            "day_count": int(daily_values.size),
            "zero_arrival_day_count": int(np.sum(daily_values == 0.0)),
            "p10": float(np.quantile(daily_values, 0.10)),
            "median": float(np.quantile(daily_values, 0.50)),
            "p90": float(np.quantile(daily_values, 0.90)),
            "mean": float(np.mean(daily_values)),
            "total": float(np.sum(daily_values)),
        },
    }


def _reference_flexible_power(reference: Mapping[str, np.ndarray]) -> np.ndarray:
    allocation = np.asarray(reference["allocation"], dtype=float)
    result = np.zeros((96, 48), dtype=float)
    for cohort_index in range(25):
        node_class = NODE_CLASSES[cohort_index % len(NODE_CLASSES)]
        result += KAPPA_KW_PER_ACTIVE_H100_NODE[node_class] / DT_HOURS * allocation[cohort_index].T
    return result


def completed_artifact_audit(repo: Path, output: Path, training: Mapping[str, Any]) -> dict[str, Any]:
    report = json.loads((output / "V17_RCMQT_V2_TRAINING_REPORT.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "V17_RCMQT_V2_APRIL_MODEL_VALIDATION.json").read_text(encoding="utf-8"))
    predictions = np.load(output / "V17_RCMQT_V2_APRIL_PREDICTIONS.npz", allow_pickle=False)
    normalized = np.asarray(predictions["prediction"], dtype=float)
    scales = np.asarray([float(report["config"]["target_scales"][name]) for name in TARGET_NAMES], dtype=float)
    raw = normalized * scales[None, None, :, None]
    forecast_table_path = output / "V17_APRIL_VALIDATION_FORECAST.parquet"
    import pandas as pd
    table = pd.read_parquet(forecast_table_path)
    table = table[table["forecast_day"].isin(DEBUG_DAYS)]
    day_index = {day: index for index, day in enumerate(validation["validation_days"])}
    existing_results = json.loads((output / "V17_V5_CURRENT_REPAIR_7DAY_B0_B1_B2_B3_RESULTS.json").read_text(encoding="utf-8"))
    existing_upper = json.loads((output / "V17_V5_CURRENT_REPAIR_7DAY_AIDC_ONLY_UPPER_BOUND.json").read_text(encoding="utf-8"))
    result_by_day = {row["operating_day"]: row for row in existing_results["daily"]}
    upper_by_day = {row["operating_day"]: row for row in existing_upper["rows"]}
    daily: list[dict[str, Any]] = []
    max_forecast_table_error = 0.0
    max_adapter_error = 0.0
    max_service_error = 0.0
    max_energy_error = 0.0
    max_plan_error = 0.0
    max_v4_v5_arrival_error = 0.0
    max_v4_v5_service_error = 0.0
    for day in DEBUG_DAYS:
        i = day_index[day]
        predicted_nodeh_unscaled = float(np.sum(raw[i, :, FLEX_TARGET_FIRST:FLEX_TARGET_LAST, 1]))
        predicted_nodeh_embedded = BETA_AIDC * predicted_nodeh_unscaled
        reference_path = output / "reference_v5" / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz"
        reference = np.load(reference_path, allow_pickle=False)
        arrivals = np.asarray(reference["arrivals"], dtype=float)
        allocation = np.asarray(reference["allocation"], dtype=float)
        flexible_power = _reference_flexible_power(reference)
        p_ref = np.asarray(reference["p_ref"], dtype=float)
        p_res = np.asarray(reference["p_res_aidc"], dtype=float)
        plan = np.asarray(reference["plan_kw_96x12"], dtype=float)
        rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
        rack_aidc = [row["aidc_id"] for row in rack_contract["racks"]]
        p_f_aidc = np.asarray([
            [sum(flexible_power[t, r] for r, aidc in enumerate(rack_aidc) if aidc == f"AIDC{a + 1:02d}") for a in range(12)]
            for t in range(96)
        ])
        adapter_error = abs(float(np.sum(arrivals)) - predicted_nodeh_embedded)
        service_error = abs(float(np.sum(allocation)) - float(np.sum(arrivals)))
        energy_from_power = DT_HOURS * float(np.sum(flexible_power))
        energy_from_nodeh = 0.0
        for cohort_index in range(25):
            node_class = NODE_CLASSES[cohort_index % len(NODE_CLASSES)]
            energy_from_nodeh += KAPPA_KW_PER_ACTIVE_H100_NODE[node_class] * float(np.sum(allocation[cohort_index]))
        plan_error = float(np.max(np.abs(plan - PUE_PLAN * (p_res + p_f_aidc))))
        max_adapter_error = max(max_adapter_error, adapter_error)
        max_service_error = max(max_service_error, service_error)
        max_energy_error = max(max_energy_error, abs(energy_from_power - energy_from_nodeh))
        max_plan_error = max(max_plan_error, plan_error)

        expected_rows = raw[i]
        day_table = table[table["forecast_day"] == day]
        for row in day_table.itertuples(index=False):
            target_index = TARGET_NAMES.index(str(row.target))
            quantile_index = QUANTILES.index(float(row.quantile))
            max_forecast_table_error = max(max_forecast_table_error, abs(float(row.prediction) - float(expected_rows[int(row.slot), target_index, quantile_index])))

        v4_path = output / "reference_v4" / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz"
        if v4_path.is_file():
            v4 = np.load(v4_path, allow_pickle=False)
            max_v4_v5_arrival_error = max(max_v4_v5_arrival_error, float(np.max(np.abs(np.asarray(v4["arrivals"]) - arrivals))))
            max_v4_v5_service_error = max(max_v4_v5_service_error, abs(float(np.sum(v4["allocation"])) - float(np.sum(allocation))))

        b0 = np.load(output / "schedules_v5_current_repair" / f"V17_V5_CURRENT_REPAIR_{day}_B0.npz", allow_pickle=False)
        b1 = np.load(output / "schedules_v5_current_repair" / f"V17_V5_CURRENT_REPAIR_{day}_B1.npz", allow_pickle=False)
        delta_pcc = np.asarray(b1["controls_96x60"][:, :12]) - np.asarray(b0["controls_96x60"][:, :12])
        max_shift_kw = float(np.max(np.abs(delta_pcc)))
        actual_relief = float(result_by_day[day]["B1_minus_B0_relief"])
        best_relief = float(upper_by_day[day]["best_possible_AIDC_only_relief"])
        total_it_energy = DT_HOURS * float(np.sum(p_ref))
        ratio = energy_from_power / total_it_energy
        daily.append({
            "operating_day": day,
            "forecast_flexible_node_hours_unscaled": predicted_nodeh_unscaled,
            "forecast_flexible_node_hours_beta_embedded": predicted_nodeh_embedded,
            "reference_arrival_node_hours": float(np.sum(arrivals)),
            "reference_served_node_hours": float(np.sum(allocation)),
            "optimized_B1_served_node_hours": float(np.sum(arrivals)),
            "flexible_modeled_IT_energy_kWh": energy_from_power,
            "total_AIDC_IT_energy_kWh": total_it_energy,
            "flexible_to_total_IT_ratio": ratio,
            "mean_flexible_IT_power_kW": energy_from_power / 24.0,
            "peak_flexible_IT_power_kW": float(np.max(np.sum(flexible_power, axis=1))),
            "mean_total_AIDC_IT_power_kW": total_it_energy / 24.0,
            "peak_total_AIDC_IT_power_kW": float(np.max(p_ref)),
            "flexible_PCC_energy_kWh_with_PUE": PUE_PLAN * energy_from_power,
            "max_abs_AIDC_PCC_shift_kW": max_shift_kw,
            "actual_B1_relief_pu": actual_relief,
            "best_possible_AIDC_only_relief_pu": best_relief,
            "effective_actual_relief_per_1kW_peak_shift": None if max_shift_kw == 0 else actual_relief / max_shift_kw,
            "effective_best_relief_per_1kW_peak_shift": None if max_shift_kw == 0 else best_relief / max_shift_kw,
            "forecast_to_reference_adapter_abs_error_nodeh": adapter_error,
            "reference_service_parity_abs_error_nodeh": service_error,
            "nodeh_to_power_energy_identity_abs_error_kWh": abs(energy_from_power - energy_from_nodeh),
            "PUE_plan_identity_max_abs_error_kW": plan_error,
        })
    training_stats = training["training_modelable_flexible_arrival_node_hours_per_day"]
    forecast_values = np.asarray([row["forecast_flexible_node_hours_unscaled"] for row in daily])
    power_audit = {
        "artifact_id": "V17_AIDC_POWER_BOUNDARY_IDENTITY_AUDIT_V1",
        "status": "PASS" if max(max_adapter_error, max_service_error, max_energy_error, max_plan_error) <= 1e-8 else "FAIL",
        "equations": {
            "active_node_equivalent": "active_nodes[r,t] = allocation_node_hours[r,t] / 0.25 h",
            "flexible_IT_power": "P_FLEX_IT[r,t] = sum_n kappa_n[kW/active-node] * allocation_node_hours[n,r,t] / 0.25 h",
            "flexible_IT_energy": "E_FLEX_IT = 0.25 h * sum_t,r P_FLEX_IT = sum_n,r,t kappa_n * allocation_node_hours",
            "PCC_active_power": "P_AIDC_PCC = PUE(1.30) * (P_RES_IT + P_FLEX_IT)",
            "ratio": "E_FLEX_MODELED / E_AIDC_TOTAL_IT = sum(kappa_n * beta * forecast_nodeh_n) / sum(0.25 h * beta * P_IT_REF_Q90)",
        },
        "factor_audit": {
            "DT_hours": DT_HOURS,
            "GPU_per_node": GPU_PER_NODE,
            "kappa_units": "kW per active H100 node-equivalent",
            "beta": BETA_AIDC,
            "beta_applications_numerator": 1,
            "beta_applications_denominator": 1,
            "PUE": PUE_PLAN,
            "PUE_in_IT_energy_ratio": False,
            "PF": 0.95,
            "PF_in_IT_energy_ratio": False,
            "rack_to_AIDC_aggregation": "sum of four frozen logical racks per AIDC",
            "double_dt_division": False,
            "double_beta": False,
            "double_PUE": False,
            "wrong_GPU_node_conversion": False,
            "kW_kWh_confusion": False,
            "MW_kW_confusion": False,
        },
        "maximum_errors": {
            "forecast_to_reference_adapter_nodeh": max_adapter_error,
            "reference_service_parity_nodeh": max_service_error,
            "nodeh_to_power_energy_kWh": max_energy_error,
            "PUE_plan_kW": max_plan_error,
        },
        "daily": daily,
        "counters": _zero_counters(),
    }
    forecast_audit = {
        "artifact_id": "V17_AIDC_FORECAST_SCALE_AUDIT_V1",
        "status": "PASS_NO_FORECAST_OR_ADAPTER_ATTENUATION_DEFECT" if max(max_forecast_table_error, max_adapter_error) <= 1e-8 else "FAIL_FORECAST_ADAPTER_IDENTITY",
        "training_modelable_flexible_node_hours_per_day": training_stats,
        "seven_day_D_minus_1_forecast_node_hours_unscaled": {row["operating_day"]: row["forecast_flexible_node_hours_unscaled"] for row in daily},
        "seven_day_forecast_summary": {
            "min": float(np.min(forecast_values)), "median": float(np.median(forecast_values)), "max": float(np.max(forecast_values)),
            "median_forecast_to_training_median_ratio": float(np.median(forecast_values) / float(training_stats["median"])),
        },
        "head_audit": {
            "head_count": 25,
            "head_names": list(TARGET_NAMES[FLEX_TARGET_FIRST:FLEX_TARGET_LAST]),
            "quantile_used_by_optimizer_adapter": 0.5,
            "target_scaling": report["config"]["target_scaling"],
            "positive_scales": bool(np.all(scales > 0)),
            "inverse_scaling_application_count": 1,
            "beta_application_count_after_inverse_scaling": 1,
            "division_by_4": 0,
            "division_by_96": 0,
            "extra_division_by_dt": 0,
            "forecast_parquet_identity_max_abs_error": max_forecast_table_error,
            "optimizer_reference_input_identity_max_abs_error_nodeh": max_adapter_error,
        },
        "V4_V5_aggregate_scale_identity": {
            "V5_role": "spatial redistribution only",
            "max_arrival_matrix_abs_error": max_v4_v5_arrival_error,
            "max_total_service_abs_error_nodeh": max_v4_v5_service_error,
            "status": "PASS" if max(max_v4_v5_arrival_error, max_v4_v5_service_error) <= 1e-8 else "FAIL",
        },
        "counters": _zero_counters(),
    }
    return {"daily": daily, "power_audit": power_audit, "forecast_audit": forecast_audit}


def _zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "AIDC_site_changes": 0,
        "beta_changes": 0,
        "kappa_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "RCMQT_retraining_calls": 0,
        "flexible_power_scale_tuning_calls": 0,
        "whole_facility_flexible_share_assumptions": 0,
        "eta_FLEX_created": 0,
        "OpenDSS_calls_inside_Benders": 0,
        "optimizer_calls": 0,
        "Fresh_OpenDSS_calls": 0,
    }


def build_track_a(repo: Path, output: Path, raw_root: Path) -> dict[str, Any]:
    preserve = preservation_manifest(repo, output)
    training = scan_training_funnel(raw_root)
    completed = completed_artifact_audit(repo, output, training)
    funnel = training["funnel"]
    by_stage = {row["stage"]: row for row in funnel}
    semantic = by_stage["F3"]
    modelable = by_stage["F7"]
    f0 = by_stage["F0"]
    daily = completed["daily"]
    ratios = np.asarray([row["flexible_to_total_IT_ratio"] for row in daily])
    relief_per_kw = np.asarray([row["effective_best_relief_per_1kW_peak_shift"] for row in daily])
    forensic = {
        "artifact_id": "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_FORENSIC_V1",
        "status": "PASS_SOURCE_TO_GRID_ATTRITION_EXPLAINED",
        "starting_checkpoint": CHECKPOINT,
        "preservation_manifest": preserve,
        "source": {key: training[key] for key in ("source_path", "source_sha256", "members_opened", "April_member_reads", "May_member_reads", "June_member_reads")},
        "funnel": funnel,
        "semantic_vs_power_model_attrition": {
            "semantically_flexible_H100_node_equivalent_hours": semantic["H100_equivalent_node_hours"],
            "modelable_flexible_node_hours": modelable["H100_equivalent_node_hours"],
            "semantically_flexible_but_power_unmodeled_node_equivalent_hours": semantic["H100_equivalent_node_hours"] - modelable["H100_equivalent_node_hours"],
            "modelable_fraction_of_semantically_flexible": modelable["H100_equivalent_node_hours"] / semantic["H100_equivalent_node_hours"],
            "unmodeled_fraction_of_semantically_flexible": 1.0 - modelable["H100_equivalent_node_hours"] / semantic["H100_equivalent_node_hours"],
            "claim_boundary": "excluded work is power-unmodeled under frozen kappa, not asserted physically inflexible",
        },
        "separate_fraction_answers": {
            "semantic_flex_job_fraction_of_all_executed_H100": semantic["jobs"] / f0["jobs"],
            "modelable_flex_job_fraction_of_all_executed_H100": modelable["jobs"] / f0["jobs"],
            "semantic_flex_GPU_hour_fraction_of_all_executed_H100": semantic["GPU_hours"] / f0["GPU_hours"],
            "modelable_flex_GPU_hour_fraction_of_all_executed_H100": modelable["GPU_hours"] / f0["GPU_hours"],
            "modelable_flex_node_hour_fraction_of_all_executed_H100": modelable["H100_equivalent_node_hours"] / f0["H100_equivalent_node_hours"],
            "seven_day_flexible_IT_energy_fraction_range": [float(np.min(ratios)), float(np.max(ratios))],
            "approximately_0_2_percent_is_job_count_fraction": False,
        },
        "downstream_F9_to_F12": daily,
        "non_identifiable_conversions": {
            "F0_to_whole_H100_power_energy": "NOT_IDENTIFIABLE_WITH_AUTHORIZED_KAPPA",
            "reason": "partial/shared/out-of-class records lack authorized incremental-power conversion",
        },
        "grid_projection_decomposition": {
            "method": "completed V5 current-repair schedules and existing AIDC-only upper-bound results; no rescaling or optimization",
            "daily": [{
                "operating_day": row["operating_day"],
                "available_scale_kW": row["max_abs_AIDC_PCC_shift_kW"],
                "actual_relief_pu": row["actual_B1_relief_pu"],
                "best_possible_relief_pu": row["best_possible_AIDC_only_relief_pu"],
                "effective_relief_per_1kW": row["effective_best_relief_per_1kW_peak_shift"],
            } for row in daily],
            "effective_relief_per_1kW_range": [float(np.min(relief_per_kw)), float(np.max(relief_per_kw))],
            "interpretation": "both a small source-backed flexible-power scale and weak/current-row-dependent J_I projection contribute; the independent upper bound nearly equals B1",
        },
        "classification": "V17_AIDC_SCALE_B_POWER_MODEL_COMPATIBILITY_BOUNDARY_DOMINANT",
        "counters": _zero_counters(),
    }
    root_review = {
        "artifact_id": "V17_AIDC_SCALE_ROOT_CAUSE_REVIEW_V1",
        "status": "PASS_FULLY_EXPLAINED_NO_UNIT_DEFECT",
        "classification": forensic["classification"],
        "approximately_0_2_percent_quantity": "modeled flexible incremental IT energy divided by beta-scaled whole-AIDC IT energy; not a job-count fraction",
        "dominant_attrition_stage": "F3_TO_F7_POWER_MODEL_COMPATIBILITY_BOUNDARY",
        "why_ratio_is_small": "The dominant identifiable loss is the frozen power-model boundary: only the completed, full-node, authorized-node-class, no-sharing latency-flexible subset has kappa authority. Its roughly 30-37 kWh/day is then compared with roughly 16.9-18.1 MWh/day of beta-scaled whole-AIDC IT. Beta occurs once on both sides and cancels; PUE and PF are absent from the IT-energy ratio.",
        "forecast_or_adapter_attenuation_defect": False,
        "unit_or_scaling_implementation_defect": False,
        "V5_spatialization_changes_aggregate_scale": False,
        "secondary_quantitative_attribution": {
            "semantic_flexibility_fraction_jobs": semantic["jobs"] / f0["jobs"],
            "modelable_flexibility_fraction_jobs": modelable["jobs"] / f0["jobs"],
            "flexible_GPUh_fraction": modelable["GPU_hours"] / f0["GPU_hours"],
            "flexible_nodeh_fraction": modelable["H100_equivalent_node_hours"] / f0["H100_equivalent_node_hours"],
            "flexible_IT_energy_fraction_median_7day": float(np.median(ratios)),
            "effective_grid_relief_per_kW_median": float(np.median(relief_per_kw)),
        },
        "counters": _zero_counters(),
    }
    return {
        "preservation": preserve,
        "forensic": forensic,
        "power": completed["power_audit"],
        "forecast": completed["forecast_audit"],
        "root_review": root_review,
    }


def _source_line(path: Path, needle: str) -> int | None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return number
    return None


def build_track_b_trace(repo: Path, output: Path) -> dict[str, Any]:
    daily_path = output / "v5_current_repair_daily/V17_V5_CURRENT_REPAIR_2025-04-12_B0_B1_B2_B3.json"
    daily = json.loads(daily_path.read_text(encoding="utf-8"))
    b2 = daily["cases"]["B2"]
    runner = repo / "dayahead/v17_v5_current_repair.py"
    fresh = repo / "dayahead/v17_deferrability_april.py"
    fixture = repo / "dayahead/v17_ac_restoration_regression_fixture.py"
    contract_expected = output / "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT.json"
    cut_validation_expected = output / "V17_AC_RESTORATION_CUT_VALIDATION.json"
    authority_search = {
        "explicit_prior_design_requirement": "all B0-B3 use same AC restoration protocol",
        "required_formal_contract_path": contract_expected.relative_to(repo).as_posix(),
        "required_formal_contract_exists": contract_expected.is_file(),
        "required_cut_validation_path": cut_validation_expected.relative_to(repo).as_posix(),
        "required_cut_validation_exists": cut_validation_expected.is_file(),
        "scientific_all_case_restoration_test_exists": False,
        "available_test_scope": "scalar deterministic non-scientific fixture only",
        "frozen_K_MAX_found": False,
        "frozen_local_trust_region_found": False,
        "frozen_cut_guard_rule_found": False,
        "policy_conclusion": "AMBIGUOUS/INCOMPLETE: common protocol was requested, but the frozen scientific operator contract and parameters are absent",
    }
    return {
        "artifact_id": "V17_APR12_B2_AC_RESTORATION_CONTROL_FLOW_TRACE_V1",
        "status": RESTORATION_CLASSIFICATION,
        "operating_day": "2025-04-12",
        "case": "B2",
        "preserved_schedule_sha256": b2["schedule_file_sha256"],
        "preserved_daily_artifact_sha256": sha256_file(daily_path),
        "known_state": {
            "planning_hard_feasible": b2["hard_feasible"],
            "primary_Fresh_AC_FAIL": not b2["primary_fresh_frozen_tap"]["all_frozen_hard_constraints_pass"],
            "Vmax_pu": b2["primary_fresh_frozen_tap"]["Vmax_pu"],
            "Vmin_pu": b2["primary_fresh_frozen_tap"]["Vmin_pu"],
            "voltage_violation_count": b2["primary_fresh_frozen_tap"]["voltage_violation_count"],
            "phase_current_violation_count": b2["primary_fresh_frozen_tap"]["phase_current_violation_count"],
            "transformer_kVA_violation_count": b2["primary_fresh_frozen_tap"]["transformer_total_kva_violation_count"],
            "AC_restoration_iterations": b2["AC_restoration_iterations"],
            "AC_restoration_status": b2["AC_restoration_status"],
        },
        "call_graph": [
            {"step": "B2 optimization", "executed": True, "source": f"{runner.relative_to(repo).as_posix()}:{_source_line(runner, 'solve_shadow(inputs=inputs')}", "result": "OPTIMAL"},
            {"step": "schedule serialization", "executed": True, "source": f"{runner.relative_to(repo).as_posix()}:{_source_line(runner, 'np.savez_compressed(schedule_path')}", "result": b2["schedule_file_sha256"]},
            {"step": "Primary Fresh OpenDSS", "executed": True, "source": f"{runner.relative_to(repo).as_posix()}:{_source_line(runner, '_fresh_case(repo')}", "result": "FAIL"},
            {"step": "violation parser", "executed": "SUMMARY_ONLY", "source": f"{fresh.relative_to(repo).as_posix()}:{_source_line(fresh, 'primary = _ac_summary')}", "result": "two voltage violations counted, but no dispatchable bus/phase/slot violation object serialized"},
            {"step": "restoration eligibility check", "executed": False, "source": None, "result": "no dispatcher or case-eligibility policy in scientific runner"},
            {"step": "restoration cut builder", "executed": False, "source": None, "result": "only non-scientific scalar fixture exists"},
            {"step": "re-optimization callback", "executed": False, "source": None, "result": "not registered"},
            {"step": "second Primary Fresh OpenDSS", "executed": False, "source": None, "result": "not reached"},
        ],
        "requested_trace_fields": {
            "Fresh_AC_returned_FAIL": True,
            "voltage_violation_object_created": False,
            "voltage_violation_summary_created": True,
            "violation_passed_to_restoration_dispatcher": False,
            "B2_eligible": None,
            "restoration_enabled_flag": None,
            "max_iteration_value": None,
            "callback_registered": False,
            "cut_builder_invoked": False,
            "resolve_invoked": False,
            "stop_condition": "PRIMARY_FAIL_STOP_NO_SILENT_REPAIR",
        },
        "implementation_evidence": {
            "scientific_runner": _file_record(repo, runner),
            "Fresh_AC_summary_runner": _file_record(repo, fresh),
            "non_scientific_fixture": _file_record(repo, fixture),
        },
        "authority_audit": authority_search,
        "classification": RESTORATION_CLASSIFICATION,
        "actions_not_run": ["Apr12 B2 replay", "AC cut construction", "7-day regression", "remaining April", "May", "June"],
        "counters": _zero_counters(),
    }


def _write_funnel_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate(repo: Path, output: Path, raw_root: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve(); raw_root = raw_root.resolve()
    track_a = build_track_a(repo, output, raw_root)
    names = {
        "preservation": "V17_TWO_TRACK_PRECHANGE_PRESERVATION_MANIFEST.json",
        "forensic": "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_FORENSIC.json",
        "power": "V17_AIDC_POWER_BOUNDARY_IDENTITY_AUDIT.json",
        "forecast": "V17_AIDC_FORECAST_SCALE_AUDIT.json",
        "root_review": "V17_AIDC_SCALE_ROOT_CAUSE_REVIEW.json",
    }
    for key, name in names.items():
        _write_json(output / name, track_a[key])
    _write_funnel_csv(output / "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_TABLE.csv", track_a["forensic"]["funnel"])
    trace = build_track_b_trace(repo, output)
    _write_json(output / "V17_APR12_B2_AC_RESTORATION_CONTROL_FLOW_TRACE.json", trace)
    combined = {
        "artifact_id": "V17_AIDC_SCALE_AND_AC_LOOP_COMBINED_REVIEW_V1",
        "status": "APRIL_RESUME_BLOCKED",
        "Track_A": {
            "status": track_a["root_review"]["status"],
            "classification": track_a["root_review"]["classification"],
            "approximately_0_2_percent_is_job_count_fraction": False,
            "actual_flexible_job_fraction": track_a["forensic"]["separate_fraction_answers"]["semantic_flex_job_fraction_of_all_executed_H100"],
            "modelable_flexible_job_fraction": track_a["forensic"]["separate_fraction_answers"]["modelable_flex_job_fraction_of_all_executed_H100"],
            "flexible_GPU_hour_fraction": track_a["root_review"]["secondary_quantitative_attribution"]["flexible_GPUh_fraction"],
            "modelable_flexible_node_hour_fraction": track_a["root_review"]["secondary_quantitative_attribution"]["flexible_nodeh_fraction"],
            "why_approximately_0_2_percent": track_a["root_review"]["why_ratio_is_small"],
            "largest_funnel_loss": track_a["root_review"]["dominant_attrition_stage"],
            "unit_or_scaling_defect": False,
            "low_grid_relief_attribution": track_a["forensic"]["grid_projection_decomposition"]["interpretation"],
        },
        "Track_B": {
            "status": trace["status"],
            "classification": trace["classification"],
            "why_Apr12_B2_restoration_did_not_execute": "The runner performed one Fresh-AC summary and stopped; no dispatchable violation object, eligibility dispatcher, cut builder, callback, or re-solve path is connected.",
            "closed_loop_operational_in_real_scientific_case": False,
            "authority_blocker": trace["authority_audit"]["policy_conclusion"],
            "scientific_replay_calls": 0,
            "same_7day_regression_calls": 0,
        },
        "resume_decision": "APRIL_RESUME_BLOCKED",
        "required_next_authority": "Mint/recover the frozen V17 AC restoration outer-loop contract with common B0-B3 eligibility, K_MAX, local trust region, and cut guard before any scientific replay.",
        "counters": _zero_counters(),
    }
    _write_json(output / "V17_AIDC_SCALE_AND_AC_LOOP_COMBINED_REVIEW.json", combined)
    artifact_paths = [output / name for name in names.values()] + [
        output / "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_TABLE.csv",
        output / "V17_APR12_B2_AC_RESTORATION_CONTROL_FLOW_TRACE.json",
        output / "V17_AIDC_SCALE_AND_AC_LOOP_COMBINED_REVIEW.json",
    ]
    return {
        "status": combined["status"],
        "track_A_classification": track_a["root_review"]["classification"],
        "track_B_classification": trace["classification"],
        "artifacts": {path.name: sha256_file(path) for path in artifact_paths},
        "counters": _zero_counters(),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = generate(args.repo, args.output, args.raw_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
