"""Decompose the stored B2 actuation into P-only, Q-only, and joint effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v28r2.opendss_backend import _branch_measurement
from dayahead.v28r2.opendss_mapping import (
    FeederAssets, apply_frozen_native_state, apply_trajectory_slot, compile_clean_engine,
)
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v35.execution import DEFAULT_SOURCE_REPO, _electrical_context
from dayahead.v35.storage import atomic_json
from dayahead.v35r2.forensic import (
    DIAGNOSTIC_DAYS,
    anchored_polygon_loading,
    polygon_loading,
    require_diagnostic_day,
)


CACHE = REPO / "dayahead/cache/v35"
PHASE = "APR01_20_AC_FIDELITY_CALIBRATION"
OUTPUT = REPO / "dayahead/artifacts/v35r2_aidc_mess_forensic"


def _npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {name: np.asarray(payload[name]) for name in payload.files}


def _trajectory(
    day: str,
    aidc: dict[str, np.ndarray],
    mess: dict[str, np.ndarray],
    *,
    use_p: bool,
    use_q: bool,
) -> FrozenTrajectory:
    digest = hashlib.sha256(f"{day}:P={use_p}:Q={use_q}".encode()).hexdigest()
    return FrozenTrajectory(
        day,
        "DAYAHEAD",
        "B2",
        np.asarray(aidc["AIDC_P_kw"], dtype=float),
        np.asarray(aidc["AIDC_Q_kvar"], dtype=float),
        np.asarray(mess["P_kw"], dtype=float) if use_p else np.zeros((96, 4)),
        np.asarray(mess["Q_kvar"], dtype=float) if use_q else np.zeros((96, 4)),
        ("MESS01", "MESS02", "MESS03", "MESS04"),
        np.asarray(mess["locations"]).astype(str),
        digest,
    )


def _fresh_day(
    odd: object,
    adapter: object,
    electrical: object,
    voltage: object,
    branches: tuple[object, ...],
    line_mask: np.ndarray,
    trajectory: FrozenTrajectory,
) -> tuple[float, int, int, np.ndarray]:
    values = np.zeros((96, len(branches)), dtype=float)
    for slot in range(96):
        apply_trajectory_slot(odd, adapter, electrical, trajectory, slot)
        apply_frozen_native_state(odd, voltage, slot)
        odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V35R2_LARGE_SIGNAL_NONCONVERGENCE:{trajectory.day}:{slot}")
        values[slot] = np.asarray([_branch_measurement(odd, branch)[1] for branch in branches])
    local = np.unravel_index(int(np.argmax(values[:, line_mask])), values[:, line_mask].shape)
    return float(values[:, line_mask].max()), int(local[0]), int(np.flatnonzero(line_mask)[local[1]]), values


def _planning_day(
    coefficients: tuple[object, ...],
    controls: tuple[str, ...],
    aidc: dict[str, np.ndarray],
    mess: dict[str, np.ndarray],
    line_mask: np.ndarray,
    *,
    use_p: bool,
    use_q: bool,
) -> dict[str, object]:
    services_p = tuple(name[10:-1] for name in controls[12:36])
    services_q = tuple(name[12:-1] for name in controls[36:60])
    affine_rows, polygon_rows, anchored_rows, exact_rows = [], [], [], []
    locations = np.asarray(mess["locations"]).astype(str)
    p_vehicle = np.asarray(mess["P_kw"], dtype=float) if use_p else np.zeros((96, 4))
    q_vehicle = np.asarray(mess["Q_kvar"], dtype=float) if use_q else np.zeros((96, 4))
    for slot, coefficient in enumerate(coefficients):
        by_p = {service: 0.0 for service in services_p}
        by_q = {service: 0.0 for service in services_q}
        for vehicle in range(4):
            service = str(locations[slot, vehicle])
            if service in by_p:
                by_p[service] += float(p_vehicle[slot, vehicle])
                by_q[service] += float(q_vehicle[slot, vehicle])
        x = np.asarray(
            list(np.asarray(aidc["AIDC_P_kw"])[slot])
            + [by_p[service] for service in services_p]
            + [by_q[service] for service in services_q],
            dtype=float,
        )
        p_flow = coefficient.flow_p_constant + coefficient.flow_p_matrix @ x
        q_flow = coefficient.flow_q_constant + coefficient.flow_q_matrix @ x
        affine_rows.append(coefficient.current_constant + coefficient.current_matrix.T @ x)
        limits = np.asarray(coefficient.branch_limits, dtype=float)
        polygon_rows.append(polygon_loading(p_flow, q_flow, limits))
        anchored_rows.append(anchored_polygon_loading(coefficient, x))
        exact_rows.append(np.hypot(p_flow, q_flow) / limits)
    result: dict[str, object] = {}
    for name, values in (
        ("affine", np.asarray(affine_rows)),
        ("polygon", np.asarray(polygon_rows)),
        ("anchored_polygon", np.asarray(anchored_rows)),
        ("exact_flow", np.asarray(exact_rows)),
    ):
        local = np.unravel_index(int(np.argmax(values[:, line_mask])), values[:, line_mask].shape)
        result[f"{name}_rho"] = float(values[:, line_mask].max())
        result[f"{name}_slot"] = int(local[0])
        result[f"{name}_branch_index"] = int(np.flatnonzero(line_mask)[local[1]])
    return result


def main() -> None:
    existing = json.loads((OUTPUT / "V35R2_Q_EXPLOIT_AUDIT.json").read_text(encoding="utf-8"))
    decompositions: dict[str, object] = {}
    for day in DIAGNOSTIC_DAYS:
        require_diagnostic_day(day)
        print(f"large-signal {day}: context", flush=True)
        started = time.perf_counter()
        data = materialize_formulation_data(DEFAULT_SOURCE_REPO, day, disable_legacy_mess_source=True)
        electrical = _electrical_context(REPO, DEFAULT_SOURCE_REPO, CACHE, PHASE, day, data)
        try:
            coefficients = tuple(
                slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
                for slot in range(96)
            )
            controls = tuple(map(str, electrical.voltage["control_names"]))
            aidc = _npz(CACHE / PHASE / day / "B0/DAYAHEAD_AIDC.npz")
            mess = _npz(CACHE / PHASE / day / "B2/DAYAHEAD_MESS.npz")
            names = np.asarray(coefficients[0].branch_names).astype(str)
            phases = np.asarray(
                [branch.phase for branch in electrical.legacy_context[3].factories[0].data.branches]
            ).astype(str)
            line_mask = np.asarray([
                not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
                for name in names
            ])
            branches = tuple(electrical.legacy_context[3].factories[0].data.branches)
            previous_records = (
                existing.get("large_signal_decomposition", {})
                .get(day, {})
                .get("records", {})
            )
            reuse_fresh = all(
                label in previous_records and "Fresh_rho" in previous_records[label]
                for label in ("ZERO", "P_ONLY", "Q_ONLY", "P_PLUS_Q")
            )
            odd = adapter = None
            if not reuse_fresh:
                odd, adapter = compile_clean_engine(FeederAssets.from_repo(DEFAULT_SOURCE_REPO))
            try:
                records: dict[str, dict[str, object]] = {}
                for label, use_p, use_q in (
                    ("ZERO", False, False),
                    ("P_ONLY", True, False),
                    ("Q_ONLY", False, True),
                    ("P_PLUS_Q", True, True),
                ):
                    planning = _planning_day(
                        coefficients, controls, aidc, mess, line_mask, use_p=use_p, use_q=use_q,
                    )
                    if reuse_fresh:
                        rho = float(previous_records[label]["Fresh_rho"])
                        slot = int(previous_records[label]["Fresh_slot"])
                        branch_index = next(
                            index for index, name in enumerate(names)
                            if str(previous_records[label]["Fresh_asset"]).startswith(f"{name}::")
                        )
                    else:
                        rho, slot, branch_index, _values = _fresh_day(
                            odd,
                            adapter,
                            electrical,
                            electrical.voltage,
                            branches,
                            line_mask,
                            _trajectory(day, aidc, mess, use_p=use_p, use_q=use_q),
                        )
                    records[label] = {
                        **planning,
                        "Fresh_rho": rho,
                        "Fresh_slot": slot,
                        "Fresh_asset": f"{names[branch_index]}::{phases[branch_index]}",
                    }
                    print(
                        f"large-signal {day}: {label} "
                        f"plan={planning['affine_rho']:.6f} fresh={rho:.6f}",
                        flush=True,
                    )

                def delta(left: str, right: str, metric: str) -> float:
                    return float(records[right][metric]) - float(records[left][metric])

                marginals = {
                    "P_from_ZERO": {
                        "Planning_affine_delta": delta("ZERO", "P_ONLY", "affine_rho"),
                        "Planning_polygon_delta": delta("ZERO", "P_ONLY", "polygon_rho"),
                        "Planning_anchored_polygon_delta": delta("ZERO", "P_ONLY", "anchored_polygon_rho"),
                        "Fresh_delta": delta("ZERO", "P_ONLY", "Fresh_rho"),
                    },
                    "Q_from_ZERO": {
                        "Planning_affine_delta": delta("ZERO", "Q_ONLY", "affine_rho"),
                        "Planning_polygon_delta": delta("ZERO", "Q_ONLY", "polygon_rho"),
                        "Planning_anchored_polygon_delta": delta("ZERO", "Q_ONLY", "anchored_polygon_rho"),
                        "Fresh_delta": delta("ZERO", "Q_ONLY", "Fresh_rho"),
                    },
                    "Q_given_P": {
                        "Planning_affine_delta": delta("P_ONLY", "P_PLUS_Q", "affine_rho"),
                        "Planning_polygon_delta": delta("P_ONLY", "P_PLUS_Q", "polygon_rho"),
                        "Planning_anchored_polygon_delta": delta("P_ONLY", "P_PLUS_Q", "anchored_polygon_rho"),
                        "Fresh_delta": delta("P_ONLY", "P_PLUS_Q", "Fresh_rho"),
                    },
                    "P_given_Q": {
                        "Planning_affine_delta": delta("Q_ONLY", "P_PLUS_Q", "affine_rho"),
                        "Planning_polygon_delta": delta("Q_ONLY", "P_PLUS_Q", "polygon_rho"),
                        "Planning_anchored_polygon_delta": delta("Q_ONLY", "P_PLUS_Q", "anchored_polygon_rho"),
                        "Fresh_delta": delta("Q_ONLY", "P_PLUS_Q", "Fresh_rho"),
                    },
                }
                q_false = any(
                    float(marginals[key]["Planning_affine_delta"]) < -1e-4
                    and float(marginals[key]["Fresh_delta"]) > 1e-4
                    for key in ("Q_from_ZERO", "Q_given_P")
                )
                decompositions[day] = {
                    "source_case": "B2",
                    "max_abs_P_kW": float(np.max(np.abs(mess["P_kw"]))),
                    "max_abs_Q_kvar": float(np.max(np.abs(mess["Q_kvar"]))),
                    "records": records,
                    "marginal_effects": marginals,
                    "Q_false_benefit": q_false,
                    "runtime_seconds": time.perf_counter() - started,
                }
            finally:
                if odd is not None:
                    odd.Basic.ClearAll()
        finally:
            electrical.voltage.close()
            electrical.current.close()

    confirmed = any(bool(row["Q_false_benefit"]) for row in decompositions.values())
    existing["large_signal_decomposition"] = decompositions
    existing["classification"] = (
        "AFFINE_CURRENT_Q_EXPLOIT_CONFIRMED" if confirmed else "NO_Q_EXPLOIT_FOUND"
    )
    existing["status"] = "FAIL_AFFINE" if confirmed else "PASS"
    existing["interpretation"] = (
        "The +/-100 kvar local sweep is directionally faithful, but stored production-scale Q "
        "leaves that local region and creates an opposite-sign marginal rho effect."
        if confirmed
        else "Both local and stored production-scale Q effects are directionally reproduced by Fresh."
    )
    atomic_json(OUTPUT / "V35R2_Q_EXPLOIT_AUDIT.json", existing)
    print(json.dumps({
        "classification": existing["classification"],
        "days": decompositions,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
