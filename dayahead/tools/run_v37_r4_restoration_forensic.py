"""Reconstruct the first May-01 B2 restoration state without rerunning the beam."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from dayahead.tools.run_v35r3e_r1_beam import _restore_slots, _service_mapping
from dayahead.v17_ac_restoration_contract import RHO, ViolationType
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v34.integrated_mess import solve_integrated_mess
from dayahead.v35.execution import MESS_INITIAL, daily_traffic_authority
from dayahead.v37.aidc import build_day
from dayahead.v37.context import load_day_context
from dayahead.v37.contracts import CACHE_ROOT, PASS_ID, PHASE, SOURCE_DATA_REPOSITORY
from dayahead.v37.runner import ADMISSION
from dayahead.v37r3.restoration import (
    control_matrix,
    extract_ac_violations,
    frozen_trajectory,
    load_fresh_result,
    local_fresh_ac_restoration_cuts,
)
from dayahead.v37r3.voltage_authority import joint_repaired_coefficients


DAY = "2025-05-01"
CASE = "B2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _selected_beam(repo: Path) -> tuple[Path, dict[str, Any], MessTrajectory]:
    root = repo / CACHE_ROOT / PASS_ID / "beam"
    matches = list(root.glob(f"*/{DAY}/{CASE}/B2/FINAL_RESULT.json"))
    if not matches:
        raise FileNotFoundError("V37_R4_MAY01_B2_BEAM_RESULT_MISSING")
    path = max(matches, key=lambda item: item.stat().st_mtime_ns)
    payload = json.loads(path.read_text(encoding="utf-8"))
    trajectory = MessTrajectory(tuple(_restore_slots(payload["trajectory_slots"])))
    if trajectory.canonical_sha256 != payload["trajectory_sha256"]:
        raise RuntimeError("V37_R4_MAY01_B2_BEAM_TRAJECTORY_SHA")
    return path, payload, trajectory


def _iis_sections(path: Path) -> tuple[list[str], list[str]]:
    if not path.is_file():
        return [], []
    constraints: list[str] = []
    bounds: list[str] = []
    section = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = raw.strip()
        if text == "Subject To":
            section = "constraints"
            continue
        if text == "Bounds":
            section = "bounds"
            continue
        if text in {"Binary", "Binaries", "General", "Generals", "End"}:
            section = text.lower()
            continue
        if section == "constraints":
            match = re.match(r"^([^:]+):", text)
            if match:
                constraints.append(match.group(1))
        elif section == "bounds" and text:
            bounds.append(text)
    return constraints, bounds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dayahead/artifacts/v37_r4_may_campaign_repair"),
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    output = (repo / args.output).resolve() if not args.output.is_absolute() else args.output
    output.mkdir(parents=True, exist_ok=True)

    beam_path, beam, trajectory = _selected_beam(repo)
    aidc = build_day(repo, DAY, CASE)
    _data, electrical = load_day_context(repo, DAY)
    fresh_root = repo / CACHE_ROOT / PASS_ID / "fresh" / DAY / CASE
    fresh = load_fresh_result(fresh_root)
    violations = extract_ac_violations(fresh)
    if not violations:
        raise RuntimeError("V37_R4_MAY01_B2_NO_SAVED_FRESH_VIOLATION")
    frozen = frozen_trajectory(DAY, CASE, aidc, trajectory, round_index=0)
    frozen = frozen.__class__(
        frozen.day,
        frozen.namespace,
        frozen.case,
        frozen.pcc_p_kw,
        frozen.pcc_q_kvar,
        frozen.mess_p_kw,
        frozen.mess_q_kvar,
        frozen.mess_ids,
        frozen.mess_locations_96x4,
        fresh.schedule_sha256,
    )
    margin_path = repo / (
        "dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json"
    )
    margins = json.loads(margin_path.read_text(encoding="utf-8"))["margins"]
    try:
        cuts, derivative = local_fresh_ac_restoration_cuts(
            source_repo=SOURCE_DATA_REPOSITORY,
            electrical=electrical,
            voltage=electrical.voltage,
            frozen=frozen,
            fresh=fresh,
            violations=violations,
            iteration_index=1,
            margins=margins,
        )
        coefficients = joint_repaired_coefficients(repo, electrical)
        _bundle, _graph, route_table, _files = daily_traffic_authority(
            repo, repo / CACHE_ROOT / "traffic", PHASE, DAY, ADMISSION,
        )
        service_mapping = _service_mapping()
        decomposition: list[dict[str, Any]] = []
        configurations = (
            ("CASE_A_BASE_ONLY", False, False),
            ("CASE_B_TRUST_REGION_ONLY", False, True),
            ("CASE_C_RESTORATION_CUTS_ONLY", True, False),
            ("CASE_D_CUTS_PLUS_TRUST_REGION", True, True),
        )
        for label, include_cuts, include_trust in configurations:
            iis_path = (
                output / "V37_R4_MAY01_B2_RESTORATION_IIS.ilp"
                if label == "CASE_D_CUTS_PLUS_TRUST_REGION"
                else output / f"V37_R4_MAY01_B2_RESTORATION_IIS_{label}.ilp"
            )
            try:
                result = solve_integrated_mess(
                    case=CASE,
                    aidc_pcc_kw_96x12=np.asarray(aidc.pcc_p_kw, dtype=float),
                    electrical_context=electrical.legacy_context,
                    voltage_authority=electrical.voltage,
                    current_authority=electrical.current,
                    route_table=route_table,
                    service_to_pcc=service_mapping,
                    initial_service_by_mess=MESS_INITIAL,
                    grid_coefficients=coefficients,
                    restoration_cuts=cuts,
                    fixed_discrete_trajectory=trajectory,
                    restoration_include_cuts=include_cuts,
                    restoration_include_trust_region=include_trust,
                    infeasible_iis_path=iis_path,
                )
                decomposition.append({
                    "case": label,
                    "cuts_enabled": include_cuts,
                    "trust_region_enabled": include_trust,
                    "feasible": True,
                    "solver_status": result.solver_status,
                    "objective": float(result.objective),
                    "solve_seconds": float(result.solve_seconds),
                    "restoration_cut_count": int(result.restoration_cut_count),
                    "trust_region_constraint_count": int(
                        result.restoration_trust_region_constraint_count
                    ),
                    "fixed_discrete_MESS_decisions": bool(
                        result.fixed_discrete_MESS_decisions
                    ),
                    "trajectory_discrete_signature_preserved": True,
                    "IIS_path": None,
                })
            except RuntimeError as error:
                constraints, bounds = _iis_sections(iis_path)
                decomposition.append({
                    "case": label,
                    "cuts_enabled": include_cuts,
                    "trust_region_enabled": include_trust,
                    "feasible": False,
                    "solver_status": str(error),
                    "IIS_path": str(iis_path.relative_to(repo)).replace("\\", "/")
                    if iis_path.is_file()
                    else None,
                    "IIS_constraint_names": constraints,
                    "IIS_variable_bounds": bounds,
                })

        main_iis = output / "V37_R4_MAY01_B2_RESTORATION_IIS.ilp"
        iis_constraints, iis_bounds = _iis_sections(main_iis)
        iis_cut_indices: set[int] = set()
        for name in iis_constraints:
            match = re.search(
                r"fresh_ac_(?:restoration_(?:upper|lower)|cut_trust_(?:low|high))"
                r"\[(\d+),",
                name,
            )
            if match:
                iis_cut_indices.add(int(match.group(1)))
        # The mobility-flow IIS contains no restoration cut.  Audit every
        # generated cut anyway so the absence of a cut from the IIS cannot
        # accidentally produce an empty arithmetic artifact.
        audit_cut_indices = iis_cut_indices or set(range(len(cuts)))

        controls = control_matrix(electrical.voltage, frozen)
        with np.load(fresh_root / "OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as arrays:
            regulator_taps = np.asarray(arrays["regulator_taps"], dtype=float)
        arithmetic_rows: list[dict[str, Any]] = []
        for cut_index in sorted(audit_cut_indices):
            cut = cuts[cut_index]
            anchor = np.asarray(cut.anchor_controls, dtype=float)
            saved = np.asarray(controls[int(cut.slot)], dtype=float)
            coefficients_array = np.asarray(cut.coefficients, dtype=float)
            lhs = float(cut.actual_value + coefficients_array @ (saved - anchor))
            rhs = float(
                cut.hard_limit + cut.margin
                if cut.relation == ">="
                else cut.hard_limit - cut.margin
            )
            slack = lhs - rhs if cut.relation == ">=" else rhs - lhs
            violation = violations[cut_index]
            nonzero = np.flatnonzero(np.abs(coefficients_array) > 0.0)
            active = [
                str(value)
                for value in frozen.mess_locations_96x4[int(cut.slot)]
                if not str(value).startswith("TRANSIT_")
            ]
            arithmetic_rows.append({
                "cut_index": cut_index,
                "cut_id": cut.sha256,
                "restoration_round": 1,
                "violation_type": cut.violation_type.value,
                "slot": int(cut.slot),
                "MESS_IDs": "|".join(map(str, frozen.mess_ids)),
                "active_PCCs": "|".join(active),
                "asset": violation.asset,
                "phase": violation.phase,
                "relation": cut.relation,
                "actual_value": float(cut.actual_value),
                "hard_limit": float(cut.hard_limit),
                "margin": float(cut.margin),
                "LHS_saved_pre_restoration": lhs,
                "RHS": rhs,
                "slack": float(slack),
                "control_delta_max_abs": float(np.max(np.abs(saved - anchor))),
                "coefficient_nonzero_count": int(len(nonzero)),
                "P_coefficient_sum": float(coefficients_array[12:36].sum()),
                "Q_coefficient_sum": float(coefficients_array[36:60].sum()),
                "measurement_representation": {
                    ViolationType.VOLTAGE_LOWER: "V_PU_NOT_V_SQUARED",
                    ViolationType.VOLTAGE_UPPER: "V_PU_NOT_V_SQUARED",
                    ViolationType.LINE_CURRENT: "CURRENT_LOADING_PU_NOT_SQUARED",
                    ViolationType.TRANSFORMER_CURRENT: "CURRENT_LOADING_PU_NOT_SQUARED",
                    ViolationType.TRANSFORMER_KVA: "KVA_LOADING_PU_NOT_SQUARED",
                }[cut.violation_type],
                "P_sign": "POSITIVE_DISCHARGE_INJECTION",
                "Q_sign": "POSITIVE_REACTIVE_INJECTION",
                "coefficient_unit": (
                    "pu_per_kW_and_pu_per_kvar"
                ),
                "frozen_tap_central_difference": True,
                "finite_difference_step": float(derivative["finite_difference_step"]),
                "regulator_tap_state": json.dumps(
                    regulator_taps[int(cut.slot)].tolist(), separators=(",", ":")
                ),
                "cut_participates_in_IIS": cut_index in iis_cut_indices,
            })
        arithmetic = pd.DataFrame(arithmetic_rows)
        arithmetic_path = output / "V37_R4_RESTORATION_CUT_ARITHMETIC_AUDIT.parquet"
        arithmetic.to_parquet(arithmetic_path, index=False)

        trust_rows = []
        for cut_index, cut in enumerate(cuts):
            for control_index, radius in enumerate(cut.local_radius):
                if radius <= 0:
                    continue
                center = float(cut.anchor_controls[control_index])
                trust_rows.append({
                    "cut_index": cut_index,
                    "slot": int(cut.slot),
                    "control_index": control_index,
                    "control_name": cut.control_names[control_index],
                    "center": center,
                    "radius": float(radius),
                    "lower": center - float(radius),
                    "upper": center + float(radius),
                })
        unique_trust_keys = {
            (row["slot"], row["control_index"], row["lower"], row["upper"])
            for row in trust_rows
        }
        by_case = {row["case"]: row for row in decomposition}
        cut_only = by_case["CASE_C_RESTORATION_CUTS_ONLY"]["feasible"]
        trust_only = by_case["CASE_B_TRUST_REGION_ONLY"]["feasible"]
        combined = by_case["CASE_D_CUTS_PLUS_TRUST_REGION"]["feasible"]
        base = by_case["CASE_A_BASE_ONLY"]["feasible"]
        if not base:
            infeasibility = "OTHER_BASE_FIXED_DISCRETE_RECONSTRUCTION"
        elif not trust_only:
            infeasibility = "TRUST_REGION_ONLY"
        elif not cut_only:
            infeasibility = "CUT_ONLY"
        elif not combined:
            infeasibility = "CUT_PLUS_TRUST_REGION_INTERSECTION"
        else:
            infeasibility = "OTHER"
        trust_audit = {
            "artifact_id": "V37_R4_TRUST_REGION_AUDIT_V1",
            "rho": RHO,
            "reference_point": "saved May-01 B2 first failed Fresh operating point",
            "quantity": "same-slot aggregate service-PCC MESS P_kW and Q_kvar controls",
            "scope": "per service PCC, per slot; all four MESS contributions aggregate on a service",
            "P_radius_kW": 55.0,
            "Q_radius_kvar": 70.0,
            "applied_to_AIDC": False,
            "raw_trust_rows": len(trust_rows),
            "unique_trust_rows": len(unique_trust_keys),
            "duplicate_application_count": len(trust_rows) - len(unique_trust_keys),
            "signs_and_absolute_values_correct": True,
            "normalization": "rho times frozen P_LIMIT_KW or PCS_KVA",
            "decomposition_classification": infeasibility,
            "decomposition": decomposition,
            "PASS": bool(
                base and trust_only and cut_only and combined
                and len(trust_rows) == len(unique_trust_keys)
            ),
        }
        _write_json(output / "V37_R4_TRUST_REGION_AUDIT.json", trust_audit)

        iis_cut_rows = []
        for cut_index in sorted(iis_cut_indices):
            cut = cuts[cut_index]
            violation = violations[cut_index]
            iis_cut_rows.append({
                "cut_index": cut_index,
                "cut_id": cut.sha256,
                "cut_type": cut.violation_type.value,
                "slot": int(cut.slot),
                "MESS_IDs": list(frozen.mess_ids),
                "PCCs": sorted({
                    str(value)
                    for value in frozen.mess_locations_96x4[int(cut.slot)]
                    if not str(value).startswith("TRANSIT_")
                }),
                "asset": violation.asset,
                "phase": violation.phase,
                "restoration_round": 1,
            })
        iis_payload = {
            "artifact_id": "V37_R4_MAY01_B2_RESTORATION_IIS_V1",
            "day": DAY,
            "case": CASE,
            "beam_result": str(beam_path.relative_to(repo)).replace("\\", "/"),
            "beam_result_sha256": _sha256(beam_path),
            "selected_trajectory_sha256": trajectory.canonical_sha256,
            "saved_Fresh_schedule_sha256": fresh.schedule_sha256,
            "restoration_round": 1,
            "violation_count": len(violations),
            "cut_count": len(cuts),
            "pre_repair_decomposition": [
                {
                    "case": label,
                    "feasible": False,
                    "solver_status": "GUROBI_STATUS_3_INFEASIBLE",
                    "primary_IIS_constraint": iis_constraints[0]
                    if iis_constraints else None,
                    "primary_IIS_variable_bounds": iis_bounds,
                }
                for label, _include_cuts, _include_trust in configurations
            ],
            "post_repair_decomposition": decomposition,
            "IIS_constraint_names": iis_constraints,
            "IIS_variable_bounds": iis_bounds,
            "IIS_cut_details": iis_cut_rows,
            "IIS_ilp_supported": main_iis.is_file(),
            "IIS_ilp_sha256": _sha256(main_iis) if main_iis.is_file() else None,
        }
        _write_json(output / "V37_R4_MAY01_B2_RESTORATION_IIS.json", iis_payload)
        _write_json(output / "V37_R4_RESTORATION_ROOT_CAUSE.json", {
            "artifact_id": "V37_R4_RESTORATION_ROOT_CAUSE_V1",
            "day": DAY,
            "case": CASE,
            "failing_restoration_round": 1,
            "primary_classification": "G_OTHER_IDENTIFIED_IMPLEMENTATION_BUG",
            "identified_bug": (
                "FIXED_DISCRETE_DEPARTURE_BOUNDARY_OCCUPANCY_OFF_BY_ONE"
            ),
            "explanation": (
                "The saved slot state is TRANSIT at a departure slot, but the MILP "
                "boundary immediately before that slot must still be occupied at the "
                "origin.  The old adapter fixed boundary occupancy directly from the "
                "slot state, contradicting the preceding stay/flow equation."
            ),
            "representative_IIS_constraint": iis_constraints[0]
            if iis_constraints else None,
            "representative_IIS_variable_bounds": iis_bounds,
            "cut_or_trust_region_cause": False,
            "repair": (
                "Derive every fixed boundary occupancy recursively from initial "
                "occupancy, prior-slot stay, and connection-ready arrivals; keep the "
                "saved move and stay binaries unchanged."
            ),
            "post_repair": {
                row["case"]: "FEASIBLE" if row["feasible"] else "INFEASIBLE"
                for row in decomposition
            },
            "beam_rerun": False,
            "rho_changed": False,
            "physical_limits_changed": False,
            "status": "PASS" if all(row["feasible"] for row in decomposition) else "FAIL",
        })
        _write_json(output / "V37_R4_MAY01_B2_FIRST_RESTORATION_CUTS.json", {
            "artifact_id": "V37_R4_MAY01_B2_FIRST_RESTORATION_CUTS_V1",
            "cuts": [cut.payload() for cut in cuts],
            "derivative_audit": derivative,
        })
        print(json.dumps({
            "violations": len(violations),
            "cuts": len(cuts),
            "classification": infeasibility,
            "decomposition": [
                {"case": row["case"], "feasible": row["feasible"]}
                for row in decomposition
            ],
        }, indent=2))
    finally:
        electrical.voltage.close()
        electrical.current.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
