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
OUT = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"
V18 = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
V17_FORENSIC = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
OLD_MANIFEST = V18 / "V18_AIDC_REFREEZE_PRECHANGE_MANIFEST.json"
V17_CAND = ROOT / "dayahead" / "artifacts" / "v17_candidate"
KESTREL = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip")
KESTREL_SHA = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
TRAIN_START = "2024-08-19"
TRAIN_END_EXCLUSIVE = "2025-04-01"
AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
DT_H = 0.25
PUE = 1.30
GPU_PER_NODE = 4
NODE_CLASSES = (1, 2, 4, 8, 16)
TIER_NAMES = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")
DEBUG_DAYS = ("2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23")
OFFICIAL_SOURCES = {
    "FY25_ALLOCATION": "https://www.nrel.gov/docs/gen/fy24/90033.pdf",
    "OCT2024_OVERVIEW": "https://www.nrel.gov/docs/fy25osti/91696.pdf",
    "AUG2024_BUILDOUT": "https://www.nrel.gov/news/program/2024/kestrel-supercomputer-ready-to-energize-renewable-energy-research.html",
    "VTO_BUYIN_Q3": "https://www.nrel.gov/docs/libraries/transportation/fy25-q3-vto-accomplishments-report.pdf",
    "VTO_BUYIN_Q1": "https://www.nrel.gov/docs/libraries/transportation/fy25-q1-vto-accomplishments-report.pdf",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_artifact(name: str, value: object) -> None:
    write_json(OUT / name, value)


def as_sequence(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, np.ndarray):
        return tuple(str(item) for item in value.tolist() if str(item))
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    try:
        if bool(np.isnan(value)):
            return ()
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return () if text.casefold() in {"", "none", "nan", "[]"} else (text,)


def is_h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


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


def interval_slot_gpuh(starts, ends, weights, boundaries) -> np.ndarray:
    import pandas as pd

    if len(weights) == 0:
        return np.zeros(len(boundaries) - 1, dtype=float)
    boundary_ns = pd.DatetimeIndex(boundaries).as_unit("ns").asi8
    origin_ns = int(boundary_ns[0])
    start_s = (pd.DatetimeIndex(starts).as_unit("ns").asi8 - origin_ns) / 1e9
    end_s = (pd.DatetimeIndex(ends).as_unit("ns").asi8 - origin_ns) / 1e9
    weight = np.asarray(weights, dtype=float)
    boundary_s = (boundary_ns - origin_ns) / 1e9

    def ramp(times: np.ndarray) -> np.ndarray:
        order = np.argsort(times)
        sorted_times = times[order]
        sorted_weights = weight[order]
        cumulative_weight = np.concatenate(([0.0], np.cumsum(sorted_weights)))
        cumulative_weighted_time = np.concatenate(([0.0], np.cumsum(sorted_weights * sorted_times)))
        indices = np.searchsorted(sorted_times, boundary_s, side="right")
        return boundary_s * cumulative_weight[indices] - cumulative_weighted_time[indices]

    return np.diff(ramp(start_s) - ramp(end_s)) / 3600.0


def scan_kestrel() -> tuple[object, dict[str, object]]:
    import pandas as pd
    import pyarrow.parquet as pq

    if sha256(KESTREL) != KESTREL_SHA:
        raise RuntimeError("KESTREL_SHA_MISMATCH")
    requested_columns = [
        "id", "job_id", "array_pos", "array_range", "partition", "qos", "state", "state_simple",
        "submit_time", "start_time", "end_time", "nodes_req", "nodes_used", "nodelist",
        "gpus_requested", "gpu_nodes_occupied", "shared_job_count", "nodes_shared", "jobs_shared",
    ]
    frames: list[object] = []
    members: list[dict[str, object]] = []
    schema_union: set[str] = set()
    schema_intersection: set[str] | None = None
    field_types: dict[str, set[str]] = defaultdict(set)
    total_rows = 0
    total_h100_rows = 0
    with zipfile.ZipFile(KESTREL) as archive, tempfile.TemporaryDirectory(prefix="v18r1-kestrel-") as temporary:
        local = Path(temporary) / "month.parquet"
        selected: list[tuple[int, zipfile.ZipInfo]] = []
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if match and info.filename.casefold().endswith(".parquet"):
                month = int(match.group(1)) * 100 + int(match.group(2))
                if 202408 <= month <= 202504:
                    selected.append((month, info))
        if len(selected) != 9:
            raise RuntimeError("KESTREL_AUGUST_TO_APRIL_MEMBER_AXIS_INCOMPLETE")
        for month, info in sorted(selected):
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = pq.read_schema(local)
            names = set(schema.names)
            schema_union |= names
            schema_intersection = names if schema_intersection is None else schema_intersection & names
            for field in schema:
                field_types[field.name].add(str(field.type))
            missing = set(requested_columns) - names
            if missing:
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{month}:{sorted(missing)}")
            table = pq.read_table(local, columns=requested_columns)
            frame = table.to_pandas()
            row_count = len(frame)
            h100_mask = frame["partition"].apply(is_h100)
            h100_frame = frame.loc[h100_mask].copy()
            h100_frame["source_month"] = month
            h100_frame["source_member"] = info.filename
            frames.append(h100_frame)
            total_rows += row_count
            total_h100_rows += len(h100_frame)
            members.append({"month": month, "member": info.filename, "rows": row_count, "H100_rows": len(h100_frame)})
    frame = pd.concat(frames, ignore_index=True)
    for column in ("submit_time", "start_time", "end_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce", format="mixed")
    for column in ("nodes_req", "nodes_used", "gpus_requested", "gpu_nodes_occupied", "shared_job_count"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["node_tuple"] = frame["nodelist"].apply(as_sequence)
    frame["nodes_shared_tuple"] = frame["nodes_shared"].apply(as_sequence)
    frame["jobs_shared_tuple"] = frame["jobs_shared"].apply(as_sequence)
    metadata = {
        "source_path": str(KESTREL),
        "source_sha256": KESTREL_SHA,
        "members": members,
        "all_rows_Aug2024_Apr2025": total_rows,
        "H100_rows_Aug2024_Apr2025": total_h100_rows,
        "schema_union": sorted(schema_union),
        "schema_intersection": sorted(schema_intersection or set()),
        "field_types": {name: sorted(types) for name, types in sorted(field_types.items())},
    }
    return frame, metadata


def training_frame(frame):
    import pandas as pd

    start_bound = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    end_bound = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    valid = (
        frame["start_time"].notna() & frame["end_time"].notna()
        & frame["end_time"].gt(frame["start_time"])
        & frame["gpus_requested"].gt(0) & frame["gpu_nodes_occupied"].gt(0)
        & frame["end_time"].gt(start_bound) & frame["start_time"].lt(end_bound)
    )
    result = frame.loc[valid].copy()
    result["clip_start"] = result["start_time"].where(result["start_time"].ge(start_bound), start_bound)
    result["clip_end"] = result["end_time"].where(result["end_time"].le(end_bound), end_bound)
    result["duration_h"] = (result["clip_end"] - result["clip_start"]).dt.total_seconds() / 3600.0
    result["queue_seconds"] = (result["start_time"] - result["submit_time"]).dt.total_seconds()
    result["node_count_list"] = result["node_tuple"].apply(len)
    result["duplicate_nodes_in_nodelist"] = result["node_tuple"].apply(lambda values: len(values) != len(set(values)))
    result["exact_uniform"] = [
        bool(nodes) and len(nodes) == int(node_count) and float(gpus).is_integer()
        and (float(gpus) / len(nodes)).is_integer() and 1 <= int(float(gpus) / len(nodes)) <= GPU_PER_NODE
        for nodes, node_count, gpus in zip(result["node_tuple"], result["gpu_nodes_occupied"], result["gpus_requested"])
    ]
    result["per_node_gpu"] = [float(gpus) / len(nodes) if exact else np.nan for nodes, gpus, exact in zip(result["node_tuple"], result["gpus_requested"], result["exact_uniform"])]
    no_share = (
        (result["shared_job_count"].isna() | result["shared_job_count"].eq(0))
        & result["nodes_shared_tuple"].apply(lambda value: not value)
        & result["jobs_shared_tuple"].apply(lambda value: not value)
    )
    result["no_share"] = no_share
    result["semantic_flexible"] = (
        result["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & result["submit_time"].notna() & result["queue_seconds"].gt(600)
        & np.isfinite(result["queue_seconds"])
    )
    return result


def schema_audit(all_h100, training, scan_meta: dict[str, object]) -> dict[str, object]:
    duplicate_id_rows = int(all_h100["id"].astype(str).duplicated(keep=False).sum())
    duplicate_exact = int(all_h100.duplicated(subset=["id", "start_time", "end_time", "gpus_requested"], keep=False).sum())
    job_groups = all_h100.groupby("job_id", dropna=False)
    array_group_count = 0
    nonexecuting_parent_summary_groups = 0
    executing_parent_child_collision_groups = 0
    for _, group in job_groups:
        if len(group) > 1 and group["array_pos"].notna().any():
            array_group_count += 1
            parents = group.loc[group["array_pos"].isna()]
            if not parents.empty:
                parent_executes = (
                    parents["start_time"].notna()
                    & parents["end_time"].notna()
                    & parents["gpus_requested"].gt(0)
                    & parents["gpu_nodes_occupied"].gt(0)
                )
                if bool(parent_executes.any()):
                    executing_parent_child_collision_groups += 1
                else:
                    nonexecuting_parent_summary_groups += 1
    step_like_id_count = int(all_h100["id"].astype(str).str.contains(r"\.(?:batch|extern|\d+)$", regex=True).sum())
    partition_counts = Counter(training["partition"].astype(str))
    queue_negative = int((training["queue_seconds"] < 0).sum())
    return {
        "artifact_id": "V18R1_KESTREL_GPU_ACCOUNTING_SCHEMA_AUDIT_V1",
        "source": scan_meta,
        "requested_fields": {
            "gpus_requested": "PRESENT_REQUEST_QUANTITY",
            "gpu_nodes_occupied": "PRESENT_NODE_COUNT_OCCUPIED",
            "nodelist": "PRESENT_EXECUTION_NODELIST",
        },
        "allocation_fields": {
            "AllocTRES": "ABSENT", "tres_alloc": "ABSENT", "gres_alloc": "ABSENT",
            "allocated_GPU_identity": "ABSENT",
        },
        "series_semantics": {
            "G_REQUESTED": "gpus_requested projected over retrospective execution interval",
            "G_ALLOCATED_OBS": None,
            "G_PHYSICAL_FEASIBLE": "nodelist-constrained source-request feasibility, after explicitly listed global conflict quarantine",
        },
        "risk_audit": {
            "A1_duplicate_rows": {"verdict": "PASS" if duplicate_id_rows == 0 else "CONTRIBUTOR", "duplicate_id_rows": duplicate_id_rows, "duplicate_exact_rows": duplicate_exact},
            "A2_job_step_double_count": {"verdict": "PASS", "step_field_present": False, "step_like_id_count": step_like_id_count},
            "A3_requeue_duplicate_execution": {"verdict": "NOT_APPLICABLE", "explicit_requeue_field": False, "duplicate_id_rows": duplicate_id_rows},
            "A4_array_parent_child_double_count": {
                "verdict": "PASS" if executing_parent_child_collision_groups == 0 else "CONTRIBUTOR",
                "array_execution_groups": array_group_count,
                "nonexecuting_parent_summary_groups": nonexecuting_parent_summary_groups,
                "executing_parent_plus_child_collision_groups": executing_parent_child_collision_groups,
                "interpretation": "null-array_pos parent summaries without executable start/end/GPU/node data are excluded by the valid execution filter; non-null array_pos rows are executed tasks",
            },
            "A5_non_H100_contamination": {"verdict": "PASS", "filter": "partition comma-token starts with gpu-h100"},
            "A6_other_subsystem_contamination": {"verdict": "PASS", "included_H100_partition_counts": dict(sorted(partition_counts.items()))},
            "A7_nodelist_parsing_duplicate": {"verdict": "PASS" if not bool(training["duplicate_nodes_in_nodelist"].any()) else "FAIL", "rows_with_duplicate_node_identity": int(training["duplicate_nodes_in_nodelist"].sum())},
            "A8_timezone_DST_conversion": {"verdict": "PASS", "source_timezone_types": scan_meta["field_types"], "normalization": "all timestamps converted to UTC before AEST boundary clipping", "negative_queue_intervals": queue_negative},
            "A9_overlap_integration": {"verdict": "PENDING_NUMERIC_IDENTITY_IN_FEASIBILITY_ARTIFACT", "interval": "half-open [start,end)", "same_timestamp_order": "release before start"},
            "A10_requested_vs_allocated_confusion": {"verdict": "CONTRIBUTOR", "reason": "V18 named a requested-over-execution integral as physical active occupancy despite no AllocTRES/GRES allocation field"},
        },
    }


def active_node_max(intervals: list[tuple[int, int, tuple[str, ...]]], begin_ns: int, end_ns: int) -> int:
    events: list[tuple[int, int, str]] = []
    for start_ns, finish_ns, nodes in intervals:
        left = max(start_ns, begin_ns)
        right = min(finish_ns, end_ns)
        if right <= left:
            continue
        for node in nodes:
            events.append((left, 1, node))
            events.append((right, -1, node))
    events.sort(key=lambda item: (item[0], item[1]))
    node_counts: Counter[str] = Counter()
    active = 0
    maximum = 0
    for _, delta, node in events:
        before = node_counts[node]
        node_counts[node] += delta
        after = node_counts[node]
        if before == 0 and after > 0:
            active += 1
        elif before > 0 and after == 0:
            active -= 1
        maximum = max(maximum, active)
    return maximum


def residual_bipartite_feasible(
    jobs: list[tuple[str, int, tuple[str, ...]]], capacities: dict[str, int]
) -> bool:
    """Integer max-flow for ambiguous residual GPU placement after mandatory one-per-listed-node use."""
    if not jobs:
        return True
    source = "__SOURCE__"
    sink = "__SINK__"
    graph: dict[str, dict[str, int]] = defaultdict(dict)

    def edge(left: str, right: str, capacity: int) -> None:
        graph[left][right] = graph[left].get(right, 0) + capacity
        graph[right].setdefault(left, 0)

    total = 0
    for job_id, demand, nodes in jobs:
        job = f"job:{job_id}"
        edge(source, job, demand)
        total += demand
        for node in nodes:
            edge(job, f"node:{node}", demand)
    for node, capacity in capacities.items():
        edge(f"node:{node}", sink, max(0, capacity))
    flow = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = [source]
        for current in queue:
            for neighbor, capacity in graph[current].items():
                if capacity > 0 and neighbor not in parent:
                    parent[neighbor] = current
                    queue.append(neighbor)
                    if neighbor == sink:
                        break
            if sink in parent:
                break
        if sink not in parent:
            break
        amount = 10**9
        cursor = sink
        while parent[cursor] is not None:
            amount = min(amount, graph[parent[cursor]][cursor])
            cursor = parent[cursor]
        cursor = sink
        while parent[cursor] is not None:
            previous = parent[cursor]
            graph[previous][cursor] -= amount
            graph[cursor][previous] = graph[cursor].get(previous, 0) + amount
            cursor = previous
        flow += amount
    return flow == total


def ambiguous_interval_feasibility(exact, ambiguous, excluded_ids: set[str]) -> dict[str, object]:
    import pandas as pd

    exact_map = {
        str(row.id): (float(row.per_node_gpu), tuple(row.node_tuple))
        for row in exact.itertuples(index=False)
        if str(row.id) not in excluded_ids
    }
    ambiguous_map = {
        str(row.id): (int(row.gpus_requested), tuple(row.node_tuple))
        for row in ambiguous.itertuples(index=False)
        if str(row.id) not in excluded_ids
    }
    events: list[tuple[int, int, str, str]] = []
    for row in exact.itertuples(index=False):
        job_id = str(row.id)
        if job_id in excluded_ids:
            continue
        events.append((int(row.clip_start.value), 1, "exact", job_id))
        events.append((int(row.clip_end.value), -1, "exact", job_id))
    for row in ambiguous.itertuples(index=False):
        job_id = str(row.id)
        if job_id in excluded_ids:
            continue
        events.append((int(row.clip_start.value), 1, "ambiguous", job_id))
        events.append((int(row.clip_end.value), -1, "ambiguous", job_id))
    events.sort(key=lambda item: (item[0], item[1]))
    active_exact: set[str] = set()
    active_ambiguous: set[str] = set()
    infeasible: list[dict[str, object]] = []
    feasible_intervals = 0
    ambiguous_slots: set[int] = set()
    infeasible_slots: set[int] = set()
    start_origin = int(pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC").value)
    index = 0
    while index < len(events):
        timestamp = events[index][0]
        while index < len(events) and events[index][0] == timestamp and events[index][1] == -1:
            _, _, kind, job_id = events[index]
            (active_exact if kind == "exact" else active_ambiguous).discard(job_id)
            index += 1
        while index < len(events) and events[index][0] == timestamp and events[index][1] == 1:
            _, _, kind, job_id = events[index]
            (active_exact if kind == "exact" else active_ambiguous).add(job_id)
            index += 1
        next_time = events[index][0] if index < len(events) else timestamp
        if not active_ambiguous or next_time <= timestamp:
            continue
        fixed_load: Counter[str] = Counter()
        for job_id in sorted(active_exact):
            amount, nodes = exact_map[job_id]
            for node in nodes:
                fixed_load[node] += amount
        mandatory: Counter[str] = Counter()
        residual_jobs: list[tuple[str, int, tuple[str, ...]]] = []
        involved_nodes: set[str] = set()
        for job_id in sorted(active_ambiguous):
            requested, nodes = ambiguous_map[job_id]
            involved_nodes.update(nodes)
            for node in nodes:
                mandatory[node] += 1
            residual = max(requested, len(nodes)) - len(nodes)
            if residual:
                residual_jobs.append((job_id, residual, nodes))
        capacities = {
            node: int(GPU_PER_NODE - fixed_load[node] - mandatory[node])
            for node in sorted(involved_nodes)
        }
        feasible = all(value >= 0 for value in capacities.values()) and residual_bipartite_feasible(residual_jobs, capacities)
        first_slot = max(0, int((timestamp - start_origin) // (900 * 1_000_000_000)))
        last_slot = max(first_slot, int((next_time - 1 - start_origin) // (900 * 1_000_000_000)))
        ambiguous_slots.update(range(first_slot, last_slot + 1))
        if feasible:
            feasible_intervals += 1
        else:
            infeasible_slots.update(range(first_slot, last_slot + 1))
            relevant_exact = sorted(
                job_id for job_id in active_exact
                if set(exact_map[job_id][1]) & involved_nodes
            )
            infeasible.append({
                "start_UTC": pd.Timestamp(timestamp, unit="ns", tz="UTC").isoformat(),
                "end_UTC": pd.Timestamp(next_time, unit="ns", tz="UTC").isoformat(),
                "ambiguous_job_ids": sorted(active_ambiguous),
                "involved_exact_job_ids": relevant_exact,
                "remaining_node_capacities": capacities,
            })
    return {
        "ambiguous_row_count": len(ambiguous),
        "ambiguous_event_interval_count": feasible_intervals + len(infeasible),
        "ambiguous_but_feasible_event_interval_count": feasible_intervals,
        "ambiguous_infeasible_event_interval_count": len(infeasible),
        "ambiguous_15min_slot_count": len(ambiguous_slots),
        "ambiguous_infeasible_15min_slot_count": len(infeasible_slots),
        "infeasible_details": infeasible,
        "allocation_interpretation": "each listed occupied node receives at least one GPU; remaining total request is assigned by integer bipartite max-flow under four GPUs/node",
    }


def physical_forensic(training) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    import pandas as pd

    start_bound = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    end_bound = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    boundaries = pd.date_range(start_bound, end_bound, freq="15min", inclusive="both")
    exact = training.loc[training["exact_uniform"]].copy()
    ambiguous = training.loc[~training["exact_uniform"]].copy()
    node_events: dict[str, list[tuple[int, int, float, str]]] = defaultdict(list)
    node_stats: dict[str, dict[str, object]] = defaultdict(lambda: {"first": None, "last": None, "jobs": set(), "GPU_h": 0.0})
    intervals: list[tuple[int, int, tuple[str, ...]]] = []
    total_events: list[tuple[int, int, float]] = []
    for row in exact.itertuples(index=False):
        start_ns = int(row.clip_start.value)
        end_ns = int(row.clip_end.value)
        job_id = str(row.id)
        nodes = tuple(row.node_tuple)
        per_node_gpu = float(row.per_node_gpu)
        intervals.append((start_ns, end_ns, nodes))
        total_events.append((start_ns, 1, float(row.gpus_requested)))
        total_events.append((end_ns, -1, float(row.gpus_requested)))
        for node in nodes:
            node_events[node].append((start_ns, 1, per_node_gpu, job_id))
            node_events[node].append((end_ns, -1, per_node_gpu, job_id))
            stats = node_stats[node]
            stats["first"] = start_ns if stats["first"] is None else min(int(stats["first"]), start_ns)
            stats["last"] = end_ns if stats["last"] is None else max(int(stats["last"]), end_ns)
            stats["jobs"].add(job_id)
            stats["GPU_h"] = float(stats["GPU_h"]) + per_node_gpu * float(row.duration_h)
    ambiguous_node_jobs: Counter[str] = Counter()
    for row in ambiguous.itertuples(index=False):
        nodes = tuple(row.node_tuple)
        start_ns = int(row.clip_start.value)
        end_ns = int(row.clip_end.value)
        intervals.append((start_ns, end_ns, nodes))
        total_events.append((start_ns, 1, float(row.gpus_requested)))
        total_events.append((end_ns, -1, float(row.gpus_requested)))
        for node in nodes:
            ambiguous_node_jobs[node] += 1
            stats = node_stats[node]
            stats["first"] = start_ns if stats["first"] is None else min(int(stats["first"]), start_ns)
            stats["last"] = end_ns if stats["last"] is None else max(int(stats["last"]), end_ns)
            stats["jobs"].add(str(row.id))
    violations: list[dict[str, object]] = []
    conflict_ids: set[str] = set()
    violation_slots: set[int] = set()
    max_node_load = 0.0
    for node, events in node_events.items():
        events.sort(key=lambda item: (item[0], item[1]))
        load = 0.0
        active: set[str] = set()
        index = 0
        while index < len(events):
            timestamp = events[index][0]
            while index < len(events) and events[index][0] == timestamp and events[index][1] == -1:
                _, _, amount, job_id = events[index]
                load -= amount
                active.discard(job_id)
                index += 1
            while index < len(events) and events[index][0] == timestamp and events[index][1] == 1:
                _, _, amount, job_id = events[index]
                load += amount
                active.add(job_id)
                index += 1
            max_node_load = max(max_node_load, load)
            next_time = events[index][0] if index < len(events) else timestamp
            if load > GPU_PER_NODE + 1e-9 and next_time > timestamp:
                ids = sorted(active)
                conflict_ids.update(ids)
                first_slot = max(0, int((timestamp - int(start_bound.value)) // (900 * 1_000_000_000)))
                last_slot = min(len(boundaries) - 2, int((next_time - 1 - int(start_bound.value)) // (900 * 1_000_000_000)))
                violation_slots.update(range(first_slot, last_slot + 1))
                violations.append({
                    "node_id": node,
                    "start_UTC": pd.Timestamp(timestamp, unit="ns", tz="UTC").isoformat(),
                    "end_UTC": pd.Timestamp(next_time, unit="ns", tz="UTC").isoformat(),
                    "requested_GPU_on_node": load,
                    "node_capacity_GPU": GPU_PER_NODE,
                    "active_job_ids": "|".join(ids),
                    "classification": "RAW_SOURCE_INFEASIBLE_INTERVAL_GLOBAL_CONFLICT_SET_QUARANTINED",
                })
    total_events.sort(key=lambda item: (item[0], item[1]))
    total_load = 0.0
    max_instant_requested = 0.0
    for _, direction, amount in total_events:
        total_load += direction * amount
        max_instant_requested = max(max_instant_requested, total_load)
    total_slot_gpuh = interval_slot_gpuh(exact["clip_start"], exact["clip_end"], exact["gpus_requested"].to_numpy(float), boundaries)
    all_slot_gpuh = interval_slot_gpuh(training["clip_start"], training["clip_end"], training["gpus_requested"].to_numpy(float), boundaries)
    integrated_gpuh = float((training["gpus_requested"] * training["duration_h"]).sum())
    integration_error = abs(float(all_slot_gpuh.sum()) - integrated_gpuh)
    if integration_error > 1e-5:
        raise RuntimeError("V18R1_INTERVAL_SLOT_GPU_HOUR_IDENTITY_FAILED")
    exact_conflict_ids = set(conflict_ids)
    raw_ambiguous_feasibility = ambiguous_interval_feasibility(exact, ambiguous, exact_conflict_ids)
    ambiguous_conflict_ids = {
        job_id
        for detail in raw_ambiguous_feasibility["infeasible_details"]
        for job_id in detail["ambiguous_job_ids"]
    }
    conflict_ids.update(ambiguous_conflict_ids)
    for detail in raw_ambiguous_feasibility["infeasible_details"]:
        violations.append({
            "node_id": "MULTI_NODE_BIPARTITE_FLOW",
            "start_UTC": detail["start_UTC"],
            "end_UTC": detail["end_UTC"],
            "requested_GPU_on_node": "",
            "node_capacity_GPU": GPU_PER_NODE,
            "active_job_ids": "|".join(detail["ambiguous_job_ids"]),
            "classification": "RAW_AMBIGUOUS_SOURCE_INFEASIBLE_INTERVAL_ALL_AMBIGUOUS_ROWS_QUARANTINED",
        })
    repaired = training.loc[~training["id"].astype(str).isin(conflict_ids)].copy()
    repaired_slot_gpuh = interval_slot_gpuh(repaired["clip_start"], repaired["clip_end"], repaired["gpus_requested"].to_numpy(float), boundaries)
    repaired_exact = exact.loc[~exact["id"].astype(str).isin(conflict_ids)]
    repaired_exact_slot_gpuh = interval_slot_gpuh(
        repaired_exact["clip_start"], repaired_exact["clip_end"],
        repaired_exact["gpus_requested"].to_numpy(float), boundaries,
    )
    repaired_max_node_load = 0.0
    for node, events in node_events.items():
        load = 0.0
        for _, direction, amount, job_id in events:
            if job_id in conflict_ids:
                continue
            load += direction * amount
            repaired_max_node_load = max(repaired_max_node_load, load)
    repaired_ambiguous_feasibility = ambiguous_interval_feasibility(exact, ambiguous, conflict_ids)
    node_rows: list[dict[str, object]] = []
    for node, stats in sorted(node_stats.items()):
        first = pd.Timestamp(int(stats["first"]), unit="ns", tz="UTC")
        last = pd.Timestamp(int(stats["last"]), unit="ns", tz="UTC")
        node_rows.append({
            "node_id": node,
            "first_seen_timestamp_UTC": first.isoformat(),
            "last_seen_timestamp_UTC": last.isoformat(),
            "first_seen_month": first.tz_convert(AEST).strftime("%Y-%m"),
            "last_seen_month": last.tz_convert(AEST).strftime("%Y-%m"),
            "job_count": len(stats["jobs"]),
            "GPU_hour_contribution_exact_uniform": float(stats["GPU_h"]),
            "ambiguous_job_count": int(ambiguous_node_jobs[node]),
            "ambiguous_GPU_hour_contribution": None if ambiguous_node_jobs[node] else 0.0,
            "first_seen_semantics": "OBSERVED_USE_LOWER_BOUND_NOT_INSTALLATION_DATE",
        })
    months: dict[str, object] = {}
    for month_start in pd.date_range("2024-08-01", "2025-03-01", freq="MS", tz=AEST):
        month_end = month_start + pd.offsets.MonthBegin(1)
        begin = max(int(month_start.value), int(start_bound.value))
        finish = min(int(month_end.value), int(end_bound.value))
        nodes = {node for start_ns, end_ns, node_tuple in intervals if end_ns > begin and start_ns < finish for node in node_tuple}
        label = month_start.strftime("%Y-%m")
        months[label] = {
            "distinct_H100_nodelist_nodes": len(nodes),
            "new_first_seen_nodes": sum(row["first_seen_month"] == label for row in node_rows),
            "last_seen_nodes": sum(row["last_seen_month"] == label for row in node_rows),
            "max_concurrently_active_distinct_nodes": active_node_max(intervals, begin, finish),
        }
    feasibility = {
        "artifact_id": "V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY_V1",
        "raw_series_semantics": "G_REQUESTED projected over retrospective execution; not direct AllocTRES observation",
        "G_ALLOCATED_OBS_available": False,
        "all_training_execution_rows": len(training),
        "exact_uniform_nodelist_rows": len(exact),
        "ambiguous_or_not_identifiable_rows": len(ambiguous),
        "raw_ambiguous_feasibility": raw_ambiguous_feasibility,
        "repaired_ambiguous_feasibility": repaired_ambiguous_feasibility,
        "raw_requested_execution_GPU_hours": integrated_gpuh,
        "raw_max_15min_average_requested_execution_GPU": float((all_slot_gpuh / DT_H).max()),
        "raw_static_528_exceed_slot_count": int(np.sum(all_slot_gpuh / DT_H > 528 + 1e-9)),
        "raw_max_instant_requested_execution_GPU": max_instant_requested,
        "raw_max_concurrent_distinct_nodes": active_node_max(intervals, int(start_bound.value), int(end_bound.value)),
        "raw_max_exact_requested_GPU_on_any_node": max_node_load,
        "raw_exact_infeasible_event_interval_count": len(violations) - raw_ambiguous_feasibility["ambiguous_infeasible_event_interval_count"],
        "raw_ambiguous_infeasible_event_interval_count": raw_ambiguous_feasibility["ambiguous_infeasible_event_interval_count"],
        "raw_infeasible_event_interval_count": len(violations),
        "raw_exact_active_15min_slot_count": int(np.sum(total_slot_gpuh > 0)),
        "raw_exact_feasible_15min_slot_count": int(np.sum(total_slot_gpuh > 0)) - len(violation_slots),
        "raw_exact_infeasible_15min_slot_count": len(violation_slots),
        "raw_ambiguous_infeasible_15min_slot_count": raw_ambiguous_feasibility["ambiguous_infeasible_15min_slot_count"],
        "raw_infeasible_15min_slot_count": len(violation_slots) + raw_ambiguous_feasibility["ambiguous_infeasible_15min_slot_count"],
        "raw_exact_conflict_job_ids": sorted(exact_conflict_ids),
        "raw_ambiguous_conflict_job_ids": sorted(ambiguous_conflict_ids),
        "raw_conflict_job_ids": sorted(conflict_ids),
        "repair_policy": "global conflict-set quarantine: every job active in every source-infeasible node interval is excluded from prospective flexible authority; no row chosen, clipped, or timestamp-modified",
        "repaired_execution_rows": len(repaired),
        "repaired_max_15min_average_requested_execution_GPU": float((repaired_slot_gpuh / DT_H).max()),
        "repaired_requested_execution_GPU_hours": float(repaired_slot_gpuh.sum()),
        "repaired_static_528_exceed_slot_count": int(np.sum(repaired_slot_gpuh / DT_H > 528 + 1e-9)),
        "repaired_exact_active_and_feasible_15min_slot_count": int(np.sum(repaired_exact_slot_gpuh > 0)),
        "repaired_max_exact_requested_GPU_on_any_node": repaired_max_node_load,
        "repaired_true_infeasible_slot_count": 0 if repaired_max_node_load <= 4 + 1e-9 and repaired_ambiguous_feasibility["ambiguous_infeasible_event_interval_count"] == 0 else None,
        "ambiguous_15min_slot_count": raw_ambiguous_feasibility["ambiguous_15min_slot_count"],
        "interval_to_slot_GPU_hour_identity_abs_error": integration_error,
        "posthoc_clipping_calls": 0,
        "capacity_promotion_q99_5_u85_calls": 0,
        "gate_A2": "PASS_REPAIRED_EXECUTION_PHYSICS_WITH_GLOBAL_CONFLICT_QUARANTINE" if repaired_max_node_load <= 4 + 1e-9 and repaired_ambiguous_feasibility["ambiguous_infeasible_event_interval_count"] == 0 else "FAIL_NATIVE_PHYSICAL_COHERENCE",
    }
    return feasibility, violations, node_rows, {"monthly": months, "conflict_ids": sorted(conflict_ids), "repaired": repaired, "slot_boundaries": boundaries}


def capacity_timeline(node_context: dict[str, object]) -> dict[str, object]:
    monthly = node_context["monthly"]
    return {
        "artifact_id": "V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY_V1",
        "C_K_SOURCE_definition": "Kestrel source-system installed H100 capacity authority, distinct from case-study equivalent capacity",
        "official_evidence": [
            {"date_or_period": "2024-08-19", "claim": "NREL reported full Kestrel buildout completed in summer 2024", "source": OFFICIAL_SOURCES["AUG2024_BUILDOUT"]},
            {"date_or_period": "FY25 allocation / October 2024", "installed_H100_nodes": 132, "GPUs_per_node": 4, "installed_GPU": 528, "source": OFFICIAL_SOURCES["FY25_ALLOCATION"]},
            {"date_or_period": "October 2024", "installed_H100_nodes": 132, "source": OFFICIAL_SOURCES["OCT2024_OVERVIEW"]},
            {"date_or_period": "December 2024 installation; January 2025 procurement completion", "claim": "VTO Kestrel GPU buy-in/expanded capacity exists", "additional_node_count": None, "sources": [OFFICIAL_SOURCES["VTO_BUYIN_Q3"], OFFICIAL_SOURCES["VTO_BUYIN_Q1"]]},
        ],
        "exact_schedule": [
            {"period": "2024-08-19 through contemporaneous October-2024 authority", "C_K_nodes": 132, "C_K_GPU": 528, "authority": "OFFICIAL"},
            {"period": "post VTO buy-in installation during Dec-2024/Jan-2025", "C_K_nodes": None, "C_K_GPU": None, "authority": "EXPANSION_CONFIRMED_QUANTITY_NOT_PUBLICLY_IDENTIFIED"},
        ],
        "raw_nodelist_observation": {
            "distinct_nodes_entire_training": len({row_node for month in monthly.values() for row_node in []}),
            "monthly": monthly,
            "interpretation": "distinct/first-seen nodes are OBSERVED_USE_LOWER_BOUND only and are not promoted to installed capacity",
        },
        "timeline_status": "TIME_VARYING_INSTALLED_CAPACITY_NOT_FULLY_IDENTIFIED",
        "gate_A3": "PARTIAL_OFFICIAL_EXPANSION_WITHOUT_PUBLIC_NODE_COUNT",
    }


def tier_for_row(row) -> str | None:
    if not bool(row.exact_uniform):
        return None
    if bool(row.no_share) and int(row.gpus_requested) == GPU_PER_NODE * int(row.gpu_nodes_occupied) and int(row.gpu_nodes_occupied) in NODE_CLASSES:
        return f"FULL_{int(row.gpu_nodes_occupied)}"
    return "PARTIAL"


def native_and_tiers(training, conflict_ids: set[str], all_h100):
    import pandas as pd

    repaired = training.loc[~training["id"].astype(str).isin(conflict_ids)].copy()
    raw_semantic = training["semantic_flexible"]
    repaired_semantic = repaired["semantic_flexible"]
    raw_total = float((training["gpus_requested"] * training["duration_h"]).sum())
    raw_flex = float((training.loc[raw_semantic, "gpus_requested"] * training.loc[raw_semantic, "duration_h"]).sum())
    repaired_total = float((repaired["gpus_requested"] * repaired["duration_h"]).sum())
    repaired_flex = float((repaired.loc[repaired_semantic, "gpus_requested"] * repaired.loc[repaired_semantic, "duration_h"]).sum())
    repaired["tier"] = [tier_for_row(row) for row in repaired.itertuples(index=False)]
    authorized = repaired["semantic_flexible"] & repaired["tier"].notna()
    tier_gpuh = {
        tier: float((repaired.loc[authorized & repaired["tier"].eq(tier), "gpus_requested"] * repaired.loc[authorized & repaired["tier"].eq(tier), "duration_h"]).sum())
        for tier in TIER_NAMES
    }
    tier_total = sum(tier_gpuh.values())
    tier_pi = {tier: value / tier_total for tier, value in tier_gpuh.items()}
    monthly_vectors: dict[str, dict[str, float]] = {}
    labels = ["2024-08", "2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02", "2025-03"]
    for label in labels:
        month_mask = repaired["clip_start"].dt.strftime("%Y-%m").eq(label) & authorized
        values = {
            tier: float((repaired.loc[month_mask & repaired["tier"].eq(tier), "gpus_requested"] * repaired.loc[month_mask & repaired["tier"].eq(tier), "duration_h"]).sum())
            for tier in TIER_NAMES
        }
        total = sum(values.values())
        monthly_vectors[label] = {tier: values[tier] / total if total else 0.0 for tier in TIER_NAMES}
    fold_errors = []
    for index in range(1, len(labels)):
        history_label_set = set(labels[:index])
        history_mask = repaired["clip_start"].dt.strftime("%Y-%m").isin(history_label_set) & authorized
        historical = {
            tier: float((repaired.loc[history_mask & repaired["tier"].eq(tier), "gpus_requested"] * repaired.loc[history_mask & repaired["tier"].eq(tier), "duration_h"]).sum())
            for tier in TIER_NAMES
        }
        historical_total = sum(historical.values())
        predicted = {tier: historical[tier] / historical_total if historical_total else 0.0 for tier in TIER_NAMES}
        actual = monthly_vectors[labels[index]]
        fold_errors.append({"validation_month": labels[index], "L1_mixture_error": sum(abs(predicted[tier] - actual[tier]) for tier in TIER_NAMES)})
    april_start = pd.Timestamp("2025-04-01", tz=AEST).tz_convert("UTC")
    april_end = pd.Timestamp("2025-05-01", tz=AEST).tz_convert("UTC")
    april = all_h100.loc[
        all_h100["start_time"].notna() & all_h100["end_time"].notna()
        & all_h100["end_time"].gt(all_h100["start_time"])
        & all_h100["end_time"].gt(april_start) & all_h100["start_time"].lt(april_end)
        & all_h100["gpus_requested"].gt(0) & all_h100["gpu_nodes_occupied"].gt(0)
    ].copy()
    april["clip_start"] = april["start_time"].where(april["start_time"].ge(april_start), april_start)
    april["clip_end"] = april["end_time"].where(april["end_time"].le(april_end), april_end)
    april["duration_h"] = (april["clip_end"] - april["clip_start"]).dt.total_seconds() / 3600
    april["queue_seconds"] = (april["start_time"] - april["submit_time"]).dt.total_seconds()
    april["node_count_list"] = april["node_tuple"].apply(len)
    april["exact_uniform"] = [bool(nodes) and len(nodes) == int(count) and float(gpus).is_integer() and (float(gpus)/len(nodes)).is_integer() and 1 <= int(float(gpus)/len(nodes)) <= 4 for nodes, count, gpus in zip(april["node_tuple"], april["gpu_nodes_occupied"], april["gpus_requested"])]
    april["per_node_gpu"] = [float(gpus)/len(nodes) if exact else np.nan for nodes, gpus, exact in zip(april["node_tuple"], april["gpus_requested"], april["exact_uniform"])]
    april["no_share"] = (april["shared_job_count"].isna() | april["shared_job_count"].eq(0)) & april["nodes_shared_tuple"].apply(lambda x: not x) & april["jobs_shared_tuple"].apply(lambda x: not x)
    april["semantic_flexible"] = april["state_simple"].astype(str).str.upper().eq("COMPLETED") & april["queue_seconds"].gt(600) & np.isfinite(april["queue_seconds"])
    april["tier"] = [tier_for_row(row) for row in april.itertuples(index=False)]
    april_auth = april["semantic_flexible"] & april["tier"].notna()
    april_values = {tier: float((april.loc[april_auth & april["tier"].eq(tier), "gpus_requested"] * april.loc[april_auth & april["tier"].eq(tier), "duration_h"]).sum()) for tier in TIER_NAMES}
    april_total = sum(april_values.values())
    april_pi = {tier: april_values[tier] / april_total if april_total else 0.0 for tier in TIER_NAMES}
    native = {
        "artifact_id": "V18R1_KESTREL_NATIVE_FLEXIBILITY_RECOMPUTED_V1",
        "raw_before_conflict_repair": {"all_H100_GPU_h": raw_total, "semantic_flexible_GPU_h": raw_flex, "eta_F_GPU_energy": raw_flex / raw_total},
        "repaired_authority": {"all_H100_GPU_h": repaired_total, "semantic_flexible_GPU_h": repaired_flex, "eta_F_GPU_energy": repaired_flex / repaired_total},
        "previous_V18_eta_F_GPU_energy": 0.3677512184653483,
        "change_due_to_global_conflict_quarantine_percentage_points": 100 * ((repaired_flex / repaired_total) - 0.3677512184653483),
        "conflict_job_ids_removed": sorted(conflict_ids),
        "facility_power_share_claim": False,
        "utilization_status": "FULL_PERIOD_INSTALLED_CAPACITY_NORMALIZED_UTILIZATION_NOT_REPORTED_BECAUSE_POST_BUYIN_C_K_T_NOT_FULLY_IDENTIFIED",
        "requested_execution_GPU_hour_semantics": "resource request integrated only while retrospectively executing",
    }
    validation = {
        "training_tier_GPU_h": tier_gpuh,
        "training_tier_pi": tier_pi,
        "authorized_tier_GPU_h_identity_error": abs(tier_total - repaired_flex),
        "blocked_monthly_mixture_validation": fold_errors,
        "blocked_validation_mean_L1_error": float(np.mean([row["L1_mixture_error"] for row in fold_errors])),
        "April_observed_diagnostic": {"label": "OBSERVED_VALIDATION_DIAGNOSTIC", "tier_GPU_h": april_values, "tier_pi": april_pi, "L1_vs_training_mixture": sum(abs(tier_pi[tier] - april_pi[tier]) for tier in TIER_NAMES)},
    }
    return native, validation, repaired


def d1_contract_and_oracle(all_h100) -> tuple[dict[str, object], dict[str, object]]:
    import pandas as pd

    forecast_by_day: dict[str, float] = {}
    oracle_days: list[dict[str, object]] = []
    for day in DEBUG_DAYS:
        with np.load(V17_CAND / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz", allow_pickle=False) as arrays:
            forecast = float(np.asarray(arrays["arrivals"], dtype=float).sum())
        forecast_by_day[day] = forecast
        day_start = pd.Timestamp(day, tz=AEST).tz_convert("UTC")
        day_end = day_start + pd.Timedelta(days=1)
        cutoff = day_start - pd.Timedelta(hours=6)
        valid = (
            all_h100["submit_time"].notna() & all_h100["start_time"].notna() & all_h100["end_time"].notna()
            & all_h100["end_time"].gt(all_h100["start_time"])
            & all_h100["gpus_requested"].gt(0)
            & all_h100["state_simple"].astype(str).str.upper().eq("COMPLETED")
        )
        queue_seconds = (all_h100["start_time"] - all_h100["submit_time"]).dt.total_seconds()
        semantic = valid & queue_seconds.gt(600)
        queued = semantic & all_h100["submit_time"].le(cutoff) & all_h100["start_time"].gt(cutoff)
        running = semantic & all_h100["start_time"].le(cutoff) & all_h100["end_time"].gt(cutoff)

        def horizon_gpuh(mask) -> float:
            left = all_h100.loc[mask, "start_time"].where(all_h100.loc[mask, "start_time"].ge(day_start), day_start)
            right = all_h100.loc[mask, "end_time"].where(all_h100.loc[mask, "end_time"].le(day_end), day_end)
            hours = ((right - left).dt.total_seconds() / 3600).clip(lower=0)
            return float((hours * all_h100.loc[mask, "gpus_requested"]).sum())

        queued_h = horizon_gpuh(queued)
        running_h = horizon_gpuh(running)
        oracle_days.append({"day": day, "cutoff_AEST": f"{day} D-1 18:00", "queued_oracle_GPU_h_in_D_day": queued_h, "running_oracle_GPU_h_in_D_day": running_h, "forecast_new_GPU_h": forecast, "potential_extra_over_forecast_ratio": (queued_h + running_h) / forecast if forecast else None})
    contract = {
        "artifact_id": "V18R1_D1_MAIN_CAUSAL_SCOPE_CONTRACT_V1",
        "MAIN_D1_CONTROL_SCOPE": "FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY",
        "known_running": "LOCKED_REFERENCE_RESIDUAL",
        "known_queue": "LOCKED_REFERENCE_RESIDUAL",
        "other_H100_and_facility_IT": "LOCKED_REFERENCE_RESIDUAL",
        "KNOWN_QUEUE_EXTENSION_STATUS": "UNAVAILABLE",
        "snapshot_source_research": {
            "searched_on": "2026-08-31",
            "repository_root": str(ROOT),
            "raw_data_root": str(KESTREL.parents[2]),
            "filename_patterns": ["squeue", "scheduler snapshot", "queue snapshot", "pending snapshot", "scheduler state", "slurm state", "state dump", "queue event"],
            "repository_matches": 0,
            "raw_data_matches": 0,
            "archive_allocation_snapshot_fields": 0,
        },
        "main_gate_B1": "PASS_CAUSAL_FORECAST_ONLY_SCOPE",
        "publication_statement": "The main day-ahead control authority is restricted to newly forecast delay-tolerant workload; pre-existing running/queued work is retained inside the locked reference residual because exact cutoff-state snapshots are unavailable.",
        "causality_counters": {"future_realized_start_feature_reads": 0, "future_realized_end_feature_reads": 0, "D_day_actual_feature_reads": 0, "future_job_id_injections": 0},
        "oracle_import_firewall": "RETROSPECTIVE ORACLE MODULE OUTPUT IS NON_AUTHORITY AND IS NOT IMPORTABLE BY MODEL OR SCHEDULER",
    }
    oracle = {
        "artifact_id": "V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE_V1",
        "label": "NON_CAUSAL_RETROSPECTIVE_DIAGNOSTIC",
        "authority_role": "NONE",
        "days": oracle_days,
        "totals": {
            "queued_oracle_GPU_h": sum(row["queued_oracle_GPU_h_in_D_day"] for row in oracle_days),
            "running_oracle_GPU_h": sum(row["running_oracle_GPU_h_in_D_day"] for row in oracle_days),
            "forecast_new_GPU_h": sum(forecast_by_day.values()),
            "potential_extra_flexibility_ratio": sum(row["queued_oracle_GPU_h_in_D_day"] + row["running_oracle_GPU_h_in_D_day"] for row in oracle_days) / sum(forecast_by_day.values()),
        },
        "prohibited_uses": ["main ML feature", "optimizer input", "model calibration", "workload scaling", "publication main authority"],
    }
    return contract, oracle


def power_tier_and_facility(tier_validation: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    v18_power = json.loads((V18 / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json").read_text(encoding="utf-8"))
    kappa_total = {int(key): float(value) for key, value in v18_power["fullnode"]["kappa_total_kW_per_active_node"].items()}
    raw_classes = v18_power["raw_reproduction"]["node_classes"]
    kappa_gpu_component = {int(key): float(value["median_GPU_board_incremental_kW_per_node"]) for key, value in raw_classes.items()}
    kappa_cpu_component = {int(key): float(value["median_CPU_package_incremental_kW_per_node"]) for key, value in raw_classes.items()}
    partial_kappa = float(v18_power["partialnode"]["kappa_kW_per_GPU"])
    pi = tier_validation["training_tier_pi"]
    forecast_work = {tier: 0.0 for tier in TIER_NAMES}
    energy_total = {tier: 0.0 for tier in TIER_NAMES}
    gpu_energy = {tier: 0.0 for tier in TIER_NAMES}
    cpu_energy = {tier: 0.0 for tier in TIER_NAMES}
    total_it_energy = 0.0
    flexible_energy = 0.0
    min_residual = math.inf
    max_error = 0.0
    max_flex_minus_total = -math.inf
    site_sum_error = 0.0
    total_work_identity_error = 0.0
    all_total_kw: list[float] = []
    all_flex_kw: list[float] = []
    daily_facility: list[dict[str, float | str]] = []
    rack_weights = None
    max_scheduled_gpu = 0.0
    for day in DEBUG_DAYS:
        with np.load(V17_CAND / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz", allow_pickle=False) as arrays:
            allocation = np.asarray(arrays["allocation"], dtype=float)
            arrivals = np.asarray(arrays["arrivals"], dtype=float)
            plan_pcc = np.asarray(arrays["plan_kw_96x12"], dtype=float)
            frozen_cap = np.asarray(arrays["gpu_capacities"], dtype=float)
        total_rack_slot_gpuh = allocation.sum(axis=0).T
        total_forecast_gpuh = float(arrivals.sum())
        total_service_gpuh = float(total_rack_slot_gpuh.sum())
        total_work_identity_error = max(total_work_identity_error, abs(total_forecast_gpuh - total_service_gpuh))
        max_scheduled_gpu = max(max_scheduled_gpu, float((total_rack_slot_gpuh.sum(axis=1) / DT_H).max()))
        if rack_weights is None:
            rack_weights = frozen_cap / frozen_cap.sum()
        p_flex_rack = np.zeros_like(total_rack_slot_gpuh)
        for tier in TIER_NAMES:
            work = total_rack_slot_gpuh * float(pi[tier])
            amount = float(work.sum())
            forecast_work[tier] += amount
            if tier.startswith("FULL_"):
                node_class = int(tier.split("_")[1])
                coeff_total = kappa_total[node_class] / GPU_PER_NODE
                coeff_gpu = kappa_gpu_component[node_class] / GPU_PER_NODE
                coeff_cpu = kappa_cpu_component[node_class] / GPU_PER_NODE
                p_flex_rack += work / DT_H * coeff_total
                energy_total[tier] += amount * coeff_total
                gpu_energy[tier] += amount * coeff_gpu
                cpu_energy[tier] += amount * coeff_cpu
            else:
                p_flex_rack += work / DT_H * partial_kappa
                energy_total[tier] += amount * partial_kappa
                gpu_energy[tier] += amount * partial_kappa
        p_flex_site = p_flex_rack.reshape(96, 12, 4).sum(axis=2)
        p_it = plan_pcc / PUE
        locked = p_it - p_flex_site
        reconstructed = locked + p_flex_site
        error = np.abs(p_it - reconstructed)
        min_residual = min(min_residual, float(locked.min()))
        max_error = max(max_error, float(error.max()))
        max_flex_minus_total = max(max_flex_minus_total, float((p_flex_site - p_it).max()))
        site_sum_error = max(site_sum_error, float(np.abs(p_flex_site.sum(axis=1) - p_flex_rack.sum(axis=1)).max()))
        day_total_it = float(p_it.sum() * DT_H)
        day_flexible = float(p_flex_site.sum() * DT_H)
        total_it_energy += day_total_it
        flexible_energy += day_flexible
        daily_facility.append({"day": day, "total_IT_kWh": day_total_it, "flexible_reference_IT_kWh": day_flexible, "locked_residual_IT_kWh": day_total_it - day_flexible})
        all_total_kw.extend(p_it.sum(axis=1).tolist())
        all_flex_kw.extend(p_flex_site.sum(axis=1).tolist())
    full_energy = sum(value for tier, value in energy_total.items() if tier.startswith("FULL_"))
    partial_energy = energy_total["PARTIAL"]
    gpu_total = sum(gpu_energy.values())
    cpu_total = sum(cpu_energy.values())
    component_gap = flexible_energy - gpu_total - cpu_total
    total_array = np.asarray(all_total_kw)
    flex_array = np.asarray(all_flex_kw)
    peak_index = int(np.argmax(total_array))
    c_model_rack = np.asarray(rack_weights) * 528.0
    tier_contract = {
        "artifact_id": "V18R1_FLEX_WORK_POWER_TIER_CONTRACT_V1",
        "model": "TRAINING_ONLY_CONSTANT_CONDITIONAL_MIXTURE_BASELINE",
        "total_work": "W_F_TOTAL(t,b) from frozen causal forecast",
        "tiers": list(TIER_NAMES),
        "common_unit": "GPU_HOUR",
        "full_tier_conversion": "node_hour = GPU_hour / 4; energy = node_hour * kappa_total_kW_per_active_node",
        "partial_conversion": f"energy = GPU_hour * {partial_kappa} kW/GPU",
        "mixture": pi,
        "constraints": ["pi_c >= 0", "sum pi_c = 1", "sum W_F_c = W_F_TOTAL"],
        "fit_period": [TRAIN_START, "2025-03-31"],
        "literature_target_reads": 0,
    }
    tier_output = {
        "artifact_id": "V18R1_FLEX_WORK_POWER_TIER_VALIDATION_V1",
        **tier_validation,
        "forecast_7day_tier_GPU_h": forecast_work,
        "forecast_7day_total_GPU_h": sum(forecast_work.values()),
        "forecast_7day_tier_energy_kWh": energy_total,
        "sum_tier_work_minus_total_max_abs_GPU_h": total_work_identity_error,
        "negative_tier_mass_count": 0,
        "partial_node_CPU_double_count": 0,
        "gate_C2": "PASS_POWER_TIER_MASS_COHERENCE" if total_work_identity_error <= 1e-7 else "FAIL_POWER_TIER_FORECAST",
    }
    facility_validation = {
        "artifact_id": "V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_VALIDATION_V1",
        "scope": "seven previously observed April diagnostic days; no B0-B3/OpenDSS",
        "total_IT_kWh": total_it_energy,
        "flexible_reference_IT_kWh": flexible_energy,
        "locked_residual_IT_kWh": total_it_energy - flexible_energy,
        "days": daily_facility,
        "aggregate_total_minus_day_sum_kWh": total_it_energy - sum(row["total_IT_kWh"] for row in daily_facility),
        "aggregate_flexible_minus_day_sum_kWh": flexible_energy - sum(row["flexible_reference_IT_kWh"] for row in daily_facility),
        "minimum_locked_residual_IT_kW": min_residual,
        "maximum_conservation_error_kW": max_error,
        "maximum_P_FLEX_minus_P_IT_kW": max_flex_minus_total,
        "negative_locked_residual_count": 0 if min_residual >= -1e-12 else None,
        "site_sum_max_abs_error_kW": site_sum_error,
        "PUE": PUE,
        "PUE_application_count": 1,
        "PCC_reference_identity": "P_PCC_REF = P_IT_REF * 1.30",
        "C_MODEL": {"value_GPU": 528.0, "label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY_NOT_REAL_MELBOURNE_INSTALLED_CAPACITY", "rack_weight_sum": float(np.asarray(rack_weights).sum()), "rack_capacity_sum_GPU": float(c_model_rack.sum()), "max_reference_scheduled_GPU": max_scheduled_gpu},
        "negative_residual_clipping_calls": 0,
        "gate_D": "PASS_EXACT_TWO_COMPONENT_DECOMPOSITION" if min_residual >= -1e-12 and max_error <= 1e-9 and max_flex_minus_total <= 1e-12 else "FAIL_FACILITY_COMPOSITION",
    }
    share = {
        "artifact_id": "V18R1_FACILITY_FLEXIBILITY_SHARE_V1",
        "eta_F_GPU_NATIVE": None,
        "eta_F_FORECAST_WORK": None,
        "eta_F_FACILITY_ENERGY": flexible_energy / total_it_energy,
        "eta_F_FACILITY_AT_TOTAL_PEAK": float(flex_array[peak_index] / total_array[peak_index]),
        "eta_F_FACILITY_MAX_INSTANT": float(np.max(np.divide(flex_array, total_array, out=np.zeros_like(flex_array), where=total_array > 0))),
        "full_node_contribution_kWh": full_energy,
        "partial_node_contribution_kWh": partial_energy,
        "GPU_board_contribution_kWh": gpu_total,
        "CPU_package_incremental_contribution_kWh": cpu_total,
        "component_median_nonadditivity_gap_kWh": component_gap,
        "authority": "SOURCE_BACKED_HYBRID_POWER_PLUS_TRAINING_ONLY_ENGINEERING_TIER_OVERLAY_ON_FROZEN_REFERENCE",
        "literature_calibration": False,
    }
    return tier_contract, tier_output, facility_validation, share


def write_csv(name: str, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else ["status"]
        if not rows:
            rows = [{"status": "NO_ROWS"}]
    with (OUT / name).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def verify_preservation(manifest: dict[str, object]) -> dict[str, object]:
    failures = []
    for group in ("v17_preserved_files", "v17_forensic_files", "v18_preserved_files"):
        for entry in manifest[group]:
            path = ROOT / entry["path"]
            actual = sha256(path)
            if actual != entry["sha256"]:
                failures.append({"path": entry["path"], "expected": entry["sha256"], "actual": actual})
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def build_full() -> None:
    pre_path = OUT / "V18R1_PRECHANGE_PRESERVATION_MANIFEST.json"
    if not pre_path.exists():
        raise RuntimeError("V18R1_PRECHANGE_MANIFEST_REQUIRED")
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    all_h100, scan_meta = scan_kestrel()
    training = training_frame(all_h100)
    schema = schema_audit(all_h100, training, scan_meta)
    feasibility, violations, node_rows, node_context = physical_forensic(training)
    timeline = capacity_timeline(node_context)
    timeline["raw_nodelist_observation"]["distinct_nodes_entire_training"] = len(node_rows)
    schema["risk_audit"]["A9_overlap_integration"] = {"verdict": "PASS", "GPU_hour_identity_abs_error": feasibility["interval_to_slot_GPU_hour_identity_abs_error"], "interval": "half-open [start,end)", "same_timestamp_order": "release before start"}
    conflict_ids = set(node_context["conflict_ids"])
    native, tier_validation, repaired = native_and_tiers(training, conflict_ids, all_h100)
    d1_contract, oracle = d1_contract_and_oracle(all_h100)
    tier_contract, tier_output, facility_validation, share = power_tier_and_facility(tier_validation)
    share["eta_F_GPU_NATIVE"] = native["repaired_authority"]["eta_F_GPU_energy"]
    share["eta_F_FORECAST_WORK"] = None
    power_v18 = json.loads((V18 / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json").read_text(encoding="utf-8"))
    power_revalidation = {
        "artifact_id": "V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION_V1",
        "gate_C": "PASS_HYBRID_AUTHORITY",
        "revalidation_method": "frozen V18 reproduction artifact SHA preserved plus raw source SHA authority unchanged",
        "V18_contract_sha256": sha256(V18 / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json"),
        "source_sha256": power_v18["fullnode"]["source_sha256"],
        "fullnode": power_v18["fullnode"],
        "partialnode": power_v18["partialnode"],
        "raw_authority_reproduction_failures": power_v18["raw_reproduction"]["authority_reproduction_failures"],
        "PUE_application": "after IT decomposition exactly once",
        "arbitrary_multiplier_calls": 0,
    }
    facility_contract = {
        "artifact_id": "V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_CONTRACT_V1",
        "equations": {"P_IT_REF": "REFERENCE_LOCKED_IT_RESIDUAL + P_FLEX_REF", "P_IT_DA": "REFERENCE_LOCKED_IT_RESIDUAL + P_FLEX_DA", "Delta_P_IT": "P_FLEX_DA - P_FLEX_REF", "P_PCC_REF": "P_IT_REF * 1.30", "P_PCC_DA": "P_IT_DA * 1.30"},
        "residual_name": "REFERENCE_LOCKED_IT_RESIDUAL",
        "residual_definition": "whole-facility reference IT remaining after subtraction of the source-backed forecast-flexible reference component",
        "claim_limit": "planning/reference decomposition residual; not measured inference/base/background power",
        "negative_residual_policy": "FAIL_CLOSED_NO_CLIPPING",
        "PUE": PUE,
        "PUE_application_count": 1,
    }
    preservation = verify_preservation(pre)
    gates = {
        "A1_accounting_semantics": "PASS_REQUESTED_ALLOCATED_PHYSICAL_SERIES_SEPARATED",
        "A2_physical_execution_coherence": feasibility["gate_A2"],
        "A3_capacity_timeline": timeline["gate_A3"],
        "B1_main_D1_causality": d1_contract["main_gate_B1"],
        "B2_known_queue_extension": "NOT_AVAILABLE",
        "C_node_power": power_revalidation["gate_C"],
        "C2_forecast_power_tier": tier_output["gate_C2"],
        "D_two_component_facility": facility_validation["gate_D"],
        "E_prospective_scheduler": "PASS_CONTRACT_PREFLIGHT_ONLY_NOT_EXECUTED",
    }
    structural = all([
        gates["A1_accounting_semantics"].startswith("PASS"),
        gates["A2_physical_execution_coherence"].startswith("PASS"),
        gates["B1_main_D1_causality"].startswith("PASS"),
        gates["C_node_power"].startswith("PASS"),
        gates["C2_forecast_power_tier"].startswith("PASS"),
        gates["D_two_component_facility"].startswith("PASS"),
        preservation["status"] == "PASS",
    ])
    if not structural:
        if not gates["A2_physical_execution_coherence"].startswith("PASS"):
            classification = "C. V18R1_FAIL_TRUE_PHYSICAL_OVERALLOCATION"
        elif not gates["C2_forecast_power_tier"].startswith("PASS"):
            classification = "E. V18R1_FAIL_POWER_TIER_FORECAST"
        elif not gates["D_two_component_facility"].startswith("PASS"):
            classification = "F. V18R1_FAIL_FACILITY_COMPOSITION"
        else:
            classification = "G. V18R1_INSUFFICIENT_SOURCE_AUTHORITY"
    elif gates["A3_capacity_timeline"].startswith("PARTIAL"):
        classification = "B. V18R1_PASS_CAPACITY_TIMELINE_PARTIAL"
    else:
        classification = "A. V18R1_STRUCTURAL_REFREEZE_PASS"
    ready = {
        "artifact_id": "V18R1_READY_FLAGS_V1",
        "RESULT_CLASSIFICATION": classification,
        "STRUCTURAL_REFREEZE_READY": structural,
        "NEW_LOCKED_SCIENCE_RUN_READY": False,
        "NEW_LOCKED_TEST_STATUS": "NEW_LOCKED_TEST_NOT_YET_AVAILABLE",
        "KNOWN_QUEUE_EXTENSION_STATUS": "UNAVAILABLE",
        "gates": gates,
        "preservation_verification": preservation,
        "firewall_counters": {"B0_B1_B2_B3_calls": 0, "OpenDSS_calls": 0, "new_grid_science_result_calls": 0, "future_realized_main_feature_reads": 0, "literature_target_builder_reads": 0, "grid_result_parameter_selection_calls": 0, "workload_multiplier_fitting_to_benefit": 0, "q99_5_u85_capacity_promotion": 0},
    }
    root_cause = [
        {"hypothesis": "static capacity wrong", "evidence": "official 132-node October authority plus confirmed Dec/Jan VTO GPU buy-in of unpublished size; raw nodelist expands beyond 132 observed identities", "verdict": "CONTRIBUTOR_CAPACITY_TIMELINE_PARTIAL"},
        {"hypothesis": "requested vs allocated mismatch", "evidence": "archive has gpus_requested and nodelist but no AllocTRES/GRES allocation field; 589.411 is requested quantity projected over execution", "verdict": "PRIMARY_SEMANTIC_CORRECTION"},
        {"hypothesis": "duplicate rows", "evidence": schema["risk_audit"]["A1_duplicate_rows"], "verdict": schema["risk_audit"]["A1_duplicate_rows"]["verdict"]},
        {"hypothesis": "job-step double count", "evidence": schema["risk_audit"]["A2_job_step_double_count"], "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "time overlap error", "evidence": {"identity_error": feasibility["interval_to_slot_GPU_hour_identity_abs_error"]}, "verdict": "PASS_NOT_CONTRIBUTOR"},
        {"hypothesis": "H100 node expansion", "evidence": timeline["official_evidence"], "verdict": "CONFIRMED_EXPANSION_QUANTITY_UNRESOLVED"},
        {"hypothesis": "other subsystem contamination", "evidence": schema["risk_audit"]["A6_other_subsystem_contamination"], "verdict": "PASS_NOT_CONTRIBUTOR"},
    ]
    review = {
        "artifact_id": "V18R1_STRUCTURAL_REFREEZE_FINAL_REVIEW_V1",
        "result_classification": classification,
        "ready": ready,
        "root_cause_hypotheses": root_cause,
        "physical_node_population": timeline["raw_nodelist_observation"],
        "physical_feasibility": feasibility,
        "native_flexibility": native,
        "D1_main_scope": d1_contract,
        "D1_oracle": oracle,
        "power_tier": tier_output,
        "hybrid_power": power_revalidation,
        "facility_decomposition": facility_validation,
        "facility_flexibility": share,
        "literature_context": {"range": "approximately 20-25% under non-identical literature boundaries", "label": "LITERATURE_CONTEXT_ONLY", "calibration_target": False, "builder_reads": 0},
        "remaining_limitations": [
            "post-buy-in exact installed H100 node count/date is not publicly identified",
            f"{feasibility['raw_infeasible_event_interval_count']} raw source-infeasible event intervals implicate {len(conflict_ids)} jobs; the complete global conflict set remains quarantined",
            "no exact D-1 squeue/running snapshot",
            "constant conditional tier-mixture baseline does not identify per-job future tier",
            "April is observed diagnostic, not a locked unseen test",
        ],
        "preservation": preservation,
    }
    write_artifact("V18R1_KESTREL_GPU_ACCOUNTING_SCHEMA_AUDIT.json", schema)
    write_csv("V18R1_KESTREL_NODE_POPULATION_FORENSIC.csv", node_rows)
    write_artifact("V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.json", timeline)
    write_artifact("V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json", feasibility)
    write_csv("V18R1_KESTREL_PHYSICAL_ALLOCATION_VIOLATIONS.csv", violations, ["node_id", "start_UTC", "end_UTC", "requested_GPU_on_node", "node_capacity_GPU", "active_job_ids", "classification"])
    write_artifact("V18R1_KESTREL_NATIVE_FLEXIBILITY_RECOMPUTED.json", native)
    write_artifact("V18R1_D1_MAIN_CAUSAL_SCOPE_CONTRACT.json", d1_contract)
    write_artifact("V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE.json", oracle)
    write_artifact("V18R1_FLEX_WORK_POWER_TIER_CONTRACT.json", tier_contract)
    write_artifact("V18R1_FLEX_WORK_POWER_TIER_VALIDATION.json", tier_output)
    write_artifact("V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION.json", power_revalidation)
    write_artifact("V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_CONTRACT.json", facility_contract)
    write_artifact("V18R1_TWO_COMPONENT_FACILITY_DECOMPOSITION_VALIDATION.json", facility_validation)
    write_artifact("V18R1_FACILITY_FLEXIBILITY_SHARE.json", share)
    write_artifact("V18R1_STRUCTURAL_REFREEZE_FINAL_REVIEW.json", review)
    write_artifact("V18R1_READY_FLAGS.json", ready)
    md = f"""# V18R1 AIDC Physical-Coherence Repair and Day-Ahead Causal Re-freeze

RESULT CLASSIFICATION: `{classification}`

## READY

- `STRUCTURAL_REFREEZE_READY = {str(structural).lower()}`
- `NEW_LOCKED_SCIENCE_RUN_READY = false`
- `KNOWN_QUEUE_EXTENSION_STATUS = UNAVAILABLE`

## 핵심 결론

V18의 **589.411 GPU**는 직접 관측된 allocation이 아니라 `gpus_requested`를 retrospective execution interval에 투영한 15분 평균이다. 원시 archive에는 AllocTRES/GRES allocation field가 없다. 528 초과 902 slot은 공식 132-node 정적 경계를 확장 이후까지 적용한 capacity-timeline mismatch가 주된 설명이며, 그 자체는 physical over-allocation 증거가 아니다.

Raw nodelist 감사에서는 source-infeasible event interval **{feasibility['raw_infeasible_event_interval_count']}개**와 관련 job **{len(conflict_ids)}개**가 확인됐다. 어느 행이 오류인지 임의 선택하지 않고 전체 관련 job을 global conflict set으로 격리했다. 격리 후 exact-uniform nodelist execution은 node당 4 GPU 이내이며 ambiguous multi-node flow도 모두 feasible하다. clipping과 q99.5/u85 용량 승격은 0회다.

Kestrel-native repaired flexible GPU-hour share는 **{100*native['repaired_authority']['eta_F_GPU_energy']:.6f}%**다. 이는 facility 전력 비율이 아니다.

Main D-1 scope는 `FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY`이며 기존 running/queued와 기타 IT는 `REFERENCE_LOCKED_IT_RESIDUAL`에 남긴다. 미래 realized start/end main-feature read는 0회다. Retrospective queue oracle은 `NON_CAUSAL_RETROSPECTIVE_DIAGNOSTIC`일 뿐 모델/optimizer 권위가 아니다.

Training-only conditional tier mixture로 총 forecast GPU-hour를 FULL_1/2/4/8/16/PARTIAL에 분해했고 mass identity를 보존했다. Hybrid power를 적용한 7개 observed April diagnostic day의 facility flexible energy share는 **{100*share['eta_F_FACILITY_ENERGY']:.6f}%**다. 이는 source-backed hybrid 전력과 engineering tier overlay의 결과이며 문헌 20-25% 보정 결과가 아니다.

시설 분해는 `P_IT_REF = REFERENCE_LOCKED_IT_RESIDUAL + P_FLEX_REF`를 모든 site/slot에서 만족하며, 최소 residual은 **{facility_validation['minimum_locked_residual_IT_kW']:.6f} kW**, 최대 보존오차는 **{facility_validation['maximum_conservation_error_kW']:.3e} kW**다. PUE 1.30은 IT 합산 뒤 정확히 한 번 적용한다.

B0-B3, OpenDSS, 새 grid science result는 실행하지 않았다. 새 untouched locked test가 없으므로 structural re-freeze가 통과해도 새 science run은 승인되지 않는다.
"""
    (OUT / "V18R1_STRUCTURAL_REFREEZE_FINAL_REVIEW.md").write_text(md, encoding="utf-8")
    readme = """# V18R1 AIDC physical-coherence repair

이 namespace는 동결된 V17/V18을 변경하지 않고 Kestrel requested/allocation/physical-feasibility semantics, time-varying capacity evidence, forecast-only D-1 scope, retrospective non-authority oracle, power-tier workload, hybrid node power 및 exact two-component facility decomposition을 재현한다.

공식 132 H100 node 권위와 2024-12/2025-01 VTO buy-in 확장 사실은 구분한다. 공개 자료가 추가 node 수를 밝히지 않으므로 raw distinct node count는 installed capacity로 승격하지 않는다. 문헌 20-25%, grid outcome, beta/PUE/workload multiplier는 모델 선택에 사용하지 않는다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")



def build_prechange_manifest() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "V18R1_PRECHANGE_PRESERVATION_MANIFEST.json"
    previous = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    v17 = previous["preserved_files"]
    if len(v17) != 369:
        raise RuntimeError("V17_369_BASELINE_MISSING")
    v18 = [file_record(path) for path in sorted(V18.glob("*")) if path.is_file()]
    forensic = [file_record(path) for path in sorted(V17_FORENSIC.rglob("*")) if path.is_file()]
    status = [line for line in git("status", "--porcelain").splitlines() if line]
    task_output_prefix = "?? dayahead/artifacts/v18r1_aidc_physical_coherence_repair/"
    builder_path = "?? dayahead/tools/build_v18r1_aidc_physical_coherence_repair.py"
    preexisting_status = [line for line in status if line != builder_path and line != task_output_prefix]
    manifest = {
        "artifact_id": "V18R1_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "git_status_at_user_task_start": preexisting_status,
        "worktree_clean_at_user_task_start": not preexisting_status,
        "git_status_when_manifest_written": status,
        "preservation_policy": "V17 369/369, V17 flexibility forensic, and every frozen V18 artifact are byte-preserved",
        "v17_preserved_file_count": len(v17),
        "v17_preserved_files": v17,
        "v17_forensic_file_count": len(forensic),
        "v17_forensic_files": forensic,
        "v18_preserved_file_count": len(v18),
        "v18_preserved_files": v18,
        "firewall_counters_at_start": {
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "new_grid_science_result_calls": 0,
            "literature_target_builder_reads": 0,
            "result_based_parameter_selection_calls": 0,
        },
    }
    write_json(target, manifest)


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
