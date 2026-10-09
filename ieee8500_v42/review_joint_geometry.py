"""Independent direct-source review of the saved joint 135 degree witness.

No geometry/search producer is imported or executed. Exact rational axis signs
are verified both for stored matrix literals and the ideal 135-degree rotation.
"""
import csv
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path

import numpy as np

from .integration import file_sha
from .mv_candidates import build_candidates


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(ok, message):
    if not ok:
        raise ValueError("JOINT_GEOMETRY_REVIEW_" + message)


def frac(value):
    return Fraction(str(value))


def sign(value):
    return 1 if value > 0 else -1 if value < 0 else 0


def audit(root=None):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    original = root.parent / "IEEE8500_scalability_20260910"
    docs = root / "docs/ieee8500_v42_single_case"
    output = docs / "joint_selection_v2/expanded_orientation_v1"
    mapping = rows(output / "JOINT_SERVICE_MAPPING.csv")
    pair_rows = rows(output / "RELATIVE_POSITION_AUDIT.csv")
    result = read_json(output / "GEOMETRY_RESULT.json")
    policy = read_json(output / "PREREGISTRATION.json")
    fit = result["proper_common_transform"]
    require(result["preregistration_sha256"] == file_sha(output / "PREREGISTRATION.json"), "PREREGISTRATION_SHA")
    require(policy["candidate_source_sha256"] == file_sha(docs / "MV_AIDC_CANDIDATES.csv"), "CANDIDATE_SHA")
    require(policy["required_pairs"] == 276 and policy["required_axis_signs"] == 552
            and policy["near_axis_and_pair_tolerances_km"] == .001, "ORIGINAL_TOLERANCES")
    require(result["geometric_feasibility"] is True and result["is_final_selection"] is False
            and result["physical_ports_qualified"] is False and result["production_configuration_frozen"] is False,
            "NO_FALSE_PHYSICAL_OR_FINAL_CLAIM")

    nodes = {r["transport_node_id"]: r for r in rows(original / "static_reference/v01_reduced48_nodes_v2.csv")}
    services = rows(original / "static_reference/final_service_nodes_24.csv")
    source_receipts = read_json(original / "audit/melbourne_static_sources.json")
    require(all(file_sha(original / "static_reference" / r["local_copy"]) == r["sha256"] for r in source_receipts), "RAW_TRAFFIC_SHA")
    identity = {}
    longitude, latitude = [], []
    for service in services:
        node = nodes[service["traffic_node"]]
        location_id = "A" + service["service_id"] if service["service_type"] == "IDC" else service["service_id"]
        role = "AIDC" if service["service_type"] == "IDC" else "STA"
        identity[location_id] = {"traffic_node": service["traffic_node"], "role": role,
                                "longitude": float(node["longitude"]), "latitude": float(node["latitude"])}
        longitude.append(float(node["longitude"]))
        latitude.append(float(node["latitude"]))
    # Direct original algebra, independent of cached projection/producer.
    lon, lat = np.radians(longitude), np.radians(latitude)
    tx = (lon - lon.mean()) * math.cos(lat.mean()) * 6371.0088
    ty = (lat - lat.mean()) * 6371.0088
    target = {location_id: (float(x), float(y)) for location_id, x, y in zip(identity, tx, ty)}
    original_coords = {}
    for line in (original / "source/Buscoords.dss").read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith(("//", "!")):
            continue
        fields = [v.strip() for v in line.split(",")]
        if len(fields) == 3:
            original_coords[fields[0].lower()] = (frac(fields[1]), frac(fields[2]))
    require(file_sha(original / "source/Buscoords.dss") == file_sha(root / "ieee8500_v42/data/feeder/Buscoords.dss"), "RAW_DSS_COORDINATE_SHA")
    mv = build_candidates(root)
    eligible = {r["dss_bus"]: r for r in mv.candidates}
    require(len(mapping) == len({r["location_id"] for r in mapping}) == 24
            and {r["location_id"] for r in mapping} == set(identity)
            and len({r["candidate_bus"] for r in mapping}) == 24, "24_DISTINCT_SERVICE_AND_BUS_IDENTITIES")
    require(len({r["traffic_node_id"] for r in mapping}) == 24, "24_DISTINCT_TRAFFIC_NODES")
    u, v, scale = fit["u"], fit["v"], fit["uniform_scale"]
    det = u * u + v * v
    require(scale > 0 and det > 0 and math.isclose(det, scale * scale, rel_tol=1e-15)
            and math.isclose(det, fit["determinant"], rel_tol=1e-15), "POSITIVE_UNIFORM_PROPER_MATRIX")
    require(abs(math.degrees(math.atan2(v, u)) - 135.) <= 1e-12 and fit["rotation_degrees"] == 135., "135_DEGREE_ROTATION")
    require(scale == policy["uniform_scale"] and 135. in policy["common_orientation_schedule_degrees"], "FROZEN_SCALE_AND_ORIENTATION_SCHEDULE")
    center, target_center = policy["common_source_center"], policy["common_target_center"]
    require(fit["translation_x"] == target_center[0] - u * center[0] + v * center[1]
            and fit["translation_y"] == target_center[1] - v * center[0] - u * center[1], "COMMON_TRANSLATION")
    mapped, source_points, error_km = {}, {}, []
    projection_error, transform_error, root_error = 0., 0., 0.
    reviewed_locations = []
    for row in mapping:
        location_id, bus = row["location_id"], row["candidate_bus"].lower()
        require(row["traffic_node_id"] == identity[location_id]["traffic_node"] and row["role"] == identity[location_id]["role"], "SOURCE_TRAFFIC_LABELS")
        require(bus in eligible and eligible[bus]["source_proximity_guard_pass"]
                and eligible[bus]["continuous_abc_from_feeder_head"] and eligible[bus]["original_source_connected"], "MV_606_ABC_ROOT_GUARD")
        require((frac(row["source_x"]), frac(row["source_y"])) == original_coords[bus], "EXACT_ORIGINAL_XY")
        require(frac(row["source_x"]) == frac(eligible[bus]["x"]) and frac(row["source_y"]) == frac(eligible[bus]["y"]), "MV_AND_ORIGINAL_COORDINATES")
        source_points[location_id] = original_coords[bus]
        x, y = map(float, original_coords[bus])
        point = (u * x - v * y + fit["translation_x"], v * x + u * y + fit["translation_y"])
        mapped[location_id] = point
        transform_error = max(transform_error, abs(point[0] - float(row["common_frame_x_km"])), abs(point[1] - float(row["common_frame_y_km"])))
        projection_error = max(projection_error, abs(target[location_id][0] - float(row["traffic_x_km"])), abs(target[location_id][1] - float(row["traffic_y_km"])))
        root_error = max(root_error, abs(float(row["root_distance_ohm"]) - mv.depth[bus]))
        error = math.dist(point, target[location_id])
        require(abs(error - float(row["geometry_error_km"])) <= 1e-12, "REPORTED_LAYOUT_ERROR")
        error_km.append(error)
        require(row["source_electrical_host_eligible"] == "True" and row["physical_port_protection_access_gate"] == "UNRESOLVED"
                and row["is_final_selection"] == "False", "PER_SITE_NO_FALSE_QUALIFICATION")
        require(row["mode"] == ("MV_3PH_AIDC" if row["role"] == "AIDC" else "MV_FALLBACK_STA"), "ALL_MV_FALLBACK_LABELS")
        reviewed_locations.append({"location_id": location_id, "traffic_node": row["traffic_node_id"], "bus": bus,
                                  "source_raw_and_guard_match": True, "physical_port_qualified": False})
    require(max(projection_error, transform_error, root_error) <= 1e-12, "NUMERIC_RECONSTRUCTION_1E_MINUS12")

    pair_by_id = {(r["location_a"], r["location_b"]): r for r in pair_rows}
    canonical_pairs = list(itertools.combinations(sorted(identity), 2))
    require(len(pair_rows) == 276 and set(pair_by_id) == set(canonical_pairs), "ALL276_PAIR_ROSTER")
    review_pairs, role_counts = [], {"AIDC-AIDC": 0, "STA-STA": 0, "AIDC-STA": 0}
    traffic_axis_min, fitted_margin_min, pair_number_error = math.inf, math.inf, 0.
    axis_count = 0
    stored_u, stored_v = frac(u), frac(v)
    for a, b in canonical_pairs:
        row = pair_by_id[(a, b)]
        expected_role = identity[a]["role"] + "-" + identity[b]["role"]
        require(row["role_pair"] == expected_role, "PAIR_ROLE")
        role_counts[expected_role] += 1
        for side, location in (("a", a), ("b", b)):
            require(row["traffic_node_" + side] == identity[location]["traffic_node"], "PAIR_TRAFFIC_LABEL")
            require(row["candidate_bus_" + side] == next(r["candidate_bus"] for r in mapping if r["location_id"] == location), "PAIR_BUS_LABEL")
        td = [target[b][k] - target[a][k] for k in (0, 1)]
        md = [mapped[b][k] - mapped[a][k] for k in (0, 1)]
        delta = [source_points[b][k] - source_points[a][k] for k in (0, 1)]
        exact_stored = [stored_u * delta[0] - stored_v * delta[1], stored_v * delta[0] + stored_u * delta[1]]
        # Exact ideal135° signs: positive scale/sqrt(2) multiplies these.
        exact_135 = [-(delta[0] + delta[1]), delta[0] - delta[1]]
        near = math.dist(target[a], target[b]) <= .001
        pair_signs = []
        for k, axis in enumerate(("x", "y")):
            expected = 0 if near or abs(td[k]) <= .001 else sign(td[k])
            actual = sign(md[k])
            require(expected != 0 and expected == actual == sign(exact_stored[k]) == sign(exact_135[k]), "EXACT_RATIONAL_DIRECTION")
            require(int(row["expected_" + axis + "_sign"]) == expected and int(row["actual_" + axis + "_sign"]) == actual
                    and row[axis + "_pass"] == "True", "SAVED_PAIR_AXIS_RESULT")
            error = max(abs(float(row["traffic_d" + axis + "_km"]) - td[k]), abs(float(row["common_frame_d" + axis + "_km"]) - md[k]))
            pair_number_error = max(pair_number_error, error)
            traffic_axis_min = min(traffic_axis_min, abs(td[k]))
            fitted_margin_min = min(fitted_margin_min, expected * md[k])
            axis_count += 1
            pair_signs.append({"axis": axis, "traffic_sign": expected, "mapped_sign": actual,
                               "stored_matrix_exact_rational_sign": sign(exact_stored[k]),
                               "ideal135_exact_rational_sign": sign(exact_135[k])})
        require(row["pair_pass"] == "True" and row["mapping_status"] == result["status"], "SAVED_PAIR_PASS")
        for key, value in (("source_xy_distance_unknown_units", math.dist(source_points[a], source_points[b])),
                           ("traffic_distance_km", math.dist(target[a], target[b])),
                           ("common_frame_distance_km", math.dist(mapped[a], mapped[b]))):
            pair_number_error = max(pair_number_error, abs(float(row[key]) - value))
        review_pairs.append({"a": a, "b": b, "axes": pair_signs, "PASS": True})
    require(axis_count == 552 and pair_number_error <= 1e-12, "ALL552_AXES_AND_PAIR_NUMBERS")

    # Historical normalized shape metrics remain audits, not current hard gates.
    aids = sorted(location for location in identity if identity[location]["role"] == "AIDC")
    t = np.asarray([target[a] for a in aids]); g = np.asarray([[float(v) for v in source_points[a]] for a in aids])
    t -= t.mean(axis=0); g -= g.mean(axis=0)
    tn = t / np.sqrt(np.mean(np.sum(t * t, axis=1))); gn = g / np.sqrt(np.mean(np.sum(g * g, axis=1)))
    h = tn.T @ gn
    e_coord = math.sqrt(max(0., 2 - 2 * math.hypot(h[0, 0] + h[1, 1], h[0, 1] - h[1, 0]) / 12))
    ii, jj = np.triu_indices(12, 1)
    td = np.linalg.norm(t[ii] - t[jj], axis=1); gd = np.linalg.norm(g[ii] - g[jj], axis=1)
    e_pair = float(np.sqrt(np.mean((td / np.sqrt(np.mean(td * td)) - gd / np.sqrt(np.mean(gd * gd))) ** 2)))
    historical_pairs = [mv.pair_metrics(next(r["candidate_bus"] for r in mapping if r["location_id"] == a),
                                       next(r["candidate_bus"] for r in mapping if r["location_id"] == b))
                        for a, b in itertools.combinations(aids, 2)]
    source_paths = [output / name for name in ("PREREGISTRATION.json", "GEOMETRY_RESULT.json", "JOINT_SERVICE_MAPPING.csv", "RELATIVE_POSITION_AUDIT.csv")]
    source_paths += [original / "static_reference/v01_reduced48_nodes_v2.csv", original / "static_reference/final_service_nodes_24.csv",
        original / "audit/melbourne_static_sources.json", original / "source/Buscoords.dss", root / "ieee8500_v42/data/feeder/Buscoords.dss",
        docs / "MV_AIDC_CANDIDATES.csv", docs / "MV_AIDC_CANDIDATE_AUDIT.json", root / "ieee8500_v42/joint_geometry.py", root / "ieee8500_v42/mv_candidates.py"]
    return {"schema": "JOINT_GEOMETRY_INDEPENDENT_RAW_SOURCE_RATIONAL_REVIEW_V1", "PASS": True,
        "scope": "SAVED_135_DEGREE_DIRECTION_WITNESS_ONLY_NOT_FINAL_PHYSICAL_CONFIGURATION",
        "locations": reviewed_locations, "all_24_bus_and_service_identities_distinct": True,
        "original_service_traffic_ids_preserved": True, "MV606_guarded_membership_count": 24,
        "independent_MV_root_distance_reconstruction_error_ohm": mv.audit["root_distance_reconstruction_error_max_ohm"],
        "all_276_pair_count": len(review_pairs), "role_pair_counts": role_counts,
        "all_552_nonexempt_axis_relations_PASS": True,
        "exact_sign_methods": ["Fraction original DSS decimal coordinates and stored u,v literals", "ideal135: x sign(-(dx+dy)), y sign(dx-dy)"],
        "pairs": review_pairs, "common_proper_transform": fit,
        "projection_from_raw_longitude_latitude_max_error_km": projection_error,
        "common_transform_point_reconstruction_max_error_km": transform_error,
        "all_pair_saved_number_reconstruction_max_error": pair_number_error,
        "all_numeric_reconstruction_errors_le_1e_minus_12": True,
        "minimum_abs_traffic_axis_delta_km": traffic_axis_min, "minimum_positive_common_frame_axis_margin_km": fitted_margin_min,
        "absolute_layout_error_km": {"RMS": math.sqrt(sum(e * e for e in error_km) / 24), "mean": sum(error_km) / 24, "max": max(error_km)},
        "historical_AIDC_shape_audit": {"E_coord": e_coord, "E_pair": e_pair, "threshold_each": .20,
            "E_coord_historical_gate_pass": e_coord <= .20, "E_pair_historical_gate_pass": e_pair <= .20,
            "role": "historical criteria separate from latest hard directions; do not claim distance or shape faithful"},
        "historical_AIDC_dispersion_audit": {"electrical_min_ohm": min(p["electrical_tree_distance_ohm"] for p in historical_pairs),
            "source_xy_min_unknown_units": min(p["source_xy_distance_unknown_units"] for p in historical_pairs),
            "electrical_gate_failing_pairs": sum(not p["original_electrical_dispersion_gate_pass"] for p in historical_pairs),
            "xy_gate_failing_pairs": sum(not p["original_xy_dispersion_gate_pass"] for p in historical_pairs)},
        "LV_STA_selected_count": 0, "MV_STA_fallback_count": 12, "physical_ports_qualified": 0,
        "final_selection": False, "Native_calls": 0, "OpenDSS_calls": 0, "selection_search_calls": 0,
        "search_producer_imports": 0, "original_source_writes_attempted": False,
        "source_records": [{"path": str(p), "sha256": file_sha(p)} for p in source_paths],
        "reviewer_module_sha256": file_sha(Path(__file__))}


def main():
    root = Path(__file__).resolve().parents[1]
    result = audit(root)
    path = root / "docs/ieee8500_v42_single_case/joint_selection_v2/expanded_orientation_v1/JOINT_GEOMETRY_INDEPENDENT_REVIEW.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("PASS", "all_276_pair_count", "all_552_nonexempt_axis_relations_PASS",
        "projection_from_raw_longitude_latitude_max_error_km", "common_transform_point_reconstruction_max_error_km",
        "all_pair_saved_number_reconstruction_max_error", "absolute_layout_error_km", "historical_AIDC_shape_audit",
        "Native_calls", "OpenDSS_calls", "selection_search_calls")}))


if __name__ == "__main__":
    main()
