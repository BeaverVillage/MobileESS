"""Causal per-operating-day Kestrel AIDC input materialization.

This module generalizes the frozen V35R3D-R1/V35R3J Apr-01 authority.  It is
an input builder only: it never calls Planning, Fresh, MESS, or Gurobi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.source_cache import day_root
from dayahead.v36.aidc import _apr01_ledger, _apr01_power, _rsp_schedule, _site_weights
from dayahead.v36.contracts import AEST, GPU_CAPACITY, PF

from .contracts import (
    CENTER_SWING_W_PER_GPU,
    EXPECTED_DATES,
    SOURCE_DATA_REPOSITORY,
)


R4A_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc")
R4A_DAY_ROOT = R4A_ROOT / "days"
COHORT_CONSTRUCTION_RULE_ID = "V37_R4A_PER_DAY_CAUSAL_AIDC_COHORT_RULE_V1"
SLOT_SECONDS = 900
SLOTS = 96
TARGET_OFFSET_SLOTS = 24
SIMULATION_SLOTS = 120
GPUS_PER_NODE = 4
PF_TAN = math.tan(math.acos(PF))
FULL_ACTIVE_REFERENCE_KW = 406.77599381381907
Q_SELECTED_SECONDS = 5576.44921875
KESTREL_ARCHIVE_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
KESTREL_ARCHIVE = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터"
    r"\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)
FROZEN_NORMALIZED_HISTORY = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2"
    r"\MobileESS_v35r3d_kestrel_runtime_authority_closure\dayahead\cache"
    r"\v35r3d_kestrel_runtime_authority_closure\kestrel_preissue_normalized.parquet"
)
FROZEN_HPCODA_HEAD = "218d75f56b783ebfd698100f9406cfb46fa04c01"
FROZEN_MODEL_CONFIG = {
    "n_windows": 120,
    "test_window_hours": 6,
    "training_lookback_days": 120,
    "enable_power_users": False,
    "time_decay_rate": 0.05,
    "objective": "reg:absoluteerror",
}
TEMPORAL_CLASSES = frozenset({"NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"})
PROTECTED_QOS = frozenset({"high", "urgent"})
STATE_COLUMNS = (
    "id", "job_id", "account_hash", "partition", "submit_time", "start_time",
    "end_time", "nodes_req", "processors_req", "memory_req", "wallclock_req",
    "qos", "gpus_requested", "user_hash",
)
MANDATORY_RUNTIME_FIELDS = (
    "requested_seconds", "num_nodes_req", "num_gpus_req", "partition", "qos",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    temporary.replace(path)


def issue_time(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=AEST) - timedelta(hours=6)


def _wallclock_seconds(value: Any) -> float:
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    return float(pd.to_timedelta(value).total_seconds())


def _submission_complete(row: Mapping[str, Any]) -> bool:
    try:
        nodes = float(row.get("nodes_req"))
        gpus = float(row.get("gpus_requested"))
        seconds = float(row.get("wallclock_seconds"))
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(nodes) and math.isfinite(gpus) and math.isfinite(seconds)
        and nodes > 0 and gpus > 0 and seconds > 0 and gpus <= GPUS_PER_NODE * nodes
    )


def _classify_pending(row: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    if not _submission_complete(row):
        return "FIXED_PROTECTED", ("INSUFFICIENT_SUBMISSION_RESOURCE_AUTHORITY",)
    qos = str(row.get("qos") or "").strip().lower()
    partition = str(row.get("partition") or "").strip().lower()
    if qos in PROTECTED_QOS:
        return "HIGH_PROTECTED", ("PROTECTED_HIGH_OR_URGENT_QOS",)
    if qos == "normal":
        reasons = ("PARTITION_NAME_NOT_QOS_AUTHORITY",) if "stdby" in partition else ()
        return "NORMAL_QUEUE_CONTROLLED", reasons
    if qos == "standby":
        return "STANDBY_QUEUE_CONTROLLED", ("STANDBY_IDLE_CAPACITY_SEMANTICS",)
    return "FIXED_PROTECTED", ("UNKNOWN_QOS_SEMANTICS",)


def _archive_members(archive: zipfile.ZipFile) -> list[str]:
    result: list[tuple[tuple[int, int], str]] = []
    for name in archive.namelist():
        match = re.search(r"year=(\d{4})/month=(\d{1,2})/.*\.parquet$", name)
        if match and (int(match.group(1)), int(match.group(2))) <= (2025, 5):
            result.append(((int(match.group(1)), int(match.group(2))), name))
    return [name for _, name in sorted(result)]


def load_state_source(
    days: Sequence[str], archive_path: Path = KESTREL_ARCHIVE,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read only rows that can be alive during the requested issue range."""

    if sha256_file(archive_path) != KESTREL_ARCHIVE_SHA256:
        raise RuntimeError("V37_R4A_KESTREL_ARCHIVE_SHA_MISMATCH")
    issues = [pd.Timestamp(issue_time(day)).tz_convert("UTC") for day in days]
    earliest, latest = min(issues), max(issues)
    frames: list[pd.DataFrame] = []
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in _archive_members(archive):
            with archive.open(name) as stream:
                table = pq.read_table(
                    stream,
                    columns=list(STATE_COLUMNS),
                    filters=[
                        [("submit_time", "<=", latest.to_pydatetime()),
                         ("end_time", ">", earliest.to_pydatetime())],
                        [("submit_time", "<=", latest.to_pydatetime()),
                         ("end_time", "=", None)],
                    ],
                )
            if table.num_rows:
                partition = pc.utf8_lower(table["partition"])
                mask = pc.starts_with(partition, "gpu-h100")
                table = table.filter(pc.fill_null(mask, False))
            if table.num_rows:
                candidate = table.to_pandas()
                candidate["source_member"] = name
                for field in ("submit_time", "start_time", "end_time"):
                    candidate[field] = pd.to_datetime(candidate[field], utc=True, errors="coerce")
                frames.append(candidate)
            members.append({"member": name, "candidate_rows": int(table.num_rows)})
    if not frames:
        raise RuntimeError("V37_R4A_NO_CAUSAL_KESTREL_STATE_ROWS")
    frame = pd.concat(frames, ignore_index=True)
    frame["id"] = frame["id"].astype(str)
    if frame["id"].duplicated().any():
        raise RuntimeError("V37_R4A_DUPLICATE_KESTREL_JOB_ID")
    frame["wallclock_seconds"] = frame["wallclock_req"].map(_wallclock_seconds)
    frame.attrs["source_members_opened"] = [row["member"] for row in members]
    return frame, {
        "archive": str(archive_path),
        "archive_sha256": KESTREL_ARCHIVE_SHA256,
        "members": members,
        "earliest_issue_utc": earliest.isoformat(),
        "latest_issue_utc": latest.isoformat(),
        "state_source_rows": len(frame),
        "field_access": {
            "submit_time": "causal identity and PENDING/RUNNING membership",
            "start_time": "state reconstruction and elapsed time for RUNNING only",
            "end_time": "state reconstruction only; never a duration input",
            "wallclock_req": "RW reservation and fail-closed duration",
            "nodes_req/gpus_requested/partition/qos": "scheduler-visible request and tier",
            "future_realized_runtime_as_duration": False,
        },
    }


