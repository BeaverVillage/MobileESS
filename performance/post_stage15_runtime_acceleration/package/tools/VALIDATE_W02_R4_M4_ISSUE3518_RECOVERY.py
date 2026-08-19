#!/usr/bin/env python3
"""Validate the exact R4 M4 issue-3518 PRE replay after trust-region correction."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--failed-policy",
        type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R4/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"),
    )
    parser.add_argument(
        "--replay-policy",
        type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R4_M4_ISSUE3518_MARGIN_REPLAY_20260818"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_R4_M4_ISSUE3518_RECOVERY_CURRENT.json"),
    )
    args = parser.parse_args()

    issue = 3518
    archived = list(args.failed_policy.glob(
        "interrupted_attempts/*/issue_003518_grid_hard_pre_replan/issue_003518"
    ))
    if len(archived) != 1:
        raise RuntimeError(f"original issue-3518 attempt cardinality={len(archived)}")
    original_issue = archived[0]
    replay_issue = args.replay_policy / "engine" / f"issue_{issue:06d}"

    original_failure = load(args.failed_policy / "FAILURE.json")
    original_final_recovery_path = args.failed_policy / "engine" / f"issue_{issue:06d}" / "A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json"
    original_final_recovery = load(original_final_recovery_path)
    original_pre = load(original_issue / "BUILD7C_PRECOMMIT_STATE.json")
    original_audit = load(original_issue / "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json")
    original_candidates = original_audit.get("candidates", [])
    replay_pre = load(replay_issue / "BUILD7C_PRECOMMIT_STATE.json")
    replay_audit = load(replay_issue / "POLICY_ISSUE_AUDIT.json")
    replay_recovery = load(replay_issue / "A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json")
    replay_candidates = replay_audit.get("fresh_ac_candidate_attempts", [])
    final_exact = replay_candidates[-1].get("exact_ac", {}) if replay_candidates else {}
    commit = replay_issue / "A_B10_COMMIT_MARKER.json"
    trust_rows = replay_recovery.get("attempts", [{}, {}])[-1].get("trust_region", [])

    checks = {
        "original_r4_failure_reproduced": (
            original_failure.get("status") == "FAIL_CLOSED"
            and original_final_recovery.get("status") == "FAIL_CLOSED_AFTER_SINGLE_SAME_PRE_H54_FULL_REPLAN"
            and original_final_recovery.get("unsafe_action_committed") is False
            and len(original_candidates) == 2
            and [row.get("stage") for row in original_candidates] == ["INITIAL", "AC_CORRECTION"]
        ),
        "same_causal_pre_state": original_pre.get("sha256") == replay_pre.get("sha256"),
        "same_initial_candidate": (
            bool(original_candidates) and bool(replay_candidates)
            and original_candidates[0].get("decision_candidate_sha256")
            == replay_candidates[0].get("decision_candidate_sha256")
        ),
        "one_bounded_correction_candidate": (
            [row.get("stage") for row in replay_candidates] == ["INITIAL", "AC_CORRECTION"]
        ),
        "finite_difference_matched_trust_region": (
            len(trust_rows) == 8
            and all(row.get("radius_kw_kvar") == 10.0 for row in trust_rows)
            and all(row.get("same_radius_as_finite_difference") is True for row in trust_rows)
            and all(row.get("feasible_set_expanded") is False for row in trust_rows)
        ),
        "conservative_voltage_inner_margin": (
            replay_recovery.get("conservative_voltage_cut_margin_pu") == 1.0e-4
            and replay_recovery.get("hard_limits_relaxed") is False
        ),
        "fresh_exact_ac_pass": (
            final_exact.get("converged") is True
            and final_exact.get("hard_constraint_pass") is True
            and final_exact.get("voltage_violation_count") == 0
            and final_exact.get("line_violation_count") == 0
            and final_exact.get("transformer_current_violation_count") == 0
            and final_exact.get("transformer_kva_violation_count") == 0
        ),
        "atomic_commit": replay_audit.get("status") == "PASS_COMMITTED" and commit.is_file(),
        "causal_safety": (
            replay_audit.get("future_actual_used") is False
            and replay_recovery.get("future_actual_used") is False
            and replay_recovery.get("max_cut_rounds") == 1
        ),
    }
    runner = (args.package / "runtime/W02_POLICY_EPISODE_RUNNER.py").resolve()
    status = "PASS" if all(checks.values()) else "FAIL_CLOSED"
    output = {
        "schema_version": "mobileess.post_stage15.w02_r4_m4_issue3518_recovery.v1",
        "status": status,
        "root_cause": "LOCAL_FINITE_DIFFERENCE_CUT_WAS_SOLVED_WITHOUT_A_MATCHED_TRUST_REGION",
        "runner": {"path": str(runner), "sha256": sha(runner)},
        "issue": issue,
        "checks": checks,
        "original_failure": {"path": str(args.failed_policy / "FAILURE.json"), "sha256": sha(args.failed_policy / "FAILURE.json")},
        "original_candidate_audit": {"path": str(original_issue / "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json"), "sha256": sha(original_issue / "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json")},
        "original_final_recovery": {"path": str(original_final_recovery_path), "sha256": sha(original_final_recovery_path)},
        "replay_policy_issue_audit": {"path": str(replay_issue / "POLICY_ISSUE_AUDIT.json"), "sha256": sha(replay_issue / "POLICY_ISSUE_AUDIT.json")},
        "replay_recovery_evidence": {"path": str(replay_issue / "A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json"), "sha256": sha(replay_issue / "A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json")},
        "commit_marker": {"path": str(commit), "sha256": sha(commit)},
        "fresh_voltage_min_pu": final_exact.get("voltage_min_pu"),
        "fresh_voltage_max_pu": final_exact.get("voltage_max_pu"),
        "full_W02_executed": False,
        "scientific_solve_count_by_this_validator": 0,
        "opendss_solve_count_by_this_validator": 0,
        "hard_limits_relaxed": False,
        "future_actual_used": False,
    }
    write(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
