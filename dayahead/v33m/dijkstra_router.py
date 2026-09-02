"""Deterministic standard-library K=1 Dijkstra routing."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from types import MappingProxyType
from typing import Mapping

from .contracts import MobilityContractError, RoadGraphAuthority


class UnreachableDestinationError(MobilityContractError):
    pass


@dataclass(frozen=True)
class DijkstraPath:
    origin_node: str
    destination_node: str
    link_ids: tuple[str, ...]
    node_ids: tuple[str, ...]
    total_cost_sec: float


class DeterministicDijkstraRouter:
    """K=1 shortest paths; ties use link-ID sequence, then node-ID sequence."""

    def __init__(self, graph: RoadGraphAuthority) -> None:
        self.graph = graph
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for link in graph.links:
            adjacency.setdefault(link.from_node, []).append((link.link_id, link.to_node))
        self._adjacency = {
            node: tuple(sorted(edges)) for node, edges in adjacency.items()
        }

    def single_source(
        self, origin_node: str, link_q50_sec: Mapping[str, float]
    ) -> Mapping[str, DijkstraPath]:
        graph_link_ids = {link.link_id for link in self.graph.links}
        if set(link_q50_sec) != graph_link_ids:
            missing = sorted(graph_link_ids - set(link_q50_sec))
            extra = sorted(set(link_q50_sec) - graph_link_ids)
            raise MobilityContractError(
                f"link-cost axis does not match graph; missing={missing[:3]} extra={extra[:3]}"
            )
        for link_id, cost in link_q50_sec.items():
            if not math.isfinite(float(cost)) or float(cost) <= 0.0:
                raise MobilityContractError(
                    f"Dijkstra edge cost must be finite and positive: {link_id}"
                )

        nodes = {link.from_node for link in self.graph.links} | {
            link.to_node for link in self.graph.links
        }
        if origin_node not in nodes:
            raise MobilityContractError(f"origin road node is absent: {origin_node}")

        # Heap/best label: (cost, canonical link sequence, canonical node sequence, node).
        initial = (0.0, (), (origin_node,), origin_node)
        heap: list[tuple[float, tuple[str, ...], tuple[str, ...], str]] = [initial]
        best: dict[str, tuple[float, tuple[str, ...], tuple[str, ...]]] = {
            origin_node: initial[:3]
        }
        settled: dict[str, DijkstraPath] = {}
        while heap:
            cost, link_path, node_path, node = heapq.heappop(heap)
            if best.get(node) != (cost, link_path, node_path):
                continue
            if node in settled:
                continue
            settled[node] = DijkstraPath(
                origin_node, node, link_path, node_path, cost
            )
            for link_id, next_node in self._adjacency.get(node, ()):
                candidate = (
                    cost + float(link_q50_sec[link_id]),
                    link_path + (link_id,),
                    node_path + (next_node,),
                )
                current = best.get(next_node)
                if current is None or candidate < current:
                    best[next_node] = candidate
                    heapq.heappush(heap, (*candidate, next_node))
        return MappingProxyType(settled)

    @staticmethod
    def require_path(
        paths: Mapping[str, DijkstraPath], destination_node: str
    ) -> DijkstraPath:
        try:
            return paths[destination_node]
        except KeyError as exc:
            raise UnreachableDestinationError(
                f"destination road node is unreachable: {destination_node}"
            ) from exc