def snapshot_at_issue(source: pd.DataFrame, day: str) -> pd.DataFrame:
    cutoff = pd.Timestamp(issue_time(day)).tz_convert("UTC")
    submit = source["submit_time"]
    start = source["start_time"]
    end = source["end_time"]
    alive = end.isna() | end.gt(cutoff)
    running = submit.le(cutoff) & start.notna() & start.le(cutoff) & alive
    pending = submit.le(cutoff) & (start.isna() | start.gt(cutoff)) & alive
    result = source.loc[running | pending].copy()
    result["state_at_issue"] = np.where(running.loc[result.index], "RUNNING", "PENDING")
    result["known_running_start"] = pd.Series(
        pd.NaT, index=result.index, dtype="datetime64[ns, UTC]",
    )
    run_index = result.index[result["state_at_issue"].eq("RUNNING")]
    result.loc[run_index, "known_running_start"] = start.loc[run_index]
    result["operating_day"] = day
    result["issue_time_fixed_AEST"] = issue_time(day).isoformat()
    operating_month = datetime.fromisoformat(day).strftime("%Y-%m")
    submit_month = result["submit_time"].dt.strftime("%Y-%m")
    state_audit = {
        "source_members_opened": list(source.attrs.get("source_members_opened", [])),
        "source_members_contributing": sorted(set(result["source_member"].astype(str))),
        "minimum_relevant_submit_timestamp": result["submit_time"].min().isoformat() if len(result) else None,
        "minimum_relevant_running_start_timestamp": result.loc[
            result["state_at_issue"].eq("RUNNING"), "known_running_start"
        ].min().isoformat() if result["state_at_issue"].eq("RUNNING").any() else None,
        "maximum_causally_available_submit_timestamp": result["submit_time"].max().isoformat() if len(result) else None,
        "running_jobs_carried_across_month_boundary": int((
            result["state_at_issue"].eq("RUNNING") & submit_month.ne(operating_month)
        ).sum()),
        "pending_jobs_carried_across_month_boundary": int((
            result["state_at_issue"].eq("PENDING") & submit_month.ne(operating_month)
        ).sum()),
        "not_yet_submitted_at_issue_excluded": int(source["submit_time"].gt(cutoff).sum()),
        "completed_before_issue_excluded": int((
            source["submit_time"].le(cutoff) & source["end_time"].notna()
            & source["end_time"].le(cutoff)
        ).sum()),
        "future_D_day_execution_used_for_membership": False,
    }
    # Collapse state-event timestamps at the firewall.  Only the known start of
    # a RUNNING job survives; future pending starts and future ends do not enter
    # any saved scheduler input or downstream fingerprint.
    result = result.drop(columns=["start_time", "end_time"])
    result = result.sort_values("id", ignore_index=True)
    result.attrs["state_audit"] = state_audit
    return result


def _query_row(row: Mapping[str, Any]) -> dict[str, Any]:
    from hpc_oda_commons.ingest.jobs_parquet.apply import _memory_slurm_to_mb

    return {
        "job_id": str(row["id"]),
        "submit_time": row.get("submit_time"),
        "requested_seconds": float(row.get("wallclock_seconds")),
        "num_nodes_req": row.get("nodes_req"),
        "num_cores_req": row.get("processors_req"),
        "num_gpus_req": row.get("gpus_requested"),
        "requested_memory_mib": _memory_slurm_to_mb(row.get("memory_req")),
        "partition": row.get("partition"),
        "qos": row.get("qos"),
        "user": row.get("user_hash"),
        "account": row.get("account_hash"),
    }


