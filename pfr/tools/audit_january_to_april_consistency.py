"""Audit one frozen implementation/calibration across January-April results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping


PERIODS = (
    ("january", date(2025, 1, 1), 31),
    ("february", date(2025, 2, 1), 28),
    ("march", date(2025, 3, 1), 31),
    ("april", date(2025, 4, 1), 30),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"missing or invalid consistency evidence: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"consistency evidence is not an object: {path}")
    return payload


def common_signature(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    evaluation = manifest.get("evaluation_contract", {})
    native = manifest.get("common_native_grid_control", {})
    predictive = manifest.get("predictive_native_dwell_guard", {})
    return {
        "git_full_commit_sha": manifest.get("git_full_commit_sha"),
        "git_branch": manifest.get("git_branch"),
        "scientific_implementation_fingerprint": manifest.get(
            "scientific_implementation_fingerprint"
        ),
        "physical_execution_authority_version": manifest.get(
            "physical_execution_authority_version"
        ),
        "risk_calibration_artifact_sha256": manifest.get(
            "risk_calibration_artifact_sha256"
        ),
        "risk_calibration_authority_id": manifest.get(
            "risk_calibration_authority_id"
        ),
        "mobility_execution_authority_sha256": manifest.get(
            "mobility_execution_authority_sha256"
        ),
        "mobility_execution_time_authority": manifest.get(
            "mobility_execution_time_authority"
        ),
        "migration_authority_sha256": manifest.get("migration_authority_sha256"),
        "migration_contract_sha256": manifest.get("migration_contract_sha256"),
        "opendss_metrics_common_sha256": manifest.get(
            "opendss_metrics_common_sha256"
        ),
        "factorized_uncertainty_sha256": evaluation.get(
            "factorized_uncertainty_sha256"
        ),
        "feeder_absolute_scale_contract_sha256": evaluation.get(
            "feeder_absolute_scale_contract_sha256"
        ),
        "mobility_physics_sha256": evaluation.get("mobility_physics_sha256"),
        "runtime_contract_sha256": evaluation.get("runtime_contract_sha256"),
        "native_grid_control_authority_sha256": native.get("authority_sha256"),
        "native_grid_control_dss_sha256": native.get("dss_sha256"),
        "predictive_native_dwell_guard_sha256": predictive.get(
            "authority_sha256"
        ),
    }


def audit(
    run_root: Path,
    risk_calibration: Path,
) -> Mapping[str, Any]:
    calibration_sha = sha256(risk_calibration)
    signatures: list[Mapping[str, Any]] = []
    source_authorities: dict[str, set[str]] = {}
    rows = []
    for month, start, days in PERIODS:
        source_authorities[month] = set()
        for registry, method_count in (("B00_B09", 10),):
            root = run_root / month / registry
            campaign = load_json(root / "CAMPAIGN_SUMMARY.json")
            storage = load_json(root / "STORAGE_VERIFICATION.json")
            if campaign.get("status") != "PASS" or storage.get("status") != "PASS":
                raise RuntimeError(f"campaign/storage did not pass: {month}/{registry}")
            daily = campaign.get("daily_runs", ())
            if len(daily) != days or any(row.get("status") != "PASS" for row in daily):
                raise RuntimeError(f"daily campaign is incomplete: {month}/{registry}")
            expected_markers = days * method_count * 288
            markers = sum(
                1
                for _ in root.glob("2025-??-??/B0[0-9]/issue_*/COMMIT_MARKER.json")
            )
            if markers != expected_markers:
                raise RuntimeError(
                    f"commit marker mismatch: {month}/{registry} "
                    f"{markers}!={expected_markers}"
                )
            for offset in range(days):
                calendar_date = (start + timedelta(days=offset)).isoformat()
                manifest = load_json(root / calendar_date / "RUN_MANIFEST.json")
                if (
                    manifest.get("status") != "PASS"
                    or manifest.get("git_worktree_dirty") is not False
                    or manifest.get("future_actual_used") is not False
                    or manifest.get("mobility_execution_actual_used_by_optimizer")
                    is not False
                    or manifest.get("mobility_execution_post_decision_only") is not True
                    or manifest.get("mobility_prediction_actual_error_materialized")
                    is not True
                    or manifest.get("migration_prediction_actual_error_materialized")
                    is not True
                    or manifest.get("risk_calibration_march_outcomes_read") is not False
                    or manifest.get("risk_calibration_artifact_sha256")
                    != calibration_sha
                ):
                    raise RuntimeError(
                        f"scientific manifest invariant failed: "
                        f"{month}/{registry}/{calendar_date}"
                    )
                signature = common_signature(manifest)
                if any(value in (None, "") for value in signature.values()):
                    raise RuntimeError(
                        f"common implementation signature is incomplete: "
                        f"{month}/{registry}/{calendar_date}"
                    )
                signatures.append(signature)
                source_authorities[month].add(
                    str(manifest.get("shared_exogenous_authority_sha256"))
                )
            rows.append(
                {
                    "month": month,
                    "registry": registry,
                    "days": days,
                    "commit_markers": markers,
                    "campaign_status": "PASS",
                    "storage_status": "PASS",
                }
            )
    reference = signatures[0]
    if any(signature != reference for signature in signatures[1:]):
        raise RuntimeError("January-April common implementation signature drift")
    if any(len(values) != 1 for values in source_authorities.values()):
        raise RuntimeError("a month used more than one shared exogenous authority")
    return {
        "schema_version": "PFR_JANUARY_TO_APRIL_ELECTRICAL_STRESS_CONSISTENCY_AUDIT_V2",
        "status": "PASS",
        "calendar_day_count": 120,
        "run_manifest_count": len(signatures),
        "same_frozen_implementation_and_calibration": True,
        "month_specific_exogenous_sources_expected": True,
        "calibration_refit_after_january": False,
        "march_outcomes_read_for_calibration": False,
        "common_signature": reference,
        "monthly_source_authority_sha256": {
            month: next(iter(values)) for month, values in source_authorities.items()
        },
        "registries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--risk-calibration", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = audit(args.run_root, args.risk_calibration)
    except RuntimeError as exc:
        parser.exit(2, f"JANUARY_TO_APRIL_CONSISTENCY_FAIL: {exc}\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_name(f".{args.report.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.report)
    print(json.dumps({"status": "PASS", "report": str(args.report)}))


if __name__ == "__main__":
    main()
