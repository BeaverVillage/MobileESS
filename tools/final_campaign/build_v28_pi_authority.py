#!/usr/bin/env python3
"""Write the final V28 perfect-information contract."""

from __future__ import annotations

import csv
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"


def main() -> None:
    contract = {
        "artifact_id": "V28_PI_CONTRACT_V1", "status": "IMPLEMENTATION_READY",
        "case": "B3", "namespace": "PERFECT_INFORMATION_SEPARATE_EXPOST",
        "known_before_PI_optimization": ["realized_AIDC_workload", "realized_weather", "realized_grid_demand", "realized_PV", "realized_mobility_travel"],
        "same_system_required": ["15_minute_96_slot_horizon", "12_AIDC_sites", "same_MESS", "same_capacities", "same_objective", "same_constraints", "same_IEEE123_feeder", "same_C1", "same_OpenDSS", "same_tolerances"],
        "primary_solver": "CL_MC_BD", "additional_resources": False,
        "leakage_to_dayahead": False, "Fresh_OpenDSS_slots": 96,
        "regret_primary": "rho_max_B3_ACTUAL-rho_max_B3_PI",
    }
    (OUT / "V28_PI_CONTRACT.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (OUT / "FINAL_PERFECT_INFORMATION_ORACLE_V1.json").write_text(json.dumps({"artifact_id": "FINAL_PERFECT_INFORMATION_ORACLE_V1", "contract": contract}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    with (OUT / "V28_PI_DAILY_RESULTS.csv").open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerow(("date", "status", "rho_max_ACTUAL", "rho_max_PI", "R_op_AC", "objective_regret", "backlog_regret"))


if __name__ == "__main__":
    main()
