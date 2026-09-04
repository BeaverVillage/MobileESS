"""Build the pre-repair V35R2 Apr-01--20 current and control diagnostics.

This tool never invokes an optimizer.  Fresh OpenDSS is restricted by an
explicit guard to Apr-01, Apr-10, and Apr-20 and is used only for frozen
single-slot perturbations.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.formulation import PF_TAN, materialize_formulation_data
from dayahead.v28r2.opendss_backend import _branch_measurement, _voltage_vector
from dayahead.v28r2.opendss_mapping import (
    FeederAssets,
    apply_frozen_native_state,
    apply_trajectory_slot,
    compile_clean_engine,
)
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v35.execution import (
    DEFAULT_SERVICE_MAPPING,
    DEFAULT_SOURCE_REPO,
    MESS_INITIAL,
    _electrical_context,
    _service_mapping,
)
from dayahead.v35.storage import atomic_json, sha256_file
from dayahead.v35r2.forensic import (
    APR01_20,
    CASES,
    DIAGNOSTIC_DAYS,
    central_slope,
    critical_identity,
    critical_index,
    effect_metrics,
    electrical_diversity,
    polygon_loading,
    q_exploit_detect,
    require_apr01_20,
    require_diagnostic_day,
    residual_metrics,
)


SOURCE = REPO / "dayahead/artifacts/v35_april_may_final"
CACHE = REPO / "dayahead/cache/v35"
PHASE = "APR01_20_AC_FIDELITY_CALIBRATION"
OUTPUT = REPO / "dayahead/artifacts/v35r2_aidc_mess_forensic"
START_HEAD = "7d8ec6eaae138782826b9fd87428c4a3874c35be"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _case_root(day: str, case: str) -> Path:
    require_apr01_20(day)
    if case not in CASES:
        raise ValueError(f"V35R2_CASE:{case}")
    return CACHE / PHASE / day / case


def _npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {name: np.asarray(payload[name]) for name in payload.files}


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _line_mask(names: np.ndarray) -> np.ndarray:
    return np.asarray([
        not str(name).startswith("transformer.") and not is_dominated_mess_current_row(str(name))
        for name in names
    ], dtype=bool)


def build_stored_current_authority() -> dict[str, object]:
    """Stream the complete 2,019,840-cell line-current match table."""

    raw_path = OUTPUT / "V35R2_COMMON_CURRENT_FIDELITY.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    residual_chunks: list[np.ndarray] = []
    critical_rows: list[dict[str, object]] = []
    effect_rows: dict[str, list[dict[str, object]]] = {"AIDC": [], "MESS": []}
    identity = Counter()
    critical_plan = Counter()
    critical_fresh = Counter()
    with raw_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "day", "case", "slot", "branch", "phase", "schedule_SHA256",
            "Planning_normalized_line_current", "Fresh_normalized_line_current",
            "E_I_SIGNED", "E_I_ABS",
        ])
        for day in APR01_20:
            print(f"stored-current {day}", flush=True)
            result = _load(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json")
            loaded: dict[str, tuple[dict[str, np.ndarray], dict[str, np.ndarray]]] = {}
            for case in CASES:
                root = _case_root(day, case)
                plan = _npz(root / "PLANNING_GRID.npz")
                fresh = _npz(root / "fresh/OPENDSS_PHASE_ARRAYS.npz")
                for axis in ("branch_names", "branch_phases"):
                    if not np.array_equal(plan[axis].astype(str), fresh[axis].astype(str)):
                        raise RuntimeError(f"V35R2_CURRENT_AXIS_IDENTITY:{day}:{case}:{axis}")
                names = plan["branch_names"].astype(str)
                phases = plan["branch_phases"].astype(str)
                mask = _line_mask(names)
                p = np.asarray(plan["phase_current_loading_pu"], dtype=float)
                f = np.asarray(fresh["phase_current_loading_pu"], dtype=float)
                residual_chunks.append((f[:, mask] - p[:, mask]).ravel())
                schedule_sha = str(result["cases"][case]["combined_schedule_sha256"])
                line_indices = np.flatnonzero(mask)
                for slot in range(96):
                    for index in line_indices:
                        signed = float(f[slot, index] - p[slot, index])
                        writer.writerow([
                            day, case, slot, names[index], phases[index], schedule_sha,
                            repr(float(p[slot, index])), repr(float(f[slot, index])),
                            repr(signed), repr(abs(signed)),
                        ])
                p_slot, p_index, p_value = critical_index(p, mask)
                f_slot, f_index, f_value = critical_index(f, mask)
                label = critical_identity(
                    (p_slot, str(names[p_index]), str(phases[p_index])),
                    (f_slot, str(names[f_index]), str(phases[f_index])),
                )
                identity[label] += 1
                critical_plan[f"{names[p_index]}::{phases[p_index]}"] += 1
                critical_fresh[f"{names[f_index]}::{phases[f_index]}"] += 1
                critical_rows.append({
                    "day": day,
                    "case": case,
                    "schedule_SHA256": schedule_sha,
                    "Planning_critical_line": names[p_index],
                    "Planning_critical_phase": phases[p_index],
                    "Planning_critical_slot": p_slot,
                    "Planning_critical_loading": p_value,
                    "Fresh_critical_line": names[f_index],
                    "Fresh_critical_phase": phases[f_index],
                    "Fresh_critical_slot": f_slot,
                    "Fresh_critical_loading": f_value,
                    "identity": label,
                })
                loaded[case] = (plan, fresh)

            for resource, comparisons in {
                "AIDC": (("B0", "B1", "B1-B0"), ("B2", "B3", "B3-B2")),
                "MESS": (("B0", "B2", "B2-B0"), ("B1", "B3", "B3-B1")),
            }.items():
                for off, on, comparison in comparisons:
                    po, fo = loaded[off]
                    pn, fn = loaded[on]
                    names = po["branch_names"].astype(str)
                    mask = _line_mask(names)
                    metrics = effect_metrics(
                        po["phase_current_loading_pu"][:, mask],
                        pn["phase_current_loading_pu"][:, mask],
                        fo["phase_current_loading_pu"][:, mask],
                        fn["phase_current_loading_pu"][:, mask],
                    )
                    case_effect = result["effects"][comparison]
                    effect_rows[resource].append({
                        "day": day,
                        "comparison": comparison,
                        **metrics,
                        "Planning_rho_delta": case_effect["planning_rho_delta"],
                        "Fresh_rho_delta": case_effect["fresh_rho_AC_delta"],
                        "Planning_effect_direction": np.sign(float(case_effect["planning_rho_delta"])),
                        "Fresh_effect_direction": np.sign(float(case_effect["fresh_rho_AC_delta"])),
                    })
    all_residuals = np.concatenate(residual_chunks)
    summary = residual_metrics(all_residuals, np.zeros_like(all_residuals))
    summary.update({
        "artifact_id": "V35R2_PRE_REPAIR_COMMON_CURRENT_FIDELITY_V1",
        "status": "DIAGNOSE",
        "scope": [APR01_20[0], APR01_20[-1]],
        "case_days": 80,
        "raw_csv": str(raw_path.resolve()),
        "raw_csv_SHA256": sha256_file(raw_path),
        "raw_csv_bytes": raw_path.stat().st_size,
        "critical_identity_counts": dict(identity),
        "critical_identity_exact_rate": identity["EXACT_LINE_PHASE_SLOT"] / 80.0,
        "Planning_critical_asset_counts": dict(critical_plan),
        "Fresh_critical_asset_counts": dict(critical_fresh),
    })
    _write_csv(OUTPUT / "V35R2_CRITICAL_BRANCH_AUDIT.csv", critical_rows)
    _write_csv(OUTPUT / "V35R2_EFFECT_FIDELITY_AIDC.csv", effect_rows["AIDC"])
    _write_csv(OUTPUT / "V35R2_EFFECT_FIDELITY_MESS.csv", effect_rows["MESS"])
    atomic_json(OUTPUT / "V35R2_COMMON_CURRENT_FIDELITY_SUMMARY.json", summary)
    return summary


def _base_trajectory(day: str, aidc: Mapping[str, np.ndarray]) -> FrozenTrajectory:
    locations = np.repeat(
        np.asarray([[MESS_INITIAL[f"MESS{index:02d}"] for index in range(1, 5)]], dtype="U64"),
        96,
        axis=0,
    )
    return FrozenTrajectory(
        day,
        "DAYAHEAD",
        "B0",
        np.asarray(aidc["AIDC_P_kw"], dtype=float),
        np.asarray(aidc["AIDC_Q_kvar"], dtype=float),
        np.zeros((96, 4), dtype=float),
        np.zeros((96, 4), dtype=float),
        ("MESS01", "MESS02", "MESS03", "MESS04"),
        locations,
        "0" * 64,
    )


def _changed_trajectory(
    base: FrozenTrajectory,
    *,
    slot: int,
    aidc_index: int | None = None,
    aidc_delta_p: float = 0.0,
    service: str | None = None,
    mess_p: float = 0.0,
    mess_q: float = 0.0,
) -> FrozenTrajectory:
    aidc_p = np.array(base.pcc_p_kw, copy=True)
    aidc_q = np.array(base.pcc_q_kvar, copy=True)
    p = np.array(base.mess_p_kw, copy=True)
    q = np.array(base.mess_q_kvar, copy=True)
    locations = np.array(base.mess_locations_96x4, copy=True)
    if aidc_index is not None:
        aidc_p[slot, aidc_index] += float(aidc_delta_p)
        aidc_q[slot, aidc_index] += float(aidc_delta_p) * PF_TAN
    if service is not None:
        locations[slot, 0] = str(service)
        p[slot, 0] = float(mess_p)
        q[slot, 0] = float(mess_q)
    digest = hashlib.sha256(
        json.dumps({
            "day": base.day,
            "slot": slot,
            "aidc_index": aidc_index,
            "aidc_delta_p": aidc_delta_p,
            "service": service,
            "mess_p": mess_p,
            "mess_q": mess_q,
        }, sort_keys=True).encode()
    ).hexdigest()
    return FrozenTrajectory(
        base.day,
        base.namespace,
        base.case,
        aidc_p,
        aidc_q,
        p,
        q,
        base.mess_ids,
        locations,
        digest,
    )


def _fresh_snapshot(
    odd: object,
    adapter: Mapping[str, object],
    electrical: object,
    voltage: object,
    branches: tuple[object, ...],
    nodes: tuple[str, ...],
    trajectory: FrozenTrajectory,
    slot: int,
) -> tuple[np.ndarray, np.ndarray]:
    trajectory.validate()
    apply_trajectory_slot(odd, adapter, electrical, trajectory, slot)
    apply_frozen_native_state(odd, voltage, slot)
    odd.Solution.SolveSnap()
    if not bool(odd.Solution.Converged()):
        raise RuntimeError(f"V35R2_FRESH_DIAGNOSTIC_NONCONVERGENCE:{trajectory.day}:{slot}")
    current = np.asarray([_branch_measurement(odd, branch)[1] for branch in branches], dtype=float)
    return current, _voltage_vector(odd, nodes)


def _control_vector(
    controls: tuple[str, ...],
    aidc_p: np.ndarray,
    slot: int,
    *,
    service: str | None = None,
    mess_p: float = 0.0,
    mess_q: float = 0.0,
) -> np.ndarray:
    result = []
    for name in controls:
        if name.startswith("aidc_load_kw["):
            result.append(float(aidc_p[slot, int(name[17:-1]) - 1]))
        elif name.startswith("mess_p_kw["):
            result.append(float(mess_p) if name[10:-1] == service else 0.0)
        elif name.startswith("mess_q_kvar["):
            result.append(float(mess_q) if name[12:-1] == service else 0.0)
        else:
            raise RuntimeError(f"V35R2_CONTROL_AXIS:{name}")
    return np.asarray(result, dtype=float)


def _planning_snapshot(coefficient: object, controls: np.ndarray) -> dict[str, np.ndarray]:
    p = coefficient.flow_p_constant + coefficient.flow_p_matrix @ controls
    q = coefficient.flow_q_constant + coefficient.flow_q_matrix @ controls
    current = coefficient.current_constant + coefficient.current_matrix.T @ controls
    ratings = np.asarray(coefficient.branch_limits, dtype=float)
    return {
        "current_affine": current,
        "flow_p": p,
        "flow_q": q,
        "current_exact_flow": np.hypot(p, q) / ratings,
        "current_polygon": polygon_loading(p, q, ratings),
    }


def _mapping_rows(
    mapping: Mapping[str, str],
    branches: tuple[object, ...],
    fingerprints: Mapping[str, np.ndarray],
) -> list[dict[str, object]]:
    parent: dict[tuple[str, str], object] = {
        (str(branch.child_bus), str(branch.phase)): branch for branch in branches
    }

    def path(host: str, phase: str) -> list[str]:
        result: list[str] = []
        node = (str(host).lower(), phase)
        seen = set()
        while node[0] != "150" and node not in seen:
            seen.add(node)
            branch = parent.get(node)
            if branch is None:
                break
            result.append(str(branch.branch_id))
            node = (str(branch.parent_bus), phase)
        return list(reversed(result))

    rows = []
    for service in sorted(mapping):
        paths = {phase: path(mapping[service], phase) for phase in "ABC"}
        vector = np.asarray(fingerprints[service], dtype=float)
        rows.append({
            "road_service_node": service,
            "electrical_PCC": mapping[service],
            "phase_support": "ABC",
            "topological_distance_edges_mean": float(np.mean([len(value) for value in paths.values()])),
            "feeder_path_A": ">".join(paths["A"]),
            "feeder_path_B": ">".join(paths["B"]),
            "feeder_path_C": ">".join(paths["C"]),
            "P_sensitivity_inf_norm": float(np.max(np.abs(vector[0::2]))),
            "Q_sensitivity_inf_norm": float(np.max(np.abs(vector[1::2]))),
            "sensitivity_fingerprint_SHA256": hashlib.sha256(vector.tobytes()).hexdigest(),
        })
    return rows


def run_fresh_diagnostics() -> dict[str, object]:
    finite_days: dict[str, object] = {}
    q_days: dict[str, object] = {}
    static_rows: list[dict[str, object]] = []
    aidc_rows: list[dict[str, object]] = []
    mapping = _service_mapping(DEFAULT_SERVICE_MAPPING)
    fingerprints: dict[str, list[np.ndarray]] = defaultdict(list)
    mapping_audit_rows: list[dict[str, object]] | None = None

    for day in DIAGNOSTIC_DAYS:
        require_diagnostic_day(day)
        print(f"fresh-diagnostic {day}: materializing formulation", flush=True)
        started = time.perf_counter()
        data = materialize_formulation_data(DEFAULT_SOURCE_REPO, day, disable_legacy_mess_source=True)
        electrical = _electrical_context(REPO, DEFAULT_SOURCE_REPO, CACHE, PHASE, day, data)
        try:
            coefficients = tuple(
                slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
                for slot in range(96)
            )
            b0 = _npz(_case_root(day, "B0") / "DAYAHEAD_AIDC.npz")
            stored_plan = _npz(_case_root(day, "B0") / "PLANNING_GRID.npz")
            stored_fresh = _npz(_case_root(day, "B0") / "fresh/OPENDSS_PHASE_ARRAYS.npz")
            names = stored_plan["branch_names"].astype(str)
            phases = stored_plan["branch_phases"].astype(str)
            line_mask = _line_mask(names)
            slot, critical_branch, _ = critical_index(stored_plan["phase_current_loading_pu"], line_mask)
            coefficient = coefficients[slot]
            controls = tuple(map(str, electrical.voltage["control_names"]))
            branches = tuple(electrical.legacy_context[3].factories[slot].data.branches)
            nodes = tuple(map(str, electrical.voltage["node_names"]))
            base = _base_trajectory(day, b0)
            odd, adapter = compile_clean_engine(FeederAssets.from_repo(DEFAULT_SOURCE_REPO))
            print(f"fresh-diagnostic {day}: slot={slot} branch={names[critical_branch]}", flush=True)
            try:
                finite: list[dict[str, object]] = []
                for aidc_id in ("AIDC01", "AIDC06", "AIDC12"):
                    index = int(aidc_id[-2:]) - 1
                    fresh_by_sign = {}
                    for sign in (-1.0, 1.0):
                        trajectory = _changed_trajectory(base, slot=slot, aidc_index=index, aidc_delta_p=sign)
                        fresh_by_sign[sign] = _fresh_snapshot(
                            odd, adapter, electrical, electrical.voltage, branches, nodes, trajectory, slot,
                        )
                    fresh_slope = central_slope(fresh_by_sign[-1.0][0], fresh_by_sign[1.0][0], 1.0)
                    plan_slope = np.asarray(coefficient.current_matrix[index], dtype=float)
                    active = line_mask
                    finite.append({
                        "resource": "AIDC",
                        "site": aidc_id,
                        "slot": slot,
                        "critical_branch": str(names[critical_branch]),
                        "critical_phase": str(phases[critical_branch]),
                        "dI_PLAN_dP_critical": float(plan_slope[critical_branch]),
                        "dI_FRESH_dP_critical": float(fresh_slope[critical_branch]),
                        "line_slope_MAE": float(np.mean(np.abs(plan_slope[active] - fresh_slope[active]))),
                        "line_slope_RMSE": float(np.sqrt(np.mean((plan_slope[active] - fresh_slope[active]) ** 2))),
                        "line_slope_sign_match_rate": float(np.mean(np.sign(plan_slope[active]) == np.sign(fresh_slope[active]))),
                        "dV_PLAN_dP_inf_norm": float(np.max(np.abs(coefficient.voltage_matrix[index] / (2.0 * np.sqrt(np.maximum(1e-12, coefficient.voltage_constant + coefficient.voltage_matrix.T @ _control_vector(controls, b0["AIDC_P_kw"], slot))))))),
                        "dV_FRESH_dP_inf_norm": float(np.max(np.abs(central_slope(fresh_by_sign[-1.0][1], fresh_by_sign[1.0][1], 1.0)))),
                    })

                mess_probe_services = ("STA01", "STA06", "STA12")
                service_index = {name[10:-1]: index for index, name in enumerate(controls) if name.startswith("mess_p_kw[")}
                q_index = {name[12:-1]: index for index, name in enumerate(controls) if name.startswith("mess_q_kvar[")}
                for service in mess_probe_services:
                    for channel in ("P", "Q"):
                        fresh_by_sign = {}
                        for sign in (-1.0, 1.0):
                            trajectory = _changed_trajectory(
                                base,
                                slot=slot,
                                service=service,
                                mess_p=sign if channel == "P" else 0.0,
                                mess_q=sign if channel == "Q" else 0.0,
                            )
                            fresh_by_sign[sign] = _fresh_snapshot(
                                odd, adapter, electrical, electrical.voltage, branches, nodes, trajectory, slot,
                            )
                        fresh_slope = central_slope(fresh_by_sign[-1.0][0], fresh_by_sign[1.0][0], 1.0)
                        index = service_index[service] if channel == "P" else q_index[service]
                        plan_slope = np.asarray(coefficient.current_matrix[index], dtype=float)
                        finite.append({
                            "resource": "MESS",
                            "site": service,
                            "channel": channel,
                            "slot": slot,
                            "critical_branch": str(names[critical_branch]),
                            "critical_phase": str(phases[critical_branch]),
                            f"dI_PLAN_d{channel}_critical": float(plan_slope[critical_branch]),
                            f"dI_FRESH_d{channel}_critical": float(fresh_slope[critical_branch]),
                            "line_slope_MAE": float(np.mean(np.abs(plan_slope[line_mask] - fresh_slope[line_mask]))),
                            "line_slope_RMSE": float(np.sqrt(np.mean((plan_slope[line_mask] - fresh_slope[line_mask]) ** 2))),
                            "line_slope_sign_match_rate": float(np.mean(np.sign(plan_slope[line_mask]) == np.sign(fresh_slope[line_mask]))),
                            f"dV_PLAN_d{channel}_inf_norm": float(np.max(np.abs(coefficient.voltage_matrix[index] / (2.0 * np.sqrt(np.maximum(1e-12, coefficient.voltage_constant + coefficient.voltage_matrix.T @ _control_vector(controls, b0["AIDC_P_kw"], slot))))))),
                            f"dV_FRESH_d{channel}_inf_norm": float(np.max(np.abs(central_slope(fresh_by_sign[-1.0][1], fresh_by_sign[1.0][1], 1.0)))),
                        })
                finite_days[day] = {
                    "critical_slot": slot,
                    "critical_asset": f"{names[critical_branch]}::{phases[critical_branch]}",
                    "records": finite,
                }

                q_records = []
                q_values = (-100.0, -50.0, 0.0, 50.0, 100.0)
                for q_value in q_values:
                    vector = _control_vector(
                        controls, b0["AIDC_P_kw"], slot, service="STA01", mess_q=q_value,
                    )
                    plan = _planning_snapshot(coefficient, vector)
                    trajectory = _changed_trajectory(base, slot=slot, service="STA01", mess_q=q_value)
                    fresh_current, _fresh_voltage = _fresh_snapshot(
                        odd, adapter, electrical, electrical.voltage, branches, nodes, trajectory, slot,
                    )
                    p_critical = int(np.argmax(plan["current_affine"][line_mask]))
                    line_indices = np.flatnonzero(line_mask)
                    q_records.append({
                        "Q_kvar": q_value,
                        "Planning_affine_rho_slot": float(np.max(plan["current_affine"][line_mask])),
                        "Planning_polygon_rho_slot": float(np.max(plan["current_polygon"][line_mask])),
                        "Planning_exact_flow_rho_slot": float(np.max(plan["current_exact_flow"][line_mask])),
                        "Fresh_rho_slot": float(np.max(fresh_current[line_mask])),
                        "Planning_affine_critical_asset": f"{names[line_indices[p_critical]]}::{phases[line_indices[p_critical]]}",
                        "Fresh_critical_asset": f"{names[np.flatnonzero(line_mask)[int(np.argmax(fresh_current[line_mask]))]]}::{phases[np.flatnonzero(line_mask)[int(np.argmax(fresh_current[line_mask]))]]}",
                    })
                detection = q_exploit_detect(
                    q_values,
                    [row["Planning_affine_rho_slot"] for row in q_records],
                    [row["Fresh_rho_slot"] for row in q_records],
                )
                polygon_detection = q_exploit_detect(
                    q_values,
                    [row["Planning_polygon_rho_slot"] for row in q_records],
                    [row["Fresh_rho_slot"] for row in q_records],
                )
                q_days[day] = {
                    "slot": slot,
                    "service": "STA01",
                    "records": q_records,
                    "affine_detection": detection,
                    "polygon_detection": polygon_detection,
                }

                support = {
                    "P_ONLY": (50.0, 0.0),
                    "Q_ONLY": (0.0, 50.0),
                    "COMBINED_PQ": (50.0, 50.0),
                }
                base_plan_other = float(np.max(np.delete(stored_plan["phase_current_loading_pu"][:, line_mask], slot, axis=0)))
                base_fresh_other = float(np.max(np.delete(stored_fresh["phase_current_loading_pu"][:, line_mask], slot, axis=0)))
                for service in sorted(mapping):
                    for scenario, (p_value, q_value) in support.items():
                        vector = _control_vector(
                            controls,
                            b0["AIDC_P_kw"],
                            slot,
                            service=service,
                            mess_p=p_value,
                            mess_q=q_value,
                        )
                        plan = _planning_snapshot(coefficient, vector)
                        trajectory = _changed_trajectory(
                            base,
                            slot=slot,
                            service=service,
                            mess_p=p_value,
                            mess_q=q_value,
                        )
                        fresh_current, _ = _fresh_snapshot(
                            odd, adapter, electrical, electrical.voltage, branches, nodes, trajectory, slot,
                        )
                        static_rows.append({
                            "day": day,
                            "slot": slot,
                            "service_node": service,
                            "electrical_PCC": mapping[service],
                            "scenario": scenario,
                            "P_kW": p_value,
                            "Q_kvar": q_value,
                            "Planning_affine_rho_slot": float(np.max(plan["current_affine"][line_mask])),
                            "Planning_polygon_rho_slot": float(np.max(plan["current_polygon"][line_mask])),
                            "Fresh_rho_slot": float(np.max(fresh_current[line_mask])),
                            "Planning_affine_rho_day": max(base_plan_other, float(np.max(plan["current_affine"][line_mask]))),
                            "Planning_polygon_rho_day": max(base_plan_other, float(np.max(plan["current_polygon"][line_mask]))),
                            "Fresh_rho_day": max(base_fresh_other, float(np.max(fresh_current[line_mask]))),
                            "Planning_critical_asset": f"{names[np.flatnonzero(line_mask)[int(np.argmax(plan['current_polygon'][line_mask]))]]}::{phases[np.flatnonzero(line_mask)[int(np.argmax(plan['current_polygon'][line_mask]))]]}",
                            "Fresh_critical_asset": f"{names[np.flatnonzero(line_mask)[int(np.argmax(fresh_current[line_mask]))]]}::{phases[np.flatnonzero(line_mask)[int(np.argmax(fresh_current[line_mask]))]]}",
                        })

                # Full 24-node fingerprints use both independent P and Q
                # slopes on the line-current axis at the predeclared slot.
                for service in sorted(mapping):
                    fingerprints[service].append(np.column_stack((
                        coefficient.current_matrix[service_index[service], line_mask],
                        coefficient.current_matrix[q_index[service], line_mask],
                    )).ravel())

                # All 12 AIDC Planning sensitivities; Fresh samples are joined
                # from the finite records for AIDC01/06/12.
                fresh_lookup = {
                    row["site"]: row for row in finite if row["resource"] == "AIDC"
                }
                for aidc_index in range(12):
                    site = f"AIDC{aidc_index + 1:02d}"
                    sensitivity = np.asarray(coefficient.current_matrix[aidc_index], dtype=float)
                    record = fresh_lookup.get(site, {})
                    aidc_rows.append({
                        "day": day,
                        "slot": slot,
                        "AIDC_site": site,
                        "electrical_host_bus": mapping[f"IDC{aidc_index + 1:02d}"],
                        "phase_support": "ABC",
                        "dominant_branch": str(names[critical_branch]),
                        "dominant_phase": str(phases[critical_branch]),
                        "Planning_dI_dP_dominant": float(sensitivity[critical_branch]),
                        "Planning_dI_dP_line_inf_norm": float(np.max(np.abs(sensitivity[line_mask]))),
                        "Fresh_dI_dP_dominant": record.get("dI_FRESH_dP_critical", "NOT_SAMPLED"),
                    })

                if mapping_audit_rows is None:
                    combined = {service: np.concatenate(fingerprints[service]) for service in sorted(mapping)}
                    mapping_audit_rows = _mapping_rows(mapping, branches, combined)
            finally:
                odd.Basic.ClearAll()
            print(f"fresh-diagnostic {day}: complete in {time.perf_counter() - started:.1f}s", flush=True)
        finally:
            electrical.voltage.close()
            electrical.current.close()

    combined_fingerprints = {service: np.concatenate(chunks) for service, chunks in fingerprints.items()}
    diversity = electrical_diversity(mapping, combined_fingerprints)
    diversity.update({
        "artifact_id": "V35R2_MESS_ELECTRICAL_DIVERSITY_V1",
        "status": "PASS" if diversity["unique_electrical_PCC_count"] == 24 else "FAIL",
        "service_axis_note": "Frozen authority contains 24 nodes: IDC01-IDC12 plus STA01-STA12; STA13-STA24 do not exist and were not invented.",
        "diagnostic_days": list(DIAGNOSTIC_DAYS),
    })
    finite_payload = {
        "artifact_id": "V35R2_FINITE_DIFFERENCE_AUDIT_V1",
        "status": "PASS",
        "Fresh_role": "DIAGNOSTIC_ONLY",
        "step": {"AIDC_P_kW": 1.0, "AIDC_Q_convention": f"Delta_Q=Delta_P*{PF_TAN}", "MESS_P_kW": 1.0, "MESS_Q_kvar": 1.0},
        "days": finite_days,
    }
    q_payload = {
        "artifact_id": "V35R2_Q_EXPLOIT_AUDIT_V1",
        "status": "FAIL_AFFINE" if any(value["affine_detection"]["exploit_confirmed"] for value in q_days.values()) else "PASS",
        "classification": "AFFINE_CURRENT_Q_EXPLOIT_CONFIRMED" if any(value["affine_detection"]["exploit_confirmed"] for value in q_days.values()) else "NO_Q_EXPLOIT_FOUND",
        "Fresh_role": "DIAGNOSTIC_ONLY",
        "days": q_days,
    }
    initial = {
        "artifact_id": "V35R2_MESS_INITIAL_LOCATION_AUDIT_V1",
        "status": "DEFECT",
        "current_initial_locations": MESS_INITIAL,
        "external_depot_authority_found": False,
        "selection_rule_found": "sequential STA identifier enumeration",
        "electrical_objective_used_to_select": False,
        "classification": "MESS_INITIAL_LOCATION_AUTHORITY_DEFECT",
        "repair_deferred_until_common_current_repair_and_net_move_audit": True,
    }
    atomic_json(OUTPUT / "V35R2_FINITE_DIFFERENCE_AUDIT.json", finite_payload)
    atomic_json(OUTPUT / "V35R2_Q_EXPLOIT_AUDIT.json", q_payload)
    _write_csv(OUTPUT / "V35R2_AIDC_SITE_SENSITIVITY.csv", aidc_rows)
    _write_csv(OUTPUT / "V35R2_MESS_STATIC_LOCATION_VALUE.csv", static_rows)
    _write_csv(OUTPUT / "V35R2_MESS_SERVICE_MAPPING_AUDIT.csv", mapping_audit_rows or [])
    atomic_json(OUTPUT / "V35R2_MESS_ELECTRICAL_DIVERSITY.json", diversity)
    atomic_json(OUTPUT / "V35R2_MESS_INITIAL_LOCATION_AUDIT.json", initial)
    return {"finite": finite_payload, "q": q_payload, "diversity": diversity, "initial": initial}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    head = _head()
    if head != START_HEAD:
        raise RuntimeError(f"V35R2_START_HEAD_DRIFT:{head}")
    start = {
        "artifact_id": "V35R2_START_STATE_V1",
        "start_HEAD": head,
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip(),
        "trusted_scope": [APR01_20[0], APR01_20[-1]],
        "forbidden_scope": "2025-04-21 and later",
        "stored_case_days": 80,
        "initial_optimization_reruns": 0,
        "Fresh_diagnostic_days": list(DIAGNOSTIC_DAYS),
    }
    atomic_json(OUTPUT / "V35R2_START_STATE.json", start)
    stored = build_stored_current_authority()
    diagnostic = run_fresh_diagnostics()
    print(json.dumps({
        "stored": stored,
        "q_classification": diagnostic["q"]["classification"],
        "diversity": diagnostic["diversity"],
    }, sort_keys=True, indent=2), flush=True)


if __name__ == "__main__":
    main()

