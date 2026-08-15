#!/usr/bin/env python3
"""Read-only audit of numerical retries in an R25R/R25S runtime tree."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
from statistics import mean, median
from typing import Any, Iterable, Mapping


DECOMP = "ConversationA_R25M_B6_EXACT_DECOMPOSITION_AUDIT.json"
ERROR_RE = re.compile(r"max_err=([0-9.eE+-]+)")


def walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"expected object: {path}")
    return value


def retry_errors(history: Any) -> list[float]:
    errors = []
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, Mapping):
            continue
        match = ERROR_RE.search(str(row.get("reason", "")))
        if match:
            errors.append(float(match.group(1)))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    issue_files = sorted(args.run_root.glob(f"issue_*/{DECOMP}"))
    rows = []
    total_root_retries = 0
    total_child_retries = 0
    total_polish_attempts = 0
    repeated_same_error_sequences = 0
    envelope_accepts = Counter()
    retry_iteration_seconds: list[float] = []
    clean_iteration_seconds: list[float] = []
    estimated_extra_seconds = 0.0
    for path in issue_files:
        data = load(path)
        issue = int(path.parent.name.split("_")[-1])
        root_records = data.get("pricing_records", [])
        root_retries = sum(int(row.get("qcp_dual_retry_count", 0)) for row in root_records)
        root_retry_iterations = sum(int(row.get("qcp_dual_retry_count", 0)) > 0 for row in root_records)
        root_retry_outcomes = []
        issue_clean_seconds = [
            float(row.get("rmp_solve_seconds", 0.0))
            for row in root_records
            if int(row.get("qcp_dual_retry_count", 0)) == 0
        ]
        issue_baseline = median(issue_clean_seconds) if issue_clean_seconds else 0.0
        for row in root_records:
            solve_seconds = float(row.get("rmp_solve_seconds", 0.0))
            if int(row.get("qcp_dual_retry_count", 0)) > 0:
                retry_iteration_seconds.append(solve_seconds)
                estimated_extra_seconds += max(0.0, solve_seconds - issue_baseline)
                history = row.get("qcp_dual_retry_history", [])
                root_retry_outcomes.append(
                    {
                        "iteration": row.get("iteration"),
                        "retry_count": int(row.get("qcp_dual_retry_count", 0)),
                        "retry_errors": retry_errors(history),
                        "accept_trigger": next(
                            (
                                entry.get("trigger")
                                for entry in history
                                if isinstance(entry, Mapping)
                                and entry.get("bounded_envelope_accept")
                            ),
                            "STRICT_RETRY_RECOVERED_FIXED_AUDIT_TOLERANCE",
                        ),
                        "effective_rc_guard": row.get("effective_rc_guard"),
                        "iteration_solve_seconds": solve_seconds,
                        "estimated_extra_seconds_vs_issue_clean_median": max(
                            0.0, solve_seconds - issue_baseline
                        ),
                    }
                )
            else:
                clean_iteration_seconds.append(solve_seconds)
            errors = retry_errors(row.get("qcp_dual_retry_history"))
            if len(errors) >= 2 and max(errors) - min(errors) <= 1e-12:
                repeated_same_error_sequences += 1
            for entry in row.get("qcp_dual_retry_history", []):
                if isinstance(entry, Mapping) and entry.get("bounded_envelope_accept"):
                    envelope_accepts[f"root:{entry.get('trigger')}"] += 1

        branch = data.get("branch_price") or {}
        child_retries = 0
        child_retry_nodes = 0
        for node in walk(branch.get("records", [])):
            if "qcp_dual_retry_count" in node:
                count = int(node.get("qcp_dual_retry_count", 0))
                child_retries += count
                child_retry_nodes += count > 0
            history = node.get("retry_history")
            if isinstance(history, list):
                errors = retry_errors(history)
                if len(errors) >= 2 and max(errors) - min(errors) <= 1e-12:
                    repeated_same_error_sequences += 1
                for entry in history:
                    if isinstance(entry, Mapping) and entry.get("bounded_envelope_accept"):
                        envelope_accepts[f"child:{entry.get('trigger')}"] += 1

        polish = data.get("fixed_integer_continuous_qcp_polish") or {}
        attempts = polish.get("attempts") if isinstance(polish.get("attempts"), list) else []
        polish_attempts = len(attempts)
        rows.append(
            {
                "issue": issue,
                "root_cg_iterations": len(root_records),
                "root_dual_retries": root_retries,
                "root_iterations_with_retry": root_retry_iterations,
                "root_retry_iteration_seconds": sum(
                    float(row.get("rmp_solve_seconds", 0.0))
                    for row in root_records
                    if int(row.get("qcp_dual_retry_count", 0)) > 0
                ),
                "root_retry_outcomes": root_retry_outcomes,
                "child_dual_retries": child_retries,
                "child_nodes_with_retry": child_retry_nodes,
                "polish_attempts": polish_attempts,
                "polish_first_attempt_passed": bool(attempts and attempts[0].get("quality_pass")),
            }
        )
        total_root_retries += root_retries
        total_child_retries += child_retries
        total_polish_attempts += polish_attempts

    result = {
        "schema_version": "r26.retry_audit.v1",
        "run_root": str(args.run_root),
        "completed_issue_audits": len(rows),
        "totals": {
            "root_dual_retries": total_root_retries,
            "child_dual_retries": total_child_retries,
            "polish_attempts": total_polish_attempts,
            "polish_extra_attempts_after_first": sum(max(0, row["polish_attempts"] - 1) for row in rows),
            "identical_rc_error_retry_sequences": repeated_same_error_sequences,
            "bounded_envelope_accepts_by_trigger": dict(envelope_accepts),
            "root_retry_iteration_seconds": sum(retry_iteration_seconds),
            "root_clean_iteration_seconds": sum(clean_iteration_seconds),
            "mean_retry_iteration_seconds": mean(retry_iteration_seconds) if retry_iteration_seconds else None,
            "mean_clean_iteration_seconds": mean(clean_iteration_seconds) if clean_iteration_seconds else None,
            "estimated_extra_retry_seconds": estimated_extra_seconds,
            "estimated_extra_retry_seconds_method": (
                "sum(max(0,retry_iteration_time - same-issue median clean iteration time)); "
                "diagnostic estimate because per-attempt durations are not separately logged"
            ),
        },
        "classification": {
            "potentially_avoidable": (
                "Up to two strict root/child QCP retries after an OPTIMAL finite RC snapshot is already "
                "inside the 5e-4 bounded envelope. Immediate guarded acceptance would remain conservative, "
                "but changing the budget would change the frozen R25R numerical policy."
            ),
            "conditional_not_redundant": (
                "Additional fixed-integer polish solves run only when the preceding solve misses the explicit "
                "ConstrVio/BoundVio gate; the loop stops on the first passing attempt."
            ),
            "required_fail_closed_recovery": (
                "The deeper dual retry schedule is reachable only when no finite OPTIMAL snapshot lies inside "
                "the hard envelope; removing it would turn recoverable dual failures into immediate aborts."
            ),
            "issue_level_automatic_retry": False,
        },
        "issues": rows,
    }
    incomplete = []
    for live_path in sorted(args.run_root.glob("issue_*/ConversationA_R25M_B6_CG_LIVE.json")):
        if (live_path.parent / DECOMP).is_file():
            continue
        live = load(live_path)
        history = live.get("qcp_dual_retry_history", [])
        incomplete.append(
            {
                "issue": int(live_path.parent.name.split("_")[-1]),
                "iteration": live.get("iteration"),
                "qcp_dual_retry_count": int(live.get("qcp_dual_retry_count", 0)),
                "rmp_solve_seconds": live.get("rmp_solve_seconds"),
                "identical_retry_errors": len(set(retry_errors(history))) == 1
                and len(retry_errors(history)) >= 2,
                "bounded_envelope_accept": any(
                    isinstance(entry, Mapping) and entry.get("bounded_envelope_accept")
                    for entry in history if isinstance(history, list)
                ),
                "not_in_completed_totals": True,
            }
        )
    result["incomplete_live_issues"] = incomplete
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(raw, encoding="utf-8")
    print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
