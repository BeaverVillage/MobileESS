"""Actual April full-IEEE123 V16.2 joint B3 monolithic formulation."""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file
from .full_ieee123_g11_v16_1 import FullGridBinding, PF_AIDC
from .grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from .mess_physics import E_INITIAL_KWH, E_MAX_KWH, E_MIN_KWH, E_TERMINAL_KWH, PCS_KVA, PCS_POLYGON_FACES, P_LIMIT_KW


OPERATING_DAY = "2025-04-15"
FORECAST_MODEL = "Proposed AIDC RC-MQT"
FORECAST_NAMESPACE = "APRIL_VALIDATION_ONLY"


@dataclass(frozen=True)
class B3Inputs:
    cohorts: tuple[str, ...]
    arrivals: Mapping[str, tuple[float, ...]]
    rack_ids: tuple[str, ...]
    rack_aidc: tuple[str, ...]
    gpu_capacity: tuple[float, ...]
    p_res_aidc_kw: tuple[tuple[float, ...], ...]
    g_res_rack: tuple[tuple[float, ...], ...]
    mess_records: Mapping[str, Mapping[str, object]]
    evidence: Mapping[str, object]


def load_b3_inputs(
    *,
    forecast_path: Path,
    reference_path: Path,
    c7_path: Path,
    rack_contract_path: Path,
) -> B3Inputs:
    import pandas as pd

    forecast = pd.read_parquet(forecast_path)
    dates = pd.to_datetime(forecast["forecast_day"])
    if dates.min().date().isoformat() < "2025-04-01" or dates.max().date().isoformat() > "2025-04-30":
        raise RuntimeError("B3_FORECAST_NAMESPACE_CONTAINS_MAY_OR_JUNE")
    selected = forecast[
        (forecast["model"] == FORECAST_MODEL)
        & (forecast["namespace"] == FORECAST_NAMESPACE)
        & (forecast["forecast_day"] == OPERATING_DAY)
        & (forecast["quantile"] == 0.5)
        & forecast["target"].astype(str).str.startswith("W_F::")
    ].copy()
    cohorts = tuple(sorted(str(value).split("::", 1)[1] for value in selected["target"].unique()))
    arrivals: dict[str, tuple[float, ...]] = {}
    for cohort in cohorts:
        rows = selected[selected["target"] == f"W_F::{cohort}"].sort_values("slot")
        if tuple(map(int, rows["slot"])) != tuple(range(96)):
            raise RuntimeError(f"B3_DIRECT96_COHORT_AXIS_FAIL:{cohort}")
        values = tuple(map(float, rows["prediction"]))
        if any(value < -1e-12 or not math.isfinite(value) for value in values):
            raise RuntimeError(f"B3_INVALID_COHORT_ARRIVALS:{cohort}")
        arrivals[cohort] = values
    if len(cohorts) != 15:
        raise RuntimeError("B3_FROZEN_COHORT_AXIS_MUST_BE_15")

    reference = pd.read_parquet(reference_path)
    reference_totals = (
        reference.groupby(["cohort", "slot"], as_index=False)["x_ref_v3_h100_nodeh"].sum()
    )
    reference_error = 0.0
    for cohort in cohorts:
        rows = reference_totals[reference_totals["cohort"] == cohort].sort_values("slot")
        reference_error = max(
            reference_error,
            max(abs(float(value) - arrivals[cohort][slot]) for slot, value in zip(rows["slot"], rows["x_ref_v3_h100_nodeh"])),
        )
    if reference_error > 1e-9:
        raise RuntimeError(f"B3_V3_SERVICE_INPUT_IDENTITY_FAIL:{reference_error}")

    c7 = json.loads(c7_path.read_text(encoding="utf-8"))
    delta = c7["reference_delta"]
    rack_contract = json.loads(rack_contract_path.read_text(encoding="utf-8"))
    racks = tuple(rack_contract["racks"])
    rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks)
    gpu_capacity = tuple(float(row["deliverable_gpu_capacity"]) for row in racks)
    p_res = tuple(tuple(map(float, row)) for row in delta["p_res_aidc_kw"])
    g_res = tuple(tuple(map(float, row)) for row in delta["g_res_rack"])
    if len(rack_ids) != 48 or len(p_res) != 96 or any(len(row) != 12 for row in p_res):
        raise RuntimeError("B3_FROZEN_AIDC_RACK_AXIS_MISMATCH")
    if len(g_res) != 96 or any(len(row) != 48 for row in g_res):
        raise RuntimeError("B3_FROZEN_GPU_RESIDUAL_AXIS_MISMATCH")
    mess_records = c7["mess_invariants"]["records"]
    if len(mess_records) != 4:
        raise RuntimeError("B3_FROZEN_MESS_AXIS_MISMATCH")
    return B3Inputs(
        cohorts,
        arrivals,
        rack_ids,
        rack_aidc,
        gpu_capacity,
        p_res,
        g_res,
        mess_records,
        {
            "forecast_path": str(forecast_path.resolve()),
            "forecast_sha256": sha256_file(forecast_path),
            "forecast_model": FORECAST_MODEL,
            "forecast_namespace": FORECAST_NAMESPACE,
            "forecast_quantile": "Q50_COHORT_ARRIVALS",
            "forecast_rows_read_scope": "APRIL_ONLY_ARTIFACT",
            "reference_path": str(reference_path.resolve()),
            "reference_sha256": sha256_file(reference_path),
            "reference_arrival_identity_max_abs_error_nodeh": reference_error,
            "c7_path": str(c7_path.resolve()),
            "c7_sha256": sha256_file(c7_path),
            "rack_contract_path": str(rack_contract_path.resolve()),
            "rack_contract_sha256": sha256_file(rack_contract_path),
            "pue": PUE_PLAN,
            "aidc_power_factor": PF_AIDC,
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
        },
    )


