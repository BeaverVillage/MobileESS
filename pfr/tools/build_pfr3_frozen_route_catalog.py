"""Build the 552-OD x frozen-K3 geometry catalog without energy ML."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


GEOMETRY_COLUMNS = [
    "physical_route_sha256",
    "source_service_id",
    "destination_service_id",
    "route_distance_km",
    "net_elevation_change_m",
    "cumulative_ascent_m",
    "cumulative_descent_m",
    "max_abs_segment_grade",
    "p95_abs_segment_grade_weighted",
    "frozen_final_operational_tt_sec",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _invariant_profile(route_sha: str, group: pd.DataFrame) -> dict[str, object]:
    invariant = [
        "route_distance_km",
        "net_elevation_change_m",
        "cumulative_ascent_m",
        "cumulative_descent_m",
        "max_abs_segment_grade",
        "p95_abs_segment_grade_weighted",
    ]
    for column in invariant:
        values = group[column].astype(float)
        tolerance = max(1e-9, abs(float(values.iloc[0])) * 1e-9)
        if float(values.max() - values.min()) > tolerance:
            raise RuntimeError(f"route geometry drift for {route_sha} column={column}")
    sources = set(group["source_service_id"].astype(str))
    destinations = set(group["destination_service_id"].astype(str))
    if len(sources) != 1 or len(destinations) != 1:
        raise RuntimeError(f"route endpoint drift for {route_sha}")
    row = group.iloc[0]
    return {
        "physical_route_sha256": route_sha,
        "source_service_id": next(iter(sources)),
        "destination_service_id": next(iter(destinations)),
        "route_distance_km": float(row["route_distance_km"]),
        "net_elevation_change_m": float(row["net_elevation_change_m"]),
        "cumulative_ascent_m": float(row["cumulative_ascent_m"]),
        "cumulative_descent_m": float(row["cumulative_descent_m"]),
        "max_abs_segment_grade": float(row["max_abs_segment_grade"]),
        "p95_abs_segment_grade_weighted": float(row["p95_abs_segment_grade_weighted"]),
        "free_flow_reference_seconds": float(group["frozen_final_operational_tt_sec"].astype(float).min()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-static", required=True, type=Path)
    parser.add_argument("--physics-geometry-dataset", required=True, type=Path)
    parser.add_argument("--service-axis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    static = pd.read_parquet(
        args.route_static,
        columns=["slot", "od_index", "rank", "physical_route_sha256"],
    ).sort_values("slot", kind="mergesort")
    if len(static) != 1656 or static["slot"].nunique() != 1656 or static["od_index"].nunique() != 552:
        raise RuntimeError("frozen route static must contain exactly 552 OD and 1656 slots")
    expected_slot = static["od_index"].astype(int) * 3 + static["rank"].astype(int) - 1
    if not (expected_slot.to_numpy() == static["slot"].astype(int).to_numpy()).all():
        raise RuntimeError("slot = od_index*3 + rank-1 contract drift")
    if set(static["rank"].astype(int)) != {1, 2, 3}:
        raise RuntimeError("production route ranks must be exactly 1, 2, and 3")

    service = pd.read_csv(args.service_axis).sort_values("service_order", kind="mergesort")
    services = service["service_id"].astype(str).tolist()
    if len(services) != 24 or len(set(services)) != 24:
        raise RuntimeError("service axis must contain 24 unique nodes")

    geometry_rows = pd.read_parquet(args.physics_geometry_dataset, columns=GEOMETRY_COLUMNS)
    profiles = {
        str(route_sha): _invariant_profile(str(route_sha), group)
        for route_sha, group in geometry_rows.groupby("physical_route_sha256", sort=True)
    }

    routes = []
    for row in static.itertuples(index=False):
        source_index = int(row.od_index) // 23
        destination_index = int(row.od_index) % 23
        if destination_index >= source_index:
            destination_index += 1
        source = services[source_index]
        destination = services[destination_index]
        route_sha = str(row.physical_route_sha256)
        if route_sha not in profiles:
            raise RuntimeError(f"missing physics geometry for route {route_sha}")
        profile = profiles[route_sha]
        if profile["source_service_id"] != source or profile["destination_service_id"] != destination:
            raise RuntimeError(f"route endpoint mismatch slot={row.slot}")
        routes.append({
            "slot": int(row.slot),
            "od_index": int(row.od_index),
            "rank": int(row.rank),
            "geometry_authority": "INHERITED_K_SHORTEST_TOP3_ALGORITHM_UNVERIFIED",
            **profile,
        })

    result = {
        "schema_version": "mobileess.pfr3.frozen_k3_physics_geometry.v1",
        "status": "PASS",
        "od_count": 552,
        "route_slot_count": 1656,
        "route_count_per_od": 3,
        "ml_generates_geometry": False,
        "mobility_energy_ml_loaded": False,
        "runtime_energy_authority": "DETERMINISTIC_PHYSICS_E_RECOMPUTED_FROM_GEOMETRY_AND_CAUSAL_ETA",
        "route_static_sha256": _sha256(args.route_static),
        "physics_geometry_dataset_sha256": _sha256(args.physics_geometry_dataset),
        "service_axis_sha256": _sha256(args.service_axis),
        "routes": routes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
