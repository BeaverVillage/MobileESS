"""No-solve integrity validator for independent January daily artifacts."""

from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


METHODS = tuple(f"B{index}" for index in range(8))
ISSUES_PER_DAY = 288
REQUIRED_STRINGS = (
    "causal_exogenous_sha256", "comparison_method_id", "controller_id",
    "post_state_sha256", "pre_state_sha256", "result_uid", "schema_version",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_tree(value: Any, where: str, errors: list[str]) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            errors.append(f"{where}: non-finite numeric value")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            finite_tree(child, f"{where}.{key}", errors)
        return
    if isinstance(value, Sequence):
        for index, child in enumerate(value):
            finite_tree(child, f"{where}[{index}]", errors)


def validate_episode(calendar_date: str, root: Path) -> Mapping[str, Any]:
    errors: list[str] = []
    manifest_path = root / "RUN_MANIFEST.json"
    matrix_path = root / "MATRIX_SUMMARY.json"
    if not manifest_path.is_file() or not matrix_path.is_file():
        return {
            "calendar_date": calendar_date, "root": str(root), "status": "FAIL",
            "errors": ["missing RUN_MANIFEST.json or MATRIX_SUMMARY.json"],
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "calendar_date": calendar_date, "root": str(root), "status": "FAIL",
            "errors": [f"invalid summary JSON: {exc}"],
        }

    day_index = (date.fromisoformat(calendar_date) - date(2025, 1, 1)).days + 1
    expected_axis = list(range((day_index - 1) * ISSUES_PER_DAY, day_index * ISSUES_PER_DAY))
    rows_by_method: dict[str, list[Mapping[str, Any]]] = {}
    result_uids_by_method: dict[str, set[str]] = {}
    for method in METHODS:
        marker_paths = sorted(
            (root / method).glob("issue_*/COMMIT_MARKER.json"),
            key=lambda path: int(path.parent.name.split("_")[-1]),
        )
        if len(marker_paths) != ISSUES_PER_DAY:
            errors.append(f"{method}: commit markers {len(marker_paths)}/{ISSUES_PER_DAY}")
        rows: list[Mapping[str, Any]] = []
        for path in marker_paths:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: invalid JSON {exc}")
                continue
            rows.append(row)
            finite_tree(row, str(path), errors)
            for key in REQUIRED_STRINGS:
                if not isinstance(row.get(key), str) or not str(row[key]).strip():
                    errors.append(f"{path}: blank/missing {key}")
            if row.get("comparison_method_id") != method:
                errors.append(f"{path}: wrong comparison_method_id")
            if row.get("status") != "PASS_COMMITTED" or row.get("commit_marker") is not True:
                errors.append(f"{path}: not PASS_COMMITTED")
            if row.get("actual_gurobi_used") is not True or row.get("actual_fresh_opendss_used") is not True:
                errors.append(f"{path}: missing real Gurobi/OpenDSS authority")
            if row.get("future_actual_used") is not False:
                errors.append(f"{path}: future actual used")
            exact = row.get("exact_ac", {})
            exact_ok = (
                exact.get("hard_constraint_pass") is True
                and exact.get("robust_grid_hard_constraint_pass") is True
                and int(exact.get("voltage_violation_count", -1)) == 0
                and int(exact.get("line_violation_count", -1)) == 0
                and int(exact.get("transformer_current_violation_count", -1)) == 0
                and int(exact.get("transformer_kva_violation_count", -1)) == 0
                and 0.95 <= float(exact.get("voltage_min_pu", float("nan")))
                and float(exact.get("voltage_max_pu", float("nan"))) <= 1.05
                and 0.95 <= float(exact.get("robust_grid_voltage_min_pu", float("nan")))
                and float(exact.get("robust_grid_voltage_max_pu", float("nan"))) <= 1.05
            )
            if not exact_ok:
                errors.append(f"{path}: invalid exact/robust AC result")
            energy = float(row.get("minimum_mess_energy_kwh", float("nan")))
            if not 440.0 - 1e-9 <= energy <= 1080.0 + 1e-9:
                errors.append(f"{path}: MESS energy outside [440,1080] kWh")
        method_uids = {str(row.get("result_uid", "")) for row in rows}
        result_uids_by_method[method] = method_uids
        if len(method_uids) != 1:
            errors.append(f"{method}: expected one stable method-run result_uid")
        rows_by_method[method] = rows
        issues = [int(row.get("issue", -1)) for row in rows]
        if issues != expected_axis:
            errors.append(f"{method}: non-contiguous or wrong daily issue axis")
        if any(
            left.get("post_state_sha256") != right.get("pre_state_sha256")
            for left, right in zip(rows, rows[1:])
        ):
            errors.append(f"{method}: broken state hash chain")
        csv_path = root / method / "MATERIALIZED_COMMIT_ROWS.csv"
        if not csv_path.is_file():
            errors.append(f"{method}: missing MATERIALIZED_COMMIT_ROWS.csv")
        else:
            with csv_path.open(newline="", encoding="utf-8") as stream:
                materialized = list(csv.DictReader(stream))
            if len(materialized) != ISSUES_PER_DAY or any(
                not any(str(value).strip() for value in row.values())
                for row in materialized
            ):
                errors.append(f"{method}: empty/incomplete materialized rows")

    if all(len(rows_by_method[method]) == ISSUES_PER_DAY for method in METHODS):
        for offset in range(ISSUES_PER_DAY):
            hashes = {
                str(rows_by_method[method][offset].get("causal_exogenous_sha256"))
                for method in METHODS
            }
            if len(hashes) != 1:
                errors.append(f"issue offset {offset}: cross-method causal input mismatch")
    all_result_uids = set().union(*result_uids_by_method.values())
    if len(all_result_uids) != len(METHODS):
        errors.append("B0-B7 method-run result_uid values are not unique")

    if matrix.get("status") != "PASS":
        errors.append("MATRIX_SUMMARY status is not PASS")
    if int(matrix.get("expected_commit_markers", -1)) != ISSUES_PER_DAY * len(METHODS):
        errors.append("MATRIX_SUMMARY expected marker count mismatch")
    if manifest.get("future_actual_used") is not False:
        errors.append("RUN_MANIFEST future_actual_used is not false")
    return {
        "calendar_date": calendar_date,
        "root": str(root),
        "status": "PASS" if not errors else "FAIL",
        "commit_markers": sum(len(value) for value in rows_by_method.values()),
        "unique_method_run_result_uids": len(all_result_uids),
        "errors": errors,
        "source_hashes": {
            "RUN_MANIFEST.json": sha256(manifest_path),
            "MATRIX_SUMMARY.json": sha256(matrix_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", action="append", required=True, help="YYYY-MM-DD=artifact_root")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    for raw in args.episode:
        calendar_date, separator, path = raw.partition("=")
        if not separator:
            parser.error("--episode must be YYYY-MM-DD=artifact_root")
        results.append(validate_episode(calendar_date, Path(path).resolve()))
    status = "PASS" if all(row["status"] == "PASS" for row in results) else "FAIL"
    report = {
        "schema_version": "PFR10_USER_AUTHORIZED_TWO_DATE_INTEGRITY_CHECKPOINT_V1",
        "status": status,
        "document_conformance_note": "This is not the v13.2.1 JAN01_07 acceptance token.",
        "episodes": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    for row in results:
        print(f"{row['calendar_date']} | {row.get('commit_markers', 0)}/2304 | {row['status']}")
    print(f"checkpoint | {len(results)} days | {status}")
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
