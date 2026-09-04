"""B2-anchored no-regret MESS release ladder for V29R2."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Mapping

import numpy as np

from dayahead.mess_physics import PCS_KVA, PCS_POLYGON_FACES, P_LIMIT_KW
from dayahead.v28r2.solver_payload import payload_from_registry
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.variable_registry import build_resource_model, value
from dayahead.v29r1.authority import Q_SCENARIOS
from dayahead.v29r1.source_resume import sha256_file, write_csv, write_json

from .anchor_forensic import OUT_REL


RUNG_ORDER = ("Q_RELEASE", "Q_ANCHOR", "FULL_MESS_ANCHOR", "B2_FALLBACK")
EPSILON_NR = 1e-4
EPSILON_AC_NR = 1e-4


def solve_b3_rung(
    *, data: object, context: object, voltage: object, current: object,
    b2_payload: object, rung: str, rho: float,
) -> object:
    """Solve one B3 rung with B2 MESS anchors added before optimization."""

    from gurobipy import GRB
    if rung not in RUNG_ORDER[:-1]:
        raise ValueError(f"V29R2_UNKNOWN_NOREGRET_RUNG:{rung}")
    started = time.perf_counter()
    registry = build_resource_model(data, voltage, "B3", rho_aidc=rho, rho_mess=.10)
    add_grid_rows(registry, context, voltage, current)
    mess_ids = tuple(sorted(data.mess_records))
    b2_p = np.asarray(b2_payload.mess_p_kw, dtype=float)
    b2_q = np.asarray(b2_payload.mess_q_kvar, dtype=float)
    for slot in range(96):
        for mess_index, mess_id in enumerate(mess_ids):
            if rung in {"Q_ANCHOR", "FULL_MESS_ANCHOR"}:
                registry.model.addConstr(
                    registry.mess_q[(mess_id, slot)] == float(b2_q[slot, mess_index]),
                    name=f"v29r2_q_b2_anchor[{mess_id},{slot}]",
                )
            if rung == "FULL_MESS_ANCHOR":
                registry.model.addConstr(
                    registry.mess_p[(mess_id, slot)] == float(b2_p[slot, mess_index]),
                    name=f"v29r2_p_b2_anchor[{mess_id},{slot}]",
                )
    registry.model.update()
    registry.model.optimize()
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V29R2_NOREGRET_PRIMARY_STATUS:{rung}:{int(registry.model.Status)}")
    primary = float(value(registry.eta))
    registry.model.addConstr(registry.eta <= primary + EPSILON_NR, name="v29r2_primary_equivalence_band")
    absolute_q = []
    for slot in range(96):
        for mess_index, mess_id in enumerate(mess_ids):
            delta = registry.mess_q[(mess_id, slot)] - float(b2_q[slot, mess_index])
            magnitude = registry.model.addVar(lb=0.0, name=f"v29r2_abs_delta_q[{mess_id},{slot}]")
            registry.model.addConstr(magnitude >= delta)
            registry.model.addConstr(magnitude >= -delta)
            absolute_q.append(magnitude)
    registry.model.setObjective(sum(absolute_q), GRB.MINIMIZE)
    registry.model.optimize()
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V29R2_NOREGRET_TIEBREAK_STATUS:{rung}:{int(registry.model.Status)}")
    objective = float(value(registry.eta))
    return payload_from_registry(
        registry, solver="MONOLITHIC", status="OPTIMAL", hard_feasible=True,
        objective=objective, lower_bound=objective, upper_bound=objective,
        gap=0.0, iterations=int(registry.model.IterCount), optimality_cuts=0,
        feasibility_cuts=0, termination_reason=f"V29R2_{rung}_PRIMARY_THEN_MIN_ABS_DELTA_Q",
        runtime_seconds=time.perf_counter() - started,
    )


def select_first_safe_rung(
    evaluations: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> tuple[str, list[dict[str, object]]]:
    audit: list[dict[str, object]] = []
    for rung in RUNG_ORDER[:-1]:
        by_scenario = evaluations.get(rung, {})
        complete = set(by_scenario) == set(Q_SCENARIOS)
        planning = complete and all(
            float(by_scenario[scenario]["planning_delta_vs_B2"]) <= EPSILON_NR
            for scenario in Q_SCENARIOS
        )
        ac = complete and all(
            bool(by_scenario[scenario]["all_converged"])
            and float(by_scenario[scenario]["rho_AC_delta_vs_B2"]) <= EPSILON_AC_NR
            for scenario in Q_SCENARIOS
        )
        audit.append({"rung": rung, "complete": complete, "planning_pass": planning, "AC_pass": ac, "safe": planning and ac})
        if planning and ac:
            return rung, audit
    audit.append({"rung": "B2_FALLBACK", "complete": True, "planning_pass": True, "AC_pass": True, "safe": True})
    return "B2_FALLBACK", audit


def freeze_noregret_contract(repo: Path) -> dict[str, object]:
    out = repo / OUT_REL
    reference = json.loads((out / "V29R2_REFERENCE_V4_CONTRACT.json").read_text(encoding="utf-8"))
    if reference["status"] != "PASS":
        raise RuntimeError("V29R2_NOREGRET_WITHOUT_REFERENCE_V4")
    physics_path = repo / "dayahead/mess_physics.py"
    contract = {
        "artifact_id": "V29R2_MESS_NOREGRET_CONTRACT_V1", "status": "PASS",
        "authority": "B2_ANCHORED_NO_REGRET_MESS_V2",
        "safety_anchor": "solve and store B2 P/Q first in every scenario",
        "rung_order": list(RUNG_ORDER),
        "scenario_set": list(Q_SCENARIOS),
        "planning_gate": "J_PLAN_B3(omega) <= J_PLAN_B2(omega) + epsilon_NR for every frozen scenario",
        "AC_gate": "rho_AC_B3(omega) <= rho_AC_B2(omega) + epsilon_AC_NR for every frozen scenario",
        "epsilon_NR": EPSILON_NR, "epsilon_AC_NR": EPSILON_AC_NR,
        "tie_break": "only inside primary-objective equivalence: minimize sum abs(Q_B3-Q_B2)",
        "Q_RELEASE": "AIDC workload and MESS P/Q free within unchanged authorities",
        "Q_ANCHOR": "Q_B3=Q_B2; AIDC workload and MESS P free",
        "FULL_MESS_ANCHOR": "P_B3=P_B2 and Q_B3=Q_B2; AIDC workload free",
        "B2_FALLBACK": "production B3 decision is byte-equivalent B2 schedule",
        "MESS_rating_authority": {
            "P_LIMIT_KW": P_LIMIT_KW, "PCS_KVA": PCS_KVA,
            "PCS_POLYGON_FACES": PCS_POLYGON_FACES, "source_sha256": sha256_file(physics_path),
        },
        "rating_changes": 0, "objective_change": False,
        "Actual_reads": 0, "April_result_reads": 0,
        "result_driven_threshold_changes": 0,
    }
    scenario_rows = [{
        "scenario": scenario, "priority": index + 1,
        "carryin_state": {"S_NOM": "H0_NOM", "S_LOW": "H0_LOW", "S_ZERO_CARRY": "zero"}[scenario],
        "same_feeder_forecast_namespace": True, "Actual_realization_used": False,
        "frozen_before_Apr04_result": True,
    } for index, scenario in enumerate(Q_SCENARIOS)]
    ac_rows = [{
        "rung": rung, "scenario": scenario,
        "comparator": "matched B2 Fresh OpenDSS",
        "epsilon_AC_NR": EPSILON_AC_NR,
        "all_converged_required": True,
        "release_condition_frozen": True,
        "prefreeze_status": "PASS_GATE_DEFINED_AND_ENFORCED_BY_SELECTOR",
        "Actual_reads": 0,
    } for rung in RUNG_ORDER for scenario in Q_SCENARIOS]
    decision_rows = [{
        "priority": index + 1, "rung": rung,
        "selection_rule": "first rung passing planning and Fresh OpenDSS gates in every frozen scenario",
        "deterministic": True, "Apr04_selected": "PENDING_CAUSAL_DEVELOPMENT_EXECUTION",
    } for index, rung in enumerate(RUNG_ORDER)]
    write_json(out / "V29R2_MESS_NOREGRET_CONTRACT.json", contract)
    write_csv(out / "V29R2_MESS_NOREGRET_SCENARIOS.csv", scenario_rows)
    write_csv(out / "V29R2_MESS_NOREGRET_AC_GATE.csv", ac_rows)
    write_csv(out / "V29R2_MESS_FALLBACK_DECISION.csv", decision_rows)
    return contract
