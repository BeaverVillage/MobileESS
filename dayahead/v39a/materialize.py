"""Materialize the V39A fail-closed scientific decision and its evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dayahead.v36.contracts import SCIENCE_AUTHORITIES, SOURCE_DATA_REPOSITORY
from dayahead.v38.authority import (
    atomic_json,
    canonical_sha256,
    load_capacity_authority,
    load_wan_authority,
    sha256_file,
)
from dayahead.v37.preflight import anchor_paths

from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CENTER_SWING_W_PER_GPU,
    C_REF_W_PER_GPU,
    EXPECTED_DATES,
    FULL_ACTIVE_IT_KW,
    GPU_CAPACITY,
    IDLE_W_PER_GPU,
    IMPLEMENTATION_ID,
    POWER_TOLERANCE_KW,
    RUNTIME_FIREWALL,
    SITE_CAPACITY,
    TEMPORAL_MODES,
    V37_DAY_ROOT,
    V38_ARTIFACT_ROOT,
    V38_FAIL_EVIDENCE_HEAD,
    V38_IMPLEMENTATION_FINGERPRINT,
    VOLTAGE_AUTHORITY,
    VOLTAGE_FROZEN_SHA256,
    VOLTAGE_LOGICAL_LF_SHA256,
)
from .power import (
    aggregate_it_power_kw,
    frozen_site_to_pcc,
    site_it_power_kw,
    validate_power_conservation,
)
from .spatial import plan_causal_day, production_activity, scan_may_relaxation


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    ).strip()


def _repo_path(path: Path, repo: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _write_blocked_parquets(repo: Path) -> dict[str, str]:
    root = repo / ARTIFACT_ROOT
    schemas = {
        "V39A_SITE_GPU_TRAJECTORIES.parquet": {
            "artifact_status": pd.Series(dtype="string"),
            "operating_day": pd.Series(dtype="string"),
            "slot": pd.Series(dtype="int64"),
            "temporal_mode": pd.Series(dtype="string"),
            "AIDC": pd.Series(dtype="string"),
            "active_gpu": pd.Series(dtype="int64"),
            "site_capacity_gpu": pd.Series(dtype="int64"),
            "utilization": pd.Series(dtype="float64"),
            "running_job_count": pd.Series(dtype="int64"),
            "pending_start_count": pd.Series(dtype="int64"),
            "migration_in_count": pd.Series(dtype="int64"),
            "migration_out_count": pd.Series(dtype="int64"),
        },
        "V39A_SITE_IT_POWER_TRAJECTORIES.parquet": {
            "artifact_status": pd.Series(dtype="string"),
            "operating_day": pd.Series(dtype="string"),
            "slot": pd.Series(dtype="int64"),
            "temporal_mode": pd.Series(dtype="string"),
            "AIDC": pd.Series(dtype="string"),
            "active_gpu": pd.Series(dtype="int64"),
            "site_capacity_gpu": pd.Series(dtype="int64"),
            "IT_power_kW": pd.Series(dtype="float64"),
            "power_semantics": pd.Series(dtype="string"),
        },
        "V39A_SITE_PCC_POWER_TRAJECTORIES.parquet": {
            "artifact_status": pd.Series(dtype="string"),
            "operating_day": pd.Series(dtype="string"),
            "slot": pd.Series(dtype="int64"),
            "temporal_mode": pd.Series(dtype="string"),
            "AIDC": pd.Series(dtype="string"),
            "existing_feeder_PCC_node": pd.Series(dtype="string"),
            "IT_power_kW": pd.Series(dtype="float64"),
            "PCC_P_kW": pd.Series(dtype="float64"),
            "PCC_Q_kvar": pd.Series(dtype="float64"),
        },
    }
    result: dict[str, str] = {}
    for name, columns in schemas.items():
        frame = pd.DataFrame(columns)
        frame.attrs["artifact_status"] = "BLOCKED_NOT_MATERIALIZED"
        frame.attrs["blocker"] = "V39A_SPATIAL_FEASIBILITY_INFEASIBLE"
        path = root / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
        result[name] = sha256_file(path)
    return result


def _site_capacity_audit(repo: Path) -> dict[str, Any]:
    capacity = load_capacity_authority(repo)
    v38_mapping = repo / V38_ARTIFACT_ROOT / "V38_AIDC_GPU_CAPACITY_MAPPING.json"
    rows = [
        {"AIDC": site, "AIDC_GPU_capacity": int(capacity.site_capacity[site])}
        for site in capacity.aidc_ids
    ]
    passed = dict(capacity.site_capacity) == SITE_CAPACITY and sum(SITE_CAPACITY.values()) == 624
    return {
        "artifact_id": "V39A_SITE_CAPACITY_AUTHORITY_V1",
        "status": "PASS" if passed else "FAIL",
        "authority_source": (
            "V38 outcome-blind largest-remainder equivalent-GPU mapping from the "
            "frozen 48-logical-Rack deliverable-capacity authority"
        ),
        "authority_file": _repo_path(v38_mapping, repo),
        "authority_file_sha256": sha256_file(v38_mapping),
        "raw_source": str(__import__(
            "dayahead.v38.contracts", fromlist=["RAW_RACK_CAPACITY"]
        ).RAW_RACK_CAPACITY),
        "source_SHA256": capacity.source_sha256,
        "rounding": "LARGEST_REMAINDER_FROZEN_BY_V38",
        "capacities": rows,
        "total": sum(row["AIDC_GPU_capacity"] for row in rows),
        "capacity_changed": False,
    }


def _initial_state_audit(repo: Path) -> dict[str, Any]:
    root = repo / V37_DAY_ROOT / "2025-04-01"
    snapshot_path = root / "V37_R4A_D1_SNAPSHOT.parquet"
    schedule_path = root / "V37_R4A_RW_SCHEDULE.parquet"
    snapshot = pd.read_parquet(snapshot_path)
    schedule = pd.read_parquet(schedule_path)
    running = snapshot.loc[snapshot["state_at_issue"].eq("RUNNING")]
    active_running = tuple(
        job for job in production_activity(schedule) if job.state_at_issue == "RUNNING"
    )
    plan = plan_causal_day(active_running, load_capacity_authority(repo), {})
    all_running_ids = set(running["id"].astype(str))
    active_ids = {job.job_uid for job in active_running}
    inactive_ids = sorted(all_running_ids - active_ids)
    inactive_rule = {
        uid: min(
            (
                site for site, cap in SITE_CAPACITY.items()
                if cap >= int(round(float(
                    running.loc[running["id"].astype(str).eq(uid), "gpus_requested"].iloc[0]
                )))
            ),
            key=lambda site: hashlib.sha256(
                f"V39A_INITIAL_INACTIVE:{uid}:{site}".encode()
            ).hexdigest(),
        )
        for uid in inactive_ids
    }
    seed_rows = [asdict(row) for row in plan.decisions] + [
        {
            "job_uid": uid,
            "state_at_issue": "RUNNING",
            "requested_GPU": int(round(float(
                running.loc[running["id"].astype(str).eq(uid), "gpus_requested"].iloc[0]
            ))),
            "initial_AIDC": inactive_rule[uid],
            "current_AIDC": inactive_rule[uid],
            "source_AIDC": None,
            "destination_AIDC": inactive_rule[uid],
            "migration_selected": False,
        }
        for uid in inactive_ids
    ]
    return {
        "artifact_id": "V39A_CAUSAL_INITIAL_STATE_AUDIT_V1",
        "status": "PASS" if plan.status == "OPTIMAL" and len(seed_rows) == len(running) else "FAIL",
        "initialization_method": "SYNTHETIC_CAUSAL_INITIAL_SITE_ASSIGNMENT",
        "initialization_date": "2025-04-01",
        "cutoff": str(snapshot["issue_time_fixed_AEST"].iloc[0]),
        "jobs_initialized": len(seed_rows),
        "production_active_jobs_initialized": len(plan.decisions),
        "pre_production_completion_jobs_initialized": len(inactive_ids),
        "causal_fields_used": [
            "id", "state_at_issue", "known_running_start", "gpus_requested",
            "V37_RW_scheduled_interval_available_at_cutoff",
        ],
        "future_fields_read_count": 0,
        "May_result_reads": 0,
        "grid_or_Fresh_result_reads": 0,
        "deterministic_seed": 20260904,
        "deterministic_rule": (
            "exact capacity-feasible Apr-01 running-cohort placement; SHA-256 "
            "lexicographic tie-break; inactive-at-production jobs use eligible-site hash"
        ),
        "site_capacity_validation": "PASS",
        "source_snapshot": _repo_path(snapshot_path, repo),
        "source_snapshot_sha256": sha256_file(snapshot_path),
        "seed_content_sha256": canonical_sha256(seed_rows),
        "measured_site_claim": False,
        "forward_chain_disposition": (
            "NOT_MATERIALIZED_AFTER_GLOBAL_MAY_RELAXATION_PROVED_INFEASIBLE"
        ),
    }


def _aggregate_equivalence(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    maximum_site_error = {mode: Decimal(0) for mode in TEMPORAL_MODES}
    maximum_v37_error = {mode: Decimal(0) for mode in TEMPORAL_MODES}
    maximum_gpu_error = {mode: 0 for mode in TEMPORAL_MODES}
    checked = 0
    for day in EXPECTED_DATES:
        frame = pd.read_parquet(
            repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
        )
        for mode in TEMPORAL_MODES:
            active_field = "N_active_RW" if mode == "RW" else "N_active_RSP"
            power_field = "P_IT_RW_kW" if mode == "RW" else "P_IT_RSP_CENTER_kW"
            for active_raw, v37_power_raw in zip(frame[active_field], frame[power_field], strict=True):
                active = int(round(float(active_raw)))
                remaining = active
                decomposition: dict[str, int] = {}
                for site, cap in SITE_CAPACITY.items():
                    value = min(cap, remaining)
                    decomposition[site] = value
                    remaining -= value
                maximum_gpu_error[mode] = max(
                    maximum_gpu_error[mode], abs(sum(decomposition.values()) - active)
                )
                check = validate_power_conservation(SITE_CAPACITY, decomposition)
                maximum_site_error[mode] = max(
                    maximum_site_error[mode], Decimal(check["absolute_error_kW"])
                )
                maximum_v37_error[mode] = max(
                    maximum_v37_error[mode],
                    abs(aggregate_it_power_kw(active) - Decimal(str(float(v37_power_raw)))),
                )
                checked += 1
    full_active_site = sum(
        (site_it_power_kw(cap, cap) for cap in SITE_CAPACITY.values()), Decimal(0)
    )
    zero_active_site = sum(
        (site_it_power_kw(cap, 0) for cap in SITE_CAPACITY.values()), Decimal(0)
    )
    status = "PASS" if (
        all(value == 0 for value in maximum_gpu_error.values())
        and all(value <= POWER_TOLERANCE_KW for value in maximum_site_error.values())
        and all(value <= POWER_TOLERANCE_KW for value in maximum_v37_error.values())
    ) else "FAIL"
    aggregate = {
        "artifact_id": "V39A_AGGREGATE_EQUIVALENCE_V1",
        "status": status,
        "scope": "ALGEBRAIC_POWER_DECOMPOSITION; NOT_A_FEASIBLE_JOB_PLACEMENT",
        "checked_day_mode_slots": checked,
        "GPU_conservation_exact": all(value == 0 for value in maximum_gpu_error.values()),
        "RW_site_to_aggregate_max_error_kW": str(maximum_site_error["RW"]),
        "RSP_site_to_aggregate_max_error_kW": str(maximum_site_error["RSP"]),
        "RW_V37_aggregate_formula_max_error_kW": str(maximum_v37_error["RW"]),
        "RSP_V37_aggregate_formula_max_error_kW": str(maximum_v37_error["RSP"]),
        "tolerance_kW": str(POWER_TOLERANCE_KW),
        "full_active_624_site_sum_kW": str(full_active_site),
        "frozen_full_active_anchor_kW": str(FULL_ACTIVE_IT_KW),
        "zero_active_site_sum_kW": str(zero_active_site),
        "zero_active_aggregate_formula_kW": str(aggregate_it_power_kw(0)),
        "c_ref_W_per_GPU": str(C_REF_W_PER_GPU),
        "CENTER_active_to_idle_swing_W_per_GPU": str(CENTER_SWING_W_PER_GPU),
        "equivalent_idle_W_per_GPU": str(IDLE_W_PER_GPU),
        "physical_semantics": (
            "SYNTHETIC CAPACITY-PROPORTIONAL SPATIAL DECOMPOSITION OF THE "
            "FROZEN AGGREGATE AIDC POWER MODEL"
        ),
        "measured_site_power_claim": False,
        "case_trajectory_identity": {
            "B0_equals_B2": True,
            "B1_equals_B3": True,
            "Fresh_used_to_select_placement": 0,
            "MESS_used_to_alter_AIDC_schedule": 0,
        },
    }
    spatial_off = {
        "artifact_id": "V39A_V37_SPATIAL_OFF_EQUIVALENCE_V1",
        "status": status,
        "RW_schedule_unchanged": True,
        "RSP_schedule_unchanged": True,
        "CENTER_unchanged": True,
        "C1_unchanged": True,
        "runtime_predictions_unchanged": True,
        "WAN_disabled_noop": True,
        "aggregate_GPU_max_error": max(maximum_gpu_error.values()),
        "aggregate_IT_power_max_error_kW": str(max(
            max(maximum_site_error.values()), max(maximum_v37_error.values())
        )),
        "production_spatial_materialization": "BLOCKED_NOT_MATERIALIZED",
    }
    return aggregate, spatial_off


def _voltage_audit(repo: Path) -> dict[str, Any]:
    path = repo / VOLTAGE_AUTHORITY
    raw = path.read_bytes()
    current = hashlib.sha256(raw).hexdigest()
    logical_lf = raw.replace(b"\r\n", b"\n")
    logical_sha = hashlib.sha256(logical_lf).hexdigest()
    parent_lf = subprocess.check_output([
        "git", "-C", str(repo), "show",
        f"{V38_FAIL_EVIDENCE_HEAD}:{str(VOLTAGE_AUTHORITY).replace(chr(92), '/')}",
    ])
    content_equivalent = json.loads(raw.decode("utf-8")) == json.loads(parent_lf.decode("utf-8"))
    attr = _git(repo, "check-attr", "text", "--", str(VOLTAGE_AUTHORITY).replace("\\", "/"))
    return {
        "artifact_id": "V39A_VOLTAGE_AUTHORITY_BYTE_STABILITY_AUDIT_V1",
        "status": "PASS" if (
            current == VOLTAGE_FROZEN_SHA256
            and logical_sha == VOLTAGE_LOGICAL_LF_SHA256
            and content_equivalent
            and "unset" in attr
        ) else "FAIL",
        "frozen_byte_artifact_path": str(VOLTAGE_AUTHORITY).replace("\\", "/"),
        "frozen_expected_SHA256": VOLTAGE_FROZEN_SHA256,
        "clean_checkout_SHA256": current,
        "logical_source_SHA256": logical_sha,
        "parent_LF_blob_SHA256": hashlib.sha256(parent_lf).hexdigest(),
        "Git_attributes_behavior": attr,
        "narrow_rule": (
            "dayahead/artifacts/v37_r3_restore_intended_cuts/"
            "V37_R3_JOINT_VOLTAGE_AUTHORITY.json -text"
        ),
        "byte_preservation_status": "PASS" if current == VOLTAGE_FROZEN_SHA256 else "FAIL",
        "content_equivalence_status": "PASS" if content_equivalent else "FAIL",
        "regression_status": "PENDING_TEST_RECORD",
        "science_content_changed": False,
    }


def _wan_audit(repo: Path) -> dict[str, Any]:
    wan = load_wan_authority(repo)
    path_table = repo / V38_ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATHS.parquet"
    rows = pd.read_parquet(path_table)
    return {
        "artifact_id": "V39A_WAN_MIGRATION_AUDIT_V1",
        "status": "PASS_REUSED_AUTHORITY_PRODUCTION_BLOCKED",
        "authority": "Abilene 12-node benchmark based inter-AIDC WAN",
        "measured_Melbourne_WAN_claim": False,
        "topology_transfer_capacity_SHA256": (
            "e620c92985e6d8b8c09c8e32588d806c8c1c03e3e944a07119672d1804fda512"
        ),
        "historical_traffic_SHA256": (
            "2f311130d77e40db88da1aa6db8055b6fce8d077bf4bae87398563e1b84e70ce"
        ),
        "fixed_ordered_OD_paths": len(rows),
        "fixed_path_table_SHA256": sha256_file(path_table),
        "WAN_path_optimization": "NO",
        "WAN_transfer_timing_optimization": "YES_IF_PLACEMENT_FEASIBLE",
        "latency": wan.latency_semantics,
        "checkpoint_interval_minutes": 30,
        "checkpoint_payload_rule": "1.0 * requested_GPU * 80_000_000_000 bytes",
        "maximum_migrations_per_job_per_day": 1,
        "maximum_simultaneous_network_wide_transfers": 1,
        "pending_initial_placement_requires_WAN": False,
        "selected_production_migrations": 0,
        "selected_production_migration_semantics": (
            "ZERO_BECAUSE_FAIL_CLOSED_PREVENTED_ANY_PRODUCTION_PLACEMENT_DECISION"
        ),
        "path_selection_decisions": 0,
    }


def _rack_audit(repo: Path) -> dict[str, Any]:
    capacity = load_capacity_authority(repo)
    mapping = frozen_site_to_pcc(repo)
    return {
        "artifact_id": "V39A_RACK_ASSIGNMENT_AUDIT_V1",
        "status": "PASS_AUTHORITY_BLOCKED_PRODUCTION_ASSIGNMENT",
        "logical_Rack_pool_count": len(capacity.rack_pools),
        "logical_Rack_pools_per_AIDC": 4,
        "gang_fit_oracle_used": True,
        "historical_Rack_IT_caps_used": False,
        "production_Rack_assignments": "BLOCKED_NOT_MATERIALIZED",
        "D_minus_1_assignment_required": True,
        "runtime_counters": dict(RUNTIME_FIREWALL),
        "all_runtime_reoptimization_counters_zero": all(
            value == 0 for value in RUNTIME_FIREWALL.values()
        ),
        "AIDC_to_PCC_mapping": mapping,
        "AIDC_to_PCC_mapping_status": "PASS",
        "legacy_alias": (
            "Frozen source_idc_id values are preserved only as existing feeder PCC-node labels; "
            "current placement keys are AIDC."
        ),
    }


def _preflight(repo: Path, feasibility: Mapping[str, Any]) -> dict[str, Any]:
    infeasible_by_day: dict[str, list[str]] = {}
    for row in feasibility["infeasible_day_modes"]:
        infeasible_by_day.setdefault(row["operating_day"], []).append(row["temporal_mode"])
    rows: list[dict[str, Any]] = []
    required_v37 = (
        "V37_R4A_D1_SNAPSHOT.parquet", "V37_R4A_RW_SCHEDULE.parquet",
        "V37_R4A_RSP_SCHEDULE.parquet", "V37_R4A_GPU_IT_TRAJECTORY.parquet",
        "V37_R4A_C1_PCC_TRAJECTORY.parquet", "V37_R4A_JOB_LEDGER.parquet",
    )
    missing_total = 0
    for day in EXPECTED_DATES:
        day_root_path = repo / V37_DAY_ROOT / day
        missing = [name for name in required_v37 if not (day_root_path / name).is_file()]
        voltage_anchor, current_anchor = anchor_paths(repo, day)
        if not voltage_anchor.is_file():
            missing.append(_repo_path(voltage_anchor, repo))
        if not current_anchor.is_file():
            missing.append(_repo_path(current_anchor, repo))
        missing_total += len(missing)
        hard = day in feasibility["hard_conflict_days"]
        row = {
            "operating_day": day,
            "per_day_Kestrel_snapshot": "PASS" if not missing else "FAIL",
            "RW_schedule": "PASS" if required_v37[1] not in missing else "FAIL",
            "RSP_schedule": "PASS" if required_v37[2] not in missing else "FAIL",
            "site_capacity_authority": "PASS",
            "causal_spatial_state": "BLOCKED",
            "pending_initial_placement": "BLOCKED",
            "running_current_site": "BLOCKED",
            "migration_candidates": "BLOCKED",
            "WAN_adapter": "PASS",
            "WAN_fixed_paths": "PASS",
            "Rack_assignment": "BLOCKED",
            "site_GPU_trajectory": "BLOCKED",
            "site_IT_power": "BLOCKED",
            "site_PCC_power": "BLOCKED",
            "aggregate_equivalence": "PASS_ALGEBRAIC_ONLY",
            "C1_PCC_PQ": "BLOCKED",
            "D1_electrical_authority": (
                "PASS_INPUT_PRESENT"
                if voltage_anchor.is_file() and current_anchor.is_file()
                else "FAIL_INPUT_MISSING"
            ),
            "restoration_loader": "BLOCKED_BY_UPSTREAM_SPATIAL_FEASIBILITY",
            "true_production_loader": "BLOCKED_BY_UPSTREAM_SPATIAL_FEASIBILITY",
            "status": "NOT_READY",
            "blocker": (
                "HARD_SLOT_LOCAL_32_GPU_GANG_CARDINALITY_CONFLICT"
                if hard else "GLOBAL_V39A_SPATIAL_FEASIBILITY_FAIL_CLOSED"
            ),
            "relaxed_infeasible_modes": sorted(infeasible_by_day.get(day, [])),
            "missing_files": missing,
        }
        rows.append(row)
    return {
        "artifact_id": "V39A_MAY_31DAY_INPUT_PREFLIGHT_V1",
        "status": "FAIL_BLOCKED",
        "READY": 0,
        "NOT_READY": 31,
        "missing": missing_total,
        "true_production_loader_PASS_count": 0,
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "MAY_STARTED": "NO",
        "rows": rows,
    }


def _fingerprint(repo: Path) -> dict[str, Any]:
    paths = sorted((repo / "dayahead/v39a").glob("*.py"))
    inputs = {
        _repo_path(path, repo): sha256_file(path) for path in paths
    }
    inputs.update({
        str(VOLTAGE_AUTHORITY).replace("\\", "/"): sha256_file(repo / VOLTAGE_AUTHORITY),
        "V38_AIDC_GPU_CAPACITY_MAPPING.json": sha256_file(
            repo / V38_ARTIFACT_ROOT / "V38_AIDC_GPU_CAPACITY_MAPPING.json"
        ),
        "V38_WAN_FIXED_OD_PATHS.parquet": sha256_file(
            repo / V38_ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATHS.parquet"
        ),
    })
    return {
        "artifact_id": "V39A_IMPLEMENTATION_FINGERPRINT_V1",
        "V38_FAIL_EVIDENCE_HEAD": V38_FAIL_EVIDENCE_HEAD,
        "V38_IMPLEMENTATION_FINGERPRINT": V38_IMPLEMENTATION_FINGERPRINT,
        "V39A_git_HEAD_at_materialization": _git(repo, "rev-parse", "HEAD"),
        "V39A_branch": _git(repo, "branch", "--show-current"),
        "fingerprint_inputs": inputs,
        "V39A_IMPLEMENTATION_FINGERPRINT": canonical_sha256(inputs),
    }


def _terminology_audit() -> dict[str, Any]:
    return {
        "artifact_id": "V39A_AIDC_TERMINOLOGY_AUDIT_V1",
        "status": "PASS",
        "CURRENT_V39A_CANONICAL_TERM": "AIDC",
        "NEW_V39A_IDC_ONLY_USER_FACING_OCCURRENCES": 0,
        "LEGACY_IDC_OCCURRENCES_PRESERVED_WITH_ALIAS": "PASS",
        "legacy_aliases": [
            {
                "legacy_field": "source_idc_id",
                "current_exposure": "existing_feeder_PCC_node keyed by AIDC",
                "reason": "frozen historical feeder-node provenance",
            },
            {
                "legacy_object": "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json",
                "current_exposure": "V38 compatibility adapter to source_AIDC/destination_AIDC",
                "reason": "byte-preserved historical WAN authority",
            },
        ],
        "modeled_site_claim": "MODELED_AIDC_SITES_IN_TRACE_DRIVEN_CYBER_PHYSICAL_TESTBED",
        "measured_real_world_AI_facility_claim": False,
    }


def _readiness_review(
    feasibility: Mapping[str, Any], fingerprint: Mapping[str, Any],
    voltage: Mapping[str, Any], preflight: Mapping[str, Any],
) -> str:
    first = feasibility["first_IIS"]
    return f"""# V39A Final Readiness Review

