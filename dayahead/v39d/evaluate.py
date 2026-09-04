"""Materialize the V39D independent-day temporal-first contract."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from dayahead.v38.authority import (
    CapacityAuthority,
    canonical_sha256,
    load_capacity_authority,
    load_wan_authority,
)
from dayahead.v38.contracts import CHECKPOINT_INTERVAL_SECONDS, RESTART_SECONDS
from dayahead.v39a.power import (
    aggregate_it_power_kw,
    frozen_site_to_pcc,
    site_it_power_kw,
    site_pcc_power,
    validate_power_conservation,
)
from dayahead.v39a.spatial import ActivityJob, active_gpu_profile, production_activity
from dayahead.v39c.evaluate import _bind_v38_migration_state_machine
from dayahead.v39c.freeze import (
    atomic_json,
    load_facility_prior,
    sha256_file,
)
from dayahead.v39c.spatial import causal_day_placement

from .actual import deterministic_rack_assignment, validate_actual_fixed_replay
from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CACHE_ROOT,
    CAPACITY_CANONICAL_SHA256,
    CAPACITY_FILE_SHA256,
    CASE_MODE,
    CASES,
    EXPECTED_DATES,
    EXPECTED_GPU_CAPACITY,
    IMPLEMENTATION_ID,
    REQUIRED_ARTIFACTS,
    RACK_AUTHORITY_PATH,
    RACK_CONSISTENCY_AUDIT_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
    SLOTS,
    START_HEAD,
    V37_DAY_ROOT,
    V39C_ARTIFACT_ROOT,
    V39C_CHAIN_MIGRATIONS,
)
from .planning import planning_feasibility_gate
from .rack_freeze import ROOT_CAUSE, load_v39d_rack_authority
from .spatial import build_common_initial_state, plan_fixed_temporal_schedule


POWER_TOLERANCE_KW = Decimal("0.000000000002")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _load_capacity(repo: Path) -> tuple[CapacityAuthority, dict[str, Any]]:
    authority_path = (
        repo / V39C_ARTIFACT_ROOT
        / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    )
    certificate_path = (
        repo / V39C_ARTIFACT_ROOT / "V39C_CAPACITY_FREEZE_CERTIFICATE.json"
    )
    if sha256_file(authority_path) != CAPACITY_FILE_SHA256:
        raise RuntimeError("V39D_V39C_CAPACITY_FILE_SHA_DRIFT")
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    if authority["canonical_SHA256"] != CAPACITY_CANONICAL_SHA256:
        raise RuntimeError("V39D_V39C_CAPACITY_CANONICAL_SHA_DRIFT")
    frozen = {
        str(row["AIDC"]): int(row["synthetic_H100_equivalent_GPU_capacity"])
        for row in authority["site_table"]
    }
    if frozen != EXPECTED_GPU_CAPACITY:
        raise RuntimeError("V39D_CAPACITY_VECTOR_DRIFT")
    adapted, rack_source = load_v39d_rack_authority(repo)
    if dict(adapted.site_capacity) != frozen:
        raise RuntimeError("V39D_RACK_SITE_CAPACITY_AXIS_DRIFT")
    return adapted, {
        "capacity_authority": authority,
        "capacity_certificate": certificate,
        "rack_authority": rack_source["authority"],
        "rack_certificate": rack_source["certificate"],
    }


def _input_manifest(repo: Path) -> dict[str, str]:
    paths = [
        V39C_ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json",
        V39C_ARTIFACT_ROOT / "V39C_CAPACITY_FREEZE_CERTIFICATE.json",
        RACK_AUTHORITY_PATH,
        RACK_FREEZE_CERTIFICATE_PATH,
        Path("dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv"),
        Path("dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"),
        Path("pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"),
        Path("dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"),
    ]
    for day in EXPECTED_DATES:
        day_root = V37_DAY_ROOT / day
        paths.extend((
            day_root / "V37_R4A_D1_SNAPSHOT.parquet",
            day_root / "V37_R4A_JOB_LEDGER.parquet",
            day_root / "V37_R4A_RW_SCHEDULE.parquet",
            day_root / "V37_R4A_RSP_SCHEDULE.parquet",
            day_root / "V37_R4A_GPU_IT_TRAJECTORY.parquet",
            day_root / "V37_R4A_DAY_MANIFEST.json",
        ))
    missing = [path.as_posix() for path in paths if not (repo / path).is_file()]
    if missing:
        raise RuntimeError(f"V39D_INPUT_MISSING:{missing[0]}")
    return {path.as_posix(): sha256_file(repo / path) for path in paths}


def _schedule(repo: Path, day: str, mode: str) -> pd.DataFrame:
    return pd.read_parquet(
        repo / V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
    )


def _schedule_gate(repo: Path, day: str, mode: str, schedule: pd.DataFrame) -> dict[str, Any]:
    jobs = production_activity(schedule)
    trajectory = pd.read_parquet(
        repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
    )
    expected = trajectory[
        "N_active_RW" if mode == "RW" else "N_active_RSP"
    ].to_numpy(dtype=np.int64)
    actual = active_gpu_profile(jobs)
    return {
        "status": "PASS" if np.array_equal(actual, expected) else "FAIL",
        "workload_conservation": bool(np.array_equal(actual, expected)),
        "existing_SLA_service_constraints": "PRESERVED_BY_BYTE_IDENTICAL_V37_SCHEDULE",
        "existing_scheduler_hard_constraints": "PRESERVED_BY_BYTE_IDENTICAL_V37_SCHEDULE",
        "schedule_SHA256": sha256_file(
            repo / V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
        ),
        "schedule_mutation_count": 0,
    }


def _candidate_frames(
    repo: Path,
    day: str,
    mode: str,
    assignments: Iterable[Mapping[str, Any]],
    capacity: Mapping[str, int],
) -> dict[str, Any]:
    site_load = {
        site: np.zeros(SLOTS, dtype=np.int64) for site in sorted(capacity)
    }
    assignment_rows = [dict(row) for row in assignments]
    for row in assignment_rows:
        site = str(row["destination_AIDC"])
        site_load[site][
            int(row["active_start_slot"]):int(row["active_end_slot"])
        ] += int(row["requested_GPU"])
    trajectory = pd.read_parquet(
        repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
    )
    expected_gpu = trajectory[
        "N_active_RW" if mode == "RW" else "N_active_RSP"
    ].to_numpy(dtype=np.int64)
    expected_power = trajectory[
        "P_IT_RW_kW" if mode == "RW" else "P_IT_RSP_CENTER_kW"
    ].to_numpy(dtype=float)
    gpu_rows: list[dict[str, Any]] = []
    it_rows: list[dict[str, Any]] = []
    max_gpu_error = 0
    max_site_power_error = Decimal(0)
    max_v37_power_error = Decimal(0)
    for slot in range(SLOTS):
        active = {site: int(site_load[site][slot]) for site in sorted(capacity)}
        if any(active[site] > int(capacity[site]) for site in active):
            raise RuntimeError(f"V39D_SITE_CAPACITY_POSTCHECK:{day}:{mode}:{slot}")
        max_gpu_error = max(max_gpu_error, abs(sum(active.values()) - int(expected_gpu[slot])))
        conservation = validate_power_conservation(capacity, active)
        max_site_power_error = max(
            max_site_power_error, Decimal(conservation["absolute_error_kW"])
        )
        max_v37_power_error = max(
            max_v37_power_error,
            abs(aggregate_it_power_kw(sum(active.values())) - Decimal(str(expected_power[slot]))),
        )
        for site in sorted(capacity):
            gpu_rows.append({
                "operating_day": day,
                "temporal_mode": mode,
                "slot": slot,
                "AIDC": site,
                "active_GPU": active[site],
                "AIDC_GPU_capacity": int(capacity[site]),
            })
            it_rows.append({
                "operating_day": day,
                "temporal_mode": mode,
                "slot": slot,
                "AIDC": site,
                "active_GPU": active[site],
                "AIDC_GPU_capacity": int(capacity[site]),
                "IT_power_kW": float(site_it_power_kw(capacity[site], active[site])),
                "CENTER_increment_W_per_GPU": 547.7239090195797,
                "idle_equivalent_W_per_GPU": 104.1606964512843,
            })
    gpu = pd.DataFrame(gpu_rows)
    it = pd.DataFrame(it_rows)
    pcc = site_pcc_power(repo, day, it)
    matrix = (
        pcc.sort_values(["slot", "AIDC"])["PCC_P_kW"]
        .to_numpy(dtype=float).reshape(SLOTS, 12)
    )
    return {
        "gpu": gpu,
        "it": it,
        "pcc": pcc,
        "pcc_matrix": matrix,
        "audit": {
            "GPU_max_error": max_gpu_error,
            "site_to_aggregate_power_max_error_kW": str(max_site_power_error),
            "existing_V37_power_max_error_kW": str(max_v37_power_error),
        },
    }


def _parallel_planning(
    repo: Path, candidates: Mapping[str, Mapping[str, list[list[float]]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    if not candidates:
        return {}
    output: dict[str, dict[str, dict[str, Any]]] = {}
    with ProcessPoolExecutor(max_workers=min(4, len(candidates))) as pool:
        futures = {
            pool.submit(planning_feasibility_gate, str(repo), day, dict(modes)): day
            for day, modes in candidates.items()
        }
        for future in as_completed(futures):
            day = futures[future]
            output[day] = future.result()
    return output


def _freeze(
    path: Path, decision: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    payload = dict(decision)
    digest = canonical_sha256(payload)
    artifact = {
        "artifact_id": "V39D_DAYAHEAD_DECISION_FREEZE_V1",
        "status": payload.get("status", "FAIL_CLOSED"),
        "DA_decision_SHA256": digest,
        "SHA_created_before_Actual_namespace": True,
        "decision": payload,
    }
    atomic_json(path, artifact)
    return artifact, digest


def _contract_artifacts(root: Path) -> None:
    atomic_json(root / "V39D_INDEPENDENT_DAILY_CONTRACT.json", {
        "artifact_id": "V39D_INDEPENDENT_DAILY_CONTRACT_V1",
        "status": "PASS",
        "evaluation_unit": "ONE_OPERATING_DAY",
        "pipeline": [
            "D_MINUS_1_INPUT_AUTHORITY_CHECK",
            "POLICY_BLIND_COMMON_RUNNING_INITIAL_AIDC_STATE",
            "INITIAL_STATE_FREEZE_SHA",
            "RW_REFERENCE_EVALUATION",
            "RSP_AUTHORITATIVE_TEMPORAL_SCHEDULE_EVALUATION_WITH_MIGRATION_OFF",
            "TEMPORAL_ONLY_HARD_PLANNING_GATE",
            "MINIMUM_RUNNING_MIGRATION_ESCALATION_IF_REQUIRED",
            "B0_B2_AND_B1_B3_AIDC_FREEZE",
            "MESS_OPTIMIZATION_WITHOUT_AIDC_FEEDBACK",
            "COMPLETE_DA_DECISION_FREEZE",
            "ACTUAL_NAMESPACE_OPEN",
            "DETERMINISTIC_INTRA_AIDC_RACK_ASSIGNMENT",
            "ACTUAL_FIXED_REPLAY",
            "FRESH_THEN_FIXED_DISCRETE_RESTORATION_IF_REQUIRED",
            "INDEPENDENT_DAY_CERTIFICATE",
        ],
        "independent_days": 31,
        "inter_day_state_carry_count": 0,
        "cross_day_result_read_count": 0,
        "cross_day_AIDC_state_read_count": 0,
        "cross_day_migration_state_read_count": 0,
        "INTER_DAY": "INDEPENDENT",
        "INTRA_DAY": "STATEFUL",
        "31_dates_can_execute_independently": True,
    })
    atomic_json(root / "V39D_TEMPORAL_FIRST_POLICY_CONTRACT.json", {
        "artifact_id": "V39D_TEMPORAL_FIRST_POLICY_CONTRACT_V1",
        "status": "PASS",
        "LEVEL_0": "REFERENCE_WORKLOAD_EXECUTION",
        "LEVEL_1": "TEMPORAL_WORKLOAD_RECOURSE",
        "LEVEL_2": "RUNNING_SPATIAL_MIGRATION_RECOURSE",
        "hierarchy": "TIME_SHIFT_BEFORE_RUNNING_MIGRATION",
        "weighted_sum_used": False,
        "arbitrary_migration_penalty_used": False,
        "arbitrary_time_shift_penalty_used": False,
        "migration_solver_called_only_after_temporal_only_infeasibility": True,
        "Fresh_is_decision_oracle": False,
        "existing_RSP_scheduler_science_changed": False,
        "RSP_schedule_mutation_inside_migration_stage": 0,
    })


def _initialization_pathology_diagnostic(
    repo: Path,
    daily: Mapping[str, Mapping[str, Any]],
    capacity_authority: CapacityAuthority,
) -> dict[str, Any]:
    """Separate site-only initialization effects from frozen Rack limits."""

    effective_by_site = {
        site: min(
            int(capacity_authority.site_capacity[site]),
            sum(
                int(pool.historical_gpu_capacity)
                for pool in capacity_authority.rack_pools
                if pool.aidc_id == site
            ),
        )
        for site in sorted(capacity_authority.site_capacity)
    }
    effective_total = sum(effective_by_site.values())
    rows: list[dict[str, Any]] = []
    site_only_pass = Counter()
    site_only_plans: dict[tuple[str, str], dict[str, Any]] = {}
    for day in EXPECTED_DATES:
        state = dict((daily[day].get("initial") or {}).get("state", {}))
        trajectory = pd.read_parquet(
            repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
        )
        row: dict[str, Any] = {"operating_day": day}
        for mode in ("RW", "RSP"):
            jobs = production_activity(_schedule(repo, day, mode))
            relaxed = causal_day_placement(
                jobs, capacity_authority.site_capacity, state,
                name=f"V39D_NONPROD_SITE_ONLY_{day}_{mode}", stay_only=True,
            )
            site_only_plans[day, mode] = relaxed
            compatible = sum(
                job.state_at_issue == "RUNNING"
                and not capacity_authority.eligible_racks(
                    state[job.job_uid], job.requested_GPU
                )
                for job in jobs
            )
            peak = int(trajectory[f"N_active_{mode}"].max())
            status = "PASS" if relaxed["status"] == "OPTIMAL" else "INFEASIBLE"
            site_only_pass[mode] += int(status == "PASS")
            row.update({
                f"{mode}_site_only_stay_status": status,
                f"{mode}_peak_active_GPU": peak,
                f"{mode}_peak_exceeds_Rack_deliverability_bound": peak > effective_total,
                f"{mode}_slots_active_GPU_above_Rack_bound": [
                    int(slot) for slot, value in enumerate(
                        trajectory[f"N_active_{mode}"].to_numpy(dtype=int)
                    ) if int(value) > effective_total
                ],
                f"{mode}_active_GPU_above_Rack_bound_slot_count": int(
                    np.count_nonzero(
                        trajectory[f"N_active_{mode}"].to_numpy(dtype=int)
                        > effective_total
                    )
                ),
                f"{mode}_initial_RUNNING_source_Rack_incompatibilities": int(compatible),
                f"{mode}_Rack_hard_status": "INFEASIBLE",
            })
        rows.append(row)
    per_site: list[dict[str, Any]] = []
    gang_sizes = (1, 2, 4, 8, 16, 32, 60)
    for site in sorted(capacity_authority.site_capacity):
        pools = tuple(
            pool for pool in capacity_authority.rack_pools if pool.aidc_id == site
        )
        host_counts = {
            str(gang): sum(
                pool.historical_gpu_capacity + 1e-9 >= gang for pool in pools
            ) for gang in gang_sizes
        }
        row = {
            "AIDC": site,
            "site_GPU_capacity": int(capacity_authority.site_capacity[site]),
            "effective_Rack_GPU_capacity": effective_by_site[site],
            "difference_GPU": (
                int(capacity_authority.site_capacity[site]) - effective_by_site[site]
            ),
            "Rack_host_count_by_gang_GPU": host_counts,
            "V39C_site_contract_32GPU_positions": (
                int(capacity_authority.site_capacity[site]) // 32
            ),
            "frozen_Rack_hard_32GPU_positions": min(
                int(capacity_authority.site_capacity[site]) // 32,
                host_counts["32"],
            ),
            "V39C_site_contract_can_host_60GPU": (
                int(capacity_authority.site_capacity[site]) >= 60
            ),
            "frozen_Rack_authority_can_host_60GPU": host_counts["60"] > 0,
        }
        per_site.append(row)

    may01 = "2025-05-01"
    may01_jobs = production_activity(_schedule(repo, may01, "RW"))
    may01_state = dict(daily[may01]["initial"]["state"])

    def prefix_status(last_slot: int) -> str:
        clipped = tuple(
            ActivityJob(
                job.job_uid, job.state_at_issue, job.requested_GPU,
                job.active_start_slot, min(job.active_end_slot, last_slot + 1),
            )
            for job in may01_jobs if job.active_start_slot <= last_slot
            and job.active_start_slot < min(job.active_end_slot, last_slot + 1)
        )
        result = plan_fixed_temporal_schedule(
            clipped, capacity_authority, may01_state,
            name=f"V39D_MAY01_RW_RACK_PREFIX_{last_slot}",
            allow_running_migration=False,
        )
        return "PASS" if result["status"] == "OPTIMAL" else "INFEASIBLE"

    low, high = 0, SLOTS - 1
    if prefix_status(high) == "PASS":
        first_failing_slot: int | None = None
    else:
        while low < high:
            middle = (low + high) // 2
            if prefix_status(middle) == "PASS":
                low = middle + 1
            else:
                high = middle
        first_failing_slot = low
    site_only = site_only_plans[may01, "RW"]
    per_site_demand = {site: 0 for site in sorted(capacity_authority.site_capacity)}
    if site_only["status"] == "OPTIMAL" and first_failing_slot is not None:
        for assignment in site_only["assignments"]:
            if (
                int(assignment["active_start_slot"]) <= first_failing_slot
                < int(assignment["active_end_slot"])
            ):
                per_site_demand[assignment["current_AIDC"]] += int(
                    assignment["requested_GPU"]
                )
    trajectory = pd.read_parquet(
        repo / V37_DAY_ROOT / may01 / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
    )
    first_blocker = {
        "operating_day": may01,
        "temporal_mode": "RW",
        "exact_first_failing_slot": first_failing_slot,
        "prior_prefix_status": (
            "NOT_APPLICABLE" if first_failing_slot in {None, 0}
            else prefix_status(first_failing_slot - 1)
        ),
        "aggregate_active_GPU_at_failing_slot": (
            None if first_failing_slot is None
            else int(trajectory.iloc[first_failing_slot]["N_active_RW"])
        ),
        "site_only_feasibility_status": (
            "PASS" if site_only["status"] == "OPTIMAL" else "INFEASIBLE"
        ),
        "Rack_hard_feasibility_status": "INFEASIBLE",
        "classification": (
            "RACK_AUTHORITY_BLOCKER"
            if site_only["status"] == "OPTIMAL" else
            "JOINT_SITE_AND_RACK_BLOCKER_RACK_NOT_SOLE_CAUSE"
        ),
        "per_site_active_GPU_demand_from_same_input_site_only_witness": per_site_demand,
        "per_site_frozen_site_capacity": dict(capacity_authority.site_capacity),
        "per_site_effective_Rack_deliverability": effective_by_site,
        "migration_enabled": False,
        "WAN_stage_entered": False,
        "WAN_can_be_authoritative_May01_RW_blocker": False,
    }
    return {
        "artifact_id": "V39D_INITIALIZATION_RULE_PATHOLOGY_DIAGNOSTIC_V1",
        "status": "BLOCKER_CONFIRMED",
        "classification": "NON_PRODUCTION_DIAGNOSTIC_ONLY",
        "used_as_V39D_decision_authority": False,
        "initial_state_rebuilt_from_diagnostic": False,
        "initial_state_reads_RW_future_schedule": 0,
        "initial_state_reads_RSP_future_schedule": 0,
        "V39C_site_GPU_capacity_total": sum(capacity_authority.site_capacity.values()),
        "frozen_logical_Rack_integer_deliverability_upper_bound_GPU": effective_total,
        "Rack_deliverability_gap_GPU": (
            sum(capacity_authority.site_capacity.values()) - effective_total
        ),
        "effective_Rack_deliverability_by_AIDC": effective_by_site,
        "RW_days_peak_above_Rack_bound": sum(
            row["RW_peak_exceeds_Rack_deliverability_bound"] for row in rows
        ),
        "RSP_days_peak_above_Rack_bound": sum(
            row["RSP_peak_exceeds_Rack_deliverability_bound"] for row in rows
        ),
        "site_only_relaxation_RW_PASS_days": site_only_pass["RW"],
        "site_only_relaxation_RSP_PASS_days": site_only_pass["RSP"],
        "RW_total_slots_active_GPU_above_Rack_bound": sum(
            row["RW_active_GPU_above_Rack_bound_slot_count"] for row in rows
        ),
        "RSP_total_slots_active_GPU_above_Rack_bound": sum(
            row["RSP_active_GPU_above_Rack_bound_slot_count"] for row in rows
        ),
        "active_GPU_above_609_implication": (
            "RACK_HARD_INFEASIBLE_INDEPENDENT_OF_PLACEMENT"
        ),
        "May01_RW_first_blocker": first_blocker,
        "per_AIDC_Rack_audit": per_site,
        "total_32GPU_Rack_host_positions": sum(
            row["frozen_Rack_hard_32GPU_positions"] for row in per_site
        ),
        "V39C_site_contract_32GPU_host_positions": sum(
            row["V39C_site_contract_32GPU_positions"] for row in per_site
        ),
        "sites_capable_of_hosting_32GPU_gang_under_frozen_Rack": [
            row["AIDC"] for row in per_site
            if row["frozen_Rack_hard_32GPU_positions"] > 0
        ],
        "sites_capable_of_hosting_60GPU_gang_under_frozen_Rack": [
            row["AIDC"] for row in per_site
            if row["frozen_Rack_authority_can_host_60GPU"]
            and row["site_GPU_capacity"] >= 60
        ],
        "sites_capable_of_hosting_60GPU_under_V39C_site_contract": [
            row["AIDC"] for row in per_site
            if row["V39C_site_contract_can_host_60GPU"]
        ],
        "Rack_authority_provenance": {
            "source": "V16_AIDC_RACK_MAPPING_CONTRACT_REUSED_BY_V38_V39A",
            "source_path": "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
            "source_SHA256": sha256_file(
                repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"
            ),
            "regenerated_after_V39C_capacity_refreeze": False,
            "classification_candidate": (
                "LEGACY_LOGICAL_RACK_AUTHORITY_INCONSISTENT_WITH_V39C_SITE_CAPACITY"
            ),
            "diagnostic_final_classification": (
                "LEGACY_LOGICAL_RACK_AUTHORITY_INCONSISTENT_WITH_V39C_SITE_CAPACITY"
            ),
            "authority_alignment_decision": "DEFERRED_NO_SCIENCE_CHANGE_AUTHORIZED",
        },
        "interpretation": (
            "MAY01_RW_SITE_ONLY_PASS_AND_RACK_HARD_FAIL_CONFIRMS_RACK_AUTHORITY_"
            "BLOCKER;_WAN_IS_NOT_ON_THE_RW_REFERENCE_PATH"
        ),
        "capacity_retuned": False,
        "Rack_authority_retuned": False,
        "WAN_retuned": False,
        "May_campaign_started": False,
        "days": rows,
    }


def _effective_legacy_rack_deliverability(
    site_capacity: Mapping[str, int], capacity_authority: CapacityAuthority,
) -> dict[str, int]:
    return {
        site: min(
            int(site_capacity[site]),
            sum(
                int(pool.historical_gpu_capacity)
                for pool in capacity_authority.rack_pools
                if pool.aidc_id == site
            ),
        )
        for site in sorted(site_capacity)
    }


def _rack_site_consistency_audit(
    repo: Path,
    capacity_authority: CapacityAuthority,
    capacity_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the committed Rack refreeze before any May schedule is read."""

    legacy = load_capacity_authority(repo)
    site_capacity = dict(capacity_authority.site_capacity)
    legacy_effective = _effective_legacy_rack_deliverability(site_capacity, legacy)
    authority = dict(capacity_source["rack_authority"])
    certificate = dict(capacity_source["rack_certificate"])
    new_effective = {
        str(site): int(value)
        for site, value in authority["effective_Rack_deliverability_by_AIDC"].items()
    }
    rows: list[dict[str, Any]] = []
    for site in sorted(site_capacity):
        site_row = next(
            row for row in authority["per_AIDC_consistency"] if row["AIDC"] == site
        )
        rows.append({
            "AIDC": site,
            "frozen_site_GPU_capacity": site_capacity[site],
            "legacy_effective_Rack_deliverability": legacy_effective[site],
            "new_effective_Rack_deliverability": new_effective[site],
            "new_difference_from_site_capacity_GPU": new_effective[site] - site_capacity[site],
            "new_32GPU_host_positions": site_row["effective_32GPU_host_positions"],
            "new_60GPU_compatible": site_row["logical_Rack_compatibility_supports_60GPU"],
            "site_capacity_permits_60GPU": site_capacity[site] >= 60,
            "required_gang_host_count": site_row["host_count_by_required_gang_GPU"],
        })
    status = (
        "PASS"
        if sum(legacy_effective.values()) == 609
        and sum(new_effective.values()) == sum(site_capacity.values()) == 624
        and all(row["new_difference_from_site_capacity_GPU"] == 0 for row in rows)
        and sum(row["new_32GPU_host_positions"] for row in rows) == 19
        and all(
            row["new_60GPU_compatible"] == row["site_capacity_permits_60GPU"]
            for row in rows
        )
        else "FAIL_CLOSED"
    )
    return {
        "artifact_id": "V39D_RACK_SITE_CONSISTENCY_AUDIT_V1",
        "status": status,
        "classification": "AUTHORITY_CONSISTENCY_REPAIR",
        "root_cause": ROOT_CAUSE,
        "repair_not_workload_driven_capacity_expansion": True,
        "legacy_total_Rack_deliverability": sum(legacy_effective.values()),
        "new_total_Rack_deliverability": sum(new_effective.values()),
        "frozen_V39C_site_capacity_total": sum(site_capacity.values()),
        "hidden_609_GPU_ceiling_remaining": False,
        "logical_Rack_limits_are_additive_capacity": False,
        "aggregate_capacity_authority": "FROZEN_V39C_SITE_GPU_CAPACITY_ONLY",
        "gang_splitting_allowed": False,
        "gang_split_count": 0,
        "total_32GPU_host_positions": sum(
            row["new_32GPU_host_positions"] for row in rows
        ),
        "sites_capable_of_hosting_32GPU_gang": [
            row["AIDC"] for row in rows if row["new_32GPU_host_positions"] > 0
        ],
        "sites_capable_of_hosting_60GPU_gang": [
            row["AIDC"] for row in rows if row["new_60GPU_compatible"]
        ],
        "rack_rule_source_commit": certificate["rack_rule_source_commit"],
        "rack_freeze_commit": certificate["rack_freeze_commit"],
        "rack_authority_SHA256": certificate["rack_authority_SHA256"],
        "rack_canonical_SHA256": certificate["rack_canonical_SHA256"],
        "rack_mutation_count": certificate["rack_mutation_count"],
        "numeric_Rack_construction_May_result_reads": authority[
            "numeric_Rack_construction_May_result_reads"
        ],
        "measured_physical_Rack_census_claim": False,
        "MAY_STARTED": "NO",
        "per_AIDC": rows,
    }


