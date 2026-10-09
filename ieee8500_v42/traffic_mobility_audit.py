"""Read-only independent traffic/mobility input audit; no model construction.

Reads route/forecast files in place. Does not import historical launchers,
Native, OpenDSS, forecast training, or Actual replay code. Actual SUMO numeric
values are not loaded; its source file is only located and SHA recorded.
"""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import re

import numpy as np

from .integration import file_sha


CURRENT_INPUT = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01")
LEGACY_CODE = Path("C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance")
ORIGINAL_TRAFFIC = Path("C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic/2025-05-01")
WSL = Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline")
FORECAST_KEYS = ("forecast_day", "issue_time", "max_input_timestamp", "target_timestamps", "link_ids",
                 "model_id", "model_sha", "data_sha", "graph_sha", "normalization_sha",
                 "causality_pass", "future_actual_read_count")
GRAPH_PATHS = {
    "link_order": WSL / "10_ml_stage1_multires_traffic_v1/graph/link_order_509.csv",
    "service_nodes": WSL / "21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1/freeze_assets/stage8/optimizer_interface/final_service_nodes_24.csv",
    "physical_edge_catalog": WSL / "24c_energy_stage_e1r_canonical_physical_route_library_v1_1_metric_repair/library/reduced_link_physical_edge_congestion_catalog.csv.gz",
    "elevated_network": WSL / "24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile/network/network_elevated_conditioned.net.xml",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(ok, label):
    if not ok:
        raise ValueError("TRAFFIC_MOBILITY_AUDIT_" + label)


def source_record(path):
    path = Path(path)
    return {"path": str(path), "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": file_sha(path) if path.is_file() else None}


def decoded_record(path, encoding="byte_identical"):
    path = Path(path)
    if encoding == "byte_identical":
        return source_record(path)
    require(encoding == "lossless_gzip", "UNKNOWN_PORTABLE_ENCODING")
    h, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block); size += len(block)
    return {"path": str(path), "exists": True, "bytes": size, "sha256": h.hexdigest(),
            "storage_encoding": encoding, "stored_bytes": path.stat().st_size, "stored_sha256": file_sha(path)}


