import json
from pathlib import Path

import pandas as pd

from dayahead.thermal.contracts import ARTIFACT_ROOT, GFS_LEADS, GFS_VARIABLES, START_HEAD


ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / ARTIFACT_ROOT


def read(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def test_raw_inventory_and_nlr_authorities() -> None:
    inventory = read("V24T_RAW_DATA_INVENTORY.json")
    assert inventory["file_count"] == len(inventory["files"])
    assert inventory["source_modified_count"] == 0
    assert all(len(item["sha256"]) == 64 for item in inventory["files"])
    boundary = read("V24T_NLR_POWER_BOUNDARY_AUDIT.json")
    assert boundary["pass"] and boundary["double_count_count"] == 0
    conservation = read("V24T_NLR_POWER_CONSERVATION_AUDIT.json")
    assert conservation["pass"] and conservation["within_tolerance_fraction"] == 1.0
    aligned = read("V24T_NLR_ALIGNMENT_AUDIT.json")
    assert aligned["monotonic"] and aligned["duplicate_timestamp_count"] == 0
    assert aligned["pseudo_sample_count"] == 0


def test_noaa_station_and_decode() -> None:
    station = read("V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json")
    assert station["station_id"] == "94866099999"
    assert abs(station["latitude"] + 37.673333) < 1e-6
    assert abs(station["longitude"] - 144.843333) < 1e-6
    decode = read("V24T_NOAA_ISD_DECODE_AUDIT.json")
    assert decode["encoding"]["TMP"]["scale"] == 10
    assert decode["encoding"]["DEW"]["scale"] == 10
    assert decode["encoding"]["MA1"]["fields"].startswith("altimeter")
    assert decode["quality_fields_preserved"]


def test_gfs_causal_coverage_and_no_full_download() -> None:
    coverage = read("V24T_GFS_FORECAST_COVERAGE.json")
    assert coverage["only_06z"]
    assert coverage["only_f008_f032"]
    assert coverage["future_cycle_read_count"] == 0
    assert coverage["actual_d_day_weather_input_count"] == 0
    assert coverage["full_grib_download_count"] == 0
    preflight = read("V24T_GFS_DOWNLOAD_PREFLIGHT.json")
    assert preflight["under_cap"]
    assert preflight["message_count"] == 7 * len(GFS_LEADS) * len(GFS_VARIABLES)


def test_thermal_acceptance_and_scale_firewall() -> None:
    c2 = read("V24T_C2_DYNAMIC_MODEL.json")
    assert 0 < c2["rho"] < 1 and c2["tau_minutes"] > 0
    assert c2["validation_state_inputs"].endswith("= 0")
    normalization = read("V24T_REFERENCE_PUE_NORMALIZATION.json")
    assert normalization["double_pue_count"] == 0
    assert normalization["extra_1p30_multiplier_count"] == 0
    for audit in normalization["audits"].values():
        assert abs(audit["achieved_overhead_ratio"] - 0.30) < 1e-12
    scale = read("V24T_THERMAL_SCALE_COMPARISON.json")
    assert scale["c0_frozen_peak_mw"] == 0.5288087919579648
    assert scale["peak_force_fit_count"] == 0
    ready = read("V24T_READY_FLAGS.json")
    assert ready["THERMAL_SCALE_REFREEZE_READY"] is False
    assert ready["NEW_GRID_SCIENCE_RUN_READY"] is False
    assert ready["FINAL_GRID_SCIENCE_AUTHORIZED"] is False
