"""Aggregate preregistered January checkpoint-payload sensitivity runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


FACTORS = (0.25, 0.5, 1.0)
METHODS = tuple(f"B{index}" for index in range(3, 9))


def factor_key(factor: float) -> str:
    return f"rho{int(round(factor * 100)):03d}"


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    complete = True
    for factor in FACTORS:
        for method in METHODS:
            campaign_root = args.root / factor_key(factor) / method
            day_roots = sorted(
                path for path in campaign_root.glob("2025-01-*") if path.is_dir()
            )
            day_summaries = []
            parameterization_hashes = set()
            for day_root in day_roots:
                matrix_path = day_root / "MATRIX_SUMMARY.json"
                manifest_path = day_root / "RUN_MANIFEST.json"
                if not matrix_path.is_file() or not manifest_path.is_file():
                    continue
                matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                methods = matrix.get("method_summaries", ())
                if len(methods) != 1 or methods[0].get("comparison_method_id") != method:
                    continue
                if float(manifest.get("checkpoint_payload_occupancy_factor", -1.0)) != factor:
                    continue
                parameterization_hashes.add(manifest["migration_authority_sha256"])
                day_summaries.append(methods[0])
            row_complete = bool(
                len(day_summaries) == 31
                and len(parameterization_hashes) == 1
                and all(item.get("status") == "PASS" for item in day_summaries)
            )
            complete = complete and row_complete
            rows.append(
                {
                    "checkpoint_payload_occupancy_factor": factor,
                    "method": method,
                    "complete_31_day_campaign": row_complete,
                    "day_count": len(day_summaries),
                    "migration_parameterization_sha256": (
                        next(iter(parameterization_hashes))
                        if len(parameterization_hashes) == 1
                        else None
                    ),
                    "migration_count": sum(
                        int(item.get("migration_count", 0)) for item in day_summaries
                    ),
                    "wan_transferred_bytes": sum(
                        int(item.get("wan_transferred_bytes", 0))
                        for item in day_summaries
                    ),
                    "full_replan_count": sum(
                        int(item.get("full_replan_count", 0))
                        for item in day_summaries
                    ),
                    "deadline_misses": sum(
                        int(item.get("deadline_misses", 0)) for item in day_summaries
                    ),
                }
            )
    report = {
        "schema_version": "JAN2025_IDC_MIGRATION_RHO_SENSITIVITY_V1",
        "status": "PASS" if complete else "INCOMPLETE_OR_FAIL_CLOSED",
        "evaluation_classification": (
            "JANUARY_POST_HOC_DEVELOPMENT_SENSITIVITY_NOT_HOLDOUT"
        ),
        "factors": FACTORS,
        "methods": METHODS,
        "selection_rule": (
            "REPORT_SENSITIVITY_WITHOUT_CHOOSING_RHO_TO_FAVOR_ANY_METHOD"
        ),
        "rows": rows,
    }
    atomic_write_json(args.output, report)
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    if not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
