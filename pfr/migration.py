"""Fail-closed authority for checkpoint-aware inter-IDC migration."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence


IDCS = tuple(f"IDC{index:02d}" for index in range(1, 13))


class MigrationAuthorityError(ValueError):
    pass


@dataclass(frozen=True)
class WanLink:
    a: str
    b: str
    capacity_mbps: float


@dataclass(frozen=True)
class MigrationAuthority:
    authority_id: str
    fingerprint: str
    checkpoint_interval_steps: int
    checkpoint_bytes_per_gpu: int
    restart_steps: int
    maximum_active_transfers: int
    minimum_gpu_squared_improvement: float
    downtime_penalty_per_gpu_step: float
    idc_to_wan_node: Mapping[str, str]
    links: tuple[WanLink, ...]
    dataset_residency_mode: str
    step_seconds: int

    def validate(self) -> None:
        if not self.authority_id or len(self.fingerprint) != 64:
            raise MigrationAuthorityError("migration authority identity is invalid")
        if self.checkpoint_interval_steps <= 0 or self.checkpoint_bytes_per_gpu <= 0:
            raise MigrationAuthorityError("checkpoint authority must be positive")
        if self.restart_steps < 0 or self.maximum_active_transfers != 1:
            raise MigrationAuthorityError("only one serialized migration is authorized")
        if self.step_seconds != 300:
            raise MigrationAuthorityError("WAN authority must use the five-minute step")
        if self.dataset_residency_mode != "PRESTAGED_AT_ALL_12_IDCS":
            raise MigrationAuthorityError("unsupported dataset residency authority")
        if set(self.idc_to_wan_node) != set(IDCS):
            raise MigrationAuthorityError("WAN node mapping must cover all 12 IDCs")
        nodes = set(self.idc_to_wan_node.values())
        if len(nodes) != 12:
            raise MigrationAuthorityError("IDC-to-WAN mapping must be one-to-one")
        if not self.links:
            raise MigrationAuthorityError("WAN topology is empty")
        if any(
            link.a not in nodes
            or link.b not in nodes
            or link.a == link.b
            or not math.isfinite(link.capacity_mbps)
            or link.capacity_mbps <= 0.0
            for link in self.links
        ):
            raise MigrationAuthorityError("WAN link is invalid")
        for source in IDCS:
            for destination in IDCS:
                if source != destination:
                    self.route(source, destination)

    def checkpoint_payload_bytes(self, requested_gpu: int) -> int:
        if requested_gpu <= 0:
            raise MigrationAuthorityError("migration GPU gang must be positive")
        return requested_gpu * self.checkpoint_bytes_per_gpu

    def route(self, source_idc: str, destination_idc: str) -> tuple[WanLink, ...]:
        if source_idc not in self.idc_to_wan_node or destination_idc not in self.idc_to_wan_node:
            raise MigrationAuthorityError("migration endpoint is outside the WAN authority")
        if source_idc == destination_idc:
            return ()
        source = self.idc_to_wan_node[source_idc]
        destination = self.idc_to_wan_node[destination_idc]
        adjacency: dict[str, list[tuple[str, WanLink]]] = {
            node: [] for node in self.idc_to_wan_node.values()
        }
        for link in self.links:
            adjacency[link.a].append((link.b, link))
            adjacency[link.b].append((link.a, link))
        queue = deque([(source, ())])
        visited = {source}
        while queue:
            node, path = queue.popleft()
            for neighbor, link in sorted(adjacency[node], key=lambda row: row[0]):
                if neighbor in visited:
                    continue
                candidate = path + (link,)
                if neighbor == destination:
                    return candidate
                visited.add(neighbor)
                queue.append((neighbor, candidate))
        raise MigrationAuthorityError("WAN topology is disconnected")

    def transfer_capacity_bytes_per_step(
        self, source_idc: str, destination_idc: str
    ) -> int:
        route = self.route(source_idc, destination_idc)
        if not route:
            return 0
        bottleneck_mbps = min(link.capacity_mbps for link in route)
        return int(math.floor(bottleneck_mbps * 1_000_000.0 / 8.0 * self.step_seconds))

    def transfer_steps(
        self, payload_bytes: int, source_idc: str, destination_idc: str
    ) -> int:
        if payload_bytes <= 0:
            raise MigrationAuthorityError("migration payload must be positive")
        capacity = self.transfer_capacity_bytes_per_step(source_idc, destination_idc)
        if capacity <= 0:
            raise MigrationAuthorityError("migration route has no transfer capacity")
        return math.ceil(payload_bytes / capacity)


def load_migration_authority(path: Path) -> MigrationAuthority:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema_version") != "IDC_MIGRATION_AUTHORITY_V1":
        raise MigrationAuthorityError("unknown migration authority schema")
    checkpoint = payload["checkpoint"]
    wan = payload["wan"]
    optimizer = payload["placement_optimizer"]
    source_sha256 = str(wan["source"]["sha256"])
    if len(source_sha256) != 64:
        raise MigrationAuthorityError("WAN raw-source SHA-256 is invalid")
    authority = MigrationAuthority(
        authority_id=str(payload["authority_id"]),
        fingerprint=hashlib.sha256(raw).hexdigest(),
        checkpoint_interval_steps=int(checkpoint["interval_steps"]),
        checkpoint_bytes_per_gpu=int(checkpoint["checkpoint_bytes_per_gpu"]),
        restart_steps=int(checkpoint["restart_steps"]),
        maximum_active_transfers=int(wan["maximum_active_transfers"]),
        minimum_gpu_squared_improvement=float(
            optimizer["minimum_gpu_squared_improvement"]
        ),
        downtime_penalty_per_gpu_step=float(
            optimizer["downtime_penalty_per_gpu_step"]
        ),
        idc_to_wan_node={
            str(key): str(value) for key, value in payload["idc_to_wan_node"].items()
        },
        links=tuple(
            WanLink(str(row["a"]), str(row["b"]), float(row["capacity_mbps"]))
            for row in payload["undirected_links"]
        ),
        dataset_residency_mode=str(payload["dataset_residency"]["mode"]),
        step_seconds=int(wan["step_seconds"]),
    )
    authority.validate()
    return authority
