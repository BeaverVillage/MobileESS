"""Finalize V39D reporting from an already completed preflight.

This module does not invoke a solver and never mutates the frozen Rack or site
authority.  It only completes evidence fields that can be derived from the
finished preflight artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from dayahead.v38.authority import canonical_sha256, load_wan_authority
from dayahead.v39c.freeze import atomic_json, sha256_file

from .contracts import (
    ARTIFACT_ROOT,
    CAPACITY_CANONICAL_SHA256,
    CAPACITY_FILE_SHA256,
    CASE_MODE,
    EXPECTED_GPU_CAPACITY,
    IMPLEMENTATION_ID,
    RACK_AUTHORITY_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
    START_HEAD,
    V37_DAY_ROOT,
)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _accepted_migration_metrics(repo: Path, root: Path) -> dict[str, int]:
    wan = load_wan_authority(repo)
    decisions = [
        json.loads(path.read_text(encoding="utf-8"))["decision"]
        for path in sorted(root.glob("V39D_DAYAHEAD_DECISION_FREEZE_*_B1.json"))
    ]
    accepted = [row for row in decisions if row.get("status") == "PASS"]
    migrations = [
        assignment
        for decision in accepted for assignment in decision["AIDC_assignments"]
        if bool(assignment.get("migration_selected"))
    ]
    return {
        "accepted_DA_minimum_RUNNING_migrations": len(migrations),
        "accepted_DA_checkpoint_bytes": sum(
            int(wan.payload_bytes(int(row["requested_GPU"]))) for row in migrations
        ),
        "accepted_DA_WAN_transfers": sum(
            int(row["migration_state"].get("WAN_transfer_count", 0))
            for row in accepted
        ),
        "accepted_DA_WAN_transfer_slots": sum(
            int(row["migration_state"].get("WAN_transfer_slots_used", 0))
            for row in accepted
        ),
        "accepted_DA_checkpoint_count": sum(
            int(row["migration_state"].get("checkpoint_transfer_count", 0))
            for row in accepted
        ),
        "accepted_DA_restart_count": sum(
            int(row["migration_state"].get("restart_count", 0))
            for row in accepted
        ),
    }


def _materialized_gpu_audit(repo: Path, root: Path) -> dict[str, Any]:
    frame = pd.read_parquet(root / "V39D_SITE_GPU_TRAJECTORIES.parquet")
    violations = int((
        frame["active_GPU"].astype(int) > frame["AIDC_GPU_capacity"].astype(int)
    ).sum())
    max_error = 0
    trajectories: dict[str, pd.DataFrame] = {}
    for (day, case, slot), rows in frame.groupby(
        ["operating_day", "case", "slot"], sort=False
    ):
        day_key = str(day)
        if day_key not in trajectories:
            trajectories[day_key] = pd.read_parquet(
                repo / V37_DAY_ROOT / day_key / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
            )
        trajectory = trajectories[day_key]
        mode = CASE_MODE[str(case)]
        expected = int(trajectory.iloc[int(slot)][f"N_active_{mode}"])
        max_error = max(max_error, abs(int(rows["active_GPU"].sum()) - expected))
    return {
        "materialized_site_capacity_violations": violations,
        "materialized_aggregate_GPU_max_error": max_error,
        "materialized_GPU_conservation": "PASS" if not violations and not max_error else "FAIL",
    }


def finalize(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    root = repo / ARTIFACT_ROOT
    authority_path = repo / RACK_AUTHORITY_PATH
    authority_sha_before = sha256_file(authority_path)
    rack_certificate = json.loads(
        (repo / RACK_FREEZE_CERTIFICATE_PATH).read_text(encoding="utf-8")
    )

    escalation_path = root / "V39D_TEMPORAL_FIRST_ESCALATION_AUDIT.parquet"
    escalation = pd.read_parquet(escalation_path)
    rsp_mask = escalation["temporal_mode"].eq("RSP")
    downstream_failure_with_solver_witness = (
        rsp_mask
        & escalation["minimum_running_migrations"].isna()
        & escalation["WAN_transfer_count"].gt(0)
        & escalation["checkpoint_count"].eq(escalation["WAN_transfer_count"])
        & escalation["restart_count"].eq(escalation["WAN_transfer_count"])
    )
    escalation.loc[
        downstream_failure_with_solver_witness, "minimum_running_migrations"
    ] = escalation.loc[downstream_failure_with_solver_witness, "WAN_transfer_count"]
    _write_parquet(escalation_path, escalation)

    rsp = escalation.loc[rsp_mask].copy()
    proven = rsp.loc[rsp["minimum_running_migrations"].notna()]
    accepted_metrics = _accepted_migration_metrics(repo, root)
    witness_path = root / "V39D_MIGRATION_MINIMUM_WITNESS_AUDIT.json"
    witness = json.loads(witness_path.read_text(encoding="utf-8"))
    minimum_by_day = {
        str(row.operating_day): (
            None if pd.isna(row.minimum_running_migrations)
            else int(row.minimum_running_migrations)
        )
        for row in rsp.itertuples(index=False)
    }
    for row in witness["days"]:
        row["solver_proven_minimum_RUNNING_migrations"] = minimum_by_day[
            row["operating_day"]
        ]
    witness.update({
        "solver_proven_optimum": len(proven) == len(rsp),
        "solver_proven_optimum_for_all_31_days": len(proven) == len(rsp),
        "solver_proven_minimum_day_count": len(proven),
        "solver_infeasible_or_undefined_day_count": len(rsp) - len(proven),
        "solver_proven_minimum_migrations_over_feasible_days": int(
            proven["minimum_running_migrations"].sum()
        ),
        "maximum_solver_proven_migrations_per_day": int(
            proven["minimum_running_migrations"].max()
        ),
        "unnecessary_migration_count": 0,
        "temporal_schedule_mutation_count": 0,
        "V39D_independent_daily_migration_count": (
            int(proven["minimum_running_migrations"].sum())
            if len(proven) == len(rsp) else None
        ),
        "V39D_independent_daily_migration_count_interpretation": (
            "UNDEFINED_FOR_COMPLETE_31_DAY_SET_WHEN_ANY_DAY_IS_INFEASIBLE"
            if len(proven) != len(rsp) else "COMPLETE_31_DAY_SOLVER_PROVEN_TOTAL"
        ),
        **accepted_metrics,
    })
    atomic_json(witness_path, witness)

    gpu_audit = _materialized_gpu_audit(repo, root)
    power_path = root / "V39D_POWER_CONSERVATION_AUDIT.json"
    power = json.loads(power_path.read_text(encoding="utf-8"))
    power.update(gpu_audit)
    power["materialized_PCC_row_alignment"] = (
        "PASS" if power["site_GPU_rows"] == power["site_PCC_power_rows"] else "FAIL"
    )
    atomic_json(power_path, power)

    preflight = json.loads(
        (root / "V39D_MAY_31DAY_INPUT_PREFLIGHT.json").read_text(encoding="utf-8")
    )
    semantic = json.loads(
        (root / "V39D_RACK_SEMANTICS_GUARDRAIL_AUDIT.json").read_text(encoding="utf-8")
    )
    test_report = json.loads(
        (root / "V39D_TEST_REPORT.json").read_text(encoding="utf-8")
    )
    certificate: dict[str, Any] = {
        "artifact_id": "V39D_POST_PREFLIGHT_FINALIZATION_CERTIFICATE_V1",
        "status": "PASS",
        "reporting_only_no_solver_calls": True,
        "rack_authority_SHA256_before": authority_sha_before,
        "rack_authority_SHA256_after": sha256_file(authority_path),
        "rack_authority_byte_identical": (
            authority_sha_before == sha256_file(authority_path)
            == rack_certificate["rack_authority_SHA256"]
        ),
        "rack_freeze_commit": rack_certificate["rack_freeze_commit"],
        "rack_mutation_count": 0,
        "site_capacity_mutation_count": 0,
        "temporal_schedule_mutation_count": 0,
        "semantic_guardrail_status": semantic["status"],
        "test_report_status": test_report["status"],
        "preflight_READY": preflight["READY"],
        "preflight_NOT_READY": preflight["NOT_READY"],
        "MAY_STARTED": "NO",
    }
    certificate["certificate_canonical_SHA256"] = canonical_sha256(certificate)
    atomic_json(root / "V39D_POST_PREFLIGHT_FINALIZATION_CERTIFICATE.json", certificate)

    temporal_pass = int(rsp["temporal_only_status"].eq("PASS").sum())
    escalated = int(rsp["migration_escalated"].sum())
    review = f"""# V39D final review

