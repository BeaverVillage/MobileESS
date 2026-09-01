"""Perfect-information B3 oracle equality and operational-regret checks."""

from __future__ import annotations

from typing import Any, Mapping


IDENTICAL_KEYS = (
    "resolution_minutes", "slots_per_day", "aidc_sites", "mess_units",
    "capacities_sha256", "objective", "constraints_sha256", "feeder_sha256",
    "thermal_authority_sha256", "opendss_settings_sha256", "solver_tolerance",
)


def verify_same_system(dayahead: Mapping[str, Any], pi: Mapping[str, Any]) -> None:
    differences = [key for key in IDENTICAL_KEYS if dayahead.get(key) != pi.get(key)]
    if differences:
        raise RuntimeError(f"V28_PI_SYSTEM_IDENTITY_FAILURE:{','.join(differences)}")


def operational_regret(actual: Mapping[str, float], pi: Mapping[str, float]) -> dict[str, float]:
    return {
        "R_op_AC": float(actual["rho_max_AC"]) - float(pi["rho_max_AC"]),
        "objective_regret": float(actual["objective"]) - float(pi["objective"]),
        "peak_PCC_regret": float(actual["peak_PCC_MW"]) - float(pi["peak_PCC_MW"]),
        "backlog_regret": float(actual["terminal_backlog_GPU_h"]) - float(pi["terminal_backlog_GPU_h"]),
        "MESS_execution_regret": float(pi["MESS_throughput_kWh"]) - float(actual["MESS_throughput_kWh"]),
        "thermal_overhead_regret": float(actual["thermal_overhead_kWh"]) - float(pi["thermal_overhead_kWh"]),
    }
