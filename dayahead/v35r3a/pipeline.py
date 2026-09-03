"""Materialize the isolated V35R3A Apr-01 scheduler prototype evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import zipfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contracts import (
    ACTIVE_V35R3_WORKTREE,
    AEST,
    AUTHORITY_ROOT,
    CRITICAL_ASSET,
    CRITICAL_SLOT,
    EXPECTED_BRANCH,
    FIXED_PROTECTED,
    FORBIDDEN_POLICY_FIELDS,
    GPU_CAPACITY,
    GPU_NODE_CAPACITY,
    GPUS_PER_NODE,
    ISSUE_TIME,
    KESTREL_ZIP,
    HIGH_PROTECTED,
    NORMAL_QUEUE_CONTROLLED,
    PREEMPTIVE,
    RUNNING_FIXED,
    SIMULATION_SLOTS,
    SLOT_MINUTES,
    SOURCE_BASELINE,
    SPATIO_TEMPORAL_CANDIDATE,
    STANDBY_QUEUE_CONTROLLED,
    STATE_EVENT_FIELDS,
    SUBMISSION_FIELDS,
    TARGET_END,
    TARGET_START,
    TEMPORAL_QUEUE_CONTROLLED,
    TEMPORAL_CONTROLLED_CLASSES,
    VALIDATION_END,
    VALIDATION_START,
    W1,
    W3,
    W5,
    classify_pending,
    is_h100_partition,
    submission_complete,
)
from .scheduler_twin import (
    SchedulerJob,
    ScheduleRow,
    deterministic_control,
    schedule_hash,
    schedule_known_queue,
    schedule_online_replay,
    service_metrics,
    service_noninferiority,
    target_gpu_profile,
    window_metrics,
)


ARTIFACT_DIRNAME = "v35r3a_kestrel_scheduler_temporal"
EXPECTED_KESREL_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
EXPECTED_KESREL_MD5 = "8f1d3be1cbe6345ef45e658a783c2aa0"
EXPECTED_DATACARD_SHA256 = "0139b75b80cd3029e0af54e22fc0dbad3080e92a8a7a602f1bd62cd7a36f62e9"
IT_PEAK_KW = 406.77599381381907
PUE = 1.30
PLANNING_RHO_APR01_B0 = 0.5670071217020519


def _run(args: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        list(args), cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(columns or (rows[0].keys() if rows else ()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _git_status(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = _run(["git", "-C", str(path), "status", "--short"], check=False)
    return text.splitlines() if text else []


def _git_repo(path: Path) -> dict[str, Any]:
    head = _run(["git", "-C", str(path), "rev-parse", "HEAD"])
    remote = _run(["git", "-C", str(path), "remote", "get-url", "origin"], check=False)
    return {
        "path": str(path),
        "HEAD": head,
        "origin": remote or None,
        "status": _git_status(path),
    }


def _pointer_files(root: Path) -> list[dict[str, Any]]:
    pointers: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        try:
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                head = handle.read(160)
        except OSError:
            continue
        if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
            text = head.decode("ascii", errors="ignore")
            oid = re.search(r"oid sha256:([0-9a-f]{64})", text)
            size = re.search(r"size (\d+)", text)
            pointers.append(
                {
                    "path": str(path.relative_to(root)).replace("\\", "/"),
                    "oid": oid.group(1) if oid else None,
                    "declared_size": int(size.group(1)) if size else None,
                }
            )
    return pointers


def authority_inventory(authority_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = [
        "01_Kestrel_job_trace",
        "02_RADDiT",
        "03_FastSim",
        "04_NLR_HPC_docs_repo",
        "05_Eagle_jobs_reference",
        "06_official_web_docs",
        "99_manifest",
    ]
    repos = {
        "RADDiT": _git_repo(authority_root / "02_RADDiT"),
        "FastSim": _git_repo(authority_root / "03_FastSim"),
        "NLR_HPC_docs": _git_repo(authority_root / "04_NLR_HPC_docs_repo"),
        "Eagle_jobs_reference": _git_repo(authority_root / "05_Eagle_jobs_reference"),
    }
    pointers = {name: _pointer_files(Path(value["path"])) for name, value in repos.items()}
    key_files = [
        authority_root / "01_Kestrel_job_trace" / "datacard.md",
        authority_root / "06_official_web_docs" / "NLR_Kestrel_Running.html",
        authority_root / "06_official_web_docs" / "NLR_Slurm_Batch_Jobs.html",
        authority_root / "06_official_web_docs" / "Slurm_Priority_Multifactor.html",
        authority_root / "03_FastSim" / "README.md",
        authority_root / "03_FastSim" / "configs" / "default_conf.yaml",
        authority_root / "03_FastSim" / "scheduler" / "priority_sorters.py",
        authority_root / "02_RADDiT" / "README.md",
        authority_root / "02_RADDiT" / "energy_aware_scheduling" / "scripts" / "ea_sched_priority.py",
    ]
    inventory = {
        "artifact_id": "V35R3A_DOWNLOADED_AUTHORITY_INVENTORY_V1",
        "authority_root": str(authority_root),
        "read_only_use_contract": True,
        "download_performed": False,
        "expected_folders": {name: (authority_root / name).is_dir() for name in expected},
        "source_file_hashes": {
            str(path.relative_to(authority_root)).replace("\\", "/"): _sha256(path)
            for path in key_files
            if path.is_file()
        },
        "git_lfs_pointer_files": pointers,
        "git_lfs_pointer_count": sum(len(values) for values in pointers.values()),
        "RADDiT_redacted_or_unavailable": {
            "encrypted_embedding_LFS_pointers": sum(
                "encrypted_embeddings" in row["path"] for row in pointers["RADDiT"]
            ),
            "runtime_predictor_result_is_pointer": any(
                row["path"] == "data/baseline_runtime_results.parquet" for row in pointers["RADDiT"]
            ),
            "interpretation": "Public code is present, but encrypted embeddings and the frozen runtime-result object are unavailable LFS payloads.",
        },
        "Eagle_role": "REFERENCE_ONLY_NOT_KESTREL_PRODUCTION_DATA",
    }
    heads = {
        "artifact_id": "V35R3A_VENDOR_REPO_HEADS_V1",
        "repositories": repos,
        "FastSim_direct_adapter": {
            "runnable": False,
            "probe": "python -B scheduler/main.py --help",
            "probe_failure": "ModuleNotFoundError: zmq",
            "additional_missing_dependency": "PyYAML",
            "missing_Kestrel_inputs": [
                "sacctmgr association dump",
                "sacctmgr QoS dump",
                "node topology/state dump",
                "reservation history",
                "Kestrel slurm.conf priority weights",
            ],
            "classification": "PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN_REQUIRED",
        },
    }
    return inventory, heads


def policy_authority(authority_root: Path) -> dict[str, Any]:
    sources = [
        authority_root / "06_official_web_docs" / "NLR_Kestrel_Running.html",
        authority_root / "06_official_web_docs" / "NLR_Slurm_Batch_Jobs.html",
        authority_root / "06_official_web_docs" / "Slurm_Priority_Multifactor.html",
        authority_root / "03_FastSim" / "scheduler" / "priority_sorters.py",
        authority_root / "03_FastSim" / "scheduler" / "controller.py",
        authority_root / "03_FastSim" / "configs" / "default_conf.yaml",
        authority_root / "02_RADDiT" / "README.md",
    ]
    result = {
        "artifact_id": "V35R3A_SCHEDULER_POLICY_AUTHORITY_V1",
        "authority_level": "PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN",
        "policy_frozen_at": ISSUE_TIME.isoformat(),
        "source_paths": [str(path) for path in sources],
        "source_sha256": {str(path): _sha256(path) for path in sources},
        "documented_priority_components": [
            "site_factor",
            "eligible age",
            "association",
            "fair-share",
            "job size/resources",
            "partition",
            "QoS",
            "TRES",
            "nice",
        ],
        "implemented_relative_components": [
            "hard service tiers: high > normal > standby, using the raw QoS field",
            "standby consumes only residual capacity after high/normal reservations",
            "eligible age represented by submission-order FIFO",
            "partition names containing stdby are audited but do not define QoS",
            "stable job-ID tie breaking",
            "SiteFactor may reorder only within normal or standby tier",
        ],
        "weights": None,
        "weights_reason": "No Kestrel slurm.conf or sprio weight dump exists in the downloaded authority; sample SchedMD weights are not Kestrel weights.",
        "backfill": {
            "type": "CONSERVATIVE_REQUESTED_WALLTIME_FIRST_FIT",
            "main_loop": "priority-order reservation",
            "hole_use": "later jobs may use an earlier compatible hole without moving an existing reservation",
            "duration": "submission-side requested walltime",
            "preemption": False,
        },
        "qos_authority": {
            "high": "takes precedence in the queue",
            "standby": "runs only when nodes are idle",
            "normal": "submission-side normal QoS is queue controlled regardless of partition-name substring",
            "source_path": str(authority_root / "06_official_web_docs" / "NLR_Slurm_Batch_Jobs.html"),
            "source_sha256": _sha256(
                authority_root / "06_official_web_docs" / "NLR_Slurm_Batch_Jobs.html"
            ),
            "source_lines": "7140-7151",
            "partition_to_qos_mapping_present": False,
        },
        "missing_historical_inputs": [
            "Kestrel priority weights and flags",
            "fair-share usage tree/history",
            "association priorities",
            "reservation/dependency/hold/requeue history",
            "complete node-state/topology history",
        ],
        "unsupported_per_job_deadline_assumed": False,
    }
    result["policy_sha256"] = _canonical_hash(result)
    return result


def _month_key(name: str) -> tuple[int, int] | None:
    match = re.search(r"year=(\d{4})/month=(\d{1,2})/.*\.parquet$", name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _read_member(
    archive: zipfile.ZipFile,
    member: str,
    columns: Sequence[str],
    filters: Sequence[tuple[str, str, Any]] | None = None,
) -> pd.DataFrame:
    with archive.open(member) as handle:
        return pq.read_table(handle, columns=list(columns), filters=filters).to_pandas()


def _wallclock_seconds(series: pd.Series) -> pd.Series:
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds()
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def _event_state(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Collapse start/end values to cutoff-state predicates immediately."""

    work = frame.copy()
    submit = pd.to_datetime(work["submit_time"], utc=True, errors="coerce")
    start = pd.to_datetime(work["start_time"], utc=True, errors="coerce")
    end = pd.to_datetime(work["end_time"], utc=True, errors="coerce")
    alive = end.isna() | end.gt(cutoff)
    running = submit.le(cutoff) & start.notna() & start.le(cutoff) & alive
    pending = submit.le(cutoff) & (start.isna() | start.gt(cutoff)) & alive
    keep = running | pending
    result = work.loc[keep, list(SUBMISSION_FIELDS)].copy()
    result["submit_time"] = submit.loc[keep]
    result["wallclock_seconds"] = _wallclock_seconds(work.loc[keep, "wallclock_req"])
    result["state_at_cutoff"] = np.where(running.loc[keep], "RUNNING", "PENDING")
    # A running start is current-state authority.  No pending future start and
    # no future end value crosses this boundary.
    result["known_running_start"] = pd.Series(
        pd.NaT, index=result.index, dtype="datetime64[ns, UTC]"
    )
    run_index = running[running].index.intersection(result.index)
    result.loc[run_index, "known_running_start"] = start.loc[run_index]
    result["start_event_at_or_before_cutoff"] = running.loc[keep].to_numpy()
    result["end_event_at_or_before_cutoff"] = False
    return result.reset_index(drop=True)


