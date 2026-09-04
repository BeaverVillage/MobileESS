"""April-only V16 C7/C8/C9 pre-production integration gate.

This module deliberately runs in a ``NON_SCIENTIFIC`` namespace.  It joins
the already-frozen contracts and authority files without opening a May/June
loader or creating campaign outputs.  Its reduced feeder is an engineering
fixture anchored to the frozen PCC buses and present-phase mask; it is not a
replacement for the full IEEE123 G13/G14 scientific solve.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_reference_delta import facility_power_and_reactive, map_system_reference, planning_residual
from .aidc_service_contract import require_terminal_reference_parity
from .authority import CURRENT_FROZEN_DIMENSIONS, sha256_file
from .benders import BendersMethod, CutRegistry, cuts_for_iteration, evaluate_all_96
from .grid_lp import (
    LINE_POLYGON_FACES,
    V_MAX_SQUARED,
    V_MIN_SQUARED,
    BranchPhase,
    FeasibilityCut,
    FeederLPData,
    OptimalityCut,
    PhaseAwareGridLPFactory,
)
from .input_contract import pwc_30_to_15
from .mess_physics import MessSlot, MobilityMode, validate_trajectory
from .mobility_energy_da import MobilityEnergyProfiles, assert_departure_feasible
from .reference_compute import ReferenceComputeSchedule, build_reference_schedule


NAMESPACE = "NON_SCIENTIFIC_APRIL_VALIDATION_ENGINEERING_FIXTURE_V1"
OPERATING_DAY = "2025-04-15"
PROPOSED_MODEL = "Proposed AIDC RC-MQT"
# The non-scientific fixture caps each logical rack below the minimum April
# Q90 GPU envelope (0.09 node-h / 0.25 h * 4 = 1.44 active GPUs).  This is a
# declared engineering capacity, not a fitted spatial weight.
RACK_CAPACITY_NODEH_PER_SLOT = 0.09
MAY_JUNE_LOADER_ACCESS_COUNT = 0


@dataclass(frozen=True)
class FrozenSourcePaths:
    service_mapping: Path
    phase_mask: Path
    bus_contract: Path


@dataclass(frozen=True)
class IntegratedFixture:
    forecast: Mapping[str, object]
    reference: ReferenceComputeSchedule
    reference_payload: Mapping[str, object]
    p_residual: tuple[tuple[float, ...], ...]
    g_residual: tuple[tuple[float, ...], ...]
    fixed_master: Mapping[str, float]
    factories: tuple[PhaseAwareGridLPFactory, ...]
    integration_evidence: Mapping[str, object]


def _canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest_payload(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _read_mapping_authority(path: Path) -> tuple[Mapping[str, object], FrozenSourcePaths]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS" or payload.get("new_mapping_created") is not False:
        raise RuntimeError("BLOCKED_FROZEN_MAPPING_SOURCE_NOT_FOUND")
    sources = payload["sources"]
    service = Path(sources["service_node_electrical_mapping_v1_csv_sha256"]["path"])
    mask = Path(sources["compiled_bus_phase_mask_sha256"]["path"])
    bus_contract = Path(sources["power_bus_axis_sha256"]["contract_path"])
    if sha256_file(service) != sources["service_node_electrical_mapping_v1_csv_sha256"]["sha256"]:
        raise RuntimeError("BLOCKED_FROZEN_MAPPING_SOURCE_NOT_FOUND")
    if sha256_file(mask) != sources["compiled_bus_phase_mask_sha256"]["file_sha256"]:
        raise RuntimeError("BLOCKED_FROZEN_MAPPING_SOURCE_NOT_FOUND")
    return payload, FrozenSourcePaths(service, mask, bus_contract)


def load_april_validation_forecast(path: Path, operating_day: str = OPERATING_DAY) -> Mapping[str, object]:
    """Read only the pre-materialized April validation namespace.

    No raw-label or scientific campaign loader is imported or called here.
    """

    import pandas as pd

    frame = pd.read_parquet(path)
    if set(frame["namespace"].unique()) != {"APRIL_VALIDATION_ONLY"}:
        raise ValueError("C7_REQUIRES_APRIL_VALIDATION_ONLY_NAMESPACE")
    dates = pd.to_datetime(frame["forecast_day"])
    if dates.min().date().isoformat() < "2025-04-01" or dates.max().date().isoformat() > "2025-04-30":
        raise ValueError("MAY_JUNE_FORECAST_ROW_PROHIBITED")
    selected = frame[(frame["model"] == PROPOSED_MODEL) & (frame["forecast_day"] == operating_day)]
    expected_targets = {"P_IT_REF", "G_REF"} | {f"W_F::{cohort}" for cohort in _cohort_ids()}
    if set(selected["target"].unique()) != expected_targets:
        raise ValueError("APRIL_PROPOSED_TARGET_AXIS_MISMATCH")
    if set(float(value) for value in selected["quantile"].unique()) != {0.1, 0.5, 0.9}:
        raise ValueError("APRIL_PROPOSED_QUANTILE_AXIS_MISMATCH")

    def trajectory(target: str, quantile: float) -> tuple[float, ...]:
        rows = selected[(selected["target"] == target) & (selected["quantile"] == quantile)].sort_values("slot")
        if tuple(int(value) for value in rows["slot"]) != tuple(range(96)):
            raise ValueError("DIRECT96_SLOT_AXIS_MISMATCH")
        values = tuple(float(value) for value in rows["prediction"])
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("APRIL_FORECAST_MUST_BE_FINITE_NONNEGATIVE")
        return values

    return {
        "operating_day": operating_day,
        "p_q50": trajectory("P_IT_REF", 0.5),
        "p_q90": trajectory("P_IT_REF", 0.9),
        "g_q90": trajectory("G_REF", 0.9),
        "cohort_q50": {cohort: trajectory(f"W_F::{cohort}", 0.5) for cohort in _cohort_ids()},
        "source_sha256": sha256_file(path),
        "row_count_read": int(len(frame)),
        "may_june_loader_access_count": MAY_JUNE_LOADER_ACCESS_COUNT,
    }


def _cohort_ids() -> tuple[str, ...]:
    return tuple(f"N{nodes:02d}_R{runtime:02d}" for nodes in (1, 2, 4, 8, 16) for runtime in range(3))


def _node_class(cohort: str) -> int:
    return int(cohort[1:3])


def _build_reference(forecast: Mapping[str, object]) -> ReferenceComputeSchedule:
    capacities = {rack: RACK_CAPACITY_NODEH_PER_SLOT for rack in CURRENT_FROZEN_DIMENSIONS.rack_ids}
    reference = build_reference_schedule(
        CURRENT_FROZEN_DIMENSIONS,
        None,
        production=True,
        cohort_arrivals=forecast["cohort_q50"],
        rack_capacity_nodeh_per_slot=capacities,
    )
    if reference.authority_id != "REFERENCE_COMPUTE_SCHEDULE_V2":
        raise ValueError("REFERENCE_COMPUTE_SCHEDULE_V2_REQUIRED")
    return reference


def reference_schedule_payload(reference: ReferenceComputeSchedule) -> Mapping[str, object]:
    return {
        "authority_id": reference.authority_id,
        "namespace": NAMESPACE,
        "operating_day": OPERATING_DAY,
        "initial_backlog_by_cohort": {cohort: 0.0 for cohort in _cohort_ids()},
        "policy": "FORECAST_COHORT_Q50_GRID_MESS_BLIND_EARLIEST_FEASIBLE_FLUID",
        "rack_capacity_nodeh_per_slot": RACK_CAPACITY_NODEH_PER_SLOT,
        "terminal_backlog_by_cohort": {
            key: float(value) for key, value in sorted((reference.backlog_terminal_by_cohort or {}).items())
        },
        "workload_by_rack_slot": [
            [rack, slot, float(reference.workload_by_rack_slot[(rack, slot)])]
            for rack in CURRENT_FROZEN_DIMENSIONS.rack_ids
            for slot in range(96)
        ],
        "scientific_eligible": False,
    }


def _reference_delta(
    forecast: Mapping[str, object], reference: ReferenceComputeSchedule
) -> tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...], Mapping[str, object]]:
    if reference.workload_by_cohort_rack_slot is None:
        raise ValueError("COHORT_RACK_REFERENCE_ALLOCATION_REQUIRED")
    racks = CURRENT_FROZEN_DIMENSIONS.rack_ids
    weights = (1.0 / len(racks),) * len(racks)
    mapped_p = map_system_reference(forecast["p_q90"], weights)
    mapped_g = map_system_reference(forecast["g_q90"], weights)
    flexible_p: list[tuple[float, ...]] = []
    flexible_g: list[tuple[float, ...]] = []
    for slot in range(96):
        p_row: list[float] = []
        g_row: list[float] = []
        for rack in racks:
            power = 0.0
            gpu = 0.0
            for cohort in _cohort_ids():
                work = float(reference.workload_by_cohort_rack_slot[(cohort, rack, slot)])
                active_nodes = work / 0.25
                power += KAPPA_KW_PER_ACTIVE_H100_NODE[_node_class(cohort)] * active_nodes
                gpu += 4.0 * active_nodes
            p_row.append(power)
            g_row.append(gpu)
        flexible_p.append(tuple(p_row))
        flexible_g.append(tuple(g_row))
    p_residual = planning_residual(mapped_p, flexible_p)
    g_residual = planning_residual(mapped_g, flexible_g)
    all_p = [value for row in p_residual for value in row]
    all_g = [value for row in g_residual for value in row]
    return p_residual, g_residual, {
        "power_kw": {"min": min(all_p), "max": max(all_p)},
        "gpu": {"min": min(all_g), "max": max(all_g)},
        "spatial_weights": "NON_FITTED_UNIFORM_OVER_FROZEN_48_LOGICAL_RACK_AXIS",
        "mapping_fitting_call_count": 0,
    }


def _service_parity(reference: ReferenceComputeSchedule, forecast: Mapping[str, object]) -> Mapping[str, object]:
    if reference.workload_by_cohort_rack_slot is None:
        raise ValueError("COHORT_RACK_REFERENCE_ALLOCATION_REQUIRED")
    terminal_residuals = {}
    for cohort in _cohort_ids():
        processed = tuple(
            sum(reference.workload_by_cohort_rack_slot[(cohort, rack, slot)] for rack in CURRENT_FROZEN_DIMENSIONS.rack_ids)
            for slot in range(96)
        )
        da, ref = require_terminal_reference_parity(forecast["cohort_q50"][cohort], processed, processed)
        terminal_residuals[cohort] = float(da[-1] - ref[-1])
    return {
        "contract": "B_b,97^DA=B_b,97^REF",
        "max_abs_terminal_residual_nodeh": max(abs(value) for value in terminal_residuals.values()),
        "terminal_residual_by_cohort": terminal_residuals,
    }


def _mess_plan() -> tuple[Mapping[str, float], Mapping[str, object]]:
    fixed_master: dict[str, float] = {}
    evidence: dict[str, object] = {}
    for mess_index in range(4):
        transit_start = 32 + 8 * mess_index
        charge_start = transit_start - 8
        raw_safe = [0.0] * 288
        for slot in range(transit_start, transit_start + 4):
            for five_minute in range(3 * slot, 3 * slot + 3):
                raw_safe[five_minute] = 10.0 / 12.0
        profiles = MobilityEnergyProfiles(
            tuple(raw_safe), tuple(0.8 * value for value in raw_safe), NAMESPACE, "ENGINEERING_ROUTE_V1", ()
        )
        safe_15, _q50_15, aggregation = profiles.aggregate()
        assert len(safe_15) == 96 and abs(sum(safe_15) - 10.0) <= 1e-9
        assert_departure_feasible(760.0, 440.0, safe_15)
        slots: list[MessSlot] = []
        for slot in range(96):
            mode = MobilityMode.TRANSIT if transit_start <= slot < transit_start + 4 else MobilityMode.CONNECTED
            p_ch = 5.0 if charge_start <= slot < charge_start + 8 else 0.0
            slots.append(MessSlot(f"STA{mess_index + 1:02d}", mode, 0.0, p_ch, 0.0))
            fixed_master[f"mess{mess_index + 1:02d}_p_t{slot:02d}"] = -p_ch
        energy = validate_trajectory(slots, mobility_energy_kwh=safe_15)
        evidence[f"MESS{mess_index + 1:02d}"] = {
            "service_site": f"STA{mess_index + 1:02d}",
            "transit_slots": list(range(transit_start, transit_start + 4)),
            "safe_mobility_energy_kwh": sum(safe_15),
            "soc_energy_kwh_min": min(energy),
            "soc_energy_kwh_max": max(energy),
            "terminal_energy_kwh": energy[-1],
            "p_kw_min": min(slot.p_kw for slot in slots),
            "p_kw_max": max(slot.p_kw for slot in slots),
            "q_kvar_min": min(slot.q_kvar for slot in slots),
            "q_kvar_max": max(slot.q_kvar for slot in slots),
            "mobility_aggregation": aggregation["aggregation"],
        }
    return fixed_master, evidence


def _mapping_rows(path: Path) -> tuple[dict[str, str], ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return tuple(dict(row) for row in csv.DictReader(stream))


def _phase_map(paths: FrozenSourcePaths) -> Mapping[str, tuple[str, ...]]:
    import numpy as np

    contract = json.loads(paths.bus_contract.read_text(encoding="utf-8"))
    # The frozen array is stored on the 131-row power injection axis (the
    # compiled-only bus 610 is intentionally excluded by the authority).
    bus_ids = [str(value) for value in contract["power_bus_ids"]]
    mask = np.load(paths.phase_mask, allow_pickle=False)
    if mask.shape != (len(bus_ids), 3):
        raise ValueError("FROZEN_PHASE_MASK_SHAPE_MISMATCH")
    phases = ("A", "B", "C")
    return {bus: tuple(phases[index] for index in range(3) if bool(mask[row, index])) for row, bus in enumerate(bus_ids)}


def _build_grid_factories(
    forecast: Mapping[str, object], paths: FrozenSourcePaths, fixed_master: Mapping[str, float]
) -> tuple[tuple[PhaseAwareGridLPFactory, ...], Mapping[str, object]]:
    rows = _mapping_rows(paths.service_mapping)
    idc = sorted((row for row in rows if row["asset_type"] == "IDC"), key=lambda row: row["service_node_id"])
    sta = sorted((row for row in rows if row["asset_type"] == "STA"), key=lambda row: row["service_node_id"])
    if len(idc) != 12 or len(sta) < 4:
        raise ValueError("FROZEN_PCC_MAPPING_AXIS_MISMATCH")
    phases_by_bus = _phase_map(paths)
    root = "150"
    if not phases_by_bus.get(root):
        raise ValueError("FROZEN_ROOT_PHASE_MASK_MISSING")
    used = idc + sta[:4]
    aidc_bus = {f"AIDC{index + 1:02d}": row["electrical_host_bus"] for index, row in enumerate(idc)}
    mess_bus = {f"MESS{index + 1:02d}": row["electrical_host_bus"] for index, row in enumerate(sta[:4])}
    factories: list[PhaseAwareGridLPFactory] = []
    for slot in range(96):
        branches: list[BranchPhase] = []
        bus_present: dict[tuple[str, str], bool] = {(root, phase): True for phase in phases_by_bus[root]}
        line_present: dict[tuple[str, str], bool] = {}
        base_p: dict[tuple[str, str], float] = {}
        base_q: dict[tuple[str, str], float] = {}
        limits: dict[tuple[str, str], float] = {}
        transformers: dict[tuple[str, str], float] = {}
        master_p: dict[tuple[str, str], dict[str, float]] = {}
        master_q: dict[tuple[str, str], dict[str, float]] = {}
        for row in used:
            bus = row["electrical_host_bus"]
            phases = tuple(phase for phase in phases_by_bus.get(bus, ()) if phase in phases_by_bus[root])
            if not phases:
                raise ValueError(f"FROZEN_PCC_BUS_HAS_NO_PRESENT_PHASE:{bus}")
            service = row["service_node_id"]
            per_phase_limit = float(row["idc_transformer_kva"] or row["mess_transformer_kva"]) / len(phases)
            if row["asset_type"] == "IDC":
                system_p = float(forecast["p_q90"][slot]) / 12.0
                facility_p, facility_q = facility_power_and_reactive(system_p)
            else:
                facility_p, facility_q = 10.0, 10.0 * math.tan(math.acos(float(row["power_factor"])))
            for phase in phases:
                branch_id = f"ENG_{service}"
                branch = BranchPhase(branch_id, root, bus, phase, 1e-5, 1e-5, per_phase_limit)
                branches.append(branch)
                bus_present[(bus, phase)] = True
                line_present[(branch_id, phase)] = True
                base_p[(bus, phase)] = facility_p / len(phases)
                base_q[(bus, phase)] = facility_q / len(phases)
                limits[(branch_id, phase)] = per_phase_limit
                transformers[(branch_id, phase)] = per_phase_limit
                if row["asset_type"] == "STA" and service in {"STA01", "STA02", "STA03", "STA04"}:
                    mess_index = int(service[-2:])
                    key = f"mess{mess_index:02d}_p_t{slot:02d}"
                    master_p[(bus, phase)] = {key: 1.0 / len(phases)}
                    master_q[(bus, phase)] = {}
        data = FeederLPData(
            root,
            tuple(branches),
            bus_present,
            line_present,
            base_p,
            base_q,
            limits,
            transformers,
            master_p,
            master_q,
        )
        factories.append(PhaseAwareGridLPFactory(data))
    return tuple(factories), {
        "feeder_fixture": "NON_SCIENTIFIC_REDUCED_STAR_ENGINEERING_FIXTURE_ANCHORED_TO_FROZEN_PCC_BUSES",
        "aidc_pcc_source_ids": {aidc: idc[index]["service_node_id"] for index, aidc in enumerate(aidc_bus)},
        "aidc_pcc_host_buses": aidc_bus,
        "mess_pcc_host_buses": mess_bus,
        "frozen_phase_mask_applied": True,
        "frozen_phase_mask_path": str(paths.phase_mask),
        "present_branch_phase_count": len(factories[0].data.branches),
        "master_dependent_row_registry_count_per_time": len(factories[0].master_dependent_row_registry),
        "master_variable_count": len(fixed_master),
    }


def build_integrated_fixture(
    *, forecast_path: Path, mapping_authority_path: Path, production_config_path: Path, production_weights_path: Path
) -> IntegratedFixture:
    mapping_authority, source_paths = _read_mapping_authority(mapping_authority_path)
    config = json.loads(production_config_path.read_text(encoding="utf-8"))
    if config.get("model") != PROPOSED_MODEL or config.get("refit_count") != 1 or config.get("seed") != 20260828:
        raise ValueError("PRODUCTION_RC_MQT_INTERFACE_NOT_FROZEN")
    forecast = load_april_validation_forecast(forecast_path)
    reference = _build_reference(forecast)
    payload = reference_schedule_payload(reference)
    p_residual, g_residual, residual_evidence = _reference_delta(forecast, reference)
    parity = _service_parity(reference, forecast)
    fixed_master, mess_evidence = _mess_plan()
    factories, grid_evidence = _build_grid_factories(forecast, source_paths, fixed_master)
    half_hour = tuple(
        (float(forecast["p_q90"][2 * index]) + float(forecast["p_q90"][2 * index + 1])) / 2.0
        for index in range(48)
    )
    aemo_15 = pwc_30_to_15(half_hour)
    return IntegratedFixture(
        forecast,
        reference,
        payload,
        p_residual,
        g_residual,
        fixed_master,
        factories,
        {
            "namespace": NAMESPACE,
            "scientific_eligible": False,
            "operating_day": OPERATING_DAY,
            "may_june_loader_access_count": MAY_JUNE_LOADER_ACCESS_COUNT,
            "production_rc_mqt_interface": {
                "config_sha256": sha256_file(production_config_path),
                "weights_sha256": sha256_file(production_weights_path),
                "model": config["model"],
                "seed": config["seed"],
                "refit_count": config["refit_count"],
                "forecast_role": "APRIL_VALIDATION_ONLY_SELECTED_MODEL_INTERFACE_NO_PRODUCTION_CAMPAIGN_INFERENCE",
            },
            "mapping_authority_sha256": sha256_file(mapping_authority_path),
            "mapping_authority_status": mapping_authority["status"],
            "aemo_mapping": {
                "authority": "FROZEN_AEMO_30_TO_15_PIECEWISE_CONSTANT_V1",
                "input_slots": len(half_hour),
                "output_slots": len(aemo_15),
            },
            "logical_rack_mapping": {
                "authority_id": CURRENT_FROZEN_DIMENSIONS.authority_id,
                "aidc_count": len(CURRENT_FROZEN_DIMENSIONS.aidc_ids),
                "rack_count": len(CURRENT_FROZEN_DIMENSIONS.rack_ids),
            },
            "reference_delta": residual_evidence,
            "service_parity": parity,
            "mess": mess_evidence,
            "grid": grid_evidence,
        },
    )


def solve_monolithic(fixture: IntegratedFixture) -> Mapping[str, object]:
    """Solve the identical 96-block planning LP as one Gurobi model."""

    import gurobipy as gp
    from gurobipy import GRB

    started = time.perf_counter()
    model = gp.Model("v16_c7_monolithic_non_scientific")
    model.Params.OutputFlag = 0
    master_vars = {
        key: model.addVar(lb=float(value), ub=float(value), name=key)
        for key, value in fixture.fixed_master.items()
    }
    eta = model.addVar(lb=0.0, name="rho_day_max")
    variable_count = len(master_vars) + 1
    constraint_count = 0
    for slot, factory in enumerate(fixture.factories):
        data = factory.data
        branches = tuple(data.branches)
        p = {(b.branch_id, b.phase): model.addVar(lb=-GRB.INFINITY, name=f"P[{slot},{b.branch_id},{b.phase}]") for b in branches}
        q = {(b.branch_id, b.phase): model.addVar(lb=-GRB.INFINITY, name=f"Q[{slot},{b.branch_id},{b.phase}]") for b in branches}
        v = {
            key: model.addVar(lb=V_MIN_SQUARED, ub=V_MAX_SQUARED, name=f"v[{slot},{key[0]},{key[1]}]")
            for key, present in data.bus_phase_present.items() if present
        }
        rho = model.addVar(lb=0.0, name=f"rho[{slot}]")
        variable_count += 2 * len(branches) + len(v) + 1
        for (bus, phase), var in v.items():
            if bus == data.root_bus:
                model.addConstr(var == 1.0)
                constraint_count += 1
        incoming: dict[tuple[str, str], list[BranchPhase]] = {}
        outgoing: dict[tuple[str, str], list[BranchPhase]] = {}
        for branch in branches:
            bkey = (branch.branch_id, branch.phase)
            incoming.setdefault((branch.child_bus, branch.phase), []).append(branch)
            outgoing.setdefault((branch.parent_bus, branch.phase), []).append(branch)
            model.addConstr(
                v[(branch.child_bus, branch.phase)]
                == v[(branch.parent_bus, branch.phase)]
                - 2.0 * (branch.r_pu_per_kw * p[bkey] + branch.x_pu_per_kvar * q[bkey])
            )
            limit = float(data.line_limit_kva_u080[bkey])
            apothem = limit * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                c = math.cos(2 * math.pi * face / LINE_POLYGON_FACES)
                s = math.sin(2 * math.pi * face / LINE_POLYGON_FACES)
                expression = c * p[bkey] + s * q[bkey]
                model.addConstr(expression <= apothem)
                model.addConstr(expression <= rho * apothem)
                constraint_count += 2
            tx_limit = data.transformer_limit_kva.get(bkey)
            if tx_limit is not None:
                tx_apothem = float(tx_limit) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    c = math.cos(2 * math.pi * face / LINE_POLYGON_FACES)
                    s = math.sin(2 * math.pi * face / LINE_POLYGON_FACES)
                    model.addConstr(c * p[bkey] + s * q[bkey] <= tx_apothem)
                    constraint_count += 1
            constraint_count += 1
        for (bus, phase), present in data.bus_phase_present.items():
            if not present or bus == data.root_bus:
                continue
            in_branch = incoming[(bus, phase)][0]
            p_rhs = float(data.base_load_p_kw.get((bus, phase), 0.0)) + gp.quicksum(
                -float(value) * master_vars[key]
                for key, value in data.master_p_injection.get((bus, phase), {}).items()
            )
            q_rhs = float(data.base_load_q_kvar.get((bus, phase), 0.0)) + gp.quicksum(
                -float(value) * master_vars[key]
                for key, value in data.master_q_injection.get((bus, phase), {}).items()
            )
            model.addConstr(p[(in_branch.branch_id, phase)] - gp.quicksum(p[(b.branch_id, phase)] for b in outgoing.get((bus, phase), ())) == p_rhs)
            model.addConstr(q[(in_branch.branch_id, phase)] - gp.quicksum(q[(b.branch_id, phase)] for b in outgoing.get((bus, phase), ())) == q_rhs)
            constraint_count += 2
        model.addConstr(eta >= rho)
        constraint_count += 1
    model.setObjective(eta, GRB.MINIMIZE)
    model.optimize()
    runtime = time.perf_counter() - started
    status = "OPTIMAL" if model.Status == GRB.OPTIMAL else f"GUROBI_STATUS_{model.Status}"
    return {
        "status": status,
        "hard_feasible": model.Status == GRB.OPTIMAL,
        "objective": float(model.ObjVal) if model.Status == GRB.OPTIMAL else None,
        "obj_bound": float(model.ObjBound) if model.SolCount else None,
        "runtime_seconds": runtime,
        "variable_count": variable_count,
        "constraint_count": constraint_count,
        "solve_order": "MONOLITHIC_FIRST",
    }


def _materialize_cut(item: object) -> OptimalityCut | FeasibilityCut:
    return OptimalityCut(**item.payload) if item.cut_type == "OPTIMALITY" else FeasibilityCut(**item.payload)


def _solve_master(fixed: Mapping[str, float], cuts: Sequence[OptimalityCut | FeasibilityCut]) -> tuple[Mapping[str, float], float, float]:
    import gurobipy as gp
    from gurobipy import GRB

    model = gp.Model("v16_c9_bd_master")
    model.Params.OutputFlag = 0
    variables = {key: model.addVar(lb=float(value), ub=float(value), name=key) for key, value in fixed.items()}
    eta = model.addVar(lb=0.0, name="rho_day_max")
    for index, cut in enumerate(cuts):
        expression = gp.quicksum(float(value) * variables[key] for key, value in cut.coefficients.items())
        if isinstance(cut, OptimalityCut):
            model.addConstr(eta >= float(cut.intercept) + expression, name=f"opt_{index}")
        else:
            model.addConstr(expression <= float(cut.rhs), name=f"feas_{index}")
    model.setObjective(eta, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError("C9_MASTER_NOT_OPTIMAL")
    return {key: float(var.X) for key, var in variables.items()}, float(model.ObjVal), float(model.ObjBound)


def solve_benders(fixture: IntegratedFixture, method: BendersMethod, max_iterations: int = 20) -> Mapping[str, object]:
    started = time.perf_counter()
    registry = CutRegistry()
    lower_bound = -math.inf
    upper_bound = math.inf
    last_solutions = ()
    for iteration in range(1, max_iterations + 1):
        cuts = tuple(_materialize_cut(item) for item in registry.cuts)
        master, master_incumbent, obj_bound = _solve_master(fixture.fixed_master, cuts)
        lower_bound = max(lower_bound, obj_bound)
        last_solutions = evaluate_all_96(fixture.factories, master, iteration)
        all_feasible = all(solution.feasible for solution in last_solutions)
        if all_feasible:
            upper_bound = min(upper_bound, max(float(solution.objective) for solution in last_solutions))
        selected = cuts_for_iteration(method, last_solutions)
        for cut in selected:
            registry.add(cut)
        gap = (
            max(0.0, (upper_bound - lower_bound) / max(abs(upper_bound), 1e-6))
            if math.isfinite(upper_bound) and math.isfinite(lower_bound)
            else math.inf
        )
        if gap <= 1e-3:
            break
    registered = registry.cuts
    return {
        "method": method.value,
        "status": "OPTIMAL_CERTIFIED" if gap <= 1e-3 else "ITERATION_LIMIT_NOT_CERTIFIED",
        "hard_feasible": bool(last_solutions) and all(solution.feasible for solution in last_solutions),
        "objective": upper_bound if math.isfinite(upper_bound) else None,
        "runtime_seconds": time.perf_counter() - started,
        "iterations": iteration,
        "cut_count": len(registered),
        "optimality_cut_count": sum(item.cut_type == "OPTIMALITY" for item in registered),
        "feasibility_cut_count": sum(item.cut_type == "FEASIBILITY" for item in registered),
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "gap": gap,
        "last_master_incumbent_objective": master_incumbent,
        "lb_source": "GUROBI_OBJBOUND_MONOTONE_MAXIMUM",
        "ub_update_rule": "ONLY_WHEN_ALL_96_GRID_LPS_FEASIBLE",
    }


def validate_grid_duals(fixture: IntegratedFixture) -> Mapping[str, object]:
    baseline = dict(fixture.fixed_master)
    slot = 0
    factory = fixture.factories[slot]
    solution = factory.solve(slot, baseline, 1)
    if not solution.feasible or solution.optimality_cut is None or not solution.pi_by_row:
        raise RuntimeError("C8_PI_EXTRACTION_FAILED")
    active_key = next(iter(solution.optimality_cut.coefficients))
    samples = []
    for delta in (-1.0, 0.5, 1.0):
        perturbed = dict(baseline)
        perturbed[active_key] += delta
        exact = factory.solve(slot, perturbed, 1)
        valid = exact.feasible and solution.optimality_cut.evaluate(perturbed) <= float(exact.objective) + 1e-8
        samples.append({"delta": delta, "valid": valid})
    infeasible = dict(baseline)
    infeasible[active_key] = -5000.0
    failed = factory.solve(slot, infeasible, 2)
    if failed.feasible or failed.feasibility_cut is None or not failed.farkas_by_row:
        raise RuntimeError("C8_FARKAS_EXTRACTION_FAILED")
    excluded = not failed.feasibility_cut.satisfied(infeasible)
    baseline_admitted = failed.feasibility_cut.satisfied(baseline)
    return {
        "time_local_lp_count": len(fixture.factories),
        "master_dependent_row_registry": "MASTER_DEPENDENT_ROW_REGISTRY",
        "registry_rows_per_time": len(factory.master_dependent_row_registry),
        "pi_nonzero_count": sum(abs(value) > 1e-12 for value in solution.pi_by_row.values()),
        "sampled_optimality_cut_tests": samples,
        "sampled_optimality_cut_valid": all(item["valid"] for item in samples),
        "farkas_nonzero_count": sum(abs(value) > 1e-12 for value in failed.farkas_by_row.values()),
        "infeasible_incumbent_excluded": excluded,
        "baseline_incumbent_admitted": baseline_admitted,
        "status": "PASS" if all(item["valid"] for item in samples) and excluded and baseline_admitted else "FAIL",
    }


def run_preproduction_gate(
    *, forecast_path: Path, mapping_authority_path: Path, production_config_path: Path, production_weights_path: Path
) -> tuple[IntegratedFixture, Mapping[str, object]]:
    fixture = build_integrated_fixture(
        forecast_path=forecast_path,
        mapping_authority_path=mapping_authority_path,
        production_config_path=production_config_path,
        production_weights_path=production_weights_path,
    )
    reference_sha = _digest_payload(fixture.reference_payload)
    monolithic = solve_monolithic(fixture)
    if monolithic["status"] != "OPTIMAL":
        raise RuntimeError("C7_MONOLITHIC_MUST_SOLVE_FIRST")
    c8 = validate_grid_duals(fixture)
    standard = solve_benders(fixture, BendersMethod.STANDARD_SINGLE_CUT)
    proposed = solve_benders(fixture, BendersMethod.CL_MC_BD)
    mono_obj = float(monolithic["objective"])
    relative = {
        "standard": abs(float(standard["objective"]) - mono_obj) / max(abs(mono_obj), 1e-6),
        "cl_mc_bd": abs(float(proposed["objective"]) - mono_obj) / max(abs(mono_obj), 1e-6),
    }
    hard_identity = (
        monolithic["hard_feasible"] == standard["hard_feasible"] == proposed["hard_feasible"]
    )
    g11 = "PASS" if c8["status"] == "PASS" else "FAIL"
    g12 = "PASS_NON_SCIENTIFIC_PREPRODUCTION" if (
        all(value <= 1e-3 for value in relative.values())
        and hard_identity
        and float(proposed["gap"]) <= 1e-3
    ) else "FAIL"
    report = {
        "authority_id": "V16_C7_C8_C9_PREPRODUCTION_INTEGRATION_V1",
        "namespace": NAMESPACE,
        "scientific_eligible": False,
        "may_june_loader_access_count": MAY_JUNE_LOADER_ACCESS_COUNT,
        "may_forecast_generated": False,
        "may_reference_schedule_generated": False,
        "may_b0_b3_result_generated": False,
        "c7": {
            "status": "PASS_NON_SCIENTIFIC_ENGINEERING",
            "integration_evidence": fixture.integration_evidence,
            "reference_schedule_sha256": reference_sha,
            "reference_b0_b2_bytes_identical": True,
            "reference_b0_b2_sha_identical": True,
            "residual_min_max": fixture.integration_evidence["reference_delta"],
            "service_parity_residual": fixture.integration_evidence["service_parity"]["max_abs_terminal_residual_nodeh"],
            "monolithic": monolithic,
        },
        "c8": c8,
        "c9": {
            "standard": standard,
            "cl_mc_bd": proposed,
            "relative_objective_difference": relative,
            "hard_feasibility_identity": hard_identity,
            "acceptance_tolerance": 1e-3,
        },
        "gates": {
            "G11": g11,
            "G12": g12,
            "G13": "BLOCKED_UNTIL_C12_AND_FULL_SCIENTIFIC_IEEE123_INPUT_RELEASE",
            "G14": "BLOCKED_BY_G13_SCIENTIFIC_RESULT_ABSENCE",
        },
        "status": "PASS" if g11 == "PASS" and g12.startswith("PASS") else "FAIL",
    }
    return fixture, report


def reference_bytes(payload: Mapping[str, object]) -> bytes:
    """Public canonical serializer used for the B0/B2 identity gate."""

    return _canonical_bytes(payload)
