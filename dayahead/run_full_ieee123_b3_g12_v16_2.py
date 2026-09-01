"""Run final April V16.2 B3 G12, stopping fail-closed after monolithic IIS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .authority import sha256_file
from .full_ieee123_b3_v16_2 import load_b3_inputs, solve_monolithic
from .full_ieee123_g11_v16_1 import build_full_grid_binding
from .grid_background_v16_2 import build_authority_background_binding
from .run_aemo_rebind_g11_v16_2 import _frozen_aemo_inputs
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json


def execute(
    *, repo: Path, artifacts: Path, assets: Path, contract: Path, pcc_v4: Path,
    aemo_contract: Path, forecast: Path, reference: Path, c7_source: Path, rack_contract: Path,
) -> dict[str, object]:
    repo = repo.resolve()
    artifacts = artifacts.resolve()
    g11_path = artifacts / "G11_V16_2_AUTHORITY_SEMANTIC_REPORT.json"
    g11 = json.loads(g11_path.read_text(encoding="utf-8"))
    if g11["status"] != "PASS_FULL_IEEE123_V16_2":
        raise RuntimeError("G12_REQUIRES_G11_AUTHORITY_SEMANTIC_PASS")
    aemo, demand, pv = _frozen_aemo_inputs(aemo_contract)
    forensic = json.loads((artifacts / "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json").read_text(encoding="utf-8"))
    timestamps = tuple(str(row["timestamp_fixed_aest"]) for row in forensic["slot_by_slot_component_totals"])
    source_root = assets.parent
    background = build_authority_background_binding(
        timestamps_fixed_aest=timestamps,
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        paths=_default_background_paths(repo, source_root),
    )
    c7_payload = json.loads(c7_source.read_text(encoding="utf-8"))
    binding = build_full_grid_binding(
        assets=assets,
        contract=contract,
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        aidc_plan_kw_96x12=c7_payload["reference_delta"]["p_aidc_plan_kw"],
        pcc_asset=pcc_v4,
        background_binding=background,
    )
    inputs = load_b3_inputs(
        forecast_path=forecast,
        reference_path=reference,
        c7_path=c7_source,
        rack_contract_path=rack_contract,
    )
    monolithic = solve_monolithic(binding, inputs, output_dir=artifacts)
    infeasible = monolithic["status"] == "G12_FAIL_B3_PLANNING_INFEASIBLE"
    if infeasible:
        standard = {
            "status": "NOT_RUN_MONOLITHIC_B3_INFEASIBLE",
            "objective": None,
            "runtime_seconds": 0,
            "iterations": 0,
            "farkas_cut_count": 0,
            "optimality_cut_count": 0,
            "final_gap": None,
        }
        proposed = dict(standard)
        final_status = "G12_FAIL_B3_PLANNING_INFEASIBLE"
    elif monolithic["status"] == "OPTIMAL":
        # The identical-problem BD phase is deliberately not approximated.
        # A feasible monolithic outcome must proceed through the certified BD
        # implementation before this runner may return success.
        raise RuntimeError("B3_MONOLITHIC_FEASIBLE_CERTIFIED_BD_EXECUTION_REQUIRED")
    else:
        standard = {"status": "NOT_RUN_MONOLITHIC_NOT_OPTIMAL"}
        proposed = {"status": "NOT_RUN_MONOLITHIC_NOT_OPTIMAL"}
        final_status = str(monolithic["status"])
    report = {
        "authority_id": "G12_V16_2_FULL_IEEE123_B3_JOINT",
        "status": final_status,
        "operating_day": "2025-04-15",
        "solve_order": "G11_PASS_THEN_MONOLITHIC_B3_FIRST_THEN_BD_ONLY_IF_FEASIBLE",
        "input_evidence": {
            **dict(inputs.evidence),
            "g11_sha256": sha256_file(g11_path),
            "background_mapping_contract_sha256": sha256_file(artifacts / "GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json"),
            "aemo_mapped_input_sha256": aemo["mapping"]["mapped_input_sha256"],
            "pcc_v4_sha256": sha256_file(pcc_v4),
        },
        "monolithic": monolithic,
        "standard_single_cut_bd": standard,
        "cl_mc_bd": proposed,
        "equivalence": {
            "status": "NOT_APPLICABLE_MONOLITHIC_INFEASIBLE" if infeasible else "NOT_EVALUATED",
            "standard_relative_objective_difference": None,
            "cl_mc_bd_relative_objective_difference": None,
            "hard_feasibility_identity": None,
        },
        "decision": {
            "ready_for_g13_preproduction": False,
            "feeder_scientific_review_required": infeasible,
            "feeder_refreeze_performed": False,
            "uprating_performed": False,
        },
        "downstream_call_counts": {"G13": 0, "realized_replay": 0, "G14": 0, "C12": 0},
        "firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "may_forecast_rows": 0,
            "may_reference_schedule_created": False,
            "may_b0_b3_results_created": False,
            "june_results_created": False,
        },
        "stop_rule": "STOP_AFTER_G12",
        "stop_rule_applied": True,
    }
    report_path = artifacts / "G12_V16_2_FULL_IEEE123_B3_REPORT.json"
    _write_json(report_path, report)
    return {
        "status": final_status,
        "report_sha256": sha256_file(report_path),
        "monolithic_runtime_seconds": monolithic["runtime_seconds"],
        "iis_constraint_family_counts": monolithic.get("iis", {}).get("constraint_family_counts"),
        "ready_for_g13_preproduction": False,
        "feeder_scientific_review_required": infeasible,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd().resolve()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--assets", type=Path, default=source / "opendss_assets")
    parser.add_argument("--contract", type=Path, default=source / "power_v70_p4f_contract")
    parser.add_argument("--pcc-v4", type=Path, default=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss")
    parser.add_argument("--aemo-contract", type=Path, default=repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    parser.add_argument("--forecast", type=Path, default=repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet")
    parser.add_argument("--reference", type=Path, default=repo / "dayahead/artifacts/v16_1/REFERENCE_COMPUTE_SCHEDULE_V3.parquet")
    parser.add_argument("--c7-source", type=Path, default=repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json")
    parser.add_argument("--rack-contract", type=Path, default=repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json")
    args = parser.parse_args(argv)
    result = execute(**vars(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"G12_FAIL_B3_PLANNING_INFEASIBLE", "PASS_FULL_IEEE123_V16_2"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
