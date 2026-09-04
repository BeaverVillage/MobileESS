"""PFR7 compute-work and reachable-energy debt dynamics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Optional, Tuple


class DebtContractError(ValueError):
    """Raised when debt accounting loses its physical unit or reachability."""


class DebtAblation(str, Enum):
    A_DEBT0 = "A-Debt0"
    A_DEBT1 = "A-Debt1"

    @property
    def debt_aware_recovery(self) -> bool:
        return self is DebtAblation.A_DEBT1


@dataclass(frozen=True)
class DebtState:
    compute_debt_gpu_hours: float = 0.0
    energy_debt_kwh: float = 0.0

    def validate(self) -> None:
        values = (self.compute_debt_gpu_hours, self.energy_debt_kwh)
        if any(not math.isfinite(float(value)) or value < 0.0 for value in values):
            raise DebtContractError("dual debt must be finite and non-negative")


@dataclass(frozen=True)
class EnergyReachability:
    soc_available_kwh: float
    route_location_available_kwh: float
    plug_available_kwh: float
    d2_available_kwh: float
    charging_headroom_kwh: float
    grid_headroom_kwh: float

    @property
    def reachable_kwh(self) -> float:
        values = (
            self.soc_available_kwh,
            self.route_location_available_kwh,
            self.plug_available_kwh,
            self.d2_available_kwh,
            self.charging_headroom_kwh,
            self.grid_headroom_kwh,
        )
        if any(not math.isfinite(float(value)) or value < 0.0 for value in values):
            raise DebtContractError("energy reachability components must be finite and non-negative")
        return min(values)


def update_dual_debt(
    state: DebtState,
    *,
    compute_reference_gpu_hours: float,
    compute_executed_gpu_hours: float,
    energy_support_kwh: float,
    energy_repay_kwh: float,
    energy_reachability: EnergyReachability,
) -> DebtState:
    """Apply D_C+=[C_ref-C_exec] and D_E+=[E_support-E_repay]."""

    state.validate()
    values = (
        compute_reference_gpu_hours,
        compute_executed_gpu_hours,
        energy_support_kwh,
        energy_repay_kwh,
    )
    if any(not math.isfinite(float(value)) or value < 0.0 for value in values):
        raise DebtContractError("debt flows must be finite and non-negative")
    if energy_repay_kwh > energy_reachability.reachable_kwh + 1e-12:
        raise DebtContractError("energy repayment exceeds physically reachable energy")
    return DebtState(
        compute_debt_gpu_hours=max(
            0.0,
            state.compute_debt_gpu_hours
            + compute_reference_gpu_hours
            - compute_executed_gpu_hours,
        ),
        energy_debt_kwh=max(
            0.0,
            state.energy_debt_kwh + energy_support_kwh - energy_repay_kwh,
        ),
    )


@dataclass(frozen=True)
class RecoveryStep:
    compute_reference_gpu_hours: float
    compute_executed_gpu_hours: float
    energy_support_kwh: float
    energy_repay_kwh: float
    energy_reachability: EnergyReachability
    aggregate_power_kw: float
    deadline_misses: int
    terminal_soc: float

    def validate(self) -> None:
        if not math.isfinite(float(self.aggregate_power_kw)):
            raise DebtContractError("aggregate power must be finite")
        if self.deadline_misses < 0:
            raise DebtContractError("deadline misses cannot be negative")
        if not math.isfinite(float(self.terminal_soc)) or not 0.0 <= self.terminal_soc <= 1.0:
            raise DebtContractError("terminal SOC must lie in [0,1]")


@dataclass(frozen=True)
class DebtMetrics:
    ablation_id: str
    recovery_window_steps: int
    recovery_window_passed: bool
    rebound_peak_kw: float
    rebound_energy_area_kwh: float
    debt_clearance_duration_minutes: Optional[int]
    deadline_misses: int
    terminal_soc: float
    terminal_compute_debt_gpu_hours: float
    terminal_energy_debt_kwh: float


def evaluate_recovery(
    *,
    initial: DebtState,
    steps: Iterable[RecoveryStep],
    ablation: DebtAblation,
    step_minutes: int,
    baseline_power_kw: float,
    recovery_peak_limit_kw: float,
    epsilon_compute_gpu_hours: float,
    epsilon_energy_kwh: float,
) -> DebtMetrics:
    if step_minutes <= 0 or recovery_peak_limit_kw < baseline_power_kw:
        raise DebtContractError("recovery cadence or peak limit is invalid")
    if epsilon_compute_gpu_hours < 0.0 or epsilon_energy_kwh < 0.0:
        raise DebtContractError("recovery epsilons cannot be negative")
    frozen = tuple(steps)
    if not frozen:
        raise DebtContractError("recovery window cannot be empty")
    state = initial
    clearance_step: Optional[int] = None
    power = []
    misses = 0
    terminal_soc = math.nan
    for index, step in enumerate(frozen, start=1):
        step.validate()
        state = update_dual_debt(
            state,
            compute_reference_gpu_hours=step.compute_reference_gpu_hours,
            compute_executed_gpu_hours=step.compute_executed_gpu_hours,
            energy_support_kwh=step.energy_support_kwh,
            energy_repay_kwh=step.energy_repay_kwh,
            energy_reachability=step.energy_reachability,
        )
        power.append(step.aggregate_power_kw)
        misses += step.deadline_misses
        terminal_soc = step.terminal_soc
        if clearance_step is None and (
            state.compute_debt_gpu_hours <= epsilon_compute_gpu_hours
            and state.energy_debt_kwh <= epsilon_energy_kwh
        ):
            clearance_step = index
    peak = max(power)
    area = sum(max(0.0, value - baseline_power_kw) * step_minutes / 60.0 for value in power)
    passed = (
        state.compute_debt_gpu_hours <= epsilon_compute_gpu_hours
        and state.energy_debt_kwh <= epsilon_energy_kwh
        and peak <= recovery_peak_limit_kw
    )
    return DebtMetrics(
        ablation_id=ablation.value,
        recovery_window_steps=len(frozen),
        recovery_window_passed=passed,
        rebound_peak_kw=max(0.0, peak - baseline_power_kw),
        rebound_energy_area_kwh=area,
        debt_clearance_duration_minutes=None if clearance_step is None else clearance_step * step_minutes,
        deadline_misses=misses,
        terminal_soc=terminal_soc,
        terminal_compute_debt_gpu_hours=state.compute_debt_gpu_hours,
        terminal_energy_debt_kwh=state.energy_debt_kwh,
    )
