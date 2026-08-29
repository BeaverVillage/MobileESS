"""V16.2 official-April C7/G10/G11 revalidation with the frozen PCC V4 asset."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Sequence

from .aemo_vintage_v16_1 import mapped_input_sha256, pwc_hold_30_to_15, select_demand_vintage, select_pv_vintage
from .full_ieee123_g11_v16_1 import (
    PF_AIDC,
    build_full_grid_binding,
    deterministic_hard_constraint_audit,
    run_g11,
)
from .pcc_transformer_v16_2 import (
    AIDC_RATING_KVA,
    AUTHORITY_ID,
    AUTHORITY_SHA256,
    MESS_RATING_KVA,
    V3_SHA256,
    sha256_file,
    validate_v4,
)


AEMO_CONTRACT_SHA256 = "b11cd2548afc24cb123dd995e5d4ae0cdf3ca8a39d9ad9eadc8da4e93c6fb3c9"
EXPECTED_AUTHORITY_COMMIT = "ee8c21ae33472e94fd92fb2948bd6c4389fe48b0"
OPERATING_DAY = "2025-04-15"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _frozen_aemo_inputs(contract_path: Path) -> tuple[dict[str, object], tuple[float, ...], tuple[float, ...]]:
    if sha256_file(contract_path) != AEMO_CONTRACT_SHA256:
        raise RuntimeError("V16_2_AEMO_CONTRACT_SHA_MISMATCH")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_demand = {"PREDISPATCHSEQNO": "2025041428", "RUNNO": "1"}
    expected_pv = {"VERSION_DATETIME": "2025/04/14 18:00:00"}
    if contract["demand"]["selected_identity"] != expected_demand or contract["rooftop_pv"]["selected_identity"] != expected_pv:
        raise RuntimeError("V16_2_OFFICIAL_APRIL_VINTAGE_IDENTITY_MISMATCH")
    demand = select_demand_vintage(Path(contract["demand"]["source_path"]))
    pv = select_pv_vintage(Path(contract["rooftop_pv"]["source_path"]))
    if demand.identity != expected_demand or pv.identity != expected_pv:
        raise RuntimeError("V16_2_APRIL_SOURCE_RESELECTION_MISMATCH")
    if demand.trajectory_sha256 != contract["demand"]["trajectory_sha256"]:
        raise RuntimeError("V16_2_APRIL_DEMAND_TRAJECTORY_SHA_MISMATCH")
    if pv.trajectory_sha256 != contract["rooftop_pv"]["trajectory_sha256"]:
        raise RuntimeError("V16_2_APRIL_PV_TRAJECTORY_SHA_MISMATCH")
    mapped_demand = pwc_hold_30_to_15(demand.values)
    mapped_pv = pwc_hold_30_to_15(pv.values)
    if mapped_input_sha256(demand, pv) != contract["mapping"]["mapped_input_sha256"]:
        raise RuntimeError("V16_2_APRIL_MAPPED_INPUT_SHA_MISMATCH")
    return contract, mapped_demand, mapped_pv


def _compile_c7_authority(assets: Path, contract: Path, pcc_v4: Path) -> dict[str, object]:
    import opendssdirect as odd

    odd.Basic.ClearAll()
    for command in (
        f'Compile "{assets / "IEEE123Master.dss"}"',
        "MakeBusList",
        f'Redirect "{pcc_v4}"',
        "MakeBusList",
        "CalcVoltageBases",
        f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"',
        f'Redirect "{contract / "Generated_PhasePV.dss"}"',
    ):
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"V16_2_FULL_IEEE123_COMPILE_ERROR:{command}:{odd.Error.Description()}")
    buses = {str(value).lower() for value in odd.Circuit.AllBusNames()}
    with (contract / "service_node_electrical_mapping_v1.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        mapping_rows = tuple(csv.DictReader(stream))
    aidc_rows = tuple(row for row in mapping_rows if row["asset_type"] == "IDC")
    missing_hosts = [row["electrical_host_bus"] for row in aidc_rows if row["electrical_host_bus"].lower() not in buses]
    missing_pccs = [f"idc_idc{index:02d}_pcc" for index in range(1, 13) if f"idc_idc{index:02d}_pcc" not in buses]
    if missing_hosts or missing_pccs:
        raise RuntimeError(f"V16_2_AIDC_PCC_HOST_BINDING_MISSING:{missing_hosts}:{missing_pccs}")
    return {
        "status": "PASS",
        "compiled_bus_count": int(odd.Circuit.NumBuses()),
        "compiled_node_count": int(odd.Circuit.NumNodes()),
        "transformer_count": int(odd.Transformers.Count()),
        "regulator_count": int(odd.RegControls.Count()),
        "capacitor_count": int(odd.Capacitors.Count()),
        "aidc_host_count": len(aidc_rows),
        "aidc_pcc_count": 12,
        "all_aidc_hosts_present": not missing_hosts,
        "all_aidc_pcc_buses_present": not missing_pccs,
        "opendss_solve_call_count": 0,
    }


def _schedule_transformer_audit(p_aidc_plan_kw: Sequence[Sequence[float]]) -> dict[str, object]:
    apparent = [[float(value) / PF_AIDC for value in row] for row in p_aidc_plan_kw]
    cases = [
        (time_index, aidc_index + 1, value)
        for time_index, row in enumerate(apparent)
        for aidc_index, value in enumerate(row)
    ]
    violations = [row for row in cases if row[2] > AIDC_RATING_KVA + 1e-9]
    worst = max(cases, key=lambda row: row[2])
    return {
        "rating_kva_each": AIDC_RATING_KVA,
        "aidc_transformer_count": 12,
        "aidc_power_factor": PF_AIDC,
        "violation_count_aidc_slots": len(violations),
        "current_loading_violation_count": len(violations),
        "kva_loading_violation_count": len(violations),
        "worst": {
            "time_index": worst[0],
            "aidc_id": f"AIDC{worst[1]:02d}",
            "apparent_power_kva": worst[2],
            "active_power_kw": float(p_aidc_plan_kw[worst[0]][worst[1] - 1]),
            "current_loading_pu_equivalent": worst[2] / AIDC_RATING_KVA,
            "kva_loading_pu": worst[2] / AIDC_RATING_KVA,
        },
        "rating_fitting_runtime_call_count": 0,
        "rating_optimization_variable_count": 0,
        "transformer_constraint_slack_variable_count": 0,
    }


def execute(
    *, repo: Path, artifacts: Path, source_artifacts: Path, assets: Path, contract: Path,
    pcc_v3: Path, pcc_v4: Path, transformer_contract: Path, authority: Path, aemo_contract: Path,
) -> dict[str, object]:
    repo = repo.resolve()
    artifacts = artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    if sha256_file(authority) != AUTHORITY_SHA256:
        raise RuntimeError("V16_2_AUTHORITY_SHA_MISMATCH")
    transformer_payload = json.loads(transformer_contract.read_text(encoding="utf-8"))
    if transformer_payload["authority_sha256"] != AUTHORITY_SHA256:
        raise RuntimeError("V16_2_TRANSFORMER_CONTRACT_AUTHORITY_BINDING_MISMATCH")
    asset_audit = validate_v4(pcc_v3, pcc_v4, contract / "service_node_electrical_mapping_v1.csv")
    if transformer_payload["generated_three_phase_pcc_v4"]["sha256"] != asset_audit["v4_sha256"]:
        raise RuntimeError("V16_2_TRANSFORMER_CONTRACT_V4_SHA_MISMATCH")
    aemo_payload, mapped_demand, mapped_pv = _frozen_aemo_inputs(aemo_contract)
    frozen_c7 = json.loads((source_artifacts / "C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    prior_rebind = json.loads((source_artifacts / "C7_FULL_IEEE123_REPORT_V16_1_AEMO_REBIND.json").read_text(encoding="utf-8"))
    delta = frozen_c7["reference_delta"]
    compile_audit = _compile_c7_authority(assets, contract, pcc_v4)
    tx_audit = _schedule_transformer_audit(delta["p_aidc_plan_kw"])
    c7 = {
        "authority_id": "C7_FULL_IEEE123_V16_2_OFFICIAL_AEMO_APRIL_REBIND",
        "scientific_authority_id": AUTHORITY_ID,
        "status": "PASS_FULL_IEEE123_V16_2",
        "operating_day": OPERATING_DAY,
        "aemo_vintage_contract_sha256": sha256_file(aemo_contract),
        "official_demand_identity": aemo_payload["demand"]["selected_identity"],
        "official_pv_identity": aemo_payload["rooftop_pv"]["selected_identity"],
        "mapped_input_sha256": aemo_payload["mapping"]["mapped_input_sha256"],
        "v16_1_power_boundary_separation_reused_unchanged": True,
        "reference_policy": "REFERENCE_COMPUTE_SCHEDULE_V3",
        "reference_schedule_sha256": prior_rebind["reference_schedule_sha256"],
        "reference_b0_b2_bytes_identical": prior_rebind["reference_b0_b2_bytes_identical"],
        "P_RES_SYS_kw": delta["P_RES_SYS_kw"],
        "G_RES_SYS": delta["G_RES_SYS"],
        "power_reconstruction_max_abs_error_kw": delta["power_reconstruction_max_abs_error_kw"],
        "pue_application_count": delta["pue_application_count"],
        "pue_reconstruction_max_abs_error_kw": delta["pue_reconstruction_max_abs_error_kw"],
        "rack_gpu_cap_violation_count": delta["rack_gpu_cap_violation_count"],
        "rack_gpu_cap_max_violation": delta["rack_gpu_cap_max_violation"],
        "service_parity_residual": frozen_c7["service_parity_residual"],
        "service_parity_status": frozen_c7["service_parity_status"],
        "mess_invariants": prior_rebind["mess_invariants"],
        "full_ieee123_compile": compile_audit,
        "pcc_transformer_contract": {
            "path": str(transformer_contract),
            "sha256": sha256_file(transformer_contract),
            "v4_sha256": asset_audit["v4_sha256"],
            "v3_preserved_sha256": asset_audit["v3_sha256"],
            "active_aidc_rating_kva": AIDC_RATING_KVA,
            "old_750_aidc_authority_active": False,
            "mess_rating_kva": MESS_RATING_KVA,
            "mess_pcc_rating_change_count": 0,
        },
        "transformer_schedule_audit": tx_audit,
        "selection_or_rating_change_call_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    if not all((
        int(delta["P_RES_SYS_kw"]["negative_slot_count"]) == 0,
        int(delta["G_RES_SYS"]["negative_slot_count"]) == 0,
        float(delta["power_reconstruction_max_abs_error_kw"]) <= 1e-9,
        int(delta["rack_gpu_cap_violation_count"]) == 0,
        abs(float(frozen_c7["service_parity_residual"])) <= 1e-12,
        compile_audit["status"] == "PASS",
        tx_audit["violation_count_aidc_slots"] == 0,
    )):
        c7["status"] = "FAIL_C7_V16_2"
    c7_path = artifacts / "C7_FULL_IEEE123_REPORT_V16_2_AEMO_REBIND.json"
    _write_json(c7_path, c7)
    g10 = {
        "authority_id": "G10_V16_2_OFFICIAL_AEMO_APRIL_REBIND",
        "status": "PASS" if c7["status"] == "PASS_FULL_IEEE123_V16_2" else "FAIL",
        "c7_sha256": sha256_file(c7_path),
        "P_RES_SYS_nonnegative_all_96": int(delta["P_RES_SYS_kw"]["negative_slot_count"]) == 0,
        "G_RES_SYS_nonnegative_all_96": int(delta["G_RES_SYS"]["negative_slot_count"]) == 0,
        "exact_power_reconstruction": float(delta["power_reconstruction_max_abs_error_kw"]) <= 1e-9,
        "rack_gpu_capacity": "PASS" if int(delta["rack_gpu_cap_violation_count"]) == 0 else "FAIL",
        "v3_service_parity": "PASS" if abs(float(frozen_c7["service_parity_residual"])) <= 1e-12 else "FAIL",
        "mess_invariants": prior_rebind["mess_invariants"]["status"],
        "aidc_pcc_transformer": "PASS" if tx_audit["violation_count_aidc_slots"] == 0 else "FAIL",
        "mess_pcc_rating_change_count": 0,
        "rating_selection_call_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    g10_path = artifacts / "G10_V16_2_AEMO_REBIND_REPORT.json"
    _write_json(g10_path, g10)
    if g10["status"] != "PASS":
        return {"status": "STOPPED_FAIL_CLOSED_AT_C7_G10", "c7_sha256": sha256_file(c7_path), "g10_sha256": sha256_file(g10_path)}
    input_manifest = {
        "authority_id": "DAYAHEAD_INPUT_MANIFEST_V16_2_APRIL",
        "status": "PASS",
        "operating_day": OPERATING_DAY,
        "aemo_vintage_contract_sha256": AEMO_CONTRACT_SHA256,
        "aemo_vintage_reselected": False,
        "aemo_vintage_revalidated_from_frozen_april_source": True,
        "mapped_96_slot_input_sha256": aemo_payload["mapping"]["mapped_input_sha256"],
        "pcc_v4_sha256": asset_audit["v4_sha256"],
        "pcc_transformer_contract_sha256": sha256_file(transformer_contract),
        "scientific_authority_sha256": AUTHORITY_SHA256,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    manifest_path = artifacts / "DAYAHEAD_INPUT_MANIFEST_V16_2_APRIL.json"
    _write_json(manifest_path, input_manifest)
    binding = build_full_grid_binding(
        assets=assets,
        contract=contract,
        demand_mw_96=mapped_demand,
        rooftop_pv_mw_96=mapped_pv,
        aidc_plan_kw_96x12=delta["p_aidc_plan_kw"],
        pcc_asset=pcc_v4,
    )
    hard_constraint_audit = deterministic_hard_constraint_audit(binding)
    execution = run_g11(binding, pass_status="PASS_FULL_IEEE123_V16_2")
    blocker = None
    if execution["status"] == "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE":
        blocker = {
            "classification": "FULL_IEEE123_UPSTREAM_TRANSFORMER_LINE_AND_VOLTAGE_HARD_INFEASIBILITY",
            "primary_irreducible_conflict": "NATIVE_REGULATOR_TRANSFORMER_REG1A_PHASE_A_HARD_KVA_POLYGON",
            "additional_deterministic_hard_violations": [
                "NATIVE_REGULATOR_TRANSFORMER_REG1A",
                "FROZEN_U080_LINE_AMPACITY",
                "MINIMUM_VOLTAGE_0_95_PU",
            ],
            "aidc_schedule_transformer_violation_count": tx_audit["violation_count_aidc_slots"],
            "deterministic_hard_constraint_audit": hard_constraint_audit,
            "time_0_iis": execution["baseline_time_0_iis"],
            "note": "No repair, slack, or post-outcome resizing was applied.",
        }
    g11 = {
        "authority_id": "G11_V16_2_FULL_IEEE123_OFFICIAL_AEMO_APRIL_REBIND",
        "scientific_authority_id": AUTHORITY_ID,
        "status": execution["status"],
        "required_pass_status": "PASS_FULL_IEEE123_V16_2",
        "operating_day": OPERATING_DAY,
        "aemo_vintage_contract_sha256": AEMO_CONTRACT_SHA256,
        "input_manifest_sha256": sha256_file(manifest_path),
        "c7_sha256": sha256_file(c7_path),
        "g10_sha256": sha256_file(g10_path),
        "pcc_v4_sha256": asset_audit["v4_sha256"],
        "pcc_transformer_contract_sha256": sha256_file(transformer_contract),
        "execution": execution,
        "independent_deterministic_hard_constraint_audit": hard_constraint_audit,
        "dedicated_aidc_pcc_transformer_audit": tx_audit,
        "mess_pcc": {
            "transformer_rating_kva": MESS_RATING_KVA,
            "pcs_rating_kva": 700.0,
            "rating_change_count": 0,
            "hard_constraint_rows_retained": True,
        },
        "exact_physical_blocker": blocker,
        "downstream_call_counts": {"G12": 0, "G13": 0, "realized_replay": 0, "G14": 0, "C12": 0},
        "firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "may_forecast_rows": 0,
            "may_reference_schedule_created": False,
            "may_b0_b3_results_created": False,
            "june_results_created": False,
        },
        "stop_rule": "STOP_AFTER_G11",
        "stop_rule_applied": True,
        "ready_for_final_g12_preproduction": execution["status"] == "PASS_FULL_IEEE123_V16_2",
        "may_primary_unlock_ready": False,
    }
    g11_path = artifacts / "G11_V16_2_FULL_IEEE123_AEMO_REBIND_REPORT.json"
    _write_json(g11_path, g11)
    return {
        "status": g11["status"],
        "c7_sha256": sha256_file(c7_path),
        "g10_sha256": sha256_file(g10_path),
        "g11_sha256": sha256_file(g11_path),
        "v4_sha256": asset_audit["v4_sha256"],
        "ready_for_final_g12_preproduction": g11["ready_for_final_g12_preproduction"],
        "may_primary_unlock_ready": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--source-artifacts", type=Path, default=repo / "dayahead/artifacts/v16_1")
    parser.add_argument("--assets", type=Path, default=source / "opendss_assets")
    parser.add_argument("--contract", type=Path, default=source / "power_v70_p4f_contract")
    parser.add_argument("--pcc-v3", type=Path, default=source / "opendss_assets/Generated_ThreePhase_PCC_v3.dss")
    parser.add_argument("--pcc-v4", type=Path, default=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss")
    parser.add_argument("--transformer-contract", type=Path, default=repo / "dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_CONTRACT_V2.json")
    parser.add_argument("--authority", type=Path, default=repo / "dayahead/artifacts/v16_2/V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json")
    parser.add_argument("--aemo-contract", type=Path, default=repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    args = parser.parse_args(argv)
    result = execute(**vars(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS_FULL_IEEE123_V16_2", "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE", "FAIL_G11_DUAL_FARKAS_VALIDATION"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
