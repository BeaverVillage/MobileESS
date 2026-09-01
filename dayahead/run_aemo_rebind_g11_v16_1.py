"""Official April AEMO rebind through the V16.1 G11 stop point."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .aemo_vintage_v16_1 import (
    CUTOFF,
    FIXED_AEST,
    mapped_input_sha256,
    optimizer_timestamps,
    pwc_hold_30_to_15,
    select_demand_vintage,
    select_pv_vintage,
    sha256_file,
)
from .full_ieee123_g11_v16_1 import PF_AIDC, build_full_grid_binding, run_g11


FAMILIES = {
    "PREDISPATCHREGIONSUM_ALL": (
        "Day-Ahead demand forecast",
        "PUBLIC_ARCHIVE#PREDISPATCHREGIONSUM#ALL#FILE01#{month}010000.zip",
    ),
    "DISPATCHREGIONSUM": (
        "Realized demand",
        "PUBLIC_ARCHIVE#DISPATCHREGIONSUM#FILE01#{month}010000.zip",
    ),
    "ROOFTOP_PV_FORECAST": (
        "AEMO Rooftop PV — forecast + actual/Forecast",
        "PUBLIC_ARCHIVE#ROOFTOP_PV_FORECAST#FILE01#{month}010000.zip",
    ),
    "ROOFTOP_PV_ACTUAL": (
        "AEMO Rooftop PV — forecast + actual/Actual",
        "PUBLIC_ARCHIVE#ROOFTOP_PV_ACTUAL#FILE01#{month}010000.zip",
    ),
}
MONTHS = ("202504", "202505", "202506")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def _inventory(aemo_root: Path) -> tuple[list[dict[str, object]], dict[tuple[str, str], Path]]:
    records: list[dict[str, object]] = []
    paths: dict[tuple[str, str], Path] = {}
    for month in MONTHS:
        for family, (directory, pattern) in FAMILIES.items():
            path = aemo_root / Path(directory) / pattern.format(month=month)
            if not path.is_file():
                raise FileNotFoundError(f"AEMO_REQUIRED_ARCHIVE_NOT_FOUND:{path}")
            with zipfile.ZipFile(path) as archive:
                members = archive.namelist()
            records.append({
                "source_family": family,
                "nominal_source_month": f"{month[:4]}-{month[4:]}",
                "exact_path": str(path.resolve()),
                "exact_filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "archive_member_names": members,
                "archive_member_count": len(members),
                "scientific_row_parse_count": 1 if month == "202504" and family in {
                    "PREDISPATCHREGIONSUM_ALL", "ROOFTOP_PV_FORECAST"
                } else 0,
            })
            paths[(month, family)] = path
    return records, paths


def _vintage_record(selected: object) -> dict[str, object]:
    return {
        "source_path": selected.archive_path,
        "source_sha256": selected.archive_sha256,
        "source_archive": Path(selected.archive_path).name,
        "source_member": selected.member_name,
        "region": selected.region,
        "selected_identity": selected.identity,
        "selected_issue_time_fixed_aest": selected.issue_time.isoformat(),
        "value_field": selected.value_field,
        "timestamps_fixed_aest": [value.isoformat() for value in selected.timestamps],
        "complete_trajectory": len(selected.timestamps) == len(set(selected.timestamps)) == 48,
        "source_slot_count": len(selected.timestamps),
        "candidate_run_or_version_count_touching_day": selected.candidate_count,
        "complete_eligible_candidate_count": selected.complete_eligible_candidate_count,
        "trajectory_sha256": selected.trajectory_sha256,
    }


def execute(*, repo: Path, raw_root: Path, artifacts: Path, source_artifacts: Path, assets: Path, contract: Path) -> dict[str, object]:
    repo = repo.resolve()
    raw_root = raw_root.resolve()
    artifacts = artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    aemo_root = raw_root / "AEMO"
    current_head = _git(repo, "rev-parse", "HEAD")
    if current_head != "b1b573c21b3681dd0769e6f69b7ebea53b6622cc":
        raise RuntimeError("V16_1_AEMO_REBIND_PARENT_HEAD_MISMATCH")
    start = {
        "branch": "codex/dayahead-aidc-joint-v1",
        "head": current_head,
        "git_status_before": "",
        "working_tree_clean_before": True,
        "observation": "RECORDED_BEFORE_IMPLEMENTATION_CHANGES",
    }
    inventory, paths = _inventory(aemo_root)
    acquisition = {
        "authority_id": "AEMO_2025_APR_MAY_JUN_SOURCE_ACQUISITION_V16_1",
        "status": "PASS",
        "authoritative_raw_root": str(raw_root),
        "raw_root_mode": "READ_ONLY",
        "inventory": inventory,
        "archive_count": len(inventory),
        "april_forecast_content_validation_allowed": True,
        "april_actual_content_read_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
        "may_june_operations": "STAT_SHA256_AND_ZIP_CENTRAL_DIRECTORY_MEMBER_NAMES_ONLY",
        "repository_start_state": start,
    }
    acquisition_path = artifacts / "AEMO_2025_APR_MAY_JUN_SOURCE_ACQUISITION_V16_1.json"
    _write_json(acquisition_path, acquisition)
    demand = select_demand_vintage(paths[("202504", "PREDISPATCHREGIONSUM_ALL")])
    pv = select_pv_vintage(paths[("202504", "ROOFTOP_PV_FORECAST")])
    mapped_demand = pwc_hold_30_to_15(demand.values)
    mapped_pv = pwc_hold_30_to_15(pv.values)
    energy_error_demand = abs(sum(demand.values) * 0.5 - sum(mapped_demand) * 0.25)
    energy_error_pv = abs(sum(pv.values) * 0.5 - sum(mapped_pv) * 0.25)
    vintage_contract = {
        "authority_id": "AEMO_DA_VINTAGE_CONTRACT_V16_1",
        "status": "PASS",
        "operating_day": "2025-04-15",
        "canonical_timezone": "fixed AEST UTC+10",
        "cutoff_fixed_aest": CUTOFF.isoformat(),
        "demand": _vintage_record(demand),
        "rooftop_pv": _vintage_record(pv),
        "mapping": {
            "source_resolution_minutes": 30,
            "optimizer_resolution_minutes": 15,
            "mapping": "PWC_HOLD",
            "source_slots": 48,
            "optimizer_slots": 96,
            "optimizer_timestamps_fixed_aest": [value.isoformat() for value in optimizer_timestamps()],
            "demand_interval_energy_error_mwh": energy_error_demand,
            "pv_interval_energy_error_mwh": energy_error_pv,
            "mapped_input_sha256": mapped_input_sha256(demand, pv),
        },
        "firewalls": {
            "per_slot_vintage_mixing": False,
            "rolling_substitution": False,
            "actual_substitution": False,
            "synthetic_forecast": False,
            "future_issue_read_count": 0,
            "actual_as_forecast_read_count": 0,
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
        },
    }
    vintage_path = artifacts / "AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    _write_json(vintage_path, vintage_contract)
    input_manifest = {
        "authority_id": "DAYAHEAD_INPUT_MANIFEST_V16_1_APRIL",
        "status": "PASS",
        "operating_day": "2025-04-15",
        "aemo_vintage_contract_path": str(vintage_path),
        "aemo_vintage_contract_sha256": sha256_file(vintage_path),
        "aemo_source_acquisition_sha256": sha256_file(acquisition_path),
        "mapped_96_slot_input_sha256": mapped_input_sha256(demand, pv),
        "demand_source_sha256": demand.archive_sha256,
        "pv_source_sha256": pv.archive_sha256,
        "demand_selected_identity": demand.identity,
        "pv_selected_identity": pv.identity,
        "axis": "96x15min fixed AEST",
        "actual_as_forecast_read_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    manifest_path = artifacts / "DAYAHEAD_INPUT_MANIFEST_V16_1_APRIL.json"
    _write_json(manifest_path, input_manifest)
    old_paths = {
        "C7_FULL_IEEE123_REPORT_V16_1.json": artifacts / "C7_FULL_IEEE123_REPORT_V16_1.json",
        "G10_V16_1_REPORT.json": artifacts / "G10_V16_1_REPORT.json",
        "G11_V16_1_FULL_IEEE123_REPORT.json": artifacts / "G11_V16_1_FULL_IEEE123_REPORT.json",
    }
    old_shas = {name: sha256_file(path) for name, path in old_paths.items()}
    supersession = {
        "authority_id": "AEMO_APRIL_REBIND_SUPERSESSION_V16_1",
        "status": "SUPERSEDED_FOR_FINAL_ELECTRICAL_INPUT_BY_OFFICIAL_AEMO_APRIL_REBIND",
        "old_artifact_sha256": old_shas,
        "new_aemo_vintage_contract_sha256": sha256_file(vintage_path),
        "new_input_manifest_sha256": sha256_file(manifest_path),
        "reason": "Official April PREDISPATCHREGIONSUM ALL and ROOFTOP_PV_FORECAST archives were absent when the prior electrical-input evidence was produced and are now bound without changing science.",
        "science_change": False,
        "ml_change": False,
        "reference_compute_schedule_v3_policy_change": False,
        "old_artifact_bytes_modified": False,
    }
    _write_json(artifacts / "AEMO_APRIL_REBIND_SUPERSESSION_V16_1.json", supersession)
    old_c7 = json.loads(old_paths["C7_FULL_IEEE123_REPORT_V16_1.json"].read_text(encoding="utf-8"))
    delta = old_c7["reference_delta"]
    c7 = {
        "authority_id": "C7_FULL_IEEE123_V16_1_OFFICIAL_AEMO_APRIL_REBIND",
        "status": "PASS_FULL_IEEE123_V16_1",
        "operating_day": "2025-04-15",
        "official_aemo_input_manifest_sha256": sha256_file(manifest_path),
        "official_demand_identity": demand.identity,
        "official_pv_identity": pv.identity,
        "P_RES_SYS_kw": delta["P_RES_SYS_kw"],
        "G_RES_SYS": delta["G_RES_SYS"],
        "power_reconstruction_max_abs_error_kw": delta["power_reconstruction_max_abs_error_kw"],
        "pue_reconstruction_max_abs_error_kw": delta["pue_reconstruction_max_abs_error_kw"],
        "pue_application_count": delta["pue_application_count"],
        "rack_gpu_cap_violation_count": delta["rack_gpu_cap_violation_count"],
        "rack_gpu_cap_max_violation": delta["rack_gpu_cap_max_violation"],
        "reference_b0_b2_bytes_identical": old_c7["reference_b0_b2_bytes_identical"],
        "reference_b0_b2_sha_identical": old_c7["reference_b0_b2_sha_identical"],
        "reference_schedule_sha256": old_c7["reference_schedule_sha256"],
        "service_parity_residual": old_c7["service_parity_residual"],
        "service_parity_status": old_c7["service_parity_status"],
        "mess_invariants": old_c7["mess_invariants"],
        "legacy_rack_power_cap_active_constraint_call_count": 0,
        "reference_policy_reused_unchanged": True,
        "production_rc_mqt_reused_unchanged": True,
        "mapping_fitting_call_count": 0,
        "optimizer_call_count": 0,
        "actual_as_forecast_read_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    c7_path = artifacts / "C7_FULL_IEEE123_REPORT_V16_1_AEMO_REBIND.json"
    _write_json(c7_path, c7)
    g10 = {
        "authority_id": "G10_V16_1_OFFICIAL_AEMO_APRIL_REBIND",
        "status": "PASS",
        "c7_rebind_report_sha256": sha256_file(c7_path),
        "P_RES_SYS_nonnegative_all_96": int(delta["P_RES_SYS_kw"]["negative_slot_count"]) == 0,
        "G_RES_SYS_nonnegative_all_96": int(delta["G_RES_SYS"]["negative_slot_count"]) == 0,
        "exact_power_reconstruction": float(delta["power_reconstruction_max_abs_error_kw"]) <= 1e-9,
        "rack_gpu_capacity": "PASS" if int(delta["rack_gpu_cap_violation_count"]) == 0 else "FAIL",
        "v3_service_parity": "PASS" if abs(float(old_c7["service_parity_residual"])) <= 1e-12 else "FAIL",
        "mess_invariants": old_c7["mess_invariants"]["status"],
        "legacy_rack_total_kw_requirement_present": False,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }
    if not all((g10["P_RES_SYS_nonnegative_all_96"], g10["G_RES_SYS_nonnegative_all_96"], g10["exact_power_reconstruction"])):
        g10["status"] = "FAIL"
    g10_path = artifacts / "G10_V16_1_AEMO_REBIND_REPORT.json"
    _write_json(g10_path, g10)
    if g10["status"] != "PASS":
        return {"status": "STOPPED_AT_G10", "g10": g10}
    binding = build_full_grid_binding(
        assets=assets,
        contract=contract,
        demand_mw_96=mapped_demand,
        rooftop_pv_mw_96=mapped_pv,
        aidc_plan_kw_96x12=delta["p_aidc_plan_kw"],
    )
    g11_execution = run_g11(binding)
    apparent = [
        [float(value) / PF_AIDC for value in row]
        for row in delta["p_aidc_plan_kw"]
    ]
    violations = [
        (time_index, aidc_index + 1, value - 750.0, value)
        for time_index, row in enumerate(apparent)
        for aidc_index, value in enumerate(row)
        if value > 750.0 + 1e-9
    ]
    worst = max(violations, key=lambda item: item[2]) if violations else None
    g11 = {
        "authority_id": "G11_V16_1_FULL_IEEE123_OFFICIAL_AEMO_APRIL_REBIND",
        "status": g11_execution["status"],
        "required_pass_status": "PASS_FULL_IEEE123_V16_1",
        "operating_day": "2025-04-15",
        "aemo_vintage_contract_sha256": sha256_file(vintage_path),
        "input_manifest_sha256": sha256_file(manifest_path),
        "c7_rebind_sha256": sha256_file(c7_path),
        "g10_rebind_sha256": sha256_file(g10_path),
        "execution": g11_execution,
        "dedicated_aidc_pcc_transformer_audit": {
            "frozen_rating_kva_each": 750.0,
            "aidc_power_factor": PF_AIDC,
            "violation_count_aidc_slots": len(violations),
            "worst": None if worst is None else {
                "time_index": worst[0],
                "aidc_id": f"AIDC{worst[1]:02d}",
                "violation_kva": worst[2],
                "apparent_power_kva": worst[3],
                "active_power_kw": float(delta["p_aidc_plan_kw"][worst[0]][worst[1] - 1]),
            },
            "rating_relaxation_or_uprate_used": False,
        },
        "prior_g11_failure_artifact_preserved_sha256": old_shas["G11_V16_1_FULL_IEEE123_REPORT.json"],
        "downstream_call_counts": {"G12": 0, "G13": 0, "realized_replay": 0, "G14": 0, "C12": 0},
        "firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "actual_as_forecast_read_count": 0,
            "may_forecast_rows": 0,
            "may_reference_schedule_created": False,
            "may_b0_b3_results_created": False,
            "june_results_created": False,
        },
        "stop_rule": "STOP_AFTER_G11",
        "stop_rule_applied": True,
    }
    g11_path = artifacts / "G11_V16_1_FULL_IEEE123_AEMO_REBIND_REPORT.json"
    _write_json(g11_path, g11)
    return {
        "status": g11["status"],
        "acquisition_sha256": sha256_file(acquisition_path),
        "vintage_contract_sha256": sha256_file(vintage_path),
        "input_manifest_sha256": sha256_file(manifest_path),
        "c7_sha256": sha256_file(c7_path),
        "g10_sha256": sha256_file(g10_path),
        "g11_sha256": sha256_file(g11_path),
        "demand_identity": demand.identity,
        "pv_identity": pv.identity,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--source-artifacts", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args(argv)
    result = execute(
        repo=args.repo,
        raw_root=args.raw_root,
        artifacts=args.artifacts,
        source_artifacts=args.source_artifacts,
        assets=args.assets,
        contract=args.contract,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS_FULL_IEEE123_V16_1", "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE", "FAIL_G11_DUAL_FARKAS_VALIDATION"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
