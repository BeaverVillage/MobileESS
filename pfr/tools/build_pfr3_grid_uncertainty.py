"""Bind the frozen P6A3 causal grid quantile envelope to PFR3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from pfr.grid_uncertainty import audit_grid_quantile_envelope


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--frozen-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frozen = json.loads(args.frozen_audit.read_text(encoding="utf-8"))
    if frozen.get("status") != "PASS_P6A3_FULL_YEAR_CAUSAL_FORECAST_NO_LEAKAGE":
        raise RuntimeError("P6A3 frozen audit is not PASS")
    leakage = frozen.get("leakage_audit", {})
    if leakage.get("status") != "PASS" or leakage.get("max_feature_minus_issue_ext") != -1:
        raise RuntimeError("P6A3 causal feature audit failed")
    if leakage.get("realized_values_used_for_evaluation_only") is not True:
        raise RuntimeError("P6A3 realized-value separation is not authoritative")
    forecast_sha = sha256(args.forecast)
    if forecast_sha != frozen.get("forecast_file_sha256"):
        raise RuntimeError("P6A3 forecast SHA-256 mismatch")

    with np.load(args.forecast, allow_pickle=False) as source:
        audit = audit_grid_quantile_envelope(
            source["issue_step"],
            source["q10"],
            source["q50"],
            source["q90"],
            tuple(str(value) for value in source["target_names"]),
        )
    result = {
        "schema_version": "PFR3_GRID_UNCERTAINTY_V13_2",
        "status": "PASS",
        "authority_type": "CAUSAL_ADAPTIVE_QUANTILE_ENVELOPE",
        "calibration": leakage["calibration"],
        "issue_convention": leakage["issue_convention"],
        "lead_convention": leakage["lead_convention"],
        "future_actual_used": False,
        "realized_values_used_for_evaluation_only": True,
        "post_outcome_retuning": False,
        "physical_grid_set": {
            "upper_net_demand": "demand_q90_mw - rooftop_pv_q10_mw",
            "lower_net_demand": "demand_q10_mw - rooftop_pv_q90_mw",
            "price_role": "OBJECTIVE_UNCERTAINTY_NOT_PHYSICAL_SAFETY_MARGIN",
        },
        "tensor_audit": audit.__dict__,
        "source_sha256": {
            "forecast": forecast_sha,
            "frozen_audit": sha256(args.frozen_audit),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f"{args.output.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