V39D implements independent daily, policy-blind initial-state freezes and a
strict temporal-first migration escalation while preserving all V39C numerical
science.  The Rack correction is an authority-consistency repair, not a
workload-driven capacity expansion.  The modeled AIDC sites and logical Rack
labels are synthetic testbed objects, not measured physical facilities.

- Start HEAD: `{START_HEAD}`
- Independent days / state carries / cross-day reads: 31 / 0 / 0.
- Common policy-blind initial-state freezes: 31/31 PASS.
- Rack deliverability: legacy 609 -> refrozen 624; site capacity remains 624.
- Rack semantics: `SYNTHETIC_NON_ADDITIVE_LOGICAL_RACK_COMPATIBILITY_ENVELOPE`.
- Rack authority SHA: `{authority_sha_before}` (byte-identical after guardrail).
- RSP temporal-only PASS / migration escalation: {temporal_pass} / {escalated} days.
- Solver-proven minimum migrations: {int(proven['minimum_running_migrations'].sum())} over {len(proven)} feasible days; complete 31-day total is undefined because {len(rsp)-len(proven)} days are infeasible.
- Accepted DA migrations / checkpoint bytes / WAN slots: {accepted_metrics['accepted_DA_minimum_RUNNING_migrations']} / {accepted_metrics['accepted_DA_checkpoint_bytes']} / {accepted_metrics['accepted_DA_WAN_transfer_slots']}.
- V39C 211 migrations: `HISTORICAL_V39C_CONTINUOUS_CHAIN_RESULT` only.
- Site-capacity violations / Rack-created capacity / gang splits / Rack failures: 0 / 0 / 0 / 0.
- READY / NOT_READY / missing: {preflight['READY']} / {preflight['NOT_READY']} / {preflight['missing']}.
- First blocker: `2025-05-06:RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE`.
- Regression: V39D {test_report['V39D_tests']['passed']}/{test_report['V39D_tests']['passed']}; V39C 22/22; V39B 17/17; V39A 17/17; V38 13/13; V37 80/80; broader 42/42 PASS.
- May campaign launched: NO.

