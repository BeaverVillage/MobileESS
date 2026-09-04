"""Fail-closed V38 readiness materialization.

This module deliberately records upstream scientific infeasibility instead
of fabricating downstream spatial, Rack, power, or Fresh artifacts.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .authority import atomic_json, canonical_sha256, sha256_file, write_recovery_audits
from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CENTER_SWING_W_PER_GPU,
    EXPECTED_DATES,
    HOME_MAPPING_AUDIT,
    IMPLEMENTATION_FINGERPRINT,
    IMPLEMENTATION_ID,
    INPUT_PREFLIGHT,
    PARENT_HEAD,
    RUNTIME_FIREWALL,
    TRUE_LOADER_PREFLIGHT,
    V37_DAY_ROOT,
    V37_INPUT_PREFLIGHT,
    V37_TRUE_LOADER_PREFLIGHT,
)
from .wan import write_synthetic_migration_certificate


BLOCKER = "V38_HOME_MAPPING_GLOBAL_CAPACITY_INFEASIBLE"
VOLTAGE_BLOCKER = "V37_PARENT_VOLTAGE_AUTHORITY_BYTE_SHA_MISMATCH"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _fingerprint(repo: Path) -> dict[str, Any]:
    code_paths = [
        Path("dayahead/v38/authority.py"),
        Path("dayahead/v38/contracts.py"),
        Path("dayahead/v38/home.py"),
        Path("dayahead/v38/preflight.py"),
        Path("dayahead/v38/rack.py"),
        Path("dayahead/v38/wan.py"),
    ]
    audit_names = [
        "V38_A_HISTORICAL_WAN_MIGRATION_RECOVERY_AUDIT.json",
        "V38_AIDC_GPU_CAPACITY_MAPPING.json",
        "V38_HOME_IDC_MAPPING_AUDIT.json",
        "V38_WAN_FIELD_SEMANTICS_AUDIT.json",
        "V38_WAN_TRANSFER_CAPACITY_AUTHORITY.json",
        "V38_WAN_15MIN_ADAPTER_AUDIT.json",
        "V38_WAN_5MIN_TO_15MIN_CONSERVATION_AUDIT.json",
        "V38_WAN_LATENCY_BINDING_AUDIT.json",
        "V38_WAN_FIXED_OD_PATH_AUTHORITY.json",
        "V38_WAN_PATH_OPTIMIZATION_REMOVAL_AUDIT.json",
        "V38_AIDC_TERMINOLOGY_AUDIT.json",
        "V38_CHECKPOINT_RESTART_CONTRACT_AUDIT.json",
        "V38_RACK_ORACLE_COMPATIBILITY_AUDIT.json",
        "V38_RUNTIME_RACK_REOPTIMIZATION_AUDIT.json",
        "V38_SYNTHETIC_MIGRATION_CERTIFICATE.json",
    ]
    code = {
        str(path).replace("\\", "/"): sha256_file(repo / path)
        for path in code_paths
    }
    audits = {
        name: sha256_file(repo / ARTIFACT_ROOT / name)
        for name in audit_names
    }
    home = _read_json(repo / HOME_MAPPING_AUDIT)
    components = {
        "implementation_id": IMPLEMENTATION_ID,
        "parent_HEAD": PARENT_HEAD,
        "branch": BRANCH,
        "code": code,
        "audits": audits,
        "V37_RW_RSP_schedule_set_sha256": home["source_schedule_set_sha256"],
        "home_mapping_input_sha256": home["mapping_input_sha256"],
        "home_mapping_status": home["status"],
        "home_mapping_IIS_sha256": home["IIS_sha256"],
        "fixed_OD_path_table_sha256": sha256_file(
            repo / ARTIFACT_ROOT / "V38_WAN_FIXED_OD_PATHS.parquet"
        ),
        "runtime_no_reoptimization_guard": dict(RUNTIME_FIREWALL),
        "electrical_authority_sha256": sha256_file(
            repo / "dayahead/artifacts/v37_r3_restore_intended_cuts/V37_R3_JOINT_VOLTAGE_AUTHORITY.json"
        ),
        "electrical_applicability_sha256": sha256_file(
            repo / "dayahead/artifacts/v37_r4_may_campaign_repair/V37_R4_MAY_VOLTAGE_APPLICABILITY.json"
        ),
        "C1_authority_sha256": sha256_file(
            repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
        ),
        "V37_parent_preflight_sha256": sha256_file(repo / V37_INPUT_PREFLIGHT),
    }
    root = canonical_sha256(components)
    payload = {
        "artifact_id": "V38_IMPLEMENTATION_FINGERPRINT_V1",
        "status": "INCOMPLETE_BLOCKED",
        "V38_READY": "NO",
        "blocker": BLOCKER,
        "components": components,
        "root_sha256": root,
        "invalidates_V37_production_result_cache": True,
        "V37_temporal_only_artifact_classification": "V37_TEMPORAL_ONLY_SUPERSEDED_FOR_V38_FINAL",
    }
    atomic_json(repo / IMPLEMENTATION_FINGERPRINT, payload)
    return payload


def _write_blocked_science_artifacts(repo: Path) -> None:
    root = repo / ARTIFACT_ROOT
    causal = {
        "artifact_id": "V38_CAUSALITY_AUDIT_V1",
        "status": "PASS",
        "scope": "IMPLEMENTED_RECOVERY_PREFLIGHT_AND_SYNTHETIC_TESTS",
        "future_runtime_used": False,
        "future_D_day_scheduler_execution_used": False,
        "actual_traffic_used_for_DA": False,
        "actual_grid_or_PV_used_for_DA": False,
        "Fresh_used_for_AIDC_placement_or_migration": False,
        "May_B0_B3_result_reads": 0,
        "note": "Production spatial decisions were not materialized because the upstream home mapping is infeasible.",
    }
    atomic_json(root / "V38_CAUSALITY_AUDIT.json", causal)
    blocked = {
        "status": "NOT_RUN",
        "blocking_gate": BLOCKER,
        "scientific_rule": "DOWNSTREAM_ARTIFACTS_MUST_NOT_BE_FABRICATED_AFTER_UPSTREAM_INFEASIBILITY",
    }
    for name, artifact_id in (
        ("V38_V37_SPATIAL_OFF_EQUIVALENCE.json", "V38_V37_SPATIAL_OFF_EQUIVALENCE_V1"),
        ("V38_POWER_RECONCILIATION_AUDIT.json", "V38_POWER_RECONCILIATION_AUDIT_V1"),
        ("V38_B0_B2_AIDC_IDENTITY_AUDIT.json", "V38_B0_B2_AIDC_IDENTITY_AUDIT_V1"),
        ("V38_B1_B3_AIDC_IDENTITY_AUDIT.json", "V38_B1_B3_AIDC_IDENTITY_AUDIT_V1"),
    ):
        atomic_json(root / name, {"artifact_id": artifact_id, **blocked})
    for name, artifact_id in (
        ("V38_DAYAHEAD_RACK_ASSIGNMENT_AUDIT.json", "V38_DAYAHEAD_RACK_ASSIGNMENT_AUDIT_V1"),
        ("V38_DAYAHEAD_RACK_CAPACITY_AUDIT.json", "V38_DAYAHEAD_RACK_CAPACITY_AUDIT_V1"),
    ):
        atomic_json(root / name, {
            "artifact_id": artifact_id,
            "status": "FAIL",
            "blocking_gate": BLOCKER,
            "production_assignment_materialized": False,
            "runtime_Rack_reoptimization_calls": 0,
        })


def write_fail_closed_preflight(repo: Path) -> dict[str, Any]:
    write_recovery_audits(repo)
    write_synthetic_migration_certificate(repo)
    home_path = repo / HOME_MAPPING_AUDIT
    if not home_path.is_file():
        raise RuntimeError("V38_HOME_MAPPING_AUDIT_MISSING_RUN_HOME_SOLVER_FIRST")
    home = _read_json(home_path)
    if home.get("status") != "FAIL" or home.get("solver_status_name") != "INFEASIBLE":
        raise RuntimeError("V38_EXPECTED_EXACT_HOME_MAPPING_INFEASIBILITY_EVIDENCE")
    _write_blocked_science_artifacts(repo)
    fingerprint = _fingerprint(repo)

    prior = _read_json(repo / V37_INPUT_PREFLIGHT)
    prior_true = _read_json(repo / V37_TRUE_LOADER_PREFLIGHT)
    if prior.get("ready_dates") != 31 or prior_true.get("ready_dates") != 31:
        raise RuntimeError("V38_V37_PARENT_PREFLIGHT_NOT_31_OF_31")
    voltage_authority = repo / (
        "dayahead/artifacts/v37_r3_restore_intended_cuts/"
        "V37_R3_JOINT_VOLTAGE_AUTHORITY.json"
    )
    voltage_applicability = repo / (
        "dayahead/artifacts/v37_r4_may_campaign_repair/"
        "V37_R4_MAY_VOLTAGE_APPLICABILITY.json"
    )
    applicability = _read_json(voltage_applicability)
    expected_voltage_sha = str(applicability["coefficient_authority_file_sha256"])
    actual_voltage_sha = sha256_file(voltage_authority)
    voltage_authority_ok = expected_voltage_sha == actual_voltage_sha
    blockers = [BLOCKER]
    if not voltage_authority_ok:
        blockers.append(VOLTAGE_BLOCKER)

    date_rows: list[dict[str, Any]] = []
    missing_total = 0
    required_files = (
        "V37_R4A_DAY_MANIFEST.json",
        "V37_R4A_JOB_LEDGER.parquet",
        "V37_R4A_RW_SCHEDULE.parquet",
        "V37_R4A_RSP_SCHEDULE.parquet",
        "V37_R4A_GPU_IT_TRAJECTORY.parquet",
        "V37_R4A_C1_PCC_TRAJECTORY.parquet",
    )
    for day in EXPECTED_DATES:
        day_root = repo / V37_DAY_ROOT / day
        missing = [name for name in required_files if not (day_root / name).is_file()]
        missing_total += len(missing)
        parent_status = "PASS" if not missing else "MISSING"
        date_rows.append({
            "operating_day": day,
            "status": "NOT_READY",
            "D_minus_1_AEMO_demand": parent_status,
            "D_minus_1_rooftop_PV": parent_status,
            "D_minus_1_GFS": parent_status,
            "per_day_Kestrel_snapshot": parent_status,
            "RW_schedule": parent_status,
            "RSP_schedule": parent_status,
            "reference_home_mapping": "FAIL_INFEASIBLE",
            "AIDC_GPU_capacity": "PASS",
            "pending_spatial_candidate_materialization": "BLOCKED",
            "running_migration_candidate_materialization": "BLOCKED",
            "checkpoint_eligibility": "BLOCKED",
            "WAN_capacity_path_latency": "PASS",
            "WAN_15min_adapter": "PASS",
            "Rack_oracle_loader": "PASS",
            "DayAhead_Rack_assignment": "BLOCKED",
            "site_power_mapping": "BLOCKED",
            "C1_PCC_PQ": "BLOCKED",
            "traffic_288x509x3": parent_status,
            "route_table_24_service": parent_status,
            "Safe_ETA": parent_status,
            "D1_electrical_authority": "PASS" if voltage_authority_ok else "FAIL_SHA_MISMATCH",
            "Fresh_context": parent_status if voltage_authority_ok else "BLOCKED",
            "V17_R5_restoration_loader": parent_status,
            "V38_fingerprint": "INCOMPLETE_BLOCKED",
            "blocker": BLOCKER,
            "missing_files": ";".join(missing),
        })
    csv_path = (repo / INPUT_PREFLIGHT).with_suffix(".csv")
    _write_csv(csv_path, date_rows)
    payload = {
        "artifact_id": "V38_MAY_31DAY_INPUT_PREFLIGHT_V1",
        "status": "FAIL",
        "V38_READY": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "MAY_STARTED": "NO",
        "expected_dates": 31,
        "ready_dates": 0,
        "not_ready_dates": 31,
        "missing_dates": sum(bool(row["missing_files"]) for row in date_rows),
        "missing_file_count": missing_total,
        "blocker": BLOCKER,
        "blockers": blockers,
        "V37_parent_voltage_authority": {
            "status": "PASS" if voltage_authority_ok else "FAIL",
            "expected_sha256": expected_voltage_sha,
            "actual_sha256": actual_voltage_sha,
            "note": "The clean LF-normalized worktree bytes do not match the CRLF-era frozen applicability SHA; no frozen byte was rewritten.",
        },
        "implementation_fingerprint_sha256": fingerprint["root_sha256"],
        "dates": date_rows,
    }
    atomic_json(repo / INPUT_PREFLIGHT, payload)
    true_loader = {
        "artifact_id": "V38_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT_V1",
        "status": "FAIL",
        "V38_READY": "NO",
        "MAY_STARTED": "NO",
        "expected_dates": 31,
        "ready_dates": 0,
        "not_ready_dates": 31,
        "missing_dates": payload["missing_dates"],
        "exact_production_loader_dry_run": "STOPPED_AT_MANDATORY_HOME_MAPPING_AND_ELECTRICAL_SHA_GATES",
        "Gurobi_production_optimization_calls": 0,
        "May_Fresh_results_created": 0,
        "campaign_processes_spawned": 0,
        "blocker": BLOCKER,
        "blockers": blockers,
        "dates": [
            {"operating_day": day, "status": "NOT_READY", "blocker": BLOCKER}
            for day in EXPECTED_DATES
        ],
    }
    atomic_json(repo / TRUE_LOADER_PREFLIGHT, true_loader)
    atomic_json(repo / ARTIFACT_ROOT / "V38_READY_STATE.json", {
        "artifact_id": "V38_READY_STATE_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "V38_READY": "NO",
        "V38_SCIENCE_FROZEN": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "MAY_STARTED": "NO",
        "blocker": BLOCKER,
        "blockers": blockers,
        "runtime_counters": dict(RUNTIME_FIREWALL),
    })
    review = f"""# V38 Final Readiness Review

