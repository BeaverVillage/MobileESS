"""Deterministic MESS traction-energy calculation from route geometry and ETA."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping, Sequence


class MobilityPhysicsContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class MobilityPhysics:
    mass_kg: float
    gravity_mps2: float
    rolling_resistance_coefficient: float
    air_density_kg_per_m3: float
    air_drag_coefficient: float
    front_surface_area_m2: float
    drivetrain_efficiency: float
    regenerative_braking_efficiency: float
    auxiliary_power_kw: float

    @classmethod
    def from_contract(cls, path: Path) -> "MobilityPhysics":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != "mobileess.mess_mobility_physics.v1"
            or payload.get("status") != "FROZEN_PHYSICS_ONLY"
            or payload.get("mobility_energy_ml_loaded") is not False
            or payload.get("traffic_ml_role") != "ETA_ONLY"
        ):
            raise MobilityPhysicsContractError("mobility physics authority is invalid")
        values = payload.get("parameters", {})
        try:
            physics = cls(
                mass_kg=float(values["gross_vehicle_mass_kg"]),
                gravity_mps2=float(values["gravity_mps2"]),
                rolling_resistance_coefficient=float(
                    values["rolling_resistance_coefficient"]
                ),
                air_density_kg_per_m3=float(values["air_density_kg_per_m3"]),
                air_drag_coefficient=float(values["air_drag_coefficient"]),
                front_surface_area_m2=float(values["front_surface_area_m2"]),
                drivetrain_efficiency=float(values["drivetrain_efficiency"]),
                regenerative_braking_efficiency=float(
                    values["regenerative_braking_efficiency"]
                ),
                auxiliary_power_kw=float(values["battery_side_auxiliary_power_kw"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MobilityPhysicsContractError(
                "mobility physics parameters are incomplete"
            ) from exc
        physics.validate()
        return physics

    def validate(self) -> None:
        positive = (
            self.mass_kg,
            self.gravity_mps2,
            self.rolling_resistance_coefficient,
            self.air_density_kg_per_m3,
            self.air_drag_coefficient,
            self.front_surface_area_m2,
            self.drivetrain_efficiency,
            self.auxiliary_power_kw,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise MobilityPhysicsContractError(
                "mobility physics parameters must be finite and positive"
            )
        if not 0.0 < self.drivetrain_efficiency <= 1.0:
            raise MobilityPhysicsContractError("drivetrain efficiency is invalid")
        if not 0.0 <= self.regenerative_braking_efficiency <= 1.0:
            raise MobilityPhysicsContractError("regeneration efficiency is invalid")

    def energy_components_kwh(
        self, route: Mapping[str, object], eta_seconds: float
    ) -> Mapping[str, float]:
        self.validate()
        try:
            distance_m = float(route["route_distance_km"]) * 1000.0
            ascent_m = float(route["cumulative_ascent_m"])
            descent_m = float(route["cumulative_descent_m"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MobilityPhysicsContractError(
                "route lacks deterministic physics geometry"
            ) from exc
        if (
            not math.isfinite(eta_seconds)
            or eta_seconds <= 0.0
            or not math.isfinite(distance_m)
            or distance_m <= 0.0
            or not math.isfinite(ascent_m)
            or ascent_m < 0.0
            or not math.isfinite(descent_m)
            or descent_m < 0.0
        ):
            raise MobilityPhysicsContractError("route physics inputs are invalid")

        speed_mps = distance_m / eta_seconds
        joules_per_kwh = 3.6e6
        rolling = (
            self.mass_kg
            * self.gravity_mps2
            * self.rolling_resistance_coefficient
            * distance_m
            / self.drivetrain_efficiency
            / joules_per_kwh
        )
        aerodynamic = (
            0.5
            * self.air_density_kg_per_m3
            * self.air_drag_coefficient
            * self.front_surface_area_m2
            * speed_mps**2
            * distance_m
            / self.drivetrain_efficiency
            / joules_per_kwh
        )
        grade = (
            self.mass_kg
            * self.gravity_mps2
            * (
                ascent_m / self.drivetrain_efficiency
                - self.regenerative_braking_efficiency * descent_m
            )
            / joules_per_kwh
        )
        auxiliary = self.auxiliary_power_kw * eta_seconds / 3600.0
        total = rolling + aerodynamic + grade + auxiliary
        if not math.isfinite(total) or total <= 0.0:
            raise MobilityPhysicsContractError(
                "deterministic route energy must be finite and positive"
            )
        return {
            "rolling_kwh": rolling,
            "aerodynamic_kwh": aerodynamic,
            "grade_kwh": grade,
            "auxiliary_kwh": auxiliary,
            "total_kwh": total,
        }

    def energy_kwh(self, route: Mapping[str, object], eta_seconds: float) -> float:
        return float(self.energy_components_kwh(route, eta_seconds)["total_kwh"])

    def forecast_energy_kwh(
        self, route: Mapping[str, object], eta_quantiles_seconds: Sequence[float]
    ) -> tuple[float, float]:
        if len(eta_quantiles_seconds) != 3:
            raise MobilityPhysicsContractError("ETA authority must provide q10/q50/q90")
        eta = tuple(float(value) for value in eta_quantiles_seconds)
        if not 0.0 < eta[0] <= eta[1] <= eta[2]:
            raise MobilityPhysicsContractError("ETA quantiles are invalid or unordered")
        energy = tuple(self.energy_kwh(route, value) for value in eta)
        return energy[1], max(energy)