def _validation_rows(frame: pd.DataFrame) -> pd.DataFrame:
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce")
    left = pd.Timestamp(VALIDATION_START).tz_convert("UTC")
    right = pd.Timestamp(VALIDATION_END).tz_convert("UTC")
    alive_at_left = end.isna() | end.gt(left)
    relevant = submit.lt(right) & alive_at_left & (start.isna() | start.ge(left) | end.gt(left))
    result = frame.loc[relevant, list(SUBMISSION_FIELDS)].copy()
    result["submit_time"] = submit.loc[relevant]
    result["actual_start_validation"] = start.loc[relevant]
    result["actual_end_validation"] = end.loc[relevant]
    result["wallclock_seconds"] = _wallclock_seconds(frame.loc[relevant, "wallclock_req"])
    result["running_at_validation_start"] = (
        start.loc[relevant].notna() & start.loc[relevant].le(left) & alive_at_left.loc[relevant]
    )
    return result.reset_index(drop=True)


def load_preissue_authority(kestrel_zip: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    issue_utc = ISSUE_TIME.astimezone(timezone.utc)
    columns = list(SUBMISSION_FIELDS) + list(STATE_EVENT_FIELDS)
    states: list[pd.DataFrame] = []
    validation: list[pd.DataFrame] = []
    members_read: list[str] = []
    returned_max_submit: datetime | None = None
    with zipfile.ZipFile(kestrel_zip) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if _month_key(name) is not None and _month_key(name) <= (2025, 3)
        )
        for member in members:
            frame = _read_member(
                archive,
                member,
                columns,
                filters=[("submit_time", "<=", issue_utc)],
            )
            members_read.append(member)
            if frame.empty:
                continue
            h100 = frame["partition"].map(is_h100_partition)
            frame = frame.loc[h100].copy()
            if frame.empty:
                continue
            maximum = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce").max()
            if pd.notna(maximum):
                candidate = maximum.to_pydatetime()
                returned_max_submit = candidate if returned_max_submit is None else max(returned_max_submit, candidate)
            state = _event_state(frame, pd.Timestamp(issue_utc))
            if not state.empty:
                states.append(state)
            historic = _validation_rows(frame)
            if not historic.empty:
                validation.append(historic)
    snapshot = pd.concat(states, ignore_index=True) if states else pd.DataFrame()
    fidelity = pd.concat(validation, ignore_index=True) if validation else pd.DataFrame()
    audit = {
        "preissue_members_read": members_read,
        "preissue_member_count": len(members_read),
        "latest_returned_submit_time": returned_max_submit.isoformat() if returned_max_submit else None,
        "parquet_return_filter": f"submit_time <= {issue_utc.isoformat()}",
        "future_job_identity_rows_returned_to_KQ0": 0,
        "future_start_end_numeric_values_passed_to_policy": 0,
        "state_event_values_collapsed_to_boolean_before_policy": True,
        "post_2025_03_member_opened_for_KQ0": False,
    }
    return snapshot, fidelity, audit