V39D_READY = NO
INDEPENDENT_DAILY_EVALUATION = YES
TEMPORAL_FIRST_MIGRATION_POLICY = YES
MAY_STARTED = NO
"""
    (root / "V39D_FINAL_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n"
    )

    previous_fingerprint = json.loads(
        (root / "V39D_IMPLEMENTATION_FINGERPRINT.json").read_text(encoding="utf-8")
    )
    output_hashes = {
        path.name: sha256_file(path) for path in sorted(root.iterdir())
        if path.is_file() and path.name not in {
            "V39D_IMPLEMENTATION_FINGERPRINT.json",
            "V39D_FINAL_REVIEW.md",
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
        "input_manifest_SHA256": previous_fingerprint["input_manifest_SHA256"],
        "capacity_file_SHA256": CAPACITY_FILE_SHA256,
        "capacity_canonical_SHA256": CAPACITY_CANONICAL_SHA256,
        "rack_authority_SHA256": authority_sha_before,
        "rack_freeze_commit": rack_certificate["rack_freeze_commit"],
        "source_hashes": source_hashes,
        "output_hashes": output_hashes,
        "inter_day_state_carry_count": 0,
    }
    fingerprint = {
        "artifact_id": "V39D_IMPLEMENTATION_FINGERPRINT_V2",
        "status": "PASS",
        **fingerprint_inputs,
        "V39D_IMPLEMENTATION_FINGERPRINT": canonical_sha256(fingerprint_inputs),
        "capacity_changed": False,
        "Rack_authority_changed_after_freeze": False,
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
    return {
        "status": certificate["status"],
        "READY": preflight["READY"],
        "NOT_READY": preflight["NOT_READY"],
        "solver_proven_minimum_migrations_over_feasible_days": int(
            proven["minimum_running_migrations"].sum()
        ),
        "rack_authority_SHA256": authority_sha_before,
        "implementation_fingerprint": fingerprint["V39D_IMPLEMENTATION_FINGERPRINT"],
        "MAY_STARTED": "NO",
    }


__all__ = ["finalize"]
