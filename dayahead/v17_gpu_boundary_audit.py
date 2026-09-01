"""Training-only V17 Kestrel H100 subsystem-boundary audit.

The audit reconstructs H100 usage from the frozen Kestrel archive while
opening only 2024-08 through 2025-03 members.  It does not import ESIF,
forecast, optimizer, OpenDSS, April-result, May, or June execution paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .reproduce_nlr_authority import object_empty


STARTING_CHECKPOINT = "2d68395171d05b899ba4d6040f5f8e28ca1fb3bd"
HISTORICAL_SHARE_CLASSIFICATION = (
    "V17_SHARE_AUTH_C_CAPRARA_SCOPE_MISMATCH_OTHER_SOURCE_NOT_FOUND"
)
HISTORICAL_ADMISSIBILITY_SHA256 = (
    "350dee04bda2ef405223515aff85f54d2c1ee568cff69d106984fbe43cdc8015"
)
HISTORICAL_GAP_RESOLUTION_SHA256 = (
    "a318f99fd9ee889e483dbef033dfed23dc388842a7b18f780e3d7480371d526c"
)
HISTORICAL_ARTIFACTS: Mapping[str, str] = {
    "dayahead/artifacts/v17_candidate/V17_EXTERNAL_SCI_FLEXIBLE_SHARE_ADMISSIBILITY.json": (
        HISTORICAL_ADMISSIBILITY_SHA256
    ),
    "dayahead/artifacts/v17_candidate/V17_FLEXIBLE_SHARE_AUTHORITY_GAP_RESOLUTION.json": (
        HISTORICAL_GAP_RESOLUTION_SHA256
    ),
}

FINAL_CLASSIFICATION = "V17_GPU_BOUNDARY_D_FLEX_COHORT_SEMANTICS_DEFECT"
NEXT_DECISION = "V17_GPU_BOUNDARY_REDESIGN_REQUIRED"
FLEX_COHORT_CLASSIFICATION = "FLEX_COHORT_SEMANTICS_DEFECT"

TRAIN_END_EXCLUSIVE = "2025-04-01"
MIN_MONTH = 202408
MAX_MONTH = 202503
CAPRARA_GPU_SIDE_FRACTION = 0.205


def _h100(value: object) -> bool:
    return any(
        token.strip().casefold().startswith("gpu-h100")
        for token in str(value).split(",")
    )


def _find_exact_kestrel(raw_root: Path) -> Path:
    matches = sorted(raw_root.rglob("esif.hpc.kestrel.job-anon.zip"))
    exact = [
        path
        for path in matches
        if path.is_file() and sha256_file(path) == NLR_SOURCE_SHA256["kestrel_jobs_zip"]
    ]
    if not exact:
        raise FileNotFoundError("EXACT_KESTREL_SOURCE_NOT_FOUND")
    return exact[0]


def _safe_fraction(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        raise RuntimeError("INVALID_H100_SHARE_DENOMINATOR")
    value = numerator / denominator
    if value < -1e-12 or value > 1.0 + 1e-12:
        raise RuntimeError("INVALID_H100_SHARE_RANGE")
    return float(value)


def verify_historical_artifacts(repo_root: Path) -> dict[str, str]:
    """Prove the rejected whole-IT-share evidence remains byte-identical."""

    observed: dict[str, str] = {}
    for relative_path, expected_sha256 in HISTORICAL_ARTIFACTS.items():
        path = repo_root / relative_path
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"HISTORICAL_V17_ARTIFACT_CHANGED:{relative_path}:"
                f"{actual_sha256}!={expected_sha256}"
            )
        observed[relative_path] = actual_sha256
    return observed


def _quantiles(values: Sequence[float]) -> dict[str, float | None]:
    import numpy as np

    if not values:
        return {"min": None, "p50": None, "p95": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {
        "min": float(array.min()),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "max": float(array.max()),
    }


def _zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "V16_3_historical_changes": 0,
        "beta_changes": 0,
        "kappa_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "AIDC_site_changes": 0,
        "whole_facility_flexible_share_assumptions": 0,
        "effect_selected_scaling_values": 0,
        "arbitrary_clipping_calls": 0,
        "OpenDSS_calls_inside_Benders": 0,
        "April_B0_B1_B2_B3_calls": 0,
        "April_result_reads": 0,
        "AC_surrogate_revalidation_calls": 0,
        "AC_restoration_calls": 0,
        "decomposition_regression_calls": 0,
        "RC_MQT_retraining_calls": 0,
    }


def audit_training_only(raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, Any]:
    """Reconstruct the H100 denominator and audit current W_F semantics."""

    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    kestrel = _find_exact_kestrel(raw_root)
    datacard = kestrel.parent / "datacard.md"
    if not datacard.is_file():
        raise FileNotFoundError("KESTREL_DATACARD_NOT_FOUND")
    required = {
        "partition",
        "state_simple",
        "submit_time",
        "start_time",
        "end_time",
        "gpu_nodes_occupied",
        "gpus_requested",
        "shared_job_count",
        "nodes_shared",
        "jobs_shared",
        "queue_wait",
        "wallclock_req",
    }

    members_opened: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    source_schema_timezones: set[str] = set()
    total_executed_job_count = 0
    completed_gref_job_count = 0
    eligible_active_job_count = 0
    eligible_arrival_job_count = 0
    total_gpu_hours = 0.0
    total_equivalent_node_hours = 0.0
    completed_gpu_hours = 0.0
    completed_equivalent_node_hours = 0.0
    flexible_gpu_hours = 0.0
    flexible_active_node_hours = 0.0
    flexible_arrival_node_hours = 0.0
    flexible_incremental_energy_kwh = 0.0
    eligible_active_node_hours_wait_le_20s = 0.0
    eligible_active_node_hours_wait_le_10m = 0.0
    eligible_active_node_hours_wait_gt_10m = 0.0
    eligible_wait_seconds: list[float] = []
    excluded_submitted_counts: Counter[str] = Counter()
    excluded_active_gpu_hours: Counter[str] = Counter()

    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(
        prefix="v17-gpu-boundary-training-"
    ) as temporary:
        local = Path(temporary) / "month.parquet"
        selected: list[tuple[int, zipfile.ZipInfo]] = []
        for info in archive.infolist():
            if not info.filename.casefold().endswith(".parquet"):
                continue
            match = re.search(
                r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/")
            )
            if not match:
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if MIN_MONTH <= month <= MAX_MONTH:
                selected.append((month, info))
        for month, info in sorted(selected):
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = pq.read_schema(local)
            names = set(schema.names)
            if not required.issubset(names):
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required - names)}")
            for field_name in ("submit_time", "start_time", "end_time"):
                source_schema_timezones.add(str(schema.field(field_name).type))
            members_opened.append(
                {
                    "month": month,
                    "member": info.filename,
                    "uncompressed_bytes": info.file_size,
                }
            )
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            is_h100 = frame["partition"].apply(_h100)
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            submitted_training = is_h100 & submit.ge(train_start) & submit.lt(train_end)
            state_counts.update(
                frame.loc[submitted_training, "state_simple"].astype(str).str.upper().tolist()
            )

            has_executed_interval = (
                is_h100
                & start.notna()
                & end.notna()
                & end.gt(start)
                & nodes.gt(0)
                & gpus.gt(0)
                & end.gt(train_start)
                & start.lt(train_end)
            )
            completed = frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            gref_valid = has_executed_interval & completed
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            full_node = np.isclose(gpus, GPU_PER_NODE * nodes)
            measured_class = nodes.isin(NODE_CLASSES)
            current_eligible = gref_valid & full_node & measured_class & no_share

            clipped_start = start.where(start.ge(train_start), train_start)
            clipped_end = end.where(end.le(train_end), train_end)
            duration_hours = (clipped_end - clipped_start).dt.total_seconds() / 3600.0
            duration_hours = duration_hours.where(has_executed_interval, 0.0).fillna(0.0)

            total_executed_job_count += int(has_executed_interval.sum())
            completed_gref_job_count += int(gref_valid.sum())
            eligible_active_job_count += int(current_eligible.sum())
            total_gpu_hours += float((gpus.where(has_executed_interval, 0.0) * duration_hours).sum())
            total_equivalent_node_hours += float(
                ((gpus.where(has_executed_interval, 0.0) / GPU_PER_NODE) * duration_hours).sum()
            )
            completed_gpu_hours += float((gpus.where(gref_valid, 0.0) * duration_hours).sum())
            completed_equivalent_node_hours += float(
                ((gpus.where(gref_valid, 0.0) / GPU_PER_NODE) * duration_hours).sum()
            )
            flexible_gpu_hours += float((gpus.where(current_eligible, 0.0) * duration_hours).sum())
            flexible_active_node_hours += float(
                (nodes.where(current_eligible, 0.0) * duration_hours).sum()
            )

            eligible_arrival = current_eligible & submit.ge(train_start) & submit.lt(train_end)
            full_runtime_hours = (end - start).dt.total_seconds() / 3600.0
            eligible_arrival_job_count += int(eligible_arrival.sum())
            flexible_arrival_node_hours += float(
                (nodes.where(eligible_arrival, 0.0) * full_runtime_hours.where(eligible_arrival, 0.0)).sum()
            )

            for node_class, kappa in KAPPA_KW_PER_ACTIVE_H100_NODE.items():
                mask = current_eligible & nodes.eq(node_class)
                flexible_incremental_energy_kwh += float(
                    (kappa * nodes.where(mask, 0.0) * duration_hours).sum()
                )

            queue_seconds = (start - submit).dt.total_seconds()
            eligible_queue = queue_seconds.where(current_eligible).dropna()
            eligible_wait_seconds.extend(float(value) for value in eligible_queue.tolist())
            eligible_active_node_hours_wait_le_20s += float(
                (nodes.where(current_eligible & queue_seconds.le(20.0), 0.0) * duration_hours).sum()
            )
            eligible_active_node_hours_wait_le_10m += float(
                (nodes.where(current_eligible & queue_seconds.le(600.0), 0.0) * duration_hours).sum()
            )
            eligible_active_node_hours_wait_gt_10m += float(
                (nodes.where(current_eligible & queue_seconds.gt(600.0), 0.0) * duration_hours).sum()
            )

            submitted_completed_valid = (
                is_h100
                & submit.ge(train_start)
                & submit.lt(train_end)
                & completed
                & start.notna()
                & end.notna()
                & end.gt(start)
                & nodes.gt(0)
                & gpus.gt(0)
            )
            exclusion_masks: Mapping[str, object] = {
                "not_completed": submitted_training & ~completed,
                "invalid_or_missing_execution_interval": submitted_training
                & completed
                & ~(start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)),
                "not_full_node_allocation": submitted_completed_valid & ~full_node,
                "node_class_outside_1_2_4_8_16": submitted_completed_valid & ~measured_class,
                "sharing_evidence_present": submitted_completed_valid & ~no_share,
            }
            for reason, mask in exclusion_masks.items():
                excluded_submitted_counts[reason] += int(mask.sum())
                active_mask = mask & has_executed_interval
                excluded_active_gpu_hours[reason] += float(
                    (gpus.where(active_mask, 0.0) * duration_hours).sum()
                )

    if not members_opened or max(item["month"] for item in members_opened) != MAX_MONTH:
        raise RuntimeError("TRAINING_MEMBER_RANGE_INCOMPLETE")
    if total_gpu_hours <= 0 or completed_gpu_hours <= 0 or flexible_gpu_hours <= 0:
        raise RuntimeError("TRAINING_H100_HOURS_EMPTY")
    if not math.isclose(
        flexible_gpu_hours / GPU_PER_NODE,
        flexible_active_node_hours,
        rel_tol=0.0,
        abs_tol=1e-8,
    ):
        raise RuntimeError("FLEXIBLE_GPU_TO_NODE_IDENTITY_FAILED")

    f_total = _safe_fraction(flexible_gpu_hours, total_gpu_hours)
    f_completed_gref = _safe_fraction(flexible_gpu_hours, completed_gpu_hours)
    low_wait_fraction = _safe_fraction(
        eligible_active_node_hours_wait_le_10m, flexible_active_node_hours
    )
    high_wait_fraction = _safe_fraction(
        eligible_active_node_hours_wait_gt_10m, flexible_active_node_hours
    )
    if low_wait_fraction <= 0:
        raise RuntimeError("EXPECTED_LOW_WAIT_ELIGIBLE_EVIDENCE_MISSING")

    result: dict[str, Any] = {
        "artifact_id": "V17_GPU_SUBSYSTEM_BOUNDARY_TRAINING_AUDIT_V1",
        "status": "FAIL_CLOSED_FLEX_COHORT_SEMANTICS_DEFECT",
        "checkpoint": {
            "branch": "codex/dayahead-aidc-joint-v1",
            "starting_checkpoint": STARTING_CHECKPOINT,
            "historical_whole_IT_share_classification_preserved": HISTORICAL_SHARE_CLASSIFICATION,
            "historical_admissibility_sha256": HISTORICAL_ADMISSIBILITY_SHA256,
            "historical_gap_resolution_sha256": HISTORICAL_GAP_RESOLUTION_SHA256,
            "historical_artifacts_modified": False,
        },
        "source": {
            "system": "NLR Kestrel H100 Slurm job archive",
            "path": str(kestrel.resolve()),
            "sha256": sha256_file(kestrel),
            "datacard_path": str(datacard.resolve()),
            "datacard_sha256": sha256_file(datacard),
            "source_scope": "KESTREL_ONLY_GPU_H100_PARTITIONS",
            "Eagle_rows": 0,
            "non_H100_rows_in_denominator": 0,
            "members_opened": members_opened,
            "minimum_member_month": min(item["month"] for item in members_opened),
            "maximum_member_month": max(item["month"] for item in members_opened),
            "April_member_reads": 0,
            "May_member_reads": 0,
            "June_member_reads": 0,
        },
        "time_contract": {
            "training_start_AEST_fixed": pd.Timestamp(TRAIN_START, tz=AEST).isoformat(),
            "training_end_exclusive_AEST_fixed": pd.Timestamp(
                TRAIN_END_EXCLUSIVE, tz=AEST
            ).isoformat(),
            "training_start_UTC": train_start.isoformat(),
            "training_end_exclusive_UTC": train_end.isoformat(),
            "source_datacard_timezone": "America/Denver with exported UTC offsets",
            "source_schema_timestamp_types": sorted(source_schema_timezones),
            "alignment_rule": "PARSE_OFFSET_AWARE_TO_UTC_THEN_CLIP_TO_FROZEN_AEST_TRAINING_INTERVAL",
            "numerator_denominator_same_interval": True,
        },
        "denominator_authority_gate": {
            "status": "PASS_NODE_EQUIVALENT_DENOMINATOR_IDENTIFIABLE",
            "exact_existing_G_REF_rule": (
                "Integral of gpus_requested/4 for valid COMPLETED H100 jobs "
                "with positive execution intervals."
            ),
            "exact_total_executed_H100_rule": (
                "Integral of gpus_requested/4 for all H100 records with positive "
                "observed execution intervals, independent of terminal state."
            ),
            "total_executed_H100_jobs_overlapping_training": total_executed_job_count,
            "existing_G_REF_completed_jobs_overlapping_training": completed_gref_job_count,
            "total_requested_H100_GPU_hours": total_gpu_hours,
            "total_H100_equivalent_node_hours": total_equivalent_node_hours,
            "existing_G_REF_requested_GPU_hours": completed_gpu_hours,
            "existing_G_REF_equivalent_node_hours": completed_equivalent_node_hours,
            "GPU_per_node_identity": GPU_PER_NODE,
            "GPU_per_node_application_count": 1,
            "measured_not_forecast": True,
            "same_Kestrel_H100_population": True,
            "same_timezone_and_training_interval": True,
        },
        "same_source_candidate_share": {
            "accepted_as_scientific_flexible_share": False,
            "qualified_flexible_jobs_active_in_training": eligible_active_job_count,
            "qualified_flexible_jobs_submitted_in_training": eligible_arrival_job_count,
            "qualified_flexible_requested_GPU_hours": flexible_gpu_hours,
            "qualified_flexible_active_node_hours": flexible_active_node_hours,
            "qualified_W_F_arrival_node_hours": flexible_arrival_node_hours,
            "f_H100_FLEX_NODEH_all_executed_H100": f_total,
            "f_H100_FLEX_NODEH_existing_completed_G_REF": f_completed_gref,
            "node_hour_GPU_hour_identity_error": abs(
                flexible_gpu_hours / GPU_PER_NODE - flexible_active_node_hours
            ),
            "energy_weighted_candidate": None,
            "energy_weighted_status": "NOT_IDENTIFIABLE_FOR_TOTAL_H100_WITH_FROZEN_KAPPA",
            "energy_weighted_failure_reason": (
                "The total H100 population contains shared/partial-GPU or "
                "out-of-class records; frozen kappa_n is defined only for full-node "
                "classes {1,2,4,8,16}. No average kappa or partial-GPU conversion is authorized."
            ),
            "qualified_subset_incremental_energy_kWh": flexible_incremental_energy_kwh,
        },
        "flexible_cohort_semantics_audit": {
            "classification": FLEX_COHORT_CLASSIFICATION,
            "current_rule": (
                "H100 + COMPLETED + valid runtime + gpus_requested=4*gpu_nodes_occupied "
                "+ node class in {1,2,4,8,16} + no sharing evidence"
            ),
            "queue_wait_threshold_in_current_rule": None,
            "deadline_or_slack_threshold_in_current_rule": None,
            "SLA_preservation_test_in_current_rule": None,
            "eligible_queue_wait_seconds": _quantiles(eligible_wait_seconds),
            "eligible_active_node_hours_wait_le_20_seconds": (
                eligible_active_node_hours_wait_le_20s
            ),
            "eligible_active_node_hours_wait_le_10_minutes": (
                eligible_active_node_hours_wait_le_10m
            ),
            "eligible_active_node_hours_wait_gt_10_minutes": (
                eligible_active_node_hours_wait_gt_10m
            ),
            "eligible_active_node_hour_fraction_wait_le_10_minutes": low_wait_fraction,
            "eligible_active_node_hour_fraction_wait_gt_10_minutes": high_wait_fraction,
            "training_submitted_H100_state_counts": dict(sorted(state_counts.items())),
            "exclusion_counts_not_mutually_exclusive": dict(sorted(excluded_submitted_counts.items())),
            "excluded_active_GPU_hours_not_mutually_exclusive": {
                key: float(value) for key, value in sorted(excluded_active_gpu_hours.items())
            },
            "physical_interpretation": (
                "The rule is a source-quality and scheduling-model tractability subset. "
                "It is not an observed service-deferrability label: it excludes work for "
                "sharing, allocation-shape, state, and node-class reasons while admitting "
                "substantial work with queue wait at or below ten minutes."
            ),
            "cohort_broadened": False,
        },
        "caprara_GPU_scope_plausibility_only": {
            "Caprara_fraction": CAPRARA_GPU_SIDE_FRACTION,
            "Kestrel_candidate_fraction_all_executed_H100": f_total,
            "absolute_difference": abs(f_total - CAPRARA_GPU_SIDE_FRACTION),
            "forced_equal": False,
            "calibration_calls": 0,
            "interpretation": (
                "Numerical comparison only; the Kestrel candidate is not accepted "
                "because current W_F lacks a service-deferrability label."
            ),
        },
        "whole_IT_boundary_actions": {
            "ESIF_reads": 0,
            "P_OTHER_IT_constructed": False,
            "P_GPU_FIXED_constructed": False,
            "whole_facility_flexible_share_parameter_removed_from_candidate": True,
            "eta_FLEX_created": False,
        },
        "downstream_not_run": [
            "cross-head retraining",
            "April P_OTHER_IT nonnegativity validation",
            "April B0/B1/B2/B3",
            "April AC-surrogate revalidation",
            "AC-feasibility restoration",
            "Fresh OpenDSS",
            "April-15 Monolithic/Standard-BD/CL-MC-BD regression",
        ],
        "final_classification": FINAL_CLASSIFICATION,
        "next_decision": NEXT_DECISION,
        "counters": _zero_counters(),
    }
    return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def artifact_fingerprint(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parent
            / "artifacts"
            / "v17_candidate"
            / "V17_GPU_SUBSYSTEM_BOUNDARY_TRAINING_AUDIT.json"
        ),
    )
    args = parser.parse_args(argv)
    verify_historical_artifacts(Path(__file__).resolve().parents[1])
    result = audit_training_only(args.raw_root)
    result["artifact_fingerprint"] = artifact_fingerprint(result)
    _write_json(args.output, result)
    print(FINAL_CLASSIFICATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
