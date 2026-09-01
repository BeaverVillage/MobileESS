"""Execute the frozen V17 common Fresh-AC feasibility-closure protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .authority import sha256_file
from .final_science_solver_v16_3 import solve_shadow
from .grid_lp import V_MAX_SQUARED, V_MIN_SQUARED
from .mess_physics import PCS_KVA, P_LIMIT_KW
from .run_v16_3_nonzero_validity import _aidc_limits, _apply_vector, _fresh_branch_metric, _fresh_capture
from .run_v16_3_correction import _ac_summary
from .run_v16_3_voltage_candidate import (
    CAPACITORS,
    REGULATORS,
    _compile,
    _enable_native_controls,
    _fix_controls,
    _perturbation,
    _set_slot,
    _voltage_map,
)
from .v17_ac_restoration_contract import (
    ACViolation,
    CONTRACT_ID,
    K_MAX,
    RHO,
    RestorationCut,
    ViolationType,
    canonical_sha256,
)
from .v17_deferrability_semantics import write_json
from .v17_v5_current_repair import DEBUG_DAYS, SOURCE_DEFAULT
from .v17_v5_revalidation import _electrical_context


V_MIN = float(np.sqrt(V_MIN_SQUARED))
V_MAX = float(np.sqrt(V_MAX_SQUARED))
HARD_TOLERANCE = 1e-9


def _schedule_array_sha(controls: np.ndarray) -> str:
    value = np.asarray(controls, dtype=np.float64)
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode("ascii")); digest.update(b"\0")
    digest.update(json.dumps(list(value.shape), separators=(",", ":")).encode("ascii")); digest.update(b"\0")
    digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def _state_payload(slot: int, nodes: Sequence[str], capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "slot": int(slot),
        "voltage": {node: float(value) for node, value in zip(nodes, capture["voltage"])},
        "branch_metrics": capture["branch_metrics"],
    }


def _voltage_asset(node: str) -> tuple[str, str]:
    bus, phase_number = node.rsplit(".", 1)
    return f"bus.{bus}", "ABC"[int(phase_number) - 1]


def _extract_violations(
    *, day: str, case: str, slot: int, nodes: Sequence[str], capture: Mapping[str, Any],
    schedule_sha256: str,
) -> list[ACViolation]:
    state_sha = canonical_sha256(_state_payload(slot, nodes, capture))
    rows: list[ACViolation] = []
    for node, raw in zip(nodes, capture["voltage"]):
        value = float(raw); asset, phase = _voltage_asset(node)
        if value > V_MAX + HARD_TOLERANCE:
            rows.append(ACViolation(ViolationType.VOLTAGE_UPPER, day, case, slot, asset, phase,
                                    value, V_MAX, value - V_MAX, state_sha, schedule_sha256))
        elif value < V_MIN - HARD_TOLERANCE:
            rows.append(ACViolation(ViolationType.VOLTAGE_LOWER, day, case, slot, asset, phase,
                                    value, V_MIN, V_MIN - value, state_sha, schedule_sha256))
    kva_seen: set[str] = set()
    for metric in capture["branch_metrics"]:
        loading = float(metric["normalized_current_loading_pu"])
        if loading > 1.0 + HARD_TOLERANCE:
            kind = ViolationType.LINE_CURRENT if metric["kind"] == "line" else ViolationType.TRANSFORMER_CURRENT
            rows.append(ACViolation(kind, day, case, slot, str(metric["branch"]), str(metric["phase"]),
                                    loading, 1.0, loading - 1.0, state_sha, schedule_sha256))
        kva = metric["transformer_total_kva_loading_pu"]
        branch = str(metric["branch"])
        if kva is not None and branch not in kva_seen and float(kva) > 1.0 + HARD_TOLERANCE:
            kva_seen.add(branch)
            rows.append(ACViolation(ViolationType.TRANSFORMER_KVA, day, case, slot, branch, None,
                                    float(kva), 1.0, float(kva) - 1.0, state_sha, schedule_sha256))
    return rows


def primary_fresh_ac(
    repo: Path, source: Path, context, voltage, controls: np.ndarray, *, day: str, case: str,
    schedule_sha256: str,
) -> tuple[dict[str, Any], list[ACViolation], int]:
    """Run 96 frozen-tap solves and retain dispatchable exact violations."""

    reference, _vintage, background, binding, _cache, _authority = context
    nodes = tuple(map(str, voltage["node_names"])); branches = tuple(binding.factories[0].data.branches)
    limits = np.asarray([
        float(binding.factories[0].data.line_limit_kva_u080[(branch.branch_id, branch.phase)])
        for branch in branches
    ])
    control_names = tuple(map(str, voltage["control_names"]))
    odd, adapter = _compile(source, repo, "NATIVE")
    captures: list[dict[str, Any]] = []; secondary_captures: list[dict[str, Any]] = []
    violations: list[ACViolation] = []
    for slot in range(96):
        taps = {name: float(voltage["regulator_taps"][slot, index]) for index, name in enumerate(REGULATORS)}
        caps = {name: [int(voltage["capacitor_states"][slot, index])] for index, name in enumerate(CAPACITORS)}
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps)
        _apply_vector(odd, control_names, np.asarray(controls[slot], dtype=float))
        odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V17_AC_RESTORATION_PRIMARY_NONCONVERGENCE:{day}:{case}:{slot}")
        capture = _fresh_capture(odd, nodes, branches, limits, range(len(branches)))
        captures.append(capture)
        violations.extend(_extract_violations(
            day=day, case=case, slot=slot, nodes=nodes, capture=capture,
            schedule_sha256=schedule_sha256,
        ))
        # Preserve the exact already-established V5 execution order.  The
        # historical 7-day runner performs its native-RegControl secondary
        # solve after every primary slot before advancing to the next slot.
        # Replaying that transition is required for byte-level state-history
        # provenance even though only the primary capture drives cuts.
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps); _enable_native_controls(odd)
        _apply_vector(odd, control_names, np.asarray(controls[slot], dtype=float))
        odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V17_AC_RESTORATION_SECONDARY_TRANSITION_NONCONVERGENCE:{day}:{case}:{slot}")
        secondary_captures.append(_fresh_capture(odd, nodes, branches, limits, range(len(branches))))
    summary = _ac_summary(captures)
    summary["exact_violation_count"] = len(violations)
    summary["Fresh_OpenDSS_state_sha256"] = canonical_sha256({
        "states": [_state_payload(slot, nodes, capture) for slot, capture in enumerate(captures)]
    })
    summary["secondary_native_RegControl"] = _ac_summary(secondary_captures)
    return summary, violations, 192


def _measurement(odd: Any, violation: ACViolation, nodes: Sequence[str], branches, limits: np.ndarray) -> float:
    if violation.violation_type in {ViolationType.VOLTAGE_UPPER, ViolationType.VOLTAGE_LOWER}:
        bus = violation.asset.split(".", 1)[1]
        node = f"{bus}.{'ABC'.index(str(violation.phase)) + 1}"
        return float(_voltage_map(odd, nodes)[node])
    branch_index = next(
        index for index, branch in enumerate(branches)
        if branch.branch_id == violation.asset and (
            violation.violation_type == ViolationType.TRANSFORMER_KVA or branch.phase == violation.phase
        )
    )
    metric = _fresh_branch_metric(odd, branches[branch_index], float(limits[branch_index]))
    if violation.violation_type == ViolationType.TRANSFORMER_KVA:
        return float(metric["transformer_total_kva_loading_pu"])
    return float(metric["normalized_current_loading_pu"])


def _case_control_indices(case: str) -> tuple[int, ...]:
    if case == "B0": return ()
    if case == "B1": return tuple(range(12))
    if case == "B2": return tuple(range(12, 60))
    if case == "B3": return tuple(range(60))
    raise ValueError(f"V17_AC_UNKNOWN_CASE:{case}")


def _local_radii(case: str, reference, authority, slot: int) -> np.ndarray:
    radius = np.zeros(60, dtype=float)
    if case in {"B1", "B3"}:
        down, up, _limits = _aidc_limits(reference, authority, slot)
        radius[:12] = RHO * np.maximum(np.asarray(down, dtype=float), np.asarray(up, dtype=float))
    if case in {"B2", "B3"}:
        radius[12:36] = RHO * P_LIMIT_KW
        radius[36:60] = RHO * PCS_KVA
    return radius


def local_fresh_ac_cuts(
    repo: Path, source: Path, context, voltage, controls: np.ndarray,
    violations: Sequence[ACViolation], *, case: str, iteration_index: int,
    margins: Mapping[str, float],
) -> tuple[list[RestorationCut], int]:
    """Central-difference only the controls already authorized for ``case``."""

    reference, _vintage, background, binding, _cache, authority = context
    nodes = tuple(map(str, voltage["node_names"])); branches = tuple(binding.factories[0].data.branches)
    limits = np.asarray([
        float(binding.factories[0].data.line_limit_kva_u080[(branch.branch_id, branch.phase)])
        for branch in branches
    ])
    names = tuple(map(str, voltage["control_names"])); allowed = _case_control_indices(case)
    if not allowed:
        return [], 0
    odd, adapter = _compile(source, repo, "NATIVE")
    cuts: list[RestorationCut] = []; solve_count = 0
    previous_slot = -1
    for slot in sorted({int(row.slot) for row in violations}):
        slot_violations = [row for row in violations if int(row.slot) == slot]
        # Reconstruct the same interleaved primary/secondary state history up
        # to this violated slot before taking a local derivative.
        for history_slot in range(previous_slot + 1, slot):
            history_taps = {name: float(voltage["regulator_taps"][history_slot, index]) for index, name in enumerate(REGULATORS)}
            history_caps = {name: [int(voltage["capacitor_states"][history_slot, index])] for index, name in enumerate(CAPACITORS)}
            history_values = np.asarray(controls[history_slot], dtype=float)
            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], history_slot)
            _fix_controls(odd, history_taps, history_caps); _apply_vector(odd, names, history_values)
            odd.Solution.SolveSnap(); solve_count += 1
            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], history_slot)
            _fix_controls(odd, history_taps, history_caps); _enable_native_controls(odd); _apply_vector(odd, names, history_values)
            odd.Solution.SolveSnap(); solve_count += 1
        taps = {name: float(voltage["regulator_taps"][slot, index]) for index, name in enumerate(REGULATORS)}
        caps = {name: [int(voltage["capacitor_states"][slot, index])] for index, name in enumerate(CAPACITORS)}
        anchor = np.asarray(controls[slot], dtype=float)
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot); _fix_controls(odd, taps, caps)
        _apply_vector(odd, names, anchor); odd.Solution.SolveSnap(); solve_count += 1
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V17_AC_LOCAL_ANCHOR_NONCONVERGENCE:{slot}")
        anchor_capture = _fresh_capture(odd, nodes, branches, limits, range(len(branches)))
        state_sha = canonical_sha256(_state_payload(slot, nodes, anchor_capture))
        if any(row.fresh_opendss_state_sha256 != state_sha for row in slot_violations):
            raise RuntimeError("V17_AC_STALE_VIOLATION_STATE_REJECTED")
        derivatives = {row.sha256: np.zeros(60, dtype=float) for row in slot_violations}
        for index in allowed:
            step = float(_perturbation(names[index], float(anchor[index])))
            plus = anchor.copy(); plus[index] += step
            _apply_vector(odd, names, plus); odd.Solution.SolveSnap(); solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V17_AC_LOCAL_PLUS_NONCONVERGENCE:{slot}:{names[index]}")
            plus_values = {row.sha256: _measurement(odd, row, nodes, branches, limits) for row in slot_violations}
            minus = anchor.copy(); minus[index] -= step
            _apply_vector(odd, names, minus); odd.Solution.SolveSnap(); solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V17_AC_LOCAL_MINUS_NONCONVERGENCE:{slot}:{names[index]}")
            for row in slot_violations:
                derivatives[row.sha256][index] = (plus_values[row.sha256] - _measurement(odd, row, nodes, branches, limits)) / (2.0 * step)
        radius = _local_radii(case, reference, authority, slot)
        for row in slot_violations:
            coefficient = derivatives[row.sha256]
            derivative_sha = hashlib.sha256(np.asarray(coefficient, dtype=np.float64).tobytes()).hexdigest()
            voltage = row.violation_type in {ViolationType.VOLTAGE_UPPER, ViolationType.VOLTAGE_LOWER}
            margin = float(margins["m_V_pu"] if voltage else (
                margins["m_transformer_kva_pu"] if row.violation_type == ViolationType.TRANSFORMER_KVA else margins["m_I_pu"]
            ))
            cuts.append(RestorationCut(
                violation_sha256=row.sha256,
                local_ac_operating_point_sha256=state_sha,
                derivative_sha256=derivative_sha,
                violation_type=row.violation_type,
                slot=slot,
                relation=">=" if row.violation_type == ViolationType.VOLTAGE_LOWER else "<=",
                actual_value=float(row.actual_value),
                hard_limit=float(row.hard_limit),
                margin=margin,
                trust_region_rho=RHO,
                iteration_index=iteration_index,
                control_names=names,
                anchor_controls=tuple(map(float, anchor)),
                coefficients=tuple(map(float, coefficient)),
                local_radius=tuple(map(float, radius)),
            ))
        # Complete the historical state transition for this slot before a
        # possible later violated slot is reconstructed.
        _apply_vector(odd, names, anchor)
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps); _enable_native_controls(odd); _apply_vector(odd, names, anchor)
        odd.Solution.SolveSnap(); solve_count += 1
        previous_slot = slot
    return cuts, solve_count


def _save_solver_schedule(path: Path, result: dict[str, Any]) -> np.ndarray:
    controls = np.asarray(result.pop("controls_96x60"), dtype=float)
    arrays = {
        name: result.pop(name)
        for name in ("workload_payload", "mess_p_96x4", "mess_q_96x4", "mess_e_97x4")
        if name in result
    }
    arrays["controls_96x60"] = controls
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    return controls


def run_apr12_b2(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    contract_path = output / "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json"
    validation_path = output / "V17_AC_RESTORATION_CUT_VALIDATION.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if contract["artifact_id"] != CONTRACT_ID or contract["status"] != "FROZEN_BEFORE_APR12_REPLAY":
        raise RuntimeError("V17_AC_CONTRACT_NOT_FROZEN_BEFORE_REPLAY")
    if validation["status"] != "PASS_FROZEN_BEFORE_APR12_REPLAY":
        raise RuntimeError("V17_AC_CUT_VALIDATION_NOT_FROZEN_BEFORE_REPLAY")

    day = "2025-04-12"; case = "B2"
    reference, inputs, vintage, background, binding, authority = _electrical_context(repo, source, output, day)
    voltage_path = output / "ac_cache_v5/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    current_path = output / "ac_cache_v5/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
    context = (reference, vintage, background, binding, voltage_path, authority)

    original_path = output / "schedules_v5_current_repair" / f"V17_V5_CURRENT_REPAIR_{day}_{case}.npz"
    preserved_daily = json.loads((output / "v5_current_repair_daily" / f"V17_V5_CURRENT_REPAIR_{day}_B0_B1_B2_B3.json").read_text(encoding="utf-8"))
    expected = preserved_daily["cases"][case]
    if sha256_file(original_path) != expected["schedule_file_sha256"]:
        raise RuntimeError("V17_AC_APR12_B2_PRESERVED_SCHEDULE_SHA_MISMATCH")
    saved = np.load(original_path, allow_pickle=False)
    controls = np.asarray(saved["controls_96x60"], dtype=float)
    pre_path = output / "V17_APR12_B2_PRE_RESTORATION_SCHEDULE.npz"
    shutil.copyfile(original_path, pre_path)
    primary, violations, fresh_calls = primary_fresh_ac(
        repo, source, context, voltage, controls, day=day, case=case,
        schedule_sha256=str(expected["schedule_sha256"]),
    )
    if int(primary["voltage_violation_count"]) != 2 or abs(float(primary["Vmax_pu"]) - 1.0500161160111587) > 1e-8:
        raise RuntimeError(f"V17_AC_APR12_ITERATION0_NOT_REPRODUCED:{primary}")
    iterations: list[dict[str, Any]] = [{
        "iteration": 0,
        "objective": float(expected["objective_max_normalized_phase_line_current"]),
        "schedule_file_sha256": sha256_file(pre_path),
        "schedule_control_array_sha256": _schedule_array_sha(controls),
        "primary_Fresh_AC": primary,
        "violations": [row.payload() | {"violation_sha256": row.sha256} for row in violations],
        "cuts_added": [],
    }]
    accumulated: list[RestorationCut] = []
    current_result: dict[str, Any] | None = None
    final_path = output / "V17_APR12_B2_POST_RESTORATION_SCHEDULE.npz"
    for iteration in range(1, K_MAX + 1):
        if not violations:
            break
        new_cuts, local_calls = local_fresh_ac_cuts(
            repo, source, context, voltage, controls, violations, case=case,
            iteration_index=iteration, margins=validation["margins"],
        )
        fresh_calls += local_calls
        if not new_cuts:
            break
        accumulated.extend(new_cuts)
        solved = solve_shadow(
            inputs=inputs, context=context, voltage_data=voltage, current_data=current,
            rho=RHO, case=case, restoration_cuts=tuple(accumulated),
        )
        current_result = dict(solved)
        if not bool(current_result.get("hard_feasible")):
            iterations.append({"iteration": iteration, "status": current_result["status"],
                               "cuts_added": [cut.payload() | {"cut_sha256": cut.sha256} for cut in new_cuts]})
            break
        controls = _save_solver_schedule(final_path, current_result)
        primary, violations, calls = primary_fresh_ac(
            repo, source, context, voltage, controls, day=day, case=case,
            schedule_sha256=str(current_result["schedule_sha256"]),
        )
        fresh_calls += calls
        iterations.append({
            "iteration": iteration,
            "objective": float(current_result["objective_max_normalized_phase_line_current"]),
            "schedule_file_sha256": sha256_file(final_path),
            "schedule_control_array_sha256": _schedule_array_sha(controls),
            "primary_Fresh_AC": primary,
            "violations": [row.payload() | {"violation_sha256": row.sha256} for row in violations],
            "cuts_added": [cut.payload() | {"cut_sha256": cut.sha256} for cut in new_cuts],
            "accumulated_cut_count": len(accumulated),
            "terminal_service_parity_max_abs_error": float(current_result["terminal_service_parity_max_abs_error"]),
            "MESS_terminal_SOC_max_abs_error_kwh": float(current_result["mess_terminal_soc_max_abs_error_kwh"]),
        })
        if not violations:
            break

    passed = not violations and current_result is not None and bool(primary["all_frozen_hard_constraints_pass"])
    secondary: dict[str, Any] | None = None
    if passed:
        secondary = dict(primary["secondary_native_RegControl"])
        if not bool(secondary["all_frozen_hard_constraints_pass"]):
            passed = False
    if not final_path.is_file():
        shutil.copyfile(pre_path, final_path)
    original_controls = np.asarray(np.load(pre_path, allow_pickle=False)["controls_96x60"], dtype=float)
    delta = controls - original_controls
    delta_payload = {
        "artifact_id": "V17_APR12_B2_RESTORATION_DELTA_V1",
        "status": "PASS" if passed else "FAIL_CLOSED",
        "pre_schedule_sha256": sha256_file(pre_path),
        "post_schedule_sha256": sha256_file(final_path),
        "max_abs_control_delta": float(np.max(np.abs(delta))),
        "nonzero_control_count": int(np.count_nonzero(np.abs(delta) > 1e-9)),
        "MESS_P_max_abs_delta_kw": float(np.max(np.abs(delta[:, 12:36]))),
        "MESS_Q_max_abs_delta_kvar": float(np.max(np.abs(delta[:, 36:60]))),
        "AIDC_max_abs_delta_kw": float(np.max(np.abs(delta[:, :12]))),
        "terminal_service_parity_max_abs_error": None if current_result is None else float(current_result["terminal_service_parity_max_abs_error"]),
        "MESS_terminal_SOC_max_abs_error_kwh": None if current_result is None else float(current_result["mess_terminal_soc_max_abs_error_kwh"]),
    }
    write_json(output / "V17_APR12_B2_RESTORATION_DELTA.json", delta_payload)
    trace = {
        "artifact_id": "V17_APR12_B2_RESTORATION_TRACE_V1",
        "status": "PASS" if passed else "FAIL_CLOSED",
        "classification": "V17_AC_LOOP_B_APR12_B2_RESTORATION_PASS_7DAY_PENDING" if passed else "V17_AC_LOOP_D_RESTORATION_UNRESOLVED",
        "operating_day": day,
        "case": case,
        "contract_sha256": sha256_file(contract_path),
        "cut_validation_sha256": sha256_file(validation_path),
        "K_MAX": K_MAX,
        "rho": RHO,
        "iterations": iterations,
        "restoration_iterations": max(0, len(iterations) - 1),
        "original_objective": float(expected["objective_max_normalized_phase_line_current"]),
        "restored_objective": None if current_result is None else float(current_result["objective_max_normalized_phase_line_current"]),
        "objective_degradation": None if current_result is None else float(current_result["objective_max_normalized_phase_line_current"] - expected["objective_max_normalized_phase_line_current"]),
        "final_primary_Fresh_AC": primary,
        "final_secondary_native_RegControl_Fresh_AC": secondary,
        "Fresh_OpenDSS_solve_count": fresh_calls,
        "OpenDSS_calls_inside_Benders": 0,
        "pre_schedule_sha256": sha256_file(pre_path),
        "post_schedule_sha256": sha256_file(final_path),
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
    }
    write_json(output / "V17_APR12_B2_RESTORATION_TRACE.json", trace)
    return trace


def run_7day_regression(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    """Revalidate the exact 28 iteration-zero schedules under the common loop."""

    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    apr12_trace = json.loads((output / "V17_APR12_B2_RESTORATION_TRACE.json").read_text(encoding="utf-8"))
    if apr12_trace["status"] != "PASS":
        raise RuntimeError("V17_AC_7DAY_REQUIRES_APR12_B2_RESTORATION_PASS")
    rows: list[dict[str, Any]] = []; fresh_calls = 0
    for day in DEBUG_DAYS:
        reference, _inputs, vintage, background, binding, authority = _electrical_context(repo, source, output, day)
        voltage_path = output / "ac_cache_v5/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        voltage = np.load(voltage_path, allow_pickle=False)
        context = (reference, vintage, background, binding, voltage_path, authority)
        daily_path = output / "v5_current_repair_daily" / f"V17_V5_CURRENT_REPAIR_{day}_B0_B1_B2_B3.json"
        daily = json.loads(daily_path.read_text(encoding="utf-8"))
        for case in ("B0", "B1", "B2", "B3"):
            initial = daily["cases"][case]
            schedule_path = output / "schedules_v5_current_repair" / f"V17_V5_CURRENT_REPAIR_{day}_{case}.npz"
            if sha256_file(schedule_path) != initial["schedule_file_sha256"]:
                raise RuntimeError(f"V17_AC_7DAY_INITIAL_SCHEDULE_SHA_MISMATCH:{day}:{case}")
            controls = np.asarray(np.load(schedule_path, allow_pickle=False)["controls_96x60"], dtype=float)
            first, violations, calls = primary_fresh_ac(
                repo, source, context, voltage, controls, day=day, case=case,
                schedule_sha256=str(initial["schedule_sha256"]),
            )
            fresh_calls += calls
            first_pass = bool(first["all_frozen_hard_constraints_pass"])
            restoration_iterations = 0; objective_degradation = 0.0
            final = first; final_schedule = schedule_path
            if not first_pass:
                if not (day == "2025-04-12" and case == "B2"):
                    raise RuntimeError(f"V17_AC_7DAY_UNEXPECTED_FIRST_PASS_FAILURE:{day}:{case}:{len(violations)}")
                final_schedule = output / "V17_APR12_B2_POST_RESTORATION_SCHEDULE.npz"
                restored_controls = np.asarray(np.load(final_schedule, allow_pickle=False)["controls_96x60"], dtype=float)
                final, final_violations, calls = primary_fresh_ac(
                    repo, source, context, voltage, restored_controls, day=day, case=case,
                    schedule_sha256=str(apr12_trace["iterations"][-1]["schedule_control_array_sha256"]),
                )
                fresh_calls += calls
                if final_violations:
                    raise RuntimeError("V17_AC_7DAY_APR12_RESTORED_SCHEDULE_REGRESSION_FAIL")
                restoration_iterations = int(apr12_trace["restoration_iterations"])
                objective_degradation = float(apr12_trace["objective_degradation"])
            secondary = final["secondary_native_RegControl"]
            final_pass = bool(final["all_frozen_hard_constraints_pass"] and secondary["all_frozen_hard_constraints_pass"])
            rows.append({
                "operating_day": day,
                "case": case,
                "optimization_hard_feasible": bool(initial["hard_feasible"]),
                "first_pass_primary_PASS": first_pass,
                "first_pass_primary": first,
                "restoration_required": not first_pass,
                "restoration_iterations": restoration_iterations,
                "restoration_success": bool((not first_pass) and final_pass),
                "final_primary": final,
                "final_secondary_native_RegControl": secondary,
                "final_PASS": final_pass,
                "initial_schedule_sha256": sha256_file(schedule_path),
                "final_schedule_sha256": sha256_file(final_schedule),
                "objective_degradation": objective_degradation,
                "terminal_service_parity_max_abs_error": float(
                    apr12_trace["iterations"][-1]["terminal_service_parity_max_abs_error"]
                    if not first_pass else initial["terminal_service_parity_max_abs_error"]
                ),
                "MESS_terminal_SOC_max_abs_error_kwh": float(
                    apr12_trace["iterations"][-1]["MESS_terminal_SOC_max_abs_error_kwh"]
                    if not first_pass else initial["mess_terminal_soc_max_abs_error_kwh"]
                ),
            })
    first_pass_count = sum(row["first_pass_primary_PASS"] for row in rows)
    required = [row for row in rows if row["restoration_required"]]
    successful = [row for row in required if row["restoration_success"]]
    all_pass = all(
        row["optimization_hard_feasible"] and row["final_PASS"]
        and row["terminal_service_parity_max_abs_error"] <= 1e-9
        and row["MESS_terminal_SOC_max_abs_error_kwh"] <= 1e-9
        for row in rows
    )
    payload = {
        "artifact_id": "V17_AC_RESTORATION_7DAY_REGRESSION_V1",
        "status": "PASS" if all_pass else "FAIL_CLOSED",
        "classification": "V17_AC_LOOP_A_COMMON_CLOSED_LOOP_IMPLEMENTED_PASS" if all_pass else "V17_AC_LOOP_D_RESTORATION_UNRESOLVED",
        "debug_days": list(DEBUG_DAYS),
        "case_axis": ["B0", "B1", "B2", "B3"],
        "schedule_count": len(rows),
        "first_pass_pass_count": first_pass_count,
        "restoration_required_count": len(required),
        "restoration_success_count": len(successful),
        "restoration_failure_count": len(required) - len(successful),
        "mean_restoration_iterations": float(np.mean([row["restoration_iterations"] for row in rows])),
        "max_restoration_iterations": max(row["restoration_iterations"] for row in rows),
        "total_objective_degradation": float(sum(row["objective_degradation"] for row in rows)),
        "total_Fresh_OpenDSS_solve_count": fresh_calls,
        "all_28_optimization_feasible": all(row["optimization_hard_feasible"] for row in rows),
        "all_28_final_primary_PASS": all(row["final_primary"]["all_frozen_hard_constraints_pass"] for row in rows),
        "all_28_final_secondary_PASS": all(row["final_secondary_native_RegControl"]["all_frozen_hard_constraints_pass"] for row in rows),
        "all_28_service_parity_PASS": all(row["terminal_service_parity_max_abs_error"] <= 1e-9 for row in rows),
        "all_28_terminal_SOC_PASS": all(row["MESS_terminal_SOC_max_abs_error_kwh"] <= 1e-9 for row in rows),
        "rows": rows,
        "OpenDSS_calls_inside_Benders": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
    }
    write_json(output / "V17_AC_RESTORATION_7DAY_REGRESSION.json", payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("apr12-b2", "seven-day"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    result = run_apr12_b2(args.repo, args.source, args.output) if args.phase == "apr12-b2" else run_7day_regression(args.repo, args.source, args.output)
    print(json.dumps({"status": result["status"], "classification": result["classification"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