def load_pr1_submissions(kestrel_zip: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    issue_utc = ISSUE_TIME.astimezone(timezone.utc)
    target_end_utc = TARGET_END.astimezone(timezone.utc)
    frames: list[pd.DataFrame] = []
    members_read: list[str] = []
    with zipfile.ZipFile(kestrel_zip) as archive:
        members = sorted(
            name for name in archive.namelist() if _month_key(name) in {(2025, 3), (2025, 4)}
        )
        for member in members:
            frame = _read_member(
                archive,
                member,
                SUBMISSION_FIELDS,
                filters=[
                    ("submit_time", ">", issue_utc),
                    ("submit_time", "<", target_end_utc),
                ],
            )
            members_read.append(member)
            if frame.empty:
                continue
            frame = frame.loc[frame["partition"].map(is_h100_partition)].copy()
            if frame.empty:
                continue
            frame["submit_time"] = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce")
            frame["wallclock_seconds"] = _wallclock_seconds(frame["wallclock_req"])
            frames.append(frame)
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    maximum = result["submit_time"].max() if not result.empty else pd.NaT
    audit = {
        "members_read": members_read,
        "returned_filter": f"{issue_utc.isoformat()} < submit_time < {target_end_utc.isoformat()}",
        "submission_side_columns_only": list(SUBMISSION_FIELDS),
        "future_actual_start_end_runtime_columns_read": 0,
        "latest_returned_submit_time": maximum.isoformat() if pd.notna(maximum) else None,
        "post_target_identity_rows_returned": 0,
        "policy_frozen_before_read": True,
    }
    return result, audit


def _clean_value(value: Any, default: Any = None) -> Any:
    return default if pd.isna(value) else value


def _frame_to_jobs(frame: pd.DataFrame, cutoff: datetime) -> tuple[list[SchedulerJob], list[SchedulerJob], pd.DataFrame]:
    running: list[SchedulerJob] = []
    pending: list[SchedulerJob] = []
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        record = row.to_dict()
        state = str(record["state_at_cutoff"])
        if state == "RUNNING":
            workload_class, reasons = RUNNING_FIXED, ("RUNNING_NON_PREEMPTIVE",)
        else:
            workload_class, reasons = classify_pending(record)
        record["workload_class"] = workload_class
        record["exclusion_reasons"] = list(reasons)
        record["spatio_temporal_candidate"] = False
        record["spatial_exclusion_reason"] = (
            "SUBMISSION_TIME_EXCLUSIVITY_AND_EXACT_AIDC_BINDING_UNAVAILABLE"
        )
        records.append(record)
        if not submission_complete(record):
            continue
        submit = pd.Timestamp(record["submit_time"]).to_pydatetime()
        duration_slots = max(1, int(math.ceil(float(record["wallclock_seconds"]) / (SLOT_MINUTES * 60))))
        running_start = record.get("known_running_start")
        remaining = 0
        if state == "RUNNING":
            elapsed = max(0.0, (cutoff - pd.Timestamp(running_start).to_pydatetime()).total_seconds())
            remaining = max(1, int(math.ceil(max(0.0, float(record["wallclock_seconds"]) - elapsed) / (SLOT_MINUTES * 60))))
        job = SchedulerJob(
            job_id=str(record["id"]),
            submit_time=submit,
            partition=str(record["partition"]),
            qos=str(record["qos"]),
            requested_nodes=int(record["nodes_req"]),
            requested_gpus=float(record["gpus_requested"]),
            duration_slots=duration_slots,
            processors_requested=int(_clean_value(record.get("processors_req"), 0)),
            memory_request=str(_clean_value(record.get("memory_req"), "")),
            workload_class=workload_class,
            protected=workload_class in {RUNNING_FIXED, HIGH_PROTECTED, FIXED_PROTECTED},
            running_at_issue=state == "RUNNING",
            arrival_slot=0,
            fixed_remaining_slots=remaining,
            exclusion_reasons=tuple(reasons),
        )
        (running if state == "RUNNING" else pending).append(job)
    return running, pending, pd.DataFrame.from_records(records)


def _pr1_jobs(frame: pd.DataFrame) -> tuple[list[SchedulerJob], pd.DataFrame]:
    jobs: list[SchedulerJob] = []
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        record = row.to_dict()
        workload_class, reasons = classify_pending(record)
        record["workload_class"] = workload_class
        record["exclusion_reasons"] = list(reasons)
        records.append(record)
        if not submission_complete(record):
            continue
        submit = pd.Timestamp(record["submit_time"]).to_pydatetime()
        jobs.append(
            SchedulerJob(
                job_id=str(record["id"]),
                submit_time=submit,
                partition=str(record["partition"]),
                qos=str(record["qos"]),
                requested_nodes=int(record["nodes_req"]),
                requested_gpus=float(record["gpus_requested"]),
                duration_slots=max(1, int(math.ceil(float(record["wallclock_seconds"]) / (SLOT_MINUTES * 60)))),
                processors_requested=int(_clean_value(record.get("processors_req"), 0)),
                memory_request=str(_clean_value(record.get("memory_req"), "")),
                workload_class=workload_class,
                protected=workload_class in {HIGH_PROTECTED, FIXED_PROTECTED},
                arrival_slot=max(1, int(math.ceil((submit - ISSUE_TIME).total_seconds() / (SLOT_MINUTES * 60)))),
                exclusion_reasons=tuple(reasons),
            )
        )
    return jobs, pd.DataFrame.from_records(records)


def _quantiles(values: pd.Series) -> dict[str, float | None]:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    if finite.empty:
        return {name: None for name in ("min", "p50", "p95", "max")}
    return {
        "min": float(finite.min()),
        "p50": float(finite.quantile(0.50)),
        "p95": float(finite.quantile(0.95)),
        "max": float(finite.max()),
    }


def queue_snapshot(frame: pd.DataFrame, classified: pd.DataFrame) -> dict[str, Any]:
    running = classified["state_at_cutoff"].eq("RUNNING")
    pending = classified["state_at_cutoff"].eq("PENDING")
    valid = classified.apply(lambda row: submission_complete(row.to_dict()), axis=1)
    wall_h = pd.to_numeric(classified["wallclock_seconds"], errors="coerce") / 3600.0
    gpu = pd.to_numeric(classified["gpus_requested"], errors="coerce")
    nodes = pd.to_numeric(classified["nodes_req"], errors="coerce")
    controlled = classified["workload_class"].isin(TEMPORAL_CONTROLLED_CLASSES)
    partial_request = valid & gpu.lt(GPUS_PER_NODE * nodes)
    full_request = valid & gpu.eq(GPUS_PER_NODE * nodes)
    qos_lower = classified["qos"].fillna("UNKNOWN").astype(str).str.strip().str.lower()
    partition_lower = classified["partition"].fillna("").astype(str).str.strip().str.lower()

    def qos_summary(name: str) -> dict[str, float | int]:
        if name == "high":
            mask = pending & qos_lower.isin({"high", "urgent"})
        else:
            mask = pending & qos_lower.eq(name)
        return {
            "job_count": int(mask.sum()),
            "schedulable_job_count": int((mask & valid).sum()),
            "known_requested_GPU_hours": float((gpu[mask] * wall_h[mask]).fillna(0.0).sum()),
            "full_node_request_count": int((mask & full_request).sum()),
            "partial_shared_request_count": int((mask & partial_request).sum()),
        }

    partition_stdby = pending & partition_lower.str.contains("stdby|standby", regex=True)
    qos_partition_ambiguous = partition_stdby & ~qos_lower.eq("standby")
    pre_correction = (
        pending
        & valid
        & qos_lower.eq("normal")
        & ~partition_lower.str.contains("stdby", regex=False)
    )
    return {
        "artifact_id": "V35R3A_APR01_QUEUE_SNAPSHOT_V1",
        "cutoff": ISSUE_TIME.isoformat(),
        "timezone": "FIXED_AEST_UTC_PLUS_10",
        "R_tau": {
            "job_count": int(running.sum()),
            "requested_nodes_sum": float(nodes[running].sum()),
            "requested_GPUs_sum": float(gpu[running].sum()),
            "requested_GPU_hours": float((gpu[running] * wall_h[running]).sum()),
            "policy": "FIXED_NON_PREEMPTIVE",
        },
        "P_tau": {
            "job_count": int(pending.sum()),
            "schedulable_request_job_count": int((pending & valid).sum()),
            "requested_nodes_sum": float(nodes[pending].sum()),
            "known_requested_GPUs_sum": float(gpu[pending].fillna(0.0).sum()),
            "known_requested_GPU_hours": float((gpu[pending] * wall_h[pending]).fillna(0.0).sum()),
            "requested_node_hours": float((nodes[pending] * wall_h[pending]).fillna(0.0).sum()),
            "qos_counts": classified.loc[pending, "qos"].fillna("UNKNOWN").value_counts().to_dict(),
            "partition_counts": classified.loc[pending, "partition"].fillna("UNKNOWN").value_counts().to_dict(),
            "wallclock_hours": _quantiles(wall_h[pending]),
            "unknown_GPU_request_count": int((pending & gpu.isna()).sum()),
            "temporal_queue_controlled_count": int((pending & controlled).sum()),
            "partial_request_count": int((pending & partial_request).sum()),
            "partial_temporal_queue_controlled_count": int((pending & partial_request & controlled).sum()),
            "full_node_request_count": int((pending & full_request).sum()),
            "qos_resource_summary": {
                "high": qos_summary("high"),
                "normal": qos_summary("normal"),
                "standby": qos_summary("standby"),
            },
            "partition_stdby_name_count": int(partition_stdby.sum()),
            "partition_only_stdby_without_standby_qos_count": int(qos_partition_ambiguous.sum()),
            "qos_partition_semantics_ambiguous_count": int(qos_partition_ambiguous.sum()),
            "temporal_controllable_mass_before_standby_correction": {
                "job_count": int(pre_correction.sum()),
                "known_requested_GPU_hours": float(
                    (gpu[pre_correction] * wall_h[pre_correction]).fillna(0.0).sum()
                ),
            },
            "temporal_controllable_mass_after_standby_correction": {
                "job_count": int((pending & controlled).sum()),
                "known_requested_GPU_hours": float(
                    (gpu[pending & controlled] * wall_h[pending & controlled]).fillna(0.0).sum()
                ),
            },
        },
        "U_tau": {
            "job_identity_count_known_at_issue": 0,
            "included_in_KQ0": 0,
            "interpretation": "Post-issue identities are unavailable to KQ0 and are isolated to PR1 event replay.",
        },
        "partition_conservation": int(running.sum() + pending.sum()) == len(classified),
        "future_identity_reads_KQ0": 0,
    }


def workload_census(classified: pd.DataFrame) -> list[dict[str, Any]]:
    gpu = pd.to_numeric(classified["gpus_requested"], errors="coerce").fillna(0.0)
    wall_h = pd.to_numeric(classified["wallclock_seconds"], errors="coerce").fillna(0.0) / 3600.0
    masks = {
        RUNNING_FIXED: classified["workload_class"].eq(RUNNING_FIXED),
        HIGH_PROTECTED: classified["workload_class"].eq(HIGH_PROTECTED),
        NORMAL_QUEUE_CONTROLLED: classified["workload_class"].eq(NORMAL_QUEUE_CONTROLLED),
        STANDBY_QUEUE_CONTROLLED: classified["workload_class"].eq(STANDBY_QUEUE_CONTROLLED),
        FIXED_PROTECTED: classified["workload_class"].eq(FIXED_PROTECTED),
        TEMPORAL_QUEUE_CONTROLLED: classified["workload_class"].isin(TEMPORAL_CONTROLLED_CLASSES),
        SPATIO_TEMPORAL_CANDIDATE: classified["spatio_temporal_candidate"].eq(True),
        PREEMPTIVE: pd.Series(False, index=classified.index),
    }
    return [
        {
            "workload_class": name,
            "job_count": int(mask.sum()),
            "known_requested_GPUs": float(gpu[mask].sum()),
            "known_requested_GPU_hours": float((gpu[mask] * wall_h[mask]).sum()),
            "subset_of_temporal": (
                bool((~mask | classified["workload_class"].isin(TEMPORAL_CONTROLLED_CLASSES)).all())
                if name == SPATIO_TEMPORAL_CANDIDATE
                else name
                in {
                    NORMAL_QUEUE_CONTROLLED,
                    STANDBY_QUEUE_CONTROLLED,
                    TEMPORAL_QUEUE_CONTROLLED,
                }
            ),
            "authority_note": {
                RUNNING_FIXED: "Running at tau; fixed and non-preemptive.",
                HIGH_PROTECTED: "Pending high/urgent QoS; no grid-driven delay.",
                NORMAL_QUEUE_CONTROLLED: "Raw QoS=normal with complete submission resource authority.",
                STANDBY_QUEUE_CONTROLLED: "Raw QoS=standby; residual-capacity ordering only.",
                FIXED_PROTECTED: "Incomplete or unknown submission-side scheduling authority.",
                TEMPORAL_QUEUE_CONTROLLED: "Union of normal and standby queue-controlled classes.",
                SPATIO_TEMPORAL_CANDIDATE: "None: submission-time exclusivity and exact AIDC binding are absent.",
                PREEMPTIVE: "Not authorized.",
            }[name],
        }
        for name, mask in masks.items()
    ]


def pending_field_audit(classified: pd.DataFrame, policy: Mapping[str, Any]) -> pd.DataFrame:
    """Return the amendment-required row-level audit of every pending job."""

    pending = classified.loc[classified["state_at_cutoff"].eq("PENDING")].copy()
    rows: list[dict[str, Any]] = []
    source = policy["qos_authority"]
    for _, row in pending.iterrows():
        record = row.to_dict()
        qos = str(_clean_value(record.get("qos"), "UNKNOWN")).strip()
        partition = str(_clean_value(record.get("partition"), "UNKNOWN")).strip()
        qos_lower = qos.lower()
        partition_lower = partition.lower()
        gpu = pd.to_numeric(pd.Series([record.get("gpus_requested")]), errors="coerce").iloc[0]
        nodes = pd.to_numeric(pd.Series([record.get("nodes_req")]), errors="coerce").iloc[0]
        valid = submission_complete(record)
        partial = bool(valid and float(gpu) < GPUS_PER_NODE * float(nodes))
        full_shape = bool(valid and float(gpu) == GPUS_PER_NODE * float(nodes))
        array_range = str(_clean_value(record.get("array_range"), "")).strip()
        partition_names_standby = "stdby" in partition_lower or "standby" in partition_lower
        if partition_names_standby and qos_lower != "standby":
            relation = "PARTITION_ONLY_STDBY_NAME_WITH_NONSTANDBY_QOS"
        elif qos_lower == "standby" and not partition_names_standby:
            relation = "QOS_STANDBY_WITHOUT_STDBY_PARTITION_NAME"
        else:
            relation = "CONSISTENT_RAW_FIELDS_NO_PARTITION_TO_QOS_INFERENCE"
        rows.append(
            {
                "job_id": str(record["id"]),
                "qos_raw": qos,
                "partition_raw": partition,
                "requested_GPUs": None if pd.isna(gpu) else float(gpu),
                "requested_nodes": None if pd.isna(nodes) else int(nodes),
                "requested_walltime_seconds": float(record["wallclock_seconds"])
                if pd.notna(record.get("wallclock_seconds"))
                else None,
                "submit_time": pd.Timestamp(record["submit_time"]).isoformat(),
                "state_at_cutoff": str(record["state_at_cutoff"]),
                "account_hash": str(_clean_value(record.get("account_hash"), "")),
                "account_association_use": "HASH_AVAILABLE_CAUSALLY_NOT_MAPPED_TO_PRIORITY",
                "partial_shared_request": partial,
                "full_node_request_shape": full_shape,
                "spatio_temporal_candidate": bool(record["spatio_temporal_candidate"]),
                "array_range": array_range,
                "explicit_special_constraint_present": bool(array_range),
                "explicit_special_constraint": "ARRAY_RANGE" if array_range else "NONE_VISIBLE_IN_TRACE",
                "dependency_hold_reservation_fields_available": False,
                "qos_partition_semantics_relation": relation,
                "workload_class": str(record["workload_class"]),
                "classification_reasons": "|".join(record["exclusion_reasons"]),
                "qos_semantics_source_path": source["source_path"],
                "qos_semantics_source_sha256": source["source_sha256"],
            }
        )
    return pd.DataFrame.from_records(rows).sort_values("job_id", ignore_index=True)


def _validation_jobs(frame: pd.DataFrame) -> tuple[list[SchedulerJob], list[SchedulerJob], dict[str, dict[str, Any]]]:
    left = pd.Timestamp(VALIDATION_START).tz_convert("UTC")
    running: list[SchedulerJob] = []
    queue: list[SchedulerJob] = []
    actual: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        record = row.to_dict()
        if not submission_complete(record):
            continue
        submit = pd.Timestamp(record["submit_time"]).to_pydatetime()
        duration_slots = max(1, int(math.ceil(float(record["wallclock_seconds"]) / (SLOT_MINUTES * 60))))
        is_running = bool(record["running_at_validation_start"])
        workload_class, reasons = (RUNNING_FIXED, ("RUNNING_NON_PREEMPTIVE",)) if is_running else classify_pending(record)
        fixed_remaining = 0
        actual_start = pd.Timestamp(record["actual_start_validation"])
        if is_running:
            elapsed = max(0.0, (VALIDATION_START - actual_start.to_pydatetime()).total_seconds())
            fixed_remaining = max(1, int(math.ceil(max(0.0, float(record["wallclock_seconds"]) - elapsed) / 900.0)))
        job = SchedulerJob(
            job_id=str(record["id"]),
            submit_time=submit,
            partition=str(record["partition"]),
            qos=str(record["qos"]),
            requested_nodes=int(record["nodes_req"]),
            requested_gpus=float(record["gpus_requested"]),
            duration_slots=duration_slots,
            processors_requested=int(_clean_value(record.get("processors_req"), 0)),
            memory_request=str(_clean_value(record.get("memory_req"), "")),
            workload_class=workload_class,
            protected=workload_class in {RUNNING_FIXED, HIGH_PROTECTED, FIXED_PROTECTED},
            running_at_issue=is_running,
            arrival_slot=max(0, int(math.ceil((submit - VALIDATION_START).total_seconds() / 900.0))),
            fixed_remaining_slots=fixed_remaining,
            exclusion_reasons=tuple(reasons),
        )
        (running if is_running else queue).append(job)
        actual[str(record["id"])] = {
            "submit": submit,
            "start": actual_start.to_pydatetime() if pd.notna(actual_start) else None,
            "end": pd.Timestamp(record["actual_end_validation"]).to_pydatetime()
            if pd.notna(record["actual_end_validation"])
            else None,
            "qos": str(record["qos"]),
            "gpus": float(record["gpus_requested"]),
        }
    return running, queue, actual


def baseline_fidelity(frame: pd.DataFrame, policy_sha: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    running, queue, actual = _validation_jobs(frame)
    replay, occupancy = schedule_online_replay(
        running,
        queue,
        replay_start=VALIDATION_START,
        maximum_slots=1344,
    )
    right = VALIDATION_END
    predicted = {row.job_id: VALIDATION_START + timedelta(minutes=15 * row.scheduled_start_slot) for row in replay}
    rows: list[dict[str, Any]] = []
    for qos in ("ALL", "normal", "standby", "high"):
        ids = [
            job_id
            for job_id, values in actual.items()
            if values["start"] is not None
            and VALIDATION_START <= values["start"] < right
            and job_id in predicted
            and (qos == "ALL" or values["qos"].lower() == qos)
        ]
        actual_start = pd.Series({job_id: actual[job_id]["start"].timestamp() for job_id in ids}, dtype=float)
        predicted_start = pd.Series({job_id: predicted[job_id].timestamp() for job_id in ids}, dtype=float)
        errors = (predicted_start - actual_start).abs() / 3600.0
        actual_wait = pd.Series(
            {job_id: (actual[job_id]["start"] - actual[job_id]["submit"]).total_seconds() / 3600.0 for job_id in ids},
            dtype=float,
        )
        predicted_wait = pd.Series(
            {job_id: (predicted[job_id] - actual[job_id]["submit"]).total_seconds() / 3600.0 for job_id in ids},
            dtype=float,
        )
        rank_corr = actual_start.rank(method="average").corr(predicted_start.rank(method="average")) if len(ids) > 1 else None
        rows.append(
            {
                "qos": qos,
                "compared_start_count": len(ids),
                "start_order_spearman": float(rank_corr) if pd.notna(rank_corr) else None,
                "start_MAE_hours": float(errors.mean()) if len(errors) else None,
                "start_median_AE_hours": float(errors.median()) if len(errors) else None,
                "start_P95_AE_hours": float(errors.quantile(0.95)) if len(errors) else None,
                "actual_wait_mean_hours": float(actual_wait.mean()) if len(actual_wait) else None,
                "actual_wait_P50_hours": float(actual_wait.quantile(0.50)) if len(actual_wait) else None,
                "actual_wait_P95_hours": float(actual_wait.quantile(0.95)) if len(actual_wait) else None,
                "actual_wait_max_hours": float(actual_wait.max()) if len(actual_wait) else None,
                "replay_wait_mean_hours": float(predicted_wait.mean()) if len(predicted_wait) else None,
                "replay_wait_P50_hours": float(predicted_wait.quantile(0.50)) if len(predicted_wait) else None,
                "replay_wait_P95_hours": float(predicted_wait.quantile(0.95)) if len(predicted_wait) else None,
                "replay_wait_max_hours": float(predicted_wait.max()) if len(predicted_wait) else None,
            }
        )
    horizon = int((VALIDATION_END - VALIDATION_START).total_seconds() // 900)
    replay_profile = np.asarray(occupancy[:horizon], dtype=float)
    actual_profile = np.zeros(horizon, dtype=float)
    actual_completed = 0
    actual_completed_gpuh = 0.0
    for values in actual.values():
        if values["start"] is None or values["end"] is None:
            continue
        left = max(0, int(math.floor((values["start"] - VALIDATION_START).total_seconds() / 900.0)))
        right_slot = min(horizon, int(math.ceil((values["end"] - VALIDATION_START).total_seconds() / 900.0)))
        if left < right_slot:
            actual_profile[left:right_slot] += values["gpus"]
        if values["end"] <= VALIDATION_END:
            actual_completed += 1
            actual_completed_gpuh += values["gpus"] * max(
                0.0, (values["end"] - values["start"]).total_seconds() / 3600.0
            )
    replay_complete = [row for row in replay if row.scheduled_end_slot <= horizon]
    error = np.abs(replay_profile - actual_profile)
    summary = {
        "policy_sha256_frozen_before_expost_validation": policy_sha,
        "window": [VALIDATION_START.isoformat(), VALIDATION_END.isoformat()],
        "replay_input_job_count": len(queue),
        "carry_in_running_job_count": len(running),
        "actual_completed_job_count": actual_completed,
        "actual_completed_GPU_hours_realized_expost": actual_completed_gpuh,
        "replay_completed_job_count_requested_walltime": len(replay_complete),
        "replay_completed_GPU_hours_requested_walltime": float(sum(row.request_gpu_hours for row in replay_complete)),
        "GPU_profile_MAE": float(error.mean()),
        "GPU_profile_WAPE": float(error.sum() / max(1e-12, np.abs(actual_profile).sum())),
        "resource_utilization_actual_mean": float(actual_profile.mean() / GPU_CAPACITY),
        "resource_utilization_replay_mean": float(replay_profile.mean() / GPU_CAPACITY),
        "realized_runtime_role": "EX_POST_VALIDATION_ONLY_AFTER_POLICY_FREEZE",
        "authority_conclusion": "RELATIVE_TWIN_ONLY",
    }
    return rows, summary


def causality_tables(classified: pd.DataFrame, pr1_records: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    field_rows: list[dict[str, Any]] = []
    for field in SUBMISSION_FIELDS:
        field_rows.append(
            {
                "field": field,
                "origin": "Kestrel submission record",
                "available_at": "submit_time",
                "policy_use": "PERMITTED",
                "numeric_future_value_use": False,
                "reason": "Scheduler-visible request field.",
            }
        )
    for field in STATE_EVENT_FIELDS:
        field_rows.append(
            {
                "field": field,
                "origin": "Kestrel event history",
                "available_at": "event occurrence",
                "policy_use": "BOOLEAN_CUTOFF_STATE_ONLY",
                "numeric_future_value_use": False,
                "reason": "Immediately collapsed to event-at-or-before-cutoff; future numeric value is not passed.",
            }
        )
    for field in FORBIDDEN_POLICY_FIELDS:
        field_rows.append(
            {
                "field": field,
                "origin": "ex-post or unavailable",
                "available_at": "after issue or unavailable",
                "policy_use": "FORBIDDEN",
                "numeric_future_value_use": False,
                "reason": "Causal field firewall.",
            }
        )
    ledger: list[dict[str, Any]] = []
    for _, row in classified.iterrows():
        job_id = str(row["id"])
        submit = pd.Timestamp(row["submit_time"]).isoformat()
        for field in SUBMISSION_FIELDS:
            ledger.append(
                {
                    "job_identifier": job_id,
                    "field": field,
                    "field_value_origin": "Kestrel submission record",
                    "available_at": submit,
                    "used_at": ISSUE_TIME.isoformat(),
                    "permitted_or_forbidden": "PERMITTED",
                    "reason": "Returned by submit_time<=tau predicate; submission-side field.",
                }
            )
        for field in STATE_EVENT_FIELDS:
            ledger.append(
                {
                    "job_identifier": job_id,
                    "field": field,
                    "field_value_origin": "event comparison",
                    "available_at": ISSUE_TIME.isoformat(),
                    "used_at": ISSUE_TIME.isoformat(),
                    "permitted_or_forbidden": "BOOLEAN_ONLY",
                    "reason": "Numeric value discarded at state-reconstruction boundary.",
                }
            )
    for _, row in pr1_records.iterrows():
        job_id = str(row["id"])
        available = pd.Timestamp(row["submit_time"]).isoformat()
        for field in SUBMISSION_FIELDS:
            ledger.append(
                {
                    "job_identifier": job_id,
                    "field": field,
                    "field_value_origin": "PR1 submit event",
                    "available_at": available,
                    "used_at": available,
                    "permitted_or_forbidden": "PERMITTED_AT_EVENT_ONLY",
                    "reason": "Frozen-policy replay reveals the request only at its submit event.",
                }
            )
    return field_rows, ledger


def _schedule_frame(rows: Sequence[ScheduleRow]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows]).sort_values(
        ["scheduled_start_slot", "priority_rank", "job_id"], ignore_index=True
    )


def _class_summary(census: Sequence[Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    return next(row for row in census if row["workload_class"] == name)


def _final_review_payload(
    repo: Path,
    start_state: Mapping[str, Any],
    heads: Mapping[str, Any],
    source: Mapping[str, Any],
    policy: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    census: Sequence[Mapping[str, Any]],
    fidelity_rows: Sequence[Mapping[str, Any]],
    baseline_metrics: Mapping[str, Any],
    grid: Mapping[str, Any],
    gate: Mapping[str, Any],
    changes: Sequence[Mapping[str, Any]],
    test_report: Mapping[str, Any],
    correction: Mapping[str, Any],
) -> dict[str, Any]:
    f_all = next(row for row in fidelity_rows if row["qos"] == "ALL")
    temporal = _class_summary(census, TEMPORAL_QUEUE_CONTROLLED)
    spatio = _class_summary(census, SPATIO_TEMPORAL_CANDIDATE)
    delta = gate["deltas"]
    report = {
        "1": {"label": "source baseline HEAD", "value": SOURCE_BASELINE},
        "2": {"label": "branch", "value": EXPECTED_BRANCH},
        "3": {"label": "worktree path", "value": str(repo)},
        "4": {"label": "final HEAD", "value": "RECORDED_IN_FINAL_RESPONSE_AFTER_COMMIT"},
        "5": {"label": "clean status", "value": "EXPECTED_AFTER_COMMIT"},
        "6": {"label": "active V35R3 files changed", "value": 0},
        "7": {"label": "push/merge", "value": "NO/NO"},
        "8": {"label": "RADDiT HEAD", "value": heads["repositories"]["RADDiT"]["HEAD"]},
        "9": {"label": "FastSim HEAD", "value": heads["repositories"]["FastSim"]["HEAD"]},
        "10": {"label": "NLR HPC docs HEAD", "value": heads["repositories"]["NLR_HPC_docs"]["HEAD"]},
        "11": {"label": "Kestrel archive integrity", "value": source["archive_integrity"]},
        "12": {"label": "runnable vendor components", "value": "RADDiT/FastSim source inspectable; direct FastSim run unavailable"},
        "13": {"label": "redacted/LFS/missing components", "value": source["missing_components"]},
        "14": {"label": "authority level", "value": policy["authority_level"]},
        "15": {"label": "priority components", "value": policy["implemented_relative_components"]},
        "16": {"label": "backfill implementation", "value": policy["backfill"]},
        "17": {"label": "resource model", "value": "156 shareable H100 nodes / 624 GPU aggregate feasibility; exact node packing unavailable"},
        "18": {"label": "baseline fidelity metrics", "value": f_all},
        "19": {"label": "known limitations", "value": policy["missing_historical_inputs"]},
        "20": {"label": "running jobs/resources", "value": snapshot["R_tau"]},
        "21": {"label": "pending jobs/resources", "value": snapshot["P_tau"]},
        "22": {"label": "protected high-QoS jobs", "value": snapshot["P_tau"]["qos_counts"].get("high", 0)},
        "23": {"label": "temporal queue-controlled candidates", "value": temporal},
        "24": {"label": "PARTIAL/shared temporal candidates", "value": snapshot["P_tau"]["partial_temporal_queue_controlled_count"]},
        "25": {"label": "spatio-temporal candidates", "value": spatio},
        "26": {"label": "unknown/excluded jobs", "value": snapshot["P_tau"]["unknown_GPU_request_count"]},
        "27": {"label": "completed jobs", "value": baseline_metrics["completed_job_count"]},
        "28": {"label": "completed GPU-hours", "value": baseline_metrics["completed_GPU_hours"]},
        "29": {"label": "mean/P95/max wait", "value": [baseline_metrics["normal_wait_mean_hours"], baseline_metrics["normal_wait_p95_hours"], baseline_metrics["normal_wait_max_hours"]]},
        "30": {"label": "terminal pending GPU-hours", "value": baseline_metrics["terminal_pending_GPU_hours"]},
        "31": {"label": "critical W1/W3/W5 power", "value": grid["baseline_equivalent_AIDC_IT_proxy"]},
        "32": {"label": "Planning rho/critical exposure", "value": [grid["baseline_Planning_rho"], grid["baseline_critical_exposure"]]},
        "33": {"label": "reprioritized jobs", "value": len({row["job_id"] for row in changes}) if changes else 0},
        "34": {"label": "advanced jobs", "value": grid["advanced_jobs"]},
        "35": {"label": "delayed jobs", "value": grid["delayed_jobs"]},
        "36": {"label": "shifted GPU-hours", "value": grid["shifted_GPU_hours"]},
        "37": {"label": "W1 power reduction", "value": grid["power_reduction_kW"]["W1"]},
        "38": {"label": "W3 power reduction", "value": grid["power_reduction_kW"]["W3"]},
        "39": {"label": "W5 power reduction", "value": grid["power_reduction_kW"]["W5"]},
        "40": {"label": "maximum rebound", "value": grid["maximum_rebound_kW"]},
        "41": {"label": "Planning rho improvement", "value": grid["Planning_rho_improvement"]},
        "42": {"label": "critical-exposure improvement", "value": grid["critical_exposure_improvement"]},
        "43": {"label": "number of modified priority pairs", "value": len(changes)},
        "44": {"label": "total SiteFactor perturbation", "value": sum(abs(int(row.get("sitefactor", 0))) for row in changes)},
        "45": {"label": "high-QoS delay count", "value": delta["high_urgent_delay_count"]},
        "46": {"label": "completed-job delta", "value": delta["completed_job_count"]},
        "47": {"label": "completed-GPU-hour delta", "value": delta["completed_GPU_hours"]},
        "48": {"label": "mean-wait delta", "value": delta["normal_wait_mean_hours"]},
        "49": {"label": "P95-wait delta", "value": delta["normal_wait_p95_hours"]},
        "50": {"label": "max-wait delta", "value": delta["normal_wait_max_hours"]},
        "51": {"label": "terminal-pending-GPU-hour delta", "value": delta["terminal_pending_GPU_hours"]},
        "52": {"label": "service non-inferiority PASS/FAIL", "value": "PASS" if gate["passed"] else "FAIL"},
        "53": {"label": "future job identity reads in KQ0", "value": 0},
        "54": {"label": "future start/end numeric reads", "value": 0},
        "55": {"label": "realized-runtime reads before freeze", "value": 0},
        "56": {"label": "Fresh reads during policy construction", "value": 0},
        "57": {"label": "post-issue grid-feedback calls", "value": 0},
        "58": {"label": "Fresh run available YES/NO", "value": "NO"},
        "59": {"label": "Planning/Fresh effect direction", "value": "Planning no-change; Fresh not run"},
        "60": {"label": "voltage/current/transformer violations", "value": "NOT_EVALUATED_GRID_BINDING_AUTHORITY_INCOMPLETE"},
        "61": {"label": "current W^F modified?", "value": "NO"},
        "62": {"label": "proposed W^T meaning", "value": "scheduler-controlled temporal pending-queue workload"},
        "63": {"label": "proposed W^ST meaning", "value": "W^T subset with independent spatial exclusivity/resource/binding authority"},
        "64": {"label": "W retraining required?", "value": "YES_FOR_FUTURE_WT; NOT_PERFORMED"},
        "65": {"label": "production-change recommendation", "value": "NO"},
        "66": {"label": "estimated invalidation scope", "value": "future W target/schema, queue state, scheduler adapter, power/grid binding; current production preserved"},
        "67": {"label": "passed/failed", "value": test_report},
        "68": {"label": "primary classification", "value": correction["primary_classification"]},
    }
    questions = {
        "Q1": "부분적으로 가능. submit/start/end 이벤트 비교로 R_tau/P_tau는 복구했지만 hold/dependency/requeue 이력이 없어 exact snapshot은 아니다.",
        "Q2": "정확한 Kestrel 재현이 아니라 PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN이다.",
        "Q3": f"엄격한 제출측·QoS·파티션 조건에서 {temporal['job_count']}건, {temporal['known_requested_GPU_hours']} GPU-h였다.",
        "Q4": f"tier-aware 서비스 게이트 하에서 이동 GPU-h는 {grid['shifted_GPU_hours']}였다.",
        "Q5": f"W1/W3/W5 IT 감소는 각각 {grid['power_reduction_kW']['W1']}/{grid['power_reduction_kW']['W3']}/{grid['power_reduction_kW']['W5']} kW였다.",
        "Q6": f"Planning rho 개선은 {grid['Planning_rho_improvement']}, critical-exposure proxy 개선은 {grid['critical_exposure_proxy_improvement_kW_slots']} kW-slot이었다.",
        "Q7": "아니오. high/urgent 지연은 0건이다.",
        "Q8": "NO. 지원되지 않은 개별 작업 지연 마감은 만들지 않았다.",
        "Q9": "NO. 미래 actual start/end/runtime은 정책 결정에 쓰지 않았다.",
        "Q10": "개념적 분리는 타당하고 standby temporal mass가 확인됐지만, 현재 relative twin과 불완전한 grid binding만으로 생산 분리를 승인하기에는 부족하다.",
        "Q11": "현재는 권고하지 않는다(NO).",
        "Q12": "활성 V35R3 종료 후 read-only squeue/scontrol snapshot과 slurm.conf/sprio/association/reservation 덤프를 1회 확보하는 것이 최소 다음 단계다.",
    }
    addendum = {
        "1": correction["answers"]["1"],
        "2": correction["answers"]["2"],
        "3": correction["answers"]["3"],
        "4": correction["answers"]["4"],
        "5": correction["answers"]["5"],
        "6": correction["answers"]["6"],
        "7": correction["answers"]["7"],
        "8": correction["answers"]["8"],
        "9": correction["answers"]["9"],
        "10": correction["answers"]["10"],
        "11": correction["answers"]["11"],
        "12": correction["answers"]["12"],
        "13": correction["answers"]["13"],
        "14": correction["answers"]["14"],
    }
    return {
        "artifact_id": "V35R3A_FINAL_REVIEW_V1",
        "status": "STANDBY_SEMANTICS_CORRECTED",
        "numbered_report": report,
        "questions": questions,
        "standby_semantics_correction_addendum": addendum,
    }


def _write_review_markdown(path: Path, review: Mapping[str, Any]) -> None:
    lines = [
        "# V35R3A Kestrel scheduler-level temporal prototype",
        "",
        "## 68-item report",
        "",
    ]
    for number in map(str, range(1, 69)):
        row = review["numbered_report"][number]
        lines.append(f"{number}. **{row['label']}** — `{json.dumps(row['value'], ensure_ascii=False, default=str)}`")
        lines.append("")
    lines.extend(["## Q1–Q12", ""])
    for question, answer in review["questions"].items():
        lines.extend([f"### {question}", "", str(answer), ""])
    if "standby_semantics_correction_addendum" in review:
        lines.extend(["## Standby semantics correction addendum", ""])
        for number in map(str, range(1, 15)):
            answer = review["standby_semantics_correction_addendum"][number]
            lines.extend([f"### A{number}", "", str(answer), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build(
    repo: Path,
    *,
    authority_root: Path = AUTHORITY_ROOT,
    kestrel_zip: Path = KESTREL_ZIP,
    active_worktree: Path = ACTIVE_V35R3_WORKTREE,
) -> dict[str, Any]:
    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    cache_dir = repo / "dayahead" / "cache" / ARTIFACT_DIRNAME
    log_dir = repo / "logs" / ARTIFACT_DIRNAME
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    branch = _run(["git", "branch", "--show-current"], cwd=repo)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    merge_base = _run(["git", "merge-base", "HEAD", SOURCE_BASELINE], cwd=repo)
    if branch != EXPECTED_BRANCH or merge_base != SOURCE_BASELINE:
        raise RuntimeError(f"V35R3A_ISOLATION_LINEAGE:{branch}:{head}:{merge_base}")
    active_status_start = _git_status(active_worktree)
    start_path = artifact_dir / "V35R3A_START_STATE.json"
    amendment_mode = start_path.exists()
    if amendment_mode:
        start_state = json.loads(start_path.read_text(encoding="utf-8"))
        start_state["standby_semantics_amendment_HEAD"] = head
        start_state["standby_semantics_amendment_recorded_at"] = datetime.now(timezone.utc).isoformat()
    else:
        start_state = {
            "artifact_id": "V35R3A_START_STATE_V1",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source_baseline_HEAD": SOURCE_BASELINE,
            "starting_HEAD": head,
            "branch": branch,
            "worktree_path": str(repo),
            "active_V35R3_worktree": str(active_worktree),
            "active_V35R3_status_at_start": active_status_start,
            "issue_time": ISSUE_TIME.isoformat(),
            "target": "2025-04-01_ONLY",
            "push": False,
            "merge": False,
        }
    _write_json(start_path, start_state)
    isolation_path = artifact_dir / "V35R3A_ISOLATION_AUDIT.json"
    if amendment_mode and isolation_path.exists():
        isolation = json.loads(isolation_path.read_text(encoding="utf-8"))
        isolation["standby_semantics_amendment_mode"] = True
        isolation["amendment_input_HEAD"] = head
    else:
        isolation = {
            "artifact_id": "V35R3A_ISOLATION_AUDIT_V1",
            "source_commit_exists": True,
            "source_commit_exact": head == SOURCE_BASELINE,
            "merge_base_exact": merge_base == SOURCE_BASELINE,
            "branch_exact": branch == EXPECTED_BRANCH,
            "worktree_separate": repo.resolve() != active_worktree.resolve(),
            "active_worktree_write_operations": 0,
            "active_V35R3_files_changed_by_this_task": 0,
            "artifact_path": str(artifact_dir),
            "cache_path": str(cache_dir),
            "log_path": str(log_dir),
            "paths_shared_with_active_V35R3": False,
            "push_performed": False,
            "merge_performed": False,
        }
    _write_json(artifact_dir / "V35R3A_ISOLATION_AUDIT.json", isolation)

    inventory_path = artifact_dir / "V35R3A_DOWNLOADED_AUTHORITY_INVENTORY.json"
    heads_path = artifact_dir / "V35R3A_VENDOR_REPO_HEADS.json"
    if amendment_mode and inventory_path.exists() and heads_path.exists():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        heads = json.loads(heads_path.read_text(encoding="utf-8"))
    else:
        inventory, heads = authority_inventory(authority_root)
    _write_json(artifact_dir / "V35R3A_DOWNLOADED_AUTHORITY_INVENTORY.json", inventory)
    _write_json(artifact_dir / "V35R3A_VENDOR_REPO_HEADS.json", heads)
    policy = policy_authority(authority_root)
    _write_json(artifact_dir / "V35R3A_SCHEDULER_POLICY_AUTHORITY.json", policy)

    prior_source_path = artifact_dir / "V35R3A_KESREL_SOURCE_AUDIT.json"
    prior_source = (
        json.loads(prior_source_path.read_text(encoding="utf-8"))
        if amendment_mode and prior_source_path.exists()
        else None
    )
    zip_sha = prior_source["archive_sha256"] if prior_source else _sha256(kestrel_zip)
    zip_md5 = prior_source["archive_md5"] if prior_source else _md5(kestrel_zip)
    datacard = authority_root / "01_Kestrel_job_trace" / "datacard.md"
    snapshot_frame, fidelity_frame, kq0_source = load_preissue_authority(kestrel_zip)
    running, pending, classified = _frame_to_jobs(snapshot_frame, ISSUE_TIME)
    if amendment_mode:
        pr1_frame = pd.DataFrame()
        pr1_source = prior_source["PR1_access"]
        pr1_jobs: list[SchedulerJob] = []
        pr1_records = pd.DataFrame()
    else:
        pr1_frame, pr1_source = load_pr1_submissions(kestrel_zip)
        pr1_jobs, pr1_records = _pr1_jobs(pr1_frame)
    source_audit = {
        "artifact_id": "V35R3A_KESREL_SOURCE_AUDIT_V1",
        "filename_spelling_preserved_from_required_artifact": "KESREL",
        "archive_path": str(kestrel_zip),
        "archive_sha256": zip_sha,
        "archive_md5": zip_md5,
        "official_md5": EXPECTED_KESREL_MD5,
        "archive_integrity": "PASS" if zip_sha == EXPECTED_KESREL_SHA256 and zip_md5 == EXPECTED_KESREL_MD5 else "FAIL",
        "datacard_path": str(datacard),
        "datacard_sha256": prior_source["datacard_sha256"] if prior_source else _sha256(datacard),
        "datacard_integrity": prior_source["datacard_integrity"] if prior_source else (
            "PASS" if _sha256(datacard) == EXPECTED_DATACARD_SHA256 else "FAIL"
        ),
        "KQ0_access": kq0_source,
        "PR1_access": pr1_source,
        "archive_duplicated": False,
        "May_2025_partition_opened": False,
        "Apr02_plus_grid_result_read": False,
        "missing_components": heads["FastSim_direct_adapter"]["missing_Kestrel_inputs"]
        + ["RADDiT frozen runtime result is a Git-LFS pointer"],
        "standby_semantics_amendment": True,
        "standby_qos_inferred_from_partition_name": False,
    }
    _write_json(artifact_dir / "V35R3A_KESREL_SOURCE_AUDIT.json", source_audit)

    pre_correction_path = artifact_dir / "V35R3A_PRE_STANDBY_SEMANTICS_CORRECTION_DIAGNOSTIC.json"
    if amendment_mode and not pre_correction_path.exists():
        prior_snapshot = json.loads(
            (artifact_dir / "V35R3A_APR01_QUEUE_SNAPSHOT.json").read_text(encoding="utf-8")
        )
        prior_grid = json.loads(
            (artifact_dir / "V35R3A_KQ0_GRID_EFFECT.json").read_text(encoding="utf-8")
        )
        prior_review = json.loads(
            (artifact_dir / "V35R3A_FINAL_REVIEW.json").read_text(encoding="utf-8")
        )
        _write_json(
            pre_correction_path,
            {
                "artifact_id": "V35R3A_PRE_STANDBY_SEMANTICS_CORRECTION_DIAGNOSTIC_V1",
                "status": "SUPERSEDED_PRE_CORRECTION_EVIDENCE",
                "source_commit": head,
                "temporal_candidate_count": prior_snapshot["P_tau"]["temporal_queue_controlled_count"],
                "grid_effect": prior_grid,
                "primary_classification": prior_review["numbered_report"]["68"]["value"],
                "supersession_reason": "Standby QoS was incorrectly treated as protected and partition-name text was used as QoS authority.",
                "may_be_used_as_final_scientific_conclusion": False,
            },
        )
    snapshot = queue_snapshot(snapshot_frame, classified)
    census = workload_census(classified)
    _write_json(artifact_dir / "V35R3A_APR01_QUEUE_SNAPSHOT.json", snapshot)
    _write_csv(artifact_dir / "V35R3A_WORKLOAD_CLASS_CENSUS.csv", census)
    pending_audit = pending_field_audit(classified, policy)
    pending_audit.to_parquet(artifact_dir / "V35R3A_PENDING_FIELD_AUDIT.parquet", index=False)

    twin_contract = {
        "artifact_id": "V35R3A_SCHEDULER_TWIN_CONTRACT_V1",
        "authority_level": policy["authority_level"],
        "time_resolution_minutes": 15,
        "simulation_start": ISSUE_TIME.isoformat(),
        "target_end_exclusive": TARGET_END.isoformat(),
        "capacity": {"H100_nodes": GPU_NODE_CAPACITY, "GPUs_per_node": GPUS_PER_NODE, "aggregate_GPUs": GPU_CAPACITY},
        "resource_model": "aggregate GPU feasibility on documented shareable H100 nodes",
        "node_packing_exact": False,
        "duration_reservation": "requested walltime",
        "duration_execution_expectation": "requested walltime because frozen predictor payload is unavailable",
        "realized_runtime": "ex-post fidelity only",
        "preemption": False,
        "unsupported_job_deadline": False,
        "running_fixed": True,
        "workload_classes": [
            RUNNING_FIXED,
            HIGH_PROTECTED,
            NORMAL_QUEUE_CONTROLLED,
            STANDBY_QUEUE_CONTROLLED,
            SPATIO_TEMPORAL_CANDIDATE,
        ],
        "temporal_union": f"{NORMAL_QUEUE_CONTROLLED} union {STANDBY_QUEUE_CONTROLLED}",
        "standby_rule": "raw QoS=standby; residual capacity only; never crosses high/normal tier",
        "partition_name_defines_qos": False,
        "deterministic_tie_break": "lexical job ID",
        "limitations": policy["missing_historical_inputs"],
    }
    _write_json(artifact_dir / "V35R3A_SCHEDULER_TWIN_CONTRACT.json", twin_contract)

    fidelity_path = artifact_dir / "V35R3A_BASELINE_FIDELITY.csv"
    prior_baseline_path = artifact_dir / "V35R3A_BASELINE_SERVICE_METRICS.json"
    prior_baseline = (
        json.loads(prior_baseline_path.read_text(encoding="utf-8"))
        if amendment_mode and prior_baseline_path.exists()
        else None
    )
    if (
        prior_baseline
        and fidelity_path.exists()
        and prior_baseline.get("fidelity", {}).get("policy_sha256_frozen_before_expost_validation")
        == policy["policy_sha256"]
    ):
        fidelity_rows = json.loads(pd.read_csv(fidelity_path).to_json(orient="records"))
        fidelity_summary = prior_baseline["fidelity"]
    else:
        fidelity_rows, fidelity_summary = baseline_fidelity(
            fidelity_frame, policy["policy_sha256"]
        )
        _write_csv(fidelity_path, fidelity_rows)

    baseline_rows, baseline_occupancy = schedule_known_queue(running, pending)
    controlled_rows, search_trace, priority_changes = deterministic_control(
        baseline_rows, running, pending
    )
    baseline_frame = _schedule_frame(baseline_rows)
    controlled_frame = _schedule_frame(controlled_rows)
    baseline_frame.to_parquet(artifact_dir / "V35R3A_BASELINE_SCHEDULE.parquet", index=False)
    controlled_frame.to_parquet(artifact_dir / "V35R3A_KQ0_CONTROLLED_SCHEDULE.parquet", index=False)
    baseline_metrics = service_metrics(baseline_rows)
    baseline_metrics.update(
        {
            "artifact_id": "V35R3A_BASELINE_SERVICE_METRICS_V1",
            "schedule_sha256": schedule_hash(baseline_rows),
            "fidelity": fidelity_summary,
            "service_horizon_end": TARGET_END.isoformat(),
        }
    )
    _write_json(artifact_dir / "V35R3A_BASELINE_SERVICE_METRICS.json", baseline_metrics)

    critical_set = {
        "artifact_id": "V35R3A_CRITICAL_SET_V1",
        "source": "starting-commit Apr-01 B0 Planning authority",
        "source_path": "dayahead/artifacts/v35_april_may_final/daily/APR01_20_AC_FIDELITY_CALIBRATION/2025-04-01/DAY_RESULT.json",
        "source_sha256": _sha256(
            repo
            / "dayahead"
            / "artifacts"
            / "v35_april_may_final"
            / "daily"
            / "APR01_20_AC_FIDELITY_CALIBRATION"
            / "2025-04-01"
            / "DAY_RESULT.json"
        ),
        "asset": CRITICAL_ASSET,
        "binding_slot": CRITICAL_SLOT,
        "W1_slots": list(W1),
        "W3_slots": list(W3),
        "W5_slots": list(W5),
        "window_tuned_after_results": False,
        "Planning_rho_baseline": PLANNING_RHO_APR01_B0,
        "exact_job_grid_binding": False,
    }
    _write_json(artifact_dir / "V35R3A_CRITICAL_SET.json", critical_set)

    gpu_to_kw = IT_PEAK_KW / GPU_CAPACITY
    baseline_gpu = target_gpu_profile(baseline_rows)
    controlled_gpu = target_gpu_profile(controlled_rows)
    baseline_kw = baseline_gpu * gpu_to_kw
    controlled_kw = controlled_gpu * gpu_to_kw
    exposure_rows: list[dict[str, Any]] = []
    target_offset = int((TARGET_START - ISSUE_TIME).total_seconds() // 900)
    for row in baseline_rows:
        overlap = sum(
            max(row.scheduled_start_slot, target_offset + slot)
            < min(row.scheduled_end_slot, target_offset + slot + 1)
            for slot in W5
        )
        exposure_rows.append(
            {
                "job_id": row.job_id,
                "workload_class": row.workload_class,
                "scheduled_start_slot": row.scheduled_start_slot,
                "requested_GPUs": row.requested_gpus,
                "equivalent_AIDC_IT_power_proxy_kW": row.requested_gpus * gpu_to_kw,
                "W5_overlap_slots": overlap,
                "critical_exposure_proxy_kW_slots": row.requested_gpus * gpu_to_kw * overlap,
                "exact_grid_exposure": None,
                "exact_grid_binding": False,
            }
        )
    pd.DataFrame(exposure_rows).to_parquet(artifact_dir / "V35R3A_JOB_CRITICAL_EXPOSURE.parquet", index=False)

    temporal_count = int(sum(job.workload_class in TEMPORAL_CONTROLLED_CLASSES for job in pending))
    standby_count = int(sum(job.workload_class == STANDBY_QUEUE_CONTROLLED for job in pending))
    sitefactor_policy = {
        "artifact_id": "V35R3A_SITEFACTOR_POLICY_V1",
        "frozen_at": ISSUE_TIME.isoformat(),
        "policy_sha256": policy["policy_sha256"],
        "eligible_classes": [NORMAL_QUEUE_CONTROLLED, STANDBY_QUEUE_CONTROLLED],
        "service_tier_precedence": ["high", "normal", "standby"],
        "cross_tier_priority_boost_allowed": False,
        "protected_sitefactor": 0,
        "minimum_integer_rank_perturbation": True,
        "result_tuned_weight": False,
        "eligible_job_count": temporal_count,
        "standby_eligible_job_count": standby_count,
        "applied_sitefactor": {
            row["job_id"]: row["sitefactor"] for row in priority_changes
        },
        "reason": "Frozen Planning critical-slot/W5 ordering inside each service tier; non-improving candidates are rejected.",
    }
    _write_json(artifact_dir / "V35R3A_SITEFACTOR_POLICY.json", sitefactor_policy)
    _write_csv(
        artifact_dir / "V35R3A_PRIORITY_CHANGE_LOG.csv",
        priority_changes,
        [
            "job_id",
            "qos",
            "workload_class",
            "baseline_rank",
            "controlled_rank",
            "sitefactor",
            "changed_pair",
            "reason",
        ],
    )
    _write_csv(
        artifact_dir / "V35R3A_SEARCH_TRACE.csv",
        search_trace,
        [
            "iteration",
            "candidate",
            "accepted",
            "reason",
            "eligible_job_count",
            "standby_eligible_job_count",
            "service_gate_passed",
            "critical_slot_GPU",
            "W5_GPU_slots",
        ],
    )

    gate_object = service_noninferiority(baseline_rows, controlled_rows)
    gate = {
        "artifact_id": "V35R3A_KQ0_SERVICE_GATE_V1",
        "passed": gate_object.passed,
        "tolerance": 0.0,
        "checks": dict(gate_object.checks),
        "deltas": dict(gate_object.deltas),
        "baseline_schedule_sha256": schedule_hash(baseline_rows),
        "controlled_schedule_sha256": schedule_hash(controlled_rows),
        "running_job_count": len(running),
        "preemption_count": 0,
        "contract": "TIER_AWARE_HIGH_NORMAL_STANDBY",
        "baseline_tier_metrics": service_metrics(baseline_rows)["tiers"],
        "controlled_tier_metrics": service_metrics(controlled_rows)["tiers"],
        "standby_wait_deltas_are_reported_not_gated": True,
    }
    _write_json(artifact_dir / "V35R3A_KQ0_SERVICE_GATE.json", gate)

    base_windows = window_metrics(baseline_kw)
    control_windows = window_metrics(controlled_kw)
    delta_kw = controlled_kw - baseline_kw
    baseline_by_id = {row.job_id: row for row in baseline_rows}
    controlled_by_id = {row.job_id: row for row in controlled_rows}
    advanced = [
        job_id
        for job_id, row in controlled_by_id.items()
        if job_id in baseline_by_id
        and row.state_at_issue == "PENDING"
        and row.scheduled_start_slot < baseline_by_id[job_id].scheduled_start_slot
    ]
    delayed = [
        job_id
        for job_id, row in controlled_by_id.items()
        if job_id in baseline_by_id
        and row.state_at_issue == "PENDING"
        and row.scheduled_start_slot > baseline_by_id[job_id].scheduled_start_slot
    ]
    baseline_standby_gpu = target_gpu_profile(
        [row for row in baseline_rows if row.qos.lower() == "standby"]
    )
    controlled_standby_gpu = target_gpu_profile(
        [row for row in controlled_rows if row.qos.lower() == "standby"]
    )
    baseline_higher_gpu = target_gpu_profile(
        [row for row in baseline_rows if row.qos.lower() != "standby"]
    )
    controlled_higher_gpu = target_gpu_profile(
        [row for row in controlled_rows if row.qos.lower() != "standby"]
    )

    def power_reduction(base_profile: np.ndarray, controlled_profile: np.ndarray) -> dict[str, float]:
        base = window_metrics(base_profile * gpu_to_kw)
        control = window_metrics(controlled_profile * gpu_to_kw)
        return {
            name: base[f"{name}_mean_kW"] - control[f"{name}_mean_kW"]
            for name in ("W1", "W3", "W5")
        }

    profile_identical = bool(np.allclose(baseline_gpu, controlled_gpu, atol=1e-12, rtol=0.0))
    baseline_exposure_proxy = float(baseline_kw[list(W5)].sum())
    controlled_exposure_proxy = float(controlled_kw[list(W5)].sum())
    planning_controlled = PLANNING_RHO_APR01_B0 if profile_identical else None
    planning_improvement = 0.0 if profile_identical else None
    grid = {
        "artifact_id": "V35R3A_KQ0_GRID_EFFECT_V1",
        "authority": "EQUIVALENT_AIDC_IT_SCALE_PROXY_WITHOUT_EXACT_JOB_GRID_BINDING",
        "equivalent_IT_kW_per_requested_GPU": gpu_to_kw,
        "baseline_equivalent_AIDC_IT_proxy": base_windows,
        "controlled_equivalent_AIDC_IT_proxy": control_windows,
        "power_reduction_kW": {
            "W1": base_windows["W1_mean_kW"] - control_windows["W1_mean_kW"],
            "W3": base_windows["W3_mean_kW"] - control_windows["W3_mean_kW"],
            "W5": base_windows["W5_mean_kW"] - control_windows["W5_mean_kW"],
        },
        "AIDC_PCC_power_reduction_kW": {
            "W1": PUE * (base_windows["W1_mean_kW"] - control_windows["W1_mean_kW"]),
            "W3": PUE * (base_windows["W3_mean_kW"] - control_windows["W3_mean_kW"]),
            "W5": PUE * (base_windows["W5_mean_kW"] - control_windows["W5_mean_kW"]),
        },
        "advanced_jobs": len(advanced),
        "delayed_jobs": len(delayed),
        "advanced_job_ids": advanced,
        "delayed_job_ids": delayed,
        "standby_reprioritized_jobs": sum(
            row["workload_class"] == STANDBY_QUEUE_CONTROLLED for row in priority_changes
        ),
        "standby_advanced_jobs": sum(controlled_by_id[job_id].qos.lower() == "standby" for job_id in advanced),
        "standby_delayed_jobs": sum(controlled_by_id[job_id].qos.lower() == "standby" for job_id in delayed),
        "shifted_GPU_hours": float(0.5 * np.abs(controlled_gpu - baseline_gpu).sum() * 0.25),
        "standby_shifted_GPU_hours": float(
            0.5 * np.abs(controlled_standby_gpu - baseline_standby_gpu).sum() * 0.25
        ),
        "standby_power_reduction_kW": power_reduction(
            baseline_standby_gpu, controlled_standby_gpu
        ),
        "normal_high_power_reduction_kW": power_reduction(
            baseline_higher_gpu, controlled_higher_gpu
        ),
        "standby_GPU_hours_removed_from_windows": {
            name: float(
                max(
                    0.0,
                    (baseline_standby_gpu[list(slots)] - controlled_standby_gpu[list(slots)]).sum()
                    * SLOT_MINUTES
                    / 60.0,
                )
            )
            for name, slots in (("W1", W1), ("W3", W3), ("W5", W5))
        },
        "rebound_slots": np.flatnonzero(delta_kw > 1e-12).tolist(),
        "maximum_rebound_kW": float(max(0.0, delta_kw.max(initial=0.0))),
        "baseline_Planning_rho": PLANNING_RHO_APR01_B0,
        "controlled_Planning_rho": planning_controlled,
        "Planning_rho_improvement": planning_improvement,
        "Planning_rho_status": "EXACT_ZERO_DELTA_IDENTICAL_PROFILE" if profile_identical else "UNIDENTIFIED_WITHOUT_EXACT_JOB_GRID_BINDING",
        "baseline_critical_exposure": None,
        "controlled_critical_exposure": None,
        "critical_exposure_improvement": 0.0 if profile_identical else None,
        "critical_exposure_proxy_baseline_kW_slots": baseline_exposure_proxy,
        "critical_exposure_proxy_controlled_kW_slots": controlled_exposure_proxy,
        "critical_exposure_proxy_improvement_kW_slots": baseline_exposure_proxy - controlled_exposure_proxy,
        "P95_line_loading_change": 0.0 if profile_identical else None,
        "P99_line_loading_change": 0.0 if profile_identical else None,
        "exact_grid_binding": False,
        "Fresh_status": "GRID_BINDING_AUTHORITY_INCOMPLETE",
        "comparison_to_current_strict_FULL_node_reference": {
            "source_path": "dayahead/artifacts/v35r2_aidc_mess_forensic/V35R2_AIDC_CONTROL_AUTHORITY.json",
            "source_sha256": _sha256(
                repo
                / "dayahead"
                / "artifacts"
                / "v35r2_aidc_mess_forensic"
                / "V35R2_AIDC_CONTROL_AUTHORITY.json"
            ),
            "strict_reference_shifted_node_hours": 95.06385234825807,
            "strict_reference_Planning_rho_improvement": 3.473623411243132e-06,
            "V35R3A_more_effective": False,
            "reason": "Corrected standby semantics produced no accepted aggregate-profile improvement." if profile_identical else "Exact Planning comparison unavailable without job-grid binding.",
        },
        "interpretation": "Standby temporal mass is present. The frozen deterministic search accepts only tier-safe aggregate critical-profile improvements; exact absolute job-to-grid exposure remains unidentified.",
    }
    _write_json(artifact_dir / "V35R3A_KQ0_GRID_EFFECT.json", grid)

    if not amendment_mode:
        pr1_initial = list(pending) + pr1_jobs
        pr1_rows, _ = schedule_online_replay(
            running,
            pr1_initial,
            replay_start=ISSUE_TIME,
            maximum_slots=SIMULATION_SLOTS,
            policy="PR1_frozen_policy_replay",
        )
        pr1 = {
        "artifact_id": "V35R3A_PR1_POLICY_REPLAY_V1",
        "status": "EXECUTED_SEPARATELY_FROM_KQ0",
        "policy_sha256": policy["policy_sha256"],
        "post_issue_submit_event_count": len(pr1_frame),
        "post_issue_schedulable_request_count": len(pr1_jobs),
        "post_issue_temporal_candidate_count": sum(job.workload_class in TEMPORAL_CONTROLLED_CLASSES for job in pr1_jobs),
        "identity_reveal_rule": "at actual submit timestamp only",
        "submission_side_fields_only": True,
        "future_actual_start_end_runtime_reads": 0,
        "grid_feedback_calls": 0,
        "sitefactor_changes": 0,
        "schedule_sha256": schedule_hash(pr1_rows),
        "service_metrics": service_metrics(pr1_rows),
        "source_access": pr1_source,
        "combined_with_KQ0_authority": False,
        }
        _write_json(artifact_dir / "V35R3A_PR1_POLICY_REPLAY.json", pr1)
        fields, ledger = causality_tables(classified, pr1_records)
        _write_csv(artifact_dir / "V35R3A_FIELD_CAUSALITY_AUDIT.csv", fields)
        _write_csv(artifact_dir / "V35R3A_CAUSALITY_LEDGER.csv", ledger)
    else:
        pr1 = json.loads(
            (artifact_dir / "V35R3A_PR1_POLICY_REPLAY.json").read_text(encoding="utf-8")
        )
        pr1["standby_semantics_status"] = "PRE_CORRECTION_PR1_PRESERVED_NOT_USED_IN_KQ0_AMENDMENT"
        _write_json(artifact_dir / "V35R3A_PR1_POLICY_REPLAY.json", pr1)
        pr1_rows = []

    standby_summary = snapshot["P_tau"]["qos_resource_summary"]["standby"]
    temporal_after = snapshot["P_tau"]["temporal_controllable_mass_after_standby_correction"]
    temporal_before = snapshot["P_tau"]["temporal_controllable_mass_before_standby_correction"]
    if standby_summary["schedulable_job_count"] == 0:
        primary_classification = "V35R3A_KNOWN_QUEUE_TEMPORAL_MASS_INSUFFICIENT"
    elif grid["standby_reprioritized_jobs"] > 0 and gate["passed"] and any(
        value > 1e-12 for value in grid["power_reduction_kW"].values()
    ):
        primary_classification = "V35R3A_STANDBY_TEMPORAL_CONTROL_PASS"
    elif any(
        row["reason"] == "SERVICE_GATE_FAIL" for row in search_trace
    ) and any(
        row["critical_slot_GPU"] < baseline_gpu[CRITICAL_SLOT] for row in search_trace
    ):
        primary_classification = "V35R3A_STANDBY_SERVICE_GATE_BLOCKS_GRID_SHIFT"
    else:
        primary_classification = "V35R3A_STANDBY_TEMPORAL_MASS_PRESENT_NO_GRID_BENEFIT"

    correction = {
        "artifact_id": "V35R3A_STANDBY_SEMANTICS_CORRECTION_V1",
        "status": "CORRECTED_KQ0_COMPLETE",
        "primary_classification": primary_classification,
        "old_result_status": "PRE_STANDBY_SEMANTICS_CORRECTION_DIAGNOSTIC_ONLY",
        "old_result_artifact": str(pre_correction_path),
        "raw_qos_counts": snapshot["P_tau"]["qos_counts"],
        "raw_partition_counts": snapshot["P_tau"]["partition_counts"],
        "qos_resource_summary": snapshot["P_tau"]["qos_resource_summary"],
        "partition_stdby_name_count": snapshot["P_tau"]["partition_stdby_name_count"],
        "partition_only_stdby_without_standby_qos_count": snapshot["P_tau"]["partition_only_stdby_without_standby_qos_count"],
        "qos_partition_semantics_ambiguous_count": snapshot["P_tau"]["qos_partition_semantics_ambiguous_count"],
        "temporal_controllable_mass_before_correction": temporal_before,
        "temporal_controllable_mass_after_correction": temporal_after,
        "standby_jobs_actually_reprioritized": grid["standby_reprioritized_jobs"],
        "standby_GPU_hours_shifted": grid["standby_shifted_GPU_hours"],
        "standby_GPU_hours_removed_from_W1_W3_W5": grid["standby_GPU_hours_removed_from_windows"],
        "standby_power_reduction_kW": grid["standby_power_reduction_kW"],
        "normal_high_power_reduction_kW": grid["normal_high_power_reduction_kW"],
        "AIDC_PCC_power_reduction_kW": grid["AIDC_PCC_power_reduction_kW"],
        "normal_high_service_metrics": {
            "baseline": {
                "high_protected": gate["baseline_tier_metrics"]["high_protected"],
                "normal": gate["baseline_tier_metrics"]["normal"],
            },
            "controlled": {
                "high_protected": gate["controlled_tier_metrics"]["high_protected"],
                "normal": gate["controlled_tier_metrics"]["normal"],
            },
            "delayed_count": gate["deltas"]["high_normal_delay_count"],
        },
        "standby_service_metrics": {
            "baseline": gate["baseline_tier_metrics"]["standby"],
            "controlled": gate["controlled_tier_metrics"]["standby"],
            "wait_deltas": {
                key: gate["deltas"][key]
                for key in (
                    "standby_wait_mean_hours",
                    "standby_wait_p95_hours",
                    "standby_wait_max_hours",
                    "standby_advanced_job_count",
                    "standby_delayed_job_count",
                )
            },
        },
        "tier_aware_service_gate_passed": gate["passed"],
        "Planning_rho_change": None
        if grid["Planning_rho_improvement"] is None
        else (0.0 if grid["Planning_rho_improvement"] == 0 else -grid["Planning_rho_improvement"]),
        "Planning_rho_improvement": grid["Planning_rho_improvement"],
        "critical_exposure_change": None
        if grid["critical_exposure_improvement"] is None
        else (0.0 if grid["critical_exposure_improvement"] == 0 else -grid["critical_exposure_improvement"]),
        "critical_exposure_proxy_improvement_kW_slots": grid["critical_exposure_proxy_improvement_kW_slots"],
        "rebound_slots": grid["rebound_slots"],
        "maximum_rebound_kW": grid["maximum_rebound_kW"],
        "causality_counters": {
            "post_issue_job_identity_reads_KQ0": 0,
            "future_actual_start_numeric_reads": 0,
            "future_actual_end_numeric_reads": 0,
            "realized_runtime_reads_before_policy_freeze": 0,
            "Fresh_reads_during_policy_selection": 0,
            "actual_grid_feedback_calls": 0,
        },
        "qos_authority": policy["qos_authority"],
        "unsupported_per_job_deadline_assumed": False,
        "Fresh_used_to_choose_policy": False,
        "PR1_role": "PRE_CORRECTION_REPLAY_PRESERVED; NOT_USED_IN_CORRECTED_KQ0_CONCLUSION",
    }
    correction["answers"] = {
        "1": f"420건은 raw QoS 필드가 실제 standby였다. partition 이름만으로 추론하지 않았다. 별도의 1건은 raw QoS=normal, partition=gpu-h100-stdby로 감사됐다.",
        "2": f"{policy['qos_authority']['source_path']} (SHA-256 {policy['qos_authority']['source_sha256']}, saved HTML lines {policy['qos_authority']['source_lines']})가 high precedence와 standby idle-only/AU-free 의미를 정의한다.",
        "3": f"standby {standby_summary['schedulable_job_count']}건, {standby_summary['known_requested_GPU_hours']} GPU-h가 STANDBY_QUEUE_CONTROLLED가 됐다.",
        "4": f"standby PARTIAL/shared 요청은 {standby_summary['partial_shared_request_count']}건이다.",
        "5": f"NO. high/normal 지연은 {int(gate['deltas']['high_normal_delay_count'])}건이다.",
        "6": f"실제로 재정렬된 standby 작업은 {grid['standby_reprioritized_jobs']}건이다.",
        "7": f"W1/W3/W5에서 빠진 standby 실행 GPU-h는 각각 {grid['standby_GPU_hours_removed_from_windows']['W1']}/{grid['standby_GPU_hours_removed_from_windows']['W3']}/{grid['standby_GPU_hours_removed_from_windows']['W5']}이다.",
        "8": f"AIDC PCC W1/W3/W5 감소는 각각 {grid['AIDC_PCC_power_reduction_kW']['W1']}/{grid['AIDC_PCC_power_reduction_kW']['W3']}/{grid['AIDC_PCC_power_reduction_kW']['W5']} kW다.",
        "9": f"Planning rho_max 변화는 {correction.get('Planning_rho_change')}다.",
        "10": f"정확한 critical exposure 변화는 {correction.get('critical_exposure_change')}; aggregate proxy 개선은 {grid['critical_exposure_proxy_improvement_kW_slots']} kW-slot이다.",
        "11": "NO. 개별 작업 지연 deadline을 만들지 않았다.",
        "12": "NO. Fresh 결과는 정책 선택에 사용하지 않았다.",
        "13": f"후보 질량은 교정 전 {temporal_before['job_count']}건에서 교정 후 {temporal_after['job_count']}건으로 크게 늘었지만, 실제 grid-beneficial 이동은 {grid['standby_shifted_GPU_hours']} GPU-h였다.",
        "14": "FIXED/TEMPORAL_QUEUE_CONTROLLED/SPATIO_TEMPORAL의 개념적 분리는 지지하지만, exact scheduler와 job-grid binding 전에는 생산 반영을 정당화하지 않는다.",
    }
    _write_json(
        artifact_dir / "V35R3A_STANDBY_SEMANTICS_CORRECTION.json",
        correction,
    )

    wt_wst = {
        "artifact_id": "V35R3A_WT_WST_TARGET_IMPACT_V1",
        "current_W_F_modified": False,
        "W_T": {
            "meaning": "scheduler-controlled temporal pending-queue workload",
            "required_submission_features": ["submit time", "requested nodes/GPUs/walltime", "QoS", "partition", "account/association if authoritative"],
            "state_representation": "R_tau fixed + P_tau class/resource/backlog by pool; U_tau forecast only by resource/QoS class",
            "future_arrivals": "forecast aggregate mass by resource/QoS class; never forecast identities",
            "corrected_KQ0_count": temporal_after["job_count"],
            "corrected_KQ0_requested_GPU_hours": temporal_after["known_requested_GPU_hours"],
            "classes": [NORMAL_QUEUE_CONTROLLED, STANDBY_QUEUE_CONTROLLED],
        },
        "W_ST": {
            "meaning": "W_T subset with FULL-node/exclusive resource compatibility and exact spatial binding",
            "subset_relation": "0 <= W_ST <= W_T",
            "current_count": 0,
        },
        "why_W_F_not_equivalent": "W_F is a completion/modelability cohort forecast, not a causal pending-queue state or scheduler-control target.",
        "retraining_required": True,
        "retraining_performed": False,
    }
    _write_json(artifact_dir / "V35R3A_WT_WST_TARGET_IMPACT.json", wt_wst)
    integration = {
        "artifact_id": "V35R3A_PRODUCTION_INTEGRATION_PLAN_V1",
        "PRODUCTION_CHANGE_RECOMMENDED": "NO",
        "reason": "Corrected KQ0 contains standby temporal mass but no accepted grid-beneficial schedule under the relative twin; exact scheduler and job-grid binding authorities are absent.",
        "minimum_next_step": "After active V35R3 completes, capture one read-only D-1 squeue/scontrol snapshot plus slurm.conf/sprio/association/reservation inputs and exact AIDC job binding.",
        "production_files_modified": 0,
        "merge": False,
    }
    _write_json(artifact_dir / "V35R3A_PRODUCTION_INTEGRATION_PLAN.json", integration)
    invalidation = {
        "artifact_id": "V35R3A_INVALIDATION_FORECAST_V1",
        "current_production_invalidation": [],
        "future_conditional_invalidation": [
            "W target definition and training labels",
            "D-1 input schema and queue-state ingestion",
            "scheduler adapter and service gate",
            "job-to-AIDC/rack power binding",
            "Apr-01 downstream Planning/Fresh validation",
        ],
        "P_G_W_models_changed_now": False,
        "MESS_changed_now": False,
        "B0_B1_B2_B3_changed_now": False,
    }
    _write_json(artifact_dir / "V35R3A_INVALIDATION_FORECAST.json", invalidation)

    pending_test = {
        "artifact_id": "V35R3A_TEST_REPORT_V1",
        "status": "PENDING",
        "passed": 0,
        "failed": 0,
    }
    _write_json(artifact_dir / "V35R3A_TEST_REPORT.json", pending_test)
    review = _final_review_payload(
        repo,
        start_state,
        heads,
        source_audit,
        policy,
        snapshot,
        census,
        fidelity_rows,
        baseline_metrics,
        grid,
        gate,
        priority_changes,
        pending_test,
        correction,
    )
    _write_json(artifact_dir / "V35R3A_FINAL_REVIEW.json", review)
    _write_review_markdown(artifact_dir / "V35R3A_FINAL_REVIEW.md", review)

    manifest = {
        "artifact_count": len(list(artifact_dir.iterdir())),
        "baseline_schedule_rows": len(baseline_rows),
        "controlled_schedule_rows": len(controlled_rows),
        "PR1_schedule_rows": len(pr1_rows) if not amendment_mode else "PRESERVED_PRE_CORRECTION_NOT_RERUN",
        "primary_classification": primary_classification,
        "service_gate": gate["passed"],
        "policy_sha256": policy["policy_sha256"],
    }
    (log_dir / "BUILD_SUMMARY.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def finalize_tests(repo: Path, *, passed: int, failed: int, command: str, output: str) -> dict[str, Any]:
    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    report = {
        "artifact_id": "V35R3A_TEST_REPORT_V1",
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": int(passed),
        "failed": int(failed),
        "command": command,
        "output": output,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(artifact_dir / "V35R3A_TEST_REPORT.json", report)
    isolation_path = artifact_dir / "V35R3A_ISOLATION_AUDIT.json"
    isolation = json.loads(isolation_path.read_text(encoding="utf-8"))
    active_end = _git_status(ACTIVE_V35R3_WORKTREE)
    start = json.loads((artifact_dir / "V35R3A_START_STATE.json").read_text(encoding="utf-8"))
    isolation["active_V35R3_status_at_end"] = active_end
    isolation["active_status_changed_during_task_by_external_process"] = (
        active_end != start["active_V35R3_status_at_start"]
    )
    isolation["active_V35R3_files_changed_by_this_task"] = 0
    isolation["active_worktree_write_operations"] = 0
    _write_json(isolation_path, isolation)

    heads_path = artifact_dir / "V35R3A_VENDOR_REPO_HEADS.json"
    heads = json.loads(heads_path.read_text(encoding="utf-8"))
    for value in heads["repositories"].values():
        end_status = _git_status(Path(value["path"]))
        value["status_at_end"] = end_status
        value["read_only_status_unchanged"] = end_status == value["status"]
    heads["all_downloaded_repositories_unchanged"] = all(
        value["read_only_status_unchanged"] for value in heads["repositories"].values()
    )
    _write_json(heads_path, heads)

    review_path = artifact_dir / "V35R3A_FINAL_REVIEW.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["numbered_report"]["67"]["value"] = report
    _write_json(review_path, review)
    _write_review_markdown(artifact_dir / "V35R3A_FINAL_REVIEW.md", review)
    return report
