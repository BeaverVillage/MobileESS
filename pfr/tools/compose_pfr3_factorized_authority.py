"""Compose the three separately calibrated PFR3 uncertainty authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"authority must be a JSON object: {path}")
    return value


def compose(mobility_path: Path, workload_path: Path, grid_path: Path) -> dict[str, Any]:
    mobility = _load(mobility_path)
    workload = _load(workload_path)
    grid = _load(grid_path)

    gates = {
        "mobility_joint_eta_energy_pass": (
            mobility.get("status") == "PASS"
            and mobility.get("no_2025_retuning") is True
            and mobility.get("row_wise_cross_dataset_merge") is False
            and "max((T_actual-T_q50)" in str(mobility.get("score", ""))
            and "(E_actual-E_q50)" in str(mobility.get("score", ""))
        ),
        "workload_global_first_recalibration_pass": (
            workload.get("status") == "PASS"
            and workload.get("calibration_year") == 2024
            and workload.get("no_2025_recalibration") is True
            and workload.get("old_idc_residual_reused") is False
            and workload.get("new_spatial_operator_applied_after_global_calibration") is True
        ),
        "grid_causal_adaptive_envelope_pass": (
            grid.get("status") == "PASS"
            and grid.get("authority_type") == "CAUSAL_ADAPTIVE_QUANTILE_ENVELOPE"
            and grid.get("future_actual_used") is False
            and grid.get("post_outcome_retuning") is False
            and grid.get("realized_values_used_for_evaluation_only") is True
            and grid.get("tensor_audit", {}).get("nonfinite_values") == 0
            and grid.get("tensor_audit", {}).get("quantile_crossings") == 0
        ),
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    return {
        "schema_version": "PFR3_FACTORIZED_UNCERTAINTY_V13_2",
        "stage": "PFR3",
        "status": status,
        "uncertainty_universe": "U_t = U_mob x U_work x U_grid",
        "composition": "CARTESIAN_PRODUCT_OF_SEPARATELY_CALIBRATED_AUTHORITIES",
        "joint_cross_factor_recalibration": False,
        "gates": gates,
        "components": {
            "U_mob": {
                "role": "JOINT_ETA_ENERGY_CALIBRATED_SET",
                "authority": mobility.get("authority"),
                "target_joint_coverage": mobility.get("target_joint_coverage"),
                "joint_quantile": mobility.get("calibration", {}).get("joint_quantile"),
                "source_sha256": _sha256(mobility_path),
            },
            "U_work": {
                "role": "GLOBAL_FIRST_WORKLOAD_RESERVE_WITH_FIXED_IDC_MAPPING",
                "target_coverage": workload.get("target_coverage"),
                "normalized_daily_joint_quantile": workload.get(
                    "normalized_daily_joint_quantile"
                ),
                "source_sha256": _sha256(workload_path),
            },
            "U_grid": {
                "role": "CAUSAL_ADAPTIVE_GRID_QUANTILE_ENVELOPE",
                "authority_type": grid.get("authority_type"),
                "physical_grid_set": grid.get("physical_grid_set"),
                "source_sha256": _sha256(grid_path),
            },
        },
        "next_authorized_stage": "PFR4" if status == "PASS" else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobility", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = compose(args.mobility, args.workload, args.grid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
