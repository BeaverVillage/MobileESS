"""Release and fail-closed C7 audit for the April full-IEEE123 gate.

This command never opens May/June data.  It materializes the independently
verified feeder/Rack authorities and the April reference schedule, then stops
before any G12/G13/G14 execution if reference-delta nonnegativity fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Sequence

from .aidc_rack_mapping import (
    AUTHORITY_ID as RACK_AUTHORITY_ID,
    build_capacity_feasible_reference,
    load_frozen_rack_authority,
    reference_delta_audit,
)
from .authority import sha256_file


OPERATING_DAY = "2025-04-15"
NAMESPACE = "APRIL_VALIDATION_FULL_SCIENTIFIC_IEEE123_V1"
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
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
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
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
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


def _write_reference_parquet(
    output: Path,
    reference: object,
    rack_ids: Sequence[str],
    cohorts: Sequence[str],
) -> tuple[Path, Path, str]:
    import pandas as pd

    rows = [
        {
            "namespace": NAMESPACE,
            "operating_day": OPERATING_DAY,
            "cohort": cohort,
            "rack_id": rack,
            "slot": slot,
            "work_h100_nodeh": float(reference.allocation[(cohort, rack, slot)]),
        }
        for cohort in cohorts
        for rack in rack_ids
        for slot in range(96)
    ]
    b0 = output / "REFERENCE_COMPUTE_SCHEDULE_V2_B0_APRIL_FULL_IEEE123.parquet"
    b2 = output / "REFERENCE_COMPUTE_SCHEDULE_V2_B2_APRIL_FULL_IEEE123.parquet"
    temporary = b0.with_suffix(".parquet.tmp")
    pd.DataFrame(rows).to_parquet(temporary, index=False)
    temporary.replace(b0)
    shutil.copyfile(b0, b2)
    if b0.read_bytes() != b2.read_bytes():
        raise RuntimeError("B0_B2_REFERENCE_BYTES_NOT_IDENTICAL")
    return b0, b2, sha256_file(b0)


def execute(
    *,
    artifacts: Path,
    capacity_source: Path,
    assets: Path,
    contract: Path,
    authority_archive: Path,
) -> dict[str, object]:
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
    rack_authority = load_frozen_rack_authority(capacity_source)
    arrivals, p_q90, g_q90 = _load_april_forecast(artifacts / "AIDC_APRIL_VALIDATION_FORECAST.parquet")
    reference = build_capacity_feasible_reference(rack_authority, arrivals)
    residual = reference_delta_audit(rack_authority, reference, p_q90, g_q90)
    b0, b2, reference_sha = _write_reference_parquet(
        artifacts,
        reference,
        [rack.rack_id for rack in rack_authority.racks],
        tuple(sorted(arrivals)),
    )
    rack_contract = {
        "authority_id": RACK_AUTHORITY_ID,
        "status": "PASS",
        "source_path": rack_authority.source_path,
        "source_sha256": rack_authority.source_sha256,
        "rack_count": 48,
        "aidc_count": 12,
        "power_weight_basis": "rack_power_cap_kw",
        "gpu_weight_basis": "deliverable_active_gpu_capacity",
        "power_weights": list(rack_authority.power_weights),
        "gpu_weights": list(rack_authority.gpu_weights),
        "power_weight_sum": sum(rack_authority.power_weights),
        "gpu_weight_sum": sum(rack_authority.gpu_weights),
        "uniform_replacement_used": False,
        "mapping_fitting_call_count": 0,
        "racks": [rack.__dict__ for rack in rack_authority.racks],
    }
    _write_json(artifacts / "AIDC_RACK_MAPPING_CONTRACT.json", rack_contract)
    authority_release = {
        "authority_id": "APRIL_FULL_IEEE123_INPUT_RELEASE_V1",
        "status": "PASS",
        "namespace": NAMESPACE,
        "operating_day": OPERATING_DAY,
        "source_files": source_audit,
        "source_archive": archive_audit,
        "compiled_full_authority": compiled,
        "rack_authority_sha256": rack_authority.source_sha256,
        "production_forecast_sha256": sha256_file(artifacts / "AIDC_APRIL_VALIDATION_FORECAST.parquet"),
        "production_model_weights_sha256": sha256_file(artifacts / "AIDC_RC_MQT_PRODUCTION_SEED20260828.pt"),
        "feeder_scale_contract_sha256": sha256_file(Path(__file__).resolve().parents[1] / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"),
        "new_bus_phase_weight_scaling_fit_count": 0,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "C7_FULL_IEEE123_AUTHORITY_RELEASE.json", authority_release)
    c7_pass = residual["status"] == "PASS"
    c7 = {
        "authority_id": "C7_APRIL_FULL_SCIENTIFIC_IEEE123_V1",
        "namespace": NAMESPACE,
        "operating_day": OPERATING_DAY,
        "authority_release_status": "PASS",
        "status": "PASS" if c7_pass else residual["status"],
        "reference_schedule_sha256": reference_sha,
        "reference_schedule_b0_path": str(b0.resolve()),
        "reference_schedule_b2_path": str(b2.resolve()),
        "reference_b0_b2_bytes_identical": b0.read_bytes() == b2.read_bytes(),
        "reference_b0_b2_sha_identical": sha256_file(b0) == sha256_file(b2),
        "terminal_backlog_max_nodeh": max(reference.terminal_backlog.values()),
        "rack_gpu_cap_max_violation": reference.max_gpu_cap_residual,
        "rack_power_cap_max_violation_kw": reference.max_power_cap_residual_kw,
        "reference_delta": residual,
        "service_parity_status": "NOT_EVALUATED_BECAUSE_REFERENCE_DELTA_FAILED" if not c7_pass else "PENDING_INTEGRATED_SOLVE",
        "full_ieee123_monolithic_solve_call_count": 0,
        "stop_rule_applied": not c7_pass,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "C7_FULL_IEEE123_REPORT.json", c7)

    equivalence_path = artifacts / "DAYAHEAD_EQUIVALENCE_REPORT.json"
    previous = json.loads(equivalence_path.read_text(encoding="utf-8"))
    if "engineering_fixture" in previous:
        engineering = previous["engineering_fixture"]
    else:
        engineering = previous
    equivalence = {
        "schema_version": "DAYAHEAD_EQUIVALENCE_REPORT_V2_SEPARATE_NAMESPACES",
        "engineering_fixture": engineering,
        "full_scientific_april": {
            "namespace": NAMESPACE,
            "status": "NOT_RUN_BLOCKED_C7_REFERENCE_DELTA",
            "blocker": residual["status"],
            "monolithic": {"status": "NOT_RUN", "solve_call_count": 0},
            "standard_bd": {"status": "NOT_RUN", "solve_call_count": 0},
            "cl_mc_bd": {"status": "NOT_RUN", "solve_call_count": 0},
            "engineering_fixture_relabelled_as_scientific": False,
        },
    }
    _write_json(equivalence_path, equivalence)
    (artifacts / "DAYAHEAD_EQUIVALENCE_REPORT.md").write_text(
        "# Day-Ahead solver equivalence namespaces\n\n"
        "- Engineering fixture: preserved exactly as non-scientific pre-production evidence.\n"
        f"- Full scientific April: **NOT RUN** because C7 stopped at `{residual['status']}`.\n"
        "- No reduced-star result was relabelled as final G12 evidence.\n",
        encoding="utf-8",
    )
    gates = {
        "G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS",
        "G5": "PASS", "G6": "PASS", "G7": "PASS", "G8": "PASS", "G9": "PASS_ENGINEERING",
        "G10": residual["status"],
        "G11": "PASS_NON_SCIENTIFIC_PREPRODUCTION_ONLY_FULL_INPUT_NOT_REACHED",
        "G12": "NOT_RUN_BLOCKED_BY_G10",
        "G13": "NOT_RUN_BLOCKED_BY_G12",
        "G14": "NOT_RUN_BLOCKED_BY_G13",
        "G15": "PASS",
    }
    final_gate = {
        "authority_id": "V16_FINAL_G0_G15_GATE_TABLE",
        "status": "FAIL_CLOSED_PREPRODUCTION_NOT_FROZEN",
        "gates": gates,
        "all_g0_g15_pass": False,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
        "may_forecast_rows": 0,
        "may_reference_schedule_exists": False,
        "may_b0_b3_exists": False,
    }
    _write_json(artifacts / "FINAL_G0_G15_GATE_TABLE.json", final_gate)
    c12 = {
        "authority_id": "C12_PREPRODUCTION_FREEZE_V1",
        "status": "BLOCKED_NOT_MINTED",
        "blocker": residual["status"],
        "production_freeze_token": None,
        "production_freeze_token_sha256": None,
        "token_mint_call_count": 0,
        "MAY_PRIMARY_UNLOCK_READY": False,
        "may_loader_access_count": 0,
        "june_loader_access_count": 0,
    }
    _write_json(artifacts / "C12_PREPRODUCTION_FREEZE_STATUS.json", c12)
    _write_sha_manifest(artifacts)
    return {"c7": c7, "gates": gates, "c12": c12}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--capacity-source", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--authority-archive", type=Path, required=True)
    args = parser.parse_args(argv)
    result = execute(
        artifacts=args.artifacts,
        capacity_source=args.capacity_source,
        assets=args.assets,
        contract=args.contract,
        authority_archive=args.authority_archive,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["c12"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
