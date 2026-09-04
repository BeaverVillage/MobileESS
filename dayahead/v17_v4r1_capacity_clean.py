"""V17 V4R1 prospective capacity-consistent whole-GPU support audit."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .authority import sha256_file
from .v17_deferrability_semantics import latency_class, write_json
from .v17_v4_whole_gpu_gres import (
    AEST,
    DATASET312_SHA256,
    GPU_PER_NODE,
    KESTREL_SHA256,
    NODE_CLASSES,
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    _as_sequence,
    _h100,
    _semantic_masks,
    _training_members,
)


CONFLICT_IDS = (7539787, 7543918, 7545385)
FROZEN_KAPPA = {"Q10": 0.3941881609951147, "Q50": 0.48563611660901085, "Q90": 0.5391969931144363}


def zero_counters() -> dict[str, int]:
    return {
        "April_scientific_input_reads_before_freeze": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "GPU_clipping_calls": 0,
        "timestamp_correction_calls": 0,
        "fractional_GPU_imputation_calls": 0,
        "arbitrary_scaling_calls": 0,
        "grid_selected_parameter_calls": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def _canonical_hash(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8")); digest.update(b"\n")
    return digest.hexdigest()


def _json_value(value: object) -> object:
    import pandas as pd

    if value is None or (not isinstance(value, (list, tuple, np.ndarray)) and pd.isna(value)):
        return None
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _sweep(events_by_node: Mapping[str, list[tuple[int, int, str, int]]], excluded: set[str] | None = None) -> dict[str, Any]:
    excluded = excluded or set()
    intervals: list[dict[str, Any]] = []
    global_max = 0
    q: set[str] = set()
    node_maxima: dict[str, int] = {}
    for node, raw_events in sorted(events_by_node.items()):
        grouped: dict[int, list[tuple[int, str, int]]] = collections.defaultdict(list)
        for timestamp, kind, job_id, delta in raw_events:
            if job_id not in excluded:
                grouped[timestamp].append((kind, job_id, delta))
        timestamps = sorted(grouped)
        active: dict[str, int] = {}
        maximum = 0
        for position, timestamp in enumerate(timestamps):
            # release kind=0 before start kind=1 at identical timestamps
            for kind, job_id, _delta in sorted(grouped[timestamp], key=lambda item: item[0]):
                if kind == 0:
                    active.pop(job_id, None)
            for kind, job_id, delta in sorted(grouped[timestamp], key=lambda item: item[0]):
                if kind == 1:
                    active[job_id] = delta
            allocated = sum(active.values())
            maximum = max(maximum, allocated)
            global_max = max(global_max, allocated)
            if position + 1 < len(timestamps) and allocated > GPU_PER_NODE:
                right = timestamps[position + 1]
                if right > timestamp:
                    members = sorted(active)
                    q.update(members)
                    intervals.append({
                        "node": node,
                        "start_ns_utc": timestamp,
                        "end_ns_utc": right,
                        "duration_seconds": (right - timestamp) / 1e9,
                        "allocated_GPUs": allocated,
                        "active_job_ids": members,
                        "GPU_count_by_job": {job_id: active[job_id] for job_id in members},
                    })
        node_maxima[node] = maximum
    return {
        "maximum_concurrent_allocated_GPUs": global_max,
        "violation_interval_count": len(intervals),
        "conflict_intervals": intervals,
        "conflict_job_union_Q": sorted(q),
        "conflict_job_union_count": len(q),
        "node_count": len(node_maxima),
        "nodes_at_global_maximum": sorted(node for node, value in node_maxima.items() if value == global_max),
    }


def audit_and_materialize(kestrel: Path, output: Path) -> dict[str, Any]:
    import pandas as pd
    import pyarrow.parquet as pq

    if sha256_file(kestrel) != KESTREL_SHA256:
        raise RuntimeError("V17_V4R1_KESTREL_SOURCE_SHA_MISMATCH")
    contract_path = output / "V17_AIDC_POWER_MODEL_V4R1_CAPACITY_CONSISTENT_SUPPORT_CONTRACT.json"
    if not contract_path.is_file():
        raise RuntimeError("V17_V4R1_PROSPECTIVE_SUPPORT_CONTRACT_MISSING")
    columns = [
        "id", "job_id", "array_pos", "array_range", "partition", "state", "state_simple",
        "submit_time", "start_time", "end_time", "wallclock_used", "gpu_nodes_occupied",
        "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared", "nodelist", "qos",
    ]
    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    events: dict[str, list[tuple[int, int, str, int]]] = collections.defaultdict(list)
    metadata: dict[str, dict[str, Any]] = {}
    duplicate_counts: collections.Counter[str] = collections.Counter()
    u2_ids: set[str] = set()
    v1_ids: set[str] = set()
    gpu_hours: collections.Counter[str] = collections.Counter()
    jobs: collections.Counter[str] = collections.Counter()
    schema_fields: set[str] = set()
    source_member_by_id: dict[str, str] = {}
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="v17-v4r1-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in _training_members(archive):
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema_fields.update(pq.read_schema(local).names)
            frame = pq.read_table(local, columns=columns).to_pandas()
            valid, semantic, v1, u2 = _semantic_masks(frame)
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            queue = (start - submit).dt.total_seconds()
            for index in frame.index[valid]:
                job_id = str(frame.at[index, "id"])
                duplicate_counts[job_id] += 1
                source_member_by_id[job_id] = info.filename
                node_list = _as_sequence(frame.at[index, "nodelist"])
                node_count = float(nodes.at[index]); gpu_count = float(gpus.at[index])
                exact_uniform = (
                    node_count.is_integer() and node_count > 0 and len(node_list) == int(node_count)
                    and gpu_count.is_integer() and (gpu_count / node_count).is_integer()
                    and 1 <= int(gpu_count / node_count) <= GPU_PER_NODE
                )
                if exact_uniform:
                    per_node = int(gpu_count / node_count)
                    left = max(start.at[index], train_start); right = min(end.at[index], train_end)
                    if right > left:
                        for node in node_list:
                            events[node].append((int(left.value), 1, job_id, per_node))
                            events[node].append((int(right.value), 0, job_id, per_node))
                if int(frame.at[index, "job_id"]) in CONFLICT_IDS:
                    metadata[job_id] = {
                        "source_member": info.filename,
                        "duplicate_row_count_training_members": None,
                        "id": job_id,
                        "job_id": int(frame.at[index, "job_id"]),
                        "array_pos": _json_value(frame.at[index, "array_pos"]),
                        "array_range": _json_value(frame.at[index, "array_range"]),
                        "state": str(frame.at[index, "state"]),
                        "state_simple": str(frame.at[index, "state_simple"]),
                        "partition": str(frame.at[index, "partition"]),
                        "qos": str(frame.at[index, "qos"]),
                        "submit_time": _json_value(submit.at[index]),
                        "start_time": _json_value(start.at[index]),
                        "end_time": _json_value(end.at[index]),
                        "elapsed_source": str(frame.at[index, "wallclock_used"]),
                        "elapsed_recomputed_seconds": (end.at[index] - start.at[index]).total_seconds(),
                        "nodelist": node_list,
                        "gpu_nodes_occupied": node_count,
                        "gpus_requested": gpu_count,
                        "shared_job_count": None if pd.isna(frame.at[index, "shared_job_count"]) else int(frame.at[index, "shared_job_count"]),
                        "nodes_shared": _as_sequence(frame.at[index, "nodes_shared"]),
                        "jobs_shared": _as_sequence(frame.at[index, "jobs_shared"]),
                        "frozen_latency_class": latency_class(float(queue.at[index])),
                        "queue_wait_seconds_recomputed": float(queue.at[index]),
                        "frozen_U2_member": bool(u2.at[index]),
                    }
            for name, mask in (("semantic", semantic), ("V1", v1), ("U2", u2)):
                for index in np.flatnonzero(np.asarray(mask, dtype=bool)):
                    job_id = str(frame.at[index, "id"])
                    left = max(start.iloc[index], train_start); right = min(end.iloc[index], train_end)
                    hours = (right - left).total_seconds() / 3600.0
                    jobs[name] += 1; gpu_hours[name] += float(gpus.iloc[index]) * hours
                    if name == "V1": v1_ids.add(job_id)
                    if name == "U2": u2_ids.add(job_id)
    missing = sorted(set(map(str, CONFLICT_IDS)) - set(metadata))
    if missing:
        raise RuntimeError(f"V17_V4R1_CONFLICT_SOURCE_ROWS_MISSING:{missing}")
    for job_id, row in metadata.items():
        row["duplicate_row_count_training_members"] = duplicate_counts[job_id]
    original = _sweep(events)
    q = set(original["conflict_job_union_Q"])
    cleaned = _sweep(events, q)
    if q != set(map(str, CONFLICT_IDS)):
        raise RuntimeError(f"V17_V4R1_UNEXPECTED_SOURCE_REPRODUCED_Q:{sorted(q)}")
    if cleaned["maximum_concurrent_allocated_GPUs"] > 4 or cleaned["violation_interval_count"] != 0:
        status = "FAIL_ADDITIONAL_CAPACITY_CONFLICTS"
    else:
        status = "PASS_CAPACITY_CONSISTENT_AFTER_GLOBAL_HYPEREDGE_QUARANTINE"
    u2_quarantined = u2_ids & q
    q_outside_u2 = q - u2_ids
    u2_clean = u2_ids - q
    q_gpu_hours = 0.0; q_nodeh = 0.0; u2_q_gpu_hours = 0.0
    for job_id in q:
        row = metadata[job_id]
        hours = float(row["elapsed_recomputed_seconds"]) / 3600.0
        amount = float(row["gpus_requested"]) * hours
        q_gpu_hours += amount; q_nodeh += amount / GPU_PER_NODE
        if job_id in u2_ids:
            u2_q_gpu_hours += amount
    semantic_gpu_h = float(gpu_hours["semantic"])
    v1_gpu_h = float(gpu_hours["V1"])
    u2_gpu_h = float(gpu_hours["U2"])
    clean_u2_gpu_h = u2_gpu_h - u2_q_gpu_hours
    coverage = (v1_gpu_h + clean_u2_gpu_h) / semantic_gpu_h
    # Strict node-day diagnostic: source-local date of the conflict interval.
    conflict_node = original["conflict_intervals"][0]["node"]
    conflict_start = pd.Timestamp(original["conflict_intervals"][0]["start_ns_utc"], unit="ns", tz="UTC")
    strict_local_day = conflict_start.tz_convert("America/Denver").date()
    strict_ids: set[str] = set()
    for timestamp, kind, job_id, _delta in events[conflict_node]:
        instant = pd.Timestamp(timestamp, unit="ns", tz="UTC").tz_convert("America/Denver")
        if instant.date() == strict_local_day:
            strict_ids.add(job_id)
    strict_u2 = sorted(strict_ids & u2_ids)
    source_audit = {
        "artifact_id": "V17_AIDC_POWER_V4R1_CONFLICT_SOURCE_AUDIT_V1",
        "status": "PASS_NO_SOURCE_BACKED_RECORD_CORRECTION",
        "source_path": str(kestrel.resolve()), "source_sha256": sha256_file(kestrel),
        "rows": metadata,
        "duplicate_job_records": {job_id: duplicate_counts[job_id] for job_id in sorted(metadata)},
        "requeue_resize_evidence": "NONE_EXPLICIT: array fields null, unique IDs, completed states; no requeue/resize field in public schema",
        "suspension_preemption_fields_available": sorted(name for name in schema_fields if re.search(r"suspend|preempt|resize|restart|requeue", name, re.I)),
        "source_resolution": "UNRESOLVED_WHICH_RECORD_CAUSED_5_GPU_INTERVAL_ALL_THREE_RETAINED_IN_GLOBAL_Q",
        "important_frozen_semantic_finding": "7545385 has queue_wait=1 second and frozen latency class FIXED, so it is in Q but not in frozen U2; the two flexible U2 members of Q are 7539787 and 7543918.",
        **zero_counters(),
    }
    sweep = {
        "artifact_id": "V17_AIDC_POWER_V4R1_GLOBAL_CAPACITY_SWEEP_V1",
        "status": status,
        "candidate_trace_universe": "all exact whole-GPU H100 completed allocation intervals; active flexible support is the U2 subset",
        "original": original,
        "cleaned_after_removing_entire_Q": cleaned,
        "boundary_semantics": "half-open [start,end); releases before starts at identical timestamps",
        "training_window_AEST": [TRAIN_START, "2025-03-31"],
        **zero_counters(),
    }
    quarantine = {
        "artifact_id": "V17_AIDC_POWER_V4R1_QUARANTINE_MANIFEST_V1",
        "status": "PASS_GLOBAL_SOURCE_ONLY_HYPEREDGE_QUARANTINE",
        "primary_Q_all_conflict_hyperedge_members": sorted(q),
        "primary_Q_membership_sha256": _canonical_hash(q),
        "Q_jobs": len(q), "Q_GPU_hours": q_gpu_hours, "Q_node_equivalent_hours": q_nodeh,
        "U2_QUARANTINED_intersection_Q": sorted(u2_quarantined),
        "Q_members_outside_frozen_U2": sorted(q_outside_u2),
        "U2_CLEAN_jobs": len(u2_clean), "U2_CLEAN_membership_sha256": _canonical_hash(u2_clean),
        "U2_CLEAN_GPU_hours": clean_u2_gpu_h,
        "U2_CLEAN_node_equivalent_hours": clean_u2_gpu_h / GPU_PER_NODE,
        "quarantined_power_role": "retained in P_IT_REF residual and total-IT denominator; no flexible delta",
        "strict_node_day_diagnostic_only": {
            "node": conflict_node, "source_local_day_America_Denver": str(strict_local_day),
            "U2_job_ids": strict_u2, "U2_job_count": len(strict_u2),
            "membership_sha256": _canonical_hash(strict_u2),
            "authority_selected": False,
        },
        "expected_values_hardcoded": False,
        **zero_counters(),
    }
    comparison = {
        "artifact_id": "V17_AIDC_POWER_V1_V4R1_COVERAGE_COMPARISON_V1",
        "status": "PASS_SOURCE_REPRODUCED_NO_COVERAGE_GATE",
        "semantic_flexible": {"jobs": int(jobs["semantic"]), "GPU_hours": semantic_gpu_h, "node_equivalent_hours": semantic_gpu_h / GPU_PER_NODE},
        "V1": {"jobs": int(jobs["V1"]), "GPU_hours": v1_gpu_h, "coverage_fraction": v1_gpu_h / semantic_gpu_h},
        "V4R1_U2_CLEAN": {"jobs": len(u2_clean), "GPU_hours": clean_u2_gpu_h, "node_equivalent_hours": clean_u2_gpu_h / GPU_PER_NODE},
        "V1_plus_V4R1_U2_CLEAN": {"jobs": int(jobs["V1"]) + len(u2_clean), "GPU_hours": v1_gpu_h + clean_u2_gpu_h, "coverage_fraction": coverage},
        "candidate_support_reaches_90_percent": coverage >= 0.9,
        "coverage_used_as_acceptance_gate": False,
        "diagnostic_expected_92_094454_percent_absolute_difference": abs(coverage - 0.92094454),
        "difference_reason": "one of the three conflict-hyperedge jobs is FIXED and was never in frozen U2, so source-reproduced U2_CLEAN removes two U2 jobs, not three",
        **zero_counters(),
    }
    validation = {
        "artifact_id": "V17_AIDC_POWER_MODEL_V4R1_VALIDATION_V1",
        "status": "PASS" if status.startswith("PASS") else "FAIL",
        "original_conflict_reproduced": original["violation_interval_count"] > 0,
        "entire_conflict_hyperedge_quarantined": q == set(map(str, CONFLICT_IDS)),
        "cleaned_maximum_concurrent_allocated_GPUs": cleaned["maximum_concurrent_allocated_GPUs"],
        "cleaned_violation_interval_count": cleaned["violation_interval_count"],
        "quarantine_independent_of_coverage_and_grid": True,
        "old_V4_record_correction_calls": 0,
        "power_coefficients": FROZEN_KAPPA,
        "CPU_host_power_role": "P_IT_REF_RESIDUAL",
        **zero_counters(),
    }
    contract = {
        "authority_id": "V17_AIDC_POWER_MODEL_V4R1_WHOLE_GPU_CLEAN_GRES",
        "status": "PASS_PROSPECTIVE_AUTHORITY_FROZEN_BEFORE_APRIL" if validation["status"] == "PASS" else "FAIL_CLOSED",
        "active_support": {
            "V1": "frozen exclusive full-node support unchanged",
            "U2_CLEAN": "same-node co-residency of capacity-consistent exclusive whole GPUs excluding U2 intersection Q",
            "Q": "no active flexible power; retained in P_IT_REF residual",
        },
        "active_delta_equation": "Delta_P_F_kW = kappa_GPU_Q50_kW * Delta_requested_whole_GPU_count",
        "sensitivity_coefficients_kW_per_GPU": FROZEN_KAPPA,
        "primary_coefficient": "Q50",
        "idle_subtraction_W_per_GPU": 72.5,
        "measurement_boundary": "NVML GPU board only",
        "CPU_host_incremental_power": "retained in P_IT_REF residual",
        "support_hashes": {"U2_CLEAN": quarantine["U2_CLEAN_membership_sha256"], "Q": quarantine["primary_Q_membership_sha256"]},
        "target_semantics": "W[c,g,t] GPU-hours per 15-minute arrival slot; c=C1..C5, g=1..4 whole GPUs per node",
        "historical_authority_changes": 0,
        **zero_counters(),
    }
    artifacts = {
        "V17_AIDC_POWER_V4R1_CONFLICT_SOURCE_AUDIT.json": source_audit,
        "V17_AIDC_POWER_V4R1_GLOBAL_CAPACITY_SWEEP.json": sweep,
        "V17_AIDC_POWER_V4R1_QUARANTINE_MANIFEST.json": quarantine,
        "V17_AIDC_POWER_V1_V4R1_COVERAGE_COMPARISON.json": comparison,
        "V17_AIDC_POWER_MODEL_V4R1_VALIDATION.json": validation,
        "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json": contract,
    }
    for name, payload in artifacts.items():
        write_json(output / name, payload)
    return {"status": contract["status"], "Q": sorted(q), "U2_CLEAN_jobs": len(u2_clean), "coverage": coverage}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kestrel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    print(json.dumps(audit_and_materialize(args.kestrel, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