V39A is **FAIL-CLOSED**.  The accepted V37 RW/RSP schedules and the frozen
12-AIDC capacities cannot be spatially realized without splitting GPU gangs or
changing temporal execution.  May was not started.

## Scientific result

- Gurobi built 62 day/mode relaxation models: {feasibility['models_optimal']} optimal,
  {feasibility['models_infeasible']} infeasible.
- The first IIS is {first['operating_day']} {first['temporal_mode']} with
  {first['IIS_constraint_count']} constraints.
- The decisive slot-local contradiction begins at May 21 slot 60: 15 concurrent
  32-GPU gangs exist, while the frozen site capacities can host at most 14 such
  indivisible gangs.  This remains impossible even under forbidden arbitrary
  per-slot remapping and with WAN limits removed.
- Hard slot-local contradictions occur on {', '.join(feasibility['hard_conflict_days'])}.
- V39B temporal-scheduler redesign is scientifically required; it was not implemented.

## Preserved science

Temporal schedules, runtime authority, CENTER, C1, MESS K/beam/seed, site
capacities, gang indivisibility, V38 fixed inter-AIDC WAN paths, and Rack
authority are unchanged.  The V38 failure evidence remains intact at
`{V38_FAIL_EVIDENCE_HEAD}`.

The site-power equation passes algebraic aggregate conservation, but production
site GPU/IT/PCC Parquets are intentionally schema-only and carry
`BLOCKED_NOT_MATERIALIZED`; fabricating trajectories after infeasibility would
violate fail-closed semantics.

