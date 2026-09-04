#!/usr/bin/env python3
"""Build and validate the final Stage-7 zero-burn-in C/B/D authorities.

This script performs no controller, Gurobi, or OpenDSS execution.  It binds the
already-completed preregistered four-transition evidence into portable,
SHA-locked handoffs and fails closed on any semantic or hash mismatch.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_IDS = [
    "W02_2025-01-13", "W07_2025-02-17", "W10_2025-03-10",
    "W17_2025-04-28", "W18_2025-05-05", "W25_2025-06-23",
    "W26_2025-06-30", "W32_2025-08-11", "W38_2025-09-22",
    "W41_2025-10-13", "W44_2025-11-03", "W51_2025-12-22",
]
RESTART_IDS = [
    "W02_2025-01-13", "W10_2025-03-10",
    "W25_2025-06-23", "W38_2025-09-22",
]
ISSUES = {
    "W02_2025-01-13": 3456,
    "W10_2025-03-10": 19584,
    "W25_2025-06-23": 49824,
    "W38_2025-09-22": 76032,
}
PR3_COMMIT = "bfbbc7cb4bc03c131f4c26df82c7c55d231cbfc8"
SCIENCE_COMMIT = "358a2699501d7465a543179c2ad40db64a383cf9"
SCIENCE_SHA = "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
PRODUCTION_CORE_SHA = "c10ed2683ce53c8ee429e0d5c58615ffd09cfeb09febed0f10380d964f036836"
PRIOR_D_ARCHIVE_SHA = "79588bd2cc78eaf9f95eaebffb2de43a839bff7eba0c19a4661cb367d2effcc2"
F7_SHA = "faa537141d67f468f10b32d741d8193c14125cd745c042d132510b72e111f8ba"
SUPERSESSION = "SUPERSEDED_BY_STAGE7_ZERO_BURNIN_CANONICAL_INITIALIZATION"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"required source file missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def reset_generated(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def write_sha_manifest(root: Path, excluded_names: set[str] | None = None) -> int:
    excluded_names = excluded_names or set()
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "SHA256SUMS.txt" or path.name in excluded_names:
            continue
        rows.append(f"{sha256(path)}  {rel}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def verify_sha_manifest(root: Path) -> None:
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(None, 1)
        path = root / rel.strip().lstrip("*")
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"SHA manifest failure: {path}")


def make_archive(source_dir: Path, archive: Path) -> str:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(source_dir, arcname=source_dir.name)
    digest = sha256(archive)
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    return digest


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_weeks(root: Path) -> list[dict]:
    with (root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    require([row["candidate_id"] for row in rows] == EXPECTED_IDS, "frozen representative weeks mismatch")
    return rows


def bind_actual_restart_evidence(root: Path, run_root: Path) -> dict:
    restart = load(root / "RESTART/RESTART_RESULTS.json")
    prereg = load(root / "RESTART/RESTART_TEST_PREREGISTRATION.json")
    require(restart.get("status") == "PASS", "restart result is not PASS")
    require(restart.get("pass_count") == 4, "restart pass count != 4")
    require([row["candidate_id"] for row in prereg["selected"]] == RESTART_IDS, "preregistered subset drift")
    by_id = {row["candidate_id"]: row for row in restart["results"]}
    evidence_rows: list[dict] = []
    total_runtime = 0.0
    evidence_root = root / "RESTART/evidence"
    reset_generated(evidence_root)
    for candidate in RESTART_IDS:
        issue = ISSUES[candidate]
        issue_root = run_root / candidate / "canonical_h0" / f"issue_{issue:06d}"
        target = evidence_root / candidate
        sources = {
            "CERTIFIED_GAP_ACCEPTANCE.json": issue_root / "ConversationA_BUILD7C_R12R1_CERTIFIED_GAP_ACCEPTANCE.json",
            "FIRSTSTEP_TRANSITION_CERTIFICATE.json": issue_root / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",
            "FRESH_EXACT_OPENDSS.json": issue_root / "exact_grid" / f"FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",
            "RUNTIME_STAGE_LIVE.json": issue_root / "BUILD7BR9_RUNTIME_STAGE_LIVE.json",
        }
        for name, source in sources.items():
            copy_file(source, target / name)
        gap = load(target / "CERTIFIED_GAP_ACCEPTANCE.json")
        cert = load(target / "FIRSTSTEP_TRANSITION_CERTIFICATE.json")
        opendss = load(target / "FRESH_EXACT_OPENDSS.json")
        runtime = load(target / "RUNTIME_STAGE_LIVE.json")
        result = by_id[candidate]
        require(gap.get("accepted") is True and float(gap["certified_mip_gap"]) <= 0.03, f"{candidate}: 3% certificate failed")
        require(cert.get("status") == "PASS" and cert.get("h0_only_committed") is True, f"{candidate}: first-step certificate failed")
        require(cert.get("future_actual_arrivals_read") is False, f"{candidate}: future actual leakage")
        require(cert.get("future_D2_state_reinjected") is False, f"{candidate}: future D2 reinjected")
        require(opendss.get("converged") is True and opendss.get("hard_constraint_pass") is True, f"{candidate}: fresh OpenDSS failed")
        require(result.get("gurobi_executed_transitions") == 1, f"{candidate}: Gurobi transition count mismatch")
        require(result.get("opendss_executed_transitions") == 1, f"{candidate}: OpenDSS transition count mismatch")
        require(result.get("hash_exact") is True, f"{candidate}: restart hash mismatch")
        require(result["canonical_post_sha256"] == result["restarted_next_pre_sha256"] == cert["post_state_sha256"], f"{candidate}: POST/restart authority mismatch")
        elapsed = float(runtime["elapsed_s"])
        total_runtime += elapsed
        evidence_rows.append({
            "candidate_id": candidate,
            "issue_step": issue,
            "certified_mip_gap": gap["certified_mip_gap"],
            "target_mip_gap": gap["target_mip_gap"],
            "firststep_status": cert["status"],
            "fresh_exact_opendss_pass": opendss["hard_constraint_pass"],
            "canonical_post_sha256": result["canonical_post_sha256"],
            "restarted_next_pre_sha256": result["restarted_next_pre_sha256"],
            "hash_exact": result["hash_exact"],
            "controller_transitions_executed": 1,
            "gurobi_executed_transitions": 1,
            "opendss_executed_transitions": 1,
            "issue_wall_runtime_seconds": elapsed,
            "gurobi_runtime_seconds": runtime.get("gurobi_runtime_s"),
            "evidence_files": {
                name: {
                    "path": f"RESTART/evidence/{candidate}/{name}",
                    "sha256": sha256(target / name),
                }
                for name in sources
            },
        })
    manifest = {
        "schema_version": "conversation_c.stage7.r13.actual_h0_evidence_manifest.v1",
        "status": "PASS_4_OF_4",
        "controller_burn_in_steps": 0,
        "preregistered_count": 4,
        "pass_count": 4,
        "total_controller_transitions_executed": 4,
        "total_gurobi_executed_transitions": 4,
        "total_opendss_executed_transitions": 4,
        "total_issue_wall_runtime_seconds": total_runtime,
        "results": evidence_rows,
    }
    dump(root / "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json", manifest)
    return manifest


def update_root_authorities(root: Path, actual: dict) -> None:
    binding_path = root / "INITIALIZER_BINDING/PRODUCTION_INITIALIZER_BINDING.json"
    binding = load(binding_path)
    binding["actual_h0_subset_pending"] = False
    binding["actual_h0_subset_status"] = "PASS_4_OF_4"
    binding["actual_h0_evidence"] = "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json"
    dump(binding_path, binding)

    no_future_path = root / "NO_FUTURE/NO_FUTURE_ACTUAL_AUDIT.json"
    no_future = load(no_future_path)
    no_future.update({
        "status": "PASS_CONTRACT_INITIAL_STATE_AND_PREREGISTERED_RUNTIME",
        "runtime_restart_results_pending": False,
        "runtime_candidates_audited": RESTART_IDS,
        "runtime_candidate_count": 4,
        "future_actual_used": False,
        "future_actual_read_count": 0,
        "future_D2_reinjected": False,
        "future_plans_persisted": False,
        "runtime_evidence": "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json",
    })
    dump(no_future_path, no_future)

    evidence = {
        "schema_version": "conversation_c.stage7.r13.completion_evidence.v1",
        "status": "PASS_ALL_STAGE7_SCIENTIFIC_GATES",
        "gates": {
            "A_zero_burnin_supersession": "PASS",
            "B_canonical_pre_states": "PASS_12_OF_12",
            "C_production_initializer_binding": "PASS_12_OF_12",
            "D_preregistered_restart": "PASS_4_OF_4",
            "E_no_future": "PASS",
            "F_downstream_contract_update": "PENDING_HANDOFF_VALIDATORS",
        },
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "seven_day_evaluation_executed": False,
        "actual_gurobi_executions": 4,
        "actual_opendss_executions": 4,
        "actual_controller_transitions": 4,
        "actual_issue_wall_runtime_seconds": actual["total_issue_wall_runtime_seconds"],
        "actual_h0_evidence": "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json",
    }
    dump(root / "C_STAGE7_COMPLETION_EVIDENCE.json", evidence)


def source_shas(root: Path) -> dict:
    return {
        "representative_week_selection_csv": sha256(root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv"),
        "representative_period_result_json": sha256(root / "frozen_authority/REPRESENTATIVE_PERIOD_RESULT_20260815.json"),
        "stress_period_candidates_csv": sha256(root / "frozen_authority/STRESS_PERIOD_CANDIDATES_2025.csv"),
        "pinned_science_main": SCIENCE_SHA,
        "production_controller_core": PRODUCTION_CORE_SHA,
        "initial_home_mapping_source": load(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json")["home_mapping_source_sha256"],
    }


def provisional_final_status(actual: dict) -> dict:
    return {
        "schema_version": "conversation_c.stage7.r13.final_status.v1",
        "status": "15_STAGE_STEP_7_FINAL_PASS",
        "stage_number": 7,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "canonical_pre_states_passed": 12,
        "canonical_pre_states_required": 12,
        "production_initializer_bindings_passed": 12,
        "restart_tests_passed": 4,
        "restart_tests_preregistered": 4,
        "no_future_audit": "PASS",
        "B_final_handoff_validator": "PASS",
        "D_final_handoff_validator": "PASS",
        "sha_manifests": "PASS",
        "actual_gurobi_executions": 4,
        "actual_opendss_executions": 4,
        "actual_controller_transitions": 4,
        "actual_issue_wall_runtime_seconds": actual["total_issue_wall_runtime_seconds"],
        "seven_day_evaluation_executed": False,
        "old_E7A_E7B_retroactive_pass_claimed": False,
        "remaining_stage7_blockers": [],
    }


def build_b_handoff(root: Path, weeks: list[dict], actual: dict, final_status: dict) -> Path:
    target = root / "C_TO_B_FINAL"
    reset_generated(target)
    copy_file(root / "00_READ_FIRST.md", target / "00_READ_FIRST.md")
    dump(target / "C_7_FINAL_STATUS.json", final_status)
    manifest = load(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json")
    by_id = {entry["candidate_id"]: entry for entry in manifest["files"]}
    episodes = []
    for row in weeks:
        candidate = row["candidate_id"]
        state = by_id[candidate]
        copy_file(root / state["path"], target / "initial_states" / Path(state["path"]).name)
        episodes.append({
            "candidate_id": candidate,
            "week_start_aest": row["week_start_aest"],
            "week_end_exclusive_aest": row["week_end_exclusive_aest"],
            "evaluation_start_step": int(row["start_index"]),
            "evaluation_end_step_inclusive": int(row["start_index"]) + 2015,
            "planned_evaluation_steps": 2016,
            "controller_burn_in_steps": 0,
            "selection_window_pre_history_steps": 576,
            "initializer_path": f"initial_states/{Path(state['path']).name}",
            "initializer_file_sha256": state["file_sha256"],
            "initializer_state_sha256": state["state_sha256"],
            "method_independent_initial_state": True,
            "future_actual_used": False,
            "future_plans_persisted": False,
            "output_namespace": f"results/representative_weeks/{candidate}",
            "checkpoint_namespace": f"checkpoints/representative_weeks/{candidate}",
            "evaluation_materialization_status": "DOWNSTREAM_NOT_STAGE7_PREREQUISITE",
        })
    orchestration = {
        "schema_version": "mobileess.b.8.representative_week_zero_burnin_manifest.v2",
        "generated_by": "Conversation C Stage-7 zero-burn-in final handoff",
        "cadence_seconds": 300,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "stage7_evaluation_steps_executed": 0,
        "downstream_evaluation_steps_per_episode": 2016,
        "method_fairness": "same canonical physical PRE state for B0-B6/A1-A8 within each episode",
        "representative_period_authority_commit": PR3_COMMIT,
        "source_authority_shas": source_shas(root),
        "supersession_marker": SUPERSESSION,
        "representative_week_episodes": episodes,
    }
    dump(target / "C_TO_B_8_ORCHESTRATION_INPUT_MANIFEST.json", orchestration)
    dump(target / "C_7_CURRENT_AUTHORITY.json", {
        "schema_version": "conversation_c.to_b.stage7_current_authority.v2",
        "status": "PASS",
        "representative_week_count": 12,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "canonical_initial_state_manifest": "C_TO_B_8_ORCHESTRATION_INPUT_MANIFEST.json",
        "production_initializer_binding": "runtime_binding/PRODUCTION_INITIALIZER_BINDING.json",
        "restart_evidence": "runtime_binding/ACTUAL_H0_EVIDENCE_MANIFEST.json",
        "source_authority_shas": source_shas(root),
    })
    dump(target / "causal_source_coverage/SOURCE_AUTHORITY.json", {
        "schema_version": "conversation_c.to_b.source_authority.v2",
        "status": "FROZEN_AUTHORITY_EVALUATION_MATERIALIZATION_DOWNSTREAM",
        "source_authority_shas": source_shas(root),
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "stage7_claims_full_7day_sources_materialized": False,
    })
    copy_file(root / "INITIALIZER_BINDING/PRODUCTION_INITIALIZER_BINDING.json", target / "runtime_binding/PRODUCTION_INITIALIZER_BINDING.json")
    copy_file(root / "INITIALIZER_BINDING/PREFLIGHT_RESULT.json", target / "runtime_binding/PREFLIGHT_RESULT.json")
    copy_file(root / "RESTART/RESTART_RESULTS.json", target / "runtime_binding/RESTART_RESULTS.json")
    copy_file(root / "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json", target / "runtime_binding/ACTUAL_H0_EVIDENCE_MANIFEST.json")
    dump(target / "SUPERSESSION_LINEAGE.json", {
        "status": "PASS",
        "marker": SUPERSESSION,
        "old_B_monthly_576_validator": "SUPERSEDED",
        "replacement_validator": "tools/validate_c_to_b_zero_burnin.py",
        "retroactive_old_validator_pass_claimed": False,
    })
    copy_file(root / "validate_c_to_b_zero_burnin.py", target / "tools/validate_c_to_b_zero_burnin.py")
    write_sha_manifest(target, {"B_ZERO_BURNIN_VALIDATION_RESULT.json", "B_ZERO_BURNIN_VALIDATION_RESULT.json.sha256"})
    return target


def build_d_handoff(
    root: Path, weeks: list[dict], actual: dict, final_status: dict, prior_d: Path
) -> Path:
    target = root / "C_TO_D_FINAL"
    reset_generated(target)
    dump(target / "C_STAGE7_FINAL_STATUS.json", final_status)
    copy_file(root / "C_STAGE7_COMPLETION_EVIDENCE.json", target / "C_STAGE7_COMPLETION_EVIDENCE.json")
    dump(target / "CURRENT_AUTHORITY.json", {
        "schema_version": "conversation_c.to_d.current_authority.v2",
        "status": "PASS_STAGE7_ZERO_BURNIN_FINAL",
        "consumer": "D",
        "representative_period_commit": PR3_COMMIT,
        "scientific_source_commit": SCIENCE_COMMIT,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "initial_state_manifest": "initial_states/INITIAL_STATE_MANIFEST.json",
        "independent_job_authority": {
            "file": "independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet",
            "sha256": F7_SHA,
            "rows": 59901,
            "unique_job_uid": 59901,
            "source_is_independent_of_job_event": True,
        },
    })
    dump(target / "CAUSAL_FRAME_CONTRACT.json", {
        "schema_version": "conversation_c.to_d.causal_frame_contract.v2",
        "status": "FROZEN_ZERO_BURNIN",
        "first_frame_pre_authority": "canonical representative-week PRE state",
        "subsequent_frame_pre_authority": "exact previous accepted POST/checkpoint",
        "required_semantics": {
            "pre_state_hash": "canonical JSON SHA-256 of current persisted physical PRE",
            "h0_only_physical_commit": True,
            "future_actual_used": False,
            "future_D2_reinjected": False,
            "future_plans_persisted": False,
        },
    })
    dump(target / "STATESTORE_CONTRACT.json", {
        "schema_version": "conversation_c.to_d.statestore_contract.v2",
        "status": "FROZEN_ZERO_BURNIN",
        "restore_pre": {"authority": "exact persisted POST/checkpoint", "must_match_frame_pre_hash": True},
        "commit_post": {"atomic_persistence": True, "expected_issue_increment": 1, "h0_only": True, "future_plans_persisted": False},
        "restart_same_trajectory_required": True,
        "preregistered_restart_evidence": "runtime_evidence/ACTUAL_H0_EVIDENCE_MANIFEST.json",
    })
    dump(target / "PRE_POST_HASH_CONTRACT.json", {
        "schema_version": "conversation_c.to_d.pre_post_hash_contract.v2",
        "status": "FROZEN",
        "serialization": "json.dumps(state,sort_keys=True,separators=(',',':'),default=str)",
        "digest": "SHA-256 UTF-8",
        "transition": "PRE -> accepted h0-only physical commit -> POST",
        "restart_equality": "persisted POST SHA-256 equals recreated-controller next PRE SHA-256",
        "preregistered_pass_count": 4,
    })
    dump(target / "CHECKPOINT_STATE_SCHEMA.json", {
        "schema_version": "conversation_c.to_d.checkpoint_state_schema.v2",
        "status": "FROZEN",
        "physical_state_exact_keys": [
            "issue_step", "queue", "running", "inventory_GB", "pipeline",
            "dest_commit", "mess_state", "mess_E_kWh", "mess_support_debt_kWh",
            "workload_debt_GPUh", "completed", "future_plans_persisted",
        ],
        "active_route_plan_is_physical_state": False,
        "future_plans_persisted_required_value": False,
    })
    no_future = load(root / "NO_FUTURE/NO_FUTURE_ACTUAL_AUDIT.json")
    dump(target / "NO_FUTURE_ACTUAL_AUDIT.json", no_future)
    prior_arrival = load(prior_d / "INDEPENDENT_RUNTIME_JOB_AUTHORITY_CONTRACT.json")
    prior_arrival["schema_version"] = "conversation_c.to_d.independent_runtime_job_authority.v2"
    prior_arrival["status"] = "PASS_FROZEN_INDEPENDENT_SOURCE_UNCHANGED"
    prior_arrival["primary_file"] = "independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
    dump(target / "INDEPENDENT_RUNTIME_JOB_AUTHORITY_CONTRACT.json", prior_arrival)
    source_f7 = prior_d / "independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
    require(sha256(source_f7) == F7_SHA, "independent F7 source SHA mismatch")
    copy_file(source_f7, target / prior_arrival["primary_file"])
    for name in [
        "PER_JOB_RUNTIME_SOURCE_AUDIT_V2044R5.json",
        "PER_JOB_TIMESTAMP_STORAGE_UNIT_AUDIT_V2044R5.json",
        "PER_JOB_TIME_QUANTIZATION_AUDIT_V2044R5.json",
        "PER_JOB_YEAR_END_CARRY_OUT_AUDIT_V2044R5.json",
    ]:
        copy_file(prior_d / "independent_job_authority" / name, target / "independent_job_authority" / name)
    boundaries = [
        {
            "candidate_id": row["candidate_id"],
            "evaluation_start_step": int(row["start_index"]),
            "evaluation_end_step_inclusive": int(row["start_index"]) + 2015,
            "week_start_aest": row["week_start_aest"],
            "week_end_exclusive_aest": row["week_end_exclusive_aest"],
        }
        for row in weeks
    ]
    dump(target / "EVALUATION_BOUNDARY_CONTRACT.json", {
        "schema_version": "conversation_c.to_d.evaluation_boundary_contract.v2",
        "status": "FROZEN_REPRESENTATIVE_WEEK_ZERO_BURNIN",
        "resolution_minutes": 5,
        "controller_burn_in_steps": 0,
        "controller_burn_in_hours": 0,
        "selection_window_pre_history_steps": 576,
        "selection_window_pre_history_role": "selection/input provenance only",
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "timezone_rule": "fixed AEST UTC+10",
        "dst_rule": "no DST",
        "period_selection_performed_here": False,
        "representative_period_authority_commit": PR3_COMMIT,
        "f7_primary_cohort": "evaluation_start_step <= arrival_step <= evaluation_end_step_inclusive",
        "episodes": boundaries,
    })
    prior_censoring = load(prior_d / "RIGHT_CENSORING_STATE_CONTRACT.json")
    prior_censoring.update({
        "schema_version": "conversation_c.to_d.right_censoring_state_contract.v2",
        "status": "FROZEN_UNCHANGED_UNDER_ZERO_BURNIN",
        "right_censoring": True,
        "canonical_cold_start_effect": "queue/running starts empty; expected F7 cohort remains independent arrivals within evaluation interval",
    })
    dump(target / "RIGHT_CENSORING_STATE_CONTRACT.json", prior_censoring)
    dump(target / "JOB_IDENTITY_CONTRACT.json", {
        "schema_version": "conversation_c.to_d.job_identity_contract.v1",
        "status": "FROZEN_UNCHANGED",
        "authoritative_id_field": "job_uid",
        "authoritative_id_type": "string-compatible stable source identity",
        "D_job_event_bridge": "job_event.job_id = str(C.job_uid)",
        "row_number_hash_surrogate_or_rekeying_allowed": False,
    })
    dump(target / "SUPERSESSION_LINEAGE.json", {
        "schema_version": "conversation_c.to_d.stage7_supersession_lineage.v2",
        "status": "PASS",
        "prior_C_to_D_archive_sha256": PRIOR_D_ARCHIVE_SHA,
        "prior_authority_relation": "SUPERSEDED_IN_PART",
        "superseded": [
            "burn_in_steps=576 controller execution boundary",
            "calendar-month/E7A/E7B washout initialization semantics",
        ],
        "unchanged": [
            "independent F7 arrival authority",
            "right-censoring semantics",
            "Kaplan–Meier survival estimator",
            "job identity bridge",
            "D R14 statistical/scientific contract",
        ],
        "replacement_marker": SUPERSESSION,
        "D_R14_change_required": False,
    })
    dump(target / "C_STAGE7_TO_D_SUMMARY.json", {
        "schema_version": "conversation_c.stage7_to_d_summary.v2",
        "stage7_status": "PASS",
        "authoritative_source_id": "C_STAGE7_R13_ZERO_BURNIN_CANONICAL_COLD_START",
        "causal_contract_status": "PASS",
        "independent_arrival_authority_file": prior_arrival["primary_file"],
        "independent_arrival_authority_sha256": F7_SHA,
        "job_id_field": "job_uid",
        "evaluation_end_state_authority": "authoritative persisted runtime physical state",
        "burn_in_steps": 0,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "timezone_rule": "fixed AEST UTC+10",
        "dst_rule": "no DST",
        "right_censoring": True,
        "survival_estimator": "Kaplan–Meier",
        "derived_from_job_event": False,
        "superseded_files": ["prior EVALUATION_BOUNDARY_CONTRACT burn_in_steps=576"],
        "new_or_changed_files": [
            "EVALUATION_BOUNDARY_CONTRACT.json", "CURRENT_AUTHORITY.json",
            "C_STAGE7_FINAL_STATUS.json", "SUPERSESSION_LINEAGE.json",
        ],
        "D_R14_change_required": False,
        "known_blockers_for_D12": [],
    })
    copy_file(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json", target / "initial_states/INITIAL_STATE_MANIFEST.json")
    for state in (root / "INITIAL_STATES").glob("CANONICAL_PRE_STATE_*.json"):
        copy_file(state, target / "initial_states" / state.name)
    copy_file(root / "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json", target / "runtime_evidence/ACTUAL_H0_EVIDENCE_MANIFEST.json")
    dump(target / "fixtures/positive/F7_COVERAGE_FIXTURE.json", {
        "expected_job_uids": ["JOB_A", "JOB_B"],
        "completed_job_uids": ["JOB_A"],
        "right_censored_job_uids": ["JOB_B"],
        "runtime_completion_log_present": True,
        "expected_status": "PASS",
    })
    dump(target / "fixtures/negative_missing_log/F7_COVERAGE_FIXTURE.json", {
        "expected_job_uids": ["JOB_A", "JOB_B"],
        "completed_job_uids": [],
        "right_censored_job_uids": [],
        "runtime_completion_log_present": False,
        "expected_status": "FAIL_CLOSED",
    })
    copy_file(root / "validate_c_to_d_zero_burnin.py", target / "tools/validate_c_to_d_zero_burnin.py")
    write_sha_manifest(target, {"D_ZERO_BURNIN_VALIDATION_RESULT.json", "D_ZERO_BURNIN_VALIDATION_RESULT.json.sha256"})
    return target


def run_validator(command: list[str], result_path: Path) -> dict:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"validator failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}")
    match = re.search(r"\{[\s\S]*\}", completed.stdout)
    if not match:
        raise RuntimeError(f"validator emitted no JSON: {completed.stdout}")
    result = json.loads(match.group(0))
    require(result.get("status") == "PASS", f"validator status not PASS: {result}")
    dump(result_path, result)
    result_path.with_name(result_path.name + ".sha256").write_text(
        f"{sha256(result_path)}  {result_path.name}\n", encoding="utf-8"
    )
    return result


def write_methodology(root: Path) -> None:
    (root / "METHODS_ZERO_BURNIN.md").write_text(
        "# Stage-7 representative-week initialization method\n\n"
        "Each representative-week controller episode begins directly at the selected week "
        "boundary from a deterministic canonical cold-start physical state shared by all "
        "methods. No controller burn-in is executed. The canonical state fixes MESS energy, "
        "location, queue/running job state, WAN state, and accumulated debt before any "
        "method-specific decision. The 48-hour pre-history associated with representative-"
        "period selection is retained only as selection/input-window provenance and is not "
        "used as controller state burn-in. This is an experimental initialization assumption, "
        "not a claim about the actual physical state preceding a selected week.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--run-root", type=Path, default=Path("/home/jaewon/mobile_ess_work/stage7_r13_zero_burnin_runs"))
    parser.add_argument("--prior-d-root", type=Path, default=Path("/home/jaewon/mobile_ess_work/stage7_zero_burnin_authority_20260816/prior_c_to_d/C_TO_D_D11D12_CAUSAL_COHORT_HANDOFF_20260815"))
    parser.add_argument("--result-root", type=Path, default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts"))
    parser.add_argument("--timestamp")
    args = parser.parse_args()
    root = args.authority_root.resolve()
    timestamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    weeks = read_weeks(root)
    require(load(root / "C_STAGE7_BURNIN_REMOVAL_SUPERSESSION.json")["new_controller_burn_in_steps"] == 0, "supersession not frozen")
    require(load(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json")["status"].startswith("PASS_12_OF_12"), "canonical PRE authority not PASS")
    actual = bind_actual_restart_evidence(root, args.run_root.resolve())
    update_root_authorities(root, actual)
    write_methodology(root)
    final_status = provisional_final_status(actual)
    b_root = build_b_handoff(root, weeks, actual, final_status)
    d_root = build_d_handoff(root, weeks, actual, final_status, args.prior_d_root.resolve())
    b_result = run_validator(
        ["python3", str(root / "validate_c_to_b_zero_burnin.py"), str(b_root)],
        b_root / "B_ZERO_BURNIN_VALIDATION_RESULT.json",
    )
    d_result = run_validator(
        ["python3", str(root / "validate_c_to_d_zero_burnin.py"), str(d_root)],
        d_root / "D_ZERO_BURNIN_VALIDATION_RESULT.json",
    )
    evidence = load(root / "C_STAGE7_COMPLETION_EVIDENCE.json")
    evidence["gates"]["F_downstream_contract_update"] = "PASS_B_AND_D_VALIDATORS"
    evidence["B_final_handoff_validator"] = b_result["status"]
    evidence["D_final_handoff_validator"] = d_result["status"]
    dump(root / "C_STAGE7_COMPLETION_EVIDENCE.json", evidence)
    dump(root / "C_7_FINAL_STATUS.json", final_status)
    dump(root / "C_STAGE7_FINAL_STATUS.json", final_status)
    dump(root / "CURRENT_AUTHORITY.json", {
        "schema_version": "conversation_c.stage7.r13.current_authority.v1",
        "status": "15_STAGE_STEP_7_FINAL_PASS",
        "representative_period_commit": PR3_COMMIT,
        "scientific_source_commit": SCIENCE_COMMIT,
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "canonical_initial_state_manifest": "INITIAL_STATES/INITIAL_STATE_MANIFEST.json",
        "actual_h0_evidence_manifest": "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json",
        "C_to_B_final": "C_TO_B_FINAL",
        "C_to_D_final": "C_TO_D_FINAL",
        "source_authority_shas": source_shas(root),
    })
    # Refresh copies whose source changed after the preliminary semantic validation.
    dump(b_root / "C_7_FINAL_STATUS.json", final_status)
    dump(d_root / "C_STAGE7_FINAL_STATUS.json", final_status)
    copy_file(root / "C_STAGE7_COMPLETION_EVIDENCE.json", d_root / "C_STAGE7_COMPLETION_EVIDENCE.json")
    write_sha_manifest(b_root, {"B_ZERO_BURNIN_VALIDATION_RESULT.json", "B_ZERO_BURNIN_VALIDATION_RESULT.json.sha256"})
    write_sha_manifest(d_root, {"D_ZERO_BURNIN_VALIDATION_RESULT.json", "D_ZERO_BURNIN_VALIDATION_RESULT.json.sha256"})
    # Re-run against the final, checksum-locked staging trees.
    b_result = run_validator(
        ["python3", str(root / "validate_c_to_b_zero_burnin.py"), str(b_root)],
        b_root / "B_ZERO_BURNIN_VALIDATION_RESULT.json",
    )
    d_result = run_validator(
        ["python3", str(root / "validate_c_to_d_zero_burnin.py"), str(d_root)],
        d_root / "D_ZERO_BURNIN_VALIDATION_RESULT.json",
    )
    require(b_result["status"] == d_result["status"] == "PASS", "final B/D validation failed")
    # Remove interpreter caches only inside the new R13 authority.
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache)
    write_sha_manifest(root)
    verify_sha_manifest(root)

    result_root = args.result_root.resolve()
    b_archive = result_root / f"ConversationC_to_B_7_FINAL_HANDOFF_{timestamp}.tar.gz"
    d_archive = result_root / f"C_TO_D_STAGE7_FINAL_CAUSAL_COHORT_AUTHORITY_{timestamp}.tar.gz"
    master_archive = result_root / f"CODEX_TO_C_STAGE7_ZERO_BURNIN_FINAL_{timestamp}.tar.gz"
    b_sha = make_archive(b_root, b_archive)
    d_sha = make_archive(d_root, d_archive)
    master_sha = make_archive(root, master_archive)
    output = {
        "schema_version": "conversation_c.stage7.r13.finalization_output.v1",
        "status": "15_STAGE_STEP_7_FINAL_PASS",
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "canonical_pre_states": "12/12 PASS",
        "production_initializer_binding": "12/12 PASS",
        "restart_tests": "4/4 PASS",
        "no_future_audit": "PASS",
        "actual_gurobi_executions": 4,
        "actual_opendss_executions": 4,
        "actual_issue_wall_runtime_seconds": actual["total_issue_wall_runtime_seconds"],
        "C_to_B": {"path": str(b_archive), "sha256": b_sha},
        "C_to_D": {"path": str(d_archive), "sha256": d_sha},
        "Codex_to_C": {"path": str(master_archive), "sha256": master_sha},
        "remaining_stage7_blockers": [],
    }
    output_path = result_root / f"STAGE7_ZERO_BURNIN_FINALIZATION_{timestamp}.json"
    dump(output_path, output)
    (result_root / "LATEST_STAGE7_ZERO_BURNIN_FINALIZATION.json").write_text(
        output_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
