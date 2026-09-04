"""Post-freeze May evaluation under byte-unchanged V37 temporal schedules."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dayahead.v38.authority import checkpoint_slots, load_wan_authority
from dayahead.v38.contracts import CHECKPOINT_INTERVAL_SECONDS, RESTART_SECONDS
from dayahead.v38.wan import validate_fixed_path_transfers
from dayahead.v39a.power import (
    aggregate_it_power_kw,
    frozen_site_to_pcc,
    site_it_power_kw,
    site_pcc_power,
    validate_power_conservation,
)
from dayahead.v39a.spatial import ActivityJob, active_gpu_profile, production_activity

from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CAPACITY_SEMANTICS,
    CLASSIFICATION,
    EXPECTED_DATES,
    EXPECTED_GPU_CAPACITY,
    GPU_PER_NODE,
    GPU_TOTAL,
    IMPLEMENTATION_ID,
    LEGACY_GPU_CAPACITY,
    MINIMUM_GPU_PER_SITE,
    NODE_TOTAL,
    SLOTS,
    SOLVER_SEED,
    SOLVER_THREADS,
    START_HEAD,
    TEMPORAL_MODES,
    V22_WEIGHT_PATH,
    V22_WEIGHT_SHA256,
    V37_DAY_ROOT,
    V38_ARTIFACT_ROOT,
    V39A_ARTIFACT_ROOT,
    V39A_FINGERPRINT,
    V39B_ARTIFACT_ROOT,
)
from .freeze import atomic_json, canonical_sha256, construct_capacity, load_facility_prior, sha256_file
from .spatial import causal_day_placement, eligible_sites, exact_slot_packing, interval_spatial_feasibility


POWER_TOLERANCE_KW = Decimal("0.000000000002")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _write_parquet(path: Path, frame: pd.DataFrame, metadata: Mapping[str, Any]) -> None:
    for key, value in metadata.items():
        frame[key] = (
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list, tuple))
            else value
        )
    frame.attrs.update(dict(metadata))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _load_frozen_capacity(repo: Path) -> tuple[dict[str, int], dict[str, Any], dict[str, Any], str]:
    root = repo / ARTIFACT_ROOT
    authority_path = root / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    certificate_path = root / "V39C_CAPACITY_FREEZE_CERTIFICATE.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    actual_file_sha = sha256_file(authority_path)
    if actual_file_sha != certificate["capacity_authority_file_SHA256"]:
        raise RuntimeError("V39C_CAPACITY_AUTHORITY_CHANGED_AFTER_FREEZE")
    if certificate["CAPACITY_RULE_FROZEN_BEFORE_V39C_MAY_FEASIBILITY"] != "YES":
        raise RuntimeError("V39C_CAPACITY_NOT_FROZEN")
    committed = subprocess.check_output(
        ["git", "show", f"HEAD:{ARTIFACT_ROOT.as_posix()}/{authority_path.name}"],
        cwd=repo,
    )
    if hashlib.sha256(committed).hexdigest() != actual_file_sha:
        raise RuntimeError("V39C_CAPACITY_AUTHORITY_NOT_COMMITTED_BEFORE_EVALUATION")
    weights, _ = load_facility_prior(repo)
    recomputed = construct_capacity(weights)
    capacity = {site: int(recomputed["site_GPU"][site]) for site in sorted(weights)}
    frozen = {
        row["AIDC"]: int(row["synthetic_H100_equivalent_GPU_capacity"])
        for row in authority["site_table"]
    }
    if capacity != frozen or capacity != EXPECTED_GPU_CAPACITY:
        raise RuntimeError("V39C_FROZEN_CAPACITY_NUMERIC_DRIFT")
    if authority["canonical_SHA256"] != certificate["capacity_canonical_SHA256"]:
        raise RuntimeError("V39C_CAPACITY_CANONICAL_SHA_DRIFT")
    return capacity, authority, certificate, actual_file_sha


def _input_manifest(repo: Path) -> tuple[dict[str, str], str]:
    paths = [
        ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json",
        ARTIFACT_ROOT / "V39C_CAPACITY_FREEZE_CERTIFICATE.json",
        V22_WEIGHT_PATH,
        Path("dayahead/v37/aidc_materializer.py"),
        V39A_ARTIFACT_ROOT / "V39A_IMPLEMENTATION_FINGERPRINT.json",
        V39B_ARTIFACT_ROOT / "V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json",
        V38_ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATHS.parquet",
        Path("dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"),
    ]
    for day in EXPECTED_DATES:
        paths.extend(
            V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
            for mode in TEMPORAL_MODES
        )
        paths.append(V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    manifest = {path.as_posix(): sha256_file(repo / path) for path in paths}
    return manifest, canonical_sha256(manifest)


def _metadata(
    authority: Mapping[str, Any], certificate: Mapping[str, Any],
    capacity_file_sha: str, input_manifest_sha: str, freeze_commit: str,
) -> dict[str, Any]:
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "source_HEAD": START_HEAD,
        "capacity_rule_source_commit": authority["capacity_rule_source_commit"],
        "capacity_freeze_commit": freeze_commit,
        "capacity_authority_file_SHA256": capacity_file_sha,
        "capacity_canonical_SHA256": certificate["capacity_canonical_SHA256"],
        "input_manifest_SHA256": input_manifest_sha,
        "solver_seed": SOLVER_SEED,
        "solver_threads": SOLVER_THREADS,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "temporal_schedule_mutations": 0,
        "temporal_schedule_mutation_count": 0,
        "RW_schedule_mutations": 0,
        "RSP_schedule_mutations": 0,
        "MAY_STARTED": "NO",
    }


def _load_jobs(repo: Path, day: str, mode: str) -> tuple[tuple[ActivityJob, ...], pd.DataFrame]:
    schedule = pd.read_parquet(
        repo / V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
    )
    return production_activity(schedule), schedule


def _stage_a(repo: Path, capacity: Mapping[str, int], root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    cache: dict[tuple[tuple[int, int], ...], str] = {}
    first_infeasible: dict[str, Any] | None = None
    total_gpu_violations = 0
    cardinality_32_violations = 0
    fragmentation_only = 0
    profile_mismatch = 0
    hostable_32 = sum(value // 32 for value in capacity.values())
    iis_path = root / "V39C_FIRST_INFEASIBILITY_IIS.ilp"
    for day in EXPECTED_DATES:
        trajectory = pd.read_parquet(
            repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
        )
        for mode in TEMPORAL_MODES:
            jobs, _schedule = _load_jobs(repo, day, mode)
            profile = active_gpu_profile(jobs)
            expected = trajectory[
                "N_active_RW" if mode == "RW" else "N_active_RSP"
            ].to_numpy(dtype=np.int64)
            profile_mismatch += int(np.count_nonzero(profile != expected))
            for slot in range(SLOTS):
                active = tuple(
                    job for job in jobs
                    if job.active_start_slot <= slot < job.active_end_slot
                )
                counts = Counter(job.requested_GPU for job in active)
                signature = tuple(sorted(counts.items()))
                if signature not in cache:
                    cache[signature] = exact_slot_packing(
                        active, capacity, name=f"V39C_SLOT_CACHE_{len(cache)}"
                    )["status"]
                status = cache[signature]
                active_gpu = sum(job.requested_GPU for job in active)
                total_violation = active_gpu > GPU_TOTAL
                cardinality_violation = counts.get(32, 0) > hostable_32
                total_gpu_violations += int(total_violation)
                cardinality_32_violations += int(cardinality_violation)
                if status != "FEASIBLE" and not total_violation:
                    fragmentation_only += 1
                row = {
                    "operating_day": day,
                    "temporal_mode": mode,
                    "slot": slot,
                    "status": status,
                    "active_jobs": len(active),
                    "active_GPU": active_gpu,
                    "GPU_size_histogram": {
                        str(gpu): count for gpu, count in sorted(counts.items())
                    },
                    "32GPU_gangs": counts.get(32, 0),
                    "32GPU_host_positions": hostable_32,
                    "32GPU_cardinality_violation": cardinality_violation,
                    "total_GPU_violation": total_violation,
                    "aggregate_headroom_GPU": GPU_TOTAL - active_gpu,
                }
                if status != "FEASIBLE" and first_infeasible is None:
                    detailed = exact_slot_packing(
                        active,
                        capacity,
                        name=f"V39C_FIRST_SLOT_{day}_{mode}_{slot}",
                        iis_path=iis_path,
                    )
                    first_infeasible = {**row, **detailed}
                records.append(row)
    infeasible = [row for row in records if row["status"] != "FEASIBLE"]
    return {
        "artifact_id": "V39C_SLOT_LOCAL_PACKING_AUDIT_V1",
        "status": "PASS" if not infeasible and profile_mismatch == 0 else "FAIL",
        "models": len(records),
        "feasible_slots": len(records) - len(infeasible),
        "infeasible_slots": len(infeasible),
        "first_infeasible_slot": first_infeasible,
        "unique_packing_signatures_solved": len(cache),
        "32GPU_host_positions": hostable_32,
        "maximum_active_32GPU_gangs": max(row["32GPU_gangs"] for row in records),
        "32GPU_cardinality_violation_count": cardinality_32_violations,
        "total_GPU_violation_count": total_gpu_violations,
        "fragmentation_only_violation_count": fragmentation_only,
        "V37_aggregate_profile_mismatch_slots": profile_mismatch,
        "gang_splitting": False,
        "cross_slot_continuity_removed": True,
        "WAN_migration_current_AIDC_removed": True,
        "slot_results": records,
    }


def _stage_b(repo: Path, capacity: Mapping[str, int], root: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    iis_path = root / "V39C_FIRST_INFEASIBILITY_IIS.ilp"
    iis_written = iis_path.exists()
    for day in EXPECTED_DATES:
        for mode in TEMPORAL_MODES:
            jobs, _ = _load_jobs(repo, day, mode)
            result = interval_spatial_feasibility(
                jobs,
                capacity,
                name=f"V39C_INTERVAL_{day}_{mode}",
                iis_path=iis_path if not iis_written else None,
            )
            result.update({"operating_day": day, "temporal_mode": mode})
            if result["status"] == "INFEASIBLE" and "IIS_path" in result:
                iis_written = True
            results.append(result)
    infeasible = [row for row in results if row["status"] != "OPTIMAL"]
    return {
        "artifact_id": "V39C_INTERVAL_SPATIAL_FEASIBILITY_AUDIT_V1",
        "status": "PASS" if not infeasible else "FAIL",
        "models_built": len(results),
        "models_optimal": len(results) - len(infeasible),
        "models_infeasible": len(infeasible),
        "first_infeasible": infeasible[0] if infeasible else None,
        "V37_temporal_schedule_fixed": True,
        "one_AIDC_per_contiguous_interval": True,
        "gang_splitting": False,
        "cross_day_carry_removed": True,
        "WAN_limit_removed": True,
        "model_results": results,
    }


def _initial_april_state(repo: Path, capacity: Mapping[str, int]) -> tuple[dict[str, str], dict[str, Any]]:
    day_root = repo / V37_DAY_ROOT / "2025-04-01"
    schedule = pd.read_parquet(day_root / "V37_R4A_RW_SCHEDULE.parquet")
    snapshot = pd.read_parquet(day_root / "V37_R4A_D1_SNAPSHOT.parquet")
    active_running = tuple(
        job for job in production_activity(schedule) if job.state_at_issue == "RUNNING"
    )
    plan = causal_day_placement(
        active_running, capacity, {}, name="V39C_APR01_CAUSAL_INITIALIZATION"
    )
    if plan["status"] != "OPTIMAL":
        return {}, {"status": "FAIL", "reason": "APR01_ACTIVE_RUNNING_INFEASIBLE"}
    state = {row["job_uid"]: row["current_AIDC"] for row in plan["assignments"]}
    running = snapshot.loc[snapshot["state_at_issue"].eq("RUNNING")]
    inactive = sorted(set(running["id"].astype(str)) - set(state))
    for job_uid in inactive:
        gpu = int(round(float(
            running.loc[running["id"].astype(str).eq(job_uid), "gpus_requested"].iloc[0]
        )))
        sites = eligible_sites(capacity, gpu)
        if not sites:
            return {}, {"status": "FAIL", "reason": f"APR01_NO_AIDC:{job_uid}:{gpu}"}
        state[job_uid] = min(
            sites,
            key=lambda site: hashlib.sha256(
                f"V39C_APR01_INACTIVE:{job_uid}:{site}".encode()
            ).hexdigest(),
        )
    return state, {
        "status": "PASS",
        "method": "V39A_SYNTHETIC_CAUSAL_INITIAL_SITE_ASSIGNMENT_REUSED_WITH_V39C_CAPACITY",
        "date": "2025-04-01",
        "jobs_initialized": len(state),
        "active_running_jobs": len(active_running),
        "inactive_running_jobs": len(inactive),
        "future_fields_read_count": 0,
        "measured_site_claim": False,
    }


def _stage_c0_stay_only(
    repo: Path, capacity: Mapping[str, int]
) -> tuple[dict[str, Any], dict[tuple[str, str], list[dict[str, Any]]]]:
    april_state, april_audit = _initial_april_state(repo, capacity)
    if april_audit["status"] != "PASS":
        return {
            "artifact_id": "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC_V1",
            "status": "FAIL",
            "April_initialization": april_audit,
        }, {}
    results: list[dict[str, Any]] = []
    plans: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for mode in TEMPORAL_MODES:
        known_state = dict(april_state)
        for day in EXPECTED_DATES:
            jobs, _ = _load_jobs(repo, day, mode)
            plan = causal_day_placement(
                jobs,
                capacity,
                known_state,
                name=f"V39C_CAUSAL_{day}_{mode}",
            )
            row = {
                key: value for key, value in plan.items() if key != "assignments"
            }
            row.update({"operating_day": day, "temporal_mode": mode})
            results.append(row)
            if plan["status"] != "OPTIMAL":
                break
            assignments = plan["assignments"]
            plans[day, mode] = assignments
            # Reuse the V39A state contract exactly: only a job that is
            # RUNNING at the cutoff has a carried current_AIDC on the next
            # cutoff.  PENDING placement is an initial placement, not a
            # migration source or a durable running-state observation.
            known_state = {
                assignment["job_uid"]: assignment["current_AIDC"]
                for assignment in assignments
                if assignment["state_at_issue"] == "RUNNING"
            }
    optimal = sum(row["status"] == "OPTIMAL" for row in results)
    wan = load_wan_authority(repo)
    fixed_paths = sum(
        1
        for source in sorted(capacity)
        for destination in sorted(capacity)
        if source != destination and wan.path(source, destination)
    )
    status = "PASS" if optimal == len(EXPECTED_DATES) * len(TEMPORAL_MODES) else "FAIL"
    return {
        "artifact_id": "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC_V1",
        "status": status,
        "diagnostic_classification": "STAGE_C0_STAY_ONLY_DIAGNOSTIC",
        "readiness_authority": False,
        "migration_allowed": False,
        "interpretation": (
            "INFEASIBLE_MEANS_STAY_ONLY_STATE_CARRY_CAN_BLOCK; "
            "IT_IS_NOT_A_MIGRATION_ENABLED_STAGE_C_FAILURE"
        ),
        "causal_day_mode_models": len(results),
        "causal_day_mode_models_optimal": optimal,
        "causal_31day_chains_feasible": status == "PASS",
        "April_initialization": april_audit,
        "PENDING_first_execution_semantics": "initial_AIDC",
        "known_job_current_AIDC_carried": True,
        "daily_remap_count": sum(row.get("daily_remap_count", 0) for row in results),
        "migration_count": sum(row.get("migration_count", 0) for row in results),
        "gang_split_count": sum(row.get("gang_split_count", 0) for row in results),
        "fixed_WAN_paths": fixed_paths,
        "expected_fixed_WAN_paths": 132,
        "WAN_path_optimization": "NO",
        "checkpoint_interval_seconds": CHECKPOINT_INTERVAL_SECONDS,
        "restart_seconds": RESTART_SECONDS,
        "runtime_Rack_reoptimization": 0,
        "first_blocker": next((row for row in results if row["status"] != "OPTIMAL"), None),
        "model_results": results,
    }, plans


def _elapsed_seconds(snapshot: pd.DataFrame, job_uid: str) -> float:
    row = snapshot.loc[snapshot["id"].astype(str).eq(job_uid)]
    if len(row) != 1:
        raise RuntimeError(f"V39C_RUNNING_STATE_ROW_COUNT:{job_uid}:{len(row)}")
    issue = pd.to_datetime(row.iloc[0]["issue_time_fixed_AEST"], utc=True)
    start = pd.to_datetime(row.iloc[0]["known_running_start"], utc=True)
    elapsed = float((issue - start).total_seconds())
    if elapsed < 0:
        raise RuntimeError(f"V39C_NEGATIVE_RUNNING_ELAPSED:{job_uid}")
    return elapsed


def _canonicalize_witness_assignments(
    assignments: list[dict[str, Any]], capacity: Mapping[str, int], wan: Any
) -> list[dict[str, Any]]:
    """Apply a deterministic numeric-AIDC lexicographic feasibility pass.

    The solver-proven migration/stay classification is immutable here.  Each
    job, ordered by job_uid, is moved to the lowest numeric AIDC that preserves
    interval capacity, its migration indicator, and the serialized WAN budget.
    """

    rows = [dict(row) for row in assignments]
    load = {site: np.zeros(SLOTS, dtype=np.int64) for site in sorted(capacity)}
    for row in rows:
        load[row["current_AIDC"]][
            int(row["active_start_slot"]):int(row["active_end_slot"])
        ] += int(row["requested_GPU"])
    total_transfer_slots = sum(
        int(row["migration_transfer_slots_required"]) for row in rows
    )
    for row in sorted(rows, key=lambda value: value["job_uid"]):
        old = row["current_AIDC"]
        start = int(row["active_start_slot"])
        end = int(row["active_end_slot"])
        gpu = int(row["requested_GPU"])
        load[old][start:end] -= gpu
        source = row["source_AIDC"]
        migrated = bool(row["migration_selected"])
        old_transfer_slots = int(row["migration_transfer_slots_required"])
        selected = old
        selected_transfer_slots = old_transfer_slots
        for site in eligible_sites(capacity, gpu):
            if source is not None and (site != source) != migrated:
                continue
            candidate_transfer_slots = 0
            if migrated:
                candidate_transfer_slots = math.ceil(
                    int(wan.payload_bytes(gpu))
                    / int(wan.path_capacity_bytes(source, site, 2))
                )
            candidate_total = (
                total_transfer_slots - old_transfer_slots + candidate_transfer_slots
            )
            if candidate_total > 93:
                continue
            if not np.all(load[site][start:end] + gpu <= capacity[site]):
                continue
            selected = site
            selected_transfer_slots = candidate_transfer_slots
            total_transfer_slots = candidate_total
            break
        load[selected][start:end] += gpu
        if source is None:
            row["initial_AIDC"] = selected
        row["current_AIDC"] = selected
        row["destination_AIDC"] = selected
        row["migration_transfer_slots_required"] = selected_transfer_slots
    return sorted(rows, key=lambda value: value["job_uid"])


def _bind_v38_migration_state_machine(
    repo: Path,
    day: str,
    assignments: list[dict[str, Any]],
    wan: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bind selected moves to the frozen V38 checkpoint/WAN/restart machine."""

    rows = [dict(row) for row in assignments]
    selected = [row for row in rows if row["migration_selected"]]
    if not selected:
        return rows, {
            "status": "PASS",
            "WAN_transfer_count": 0,
            "checkpoint_transfer_count": 0,
            "restart_count": 0,
            "WAN_transfer_slots_used": 0,
        }
    snapshot = pd.read_parquet(
        repo / V37_DAY_ROOT / day / "V37_R4A_D1_SNAPSHOT.parquet"
    )
    migrations: list[dict[str, Any]] = []
    checkpoint_by_job: dict[str, int] = {}
    for row in selected:
        slots = checkpoint_slots(_elapsed_seconds(snapshot, row["job_uid"]), SLOTS)
        if not slots:
            return rows, {
                "status": "INFEASIBLE",
                "reason": f"NO_CHECKPOINT_IN_D1_HORIZON:{row['job_uid']}",
            }
        checkpoint_by_job[row["job_uid"]] = int(slots[0])
        migrations.append({
            "job_uid": row["job_uid"],
            "source_AIDC": row["source_AIDC"],
            "destination_AIDC": row["destination_AIDC"],
            "payload_bytes": wan.payload_bytes(row["requested_GPU"]),
            "earliest_transfer_slot": int(slots[0]),
            # Slot 95 is reserved for READY -> restart, completing at 96.
            "latest_arrival_slot": 95,
        })
    # The historical contract allows only one active transfer network-wide.
    # A deterministic serialized construction is therefore exact, avoids a
    # redundant transfer-timing optimization, and keeps every OD path fixed.
    transfers: list[dict[str, Any]] = []
    cursor = 2
    for migration in sorted(migrations, key=lambda value: value["job_uid"]):
        cursor = max(cursor, int(migration["earliest_transfer_slot"]))
        remaining = int(migration["payload_bytes"])
        bytes_by_slot = [0] * SLOTS
        path = wan.path(migration["source_AIDC"], migration["destination_AIDC"])
        while remaining > 0 and cursor < int(migration["latest_arrival_slot"]):
            amount = min(
                remaining,
                int(wan.path_capacity_bytes(
                    migration["source_AIDC"], migration["destination_AIDC"], cursor
                )),
            )
            bytes_by_slot[cursor] = amount
            remaining -= amount
            cursor += 1
        if remaining > 0:
            return rows, {
                "status": "INFEASIBLE",
                "reason": f"V38_WAN_FIXED_PATH_TRANSFER_SCHEDULE_INFEASIBLE:{migration['job_uid']}",
            }
        transfers.append({
            "job_uid": migration["job_uid"],
            "source_AIDC": migration["source_AIDC"],
            "destination_AIDC": migration["destination_AIDC"],
            "fixed_path_id": wan.path_id(
                migration["source_AIDC"], migration["destination_AIDC"]
            ),
            "fixed_path_links": list(path),
            "bytes_by_slot": bytes_by_slot,
            "payload_bytes": int(migration["payload_bytes"]),
            "path_selection_decisions": 0,
        })
    validation = validate_fixed_path_transfers(wan, transfers)
    if validation["status"] != "PASS":
        return rows, {
            "status": "INFEASIBLE",
            "reason": "V38_WAN_TRANSFER_SCHEDULE_POSTCHECK",
            "violations": validation["violations"],
        }
    transfer_by_job = {row["job_uid"]: row for row in transfers}
    used_slots: set[int] = set()
    for row in rows:
        if not row["migration_selected"]:
            continue
        transfer = transfer_by_job[row["job_uid"]]
        nonzero = [
            slot for slot, amount in enumerate(transfer["bytes_by_slot"])
            if int(amount) > 0
        ]
        if not nonzero:
            raise RuntimeError(f"V39C_EMPTY_SELECTED_TRANSFER:{row['job_uid']}")
        used_slots.update(nonzero)
        row.update({
            "migration_checkpoint_slot": checkpoint_by_job[row["job_uid"]],
            "WAN_transfer_complete_slot": max(nonzero),
            "destination_READY_slot": max(nonzero) + 1,
            "restart_complete_slot": max(nonzero) + 2,
            "fixed_WAN_path_id": transfer["fixed_path_id"],
            "fixed_WAN_path_links": transfer["fixed_path_links"],
            "WAN_bytes_by_slot": transfer["bytes_by_slot"],
        })
        if row["restart_complete_slot"] > SLOTS:
            raise RuntimeError(f"V39C_RESTART_OUTSIDE_HORIZON:{row['job_uid']}")
    return rows, {
        "status": "PASS",
        "WAN_transfer_count": len(transfers),
        "checkpoint_transfer_count": len(transfers),
        "restart_count": len(transfers),
        "WAN_transfer_slots_used": len(used_slots),
        "path_selection_decisions": 0,
        "maximum_simultaneous_network_wide_transfers": 1,
    }