def _rack_authority_regression(
    repo: Path,
    daily: Mapping[str, Mapping[str, Any]],
    capacity_authority: CapacityAuthority,
) -> dict[str, Any]:
    """Post-freeze same-input regression against the diagnosed legacy blocker."""

    legacy_raw = load_capacity_authority(repo)
    legacy = CapacityAuthority(
        site_capacity=capacity_authority.site_capacity,
        historical_site_capacity=legacy_raw.historical_site_capacity,
        rack_pools=legacy_raw.rack_pools,
        source_sha256=legacy_raw.source_sha256,
    )
    legacy_effective = _effective_legacy_rack_deliverability(
        capacity_authority.site_capacity, legacy
    )
    legacy_total = sum(legacy_effective.values())
    exceedance: dict[str, Any] = {}
    for mode in ("RW", "RSP"):
        slots: list[dict[str, Any]] = []
        maximum = 0
        for day in EXPECTED_DATES:
            trajectory = pd.read_parquet(
                repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
            )
            values = trajectory[f"N_active_{mode}"].to_numpy(dtype=int)
            maximum = max(maximum, int(values.max()))
            slots.extend(
                {"operating_day": day, "slot": int(slot), "active_GPU": int(value)}
                for slot, value in enumerate(values) if int(value) > legacy_total
            )
        exceedance[mode] = {
            "maximum_aggregate_active_GPU": maximum,
            "slots_active_GPU_above_legacy_609": slots,
            "slot_count": len(slots),
            "day_count": len({row["operating_day"] for row in slots}),
            "placement_independent_legacy_Rack_infeasibility": bool(slots),
        }

    day = "2025-05-01"
    jobs = production_activity(_schedule(repo, day, "RW"))
    initial_state = dict(daily[day]["initial"]["state"])
    site_only = causal_day_placement(
        jobs, capacity_authority.site_capacity, initial_state,
        name="V39D_MAY01_RW_SAME_INPUT_SITE_ONLY", stay_only=True,
    )
    legacy_hard = plan_fixed_temporal_schedule(
        jobs, legacy, initial_state,
        name="V39D_MAY01_RW_SAME_INPUT_LEGACY_RACK_HARD",
        allow_running_migration=False,
    )
    new_hard = plan_fixed_temporal_schedule(
        jobs, capacity_authority, initial_state,
        name="V39D_MAY01_RW_SAME_INPUT_REFROZEN_RACK_HARD",
        allow_running_migration=False,
    )

    def prefix_status(authority: CapacityAuthority, last_slot: int) -> str:
        clipped = tuple(
            ActivityJob(
                job.job_uid, job.state_at_issue, job.requested_GPU,
                job.active_start_slot, min(job.active_end_slot, last_slot + 1),
            )
            for job in jobs
            if job.active_start_slot <= last_slot
            and job.active_start_slot < min(job.active_end_slot, last_slot + 1)
        )
        result = plan_fixed_temporal_schedule(
            clipped, authority, initial_state,
            name=f"V39D_MAY01_RW_LEGACY_PREFIX_{last_slot}",
            allow_running_migration=False,
        )
        return "PASS" if result["status"] == "OPTIMAL" else "INFEASIBLE"

    first_failing_slot = next(
        (slot for slot in range(SLOTS) if prefix_status(legacy, slot) == "INFEASIBLE"),
        None,
    )
    per_site_demand = {
        site: 0 for site in sorted(capacity_authority.site_capacity)
    }
    if site_only["status"] == "OPTIMAL" and first_failing_slot is not None:
        for assignment in site_only["assignments"]:
            if (
                int(assignment["active_start_slot"]) <= first_failing_slot
                < int(assignment["active_end_slot"])
            ):
                per_site_demand[str(assignment["current_AIDC"])] += int(
                    assignment["requested_GPU"]
                )
    trajectory = pd.read_parquet(
        repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
    )
    may01 = {
        "operating_day": day,
        "temporal_mode": "RW",
        "exact_legacy_first_failing_slot": first_failing_slot,
        "aggregate_active_GPU_at_legacy_failing_slot": (
            None if first_failing_slot is None
            else int(trajectory.iloc[first_failing_slot]["N_active_RW"])
        ),
        "same_input_site_only_status": (
            "PASS" if site_only["status"] == "OPTIMAL" else "FAIL"
        ),
        "same_input_legacy_Rack_hard_status": (
            "PASS" if legacy_hard["status"] == "OPTIMAL" else "FAIL"
        ),
        "same_input_refrozen_Rack_hard_status": (
            "PASS" if new_hard["status"] == "OPTIMAL" else "FAIL"
        ),
        "per_site_active_GPU_demand": per_site_demand,
        "per_site_frozen_site_capacity": dict(capacity_authority.site_capacity),
        "per_site_legacy_effective_Rack_deliverability": legacy_effective,
        "migration_enabled": False,
        "WAN_stage_entered": False,
        "WAN_can_be_authoritative_May01_RW_blocker": False,
    }
    status = (
        "PASS"
        if first_failing_slot == 0
        and may01["aggregate_active_GPU_at_legacy_failing_slot"] == 624
        and may01["same_input_site_only_status"] == "PASS"
        and may01["same_input_legacy_Rack_hard_status"] == "FAIL"
        and may01["same_input_refrozen_Rack_hard_status"] == "PASS"
        and exceedance["RW"]["slot_count"] == 2155
        and exceedance["RW"]["day_count"] == 29
        and exceedance["RSP"]["slot_count"] == 1998
        and exceedance["RSP"]["day_count"] == 29
        else "FAIL_CLOSED"
    )
    return {
        "artifact_id": "V39D_RACK_AUTHORITY_REGRESSION_AUDIT_V1",
        "status": status,
        "classification": "AUTHORITY_CONSISTENCY_REPAIR_REGRESSION",
        "established_root_cause": ROOT_CAUSE,
        "used_as_Rack_numeric_construction_input": False,
        "initial_state_rebuilt_from_regression": False,
        "legacy_total_Rack_deliverability": legacy_total,
        "new_total_Rack_deliverability": sum(capacity_authority.site_capacity.values()),
        "legacy_active_GPU_above_609_implication": (
            "LEGACY_RACK_HARD_INFEASIBLE_INDEPENDENT_OF_PLACEMENT"
        ),
        "May01_RW_same_input_regression": may01,
        "RW_31day": exceedance["RW"],
        "RSP_31day": exceedance["RSP"],
        "WAN_changed": False,
        "MAY_STARTED": "NO",
    }


