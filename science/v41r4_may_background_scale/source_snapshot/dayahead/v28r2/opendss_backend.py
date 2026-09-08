"""Fresh-context, 96-slot production OpenDSS execution for V28R2."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .electrical_context import ElectricalContext
from .opendss_mapping import (
    CAPACITORS, REGULATORS, FeederAssets,
    apply_frozen_native_state, apply_trajectory_slot, compile_clean_engine,
)
from .opendss_results import OpenDSSResult
from .trajectory import FrozenTrajectory


ProgressCallback = Callable[[dict[str, object]], None]


def _voltage_vector(odd: object, nodes: tuple[str, ...]) -> np.ndarray:
    values = dict(zip(
        (str(name).lower() for name in odd.Circuit.AllNodeNames()),
        map(float, odd.Circuit.AllBusMagPu()), strict=True,
    ))
    try:
        return np.asarray([values[name.lower()] for name in nodes], dtype=float)
    except KeyError as error:
        raise RuntimeError(f"V28R2_OPENDSS_NODE_AXIS:{error}") from error


def _branch_measurement(odd: object, branch: object) -> tuple[float, float, float]:
    odd.Circuit.SetActiveElement(branch.branch_id)
    if str(odd.CktElement.Name()).lower() != branch.branch_id.lower():
        raise RuntimeError(f"V28R2_OPENDSS_BRANCH_NOT_FOUND:{branch.branch_id}")
    conductors = int(odd.CktElement.NumConductors())
    buses = [str(value).split(".", 1)[0].lower() for value in odd.CktElement.BusNames()]
    terminal = buses.index(str(branch.parent_bus).lower())
    nodes = list(map(int, odd.CktElement.NodeOrder()))
    currents = list(map(float, odd.CktElement.CurrentsMagAng()))
    powers = list(map(float, odd.CktElement.Powers()))
    wanted = "ABC".index(branch.phase) + 1
    local = next(
        index for index in range(conductors)
        if nodes[terminal * conductors + index] == wanted
    )
    position = terminal * conductors + local
    current_a = float(currents[2 * position])
    if branch.branch_id.startswith("line."):
        odd.Lines.Name(branch.branch_id.split(".", 1)[1])
        rated_current_a = float(odd.Lines.NormAmps())
        transformer_kva_loading = math.nan
    else:
        odd.Transformers.Name(branch.branch_id.split(".", 1)[1])
        winding = terminal + 1; odd.Transformers.Wdg(winding)
        rating_kva = float(odd.Transformers.kVA())
        kv = float(odd.Transformers.kV())
        phases = int(odd.CktElement.NumPhases())
        rated_current_a = rating_kva / (math.sqrt(3.0) * kv) if phases >= 2 else rating_kva / kv
        phase_positions = [
            terminal * conductors + index for index in range(conductors)
            if nodes[terminal * conductors + index] in (1, 2, 3)
        ]
        p_kw = sum(float(powers[2 * index]) for index in phase_positions)
        q_kvar = sum(float(powers[2 * index + 1]) for index in phase_positions)
        transformer_kva_loading = math.hypot(p_kw, q_kvar) / rating_kva
    if rated_current_a <= 0:
        raise RuntimeError(f"V28R2_OPENDSS_BRANCH_RATING:{branch.branch_id}")
    return current_a, current_a / rated_current_a, transformer_kva_loading


def _native_state(odd: object) -> tuple[list[float], list[int]]:
    taps = []
    for name in REGULATORS:
        odd.Transformers.Name(name); odd.Transformers.Wdg(2)
        taps.append(float(odd.Transformers.Tap()))
    caps = []
    for name in CAPACITORS:
        odd.Capacitors.Name(name)
        state = list(map(int, odd.Capacitors.States()))
        if len(state) != 1:
            raise RuntimeError(f"V28R2_OPENDSS_CAPACITOR_STATE:{name}")
        caps.append(state[0])
    return taps, caps


def run_fresh_opendss(
    *, repo: Path, context: ElectricalContext, voltage: object,
    trajectory: FrozenTrajectory, output: Path | None = None,
    progress: ProgressCallback | None = None,
) -> OpenDSSResult:
    """Run a schedule unchanged through one new OpenDSS engine context."""

    trajectory.validate()
    before = trajectory.immutable_sha256
    _reference, _vintage, _background, binding, _cache, _authority = context.legacy_context
    nodes = tuple(map(str, voltage["node_names"]))
    node_phases = tuple("ABC"[int(name.rsplit(".", 1)[1]) - 1] for name in nodes)
    branches = tuple(binding.factories[0].data.branches)
    branch_names = tuple(str(branch.branch_id) for branch in branches)
    branch_phases = tuple(str(branch.phase) for branch in branches)
    branch_kinds = tuple("transformer" if name.startswith("transformer.") else "line" for name in branch_names)
    voltage_rows = np.zeros((96, len(nodes)), dtype=float)
    current_a = np.zeros((96, len(branches)), dtype=float)
    current_pu = np.zeros((96, len(branches)), dtype=float)
    tx_kva_pu = np.full((96, len(branches)), np.nan, dtype=float)
    losses = np.zeros((96, 2), dtype=float)
    taps = np.zeros((96, len(REGULATORS)), dtype=float)
    caps = np.zeros((96, len(CAPACITORS)), dtype=int)
    converged = np.zeros(96, dtype=bool)
    assets = FeederAssets.from_repo(repo)
    started = time.perf_counter()
    odd, adapter = compile_clean_engine(assets)
    version = str(odd.Basic.Version())
    try:
        for slot in range(96):
            apply_trajectory_slot(odd, adapter, context, trajectory, slot)
            apply_frozen_native_state(odd, voltage, slot)
            odd.Solution.SolveSnap()
            converged[slot] = bool(odd.Solution.Converged())
            if not converged[slot]:
                raise RuntimeError(
                    f"V28R2_OPENDSS_NONCONVERGENCE:{trajectory.namespace}:{trajectory.case}:{slot}"
                )
            voltage_rows[slot] = _voltage_vector(odd, nodes)
            for index, branch in enumerate(branches):
                current_a[slot, index], current_pu[slot, index], tx_kva_pu[slot, index] = _branch_measurement(odd, branch)
            raw_losses = list(map(float, odd.Circuit.Losses()))
            losses[slot] = np.asarray(raw_losses[:2], dtype=float) / 1000.0
            taps[slot], caps[slot] = _native_state(odd)
            if progress is not None:
                progress({
                    "active_OpenDSS_trajectory": f"{trajectory.namespace}:{trajectory.case}",
                    "OpenDSS_slot": slot + 1, "OpenDSS_slots_total": 96,
                    "OpenDSS_solve_count": slot + 1,
                })
    finally:
        odd.Basic.ClearAll()
    if trajectory.immutable_sha256 != before:
        raise RuntimeError("V28R2_OPENDSS_MODIFIED_FROZEN_SCHEDULE")
    result = OpenDSSResult(
        trajectory.day, trajectory.namespace, trajectory.case,
        trajectory.source_schedule_sha256, nodes, node_phases,
        branch_names, branch_phases, branch_kinds, converged, voltage_rows,
        current_a, current_pu, tx_kva_pu, losses, taps, caps, version,
        time.perf_counter() - started,
    )
    result.validate()
    if output is not None:
        result.write(output)
    return result