def capture_portable_inputs(root):
    """Save frozen planning inputs and lossless static graph; never Actual data.

    Native/window JSON reuse the existing workload_flexibility copies. The
    elevated XML is losslessly gzip encoded; original decoded SHA is preserved.
    """
    root = Path(root).resolve()
    destination = root / "ieee8500_v42/data/traffic_audit"
    destination.mkdir(parents=True, exist_ok=True)
    proof = read_json(root / "docs/ieee8500_v42_single_case/TRAFFIC_MOBILITY_AUDIT.json")
    source_by_path = {r["path"]: r for r in proof["source_files"]}
    files = {}
    sources = {name: CURRENT_INPUT / name for name in ("ROUTE_TABLE.json.gz", "TRAFFIC_FORECAST.npz", "OPERATIONS.json")}
    sources.update({"LINK_ORDER.csv": GRAPH_PATHS["link_order"], "SERVICE_NODES.csv": GRAPH_PATHS["service_nodes"],
                    "PHYSICAL_EDGE_CATALOG.csv.gz": GRAPH_PATHS["physical_edge_catalog"],
                    "MOBILITY_PHYSICS.json": LEGACY_CODE / "pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json"})
    for name, source in sources.items():
        expected = source_by_path[str(source)]
        require(file_sha(source) == expected["sha256"], "PORTABLE_ORIGINAL_SOURCE_SHA")
        (destination / name).write_bytes(source.read_bytes())
        files[name] = {"relative_path": name, "original_readonly_path": str(source), "encoding": "byte_identical",
                       "sha256": expected["sha256"], "bytes": expected["bytes"],
                       "stored_sha256": file_sha(destination / name), "stored_bytes": (destination / name).stat().st_size}
    elevated = destination / "ELEVATED_NETWORK.xml.gz"
    expected = source_by_path[str(GRAPH_PATHS["elevated_network"])]
    if not elevated.is_file():
        with elevated.open("wb") as out, GRAPH_PATHS["elevated_network"].open("rb") as source:
            with gzip.GzipFile(filename="", mode="wb", fileobj=out, compresslevel=6, mtime=0) as encoded:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    encoded.write(block)
    decoded = decoded_record(elevated, "lossless_gzip")
    require(decoded["sha256"] == expected["sha256"] and decoded["bytes"] == expected["bytes"], "LOSSLESS_ORIGINAL_XML_SHA")
    files[elevated.name] = {"relative_path": elevated.name, "original_readonly_path": str(GRAPH_PATHS["elevated_network"]),
                           "encoding": "lossless_gzip", "sha256": expected["sha256"], "bytes": expected["bytes"],
                           "stored_sha256": decoded["stored_sha256"], "stored_bytes": decoded["stored_bytes"]}
    shared = root / "ieee8500_v42/data/workload_flexibility"
    shared_manifest = read_json(shared / "MANIFEST.json")
    for name in ("NATIVE_INPUT.json", "WINDOWS.json"):
        row = shared_manifest["files"][name]
        require(file_sha(shared / name) == row["sha256"] == source_by_path[str(CURRENT_INPUT / name)]["sha256"], "SHARED_WORKLOAD_COPY_SHA")
        files[name] = {"relative_path": "../workload_flexibility/" + name, "original_readonly_path": str(CURRENT_INPUT / name),
                       "encoding": "byte_identical", "sha256": row["sha256"], "bytes": row["bytes"],
                       "stored_sha256": row["sha256"], "stored_bytes": row["bytes"], "shared_existing_copy": True}
    total = sum(r["stored_bytes"] for r in files.values() if not r.get("shared_existing_copy"))
    require(total < 50 * 1024 * 1024 and all(r["stored_bytes"] < 50 * 1024 * 1024 for r in files.values()), "PORTABLE_BUNDLE_SIZE")
    source_proof = {"schema": "READ_ONLY_ARCHIVED_SOURCE_IDENTITY_PROOF_NOT_ACTUAL_DATA",
        "source_files": proof["source_files"], "same_original_route_and_forecast_container_bytes": True,
        "original_graph_manifest_sha256": proof["original_graph_manifest_sha256"],
        "actual_sumo_source_metadata_only": proof["actual_sumo_source"],
        "actual_sumo_values_loaded": False, "actual_sumo_data_copied": False,
        "original_service_csv_readonly_path": str(root.parent / "IEEE8500_scalability_20260910/static_reference/final_service_nodes_24.csv"),
        "safe_eta_calibration_json_in_legacy_code_exists": proof["safe_eta_calibration_json_in_legacy_code_exists"]}
    proof_path = destination / "ORIGINAL_SOURCE_SHA_PROOF.json"
    proof_path.write_text(json.dumps(source_proof, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": "IEEE8500_PORTABLE_PLANNING_TRAFFIC_AUDIT_INPUT_V1", "files": files,
        "original_source_proof_sha256": file_sha(proof_path), "new_bundle_storage_bytes": total,
        "original_elevated_xml_bytes": expected["bytes"], "XML_is_lossless_gzip": True,
        "size_scope": "new traffic copies <50MiB approved after rawXML134MB inspection; sharedNative/windows are not duplicated",
        "graph_roles": {"link_order": "LINK_ORDER.csv", "service_nodes": "SERVICE_NODES.csv",
                        "physical_edge_catalog": "PHYSICAL_EDGE_CATALOG.csv.gz", "elevated_network": "ELEVATED_NETWORK.xml.gz"},
        "Actual_numeric_inputs_or_outcomes_copied": False, "Native_calls": 0, "OpenDSS_calls": 0}
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def portable_configuration(root):
    data = Path(root) / "ieee8500_v42/data/traffic_audit"
    manifest = read_json(data / "SOURCE_MANIFEST.json")
    require(file_sha(data / "ORIGINAL_SOURCE_SHA_PROOF.json") == manifest["original_source_proof_sha256"], "PORTABLE_ORIGINAL_PROOF_SHA")
    proof = read_json(data / "ORIGINAL_SOURCE_SHA_PROOF.json")
    paths, records = {}, {}
    for name, row in manifest["files"].items():
        path = (data / row["relative_path"]).resolve()
        require(path.parent in (data.resolve(), (data.parent / "workload_flexibility").resolve()), "PORTABLE_PATH_SCOPE")
        require(file_sha(path) == row["stored_sha256"] and path.stat().st_size == row["stored_bytes"], "PORTABLE_CONTAINER_SHA_" + name)
        record = decoded_record(path, row["encoding"])
        require(record["sha256"] == row["sha256"] and record["bytes"] == row["bytes"], "PORTABLE_DECODED_ORIGINAL_SHA_" + name)
        records[name], paths[name] = record, path
    return {"manifest": manifest, "proof": proof, "paths": paths, "records": records,
            "graph_paths": {role: paths[name] for role, name in manifest["graph_roles"].items()},
            "graph_records": [records[name] | {"role": role} for role, name in manifest["graph_roles"].items()]}


def traffic_node(value):
    match = re.fullmatch(r"(?:TN_)?(\d+)", value.strip(), re.IGNORECASE)
    return f"TN_{int(match.group(1)):02d}" if match else value.strip()


def longitudinal_energy(row, eta, parameters):
    """Audit algebra from frozen contract; not a replacement route producer."""
    distance = row["route_distance_km"] * 1000.
    mass, gravity = parameters["gross_vehicle_mass_kg"], parameters["gravity_mps2"]
    drive = parameters["drivetrain_efficiency"]
    rolling = mass * gravity * parameters["rolling_resistance_coefficient"] * distance / drive / 3.6e6
    aero = (.5 * parameters["air_density_kg_per_m3"] * parameters["air_drag_coefficient"]
            * parameters["front_surface_area_m2"] * (distance / eta) ** 2 * distance / drive / 3.6e6)
    grade = mass * gravity * (row["cumulative_ascent_m"] / drive
            - parameters["regenerative_braking_efficiency"] * row["cumulative_descent_m"]) / 3.6e6
    auxiliary = parameters["battery_side_auxiliary_power_kw"] * eta / 3600.
    return rolling + aero + grade + auxiliary


def audit(root=None, current_input=CURRENT_INPUT, *, prefer_copied=True):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    original = root.parent / "IEEE8500_scalability_20260910"
    current_input = Path(current_input)
    portable = portable_configuration(root) if prefer_copied and (root / "ieee8500_v42/data/traffic_audit/SOURCE_MANIFEST.json").is_file() else None
    input_paths = portable["paths"] if portable else {name: current_input / name for name in
        ("NATIVE_INPUT.json", "OPERATIONS.json", "WINDOWS.json", "ROUTE_TABLE.json.gz", "TRAFFIC_FORECAST.npz")}
    graph_paths = portable["graph_paths"] if portable else GRAPH_PATHS
    native = read_json(input_paths["NATIVE_INPUT.json"])
    operations = read_json(input_paths["OPERATIONS.json"])
    windows = read_json(input_paths["WINDOWS.json"])
    route_path = input_paths["ROUTE_TABLE.json.gz"]
    raw_routes = gzip.decompress(route_path.read_bytes())
    table = json.loads(raw_routes)
    require(file_sha(route_path) == native["route_table"]["sha256"], "NATIVE_ROUTE_BYTE_SHA")
    if not portable:
        require(file_sha(route_path) == file_sha(ORIGINAL_TRAFFIC / route_path.name), "ORIGINAL_ROUTE_COPY_SHA")
    forecast_path = input_paths["TRAFFIC_FORECAST.npz"]
    if not portable:
        require(file_sha(forecast_path) == file_sha(ORIGINAL_TRAFFIC / forecast_path.name), "ORIGINAL_FORECAST_COPY_SHA")
    with np.load(forecast_path, allow_pickle=False) as payload:
        require(set(payload.files) == {"metadata", "Q10_sec", "Q50_sec", "Q90_sec"}, "FORECAST_FIELDS")
        metadata = json.loads(str(payload["metadata"]))
        quantiles = {key: payload[key].copy() for key in ("Q10_sec", "Q50_sec", "Q90_sec")}
    logical_hash = hashlib.sha256(json.dumps({key: metadata[key] for key in FORECAST_KEYS},
                                            sort_keys=True, separators=(",", ":")).encode())
    for array in quantiles.values():
        require(array.shape == (288, 509) and array.dtype == np.dtype("float32")
                and np.isfinite(array).all() and (array > 0).all(), "FORECAST_SHAPE_SECONDS")
        logical_hash.update(np.ascontiguousarray(array, dtype="<f4").tobytes())
    logical_sha = logical_hash.hexdigest()
    require(logical_sha == metadata["bundle_sha"] == native["traffic_forecast_sha"], "LOGICAL_FORECAST_SHA")
    require(np.all(quantiles["Q10_sec"] <= quantiles["Q50_sec"])
            and np.all(quantiles["Q50_sec"] <= quantiles["Q90_sec"]), "FORECAST_ORDER")
    midnight = datetime.fromisoformat(native["day"]).replace(tzinfo=timezone(timedelta(hours=10)))
    require(datetime.fromisoformat(metadata["issue_time"]) == midnight - timedelta(hours=6)
            and datetime.fromisoformat(metadata["max_input_timestamp"]) <= datetime.fromisoformat(metadata["issue_time"])
            and metadata["forecast_day"] == native["day"] == "2025-05-01"
            and metadata["causality_pass"] is True and metadata["future_actual_read_count"] == 0,
            "SAME_DAY_CAUSAL_AEST")
    require([datetime.fromisoformat(s) for s in metadata["target_timestamps"]]
            == [midnight + timedelta(minutes=5 * i) for i in range(288)], "FIVE_MINUTE_TIME_AXIS")

    original_service_path = graph_paths["service_nodes"] if portable else original / "static_reference/final_service_nodes_24.csv"
    original_services = csv_rows(original_service_path)
    expected = {row["service_id"]: row["traffic_node"] for row in original_services}
    current_services = csv_rows(graph_paths["service_nodes"])
    if portable:
        original_service_record = next(r for r in portable["proof"]["source_files"] if r["path"] == portable["proof"]["original_service_csv_readonly_path"])
        require(file_sha(original_service_path) == original_service_record["sha256"], "ARCHIVED_ORIGINAL_IEEE8500_SERVICE_SHA")
    else:
        require(file_sha(graph_paths["service_nodes"]) == file_sha(original_service_path), "ORIGINAL_IEEE8500_TRAFFIC_SERVICE_SOURCE_SHA")
    require({r["service_id"]: r["traffic_node"] for r in current_services} == expected, "SERVICE_24_NODE_IDENTITY")
    with (root / "ieee8500_v42/data/geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv").open(encoding="utf-8-sig", newline="") as stream:
        electrical_registry = list(csv.DictReader(stream))
    registry = {r["location_id"]: r for r in electrical_registry}
    identity = []
    for service_id, node in sorted(expected.items()):
        location_id = "A" + service_id if service_id.startswith("IDC") else service_id
        require(registry[location_id]["traffic_anchor"] == node, "ELECTRICAL_REGISTRY_TRAFFIC_IDENTITY")
        identity.append({"route_service_id": service_id, "electrical_location_id": location_id,
                         "original_traffic_node": node, "preserved": True})
    require(table["service_ids"] == sorted(expected) and table["departure_slots"] == list(range(96)), "ROUTE_AXES")
    graph_records = portable["graph_records"] if portable else [source_record(path) | {"role": role} for role, path in graph_paths.items()]
    require(all(row["exists"] for row in graph_records), "GRAPH_SOURCE_FILES_AVAILABLE")
    graph_manifest = [{"role": r["role"], "bytes": r["bytes"], "sha256": r["sha256"]} for r in graph_records]
    graph_sha = hashlib.sha256(json.dumps(graph_manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(graph_sha == metadata["graph_sha"], "ORIGINAL_GRAPH_FILE_MANIFEST_SHA")
    links = sorted(csv_rows(graph_paths["link_order"]), key=lambda r: int(r["tensor_index"]))
    require([r["reduced_link_id"] for r in links] == metadata["link_ids"], "LINK_509_TENSOR_AXIS")
    link_graph = {r["reduced_link_id"]: (traffic_node(r["from_node"]), traffic_node(r["to_node"])) for r in links}
    sequences = defaultdict(list)
    with gzip.open(graph_paths["physical_edge_catalog"], "rt", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            sequences[row["reduced_link_id"]].append((int(row["source_position"]), float(row["length_m"])))
    link_lengths = {}
    for link, sequence in sequences.items():
        sequence.sort()
        require([position for position, value in sequence] == list(range(len(sequence))), "PHYSICAL_EDGE_POSITION")
        require(all(math.isfinite(length) and length > 0 for position, length in sequence), "PHYSICAL_EDGE_METERS")
        link_lengths[link] = sum(length for position, length in sequence) / 1000.
    require(set(link_lengths) == set(link_graph), "PHYSICAL_EDGE_LINK_AXIS")

    physics_path = input_paths["MOBILITY_PHYSICS.json"] if portable else LEGACY_CODE / "pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json"
    physics = read_json(physics_path)
    require(physics["status"] == "FROZEN_PHYSICS_ONLY" and physics["mobility_energy_ml_loaded"] is False,
            "ORIGINAL_PHYSICS_CONTRACT")
    physics_sha = file_sha(physics_path)
    link_index = {link: i for i, link in enumerate(metadata["link_ids"])}
    keys, counts = set(), Counter()
    maxima = {"eta_snapshot_abs_error_sec": 0., "physical_distance_abs_error_km": 0., "physics_energy_abs_error_kwh": 0.}
    bands = defaultdict(list)
    moving_values = defaultdict(list)
    samples = []
    expected_keys = set(itertools.product(range(96), table["service_ids"], table["service_ids"]))
    for row in table["routes"]:
        depart, source, dest = row["departure_slot_15"], row["origin_service_id"], row["destination_service_id"]
        key = (depart, source, dest)
        require(key not in keys and key in expected_keys, "ROUTE_PRODUCT_KEY")
        keys.add(key)
        require(row["road_origin_node"] == expected[source] and row["road_destination_node"] == expected[dest], "ROW_TRAFFIC_NODE_IDENTITY")
        require(row["traffic_forecast_sha"] == logical_sha and row["route_graph_sha"] == graph_sha
                and row["physics_contract_sha"] == physics_sha, "ROW_SOURCE_SHA")
        eta = [row["route_" + q + "_eta_sec"] for q in ("q10", "q50", "q90")]
        require(all(math.isfinite(v) and v >= 0 for v in eta) and eta == sorted(eta), "ETA_QUANTILES_SECONDS")
        cursor = expected[source]
        for link in row["route_link_ids"]:
            require(link in link_graph and link_graph[link][0] == cursor, "CONTIGUOUS_DIRECTED_ROAD_PATH")
            cursor = link_graph[link][1]
        require(cursor == expected[dest], "ROAD_PATH_END_NODE")
        for q, value in zip(("Q10_sec", "Q50_sec", "Q90_sec"), eta):
            snapshot = sum(float(quantiles[q][3 * depart, link_index[link]]) for link in row["route_link_ids"])
            maxima["eta_snapshot_abs_error_sec"] = max(maxima["eta_snapshot_abs_error_sec"], abs(value - snapshot))
            require(value == snapshot, "EXACT_ORIGINAL_DEPARTURE_SNAPSHOT_ETA")
        distance = sum(link_lengths[link] for link in row["route_link_ids"])
        error = abs(distance - row["route_distance_km"])
        maxima["physical_distance_abs_error_km"] = max(maxima["physical_distance_abs_error_km"], error)
        require(error < 1e-10, "ORIGINAL_PHYSICAL_DISTANCE_KM")
        travel, ready, safe = row["travel_slots_15min"], row["connection_ready_slots_15min"], row["route_safe_eta_sec"]
        require(type(travel) is int and type(ready) is int, "INTEGER_TRAVEL_AND_CONNECTION_OFFSETS")
        if source == dest:
            require(travel == ready == 0 and row["route_link_ids"] == [] and safe == 0
                    and row["energy_nominal_kwh"] == row["energy_safe_kwh"] == 0, "ORIGINAL_STAY")
            counts["same_site_stay_rows"] += 1
            continue
        require(safe >= eta[1] and travel == math.ceil(safe / 900.)
                and ready == math.ceil((safe + 600.) / 900.), "ORIGINAL_600_SECOND_CONNECTION")
        bands[depart // 24].append(safe - eta[1])
        energy = [longitudinal_energy(row, value, physics["parameters"]) for value in eta]
        error = max(abs(energy[1] - row["energy_nominal_kwh"]), abs(max(energy) - row["energy_safe_kwh"]))
        maxima["physics_energy_abs_error_kwh"] = max(maxima["physics_energy_abs_error_kwh"], error)
        require(error < 1e-10, "ORIGINAL_PHYSICS_ENERGY_KWH")
        counts["moving_rows"] += 1
        counts["safe_eta_differs_from_route_q90"] += safe != eta[2]
        counts["accepted_original_move_arcs"] += 0 <= depart < depart + travel <= depart + ready < 96
        counts["outside_original_time_horizon"] += not 0 <= depart < depart + travel <= depart + ready < 96
        for name, value in (("distance_km", distance), ("safe_eta_sec", safe), ("travel_slots", travel),
                            ("ready_slots", ready), ("energy_safe_kwh", row["energy_safe_kwh"])):
            moving_values[name].append(value)
        if depart == 0 and source == "IDC01" and dest in ("IDC02", "STA01", "STA12"):
            samples.append({k: row[k] for k in ("origin_service_id", "destination_service_id", "road_origin_node", "road_destination_node",
                "departure_slot_15", "route_distance_km", "route_q50_eta_sec", "route_q90_eta_sec", "route_safe_eta_sec",
                "travel_slots_15min", "connection_ready_slots_15min", "energy_safe_kwh")})
    require(len(table["routes"]) == len(keys) == 96 * 24 * 24, "COMPLETE_55296_ROUTE_PRODUCT")

    code_files = [root / p for p in ("v42_bootstrap/m1.py", "v42_native/mess.py", "v42_may_campaign_native90/inputs.py",
        "v42_may_campaign_native90/traffic.py", "v42_may_campaign_native90/operations.py", "v42_pr134_b1/replay.py")]
    code_files += [LEGACY_CODE / p for p in ("dayahead/v33m/contracts.py", "dayahead/v33m/mobility_15min_adapter.py",
        "dayahead/v33m/road_graph_authority.py", "dayahead/v33m3/calibration.py", "dayahead/v33m3/actual_replay.py",
        "dayahead/v35/traffic_authority.py", "dayahead/v35/execution.py", "pfr/mobility_physics.py")]
    actual_path = WSL / "08_production_5min_validated_stage25f/year=2025/date=2025-05-01/link_tt_5min_24h.parquet"
    result = {"schema": "IEEE8500_READ_ONLY_TRAFFIC_MOBILITY_AUDIT_V1",
        "status": "ORIGINAL_24_TRAFFIC_IDENTITIES_AND_PLANNING_ROUTES_PASS_SIX_MESS_ACTUAL_GATE_UNCONNECTED",
        "planning_input_consistency_PASS": True, "six_vehicle_production_eligible": False,
        "service_identity_24": identity, "route_counts": dict(counts), "route_rows": len(keys),
        "native_network": native["network"], "native_schema": native["schema"],
        "initial_MESS_sites": native["initial_MESS_sites"], "native_vehicle_count": len(native["initial_MESS_sites"]),
        "native_battery": native["battery"], "native_nominal_capacity_kwh_field_present": "capacity_kwh" in native["battery"],
        "physics_parameters": physics["parameters"], "physics_contract_sha256": physics_sha,
        "forecast_shape": [288, 509, 3], "route_shape": [96, 24, 24],
        "forecast_issue_time": metadata["issue_time"], "forecast_max_input_timestamp": metadata["max_input_timestamp"],
        "forecast_future_actual_read_count": metadata["future_actual_read_count"],
        "logical_forecast_sha256": logical_sha, "raw_forecast_npz_sha256": file_sha(forecast_path),
        "original_graph_manifest_sha256": graph_sha, "route_uncompressed_sha256": hashlib.sha256(raw_routes).hexdigest(),
        "same_original_route_and_forecast_container_bytes": True,
        "input_read_mode": "PINNED_PORTABLE_COPIES_PREFERRED" if portable else "READ_ONLY_ORIGINAL_EXTERNAL_INPUTS",
        "external_files_required_for_this_replay": not bool(portable),
        "portable_new_storage_bytes": portable["manifest"]["new_bundle_storage_bytes"] if portable else None,
        "lossless_elevated_network_original_decoded_SHA_verified": bool(portable),
        "independent_reconstruction_error_max": maxima,
        "moving_route_ranges": {k: {"min": min(v), "max": max(v)} for k, v in moving_values.items()},
        "four_safe_eta_margin_bands_sec_from_rows": {str(k): {"min": min(v), "max": max(v)} for k, v in bands.items()},
        "safe_eta_calibration_fit_reexecuted": False,
        "safe_eta_calibration_json_in_legacy_code_exists": portable["proof"]["safe_eta_calibration_json_in_legacy_code_exists"] if portable else (LEGACY_CODE / "dayahead/artifacts/v33m3_causal_dayahead_traffic/V33M3_SAFE_ETA_CALIBRATION.json").is_file(),
        "original_safe_eta_not_replaced_by_route_q90": True,
        "connection_seconds_original": 600, "physical_site_specific_connection_time_certified": False,
        "WINDOWS_json_role": "AIDC_JOB_START_WINDOWS_NOT_MESS_SERVICE_ACCESS_OR_CONNECTION_WINDOWS",
        "WINDOWS_json_job_row_count": len(windows), "OPERATIONS_json_top_keys": list(operations),
        "representative_original_routes": samples,
        "actual_sumo_source": portable["proof"]["actual_sumo_source_metadata_only"] if portable else source_record(actual_path),
        "actual_sumo_source_record_role": "ARCHIVED_SOURCE_METADATA_ONLY_NOT_REOPENED" if portable else "READ_ONLY_SOURCE_FILE_IDENTITY",
        "actual_sumo_values_loaded": False, "actual_sumo_data_copied": False,
        "legacy_actual_replay_function_available": "dayahead/v33m3/actual_replay.py::replay_committed_move",
        "legacy_actual_algorithm": "freeze committed road links; per-link-entry five-minute realized time; physics energy at realized ETA; +600sec connection",
        "legacy_actual_batch_wrapper_hardcoded_units": 4,
        "current_V42_actual_MESS_policy": "v42_may_campaign_native90.operations.actual copies Planning MESS arrays bit-exact; no SUMO route availability or realized energy gate",
        "actual_six_vehicle_route_gate_connected": False,
        "missing_six_vehicle_fields_and_receipts": [
            "MESS05/MESS06 initial sites and six-unit native/Actual/Fresh DTO axes",
            "explicit nominal1800kWh and six-unit min/max/initial/terminal SOC in frozen scenario, p450kW/PCS600kVA",
            "vehicle physical contract applicability to new six1800kWh units, including frozen28000kg mass",
            "new joint24 electrical-location -> preserved24 route-service/road-node bijection bound to scenario SHA",
            "location-specific travel access and connection-time assumptions/evidence for reassigned MV/LV ports",
            "accepted six-vehicle frozen committed path/PQ/SOC plan and independent original route validator receipt",
            "post-freeze SUMO realized-time committed-route replay bound to exact same planning/scenario/graph/physics sources",
            "96x6 Actual availability and97x6 Actual SOC/traction-energy validation, late readiness conflict gate without reroute or repair"],
        "source_files": portable["proof"]["source_files"] if portable else [source_record(current_input / name) for name in
            ("NATIVE_INPUT.json", "OPERATIONS.json", "WINDOWS.json", "ROUTE_TABLE.json.gz", "TRAFFIC_FORECAST.npz")]
            + [source_record(ORIGINAL_TRAFFIC / name) for name in ("ROUTE_TABLE.json.gz", "TRAFFIC_FORECAST.npz")]
            + [source_record(original / "static_reference/final_service_nodes_24.csv"), source_record(physics_path)]
            + graph_records + [source_record(path) for path in code_files],
        "portable_file_records": list(portable["records"].values()) if portable else [],
        "module_sha256": file_sha(Path(__file__)), "Native_calls": 0, "model_build_calls": 0,
        "OpenDSS_calls": 0, "historical_launcher_imports": 0, "route_generation_calls": 0,
        "forecast_generation_calls": 0, "Actual_replay_calls": 0,
        "route_copy_policy": "ONE_PINNED_5.8MB_COMPRESSED_PLANNING_COPY_EXPLICITLY_AUTHORIZED_FOR_OFFLINE_REPLAY" if portable else "READ_IN_PLACE_NO_COPY"}
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    result = audit(root)
    path = root / "docs/ieee8500_v42_single_case/TRAFFIC_MOBILITY_AUDIT.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "route_rows", "route_counts", "native_vehicle_count",
        "independent_reconstruction_error_max", "actual_six_vehicle_route_gate_connected", "Native_calls", "OpenDSS_calls")}))


if __name__ == "__main__":
    main()
