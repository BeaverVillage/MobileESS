#!/usr/bin/env python3
"""Fail-closed R12 checkpoint/restart representative-week checkpoint/restart equivalence validator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_hash(state: dict) -> str:
    payload = json.dumps(
        state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing checkpoint/restart evidence: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_lane(root: Path, start: int, count: int) -> dict:
    previous_post_hash = None
    max_gap = 0.0
    for issue in range(start, start + count):
        issue_root = root / f"issue_{issue:06d}"
        pre = read_json(issue_root / "BUILD7C_PRECOMMIT_STATE.json")
        post = read_json(issue_root / "BUILD7C_POSTCOMMIT_STATE.json")
        transition = read_json(issue_root / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json")
        gap = read_json(issue_root / "ConversationA_BUILD7C_R12R1_CERTIFIED_GAP_ACCEPTANCE.json")
        if pre.get("sha256") != canonical_hash(pre.get("state", {})):
            raise RuntimeError(f"PRE canonical hash mismatch: {issue}")
        if post.get("sha256") != canonical_hash(post.get("state", {})):
            raise RuntimeError(f"POST canonical hash mismatch: {issue}")
        if int(pre["state"]["issue_step"]) != issue:
            raise RuntimeError(f"PRE issue axis mismatch: {issue}")
        if int(post["state"]["issue_step"]) != issue + 1:
            raise RuntimeError(f"POST issue axis mismatch: {issue}")
        if previous_post_hash is not None and pre["sha256"] != previous_post_hash:
            raise RuntimeError(f"POST/PRE chain mismatch: {issue}")
        if transition.get("status") != "PASS":
            raise RuntimeError(f"transition certificate failed: {issue}")
        if transition.get("pre_state_sha256") != pre["sha256"]:
            raise RuntimeError(f"transition PRE hash mismatch: {issue}")
        if transition.get("post_state_sha256") != post["sha256"]:
            raise RuntimeError(f"transition POST hash mismatch: {issue}")
        for key, expected in (
            ("fresh_exact_ac_pass", True),
            ("future_actual_arrivals_read", False),
            ("future_D2_state_reinjected", False),
            ("h0_only_committed", True),
            ("h1_to_h53_committed", False),
        ):
            if transition.get(key) is not expected:
                raise RuntimeError(f"transition {key} mismatch: {issue}")
        if post["state"].get("future_plans_persisted") is not False:
            raise RuntimeError(f"future plan persisted: {issue}")
        certified_gap = float(gap.get("certified_mip_gap", float("inf")))
        if gap.get("accepted") is not True or certified_gap > 0.03 + 1e-12:
            raise RuntimeError(f"global certified gap failed: {issue} {certified_gap}")
        max_gap = max(max_gap, certified_gap)
        previous_post_hash = post["sha256"]
    final = read_json(root / f"issue_{start+count-1:06d}" / "BUILD7C_POSTCOMMIT_STATE.json")
    return {
        "root": str(root),
        "issue_count": count,
        "start_issue": start,
        "end_issue": start + count - 1,
        "evaluation_start_issue": start + count,
        "final_state_sha256": final["sha256"],
        "max_global_certified_gap": max_gap,
        "post_pre_hash_chain_pass": True,
        "all_transition_and_ac_gates_pass": True,
        "future_actual_used": False,
        "future_plans_persisted": False,
    }


def validate_restart_invocations(control_root: Path, start: int, checkpoint: int, count: int) -> list[dict]:
    records = [read_json(path) for path in sorted((control_root / "invocations").glob("*.json"))]
    finished = [row for row in records if row.get("status") == "FINISHED" and row.get("child_return_code") == 0]
    first_resume = start
    second_resume = start + checkpoint
    if not any(
        int(row.get("resume_issue", -1)) == first_resume
        and int(row.get("configured_issue_count", -1)) == checkpoint
        and int(row.get("verified_issue_count_after_invocation", -1)) == checkpoint
        for row in finished
    ):
        raise RuntimeError("checkpoint/restart candidate lacks a completed first-half invocation")
    if not any(
        int(row.get("resume_issue", -1)) == second_resume
        and int(row.get("configured_issue_count", -1)) == count
        and int(row.get("verified_issue_count_after_invocation", -1)) == count
        for row in finished
    ):
        raise RuntimeError("checkpoint/restart candidate lacks a completed checkpoint resume invocation")
    return finished


CONTINUOUS_FIELDS = (
    "mess_E_kWh",
    "mess_support_debt_kWh",
    "workload_debt_GPUh",
)


def compare_initializer_endpoints(reference_root: Path, candidate_root: Path,
                                  start: int, count: int, tolerance: float = 1e-6) -> dict:
    reference_lane = validate_lane(reference_root, start, count)
    candidate_lane = validate_lane(candidate_root, start, count)
    reference = read_json(reference_root / f"issue_{start + count - 1:06d}" / "BUILD7C_POSTCOMMIT_STATE.json")["state"]
    candidate = read_json(candidate_root / f"issue_{start + count - 1:06d}" / "BUILD7C_POSTCOMMIT_STATE.json")["state"]
    reference_discrete = {key: value for key, value in reference.items() if key not in CONTINUOUS_FIELDS}
    candidate_discrete = {key: value for key, value in candidate.items() if key not in CONTINUOUS_FIELDS}
    if reference_discrete != candidate_discrete:
        differing = sorted(
            key for key in set(reference_discrete) | set(candidate_discrete)
            if reference_discrete.get(key) != candidate_discrete.get(key)
        )
        raise RuntimeError(f"initializer endpoint discrete state mismatch: {differing}")
    maxima: dict[str, float] = {}
    for field in CONTINUOUS_FIELDS:
        reference_values = reference.get(field, {})
        candidate_values = candidate.get(field, {})
        if set(reference_values) != set(candidate_values):
            raise RuntimeError(f"initializer endpoint key mismatch: {field}")
        maximum = max(
            (abs(float(reference_values[key]) - float(candidate_values[key])) for key in reference_values),
            default=0.0,
        )
        maxima[field] = maximum
        if maximum > tolerance:
            raise RuntimeError(
                f"initializer endpoint tolerance failed: {field} max_abs={maximum} tolerance={tolerance}"
            )
    return {
        "status": "PASS",
        "reference": reference_lane,
        "candidate": candidate_lane,
        "comparison_issue": start + count,
        "discrete_state_exact": True,
        "continuous_tolerance": tolerance,
        "continuous_max_abs": maxima,
        "future_actual_used": False,
        "future_plans_persisted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--reference-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--candidate-control-root", required=True)
    parser.add_argument("--start-issue", required=True, type=int)
    parser.add_argument("--issue-count", type=int, default=576)
    parser.add_argument("--checkpoint-after", type=int, default=288)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.issue_count != 576 or args.checkpoint_after != 288:
        raise RuntimeError("R12 checkpoint/restart requires exactly 576 steps and checkpoint 288")
    reference = validate_lane(Path(args.reference_root), args.start_issue, args.issue_count)
    suffix_start = args.start_issue + args.checkpoint_after
    suffix_count = args.issue_count - args.checkpoint_after
    candidate = validate_lane(Path(args.candidate_root), suffix_start, suffix_count)
    records = [
        read_json(path)
        for path in sorted((Path(args.candidate_control_root) / "invocations").glob("*.json"))
    ]
    invocations = [
        row for row in records
        if row.get("status") == "FINISHED"
        and row.get("child_return_code") == 0
        and int(row.get("resume_issue", -1)) == suffix_start
        and int(row.get("configured_issue_count", -1)) == suffix_count
        and int(row.get("verified_issue_count_after_invocation", -1)) == suffix_count
    ]
    if not invocations:
        raise RuntimeError("checkpoint/restart suffix invocation evidence missing")
    reference_checkpoint = read_json(
        Path(args.reference_root)
        / f"issue_{suffix_start - 1:06d}"
        / "BUILD7C_POSTCOMMIT_STATE.json"
    )
    candidate_pre = read_json(
        Path(args.candidate_root)
        / f"issue_{suffix_start:06d}"
        / "BUILD7C_PRECOMMIT_STATE.json"
    )
    if reference_checkpoint["sha256"] != candidate_pre["sha256"]:
        raise RuntimeError("checkpoint/restart midpoint state hash mismatch")
    if reference["final_state_sha256"] != candidate["final_state_sha256"]:
        raise RuntimeError("checkpoint/restart evaluation-start canonical state hash mismatch")
    result = {
        "schema_version": "conversation_c.stage7.r12.checkpoint_restart.v1",
        "status": "PASS",
        "candidate_id": args.candidate_id,
        "checkpoint_after_steps": args.checkpoint_after,
        "candidate_suffix_steps": suffix_count,
        "duplicated_first_half_solve": False,
        "reference": reference,
        "candidate": candidate,
        "evaluation_start_state_hash_exact": True,
        "candidate_finished_invocation_count": len(invocations),
        "future_actual_used": False,
        "future_plans_persisted": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
