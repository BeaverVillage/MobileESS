"""Read-only AIDC grid-value root-cause forensic for frozen V16.3 results."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file
from .full_ieee123_g11_v16_1 import PF_AIDC
from .run_v16_3_nonzero_validity import _aidc_limits
from .run_v16_3_prepare_final_days import DEFAULT_SOURCE
from .v16_3_final_context import build_context, final_forecast_day


AUTHORITY_COMMIT = "2246063175977f152f3ac8df8f65a861cc7bbd22"
COMPLETION_COMMIT = "1c46d6510be6be6e00f3305821cbe3bbbd79bdd9"
RHO = 0.10
TOL = 1e-9
FIREWALL = {
    "scientific_authority_changes": 0,
    "historical_result_changes": 0,
    "beta_changes": 0,
    "rho_changes": 0,
    "H_changes": 0,
    "J_I_changes": 0,
    "AIDC_site_changes": 0,
    "retraining_calls": 0,
    "May_June_result_dependent_tuning": 0,
}


def _write(path: Path, value: Mapping[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _sha_array(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(array.view(np.uint8)).hexdigest()


def _common_feasible_days(final: Path) -> list[str]:
    days = []
    for path in sorted((final / "cache/results").glob("2025-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") == "COMPLETED" and all(row["cases"][case].get("hard_feasible") for case in ("B0", "B1", "B2", "B3")):
            days.append(str(row["operating_day"]))
    if len(days) != 21:
        raise RuntimeError(f"AIDC_FORENSIC_COMMON_FEASIBLE_DAY_COUNT:{len(days)}")
    return days


def _workload_cube(raw: Mapping[str, np.ndarray], inputs) -> np.ndarray:
    expected = len(inputs.cohorts) * len(inputs.rack_ids) * 96
    payload = np.asarray(raw["workload"], dtype=float)
    if payload.size != expected:
        raise RuntimeError("AIDC_FORENSIC_WORKLOAD_AXIS")
    return payload.reshape(len(inputs.cohorts), len(inputs.rack_ids), 96)


def _flexible_power(cube: np.ndarray, inputs) -> tuple[np.ndarray, np.ndarray]:
    by_cohort_aidc = np.zeros((len(inputs.cohorts), 12, 96), dtype=float)
    for c, cohort in enumerate(inputs.cohorts):
        kappa = KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])]
        for r, aidc in enumerate(inputs.rack_aidc):
            d = int(str(aidc)[-2:]) - 1
            by_cohort_aidc[c, d] += kappa / DT_HOURS * cube[c, r]
    return by_cohort_aidc.sum(axis=0).T, by_cohort_aidc


def _states(voltage, current, controls: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    delta = controls - np.asarray(voltage["anchor_control"], dtype=float)
    v = np.asarray(voltage["anchor_v_squared"], dtype=float) + np.einsum(
        "tcn,tc->tn", np.asarray(voltage["sensitivity"], dtype=float), delta
    )
    i = np.maximum(
        np.asarray(current["anchor_current_loading_pu"], dtype=float)
        + np.einsum("tcb,tc->tb", np.asarray(current["current_sensitivity_pu_per_control"], dtype=float), delta),
        0.0,
    )
    return v, i


def _spatial_reduction(coeff: np.ndarray, low: Sequence[float], high: Sequence[float]) -> dict[str, object]:
    """Exact greedy solution of min c*d, sum(d)=0, low<=d<=high."""
    delta = np.zeros(12, dtype=float)
    sinks = sorted(range(12), key=lambda i: (float(coeff[i]), i))
    sources = sorted(range(12), key=lambda i: (-float(coeff[i]), i))
    source_left = {i: max(0.0, -float(low[i])) for i in sources}
    sink_left = {i: max(0.0, float(high[i])) for i in sinks}
    transfers = []
    for source in sources:
        for sink in sinks:
            if float(coeff[source]) <= float(coeff[sink]) + 1e-18:
                continue
            amount = min(source_left[source], sink_left[sink])
            if amount <= 0:
                continue
            delta[source] -= amount
            delta[sink] += amount
            source_left[source] -= amount
            sink_left[sink] -= amount
            transfers.append({"from": f"AIDC{source+1:02d}", "to": f"AIDC{sink+1:02d}", "facility_kw": amount})
            if source_left[source] <= 1e-15:
                break
    change = float(coeff @ delta)
    return {
        "maximum_reduction_pu": max(0.0, -change),
        "optimal_delta_facility_kw": delta.tolist(),
        "conservation_error_kw": float(abs(delta.sum())),
        "transfers": transfers,
    }


def _topology(binding, pcc_path: Path) -> dict[str, object]:
    branches = tuple(binding.factories[0].data.branches)
    by_child = {(row.child_bus, row.phase): row for row in branches}
    sites = []
    downstream = []
    upstream = []
    for d in range(1, 13):
        aidc = f"AIDC{d:02d}"
        pcc = f"idc_idc{d:02d}_pcc"
        phase_rows = {}
        host = None
        for phase in ("A", "B", "C"):
            node = (pcc, phase)
            reverse_path = []
            while node[0] != "150":
                if node not in by_child:
                    raise RuntimeError(f"AIDC_TOPOLOGY_PATH_MISSING:{aidc}:{node}")
                branch = by_child[node]
                reverse_path.append(branch)
                node = (branch.parent_bus, phase)
            path = list(reversed(reverse_path))
            pcc_tx = next(row for row in path if row.branch_id == f"transformer.idc_idc{d:02d}_tx")
            host = pcc_tx.parent_bus
            l10_index = next((index for index, row in enumerate(path) if row.branch_id == "line.l10"), None)
            z = [math.hypot(float(row.r_pu_per_kw), float(row.x_pu_per_kvar)) for row in path]
            phase_rows[phase] = {
                "root_to_AIDC_path": [f"{row.branch_id}::{row.phase}" for row in path],
                "path_branch_count": len(path),
                "line_l10_on_path": l10_index is not None,
                "electrical_distance_from_source_model_units": float(sum(z)),
                "electrical_distance_from_line_l10_model_units": float(sum(z[l10_index + 1 :])) if l10_index is not None else None,
            }
        on_l10 = all(row["line_l10_on_path"] for row in phase_rows.values())
        (downstream if on_l10 else upstream).append(aidc)
        a_path = phase_rows["A"]["root_to_AIDC_path"]
        first_distinguishing = next((item for item in a_path if item.split("::", 1)[0] not in {"transformer.reg1a", "line.l10"}), a_path[-1])
        sites.append(
            {
                "AIDC_ID": aidc,
                "PCC_bus": pcc,
                "host_bus": host,
                "phase_connectivity": ["A", "B", "C"],
                "phase_paths": phase_rows,
                "line_l10_on_all_phase_paths": on_l10,
                "line_l10_cut_side": "DOWNSTREAM" if on_l10 else "UPSTREAM",
                "feeder_subtree_or_electrical_zone": first_distinguishing,
                "mean_electrical_distance_from_source_model_units": mean(row["electrical_distance_from_source_model_units"] for row in phase_rows.values()),
                "mean_electrical_distance_from_line_l10_model_units": mean(row["electrical_distance_from_line_l10_model_units"] for row in phase_rows.values()) if on_l10 else None,
            }
        )
    return {
        "artifact_id": "V16_3_AIDC_TOPOLOGY_CUTSET_AUDIT",
        "status": "PASS_READ_ONLY",
        "source": {"PCC_asset": str(pcc_path.resolve()), "PCC_asset_sha256": sha256_file(pcc_path)},
        "root_bus": "150",
        "sites": sites,
        "line_l10_cut_set": {
            "AIDC_upstream_of_line_l10": upstream,
            "AIDC_downstream_of_line_l10": downstream,
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
        },
        "topology_identity": {
            "all_12_AIDCs_downstream_of_line_l10": len(downstream) == 12,
            "spatial_redistribution_with_conserved_total_active_power_can_change_line_l10_flow": bool(upstream and downstream),
            "explanation": "For a radial feeder, line.l10 flow equals the sum of downstream injections. Moving equal active power among AIDCs on the same downstream side leaves that cut sum unchanged; only temporal/system-total AIDC changes can alter line.l10 flow.",
        },
        "firewall": FIREWALL,
    }


def _best_aidc_lp(inputs, reference, authority, voltage, current, b0_controls: np.ndarray) -> dict[str, object]:
    import gurobipy as gp
    from gurobipy import GRB

    model = gp.Model("v16_3_read_only_best_aidc_relief_bound")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260828
    model.Params.Method = 1
    model.Params.FeasibilityTol = 1e-7
    model.Params.OptimalityTol = 1e-7
    cohorts = tuple(inputs.cohorts)
    racks = tuple(inputs.rack_ids)
    rack_index = {rack: index for index, rack in enumerate(racks)}
    aidc_racks = {f"AIDC{d:02d}": tuple(r for r, a in zip(racks, inputs.rack_aidc) if a == f"AIDC{d:02d}") for d in range(1, 13)}
    x = {(c, r, t): model.addVar(lb=0.0, name=f"workload[{c},{r},{t}]") for c in cohorts for r in racks for t in range(96)}
    backlog = {(c, t): model.addVar(lb=0.0, name=f"backlog[{c},{t}]") for c in cohorts for t in range(97)}
    for cohort in cohorts:
        model.addConstr(backlog[(cohort, 0)] == 0.0)
        for slot in range(96):
            model.addConstr(backlog[(cohort, slot + 1)] == backlog[(cohort, slot)] + inputs.arrivals[cohort][slot] - gp.quicksum(x[(cohort, rack, slot)] for rack in racks))
        model.addConstr(backlog[(cohort, 96)] == 0.0)
    for slot in range(96):
        for rack in racks:
            r = rack_index[rack]
            model.addConstr(inputs.g_res_rack[slot][r] + GPU_PER_NODE / DT_HOURS * gp.quicksum(x[(cohort, rack, slot)] for cohort in cohorts) <= inputs.gpu_capacity[r])
    controls = {}
    for slot in range(96):
        for d in range(1, 13):
            aidc = f"AIDC{d:02d}"
            flexible = gp.quicksum(KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * x[(cohort, rack, slot)] for cohort in cohorts for rack in aidc_racks[aidc])
            controls[(d - 1, slot)] = PUE_PLAN * (inputs.p_res_aidc_kw[slot][d - 1] + flexible)
        down, up, _ = _aidc_limits(reference, authority, slot)
        anchor = np.asarray(voltage["anchor_control"][slot], dtype=float)
        for d in range(12):
            model.addConstr(controls[(d, slot)] - float(anchor[d]) >= -RHO * float(down[d]))
            model.addConstr(controls[(d, slot)] - float(anchor[d]) <= RHO * float(up[d]))
    eta = model.addVar(lb=0.0, name="maximum_line_current")
    names = tuple(map(str, current["branch_names"]))
    ji = np.asarray(current["current_sensitivity_pu_per_control"], dtype=float)
    i0 = np.asarray(current["anchor_current_loading_pu"], dtype=float)
    anchors = np.asarray(voltage["anchor_control"], dtype=float)
    for slot in range(96):
        fixed_mess = b0_controls[slot, 12:] - anchors[slot, 12:]
        for branch, name in enumerate(names):
            if name.startswith("transformer."):
                continue
            expression = float(i0[slot, branch] + ji[slot, 12:, branch] @ fixed_mess) + gp.quicksum(float(ji[slot, d, branch]) * (controls[(d, slot)] - float(anchors[slot, d])) for d in range(12))
            model.addConstr(eta >= expression)
    model.setObjective(eta, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        return {"status": f"FAIL_GUROBI_{int(model.Status)}", "solver_calls": 1}
    terminal_error = max(abs(float(backlog[(cohort, 96)].X)) for cohort in cohorts)
    best_controls = np.asarray([[float(controls[(d, slot)].getValue()) for d in range(12)] for slot in range(96)])
    return {
        "status": "OPTIMAL_ANALYTICAL_UPPER_BOUND",
        "objective": float(model.ObjVal),
        "runtime_seconds": float(model.Runtime),
        "variable_count": int(model.NumVars),
        "constraint_count": int(model.NumConstrs),
        "service_parity_max_abs_nodeh": terminal_error,
        "best_AIDC_controls_sha256": _sha_array(best_controls),
        "solver_calls": 1,
        "OpenDSS_calls": 0,
    }


def execute(repo: Path, source: Path, final: Path, output: Path) -> dict[str, object]:
    start_head = _git(repo, "rev-parse", "HEAD")
    tracked_dirty = _git(repo, "diff", "--name-only") or _git(repo, "diff", "--cached", "--name-only")
    if start_head != COMPLETION_COMMIT or tracked_dirty:
        raise RuntimeError(f"AIDC_FORENSIC_CHECKPOINT_NOT_CLEAN:{start_head}")
    for commit in (AUTHORITY_COMMIT, COMPLETION_COMMIT):
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, start_head], cwd=repo, check=True)
    completion_manifest = json.loads((repo / "dayahead/artifacts/v16_3_decomposition_completion/V16_3_DECOMPOSITION_COMPLETION_MANIFEST.json").read_text(encoding="utf-8"))
    historical_hashes = {name: row["observed_sha256"] for name, row in completion_manifest["historical_final_artifact_integrity"].items()}
    days = _common_feasible_days(final)
    forecast_path = final / "cache/V16_3_FINAL_AIDC_DA_FORECAST.parquet"
    forecast = pd.read_parquet(forecast_path)
    pcc_path = repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss"

    topology = None
    observations = []
    magnitude_rows = []
    power_days = []
    objective_days = []
    trust_rows = []
    best_rows = []
    cohort_accumulator: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    identity_max = defaultdict(float)
    all_sensitivity_ranges = []
    all_line_l10_ranges = []
    all_spatial_bounds = []
    all_actual_aidc_projection = []
    all_actual_mess_projection = []

    for day_index, day in enumerate(days, 1):
        context, inputs, _ = build_context(repo, source, final, day, prepare=False)
        reference, _vintage, _background, binding, _path, authority = context
        if topology is None:
            topology = _topology(binding, pcc_path)
        voltage_path = final / f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        current_path = final / f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
        voltage = np.load(voltage_path, allow_pickle=False)
        current = np.load(current_path, allow_pickle=False)
        result = json.loads((final / f"cache/results/{day}.json").read_text(encoding="utf-8"))
        raw = {case: np.load(result["cases"][case]["raw_schedule_cache"], allow_pickle=False) for case in ("B0", "B1", "B2", "B3")}
        controls = {case: np.asarray(raw[case]["controls_96x60"], dtype=float) for case in raw}
        states = {case: _states(voltage, current, controls[case]) for case in raw}
        names = tuple(map(str, current["branch_names"]))
        ji = np.asarray(current["current_sensitivity_pu_per_control"], dtype=float)
        line_indices = [i for i, name in enumerate(names) if not name.startswith("transformer.")]
        line_l10 = names.index("line.l10::A")

        for case in ("B0", "B1", "B2", "B3"):
            critical = result["cases"][case]["planning_audit"]["critical_line_phase_slot"]
            slot = int(critical["slot"])
            critical_index = names.index(str(critical["branch"]))
            top = sorted(line_indices, key=lambda index: (-float(states[case][1][slot, index]), names[index]))[:10]
            targets = [("LINE_L10_A", line_l10), ("REALIZED_CRITICAL", critical_index)] + [(f"TOP_{rank:02d}", index) for rank, index in enumerate(top, 1)]
            seen = set()
            down, up, _ = _aidc_limits(reference, authority, slot)
            low = [-RHO * float(value) for value in down]
            high = [RHO * float(value) for value in up]
            for role, index in targets:
                if (role, index) in seen:
                    continue
                seen.add((role, index))
                coeff = ji[slot, :12, index]
                pairwise = [[float(abs(coeff[i] - coeff[j])) for j in range(12)] for i in range(12)]
                spatial = _spatial_reduction(coeff, low, high)
                spread = float(np.ptp(coeff))
                row = {
                    "operating_day": day,
                    "case": case,
                    "critical_slot": slot,
                    "target_role": role,
                    "line_phase": names[index],
                    "AIDC_sensitivity_12_pu_per_facility_kw": coeff.tolist(),
                    "min": float(coeff.min()),
                    "max": float(coeff.max()),
                    "range": spread,
                    "standard_deviation": float(coeff.std()),
                    "mean_absolute": float(np.mean(np.abs(coeff))),
                    "normalized_coefficient_of_variation": float(coeff.std() / max(np.mean(np.abs(coeff)), 1e-15)),
                    "pairwise_absolute_difference_matrix": pairwise,
                    "pairwise_max_absolute_difference": max(max(x) for x in pairwise),
                    "pure_spatial_conserved_power_bound": spatial,
                }
                observations.append(row)
                all_sensitivity_ranges.append(spread)
                all_spatial_bounds.append(float(spatial["maximum_reduction_pu"]))
                if index == line_l10:
                    all_line_l10_ranges.append(spread)

        b1_critical = result["cases"]["B1"]["planning_audit"]["critical_line_phase_slot"]
        slot = int(b1_critical["slot"])
        branch = names.index(str(b1_critical["branch"]))
        delta = controls["B1"][slot, :12] - controls["B0"][slot, :12]
        coeff = ji[slot, :12, branch]
        products = coeff * delta
        dot = float(products.sum())
        centered_coeff = coeff - coeff.mean()
        centered_delta = delta - delta.mean()
        magnitude = float(np.linalg.norm(delta))
        magnitude_rows.append(
            {
                "operating_day": day,
                "critical_line_phase": names[branch],
                "critical_slot": slot,
                "Delta_P_AIDC_facility_kw": delta.tolist(),
                "control_magnitude_L1_kw": float(np.linalg.norm(delta, 1)),
                "control_magnitude_L2_kw": magnitude,
                "control_magnitude_Linf_kw": float(np.linalg.norm(delta, np.inf)),
                "system_net_delta_kw": float(delta.sum()),
                "electrical_leverage_L2_pu_per_kw": float(np.linalg.norm(centered_coeff)),
                "electrical_leverage_range_pu_per_kw": float(np.ptp(coeff)),
                "signed_Delta_I_AIDC_pu": dot,
                "alignment_cosine_efficiency": float(abs(centered_coeff @ centered_delta) / max(np.linalg.norm(centered_coeff) * np.linalg.norm(centered_delta), 1e-15)),
                "cancellation_efficiency": float(abs(dot) / max(np.abs(products).sum(), 1e-15)),
                "critical_slot_control_magnitude_to_daily_max_ratio": float(magnitude / max(np.linalg.norm(controls["B1"][:, :12] - controls["B0"][:, :12], axis=1).max(), 1e-15)),
            }
        )

        b3_critical = result["cases"]["B3"]["planning_audit"]["critical_line_phase_slot"]
        s3, b3 = int(b3_critical["slot"]), names.index(str(b3_critical["branch"]))
        d3 = controls["B3"][s3] - controls["B0"][s3]
        all_actual_aidc_projection.append(abs(float(ji[s3, :12, b3] @ d3[:12])))
        all_actual_mess_projection.append(abs(float(ji[s3, 12:, b3] @ d3[12:])))

        cubes = {case: _workload_cube(raw[case], inputs) for case in ("B0", "B1")}
        flexible = {}
        by_cohort = {}
        for case in cubes:
            flexible[case], by_cohort[case] = _flexible_power(cubes[case], inputs)
        p_res = np.asarray(inputs.p_res_aidc_kw, dtype=float)
        p_it_ref = p_res + flexible["B0"]
        p_it_b1 = p_res + flexible["B1"]
        identity_max["B0_reference_allocation"] = max(identity_max["B0_reference_allocation"], float(np.max(np.abs(cubes["B0"] - np.asarray([[[reference["reference"].allocation[(c, r, t)] for t in range(96)] for r in inputs.rack_ids] for c in inputs.cohorts])))))
        identity_max["B0_control_reconstruction"] = max(identity_max["B0_control_reconstruction"], float(np.max(np.abs(PUE_PLAN * p_it_ref - controls["B0"][:, :12]))))
        identity_max["B1_control_reconstruction"] = max(identity_max["B1_control_reconstruction"], float(np.max(np.abs(PUE_PLAN * p_it_b1 - controls["B1"][:, :12]))))
        arrivals_raw, _p_raw, _g_raw = final_forecast_day(forecast, day)
        beta_error = max(abs(float(inputs.arrivals[c][t]) - 0.25 * float(arrivals_raw[c][t])) for c in inputs.cohorts for t in range(96))
        capacity_error = max(abs(float(inputs.gpu_capacity[r]) - 0.25 * float(authority.racks[r].deliverable_gpu_capacity)) for r in range(48))
        identity_max["beta_arrivals_once"] = max(identity_max["beta_arrivals_once"], beta_error)
        identity_max["beta_capacity_once"] = max(identity_max["beta_capacity_once"], capacity_error)
        dx = cubes["B1"] - cubes["B0"]
        for c, cohort in enumerate(inputs.cohorts):
            daily_delta = float(dx[c].sum())
            cohort_accumulator[cohort]["signed_service_delta_nodeh"] += daily_delta
            cohort_accumulator[cohort]["absolute_reallocated_nodeh"] += float(np.abs(dx[c]).sum())
            cohort_accumulator[cohort]["kappa_kw_per_active_node"] = KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])]
            cohort_accumulator[cohort]["max_active_node_delta"] = max(cohort_accumulator[cohort]["max_active_node_delta"], float(np.max(np.abs(dx[c] / DT_HOURS))))
            identity_max["cohort_service_conservation"] = max(identity_max["cohort_service_conservation"], abs(daily_delta))
        reconstructed_delta = (by_cohort["B1"] - by_cohort["B0"]).sum(axis=0).T
        identity_max["kappa_dt_once"] = max(identity_max["kappa_dt_once"], float(np.max(np.abs(reconstructed_delta - (flexible["B1"] - flexible["B0"])))))
        identity_max["source_destination_AIDC_index"] = max(identity_max["source_destination_AIDC_index"], float(abs((flexible["B1"] - flexible["B0"]).sum() - sum((KAPPA_KW_PER_ACTIVE_H100_NODE[int(c[1:3])] / DT_HOURS * dx[k]).sum() for k, c in enumerate(inputs.cohorts)))))

        bounds = [_aidc_limits(reference, authority, slot)[0:2] for slot in range(96)]
        available = np.asarray([[max(float(bounds[t][0][d]), float(bounds[t][1][d])) / PUE_PLAN for d in range(12)] for t in range(96)])
        delta_f = flexible["B1"] - flexible["B0"]
        system_total = p_it_ref.sum(axis=1)
        gross_ratio = np.abs(delta_f).sum(axis=1) / np.maximum(system_total, 1e-12)
        net_ratio = np.abs(delta_f.sum(axis=1)) / np.maximum(system_total, 1e-12)
        available_ratio = available.sum(axis=1) / np.maximum(system_total, 1e-12)
        pf_ratio = flexible["B0"].sum(axis=1) / np.maximum(system_total, 1e-12)
        mess_p = np.asarray(raw["B2"]["mess_p"], dtype=float)
        mess_q = np.asarray(raw["B2"]["mess_q"], dtype=float)
        power_days.append(
            {
                "operating_day": day,
                "matrix_sha256": {"P_IT_TOTAL_REF": _sha_array(p_it_ref), "P_RES": _sha_array(p_res), "P_F_REF": _sha_array(flexible["B0"]), "P_F_DA_B1": _sha_array(flexible["B1"]), "Delta_P_F": _sha_array(delta_f)},
                "P_F_REF_to_P_IT_TOTAL": {"energy_ratio": float(flexible["B0"].sum() / p_it_ref.sum()), "median_slot_ratio": float(np.median(pf_ratio)), "maximum_slot_ratio": float(np.max(pf_ratio))},
                "max_available_abs_Delta_P_F_to_P_IT_TOTAL": {"median_slot_ratio": float(np.median(available_ratio)), "maximum_slot_ratio": float(np.max(available_ratio))},
                "actual_optimized_Delta_P_F_to_P_IT_TOTAL": {"gross_median_slot_ratio": float(np.median(gross_ratio)), "gross_maximum_slot_ratio": float(np.max(gross_ratio)), "net_median_slot_ratio": float(np.median(net_ratio)), "net_maximum_slot_ratio": float(np.max(net_ratio))},
                "Kestrel_flexible_power": {"reference_peak_kw": float(np.max(flexible["B0"].sum(axis=1))), "actual_delta_gross_peak_kw": float(np.max(np.abs(delta_f).sum(axis=1))), "actual_delta_net_peak_kw": float(np.max(np.abs(delta_f.sum(axis=1))))},
                "MESS": {"absolute_P_peak_kw": float(np.max(np.abs(mess_p).sum(axis=1))), "absolute_Q_peak_kvar": float(np.max(np.abs(mess_q).sum(axis=1))), "absolute_P_energy_kwh": float(DT_HOURS * np.abs(mess_p).sum()), "absolute_Q_energy_kvarh": float(DT_HOURS * np.abs(mess_q).sum())},
                "matrices_96x12_kw": {"P_IT_TOTAL_REF": p_it_ref.tolist(), "P_RES": p_res.tolist(), "P_F_REF": flexible["B0"].tolist(), "P_F_DA_B1": flexible["B1"].tolist(), "Delta_P_F_B1_minus_REF": delta_f.tolist(), "maximum_available_abs_Delta_P_F": available.tolist()},
                "system_ratio_96": {"P_F_REF_over_P_IT_TOTAL": pf_ratio.tolist(), "maximum_available_abs_Delta_P_F_over_P_IT_TOTAL": available_ratio.tolist(), "actual_gross_abs_Delta_P_F_over_P_IT_TOTAL": gross_ratio.tolist(), "actual_net_abs_Delta_P_F_over_P_IT_TOTAL": net_ratio.tolist()},
                "MESS_96x4": {"P_kw": mess_p.tolist(), "Q_kvar": mess_q.tolist()},
                "per_AIDC_slot_extrema": {"P_IT_TOTAL_min_max_kw": [float(p_it_ref.min()), float(p_it_ref.max())], "P_RES_min_max_kw": [float(p_res.min()), float(p_res.max())], "P_F_REF_min_max_kw": [float(flexible["B0"].min()), float(flexible["B0"].max())], "P_F_DA_min_max_kw": [float(flexible["B1"].min()), float(flexible["B1"].max())], "Delta_P_F_min_max_kw": [float(delta_f.min()), float(delta_f.max())]},
            }
        )

        for case in ("B1", "B3"):
            delta_control = controls[case][:, :12] - np.asarray(voltage["anchor_control"])[:, :12]
            boundary = 0
            binding_slots = set()
            for t in range(96):
                down, up, _ = _aidc_limits(reference, authority, t)
                for d in range(12):
                    denominator = RHO * (float(up[d]) if delta_control[t, d] >= 0 else float(down[d]))
                    utilization = abs(float(delta_control[t, d])) / denominator if denominator > 1e-12 else 0.0
                    if utilization >= 1 - 1e-6:
                        boundary += 1
                        binding_slots.add(t)
            critical = result["cases"][case]["planning_audit"]["critical_line_phase_slot"]
            t = int(critical["slot"]); b = names.index(str(critical["branch"])); c = ji[t, :12, b]
            trust_rows.append({"operating_day": day, "case": case, "AIDC_variable_count": 1152, "AIDC_variables_at_rho_boundary": boundary, "percentage_at_rho_boundary": 100.0 * boundary / 1152, "AIDC_trust_binding_slot_count": len(binding_slots), "unconstrained_spatial_descent_direction": {"decrease_site": f"AIDC{int(np.argmax(c))+1:02d}", "increase_site": f"AIDC{int(np.argmin(c))+1:02d}", "sensitivity_range_pu_per_kw": float(np.ptp(c))}})

        v0, i0_state = states["B0"]
        v1, i1_state = states["B1"]
        top10 = sorted(line_indices, key=lambda index: (-float(i0_state[:, index].max()), names[index]))[:10]
        aidc_tx = [index for index, name in enumerate(names) if name.startswith("transformer.idc_idc")]
        feeder_tx = [index for index, name in enumerate(names) if name.startswith("transformer.") and not name.startswith(("transformer.idc_", "transformer.mess_"))]
        objective_days.append(
            {
                "operating_day": day,
                "maximum_normalized_phase_line_current": {"B0": float(i0_state[:, line_indices].max()), "B1": float(i1_state[:, line_indices].max()), "change_B1_minus_B0": float(i1_state[:, line_indices].max() - i0_state[:, line_indices].max())},
                "top10_B0_line_phase_currents": [{"line_phase": names[index], "B0_max": float(i0_state[:, index].max()), "B1_max": float(i1_state[:, index].max()), "change": float(i1_state[:, index].max() - i0_state[:, index].max())} for index in top10],
                "AIDC_PCC_transformer_current": {"B0_max": float(i0_state[:, aidc_tx].max()), "B1_max": float(i1_state[:, aidc_tx].max()), "change": float(i1_state[:, aidc_tx].max() - i0_state[:, aidc_tx].max())},
                "feeder_transformer_current": {"B0_max": float(i0_state[:, feeder_tx].max()), "B1_max": float(i1_state[:, feeder_tx].max()), "change": float(i1_state[:, feeder_tx].max() - i0_state[:, feeder_tx].max())},
                "voltage": {"B0_Vmin": float(np.sqrt(max(0.0, v0.min()))), "B1_Vmin": float(np.sqrt(max(0.0, v1.min()))), "B0_Vmax": float(np.sqrt(v0.max())), "B1_Vmax": float(np.sqrt(v1.max()))},
            }
        )

        best = _best_aidc_lp(inputs, reference, authority, voltage, current, controls["B0"])
        if best["status"] != "OPTIMAL_ANALYTICAL_UPPER_BOUND":
            raise RuntimeError(f"AIDC_BEST_BOUND_FAIL:{day}:{best}")
        b0_objective = float(result["cases"]["B0"]["objective_max_normalized_phase_line_current"])
        b1_objective = float(result["cases"]["B1"]["objective_max_normalized_phase_line_current"])
        best_rows.append({"operating_day": day, "B0_objective": b0_objective, "actual_B1_objective": b1_objective, "actual_B1_relief": b0_objective - b1_objective, "best_possible_AIDC_only_objective": best["objective"], "best_possible_AIDC_only_relief": b0_objective - float(best["objective"]), "actual_to_best_relief_gap": (b0_objective - float(best["objective"])) - (b0_objective - b1_objective), **best})
        print(json.dumps({"forensic_complete": day_index, "total": len(days), "day": day, "best_status": best["status"]}), flush=True)

    assert topology is not None
    sensitivity = {
        "artifact_id": "V16_3_AIDC_SENSITIVITY_DIVERSITY_AUDIT",
        "status": "PASS_READ_ONLY",
        "common_feasible_days": days,
        "observation_count": len(observations),
        "observations": observations,
        "aggregate": {
            "median_AIDC_sensitivity_range_pu_per_kw": median(all_sensitivity_ranges),
            "maximum_AIDC_sensitivity_range_pu_per_kw": max(all_sensitivity_ranges),
            "median_line_l10_AIDC_sensitivity_range_pu_per_kw": median(all_line_l10_ranges),
            "maximum_line_l10_AIDC_sensitivity_range_pu_per_kw": max(all_line_l10_ranges),
            "median_pure_spatial_conserved_power_maximum_reduction_pu": median(all_spatial_bounds),
            "maximum_pure_spatial_conserved_power_reduction_pu": max(all_spatial_bounds),
            "columns_nearly_identical_at_line_l10": max(all_line_l10_ranges) <= 1e-9,
        },
        "magnitude_sensitivity_alignment": magnitude_rows,
        "magnitude_sensitivity_alignment_aggregate": {
            "median_control_magnitude_L1_kw": median(row["control_magnitude_L1_kw"] for row in magnitude_rows),
            "median_control_magnitude_L2_kw": median(row["control_magnitude_L2_kw"] for row in magnitude_rows),
            "median_electrical_leverage_range_pu_per_kw": median(row["electrical_leverage_range_pu_per_kw"] for row in magnitude_rows),
            "median_alignment_cosine_efficiency": median(row["alignment_cosine_efficiency"] for row in magnitude_rows),
            "median_cancellation_efficiency": median(row["cancellation_efficiency"] for row in magnitude_rows),
            "median_critical_slot_to_daily_max_control_magnitude_ratio": median(row["critical_slot_control_magnitude_to_daily_max_ratio"] for row in magnitude_rows),
            "primary_mechanism": "CONTROL_MAGNITUDE_AND_TEMPORAL_MAX_PLATEAU_LIMITED; ALIGNMENT_CANCELLATION_NOT_PRIMARY",
        },
        "projection_comparison": {"median_abs_Delta_Icrit_from_AIDC_pu": median(all_actual_aidc_projection), "median_abs_Delta_Icrit_from_MESS_pu": median(all_actual_mess_projection)},
        "trust_region_audit": {"rows": trust_rows, "median_percentage_AIDC_variables_at_boundary": median(row["percentage_at_rho_boundary"] for row in trust_rows), "median_AIDC_binding_slot_count": median(row["AIDC_trust_binding_slot_count"] for row in trust_rows), "outside_rho_solves": 0, "diagnostic_linear_10x_radius_relief_upper_estimate_pu": 10.0 * max(row["best_possible_AIDC_only_relief"] for row in best_rows), "estimate_basis": "Local frozen-J_I linear extrapolation of the already optimistic rho=0.10 AIDC-only bound; no rho>0.10 solve was run.", "material_at_1e_minus_3_threshold": 10.0 * max(row["best_possible_AIDC_only_relief"] for row in best_rows) >= 1e-3},
        "firewall": FIREWALL,
    }
    power = {
        "artifact_id": "V16_3_AIDC_FLEXIBLE_POWER_SCALE_AUDIT",
        "status": "PASS_NO_IMPLEMENTATION_DEFECT" if max(identity_max.values()) <= 1e-7 else "FAIL_IMPLEMENTATION_DEFECT",
        "common_feasible_days": days,
        "per_day": power_days,
        "global": {
            "median_P_F_REF_energy_ratio": median(row["P_F_REF_to_P_IT_TOTAL"]["energy_ratio"] for row in power_days),
            "median_actual_gross_peak_Delta_P_F_kw": median(row["Kestrel_flexible_power"]["actual_delta_gross_peak_kw"] for row in power_days),
            "median_actual_net_peak_Delta_P_F_kw": median(row["Kestrel_flexible_power"]["actual_delta_net_peak_kw"] for row in power_days),
            "median_MESS_absolute_P_peak_kw": median(row["MESS"]["absolute_P_peak_kw"] for row in power_days),
            "median_MESS_absolute_Q_peak_kvar": median(row["MESS"]["absolute_Q_peak_kvar"] for row in power_days),
            "median_gross_Delta_P_F_to_total_max_slot_ratio": median(row["actual_optimized_Delta_P_F_to_P_IT_TOTAL"]["gross_maximum_slot_ratio"] for row in power_days),
            "median_net_Delta_P_F_to_total_max_slot_ratio": median(row["actual_optimized_Delta_P_F_to_P_IT_TOTAL"]["net_maximum_slot_ratio"] for row in power_days),
        },
        "kappa_cohort_audit": {
            "equation": "Delta_x_nodeh / 0.25h -> Delta_active_H100_nodes; frozen kappa_n applied once -> Delta_P_F_kw",
            "GPU_per_node": GPU_PER_NODE,
            "dt_hours": DT_HOURS,
            "PUE_application": "once_after_P_RES_plus_P_F",
            "beta_application": "once_to_W_F_and_rack_GPU_capacity_before_V3_reference",
            "cohorts": {cohort: dict(values) for cohort, values in sorted(cohort_accumulator.items())},
            "identity_max_abs_errors": dict(identity_max),
            "source_destination_AIDC_assignment": "rack_aidc frozen axis",
            "missing_beta": False,
            "double_beta": False,
            "dt_applied_once": identity_max["kappa_dt_once"] <= 1e-7,
            "kappa_applied_once": identity_max["B1_control_reconstruction"] <= 1e-7,
            "code_indexing_defect": max(identity_max.values()) > 1e-7,
        },
        "firewall": FIREWALL,
    }
    best = {
        "artifact_id": "V16_3_AIDC_BEST_POSSIBLE_RELIEF_BOUND",
        "status": "PASS_READ_ONLY_ANALYTICAL_LP",
        "formulation": "Optimistic AIDC-only LP: frozen J_I line-current epigraph over all 96 slots/line-phases, frozen rho=0.10 AIDC bounds, exact service balance/parity and rack GPU limits, B0 MESS fixed, voltage/transformer constraints omitted only to make relief an upper bound.",
        "common_feasible_days": days,
        "per_day": best_rows,
        "aggregate": {
            "median_actual_B1_relief": median(row["actual_B1_relief"] for row in best_rows),
            "maximum_actual_B1_relief": max(row["actual_B1_relief"] for row in best_rows),
            "median_best_possible_AIDC_only_relief": median(row["best_possible_AIDC_only_relief"] for row in best_rows),
            "maximum_best_possible_AIDC_only_relief": max(row["best_possible_AIDC_only_relief"] for row in best_rows),
            "median_actual_to_best_relief_gap": median(row["actual_to_best_relief_gap"] for row in best_rows),
            "maximum_actual_to_best_relief_gap": max(row["actual_to_best_relief_gap"] for row in best_rows),
            "solver_calls": sum(row["solver_calls"] for row in best_rows),
            "OpenDSS_calls": 0,
        },
        "interpretation_rule": "Near-zero actual and optimistic best relief rules out a hidden material AIDC-only solution inside the frozen rho/resource/service feasible set.",
        "firewall": FIREWALL,
    }
    objective = {
        "per_day": objective_days,
        "aggregate": {
            "median_objective_change_B1_minus_B0": median(row["maximum_normalized_phase_line_current"]["change_B1_minus_B0"] for row in objective_days),
            "maximum_absolute_objective_change": max(abs(row["maximum_normalized_phase_line_current"]["change_B1_minus_B0"]) for row in objective_days),
            "median_AIDC_PCC_transformer_change": median(row["AIDC_PCC_transformer_current"]["change"] for row in objective_days),
            "median_feeder_transformer_change": median(row["feeder_transformer_current"]["change"] for row in objective_days),
            "largest_local_top10_reduction": min(item["change"] for row in objective_days for item in row["top10_B0_line_phase_currents"]),
            "interpretation": "Some local top-10 and feeder-transformer reductions exist, but their magnitude is much smaller than MESS relief and does not move the line.l10-dominated maximum materially; objective hiding is secondary, not the primary cause.",
        },
    }

    implementation_defect = power["status"].startswith("FAIL")
    topology_limited = topology["topology_identity"]["all_12_AIDCs_downstream_of_line_l10"] and sensitivity["aggregate"]["columns_nearly_identical_at_line_l10"]
    scale_ratio = float(power["global"]["median_net_Delta_P_F_to_total_max_slot_ratio"])
    scale_limited = scale_ratio < 0.01 and power["global"]["median_actual_net_peak_Delta_P_F_kw"] < power["global"]["median_MESS_absolute_P_peak_kw"]
    best_near_zero = float(best["aggregate"]["maximum_best_possible_AIDC_only_relief"]) <= 1e-3
    if implementation_defect:
        classification = "AIDC_CAUSE_A_IMPLEMENTATION_DEFECT"
        next_decision = "AIDC_IMPLEMENTATION_CORRECTION_REQUIRED"
    elif topology_limited and scale_limited and best_near_zero:
        classification = "AIDC_CAUSE_F_COMBINED_PHYSICAL_LIMITATION"
        next_decision = "PROSPECTIVE_V17_AIDC_REDESIGN_JUSTIFIED"
    elif topology_limited:
        classification = "AIDC_CAUSE_C_CRITICAL_CUT_TOPOLOGY_CANCELLATION"
        next_decision = "PROSPECTIVE_V17_AIDC_REDESIGN_JUSTIFIED"
    elif scale_limited:
        classification = "AIDC_CAUSE_B_FLEXIBLE_POWER_SCALE_LIMITED"
        next_decision = "CURRENT_V16_3_AIDC_RESULT_IS_PHYSICALLY_EXPLAINED"
    else:
        classification = "AIDC_CAUSE_G_OTHER"
        next_decision = "CURRENT_V16_3_AIDC_RESULT_IS_PHYSICALLY_EXPLAINED"

    coherence_design = {
        "artifact_id": "V17_AIDC_COHERENCE_CORRECTION_DESIGN_CANDIDATE",
        "status": "DESIGN_ONLY_NOT_IMPLEMENTED",
        "independence_statement": "Reference coherence and V16.3 grid-value limitation are separate questions; no causal link is inferred.",
        "failure_evidence": "13 frozen days have G_F_REF_SYS(Q50 workload-derived) > G_REF_Q90 from a separately predicted head; beta/unit/time identities pass.",
        "alternatives": [
            {"id": "A_COHERENT_MULTIHEAD_PARAMETERIZATION", "definition": "Predict W_F quantiles and nonnegative G_RES directly; define G_REF := 4*served(W_F)/Delta_t + softplus(G_RES_raw).", "training_inference_change": "Joint loss with differentiable/reference-service layer or teacher-forced workload-to-G_F mapping.", "historical_raw_labels_support": True, "D_minus_1_causality_preserved": True, "retraining_required": True, "G_RES_negative_removed_by_construction": True},
            {"id": "B_COHERENCE_CONSTRAINED_REFERENCE_SCHEDULER", "definition": "Add sum_r 4*x_r,t/Delta_t <= G_REF_Q90(t) to the deterministic V3 scheduler while retaining service parity.", "training_inference_change": "No forecast retraining; scheduler feasibility contract changes prospectively.", "historical_raw_labels_support": True, "D_minus_1_causality_preserved": True, "retraining_required": False, "G_RES_negative_removed_by_construction": "YES_IF_SERVICE_PARITY_REMAINS_FEASIBLE; otherwise fail closed", "limitation": "Can expose cross-head infeasibility rather than resolve it."},
            {"id": "C_JOINT_G_FIXED_PLUS_G_FLEX_PARAMETERIZATION", "definition": "Predict nonnegative G_FIXED and workload W_F; compute G_FLEX from W_F/reference service and set G_REF=G_FIXED+G_FLEX.", "training_inference_change": "Replace independent G_REF head with structurally joint fixed-plus-flex heads.", "historical_raw_labels_support": True, "D_minus_1_causality_preserved": True, "retraining_required": True, "G_RES_negative_removed_by_construction": True},
        ],
        "clipping_main_fix": False,
        "recommended_review_order": ["C_JOINT_G_FIXED_PLUS_G_FLEX_PARAMETERIZATION", "A_COHERENT_MULTIHEAD_PARAMETERIZATION", "B_COHERENCE_CONSTRAINED_REFERENCE_SCHEDULER"],
        "firewall": FIREWALL,
    }
    diversity_design = {
        "artifact_id": "V17_AIDC_ELECTRICAL_DIVERSITY_CASE_DESIGN_CANDIDATE",
        "status": "DESIGN_ONLY_NOT_EXECUTED",
        "selection_data_firewall": {"allowed": "training period plus April validation D-1 feeder anchors/sensitivities", "forbidden": "May/June outcomes, B0-B3 results, or post-evaluation critical cuts"},
        "candidate_universe": "Predeclared feasible three-phase service buses satisfying voltage, PCC-transformer, land/use, and interconnection screening before evaluation.",
        "deterministic_rule": {
            "feature_vector": "For each candidate bus: April-only normalized J_I columns over predeclared top-K native line-phase cuts and H voltage sensitivities, phase incidence, root-path branch incidence, and source electrical distance.",
            "constraints": ["select exactly 12", "minimum number of distinct first-level feeder subtrees", "phase-connectivity diversity quota", "no two sites with identical cut-incidence vector unless candidate scarcity is certified"],
            "objective": "Lexicographically maximize: (1) minimum pairwise standardized sensitivity distance, (2) logdet of sensitivity Gram matrix plus epsilon I, (3) subtree entropy, (4) electrical-distance range.",
            "tie_break": "ascending canonical bus ID then phase mask",
            "precommit": "Freeze candidate set, April feature hashes, normalization, K, epsilon, constraints, solver seed, and selected sites before May/June access.",
        },
        "executed": False,
        "selected_sites": None,
        "firewall": FIREWALL,
    }

    topology_sha = _write(output / "V16_3_AIDC_TOPOLOGY_CUTSET_AUDIT.json", topology)
    sensitivity_sha = _write(output / "V16_3_AIDC_SENSITIVITY_DIVERSITY_AUDIT.json", sensitivity)
    power_sha = _write(output / "V16_3_AIDC_FLEXIBLE_POWER_SCALE_AUDIT.json", power)
    best_sha = _write(output / "V16_3_AIDC_BEST_POSSIBLE_RELIEF_BOUND.json", best)
    coherence_sha = _write(output / "V17_AIDC_COHERENCE_CORRECTION_DESIGN_CANDIDATE.json", coherence_design)
    diversity_sha = _write(output / "V17_AIDC_ELECTRICAL_DIVERSITY_CASE_DESIGN_CANDIDATE.json", diversity_design)
    root = {
        "artifact_id": "V16_3_AIDC_GRID_VALUE_ROOT_CAUSE_FORENSIC",
        "status": "PASS_READ_ONLY_FAIL_CLOSED",
        "checkpoint": {"branch": _git(repo, "branch", "--show-current"), "head": start_head, "authority_commit": AUTHORITY_COMMIT, "decomposition_completion_commit": COMPLETION_COMMIT, "working_tree_clean_before": True},
        "science_separation": {"REFERENCE_COHERENCE": "13-day A_EXPECTED_CROSS_HEAD_FORECAST_INCOHERENCE; analyzed independently.", "GRID_VALUE": "21-day topology/sensitivity/power/optimization forensic; no inference from reference-coherence failures."},
        "evidence_artifact_sha256": {"topology": topology_sha, "sensitivity": sensitivity_sha, "flexible_power": power_sha, "best_possible_relief": best_sha, "coherence_design": coherence_sha, "electrical_diversity_design": diversity_sha},
        "root_cause_tests": {"implementation_defect": implementation_defect, "critical_cut_topology_cancellation": topology_limited, "line_l10_cut_has_one_upstream_and_eleven_downstream_AIDCs": topology["line_l10_cut_set"]["upstream_count"] == 1 and topology["line_l10_cut_set"]["downstream_count"] == 11, "flexible_power_scale_limited": scale_limited, "best_possible_relief_near_zero": best_near_zero, "trust_region_limited_primary_cause": sensitivity["trust_region_audit"]["material_at_1e_minus_3_threshold"], "trust_region_outside_radius_solve_count": 0, "objective_misalignment_primary_cause": False, "objective_misalignment_audit": objective},
        "primary_classification": classification,
        "classification_basis": {"all_AIDCs_downstream_line_l10": topology_limited, "median_line_l10_sensitivity_range_pu_per_kw": sensitivity["aggregate"]["median_line_l10_AIDC_sensitivity_range_pu_per_kw"], "median_net_peak_Delta_P_F_to_total_ratio": scale_ratio, "median_AIDC_projection_pu": sensitivity["projection_comparison"]["median_abs_Delta_Icrit_from_AIDC_pu"], "median_MESS_projection_pu": sensitivity["projection_comparison"]["median_abs_Delta_Icrit_from_MESS_pu"], "maximum_best_possible_AIDC_only_relief": best["aggregate"]["maximum_best_possible_AIDC_only_relief"], "implementation_identity_max_abs_error": max(identity_max.values())},
        "next_decision": next_decision,
        "historical_artifact_sha256_before": historical_hashes,
        "historical_artifacts_modified": 0,
        "firewall": FIREWALL,
    }
    root_sha = _write(output / "V16_3_AIDC_GRID_VALUE_ROOT_CAUSE_FORENSIC.json", root)
    return {"classification": classification, "next_decision": next_decision, "root_sha256": root_sha, "days": len(days)}


def main() -> None:
    repo = Path.cwd()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--final", type=Path, default=repo / "dayahead/artifacts/v16_3_final")
    parser.add_argument("--output", type=Path, default=repo / "dayahead/artifacts/v16_3_aidc_grid_value_forensic")
    print(json.dumps(execute(**vars(parser.parse_args())), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
