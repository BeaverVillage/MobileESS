"""Fresh-process 96-slot OpenDSS QSTS orchestration and physical KPI audit."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from .grid_lp import phase_mask_metrics
from .science_firewall import AuthorityGate, CURRENT_AIDC_GATE


class OpenDSSEngine(Protocol):
    def load_clean_ieee123(self) -> None: ...
    def solve_slot(self, slot: int, schedule_record: Mapping[str, object]) -> Mapping[str, object]: ...
    def close(self) -> None: ...


def schedule_sha256(schedule: Sequence[Mapping[str, object]]) -> str:
    return hashlib.sha256(json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class QSTSResult:
    namespace: str
    schedule_sha256: str
    line_loading_pu: Mapping[tuple[str, str, int], float]
    voltage_pu: Mapping[tuple[str, str, int], float]
    transformer_loading_pu: Mapping[tuple[str, str, int], float]
    metrics: Mapping[str, float]


def run_qsts(
    engine_factory: Callable[[], OpenDSSEngine],
    schedule: Sequence[Mapping[str, object]],
    ampacity_a: Mapping[tuple[str, str], float],
    line_phase_present: Mapping[tuple[str, str], bool],
    bus_phase_present: Mapping[tuple[str, str], bool],
    *,
    namespace: str,
    production: bool = False,
    gate: AuthorityGate = CURRENT_AIDC_GATE,
) -> QSTSResult:
    if len(schedule) != 96:
        raise ValueError("OpenDSS QSTS requires exactly 96 frozen slots")
    if namespace not in {"FORECAST_PLANNING", "REALIZED_REPLAY"}:
        raise ValueError("forecast and realized OpenDSS namespaces are fixed and separate")
    if production:
        gate.require()
    before = schedule_sha256(schedule)
    engine = engine_factory()
    line_loading: dict[tuple[str, str, int], float] = {}
    voltage: dict[tuple[str, str, int], float] = {}
    transformer: dict[tuple[str, str, int], float] = {}
    try:
        engine.load_clean_ieee123()
        for slot, record in enumerate(schedule):
            raw = engine.solve_slot(slot, record)
            for (line, phase), current in raw.get("line_current_a", {}).items():
                if line_phase_present.get((line, phase), False):
                    line_loading[(line, phase, slot)] = abs(float(current)) / float(ampacity_a[(line, phase)])
            for (bus, phase), value in raw.get("voltage_pu", {}).items():
                if bus_phase_present.get((bus, phase), False):
                    voltage[(bus, phase, slot)] = float(value)
            for (tx, phase), value in raw.get("transformer_loading_pu", {}).items():
                transformer[(tx, phase, slot)] = float(value)
    finally:
        engine.close()
    if schedule_sha256(schedule) != before:
        raise RuntimeError("OPENDSS_MODIFIED_FROZEN_SCHEDULE")
    load_metrics = phase_mask_metrics(line_loading, line_phase_present)
    voltage_metrics = phase_mask_metrics(voltage, bus_phase_present)
    exposure = sum(value >= 0.90 for value in line_loading.values()) / max(len(line_loading), 1)
    metrics = {
        "rho_max_AC": load_metrics["max"],
        "p95_loading": load_metrics["p95"],
        "p99_loading": load_metrics["p99"],
        "rho_ge_0_90_exposure": exposure,
        "Vmin": voltage_metrics["min"],
        "Vmax": voltage_metrics["max"],
        "DeltaVmax": max(abs(voltage_metrics["min"] - 1), abs(voltage_metrics["max"] - 1)),
        "transformer_loading_max": max(transformer.values(), default=0.0),
    }
    return QSTSResult(namespace, before, line_loading, voltage, transformer, metrics)


def assert_namespace_non_overwrite(existing: Mapping[str, object], new_namespace: str) -> None:
    if new_namespace in existing:
        raise FileExistsError(f"OpenDSS namespace already exists: {new_namespace}")


def classify_g13(case: str, result: QSTSResult, *, convergence_count: int = 96) -> str:
    if convergence_count != 96:
        return "RELEASE_FAIL" if case == "B3_JOINT_PROPOSED" else "BENCHMARK_INFEASIBLE"
    metrics=result.metrics
    violated=(metrics["rho_max_AC"]>1.0+1e-9 or metrics["Vmin"]<0.95-1e-9 or metrics["Vmax"]>1.05+1e-9 or metrics["transformer_loading_max"]>1.0+1e-9)
    if violated:
        return "RELEASE_FAIL" if case == "B3_JOINT_PROPOSED" else "BENCHMARK_INFEASIBLE"
    return "PASS"
