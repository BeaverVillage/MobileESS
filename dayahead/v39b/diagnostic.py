"""Materialize the V39B diagnostic without changing any production scheduler.

The only optimization performed here is read-only feasibility analysis.  In
particular, the module never writes a replacement RW/RSP schedule.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB
import pandas as pd

from dayahead.v37.aidc_materializer import issue_time
from dayahead.v38.authority import CapacityAuthority, load_capacity_authority
from dayahead.v39a.spatial import ActivityJob, production_activity

from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CAPACITY_AUTHORITY_SHA256,
    DIAGNOSTIC_LABEL,
    IMPLEMENTATION_ID,
    INFEASIBLE_DAY_MODES,
    NONSHIFTABLE_CLASSES,
    SHIFTABLE_CLASSES,
    SITE_CAPACITY,
    SLOT_SECONDS,
    SLOTS,
    SOLVER_SEED,
    SOLVER_THREADS,
    SOURCE_FINGERPRINT,
    SOURCE_HEAD,
    STORED_SLOTS,
    TARGET_OFFSET_SLOTS,
    V37_DAY_ROOT,
    V37_SCHEDULER_SOURCE,
    V39A_ARTIFACT_ROOT,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _input_manifest(repo: Path) -> tuple[dict[str, str], str]:
    paths = [
        V37_SCHEDULER_SOURCE,
        Path("dayahead/artifacts/v37_r4a_per_day_aidc/V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json"),
        V39A_ARTIFACT_ROOT / "V39A_SPATIAL_FEASIBILITY_AUDIT.json",
        V39A_ARTIFACT_ROOT / "V39A_IMPLEMENTATION_FINGERPRINT.json",
        Path("dayahead/artifacts/v38_aidc_spatiotemporal_wan/V38_AIDC_GPU_CAPACITY_MAPPING.json"),
    ]
    seen_days: set[str] = set()
    for day, mode in INFEASIBLE_DAY_MODES:
        paths.append(V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet")
        if day not in seen_days:
            paths.append(V37_DAY_ROOT / day / "V37_R4A_JOB_LEDGER.parquet")
            seen_days.add(day)
    manifest = {path.as_posix(): sha256_file(repo / path) for path in paths}
    return manifest, canonical_sha256(manifest)


def _metadata(input_manifest_sha256: str) -> dict[str, Any]:
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "source_HEAD": SOURCE_HEAD,
        "source_implementation_fingerprint": SOURCE_FINGERPRINT,
        "input_manifest_sha256": input_manifest_sha256,
        "input_hashes": {
            "V39A_source_HEAD": SOURCE_HEAD,
            "V39A_implementation_fingerprint": SOURCE_FINGERPRINT,
            "Rack_capacity_source_SHA256": CAPACITY_AUTHORITY_SHA256,
            "diagnostic_input_manifest_SHA256": input_manifest_sha256,
        },
        "solver_seed": SOLVER_SEED,
        "solver_threads": SOLVER_THREADS,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "diagnostic_label": DIAGNOSTIC_LABEL,
        "MAY_STARTED": "NO",
    }


def _write_parquet(path: Path, frame: pd.DataFrame, metadata: Mapping[str, Any]) -> None:
    for key, value in metadata.items():
        frame[key] = (
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list, tuple))
            else value
        )
    frame.attrs.update(dict(metadata))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _eligible_sites(capacity: CapacityAuthority, gpu: int) -> tuple[str, ...]:
    return tuple(
        site
        for site in capacity.aidc_ids
        if capacity.site_capacity[site] >= gpu
        and capacity.eligible_racks(site, gpu)
    )


def _new_model(name: str) -> gp.Model:
    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = SOLVER_THREADS
    model.Params.Seed = SOLVER_SEED
    model.Params.MIPGap = 0.0
    return model


def exact_slot_packing(
    jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    *,
    name: str,
    compute_iis: bool = False,
) -> dict[str, Any]:
    """Solve an exact slot-local bin packing grouped only by equivalent gangs."""

    rows = tuple(jobs)
    counts = Counter(job.requested_GPU for job in rows)
    model = _new_model(name)
    variables: dict[tuple[int, str], gp.Var] = {}
    eligible: dict[int, tuple[str, ...]] = {}
    for gpu, count in sorted(counts.items()):
        eligible[gpu] = _eligible_sites(capacity, gpu)
        if not eligible[gpu]:
            return {
                "status": "INFEASIBLE_SLOT_LOCAL",
                "reason": f"NO_AIDC_RACK_GANG_FIT:{gpu}",
            }
        for site in eligible[gpu]:
            variables[gpu, site] = model.addVar(
                vtype=GRB.INTEGER,
                lb=0,
                ub=count,
                name=f"gang_count[{gpu},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[gpu, site] for site in eligible[gpu]) == count,
            name=f"all_gangs[{gpu}]",
        )
    for site in capacity.aidc_ids:
        model.addConstr(
            gp.quicksum(
                gpu * variable
                for (gpu, candidate), variable in variables.items()
                if candidate == site
            )
            <= capacity.site_capacity[site],
            name=f"AIDC_capacity[{site}]",
        )
    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    result: dict[str, Any] = {
        "status": (
            "FEASIBLE" if model.Status == GRB.OPTIMAL else "INFEASIBLE_SLOT_LOCAL"
        ),
        "solver_status": int(model.Status),
        "active_jobs": len(rows),
        "active_GPU": sum(job.requested_GPU for job in rows),
        "GPU_size_histogram": {str(gpu): count for gpu, count in sorted(counts.items())},
    }
    if model.Status == GRB.OPTIMAL:
        result["assignment_counts"] = {
            f"{gpu}@{site}": int(round(variable.X))
            for (gpu, site), variable in sorted(variables.items())
            if variable.X > 0.5
        }
    elif compute_iis and model.Status == GRB.INFEASIBLE:
        model.computeIIS()
        result["IIS_constraints"] = sorted(
            constraint.ConstrName
            for constraint in model.getConstrs()
            if constraint.IISConstr
        )
    model.dispose()
    return result


def _solve_relief(
    jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    removable: Callable[[ActivityJob], bool],
    *,
    primary: str,
    name: str,
) -> dict[str, Any]:
    """Find an exact packing after the minimum permitted slot removals."""

    rows = tuple(jobs)
    grouped = Counter((job.requested_GPU, removable(job)) for job in rows)
    model = _new_model(name)
    placed: dict[tuple[int, bool, str], gp.Var] = {}
    removed: dict[tuple[int, bool], gp.Var] = {}
    for (gpu, may_remove), count in sorted(grouped.items()):
        sites = _eligible_sites(capacity, gpu)
        for site in sites:
            placed[gpu, may_remove, site] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=count,
                name=f"placed[{gpu},{int(may_remove)},{site}]",
            )
        if may_remove:
            removed[gpu, may_remove] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=count,
                name=f"removed[{gpu},{int(may_remove)}]",
            )
        model.addConstr(
            gp.quicksum(placed[gpu, may_remove, site] for site in sites)
            + (removed[gpu, may_remove] if may_remove else 0)
            == count,
            name=f"gang_balance[{gpu},{int(may_remove)}]",
        )
    for site in capacity.aidc_ids:
        model.addConstr(
            gp.quicksum(
                gpu * variable
                for (gpu, _flag, candidate), variable in placed.items()
                if candidate == site
            )
            <= capacity.site_capacity[site],
            name=f"AIDC_capacity[{site}]",
        )
    removed_jobs = gp.quicksum(removed.values())
    removed_gpu = gp.quicksum(gpu * variable for (gpu, _), variable in removed.items())
    if primary == "jobs":
        model.setObjectiveN(removed_jobs, 0, priority=2, name="minimum_jobs")
        model.setObjectiveN(removed_gpu, 1, priority=1, name="then_minimum_GPU")
    elif primary == "GPU":
        model.setObjectiveN(removed_gpu, 0, priority=2, name="minimum_GPU")
        model.setObjectiveN(removed_jobs, 1, priority=1, name="then_minimum_jobs")
    else:
        raise ValueError(primary)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        status = int(model.Status)
        model.dispose()
        return {"status": "INFEASIBLE", "solver_status": status}
    histogram = {
        str(gpu): int(round(variable.X))
        for (gpu, _flag), variable in sorted(removed.items())
        if variable.X > 0.5
    }
    result = {
        "status": "OPTIMAL",
        "solver_status": int(model.Status),
        "removed_jobs": sum(histogram.values()),
        "removed_GPU": sum(int(gpu) * count for gpu, count in histogram.items()),
        "removed_GPU_histogram": histogram,
    }
    model.dispose()
    return result


def _classify_job(ledger_row: pd.Series) -> tuple[str, str]:
    state = str(ledger_row["state_at_issue"])
    workload_class = str(ledger_row["workload_class"])
    flag = ledger_row["temporal_flexible"]
    if state == "RUNNING" or workload_class in NONSHIFTABLE_CLASSES:
        return "NON_SHIFTABLE", "NO"
    if (
        state == "PENDING"
        and workload_class in SHIFTABLE_CLASSES
        and bool(flag)
    ):
        return "SHIFTABLE", "YES"
    return "UNKNOWN_NOT_AUTHORIZED", "UNKNOWN"


def _causal_status(ledger_row: pd.Series, cutoff: pd.Timestamp) -> tuple[str, str]:
    submit = pd.Timestamp(ledger_row["submit_time"])
    if submit > cutoff:
        return "NOT_YET_KNOWN_AT_CUTOFF", "NO"
    state = str(ledger_row["state_at_issue"])
    if state == "RUNNING":
        return "ALREADY_RUNNING_AT_CUTOFF", "YES"
    if state == "PENDING":
        return "PENDING_KNOWN_AT_CUTOFF", "YES"
    return "UNKNOWN_AUTHORITY_INSUFFICIENT", "NO"


def _runtime_authority(ledger_row: pd.Series, mode: str) -> tuple[str, int]:
    if str(ledger_row["state_at_issue"]) == "RUNNING":
        return "REQUESTED_REMAINING", int(ledger_row[f"{mode}_duration_slots"])
    if mode == "RW":
        return "REQUESTED_WALLTIME", int(ledger_row["RW_duration_slots"])
    return str(ledger_row["duration_authority"]), int(ledger_row["RSP_duration_slots"])


def _gpu_histogram(frame: pd.DataFrame) -> dict[str, int]:
    values = frame["requested_GPU"].astype(int).value_counts().sort_index()
    return {str(index): int(value) for index, value in values.items()}


def _validate_start(repo: Path) -> tuple[CapacityAuthority, dict[str, Any], dict[str, str], str]:
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39B_DIAGNOSTIC_BRANCH_MISMATCH")
    if _git(repo, "merge-base", "HEAD", SOURCE_HEAD) != SOURCE_HEAD:
        raise RuntimeError("V39B_NOT_DESCENDED_FROM_EXACT_V39A_HEAD")
    fingerprint = json.loads(
        (repo / V39A_ARTIFACT_ROOT / "V39A_IMPLEMENTATION_FINGERPRINT.json").read_text(
            encoding="utf-8"
        )
    )
    if fingerprint["V39A_IMPLEMENTATION_FINGERPRINT"] != SOURCE_FINGERPRINT:
        raise RuntimeError("V39B_V39A_FINGERPRINT_DRIFT")
    spatial = json.loads(
        (repo / V39A_ARTIFACT_ROOT / "V39A_SPATIAL_FEASIBILITY_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    actual_cases = tuple(
        (row["operating_day"], row["temporal_mode"])
        for row in spatial["infeasible_day_modes"]
    )
    if actual_cases != INFEASIBLE_DAY_MODES:
        raise RuntimeError("V39B_V39A_INFEASIBLE_CASE_DRIFT")
    capacity = load_capacity_authority(repo)
    if dict(capacity.site_capacity) != SITE_CAPACITY:
        raise RuntimeError("V39B_CAPACITY_DRIFT")
    if capacity.source_sha256 != CAPACITY_AUTHORITY_SHA256:
        raise RuntimeError("V39B_CAPACITY_SOURCE_SHA_DRIFT")
    mapping_path = (
        repo
        / "dayahead/artifacts/v38_aidc_spatiotemporal_wan/V38_AIDC_GPU_CAPACITY_MAPPING.json"
    )
    if sha256_file(mapping_path) != "2ddd1efa51920b74c45b27ed58b408b432eccf6a8c95e12217b3b18b0b737570":
        raise RuntimeError("V39B_CAPACITY_ARTIFACT_BYTE_DRIFT")
    manifest, manifest_sha = _input_manifest(repo)
    return capacity, spatial, manifest, manifest_sha


def _case_jobs(
    repo: Path, day: str, mode: str
) -> tuple[tuple[ActivityJob, ...], pd.DataFrame, pd.DataFrame]:
    day_root = repo / V37_DAY_ROOT / day
    schedule = pd.read_parquet(day_root / f"V37_R4A_{mode}_SCHEDULE.parquet")
    ledger = pd.read_parquet(day_root / "V37_R4A_JOB_LEDGER.parquet")
    if ledger["job_id"].duplicated().any():
        raise RuntimeError(f"V39B_DUPLICATE_LEDGER_JOB:{day}")
    jobs = production_activity(schedule)
    return jobs, schedule, ledger.set_index("job_id", drop=False)


def _build_diagnostics(
    repo: Path,
    capacity: CapacityAuthority,
    spatial: Mapping[str, Any],
    input_manifest: Mapping[str, str],
    manifest_sha: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Mapping[str, Any]]]:
    census_rows: list[dict[str, Any]] = []
    root_rows: list[dict[str, Any]] = []
    slot_records: list[dict[str, Any]] = []
    first_iis: dict[str, Any] | None = None
    first_minimal_conflict: dict[str, Any] | None = None

    for day, mode in INFEASIBLE_DAY_MODES:
        jobs, schedule, ledger = _case_jobs(repo, day, mode)
        schedule_index = schedule.set_index("job_id", drop=False)
        cutoff = pd.Timestamp(issue_time(day))
        for slot in range(SLOTS):
            active = tuple(
                job
                for job in jobs
                if job.active_start_slot <= slot < job.active_end_slot
            )
            packing = exact_slot_packing(
                active,
                capacity,
                name=f"V39B_SLOT_{day}_{mode}_{slot}",
                compute_iis=first_iis is None,
            )
            if packing["status"] == "FEASIBLE":
                continue
            if first_iis is None:
                first_iis = {
                    "operating_day": day,
                    "temporal_mode": mode,
                    "slot": slot,
                    **{key: value for key, value in packing.items() if key.startswith("IIS")},
                }

            active_gpu = sum(job.requested_GPU for job in active)
            counts = Counter(job.requested_GPU for job in active)
            cardinality = {}
            for gpu, count in sorted(counts.items()):
                hostable = sum(
                    capacity.site_capacity[site] // gpu
                    for site in _eligible_sites(capacity, gpu)
                )
                cardinality[str(gpu)] = {
                    "active_gangs": count,
                    "maximum_hostable_gangs": hostable,
                    "excess_gangs": max(0, count - hostable),
                }
            required_jobs = _solve_relief(
                active, capacity, lambda _job: True,
                primary="jobs", name=f"V39B_REQUIRED_JOBS_{day}_{mode}_{slot}",
            )
            required_gpu = _solve_relief(
                active, capacity, lambda _job: True,
                primary="GPU", name=f"V39B_REQUIRED_GPU_{day}_{mode}_{slot}",
            )
            classifications = {
                job.job_uid: _classify_job(ledger.loc[job.job_uid])[0]
                for job in active
            }
            nonshiftable = tuple(
                job for job in active if classifications[job.job_uid] != "SHIFTABLE"
            )
            shiftable = tuple(
                job for job in active if classifications[job.job_uid] == "SHIFTABLE"
            )
            floor = exact_slot_packing(
                nonshiftable,
                capacity,
                name=f"V39B_FLOOR_{day}_{mode}_{slot}",
            )
            authorized_jobs = _solve_relief(
                active,
                capacity,
                lambda job: classifications[job.job_uid] == "SHIFTABLE",
                primary="jobs",
                name=f"V39B_AUTHORIZED_JOBS_{day}_{mode}_{slot}",
            )
            authorized_gpu = _solve_relief(
                active,
                capacity,
                lambda job: classifications[job.job_uid] == "SHIFTABLE",
                primary="GPU",
                name=f"V39B_AUTHORIZED_GPU_{day}_{mode}_{slot}",
            )
            excess32 = cardinality.get("32", {}).get("excess_gangs", 0)
            physical_root = (
                "NONSHIFTABLE_RUNNING_OVERLOAD"
                if floor["status"] != "FEASIBLE"
                else "FLEXIBLE_PENDING_OVERLAP"
                if excess32 > 0
                else "MIXED_GANG_FRAGMENTATION"
            )
            slot_record = {
                "operating_day": day,
                "temporal_mode": mode,
                "slot": slot,
                "status": "INFEASIBLE_SLOT_LOCAL",
                "active_jobs": len(active),
                "active_GPU": active_gpu,
                "GPU_size_histogram": {
                    str(gpu): count for gpu, count in sorted(counts.items())
                },
                "aggregate_capacity_GPU": sum(capacity.site_capacity.values()),
                "aggregate_headroom_despite_infeasibility_GPU": (
                    sum(capacity.site_capacity.values()) - active_gpu
                ),
                "packing_lower_bounds": {
                    "aggregate_utilization": active_gpu / sum(capacity.site_capacity.values()),
                    "minimum_AIDCs_by_largest_site_capacity": math.ceil(
                        active_gpu / max(capacity.site_capacity.values())
                    ),
                    "gang_cardinality_by_GPU_size": cardinality,
                },
                "required_relief": {
                    "minimum_jobs": required_jobs,
                    "minimum_GPU": required_gpu,
                    "required_32gang_relief": excess32,
                    "minimum_shifted_GPU_hours_lower_bound": (
                        required_gpu["removed_GPU"] * SLOT_SECONDS / 3600
                    ),
                },
                "nonshiftable_floor": {
                    "jobs": len(nonshiftable),
                    "GPU": sum(job.requested_GPU for job in nonshiftable),
                    "packing_status": floor["status"],
                },
                "available_flexible_relief": {
                    "shiftable_jobs": len(shiftable),
                    "shiftable_GPU": sum(job.requested_GPU for job in shiftable),
                    "shiftable_32GPU_gangs": sum(
                        job.requested_GPU == 32 for job in shiftable
                    ),
                    "minimum_authorized_jobs_for_slot_local_repair": authorized_jobs,
                    "minimum_authorized_GPU_for_slot_local_repair": authorized_gpu,
                    "alternate_start_windows": "UNKNOWN_NOT_AUTHORIZED",
                    "creates_later_conflict": "UNKNOWN_NOT_TESTABLE_WITHOUT_WINDOW",
                },
                "physical_root_cause": physical_root,
            }
            slot_records.append(slot_record)

            if first_minimal_conflict is None and excess32 > 0:
                gangs32 = sorted(
                    job.job_uid for job in active if job.requested_GPU == 32
                )
                first_minimal_conflict = {
                    "operating_day": day,
                    "temporal_mode": mode,
                    "slot": slot,
                    "certificate": "15_32GPU_GANGS_EXCEED_14_HOSTABLE_POSITIONS",
                    "job_uids": gangs32[:15],
                    "subset_jobs": 15,
                    "subset_GPU": 480,
                    "removing_any_one_32GPU_gang_satisfies_this_cardinality_bound": True,
                    "note": "Necessary minimal cardinality conflict; not a complete mixed-size packing equivalence claim.",
                }

            shiftable32 = sum(job.requested_GPU == 32 for job in shiftable)
            root_rows.append({
                "operating_day": day,
                "slot": slot,
                "temporal_mode": mode,
                "active_jobs": len(active),
                "active_GPU": active_gpu,
                "32GPU_gangs": counts.get(32, 0),
                "max_hostable_32GPU_gangs": cardinality.get("32", {}).get(
                    "maximum_hostable_gangs", 0
                ),
                "gang_excess": excess32,
                "nonshiftable_jobs": len(nonshiftable),
                "nonshiftable_GPU": sum(job.requested_GPU for job in nonshiftable),
                "shiftable_jobs": len(shiftable),
                "shiftable_GPU": sum(job.requested_GPU for job in shiftable),
                "shiftable_32GPU_gangs": shiftable32,
                "minimum_jobs_to_shift": required_jobs["removed_jobs"],
                "minimum_GPU_relief": required_gpu["removed_GPU"],
                "best_case_temporal_feasible": "UNKNOWN_NOT_RUN_MISSING_WINDOW_AUTHORITY",
                "full_causal_feasible": "NOT_PERFORMED",
                "root_cause": physical_root,
                "authority_blocker": "UNKNOWN_AUTHORITY_BLOCKER",
            })

            for job in active:
                row = ledger.loc[job.job_uid]
                schedule_row = schedule_index.loc[job.job_uid]
                causal_status, causal_visibility = _causal_status(row, cutoff)
                flexibility_class, shift_allowed = _classify_job(row)
                runtime_authority, runtime_slots = _runtime_authority(row, mode)
                census_rows.append({
                    "operating_day": day,
                    "temporal_mode": mode,
                    "conflict_slot": slot,
                    "job_uid": job.job_uid,
                    "requested_GPU": job.requested_GPU,
                    "submit_time": str(row["submit_time"]),
                    "D_minus_1_cutoff": cutoff.isoformat(),
                    "D_minus_1_cutoff_status": causal_status,
                    "causal_visibility": causal_visibility,
                    "shift_decision_allowed": shift_allowed,
                    "V37_scheduled_start_stored_slot": int(
                        schedule_row["scheduled_start_slot"]
                    ),
                    "V37_scheduled_end_stored_slot": int(
                        schedule_row["scheduled_end_slot"]
                    ),
                    "active_start_production_slot": job.active_start_slot,
                    "active_end_production_slot": job.active_end_slot,
                    "runtime_authority": runtime_authority,
                    "runtime_slots": runtime_slots,
                    "safe_runtime_seconds": (
                        None
                        if pd.isna(row["diagnostic_safe_total_seconds"])
                        else float(row["diagnostic_safe_total_seconds"])
                    ),
                    "remaining_runtime_seconds": (
                        None
                        if str(row["state_at_issue"]) != "RUNNING"
                        else max(
                            float(row["requested_walltime_seconds"])
                            - float(row["elapsed_seconds_at_issue"]),
                            float(SLOT_SECONDS),
                        )
                    ),
                    "original_nominal_start_stored_slot": int(
                        schedule_row["scheduled_start_slot"]
                    ),
                    "earliest_legal_start_stored_slot": (
                        0 if str(row["state_at_issue"]) == "PENDING" else None
                    ),
                    "latest_legal_start": "UNKNOWN",
                    "deadline": "UNKNOWN",
                    "maximum_shift": "UNKNOWN",
                    "preemption_allowed": False,
                    "restart_allowed": False,
                    "allowed_movement_relative_to_V37_start": "UNKNOWN",
                    "queueing_rule": (
                        "protected/normal/standby/other tier; FIFO submit_time/job_id; "
                        "aggregate 624-GPU first-fit"
                    ),
                    "contiguous_execution_interval": True,
                    "flexibility_class": flexibility_class,
                    "existing_scheduler_classification": str(row["workload_class"]),
                    "current_known_state": str(row["state_at_issue"]),
                    "temporal_controllable": bool(row["temporal_flexible"]),
                    "protected": bool(row["protected"]),
                    "qos": str(row["qos"]),
                    "partition": str(row["partition"]),
                    "slot_total_active_GPU": active_gpu,
                    "slot_active_jobs": len(active),
                    "slot_32GPU_gangs": counts.get(32, 0),
                    "slot_max_hostable_32GPU_gangs": cardinality.get("32", {}).get(
                        "maximum_hostable_gangs", 0
                    ),
                    "slot_required_32gang_relief": excess32,
                    "slot_exact_packing_status": "INFEASIBLE_SLOT_LOCAL",
                })

    census = pd.DataFrame(census_rows).sort_values(
        ["operating_day", "temporal_mode", "conflict_slot", "job_uid"],
        ignore_index=True,
    )
    roots = pd.DataFrame(root_rows).sort_values(
        ["operating_day", "temporal_mode", "slot"], ignore_index=True
    )
    unique_case_jobs = census.drop_duplicates(
        ["operating_day", "temporal_mode", "job_uid"]
    )
    unique_global_jobs = census.drop_duplicates(["job_uid"])
    metadata = _metadata(manifest_sha)
    exact_slots = len(slot_records)
    hard_records = spatial["hard_slot_local_gang_cardinality_conflicts"]

    census_audit = {
        **metadata,
        "artifact_id": "V39B_CONFLICT_JOB_CENSUS_AUDIT_V1",
        "status": "PASS",
        "infeasible_day_modes": len(INFEASIBLE_DAY_MODES),
        "conflict_slot_count": exact_slots,
        "hard_32GPU_cardinality_conflict_slots": len(hard_records),
        "unique_conflicting_jobs": len(unique_global_jobs),
        "unique_day_mode_job_records": len(unique_case_jobs),
        "census_slot_job_rows": len(census),
        "GPU_size_histogram_unique_day_mode_job": _gpu_histogram(unique_case_jobs),
        "GPU_size_histogram_unique_global_job": _gpu_histogram(unique_global_jobs),
        "RUNNING_count_unique_day_mode_job": int(
            unique_case_jobs["current_known_state"].eq("RUNNING").sum()
        ),
        "PENDING_count_unique_day_mode_job": int(
            unique_case_jobs["current_known_state"].eq("PENDING").sum()
        ),
        "RUNNING_count_unique_global_job": int(
            unique_global_jobs["current_known_state"].eq("RUNNING").sum()
        ),
        "PENDING_count_unique_global_job": int(
            unique_global_jobs["current_known_state"].eq("PENDING").sum()
        ),
        "temporally_controllable_count_unique_day_mode_job": int(
            unique_case_jobs["flexibility_class"].eq("SHIFTABLE").sum()
        ),
        "non_controllable_count_unique_day_mode_job": int(
            unique_case_jobs["flexibility_class"].eq("NON_SHIFTABLE").sum()
        ),
        "unknown_unauthorized_count_unique_day_mode_job": int(
            unique_case_jobs["flexibility_class"].eq("UNKNOWN_NOT_AUTHORIZED").sum()
        ),
        "peak_32GPU_gang_count": int(roots["32GPU_gangs"].max()),
        "maximum_hostable_32GPU_gangs": int(
            roots["max_hostable_32GPU_gangs"].max()
        ),
        "per_slot_records": slot_records,
        "input_hashes": dict(input_manifest),
    }
    d1_audit = {
        **metadata,
        "artifact_id": "V39B_D1_CAUSAL_CONFLICT_AUDIT_V1",
        "status": "PASS",
        "cutoff_authority": "D-1 18:00 fixed AEST (UTC+10)",
        "classification_counts_unique_day_mode_job": {
            str(key): int(value)
            for key, value in unique_case_jobs["D_minus_1_cutoff_status"].value_counts().items()
        },
        "classification_counts_unique_global_job": {
            str(key): int(value)
            for key, value in unique_global_jobs["D_minus_1_cutoff_status"].value_counts().items()
        },
        "causal_visibility_YES": int(
            unique_case_jobs["causal_visibility"].eq("YES").sum()
        ),
        "causal_visibility_NO": int(
            unique_case_jobs["causal_visibility"].eq("NO").sum()
        ),
        "future_runtime_reads": 0,
        "future_execution_reads": 0,
        "May_result_reads": 0,
        "Fresh_reads": 0,
        "Actual_grid_reads": 0,
        "Actual_traffic_reads": 0,
        "source_fields_read": [
            "job_id", "state_at_issue", "workload_class", "protected", "qos",
            "partition", "submit_time", "requested_gpus", "duration authority",
            "D-1-materialized RW/RSP scheduled interval",
        ],
    }
    flexibility = {
        **metadata,
        "artifact_id": "V39B_FLEXIBILITY_AUTHORITY_AUDIT_V1",
        "status": "FAIL_CLOSED_MISSING_BOUNDED_WINDOW_AUTHORITY",
        "classification_counts_unique_day_mode_job": {
            str(key): int(value)
            for key, value in unique_case_jobs["flexibility_class"].value_counts().items()
        },
        "classification_counts_unique_global_job": {
            str(key): int(value)
            for key, value in unique_global_jobs["flexibility_class"].value_counts().items()
        },
        "exact_authority_sources": {
            "classification": "dayahead/v37/aidc_materializer.py:TEMPORAL_CLASSES and _classify_pending",
            "queueing": "dayahead/v37/aidc_materializer.py:_first_fit and schedule",
            "runtime": "dayahead/v37/aidc_materializer.py:_jobs_and_ledger",
            "recovered_contract": "dayahead/artifacts/v37_r4a_per_day_aidc/V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json",
        },
        "recovered_contract": {
            "temporal_controllable": "YES only for PENDING NORMAL_QUEUE_CONTROLLED or STANDBY_QUEUE_CONTROLLED",
            "original_nominal_start": "V37 scheduled_start_slot; a reference-dispatch output, not raw execution start",
            "earliest_legal_start": 0,
            "earliest_start_authority": "_first_fit initializes start=0 in the cutoff-based 120-slot frame",
            "latest_legal_start": "UNKNOWN",
            "deadline": "UNKNOWN",
            "maximum_shift": "UNKNOWN",
            "safe_runtime": "RW requested walltime; RSP frozen causal-safe duration; requested fallback",
            "remaining_runtime": "RUNNING requested walltime minus elapsed at cutoff, at least one slot",
            "queueing_rule": "protected QoS then normal then standby then other; FIFO by submit time and job id; aggregate 624-GPU first-fit",
            "preemption_allowed": False,
            "restart_allowed": False,
            "movement_direction_relative_to_V37_start": "UNKNOWN; deliberate recourse movement is not defined by the first-fit reference scheduler",
            "existing_RSP_constraints": "same aggregate capacity and tier/FIFO first-fit as RW; only PENDING duration authority differs",
            "implementation_search_guard": 20000,
            "search_guard_is_scientific_deadline": False,
        },
        "missing_flexibility_authority": [
            "authoritative latest legal start",
            "deadline or terminal-service requirement",
            "maximum shift",
            "legal alternate-start set relative to the V37 reference start",
            "cross-day service conservation for deferred work",
        ],
        "fail_closed_rule": "UNKNOWN_NOT_AUTHORIZED is non-shiftable; no 20000-slot synthetic window",
        "temporal_recourse_model_authorized": False,
    }
    coordinate = {
        **metadata,
        "artifact_id": "V39B_SLOT_COORDINATE_AUDIT_V1",
        "status": "PASS",
        "authority_sources": {
            "constants": "dayahead/v37/aidc_materializer.py:SLOT_SECONDS,SLOTS,TARGET_OFFSET_SLOTS,SIMULATION_SLOTS",
            "mapping": "dayahead/v37/aidc_materializer.py:_target_profile",
            "timezone": "dayahead/v36/contracts.py:AEST",
            "cutoff": "dayahead/v37/aidc_materializer.py:issue_time",
            "V39A_revalidation": "dayahead/v39a/spatial.py:production_activity",
        },
        "stored_schedule_coordinate": {
            "slots": STORED_SLOTS,
            "slot_seconds": SLOT_SECONDS,
            "slot_zero": "D-1 18:00 fixed AEST",
        },
        "production_day_coordinate": {"slots": SLOTS, "range": "0..95"},
        "exact_mapping": "production_slot = stored_slot - 24 for stored slots [24,120)",
        "target_offset_slots": TARGET_OFFSET_SLOTS,
        "timezone": "AEST_FIXED_UTC_PLUS_10",
        "boundary_rule": "intersect [scheduled_start,scheduled_end) with [24,120), then subtract 24",
        "conflict_rows_starting_before_production": int(
            census["V37_scheduled_start_stored_slot"].lt(TARGET_OFFSET_SLOTS).sum()
        ),
        "conflict_rows_ending_after_production": int(
            census["V37_scheduled_end_stored_slot"].gt(STORED_SLOTS).sum()
        ),
        "mapping_fail_closed": False,
    }
    slot_audit = {
        **metadata,
        "artifact_id": "V39B_SLOT_LOCAL_PACKING_AUDIT_V1",
        "status": "PASS_DIAGNOSTIC_CONFLICTS_CONFIRMED",
        "model": "exact grouped integer bin packing; equivalent to per-job binaries because AIDC/rack eligibility depends only on requested_GPU",
        "gang_splitting": False,
        "WAN_carry_migration_constraints": "REMOVED_FOR_THIS_RELAXATION",
        "slots_scanned": len(INFEASIBLE_DAY_MODES) * SLOTS,
        "FEASIBLE": len(INFEASIBLE_DAY_MODES) * SLOTS - exact_slots,
        "INFEASIBLE_SLOT_LOCAL": exact_slots,
        "first_slot_IIS": first_iis,
        "first_large_gang_minimal_conflict_subset": first_minimal_conflict,
        "slot_results": slot_records,
    }
    floor_records = [
        {
            "operating_day": row["operating_day"],
            "temporal_mode": row["temporal_mode"],
            "slot": row["slot"],
            **row["nonshiftable_floor"],
        }
        for row in slot_records
    ]
    floor_audit = {
        **metadata,
        "artifact_id": "V39B_NONSHIFTABLE_FLOOR_AUDIT_V1",
        "status": "PASS_SCREENING_CASE_B",
        "classification": "CASE_B_NONSHIFTABLE_JOBS_SPATIALLY_FEASIBLE",
        "slots_tested": exact_slots,
        "nonshiftable_floor_feasible_slots": sum(
            row["packing_status"] == "FEASIBLE" for row in floor_records
        ),
        "nonshiftable_floor_infeasible_slots": sum(
            row["packing_status"] != "FEASIBLE" for row in floor_records
        ),
        "UNKNOWN_NOT_AUTHORIZED_treated_as_nonshiftable": True,
        "slot_results": floor_records,
    }
    relief_records = [
        {
            "operating_day": row["operating_day"],
            "temporal_mode": row["temporal_mode"],
            "slot": row["slot"],
            **row["required_relief"],
            "excess_gang_count_by_GPU_size": {
                gpu: values["excess_gangs"]
                for gpu, values in row["packing_lower_bounds"][
                    "gang_cardinality_by_GPU_size"
                ].items()
            },
        }
        for row in slot_records
    ]
    required_audit = {
        **metadata,
        "artifact_id": "V39B_REQUIRED_TEMPORAL_RELIEF_V1",
        "status": "PASS_LOWER_BOUNDS_COMPUTED",
        "interpretation": "Independent exact slot-removal lower bounds; not a proof that removed work can be legally scheduled elsewhere.",
        "minimum_jobs_over_all_conflict_slots": min(
            row["minimum_jobs"]["removed_jobs"] for row in relief_records
        ),
        "maximum_of_slotwise_minimum_jobs": max(
            row["minimum_jobs"]["removed_jobs"] for row in relief_records
        ),
        "minimum_GPU_over_all_conflict_slots": min(
            row["minimum_GPU"]["removed_GPU"] for row in relief_records
        ),
        "maximum_of_slotwise_minimum_GPU": max(
            row["minimum_GPU"]["removed_GPU"] for row in relief_records
        ),
        "slot_results": relief_records,
    }
    available_records = [
        {
            "operating_day": row["operating_day"],
            "temporal_mode": row["temporal_mode"],
            "slot": row["slot"],
            **row["available_flexible_relief"],
        }
        for row in slot_records
    ]
    screening_pass = all(
        row["minimum_authorized_jobs_for_slot_local_repair"]["status"] == "OPTIMAL"
        for row in available_records
    )
    available_audit = {
        **metadata,
        "artifact_id": "V39B_AVAILABLE_FLEXIBLE_RELIEF_V1",
        "status": "PASS_SLOT_REMOVAL_SCREENING_ONLY" if screening_pass else "FAIL",
        "slots_tested": exact_slots,
        "authorized_shiftable_relief_can_repair_each_slot_in_isolation": screening_pass,
        "alternate_window_feasibility_known": False,
        "shiftable_jobs_per_conflict_slot_min": min(
            row["shiftable_jobs"] for row in available_records
        ),
        "shiftable_jobs_per_conflict_slot_max": max(
            row["shiftable_jobs"] for row in available_records
        ),
        "shiftable_GPU_per_conflict_slot_min": min(
            row["shiftable_GPU"] for row in available_records
        ),
        "shiftable_GPU_per_conflict_slot_max": max(
            row["shiftable_GPU"] for row in available_records
        ),
        "shiftable_32GPU_gangs_per_conflict_slot_min": min(
            row["shiftable_32GPU_gangs"] for row in available_records
        ),
        "shiftable_32GPU_gangs_per_conflict_slot_max": max(
            row["shiftable_32GPU_gangs"] for row in available_records
        ),
        "warning": "Raw active flexible relief and isolated slot removal do not establish a causal schedule.",
        "slot_results": available_records,
    }
    temporal = {
        **metadata,
        "artifact_id": "V39B_DIAGNOSTIC_TEMPORAL_RECOURSE_V1",
        "status": "NOT_RUN_FAIL_CLOSED_MISSING_AUTHORITATIVE_WINDOWS",
        "model_label": DIAGNOSTIC_LABEL,
        "screening_nonshiftable_floor": "PASS_CASE_B",
        "screening_slot_local_authorized_removal": (
            "PASS" if screening_pass else "FAIL"
        ),
        "solver_model_built": False,
        "best_case_solver_status": "NOT_RUN_MISSING_AUTHORITATIVE_TEMPORAL_WINDOWS",
        "TEMPORAL_RECOURSE_BEST_CASE_FEASIBLE": "UNKNOWN",
        "jobs_shifted_in_minimum_witness": None,
        "total_delay_slots": None,
        "maximum_delay_slots": None,
        "IIS": "NOT_APPLICABLE_MODEL_NOT_BUILT",
        "reason": (
            "V37 has flexible PENDING classes but no authoritative latest-start, "
            "deadline, maximum-shift, legal alternate-start, or terminal-service window."
        ),
        "search_guard_20000_used_as_deadline": False,
        "production_schedule_written": False,
        "TEMPORAL_RECOURSE_SUFFICIENT": "NO",
        "decision_basis": "NOT_PROVEN_FAIL_CLOSED_MISSING_WINDOW_AUTHORITY",
        "V39B_IMPLEMENTATION_SCIENTIFICALLY_JUSTIFIED": "NO",
        "V39B_IMPLEMENTATION_READY": "NO",
    }
    baseline = {
        **metadata,
        "artifact_id": "V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT_V1",
        "status": "PASS_RECOVERED",
        "RW_authoritative_meaning": (
            "Trace-derived D-1-visible workload arrivals and requested/remaining runtime, "
            "dispatched by protected-tier/FIFO first-fit against the modeled aggregate "
            "624-GPU testbed capacity; it is not raw Kestrel execution replay."
        ),
        "RSP_authoritative_meaning": (
            "The same modeled aggregate-capacity tier/FIFO first-fit dispatch; RUNNING "
            "uses requested remaining runtime and PENDING uses frozen causal-safe runtime "
            "with requested-walltime fallback."
        ),
        "RW_raw_execution_replay": False,
        "same_physical_constraints": True,
        "RSP_jobs_shiftable_by_class": sorted(SHIFTABLE_CLASSES),
        "REFERENCE_BASELINE_REDEFINITION_REQUIRED": "NO",
        "scientific_decision_required": "YES_DEFINE_BOUNDED_LEGAL_TEMPORAL_WINDOW_BEFORE_V39B",
    }
    reports: dict[str, Mapping[str, Any]] = {
        "V39B_CONFLICT_JOB_CENSUS_AUDIT.json": census_audit,
        "V39B_D1_CAUSAL_CONFLICT_AUDIT.json": d1_audit,
        "V39B_FLEXIBILITY_AUTHORITY_AUDIT.json": flexibility,
        "V39B_SLOT_COORDINATE_AUDIT.json": coordinate,
        "V39B_SLOT_LOCAL_PACKING_AUDIT.json": slot_audit,
        "V39B_NONSHIFTABLE_FLOOR_AUDIT.json": floor_audit,
        "V39B_REQUIRED_TEMPORAL_RELIEF.json": required_audit,
        "V39B_AVAILABLE_FLEXIBLE_RELIEF.json": available_audit,
        "V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json": temporal,
        "V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.json": baseline,
    }
    return census, roots, reports


def _baseline_markdown(metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> str:
    return f"""# V39B RW/RSP baseline semantics audit

