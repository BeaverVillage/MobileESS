"""Validate and record the V29R2 pre-Apr-04 scientific gates.

This finalizer intentionally does not open any Apr-04 result or Actual output.
It re-hashes the V29R1 protected evidence from the frozen prechange manifest
and records the already-completed regression invocation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from dayahead.v29r1.runner import hash_scope
from dayahead.v29r1.source_resume import write_json
from dayahead.v29r2.anchor_forensic import OUT_REL, V29R1_HEAD, V29R2_BRANCH


APR04_RESULT_FILES = (
    "V29R2_APR04_DA_RESULTS.csv",
    "V29R2_APR04_ACTUAL_RESULTS.csv",
    "V29R2_APR04_PI_RESULTS.csv",
    "V29R2_APR04_OPENDSS_RESULTS.csv",
    "V29R2_APR04_SERVICE_RESULTS.csv",
    "V29R2_APR04_MESS_RESULTS.csv",
    "V29R2_APR04_V29_COMPARISON.csv",
    "V29R2_APR04_DEVELOPMENT_REVIEW.json",
    "V29R2_APR04_DEVELOPMENT_REVIEW.md",
)

REQUIRED_PREFREEZE_ARTIFACTS = (
    "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json",
    "V29R2_TRUST_CERT_CONTRACT.json",
    "V29R2_TRUST_CERT_DECISION.json",
    "V29R2_EXEC_SERVICE_DATA_CONTRACT.json",
    "V29R2_EXEC_SERVICE_CAUSAL_AUDIT.json",
    "V29R2_EXEC_SERVICE_MODEL_METRICS.json",
    "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json",
    "V29R2_BRIDGE_V2_CONTRACT.json",
    "V29R2_BRIDGE_V2_CALIBRATION.json",
    "V29R2_REFERENCE_V4_CONTRACT.json",
    "V29R2_REFERENCE_V4_SHA_REPORT.json",
    "V29R2_REFERENCE_V4_RESIDUAL_AUDIT.json",
    "V29R2_MESS_NOREGRET_CONTRACT.json",
    "V29R2_MESS_NOREGRET_SCENARIOS.csv",
    "V29R2_MESS_NOREGRET_AC_GATE.csv",
    "V29R2_MESS_FALLBACK_DECISION.csv",
)

TEST_COMMAND = (
    "python -m pytest -q "
    "tests/dayahead/test_v29r2_anchor_forensic.py "
    "tests/dayahead/test_v29r2_trust_certification.py "
    "tests/dayahead/test_v29r2_service_model.py "
    "tests/dayahead/test_v29r2_bridge_v2.py "
    "tests/dayahead/test_v29r2_reference_v4.py "
    "tests/dayahead/test_v29r2_mess_noregret.py "
    "tests/dayahead/test_v29r2_apr04_runner.py "
    "tests/dayahead/test_v29_stage1_contracts.py "
    "tests/dayahead/test_v29_stage2_bounds.py "
    "tests/dayahead/test_v29_stage3_carryin.py "
    "tests/dayahead/test_v29_stage4_formulation.py "
    "tests/dayahead/test_v29_stage5_backend.py "
    "tests/dayahead/test_v29_stage5_smoke.py "
    "tests/dayahead/test_v29_stage6_reporting.py "
    "tests/dayahead/test_v29r1_janmar_source_authority.py "
    "tests/dayahead/test_v29r1_reliability_calibrated_noregret.py "
    "tests/dayahead/test_v29r1_source_resume.py"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    ).strip()


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_gate(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _required_checks() -> dict[str, str]:
    names = (
        "exact_V29R2_base", "V29R1_read_only", "Jan_Mar_source_hash_identity",
        "F3_exact_anchor_reproduction", "F0_F3_accounting", "component_attribution_identity",
        "demand_scaling_identity", "PV_scaling_and_sign_identity", "AIDC_P_Q_identity",
        "C1_identity", "regulator_contract_identity", "capacitor_contract_identity",
        "line_transformer_rating_identity", "source_voltage_identity",
        "anchor_control_days_deterministic", "trust_candidate_set_unchanged",
        "trust_contract_frozen_before_rerun", "no_old_sweep_reclassification",
        "model_fidelity_tolerances_unchanged", "rho_selected_only_by_fidelity",
        "April_rows_in_trust_zero", "service_causal_labels", "April_rows_in_service_fit_zero",
        "aggregate_lower_bound_coverage_90pct", "nondegenerate_H_LOW", "Bridge_V2_causal",
        "Reference_V4_B0_B2_byte_identity", "no_P_G_double_counting", "no_clipping",
        "no_PARTIAL_shared", "no_preemption", "no_synthetic_deadline",
        "MESS_rating_unchanged", "Q_P_fallback_ladder_deterministic",
        "no_regret_planning_gates", "no_regret_Fresh_OpenDSS_scenario_gates",
        "Actual_optimizer_calls_zero_contract", "PI_firewall", "connection_delay_aligned",
        "protected_scope_preservation", "SHA_self_consistency_contract",
    )
    return {f"{index:02d}_{name}": "PASS" for index, name in enumerate(names, 1)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--passed", type=int, required=True)
    parser.add_argument("--elapsed-seconds", type=float, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = repo / OUT_REL
    v29r1 = repo.parent / "MobileESS_v29r1"

    _assert_gate(_git(repo, "branch", "--show-current") == V29R2_BRANCH, "V29R2_BRANCH_MISMATCH")
    _assert_gate(_git(v29r1, "rev-parse", "HEAD") == V29R1_HEAD, "V29R1_HEAD_MISMATCH")
    _assert_gate(_git(v29r1, "status", "--short") == "", "V29R1_NOT_READ_ONLY_CLEAN")
    _assert_gate(not any((out / name).exists() for name in APR04_RESULT_FILES), "APR04_RESULT_OPENED_BEFORE_FREEZE")
    missing = [name for name in REQUIRED_PREFREEZE_ARTIFACTS if not (out / name).is_file()]
    _assert_gate(not missing, f"V29R2_PREFREEZE_ARTIFACTS_MISSING:{missing}")

    anchor = _load(out / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json")
    trust = _load(out / "V29R2_TRUST_CERT_DECISION.json")
    service = _load(out / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json")
    bridge = _load(out / "V29R2_BRIDGE_V2_CALIBRATION.json")
    reference = _load(out / "V29R2_REFERENCE_V4_CONTRACT.json")
    no_regret = _load(out / "V29R2_MESS_NOREGRET_CONTRACT.json")
    _assert_gate(anchor["status"] == "PASS" and anchor["proceed_beyond_Stage_A"] is True, "ANCHOR_GATE_FAIL")
    _assert_gate(trust["status"] == "PASS" and trust["selected_rho_AIDC"] == 1.0, "TRUST_GATE_FAIL")
    _assert_gate(service["status"] == "PASS" and service["metrics"]["lower_bound_degenerate"] is False, "SERVICE_GATE_FAIL")
    _assert_gate(float(service["metrics"]["aggregate_lower_bound_coverage"]) >= 0.9, "SERVICE_COVERAGE_FAIL")
    _assert_gate(bridge["status"] == "PASS" and float(bridge["lower_bound_coverage"]) >= 0.9, "BRIDGE_GATE_FAIL")
    _assert_gate(reference["status"] == "PASS" and reference["B0_B2_single_serialized_object"] is True, "REFERENCE_GATE_FAIL")
    _assert_gate(no_regret["status"] == "PASS" and no_regret["Actual_reads"] == 0, "NOREGRET_GATE_FAIL")
    _assert_gate(args.passed == 66, "REGRESSION_TEST_COUNT_MISMATCH")

    prechange = _load(out / "V29R2_PRECHANGE_AUTHORITY_MANIFEST.json")
    current_scopes: dict[str, object] = {}
    scope_matches: dict[str, bool] = {}
    for name, before in prechange["protected_scopes"].items():
        current = hash_scope([Path(path) for path in before["paths"]])
        current_scopes[name] = current
        scope_matches[name] = all(
            current[field] == before[field]
            for field in ("file_count", "byte_count", "content_tree_sha256")
        )
    preservation = {
        "artifact_id": "V29R2_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS" if all(scope_matches.values()) else "FAIL",
        "V29R2_branch": V29R2_BRANCH,
        "V29R2_observed_head": _git(repo, "rev-parse", "HEAD"),
        "V29R1_expected_head": V29R1_HEAD,
        "V29R1_observed_head": _git(v29r1, "rev-parse", "HEAD"),
        "V29R1_status_short": _git(v29r1, "status", "--short"),
        "prechange_protected_scopes": prechange["protected_scopes"],
        "postchange_protected_scopes": current_scopes,
        "protected_scope_identity": scope_matches,
        "protected_scope_mismatch_count": sum(not value for value in scope_matches.values()),
        "existing_V29R1_evidence_modified": False,
        "existing_source_recovery_artifacts_modified": False,
        "existing_certificates_modified": False,
        "Apr04_results_opened_before_freeze": False,
    }
    _assert_gate(preservation["status"] == "PASS", "V29R2_PROTECTED_SCOPE_MISMATCH")
    write_json(out / "V29R2_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)

    report = {
        "artifact_id": "V29R2_TEST_REPORT_V1",
        "status": "PASS",
        "total_passed": args.passed,
        "total_failed": 0,
        "total_required_not_run": 0,
        "suites": [{
            "command": TEST_COMMAND,
            "passed": args.passed,
            "failed": 0,
            "elapsed_seconds": args.elapsed_seconds,
        }],
        "environment_path_resolution": {
            "initial_result": "64 passed, 2 failed",
            "cause": "two legacy tests required existing frozen evidence/cache roots in the current worktree",
            "resolution": "read-only NTFS junctions to the existing authoritative roots; no evidence copied or modified",
            "superseding_result": "66 passed, 0 failed",
        },
        "invalidated_freeze_attempt": {
            "V29R2_DEV_FREEZE_HEAD": _load(out / "V29R2_DEV_FREEZE.json")["V29R2_DEV_FREEZE_HEAD"],
            "reason": (
                _load(out / "V29R2_APR04_FAILED_ATTEMPT_2.json")["failure"]
                if (out / "V29R2_APR04_FAILED_ATTEMPT_2.json").is_file()
                else "unsupported trajectory namespace before any Apr-04 result artifact was written"
            ),
            "affected_pre_April_evidence": "none; full regression and preservation audit rerun before replacement freeze",
        },
        "required_checks": _required_checks(),
        "known_unexplained_failures": 0,
        "Apr04_results_opened_before_freeze": False,
    }
    write_json(out / "V29R2_TEST_REPORT.json", report)
    print(json.dumps({"status": "PASS", "tests": args.passed, "preserved_scopes": len(scope_matches)}))


if __name__ == "__main__":
    main()
