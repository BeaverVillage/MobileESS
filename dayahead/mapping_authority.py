"""Role-separated road, AIDC-anchor, and Mobile ESS service-site metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class TrafficNode:
    traffic_node: str
    latitude: float
    longitude: float
    scats_id: str | None = None
    aidc_anchor: str | None = None
    mess_service_site: str | None = None

    def validate(self) -> None:
        if not self.traffic_node:
            raise ValueError("traffic_node is required")
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("invalid traffic-node coordinates")


@dataclass(frozen=True)
class MappingAuthority:
    authority_id: str
    nodes: tuple[TrafficNode, ...]
    route_edges: tuple[tuple[str, str], ...]
    scientific_eligible: bool = True

    def validate(self, *, production: bool = False) -> None:
        for node in self.nodes:
            node.validate()
        node_ids = tuple(node.traffic_node for node in self.nodes)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("duplicate traffic_node")
        known = set(node_ids)
        if any(source not in known or target not in known for source, target in self.route_edges):
            raise ValueError("route edge references an unknown traffic node")
        aidcs = [node.aidc_anchor for node in self.nodes if node.aidc_anchor]
        services = [node.mess_service_site for node in self.nodes if node.mess_service_site]
        if len(set(aidcs)) != len(aidcs) or len(set(services)) != len(services):
            raise ValueError("service roles must have unique authority identities")
        if production and not self.scientific_eligible:
            raise ValueError("NON_SCIENTIFIC_AUTHORITY_REJECTED_IN_PRODUCTION")

    @property
    def aidc_to_traffic(self) -> Mapping[str, str]:
        return {node.aidc_anchor: node.traffic_node for node in self.nodes if node.aidc_anchor}

    @property
    def service_to_traffic(self) -> Mapping[str, str]:
        return {node.mess_service_site: node.traffic_node for node in self.nodes if node.mess_service_site}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, production: bool = False) -> "MappingAuthority":
        result = cls(
            authority_id=str(payload["authority_id"]),
            nodes=tuple(TrafficNode(**record) for record in payload["nodes"]),
            route_edges=tuple((str(edge[0]), str(edge[1])) for edge in payload.get("route_edges", ())),
            scientific_eligible=bool(payload.get("scientific_eligible", False)),
        )
        result.validate(production=production)
        return result


def load_mapping_authority(path: Path, *, production: bool = False) -> MappingAuthority:
    return MappingAuthority.from_mapping(json.loads(path.read_text(encoding="utf-8")), production=production)
