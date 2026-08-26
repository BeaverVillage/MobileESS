"""Paired mobility-enabled versus screened H54 MIQCP audit.

The tool never fits or changes a controller.  It verifies that two committed
issues share the same causal state/forecast and materializes the objective,
runtime, route, and Fresh-AC differences needed before a soft screening rule
can be considered for production use.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _commit(root: Path, method: str, issue: int) -> dict[str, Any]:
    path = root / method / f"issue_{issue:06d}" / "COMMIT_MARKER.json"
    if not path.is_file():
        raise RuntimeError(f"committed issue is missing: {path}")
    value = _load(path)
    if value.get("commit_marker") is not True:
        raise RuntimeError(f"issue is not atomically committed: {path}")
    return value


def _termination(root: Path, method: str, issue: int) -> dict[str, Any]:
    path = (
        root
        / "_RETAINED_H54"
        / method
        / f"issue_{issue:06d}"
        / "BUILD7BR6_GUROBI_TERMINATION.json"
    )
    return _load(path)


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{name} is not finite")
    return result


def _routes(
    root: Path, method: str, issue: int, commit: Mapping[str, Any]
) -> list[dict[str, Any]]:
    certificate = dict(commit.get("slow_miqp_certificate", {}))
    stored = [dict(row) for row in certificate.get("planned_mobility_routes", [])]
    if stored:
        return stored
    path = (
        root
        / "_RETAINED_H54"
        / method
        / f"issue_{issue:06d}"
        / "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"
    )
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def audit(
    full_root: Path,
    restricted_root: Path,
    method: str,
    issue: int,
) -> dict[str, Any]:
    full = _commit(full_root, method, issue)
    restricted = _commit(restricted_root, method, issue)
    identity_fields = (
        "pre_state_sha256",
        "causal_exogenous_sha256",
        "comparison_method_id",
        "planning_mobility_npz_sha256",
    )
    identity = {
        field: {
            "full": full.get(field),
            "restricted": restricted.get(field),
            "match": full.get(field) == restricted.get(field),
        }
        for field in identity_fields
    }
    identity["h54_capability_mask"] = {
        "full": full.get("h54_capability_mask"),
        "restricted": restricted.get("h54_capability_mask"),
        "match": full.get("h54_capability_mask")
        == restricted.get("h54_capability_mask"),
    }
    if not all(row["match"] for row in identity.values()):
        raise RuntimeError(f"paired causal identity mismatch: {identity}")

    full_z = _finite(full["predicted_worst_electrical_stress_pu"], "full z")
    restricted_z = _finite(
        restricted["predicted_worst_electrical_stress_pu"], "restricted z"
    )
    full_exposure = _finite(
        full["predicted_electrical_stress_exposure_pu_hours"], "full exposure"
    )
    restricted_exposure = _finite(
        restricted["predicted_electrical_stress_exposure_pu_hours"],
        "restricted exposure",
    )
    full_ac = _finite(
        full["realized_exact_electrical_stress"]["worst_electrical_stress_pu"],
        "full Fresh-AC z",
    )
    restricted_ac = _finite(
        restricted["realized_exact_electrical_stress"][
            "worst_electrical_stress_pu"
        ],
        "restricted Fresh-AC z",
    )
    full_cert = dict(full.get("slow_miqp_certificate", {}))
    restricted_cert = dict(restricted.get("slow_miqp_certificate", {}))
    full_remaining = int(full_cert.get("evaluation_steps_remaining", -1))
    restricted_remaining = int(
        restricted_cert.get("evaluation_steps_remaining", -1)
    )
    identity["evaluation_steps_remaining"] = {
        "full": full_remaining,
        "restricted": restricted_remaining,
        "match": full_remaining == restricted_remaining and full_remaining > 0,
    }
    if not identity["evaluation_steps_remaining"]["match"]:
        raise RuntimeError(
            "paired evaluation horizon mismatch: "
            f"full={full_remaining} restricted={restricted_remaining}"
        )
    screen = dict(restricted_cert.get("legacy_causal_mobility_screening", {}))
    if screen.get("applied") is not True:
        raise RuntimeError("restricted pair member lacks applied screening evidence")

    delta_z = restricted_z - full_z
    delta_exposure = restricted_exposure - full_exposure
    delta_ac = restricted_ac - full_ac
    return {
        "schema": "MOBILITY_SCREENING_PAIRED_ORACLE_AUDIT_V1",
        "status": "PAIRED_SAMPLE_COMPLETE_NOT_PRODUCTION_APPROVAL",
        "method": method,
        "issue": issue,
        "causal_identity": identity,
        "mobility_screening": screen,
        "mobility_domain_before": screen.get(
            "mobility_domain_before_candidate_arcs",
            full_cert.get("candidate_move_continuous_arc_count"),
        ),
        "mobility_domain_after": screen.get(
            "mobility_domain_after_candidate_arcs",
            restricted_cert.get("candidate_move_continuous_arc_count"),
        ),
        "full_miqcp_z": full_z,
        "restricted_miqcp_z": restricted_z,
        "stress_gap_absolute": delta_z,
        "stress_gap_relative": delta_z / full_z if abs(full_z) > 1e-12 else None,
        "full_stress_exposure_pu_hours": full_exposure,
        "restricted_stress_exposure_pu_hours": restricted_exposure,
        "stress_exposure_gap_absolute": delta_exposure,
        "stress_exposure_gap_relative": (
            delta_exposure / full_exposure if abs(full_exposure) > 1e-12 else None
        ),
        "fresh_ac_z_full": full_ac,
        "fresh_ac_z_restricted": restricted_ac,
        "fresh_ac_stress_gap": delta_ac,
        "fresh_ac_hard_constraint_pass_full": bool(
            full["exact_ac"]["hard_constraint_pass"]
        ),
        "fresh_ac_hard_constraint_pass_restricted": bool(
            restricted["exact_ac"]["hard_constraint_pass"]
        ),
        "full_route": _routes(full_root, method, issue, full),
        "restricted_route": _routes(
            restricted_root, method, issue, restricted
        ),
        "full_runtime_seconds": _finite(full["runtime_seconds"], "full runtime"),
        "restricted_runtime_seconds": _finite(
            restricted["runtime_seconds"], "restricted runtime"
        ),
        "full_gurobi_runtime_seconds": _finite(
            full_cert["runtime_s"], "full Gurobi runtime"
        ),
        "restricted_gurobi_runtime_seconds": _finite(
            restricted_cert["runtime_s"], "restricted Gurobi runtime"
        ),
        "full_termination": _termination(full_root, method, issue),
        "restricted_termination": _termination(restricted_root, method, issue),
        "future_actual_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-root", type=Path, required=True)
    parser.add_argument("--restricted-root", type=Path, required=True)
    parser.add_argument("--method", default="B07")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.full_root.resolve(),
        args.restricted_root.resolve(),
        args.method,
        args.issue,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: result[key] for key in (
        "status", "stress_gap_absolute", "stress_gap_relative",
        "fresh_ac_stress_gap", "full_runtime_seconds", "restricted_runtime_seconds",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