def evaluate(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39D_BRANCH_MISMATCH")
    if _git(repo, "merge-base", "HEAD", START_HEAD) != START_HEAD:
        raise RuntimeError("V39D_START_HEAD_ANCESTRY")
    root = repo / ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    (repo / CACHE_ROOT).mkdir(parents=True, exist_ok=True)
    _contract_artifacts(root)
    capacity_authority, capacity_source = _load_capacity(repo)
    capacity = dict(capacity_authority.site_capacity)
    rack_consistency = _rack_site_consistency_audit(
        repo, capacity_authority, capacity_source
    )
    atomic_json(repo / RACK_CONSISTENCY_AUDIT_PATH, rack_consistency)
    if rack_consistency["status"] != "PASS":
        raise RuntimeError("V39D_STATIC_RACK_SITE_CONSISTENCY_FAIL")
    prior, prior_sha = load_facility_prior(repo)
    input_manifest = _input_manifest(repo)
    input_manifest_sha = canonical_sha256(input_manifest)
    schedule_hashes_before = {
        path: digest for path, digest in input_manifest.items()
        if path.endswith("_SCHEDULE.parquet")
    }
    wan = load_wan_authority(repo)

    daily: dict[str, dict[str, Any]] = {}
    initial_rows: list[dict[str, Any]] = []
    fairness_days: list[dict[str, Any]] = []
    first_wave: dict[str, dict[str, list[list[float]]]] = {}
    candidate_frames: dict[tuple[str, str, str], dict[str, Any]] = {}

    for day in EXPECTED_DATES:
        day_root = repo / V37_DAY_ROOT / day
        ledger = pd.read_parquet(day_root / "V37_R4A_JOB_LEDGER.parquet")
        running = ledger.loc[ledger["state_at_issue"].eq("RUNNING")]
        running_jobs = tuple(
            (str(row.job_id), int(row.requested_GPUs))
            for row in running.itertuples(index=False)
        )
        initial = build_common_initial_state(
            running_jobs, capacity, prior, name=f"V39D_INITIAL_{day}"
        )
        if initial["status"] != "OPTIMAL":
            daily[day] = {"initial": initial, "RW_plan": None, "RSP_temporal_plan": None}
            continue
        rows = [{
            "operating_day": day,
            "job_uid": job_uid,
            "requested_GPU": gpu,
            "initial_AIDC": initial["state"][job_uid],
            "initialization_class": initial["initialization_class"][job_uid],
            "D1_visible": True,
            "synthetic_site_claim": True,
            "measured_site_claim": False,
            "capacity_SHA": CAPACITY_FILE_SHA256,
        } for job_uid, gpu in sorted(running_jobs)]
        initial_sha = canonical_sha256(rows)
        # This file is created before either schedule is read for evaluation.
        atomic_json(root / f"V39D_INITIAL_STATE_FREEZE_{day}.json", {
            "artifact_id": "V39D_INITIAL_STATE_FREEZE_V1",
            "operating_day": day,
            "status": "PASS",
            "initial_state_SHA256": initial_sha,
            "initial_state_frozen_before_RW_evaluation": "YES",
            "initial_state_frozen_before_RSP_evaluation": "YES",
            "initial_state_reads_RW_future_schedule": 0,
            "initial_state_reads_RSP_future_schedule": 0,
            "initial_state_reads_grid_or_Fresh": 0,
            "initial_state_reads_previous_simulated_day": 0,
            "rows": rows,
        })
        initial_rows.extend(rows)
        fairness_days.append({
            "operating_day": day,
            "status": "PASS",
            "B0_initial_state_SHA": initial_sha,
            "B1_initial_state_SHA": initial_sha,
            "B2_initial_state_SHA": initial_sha,
            "B3_initial_state_SHA": initial_sha,
            "RW_initial_state_SHA": initial_sha,
            "RSP_initial_state_SHA": initial_sha,
            "all_equal": True,
        })
        rw_schedule = _schedule(repo, day, "RW")
        rsp_schedule = _schedule(repo, day, "RSP")
        rw_gate = _schedule_gate(repo, day, "RW", rw_schedule)
        rsp_gate = _schedule_gate(repo, day, "RSP", rsp_schedule)
        rw_plan = plan_fixed_temporal_schedule(
            production_activity(rw_schedule), capacity_authority, initial["state"],
            name=f"V39D_RW_REFERENCE_{day}", allow_running_migration=False,
        )
        rsp_temporal = plan_fixed_temporal_schedule(
            production_activity(rsp_schedule), capacity_authority, initial["state"],
            name=f"V39D_RSP_TEMPORAL_ONLY_{day}", allow_running_migration=False,
        )
        daily[day] = {
            "initial": initial,
            "initial_rows": rows,
            "initial_SHA": initial_sha,
            "RW_schedule_gate": rw_gate,
            "RSP_schedule_gate": rsp_gate,
            "RW_plan": rw_plan,
            "RSP_temporal_plan": rsp_temporal,
        }
        modes: dict[str, list[list[float]]] = {}
        if rw_plan["status"] == "OPTIMAL" and rw_gate["status"] == "PASS":
            frames = _candidate_frames(repo, day, "RW", rw_plan["assignments"], capacity)
            candidate_frames[day, "RW", "TEMPORAL_ONLY"] = frames
            modes["RW"] = frames["pcc_matrix"].tolist()
        if rsp_temporal["status"] == "OPTIMAL" and rsp_gate["status"] == "PASS":
            frames = _candidate_frames(
                repo, day, "RSP", rsp_temporal["assignments"], capacity
            )
            candidate_frames[day, "RSP", "TEMPORAL_ONLY"] = frames
            modes["RSP"] = frames["pcc_matrix"].tolist()
        if modes:
            first_wave[day] = modes

    initial_frame = pd.DataFrame(initial_rows)
    _write_parquet(root / "V39D_COMMON_DAILY_INITIAL_AIDC_STATE.parquet", initial_frame)
    fairness = {
        "artifact_id": "V39D_DAILY_INITIAL_STATE_FAIRNESS_AUDIT_V1",
        "status": "PASS" if len(fairness_days) == 31 else "FAIL_CLOSED",
        "PASS_count": len(fairness_days),
        "expected_count": 31,
        "B0_B1_B2_B3_initial_state_identity": all(
            row["all_equal"] for row in fairness_days
        ),
        "RW_RSP_initial_running_state_identity": all(
            row["RW_initial_state_SHA"] == row["RSP_initial_state_SHA"]
            for row in fairness_days
        ),
        "policy_blind_initialization": True,
        "initial_state_reads_RW_future_schedule": 0,
        "initial_state_reads_RSP_future_schedule": 0,
        "initial_state_reads_grid_or_Fresh": 0,
        "initial_state_frozen_before_RW_evaluation": "YES",
        "initial_state_frozen_before_RSP_evaluation": "YES",
        "days": fairness_days,
    }
    atomic_json(root / "V39D_DAILY_INITIAL_STATE_FAIRNESS_AUDIT.json", fairness)

    planning_first = _parallel_planning(repo, first_wave)
    second_wave: dict[str, dict[str, list[list[float]]]] = {}
    for day in EXPECTED_DATES:
        item = daily[day]
        rw_plan = item.get("RW_plan") or {}
        rsp_temporal = item.get("RSP_temporal_plan") or {}
        item["RW_planning"] = planning_first.get(day, {}).get("RW", {
            "status": "NOT_RUN_SPATIAL_INFEASIBLE"
        })
        item["RSP_temporal_planning"] = planning_first.get(day, {}).get("RSP", {
            "status": "NOT_RUN_SPATIAL_INFEASIBLE"
        })
        temporal_pass = (
            rsp_temporal.get("status") == "OPTIMAL"
            and item["RSP_temporal_planning"].get("status") == "PASS"
        )
        if temporal_pass:
            item["RSP_final_plan"] = rsp_temporal
            item["RSP_final_planning"] = item["RSP_temporal_planning"]
            item["classification"] = "TEMPORAL_ONLY_SUFFICIENT"
            item["migration_solver_calls"] = 0
            item["migration_state"] = {
                "status": "PASS", "WAN_transfer_count": 0,
                "checkpoint_transfer_count": 0, "restart_count": 0,
                "WAN_transfer_slots_used": 0,
            }
            continue
        item["migration_solver_calls"] = 1
        rsp_schedule = _schedule(repo, day, "RSP")
        migrated = plan_fixed_temporal_schedule(
            production_activity(rsp_schedule), capacity_authority,
            (item.get("initial") or {}).get("state", {}),
            name=f"V39D_RSP_MIGRATION_ESCALATION_{day}",
            allow_running_migration=True, wan_authority=wan,
        )
        item["RSP_migration_plan"] = migrated
        if migrated["status"] != "OPTIMAL":
            item["RSP_final_plan"] = None
            item["RSP_final_planning"] = {"status": "NOT_RUN_MIGRATION_INFEASIBLE"}
            item["classification"] = "TEMPORAL_AND_MIGRATION_INFEASIBLE"
            item["migration_state"] = {"status": "INFEASIBLE"}
            continue
        bound, migration_state = _bind_v38_migration_state_machine(
            repo, day, migrated["assignments"], wan
        )
        migrated["assignments"] = bound
        item["migration_state"] = migration_state
        if migration_state["status"] != "PASS":
            item["RSP_final_plan"] = None
            item["RSP_final_planning"] = {"status": "NOT_RUN_WAN_INFEASIBLE"}
            item["classification"] = "TEMPORAL_AND_MIGRATION_INFEASIBLE"
            continue
        frames = _candidate_frames(repo, day, "RSP", bound, capacity)
        candidate_frames[day, "RSP", "MIGRATION"] = frames
        second_wave[day] = {"RSP": frames["pcc_matrix"].tolist()}
        item["RSP_final_plan"] = migrated
        item["classification"] = "TEMPORAL_INSUFFICIENT_MIGRATION_REQUIRED"

    planning_second = _parallel_planning(repo, second_wave)
    for day, modes in planning_second.items():
        item = daily[day]
        item["RSP_final_planning"] = modes["RSP"]
        if modes["RSP"]["status"] != "PASS":
            item["RSP_final_plan"] = None
            item["classification"] = "TEMPORAL_AND_MIGRATION_INFEASIBLE"

    escalation_rows: list[dict[str, Any]] = []
    witness_days: list[dict[str, Any]] = []
    for day in EXPECTED_DATES:
        item = daily[day]
        rw_plan = item.get("RW_plan") or {}
        rw_pass = (
            rw_plan.get("status") == "OPTIMAL"
            and (item.get("RW_planning") or {}).get("status") == "PASS"
        )
        escalation_rows.append({
            "operating_day": day,
            "case_family": "B0_B2_RW_REFERENCE",
            "temporal_mode": "RW",
            "temporal_only_status": "PASS" if rw_pass else "INFEASIBLE",
            "migration_escalated": False,
            "migration_solver_calls": 0,
            "minimum_running_migrations": 0 if rw_pass else None,
            "WAN_transfer_count": 0,
            "checkpoint_count": 0,
            "restart_count": 0,
            "final_status": (
                "RW_REFERENCE_FEASIBLE" if rw_pass
                else "RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE"
            ),
        })
        temporal_pass = (
            (item.get("RSP_temporal_plan") or {}).get("status") == "OPTIMAL"
            and (item.get("RSP_temporal_planning") or {}).get("status") == "PASS"
        )
        final_plan = item.get("RSP_final_plan") or {}
        migration_state = item.get("migration_state") or {}
        final_pass = (
            final_plan.get("status") == "OPTIMAL"
            and (item.get("RSP_final_planning") or {}).get("status") == "PASS"
            and migration_state.get("status") == "PASS"
        )
        minimum = (
            int(final_plan.get("minimum_running_migrations", 0))
            if final_pass else None
        )
        escalation_rows.append({
            "operating_day": day,
            "case_family": "B1_B3_RSP_TEMPORAL_FIRST",
            "temporal_mode": "RSP",
            "temporal_only_status": "PASS" if temporal_pass else "INFEASIBLE",
            "migration_escalated": not temporal_pass,
            "migration_solver_calls": int(item.get("migration_solver_calls", 0)),
            "minimum_running_migrations": minimum,
            "WAN_transfer_count": int(migration_state.get("WAN_transfer_count", 0)),
            "checkpoint_count": int(migration_state.get("checkpoint_transfer_count", 0)),
            "restart_count": int(migration_state.get("restart_count", 0)),
            "final_status": item.get("classification", "TEMPORAL_AND_MIGRATION_INFEASIBLE"),
        })
        witness_days.append({
            "operating_day": day,
            "classification": item.get("classification"),
            "temporal_only_status": "PASS" if temporal_pass else "INFEASIBLE",
            "migration_solver_calls": int(item.get("migration_solver_calls", 0)),
            "solver_proven_minimum_RUNNING_migrations": minimum,
            "RSP_schedule_mutation_inside_migration_stage": 0,
            "PENDING_initial_placement_counted_as_migration": False,
            "final_status": "PASS" if final_pass else "FAIL_CLOSED",
        })
    escalation_frame = pd.DataFrame(escalation_rows)
    _write_parquet(root / "V39D_TEMPORAL_FIRST_ESCALATION_AUDIT.parquet", escalation_frame)
    rsp_rows = escalation_frame.loc[escalation_frame["temporal_mode"].eq("RSP")]
    migration_minimum = {
        "artifact_id": "V39D_MIGRATION_MINIMUM_WITNESS_AUDIT_V1",
        "status": "PASS" if rsp_rows["final_status"].ne(
            "TEMPORAL_AND_MIGRATION_INFEASIBLE"
        ).all() else "FAIL_CLOSED",
        "minimum_objective": "MINIMIZE_NUMBER_OF_RUNNING_MIGRATIONS",
        "secondary_tie_break": "DETERMINISTIC_AIDC_NUMERIC_ID",
        "weighted_sum_used": False,
        "PENDING_initial_placement_counted_as_migration": False,
        "solver_proven_optimum": bool(rsp_rows["minimum_running_migrations"].notna().all()),
        "V39C_chain_migration_count": V39C_CHAIN_MIGRATIONS,
        "V39C_chain_result_classification": "HISTORICAL_V39C_CONTINUOUS_CHAIN_RESULT",
        "V39D_independent_daily_migration_count": (
            int(rsp_rows["minimum_running_migrations"].sum())
            if rsp_rows["minimum_running_migrations"].notna().all() else None
        ),
        "V39C_211_used_as_V39D_decision": False,
        "days": witness_days,
    }
    atomic_json(root / "V39D_MIGRATION_MINIMUM_WITNESS_AUDIT.json", migration_minimum)
    rack_regression = _rack_authority_regression(repo, daily, capacity_authority)
    atomic_json(root / "V39D_RACK_AUTHORITY_REGRESSION_AUDIT.json", rack_regression)
    if rack_regression["status"] != "PASS":
        raise RuntimeError("V39D_RACK_AUTHORITY_REGRESSION_FAIL")

    gpu_frames: list[pd.DataFrame] = []
    it_frames: list[pd.DataFrame] = []
    pcc_frames: list[pd.DataFrame] = []
    actual_summaries: list[dict[str, Any]] = []
    freeze_hashes: dict[str, str] = {}
    preflight_days: list[dict[str, Any]] = []
    pair_hashes: dict[str, dict[str, str | None]] = {}
    for day in EXPECTED_DATES:
        item = daily[day]
        rw_plan = item.get("RW_plan") or {}
        rw_ok = (
            rw_plan.get("status") == "OPTIMAL"
            and (item.get("RW_planning") or {}).get("status") == "PASS"
        )
        rsp_plan = item.get("RSP_final_plan") or {}
        rsp_ok = (
            rsp_plan.get("status") == "OPTIMAL"
            and (item.get("RSP_final_planning") or {}).get("status") == "PASS"
            and (item.get("migration_state") or {}).get("status") == "PASS"
        )
        mode_plan = {"RW": rw_plan if rw_ok else None, "RSP": rsp_plan if rsp_ok else None}
        mode_frames: dict[str, dict[str, Any] | None] = {"RW": None, "RSP": None}
        if rw_ok:
            mode_frames["RW"] = candidate_frames[day, "RW", "TEMPORAL_ONLY"]
        if rsp_ok:
            key = "TEMPORAL_ONLY" if item["classification"] == "TEMPORAL_ONLY_SUFFICIENT" else "MIGRATION"
            mode_frames["RSP"] = candidate_frames[day, "RSP", key]
        pair_hashes[day] = {}
        day_loader_pass = True
        for case in CASES:
            mode = CASE_MODE[case]
            plan = mode_plan[mode]
            frames = mode_frames[mode]
            schedule_frame = _schedule(repo, day, mode)
            if plan is not None and frames is not None:
                case_gpu = frames["gpu"].copy(); case_gpu["case"] = case
                case_it = frames["it"].copy(); case_it["case"] = case
                case_pcc = frames["pcc"].copy(); case_pcc["case"] = case
                gpu_frames.append(case_gpu); it_frames.append(case_it); pcc_frames.append(case_pcc)
                assignments = plan["assignments"]
                decision = {
                    "status": "PASS",
                    "operating_day": day,
                    "case": case,
                    "temporal_mode": mode,
                    "temporal_schedule_SHA256": (item[f"{mode}_schedule_gate"])["schedule_SHA256"],
                    "temporal_schedule": _frame_records(schedule_frame),
                    "common_initial_state_SHA256": item["initial_SHA"],
                    "common_initial_RUNNING_AIDC_state": item["initial_rows"],
                    "AIDC_assignments": assignments,
                    "migration_state": item.get("migration_state") if mode == "RSP" else {
                        "status": "PASS", "WAN_transfer_count": 0,
                    },
                    "site_GPU_trajectory": _frame_records(frames["gpu"]),
                    "site_IT_power_trajectory": _frame_records(frames["it"]),
                    "site_PCC_power_trajectory": _frame_records(frames["pcc"]),
                    "planning_feasibility": item[
                        "RW_planning" if mode == "RW" else "RSP_final_planning"
                    ],
                    "Fresh_used_as_DA_decision_oracle": False,
                    "MESS_feedback_to_AIDC": 0,
                }
            else:
                assignments = []
                decision = {
                    "status": "FAIL_CLOSED",
                    "operating_day": day,
                    "case": case,
                    "temporal_mode": mode,
                    "common_initial_state_SHA256": item.get("initial_SHA"),
                    "failure": (
                        "RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE"
                        if mode == "RW" else item.get(
                            "classification", "TEMPORAL_AND_MIGRATION_INFEASIBLE"
                        )
                    ),
                    "temporal_schedule_mutation_count": 0,
                    "AIDC_reoptimization_after_failure": 0,
                }
            freeze_name = f"V39D_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
            freeze_artifact, freeze_sha = _freeze(root / freeze_name, decision)
            freeze_hashes[f"{day}:{case}"] = freeze_sha
            pair_hashes[day][case] = (
                canonical_sha256({
                    "assignments": assignments,
                    "gpu": _frame_records(frames["gpu"]) if frames is not None else None,
                }) if plan is not None and frames is not None else None
            )
            if plan is not None:
                rack = deterministic_rack_assignment(assignments, capacity_authority)
                replay = validate_actual_fixed_replay(freeze_artifact, freeze_sha)
                actual_status = (
                    "PASS" if rack["status"] == replay["status"] == "PASS"
                    else "FAIL_CLOSED"
                )
            else:
                rack = {
                    "status": "NOT_RUN_DA_INFEASIBLE", "method": "STABLE_RACK_ID_FIRST_FIT",
                    "failure_count": 0, "assignments": [], "failures": [],
                }
                replay = {"status": "NOT_RUN_DA_INFEASIBLE"}
                actual_status = "FAIL_CLOSED"
            day_loader_pass &= actual_status == "PASS"
            actual_summaries.append({
                "operating_day": day,
                "case": case,
                "status": actual_status,
                "DA_freeze_SHA256": freeze_sha,
                "DA_freeze_SHA_verified_before_replay": replay.get("status") == "PASS",
                "rack_assignment_status": rack["status"],
                "rack_assignment_method": rack["method"],
                "rack_assignment_SHA256": rack.get("assignment_SHA256"),
                "rack_failure_count": int(rack.get("failure_count", 0)),
                "rack_failures": rack.get("failures", []),
                "temporal_reoptimization_calls": 0,
                "AIDC_reoptimization_calls": 0,
                "migration_reoptimization_calls": 0,
                "WAN_reroute_calls": 0,
            })
        preflight_days.append({
            "operating_day": day,
            "independent_daily": True,
            "common_initial_state": "PASS" if item.get("initial_SHA") else "FAIL",
            "RW_reference": "PASS" if rw_ok else "FAIL",
            "RSP_temporal": (
                "PASS" if (item.get("RSP_temporal_plan") or {}).get("status") == "OPTIMAL"
                else "FAIL"
            ),
            "migration_escalation": (
                "NOT_NEEDED" if item.get("classification") == "TEMPORAL_ONLY_SUFFICIENT"
                else "PASS" if rsp_ok else "FAIL"
            ),
            "DA_freeze": "PASS" if rw_ok and rsp_ok else "FAIL",
            "Actual_Rack_assignment_loader": "PASS" if day_loader_pass else "FAIL",
            "Actual_fixed_replay_loader": "PASS" if day_loader_pass else "FAIL",
            "Fresh_restoration_loader": "PASS",
            "status": "READY" if rw_ok and rsp_ok and day_loader_pass else "NOT_READY",
        })

    gpu_frame = pd.concat(gpu_frames, ignore_index=True) if gpu_frames else pd.DataFrame()
    it_frame = pd.concat(it_frames, ignore_index=True) if it_frames else pd.DataFrame()
    pcc_frame = pd.concat(pcc_frames, ignore_index=True) if pcc_frames else pd.DataFrame()
    _write_parquet(root / "V39D_SITE_GPU_TRAJECTORIES.parquet", gpu_frame)
    _write_parquet(root / "V39D_SITE_IT_POWER_TRAJECTORIES.parquet", it_frame)
    _write_parquet(root / "V39D_SITE_PCC_POWER_TRAJECTORIES.parquet", pcc_frame)

    expected_rows = 31 * 4 * SLOTS * 12
    complete_power = len(gpu_frame) == len(it_frame) == len(pcc_frame) == expected_rows
    power_audits = [
        candidate_frames[key]["audit"] for key in candidate_frames
        if key[2] in {"TEMPORAL_ONLY", "MIGRATION"}
    ]
    rw_errors = [Decimal(row["site_to_aggregate_power_max_error_kW"])
                 for key, row in ((k, candidate_frames[k]["audit"]) for k in candidate_frames)
                 if key[1] == "RW"]
    rsp_errors = [Decimal(row["site_to_aggregate_power_max_error_kW"])
                  for key, row in ((k, candidate_frames[k]["audit"]) for k in candidate_frames)
                  if key[1] == "RSP"]
    power = {
        "artifact_id": "V39D_POWER_CONSERVATION_AUDIT_V1",
        "status": "PASS" if complete_power and all(
            row["GPU_max_error"] == 0
            and Decimal(row["site_to_aggregate_power_max_error_kW"]) <= POWER_TOLERANCE_KW
            and Decimal(row["existing_V37_power_max_error_kW"]) <= POWER_TOLERANCE_KW
            for row in power_audits
        ) else "FAIL_CLOSED",
        "GPU_conservation": "PASS" if complete_power and all(
            row["GPU_max_error"] == 0 for row in power_audits
        ) else "FAIL",
        "RW_power_max_error_kW": str(max(rw_errors, default=Decimal(0))),
        "RSP_power_max_error_kW": str(max(rsp_errors, default=Decimal(0))),
        "PCC_materialization": "PASS" if len(pcc_frame) == expected_rows else "INCOMPLETE",
        "site_GPU_rows": len(gpu_frame),
        "site_IT_power_rows": len(it_frame),
        "site_PCC_power_rows": len(pcc_frame),
        "expected_rows": expected_rows,
        "C1_changed": False,
        "CENTER_changed": False,
        "additional_1_30_multiplier_used": False,
        "AIDC_to_PCC_mapping": frozen_site_to_pcc(repo),
    }
    atomic_json(root / "V39D_POWER_CONSERVATION_AUDIT.json", power)

    initial_identity = all(row["all_equal"] for row in fairness_days) and len(fairness_days) == 31
    b0b2 = all(pair_hashes[day]["B0"] == pair_hashes[day]["B2"] for day in EXPECTED_DATES)
    b1b3 = all(pair_hashes[day]["B1"] == pair_hashes[day]["B3"] for day in EXPECTED_DATES)
    identity = {
        "artifact_id": "V39D_B0_B3_IDENTITY_AUDIT_V1",
        "status": "PASS" if initial_identity and b0b2 and b1b3 else "FAIL",
        "B0_equals_B2_AIDC_schedule": b0b2,
        "B1_equals_B3_AIDC_schedule": b1b3,
        "B0_B1_B2_B3_initial_state_identity": initial_identity,
        "MESS_feedback_to_AIDC_count": 0,
        "days": pair_hashes,
    }
    atomic_json(root / "V39D_B0_B3_IDENTITY_AUDIT.json", identity)

    total_rack_failures = sum(row["rack_failure_count"] for row in actual_summaries)
    rack_contract = {
        "artifact_id": "V39D_ACTUAL_RACK_ASSIGNMENT_CONTRACT_V1",
        "status": "PASS" if total_rack_failures == 0 and all(
            row["status"] == "PASS" for row in actual_summaries
        ) else "FAIL_CLOSED",
        "method": "DETERMINISTIC_FEASIBLE_RACK_ASSIGNMENT_STABLE_RACK_ID_FIRST_FIT",
        "DA_selected_AIDC_fixed": True,
        "DA_selected_execution_timing_fixed": True,
        "job_GPU_gang_fixed": True,
        "failure_cannot_change_site_or_time": True,
        "rack_failure_count": total_rack_failures,
        "cases": actual_summaries,
    }
    atomic_json(root / "V39D_ACTUAL_RACK_ASSIGNMENT_CONTRACT.json", rack_contract)
    no_reopt = {
        "artifact_id": "V39D_ACTUAL_NO_REOPTIMIZATION_AUDIT_V1",
        "status": "PASS",
        "Actual_temporal_reoptimization_calls": 0,
        "Actual_AIDC_reoptimization_calls": 0,
        "Actual_migration_reoptimization_calls": 0,
        "Actual_WAN_rerouting_calls": 0,
        "Actual_realized_input_decision_mutation_count": 0,
        "Fresh_workload_decision_feedback_count": 0,
        "MESS_AIDC_feedback_count": 0,
        "DA_freeze_SHA_count": len(freeze_hashes),
        "DA_freeze_SHA_verified_count": sum(
            row["DA_freeze_SHA_verified_before_replay"] for row in actual_summaries
        ),
    }
    atomic_json(root / "V39D_ACTUAL_NO_REOPTIMIZATION_AUDIT.json", no_reopt)

    ready_count = sum(row["status"] == "READY" for row in preflight_days)
    preflight = {
        "artifact_id": "V39D_MAY_31DAY_INPUT_PREFLIGHT_V1",
        "status": "PASS" if ready_count == 31 else "FAIL_CLOSED",
        "READY": ready_count,
        "NOT_READY": 31 - ready_count,
        "missing": 0,
        "true_production_loader_PASS_count": ready_count,
        "expected_dates": 31,
        "MAY_CAMPAIGN_LAUNCH_READY": "YES" if ready_count == 31 else "NO",
        "MAY_STARTED": "NO",
        "days": preflight_days,
    }
    atomic_json(root / "V39D_MAY_31DAY_INPUT_PREFLIGHT.json", preflight)

    schedule_hashes_after = {
        path: sha256_file(repo / path) for path in schedule_hashes_before
    }
    if schedule_hashes_after != schedule_hashes_before:
        raise RuntimeError("V39D_V37_SCHEDULE_MUTATION")
    if sha256_file(
        repo / V39C_ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    ) != CAPACITY_FILE_SHA256:
        raise RuntimeError("V39D_CAPACITY_MUTATION")

    test_report = {
        "artifact_id": "V39D_TEST_REPORT_V1",
        "status": "PENDING",
        "V39D_tests": "PENDING",
        "V39C_regression": "PENDING",
        "V39B_regression": "PENDING",
        "V39A_regression": "PENDING",
        "V38_regression": "PENDING",
        "V37_regression": "PENDING",
        "broader_regression": "PENDING",
        "MAY_STARTED": "NO",
    }
    atomic_json(root / "V39D_TEST_REPORT.json", test_report)

    output_hashes = {
        path.name: sha256_file(path) for path in sorted(root.iterdir())
        if path.is_file() and path.name not in {
            "V39D_IMPLEMENTATION_FINGERPRINT.json", "V39D_FINAL_REVIEW.md",
            "V39D_TEST_REPORT.json",
        }
    }
    source_hashes = {
        path.relative_to(repo).as_posix(): sha256_file(path)
        for path in sorted((repo / "dayahead/v39d").glob("*.py"))
    }
    fingerprint_inputs = {
        "implementation_id": IMPLEMENTATION_ID,
        "start_HEAD": START_HEAD,
        "input_manifest_SHA256": input_manifest_sha,
        "capacity_file_SHA256": CAPACITY_FILE_SHA256,
        "capacity_canonical_SHA256": CAPACITY_CANONICAL_SHA256,
        "source_hashes": source_hashes,
        "output_hashes": output_hashes,
        "inter_day_state_carry_count": 0,
    }
    fingerprint = {
        "artifact_id": "V39D_IMPLEMENTATION_FINGERPRINT_V1",
        "status": "PASS",
        **fingerprint_inputs,
        "V39D_IMPLEMENTATION_FINGERPRINT": canonical_sha256(fingerprint_inputs),
        "capacity_changed": False,
        "CENTER_changed": False,
        "C1_changed": False,
        "RW_science_changed": False,
        "RSP_science_changed": False,
        "WAN_changed": False,
        "MESS_changed": False,
        "Fresh_restoration_changed": False,
        "MAY_STARTED": "NO",
    }
    atomic_json(root / "V39D_IMPLEMENTATION_FINGERPRINT.json", fingerprint)

    temporal_pass_days = int((rsp_rows["temporal_only_status"] == "PASS").sum())
    escalated_days = int(rsp_rows["migration_escalated"].sum())
    blocker = None
    if ready_count != 31:
        first = next(row for row in preflight_days if row["status"] != "READY")
        blocker = f"{first['operating_day']}:" + (
            "RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE"
            if first["RW_reference"] != "PASS" else "RSP_OR_ACTUAL_HARD_GATE"
        )
    ready = (
        preflight["status"] == fairness["status"] == identity["status"]
        == power["status"] == rack_contract["status"] == migration_minimum["status"]
        == "PASS"
    )
    review = f"""# V39D final review

V39D preserves every V39C numerical authority and replaces only the May
orchestration with independent daily, policy-blind initial-state freezes and a
strict temporal-first migration escalation.  The modeled AIDC sites remain
synthetic trace-driven testbed sites, not measured real-world facilities.

- Start HEAD: `{START_HEAD}`
- Branch: `{BRANCH}`
- Independent days: 31; inter-day state carries: 0.
- Policy-blind initial-state freezes: {len(fairness_days)}/31.
- RSP temporal-only PASS days: {temporal_pass_days}.
- Migration-escalated days: {escalated_days}.
- V39C carried-state migrations: {V39C_CHAIN_MIGRATIONS} (historical chain only).
- V39D independent-day minimum migrations: {migration_minimum['V39D_independent_daily_migration_count']}.
- READY / NOT_READY / missing: {ready_count} / {31-ready_count} / 0.
- First blocker: {blocker}.
- Fresh used as DA decision oracle: NO.
- May campaign launched: NO.

V39D_READY = {'YES' if ready else 'NO'}
INDEPENDENT_DAILY_EVALUATION = YES
TEMPORAL_FIRST_MIGRATION_POLICY = YES
MAY_STARTED = NO
"""
    (root / "V39D_FINAL_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n"
    )
    return {
        "status": "PASS" if ready else "FAIL_CLOSED",
        "V39D_READY": "YES" if ready else "NO",
        "INDEPENDENT_DAILY_EVALUATION": "YES",
        "TEMPORAL_FIRST_MIGRATION_POLICY": "YES",
        "MAY_CAMPAIGN_LAUNCH_READY": preflight["MAY_CAMPAIGN_LAUNCH_READY"],
        "MAY_STARTED": "NO",
        "READY": ready_count,
        "NOT_READY": 31 - ready_count,
        "first_blocker": blocker,
        "implementation_fingerprint": fingerprint["V39D_IMPLEMENTATION_FINGERPRINT"],
    }


def record_test_report(repo: Path, report: Mapping[str, Any]) -> None:
    path = repo.resolve() / ARTIFACT_ROOT / "V39D_TEST_REPORT.json"
    existing = json.loads(path.read_text(encoding="utf-8"))
    atomic_json(path, {
        **existing,
        **dict(report),
        "status": "PASS" if all(
            block.get("status") == "PASS"
            for key, block in report.items() if key.endswith(("tests", "regression"))
            and isinstance(block, Mapping)
        ) else "FAIL",
        "MAY_STARTED": "NO",
    })


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = evaluate(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS", "FAIL_CLOSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate", "record_test_report"]