V38_READY = NO
MAY_STARTED = NO

## Exact blocker

The mandated global synthetic reference-home mapping is mathematically
infeasible. Gurobi status 3 and the persisted IIS prove that the same
`job_uid -> home AIDC` invariant cannot jointly satisfy the accepted V37
RW/RSP schedules, gang indivisibility, and the frozen 12-site capacities
whose sum is 624.

The IIS contains {home['IIS_constraint_count']} constraints and binds site
capacity cells on May 24 through May 28. Evidence:
`{home['IIS_path']}` (SHA-256 `{home['IIS_sha256']}`).

No date-dependent remapping, gang splitting, capacity inflation, temporal
rescheduling, result-based fitting, runtime Rack reoptimization, or Fresh
feedback was used. Downstream production spatial/Rack/power/identity
artifacts remain explicitly NOT_RUN or FAIL, the science freeze was not
written, and the May launcher must refuse execution.

The exact V37 electrical production-loader regression also fails in this
clean worktree: applicability expects byte SHA `{expected_voltage_sha}`, while
the canonical LF-normalized authority file is `{actual_voltage_sha}`. The
preserved original V37 working tree has CRLF-era bytes and passes its 80/80
namespace regression, but those bytes are not the clean parent checkout. No
frozen historical artifact was silently rewritten to conceal this mismatch.

## Recovered authorities

- Abilene pre-installed benchmark link capacities: PASS.
- 5-minute rate-to-byte and 15-minute sum adapter: PASS.
- Latency binding: NO_AUTHORITATIVE_LATENCY_AVAILABLE; no latency invented.
- Fixed OD paths: 132/132 PASS; WAN path optimization disabled.
- Current terminology: AIDC; frozen historical IDC fields use documented aliases.
- Checkpoint payload/restart authority: recovered and synthetic test PASS.
- 48 logical Rack pools as GPU-gang oracle only: PASS.
- Historical runtime Rack optimization: disabled for V38; runtime call counts 0.
- CENTER coefficient remains {CENTER_SWING_W_PER_GPU} W/GPU.
"""
    (repo / ARTIFACT_ROOT / "V38_FINAL_READINESS_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n"
    )
    return payload


__all__ = ["BLOCKER", "write_fail_closed_preflight"]
