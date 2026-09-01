#!/usr/bin/env python3
"""Write the V28 input authority matrix and 15-minute contract."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"
RAW = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터")


ROWS = [
    ("AIDC workload", "B2/B3 LightGBM frozen through 2025-03-31", "Kestrel realized H100 jobs", "GPU-h", "forecast/actual separated"),
    ("weather", "NOAA GFS 06Z f008-f032 range messages", "NOAA Melbourne 94866099999 observations", "degC/%/Pa/m/s", "GFS/NOAA separated"),
    ("grid demand", "latest complete causal VIC1 predispatch vintage", "AEMO VIC1 operational demand", "MW", "no vintage mixing"),
    ("PV", "latest complete causal VIC1 rooftop-PV vintage", "AEMO realized rooftop PV", "MW", "no forecast substitution"),
    ("traffic", "frozen D-1 traffic support authority", "frozen realized replay authority", "15-minute mobility factors", "same mapping"),
    ("Mobile ESS mobility", "frozen safe ETA/route schedule", "realized travel/availability/energy", "slot/location/kWh", "fixed execution gates"),
    ("AIDC site allocation", "V22SR1 frozen 12-site weights", "same engineering weights", "fraction", "sum=1"),
    ("rack/cohort", "V16 frozen nonuniform 48-rack authority", "same resource authority", "GPU/service", "no uniform allocation"),
]


def atomic_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def main() -> None:
    with (OUT / "V28_FINAL_INPUT_AUTHORITY_MATRIX.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("domain", "dayahead_authority", "actual_authority", "units", "firewall"))
        writer.writerows(ROWS)
    atomic_json("V28_FINAL_15MIN_TIME_CONTRACT.json", {
        "artifact_id": "V28_FINAL_15MIN_TIME_CONTRACT_V1",
        "timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "resolution_minutes": 15,
        "slots_per_day": 96,
        "slot_labels": [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)],
        "cutoff": "D-1 18:00 fixed AEST",
        "aggregation": "INTERVAL_ENERGY_CONSERVING_MEAN_POWER",
        "5_minute_control_path": False,
        "288_slots_per_day": False,
        "hourly_optimization": False,
    })
    atomic_json("V28_FINAL_INPUT_COVERAGE.json", {
        "artifact_id": "V28_FINAL_INPUT_COVERAGE_V1",
        "April": {"start": "2025-04-01", "end": "2025-04-30", "expected_days": 30, "policy": "FULL_MONTH_INTEGRATION_PREFLIGHT"},
        "May": {"start": "2025-05-01", "end": "2025-05-31", "expected_days": 31, "policy": "FINAL_MAY_OPERATIONAL_EVALUATION_CAMPAIGN"},
        "raw_root": str(RAW),
        "raw_root_exists": RAW.exists(),
        "implementation_schema_ready": True,
        "per_day_content_check": "MANDATORY_STEP_01_INPUT_AUTHORITY_CHECK",
        "missing_actual_behavior": "FAIL_DAY_NO_FORECAST_SUBSTITUTION",
        "future_actual_reads_before_DA_freeze": 0,
        "actual_namespace_open_before_DA_freeze": 0,
    })


if __name__ == "__main__":
    main()