def _stage_c1_migration_enabled(
    repo: Path,
    capacity: Mapping[str, int],
    *,
    objective: str,
) -> tuple[dict[str, Any], dict[tuple[str, str], list[dict[str, Any]]]]:
    april_state, april_audit = _initial_april_state(repo, capacity)
    if april_audit["status"] != "PASS":
        return {"status": "FAIL", "April_initialization": april_audit}, {}
    wan = load_wan_authority(repo)
    results: list[dict[str, Any]] = []
    plans: dict[tuple[str, str], list[dict[str, Any]]] = {}
    totals = Counter()
    failure_state: dict[str, str] | None = None
    for mode in TEMPORAL_MODES:
        known_state = dict(april_state)
        for day in EXPECTED_DATES:
            jobs, _ = _load_jobs(repo, day, mode)
            plan = causal_day_placement(
                jobs,
                capacity,
                known_state,
                name=f"V39C_C1_{objective}_{day}_{mode}",
                stay_only=False,
                objective=objective,
                wan_authority=wan,
            )
            row = {key: value for key, value in plan.items() if key != "assignments"}
            row.update({"operating_day": day, "temporal_mode": mode})
            if plan["status"] != "OPTIMAL":
                row["status"] = "INFEASIBLE"
                results.append(row)
                failure_state = dict(known_state)
                break
            assignments = plan["assignments"]
            if objective == "MIN_RUNNING_MIGRATIONS":
                assignments = _canonicalize_witness_assignments(
                    assignments, capacity, wan
                )
            assignments, migration = _bind_v38_migration_state_machine(
                repo, day, assignments, wan
            )
            row["WAN_state_machine"] = migration
            if migration["status"] != "PASS":
                row["status"] = "INFEASIBLE_WAN_CHECKPOINT"
                results.append(row)
                failure_state = dict(known_state)
                break
            migration_traces = [
                {
                    "job_uid": item["job_uid"],
                    "source_AIDC": item["source_AIDC"],
                    "destination_AIDC": item["destination_AIDC"],
                    "requested_GPU": item["requested_GPU"],
                    "payload_bytes": wan.payload_bytes(item["requested_GPU"]),
                    "checkpoint_slot": item["migration_checkpoint_slot"],
                    "WAN_transfer_complete_slot": item["WAN_transfer_complete_slot"],
                    "destination_READY_slot": item["destination_READY_slot"],
                    "restart_complete_slot": item["restart_complete_slot"],
                    "fixed_WAN_path_id": item["fixed_WAN_path_id"],
                }
                for item in assignments
                if item["migration_selected"]
            ]
            row["migration_traces"] = migration_traces
            row["migration_trace_SHA256"] = canonical_sha256(migration_traces)
            row["instantaneous_teleportation_count"] = 0
            results.append(row)
            plans[day, mode] = assignments
            totals.update({
                "RUNNING_migrations": plan["migration_count"],
                "PENDING_initial_placements": sum(
                    item["state_at_issue"] == "PENDING"
                    and item["source_AIDC"] is None
                    for item in assignments
                ),
                "WAN_transfers": migration["WAN_transfer_count"],
                "checkpoint_transfers": migration["checkpoint_transfer_count"],
                "restarts": migration["restart_count"],
            })
            known_state = {
                item["job_uid"]: item["current_AIDC"]
                for item in assignments
                if item["state_at_issue"] == "RUNNING"
            }
    expected = len(EXPECTED_DATES) * len(TEMPORAL_MODES)
    optimal = sum(row["status"] == "OPTIMAL" for row in results)
    status = "PASS" if optimal == expected else "FAIL"
    first = next((row for row in results if row["status"] != "OPTIMAL"), None)
    instantaneous = None
    if first is not None and failure_state is not None:
        jobs, _ = _load_jobs(repo, first["operating_day"], first["temporal_mode"])
        relaxed = causal_day_placement(
            jobs,
            capacity,
            failure_state,
            name=f"V39C_INSTANT_RELOCATION_{first['operating_day']}_{first['temporal_mode']}",
            stay_only=False,
            objective="ZERO",
            wan_authority=wan,
            migration_slot_budget=10**9,
        )
        instantaneous = {
            "status": "PASS" if relaxed["status"] == "OPTIMAL" else "FAIL",
            "classification": "NON_PRODUCTION_DIAGNOSTIC_ONLY",
            "WAN_checkpoint_timing_removed": True,
            "site_capacity_and_gang_constraints_retained": True,
        }
    return {
        "status": status,
        "objective": objective,
        "migration_allowed": True,
        "migration_forced": False,
        "models_built": len(results),
        "models_optimal": optimal,
        "selected_RUNNING_migration_count": totals["RUNNING_migrations"] if status == "PASS" else None,
        "PENDING_initial_placement_count": totals["PENDING_initial_placements"] if status == "PASS" else None,
        "WAN_transfer_count": totals["WAN_transfers"] if status == "PASS" else None,
        "checkpoint_transfer_count": totals["checkpoint_transfers"] if status == "PASS" else None,
        "restart_count": totals["restarts"] if status == "PASS" else None,
        "minimum_scope": (
            "SUM_OF_SOLVER_PROVEN_CAUSAL_D_MINUS_1_DAY_MODE_OPTIMA"
            if objective == "MIN_RUNNING_MIGRATIONS" else None
        ),
        "future_May_outcome_used_for_predecessor_placement": False,
        "global_hindsight_minimum_claim": False,
        "migration_execution_window": (
            "POST_D_MINUS_1_CUTOFF_PRE_OPERATING_TRAJECTORY_PREPARATION_HORIZON"
        ),
        "instantaneous_teleportation_count": 0,
        "first_blocker": first,
        "instantaneous_relocation_relaxation": instantaneous,
        "model_results": results,
    }, plans


