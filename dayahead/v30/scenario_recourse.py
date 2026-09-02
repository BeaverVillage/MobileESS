"""Pre-April coupled day-block recourse scenarios and K certification."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .contracts import SCENARIO_CANDIDATES, canonical_sha256


@dataclass(frozen=True)
class CoupledScenario:
    source_day: str
    executable_service_factor: float
    rack_residual_capacity_factor: float
    background_loading_factor: float

    def payload(self) -> dict[str, object]:
        return {
            "source_day": self.source_day,
            "executable_service_factor": self.executable_service_factor,
            "rack_residual_capacity_factor": self.rack_residual_capacity_factor,
            "background_loading_factor": self.background_loading_factor,
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def build_day_population(repo: Path, trust_cache: Path) -> list[CoupledScenario]:
    """Join service, rack-availability proxy, and feeder state by historical day.

    Rack residual capacity is the observed non-executable fraction of requested
    strict-FULL node-hours, clipped away from zero.  It is intentionally kept on
    the same day as service and feeder state; no axis is shuffled independently.
    """

    root = repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"
    rows = _read_csv(root / "V29R2_EXEC_SERVICE_ROLLING_ORIGIN.csv")
    by_day: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        day = row["day"]
        if day >= "2025-04-01":
            raise RuntimeError("V30_APRIL_ROW_IN_SCENARIO_POPULATION")
        by_day.setdefault(day, []).append(row)
    result: list[CoupledScenario] = []
    anchor_root = trust_cache / "electrical_anchor"
    for day in sorted(by_day):
        selected = by_day[day]
        requested = sum(float(row["H_REQ"]) for row in selected)
        nominal = sum(float(row["H_NOM"]) for row in selected)
        realized = sum(float(row["H_REALIZED"]) for row in selected)
        service = min(1.5, realized / max(nominal, 1e-12))
        capacity = min(1.0, max(0.05, realized / max(requested, 1e-12)))
        cache = np.load(anchor_root / day / "D1_AC_ANCHOR.npz", allow_pickle=False)
        root_p = np.asarray(cache["root_pq"], dtype=float)[:, 0]
        background = float(np.max(root_p) / max(np.mean(root_p), 1e-12))
        result.append(CoupledScenario(day, service, capacity, background))
    if len(result) < 8:
        raise RuntimeError("V30_INSUFFICIENT_PREAPRIL_COUPLED_DAYS")
    # A day-block bootstrap is permitted to sample whole days with replacement.
    # Expand the 40 rolling-origin evaluation days to the K64 reference using a
    # frozen hash draw; all three axes always come from the same selected day.
    observed = tuple(result)
    draw = 0
    while len(result) < 64:
        digest = hashlib.sha256(f"V30_COUPLED_DAY_BOOTSTRAP_V1:{draw}".encode()).digest()
        result.append(observed[int.from_bytes(digest[:8], "big") % len(observed)])
        draw += 1
    return result


def _feature(population: list[CoupledScenario]) -> np.ndarray:
    values = np.asarray([[x.executable_service_factor, x.rack_residual_capacity_factor, x.background_loading_factor] for x in population])
    scale = np.ptp(values, axis=0)
    scale[scale == 0] = 1.0
    return (values - np.mean(values, axis=0)) / scale


def deterministic_nested_indices(population: list[CoupledScenario], count: int) -> list[int]:
    """Deterministic maximin day-block sample; candidates are nested prefixes."""

    features = _feature(population)
    center = np.mean(features, axis=0)
    first = int(np.argmax(np.sum((features - center) ** 2, axis=1)))
    chosen = [first]
    while len(chosen) < count:
        distances = np.min(np.sum((features[:, None, :] - features[chosen][None, :, :]) ** 2, axis=2), axis=1)
        distances[chosen] = -1.0
        chosen.append(int(np.argmax(distances)))
    return chosen


def scenario_set(population: list[CoupledScenario], count: int) -> list[CoupledScenario]:
    return [population[index] for index in deterministic_nested_indices(population, count)]


def metrics(values: list[CoupledScenario]) -> dict[str, float]:
    a = np.asarray([[x.executable_service_factor, x.rack_residual_capacity_factor, x.background_loading_factor] for x in values])
    service = float(np.mean(np.minimum(a[:, 0], a[:, 1])))
    unexecuted = float(1.0 - service)
    headroom = float(np.mean(np.maximum(0.0, a[:, 1] - np.minimum(a[:, 0], a[:, 1]))))
    movement = float(np.mean(np.abs(a[:, 0] - a[:, 1])))
    grid = float(np.max(a[:, 2] / np.maximum(a[:, 1], 0.05)))
    return {
        "first_stage_primary_grid_objective": grid,
        "expected_executable_service": service,
        "expected_unexecuted_service": unexecuted,
        "aggregate_recourse_headroom": headroom,
        "expected_recourse_movement_mass": movement,
    }


def certify_count(population: list[CoupledScenario]) -> tuple[list[dict[str, object]], dict[str, object], list[CoupledScenario]]:
    reference_set = scenario_set(population, 64)
    reference = metrics(reference_set)
    rows: list[dict[str, object]] = []
    selected = 64
    for count in SCENARIO_CANDIDATES:
        subset = scenario_set(population, count)
        current = metrics(subset)
        relative = {name: abs(value - reference[name]) / max(abs(reference[name]), 1e-12) for name, value in current.items()}
        # Predeclared structural rule: the 12 worst joint-stress day IDs in K
        # must be an ordered prefix of those in K64, and metric max error <=1%.
        stress = lambda x: x.background_loading_factor / max(x.rack_residual_capacity_factor, 0.05)
        top_ref = [x.source_day for x in sorted(reference_set, key=stress, reverse=True)[: min(12, count)]]
        top_cur = [x.source_day for x in sorted(subset, key=stress, reverse=True)[: min(12, count)]]
        stable = top_cur == top_ref
        passed = max(relative.values()) <= 0.01 and stable
        rows.append({
            "K": count, **current,
            **{f"relative_error_{name}": value for name, value in relative.items()},
            "structurally_stable": stable, "within_one_percent": max(relative.values()) <= 0.01,
            "selected": False, "April_rows_used": 0,
        })
        if passed and selected == 64:
            selected = count
    for row in rows:
        row["selected"] = row["K"] == selected
    chosen = scenario_set(population, selected)
    payload = [item.payload() for item in chosen]
    decision = {
        "artifact_id": "V30_SCENARIO_COUNT_DECISION_V1",
        "status": "PASS",
        "candidate_counts": list(SCENARIO_CANDIDATES),
        "reference_K": 64,
        "selection_rule": "smallest K within 1% on all five metrics and satisfying predeclared ordered worst-12 joint-stress structural rule; else 64",
        "V30_SCENARIO_COUNT": selected,
        "V30_SCENARIO_SET_SHA256": canonical_sha256(payload),
        "population_day_count": len(population),
        "population_unique_day_count": len({x.source_day for x in population}),
        "population_latest_day": max(x.source_day for x in population),
        "April_rows_used": 0,
        "coupling": "WHOLE_DAY_BLOCK_NO_INDEPENDENT_AXIS_SHUFFLE",
    }
    return rows, decision, chosen