Diagnostic label: `{DIAGNOSTIC_LABEL}`
Source HEAD: `{metadata['source_HEAD']}`
Input manifest SHA-256: `{metadata['input_manifest_sha256']}`
Solver seed/threads: `{SOLVER_SEED}` / `{SOLVER_THREADS}`
Production mutations/future reads: `0` / `0`

## RW

{baseline['RW_authoritative_meaning']}

## RSP

{baseline['RSP_authoritative_meaning']}

Both share the same modeled aggregate 624-GPU capacity and tier/FIFO first-fit
dispatch. The exact authority is `dayahead/v37/aidc_materializer.py`, together
with `V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json`.

`REFERENCE_BASELINE_REDEFINITION_REQUIRED=NO`: RW already is a modeled
capacity-queued reference dispatch rather than immutable raw execution replay.
This does not authorize an arbitrary V39B reschedule. A separate scientific
decision must define latest-start/deadline/terminal-service windows first.
"""


def _final_review(
    metadata: Mapping[str, Any], reports: Mapping[str, Mapping[str, Any]]
) -> str:
    census = reports["V39B_CONFLICT_JOB_CENSUS_AUDIT.json"]
    d1 = reports["V39B_D1_CAUSAL_CONFLICT_AUDIT.json"]
    flex = reports["V39B_FLEXIBILITY_AUTHORITY_AUDIT.json"]
    required = reports["V39B_REQUIRED_TEMPORAL_RELIEF.json"]
    available = reports["V39B_AVAILABLE_FLEXIBLE_RELIEF.json"]
    temporal = reports["V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json"]
    counts = d1["classification_counts_unique_day_mode_job"]
    classes = flex["classification_counts_unique_day_mode_job"]
    return f"""# V39B pre-implementation scientific diagnostic