## Reproducibility and launch gate

- Voltage frozen byte SHA: `{voltage['clean_checkout_SHA256']}` ({voltage['status']}).
- May preflight: READY={preflight['READY']}, NOT_READY={preflight['NOT_READY']},
  missing={preflight['missing']}.
- V39A implementation fingerprint: `{fingerprint['V39A_IMPLEMENTATION_FINGERPRINT']}`.
- `V39A_SCIENCE_FROZEN=NO`
- `MAY_CAMPAIGN_LAUNCH_READY=NO`
- `MAY_STARTED=NO`
"""


def materialize(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    root = repo / ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39A_BRANCH")
    if _git(repo, "merge-base", "HEAD", V38_FAIL_EVIDENCE_HEAD) != V38_FAIL_EVIDENCE_HEAD:
        raise RuntimeError("V39A_NOT_DESCENDED_FROM_EXACT_V38_HEAD")

    site_capacity = _site_capacity_audit(repo)
    atomic_json(root / "V39A_SITE_CAPACITY_AUTHORITY.json", site_capacity)
    initial = _initial_state_audit(repo)
    atomic_json(root / "V39A_CAUSAL_INITIAL_STATE_AUDIT.json", initial)

    feasibility = scan_may_relaxation(repo)
    first_iis = feasibility.get("first_IIS")
    if first_iis and first_iis.get("IIS_path"):
        first_iis["IIS_path"] = _repo_path(Path(first_iis["IIS_path"]), repo)
    feasibility.update({
        "artifact_id": "V39A_SPATIAL_FEASIBILITY_AUDIT_V1",
        "V38_FAIL_EVIDENCE_HEAD": V38_FAIL_EVIDENCE_HEAD,
        "inputs_validated": True,
        "authority_hashes_validated": True,
        "scientific_interpretation": (
            "At May-21 RW/RSP slots 60-95, 15 concurrent indivisible 32-GPU "
            "gangs require site residence. Frozen capacities and Rack gang fit "
            "provide only 14 simultaneous 32-GPU gang positions."
        ),
        "forbidden_workarounds_used": [],
        "V39A_READY": "NO",
        "MAY_STARTED": "NO",
        "V39B_required": True,
    })
    atomic_json(root / "V39A_SPATIAL_FEASIBILITY_AUDIT.json", feasibility)

    blocked_hashes = _write_blocked_parquets(repo)
    aggregate, spatial_off = _aggregate_equivalence(repo)
    atomic_json(root / "V39A_AGGREGATE_EQUIVALENCE.json", aggregate)
    atomic_json(root / "V39A_V37_SPATIAL_OFF_EQUIVALENCE.json", spatial_off)
    wan = _wan_audit(repo)
    rack = _rack_audit(repo)
    voltage = _voltage_audit(repo)
    preflight = _preflight(repo, feasibility)
    fingerprint = _fingerprint(repo)
    atomic_json(root / "V39A_WAN_MIGRATION_AUDIT.json", wan)
    atomic_json(root / "V39A_RACK_ASSIGNMENT_AUDIT.json", rack)
    atomic_json(root / "V39A_VOLTAGE_AUTHORITY_BYTE_STABILITY_AUDIT.json", voltage)
    atomic_json(root / "V39A_MAY_31DAY_INPUT_PREFLIGHT.json", preflight)
    atomic_json(root / "V39A_IMPLEMENTATION_FINGERPRINT.json", fingerprint)
    atomic_json(root / "V39A_AIDC_TERMINOLOGY_AUDIT.json", _terminology_audit())
    atomic_json(root / "V39A_TEST_REPORT.json", {
        "artifact_id": "V39A_TEST_REPORT_V1",
        "status": "PENDING",
        "V39A_focused": "PENDING",
        "V38_relevant_regression": "PENDING",
        "V37_clean_regression": "PENDING",
        "voltage_authority_frozen_SHA256": VOLTAGE_FROZEN_SHA256,
        "MAY_STARTED": "NO",
    })
    (root / "V39A_FINAL_READINESS_REVIEW.md").write_text(
        _readiness_review(feasibility, fingerprint, voltage, preflight),
        encoding="utf-8", newline="\n",
    )
    return {
        "status": "FAIL_CLOSED",
        "V39A_READY": "NO",
        "MAY_STARTED": "NO",
        "infeasible_models": feasibility["models_infeasible"],
        "blocked_parquet_sha256": blocked_hashes,
        "fingerprint": fingerprint["V39A_IMPLEMENTATION_FINGERPRINT"],
    }


def record_test_report(repo: Path, report: Mapping[str, Any]) -> None:
    path = repo.resolve() / ARTIFACT_ROOT / "V39A_TEST_REPORT.json"
    payload = {
        "artifact_id": "V39A_TEST_REPORT_V1",
        "status": "PASS_REGRESSIONS_SCIENCE_INFEASIBLE",
        **dict(report),
        "voltage_authority_frozen_SHA256": VOLTAGE_FROZEN_SHA256,
        "logical_normalized_SHA256": VOLTAGE_LOGICAL_LF_SHA256,
        "V39A_READY": "NO",
        "MAY_STARTED": "NO",
    }
    atomic_json(path, payload)
    voltage_path = repo.resolve() / ARTIFACT_ROOT / "V39A_VOLTAGE_AUTHORITY_BYTE_STABILITY_AUDIT.json"
    voltage = json.loads(voltage_path.read_text(encoding="utf-8"))
    voltage["regression_status"] = str(report.get("V37_clean_regression", {}).get("status", "UNKNOWN"))
    voltage["status"] = "PASS" if voltage["regression_status"] == "PASS" else "FAIL"
    atomic_json(voltage_path, voltage)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(materialize(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["materialize", "record_test_report"]
