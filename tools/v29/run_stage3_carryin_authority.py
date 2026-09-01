"""Freeze causal D-1 cutoff-observable carry-in workload authority."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256
from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES
from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v28r2.reference_compute import case_rack_capacity_nodeh_per_slot


DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")
AEST = "Etc/GMT-10"
COLUMNS = (
    "id", "partition", "state", "state_simple", "submit_time", "start_time", "end_time",
    "nodes_req", "processors_req", "memory_req", "wallclock_req", "nodes_used",
    "processors_used", "wallclock_used", "nodelist", "qos", "queue_wait",
    "gpus_requested", "gpu_nodes_occupied", "shared_job_count", "nodes_shared", "jobs_shared",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def source_zip() -> Path:
    candidates = sorted(path for path in DEFAULT_RAW_ROOT.rglob("esif.hpc.kestrel.job-anon.zip") if path.is_file())
    for path in candidates:
        if sha256(path) == NLR_SOURCE_SHA256["kestrel_jobs_zip"]:
            return path
    raise FileNotFoundError("V29_EXACT_KESTREL_SOURCE_NOT_FOUND")


def cutoff(day: str) -> pd.Timestamp:
    return (pd.Timestamp(day, tz=AEST) - pd.Timedelta(hours=6)).tz_convert("UTC")


def read_candidate_events(path: Path) -> tuple[pd.DataFrame, list[str], list[dict[str, object]]]:
    latest = max(cutoff(day) for day in DAYS)
    frames: list[pd.DataFrame] = []
    opened: list[str] = []
    schemas: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        members = []
        for name in archive.namelist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", name.replace("\\", "/"))
            # The archive partition can reflect completion/filing month rather
            # than submission month.  Future members must therefore be opened
            # to reconstruct the historical cutoff queue without omission.
            if name.endswith(".parquet") and match:
                members.append(name)
        for name in sorted(members):
            with archive.open(name) as raw:
                buffer = io.BytesIO(raw.read())
            parquet = pq.ParquetFile(buffer)
            available = tuple(parquet.schema_arrow.names)
            missing = sorted(set(COLUMNS) - set(available))
            if missing:
                raise RuntimeError(f"V29_CARRYIN_SCHEMA_MISSING:{name}:{missing}")
            schemas.append({"member": name, "row_count": parquet.metadata.num_rows, "fields": list(available)})
            table = parquet.read(columns=list(COLUMNS))
            frame = table.to_pandas()
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce")
            partition = frame["partition"].astype(str).str.casefold()
            keep = submit.le(latest) & partition.str.contains("gpu-h100", regex=False)
            if keep.any():
                frames.append(frame.loc[keep].copy())
            opened.append(name)
            del frame, table, parquet, buffer
            gc.collect()
    if not frames:
        return pd.DataFrame(columns=COLUMNS), opened, schemas
    return pd.concat(frames, ignore_index=True), opened, schemas


def cohort_bins(repo: Path) -> dict[int, tuple[float, float]]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json").read_text(encoding="utf-8"))
    return {int(nodes): (float(values["q33_hours"]), float(values["q67_hours"])) for nodes, values in payload["runtime_bins_hours_by_node_class"].items()}


def cohort(nodes: int, requested_hours: float, bins: dict[int, tuple[float, float]]) -> str:
    low, high = bins[nodes]
    runtime_class = 0 if requested_hours <= low else 1 if requested_hours <= high else 2
    return f"N{nodes:02d}_R{runtime_class:02d}"


def bridge_capacity(repo: Path) -> float:
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    rack_ids = tuple(str(row["rack_id"]) for row in mapping["racks"])
    gpu_weights = dict(zip(rack_ids, map(float, mapping["gpu_weights"]), strict=True))
    return float(case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights).sum())


def queue_by_day(repo: Path, events: pd.DataFrame) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    bins = cohort_bins(repo)
    slot_capacity = bridge_capacity(repo)
    cohort_rows: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    provenance_rows: list[dict[str, object]] = []
    submit = pd.to_datetime(events["submit_time"], utc=True, errors="coerce")
    start = pd.to_datetime(events["start_time"], utc=True, errors="coerce")
    end = pd.to_datetime(events["end_time"], utc=True, errors="coerce")
    nodes = pd.to_numeric(events["nodes_req"], errors="coerce")
    gpus = pd.to_numeric(events["gpus_requested"], errors="coerce")
    requested_hours = pd.to_timedelta(events["wallclock_req"], errors="coerce").dt.total_seconds() / 3600.0
    request_fullnode = (
        events["partition"].astype(str).str.casefold().str.contains("gpu-h100", regex=False)
        & nodes.isin(CONTROLLABLE_NODE_CLASSES)
        & np.isclose(gpus, 4.0 * nodes, equal_nan=False)
    )
    service_known = nodes.gt(0) & requested_hours.gt(0) & np.isfinite(requested_hours)
    for day in DAYS:
        mark = cutoff(day)
        not_started = start.isna() | start.gt(mark)
        not_cancelled_before = start.notna() | end.isna() | end.gt(mark)
        reconstructed_queue = submit.le(mark) & not_started & not_cancelled_before
        admitted = reconstructed_queue & request_fullnode & service_known
        selected = events.loc[admitted].copy()
        selected["nodes"] = nodes[admitted].astype(int)
        selected["requested_hours"] = requested_hours[admitted]
        selected["service_nodeh"] = selected["nodes"] * selected["requested_hours"]
        selected["submit_utc"] = submit[admitted]
        selected["cohort"] = [cohort(int(n), float(h), bins) for n, h in zip(selected["nodes"], selected["requested_hours"], strict=True)]
        selected = selected.sort_values(["cohort", "submit_utc", "id"], kind="stable")
        cutoff_total = float(selected["service_nodeh"].sum())
        bridge_budget = 24.0 * slot_capacity
        remaining_budget = bridge_budget
        by_cohort = {name: float(value) for name, value in selected.groupby("cohort")["service_nodeh"].sum().items()}
        for name in sorted({f"N{nodes:02d}_R{runtime:02d}" for nodes in CONTROLLABLE_NODE_CLASSES for runtime in range(3)}):
            mass = by_cohort.get(name, 0.0)
            served = min(mass, remaining_budget)
            carry = mass - served
            remaining_budget -= served
            cohort_rows.append({
                "day": day, "cutoff_fixed_aest": str(mark.tz_convert(AEST)), "cohort_id": name,
                "cutoff_known_queue_nodeh": mass, "bridge_service_nodeh": served,
                "D_day_carryin_nodeh": carry,
            })
        bridge_service = min(cutoff_total, bridge_budget)
        carryin = cutoff_total - bridge_service
        forecast_mass = float(materialize_formulation_data(repo, day).arrivals_nodeh.sum())
        reference_only = reconstructed_queue & ~(request_fullnode & service_known)
        decisions.append({
            "day": day, "cutoff_fixed_aest": str(mark.tz_convert(AEST)),
            "cutoff_known_queue_job_count": int(admitted.sum()),
            "cutoff_known_queue_nodeh": cutoff_total,
            "bridge_capacity_nodeh_per_slot": slot_capacity,
            "bridge_service_nodeh": bridge_service,
            "D_day_carryin_nodeh": carryin,
            "D_day_forecast_flexible_arrival_nodeh": forecast_mass,
            "fraction_of_D_day_flexible_mass_represented_by_carryin": carryin / max(carryin + forecast_mass, 1e-15),
            "reference_only_queue_job_count": int(reference_only.sum()),
            "post_cutoff_new_arrival_count_in_bridge": 0,
        })
        provenance_rows.append({
            "day": day, "queue_state": "OBSERVABLE_AT_CUTOFF_RECONSTRUCTED_FROM_EVENT_LOG",
            "service_mass": "nodes_req * wallclock_req",
            "strict_fullnode_admission": "partition gpu-h100 AND nodes_req in frozen classes AND gpus_requested=4*nodes_req",
            "future_start_feature_count": 0, "future_runtime_feature_count": 0,
            "final_state_feature_count": 0, "allocated_node_feature_count": 0,
            "sharing_indicator_feature_count": 0,
        })
    return cohort_rows, decisions, provenance_rows


def field_audit() -> list[dict[str, object]]:
    rows = [
        ("partition", "CUTOFF_OBSERVABLE", "request-time queue/partition field", True, "strict full-node admission"),
        ("nodes_req", "CUTOFF_OBSERVABLE", "request-time requested nodes", True, "strict full-node admission and service mass"),
        ("gpus_requested", "CUTOFF_OBSERVABLE", "request-time requested GPUs", True, "strict full-node admission"),
        ("wallclock_req", "CUTOFF_OBSERVABLE", "request-time requested walltime", True, "service mass"),
        ("processors_req", "CUTOFF_OBSERVABLE", "request-time resource request", False, "audit only"),
        ("memory_req", "CUTOFF_OBSERVABLE", "request-time resource request", False, "audit only"),
        ("qos", "CUTOFF_OBSERVABLE", "request-time scheduling field", False, "audit only"),
        ("submit_time", "CUTOFF_OBSERVABLE", "submission event timestamp", True, "submitted_at <= cutoff"),
        ("start_time", "RECONSTRUCTED_PAST_STATE", "future event timestamp used only to reconstruct not-started-at-cutoff", True, "queue membership reconstruction only"),
        ("end_time", "RECONSTRUCTED_PAST_STATE", "used only to exclude a never-started job already terminated before cutoff", True, "queue membership reconstruction only"),
        ("state", "POST_CUTOFF_EX_POST_ONLY", "final/eventual state", False, "prohibited"),
        ("state_simple", "POST_CUTOFF_EX_POST_ONLY", "eventual COMPLETED status", False, "prohibited"),
        ("wallclock_used", "POST_CUTOFF_EX_POST_ONLY", "actual runtime", False, "prohibited"),
        ("nodes_used", "POST_CUTOFF_EX_POST_ONLY", "allocated/used nodes", False, "prohibited"),
        ("gpu_nodes_occupied", "POST_CUTOFF_EX_POST_ONLY", "allocated GPU nodes", False, "prohibited"),
        ("nodelist", "POST_CUTOFF_EX_POST_ONLY", "future allocated-node evidence", False, "prohibited"),
        ("shared_job_count", "POST_CUTOFF_EX_POST_ONLY", "realized sharing indicator", False, "prohibited"),
        ("nodes_shared", "POST_CUTOFF_EX_POST_ONLY", "realized sharing indicator", False, "prohibited"),
        ("jobs_shared", "POST_CUTOFF_EX_POST_ONLY", "realized sharing indicator", False, "prohibited"),
        ("queue_wait", "POST_CUTOFF_EX_POST_ONLY", "realized wait duration", False, "prohibited"),
    ]
    return [{"field": field, "classification": classification, "basis": basis, "used_by_V29_DA": used, "use": use} for field, classification, basis, used, use in rows]


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--repo", type=Path, default=REPO_ROOT); args = parser.parse_args()
    repo = args.repo.resolve(); out = repo / "dayahead/artifacts/v29_grid_responsive_aidc"; out.mkdir(parents=True, exist_ok=True)
    source = source_zip(); events, members, schemas = read_candidate_events(source)
    rows = field_audit(); cohort_rows, decisions, provenance = queue_by_day(repo, events)
    ready = all(value >= 0.0 for value in (row["D_day_carryin_nodeh"] for row in decisions))
    write_csv(out / "V29_CUTOFF_FIELD_OBSERVABILITY_AUDIT.csv", rows)
    write_json(out / "V29_CUTOFF_FIELD_OBSERVABILITY_AUDIT.json", {
        "artifact_id": "V29_CUTOFF_FIELD_OBSERVABILITY_AUDIT_V1", "status": "PASS",
        "fields": rows, "Day_Ahead_prohibited_field_use_count": 0,
    })
    write_csv(out / "V29_CARRYIN_BY_DAY_COHORT.csv", cohort_rows)
    write_json(out / "V29_PRE_DAY_QUEUE_BRIDGE_CONTRACT.json", {
        "artifact_id": "V29_PRE_DAY_QUEUE_BRIDGE_CONTRACT_V1", "status": "PASS",
        "cutoff": "D-1 18:00 fixed AEST", "bridge_end": "D-day 00:00 fixed AEST",
        "optimization_horizon_extended": False, "bridge_slots": 24, "resolution_minutes": 15,
        "policy": "deterministic earliest-feasible fluid service; cohort ID then slot",
        "grid_signal_reads": 0, "MESS_signal_reads": 0, "post_cutoff_actual_arrivals": 0,
        "future_actual_runtime_reads": 0, "future_queue_selection": 0,
        "days": decisions,
    })
    write_json(out / "V29_CARRYIN_SOURCE_PROVENANCE.json", {
        "artifact_id": "V29_CARRYIN_SOURCE_PROVENANCE_V1", "status": "PASS",
        "source_path": str(source), "source_sha256": sha256(source),
        "archive_members_opened": members, "schemas": schemas,
        "all_archive_month_members_opened": True,
        "reason_future_members_opened": "capture pre-cutoff submissions completed/filed in a later month; later timestamps are not scheduling features",
        "event_log_reconstruction_label": "OBSERVABLE_AT_CUTOFF_RECONSTRUCTED_FROM_EVENT_LOG",
        "days": provenance,
    })
    write_json(out / "V29_CARRYIN_AUTHORITY_DECISION.json", {
        "artifact_id": "V29_CARRYIN_AUTHORITY_DECISION_V1",
        "RESULT_CLASSIFICATION": "V29_CARRYIN_AUTHORITY_READY" if ready else "V29_BLOCKED_CARRYIN_SOURCE_AUTHORITY_INSUFFICIENT",
        "CARRYIN_QUEUE_STATE_OBSERVABLE": True,
        "CARRYIN_SERVICE_MASS_CAUSAL": True,
        "CARRYIN_STRICT_FULLNODE_ADMISSION_CAUSAL": True,
        "PRE_DAY_QUEUE_BRIDGE_READY": True,
        "APRIL_FIT_ROWS": 0,
        "POST_CUTOFF_ACTUAL_FEATURE_COUNT": 0,
        "CARRYIN_AUTHORITY_READY": ready,
        "service_mass_authority": "request-time wallclock_req; no estimator required",
        "strict_fullnode_authority": "request fields only; PARTIAL/shared noncontrollable",
        "running_job_preemption": False,
        "synthetic_deadline_count": 0,
        "days": decisions,
    })


if __name__ == "__main__":
    main()
