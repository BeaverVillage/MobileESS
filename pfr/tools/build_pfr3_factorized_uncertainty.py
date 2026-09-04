"""Bind workload/grid residual calibration to the PFR3 mobility joint set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from pfr.factorized_uncertainty import (
    FactorizedUncertaintySet,
    NormalizedResidualObservation,
    fit_component_calibration,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobility-contract", type=Path, required=True)
    parser.add_argument("--residual-csv", type=Path, required=True)
    parser.add_argument("--workload-scale-authority", required=True)
    parser.add_argument("--grid-scale-authority", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    mobility = json.loads(args.mobility_contract.read_text(encoding="utf-8"))
    if mobility.get("status") != "PASS" or mobility.get("calibration", {}).get("year") != 2024:
        raise RuntimeError("mobility joint calibration is not a 2024 PASS authority")
    rows: list[NormalizedResidualObservation] = []
    with args.residual_csv.open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            rows.append(
                NormalizedResidualObservation(
                    family=raw["family"],
                    block_id=raw["block_id"],
                    actual=float(raw["actual"]),
                    predicted=float(raw["predicted"]),
                    frozen_scale=float(raw["frozen_scale"]),
                    source_year=int(raw["source_year"]),
                )
            )
    workload = fit_component_calibration(
        (row for row in rows if row.family == "workload"),
        family="workload",
        target_coverage=0.95,
        frozen_scale_authority=args.workload_scale_authority,
    )
    grid = fit_component_calibration(
        (row for row in rows if row.family == "grid"),
        family="grid",
        target_coverage=0.95,
        frozen_scale_authority=args.grid_scale_authority,
    )
    factorized = FactorizedUncertaintySet(
        mobility_joint_quantile=float(mobility["calibration"]["joint_quantile"]),
        workload=workload,
        grid=grid,
    )
    result = {
        "schema_version": "PFR3_FACTORIZED_UNCERTAINTY_V13_2",
        "status": "PASS",
        "calibration_year": 2024,
        "target_component_coverage": 0.95,
        "no_2025_retuning": True,
        "row_wise_cross_dataset_merge": False,
        "uncertainty_set": factorized.as_mapping(),
        "source_sha256": {
            "mobility_contract": sha256(args.mobility_contract),
            "workload_grid_residual_csv": sha256(args.residual_csv),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f"{args.output.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