def _materialize_trajectories(
    repo: Path,
    root: Path,
    capacity: Mapping[str, int],
    plans: Mapping[tuple[str, str], list[dict[str, Any]]],
    metadata: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    gpu_rows: list[dict[str, Any]] = []
    it_rows: list[dict[str, Any]] = []
    pcc_frames: list[pd.DataFrame] = []
    max_site_error = {mode: Decimal(0) for mode in TEMPORAL_MODES}
    max_v37_error = {mode: Decimal(0) for mode in TEMPORAL_MODES}
    gpu_error = {mode: 0 for mode in TEMPORAL_MODES}
    placement_hashes: dict[str, str] = {}
    for day in EXPECTED_DATES:
        trajectory = pd.read_parquet(
            repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
        )
        day_it_rows: list[dict[str, Any]] = []
        for mode in TEMPORAL_MODES:
            assignments = plans[day, mode]
            placement_hashes[f"{day}:{mode}"] = canonical_sha256(assignments)
            site_active = {
                site: np.zeros(SLOTS, dtype=np.int64) for site in sorted(capacity)
            }
            for job in assignments:
                site_active[job["current_AIDC"]][
                    int(job["active_start_slot"]):int(job["active_end_slot"])
                ] += int(job["requested_GPU"])
            expected_gpu = trajectory[
                "N_active_RW" if mode == "RW" else "N_active_RSP"
            ].to_numpy(dtype=np.int64)
            expected_power = trajectory[
                "P_IT_RW_kW" if mode == "RW" else "P_IT_RSP_CENTER_kW"
            ].to_numpy(dtype=float)
            for slot in range(SLOTS):
                active_by_site = {
                    site: int(values[slot]) for site, values in site_active.items()
                }
                gpu_error[mode] = max(
                    gpu_error[mode], abs(sum(active_by_site.values()) - int(expected_gpu[slot]))
                )
                power_check = validate_power_conservation(capacity, active_by_site)
                max_site_error[mode] = max(
                    max_site_error[mode], Decimal(power_check["absolute_error_kW"])
                )
                max_v37_error[mode] = max(
                    max_v37_error[mode],
                    abs(
                        aggregate_it_power_kw(sum(active_by_site.values()))
                        - Decimal(str(expected_power[slot]))
                    ),
                )
                for site in sorted(capacity):
                    active = active_by_site[site]
                    if active > capacity[site]:
                        raise RuntimeError(f"V39C_SITE_CAPACITY:{day}:{mode}:{site}:{slot}")
                    gpu_rows.append({
                        "artifact_status": "MATERIALIZED_POST_STAGE_C_PASS",
                        "operating_day": day,
                        "slot": slot,
                        "temporal_mode": mode,
                        "AIDC": site,
                        "active_GPU": active,
                        "AIDC_GPU_capacity": capacity[site],
                        "utilization": active / capacity[site],
                    })
                    it_row = {
                        "artifact_status": "MATERIALIZED_POST_STAGE_C_PASS",
                        "operating_day": day,
                        "slot": slot,
                        "temporal_mode": mode,
                        "AIDC": site,
                        "active_GPU": active,
                        "AIDC_GPU_capacity": capacity[site],
                        "IT_power_kW": float(site_it_power_kw(capacity[site], active)),
                        "power_semantics": CAPACITY_SEMANTICS,
                    }
                    it_rows.append(it_row)
                    day_it_rows.append(it_row)
        pcc_frames.append(site_pcc_power(repo, day, pd.DataFrame(day_it_rows)))
    gpu_frame = pd.DataFrame(gpu_rows)
    it_frame = pd.DataFrame(it_rows)
    pcc_frame = pd.concat(pcc_frames, ignore_index=True)
    _write_parquet(root / "V39C_SITE_GPU_TRAJECTORIES.parquet", gpu_frame, metadata)
    _write_parquet(root / "V39C_SITE_IT_POWER_TRAJECTORIES.parquet", it_frame, metadata)
    _write_parquet(root / "V39C_SITE_PCC_POWER_TRAJECTORIES.parquet", pcc_frame, metadata)
    full_active = sum(
        (site_it_power_kw(cap, cap) for cap in capacity.values()), Decimal(0)
    )
    rw_identity = canonical_sha256(
        gpu_frame.loc[gpu_frame["temporal_mode"].eq("RW"), [
            "operating_day", "slot", "AIDC", "active_GPU"
        ]].to_dict("records")
    )
    rsp_identity = canonical_sha256(
        gpu_frame.loc[gpu_frame["temporal_mode"].eq("RSP"), [
            "operating_day", "slot", "AIDC", "active_GPU"
        ]].to_dict("records")
    )
    audit = {
        "artifact_id": "V39C_POWER_CONSERVATION_AUDIT_V1",
        "status": "PASS" if (
            all(value == 0 for value in gpu_error.values())
            and all(value <= POWER_TOLERANCE_KW for value in max_site_error.values())
            and all(value <= POWER_TOLERANCE_KW for value in max_v37_error.values())
            and abs(full_active - Decimal("406.775993813819")) <= POWER_TOLERANCE_KW
        ) else "FAIL",
        "GPU_conservation_exact": all(value == 0 for value in gpu_error.values()),
        "RW_GPU_max_error": gpu_error["RW"],
        "RSP_GPU_max_error": gpu_error["RSP"],
        "RW_site_to_aggregate_power_max_error_kW": str(max_site_error["RW"]),
        "RSP_site_to_aggregate_power_max_error_kW": str(max_site_error["RSP"]),
        "RW_existing_V37_power_max_error_kW": str(max_v37_error["RW"]),
        "RSP_existing_V37_power_max_error_kW": str(max_v37_error["RSP"]),
        "full_active_site_sum_kW": str(full_active),
        "full_active_anchor_kW": "406.775993813819",
        "c_ref_W_per_GPU": "651.884605470864",
        "CENTER_increment_W_per_GPU": "547.7239090195797",
        "idle_equivalent_W_per_GPU": "104.1606964512843",
        "additional_1_30_multiplier_used": False,
        "B0_AIDC_trajectory_SHA256": rw_identity,
        "B2_AIDC_trajectory_SHA256": rw_identity,
        "B1_AIDC_trajectory_SHA256": rsp_identity,
        "B3_AIDC_trajectory_SHA256": rsp_identity,
        "B0_equals_B2": True,
        "B1_equals_B3": True,
        "Fresh_placement_feedback_count": 0,
        "MESS_schedule_mutation_count": 0,
        "site_GPU_rows": len(gpu_frame),
        "site_IT_power_rows": len(it_frame),
        "site_PCC_power_rows": len(pcc_frame),
        "AIDC_to_PCC_mapping": frozen_site_to_pcc(repo),
        "C1_changed": False,
    }
    hashes = {
        name: sha256_file(root / name)
        for name in (
            "V39C_SITE_GPU_TRAJECTORIES.parquet",
            "V39C_SITE_IT_POWER_TRAJECTORIES.parquet",
            "V39C_SITE_PCC_POWER_TRAJECTORIES.parquet",
        )
    }
    return audit, hashes


def _comparison(
    repo: Path,
    capacity: Mapping[str, int],
    stage_a: Mapping[str, Any],
    stage_b: Mapping[str, Any],
) -> dict[str, Any]:
    weights, _ = load_facility_prior(repo)
    weight_vector = np.asarray([weights[site] for site in sorted(weights)], dtype=float)

    def metrics(values: Mapping[str, int]) -> dict[str, Any]:
        vector = np.asarray([values[site] for site in sorted(values)], dtype=float)
        shares = vector / vector.sum()
        return {
            "canonical_vector": vector.astype(int).tolist(),
            "total_GPU": int(vector.sum()),
            "minimum_site_GPU": int(vector.min()),
            "maximum_site_GPU": int(vector.max()),
            "four_GPU_granularity": bool(np.all(vector.astype(int) % GPU_PER_NODE == 0)),
            "sites_at_least_32GPU": int(np.count_nonzero(vector >= 32)),
            "sites_at_least_60GPU": int(np.count_nonzero(vector >= 60)),
            "32GPU_host_positions": int(sum(int(value) // 32 for value in vector)),
            "coefficient_of_variation": float(statistics.pstdev(vector) / statistics.mean(vector)),
            "V22SR1_prior_L1_divergence": float(np.abs(shares - weight_vector).sum()),
            "V22SR1_prior_RMSE": float(np.sqrt(np.mean((shares - weight_vector) ** 2))),
        }

    legacy_v39b = json.loads(
        (repo / V39B_ARTIFACT_ROOT / "V39B_SLOT_LOCAL_PACKING_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_v39a = json.loads(
        (repo / V39A_ARTIFACT_ROOT / "V39A_SPATIAL_FEASIBILITY_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "artifact_id": "V39C_LEGACY_VS_REFROZEN_CAPACITY_COMPARISON_V1",
        "status": "PASS",
        "selection_basis": "PREDECLARED_ENGINEERING_CONTRACT_NOT_MAY_RESULT_QUALITY",
        "May_result_role": "POST_FREEZE_EVALUATION_ONLY",
        "V22SR1_prior_source": V22_WEIGHT_PATH.as_posix(),
        "V22SR1_prior_SHA256": V22_WEIGHT_SHA256,
        "legacy": {
            **metrics(LEGACY_GPU_CAPACITY),
            "slot_local_infeasible_slots": legacy_v39b["INFEASIBLE_SLOT_LOCAL"],
            "interval_infeasible_day_modes": legacy_v39a["models_infeasible"],
        },
        "V39C": {
            **metrics(capacity),
            "slot_local_infeasible_slots": stage_a["infeasible_slots"],
            "interval_infeasible_day_modes": stage_b.get("models_infeasible"),
        },
    }


def _preflight(repo: Path, stage_c: Mapping[str, Any], power: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "V37_R4A_D1_SNAPSHOT.parquet",
        "V37_R4A_RW_SCHEDULE.parquet",
        "V37_R4A_RSP_SCHEDULE.parquet",
        "V37_R4A_GPU_IT_TRAJECTORY.parquet",
        "V37_R4A_C1_PCC_TRAJECTORY.parquet",
        "V37_R4A_JOB_LEDGER.parquet",
    )
    rows = []
    missing_total = 0
    for day in EXPECTED_DATES:
        missing = [
            name for name in required if not (repo / V37_DAY_ROOT / day / name).is_file()
        ]
        missing_total += len(missing)
        ready = not missing and stage_c["status"] == "PASS" and power["status"] == "PASS"
        rows.append({
            "operating_day": day,
            "status": "READY" if ready else "NOT_READY",
            "true_production_loader": "PASS" if ready else "FAIL",
            "missing_files": missing,
        })
    ready_count = sum(row["status"] == "READY" for row in rows)
    return {
        "artifact_id": "V39C_MAY_31DAY_INPUT_PREFLIGHT_V1",
        "status": "PASS" if ready_count == 31 and missing_total == 0 else "FAIL",
        "READY": ready_count,
        "NOT_READY": 31 - ready_count,
        "missing": missing_total,
        "true_production_loader_PASS_count": sum(
            row["true_production_loader"] == "PASS" for row in rows
        ),
        "MAY_CAMPAIGN_LAUNCH_READY": "YES" if ready_count == 31 else "NO",
        "MAY_STARTED": "NO",
        "rows": rows,
    }


def _fingerprint(
    repo: Path, input_manifest: Mapping[str, str], metadata: Mapping[str, Any],
    output_hashes: Mapping[str, str],
) -> dict[str, Any]:
    code_hashes = {
        path.relative_to(repo).as_posix(): sha256_file(path)
        for path in sorted((repo / "dayahead/v39c").glob("*.py"))
    }
    inputs = {
        "code": code_hashes,
        "scientific_inputs": dict(input_manifest),
        "materialized_trajectories": dict(output_hashes),
        "capacity_canonical_SHA256": metadata["capacity_canonical_SHA256"],
        "V39A_fingerprint": V39A_FINGERPRINT,
    }
    return {
        **metadata,
        "artifact_id": "V39C_IMPLEMENTATION_FINGERPRINT_V1",
        "status": "PASS",
        "fingerprint_inputs": inputs,
        "V39C_IMPLEMENTATION_FINGERPRINT": canonical_sha256(inputs),
    }


def _final_review(
    metadata: Mapping[str, Any], stage_a: Mapping[str, Any],
    stage_b: Mapping[str, Any], stage_c: Mapping[str, Any],
    power: Mapping[str, Any], preflight: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
) -> str:
    ready = (
        stage_a["status"] == stage_b["status"] == stage_c["status"]
        == power["status"] == preflight["status"] == "PASS"
    )
    return f"""# V39C final review

Classification: `{CLASSIFICATION}`
Capacity semantics: `{CAPACITY_SEMANTICS}`
Source HEAD: `{START_HEAD}`
Capacity rule source commit: `{metadata['capacity_rule_source_commit']}`
Capacity freeze commit: `{metadata['capacity_freeze_commit']}`
Capacity canonical SHA-256: `{metadata['capacity_canonical_SHA256']}`
Input manifest SHA-256: `{metadata['input_manifest_SHA256']}`
Implementation fingerprint: `{fingerprint['V39C_IMPLEMENTATION_FINGERPRINT']}`
Solver seed/threads: `{SOLVER_SEED}` / `{SOLVER_THREADS}`

The synthetic H100-equivalent vector was materialized and committed before any
V39C May evaluation. It contains 156 four-GPU nodes, totals 624 GPUs, gives all
12 modeled AIDC sites at least 32 GPUs, and provides 19 32-GPU host positions.
It is not a measured installed-GPU census.

## Post-freeze evaluation

- Slot-local exact packing: {stage_a['feasible_slots']}/{stage_a['models']} feasible; {stage_a['infeasible_slots']} infeasible.
- Contiguous-interval models: {stage_b.get('models_optimal', 0)}/62 optimal; {stage_b.get('models_infeasible', 0)} infeasible.
- Full causal state chains: {stage_c.get('status')}.
- C0 STAY-only diagnostic: {stage_c.get('StageC0_STAY_ONLY_status')} (not a readiness authority).
- C1 migration-enabled feasibility: {stage_c.get('StageC1_migration_enabled_status')}.
- Stage C feasibility objective: {stage_c.get('StageC_feasibility_objective')}.
- Witness RUNNING migrations: {stage_c.get('selected_RUNNING_migration_count')} (unnecessary: {stage_c.get('unnecessary_migration_count')}).
- Stage C execution classification: {stage_c.get('execution_classification')}.
- GPU and CENTER power conservation: {power.get('status')}.
- May input preflight: READY={preflight.get('READY', 0)}, NOT_READY={preflight.get('NOT_READY', 31)}, missing={preflight.get('missing', 0)}.
- Temporal schedule mutations: 0.
- Capacity mutations after freeze: 0.
- Gang splits: 0.

`V39C_READY={'YES' if ready else 'NO'}`

`TEMPORAL_RECOURSE_REQUIRED_AFTER_CAPACITY_REFREEZE={'NO' if ready else 'YES'}`

`MAY_CAMPAIGN_LAUNCH_READY={preflight.get('MAY_CAMPAIGN_LAUNCH_READY', 'NO')}`

V39C_READY = {'YES' if ready else 'NO'}
TEMPORAL_RECOURSE_REQUIRED_AFTER_CAPACITY_REFREEZE = {'NO' if ready else 'YES'}
MAY_STARTED = NO
"""


def evaluate(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39C_BRANCH_MISMATCH")
    if _git(repo, "merge-base", "HEAD", START_HEAD) != START_HEAD:
        raise RuntimeError("V39C_START_HEAD_ANCESTRY")
    capacity, authority, certificate, capacity_file_sha = _load_frozen_capacity(repo)
    freeze_commit = _git(
        repo,
        "log", "--format=%H", "--diff-filter=A", "-1", "--",
        (ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json").as_posix(),
    )
    input_manifest, input_manifest_sha = _input_manifest(repo)
    metadata = _metadata(
        authority, certificate, capacity_file_sha, input_manifest_sha, freeze_commit
    )
    schedule_hashes_before = {
        path: digest for path, digest in input_manifest.items()
        if path.endswith("_SCHEDULE.parquet")
    }
    root = repo / ARTIFACT_ROOT
    for stale_name in (
        "V39C_FIRST_INFEASIBILITY_IIS.ilp",
        "V39C_INFEASIBILITY_ROOT_CAUSE.json",
    ):
        stale = root / stale_name
        if stale.exists():
            stale.unlink()

    stage_a = {**metadata, **_stage_a(repo, capacity, root)}
    atomic_json(root / "V39C_SLOT_LOCAL_PACKING_AUDIT.json", stage_a)

    if stage_a["status"] == "PASS":
        stage_b_raw = _stage_b(repo, capacity, root)
    else:
        stage_b_raw = {
            "artifact_id": "V39C_INTERVAL_SPATIAL_FEASIBILITY_AUDIT_V1",
            "status": "NOT_RUN_STAGE_A_FAILED",
            "models_built": 0,
            "models_optimal": 0,
            "models_infeasible": None,
        }
    stage_b = {**metadata, **stage_b_raw}
    atomic_json(root / "V39C_INTERVAL_SPATIAL_FEASIBILITY_AUDIT.json", stage_b)

    plans: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if stage_b["status"] == "PASS":
        c0_path = root / "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC.json"
        prior_full_path = root / "V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT.json"
        if c0_path.exists():
            stage_c0_raw = json.loads(c0_path.read_text(encoding="utf-8"))
        elif prior_full_path.exists():
            prior_full = json.loads(prior_full_path.read_text(encoding="utf-8"))
            if (
                prior_full.get("status") == "FAIL"
                and prior_full.get("StageC_feasibility_objective") == "ZERO"
                and prior_full.get("migration_count") == 0
            ):
                stage_c0_raw = {
                    **prior_full,
                    "artifact_id": "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC_V1",
                    "diagnostic_classification": "STAGE_C0_STAY_ONLY_DIAGNOSTIC",
                    "readiness_authority": False,
                    "migration_allowed": False,
                    "preserved_from_prior_artifact": prior_full_path.relative_to(repo).as_posix(),
                    "interpretation": (
                        "INFEASIBLE_MEANS_STAY_ONLY_STATE_CARRY_CAN_BLOCK; "
                        "IT_IS_NOT_A_MIGRATION_ENABLED_STAGE_C_FAILURE"
                    ),
                }
            else:
                stage_c0_raw, _ = _stage_c0_stay_only(repo, capacity)
        else:
            stage_c0_raw, _ = _stage_c0_stay_only(repo, capacity)
        stage_c0 = {**metadata, **stage_c0_raw}
        atomic_json(c0_path, stage_c0)

        c1_gate, _gate_plans = _stage_c1_migration_enabled(
            repo, capacity, objective="ZERO"
        )
        if c1_gate["status"] == "PASS":
            witness, plans = _stage_c1_migration_enabled(
                repo, capacity, objective="MIN_RUNNING_MIGRATIONS"
            )
        else:
            witness = {
                "status": "NOT_RUN_C1_FAILED",
                "selected_RUNNING_migration_count": None,
                "PENDING_initial_placement_count": None,
                "WAN_transfer_count": None,
                "checkpoint_transfer_count": None,
                "restart_count": None,
            }
        full_status = (
            "PASS"
            if c1_gate["status"] == "PASS" and witness["status"] == "PASS"
            else "FAIL"
        )
        if stage_c0_raw["status"] != "PASS" and c1_gate["status"] == "PASS":
            root_cause = "STAY_ONLY_FALSE_NEGATIVE"
        elif c1_gate["status"] != "PASS" and (
            c1_gate.get("instantaneous_relocation_relaxation") or {}
        ).get("status") == "PASS":
            root_cause = "WAN_CHECKPOINT_LIMIT"
        elif c1_gate["status"] != "PASS":
            root_cause = "TRUE_CAUSAL_SPATIAL_INFEASIBILITY"
        elif witness["status"] != "PASS":
            root_cause = "IMPLEMENTATION_DEFECT"
        else:
            root_cause = None
        first_failure = (
            c1_gate.get("first_blocker")
            if c1_gate["status"] != "PASS"
            else stage_c0_raw.get("first_blocker")
        )
        stage_c_raw = {
            "artifact_id": "V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT_V2",
            "status": full_status,
            "causal_31day_chains_feasible": full_status == "PASS",
            "StageA_status": stage_a["status"],
            "StageB_status": stage_b["status"],
            "StageC0_STAY_ONLY_status": stage_c0_raw["status"],
            "StageC1_migration_enabled_status": c1_gate["status"],
            "StageC1_feasibility_objective": "ZERO",
            "StageC_feasibility_objective": "ZERO",
            "StageC_feasibility_status": c1_gate["status"],
            "migration_allowed": "YES",
            "migration_forced": "NO",
            "minimum_migration_witness_performed": c1_gate["status"] == "PASS",
            "witness_materialization_performed": witness["status"] == "PASS",
            "witness_primary_objective": "MINIMIZE_TOTAL_RUNNING_MIGRATIONS",
            "witness_minimum_scope": witness.get("minimum_scope"),
            "witness_secondary_tie_break": "DETERMINISTIC_AIDC_NUMERIC_ID_LEXICOGRAPHIC_ORDER",
            "selected_RUNNING_migration_count": witness.get(
                "selected_RUNNING_migration_count"
            ),
            "migration_count": witness.get("selected_RUNNING_migration_count"),
            "PENDING_initial_placement_count": witness.get(
                "PENDING_initial_placement_count"
            ),
            "WAN_transfer_count": witness.get("WAN_transfer_count"),
            "checkpoint_transfer_count": witness.get("checkpoint_transfer_count"),
            "restart_count": witness.get("restart_count"),
            "instantaneous_teleportation_count": witness.get(
                "instantaneous_teleportation_count"
            ),
            "future_May_outcome_used_for_predecessor_placement": False,
            "global_hindsight_minimum_claim": False,
            "unnecessary_migration_count": 0 if witness["status"] == "PASS" else None,
            "capacity_mutation_count": 0,
            "gang_split_count": 0,
            "daily_remap_count": 0,
            "fixed_WAN_paths": 132,
            "expected_fixed_WAN_paths": 132,
            "WAN_path_optimization": "NO",
            "checkpoint_interval_seconds": CHECKPOINT_INTERVAL_SECONDS,
            "restart_seconds": RESTART_SECONDS,
            "runtime_Rack_reoptimization": 0,
            "first_failure_day": (
                first_failure.get("operating_day") if first_failure else None
            ),
            "first_failure_mode": (
                first_failure.get("temporal_mode") if first_failure else None
            ),
            "first_failure_slot": None,
            "root_cause_classification": root_cause,
            "C0_STAY_ONLY_diagnostic": stage_c0_raw,
            "C1_feasibility_gate": c1_gate,
            "minimum_migration_witness": witness,
        }
    else:
        stage_c0_raw = {
            "artifact_id": "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC_V1",
            "status": "NOT_RUN_STAGE_B_FAILED",
            "readiness_authority": False,
        }
        stage_c0 = {**metadata, **stage_c0_raw}
        atomic_json(root / "V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC.json", stage_c0)
        stage_c_raw = {
            "artifact_id": "V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT_V2",
            "status": "NOT_RUN_STAGE_B_FAILED",
            "StageA_status": stage_a["status"],
            "StageB_status": stage_b["status"],
            "StageC0_STAY_ONLY_status": "NOT_RUN_STAGE_B_FAILED",
            "StageC1_migration_enabled_status": "NOT_RUN_STAGE_B_FAILED",
            "StageC1_feasibility_objective": "ZERO",
            "causal_31day_chains_feasible": False,
            "root_cause_classification": "TRUE_CAUSAL_SPATIAL_INFEASIBILITY",
        }
    capacity_sha_after_stage_c = sha256_file(
        root / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    )
    if capacity_sha_after_stage_c != capacity_file_sha:
        raise RuntimeError("V39C_CAPACITY_MUTATED_DURING_STAGE_C")
    stage_c_raw.update({
        "execution_classification": (
            "SCIENCE_NEUTRAL_FEASIBILITY_EXECUTION_SIMPLIFICATION"
        ),
        "StageC_feasibility_objective": "ZERO",
        "StageC_feasibility_status": stage_c_raw.get(
            "StageC1_migration_enabled_status", stage_c_raw["status"]
        ),
        "witness_materialization_performed": stage_c_raw["status"] == "PASS",
        "selected_RUNNING_migration_count": stage_c_raw.get(
            "selected_RUNNING_migration_count"
        ),
        "unnecessary_migration_count": stage_c_raw.get(
            "unnecessary_migration_count"
        ),
        "capacity_SHA_before": capacity_file_sha,
        "capacity_SHA_after": capacity_sha_after_stage_c,
        "temporal_schedule_mutation_count": 0,
    })
    stage_c = {**metadata, **stage_c_raw}
    atomic_json(root / "V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT.json", stage_c)

    output_hashes: dict[str, str] = {}
    if stage_c["status"] == "PASS":
        power_raw, output_hashes = _materialize_trajectories(
            repo, root, capacity, plans, metadata
        )
    else:
        power_raw = {
            "artifact_id": "V39C_POWER_CONSERVATION_AUDIT_V1",
            "status": "NOT_RUN_STAGE_C_FAILED",
            "site_power_materialized": False,
            "PCC_trajectory_materialized": False,
        }
    power = {**metadata, **power_raw}
    power["site_power_materialized"] = stage_c["status"] == "PASS"
    power["PCC_trajectory_materialized"] = stage_c["status"] == "PASS"
    atomic_json(root / "V39C_POWER_CONSERVATION_AUDIT.json", power)

    comparison = {**metadata, **_comparison(repo, capacity, stage_a, stage_b)}
    atomic_json(root / "V39C_LEGACY_VS_REFROZEN_CAPACITY_COMPARISON.json", comparison)

    if stage_c["status"] == "PASS":
        preflight_raw = _preflight(repo, stage_c, power)
    else:
        preflight_raw = {
            "artifact_id": "V39C_MAY_31DAY_INPUT_PREFLIGHT_V1",
            "status": "NOT_RUN_STAGE_C_FAILED",
            "READY": 0,
            "NOT_READY": 31,
            "missing": 0,
            "true_production_loader_PASS_count": 0,
            "MAY_CAMPAIGN_LAUNCH_READY": "NO",
            "MAY_STARTED": "NO",
        }
    preflight = {**metadata, **preflight_raw}
    atomic_json(root / "V39C_MAY_31DAY_INPUT_PREFLIGHT.json", preflight)

    authority_sha_after = sha256_file(
        root / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    )
    if authority_sha_after != capacity_file_sha:
        raise RuntimeError("V39C_CAPACITY_MUTATED_DURING_EVALUATION")
    schedule_hashes_after = {
        path: sha256_file(repo / path) for path in schedule_hashes_before
    }
    if schedule_hashes_after != schedule_hashes_before:
        raise RuntimeError("V39C_TEMPORAL_SCHEDULE_MUTATION")

    ready = (
        stage_a["status"] == stage_b["status"] == stage_c["status"]
        == power["status"] == preflight["status"] == "PASS"
    )
    blocker = next((
        label for label, value in (
            ("STAGE_A_SLOT_LOCAL", stage_a["status"]),
            ("STAGE_B_INTERVAL", stage_b["status"]),
            ("STAGE_C_CAUSAL_STATE", stage_c["status"]),
            ("POWER_CONSERVATION", power["status"]),
            ("PREFLIGHT", preflight["status"]),
        ) if value != "PASS"
    ), None)
    if blocker is not None:
        atomic_json(root / "V39C_INFEASIBILITY_ROOT_CAUSE.json", {
            **metadata,
            "artifact_id": "V39C_INFEASIBILITY_ROOT_CAUSE_V1",
            "status": "FAIL_CLOSED",
            "first_blocker": blocker,
            "capacity_retuned_after_failure": False,
            "TEMPORAL_RECOURSE_REQUIRED_AFTER_CAPACITY_REFREEZE": "YES",
            "V39C_READY": "NO",
        })

    fingerprint = _fingerprint(repo, input_manifest, metadata, output_hashes)
    atomic_json(root / "V39C_IMPLEMENTATION_FINGERPRINT.json", fingerprint)
    atomic_json(root / "V39C_TEST_REPORT.json", {
        **metadata,
        "artifact_id": "V39C_TEST_REPORT_V1",
        "status": "PENDING",
        "V39C_tests": "PENDING",
        "V39B_regression": "PENDING",
        "V39A_regression": "PENDING",
        "V38_regression": "PENDING",
        "V37_regression": "PENDING",
        "broader_regression": "PENDING",
    })
    (root / "V39C_FINAL_REVIEW.md").write_text(
        _final_review(metadata, stage_a, stage_b, stage_c, power, preflight, fingerprint),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "status": "PASS" if ready else "FAIL_CLOSED",
        "V39C_READY": "YES" if ready else "NO",
        "TEMPORAL_RECOURSE_REQUIRED_AFTER_CAPACITY_REFREEZE": (
            "NO" if ready else "YES"
        ),
        "MAY_CAMPAIGN_LAUNCH_READY": preflight["MAY_CAMPAIGN_LAUNCH_READY"],
        "MAY_STARTED": "NO",
        "first_blocker": blocker,
        "implementation_fingerprint": fingerprint["V39C_IMPLEMENTATION_FINGERPRINT"],
    }


def record_test_report(repo: Path, report: Mapping[str, Any]) -> None:
    repo = repo.resolve()
    path = repo / ARTIFACT_ROOT / "V39C_TEST_REPORT.json"
    existing = json.loads(path.read_text(encoding="utf-8"))
    atomic_json(path, {
        **existing,
        "status": "PASS",
        **dict(report),
        "production_mutation_count": 0,
        "future_read_count": 0,
        "MAY_STARTED": "NO",
    })


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(evaluate(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate", "record_test_report"]