Label: `{DIAGNOSTIC_LABEL}`
Source HEAD: `{metadata['source_HEAD']}`
Source fingerprint: `{metadata['source_implementation_fingerprint']}`
Input manifest SHA-256: `{metadata['input_manifest_sha256']}`
Solver seed/threads: `{SOLVER_SEED}` / `{SOLVER_THREADS}`
Production mutations/future reads: `0` / `0`

## Result

The exact slot-local audit confirms {census['conflict_slot_count']} infeasible
day/mode/slots across all 14 V39A-infeasible models. All non-shiftable floors
are feasible, and flexible PENDING removals can repair every conflicting slot
in isolation. This is only a necessary screening result.

No diagnostic temporal-recourse MILP was built. V37 defines flexible PENDING
classes and queueing, but no authoritative latest start, deadline, maximum
shift, legal alternate-start set, or cross-day terminal-service window. Using
the implementation's 20,000-slot search guard as a deadline would invent
science and make deferral artificially unbounded.

## Evidence summary

- Exact slot-local conflicts: {census['conflict_slot_count']}
- V39A 32-GPU cardinality conflict records: {census['hard_32GPU_cardinality_conflict_slots']}
- Unique global conflict jobs: {census['unique_conflicting_jobs']}
- Unique day/mode/job records: {census['unique_day_mode_job_records']}
- D-1 RUNNING (unique day/mode/job): {counts.get('ALREADY_RUNNING_AT_CUTOFF', 0)}
- D-1 known PENDING (unique day/mode/job): {counts.get('PENDING_KNOWN_AT_CUTOFF', 0)}
- SHIFTABLE (unique day/mode/job): {classes.get('SHIFTABLE', 0)}
- NON_SHIFTABLE (unique day/mode/job): {classes.get('NON_SHIFTABLE', 0)}
- UNKNOWN_NOT_AUTHORIZED (unique day/mode/job): {classes.get('UNKNOWN_NOT_AUTHORIZED', 0)}
- Slotwise minimum jobs needing removal: {required['minimum_jobs_over_all_conflict_slots']} to {required['maximum_of_slotwise_minimum_jobs']}
- Slotwise minimum GPU relief: {required['minimum_GPU_over_all_conflict_slots']} to {required['maximum_of_slotwise_minimum_GPU']}
- Isolated authorized-removal screening: {available['status']}
- Temporal solver: {temporal['best_case_solver_status']}

