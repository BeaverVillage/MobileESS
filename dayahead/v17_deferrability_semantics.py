"""Training-only V17 revealed-latency deferrability semantics.

This module is deliberately independent of the April scientific runners.  It
opens only the frozen Kestrel 2024-08 through 2025-03 archive members, treats
queue latency as a historical training label, and constructs a disjoint
fixed-plus-flexible H100 resource identity.  It never uses realized future-job
fields at D-1 inference.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_gpu_boundary_audit import (
    HISTORICAL_ARTIFACTS,
    artifact_fingerprint,
    verify_historical_artifacts,
)


STARTING_CHECKPOINT = "4ae0aa98bb995001d657f8a4de2f9cea868ae92d"
PRIOR_GPU_AUDIT_PATH = (
    "dayahead/artifacts/v17_candidate/"
    "V17_GPU_SUBSYSTEM_BOUNDARY_TRAINING_AUDIT.json"
)
PRIOR_GPU_AUDIT_SHA256 = (
    "e175b82d38079bdde39f8deb34472a029c1991c8130d6b7395ac330d9182b5da"
)
TRAIN_END_EXCLUSIVE = "2025-04-01"
MIN_MONTH = 202408
MAX_MONTH = 202503
CAPRARA_GPU_SCOPE_FRACTION = 0.205
LATENCY_CLASSES = ("C1", "C2", "C3", "C4", "C5")
LATENCY_UPPER_SECONDS: Mapping[str, float] = {
    "C1": 30.0 * 60.0,
    "C2": 60.0 * 60.0,
    "C3": 2.0 * 3600.0,
    "C4": 3.0 * 3600.0,
    "C5": math.inf,
}
DEFERRAL_LOWER_MINUTES: Mapping[str, int] = {
    "C1": 10,
    "C2": 30,
    "C3": 60,
    "C4": 120,
    "C5": 180,
}
DEFERRAL_SLOTS: Mapping[str, int] = {
    key: int(minutes // 15) for key, minutes in DEFERRAL_LOWER_MINUTES.items()
}


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


def latency_class(queue_wait_seconds: float) -> str | None:
    """Return the prospectively frozen left-open/right-closed latency class."""

    value = float(queue_wait_seconds)
    if not math.isfinite(value) or value < 0:
        return None
    if value <= 10.0 * 60.0:
        return "FIXED"
    for name in LATENCY_CLASSES:
        if value <= LATENCY_UPPER_SECONDS[name]:
            return name
    raise AssertionError("unreachable latency class")


def _add_interval_average(
    difference: Any,
    partial: Any,
    *,
    start_seconds: float,
    end_seconds: float,
    magnitude: float,
    slot_count: int,
) -> None:
    if end_seconds <= 0 or start_seconds >= slot_count * 900:
        return
    start_seconds = max(0.0, start_seconds)
    end_seconds = min(slot_count * 900.0, end_seconds)
    if end_seconds <= start_seconds:
        return
    first = int(start_seconds // 900)
    last = int(math.nextafter(end_seconds, -math.inf) // 900)
    if first == last:
        partial[first] += magnitude * (end_seconds - start_seconds) / 900.0
        return
    partial[first] += magnitude * ((first + 1) * 900.0 - start_seconds) / 900.0
    partial[last] += magnitude * (end_seconds - last * 900.0) / 900.0
    if last > first + 1:
        difference[first + 1] += magnitude
        difference[last] -= magnitude


def _field_evidence(schema_names: set[str], qos_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    def row(
        concept: str,
        fields: Sequence[str],
        classification: str,
        evidence: str,
        *,
        inference: bool,
    ) -> dict[str, Any]:
        present = [name for name in fields if name in schema_names]
        return {
            "candidate": concept,
            "source_fields": list(fields),
            "present_fields": present,
            "classification": classification if present else "NOT_AVAILABLE",
            "D_minus_1_inference_permitted": bool(inference and present),
            "evidence": evidence,
        }

    return [
        row("submit/request time", ["submit_time"], "CAUSAL_AT_SUBMISSION", "Slurm Submit timestamp.", inference=True),
        row("eligible time", ["eligible_time"], "NOT_AVAILABLE", "No Eligible field in the 50-column export.", inference=False),
        row("queue wait", ["queue_wait"], "HISTORICAL_LABEL_ONLY", "Derived as start_time minus submit_time.", inference=False),
        row("start time", ["start_time"], "EX_POST_ONLY", "Realized scheduler start.", inference=False),
        row("end time", ["end_time"], "EX_POST_ONLY", "Realized terminal timestamp.", inference=False),
        row("runtime", ["wallclock_used"], "EX_POST_ONLY", "Realized elapsed wallclock.", inference=False),
        row("terminal state", ["state", "state_simple"], "HISTORICAL_LABEL_ONLY", "Observed terminal/operational state; future terminal state is forbidden.", inference=False),
        row("partition", ["partition"], "CAUSAL_AT_SUBMISSION", "Requested Slurm partition.", inference=True),
        row("QOS", ["qos"], "CAUSAL_AT_SUBMISSION", f"Observed QOS values {dict(qos_counts)}; datacard supplies no QOS-to-SLA/deadline guarantee.", inference=True),
        row("priority", ["priority"], "NOT_AVAILABLE", "No Priority field.", inference=False),
        row("reservation", ["reservation", "reservation_name"], "NOT_AVAILABLE", "No Reservation field.", inference=False),
        row("deadline", ["deadline"], "NOT_AVAILABLE", "No Deadline field.", inference=False),
        row("requested time limit", ["wallclock_req"], "CAUSAL_AT_SUBMISSION", "Slurm Timelimit is a requested execution-duration cap, not a service-start deadline.", inference=True),
        row("preemption indicator", ["preempted", "preempt_time"], "NOT_AVAILABLE", "No dedicated preemption field.", inference=False),
        row("requeue indicator", ["requeue", "requeued"], "NOT_AVAILABLE", "No dedicated requeue field.", inference=False),
        row("requested GPUs/nodes", ["gpus_requested", "nodes_req"], "CAUSAL_AT_SUBMISSION", "Requested resources are known at submission.", inference=True),
        row("realized node occupancy", ["gpu_nodes_occupied", "nodes_used"], "EX_POST_ONLY", "Realized allocation/occupancy; label construction only.", inference=False),
        row("sharing/full-node status", ["shared_job_count", "nodes_shared", "jobs_shared"], "EX_POST_ONLY", "Observed co-residency; used only to establish historical power-model compatibility.", inference=False),
    ]


def _safe_fraction(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not math.isfinite(numerator) or not math.isfinite(denominator):
        raise RuntimeError("INVALID_SEMANTIC_FRACTION_DENOMINATOR")
    result = numerator / denominator
    if result < -1e-12 or result > 1.0 + 1e-12:
        raise RuntimeError("INVALID_SEMANTIC_FRACTION_RANGE")
    return float(result)


def _quantiles(values: Sequence[float]) -> dict[str, float | None]:
    import numpy as np

    if not values:
        return {"min": None, "p50": None, "p95": None, "p99": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {
        "min": float(array.min()),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
        "max": float(array.max()),
    }


def verify_immutable_history(repo_root: Path) -> dict[str, str]:
    observed = verify_historical_artifacts(repo_root)
    prior = repo_root / PRIOR_GPU_AUDIT_PATH
    prior_sha = sha256_file(prior)
    if prior_sha != PRIOR_GPU_AUDIT_SHA256:
        raise RuntimeError(f"PRIOR_GPU_AUDIT_CHANGED:{prior_sha}")
    observed[PRIOR_GPU_AUDIT_PATH] = prior_sha
    return observed


@dataclass(frozen=True)
class TrainingSemanticData:
    report: Mapping[str, Any]
    timestamps: Any
    p_placeholder: Any
    g_fixed: Any
    g_total_modelable: Any
    g_flex_by_class: Mapping[str, Any]
    arrivals_by_class_node: Mapping[tuple[str, int], Any]


def audit_training_semantics(raw_root: Path = DEFAULT_RAW_ROOT) -> TrainingSemanticData:
    """Audit and materialize labels without opening an April Kestrel member."""

    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    timestamps = pd.date_range(
        pd.Timestamp(TRAIN_START, tz=AEST),
        pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST),
        freq="15min",
        inclusive="left",
    )
    origin = timestamps[0].tz_convert("UTC").timestamp()
    slot_count = len(timestamps)
    kestrel = _find_exact_kestrel(raw_root)
    datacard = kestrel.parent / "datacard.md"
    datacard_text = datacard.read_text(encoding="utf-8")
    required = {
        "partition", "state", "state_simple", "submit_time", "start_time", "end_time",
        "nodes_req", "nodes_used", "wallclock_req", "wallclock_used", "qos",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared",
        "jobs_shared", "queue_wait",
    }
    retained: list[Any] = []
    members: list[dict[str, Any]] = []
    schemas: list[set[str]] = []
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(
        prefix="v17-deferrability-training-"
    ) as temporary:
        local = Path(temporary) / "month.parquet"
        selected: list[tuple[int, zipfile.ZipInfo]] = []
        for info in archive.infolist():
            match = re.search(
                r"year=(\d{4})/month=(\d{1,2})",
                info.filename.replace("\\", "/"),
            )
            if not match or not info.filename.casefold().endswith(".parquet"):
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
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required-names)}")
            schemas.append(names)
            retained.append(pq.read_table(local, columns=sorted(required)).to_pandas())
            members.append({"month": month, "member": info.filename, "rows": pq.read_metadata(local).num_rows})
    if not retained or len(members) != 8 or max(row["month"] for row in members) != MAX_MONTH:
        raise RuntimeError("TRAINING_MEMBER_RANGE_INCOMPLETE")
    schema_names = set.intersection(*schemas)
    frame = pd.concat(retained, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    is_h100 = frame["partition"].apply(_h100)
    completed = frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
    valid_interval = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
    observed_execution = is_h100 & valid_interval & end.gt(train_start) & start.lt(train_end)
    successfully_served = observed_execution & completed
    queue_seconds = (start - submit).dt.total_seconds()
    no_share = (
        (sharing.isna() | sharing.eq(0))
        & frame["nodes_shared"].apply(object_empty)
        & frame["jobs_shared"].apply(object_empty)
    )
    full_node = np.isclose(gpus, GPU_PER_NODE * nodes)
    measured_class = nodes.isin(NODE_CLASSES)
    valid_latency = queue_seconds.ge(0) & np.isfinite(queue_seconds)
    modelable = successfully_served & full_node & measured_class & no_share & valid_latency
    class_values = queue_seconds.apply(lambda value: latency_class(float(value)) if pd.notna(value) else None)
    fixed = modelable & class_values.eq("FIXED")
    flexible = modelable & class_values.isin(LATENCY_CLASSES)
    semantically_flexible = successfully_served & valid_latency & queue_seconds.gt(600.0)
    flexible_unmodeled = semantically_flexible & ~modelable

    clipped_start = start.where(start.ge(train_start), train_start)
    clipped_end = end.where(end.le(train_end), train_end)
    duration_hours = ((clipped_end - clipped_start).dt.total_seconds() / 3600.0).where(observed_execution, 0.0).fillna(0.0)
    all_gpu_hours = float((gpus.where(observed_execution, 0.0) * duration_hours).sum())
    all_node_hours = float(((gpus.where(observed_execution, 0.0) / GPU_PER_NODE) * duration_hours).sum())
    modelable_node_hours = float((nodes.where(modelable, 0.0) * duration_hours).sum())
    flexible_node_hours = float((nodes.where(flexible, 0.0) * duration_hours).sum())
    flexible_gpu_hours = float((gpus.where(flexible, 0.0) * duration_hours).sum())
    unmodeled_flexible_node_equivalent_hours = float(
        ((gpus.where(flexible_unmodeled, 0.0) / GPU_PER_NODE) * duration_hours).sum()
    )

    def trajectory(mask: Any) -> Any:
        difference = np.zeros(slot_count + 1, dtype=np.float64)
        partial = np.zeros(slot_count, dtype=np.float64)
        for index in np.flatnonzero(np.asarray(mask, dtype=bool)):
            _add_interval_average(
                difference,
                partial,
                start_seconds=start.iloc[index].timestamp() - origin,
                end_seconds=end.iloc[index].timestamp() - origin,
                magnitude=float(nodes.iloc[index]),
                slot_count=slot_count,
            )
        return partial + np.cumsum(difference[:-1])

    g_fixed = trajectory(fixed)
    g_flex_by_class = {
        name: trajectory(modelable & class_values.eq(name)) for name in LATENCY_CLASSES
    }
    g_total_modelable = trajectory(modelable)
    identity_error = float(
        np.max(np.abs(g_total_modelable - g_fixed - sum(g_flex_by_class.values())))
    )
    if identity_error > 1e-10 or np.any(g_fixed < -1e-12):
        raise RuntimeError("FIXED_PLUS_FLEX_RESOURCE_IDENTITY_FAILED")

    arrivals = {
        (name, node_class): np.zeros(slot_count, dtype=np.float64)
        for name in LATENCY_CLASSES
        for node_class in NODE_CLASSES
    }
    submitted_training = submit.ge(train_start) & submit.lt(train_end)
    for index in np.flatnonzero(np.asarray(flexible & submitted_training, dtype=bool)):
        name = str(class_values.iloc[index])
        node_class = int(nodes.iloc[index])
        slot = int((submit.iloc[index].timestamp() - origin) // 900)
        runtime_hours = float((end.iloc[index] - start.iloc[index]).total_seconds() / 3600.0)
        if 0 <= slot < slot_count:
            arrivals[(name, node_class)][slot] += node_class * runtime_hours

    class_stats: dict[str, Any] = {}
    for name in LATENCY_CLASSES:
        mask = flexible & class_values.eq(name)
        nodeh = float((nodes.where(mask, 0.0) * duration_hours).sum())
        gpuh = float((gpus.where(mask, 0.0) * duration_hours).sum())
        class_stats[name] = {
            "active_jobs_overlapping_training": int(mask.sum()),
            "active_node_hours": nodeh,
            "active_GPU_hours": gpuh,
            "fraction_of_modelable_flexible_node_hours": _safe_fraction(nodeh, flexible_node_hours),
            "queue_wait_seconds": _quantiles(queue_seconds[mask].dropna().astype(float).tolist()),
            "minimum_revealed_tolerance_minutes": DEFERRAL_LOWER_MINUTES[name],
            "conservative_15min_deferral_slots": DEFERRAL_SLOTS[name],
        }

    qos_mask = is_h100 & submitted_training
    qos_counts = Counter(frame.loc[qos_mask, "qos"].fillna("<NULL>").astype(str).tolist())
    field_table = _field_evidence(schema_names, dict(sorted(qos_counts.items())))
    stronger_metadata = False
    report: dict[str, Any] = {
        "artifact_id": "V17_DEFERRABILITY_TRAINING_SEMANTICS_AUDIT_V2",
        "status": "PASS_TRAINING_SEMANTICS_AND_RESOURCE_COHERENCE",
        "checkpoint": STARTING_CHECKPOINT,
        "source": {
            "kestrel_path": str(kestrel.resolve()),
            "kestrel_sha256": sha256_file(kestrel),
            "datacard_path": str(datacard.resolve()),
            "datacard_sha256": sha256_file(datacard),
            "datacard_declared_variable_count": 50,
            "schema_field_count": len(schema_names),
            "members_opened": members,
            "April_member_reads": 0,
            "May_member_reads": 0,
            "June_member_reads": 0,
            "datacard_documents_queue_wait_as_start_minus_submit": "queue_wait (start_time − submit_time)" in datacard_text,
        },
        "field_audit": field_table,
        "authority_hierarchy": {
            "explicit_user_SLA_deadline_metadata_semantically_valid": stronger_metadata,
            "qos_present_but_no_documented_service_tolerance_mapping": True,
            "selected_authority": "REVEALED_LATENCY_DEFERRABILITY_PROXY",
            "claim_boundary": "TRAINING_LABEL_PROXY_NOT_MEASURED_SLA",
        },
        "historical_name_correction": {
            "old_cohort_conceptual_name": "W_MODELABLE_OLD",
            "historical_artifacts_mutated": False,
        },
        "latency_contract": {
            "fixed": "queue_wait_seconds <= 600",
            "classes_left_open_right_closed": {
                "C1": "(600,1800]",
                "C2": "(1800,3600]",
                "C3": "(3600,7200]",
                "C4": "(7200,10800]",
                "C5": "(10800,+inf)",
            },
            "rounding_rule": "FLOOR_MINIMUM_REVEALED_TOLERANCE_TO_COMPLETE_15MIN_SLOTS",
            "deferral_slots": dict(DEFERRAL_SLOTS),
            "threshold_selection_data": "TRAINING_ONLY_PROSPECTIVE",
        },
        "magnitude": {
            "all_executed_H100_GPU_hours": all_gpu_hours,
            "all_executed_H100_equivalent_node_hours": all_node_hours,
            "modelable_H100_node_hours": modelable_node_hours,
            "semantic_flexible_modelable_node_hours": flexible_node_hours,
            "semantic_flexible_modelable_GPU_hours": flexible_gpu_hours,
            "flexible_node_hours_over_all_executed_H100": _safe_fraction(flexible_node_hours, all_node_hours),
            "flexible_GPU_hours_over_all_executed_H100": _safe_fraction(flexible_gpu_hours, all_gpu_hours),
            "flexible_node_hours_over_modelable_H100": _safe_fraction(flexible_node_hours, modelable_node_hours),
            "semantically_flexible_but_power_unmodeled_equivalent_node_hours": unmodeled_flexible_node_equivalent_hours,
            "semantically_flexible_but_power_unmodeled_fraction_of_semantic_flexible": _safe_fraction(
                unmodeled_flexible_node_equivalent_hours,
                flexible_node_hours + unmodeled_flexible_node_equivalent_hours,
            ),
            "kappa_modelable_fraction_of_semantic_flexible": _safe_fraction(
                flexible_node_hours,
                flexible_node_hours + unmodeled_flexible_node_equivalent_hours,
            ),
            "class_distribution": class_stats,
        },
        "resource_identity": {
            "definition": "G_TOTAL_MODELABLE = G_FIXED + sum_c G_FLEX_C",
            "sets_disjoint": True,
            "G_FIXED_direct_label_identifiable": True,
            "maximum_slot_identity_abs_error": identity_error,
            "negative_G_FIXED_slots": int(np.count_nonzero(g_fixed < -1e-12)),
            "unsupported_kappa_conversion_count": 0,
            "authorized_kappa_node_classes": sorted(KAPPA_KW_PER_ACTIVE_H100_NODE),
        },
        "causality_firewall": {
            "queue_wait_use": "TRAINING_LABEL_ONLY",
            "production_targets": ["G_FIXED", *[f"W_F_{name}" for name in LATENCY_CLASSES]],
            "class_node_subtargets": [
                f"W_F_{name}::N{node_class:02d}"
                for name in LATENCY_CLASSES
                for node_class in NODE_CLASSES
            ],
            "future_realized_start_time_reads": 0,
            "future_realized_end_time_reads": 0,
            "future_realized_queue_wait_reads": 0,
            "future_terminal_state_reads": 0,
            "future_realized_runtime_reads": 0,
            "future_realized_node_occupancy_reads": 0,
            "individual_future_job_injection": False,
        },
        "caprara_comparison": {
            "Caprara_GPU_scope_fraction": CAPRARA_GPU_SCOPE_FRACTION,
            "Kestrel_GPU_scope_fraction": _safe_fraction(flexible_gpu_hours, all_gpu_hours),
            "absolute_difference": abs(_safe_fraction(flexible_gpu_hours, all_gpu_hours) - CAPRARA_GPU_SCOPE_FRACTION),
            "purpose": "EXTERNAL_PLAUSIBILITY_ONLY",
            "calibration_to_Caprara": 0,
            "forced_equal": False,
        },
        "counters": {
            "April_result_reads_before_model_freeze": 0,
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
            "eta_FLEX_created": 0,
            "Caprara_calibration_calls": 0,
            "effect_selected_thresholds": 0,
            "effect_selected_delay_budgets": 0,
            "arbitrary_clipping_calls": 0,
            "OpenDSS_calls_inside_Benders": 0,
        },
    }
    report["artifact_fingerprint"] = artifact_fingerprint(report)
    return TrainingSemanticData(
        report=report,
        timestamps=timestamps,
        p_placeholder=np.zeros(slot_count, dtype=np.float64),
        g_fixed=g_fixed,
        g_total_modelable=g_total_modelable,
        g_flex_by_class=g_flex_by_class,
        arrivals_by_class_node=arrivals,
    )


@dataclass(frozen=True)
class ReferenceScheduleV4:
    authority_id: str
    service_by_class_node_rack_slot: Mapping[tuple[str, int, str, int], float]
    evidence: Mapping[str, Any]


def build_reference_schedule_v4(
    arrivals: Mapping[tuple[str, int], Sequence[float]],
    rack_capacity_nodeh_per_slot: Mapping[str, float],
) -> ReferenceScheduleV4:
    """Grid-blind/MESS-blind earliest-deadline, earliest-feasible fluid service."""

    expected = {(name, node) for name in LATENCY_CLASSES for node in NODE_CLASSES}
    if set(arrivals) != expected:
        raise ValueError("REFERENCE_V4_CLASS_NODE_AXIS_MISMATCH")
    if not rack_capacity_nodeh_per_slot or any(float(value) < 0 for value in rack_capacity_nodeh_per_slot.values()):
        raise ValueError("REFERENCE_V4_INVALID_RACK_CAPACITY")
    for values in arrivals.values():
        if len(values) != 96 or any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
            raise ValueError("REFERENCE_V4_REQUIRES_96_FINITE_NONNEGATIVE_ARRIVALS")
    racks = tuple(sorted(rack_capacity_nodeh_per_slot))
    service = {
        (name, node, rack, slot): 0.0
        for name in LATENCY_CLASSES
        for node in NODE_CLASSES
        for rack in racks
        for slot in range(96)
    }
    pending: list[dict[str, Any]] = []
    max_overdue = 0.0
    for slot in range(96):
        for name in LATENCY_CLASSES:
            for node in NODE_CLASSES:
                value = float(arrivals[(name, node)][slot])
                if value > 0:
                    pending.append({"class": name, "node": node, "arrival": slot, "due": min(95, slot + DEFERRAL_SLOTS[name]), "remaining": value})
        remaining = {rack: float(rack_capacity_nodeh_per_slot[rack]) for rack in racks}
        pending.sort(key=lambda item: (item["due"], item["arrival"], item["class"], item["node"]))
        for item in pending:
            for rack in racks:
                amount = min(float(item["remaining"]), remaining[rack])
                if amount <= 0:
                    continue
                service[(item["class"], item["node"], rack, slot)] += amount
                item["remaining"] -= amount
                remaining[rack] -= amount
                if item["remaining"] <= 1e-12:
                    break
        for item in pending:
            if item["due"] <= slot and item["remaining"] > 1e-10:
                max_overdue = max(max_overdue, float(item["remaining"]))
        if max_overdue > 0:
            raise RuntimeError(f"REFERENCE_V4_DEADLINE_INFEASIBLE:{slot}:{max_overdue}")
        pending = [item for item in pending if item["remaining"] > 1e-12]
    terminal = float(sum(float(item["remaining"]) for item in pending))
    if terminal > 1e-10:
        raise RuntimeError(f"REFERENCE_V4_TERMINAL_SERVICE_PARITY_FAILED:{terminal}")

    max_anticipation = 0.0
    max_deadline_shortfall = 0.0
    for name, node in sorted(expected):
        arrival_values = [float(value) for value in arrivals[(name, node)]]
        served = [
            sum(service[(name, node, rack, slot)] for rack in racks)
            for slot in range(96)
        ]
        cumulative_arrival = 0.0
        cumulative_service = 0.0
        for slot in range(96):
            cumulative_arrival += arrival_values[slot]
            cumulative_service += served[slot]
            max_anticipation = max(max_anticipation, cumulative_service - cumulative_arrival)
            due_slot = min(95, slot + DEFERRAL_SLOTS[name])
            served_by_due = sum(served[: due_slot + 1])
            arrived_by_slot = sum(arrival_values[: slot + 1])
            max_deadline_shortfall = max(max_deadline_shortfall, arrived_by_slot - served_by_due)
    evidence = {
        "policy": "EARLIEST_DEADLINE_EARLIEST_FEASIBLE_FLUID",
        "grid_information_reads": 0,
        "MESS_information_reads": 0,
        "OpenDSS_calls": 0,
        "optimized_result_reads": 0,
        "max_no_anticipation_violation_nodeh": max(0.0, max_anticipation),
        "max_deadline_shortfall_nodeh": max(0.0, max_deadline_shortfall),
        "terminal_backlog_nodeh": terminal,
        "service_parity_abs_error_nodeh": terminal,
    }
    return ReferenceScheduleV4("REFERENCE_COMPUTE_SCHEDULE_V4", service, evidence)


def contracts_from_report(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    magnitude = report["magnitude"]
    counters = report["counters"]
    common = {
        "starting_checkpoint": STARTING_CHECKPOINT,
        "source_sha256": report["source"]["kestrel_sha256"],
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
    }
    return {
        "V17_KESTREL_DEFERRABILITY_FIELD_AUDIT.json": {
            "artifact_id": "V17_KESTREL_DEFERRABILITY_FIELD_AUDIT_V1", **common,
            "status": "PASS_REVEALED_LATENCY_PROXY_SELECTED",
            "field_evidence": report["field_audit"],
            "authority_hierarchy": report["authority_hierarchy"],
            "source": report["source"],
        },
        "V17_REVEALED_LATENCY_DEFERRABILITY_CONTRACT.json": {
            "artifact_id": "V17_REVEALED_LATENCY_DEFERRABILITY_CONTRACT_V1", **common,
            "status": "PASS_FROZEN_PROSPECTIVELY",
            "latency_contract": report["latency_contract"],
            "label_claim": "REVEALED_LATENCY_DEFERRABILITY_PROXY_NOT_MEASURED_SLA",
            "Caprara": report["caprara_comparison"],
        },
        "V17_FLEXIBLE_COHORT_SEMANTICS_V2.json": {
            "artifact_id": "V17_FLEXIBLE_COHORT_SEMANTICS_V2", **common,
            "status": "PASS",
            "primary_filter": ["H100", "COMPLETED", "valid execution interval", "full-node allocation", "kappa node class", "no sharing", "latency C1-C5"],
            "historical_old_name": "W_MODELABLE_OLD",
            "causality_firewall": report["causality_firewall"],
            "unmodeled_rule": "SEMANTICALLY_FLEXIBLE_BUT_POWER_UNMODELED",
        },
        "V17_CLASS_SPECIFIC_WORKLOAD_TARGET_CONTRACT.json": {
            "artifact_id": "V17_CLASS_SPECIFIC_WORKLOAD_TARGET_CONTRACT_V1", **common,
            "status": "PASS",
            "aggregate_targets": [f"W_F_{name}" for name in LATENCY_CLASSES],
            "direct_class_node_heads": report["causality_firewall"]["class_node_subtargets"],
            "aggregate_identity": "W_F_Cc = sum_n W_F_Cc::Nn",
            "output_slots": 96,
            "quantiles": [0.1, 0.5, 0.9],
            "positive_only_scaling": True,
        },
        "V17_REFERENCE_SCHEDULER_V4_CONTRACT.json": {
            "artifact_id": "V17_REFERENCE_SCHEDULER_V4_CONTRACT_V1", **common,
            "status": "PASS_CONTRACT_UNIT_VALIDATED",
            "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V4",
            "policy": "GRID_BLIND_MESS_BLIND_EARLIEST_DEADLINE_EARLIEST_FEASIBLE_FLUID",
            "deferral_slots": dict(DEFERRAL_SLOTS),
            "constraints": ["NO_ANTICIPATORY_SERVICE", "CLASS_DEADLINE", "TERMINAL_SERVICE_PARITY"],
        },
        "V17_FIXED_PLUS_FLEX_RESOURCE_LABEL_AUDIT.json": {
            "artifact_id": "V17_FIXED_PLUS_FLEX_RESOURCE_LABEL_AUDIT_V1", **common,
            "status": "PASS",
            **report["resource_identity"],
        },
        "V17_TRAINING_SEMANTIC_FLEXIBILITY_MAGNITUDE.json": {
            "artifact_id": "V17_TRAINING_SEMANTIC_FLEXIBILITY_MAGNITUDE_V1", **common,
            "status": "PASS_DEFINITION_RESULT_NOT_TUNING_TARGET",
            **magnitude,
            "Caprara_comparison": report["caprara_comparison"],
            "counters": counters,
        },
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_training_semantics_artifacts(output: Path, data: TrainingSemanticData) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in contracts_from_report(data.report).items():
        write_json(output / name, payload)
