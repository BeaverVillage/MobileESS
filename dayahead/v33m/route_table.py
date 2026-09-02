"""Deterministic immutable route-table construction for 15-minute MESS models."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Iterable, Mapping

from .contracts import MobilityContractError, RouteParameters15Min
from .mobility_15min_adapter import Mobility15MinAdapter


RouteKey = tuple[int, str, str]


@dataclass(frozen=True)
class MobilityRouteTable:
    departure_slots: tuple[int, ...]
    service_ids: tuple[str, ...]
    records: Mapping[RouteKey, RouteParameters15Min]
    canonical_sha256: str = ""

    def __post_init__(self) -> None:
        slots = tuple(sorted(set(int(slot) for slot in self.departure_slots)))
        services = tuple(sorted(set(str(service) for service in self.service_ids)))
        records = dict(self.records)
        expected = {
            (slot, origin, destination)
            for slot in slots
            for origin in services
            for destination in services
        }
        if not slots or not services or set(records) != expected:
            missing = sorted(expected - set(records))
            extra = sorted(set(records) - expected)
            raise MobilityContractError(
                f"route table must be a complete slot/origin/destination product; "
                f"missing={missing[:3]} extra={extra[:3]}"
            )
        for key, record in records.items():
            if key != (
                record.departure_slot_15,
                record.origin_service_id,
                record.destination_service_id,
            ):
                raise MobilityContractError(f"route-table key/record mismatch: {key}")
        object.__setattr__(self, "departure_slots", slots)
        object.__setattr__(self, "service_ids", services)
        object.__setattr__(self, "records", MappingProxyType(records))
        digest = hashlib.sha256(self.canonical_json_bytes()).hexdigest()
        if self.canonical_sha256 and self.canonical_sha256 != digest:
            raise MobilityContractError("route-table canonical SHA does not match content")
        object.__setattr__(self, "canonical_sha256", digest)

    def __getitem__(self, key: RouteKey) -> RouteParameters15Min:
        return self.records[key]

    def canonical_json_bytes(self) -> bytes:
        payload = {
            "departure_slots": list(self.departure_slots),
            "service_ids": list(self.service_ids),
            "routes": [
                self.records[key].to_dict()
                for key in sorted(self.records)
            ],
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")


def build_mobility_route_table(
    adapter: Mobility15MinAdapter,
    departure_slots: Iterable[int],
    service_ids: Iterable[str] | None = None,
) -> MobilityRouteTable:
    """Use exactly one single-source Dijkstra per departure slot and origin."""
    slots = tuple(sorted(set(int(slot) for slot in departure_slots)))
    services = tuple(
        sorted(
            set(
                adapter.graph.service_to_road_node
                if service_ids is None
                else (str(service) for service in service_ids)
            )
        )
    )
    unknown = sorted(set(services) - set(adapter.graph.service_to_road_node))
    if unknown:
        raise MobilityContractError(f"route-table services are unknown: {unknown}")
    records: dict[RouteKey, RouteParameters15Min] = {}
    for slot in slots:
        for origin in services:
            origin_records = {
                route.destination_service_id: route
                for route in adapter.routes_for_origin(slot, origin)
            }
            for destination in services:
                records[(slot, origin, destination)] = origin_records[destination]
    return MobilityRouteTable(slots, services, records)
