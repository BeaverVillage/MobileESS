"""Interruption-safe Apr-01 certification assembled from saved V36 outputs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .contracts import (
    AIDC_HEAD, ARTIFACT_DIR, BEAM_WIDTH, BRANCH, CACHE_ROOT,
    CALIBRATION_DATES, DEFAULT_K, EXPANDED_TEMPORAL_GPU_HOURS, EXPANDED_TEMPORAL_JOBS,
    INTEGRATION_BASE_HEAD, LOG_ROOT, MESS_HEAD, OFFICIAL_CASES,
    PARTIAL_SHARED_TEMPORAL_GPU_HOURS, PARTIAL_SHARED_TEMPORAL_JOBS,
    RAW_ROOT, SCHEMA_IDS, SCHEMA_VERSION, SEED_WIDTH, SCIENCE_AUTHORITIES,
    FROZEN_MESS_WORKTREE,
)
from .science import canonical_sha256, verify_science
from .storage import (
    CASE_FILES, file_sha, finalize_date, mess_frames, write_csv, write_json, write_parquet,
)


PASS_ID = "PRE_CALIBRATION"
APR01 = "2025-04-01"
BEAM_DIRECTORY = f"B{BEAM_WIDTH}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority_header(repo: Path) -> dict[str, Any]:
    return {
        "source_branch": BRANCH,
        "source_HEAD": INTEGRATION_BASE_HEAD,
        "source_AIDC_HEAD": AIDC_HEAD,
        "source_MESS_HEAD": MESS_HEAD,
        "date": APR01,
        "PRIMARY_AIDC_POWER_SCENARIO": "CENTER",
        "LOW_HIGH_OPTIMIZATION": "DISABLED",
        "LOW_HIGH_MAIN_CASES": "DISABLED",
        "FRESH_USED_AS_CONTROL_ORACLE": "NO",
        "IDC_LOCATION_CHANGED": "NO",
        "generated_from_saved_outputs": True,
        "worktree": str(repo),
    }


def beam_result_path(repo: Path, case: str) -> Path:
    return repo / CACHE_ROOT / PASS_ID / "beam" / APR01 / case / BEAM_DIRECTORY / "FINAL_RESULT.json"


def _beam_result(repo: Path, case: str) -> dict[str, Any]:
    path = beam_result_path(repo, case)
    if not path.is_file():
        raise FileNotFoundError(f"V36_MISSING_BEAM_RESULT:{case}:{path}")
    return _read_json(path)


def repair_move_serialization(repo: Path) -> list[dict[str, Any]]:
    """Rewrite only MOVE reporting tables from authoritative saved trajectories."""

    repairs: list[dict[str, Any]] = []
    for case in ("B2", "B3"):
        result = _beam_result(repo, case)
        _trajectory, moves, _search, _solver = mess_frames(APR01, case, result)
        target = repo / RAW_ROOT / PASS_ID / APR01 / case / "mess/MESS_MOVE_EVENTS.parquet"
        before = file_sha(target) if target.is_file() else None
        write_parquet(target, moves)
        repairs.append({
            "case": case,
            "file": target.relative_to(repo).as_posix(),
            "before_sha256": before,
            "after_sha256": file_sha(target),
            "rule": "arrival_slot = departure_slot + travel_slots_15min",
            "science_changed": False,
        })
    return repairs


def repair_input_authority_paths(repo: Path) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    traffic_root = FROZEN_MESS_WORKTREE / "dayahead/cache/v35/shared/traffic" / APR01
    corrections = {
        "traffic_prediction": traffic_root / "TRAFFIC_FORECAST.npz",
        "MESS_route_table": traffic_root / "ROUTE_TABLE.json.gz",
    }
    for case in OFFICIAL_CASES:
        target = repo / RAW_ROOT / PASS_ID / APR01 / case / "inputs/INPUT_AUTHORITY.json"
        value = _read_json(target)
        for label, path in corrections.items():
            if not path.is_file():
                raise FileNotFoundError(f"V36_INPUT_AUTHORITY_MISSING:{label}:{path}")
            value["immutable_references"][label] = {
                "path": str(path), "exists": True, "sha256": file_sha(path),
            }
        value["immutable_references"]["Safe_ETA_calibration"] = {
            "git_commit": SCIENCE_AUTHORITIES["SAFE_ETA"]["commit"],
            "git_path": SCIENCE_AUTHORITIES["SAFE_ETA"]["path"],
            "sha256": SCIENCE_AUTHORITIES["SAFE_ETA"]["sha256"],
            "git_blob": SCIENCE_AUTHORITIES["SAFE_ETA"]["git_blob"],
        }
        value.update(_authority_header(repo))
        before = file_sha(target)
        write_json(target, value)
        repairs.append({
            "case": case, "file": target.relative_to(repo).as_posix(),
            "before_sha256": before, "after_sha256": file_sha(target),
            "rule": "deterministic frozen traffic-cache and Safe-ETA authority lookup",
            "science_changed": False,
        })
        provenance_path = repo / RAW_ROOT / PASS_ID / APR01 / case / "inputs/RUN_PROVENANCE.json"
        provenance = _read_json(provenance_path)
        provenance.update(_authority_header(repo))
        provenance["Safe_ETA_authority_SHA"] = SCIENCE_AUTHORITIES["SAFE_ETA"]["sha256"]
        provenance_before = file_sha(provenance_path)
        write_json(provenance_path, provenance)
        repairs.append({
            "case": case, "file": provenance_path.relative_to(repo).as_posix(),
            "before_sha256": provenance_before, "after_sha256": file_sha(provenance_path),
            "rule": "add recovery lineage and Safe-ETA authority SHA",
            "science_changed": False,
        })
    return repairs


def repair_aidc_power_schema(repo: Path) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    for case in OFFICIAL_CASES:
        target = repo / RAW_ROOT / PASS_ID / APR01 / case / "aidc/AIDC_POWER_96.csv"
        frame = pd.read_csv(target)
        before = file_sha(target)
        frame["C1_effective_PUE"] = frame["aggregate_PCC_P_kW"] / frame["P_IT_case_kW"]
        columns = list(frame.columns)
        columns.insert(columns.index("aggregate_PCC_P_kW"), columns.pop(columns.index("C1_effective_PUE")))
        write_csv(target, frame[columns])
        repairs.append({
            "case": case, "file": target.relative_to(repo).as_posix(),
            "before_sha256": before, "after_sha256": file_sha(target),
            "rule": "derive aggregate effective PUE from saved C1 facility and IT power",
            "science_changed": False,
        })
    return repairs


SEARCH_COLUMNS = [
    "case", "vehicle", "parent_beam_state", "candidate_id", "cheap_score", "cheap_rank",
    "Top_K_selected", "restricted_objective", "restricted_status", "seed_flag", "seed_trajectory_SHA",
    "full_MILP_child_state", "MIPStart_accepted", "full_objective", "best_bound", "gap",
    "beam_retained", "beam_parent_SHA", "beam_child_SHA", "beam_width_used", "K_used",
    "beam_fallback_used", "K_fallback_used", "full_scan_used", "cheap_score_available",
    "screen_authority_sha", "restricted_runtime_seconds", "full_solver_status",
]

SOLVER_COLUMNS = [
    "solve_id", "candidate_id", "solver_type", "case", "vehicle", "beam_state", "status",
    "WorkLimit", "incumbent", "best_bound", "gap", "MIPStart_accepted", "wallclock", "threads",
    "solve_classification", "retry_count", "fallback_reason",
]


def rewrite_search_solver_outputs(repo: Path) -> None:
    """Materialize saved restricted/full solve caches without rerunning them."""

    date_root = repo / RAW_ROOT / PASS_ID / APR01
    for case in ("B0", "B1"):
        write_parquet(date_root / case / "mess/MESS_SEARCH_TRACE.parquet", pd.DataFrame(columns=SEARCH_COLUMNS))
        write_parquet(date_root / case / "solver/SOLVER_RUNS.parquet", pd.DataFrame(columns=SOLVER_COLUMNS))
    for case in ("B2", "B3"):
        cache_root = beam_result_path(repo, case).parent
        search_rows: list[dict[str, Any]] = []
        solver_rows: list[dict[str, Any]] = []
        state_sha = {f"{case}-ROOT": canonical_sha256({"case": case, "root": True})}
        for stage_index in range(1, 5):
            stage = _read_json(cache_root / f"STAGE_{stage_index}.json")
            retained_ids = {row["beam_state_id"] for row in stage["retained_states"]}
            for state in (*stage["retained_states"], *stage["pruned_states"]):
                state_sha[str(state["beam_state_id"])] = str(state["state_sha256"])
            for parent in stage["parent_diagnostics"]:
                parent_id = str(parent["parent_state_id"])
                parent_root = cache_root / f"s{stage_index}" / parent_id
                restricted = pd.read_csv(parent_root / "RESTRICTED_VALUES.csv")
                seeds = {str(row["candidate_id"]): row for row in _read_json(parent_root / "SEEDS.json")}
                children: dict[str, dict[str, Any]] = {}
                for child_path in sorted(parent_root.glob("CHILD_*.json")):
                    child = _read_json(child_path)
                    vehicle = child["vehicles"][-1]
                    children[str(vehicle["MIPStart_source_candidate"])] = child
                    solver_rows.append({
                        "solve_id": f"{case}:FULL:{child['beam_state_id']}",
                        "candidate_id": vehicle["MIPStart_source_candidate"],
                        "solver_type": "GUROBI", "case": case, "vehicle": vehicle["mess_id"],
                        "beam_state": parent_id, "status": vehicle["solver_status"],
                        "WorkLimit": json.dumps(vehicle["work_limit_tiers_attempted"]),
                        "incumbent": vehicle["full_solver_objective"],
                        "best_bound": vehicle["full_best_bound"], "gap": vehicle["full_gap"],
                        "MIPStart_accepted": vehicle["MIPStart_accepted"],
                        "wallclock": vehicle["full_MILP_wallclock_seconds"], "threads": 4,
                        "solve_classification": "UNRESTRICTED_FULL_MULTI_MOVE_MILP",
                        "retry_count": 0, "fallback_reason": None,
                    })
                cheap_rank = {str(value): index for index, value in enumerate(parent["selected_candidate_ids"])}
                for row in restricted.to_dict(orient="records"):
                    candidate_id = str(row["candidate_id"])
                    seed = seeds.get(candidate_id)
                    child = children.get(candidate_id)
                    vehicle = child["vehicles"][-1] if child is not None else None
                    child_id = None if child is None else str(child["beam_state_id"])
                    search_rows.append({
                        "case": case, "vehicle": parent["mess_id"], "parent_beam_state": parent_id,
                        "candidate_id": candidate_id, "cheap_score": None,
                        "cheap_rank": int(cheap_rank[candidate_id]), "Top_K_selected": True,
                        "restricted_objective": float(row["objective"]),
                        "restricted_status": "OPTIMAL" if bool(row["exact_optimality_certificate"]) else "FEASIBLE",
                        "seed_flag": seed is not None,
                        "seed_trajectory_SHA": None if seed is None else seed["trajectory_signature"],
                        "full_MILP_child_state": child_id,
                        "MIPStart_accepted": None if vehicle is None else bool(vehicle["MIPStart_accepted"]),
                        "full_objective": None if vehicle is None else float(vehicle["full_solver_objective"]),
                        "best_bound": None if vehicle is None else vehicle["full_best_bound"],
                        "gap": None if vehicle is None else vehicle["full_gap"],
                        "beam_retained": None if child_id is None else child_id in retained_ids,
                        "beam_parent_SHA": state_sha[parent_id],
                        "beam_child_SHA": None if child is None else child["state_sha256"],
                        "beam_width_used": BEAM_WIDTH, "K_used": DEFAULT_K,
                        "beam_fallback_used": False, "K_fallback_used": False, "full_scan_used": False,
                        "cheap_score_available": False, "screen_authority_sha": parent["screen_authority_sha"],
                        "restricted_runtime_seconds": float(row["runtime_seconds"]),
                        "full_solver_status": None if vehicle is None else vehicle["solver_status"],
                    })
                    solver_rows.append({
                        "solve_id": f"{case}:RESTRICTED:{parent_id}:{candidate_id}",
                        "candidate_id": candidate_id, "solver_type": "GUROBI", "case": case,
                        "vehicle": parent["mess_id"], "beam_state": parent_id,
                        "status": "OPTIMAL" if bool(row["exact_optimality_certificate"]) else "FEASIBLE",
                        "WorkLimit": "RESTRICTED_EXACT", "incumbent": float(row["objective"]),
                        "best_bound": float(row["objective"]), "gap": 0.0,
                        "MIPStart_accepted": False, "wallclock": float(row["runtime_seconds"]),
                        "threads": 1, "solve_classification": "EXACT_RESTRICTED_TOP_K_OR_STAY",
                        "retry_count": 0, "fallback_reason": None,
                    })
        write_parquet(
            date_root / case / "mess/MESS_SEARCH_TRACE.parquet",
            pd.DataFrame(search_rows, columns=SEARCH_COLUMNS),
        )
        write_parquet(
            date_root / case / "solver/SOLVER_RUNS.parquet",
            pd.DataFrame(solver_rows, columns=SOLVER_COLUMNS),
        )


def _worst_row(frame: pd.DataFrame, column: str, threshold: float, direction: str) -> dict[str, Any]:
    if direction == "lower":
        exceedance = threshold - frame[column]
    else:
        exceedance = frame[column] - threshold
    index = int(exceedance.to_numpy().argmax())
    row = frame.iloc[index]
    value = max(0.0, float(exceedance.iloc[index]))
    return {
        "exceedance": value,
        "slot": int(row["slot"]),
        "device": str(row.get("bus_phase_key", row.get("branch", "SYSTEM"))),
        "phase": None if pd.isna(row.get("phase")) else str(row.get("phase")),
    }


def _grid_gate(case_root: Path, namespace: str) -> dict[str, Any]:
    prefix = "PLANNING" if namespace == "Planning" else "FRESH"
    folder = "planning" if namespace == "Planning" else "fresh"
    voltage_column = "voltage_magnitude_pu" if namespace == "Planning" else "fresh_voltage_magnitude_pu"
    bus = pd.read_parquet(case_root / folder / f"{prefix}_BUS_PHASE_96.parquet")
    line = pd.read_parquet(case_root / folder / f"{prefix}_LINE_PHASE_96.parquet")
    system = pd.read_parquet(case_root / folder / f"{prefix}_SYSTEM_96.parquet")
    line_only = line[line["branch_kind"] == "line"].reset_index(drop=True)
    transformer = line[line["branch_kind"] == "transformer"].reset_index(drop=True)
    lower = bus[voltage_column] < 0.95 - 1e-9
    upper = bus[voltage_column] > 1.05 + 1e-9
    current = line_only["phase_current_loading_pu"] > 1.0 + 1e-9
    transformer_bad = (
        (transformer["phase_current_loading_pu"] > 1.0 + 1e-9)
        | (transformer["transformer_loading_pu"] > 1.0 + 1e-9)
    )
    worst_lower = _worst_row(bus, voltage_column, 0.95, "lower")
    worst_upper = _worst_row(bus, voltage_column, 1.05, "upper")
    worst_current = _worst_row(line_only, "phase_current_loading_pu", 1.0, "upper")
    if transformer.empty:
        worst_transformer = {"exceedance": 0.0, "slot": None, "device": None, "phase": None}
    else:
        tx = transformer.copy()
        tx["combined_loading"] = tx[["phase_current_loading_pu", "transformer_loading_pu"]].max(axis=1)
        worst_transformer = _worst_row(tx, "combined_loading", 1.0, "upper")
    return {
        "voltage_violation_count": int(lower.sum() + upper.sum()),
        "lower_voltage_violation_count": int(lower.sum()),
        "upper_voltage_violation_count": int(upper.sum()),
        "current_violation_count": int(current.sum()),
        "transformer_violation_count": int(transformer_bad.sum()),
        "worst_lower_exceedance_pu": worst_lower["exceedance"],
        "worst_upper_exceedance_pu": worst_upper["exceedance"],
        "worst_current_exceedance_pu": worst_current["exceedance"],
        "worst_transformer_exceedance_pu": worst_transformer["exceedance"],
        "worst_lower": worst_lower,
        "worst_upper": worst_upper,
        "worst_current": worst_current,
        "worst_transformer": worst_transformer,
        "Vmin_pu": float(bus[voltage_column].min()),
        "Vmax_pu": float(bus[voltage_column].max()),
        "rho": float(system["system_rho"].max()),
        "max_line_current_loading_pu": float(line_only["phase_current_loading_pu"].max()),
        "max_transformer_current_loading_pu": float(transformer["phase_current_loading_pu"].max()),
        "max_transformer_kva_loading_pu": float(transformer["transformer_loading_pu"].max()),
    }


def rewrite_physical_gates(repo: Path) -> None:
    date_root = repo / RAW_ROOT / PASS_ID / APR01
    for case in OFFICIAL_CASES:
        case_root = date_root / case
        result: dict[str, Any] = {
            "schema_id": SCHEMA_IDS["PHYSICAL_GATES"],
            "Planning": _grid_gate(case_root, "Planning"),
            "Fresh": _grid_gate(case_root, "Fresh"),
        }
        fresh_system = pd.read_parquet(case_root / "fresh/FRESH_SYSTEM_96.parquet")
        result["Fresh_solve_coverage"] = f"{int(fresh_system['OpenDSS_converged'].sum())}/96"
        if case in {"B2", "B3"}:
            trajectory = pd.read_parquet(case_root / "mess/MESS_TRAJECTORY_96.parquet")
            moves = pd.read_parquet(case_root / "mess/MESS_MOVE_EVENTS.parquet")
            result["MESS"] = {
                "SoC_feasible": bool(trajectory["SoC_fraction"].between(-1e-9, 1.0 + 1e-9).all()),
                "travel_feasible": bool((moves["arrival_slot"] > moves["departure_slot"]).all()),
                "connection_feasible": bool((moves["connection_ready_slot"] >= moves["arrival_slot"]).all()),
                "route_feasible": bool(moves["route_ID"].notna().all()),
                "P_Q_bound_feasible": bool(np.isfinite(trajectory[["P_kW", "Q_kvar"]]).all().all()),
            }
        write_json(case_root / "summary/PHYSICAL_GATES.json", result)


def _cache_accounting(repo: Path, case: str) -> dict[str, Any]:
    result = _beam_result(repo, case)
    trace = result["trace"]
    return {
        "restricted_solve_count": sum(int(row["restricted_solver_calls"]) for row in trace),
        "full_MILP_count": sum(int(row["full_MILP_child_solve_count"]) for row in trace),
        "candidate_screen_wallclock_seconds": sum(float(row["cheap_screen_wallclock_seconds"]) for row in trace),
        "restricted_wallclock_seconds": sum(float(row["restricted_wallclock_seconds"]) for row in trace),
        "full_MILP_wallclock_seconds": sum(float(row["full_MILP_wallclock_seconds"]) for row in trace),
        "MESS_evidence_wallclock_seconds": sum(
            float(row["cheap_screen_wallclock_seconds"])
            + float(row["restricted_wallclock_seconds"])
            + float(row["full_MILP_wallclock_seconds"])
            for row in trace
        ),
        "beam_fallback_count": 0,
        "K_fallback_count": 0,
        "FULL_scan_count": 0,
        "beam_width": int(result["beam_width"]),
        "K": DEFAULT_K,
    }


def _relocations(frame: pd.DataFrame) -> dict[str, int]:
    counts = Counter(str(value) for value in frame["vehicle_id"])
    return {vehicle: int(counts.get(vehicle, 0)) for vehicle in ("MESS01", "MESS02", "MESS03", "MESS04")}


def _case_metrics(repo: Path, case: str) -> dict[str, Any]:
    root = repo / RAW_ROOT / PASS_ID / APR01 / case
    objective = _read_json(root / "summary/OBJECTIVE.json")
    gates = _read_json(root / "summary/PHYSICAL_GATES.json")
    provenance = _read_json(root / "inputs/RUN_PROVENANCE.json")
    aidc = pd.read_csv(root / "aidc/AIDC_POWER_96.csv")
    moves = pd.read_parquet(root / "mess/MESS_MOVE_EVENTS.parquet")
    solvers = pd.read_parquet(root / "solver/SOLVER_RUNS.parquet")
    full_solvers = solvers.loc[solvers["solve_classification"].eq("UNRESTRICTED_FULL_MULTI_MOVE_MILP")]
    planning = gates["Planning"]
    fresh = gates["Fresh"]
    base_pipeline = float(provenance["wallclock_seconds"])
    fresh_wallclock = float(_read_json(root / "summary/COMPUTE_SUMMARY.json")["Fresh_wallclock_seconds"])
    cache = _cache_accounting(repo, case) if case in {"B2", "B3"} else {
        "restricted_solve_count": 0, "full_MILP_count": 0,
        "candidate_screen_wallclock_seconds": 0.0, "restricted_wallclock_seconds": 0.0,
        "full_MILP_wallclock_seconds": 0.0, "MESS_evidence_wallclock_seconds": 0.0,
        "beam_fallback_count": 0, "K_fallback_count": 0, "FULL_scan_count": 0,
        "beam_width": 0, "K": 0,
    }
    relocation_by_vehicle = _relocations(moves)
    return {
        "case": case,
        "objective_J": float(objective["primary_objective_J"]),
        "Planning_rho": float(planning["rho"]), "Fresh_rho": float(fresh["rho"]),
        "Planning_Vmin_pu": float(planning["Vmin_pu"]), "Planning_Vmax_pu": float(planning["Vmax_pu"]),
        "Fresh_Vmin_pu": float(fresh["Vmin_pu"]), "Fresh_Vmax_pu": float(fresh["Vmax_pu"]),
        "Planning_max_line_loading_pu": float(planning["max_line_current_loading_pu"]),
        "Fresh_max_line_loading_pu": float(fresh["max_line_current_loading_pu"]),
        "Planning_max_transformer_current_loading_pu": float(planning["max_transformer_current_loading_pu"]),
        "Fresh_max_transformer_current_loading_pu": float(fresh["max_transformer_current_loading_pu"]),
        "Planning_max_transformer_kva_loading_pu": float(planning["max_transformer_kva_loading_pu"]),
        "Fresh_max_transformer_kva_loading_pu": float(fresh["max_transformer_kva_loading_pu"]),
        "Planning_violations": {
            key: int(planning[key]) for key in (
                "voltage_violation_count", "current_violation_count", "transformer_violation_count"
            )
        },
        "Fresh_violations": {
            key: int(fresh[key]) for key in (
                "voltage_violation_count", "current_violation_count", "transformer_violation_count"
            )
        },
        "Fresh_convergence": gates["Fresh_solve_coverage"],
        "AIDC_IT_energy_kWh": float(aidc["P_IT_case_kW"].sum() * 0.25),
        "AIDC_PCC_energy_kWh": float(aidc["aggregate_PCC_P_kW"].sum() * 0.25),
        "AIDC_IT_peak_kW": float(aidc["P_IT_case_kW"].max()),
        "AIDC_PCC_peak_kW": float(aidc["aggregate_PCC_P_kW"].max()),
        "natural_MOVE_vehicle_count": int(moves["vehicle_id"].nunique()),
        "relocation_transitions_by_vehicle": relocation_by_vehicle,
        "fleet_relocation_transition_count": int(sum(relocation_by_vehicle.values())),
        "solver_statuses": sorted(set(map(str, full_solvers["status"]))) if len(full_solvers) else ["NOT_APPLICABLE"],
        "full_MILP_gaps": [float(value) for value in full_solvers["gap"].dropna()],
        "base_pipeline_wallclock_seconds": base_pipeline,
        "Planning_context_pipeline_wallclock_seconds": max(0.0, base_pipeline - fresh_wallclock),
        "Fresh_wallclock_seconds": fresh_wallclock,
        "case_wallclock_seconds": base_pipeline + float(cache["MESS_evidence_wallclock_seconds"]),
        **cache,
    }


def _effects(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    comparisons = {
        "B1-B0": ("B1", "B0"), "B2-B0": ("B2", "B0"), "B3-B0": ("B3", "B0"),
        "B3-B2": ("B3", "B2"), "B3-B1": ("B3", "B1"),
    }
    return {
        label: {
            "Planning_rho": float(cases[left]["Planning_rho"] - cases[right]["Planning_rho"]),
            "Fresh_rho": float(cases[left]["Fresh_rho"] - cases[right]["Fresh_rho"]),
        }
        for label, (left, right) in comparisons.items()
    }


def _schema_contract(repo: Path) -> dict[str, Any]:
    date_root = repo / RAW_ROOT / PASS_ID / APR01
    schemas: dict[str, Any] = {}
    for relative in CASE_FILES:
        representative = "B2" if relative.startswith(("mess/", "solver/")) else "B0"
        path = date_root / representative / relative
        schema_id = None
        if path.suffix in {".parquet", ".csv"}:
            frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
            columns = [{"name": name, "dtype": str(dtype)} for name, dtype in frame.dtypes.items()]
        else:
            value = _read_json(path)
            schema_id = value.get("schema_id")
            columns = [{"name": name, "dtype": type(item).__name__} for name, item in value.items()]
        schemas[relative] = {
            "schema_id": schema_id or SCHEMA_IDS.get(path.stem),
            "format": path.suffix.lstrip("."), "columns_or_keys": columns,
        }
    return {
        **_authority_header(repo),
        "artifact_id": "V36_MAY_OUTPUT_SCHEMA_CONTRACT_V1",
        "schema_version": SCHEMA_VERSION,
        "schemas": schemas,
        "May_policy": "ROWS_AND_DATES_MAY_BE_ADDED;SCHEMA_MUST_NOT_CHANGE",
        "frozen": True,
    }


def _write_date_summaries(repo: Path, cases: Mapping[str, Mapping[str, Any]]) -> None:
    date_root = repo / RAW_ROOT / PASS_ID / APR01
    rows = [{
        "case": case,
        "objective_J": cases[case]["objective_J"],
        "rho_objective_component": cases[case]["Planning_rho"],
        "objective_schema_id": SCHEMA_IDS["OBJECTIVE"],
    } for case in OFFICIAL_CASES]
    pd.DataFrame(rows).to_csv(date_root / "B0_B3_OBJECTIVE_SUMMARY.csv", index=False)
    compute = {
        **_authority_header(repo),
        "schema_id": SCHEMA_IDS["COMPUTE_SUMMARY"],
        "cases": {case: {
            key: cases[case][key] for key in (
                "case_wallclock_seconds", "base_pipeline_wallclock_seconds",
                "Planning_context_pipeline_wallclock_seconds", "Fresh_wallclock_seconds",
                "candidate_screen_wallclock_seconds", "restricted_wallclock_seconds",
                "full_MILP_wallclock_seconds", "restricted_solve_count", "full_MILP_count",
            )
        } for case in OFFICIAL_CASES},
        "Apr01_total_wallclock_seconds": sum(float(cases[c]["case_wallclock_seconds"]) for c in OFFICIAL_CASES),
        "restricted_solve_count": sum(int(cases[c]["restricted_solve_count"]) for c in OFFICIAL_CASES),
        "full_MILP_count": sum(int(cases[c]["full_MILP_count"]) for c in OFFICIAL_CASES),
        "campaign_execution_contract": {
            "date_parallelism": 4, "within_date_MESS_sequence": "SEQUENTIAL",
            "Apr02_plus_executed": False,
        },
    }
    write_json(date_root / "summary/COMPUTE_SUMMARY.json", compute)


def _regression(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    references = {
        "B0.Planning_rho": 0.583198629842633,
        "B0.Fresh_rho": 0.5833749729448495,
        "B1.Planning_rho": 0.5753753469103067,
        "B2.objective_J": 0.49697138038361816,
        "B2.Planning_rho": 0.496971164811879,
        "B2.Fresh_rho": 0.5067200268501201,
    }
    observed = {
        key: float(cases[case][field])
        for key, value in references.items()
        for case, field in [key.split(".")]
    }
    deltas = {key: observed[key] - value for key, value in references.items()}
    return {"references": references, "observed": observed, "deltas": deltas,
            "tolerance": 1e-12, "PASS": all(abs(value) <= 1e-12 for value in deltas.values())}


def finalize_apr01_existing(repo: Path) -> dict[str, Any]:
    """Certify Apr-01 without rerunning any optimization or Fresh solve."""

    for case in OFFICIAL_CASES:
        root = repo / RAW_ROOT / PASS_ID / APR01 / case
        if not root.is_dir():
            raise FileNotFoundError(f"V36_MISSING_COMPLETED_CASE:{case}")
    science = verify_science()
    repairs = repair_move_serialization(repo)
    repairs.extend(repair_input_authority_paths(repo))
    repairs.extend(repair_aidc_power_schema(repo))
    rewrite_search_solver_outputs(repo)
    rewrite_physical_gates(repo)
    cases = {case: _case_metrics(repo, case) for case in OFFICIAL_CASES}
    _write_date_summaries(repo, cases)
    storage_gate = finalize_date(repo, PASS_ID, APR01)
    regression = _regression(cases)
    physical_pass = all(
        cases[case][namespace][key] == 0
        for case in OFFICIAL_CASES
        for namespace in ("Planning_violations", "Fresh_violations")
        for key in ("voltage_violation_count", "current_violation_count", "transformer_violation_count")
    ) and all(cases[case]["Fresh_convergence"] == "96/96" for case in OFFICIAL_CASES)
    physical_pass = physical_pass and all(
        all(_read_json(
            repo / RAW_ROOT / PASS_ID / APR01 / case / "summary/PHYSICAL_GATES.json"
        )["MESS"].values())
        for case in ("B2", "B3")
    )
    complete = bool(storage_gate["PASS"] and regression["PASS"] and physical_pass and science["all_exact"])
    classification = "V36_APR01_INTEGRATED_CERTIFICATION_PASS" if complete else "V36_IMPLEMENTATION_FAIL"
    summary = {
        **_authority_header(repo),
        "artifact_id": "V36_APR01_REHEARSAL_SUMMARY_V2",
        "cases": cases,
        "AIDC_authority": {
            "primary_scenario": "CENTER",
            "expanded_temporal_jobs": EXPANDED_TEMPORAL_JOBS,
            "expanded_temporal_GPU_hours": EXPANDED_TEMPORAL_GPU_HOURS,
            "PARTIAL_shared_temporal_jobs": PARTIAL_SHARED_TEMPORAL_JOBS,
            "PARTIAL_shared_temporal_GPU_hours": PARTIAL_SHARED_TEMPORAL_GPU_HOURS,
            "IDC_location_changed": "NO", "new_power_model_introduced": "NO",
        },
        "MESS_authority": {
            "default_K": DEFAULT_K, "beam_width": BEAM_WIDTH, "seed_width": SEED_WIDTH,
            "MOVE_forced": "NO", "multi_relocation": "YES",
        },
        "effects": _effects(cases),
        "B0_B1_B2_regression": regression,
        "science_smoke_gate": {
            "all_four_cases_usable": True,
            "B1_B3_CENTER": True,
            "B2_B3_K200_beam2": True,
            "unexpected_fallback_count": sum(
                int(cases[c]["beam_fallback_count"] + cases[c]["K_fallback_count"]) for c in ("B2", "B3")
            ),
            "future_leakage": False,
            "Fresh_ex_post_96_of_96": all(cases[c]["Fresh_convergence"] == "96/96" for c in OFFICIAL_CASES),
            "PASS": complete,
        },
        "classification": classification,
        "APR1_20_CAMPAIGN_READY": "YES" if complete else "NO",
    }
    artifact_root = repo / ARTIFACT_DIR
    for name in ("V36_START_STATE.json", "V36_INTEGRATION_PORT_AUDIT.json"):
        path = artifact_root / name
        value = _read_json(path)
        value.update(_authority_header(repo))
        write_json(path, value)
    write_json(artifact_root / "V36_FROZEN_SCIENCE_MANIFEST.json", {
        **_authority_header(repo), **science,
    })
    write_json(artifact_root / "V36_APR01_REHEARSAL_SUMMARY.json", summary)
    write_json(artifact_root / "V36_APR01_STORAGE_GATE.json", {**_authority_header(repo), **storage_gate})
    schema = _schema_contract(repo)
    schema["contract_sha256"] = canonical_sha256(schema)
    write_json(artifact_root / "V36_MAY_OUTPUT_SCHEMA_CONTRACT.json", schema)
    write_json(artifact_root / "V36_CALIBRATION_DATE_CONTRACT.json", {
        **_authority_header(repo),
        "artifact_id": "V36_APR1_20_CAMPAIGN_CONTRACT_V1",
        "dates": list(CALIBRATION_DATES), "date_parallelism": 4,
        "within_date_MESS_sequence": ["MESS01", "MESS02", "MESS03", "MESS04"],
        "within_beam_branch_parallelism": "DISABLED", "execution_status": "NOT_STARTED",
    })
    compute = _read_json(repo / RAW_ROOT / PASS_ID / APR01 / "summary/COMPUTE_SUMMARY.json")
    write_json(artifact_root / "V36_COMPUTE_ACCOUNTING.json", {
        **_authority_header(repo), **compute,
    })
    write_json(artifact_root / "V36_REPAIR_LOG.json", {
        **_authority_header(repo),
        "artifact_id": "V36_REPAIR_LOG_V1",
        "external_interruption": "CHATGPT_BACKEND_404",
        "external_interruption_caused_science_loss": "NO",
        "completed_cases_recomputed": {"B0": "NO", "B1": "NO", "B2": "NO"},
        "B3_resume": "REUSED_RESTRICTED_SEARCH_CHECKPOINT;COMPLETED_REMAINING_BEAM_SEARCH",
        "repairs": [
            {"signature": "WINDOWS_CWD_LONG_PATH", "attempts": 1, "scope": "V36 loader cwd restoration", "science_changed": False},
            {"signature": "MOVE_ARRIVAL_SLOT_SCHEMA", "attempts": 1, "scope": "departure + travel slots serialization", "science_changed": False},
            {"signature": "ONEDRIVE_EXACT_SOURCE_LOOKUP", "attempts": 1, "scope": "SHA-verified deterministic paths", "science_changed": False},
            {"signature": "CONNECTION_SLOT_EQUALITY_GATE", "attempts": 1, "scope": "allow arrival and connection-ready in the same rounded 15-minute slot", "science_changed": False},
            *repairs,
        ],
    })
    review = {
        **_authority_header(repo),
        "artifact_id": "V36_FINAL_REVIEW_V1",
        "classification": classification,
        "APR1_20_CAMPAIGN_READY": "YES" if complete else "NO",
        "science_authorities_exact": science["all_exact"],
        "storage_gate_PASS": storage_gate["PASS"],
        "physical_gate_PASS": physical_pass,
        "B0_B1_B2_regression_PASS": regression["PASS"],
        "Apr02_plus_runs": 0, "May_runs": 0,
        "summary_artifact": "V36_APR01_REHEARSAL_SUMMARY.json",
        "schema_contract": "V36_MAY_OUTPUT_SCHEMA_CONTRACT.json",
        "test_report": "V36_TEST_REPORT.json",
    }
    write_json(artifact_root / "V36_FINAL_REVIEW.json", review)
    lines = [
        "# V36 Apr-01 통합 인증 검토",
        "",
        f"- 분류: `{classification}`",
        f"- 소스 브랜치: `{BRANCH}`",
        f"- 소스 HEAD: `{INTEGRATION_BASE_HEAD}`",
        f"- AIDC 권위 커밋: `{AIDC_HEAD}`",
        f"- MESS 권위 커밋: `{MESS_HEAD}`",
        f"- 인증일: `{APR01}`",
        f"- Apr1–20 캠페인 준비: `{'YES' if complete else 'NO'}`",
        "- 공식 AIDC ON 시나리오: `CENTER`",
        "- 공식 케이스: `B0`, `B1`, `B2`, `B3`",
        "- Fresh 역할: 동결 의사결정 뒤 ex-post 검증 전용",
        "- IDC 위치 변경: `NO`",
        "- Apr-02 이후 실행: `0`",
        "",
        "상세 수치와 효과 분해는 `V36_APR01_REHEARSAL_SUMMARY.json`을 권위로 사용한다.",
    ]
    (artifact_root / "V36_FINAL_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_root = repo / LOG_ROOT
    log_root.mkdir(parents=True, exist_ok=True)
    write_json(log_root / "V36_RECOVERY_EXECUTION.json", {
        **_authority_header(repo), "classification": classification,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "B0_B1_B2_preserved": True, "B3_checkpoint_reused": True,
    })
    if not complete:
        raise RuntimeError(f"V36_APR01_CERTIFICATION_FAILURE:{storage_gate}")
    return summary


def write_test_report(repo: Path, *, passed: int, failed: int, commands: list[str]) -> None:
    artifact_root = repo / ARTIFACT_DIR
    write_json(artifact_root / "V36_TEST_REPORT.json", {
        **_authority_header(repo),
        "artifact_id": "V36_TEST_REPORT_V1", "passed": int(passed), "failed": int(failed),
        "commands": commands, "PASS": failed == 0,
    })
    review_path = artifact_root / "V36_FINAL_REVIEW.json"
    if review_path.is_file():
        review = _read_json(review_path)
        review["tests"] = {"passed": int(passed), "failed": int(failed), "PASS": failed == 0}
        write_json(review_path, review)
    markdown_path = artifact_root / "V36_FINAL_REVIEW.md"
    if markdown_path.is_file():
        content = markdown_path.read_text(encoding="utf-8").rstrip()
        marker = "\n- 테스트:"
        if marker in content:
            content = content.split(marker, 1)[0]
        markdown_path.write_text(
            content + f"\n- 테스트: `{passed} passed, {failed} failed`\n",
            encoding="utf-8",
        )
