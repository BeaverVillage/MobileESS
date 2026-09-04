"""Load the frozen 509-link traffic graph and authoritative physical geometry."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterable, TextIO
import xml.etree.ElementTree as ET

from .contracts import MobilityContractError, RoadGraphAuthority, RoadLink


class RoadGraphAuthorityError(MobilityContractError):
    pass


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _traffic_node(value: str) -> str:
    raw = str(value).strip()
    match = re.fullmatch(r"(?:TN_)?(\d+)", raw, flags=re.IGNORECASE)
    return f"TN_{int(match.group(1)):02d}" if match else raw


def _file_manifest_sha(files: Iterable[tuple[str, Path]]) -> str:
    rows = []
    for role, path in files:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        rows.append(
            {
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_link_order(path: Path) -> list[dict[str, str]]:
    with _open_text(path) as handle:
        rows = list(csv.DictReader(handle))
    required = {"tensor_index", "reduced_link_id", "from_node", "to_node"}
    if not rows or not required.issubset(rows[0]):
        raise RoadGraphAuthorityError("link-order authority has an invalid schema")
    rows.sort(key=lambda row: int(row["tensor_index"]))
    if [int(row["tensor_index"]) for row in rows] != list(range(len(rows))):
        raise RoadGraphAuthorityError("link tensor indices must be contiguous from zero")
    if len({row["reduced_link_id"] for row in rows}) != len(rows):
        raise RoadGraphAuthorityError("reduced link IDs must be unique")
    return rows


def _read_service_mapping(path: Path) -> dict[str, str]:
    with _open_text(path) as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"service_id", "traffic_node"}.issubset(rows[0]):
        raise RoadGraphAuthorityError("service-node authority has an invalid schema")
    mapping = {
        str(row["service_id"]).strip(): _traffic_node(row["traffic_node"])
        for row in rows
    }
    if len(mapping) != len(rows):
        raise RoadGraphAuthorityError("service-node authority contains duplicate IDs")
    return mapping


def _read_physical_edge_sequences(path: Path) -> dict[str, tuple[tuple[int, str, float], ...]]:
    grouped: dict[str, list[tuple[int, str, float]]] = {}
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        required = {"reduced_link_id", "source_position", "edge_id", "length_m"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RoadGraphAuthorityError("physical-edge catalog has an invalid schema")
        for row in reader:
            grouped.setdefault(row["reduced_link_id"], []).append(
                (int(row["source_position"]), row["edge_id"], float(row["length_m"]))
            )
    result: dict[str, tuple[tuple[int, str, float], ...]] = {}
    for link_id, entries in grouped.items():
        ordered = tuple(sorted(entries))
        if [item[0] for item in ordered] != list(range(len(ordered))):
            raise RoadGraphAuthorityError(
                f"physical-edge positions are not contiguous for {link_id}"
            )
        if any(not math.isfinite(item[2]) or item[2] <= 0.0 for item in ordered):
            raise RoadGraphAuthorityError(f"invalid physical-edge length for {link_id}")
        result[link_id] = ordered
    return result


def _shape_xyz(shape: str) -> tuple[tuple[float, float, float], ...]:
    points = []
    for token in shape.split():
        parts = token.split(",")
        if len(parts) < 3:
            continue
        point = tuple(float(value) for value in parts[:3])
        if all(math.isfinite(value) for value in point):
            points.append(point)
    return tuple(points)


def _read_elevated_edge_shapes(
    network_path: Path, required_edge_ids: set[str]
) -> dict[str, tuple[tuple[float, float, float], ...]]:
    shapes: dict[str, tuple[tuple[float, float, float], ...]] = {}
    with _open_text(network_path) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "edge":
                edge_id = element.attrib.get("id", "")
                if edge_id in required_edge_ids:
                    lanes = [
                        child
                        for child in element
                        if child.tag.rsplit("}", 1)[-1] == "lane"
                    ]
                    lanes.sort(key=lambda lane: lane.attrib.get("id", ""))
                    shape = _shape_xyz(lanes[0].attrib.get("shape", "")) if lanes else ()
                    if len(shape) < 2:
                        raise RoadGraphAuthorityError(
                            f"elevated lane shape is unavailable for physical edge {edge_id}"
                        )
                    shapes[edge_id] = shape
                element.clear()
            elif tag != "lane":
                element.clear()
    missing = sorted(required_edge_ids - set(shapes))
    if missing:
        raise RoadGraphAuthorityError(
            f"elevated network lacks required physical edges: {missing[:5]}"
        )
    return shapes


def _ascent_descent(
    edge_sequence: tuple[tuple[int, str, float], ...],
    shapes: dict[str, tuple[tuple[float, float, float], ...]],
) -> tuple[float, float]:
    profile: list[float] = []
    for _, edge_id, _ in edge_sequence:
        elevations = [point[2] for point in shapes[edge_id]]
        if profile and math.isclose(profile[-1], elevations[0], abs_tol=1e-9):
            profile.extend(elevations[1:])
        else:
            profile.extend(elevations)
    ascent = 0.0
    descent = 0.0
    for first, second in zip(profile, profile[1:]):
        delta = second - first
        ascent += max(delta, 0.0)
        descent += max(-delta, 0.0)
    return ascent, descent


def load_road_graph_authority(
    link_order_path: Path,
    service_nodes_path: Path,
    reduced_link_physical_edge_catalog_path: Path,
    elevated_network_path: Path,
    *,
    expected_link_count: int | None = 509,
    expected_service_count: int | None = 24,
) -> RoadGraphAuthority:
    """Bind traffic adjacency to physical distance and elevation without K3 routes."""
    paths = tuple(
        Path(path)
        for path in (
            link_order_path,
            service_nodes_path,
            reduced_link_physical_edge_catalog_path,
            elevated_network_path,
        )
    )
    missing_files = [str(path) for path in paths if not path.is_file()]
    if missing_files:
        raise RoadGraphAuthorityError(f"road graph authority files are missing: {missing_files}")
    link_rows = _read_link_order(paths[0])
    services = _read_service_mapping(paths[1])
    physical = _read_physical_edge_sequences(paths[2])
    if expected_link_count is not None and len(link_rows) != expected_link_count:
        raise RoadGraphAuthorityError(
            f"expected {expected_link_count} links, found {len(link_rows)}"
        )
    if expected_service_count is not None and len(services) != expected_service_count:
        raise RoadGraphAuthorityError(
            f"expected {expected_service_count} services, found {len(services)}"
        )
    graph_link_ids = {row["reduced_link_id"] for row in link_rows}
    if set(physical) != graph_link_ids:
        raise RoadGraphAuthorityError("physical-edge catalog axis does not match link order")
    required_edges = {
        edge_id for sequence in physical.values() for _, edge_id, _ in sequence
    }
    shapes = _read_elevated_edge_shapes(paths[3], required_edges)
    links = []
    for row in link_rows:
        link_id = row["reduced_link_id"]
        sequence = physical[link_id]
        ascent, descent = _ascent_descent(sequence, shapes)
        links.append(
            RoadLink(
                link_id=link_id,
                from_node=_traffic_node(row["from_node"]),
                to_node=_traffic_node(row["to_node"]),
                distance_km=sum(item[2] for item in sequence) / 1000.0,
                cumulative_ascent_m=ascent,
                cumulative_descent_m=descent,
            )
        )
    route_graph_sha = _file_manifest_sha(
        zip(
            ("link_order", "service_nodes", "physical_edge_catalog", "elevated_network"),
            paths,
        )
    )
    return RoadGraphAuthority(tuple(links), services, route_graph_sha)
