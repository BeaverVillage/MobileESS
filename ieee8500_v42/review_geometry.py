"""Independent read-only review of saved geometry inputs and certificates.

No geometry producer, historical selector, Native model, or OpenDSS code is
imported. The original decimal coordinates are evaluated with exact rational
arithmetic for the positive-combination impossibility certificates.
"""
import csv
from decimal import Decimal
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path

from .integration import file_sha


FIXED = dict(zip((f"AIDC{i:02d}" for i in range(1, 13)),
    ("l3234149", "e182733", "m1027055", "m1069411", "l2688693", "m1142814",
     "m1026690", "l3123452", "l2728247", "l2973833", "m1047763", "e192258")))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_float=Decimal)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def rational(value):
    return Fraction(str(value))


def rational_coordinates(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith(("//", "!")):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            result[parts[0].lower()] = (rational(parts[1]), rational(parts[2]))
    return result


def sign(value, tolerance=Fraction(1, 1000)):
    return 0 if abs(value) <= tolerance else (1 if value > 0 else -1)


def exact_fraction(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def review(root, original_root):
    root, original = Path(root).resolve(), Path(original_root).resolve()
    data = root / "ieee8500_v42/data"
    docs = root / "docs/ieee8500_v42_single_case"
    geometry_data = data / "geometry"
    original_geometry = original / "station_selection_v1"
    original_v3 = original / "selection_v3_source_proximity"
    historical_pairs = docs / "historical_fixed_v3_outputs/RELATIVE_POSITION_AUDIT.csv"
    pair_path = historical_pairs if historical_pairs.exists() else docs / "RELATIVE_POSITION_AUDIT.csv"
    pairs = read_csv(pair_path)
    full_pairs = read_csv(docs / "AIDC_66_DIRECTION_AUDIT.csv")
    aidcs = read_csv(geometry_data / "AIDC_V3_MAPPING.csv")
    registry = read_csv(geometry_data / "ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
    anchors = read_json(geometry_data / "STATIC_24_TRAFFIC_ANCHORS.json")
    status = read_json(docs / "GEOMETRY_STATUS.json")
    coords = rational_coordinates(data / "feeder/Buscoords.dss")
    original_coords = rational_coordinates(original / "source/Buscoords.dss")
    policy = read_json(docs / "GEOMETRY_POLICY.json")
    assert policy["traffic_axis_zero_tolerance_km"] == Decimal("0.001")
    assert policy["traffic_pair_distance_tolerance_km"] == Decimal("0.001")
    assert policy["direction_relaxation_allowed"] is False

    copied_paths = {
        "AIDC_V3_MAPPING.csv": original_v3 / "AIDC01_AIDC12_IEEE8500_MAPPING.csv",
        "ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv": original_geometry / "FINAL_24_LOCATION_ELECTRICAL_MAPPING.csv",
        "STATIC_24_TRAFFIC_ANCHORS.json": original_geometry / "STATIC_24_TRAFFIC_ANCHORS.json",
    }
    input_manifest = read_json(docs / "GEOMETRY_INPUT_SHA256.json")
    byte_checks = {}
    for name, source in copied_paths.items():
        byte_checks[name] = file_sha(geometry_data / name) == file_sha(source) == input_manifest[name]
    assert all(byte_checks.values()), "Original copied geometry byte identity failed"
    assert file_sha(data / "feeder/Buscoords.dss") == file_sha(original / "source/Buscoords.dss")
    aidc_by_id = {r["aidc_id"]: r for r in aidcs}
    registry_by_id = {r["location_id"]: r for r in registry}
    traffic = {r["location_id"]: r for r in anchors}
    old_anchors = {r["aidc_id"]: r for r in read_json(original / "audit/melbourne_12_anchors.json")}
    nodes = {r["transport_node_id"]: r for r in read_csv(original / "static_reference/v01_reduced48_nodes_v2.csv")}
    services = {("A" + r["service_id"] if r["service_type"] == "IDC" else r["service_id"]): r
                for r in read_csv(original / "static_reference/final_service_nodes_24.csv")}
    traffic_source_receipts = read_json(original / "audit/melbourne_static_sources.json")
    assert all(file_sha(original / "static_reference" / row["local_copy"]) == row["sha256"]
               for row in traffic_source_receipts)
    assert len(traffic) == len(anchors) == len(registry_by_id) == 24
    assert set(aidc_by_id) == set(FIXED)
    identity_rows = []
    grid = {}
    for aid, expected_bus in FIXED.items():
        copied, full, a, old = aidc_by_id[aid], registry_by_id[aid], traffic[aid], old_anchors[aid]
        expected_node = "TN_" + aid[-2:]
        node = nodes[expected_node]
        assert copied["ieee8500_bus"].lower() == full["ieee8500_bus"].lower() == expected_bus
        assert a["role"] == "AIDC" and a["traffic_node"] == full["traffic_anchor"] == old["traffic_node"] == expected_node
        assert services[aid]["traffic_node"] == expected_node
        assert old["service_id"] == "IDC" + aid[-2:]
        assert node["model_idc_id"] == "IDC_" + aid[-2:]
        for axis, key in enumerate(("x", "y")):
            assert rational(copied[key]) == rational(full["bus_" + key]) == coords[expected_bus][axis] == original_coords[expected_bus][axis]
        for key in ("longitude", "latitude"):
            assert rational(a[key]) == rational(old[key]) == rational(node[key])
        grid[aid] = coords[expected_bus]
        identity_rows.append({"aidc_id": aid, "source_bus": expected_bus, "traffic_node": expected_node,
                              "coordinate_and_label_match": True})

    # Recalculate the 24-anchor east/north projection from source lon/lat.
    lon = [math.radians(float(a["longitude"])) for a in anchors]
    lat = [math.radians(float(a["latitude"])) for a in anchors]
    mean_lon, mean_lat = sum(lon) / 24, sum(lat) / 24
    projection_error = max(max(abs((x - mean_lon) * math.cos(mean_lat) * 6371.0088 - float(a["x_east_km"])),
                               abs((y - mean_lat) * 6371.0088 - float(a["y_north_km"])))
                           for a, x, y in zip(anchors, lon, lat))
    assert projection_error < 1e-8

    certificates = {}
    fit = {key: float(value) for key, value in status["common_similarity"].items()
           if isinstance(value, (Decimal, int, float))}
    assert fit["determinant"] > 0
    assert math.isclose(fit["determinant"], fit["u"] ** 2 + fit["v"] ** 2, rel_tol=1e-13)
    aidc_pairs = [r for r in pairs if r["role_pair"] == "AIDC-AIDC"]
    expected_pairs = set(itertools.combinations(sorted(FIXED), 2))
    assert len(aidc_pairs) == 66 and {(r["location_a"], r["location_b"]) for r in aidc_pairs} == expected_pairs
    full_pair_by_ids = {(r["aidc_a"], r["aidc_b"]): r for r in full_pairs}
    assert len(full_pairs) == 66 and set(full_pair_by_ids) == expected_pairs
    assert len(pairs) == 276
    reviewed_pairs = []
    violations = {"raw_x": 0, "raw_y": 0, "fit_x": 0, "fit_y": 0, "fit_pairs": 0}
    old_projection_sign_matches = 0
    for row in aidc_pairs:
        a, b = row["location_a"], row["location_b"]
        full_row = full_pair_by_ids[(a, b)]
        assert row["traffic_node_a"] == traffic[a]["traffic_node"]
        assert row["traffic_node_b"] == traffic[b]["traffic_node"]
        for side, aid in (("a", a), ("b", b)):
            assert full_row["traffic_node_" + side] == traffic[aid]["traffic_node"]
            assert full_row["dss_bus_" + side].lower() == FIXED[aid]
            point = grid[aid]
            fitted = [fit["u"] * float(point[0]) - fit["v"] * float(point[1]) + fit["translation_x"],
                      fit["v"] * float(point[0]) + fit["u"] * float(point[1]) + fit["translation_y"]]
            for k, axis in enumerate(("x", "y")):
                traffic_key = ("x_east_km", "y_north_km")[k]
                assert abs(float(full_row["traffic_" + side + "_" + axis]) - float(traffic[aid][traffic_key])) < 1e-10
                assert rational(full_row["source_dss_" + side + "_" + axis]) == point[k]
                assert abs(float(full_row["common_fit_" + side + "_" + axis]) - fitted[k]) < 1e-8
        tdelta = [rational(traffic[b][key]) - rational(traffic[a][key]) for key in ("x_east_km", "y_north_km")]
        expected = [sign(x) for x in tdelta]
        old_sign = [sign(rational(old_anchors[b][key]) - rational(old_anchors[a][key])) for key in ("x_east_km", "y_north_km")]
        assert expected == old_sign
        old_projection_sign_matches += 1
        delta = [grid[b][k] - grid[a][k] for k in (0, 1)]
        raw_sign = [sign(x, Fraction(0)) for x in delta]
        mapped = [fit["u"] * float(delta[0]) - fit["v"] * float(delta[1]),
                  fit["v"] * float(delta[0]) + fit["u"] * float(delta[1])]
        actual = [sign(rational(str(x)), Fraction(1, 10 ** 12)) for x in mapped]
        for k, axis in enumerate(("x", "y")):
            assert int(row["expected_" + axis + "_sign"]) == expected[k]
            assert int(row["actual_" + axis + "_sign"]) == actual[k]
            assert int(row["source_no_transform_" + axis + "_sign"]) == raw_sign[k]
            assert abs(float(row["traffic_d" + axis + "_km"]) - float(tdelta[k])) < 1e-10
            assert abs(float(row["source_no_transform_d" + axis + "_unknown_units"]) - float(delta[k])) < 2e-9
            assert abs(float(row["transformed_grid_d" + axis + "_km"]) - mapped[k]) < 1e-8
            raw_pass = not expected[k] or expected[k] == raw_sign[k]
            fit_pass = not expected[k] or expected[k] == actual[k]
            assert (row["source_no_transform_" + axis + "_preserved"] == "True") == raw_pass
            assert (row[axis + "_preserved"] == "True") == fit_pass
            assert int(full_row["expected_" + axis + "_sign"]) == expected[k]
            assert int(full_row["raw_" + axis + "_sign"]) == raw_sign[k]
            assert int(full_row["fit_" + axis + "_sign"]) == actual[k]
            assert abs(float(full_row["traffic_delta_" + axis + "_km"]) - float(tdelta[k])) < 1e-10
            assert abs(float(full_row["source_dss_delta_" + axis + "_unknown_units"]) - float(delta[k])) < 2e-9
            assert abs(float(full_row["common_fit_delta_" + axis + "_km"]) - mapped[k]) < 1e-8
            assert (full_row["raw_" + axis + "_preserved"] == "True") == raw_pass
            assert (full_row["fit_" + axis + "_preserved"] == "True") == fit_pass
            violations["raw_" + axis] += not raw_pass
            violations["fit_" + axis] += not fit_pass
        pair_pass = all(not e or e == s for e, s in zip(expected, actual))
        assert (row["pair_pass"] == "True") == pair_pass
        assert row["near_pair_exempt"] == "False"
        assert full_row["near_pair_distance_exempt"] == "False"
        assert full_row["fitted_transform_accepted"] == "False"
        violations["fit_pairs"] += not pair_pass
        reviewed_pairs.append({"a": a, "b": b, "input_pair_identity": True,
                               "expected_x_sign": expected[0], "expected_y_sign": expected[1],
                               "raw_x_sign": raw_sign[0], "raw_y_sign": raw_sign[1],
                               "fitted_x_sign": actual[0], "fitted_y_sign": actual[1],
                               "csv_independently_verified": True,
                               "complete_original_and_fitted_point_coordinates_verified": True})

    for axis, label in enumerate(("east_west", "north_south")):
        entry = status["fixed_aidc_affine_certificate"][label]
        assert entry["constraint_count"] == 66 and entry["feasible"] is False
        assert entry["feasible_intervals_radians"] == []
        witness = entry["irreducible_witness"]
        assert len(witness) == 3
        vectors = []
        for row in witness:
            a, b = row["a"], row["b"]
            key = ("x_east_km", "y_north_km")[axis]
            td = rational(traffic[b][key]) - rational(traffic[a][key])
            s = sign(td)
            assert s != 0
            vector = tuple(s * (grid[b][k] - grid[a][k]) for k in (0, 1))
            assert abs(float(td) - float(row["traffic_delta_km"])) < 1e-10
            assert all(abs(float(x) - float(y)) < 2e-9 for x, y in zip(vector, row["signed_grid_delta"]))
            vectors.append(vector)
        weights = [cross(vectors[1], vectors[2]), cross(vectors[2], vectors[0]), cross(vectors[0], vectors[1])]
        if all(w < 0 for w in weights):
            weights = [-w for w in weights]
        assert all(w > 0 for w in weights)
        norm = sum(weights)
        weights = [w / norm for w in weights]
        residual = [sum(w * v[k] for w, v in zip(weights, vectors)) for k in (0, 1)]
        assert residual == [Fraction(0), Fraction(0)]
        weight_serialization_difference = max(abs(float(w) - float(saved))
                                              for w, saved in zip(weights, entry["positive_convex_weights"]))
        assert weight_serialization_difference < 1e-12
        certificates[label] = {"PASS": True, "strict_positive_weights": True,
            "witness_pairs": [[r["a"], r["b"]] for r in witness],
            "signed_vectors_exact": [[exact_fraction(x) for x in v] for v in vectors],
            "weights_exact": [exact_fraction(w) for w in weights],
            "weights_float": [float(w) for w in weights],
            "source_decimal_vs_producer_binary64_weight_difference_max": weight_serialization_difference,
            "weighted_vector_sum_exact": ["0", "0"],
            "proof": "If all row dot v_i > 0, their strictly positive weighted sum is > 0, contradicting row dot 0 = 0"}

    source_paths = [geometry_data / name for name in copied_paths] + list(copied_paths.values()) + [
        data / "feeder/Buscoords.dss", original / "source/Buscoords.dss",
        data / "feeder/AddBusXY.py", original / "audit/melbourne_12_anchors.json",
        original / "audit/melbourne_static_sources.json", original / "static_reference/v01_reduced48_nodes_v2.csv",
        original / "static_reference/final_service_nodes_24.csv", original / "methodology_inputs.py",
        original_geometry / "prepare_sta.py", original_geometry / "SERVICE_REGISTRY_FREEZE_MANIFEST.json",
        original_v3 / "select_sites.py", original_v3 / "verify_guarded_selection.py",
        original_v3 / "SELECTION_VALIDATION.json", original_v3 / "GUARDED_SELECTION_FREEZE_MANIFEST.json",
        docs / "GEOMETRY_POLICY.json", docs / "GEOMETRY_STATUS.json", pair_path,
        docs / "AIDC_66_DIRECTION_AUDIT.csv", docs / "DIRECTION_ROOT_CAUSE_AUDIT.json",
        root / "ieee8500_v42/geometry.py", docs / "ORIGINAL_FEEDER_REGRESSION.json"]
    return {"PASS": True, "schema": "IEEE8500_GEOMETRY_INDEPENDENT_RATIONAL_REVIEW_V1",
        "scope": "READ_ONLY_GEOMETRY_AND_SAVED_ORIGINAL_AC_RESULTS_NO_NEW_SOLVES",
        "copied_original_input_byte_checks": byte_checks, "fixed_aidc_input_roster": identity_rows,
        "traffic_projection_error_km_max": projection_error,
        "original12_vs_station24_projection_pair_sign_matches": old_projection_sign_matches,
        "all_66_pair_review": reviewed_pairs, "pair_counts": {"total": 276, "fixed_aidc": 66},
        "fixed_pair_violation_counts": violations, "exact_impossibility_certificates": certificates,
        "permitted_similarity_class": "F(g)=s R(theta)g+t, s>0, det(R)=1; one common transform, no reflection",
        "affine_superset_proved_impossible": "F(g)=Ag+t for every constant 2x2 A; each required row needs r dot signed_delta>0",
        "nonlinear_warps_impossibility_claim": False,
        "physical_compass_or_CRS_certified": False,
        "original_static_source_regression_is_full_v42_B0": False,
        "original_files_write_attempted": False, "native_calls": 0, "OpenDSS_calls": 0,
        "source_records": [{"path": str(p), "sha256": file_sha(p)} for p in source_paths],
        "reviewer_source_sha256": file_sha(Path(__file__))}


def main():
    root = Path(__file__).resolve().parents[1]
    original = root.parent / "IEEE8500_scalability_20260910"
    result = review(root, original)
    destination = root / "docs/ieee8500_v42_single_case/GEOMETRY_INDEPENDENT_REVIEW.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"PASS": result["PASS"], "pair_counts": result["pair_counts"],
                      "violations": result["fixed_pair_violation_counts"],
                      "exact_certificates": {k: v["weighted_vector_sum_exact"] for k, v in
                          result["exact_impossibility_certificates"].items()},
                      "native_calls": 0, "OpenDSS_calls": 0}))


if __name__ == "__main__":
    main()
