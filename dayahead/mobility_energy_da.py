"""Frozen Safe mobility-energy aggregation and causality contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from .input_contract import InputContractError, sum_energy_5_to_15


@dataclass(frozen=True)
class MobilityEnergyProfiles:
    safe_kwh: tuple[float, ...]
    q50_kwh: tuple[float, ...]
    source_profile_authority: str
    model_version: str
    source_hashes: tuple[str, ...]

    def aggregate(self) -> tuple[tuple[float, ...], tuple[float, ...], dict[str, object]]:
        safe = sum_energy_5_to_15(self.safe_kwh)
        q50 = sum_energy_5_to_15(self.q50_kwh)
        payload = {"safe_kwh": safe, "q50_kwh": q50, "aggregation": "5MIN_TO_15MIN_SUM_V1"}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return safe, q50, {
            "authority_id": "MESS_MOBILITY_ENERGY_DA_V1",
            "source_profile_authority": self.source_profile_authority,
            "model_version": self.model_version,
            "source_hashes": list(self.source_hashes),
            "aggregation": "5MIN_TO_15MIN_SUM_V1",
            "aggregation_sha256": digest,
            "safe_role": "HARD_SOC_AND_DEPARTURE_FEASIBILITY",
            "q50_role": "EXPECTED_REPORTING_ONLY",
        }


def departure_energy_required(safe_increments_kwh: Sequence[float]) -> float:
    """Energy available at departure may not include future regeneration."""
    return sum(max(0.0, float(value)) for value in safe_increments_kwh)


def assert_departure_feasible(energy_kwh: float, floor_kwh: float, safe_increments_kwh: Sequence[float]) -> None:
    required = departure_energy_required(safe_increments_kwh)
    if energy_kwh - required < floor_kwh - 1e-9:
        raise InputContractError("SAFE_DEPARTURE_ENERGY_INFEASIBLE_NO_FUTURE_REGEN_PRECREDIT")
