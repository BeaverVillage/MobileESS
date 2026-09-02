"""One primal variable registry shared by all V28R2 solvers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.mess_physics import (
    E_INITIAL_KWH, E_MAX_KWH, E_MIN_KWH, E_TERMINAL_KWH,
    PCS_KVA, PCS_POLYGON_FACES, P_LIMIT_KW,
)
from dayahead.v28r2.c1_affine import add_planning_equality
from dayahead.v28r2.formulation import DT_HOURS, PF_TAN, V28R2FormulationData


def value(expression: object) -> float:
    if hasattr(expression, "getValue"):
        return float(expression.getValue())
    if hasattr(expression, "X"):
        return float(expression.X)
    return float(expression)


@dataclass
class VariableRegistry:
    model: object
    data: V28R2FormulationData
    case: str
    eta: object
    x: Mapping[tuple[str, str, int], object]
    backlog: Mapping[tuple[str, int], object]
    p_it: Mapping[tuple[str, int], object]
    p_pcc: Mapping[tuple[str, int], object]
    mess_p: Mapping[tuple[str, int], object]
    mess_q: Mapping[tuple[str, int], object]
    mess_e: Mapping[tuple[str, int], object]
    control_expressions: tuple[tuple[object, ...], ...]

    def controls(self) -> np.ndarray:
        return np.asarray([[value(item) for item in row] for row in self.control_expressions], dtype=float)

    def primal_arrays(self) -> dict[str, np.ndarray]:
        data = self.data
        x = np.asarray([
            [[value(self.x[(cohort, rack, slot)]) for slot in range(96)] for rack in data.rack_ids]
            for cohort in data.cohort_ids
        ])
        backlog = np.asarray([
            [value(self.backlog[(cohort, boundary)]) for cohort in data.cohort_ids]
            for boundary in range(97)
        ])
        p_it = np.asarray([[value(self.p_it[(aidc, slot)]) for aidc in data.aidc_ids] for slot in range(96)])
        p_pcc = np.asarray([[value(self.p_pcc[(aidc, slot)]) for aidc in data.aidc_ids] for slot in range(96)])
        mess_ids = tuple(sorted(data.mess_records))
        mess_p = np.asarray([[value(self.mess_p[(mess, slot)]) for mess in mess_ids] for slot in range(96)])
        mess_q = np.asarray([[value(self.mess_q[(mess, slot)]) for mess in mess_ids] for slot in range(96)])
        mess_e = np.asarray([[value(self.mess_e[(mess, boundary)]) for mess in mess_ids] for boundary in range(97)])
        gpu = data.delta.g_res_plan_gpu.T + x.sum(axis=0).T / DT_HOURS * 4.0
        kappa = np.asarray([
            KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])]
            for cohort in data.cohort_ids
        ], dtype=float)
        rack_it = data.delta.p_res_plan_kw.T + np.einsum("c,crh->hr", kappa, x) / DT_HOURS
        site_gpu = np.asarray([
            [
                gpu[slot, [index for index, owner in enumerate(data.rack_aidc) if owner == aidc]].sum()
                for aidc in data.aidc_ids
            ]
            for slot in range(96)
        ], dtype=float)
        return {
            "workload_service_nodeh": x,
            "backlog_nodeh": backlog,
            "site_it_power_kw": p_it,
            "rack_it_power_kw": rack_it,
            "site_pcc_power_kw": p_pcc,
            "site_pcc_reactive_kvar": p_pcc * PF_TAN,
            "rack_gpu": gpu,
            "site_gpu": site_gpu,
            "mess_p_kw": mess_p,
            "mess_q_kvar": mess_q,
            "mess_soc_kwh": mess_e,
            "controls_96x60": self.controls(),
        }


def configure_model(model: object) -> None:
    model.Params.OutputFlag = 0
    model.Params.Threads = 4
    model.Params.Seed = 20260828
    model.Params.Method = 1
    model.Params.NumericFocus = 1
    model.Params.DualReductions = 0
    model.Params.InfUnbdInfo = 1
    model.Params.FeasibilityTol = 1e-6
    model.Params.OptimalityTol = 1e-6
    model.Params.TimeLimit = 1800.0


def build_resource_model(
    data: V28R2FormulationData, voltage: object, case: str, *, rho: float = 0.1,
    rho_aidc: float | None = None, rho_mess: float | None = None,
) -> VariableRegistry:
    import gurobipy as gp
    from gurobipy import GRB

    if case not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("V28R2_UNKNOWN_CASE")
    data.validate()
    aidc_trust = float(rho if rho_aidc is None else rho_aidc)
    mess_trust = float(rho if rho_mess is None else rho_mess)
    if not (0 <= aidc_trust <= 1 and 0 <= mess_trust <= 1):
        raise ValueError("V28R2_TRUST_REGION_RANGE")
    compute_flexible = case in {"B1", "B3"}
    mess_flexible = case in {"B2", "B3"}
    model = gp.Model(f"v28r2_{case}_resource")
    configure_model(model)
    cohort_index = {value: index for index, value in enumerate(data.cohort_ids)}
    rack_index = {value: index for index, value in enumerate(data.rack_ids)}
    aidc_racks = {
        aidc: tuple(rack for rack, owner in zip(data.rack_ids, data.rack_aidc, strict=True) if owner == aidc)
        for aidc in data.aidc_ids
    }
    x = {}
    for cohort in data.cohort_ids:
        c = cohort_index[cohort]
        for rack in data.rack_ids:
            r = rack_index[rack]
            for slot in range(96):
                fixed = float(data.reference.x_ref_nodeh[c, r, slot])
                x[(cohort, rack, slot)] = model.addVar(
                    lb=0.0 if compute_flexible else fixed,
                    ub=GRB.INFINITY if compute_flexible else fixed,
                    name=f"workload[{cohort},{rack},{slot}]",
                )
    backlog = {
        (cohort, boundary): model.addVar(lb=0.0, name=f"backlog[{cohort},{boundary}]")
        for cohort in data.cohort_ids for boundary in range(97)
    }
    initial_backlog = np.asarray(
        getattr(data, "initial_backlog_nodeh", np.zeros(len(data.cohort_ids))), dtype=float,
    )
    if initial_backlog.shape != (len(data.cohort_ids),) or np.any(initial_backlog < 0):
        raise ValueError("V29_INITIAL_BACKLOG_AXIS_OR_SIGN")
    for cohort in data.cohort_ids:
        c = cohort_index[cohort]
        model.addConstr(backlog[(cohort, 0)] == float(initial_backlog[c]), name=f"service_initial[{cohort}]")
        for slot in range(96):
            model.addConstr(
                backlog[(cohort, slot + 1)] == backlog[(cohort, slot)]
                + float(data.arrivals_nodeh[slot, c])
                - gp.quicksum(x[(cohort, rack, slot)] for rack in data.rack_ids),
                name=f"service_balance[{cohort},{slot}]",
            )
        model.addConstr(
            backlog[(cohort, 96)] == float(data.reference.backlog_nodeh[96, c]),
            name=f"service_terminal_reference_parity[{cohort}]",
        )
    for slot in range(96):
        for rack in data.rack_ids:
            r = rack_index[rack]
            model.addConstr(
                float(data.delta.g_res_plan_gpu[r, slot])
                + 4.0 / DT_HOURS * gp.quicksum(x[(cohort, rack, slot)] for cohort in data.cohort_ids)
                <= float(data.rack_gpu_capacity[r]),
                name=f"rack_gpu_hard[{rack},{slot}]",
            )

    coefficients = data.c1_by_site_slot
    p_it, p_pcc = {}, {}
    for slot in range(96):
        for aidc in data.aidc_ids:
            indices = [rack_index[rack] for rack in aidc_racks[aidc]]
            coefficient = coefficients[(aidc, slot)]
            flexible_it = gp.quicksum(
                KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * x[(cohort, rack, slot)]
                for cohort in data.cohort_ids for rack in aidc_racks[aidc]
            )
            p_it[(aidc, slot)] = model.addVar(
                lb=coefficient.p_min_kw, ub=coefficient.p_max_kw,
                name=f"aidc_it_kw[{aidc},{slot}]",
            )
            model.addConstr(
                p_it[(aidc, slot)] == float(data.delta.p_res_plan_kw[indices, slot].sum()) + flexible_it,
                name=f"aidc_it_composition[{aidc},{slot}]",
            )
            pcc_min = coefficient.slope * coefficient.p_min_kw + coefficient.intercept_kw
            pcc_max = coefficient.slope * coefficient.p_max_kw + coefficient.intercept_kw
            p_pcc[(aidc, slot)] = model.addVar(lb=pcc_min, ub=pcc_max, name=f"aidc_pcc_kw[{aidc},{slot}]")
            add_planning_equality(model, p_it[(aidc, slot)], p_pcc[(aidc, slot)], coefficient)
            reference_it = float(data.delta.p_res_plan_kw[indices, slot].sum() + data.reference.p_f_ref_kw[indices, slot].sum())
            reference_pcc = coefficient.slope * reference_it + coefficient.intercept_kw
            model.addConstr(p_pcc[(aidc, slot)] >= reference_pcc - aidc_trust * (reference_pcc - pcc_min), name=f"trust_aidc_low[{aidc},{slot}]")
            model.addConstr(p_pcc[(aidc, slot)] <= reference_pcc + aidc_trust * (pcc_max - reference_pcc), name=f"trust_aidc_high[{aidc},{slot}]")

    mess_p, mess_q, mess_e = {}, {}, {}
    for mess_id, record in sorted(data.mess_records.items()):
        transit = set(map(int, record["transit_slots"]))
        unavailable = set(map(int, record.get("unavailable_slots", record["transit_slots"])))
        start = min(transit)
        for boundary in range(97):
            mess_e[(mess_id, boundary)] = model.addVar(lb=E_MIN_KWH, ub=E_MAX_KWH, name=f"mess_soc_kwh[{mess_id},{boundary}]")
        model.addConstr(mess_e[(mess_id, 0)] == E_INITIAL_KWH, name=f"mess_initial_soc[{mess_id}]")
        for slot in range(96):
            connected = slot not in unavailable
            fixed = -5.0 if connected and slot in range(start - 8, start) else 0.0
            mess_p[(mess_id, slot)] = model.addVar(
                lb=(-mess_trust * P_LIMIT_KW if connected else 0.0) if mess_flexible else fixed,
                ub=(mess_trust * P_LIMIT_KW if connected else 0.0) if mess_flexible else fixed,
                name=f"mess_p_kw[{mess_id},{slot}]",
            )
            mess_q[(mess_id, slot)] = model.addVar(
                lb=(-mess_trust * PCS_KVA if connected else 0.0) if mess_flexible else 0.0,
                ub=(mess_trust * PCS_KVA if connected else 0.0) if mess_flexible else 0.0,
                name=f"mess_q_kvar[{mess_id},{slot}]",
            )
            mobility = float(record["safe_mobility_energy_kwh"]) / len(transit) if slot in transit else 0.0
            model.addConstr(
                mess_e[(mess_id, slot + 1)] == mess_e[(mess_id, slot)]
                - DT_HOURS * mess_p[(mess_id, slot)] - mobility,
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

    controls = tuple(map(str, voltage["control_names"]))
    service_to_mess = {str(record["service_site"]): mess for mess, record in data.mess_records.items()}
    rows = []
    for slot in range(96):
        expressions = []
        for name in controls:
            if name.startswith("aidc_load_kw["):
                expressions.append(p_pcc[(name[13:-1], slot)])
            elif name.startswith("mess_p_kw["):
                service = name[10:-1]
                expressions.append(mess_p[(service_to_mess[service], slot)] if service in service_to_mess else 0.0)
            elif name.startswith("mess_q_kvar["):
                service = name[12:-1]
                expressions.append(mess_q[(service_to_mess[service], slot)] if service in service_to_mess else 0.0)
            else:
                raise RuntimeError(f"V28R2_UNKNOWN_CONTROL:{name}")
        rows.append(tuple(expressions))
    eta = model.addVar(lb=0.0, name="max_normalized_phase_line_current")
    model.setObjective(eta, GRB.MINIMIZE)
    model.update()
    return VariableRegistry(
        model, data, case, eta, x, backlog, p_it, p_pcc,
        mess_p, mess_q, mess_e, tuple(rows),
    )
