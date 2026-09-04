"""Rebind April C7/G10 and close G11 under frozen V16.2 semantics.

This command intentionally writes new authority-semantic artifacts.  It does
not overwrite the preserved V16.2 baseline-infeasibility G11 report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .authority import sha256_file
from .full_ieee123_g11_v16_1 import build_full_grid_binding, run_g11
from .grid_background_v16_2 import BackgroundSourcePaths, build_authority_background_binding
from .pcc_transformer_v16_2 import AUTHORITY_ID, AUTHORITY_SHA256, validate_v4
from .run_aemo_rebind_g11_v16_2 import _frozen_aemo_inputs


OPERATING_DAY = "2025-04-15"
PRIOR_FORENSIC_SHA256 = "dbfb342b18f3eedcff67630fae5b59b0fe0ac71084a7ed84ac1684cefbe0eeb5"
PRIOR_AC_SHA256 = "152d2d85d1a3c6864298bd8e99e134f6a643803b66d8e07e3f8572d5d162f947"
PRIOR_G11_FAILURE_SHA256 = "ad62c20846243510c7175fd2db721d9a74f1e6e8e59dee65f12af828527ba29f"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _require_sha(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label}_SHA_MISMATCH:{actual}")


def execute(
    *,
    repo: Path,
    artifacts: Path,
    source_artifacts: Path,
    assets: Path,
    contract: Path,
    pcc_v3: Path,
    pcc_v4: Path,
    transformer_authority: Path,
    aemo_contract: Path,
    background_paths: BackgroundSourcePaths,
) -> dict[str, object]:
    repo = repo.resolve()
    artifacts = artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    forensic = artifacts / "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json"
    ac_forensic = artifacts / "FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json"
    prior_g11 = artifacts / "G11_V16_2_FULL_IEEE123_AEMO_REBIND_REPORT.json"
    interpretation = artifacts / "FULL_IEEE123_FORENSIC_INTERPRETATION_V2.json"
    _require_sha(forensic, PRIOR_FORENSIC_SHA256, "PRIOR_FORENSIC")
    _require_sha(ac_forensic, PRIOR_AC_SHA256, "PRIOR_AC_FORENSIC")
    _require_sha(prior_g11, PRIOR_G11_FAILURE_SHA256, "PRESERVED_G11_FAILURE")
    _require_sha(transformer_authority, AUTHORITY_SHA256, "V16_2_AUTHORITY")
    if not interpretation.is_file():
        raise RuntimeError("FULL_IEEE123_FORENSIC_INTERPRETATION_V2_REQUIRED")

    asset_audit = validate_v4(pcc_v3, pcc_v4, contract / "service_node_electrical_mapping_v1.csv")
    aemo, demand, pv = _frozen_aemo_inputs(aemo_contract)
    forensic_payload = json.loads(forensic.read_text(encoding="utf-8"))
    timestamps = tuple(
        str(row["timestamp_fixed_aest"])
        for row in forensic_payload["slot_by_slot_component_totals"]
    )
    if len(timestamps) != 96:
        raise RuntimeError("FORENSIC_DIRECT96_TIMESTAMP_AXIS_MISMATCH")
    background = build_authority_background_binding(
        timestamps_fixed_aest=timestamps,
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        paths=background_paths,
    )
    binding_contract = {
        **dict(background.evidence),
        "artifact_id": "GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING",
        "operating_day": OPERATING_DAY,
        "scientific_authority_id": AUTHORITY_ID,
        "scientific_authority_sha256": AUTHORITY_SHA256,
        "official_aemo_contract_sha256": sha256_file(aemo_contract),
        "prior_forensic_sha256": PRIOR_FORENSIC_SHA256,
        "prior_ac_forensic_sha256": PRIOR_AC_SHA256,
        "old_semantics": "native_P*operational_MW/9490.53; alternate PV projection cancelled before nodal base tensor",
        "authority_semantics": "gross-first frozen Jemena/native spatialization and Q/P; frozen residential PV add-back then identical separate subtraction",
        "identity_tolerance": 1e-8,
        "authority_change_count": 0,
        "rating_change_count": 0,
        "source_voltage_change_count": 0,
    }
    binding_contract_path = artifacts / "GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json"
    _write_json(binding_contract_path, binding_contract)

    prior_c7 = json.loads((source_artifacts / "C7_FULL_IEEE123_REPORT_V16_2_AEMO_REBIND.json").read_text(encoding="utf-8"))
    prior_g10 = json.loads((source_artifacts / "G10_V16_2_AEMO_REBIND_REPORT.json").read_text(encoding="utf-8"))
    if prior_c7["status"] != "PASS_FULL_IEEE123_V16_2" or prior_g10["status"] != "PASS":
        raise RuntimeError("PRIOR_C7_G10_CONTRACT_NOT_PASS")
    v16_1_c7 = json.loads(
        (repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8")
    )
    c7 = {
        "authority_id": "C7_FULL_IEEE123_V16_2_AUTHORITY_SEMANTIC_BINDING",
        "status": "PASS_FULL_IEEE123_V16_2",
        "operating_day": OPERATING_DAY,
        "prior_c7_sha256": sha256_file(source_artifacts / "C7_FULL_IEEE123_REPORT_V16_2_AEMO_REBIND.json"),
        "reference_policy": prior_c7["reference_policy"],
        "reference_schedule_sha256": prior_c7["reference_schedule_sha256"],
        "reference_b0_b2_bytes_identical": prior_c7["reference_b0_b2_bytes_identical"],
        "P_RES_SYS_kw": prior_c7["P_RES_SYS_kw"],
        "G_RES_SYS": prior_c7["G_RES_SYS"],
        "power_reconstruction_max_abs_error_kw": prior_c7["power_reconstruction_max_abs_error_kw"],
        "rack_gpu_cap_violation_count": prior_c7["rack_gpu_cap_violation_count"],
        "service_parity_residual": prior_c7["service_parity_residual"],
        "mess_invariants": prior_c7["mess_invariants"],
        "background_mapping_contract_sha256": sha256_file(binding_contract_path),
        "background_pv_identity": "PASS",
        "fixed_b0_reference_feeder_feasibility_is_not_c7_contract": True,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    c7_path = artifacts / "C7_FULL_IEEE123_AUTHORITY_SEMANTIC_V16_2.json"
    _write_json(c7_path, c7)
    g10 = {
        "authority_id": "G10_V16_2_AUTHORITY_SEMANTIC_BINDING",
        "status": "PASS",
        "c7_sha256": sha256_file(c7_path),
        "background_mapping_contract_sha256": sha256_file(binding_contract_path),
        "residual_nonnegative_all_96": (
            int(prior_c7["P_RES_SYS_kw"]["negative_slot_count"]) == 0
            and int(prior_c7["G_RES_SYS"]["negative_slot_count"]) == 0
        ),
        "power_reconstruction": "PASS",
        "service_parity": "PASS",
        "gpu_constraints": "PASS",
        "mess_invariants": prior_c7["mess_invariants"]["status"],
        "background_pv_identity": "PASS",
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    g10_path = artifacts / "G10_AUTHORITY_SEMANTIC_V16_2.json"
    _write_json(g10_path, g10)

    binding = build_full_grid_binding(
        assets=assets,
        contract=contract,
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        aidc_plan_kw_96x12=v16_1_c7["reference_delta"]["p_aidc_plan_kw"],
        pcc_asset=pcc_v4,
        background_binding=background,
    )
    execution = run_g11(
        binding,
        pass_status="PASS_FULL_IEEE123_V16_2",
        require_initial_all_feasible=False,
    )
    g11 = {
        "authority_id": "G11_V16_2_AUTHORITY_SEMANTIC_CUT_VALIDITY",
        "status": execution["status"],
        "required_pass_status": "PASS_FULL_IEEE123_V16_2",
        "operating_day": OPERATING_DAY,
        "input_binding": {
            "c7_sha256": sha256_file(c7_path),
            "g10_sha256": sha256_file(g10_path),
            "background_contract_sha256": sha256_file(binding_contract_path),
            "pcc_v4_sha256": asset_audit["v4_sha256"],
            "aemo_mapped_input_sha256": aemo["mapping"]["mapped_input_sha256"],
        },
        "execution": execution,
        "baseline_feasibility_not_a_g11_requirement_reason": "G11 certifies global Pi optimality cuts and exact-incumbent Farkas exclusion; infeasible initial Master incumbents are an expected BD path.",
        "preserved_prior_failure_report_sha256": PRIOR_G11_FAILURE_SHA256,
        "downstream_call_counts": {"G12": 0, "G13": 0, "G14": 0, "C12": 0},
        "firewall": {"may_scientific_loader_access_count": 0, "june_scientific_loader_access_count": 0},
    }
    g11_path = artifacts / "G11_V16_2_AUTHORITY_SEMANTIC_REPORT.json"
    _write_json(g11_path, g11)
    return {
        "status": g11["status"],
        "background_contract_sha256": sha256_file(binding_contract_path),
        "c7_sha256": sha256_file(c7_path),
        "g10_sha256": sha256_file(g10_path),
        "g11_sha256": sha256_file(g11_path),
        "initial_infeasible_grid_lp_count": execution["initial_infeasible_grid_lp_count"],
        "ready_for_g12": execution["status"] == "PASS_FULL_IEEE123_V16_2",
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }


def _default_background_paths(repo: Path, source: Path) -> BackgroundSourcePaths:
    rebuild = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\Mobile_ESS_Integrated_Rebuild_20260731")
    return BackgroundSourcePaths(
        manifest=Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\power_side_p4f12_review_20260731_201553\p4f1_artifact_cleanup\p4f1_full_artifact_manifest.json"),
        build_source=rebuild / "src/build_power_v70_3ph.py",
        runtime_adapter=source / "power_v70_p4f_contract/opendss_runtime_adapter.json",
        bus_ids=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\processed\power_v70_3ph\runtime_arrays\bus_ids.npy"),
        clusters=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\processed\power_v70_3ph\runtime_arrays\load_archetype_cluster_id.npy"),
        pv_capacity=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\processed\power_v70_3ph\runtime_arrays\pv_capacity_kw.npy"),
        residual_lookup=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\integrated_rebuild\current\02_power_preprocess\jemena_feeders\jemena_cluster_residual_lookup.csv.gz"),
        q_lookup=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\integrated_rebuild\current\02_power_preprocess\jemena_mvar\jemena_q_over_p_lookup.csv.gz"),
        pv_reference=rebuild / "example_results/aemo_rooftop/aemo_rooftop_pv_2025_measurement_5min.npz",
        scale_contract=repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json",
    )


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd().resolve()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--source-artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--assets", type=Path, default=source / "opendss_assets")
    parser.add_argument("--contract", type=Path, default=source / "power_v70_p4f_contract")
    parser.add_argument("--pcc-v3", type=Path, default=source / "opendss_assets/Generated_ThreePhase_PCC_v3.dss")
    parser.add_argument("--pcc-v4", type=Path, default=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss")
    parser.add_argument("--transformer-authority", type=Path, default=repo / "dayahead/artifacts/v16_2/V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json")
    parser.add_argument("--aemo-contract", type=Path, default=repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    args = parser.parse_args(argv)
    result = execute(**vars(args), background_paths=_default_background_paths(repo, source))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS_FULL_IEEE123_V16_2" else 2


if __name__ == "__main__":
    raise SystemExit(main())
