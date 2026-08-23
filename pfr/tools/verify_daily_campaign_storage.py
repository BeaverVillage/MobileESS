"""Verify that a daily campaign is complete, parseable, and restart-safe."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from pfr.provenance import scientific_implementation_fingerprint


METHODS = tuple(f"B{index}" for index in range(8))
ISSUES_PER_DAY = 288


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def inspect_method(method_root: Path, method: str) -> dict[str, Any]:
    errors: list[str] = []
    markers: list[Mapping[str, Any]] = []
    for marker_path in sorted(method_root.glob("issue_*/COMMIT_MARKER.json")):
        try:
            marker = load_json(marker_path)
            if marker.get("status") != "PASS_COMMITTED":
                raise ValueError("status is not PASS_COMMITTED")
            if marker.get("commit_marker") is not True:
                raise ValueError("commit_marker is not true")
            if marker.get("comparison_method_id") != method:
                raise ValueError("comparison_method_id mismatch")
            if marker.get("actual_gurobi_used") is not True:
                raise ValueError("actual Gurobi evidence missing")
            if marker.get("actual_fresh_opendss_used") is not True:
                raise ValueError("fresh OpenDSS evidence missing")
            if marker.get("future_actual_used") is not False:
                raise ValueError("future actual leakage flag")
            if not marker.get("pre_state_sha256") or not marker.get(
                "post_state_sha256"
            ):
                raise ValueError("state-chain hash missing")
            markers.append(marker)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{marker_path}: {type(exc).__name__}: {exc}")
    markers.sort(key=lambda row: int(row["issue"]))
    issues = [int(row["issue"]) for row in markers]
    if len(issues) != len(set(issues)):
        errors.append("duplicate committed issue")
    if any(
        markers[index]["post_state_sha256"]
        != markers[index + 1]["pre_state_sha256"]
        for index in range(max(0, len(markers) - 1))
    ):
        errors.append("state chain is discontinuous")

    summary_path = method_root / "METHOD_SUMMARY.json"
    failure_path = method_root / "FAILURE.json"
    summary: Mapping[str, Any] | None = None
    failure: Mapping[str, Any] | None = None
    try:
        if summary_path.is_file():
            summary = load_json(summary_path)
        if failure_path.is_file():
            failure = load_json(failure_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"method evidence JSON: {type(exc).__name__}: {exc}")
    if summary is not None:
        if summary.get("comparison_method_id") != method:
            errors.append("METHOD_SUMMARY method mismatch")
        if int(summary.get("commit_marker_count", -1)) != len(markers):
            errors.append("METHOD_SUMMARY commit count mismatch")
        if summary.get("status") == "PASS" and len(markers) != ISSUES_PER_DAY:
            errors.append("PASS method does not contain 288 markers")
        if summary.get("status") != "PASS" and failure is None:
            errors.append("failed method has no FAILURE.json")
    elif method_root.exists() and (markers or failure is not None):
        errors.append("METHOD_SUMMARY.json missing")
    return {
        "method": method,
        "status": summary.get("status") if summary is not None else "NOT_RUN",
        "commit_markers": len(markers),
        "first_issue": min(issues) if issues else None,
        "last_issue": max(issues) if issues else None,
        "failure_evidence": failure is not None,
        "errors": errors,
    }


def inspect_day(
    day_root: Path, calendar_date: str, implementation_fingerprint: str
) -> dict[str, Any]:
    errors: list[str] = []
    methods = [inspect_method(day_root / method, method) for method in METHODS]
    errors.extend(
        error for method in methods for error in method["errors"]
    )
    temp_files = [str(path) for path in day_root.rglob("*.tmp")]
    if temp_files:
        errors.append("unpublished temporary files remain")

    summary = manifest = None
    try:
        if (day_root / "MATRIX_SUMMARY.json").is_file():
            summary = load_json(day_root / "MATRIX_SUMMARY.json")
        if (day_root / "RUN_MANIFEST.json").is_file():
            manifest = load_json(day_root / "RUN_MANIFEST.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"day JSON: {type(exc).__name__}: {exc}")

    orchestration_failure = None
    try:
        path = day_root / "ORCHESTRATION_FAILURE.json"
        if path.is_file():
            orchestration_failure = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"orchestration failure JSON: {type(exc).__name__}: {exc}")

    marker_count = sum(int(row["commit_markers"]) for row in methods)
    scientific_status = "NOT_RUN"
    complete = False
    if summary is not None:
        scientific_status = str(summary.get("status", "UNKNOWN"))
        complete = True
        if int(summary.get("valid_commit_markers", -1)) != marker_count:
            errors.append("MATRIX_SUMMARY commit count mismatch")
        if summary.get("continue_to_next_method_after_failure") is not True:
            errors.append("B-failure continuation policy missing")
        if scientific_status == "PASS":
            if marker_count != ISSUES_PER_DAY * len(METHODS):
                errors.append("PASS day does not contain 2304 markers")
            if summary.get("all_actual_gurobi") is not True:
                errors.append("PASS day lacks all-actual-Gurobi evidence")
            if summary.get("all_fresh_exact_opendss") is not True:
                errors.append("PASS day lacks fresh-OpenDSS evidence")
            if summary.get("all_state_chains_complete") is not True:
                errors.append("PASS day lacks state-chain evidence")
    elif orchestration_failure is not None:
        scientific_status = "FAIL_CLOSED_ORCHESTRATION_EXCEPTION"
        complete = True

    if manifest is not None:
        if manifest.get("scientific_implementation_fingerprint") != implementation_fingerprint:
            errors.append("scientific implementation fingerprint drift")
        if manifest.get("status") != scientific_status and summary is not None:
            errors.append("RUN_MANIFEST/MATRIX_SUMMARY status mismatch")
        if int(manifest.get("count", -1)) != ISSUES_PER_DAY:
            errors.append("RUN_MANIFEST issue count mismatch")
        source_authority_path = Path(
            str(manifest.get("shared_exogenous_authority_path", ""))
        )
        if (
            not source_authority_path.is_file()
            or manifest.get("shared_exogenous_authority_sha256")
            != sha256(source_authority_path)
        ):
            errors.append("shared exogenous authority path/SHA drift")
    elif summary is not None:
        errors.append("RUN_MANIFEST.json missing")

    return {
        "calendar_date": calendar_date,
        "complete": complete,
        "scientific_status": scientific_status,
        "storage_integrity": "PASS" if not errors else "FAIL",
        "commit_markers": marker_count,
        "methods": methods,
        "orchestration_failure_evidence": orchestration_failure is not None,
        "temporary_files": temp_files,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 1 <= args.days <= 31:
        parser.error("--days must be in [1, 31]")
    expected_dates = [
        (args.start_date + timedelta(days=offset)).isoformat()
        for offset in range(args.days)
    ]
    fingerprint = scientific_implementation_fingerprint(args.repo)
    rows = [
        inspect_day(args.root / calendar_date, calendar_date, fingerprint)
        for calendar_date in expected_dates
    ]
    storage_ok = all(row["storage_integrity"] == "PASS" for row in rows)
    complete = all(bool(row["complete"]) for row in rows)
    scientific_pass = complete and all(
        row["scientific_status"] == "PASS" for row in rows
    )
    report = {
        "schema_version": "PFR_DAILY_CAMPAIGN_STORAGE_VERIFICATION_V13_13",
        "status": (
            "PASS"
            if storage_ok and scientific_pass
            else (
                "COMPLETE_WITH_SCIENTIFIC_FAILURES"
                if storage_ok and complete
                else "FAIL_STORAGE_OR_INCOMPLETE"
            )
        ),
        "storage_integrity": "PASS" if storage_ok else "FAIL",
        "campaign_complete": complete,
        "scientific_status": "PASS" if scientific_pass else "FAIL_OR_INCOMPLETE",
        "root": str(args.root),
        "expected_days": args.days,
        "completed_days": sum(bool(row["complete"]) for row in rows),
        "pass_days": sum(row["scientific_status"] == "PASS" for row in rows),
        "total_commit_markers": sum(int(row["commit_markers"]) for row in rows),
        "scientific_implementation_fingerprint": fingerprint,
        "days": rows,
    }
    report_path = args.report or (args.root / "STORAGE_VERIFICATION.json")
    atomic_write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "storage_integrity": report["storage_integrity"],
        "completed_days": report["completed_days"],
        "pass_days": report["pass_days"],
        "report": str(report_path),
    }), flush=True)
    if not storage_ok or not complete:
        raise SystemExit(2)
    if not scientific_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