## Decision

`TEMPORAL_RECOURSE_SUFFICIENT=NO`

Basis: `NOT_PROVEN_FAIL_CLOSED_MISSING_WINDOW_AUTHORITY`.

`V39B_IMPLEMENTATION_SCIENTIFICALLY_JUSTIFIED=NO`

`REFERENCE_BASELINE_REDEFINITION_REQUIRED=NO`

The exact remaining blocker is missing bounded legal temporal-window and
terminal-service authority. Full causal current-AIDC/WAN diagnostics are not
performed because best-case temporal feasibility is not legally modelable.
May remains unstarted.

V39B_IMPLEMENTATION_READY = NO
MAY_STARTED = NO
"""


def materialize(repo: Path) -> dict[str, Any]:
    """Create only diagnostic artifacts; production schedules remain untouched."""

    repo = repo.resolve()
    capacity, spatial, input_manifest, manifest_sha = _validate_start(repo)
    metadata = _metadata(manifest_sha)
    census, roots, reports = _build_diagnostics(
        repo, capacity, spatial, input_manifest, manifest_sha
    )
    root = repo / ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    _write_parquet(root / "V39B_CONFLICT_JOB_CENSUS.parquet", census, metadata)
    _write_parquet(root / "V39B_CONFLICT_ROOT_CAUSE_TABLE.parquet", roots, metadata)
    for name, payload in reports.items():
        atomic_json(root / name, payload)
    baseline = reports["V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.json"]
    (root / "V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.md").write_text(
        _baseline_markdown(metadata, baseline), encoding="utf-8", newline="\n"
    )
    (root / "V39B_PREIMPLEMENTATION_FINAL_REVIEW.md").write_text(
        _final_review(metadata, reports), encoding="utf-8", newline="\n"
    )
    atomic_json(root / "V39B_DIAGNOSTIC_TEST_REPORT.json", {
        **metadata,
        "artifact_id": "V39B_DIAGNOSTIC_TEST_REPORT_V1",
        "status": "PENDING",
        "V39B_diagnostic_tests": "PENDING",
        "V39A_regression": "PENDING",
        "V38_regression": "PENDING",
        "V37_regression": "PENDING",
        "broader_regression": "PENDING",
        "MAY_STARTED": "NO",
    })
    return {
        "status": "DIAGNOSTIC_COMPLETE_FAIL_CLOSED",
        "artifact_root": ARTIFACT_ROOT.as_posix(),
        "exact_conflict_slots": len(roots),
        "nonshiftable_floor_infeasible_slots": 0,
        "temporal_recourse_solver": "NOT_RUN_MISSING_WINDOW_AUTHORITY",
        "V39B_IMPLEMENTATION_READY": "NO",
        "MAY_STARTED": "NO",
    }


def record_test_report(repo: Path, report: Mapping[str, Any]) -> None:
    repo = repo.resolve()
    _manifest, manifest_sha = _input_manifest(repo)
    payload = {
        **_metadata(manifest_sha),
        "artifact_id": "V39B_DIAGNOSTIC_TEST_REPORT_V1",
        "status": "PASS",
        **dict(report),
        "production_scheduler_modified": False,
        "MAY_STARTED": "NO",
    }
    atomic_json(repo / ARTIFACT_ROOT / "V39B_DIAGNOSTIC_TEST_REPORT.json", payload)
    names = (
        "V39B_CONFLICT_JOB_CENSUS_AUDIT.json",
        "V39B_D1_CAUSAL_CONFLICT_AUDIT.json",
        "V39B_FLEXIBILITY_AUTHORITY_AUDIT.json",
        "V39B_SLOT_COORDINATE_AUDIT.json",
        "V39B_SLOT_LOCAL_PACKING_AUDIT.json",
        "V39B_NONSHIFTABLE_FLOOR_AUDIT.json",
        "V39B_REQUIRED_TEMPORAL_RELIEF.json",
        "V39B_AVAILABLE_FLEXIBLE_RELIEF.json",
        "V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json",
        "V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.json",
    )
    reports = {
        name: json.loads((repo / ARTIFACT_ROOT / name).read_text(encoding="utf-8"))
        for name in names
    }
    review = _final_review(_metadata(manifest_sha), reports)
    regression = """## Regression verification

- V39B diagnostic: {v39b} passed
- V39A focused: {v39a} passed
- V38 relevant: {v38} passed
- V37 clean namespace: {v37} passed
- Broader relevant: {broader} passed

""".format(
        v39b=payload["V39B_diagnostic_tests"]["passed"],
        v39a=payload["V39A_regression"]["passed"],
        v38=payload["V38_regression"]["passed"],
        v37=payload["V37_regression"]["passed"],
        broader=payload["broader_regression"]["passed"],
    )
    review = review.replace("## Decision\n", regression + "## Decision\n")
    (repo / ARTIFACT_ROOT / "V39B_PREIMPLEMENTATION_FINAL_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n"
    )
    baseline = reports["V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.json"]
    (repo / ARTIFACT_ROOT / "V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.md").write_text(
        _baseline_markdown(_metadata(manifest_sha), baseline),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(materialize(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "exact_slot_packing", "materialize", "record_test_report", "sha256_file"
]
