"""Immutable contracts for the V33M K=1 mobility adapter."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping, Sequence


SAFE_ETA_AUTHORITY = "DEVELOPMENT_Q90_ONLY_PENDING_CALIBRATION_AUDIT"
ROUTING_TIME_MODEL = "DEPARTURE_EPOCH_STATIC_FORECAST_SNAPSHOT"
TRAFFIC_RESOLUTION_SECONDS = 300
OPTIMIZATION_RESOLUTION_SECONDS = 900
CONNECTION_DELAY_SECONDS = 600


class MobilityContractError(ValueError):
    """Raised when graph, forecast, or route data violates the adapter contract."""


@dataclass(frozen=True)
class RoadLink:
    link_id: str
    from_node: str
    to_node: str
    distance_km: float
    cumulative_ascent_m: float = 0.0
    cumulative_descent_m: float = 0.0

    def __post_init__(self) -> None:
        if not self.link_id or not self.from_node or not self.to_node:
            raise MobilityContractError("road link identifiers must be non-empty")
        values = (
            self.distance_km,
            self.cumulative_ascent_m,
            self.cumulative_descent_m,
        )
        if any(not math.isfinite(value) for value in values):
            raise MobilityContractError("road link geometry must be finite")
        if self.distance_km <= 0.0:
            raise MobilityContractError("road link distance must be positive")
        if self.cumulative_ascent_m < 0.0 or self.cumulative_descent_m < 0.0:
            raise MobilityContractError("road link ascent/descent cannot be negative")


@dataclass(frozen=True)
class RoadGraphAuthority:
    links: tuple[RoadLink, ...]
    service_to_road_node: Mapping[str, str]
    route_graph_sha: str

    def __post_init__(self) -> None:
        links = tuple(self.links)
        mapping = dict(self.service_to_road_node)
        if not links:
            raise MobilityContractError("road graph must contain links")
        link_ids = [link.link_id for link in links]
        if len(link_ids) != len(set(link_ids)):
            raise MobilityContractError("road graph link IDs must be unique")
        if not mapping or any(not key or not value for key, value in mapping.items()):
            raise MobilityContractError("service-node mapping is missing or invalid")
        if len(mapping) != len(set(mapping)):
            raise MobilityContractError("service IDs must be unique")
        nodes = {link.from_node for link in links} | {link.to_node for link in links}
        missing = sorted(set(mapping.values()) - nodes)
        if missing:
            raise MobilityContractError(
                f"service mapping references absent road nodes: {missing}"
            )
        if not self.route_graph_sha:
            raise MobilityContractError("route graph SHA is required")
        object.__setattr__(self, "links", links)
        object.__setattr__(self, "service_to_road_node", MappingProxyType(mapping))

    @property
    def node_count(self) -> int:
        return len({link.from_node for link in self.links} | {link.to_node for link in self.links})

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def links_by_id(self) -> Mapping[str, RoadLink]:
        return MappingProxyType({link.link_id: link for link in self.links})


@dataclass(frozen=True)
class LinkTravelTimeForecast:
    """Already-materialized native 5-minute link Q50/Q90 predictions."""

    link_ids: tuple[str, ...]
    link_q50_sec: tuple[tuple[float, ...], ...]
    link_q90_sec: tuple[tuple[float, ...], ...]
    traffic_forecast_sha: str = ""

    def __post_init__(self) -> None:
        link_ids = tuple(str(value) for value in self.link_ids)
        q50 = tuple(tuple(float(value) for value in row) for row in self.link_q50_sec)
        q90 = tuple(tuple(float(value) for value in row) for row in self.link_q90_sec)
        if not link_ids or len(link_ids) != len(set(link_ids)):
            raise MobilityContractError("forecast link IDs must be non-empty and unique")
        if not q50 or len(q50) != len(q90):
            raise MobilityContractError("Q50 and Q90 forecast steps must align")
        width = len(link_ids)
        for step, (median_row, safe_row) in enumerate(zip(q50, q90)):
            if len(median_row) != width or len(safe_row) != width:
                raise MobilityContractError(f"forecast width mismatch at step {step}")
            for median, safe in zip(median_row, safe_row):
                if not math.isfinite(median) or median <= 0.0:
                    raise MobilityContractError("all Q50 link costs must be finite and positive")
                if not math.isfinite(safe) or safe <= 0.0:
                    raise MobilityContractError("all Q90 link costs must be finite and positive")
                if safe < median:
                    raise MobilityContractError("Q90 link time cannot be below Q50")
        object.__setattr__(self, "link_ids", link_ids)
        object.__setattr__(self, "link_q50_sec", q50)
        object.__setattr__(self, "link_q90_sec", q90)
        if not self.traffic_forecast_sha:
            payload = {
                "link_ids": link_ids,
                "link_q50_sec": q50,
                "link_q90_sec": q90,
                "resolution_seconds": TRAFFIC_RESOLUTION_SECONDS,
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            object.__setattr__(self, "traffic_forecast_sha", digest)

    @classmethod
    def from_arrays(
        cls,
        link_ids: Sequence[str],
        link_q50_sec: Sequence[Sequence[float]],
        link_q90_sec: Sequence[Sequence[float]],
        traffic_forecast_sha: str = "",
    ) -> "LinkTravelTimeForecast":
        return cls(
            tuple(link_ids),
            tuple(tuple(row) for row in link_q50_sec),
            tuple(tuple(row) for row in link_q90_sec),
            traffic_forecast_sha,
        )

    @property
    def step_count(self) -> int:
        return len(self.link_q50_sec)

    def snapshot(self, forecast_step_5min: int) -> tuple[Mapping[str, float], Mapping[str, float]]:
        if not 0 <= forecast_step_5min < self.step_count:
            raise MobilityContractError(
                f"5-minute forecast step {forecast_step_5min} is unavailable"
            )
        q50 = MappingProxyType(dict(zip(self.link_ids, self.link_q50_sec[forecast_step_5min])))
        q90 = MappingProxyType(dict(zip(self.link_ids, self.link_q90_sec[forecast_step_5min])))
        return q50, q90


@dataclass(frozen=True)
class RouteParameters15Min:
    departure_slot_15: int
    origin_service_id: str
    destination_service_id: str
    road_origin_node: str
    road_destination_node: str
    route_link_ids: tuple[str, ...]
    route_distance_km: float
    cumulative_ascent_m: float
    cumulative_descent_m: float
    route_q50_eta_sec: float
    route_q90_eta_sec: float
    travel_slots_15min: int
    connection_ready_slots_15min: int
    energy_nominal_kwh: float
    energy_safe_kwh: float
    route_graph_sha: str
    traffic_forecast_sha: str
    physics_contract_sha: str

    def to_dict(self) -> dict[str, object]:
        return {
            "departure_slot_15": self.departure_slot_15,
            "origin_service_id": self.origin_service_id,
            "destination_service_id": self.destination_service_id,
            "road_origin_node": self.road_origin_node,
            "road_destination_node": self.road_destination_node,
            "route_link_ids": list(self.route_link_ids),
            "route_distance_km": self.route_distance_km,
            "cumulative_ascent_m": self.cumulative_ascent_m,
            "cumulative_descent_m": self.cumulative_descent_m,
            "route_q50_eta_sec": self.route_q50_eta_sec,
            "route_q90_eta_sec": self.route_q90_eta_sec,
            "travel_slots_15min": self.travel_slots_15min,
            "connection_ready_slots_15min": self.connection_ready_slots_15min,
            "energy_nominal_kwh": self.energy_nominal_kwh,
            "energy_safe_kwh": self.energy_safe_kwh,
            "route_graph_sha": self.route_graph_sha,
            "traffic_forecast_sha": self.traffic_forecast_sha,
            "physics_contract_sha": self.physics_contract_sha,
        }

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
