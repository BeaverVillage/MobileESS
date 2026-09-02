"""Convert native 5-minute ML link forecasts into 15-minute MESS parameters."""

from __future__ import annotations

import math
from typing import Mapping

from .contracts import (
    CONNECTION_DELAY_SECONDS,
    OPTIMIZATION_RESOLUTION_SECONDS,
    LinkTravelTimeForecast,
    MobilityContractError,
    RoadGraphAuthority,
    RouteParameters15Min,
)
from .dijkstra_router import DeterministicDijkstraRouter, DijkstraPath
from .mobility_physics_adapter import PhysicsMobilityEnergyAdapter


def forecast_step_for_departure_slot(departure_slot_15: int) -> int:
    if not 0 <= departure_slot_15 < 96:
        raise MobilityContractError("15-minute departure slot must be in [0, 95]")
    return departure_slot_15 * 3


def travel_slots_15min(q90_eta_sec: float) -> int:
    if not math.isfinite(q90_eta_sec) or q90_eta_sec < 0.0:
        raise MobilityContractError("Q90 ETA must be finite and non-negative")
    return math.ceil(q90_eta_sec / OPTIMIZATION_RESOLUTION_SECONDS)


def connection_ready_slots_15min(q90_eta_sec: float) -> int:
    if not math.isfinite(q90_eta_sec) or q90_eta_sec < 0.0:
        raise MobilityContractError("Q90 ETA must be finite and non-negative")
    return math.ceil(
        (q90_eta_sec + CONNECTION_DELAY_SECONDS) / OPTIMIZATION_RESOLUTION_SECONDS
    )


class Mobility15MinAdapter:
    def __init__(
        self,
        graph: RoadGraphAuthority,
        forecast: LinkTravelTimeForecast,
        physics: PhysicsMobilityEnergyAdapter | None = None,
    ) -> None:
        if set(forecast.link_ids) != {link.link_id for link in graph.links}:
            raise MobilityContractError("traffic forecast link axis must exactly match graph")
        self.graph = graph
        self.forecast = forecast
        self.physics = physics or PhysicsMobilityEnergyAdapter()
        self.router = DeterministicDijkstraRouter(graph)

    def stay(self, departure_slot_15: int, service_id: str) -> RouteParameters15Min:
        forecast_step_for_departure_slot(departure_slot_15)
        try:
            road_node = self.graph.service_to_road_node[service_id]
        except KeyError as exc:
            raise MobilityContractError(f"unknown service node: {service_id}") from exc
        return RouteParameters15Min(
            departure_slot_15=departure_slot_15,
            origin_service_id=service_id,
            destination_service_id=service_id,
            road_origin_node=road_node,
            road_destination_node=road_node,
            route_link_ids=(),
            route_distance_km=0.0,
            cumulative_ascent_m=0.0,
            cumulative_descent_m=0.0,
            route_q50_eta_sec=0.0,
            route_q90_eta_sec=0.0,
            travel_slots_15min=0,
            connection_ready_slots_15min=0,
            energy_nominal_kwh=0.0,
            energy_safe_kwh=0.0,
            route_graph_sha=self.graph.route_graph_sha,
            traffic_forecast_sha=self.forecast.traffic_forecast_sha,
            physics_contract_sha=self.physics.physics_contract_sha,
        )

    def _route_record(
        self,
        departure_slot_15: int,
        origin_service_id: str,
        destination_service_id: str,
        path: DijkstraPath,
        q50: Mapping[str, float],
        q90: Mapping[str, float],
    ) -> RouteParameters15Min:
        route_q50 = sum(q50[link_id] for link_id in path.link_ids)
        route_q90 = sum(q90[link_id] for link_id in path.link_ids)
        geometry = self.physics.geometry_for_path(path.link_ids, self.graph.links_by_id)
        nominal, safe = self.physics.route_energy_kwh(geometry, route_q50, route_q90)
        return RouteParameters15Min(
            departure_slot_15=departure_slot_15,
            origin_service_id=origin_service_id,
            destination_service_id=destination_service_id,
            road_origin_node=path.origin_node,
            road_destination_node=path.destination_node,
            route_link_ids=path.link_ids,
            route_distance_km=geometry.route_distance_km,
            cumulative_ascent_m=geometry.cumulative_ascent_m,
            cumulative_descent_m=geometry.cumulative_descent_m,
            route_q50_eta_sec=route_q50,
            route_q90_eta_sec=route_q90,
            travel_slots_15min=travel_slots_15min(route_q90),
            connection_ready_slots_15min=connection_ready_slots_15min(route_q90),
            energy_nominal_kwh=nominal,
            energy_safe_kwh=safe,
            route_graph_sha=self.graph.route_graph_sha,
            traffic_forecast_sha=self.forecast.traffic_forecast_sha,
            physics_contract_sha=self.physics.physics_contract_sha,
        )

    def routes_for_origin(
        self, departure_slot_15: int, origin_service_id: str
    ) -> tuple[RouteParameters15Min, ...]:
        """Run one single-source Q50 Dijkstra, then materialize every destination."""
        try:
            origin_node = self.graph.service_to_road_node[origin_service_id]
        except KeyError as exc:
            raise MobilityContractError(f"unknown service node: {origin_service_id}") from exc
        q50, q90 = self.forecast.snapshot(
            forecast_step_for_departure_slot(departure_slot_15)
        )
        paths = self.router.single_source(origin_node, q50)
        records = [self.stay(departure_slot_15, origin_service_id)]
        for destination_service_id in sorted(self.graph.service_to_road_node):
            if destination_service_id == origin_service_id:
                continue
            destination_node = self.graph.service_to_road_node[destination_service_id]
            path = self.router.require_path(paths, destination_node)
            records.append(
                self._route_record(
                    departure_slot_15,
                    origin_service_id,
                    destination_service_id,
                    path,
                    q50,
                    q90,
                )
            )
        return tuple(records)

    def route(
        self,
        departure_slot_15: int,
        origin_service_id: str,
        destination_service_id: str,
    ) -> RouteParameters15Min:
        if origin_service_id == destination_service_id:
            return self.stay(departure_slot_15, origin_service_id)
        try:
            origin_node = self.graph.service_to_road_node[origin_service_id]
            destination_node = self.graph.service_to_road_node[destination_service_id]
        except KeyError as exc:
            raise MobilityContractError(f"unknown service node: {exc.args[0]}") from exc
        q50, q90 = self.forecast.snapshot(
            forecast_step_for_departure_slot(departure_slot_15)
        )
        paths = self.router.single_source(origin_node, q50)
        path = self.router.require_path(paths, destination_node)
        return self._route_record(
            departure_slot_15,
            origin_service_id,
            destination_service_id,
            path,
            q50,
            q90,
        )
