#!/usr/bin/env python3
"""Validate six causal M4 exact-grid recovery boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def original_issue(failed_policy: Path, issue: int) -> Path:
    matches = list(failed_policy.glob(
        f"interrupted_attempts/*/issue_{issue:06d}_grid_hard_pre_replan/issue_{issue:06d}"
    ))
    direct = failed_policy / "engine" / f"issue_{issue:06d}"
    if not matches and direct.joinpath("A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json").is_file():
        matches.append(direct)
    if len(matches) != 1:
        raise RuntimeError(f"original issue-{issue} attempt cardinality={len(matches)}")
    return matches[0]


def validate_boundary(
    *, failed_policy: Path, replay_policy: Path, issue: int,
    profile: str, p_radius: float, q_radius: float,
    original_voltage_violations: int, original_line_violations: int,
    correction_rounds: int = 1, secondary_scope: str | None = None,
    q_frozen: bool = False, boundary_id: str | None = None,
) -> dict:
    original = original_issue(failed_policy, issue)
    replay = replay_policy / "engine" / f"issue_{issue:06d}"
    original_pre_path = original / "BUILD7C_PRECOMMIT_STATE.json"
    original_candidates_path = original / "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json"
    original_exact_path = original / f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
    replay_pre_path = replay / "BUILD7C_PRECOMMIT_STATE.json"
    replay_candidates_path = replay / "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json"
    recovery_path = replay / "A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json"
    fresh_path = replay / f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
    policy_audit_path = replay / "POLICY_ISSUE_AUDIT.json"
    commit_path = replay / "A_B10_COMMIT_MARKER.json"

    original_pre = load(original_pre_path)
    original_candidates = load(original_candidates_path)
    original_exact = load(original_exact_path)
    replay_pre = load(replay_pre_path)
    replay_candidates = load(replay_candidates_path)
    recovery = load(recovery_path)
    fresh = load(fresh_path)
    policy_audit = load(policy_audit_path)
    commit = load(commit_path)

    original_rows = original_candidates.get("candidates", [])
    replay_rows = replay_candidates.get("candidates", [])
    attempts = recovery.get("attempts", [])
    correction = attempts[-1] if attempts else {}
    correction_exact = correction.get("exact_ac", {})
    correction_fast = correction.get("fast_solver", {})
    trust_rows = correction.get("trust_region", [])
    cut_families = [row.get("constraint_family") for row in correction.get("cuts", [])]
    radii = {
        coordinate: {float(row.get("radius_kw_kvar")) for row in trust_rows
                     if row.get("coordinate") == coordinate}
        for coordinate in ("P", "Q")
    }
    physical_zero_keys = (
        "voltage_violation_count", "line_violation_count",
        "transformer_current_violation_count", "transformer_kva_violation_count",
        "command_error_count",
    )
    checks = {
        "same_causal_pre_state": original_pre.get("sha256") == replay_pre.get("sha256"),
        "same_initial_decision_candidate": (
            bool(original_rows) and bool(replay_rows)
            and original_rows[0].get("decision_candidate_sha256")
            == replay_rows[0].get("decision_candidate_sha256")
        ),
        "original_exact_failure_reproduced": (
            original_exact.get("converged") is True
            and original_exact.get("hard_constraint_pass") is False
            and original_exact.get("voltage_violation_count") == original_voltage_violations
            and original_exact.get("line_violation_count") == original_line_violations
            and attempts[0].get("exact_ac", {}).get("voltage_max_pu")
            == original_exact.get("voltage_max_pu")
            and attempts[0].get("exact_ac", {}).get("line_max_loading_pu")
            == original_exact.get("line_max_loading_pu")
        ),
        "bounded_correction_candidates": (
            replay_candidates.get("candidate_count") == correction_rounds + 1
            and [row.get("stage") for row in replay_rows]
            == ["INITIAL"] + ["AC_CORRECTION"] * correction_rounds
            and recovery.get("max_cut_rounds") == correction_rounds
        ),
        "pre_violation_class_selected_profile": (
            len(trust_rows) == 8
            and {row.get("profile") for row in trust_rows} == {profile}
            and {row.get("selector") for row in trust_rows}
            == {"PRE_RECOVERY_EXACT_VIOLATION_FAMILY"}
            and radii["P"] == {p_radius}
            and radii["Q"] == {q_radius}
            and all(row.get("normalized_model_coefficient") is True for row in trust_rows)
            and all(row.get("feasible_set_expanded") is False for row in trust_rows)
        ),
        "required_exact_cut_families_present": (
            "VOLTAGE" in cut_families
            and (("LINE_CURRENT" in cut_families) == (original_line_violations > 0))
        ),
        "branch_specific_secondary_objective": (
            (
                correction_fast.get("secondary_scope") == secondary_scope
                and correction_fast.get("secondary_objective") == "MIN_NORMALIZED_L1_H0_PQ_CHANGE"
                and correction_fast.get("primary_economic_quality_preserved") is True
                and (not q_frozen or all(
                    before[4] == after[4]
                    for before, after in zip(
                        attempts[0].get("candidate", {}).get("decision_payload", {}).get("mess", []),
                        correction.get("candidate", {}).get("decision_payload", {}).get("mess", []),
                    )
                ))
            ) if secondary_scope else "secondary_scope" not in correction_fast
        ),
        "fresh_exact_ac_pass": (
            fresh.get("converged") is True
            and fresh.get("hard_constraint_pass") is True
            and fresh.get("root_sign_pass") is True
            and all(fresh.get(key) == 0 for key in physical_zero_keys)
            and correction_exact == fresh
        ),
        "atomic_commit": (
            policy_audit.get("status") == "PASS_COMMITTED"
            and commit.get("status") == "COMMITTED"
            and commit.get("issue") == issue
        ),
        "causal_fail_closed_contract": (
            policy_audit.get("future_actual_used") is False
            and recovery.get("future_actual_used") is False
            and recovery.get("hard_limits_relaxed") is False
            and replay_candidates.get("unsafe_action_committed") is False
        ),
    }
    return {
        "boundary_id": boundary_id or str(issue),
        "issue": issue,
        "status": "PASS" if all(checks.values()) else "FAIL_CLOSED",
        "selected_profile": profile,
        "checks": checks,
        "initial_exact": original_exact,
        "fresh_exact": fresh,
        "evidence": {
            "original_pre": {"path": str(original_pre_path), "sha256": sha(original_pre_path)},
            "original_candidates": {"path": str(original_candidates_path), "sha256": sha(original_candidates_path)},
            "original_fresh_exact": {"path": str(original_exact_path), "sha256": sha(original_exact_path)},
            "replay_pre": {"path": str(replay_pre_path), "sha256": sha(replay_pre_path)},
            "replay_candidates": {"path": str(replay_candidates_path), "sha256": sha(replay_candidates_path)},
            "recovery": {"path": str(recovery_path), "sha256": sha(recovery_path)},
            "fresh_exact": {"path": str(fresh_path), "sha256": sha(fresh_path)},
            "policy_audit": {"path": str(policy_audit_path), "sha256": sha(policy_audit_path)},
            "commit_marker": {"path": str(commit_path), "sha256": sha(commit_path)},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--r4-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R4/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--r5-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R5/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--r6-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R6/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--r7-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R7/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--r8-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R8/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--r9-failed-policy", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R9/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--issue3518-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_FINAL_M4_ISSUE3518_REGRESSION_V2_20260818"),
    )
    parser.add_argument(
        "--issue3573-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_FINAL_M4_ISSUE3573_REGRESSION_20260818"),
    )
    parser.add_argument(
        "--issue3574-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_FINAL_M4_ISSUE3574_REGRESSION_20260818"),
    )
    parser.add_argument(
        "--r7-issue3573-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R7PRE_M4_ISSUE3573_SEVERE_LINE_REPLAY_20260818"),
    )
    parser.add_argument(
        "--r8-issue3577-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R8PRE_M4_ISSUE3577_SEVERE_VOLTAGE_REPLAY_20260818"),
    )
    parser.add_argument(
        "--r9-issue3577-replay", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R9PRE_M4_ISSUE3577_RELINEARIZED_Q_REPLAY_20260818"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_M4_ADAPTIVE_GRID_RECOVERY_CURRENT.json"),
    )
    args = parser.parse_args()

    runner = (args.package / "runtime/W02_POLICY_EPISODE_RUNNER.py").resolve()
    runner_text = runner.read_text(encoding="utf-8")
    boundaries = [
        validate_boundary(
            failed_policy=args.r4_failed_policy, replay_policy=args.issue3518_replay,
            issue=3518, profile="LOCAL_VOLTAGE_ONLY", p_radius=10.0, q_radius=10.0,
            original_voltage_violations=2, original_line_violations=0,
            boundary_id="R4_ISSUE3518_LOCAL_VOLTAGE",
        ),
        validate_boundary(
            failed_policy=args.r5_failed_policy, replay_policy=args.issue3573_replay,
            issue=3573, profile="COUPLED_VOLTAGE_LINE", p_radius=100.0, q_radius=50.0,
            original_voltage_violations=2, original_line_violations=7,
            boundary_id="R5_ISSUE3573_COUPLED_VOLTAGE_LINE",
        ),
        validate_boundary(
            failed_policy=args.r6_failed_policy, replay_policy=args.issue3574_replay,
            issue=3574, profile="SEVERE_VOLTAGE_ONLY", p_radius=1100.0, q_radius=0.0,
            original_voltage_violations=9, original_line_violations=0,
            secondary_scope="SEVERE_VOLTAGE_ONLY", q_frozen=True,
            boundary_id="R6_ISSUE3574_SEVERE_VOLTAGE",
        ),
        validate_boundary(
            failed_policy=args.r7_failed_policy, replay_policy=args.r7_issue3573_replay,
            issue=3573, profile="SEVERE_VOLTAGE_POST_LINE", p_radius=1100.0, q_radius=100.0,
            original_voltage_violations=4, original_line_violations=7,
            correction_rounds=2, secondary_scope="SEVERE_VOLTAGE_POST_LINE",
            boundary_id="R7_ISSUE3573_SEVERE_VOLTAGE_LINE_TWO_STAGE",
        ),
        validate_boundary(
            failed_policy=args.r8_failed_policy, replay_policy=args.r8_issue3577_replay,
            issue=3577, profile="SEVERE_VOLTAGE_ONLY", p_radius=1100.0, q_radius=0.0,
            original_voltage_violations=1, original_line_violations=0,
            secondary_scope="SEVERE_VOLTAGE_ONLY", q_frozen=True,
            boundary_id="R8_ISSUE3577_VOLTAGE_ONLY_TAP_RISK",
        ),
        validate_boundary(
            failed_policy=args.r9_failed_policy, replay_policy=args.r9_issue3577_replay,
            issue=3577, profile="SEVERE_VOLTAGE_RELINEARIZED", p_radius=1100.0, q_radius=100.0,
            original_voltage_violations=3, original_line_violations=0,
            correction_rounds=2, secondary_scope="SEVERE_VOLTAGE_RELINEARIZED",
            boundary_id="R9_ISSUE3577_VOLTAGE_ONLY_TWO_STAGE_TAP_RELINEARIZATION",
        ),
    ]
    design_checks = {
        "all_six_exact_failure_boundaries_pass": all(row["status"] == "PASS" for row in boundaries),
        "power_scale_1000_kw_per_model_unit_unchanged": (
            runner_text.count('_c5r4_power_scale_kw_per_model_unit",1000.0') >= 3
        ),
        "adaptive_selector_is_outcome_blind": (
            'if line_violations:' in runner_text
            and '"selector":"PRE_RECOVERY_EXACT_VIOLATION_FAMILY"' in runner_text
        ),
        "severe_voltage_uses_tap_aware_two_stage_q_policy": (
            'AC_RECOVERY_SEVERE_VOLTAGE_Q_TRUST_REGION_KVAR=0.0' in runner_text
            and 'AC_RECOVERY_RELINEARIZED_VOLTAGE_Q_TRUST_REGION_KVAR=100.0' in runner_text
            and 'AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW=1100.0' in runner_text
            and 'trust_profile="SEVERE_VOLTAGE_RELINEARIZED"' in runner_text
            and 'if trust_profile in {"SEVERE_VOLTAGE_ONLY","SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"}:' in runner_text
            and '"secondary_scope":trust_profile' in runner_text
        ),
        "severe_voltage_line_uses_bounded_two_stage_closure": (
            'AC_RECOVERY_SEVERE_LINE_P_TRUST_REGION_KW=1100.0' in runner_text
            and 'AC_RECOVERY_SEVERE_LINE_Q_TRUST_REGION_KVAR=100.0' in runner_text
            and 'AC_RECOVERY_POST_LINE_Q_TRUST_REGION_KVAR=100.0' in runner_text
            and 'protected_line_keys=' in runner_text
            and 'recovery_round_limit=(2 if initial_voltage_severity_pu>' in runner_text
        ),
        "voltage_only_tap_risk_has_separate_threshold": (
            'AC_RECOVERY_SEVERE_VOLTAGE_ONLY_THRESHOLD_PU=5.0e-4' in runner_text
            and 'AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU=2.0e-3' in runner_text
        ),
    }
    status = "PASS" if all(design_checks.values()) else "FAIL_CLOSED"
    output = {
        "schema_version": "mobileess.post_stage15.w02_m4_adaptive_grid_recovery.v1",
        "status": status,
        "root_cause": (
            "A_SINGLE_GLOBAL_TRUST_RADIUS_AND_UNSCOPED_PQ_SECONDARY_OBJECTIVE_CANNOT_"
            "COVER_LOCAL_VOLTAGE_COUPLED_LINE_AND_DISCRETE_REGULATOR_TAP_BOUNDARIES"
        ),
        "correction": (
            "PRE_RECOVERY_EXACT_VIOLATION_CLASS_SELECTS_LOCAL_10_10_COUPLED_LINE_100_50_"
            "OR_SEVERE_VOLTAGE_TWO_STAGE_TAP_RELINEARIZATION_WITH_SCOPED_MINIMUM_INTERVENTION"
        ),
        "runner": {"path": str(runner), "sha256": sha(runner)},
        "design_checks": design_checks,
        "boundaries": boundaries,
        "full_W02_executed": False,
        "scientific_solve_count_by_this_validator": 0,
        "opendss_solve_count_by_this_validator": 0,
        "hard_limits_relaxed": False,
        "power_scale_changed": False,
        "future_actual_used": False,
    }
    write(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
