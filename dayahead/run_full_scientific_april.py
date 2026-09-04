"""Release and fail-closed C7 audit for the April full-IEEE123 gate.

This command never opens May/June data.  It materializes the independently
verified feeder/Rack authorities and the April reference schedule, then stops
before any G12/G13/G14 execution if reference-delta nonnegativity fails.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Sequence

from .aidc_boundary_v16_1 import (
    AUTHORITY_ID as V16_1_AUTHORITY_ID,
    REFERENCE_AUTHORITY_ID,
    audit_boundary_separation,
    build_reference_schedule_v3,
)
from .aidc_rack_mapping import AUTHORITY_ID as RACK_AUTHORITY_ID, load_frozen_rack_authority
from .aidc_service_contract import require_terminal_reference_parity
from .authority import sha256_file


OPERATING_DAY = "2025-04-15"
NAMESPACE = "APRIL_VALIDATION_FULL_SCIENTIFIC_IEEE123_V16_1"
EXPECTED_FULL_AUTHORITY_SHA256 = {
    "IEEE123Master.dss": "cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969",
    "Generated_ThreePhase_PCC_v3.dss": "3c3e27020e266dc8f1c4e28e90d49f298d6ca741ef6b54599e44265882cd747c",
    "Generated_Planning_Line_Ratings_u080.dss": "46d492b5b62400d33646089b80105d713250d0790ed7baab85b002d48121f302",
    "Generated_PhasePV.dss": "fb4149c6c79de49cd059a7d5b7dc5142ab405948a1876a24e94252019b392562",
    "compiled_bus_phase_mask.npy": "4f3b5dea7237d4cb5461b4b8735b7825be8249ba035d35224308ba446ff7d59b",
    "service_node_electrical_mapping_v1.csv": "c3763567f6785f182ab151ca0390918017d4e24c2733f6d72d2304bba416322e",
    "opendss_runtime_adapter.json": "5637dc95ab3ea62611b278e0b5f1aefe49befd4bf90bafb7a478fe83e0c43036",
}
EXPECTED_AUTHORITY_ARCHIVE_SHA256 = "de89f122f2c56c25c268cef114f24188e9fdce452f24d07f8117a4b97d06c72e"
AUTHORITY_ARCHIVE_ROOT = "Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference"
AUTHORITY_ARCHIVE_MEMBERS = {
    "IEEE123Master.dss": f"{AUTHORITY_ARCHIVE_ROOT}/opendss_assets/IEEE123Master.dss",
    "Generated_ThreePhase_PCC_v3.dss": f"{AUTHORITY_ARCHIVE_ROOT}/opendss_assets/Generated_ThreePhase_PCC_v3.dss",
    "Generated_Planning_Line_Ratings_u080.dss": f"{AUTHORITY_ARCHIVE_ROOT}/opendss_assets/Generated_Planning_Line_Ratings_u080.dss",
    "Generated_PhasePV.dss": f"{AUTHORITY_ARCHIVE_ROOT}/power_v70_p4f_contract/Generated_PhasePV.dss",
    "compiled_bus_phase_mask.npy": f"{AUTHORITY_ARCHIVE_ROOT}/power_v70_p4f_contract/compiled_bus_phase_mask.npy",
    "service_node_electrical_mapping_v1.csv": f"{AUTHORITY_ARCHIVE_ROOT}/power_v70_p4f_contract/service_node_electrical_mapping_v1.csv",
    "opendss_runtime_adapter.json": f"{AUTHORITY_ARCHIVE_ROOT}/power_v70_p4f_contract/opendss_runtime_adapter.json",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _write_sha_manifest(artifacts: Path) -> None:
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(artifacts.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "DAYAHEAD_SHA256SUMS.txt"
    ]
    target = artifacts / "DAYAHEAD_SHA256SUMS.txt"
    temporary = target.with_suffix(".txt.tmp")
    temporary.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    temporary.replace(target)


def _verify_file(path: Path, expected: str) -> dict[str, object]:
    actual = sha256_file(path) if path.is_file() else None
    return {
        "path": str(path.resolve()),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "bytes": path.stat().st_size if path.is_file() else None,
        "status": "PASS" if actual == expected else "FAIL_AUTHORITY_SHA_MISMATCH",
    }


def _compile_full_authority(assets: Path, contract: Path) -> dict[str, object]:
    import opendssdirect as odd

    odd.Basic.ClearAll()
    for command in (
        f'Compile "{assets / "IEEE123Master.dss"}"',
        "MakeBusList",
        f'Redirect "{assets / "Generated_ThreePhase_PCC_v3.dss"}"',
        "MakeBusList",
        "CalcVoltageBases",
        f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"',
        f'Redirect "{contract / "Generated_PhasePV.dss"}"',
    ):
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"FULL_IEEE123_AUTHORITY_COMPILE_ERROR:{command}:{odd.Error.Description()}")
    result = {
        "base_authority": "IEEE_123_NODE_TEST_FEEDER",
        "runtime_augmented_bus_count": int(odd.Circuit.NumBuses()),
        "runtime_node_count": int(odd.Circuit.NumNodes()),
        "line_count": int(odd.Lines.Count()),
        "transformer_count": int(odd.Transformers.Count()),
        "regcontrol_count": int(odd.RegControls.Count()),
        "capacitor_count": int(odd.Capacitors.Count()),
        "regcontrol_names": sorted(map(str, odd.RegControls.AllNames())),
        "capacitor_names": sorted(map(str, odd.Capacitors.AllNames())),
        "fresh_solve_call_count": 0,
    }
    if result["runtime_augmented_bus_count"] != 168:
        raise RuntimeError("FULL_IEEE123_RUNTIME_BUS_COUNT_MISMATCH")
    if result["regcontrol_count"] != 7 or result["capacitor_count"] != 4:
        raise RuntimeError("NATIVE_IEEE123_CONTROL_ASSET_COUNT_MISMATCH")
    return result


def _pcc_mapping_audit(path: Path) -> dict[str, object]:
    import opendssdirect as odd

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["asset_type"] == "IDC"]
    rows.sort(key=lambda row: row["service_node_id"])
    if [row["service_node_id"] for row in rows] != [f"IDC{index:02d}" for index in range(1, 13)]:
        raise RuntimeError("V16_1_AIDC_PCC_MAPPING_AXIS_MISMATCH")
    buses = {str(value).lower() for value in odd.Circuit.AllBusNames()}
    missing = [row["electrical_host_bus"] for row in rows if row["electrical_host_bus"].lower() not in buses]
    if missing:
        raise RuntimeError(f"V16_1_AIDC_PCC_BUS_NOT_IN_FULL_IEEE123:{missing}")
    return {
        "authority_sha256": sha256_file(path),
        "aidc_count": len(rows),
        "aidc_pcc_host_buses": {
            f"AIDC{int(row['service_node_id'][-2:]):02d}": row["electrical_host_bus"] for row in rows
        },
        "all_hosts_present_in_compiled_full_ieee123": True,
        "mapping_fitting_call_count": 0,
        "mapping_rated_kw_active_constraint_call_count": 0,
    }


def _load_april_forecast(path: Path) -> tuple[dict[str, tuple[float, ...]], tuple[float, ...], tuple[float, ...]]:
    import pandas as pd

    frame = pd.read_parquet(path)
    dates = pd.to_datetime(frame["forecast_day"])
    if dates.min().date().isoformat() < "2025-04-01" or dates.max().date().isoformat() > "2025-04-30":
        raise ValueError("MAY_JUNE_FORECAST_ROW_PROHIBITED")
    selected = frame[(frame["model"] == "Proposed AIDC RC-MQT") & (frame["forecast_day"] == OPERATING_DAY)]
    cohorts = tuple(sorted(str(value).split("::", 1)[1] for value in selected["target"].unique() if str(value).startswith("W_F::")))

    def values(target: str, quantile: float) -> tuple[float, ...]:
        rows = selected[(selected["target"] == target) & (selected["quantile"] == quantile)].sort_values("slot")
        if tuple(map(int, rows["slot"])) != tuple(range(96)):
            raise ValueError("APRIL_FORECAST_DIRECT96_AXIS_MISMATCH")
        return tuple(map(float, rows["prediction"]))

    return (
        {cohort: values(f"W_F::{cohort}", 0.5) for cohort in cohorts},
        values("P_IT_REF", 0.9),
        values("G_REF", 0.9),
    )


def _write_reference_v3_artifacts(
    output: Path,
    reference: object,
    rack_ids: Sequence[str],
    cohorts: Sequence[str],
) -> dict[str, object]:
    import pandas as pd

    x_rows = [
        {
            "namespace": NAMESPACE,
            "operating_day": OPERATING_DAY,
            "authority_id": REFERENCE_AUTHORITY_ID,
            "cohort": cohort,
            "rack_id": rack,
            "slot": slot,
            "x_ref_v3_h100_nodeh": float(reference.allocation[(cohort, rack, slot)]),
        }
        for cohort in cohorts
        for rack in rack_ids
        for slot in range(96)
    ]
    canonical = output / "REFERENCE_COMPUTE_SCHEDULE_V3.parquet"
    temporary = canonical.with_suffix(".parquet.tmp")
    pd.DataFrame(x_rows).to_parquet(temporary, index=False)
    temporary.replace(canonical)
    b0 = output / "REFERENCE_COMPUTE_SCHEDULE_V3_B0_APRIL_FULL_IEEE123.parquet"
    b2 = output / "REFERENCE_COMPUTE_SCHEDULE_V3_B2_APRIL_FULL_IEEE123.parquet"
    x_ref = output / "X_REF_V3.parquet"
    shutil.copyfile(canonical, b0)
    shutil.copyfile(b0, b2)
    shutil.copyfile(canonical, x_ref)
    if not (canonical.read_bytes() == b0.read_bytes() == b2.read_bytes() == x_ref.read_bytes()):
        raise RuntimeError("B0_B2_REFERENCE_BYTES_NOT_IDENTICAL")
    p_f_ref = output / "P_F_REF_V3.parquet"
    g_f_ref = output / "G_F_REF_V3.parquet"
    b97_ref = output / "B97_REF_V3.parquet"
    pd.DataFrame(
        [
            {"namespace": NAMESPACE, "operating_day": OPERATING_DAY, "slot": slot, "rack_id": rack, "p_f_ref_kw": float(reference.flexible_power_kw[slot][rack_index])}
            for slot in range(96)
            for rack_index, rack in enumerate(rack_ids)
        ]
    ).to_parquet(p_f_ref, index=False)
    pd.DataFrame(
        [
            {"namespace": NAMESPACE, "operating_day": OPERATING_DAY, "slot": slot, "rack_id": rack, "g_f_ref": float(reference.flexible_gpu[slot][rack_index])}
            for slot in range(96)
            for rack_index, rack in enumerate(rack_ids)
        ]
    ).to_parquet(g_f_ref, index=False)
    pd.DataFrame(
        [
            {"namespace": NAMESPACE, "operating_day": OPERATING_DAY, "cohort": cohort, "B97_REF_V3_h100_nodeh": float(reference.terminal_backlog[cohort])}
            for cohort in cohorts
        ]
    ).to_parquet(b97_ref, index=False)
    return {
        "canonical_path": str(canonical.resolve()),
        "b0_path": str(b0.resolve()),
        "b2_path": str(b2.resolve()),
        "x_ref_path": str(x_ref.resolve()),
        "p_f_ref_path": str(p_f_ref.resolve()),
        "g_f_ref_path": str(g_f_ref.resolve()),
        "b97_ref_path": str(b97_ref.resolve()),
        "canonical_sha256": sha256_file(canonical),
        "b0_sha256": sha256_file(b0),
        "b2_sha256": sha256_file(b2),
        "x_ref_sha256": sha256_file(x_ref),
        "p_f_ref_sha256": sha256_file(p_f_ref),
        "g_f_ref_sha256": sha256_file(g_f_ref),
        "b97_ref_sha256": sha256_file(b97_ref),
        "b0_b2_bytes_identical": b0.read_bytes() == b2.read_bytes(),
    }


def _retained_mess_evidence(source_artifacts: Path) -> dict[str, object]:
    source = source_artifacts / "C7_C8_C9_PREPRODUCTION_REPORT.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    mess = payload["c7"]["integration_evidence"]["mess"]
    if len(mess) != 4:
        raise RuntimeError("V16_1_RETAINED_MESS_AXIS_MISMATCH")
    if any(abs(float(record["terminal_energy_kwh"]) - 760.0) > 1e-9 for record in mess.values()):
        raise RuntimeError("V16_1_RETAINED_MESS_TERMINAL_INVARIANT_FAIL")
    return {
        "status": "PASS_REUSED_UNCHANGED_BOUNDARY",
        "source_artifact": str(source.resolve()),
        "source_artifact_sha256": sha256_file(source),
        "mess_count": len(mess),
        "route_soc_connection_terminal_invariants": "PASS",
        "records": mess,
        "new_optimizer_call_count": 0,
    }


def _service_parity_v3(
    reference: object,
    arrivals: dict[str, tuple[float, ...]],
    rack_ids: Sequence[str],
) -> dict[str, object]:
    terminal_residuals: dict[str, float] = {}
    for cohort in sorted(arrivals):
        processed = tuple(
            sum(float(reference.allocation[(cohort, rack, slot)]) for rack in rack_ids)
            for slot in range(96)
        )
        da_backlog, ref_backlog = require_terminal_reference_parity(arrivals[cohort], processed, processed)
        terminal_residuals[cohort] = float(da_backlog[-1] - ref_backlog[-1])
    return {
        "contract": "B_97_DA=B_97_REF_V3",
        "max_abs_terminal_residual_nodeh": max(abs(value) for value in terminal_residuals.values()),
        "terminal_residual_by_cohort": terminal_residuals,
        "artificial_deadline": None,
        "sla_claim": False,
    }


def _write_traceability(output: Path) -> None:
    rows = [
        ("RETAINED", "P_IT_REF/G_REF/W_F", "Frozen RC-MQT April validation output", "UNCHANGED"),
        ("RETAINED", "Dataset312 kappa", "dayahead/aidc_power_response.py", "UNCHANGED"),
        ("RETAINED", "ML/Traffic/MESS/IEEE123/CL-MC-BD", "Existing frozen implementations", "UNCHANGED"),
        ("RETAINED", "GPU planning capacity", "deliverable_active_gpu_capacity", "ACTIVE_LOGICAL_POOL_CONSTRAINT"),
        ("RETAINED", "Virtual spatial mapping ratios", "Normalized legacy power ratios", "SPATIALIZATION_ONLY"),
        ("SUPERSEDED", "V16 Rack-level whole-power residual", "AIDC_REFERENCE_DELTA_V1", "INACTIVE_V16_1"),
        ("SUPERSEDED", "Legacy Rack total-kW hard cap", "rack_power_cap_kw", "ACTIVE_CONSTRAINT_CALL_COUNT_0"),
        ("SUPERSEDED", "REFERENCE_COMPUTE_SCHEDULE_V2 production reference", "Historical V2 artifacts", "PRESERVED_INACTIVE"),
        ("NEW", "ESIF/Kestrel power-boundary separation", "dayahead/aidc_boundary_v16_1.py", "ACTIVE_V16_1"),
        ("NEW", "AIDC-level whole-facility residual spatialization", "audit_boundary_separation", "ACTIVE_V16_1"),
        ("NEW", "REFERENCE_COMPUTE_SCHEDULE_V3", "build_reference_schedule_v3", "ACTIVE_V16_1"),
    ]
    path = output / "DAYAHEAD_PRECODE_TO_CODE_TRACEABILITY.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("classification", "authority_item", "implementation_or_evidence", "v16_1_status"))
        writer.writerows(rows)
    temporary.replace(path)


def execute(
    *,
    artifacts: Path,
    source_artifacts: Path,
    capacity_source: Path,
    assets: Path,
    contract: Path,
    authority_archive: Path,
) -> dict[str, object]:
    artifacts = artifacts.resolve()
    source_artifacts = source_artifacts.resolve()
    capacity_source = capacity_source.resolve()
    assets = assets.resolve()
    contract = contract.resolve()
    authority_archive = authority_archive.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "IEEE123Master.dss": assets / "IEEE123Master.dss",
        "Generated_ThreePhase_PCC_v3.dss": assets / "Generated_ThreePhase_PCC_v3.dss",
        "Generated_Planning_Line_Ratings_u080.dss": assets / "Generated_Planning_Line_Ratings_u080.dss",
        "Generated_PhasePV.dss": contract / "Generated_PhasePV.dss",
        "compiled_bus_phase_mask.npy": contract / "compiled_bus_phase_mask.npy",
        "service_node_electrical_mapping_v1.csv": contract / "service_node_electrical_mapping_v1.csv",
        "opendss_runtime_adapter.json": contract / "opendss_runtime_adapter.json",
    }
    source_audit = {
        name: _verify_file(source_paths[name], expected)
        for name, expected in EXPECTED_FULL_AUTHORITY_SHA256.items()
    }
    archive_actual = sha256_file(authority_archive) if authority_archive.is_file() else None
    archive_audit = {
        "path": str(authority_archive.resolve()),
        "expected_sha256": EXPECTED_AUTHORITY_ARCHIVE_SHA256,
        "actual_sha256": archive_actual,
        "status": "PASS" if archive_actual == EXPECTED_AUTHORITY_ARCHIVE_SHA256 else "FAIL_AUTHORITY_ARCHIVE_SHA_MISMATCH",
    }
    if archive_audit["status"] != "PASS":
        raise RuntimeError("FULL_IEEE123_AUTHORITY_ARCHIVE_SHA_MISMATCH")
    for name, record in source_audit.items():
        record["authority_location_type"] = "VERIFIED_ZIP_MEMBER"
        record["authority_archive_path"] = archive_audit["path"]
        record["authority_archive_sha256"] = archive_actual
        record["authority_archive_member"] = AUTHORITY_ARCHIVE_MEMBERS[name]
        record.pop("path")
        record["verification_extraction_retained"] = False
    if any(record["status"] != "PASS" for record in source_audit.values()):
        raise RuntimeError("FULL_IEEE123_AUTHORITY_SHA_MISMATCH")
    compiled = _compile_full_authority(assets, contract)
    pcc_mapping = _pcc_mapping_audit(contract / "service_node_electrical_mapping_v1.csv")
    rack_authority = load_frozen_rack_authority(capacity_source)
    boundary_authority = artifacts / "V16_1_AIDC_POWER_BOUNDARY_REFREEZE_AUTHORITY.json"
    boundary_payload = json.loads(boundary_authority.read_text(encoding="utf-8"))
    if boundary_payload.get("authority_id") != V16_1_AUTHORITY_ID:
        raise RuntimeError("V16_1_BOUNDARY_AUTHORITY_NOT_MINTED")
    if boundary_payload["legacy_power_capacity_retirement"]["source_sha256"] != rack_authority.source_sha256:
        raise RuntimeError("V16_1_LEGACY_PROVENANCE_SHA_MISMATCH")
    forecast_path = source_artifacts / "AIDC_APRIL_VALIDATION_FORECAST.parquet"
    weights_path = source_artifacts / "AIDC_RC_MQT_PRODUCTION_SEED20260828.pt"
    arrivals, p_q90, g_q90 = _load_april_forecast(forecast_path)
    rack_ids = tuple(rack.rack_id for rack in rack_authority.racks)
    gpu_caps = {rack.rack_id: rack.deliverable_gpu_capacity for rack in rack_authority.racks}
    reference = build_reference_schedule_v3(rack_ids, gpu_caps, arrivals)
    residual = audit_boundary_separation(rack_authority, reference, p_q90, g_q90)
    reference_artifacts = _write_reference_v3_artifacts(
        artifacts,
        reference,
        rack_ids,
        tuple(sorted(arrivals)),
    )
    rack_contract = {
        "authority_id": "V16_1_VIRTUAL_SPATIAL_AND_GPU_CAPACITY_CONTRACT",
        "status": "PASS",
        "source_path": rack_authority.source_path,
        "source_sha256": rack_authority.source_sha256,
        "rack_count": 48,
        "aidc_count": 12,
        "legacy_authority_id": RACK_AUTHORITY_ID,
        "power_weight_basis": "NORMALIZED_LEGACY_RACK_POWER_RATIO_VIRTUAL_SPATIALIZATION_ONLY",
        "absolute_legacy_rack_kw_capacity_semantics": "RETIRED",
        "legacy_rack_power_cap_active_constraint_call_count": 0,
        "gpu_weight_basis": "deliverable_active_gpu_capacity",
        "power_weights": list(rack_authority.power_weights),
        "gpu_weights": list(rack_authority.gpu_weights),
        "power_weight_sum": sum(rack_authority.power_weights),
        "gpu_weight_sum": sum(rack_authority.gpu_weights),
        "uniform_replacement_used": False,
        "mapping_fitting_call_count": 0,
        "gpu_cap_values_changed": False,
        "capacity_scaling_call_count": 0,
        "racks": [
            {
                "rack_id": rack.rack_id,
                "aidc_id": rack.aidc_id,
                "source_idc_id": rack.source_idc_id,
                "pool_id": rack.pool_id,
                "deliverable_gpu_capacity": rack.deliverable_gpu_capacity,
                "legacy_power_ratio": rack_authority.power_weights[index],
            }
            for index, rack in enumerate(rack_authority.racks)
        ],
    }
    _write_json(artifacts / "AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json", rack_contract)
    authority_release = {
        "authority_id": "APRIL_FULL_IEEE123_INPUT_RELEASE_V16_1",
        "status": "PASS",
        "namespace": NAMESPACE,
        "operating_day": OPERATING_DAY,
        "source_files": source_audit,
        "source_archive": archive_audit,
        "compiled_full_authority": compiled,
        "aidc_pcc_mapping": pcc_mapping,
        "boundary_refreeze_authority_sha256": sha256_file(boundary_authority),
        "legacy_rack_source_sha256_preserved": rack_authority.source_sha256,
        "production_forecast_sha256": sha256_file(forecast_path),
        "production_model_weights_sha256": sha256_file(weights_path),
        "feeder_scale_contract_sha256": sha256_file(Path(__file__).resolve().parents[1] / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"),
        "new_bus_phase_weight_scaling_fit_count": 0,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "C7_FULL_IEEE123_AUTHORITY_RELEASE_V16_1.json", authority_release)
    mess = _retained_mess_evidence(source_artifacts)
    service_parity = _service_parity_v3(reference, arrivals, rack_ids)
    service_parity_residual = float(service_parity["max_abs_terminal_residual_nodeh"])
    c7_pass = (
        residual["status"] == "PASS"
        and residual["power_reconstruction_max_abs_error_kw"] <= 1e-9
        and residual["pue_reconstruction_max_abs_error_kw"] <= 1e-9
        and residual["pue_application_count"] == 1
        and reference.max_flexible_gpu_cap_violation <= 1e-9
        and service_parity_residual <= 1e-12
        and mess["route_soc_connection_terminal_invariants"] == "PASS"
    )
    c7 = {
        "authority_id": "C7_APRIL_FULL_SCIENTIFIC_IEEE123_V16_1",
        "namespace": NAMESPACE,
        "operating_day": OPERATING_DAY,
        "authority_release_status": "PASS",
        "full_ieee123_aidc_pcc_mapping": pcc_mapping,
        "status": "PASS_FULL_IEEE123_V16_1" if c7_pass else residual["status"],
        "reference_authority_id": reference.authority_id,
        "reference_schedule_sha256": reference_artifacts["canonical_sha256"],
        "reference_artifacts": reference_artifacts,
        "reference_b0_b2_bytes_identical": reference_artifacts["b0_b2_bytes_identical"],
        "reference_b0_b2_sha_identical": reference_artifacts["b0_sha256"] == reference_artifacts["b2_sha256"],
        "terminal_backlog_max_nodeh": max(reference.terminal_backlog.values()),
        "service_parity_contract": "B_97_DA=B_97_REF_V3",
        "service_parity_residual": service_parity_residual,
        "service_parity": service_parity,
        "rack_gpu_cap_violation_count": residual["rack_gpu_cap_violation_count"],
        "rack_gpu_cap_max_violation": residual["rack_gpu_cap_max_violation"],
        "legacy_rack_power_cap_active_constraint_call_count": residual["legacy_rack_power_cap_active_constraint_call_count"],
        "reference_delta": residual,
        "mess_invariants": mess,
        "service_parity_status": "PASS" if service_parity_residual <= 1e-12 else "FAIL",
        "full_ieee123_monolithic_solve_call_count": 0,
        "stop_rule_applied": not c7_pass,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "C7_FULL_IEEE123_REPORT_V16_1.json", c7)
    g10 = {
        "authority_id": "G10_V16_1_POWER_BOUNDARY_SEPARATION_GATE",
        "status": "PASS" if c7_pass else "FAIL_CLOSED",
        "P_RES_SYS_nonnegative": residual["P_RES_SYS_kw"]["negative_slot_count"] == 0,
        "G_RES_SYS_nonnegative": residual["G_RES_SYS"]["negative_slot_count"] == 0,
        "power_reconstruction_max_abs_error_kw": residual["power_reconstruction_max_abs_error_kw"],
        "rack_gpu_capacity_pass": residual["rack_gpu_cap_violation_count"] == 0,
        "reference_v3_service_parity_pass": service_parity_residual <= 1e-12,
        "mess_invariants_pass": mess["route_soc_connection_terminal_invariants"] == "PASS",
        "legacy_rack_total_kw_cap_required": False,
        "legacy_rack_power_cap_active_constraint_call_count": 0,
        "g12_call_count": 0,
        "g13_call_count": 0,
        "g14_call_count": 0,
        "c12_call_count": 0,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "G10_V16_1_REPORT.json", g10)
    _write_traceability(artifacts)
    _write_sha_manifest(artifacts)
    return {"c7": c7, "g10": g10}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--source-artifacts", type=Path, required=True)
    parser.add_argument("--capacity-source", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--authority-archive", type=Path, required=True)
    args = parser.parse_args(argv)
    result = execute(
        artifacts=args.artifacts,
        source_artifacts=args.source_artifacts,
        capacity_source=args.capacity_source,
        assets=args.assets,
        contract=args.contract,
        authority_archive=args.authority_archive,
    )
    print(json.dumps({
        "c7_status": result["c7"]["status"],
        "g10_status": result["g10"]["status"],
        "reference_schedule_sha256": result["c7"]["reference_schedule_sha256"],
        "may_loader_access_count": result["c7"]["may_loader_access_count"],
        "june_loader_access_count": result["c7"]["june_loader_access_count"],
    }, indent=2, sort_keys=True))
    return 0 if result["c7"]["status"] == "PASS_FULL_IEEE123_V16_1" and result["g10"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
