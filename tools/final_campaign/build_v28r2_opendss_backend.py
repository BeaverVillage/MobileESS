#!/usr/bin/env python3
"""Freeze static evidence for the V28R2 Fresh OpenDSS implementation."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import sha256_file
from dayahead.v28r2.opendss_mapping import (
    CAPACITORS, NATIVE_MASTER_SHA256, REGULATORS, FeederAssets,
    aidc_injection_mapping, compile_clean_engine, mess_injection_mapping,
)


OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def write(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, path)


def main() -> None:
    assets = FeederAssets.from_repo(REPO)
    assets.validate()
    adapter = json.loads(assets.runtime_adapter.read_text(encoding="utf-8"))
    pcc = assets.pcc.read_text(encoding="utf-8-sig")
    with assets.service_mapping.open("r", encoding="utf-8-sig", newline="") as stream:
        service_rows = list(csv.DictReader(stream))
    odd, _compiled_adapter = compile_clean_engine(assets)
    compiled = {
        "bus_count": int(odd.Circuit.NumBuses()),
        "present_node_count": int(odd.Circuit.NumNodes()),
        "load_count": int(odd.Loads.Count()),
        "generator_count": int(odd.Generators.Count()),
        "regulator_count": int(odd.RegControls.Count()),
        "capacitor_count": int(odd.Capacitors.Count()),
    }
    odd.Basic.ClearAll()
    source_sha = {
        name: sha256_file(REPO / "dayahead/v28r2" / name)
        for name in ("opendss_mapping.py", "opendss_backend.py", "opendss_results.py")
    }
    mapping = {
        "artifact_id": "V28R2_OPENDSS_MAPPING_VALIDATION_V1",
        "status": "PASS",
        "feeder": "AUDITED_NATIVE_IEEE123_WITH_V16_2_THREE_PHASE_PCC_V4",
        "native_master_sha256": assets.sha256["master"],
        "native_master_expected_sha256": NATIVE_MASTER_SHA256,
        "asset_sha256": assets.sha256,
        "runtime_background_load_count": len(adapter["loads"]),
        "runtime_phase_pv_count": len(adapter["pv_generators"]),
        "service_mapping_rows": len(service_rows),
        "service_mapping_idc_rows": sum(row["asset_type"] == "IDC" for row in service_rows),
        "service_mapping_station_rows": sum(row["asset_type"] == "STA" for row in service_rows),
        "pcc_aidc_load_count": len(re.findall(r"(?im)^New Load\.IDC_IDC\d{2}\b", pcc)),
        "pcc_mess_discharge_element_count": len(re.findall(r"(?im)^New Generator\.MESS_DIS_", pcc)),
        "pcc_mess_charge_element_count": len(re.findall(r"(?im)^New Load\.MESS_CHG_", pcc)),
        "regulator_axis": list(REGULATORS),
        "capacitor_axis": list(CAPACITORS),
        "clean_context_compile_evidence": compiled,
        "OpenDSS_compile_count": 1,
        "OpenDSS_solve_count": 0,
        "phase_mapping": "compiled-present-phase axes from frozen FullGridBinding",
        "new_feeder_created": False,
        "source_sha256": source_sha,
        "OPENDSS_MAPPING_IMPLEMENTATION_READY": True,
    }
    if (
        mapping["pcc_aidc_load_count"] != 12
        or mapping["pcc_mess_discharge_element_count"] != 24
        or mapping["pcc_mess_charge_element_count"] != 24
        or mapping["service_mapping_idc_rows"] != 12
        or mapping["service_mapping_station_rows"] != 12
        or compiled["present_node_count"] != 386
        or compiled["regulator_count"] != 7
        or compiled["capacitor_count"] != 4
    ):
        raise RuntimeError(f"V28R2_OPENDSS_MAPPING_AXIS:{mapping}")
    write("V28R2_OPENDSS_MAPPING_VALIDATION.json", mapping)

    tests = {
        "AIDC_positive_consumption": aidc_injection_mapping(100.0, 32.8684105),
        "MESS_positive_discharge": mess_injection_mapping(100.0, 25.0),
        "MESS_negative_charge": mess_injection_mapping(-100.0, -25.0),
        "MESS_zero_active_reactive_only": mess_injection_mapping(0.0, 25.0),
    }
    passed = (
        tests["AIDC_positive_consumption"]["load_p_kw"] == 100.0
        and tests["MESS_positive_discharge"]["generator_p_kw"] == 100.0
        and tests["MESS_positive_discharge"]["charging_load_p_kw"] == 0.0
        and tests["MESS_negative_charge"]["generator_p_kw"] == 0.0
        and tests["MESS_negative_charge"]["charging_load_p_kw"] == 100.0
        and tests["MESS_zero_active_reactive_only"]["generator_q_kvar"] == 25.0
    )
    if not passed:
        raise RuntimeError("V28R2_OPENDSS_INJECTION_SIGN")
    write("V28R2_OPENDSS_INJECTION_SIGN_TEST.json", {
        "artifact_id": "V28R2_OPENDSS_INJECTION_SIGN_TEST_V1",
        "status": "PASS", "tests": tests,
        "deterministic_repeat_equal": tests == {
            "AIDC_positive_consumption": aidc_injection_mapping(100.0, 32.8684105),
            "MESS_positive_discharge": mess_injection_mapping(100.0, 25.0),
            "MESS_negative_charge": mess_injection_mapping(-100.0, -25.0),
            "MESS_zero_active_reactive_only": mess_injection_mapping(0.0, 25.0),
        },
        "OpenDSS_solve_count": 0,
        "physical_sign_confirmation_deferred_to_heavy_smoke": True,
    })
    write("V28R2_OPENDSS_PRODUCTION_CONTRACT.json", {
        "artifact_id": "V28R2_OPENDSS_PRODUCTION_CONTRACT_V1",
        "status": "PASS_IMPLEMENTATION_READY",
        "engine_context": "opendssdirect.NewContext per trajectory",
        "slots_per_trajectory": 96,
        "sequential_solves": True,
        "schedule_immutable_sha_before_after": True,
        "native_controls": "D-1 native RegControl/capacitor states frozen identically across cases",
        "collected": [
            "convergence", "phase_voltage", "line_phase_current",
            "transformer_phase_current_and_total_kVA", "losses",
            "regulator_state", "capacitor_state", "phase_masks",
            "rho_max_AC", "p95", "p99", "Vmin", "Vmax", "violation_exposure",
        ],
        "physical_violation_is_result": True,
        "unexpected_nonconvergence_is_pipeline_failure": True,
        "source_sha256": source_sha,
        "FRESH_OPENDSS_IMPLEMENTATION_READY": True,
        "FRESH_OPENDSS_BACKEND_READY": False,
        "readiness_blocker": "one authorized end-to-end heavy smoke has not run",
    })


if __name__ == "__main__":
    main()