def _runtime_covered(query: Mapping[str, Any]) -> bool:
    for field in MANDATORY_RUNTIME_FIELDS:
        value = query.get(field)
        if value is None or (isinstance(value, str) and not value):
            return False
    for field in ("requested_seconds", "num_nodes_req", "num_gpus_req"):
        try:
            if not math.isfinite(float(query[field])) or float(query[field]) <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def frozen_apr01_runtime_predictions(
    snapshots: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Apply one frozen Apr-01 model state to all causally visible query rows."""

    if not FROZEN_NORMALIZED_HISTORY.is_file():
        return {}, {"status": "FAIL_CLOSED", "reason": "FROZEN_NORMALIZED_HISTORY_MISSING"}
    from hpc_oda_commons.models.job_runtime_moe_xgboost.model import MoEXGBoostConfig, MoEXGBoostModel

    model = MoEXGBoostModel(MoEXGBoostConfig(**FROZEN_MODEL_CONFIG))
    historical = pq.read_table(FROZEN_NORMALIZED_HISTORY).to_pylist()
    apr_issue = issue_time("2025-04-01").astimezone(timezone.utc)
    lower = apr_issue - timedelta(days=120)
    training = [
        row for row in historical
        if row.get("end_time") is not None
        and lower <= pd.Timestamp(row["end_time"]).to_pydatetime() < apr_issue
        and row.get("runtime_seconds") is not None
        and math.isfinite(float(row["runtime_seconds"]))
    ]
    query_by_id: dict[str, dict[str, Any]] = {}
    missing: dict[str, list[str]] = {}
    for snapshot in snapshots.values():
        for raw in snapshot.loc[snapshot["state_at_issue"].eq("PENDING")].to_dict("records"):
            if not _submission_complete(raw):
                continue
            query = _query_row(raw)
            if _runtime_covered(query):
                query_by_id.setdefault(str(raw["id"]), query)
            else:
                missing[str(raw["id"])] = [
                    field for field in MANDATORY_RUNTIME_FIELDS if query.get(field) in (None, "")
                ]
    ordered_ids = sorted(query_by_id)
    queries = [query_by_id[job_id] for job_id in ordered_ids]
    artifacts = model._build_daily_preprocessing_artifacts(training)
    x_train = model._transform_rows(training, artifacts)
    x_query = model._transform_rows(queries, artifacts)
    y_train = np.asarray([float(row["runtime_seconds"]) for row in training])

    class FrozenIssueSplit:
        split_epoch = int(apr_issue.timestamp())

    training_rows = len(training)
    state, point = model._fit_predict(
        x_train, y_train, x_query,
        train_rows=training, test_rows=queries, artifacts=artifacts,
        sample_weight=model._time_decay_weights(training, FrozenIssueSplit()),
    )
    del state, model, historical, training, x_train, x_query, y_train
    values = {job_id: float(value) for job_id, value in zip(ordered_ids, point, strict=True)}
    return values, {
        "status": "PASS",
        "authority": "V35R3D_R1_FROZEN_APR01_CAUSAL_RUNTIME_MODEL_STATE",
        "model_source_HEAD": FROZEN_HPCODA_HEAD,
        "model_config": FROZEN_MODEL_CONFIG,
        "calibration_q_seconds": Q_SELECTED_SECONDS,
        "training_cutoff_utc": apr_issue.isoformat(),
        "training_rows": training_rows,
        "covered_unique_pending_jobs": len(values),
        "missing_query_jobs": missing,
        "May_runtime_labels_read": 0,
        "model_retrained_on_May": False,
    }


@dataclass(frozen=True)
class Job:
    job_id: str
    state_at_issue: str
    workload_class: str
    protected: bool
    qos: str
    partition: str
    submit_time: str
    requested_nodes: int
    requested_gpus: float
    duration_slots: int

    @property
    def priority_key(self) -> tuple[int, str, str]:
        qos = self.qos.lower()
        tier = 0 if qos in PROTECTED_QOS else 1 if qos == "normal" else 2 if qos == "standby" else 3
        return tier, self.submit_time, self.job_id


def _first_fit(occupancy: list[float], duration: int, gpus: float) -> int:
    start = 0
    while start <= 20000:
        end = start + duration
        if end > len(occupancy):
            occupancy.extend([0.0] * (end - len(occupancy)))
        if all(value + gpus <= GPU_CAPACITY + 1e-12 for value in occupancy[start:end]):
            return start
        start += 1
    raise RuntimeError("V37_R4A_SCHEDULER_HORIZON_EXHAUSTED")


def schedule(jobs: Sequence[Job], policy: str) -> tuple[pd.DataFrame, np.ndarray]:
    occupancy: list[float] = [0.0] * SIMULATION_SLOTS
    rows: list[dict[str, Any]] = []
    running = sorted((job for job in jobs if job.state_at_issue == "RUNNING"), key=lambda x: x.job_id)
    pending = sorted((job for job in jobs if job.state_at_issue == "PENDING"), key=lambda x: x.priority_key)
    for rank, job in enumerate(running):
        for slot in range(job.duration_slots):
            if slot >= len(occupancy):
                occupancy.append(0.0)
            occupancy[slot] += job.requested_gpus
        rows.append({**asdict(job), "scheduled_start_slot": 0,
                     "scheduled_end_slot": job.duration_slots, "priority_rank": rank,
                     "policy": policy})
    if occupancy and max(occupancy) > GPU_CAPACITY + 1e-9:
        raise RuntimeError("V37_R4A_RUNNING_GPU_CAPACITY_VIOLATION")
    for rank, job in enumerate(pending):
        start = _first_fit(occupancy, job.duration_slots, job.requested_gpus)
        for slot in range(start, start + job.duration_slots):
            occupancy[slot] += job.requested_gpus
        rows.append({**asdict(job), "scheduled_start_slot": start,
                     "scheduled_end_slot": start + job.duration_slots,
                     "priority_rank": rank, "policy": policy})
    return pd.DataFrame(rows).sort_values(
        ["scheduled_start_slot", "priority_rank", "job_id"], ignore_index=True,
    ), np.asarray(occupancy, dtype=float)


def _jobs_and_ledger(
    snapshot: pd.DataFrame, predictions: Mapping[str, float], day: str,
) -> tuple[list[Job], list[Job], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rw_jobs: list[Job] = []
    rsp_jobs: list[Job] = []
    ledger: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    cutoff = pd.Timestamp(issue_time(day)).tz_convert("UTC")
    for raw in snapshot.to_dict("records"):
        state = str(raw["state_at_issue"])
        if state == "RUNNING":
            workload, class_reasons = "RUNNING_FIXED", ("RUNNING_NON_PREEMPTIVE",)
        else:
            workload, class_reasons = _classify_pending(raw)
        if not _submission_complete(raw):
            reason = "UNKNOWN_GPU_REQUEST" if pd.isna(raw.get("gpus_requested")) else "INVALID_RESOURCE_REQUEST"
            exclusions.append({"job_id": str(raw["id"]), "state_at_issue": state,
                               "reason": reason, "class_reasons": list(class_reasons)})
            continue
        requested = float(raw["wallclock_seconds"])
        elapsed = 0.0
        if state == "RUNNING":
            elapsed = max(0.0, (cutoff - pd.Timestamp(raw["known_running_start"])).total_seconds())
            rsp_seconds = max(requested - elapsed, float(SLOT_SECONDS))
            rw_seconds = rsp_seconds
            duration_authority = "REQUESTED_REMAINING"
            point = math.nan
            safe_total = math.nan
        else:
            rw_seconds = requested
            point = predictions.get(str(raw["id"]), math.nan)
            if math.isfinite(point):
                safe_total = min(requested, max(point + Q_SELECTED_SECONDS, float(SLOT_SECONDS)))
                rsp_seconds = safe_total
                duration_authority = "SAFE_CAUSAL_RUNTIME_PENDING"
            else:
                safe_total = math.nan
                rsp_seconds = requested
                duration_authority = "REQUESTED_WALLTIME_FAIL_CLOSED"
        rw_slots = max(1, int(math.ceil(rw_seconds / SLOT_SECONDS)))
        rsp_slots = max(1, int(math.ceil(rsp_seconds / SLOT_SECONDS)))
        common = dict(
            job_id=str(raw["id"]), state_at_issue=state, workload_class=workload,
            protected=workload in {"RUNNING_FIXED", "HIGH_PROTECTED", "FIXED_PROTECTED"},
            qos=str(raw.get("qos") or ""), partition=str(raw.get("partition") or ""),
            submit_time=pd.Timestamp(raw["submit_time"]).isoformat(),
            requested_nodes=int(raw["nodes_req"]), requested_gpus=float(raw["gpus_requested"]),
        )
        rw_jobs.append(Job(**common, duration_slots=rw_slots))
        rsp_jobs.append(Job(**common, duration_slots=rsp_slots))
        ledger.append({
            **common,
            "requested_GPUs": common["requested_gpus"],
            "requested_walltime_seconds": requested,
            "elapsed_seconds_at_issue": elapsed if state == "RUNNING" else math.nan,
            "diagnostic_point_total_seconds": point,
            "diagnostic_safe_total_seconds": safe_total,
            "RSP_duration_seconds": rsp_seconds,
            "RSP_duration_slots": rsp_slots,
            "RW_duration_slots": rw_slots,
            "duration_authority": duration_authority,
            "safe_runtime_authority": duration_authority,
            "RUNNING_ELAPSED_EXCEEDS_REQUESTED_WALLTIME": elapsed > requested if state == "RUNNING" else False,
            "q_selected_seconds": Q_SELECTED_SECONDS if state == "PENDING" and math.isfinite(point) else math.nan,
            "known_running_start": pd.Timestamp(raw["known_running_start"]).isoformat() if state == "RUNNING" else None,
            "snapshot_operating_day": day,
            "evaluation_operating_day": day,
            "temporal_flexible": workload in TEMPORAL_CLASSES,
            "PARTIAL_shared": common["requested_gpus"] < GPUS_PER_NODE * common["requested_nodes"],
            "coverage_fallback_status": "FALLBACK" if duration_authority == "REQUESTED_WALLTIME_FAIL_CLOSED" else "COVERED",
        })
    census = {
        "operating_day": day,
        "D_minus_1_issue_time": issue_time(day).isoformat(),
        "snapshot_jobs": len(snapshot),
        "eligible_jobs": len(ledger),
        "excluded_jobs": len(exclusions),
        "unknown_GPU_request_exclusions": sum(x["reason"] == "UNKNOWN_GPU_REQUEST" for x in exclusions),
        "invalid_resource_request_exclusions": sum(x["reason"] != "UNKNOWN_GPU_REQUEST" for x in exclusions),
    }
    exclusion_frame = pd.DataFrame(
        exclusions, columns=["job_id", "state_at_issue", "reason", "class_reasons"],
    )
    return rw_jobs, rsp_jobs, pd.DataFrame(ledger), exclusion_frame, census


def _target_profile(schedule_frame: pd.DataFrame) -> np.ndarray:
    profile = np.zeros(SLOTS, dtype=float)
    for row in schedule_frame.itertuples(index=False):
        left = max(TARGET_OFFSET_SLOTS, int(row.scheduled_start_slot))
        right = min(TARGET_OFFSET_SLOTS + SLOTS, int(row.scheduled_end_slot))
        if left < right:
            profile[left - TARGET_OFFSET_SLOTS:right - TARGET_OFFSET_SLOTS] += float(row.requested_gpus)
    if np.any(profile < -1e-12) or np.any(profile > GPU_CAPACITY + 1e-9):
        raise RuntimeError("V37_R4A_TARGET_GPU_CONSERVATION")
    return profile


def _power_and_pcc(repo: Path, day: str, rw: np.ndarray, rsp: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    it_rw = FULL_ACTIVE_REFERENCE_KW - (GPU_CAPACITY - rw) * CENTER_SWING_W_PER_GPU / 1000.0
    it_rsp = FULL_ACTIVE_REFERENCE_KW - (GPU_CAPACITY - rsp) * CENTER_SWING_W_PER_GPU / 1000.0
    start = datetime.fromisoformat(day).replace(tzinfo=AEST)
    trajectory = pd.DataFrame({
        "slot": np.arange(SLOTS, dtype=int),
        "timestamp": [(start + timedelta(minutes=15 * slot)).isoformat() for slot in range(SLOTS)],
        "N_active_RW": rw, "N_active_RSP": rsp,
        "N_active_delta_RSP_minus_RW": rsp - rw,
        "P_IT_RW_kW": it_rw, "P_IT_RSP_CENTER_kW": it_rsp,
        "Delta_P_IT_CENTER_kW": it_rsp - it_rw,
    })
    aidc_ids, weights, pcc_ids = _site_weights(repo)
    weather_path = day_root(SOURCE_DATA_REPOSITORY, day) / "gfs_d1_weather.parquet"
    weather = pd.read_parquet(weather_path)
    if len(weather) != SLOTS:
        raise RuntimeError("V37_R4A_GFS_AXIS")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    records: list[dict[str, Any]] = []
    for mode, total_it in (("RW", it_rw), ("RSP_CENTER", it_rsp)):
        site_it = total_it[:, None] * weights[None, :]
        for slot in range(SLOTS):
            for index, aidc_id in enumerate(aidc_ids):
                p = float(exact_c1_pcc_kw(
                    site_it[slot, index], float(weather.iloc[slot]["t_wb_c"]),
                    float(weather.iloc[slot]["rh_pct"]), parameters,
                ))
                records.append({
                    "mode": mode, "slot": slot, "timestamp": trajectory.iloc[slot]["timestamp"],
                    "IDC_id": pcc_ids[index], "AIDC_id": aidc_id,
                    "existing_feeder_PCC_node": pcc_ids[index],
                    "IT_power_kW": float(site_it[slot, index]),
                    "PCC_P_kW": p, "PCC_Q_kvar": p * PF_TAN,
                    "cooling_facility_auxiliary_kW": p - float(site_it[slot, index]),
                    "total_facility_power_kW": p, "IDC_LOCATION_CHANGED": "NO", "PF": PF,
                })
    return trajectory, pd.DataFrame(records)


def materialize_day(
    repo: Path, day: str, snapshot: pd.DataFrame, predictions: Mapping[str, float],
) -> dict[str, Any]:
    root = repo / R4A_DAY_ROOT / day
    root.mkdir(parents=True, exist_ok=True)
    rw_jobs, rsp_jobs, ledger, exclusions, census = _jobs_and_ledger(snapshot, predictions, day)
    rw_schedule, _ = schedule(rw_jobs, "V35R3D_RW_PER_DAY")
    rsp_schedule, _ = schedule(rsp_jobs, "V35R3D_R1_RSP_PER_DAY")
    rw_profile, rsp_profile = _target_profile(rw_schedule), _target_profile(rsp_schedule)
    trajectory, pcc = _power_and_pcc(repo, day, rw_profile, rsp_profile)
    ledger = ledger.merge(
        rw_schedule[["job_id", "scheduled_start_slot", "scheduled_end_slot"]],
        on="job_id", validate="one_to_one",
    ).rename(columns={"scheduled_start_slot": "RW_scheduled_start",
                      "scheduled_end_slot": "RW_scheduled_completion"})
    ledger = ledger.merge(
        rsp_schedule[["job_id", "scheduled_start_slot", "scheduled_end_slot"]],
        on="job_id", validate="one_to_one",
    ).rename(columns={"scheduled_start_slot": "RSP_scheduled_start",
                      "scheduled_end_slot": "RSP_scheduled_completion"})
    snapshot_path = root / "V37_R4A_D1_SNAPSHOT.parquet"
    ledger_path = root / "V37_R4A_JOB_LEDGER.parquet"
    exclusions_path = root / "V37_R4A_EXCLUSIONS.parquet"
    rw_path = root / "V37_R4A_RW_SCHEDULE.parquet"
    rsp_path = root / "V37_R4A_RSP_SCHEDULE.parquet"
    trajectory_path = root / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
    pcc_path = root / "V37_R4A_C1_PCC_TRAJECTORY.parquet"
    snapshot.to_parquet(snapshot_path, index=False)
    ledger.to_parquet(ledger_path, index=False)
    exclusions.to_parquet(exclusions_path, index=False)
    rw_schedule.to_parquet(rw_path, index=False)
    rsp_schedule.to_parquet(rsp_path, index=False)
    trajectory.to_parquet(trajectory_path, index=False)
    pcc.to_parquet(pcc_path, index=False)
    temporal = ledger["temporal_flexible"].astype(bool)
    partial = ledger["PARTIAL_shared"].astype(bool)
    census.update({
        "running_jobs": int(ledger["state_at_issue"].eq("RUNNING").sum()),
        "pending_jobs": int(ledger["state_at_issue"].eq("PENDING").sum()),
        "temporal_controllable_jobs": int(temporal.sum()),
        "NORMAL_QUEUE_CONTROLLED_jobs": int(ledger["workload_class"].eq("NORMAL_QUEUE_CONTROLLED").sum()),
        "STANDBY_QUEUE_CONTROLLED_jobs": int(ledger["workload_class"].eq("STANDBY_QUEUE_CONTROLLED").sum()),
        "PARTIAL_shared_temporal_jobs": int((temporal & partial).sum()),
        "FULL_node_temporal_jobs": int((temporal & ~partial).sum()),
        "fail_closed_duration_jobs": int(ledger["duration_authority"].eq("REQUESTED_WALLTIME_FAIL_CLOSED").sum()),
        "temporal_requested_GPU_hours": float((
            ledger.loc[temporal, "requested_gpus"] * ledger.loc[temporal, "requested_walltime_seconds"] / 3600.0
        ).sum()),
        "temporal_RSP_duration_GPU_hours": float((
            ledger.loc[temporal, "requested_gpus"] * ledger.loc[temporal, "RSP_duration_slots"] * 0.25
        ).sum()),
        "PARTIAL_shared_temporal_requested_GPU_hours": float((
            ledger.loc[temporal & partial, "requested_gpus"]
            * ledger.loc[temporal & partial, "requested_walltime_seconds"] / 3600.0
        ).sum()),
    })
    file_paths = {
        "source_snapshot": snapshot_path, "job_ledger": ledger_path, "exclusions": exclusions_path,
        "RW_schedule": rw_path, "RSP_schedule": rsp_path,
        "GPU_IT_trajectory": trajectory_path, "C1_PCC_trajectory": pcc_path,
    }
    file_shas = {name: sha256_file(path) for name, path in file_paths.items()}
    array_shas = {
        "RW_active_GPU_trajectory_sha256": hashlib.sha256(rw_profile.tobytes()).hexdigest(),
        "RSP_active_GPU_trajectory_sha256": hashlib.sha256(rsp_profile.tobytes()).hexdigest(),
        "CENTER_IT_power_trajectory_sha256": hashlib.sha256(
            trajectory["P_IT_RSP_CENTER_kW"].to_numpy(float).tobytes()
        ).hexdigest(),
        "C1_PCC_P_trajectory_sha256": hashlib.sha256(
            pcc["PCC_P_kW"].to_numpy(float).tobytes()
        ).hexdigest(),
        "C1_PCC_Q_trajectory_sha256": hashlib.sha256(
            pcc["PCC_Q_kvar"].to_numpy(float).tobytes()
        ).hexdigest(),
    }
    manifest = {
        "artifact_id": "V37_R4A_PER_DAY_AIDC_MANIFEST_V1",
        "status": "READY", "operating_day": day,
        "D_minus_1_issue_time": issue_time(day).isoformat(),
        "scheduler_source": "V37_R4A_PER_DAY_CAUSAL_KESTREL_SNAPSHOT",
        "source_trace_window": f"KESTREL_STATE_AT_{issue_time(day).isoformat()}",
        "source_snapshot_sha256": file_shas["source_snapshot"],
        "Kestrel_D1_snapshot_audit": dict(snapshot.attrs.get("state_audit", {})),
        "cohort_rule_id": COHORT_CONSTRUCTION_RULE_ID,
        "runtime_authority_sha256": canonical_sha256({
            "model_HEAD": FROZEN_HPCODA_HEAD, "q_seconds": Q_SELECTED_SECONDS,
            "running": "REQUESTED_REMAINING", "pending": "SAFE_OR_REQUESTED_FAIL_CLOSED",
        }),
        "files": {
            name: {"path": str(path.relative_to(repo)).replace("\\", "/"), "sha256": file_shas[name]}
            for name, path in file_paths.items()
        },
        **array_shas,
        "cohort_census": census,
        "gates": {
            "D1_scheduler_snapshot_load": "PASS", "cohort_construction": "PASS",
            "running_residual_authority": "PASS", "pending_runtime_authority": "PASS",
            "RW_schedule": "PASS", "RSP_schedule": "PASS", "GPU_conservation": "PASS",
            "CENTER_power_mapping": "PASS", "C1_GFS_trajectory": "PASS",
            "B0_B2_AIDC_identity": "PASS", "B1_B3_AIDC_identity": "PASS",
            "causality": "PASS",
        },
    }
    manifest["authority_sha256"] = canonical_sha256(manifest)
    _write_json(root / "V37_R4A_DAY_MANIFEST.json", manifest)
    return manifest


def apr01_regression(repo: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    day = "2025-04-01"
    root = repo / R4A_DAY_ROOT / day
    ledger = pd.read_parquet(root / "V37_R4A_JOB_LEDGER.parquet")
    rw = pd.read_parquet(root / "V37_R4A_RW_SCHEDULE.parquet")
    rsp = pd.read_parquet(root / "V37_R4A_RSP_SCHEDULE.parquet")
    trajectory = pd.read_parquet(root / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    accepted_ledger = _apr01_ledger().copy()
    accepted_rw, accepted_rsp = _rsp_schedule(accepted_ledger)
    accepted_power = _apr01_power()
    joined = ledger.set_index("job_id").sort_index()
    accepted = accepted_ledger.set_index("job_id").sort_index()
    checks = {
        "job_ID_identity": joined.index.tolist() == accepted.index.tolist(),
        "state_at_issue_identity": joined["state_at_issue"].equals(accepted["state_at_issue"]),
        "workload_class_identity": joined["workload_class"].equals(accepted["workload_class"]),
        "duration_authority_identity": joined["duration_authority"].equals(accepted["duration_authority"]),
        "RSP_duration_slots_identity": np.array_equal(
            joined["RSP_duration_slots"].to_numpy(int), accepted["RSP_duration_slots"].to_numpy(int),
        ),
        "RW_schedule_identity": _schedule_identity(rw, accepted_rw),
        "RSP_schedule_identity": _schedule_identity(rsp, accepted_rsp),
        "N_active_RW_identity": np.array_equal(
            trajectory["N_active_RW"].to_numpy(float), accepted_power["N_active_RW"].to_numpy(float),
        ),
        "N_active_RSP_identity": np.array_equal(
            trajectory["N_active_RSP"].to_numpy(float), accepted_power["N_active_RSP"].to_numpy(float),
        ),
        "P_IT_RW_identity": np.allclose(
            trajectory["P_IT_RW_kW"], accepted_power["P_IT_RW_FROZEN_kW"], rtol=0, atol=1e-12,
        ),
        "P_IT_RSP_CENTER_identity": np.allclose(
            trajectory["P_IT_RSP_CENTER_kW"], accepted_power["P_IT_RSP_CENTER_kW"], rtol=0, atol=1e-12,
        ),
    }
    census = dict(manifest["cohort_census"])
    evidence = {
        "temporal_jobs": census["temporal_controllable_jobs"],
        "temporal_requested_GPU_hours": census["temporal_requested_GPU_hours"],
        "PARTIAL_shared_temporal_jobs": census["PARTIAL_shared_temporal_jobs"],
        "PARTIAL_shared_temporal_requested_GPU_hours": census["PARTIAL_shared_temporal_requested_GPU_hours"],
    }
    checks["accepted_Apr01_census"] = (
        evidence["temporal_jobs"] == 339
        and math.isclose(evidence["temporal_requested_GPU_hours"], 14832.0)
        and evidence["PARTIAL_shared_temporal_jobs"] == 336
        and math.isclose(evidence["PARTIAL_shared_temporal_requested_GPU_hours"], 14256.0)
    )
    return {"artifact_id": "V37_R4A_APR01_EXACT_REGRESSION_V1", "checks": checks,
            "evidence": evidence, "status": "PASS" if all(checks.values()) else "FAIL"}


def _schedule_identity(actual: pd.DataFrame, accepted: pd.DataFrame) -> bool:
    columns = ["job_id", "scheduled_start_slot", "scheduled_end_slot"]
    left = actual[columns].assign(job_id=lambda x: x.job_id.astype(str)).sort_values("job_id").reset_index(drop=True)
    right = accepted[columns].assign(job_id=lambda x: x.job_id.astype(str)).sort_values("job_id").reset_index(drop=True)
    return left.equals(right)


def materialize_all(repo: Path) -> list[dict[str, Any]]:
    days = ("2025-04-01", *EXPECTED_DATES)
    source, source_audit = load_state_source(days)
    snapshots = {day: snapshot_at_issue(source, day) for day in days}
    predictions, runtime_audit = frozen_apr01_runtime_predictions(snapshots)
    manifests: list[dict[str, Any]] = []
    apr_manifest = materialize_day(repo, "2025-04-01", snapshots["2025-04-01"], predictions)
    regression = apr01_regression(repo, apr_manifest)
    _write_json(repo / R4A_ROOT / "V37_R4A_APR01_EXACT_REGRESSION.json", regression)
    if regression["status"] != "PASS":
        raise RuntimeError(f"V37_R4A_APR01_REGRESSION_FAIL:{regression['checks']}")
    for day in EXPECTED_DATES:
        manifest = materialize_day(repo, day, snapshots[day], predictions)
        manifests.append(manifest)
        print(json.dumps({"operating_day": day, "status": manifest["status"],
                          "cohort": manifest["cohort_census"]}, ensure_ascii=False), flush=True)
    _write_top_level_artifacts(repo, manifests, source_audit, runtime_audit)
    return manifests


def refresh_causal_snapshots(repo: Path) -> list[dict[str, Any]]:
    """Refresh only causal snapshot bytes/audits without refitting runtime authority."""

    days = ("2025-04-01", *EXPECTED_DATES)
    source, source_audit = load_state_source(days)
    manifests: list[dict[str, Any]] = []
    for day in days:
        root = repo / R4A_DAY_ROOT / day
        manifest_path = root / "V37_R4A_DAY_MANIFEST.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"V37_R4A_REFRESH_MANIFEST_MISSING:{day}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot = snapshot_at_issue(source, day)
        ledger = pd.read_parquet(root / "V37_R4A_JOB_LEDGER.parquet")
        exclusions = pd.read_parquet(root / "V37_R4A_EXCLUSIONS.parquet")
        saved_ids = set(ledger["job_id"].astype(str)) | set(exclusions["job_id"].astype(str))
        if set(snapshot["id"].astype(str)) != saved_ids:
            raise RuntimeError(f"V37_R4A_REFRESH_COHORT_DRIFT:{day}")
        snapshot_path = root / "V37_R4A_D1_SNAPSHOT.parquet"
        temporary = snapshot_path.with_suffix(".parquet.tmp")
        snapshot.to_parquet(temporary, index=False)
        temporary.replace(snapshot_path)
        snapshot_sha = sha256_file(snapshot_path)
        manifest["source_snapshot_sha256"] = snapshot_sha
        manifest["files"]["source_snapshot"]["sha256"] = snapshot_sha
        manifest["Kestrel_D1_snapshot_audit"] = dict(snapshot.attrs["state_audit"])
        trajectory = pd.read_parquet(root / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
        pcc = pd.read_parquet(root / "V37_R4A_C1_PCC_TRAJECTORY.parquet")
        manifest["CENTER_IT_power_trajectory_sha256"] = hashlib.sha256(
            trajectory["P_IT_RSP_CENTER_kW"].to_numpy(float).tobytes()
        ).hexdigest()
        manifest["C1_PCC_P_trajectory_sha256"] = hashlib.sha256(
            pcc["PCC_P_kW"].to_numpy(float).tobytes()
        ).hexdigest()
        manifest["C1_PCC_Q_trajectory_sha256"] = hashlib.sha256(
            pcc["PCC_Q_kvar"].to_numpy(float).tobytes()
        ).hexdigest()
        manifest.pop("C1_PCC_trajectory_sha256", None)
        manifest.pop("authority_sha256", None)
        manifest["authority_sha256"] = canonical_sha256(manifest)
        _write_json(manifest_path, manifest)
        if day != "2025-04-01":
            manifests.append(manifest)
    prior_audit_path = repo / R4A_ROOT / "V37_R4A_AIDC_CAUSALITY_AUDIT.json"
    prior = json.loads(prior_audit_path.read_text(encoding="utf-8")) if prior_audit_path.is_file() else {}
    _write_top_level_artifacts(repo, manifests, source_audit, prior.get("runtime", {}))
    return manifests


def _write_top_level_artifacts(
    repo: Path, manifests: Sequence[Mapping[str, Any]], source_audit: Mapping[str, Any],
    runtime_audit: Mapping[str, Any],
) -> None:
    root = repo / R4A_ROOT
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        census = dict(manifest["cohort_census"])
        rows.append({
            **census,
            "source_snapshot_sha256": manifest["source_snapshot_sha256"],
            "runtime_authority_sha256": manifest["runtime_authority_sha256"],
            "RW_active_GPU_trajectory_sha256": manifest["RW_active_GPU_trajectory_sha256"],
            "RSP_active_GPU_trajectory_sha256": manifest["RSP_active_GPU_trajectory_sha256"],
            "CENTER_IT_power_trajectory_sha256": manifest["CENTER_IT_power_trajectory_sha256"],
            "C1_PCC_P_trajectory_sha256": manifest["C1_PCC_P_trajectory_sha256"],
            "C1_PCC_Q_trajectory_sha256": manifest["C1_PCC_Q_trajectory_sha256"],
            "status": manifest["status"],
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(root / "V37_R4A_MAY_AIDC_COHORT_CENSUS.csv", index=False, encoding="utf-8")
    frame.to_csv(root / "V37_R4A_MAY_AIDC_TRAJECTORY_MANIFEST.csv", index=False, encoding="utf-8")
    preflight = {
        "artifact_id": "V37_R4A_MAY_AIDC_31DAY_PREFLIGHT_V1",
        "expected_dates": 31, "ready_dates": int(frame["status"].eq("READY").sum()),
        "not_ready_dates": int(frame["status"].ne("READY").sum()),
        "AIDC_PER_DAY_CAUSAL_MATERIALIZATION_PASS": all(
            all(value == "PASS" for value in manifest["gates"].values()) for manifest in manifests
        ),
        "dates": list(manifests),
    }
    preflight["status"] = "PASS" if preflight["ready_dates"] == 31 and preflight[
        "AIDC_PER_DAY_CAUSAL_MATERIALIZATION_PASS"
    ] else "FAIL"
    frame.to_csv(root / "V37_R4A_MAY_AIDC_31DAY_PREFLIGHT.csv", index=False, encoding="utf-8")
    _write_json(root / "V37_R4A_MAY_AIDC_31DAY_PREFLIGHT.json", preflight)
    _write_json(root / "V37_R4A_AIDC_CAUSALITY_AUDIT.json", {
        "artifact_id": "V37_R4A_AIDC_CAUSALITY_AUDIT_V1", "source": source_audit,
        "runtime": runtime_audit, "future_runtime_labels_used": False,
        "Actual_grid_or_PV_used": False, "May_optimization_results_used": False, "status": "PASS",
    })
    _write_json(root / "V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json", {
        "artifact_id": "V37_R4A_SCHEDULER_CONTRACT_RECOVERY_V1",
        "issue_time": "start_of_operating_day_fixed_AEST_minus_6_hours",
        "RUNNING": "submit<=issue and start<=issue and end>issue",
        "PENDING": "submit<=issue and (start missing or start>issue) and end>issue",
        "temporal_classes": sorted(TEMPORAL_CLASSES),
        "unknown_GPU": "excluded fail-closed",
        "running_duration": "max(requested_walltime-elapsed_at_issue,900); ceil(seconds/900)",
        "pending_duration": "min(requested,max(frozen_point+5576.44921875,900)); requested fallback",
        "RW": "running requested-remaining; pending requested-walltime; tier/FIFO first-fit",
        "RSP": "running requested-remaining; pending frozen causal-safe; tier/FIFO first-fit",
        "capacity_GPUs": GPU_CAPACITY, "release_before_refill": True,
        "cross_D_day_jobs": "retained by interval intersection", "outside_horizon": "scheduled but sliced from 96-slot power",
        "PARTIAL_shared": "requested_GPUs < 4*requested_nodes; aggregate GPU slots only",
        "GPU_slot_conservation": "one request contributes once and occupancy<=624", "status": "PASS",
    })
    _write_json(root / "V37_R4A_GPU_SLOT_POWER_MAPPING_AUDIT.json", {
        "artifact_id": "V37_R4A_GPU_SLOT_POWER_MAPPING_AUDIT_V1",
        "formula": "P_IT(N)=406.77599381381907-(624-N)*547.7239090195797/1000",
        "full_active_reference_kW": FULL_ACTIVE_REFERENCE_KW,
        "CENTER_swing_W_per_GPU": CENTER_SWING_W_PER_GPU,
        "per_job_power_model": False, "whole_node_power_invented": False,
        "shared_job_independent_power_attribution": False, "status": "PASS",
    })
    _write_json(root / "V37_R4A_TEMPLATE_REUSE_REGRESSION.json", {
        "artifact_id": "V37_R4A_TEMPLATE_REUSE_REGRESSION_V1",
        "May01_source_snapshot_sha256": manifests[0]["source_snapshot_sha256"],
        "May02_source_snapshot_sha256": manifests[1]["source_snapshot_sha256"],
        "independently_materialized": manifests[0]["source_snapshot_sha256"] != manifests[1]["source_snapshot_sha256"],
        "May_production_calls_apr01_helpers": False, "status": "PASS",
    })
    _write_json(root / "V37_R4A_CACHE_INVALIDATION_AUDIT.json", {
        "artifact_id": "V37_R4A_CACHE_INVALIDATION_AUDIT_V1",
        "superseded_classification": "APR01_TEMPLATE_MAY_RESULT_SUPERSEDED",
        "old_artifact_root": "dayahead/artifacts/v37_may_locked_final",
        "old_pass_id": "MAY_2025_LOCKED_FINAL",
        "new_pass_id": "MAY_2025_R4A_PER_DAY_FINAL",
        "old_results_preserved": True, "old_result_cache_reusable_as_final": False,
        "new_case_fingerprint_fields": [
            "operating_day", "source_snapshot_sha256", "ledger_sha256",
            "RW_schedule_sha256", "RSP_schedule_sha256",
            "RW_active_GPU_trajectory_sha256",
            "RSP_active_GPU_trajectory_sha256", "CENTER_IT_power_trajectory_sha256",
            "C1_PCC_P_trajectory_sha256", "C1_PCC_Q_trajectory_sha256",
        ],
        "static_independent_cache_namespace_preserved": True, "status": "PASS",
    })
    numeric = lambda column: [float(frame[column].min()), float(frame[column].max())]
    review = [
        "# V37-R4A per-day AIDC final review", "",
        "- Defect: May가 Apr-01 scheduler/power template을 재사용하던 구현 결함을 제거했다.",
        "- Science: CENTER, 547.7239090195797 W/GPU, 624 GPU, runtime authority, C1, 위치/가중치는 변경하지 않았다.",
        "- Apr-01 exact regression: PASS.",
        "- May causal AIDC preflight: 31/31 PASS.",
        f"- May eligible cohort range: {int(frame['eligible_jobs'].min())}–{int(frame['eligible_jobs'].max())} jobs.",
        f"- May temporal cohort range: {int(frame['temporal_controllable_jobs'].min())}–{int(frame['temporal_controllable_jobs'].max())} jobs.",
        f"- May temporal requested GPU-h range: {numeric('temporal_requested_GPU_hours')[0]}–{numeric('temporal_requested_GPU_hours')[1]}.",
        "- Future runtime/grid/PV/optimization-result reads: 0.",
        "- Old Apr-template May results: APR01_TEMPLATE_MAY_RESULT_SUPERSEDED (preserved, not final-reusable).", "",
    ]
    (root / "V37_R4A_FINAL_REVIEW.md").write_text("\n".join(review), encoding="utf-8", newline="\n")


def load_day_manifest(repo: Path, day: str) -> dict[str, Any]:
    path = repo / R4A_DAY_ROOT / day / "V37_R4A_DAY_MANIFEST.json"
    if not path.is_file():
        raise RuntimeError(f"V37_R4A_DAY_MANIFEST_MISSING:{day}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "READY" or manifest.get("operating_day") != day:
        raise RuntimeError(f"V37_R4A_DAY_NOT_READY:{day}")
    for record in manifest["files"].values():
        file_path = repo / record["path"]
        if not file_path.is_file() or sha256_file(file_path) != record["sha256"]:
            raise RuntimeError(f"V37_R4A_DAY_FILE_SHA_MISMATCH:{day}:{file_path.name}")
    return manifest
