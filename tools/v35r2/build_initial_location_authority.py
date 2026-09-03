"""Freeze the V35R2 objective-independent initial MESS depot authority."""

from __future__ import annotations

import heapq
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v33m import load_road_graph_authority
from dayahead.v35.execution import MESS_INITIAL
from dayahead.v35.storage import atomic_json
from dayahead.v35.traffic_authority import ELEVATED, LINK_ORDER, PHYSICAL, SERVICE_NODES
from dayahead.v35r2.forensic import deterministic_farthest_point_cover


OUTPUT = REPO / "dayahead/artifacts/v35r2_aidc_mess_forensic"


def _distances() -> tuple[object, dict[tuple[str, str], float]]:
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for link in graph.links:
        adjacency.setdefault(link.from_node, []).append((link.to_node, link.distance_km))
        adjacency.setdefault(link.to_node, []).append((link.from_node, link.distance_km))

    def dijkstra(source: str) -> dict[str, float]:
        result = {source: 0.0}
        queue = [(0.0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != result[node]:
                continue
            for neighbor, weight in adjacency.get(node, ()):
                candidate = distance + float(weight)
                if candidate < result.get(neighbor, float("inf")):
                    result[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        return result

    stations = tuple(f"STA{index:02d}" for index in range(1, 13))
    by_station = {
        station: dijkstra(graph.service_to_road_node[station])
        for station in stations
    }
    distances = {
        (left, right): float(by_station[left][graph.service_to_road_node[right]])
        for left in stations
        for right in stations
    }
    return graph, distances


def main() -> None:
    graph, distances = _distances()
    stations = tuple(f"STA{index:02d}" for index in range(1, 13))
    selected = deterministic_farthest_point_cover(
        distances,
        stations,
        count=4,
        seed="STA01",
    )
    expected = tuple(MESS_INITIAL[f"MESS{index:02d}"] for index in range(1, 5))
    if selected != expected:
        raise RuntimeError(f"V35R2_INITIAL_LOCATION_AUTHORITY_DRIFT:{selected}:{expected}")
    nearest_selected = {
        service: min(
            distances[(service, other)]
            for other in selected
            if other != service
        )
        for service in selected
    }
    payload = {
        "artifact_id": "V35R2_MESS_INITIAL_LOCATION_AUDIT_V2",
        "status": "REPAIRED",
        "classification": "MESS_INITIAL_LOCATION_AUTHORITY_DEFECT_REPAIRED",
        "old_initial_locations": {
            "MESS01": "STA01",
            "MESS02": "STA02",
            "MESS03": "STA03",
            "MESS04": "STA04",
        },
        "old_authority": "sequential STA identifier enumeration; no external depot source",
        "new_initial_locations": MESS_INITIAL,
        "eligible_nodes": list(stations),
        "selection_rule": (
            "Seed lexicographically at STA01; repeatedly select the station "
            "maximizing minimum undirected shortest physical-road distance "
            "to selected stations; break exact ties lexicographically."
        ),
        "road_graph_SHA256": graph.route_graph_sha,
        "electrical_inputs_read_for_selection": 0,
        "April_objective_inputs_read_for_selection": 0,
        "traffic_forecast_inputs_read_for_selection": 0,
        "nearest_selected_distance_km": nearest_selected,
        "proof": "TOPOLOGY_ONLY_EXOGENOUS_ROAD_COVERAGE",
    }
    atomic_json(OUTPUT / "V35R2_MESS_INITIAL_LOCATION_AUDIT.json", payload)
    print(payload)


if __name__ == "__main__":
    main()