def _family(name: str) -> str:
    return name.split("[", 1)[0]


def solve_monolithic(
    binding: FullGridBinding,
    inputs: B3Inputs,
    *,
    output_dir: Path,
) -> dict[str, object]:
    import gurobipy as gp
    from gurobipy import GRB

    if len(binding.factories) != 96:
        raise RuntimeError("B3_FULL_IEEE123_REQUIRES_96_GRID_BLOCKS")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = gp.Model("v16_2_full_ieee123_b3_joint_monolithic")
    model.Params.OutputFlag = 1
    model.Params.DualReductions = 0
    model.Params.InfUnbdInfo = 1
    model.Params.NumericFocus = 1

    cohorts = inputs.cohorts
    rack_ids = inputs.rack_ids
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    aidc_racks = {
        f"AIDC{index:02d}": tuple(rack for rack, aidc in zip(rack_ids, inputs.rack_aidc) if aidc == f"AIDC{index:02d}")
        for index in range(1, 13)
    }
    x = {
        (cohort, rack, slot): model.addVar(lb=0.0, name=f"workload[{cohort},{rack},{slot}]")
        for cohort in cohorts for rack in rack_ids for slot in range(96)
    }
    backlog = {
        (cohort, boundary): model.addVar(lb=0.0, name=f"backlog[{cohort},{boundary}]")
        for cohort in cohorts for boundary in range(97)
    }
    for cohort in cohorts:
        model.addConstr(backlog[(cohort, 0)] == 0.0, name=f"service_initial[{cohort}]")
        for slot in range(96):
            model.addConstr(
                backlog[(cohort, slot + 1)]
                == backlog[(cohort, slot)] + inputs.arrivals[cohort][slot]
                - gp.quicksum(x[(cohort, rack, slot)] for rack in rack_ids),
                name=f"service_balance[{cohort},{slot}]",
            )
        model.addConstr(backlog[(cohort, 96)] == 0.0, name=f"service_terminal_parity[{cohort}]")
    for slot in range(96):
        for rack in rack_ids:
            r = rack_index[rack]
            model.addConstr(
                inputs.g_res_rack[slot][r]
                + GPU_PER_NODE / DT_HOURS * gp.quicksum(x[(cohort, rack, slot)] for cohort in cohorts)
                <= inputs.gpu_capacity[r],
                name=f"rack_gpu_hard[{rack},{slot}]",
            )

    aidc_load: dict[tuple[str, int], object] = {}
    for slot in range(96):
        for aidc_index in range(1, 13):
            aidc = f"AIDC{aidc_index:02d}"
            flexible_it = gp.quicksum(
                KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * x[(cohort, rack, slot)]
                for cohort in cohorts for rack in aidc_racks[aidc]
            )
            aidc_load[(aidc, slot)] = PUE_PLAN * (inputs.p_res_aidc_kw[slot][aidc_index - 1] + flexible_it)

    mess_p: dict[tuple[str, int], object] = {}
    mess_q: dict[tuple[str, int], object] = {}
    mess_e: dict[tuple[str, int], object] = {}
    for mess_id, record in sorted(inputs.mess_records.items()):
        transit = set(map(int, record["transit_slots"]))
        for boundary in range(97):
            mess_e[(mess_id, boundary)] = model.addVar(lb=E_MIN_KWH, ub=E_MAX_KWH, name=f"mess_soc_kwh[{mess_id},{boundary}]")
        model.addConstr(mess_e[(mess_id, 0)] == E_INITIAL_KWH, name=f"mess_initial_soc[{mess_id}]")
        for slot in range(96):
            connected = slot not in transit
            mess_p[(mess_id, slot)] = model.addVar(
                lb=-P_LIMIT_KW if connected else 0.0,
                ub=P_LIMIT_KW if connected else 0.0,
                name=f"mess_p_kw[{mess_id},{slot}]",
            )
            mess_q[(mess_id, slot)] = model.addVar(
                lb=-PCS_KVA if connected else 0.0,
                ub=PCS_KVA if connected else 0.0,
                name=f"mess_q_kvar[{mess_id},{slot}]",
            )
            mobility = float(record["safe_mobility_energy_kwh"]) / len(transit) if slot in transit else 0.0
            model.addConstr(
                mess_e[(mess_id, slot + 1)] == mess_e[(mess_id, slot)] - DT_HOURS * mess_p[(mess_id, slot)] - mobility,
                name=f"mess_soc_balance[{mess_id},{slot}]",
            )
            apothem = PCS_KVA * math.cos(math.pi / PCS_POLYGON_FACES)
            for face in range(PCS_POLYGON_FACES):
                angle = 2.0 * math.pi * face / PCS_POLYGON_FACES
                model.addConstr(
                    math.cos(angle) * mess_p[(mess_id, slot)] + math.sin(angle) * mess_q[(mess_id, slot)] <= apothem,
                    name=f"mess_pcs_hard[{mess_id},{slot},{face}]",
                )
        model.addConstr(mess_e[(mess_id, 96)] == E_TERMINAL_KWH, name=f"mess_terminal_soc[{mess_id}]")

    eta = model.addVar(lb=0.0, name="rho_day_max")
    flow_p: dict[tuple[int, str, str], object] = {}
    flow_q: dict[tuple[int, str, str], object] = {}
    voltage: dict[tuple[int, str, str], object] = {}
    mess_by_service = {str(record["service_site"]): mess_id for mess_id, record in inputs.mess_records.items()}
    for slot, (factory, baseline) in enumerate(zip(binding.factories, binding.baseline_master)):
        expressions: dict[str, object] = {}
        for key in baseline:
            if key.startswith("aidc_load_kw["):
                expressions[key] = aidc_load[(key[13:-1], slot)]
            elif key.startswith("mess_p_kw["):
                service = key[10:-1]
                expressions[key] = mess_p[(mess_by_service[service], slot)] if service in mess_by_service else 0.0
            elif key.startswith("mess_q_kvar["):
                service = key[12:-1]
                expressions[key] = mess_q[(mess_by_service[service], slot)] if service in mess_by_service else 0.0
            else:
                raise RuntimeError(f"B3_UNBOUND_MASTER_KEY:{key}")
        data = factory.data
        branches = tuple(data.branches)
        incoming: dict[tuple[str, str], list[object]] = defaultdict(list)
        outgoing: dict[tuple[str, str], list[object]] = defaultdict(list)
        for branch in branches:
            key = (branch.branch_id, branch.phase)
            p = model.addVar(lb=-GRB.INFINITY, name=f"grid_p_kw[{slot},{branch.branch_id},{branch.phase}]")
            q = model.addVar(lb=-GRB.INFINITY, name=f"grid_q_kvar[{slot},{branch.branch_id},{branch.phase}]")
            flow_p[(slot, *key)] = p
            flow_q[(slot, *key)] = q
            incoming[(branch.child_bus, branch.phase)].append(branch)
            outgoing[(branch.parent_bus, branch.phase)].append(branch)
        for (bus, phase), present in data.bus_phase_present.items():
            if present:
                voltage[(slot, bus, phase)] = model.addVar(
                    lb=V_MIN_SQUARED,
                    ub=V_MAX_SQUARED,
                    name=f"grid_v_squared[{slot},{bus},{phase}]",
                )
                if bus == data.root_bus:
                    model.addConstr(voltage[(slot, bus, phase)] == 1.0, name=f"grid_root_voltage[{slot},{bus},{phase}]")
        for branch in branches:
            key = (branch.branch_id, branch.phase)
            p = flow_p[(slot, *key)]
            q = flow_q[(slot, *key)]
            model.addConstr(
                voltage[(slot, branch.child_bus, branch.phase)]
                == voltage[(slot, branch.parent_bus, branch.phase)]
                - 2.0 * (branch.r_pu_per_kw * p + branch.x_pu_per_kvar * q),
                name=f"grid_voltage_drop[{slot},{branch.branch_id},{branch.phase}]",
            )
            limit = float(data.line_limit_kva_u080[key])
            apothem = limit * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                expression = math.cos(angle) * p + math.sin(angle) * q
                model.addConstr(expression <= apothem, name=f"grid_line_hard[{slot},{branch.branch_id},{branch.phase},{face}]")
                model.addConstr(expression <= eta * apothem, name=f"grid_day_rho[{slot},{branch.branch_id},{branch.phase},{face}]")
            tx_limit = data.transformer_limit_kva.get(key)
            if tx_limit is not None:
                tx_apothem = float(tx_limit) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        math.cos(angle) * p + math.sin(angle) * q <= tx_apothem,
                        name=f"grid_transformer_hard[{slot},{branch.branch_id},{branch.phase},{face}]",
                    )
        for (bus, phase), present in data.bus_phase_present.items():
            if not present or bus == data.root_bus:
                continue
            if len(incoming[(bus, phase)]) != 1:
                raise RuntimeError(f"B3_NONRADIAL_PRESENT_PHASE:{bus}:{phase}")
            in_branch = incoming[(bus, phase)][0]
            p_rhs = float(data.base_load_p_kw.get((bus, phase), 0.0)) + gp.quicksum(
                -float(value) * expressions[key]
                for key, value in data.master_p_injection.get((bus, phase), {}).items()
            )
            q_rhs = float(data.base_load_q_kvar.get((bus, phase), 0.0)) + gp.quicksum(
                -float(value) * expressions[key]
                for key, value in data.master_q_injection.get((bus, phase), {}).items()
            )
            model.addConstr(
                flow_p[(slot, in_branch.branch_id, phase)]
                - gp.quicksum(flow_p[(slot, branch.branch_id, phase)] for branch in outgoing.get((bus, phase), ()))
                == p_rhs,
                name=f"grid_p_balance[{slot},{bus},{phase}]",
            )
            model.addConstr(
                flow_q[(slot, in_branch.branch_id, phase)]
                - gp.quicksum(flow_q[(slot, branch.branch_id, phase)] for branch in outgoing.get((bus, phase), ()))
                == q_rhs,
                name=f"grid_q_balance[{slot},{bus},{phase}]",
            )

    model.setObjective(eta, GRB.MINIMIZE)
    model.optimize()
    elapsed = time.perf_counter() - started
    common = {
        "model_name": model.ModelName,
        "gurobi_status_code": int(model.Status),
        "runtime_seconds": float(model.Runtime),
        "wall_runtime_seconds": elapsed,
        "variable_count": int(model.NumVars),
        "constraint_count": int(model.NumConstrs),
        "objective": float(model.ObjVal) if model.Status == GRB.OPTIMAL else None,
        "objective_bound": float(model.ObjBound) if model.Status == GRB.OPTIMAL else None,
        "full_ieee123_grid_block_count": 96,
        "compute_flexibility": "ON",
        "mess_flexibility": "ON_FIXED_FROZEN_ROUTES",
        "slack_variable_count": 0,
        "rating_change_count": 0,
        "alpha_grid_change_count": 0,
        "source_voltage_change_count": 0,
        "placement_change_count": 0,
    }
    if model.Status == GRB.INFEASIBLE:
        iis_started = time.perf_counter()
        # Gurobi has already produced an exact Farkas certificate for the
        # full 1.48M-row model.  Computing an IIS over rows with zero ray
        # support is both unnecessary and numerically costly.  Retain every
        # original variable/bound and every nonzero-support original row,
        # verify that exact subset remains infeasible, then compute its IIS.
        farkas_support = {
            constraint.ConstrName
            for constraint in model.getConstrs()
            if abs(float(constraint.FarkasDual)) > 1e-12
        }
        if not farkas_support:
            raise RuntimeError("B3_FULL_MODEL_FARKAS_SUPPORT_EMPTY")
        iis_model = model.copy()
        iis_model.Params.OutputFlag = 1
        iis_model.Params.DualReductions = 0
        iis_model.Params.IISMethod = 0
        iis_model.remove([
            constraint for constraint in iis_model.getConstrs()
            if constraint.ConstrName not in farkas_support
        ])
        iis_model.setObjective(0.0, GRB.MINIMIZE)
        iis_model.update()
        iis_model.optimize()
        if iis_model.Status != GRB.INFEASIBLE:
            raise RuntimeError(f"B3_FARKAS_SUPPORT_SUBMODEL_NOT_INFEASIBLE:{iis_model.Status}")
        iis_model.computeIIS()
        iis_constraints = [constraint.ConstrName for constraint in iis_model.getConstrs() if bool(constraint.IISConstr)]
        iis_bounds = [
            {"variable": variable.VarName, "side": side, "value": float(variable.LB if side == "LB" else variable.UB)}
            for variable in iis_model.getVars()
            for side, active in (("LB", bool(variable.IISLB)), ("UB", bool(variable.IISUB)))
            if active
        ]
        iis_path = output_dir / "G12_V16_2_B3_MONOLITHIC.ilp"
        ascii_iis_path = Path(tempfile.gettempdir()) / "G12_V16_2_B3_MONOLITHIC.ilp"
        iis_model.write(str(ascii_iis_path))
        shutil.copyfile(ascii_iis_path, iis_path)
        return {
            **common,
            "status": "G12_FAIL_B3_PLANNING_INFEASIBLE",
            "hard_feasible": False,
            "iis": {
                "computed": True,
                "method": "FULL_MODEL_FARKAS_NONZERO_SUPPORT_THEN_GUROBI_IIS",
                "full_model_farkas_proof": float(model.FarkasProof),
                "full_model_farkas_support_constraint_count": len(farkas_support),
                "support_submodel_status": "INFEASIBLE",
                "runtime_seconds": time.perf_counter() - iis_started,
                "constraint_count": len(iis_constraints),
                "constraint_family_counts": dict(sorted(Counter(map(_family, iis_constraints)).items())),
                "constraint_names": iis_constraints,
                "variable_bound_count": len(iis_bounds),
                "variable_bounds": iis_bounds,
                "ilp_path": str(iis_path.resolve()),
                "ilp_sha256": sha256_file(iis_path),
            },
            "workload_allocation_saved": False,
            "mess_schedule_saved": False,
        }
    if model.Status != GRB.OPTIMAL:
        return {**common, "status": f"G12_FAIL_GUROBI_STATUS_{model.Status}", "hard_feasible": False}

    output_dir.mkdir(parents=True, exist_ok=True)
    workload_path = output_dir / "G12_V16_2_B3_WORKLOAD_ALLOCATION.parquet"
    mess_path = output_dir / "G12_V16_2_B3_MESS_SCHEDULE.parquet"
    import pandas as pd
    pd.DataFrame([
        {"cohort": cohort, "rack_id": rack, "slot": slot, "x_h100_nodeh": float(variable.X)}
        for (cohort, rack, slot), variable in x.items()
    ]).to_parquet(workload_path, index=False)
    pd.DataFrame([
        {
            "mess_id": mess_id,
            "service_site": inputs.mess_records[mess_id]["service_site"],
            "slot": slot,
            "p_kw": float(mess_p[(mess_id, slot)].X),
            "q_kvar": float(mess_q[(mess_id, slot)].X),
            "energy_start_kwh": float(mess_e[(mess_id, slot)].X),
            "energy_end_kwh": float(mess_e[(mess_id, slot + 1)].X),
            "in_transit": slot in set(map(int, inputs.mess_records[mess_id]["transit_slots"])),
        }
        for mess_id in sorted(inputs.mess_records) for slot in range(96)
    ]).to_parquet(mess_path, index=False)
    loading_rows = []
    for slot, factory in enumerate(binding.factories):
        for branch in factory.data.branches:
            key = (branch.branch_id, branch.phase)
            p_value = float(flow_p[(slot, *key)].X)
            q_value = float(flow_q[(slot, *key)].X)
            loading_rows.append({
                "time_index": slot,
                "branch_id": branch.branch_id,
                "phase": branch.phase,
                "p_kw": p_value,
                "q_kvar": q_value,
                "loading_pu": math.hypot(p_value, q_value) / float(factory.data.line_limit_kva_u080[key]),
                "is_transformer": key in factory.data.transformer_limit_kva,
            })
    voltage_rows = [
        {"time_index": slot, "bus": bus, "phase": phase, "v_squared_pu": float(variable.X), "voltage_pu": math.sqrt(float(variable.X))}
        for (slot, bus, phase), variable in voltage.items()
    ]
    return {
        **common,
        "status": "OPTIMAL",
        "hard_feasible": True,
        "workload_allocation": {"path": str(workload_path.resolve()), "sha256": sha256_file(workload_path)},
        "mess_schedule": {"path": str(mess_path.resolve()), "sha256": sha256_file(mess_path)},
        "worst_planning_line": max((row for row in loading_rows if not row["is_transformer"]), key=lambda row: row["loading_pu"]),
        "worst_transformer": max((row for row in loading_rows if row["is_transformer"]), key=lambda row: row["loading_pu"]),
        "minimum_voltage": min(voltage_rows, key=lambda row: row["v_squared_pu"]),
        "maximum_voltage": max(voltage_rows, key=lambda row: row["v_squared_pu"]),
        "terminal_service_parity_max_abs_nodeh": max(abs(float(backlog[(cohort, 96)].X)) for cohort in cohorts),
        "mess_terminal_soc_max_abs_error_kwh": max(abs(float(mess_e[(mess_id, 96)].X) - E_TERMINAL_KWH) for mess_id in inputs.mess_records),
    }
