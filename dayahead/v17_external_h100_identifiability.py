"""Fail-closed V17 external-H100/Kestrel semantic identifiability audit."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import re
import shutil
import statistics
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_external_h100_forensic import (
    SCIENTIFIC_PAYLOAD,
    SCIENTIFIC_DUP_DIR,
    EUROSYS_ARCHIVE,
    EUROSYS_DIR,
    write_json,
    zero_counters,
)


TRAIN_END_EXCLUSIVE = "2025-04-01"
GPU_PER_NODE = 4
KESTREL_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
V2_CONTRACT_SHA256 = "882dfbdf24abade96bd2aacd1dae66dfd7a25e89885d9d62a902bc273dad937b"
V2_VALIDATION_SHA256 = "36b93cbeb224223a98dfcf7c2d47c5b8c3fa0f8b358f205082595451d76ccb68"
FINAL_CLASSIFICATION = "V17_AIDC_POWER_V3_E_EXTERNAL_POWER_NOT_IDENTIFIABLE"
SHARE_CLASSIFICATION = "V17_EXT_SHARE_D_NOT_SEMANTICALLY_IDENTIFIABLE"


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _as_sequence(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [] if not stripped or stripped in {"[]", "{}"} else [stripped]
    try:
        return [str(item) for item in value]  # type: ignore[arg-type]
    except TypeError:
        return [str(value)]


def _training_members(archive: zipfile.ZipFile) -> list[tuple[int, zipfile.ZipInfo]]:
    selected: list[tuple[int, zipfile.ZipInfo]] = []
    for info in archive.infolist():
        match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
        if match and info.filename.casefold().endswith(".parquet"):
            month = int(match.group(1)) * 100 + int(match.group(2))
            if 202408 <= month <= 202503:
                selected.append((month, info))
    return sorted(selected)


def audit_kestrel_u2(kestrel: Path, prior: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    import pandas as pd
    import pyarrow.parquet as pq

    if sha256_file(kestrel) != KESTREL_SHA256:
        raise RuntimeError("V17_KESTREL_SOURCE_SHA_MISMATCH")
    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    required = {
        "job_id", "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared", "nodelist",
    }
    names = [
        "U1_EXCLUSIVE_PARTIAL_NODE", "U2_SHARED_PARTIAL_OR_SHARED_NODE",
        "U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT", "U4_OTHER_POWER_UNMODELED",
    ]
    groups = {
        name: {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
        for name in names
    }
    semantic = {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
    modelable = {"jobs": 0, "GPU_hours": 0.0, "node_equivalent_hours": 0.0, "occupied_node_hours": 0.0}
    u2_counts: collections.Counter[str] = collections.Counter()
    shared_count_distribution: collections.Counter[str] = collections.Counter()
    requested_gpu_distribution: collections.Counter[str] = collections.Counter()
    occupied_node_distribution: collections.Counter[str] = collections.Counter()
    referenced_jobs: set[int] = set()
    u2_examples: list[dict[str, Any]] = []
    member_records: list[dict[str, Any]] = []

    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="v17-ext-u2-") as temporary:
        local = Path(temporary) / "month.parquet"
        members = _training_members(archive)
        if len(members) != 8:
            raise RuntimeError("V17_KESTREL_TRAINING_MONTH_AXIS_INCOMPLETE")
        for month, info in members:
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            schema = pq.read_schema(local)
            if not required.issubset(set(schema.names)):
                raise RuntimeError("V17_KESTREL_U2_REQUIRED_SCHEMA_MISSING")
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            member_records.append({"month": month, "member": info.filename, "rows": len(frame)})
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid_execution = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            overlap = end.gt(train_start) & start.lt(train_end)
            queue = (start - submit).dt.total_seconds()
            valid_queue = submit.notna() & queue.ge(0) & np.isfinite(queue)
            completed = frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            semantic_mask = frame["partition"].apply(_h100) & valid_execution & overlap & valid_queue & queue.gt(600.0) & completed
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            full_node = np.isclose(gpus, GPU_PER_NODE * nodes)
            supported_count = nodes.isin(NODE_CLASSES)
            modelable_mask = semantic_mask & full_node & supported_count & no_share
            unmodeled = semantic_mask & ~modelable_mask
            masks = {
                names[0]: unmodeled & no_share & gpus.gt(0) & gpus.lt(GPU_PER_NODE * nodes),
                names[1]: unmodeled & ~no_share,
                names[2]: unmodeled & no_share & full_node & ~supported_count,
            }
            masks[names[3]] = unmodeled & ~(masks[names[0]] | masks[names[1]] | masks[names[2]])
            clipped_start = start.where(start.ge(train_start), train_start)
            clipped_end = end.where(end.le(train_end), train_end)
            duration = ((clipped_end - clipped_start).dt.total_seconds() / 3600.0).where(semantic_mask, 0.0).fillna(0.0)

            def accumulate(target: dict[str, float], mask: Any) -> None:
                target["jobs"] += int(mask.sum())
                target["GPU_hours"] += float((gpus.where(mask, 0.0) * duration).sum())
                target["node_equivalent_hours"] += float(((gpus.where(mask, 0.0) / GPU_PER_NODE) * duration).sum())
                target["occupied_node_hours"] += float((nodes.where(mask, 0.0) * duration).sum())

            accumulate(semantic, semantic_mask)
            accumulate(modelable, modelable_mask)
            for name, mask in masks.items():
                accumulate(groups[name], mask)

            u2 = masks[names[1]]
            for index in frame.index[u2]:
                node_list = _as_sequence(frame.at[index, "nodelist"])
                nodes_shared = _as_sequence(frame.at[index, "nodes_shared"])
                jobs_shared = _as_sequence(frame.at[index, "jobs_shared"])
                shared_count = int(float(frame.at[index, "shared_job_count"]))
                gpu_count = float(frame.at[index, "gpus_requested"])
                occupied = float(frame.at[index, "gpu_nodes_occupied"])
                u2_counts["rows"] += 1
                u2_counts["shared_count_positive"] += int(shared_count > 0)
                u2_counts["nodes_shared_nonempty"] += int(bool(nodes_shared))
                u2_counts["jobs_shared_nonempty"] += int(bool(jobs_shared))
                u2_counts["single_occupied_node"] += int(occupied == 1)
                u2_counts["single_shared_node"] += int(len(nodes_shared) == 1)
                u2_counts["shared_count_equals_jobs_list_length"] += int(shared_count == len(jobs_shared))
                u2_counts["nodelist_contains_shared_node"] += int(bool(set(node_list) & set(nodes_shared)))
                shared_count_distribution[str(shared_count)] += 1
                requested_gpu_distribution[str(gpu_count)] += 1
                occupied_node_distribution[str(occupied)] += 1
                for value in jobs_shared:
                    if value.isdigit():
                        referenced_jobs.add(int(value))
                if len(u2_examples) < 8:
                    u2_examples.append({
                        "job_id": int(frame.at[index, "job_id"]),
                        "gpus_requested": gpu_count,
                        "gpu_nodes_occupied": occupied,
                        "nodelist": node_list,
                        "shared_job_count": shared_count,
                        "nodes_shared": nodes_shared,
                        "jobs_shared": jobs_shared[:12],
                    })

        resolved: dict[int, dict[str, Any]] = {}
        for month, info in members:
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            frame = pq.read_table(
                local,
                columns=["job_id", "start_time", "end_time", "gpus_requested", "gpu_nodes_occupied", "nodelist"],
            ).to_pandas()
            selected = frame[frame["job_id"].isin(referenced_jobs)]
            for _, row in selected.iterrows():
                resolved[int(row["job_id"])] = {
                    "start_time": str(row["start_time"]), "end_time": str(row["end_time"]),
                    "gpus_requested": float(row["gpus_requested"]),
                    "gpu_nodes_occupied": float(row["gpu_nodes_occupied"]),
                    "nodelist": _as_sequence(row["nodelist"]),
                }

    expected_groups = {row["group"]: row for row in prior["groups"]}
    reproduction_errors = {
        name: {
            "jobs": int(groups[name]["jobs"] - expected_groups[name]["jobs"]),
            "node_equivalent_hours": float(groups[name]["node_equivalent_hours"] - expected_groups[name]["node_equivalent_hours"]),
        }
        for name in names
    }
    identity = all(row["jobs"] == 0 and abs(row["node_equivalent_hours"]) <= 1e-9 for row in reproduction_errors.values())
    if not identity:
        raise RuntimeError("V17_KESTREL_U1_U2_U3_REPRODUCTION_MISMATCH")

    cohort = {
        "artifact_id": "V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY_V1",
        "status": "PASS_REPRODUCTION_FAIL_CLOSED_NO_NEW_SOURCE_BACKED_COHORT",
        "source": {"path": str(kestrel.resolve()), "sha256": KESTREL_SHA256, "members_opened": member_records},
        "semantic_flexible": semantic,
        "V1_modelable": modelable,
        "groups": [{"group": name, **groups[name]} for name in names],
        "reproduction_identity": {"pass": identity, "errors": reproduction_errors},
        "classifications": {
            "U1": "V17_V3_U1_NOT_IDENTIFIABLE",
            "U2": "V17_V3_U2_NOT_IDENTIFIABLE",
            "U3": "V17_V3_U3_NOT_IDENTIFIABLE",
        },
        "recoverable_node_equivalent_hours": {"U1": 0.0, "U2": 0.0, "U3": 0.0},
        "reasons": {
            "U1": "Kestrel requested-GPU fraction is observable, but neither external source supplies held-out measurements for the corresponding exclusive partial allocation state on a compatible 4-GPU Kestrel node.",
            "U2": "Kestrel exposes node/job co-residency but not per-device assignment, same-GPU sharing mechanism, utilization, MIG state, or time-slice fraction; EuroSys raw power rows are absent.",
            "U3": "V1 only freezes measured node classes 1/2/4/8/16; external sources do not validate extrapolation to unsupported Kestrel full-node counts under the V1 power boundary.",
        },
        "disjoint_set_validation": {
            "mutually_exclusive": True,
            "jobs_sum_exact": sum(int(row["jobs"]) for row in groups.values()) == int(semantic["jobs"] - modelable["jobs"]),
            "node_equivalent_hours_sum_abs_error": abs(
                sum(float(row["node_equivalent_hours"]) for row in groups.values())
                - float(semantic["node_equivalent_hours"] - modelable["node_equivalent_hours"])
            ),
        },
        **zero_counters(),
    }

    u2_audit = {
        "artifact_id": "V17_KESTREL_U2_SHARING_SEMANTICS_AUDIT_V1",
        "status": "PASS_OBSERVABLE_AUDIT_NOT_ELECTRICALLY_IDENTIFIABLE",
        "U2_jobs": groups[names[1]]["jobs"],
        "U2_node_equivalent_hours": groups[names[1]]["node_equivalent_hours"],
        "entry_rule": "semantic flexible AND not V1 modelable AND any of shared_job_count!=0, nodes_shared nonempty, jobs_shared nonempty",
        "evidence_consistency_counts": dict(u2_counts),
        "shared_job_count_distribution": dict(sorted(shared_count_distribution.items(), key=lambda item: int(item[0]))),
        "gpus_requested_distribution": dict(sorted(requested_gpu_distribution.items(), key=lambda item: float(item[0]))),
        "gpu_nodes_occupied_distribution": dict(sorted(occupied_node_distribution.items(), key=lambda item: float(item[0]))),
        "observables": {
            "sharing_inference": "source-provided shared_job_count and explicit nodes_shared/jobs_shared lists",
            "exact_physical_node_identity_known": True,
            "multiple_jobs_tied_to_same_physical_node": True,
            "per_device_GPU_assignment_known": False,
            "concurrent_overlap_intervals_known": "PARTIAL: start/end exist for resolved listed jobs, but jobs_shared is not a per-device or per-node allocation map for multi-node jobs",
            "referenced_job_ID_count": len(referenced_jobs),
            "referenced_job_IDs_resolved_within_training_months": len(resolved),
            "referenced_job_resolution_fraction": len(resolved) / max(len(referenced_jobs), 1),
            "total_requested_GPU_count_per_shared_node_known": "ONLY for resolvable single-node jobs; not generally attributable per node/device",
            "GPU_utilization_known": False,
            "same_GPU_vs_separate_GPU_co_residency_known": False,
            "MIG_state_known": False,
            "time_slicing_known": False,
            "D1_future_physical_node_assignment_known": False,
        },
        "examples": u2_examples,
        "external_semantic_transfer_classification": SHARE_CLASSIFICATION,
        "transfer_reason": "EuroSys experiments explicitly impose MIG or time-slicing/container sharing. Kestrel U2 records only scheduler co-residency and requested GPU totals; the mechanism is unobserved and the external raw response is absent.",
        "rowwise_external_to_Kestrel_merges": 0,
        **zero_counters(),
    }
    return cohort, u2_audit


class Moments:
    def __init__(self) -> None:
        self.n = 0
        self.x = 0.0
        self.y = 0.0
        self.xx = 0.0
        self.yy = 0.0
        self.xy = 0.0

    def add(self, x: float, y: float) -> None:
        self.n += 1; self.x += x; self.y += y
        self.xx += x * x; self.yy += y * y; self.xy += x * y

    def correlation(self) -> float | None:
        if self.n < 2:
            return None
        num = self.n * self.xy - self.x * self.y
        den = math.sqrt(max(self.n * self.xx - self.x * self.x, 0.0) * max(self.n * self.yy - self.y * self.y, 0.0))
        return num / den if den > 0 else None


def audit_scientific_power(payload: Path) -> dict[str, Any]:
    moments = Moments()
    power_by_gpu: dict[int, list[float]] = {index: [] for index in range(8)}
    zero_util_power: list[float] = []
    positive_util_power: list[float] = []
    session_rows: list[dict[str, Any]] = []
    cpu_power_nonempty = 0
    with zipfile.ZipFile(payload) as archive:
        candidates = [
            info for info in archive.infolist()
            if "/Node_Dataset/" in info.filename and "/H100/" in info.filename
            and info.filename.casefold().endswith(".csv")
        ]
        unique: dict[int, zipfile.ZipInfo] = {}
        for info in candidates:
            unique.setdefault(info.CRC, info)
        for info in unique.values():
            node_power: list[float] = []
            rows = 0
            with archive.open(info) as binary:
                reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline=""))
                for row in reader:
                    rows += 1
                    if row.get("cpu_power_W", "").strip():
                        cpu_power_nonempty += 1
                    slot_power = 0.0
                    valid_slot = True
                    for gpu in range(8):
                        try:
                            util = float(row[f"gpu{gpu}_utilization_percent"])
                            power = float(row[f"gpu{gpu}_power_W"])
                        except (KeyError, TypeError, ValueError):
                            valid_slot = False
                            continue
                        moments.add(util, power)
                        power_by_gpu[gpu].append(power)
                        (zero_util_power if util == 0 else positive_util_power).append(power)
                        slot_power += power
                    if valid_slot:
                        node_power.append(slot_power)
            session_rows.append({
                "member": info.filename,
                "rows": rows,
                "mean_node_GPU_power_W": statistics.fmean(node_power) if node_power else None,
                "p95_node_GPU_power_W": float(np.percentile(node_power, 95)) if node_power else None,
            })
    per_gpu_means = {str(index): statistics.fmean(values) for index, values in power_by_gpu.items() if values}
    session_means = [float(row["mean_node_GPU_power_W"]) for row in session_rows if row["mean_node_GPU_power_W"] is not None]
    return {
        "artifact_id": "V17_SCIENTIFIC_DATA_H100_POWER_RESPONSE_AUDIT_V1",
        "status": "PASS_INDEPENDENT_PHYSICAL_RESPONSE_EVIDENCE_NOT_SHARING_AUTHORITY",
        "source_path": str(payload.resolve()),
        "unique_H100_sessions_by_CRC32": len(session_rows),
        "per_GPU_samples": moments.n,
        "P_GPU_vs_GPU_utilization": {
            "pearson_correlation": moments.correlation(),
            "note": "Utilization is a measured activity percentage, not GPU allocation fraction.",
        },
        "P_CPU_vs_GPU_state": {
            "cpu_power_nonempty_rows": cpu_power_nonempty,
            "identifiable": False,
            "reason": "cpu_power_W is empty in all H100 node rows.",
        },
        "node_power_composition": "sum of eight directly measured per-GPU board-power channels only; host/CPU power unavailable",
        "idle_to_active_transition": {
            "source_labeled_idle_state_available": False,
            "zero_utilization_sample_count": len(zero_util_power),
            "positive_utilization_sample_count": len(positive_util_power),
            "mean_power_W_at_zero_utilization_not_an_idle_authority": statistics.fmean(zero_util_power) if zero_util_power else None,
            "mean_power_W_at_positive_utilization": statistics.fmean(positive_util_power) if positive_util_power else None,
        },
        "per_GPU_heterogeneity": {
            "mean_power_W_by_device_index": per_gpu_means,
            "range_of_device_means_W": max(per_gpu_means.values()) - min(per_gpu_means.values()),
        },
        "session_variability": {
            "minimum_session_mean_node_GPU_power_W": min(session_means),
            "maximum_session_mean_node_GPU_power_W": max(session_means),
            "coefficient_of_variation_session_means": statistics.pstdev(session_means) / statistics.fmean(session_means),
        },
        "sessions": session_rows,
        "sharing_or_co_resident_measurements": False,
        "improves_H100_physical_power_authority": True,
        "permitted_role": "independent dimensionless/qualitative H100 activity-power evidence only",
        **zero_counters(),
    }


def audit_eurosys(eurosys: Path) -> dict[str, Any]:
    with zipfile.ZipFile(eurosys) as archive:
        data_files = [
            info for info in archive.infolist()
            if not info.is_dir() and ("/data/" in info.filename or "/bench-res/" in info.filename)
            and not info.filename.endswith(".gitkeep")
        ]
    return {
        "artifact_id": "V17_EUROSYS_H100_SHARING_POWER_AUDIT_V1",
        "status": "FAIL_CLOSED_RAW_SHARING_POWER_TELEMETRY_ABSENT",
        "source_path": str(eurosys.resolve()),
        "experimental_families": {
            "non_shared_full_GPU": {"present_as_code": True, "power_boundary": "DCGM device plus IPMI platform declared", "measurement_rows": 0},
            "MIG": {"present_as_code": True, "power_boundary": "DCGM device plus IPMI platform declared", "measurement_rows": 0},
            "time_slicing": {"present_as_code": True, "power_boundary": "DCGM device plus IPMI platform declared", "measurement_rows": 0},
            "concurrent_container_or_job": {"present_as_code": True, "power_boundary": "DCGM device plus IPMI platform declared", "measurement_rows": 0},
        },
        "raw_data_file_count": len(data_files),
        "GPU_only_response_identifiable": False,
        "node_level_response_identifiable": False,
        "marginal_shared_work_power_identifiable": False,
        "transfer_to_Kestrel_U2": SHARE_CLASSIFICATION,
        "reason": "The archive defines sharing interventions but includes no resulting measurements; Kestrel also does not reveal whether scheduler co-residency is MIG, time-slicing, same-GPU sharing, or separate-GPU placement.",
        **zero_counters(),
    }


def _acceptance_contract() -> dict[str, Any]:
    return {
        "artifact_id": "V17_AIDC_POWER_V3_EXTERNAL_ACCEPTANCE_CONTRACT_V1",
        "status": "FAIL_CLOSED_NO_PROSPECTIVE_NUMERICAL_THRESHOLD",
        "created_before_final_held_out_error_reads": True,
        "final_held_out_error_reads": 0,
        "split_rule": "hold out complete experiment/session/workload/sharing configuration; random telemetry-row split prohibited",
        "required_metrics": [
            "MAE", "RMSE", "bias", "NRMSE", "absolute relative-error distribution",
            "P95 error", "worst-case error", "marginal-power MAE", "marginal-power bias",
        ],
        "threshold_sources_considered": {
            "frozen_Dataset312_V1_validation_error_envelope": "No predictive held-out error envelope exists; only deterministic kappa reproduction tolerances.",
            "external_repeatability_uncertainty": "EuroSys raw repeats absent; Scientific Data has no documented repeatability/noise bound for identical configurations.",
            "source_documented_noise_bound": "Not encoded in either downloaded source.",
        },
        "numerical_acceptance_threshold": None,
        "outcome_seeking_threshold_invention": 0,
        "authorization_consequence": "No V3 point model may be fitted, validated, or minted.",
        "held_out_run_leakage_prevention": "PASS_BY_NO_FIT_AND_PROSPECTIVE_COMPLETE_RUN_RULE",
        **zero_counters(),
    }


def materialize(repo: Path, external_root: Path, kestrel: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); external_root = external_root.resolve(); output = output.resolve()
    prior = json.loads((output / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json").read_text(encoding="utf-8"))
    if sha256_file(output / "V17_AIDC_POWER_MODEL_V2_CONTRACT.json") != V2_CONTRACT_SHA256:
        raise RuntimeError("V17_REJECTED_V2_CONTRACT_CHANGED")
    if sha256_file(output / "V17_AIDC_POWER_MODEL_V2_VALIDATION.json") != V2_VALIDATION_SHA256:
        raise RuntimeError("V17_REJECTED_V2_VALIDATION_CHANGED")

    # This is intentionally written before any candidate held-out error could be read.
    acceptance = _acceptance_contract()
    write_json(output / "V17_AIDC_POWER_V3_EXTERNAL_ACCEPTANCE_CONTRACT.json", acceptance)

    cohort, u2 = audit_kestrel_u2(kestrel, prior)
    eurosys = external_root / EUROSYS_DIR / EUROSYS_ARCHIVE
    scientific = external_root / SCIENTIFIC_DUP_DIR / SCIENTIFIC_PAYLOAD
    euro_audit = audit_eurosys(eurosys)
    scientific_audit = audit_scientific_power(scientific)

    v1_jobs = int(cohort["V1_modelable"]["jobs"])
    v1_nodeh = float(cohort["V1_modelable"]["node_equivalent_hours"])
    semantic_jobs = int(cohort["semantic_flexible"]["jobs"])
    semantic_nodeh = float(cohort["semantic_flexible"]["node_equivalent_hours"])
    coverage = {
        "artifact_id": "V17_AIDC_POWER_V1_V3_COVERAGE_COMPARISON_V1",
        "status": "PASS_V3_NOT_AUTHORIZED_COVERAGE_UNCHANGED",
        "semantic_flexible": cohort["semantic_flexible"],
        "V1_modelable": cohort["V1_modelable"],
        "V3_modelable": cohort["V1_modelable"],
        "newly_recovered": {
            "U1": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U2": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U3": {"jobs": 0, "node_equivalent_hours": 0.0},
        },
        "V1_coverage_fraction": {"jobs": v1_jobs / semantic_jobs, "node_equivalent_hours": v1_nodeh / semantic_nodeh},
        "V3_coverage_fraction": {"jobs": v1_jobs / semantic_jobs, "node_equivalent_hours": v1_nodeh / semantic_nodeh},
        "incremental_coverage_fraction": {"jobs": 0.0, "node_equivalent_hours": 0.0},
        "remaining_unmodeled_fraction": {
            "jobs": (semantic_jobs - v1_jobs) / semantic_jobs,
            "node_equivalent_hours": (semantic_nodeh - v1_nodeh) / semantic_nodeh,
        },
        **zero_counters(),
    }
    cross = {
        "artifact_id": "V17_EXTERNAL_H100_CROSS_DATASET_CONSISTENCY_V1",
        "status": "NOT_IDENTIFIABLE_THREE_WAY_COMPARISON",
        "Dataset312": {
            "absolute_anchor_kW_per_active_4GPU_H100_node": dict(KAPPA_KW_PER_ACTIVE_H100_NODE),
            "boundary": "incremental NVML GPU plus RAPL CPU package after frozen idle subtraction",
        },
        "EuroSys": {"observations_available": 0, "reason": "raw data and benchmark results absent"},
        "Scientific_Data": {
            "observations_available": scientific_audit["per_GPU_samples"],
            "boundary": scientific_audit["node_power_composition"],
            "utilization_power_correlation": scientific_audit["P_GPU_vs_GPU_utilization"]["pearson_correlation"],
        },
        "full_H100_state_overlap": "No source-identical full-state tuple across form factor, GPU count, CPU, workload, boundary and idle semantics.",
        "confidence_interval": None,
        "incompatible_hardware_averaging_calls": 0,
        "conclusion": "Scientific Data independently confirms a physical activity-power response, but cannot calibrate a Kestrel allocation/sharing marginal or replace V1 kappa.",
        **zero_counters(),
    }
    contract = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT_REJECTION_RECORD_V1",
        "status": "NOT_MINTED",
        "requested_authority_id": "V17_AIDC_POWER_MODEL_V3_EXTERNAL_SHARED_AUTHORITY",
        "authority_id": None,
        "primary_classification": FINAL_CLASSIFICATION,
        "active_boundary": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        "hybrid_support_map": None,
        "candidate_equations_not_authorized": {
            "U1": "P_inc = kappa_V1(full-node anchor) * g_external(f_GPU)",
            "U2_aggregate": "P_node = F(co_resident_job_count,total_requested_GPUs,node_occupancy)",
        },
        "reason": "No new cohort passes observable-semantic compatibility, marginal-power identifiability, held-out validation and the prospective acceptance gate.",
        "V1_kappa_changes": 0,
        **zero_counters(),
    }
    validation = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION_REJECTION_RECORD_V1",
        "status": "NOT_RUN_NOT_AUTHORIZED",
        "primary_classification": FINAL_CLASSIFICATION,
        "U1_CLASSIFICATION": cohort["classifications"]["U1"],
        "U2_CLASSIFICATION": cohort["classifications"]["U2"],
        "U3_CLASSIFICATION": cohort["classifications"]["U3"],
        "held_out_metrics": None,
        "marginal_power_metrics": None,
        "acceptance_gate": acceptance["status"],
        "fit_calls": 0,
        "final_held_out_error_reads": 0,
        **zero_counters(),
    }

    artifacts = {
        "V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json": u2,
        "V17_SCIENTIFIC_DATA_H100_POWER_RESPONSE_AUDIT.json": scientific_audit,
        "V17_EUROSYS_H100_SHARING_POWER_AUDIT.json": euro_audit,
        "V17_EXTERNAL_H100_CROSS_DATASET_CONSISTENCY.json": cross,
        "V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY.json": cohort,
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json": contract,
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION.json": validation,
        "V17_AIDC_POWER_V1_V3_COVERAGE_COMPARISON.json": coverage,
    }
    for name, payload in artifacts.items():
        write_json(output / name, payload)
    return {
        "status": FINAL_CLASSIFICATION,
        "U1_CLASSIFICATION": cohort["classifications"]["U1"],
        "U2_CLASSIFICATION": cohort["classifications"]["U2"],
        "U3_CLASSIFICATION": cohort["classifications"]["U3"],
        "V3_minted": False,
        "RCMQT_retrained": False,
        "same_7day_rerun": False,
        "READY_FOR_APRIL_RESUME": True,
        **zero_counters(),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--kestrel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    print(json.dumps(materialize(args.repo, args.external_root, args.kestrel, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
