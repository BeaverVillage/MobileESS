"""Physics-only energy bridge for a selected V33M Dijkstra path."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping

from pfr.mobility_physics import MobilityPhysics

from .contracts import RoadLink


DEFAULT_PHYSICS_CONTRACT = (
    Path(__file__).resolve().parents[2] / "pfr" / "contracts" / "MESS_MOBILITY_PHYSICS_V1.json"
)


@dataclass(frozen=True)
class RouteGeometry:
    route_distance_km: float
    cumulative_ascent_m: float
    cumulative_descent_m: float

    def physics_mapping(self) -> Mapping[str, object]:
        return {
            "route_distance_km": self.route_distance_km,
            "cumulative_ascent_m": self.cumulative_ascent_m,
            "cumulative_descent_m": self.cumulative_descent_m,
        }


class PhysicsMobilityEnergyAdapter:
    """Travel time is ML; energy is deterministic longitudinal physics."""

    def __init__(self, contract_path: Path = DEFAULT_PHYSICS_CONTRACT) -> None:
        self.contract_path = Path(contract_path)
        self.physics_contract_sha = hashlib.sha256(self.contract_path.read_bytes()).hexdigest()
        self.physics = MobilityPhysics.from_contract(self.contract_path)

    @staticmethod
    def geometry_for_path(
        route_link_ids: tuple[str, ...], links_by_id: Mapping[str, RoadLink]
    ) -> RouteGeometry:
        selected = tuple(links_by_id[link_id] for link_id in route_link_ids)
        return RouteGeometry(
            route_distance_km=sum(link.distance_km for link in selected),
            cumulative_ascent_m=sum(link.cumulative_ascent_m for link in selected),
            cumulative_descent_m=sum(link.cumulative_descent_m for link in selected),
        )

    def route_energy_kwh(
        self,
        geometry: RouteGeometry,
        q10_eta_sec: float,
        q50_eta_sec: float,
        q90_eta_sec: float,
    ) -> tuple[float, float]:
        q10_energy = self.physics.energy_kwh(geometry.physics_mapping(), q10_eta_sec)
        nominal = self.physics.energy_kwh(geometry.physics_mapping(), q50_eta_sec)
        q90_energy = self.physics.energy_kwh(geometry.physics_mapping(), q90_eta_sec)
        return nominal, max(q10_energy, nominal, q90_energy)
