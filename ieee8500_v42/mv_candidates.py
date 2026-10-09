"""Static MV host audit; imports no original launcher, Native or OpenDSS.

Electrical host eligibility is independent from physical service-port approval.
Original line-matrix placement weights are reconstructed, not fitted to AC.
"""
import argparse
from collections import defaultdict, deque
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

from .integration import file_sha


ROOT_BUS = "_hvmv_sub_lsb"
NOMINAL_KV_LL = 12.47
KV_TOLERANCE = .01247
GUARD_QUANTILE = .05
PINNED_Q05_OHM = 1.3819547376654384
OLD_PAIR_ELECTRICAL_MIN_OHM = .9129072401559803
OLD_PAIR_XY_MIN_UNKNOWN_UNITS = 2221.532547954318
SOURCE_INPUTS = {
    "HISTORICAL_LINES.json": "audit/lines.json",
    "HISTORICAL_TOPOLOGY_EDGES.json": "audit/topology_edges.json",
    "PRIMARY_CORRIDORS.json": "audit/primary_corridors.json",
    "ORIGINAL_STATIC_FEATURES.json": "audit/candidate_pool_static_features.json",
    "METHODOLOGY_INPUTS.json": "audit/methodology_inputs.json",
    "ROOT_DISTANCE_GUARD.json": "selection_v3_source_proximity/ROOT_DISTANCE_GUARD_AUDIT.json",
    "ORIGINAL_GUARDED_POOL.json": "selection_v3_source_proximity/GUARDED_CANDIDATE_POOL.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def base_bus(value):
    return value.split(".")[0].lower()


def quantile_linear(values, fraction):
    values = sorted(values)
    require(bool(values) and 0 <= fraction <= 1, "Invalid quantile input")
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (position - lower) * (values[upper] - values[lower])


def line_length_km(length, units):
    # DSS length units: none, miles, kft, km, m, ft, inch, cm.
    factors = {1: 1.609344, 2: .3048, 3: 1., 4: .001, 5: .0003048,
               6: .0000254, 7: .00001}
    return float(length) * factors[int(units)] if int(units) in factors else None


def terminal_nodes(row, terminal):
    ncond = int(row["ncond"])
    start = terminal * ncond
    return row["node_order"][start:start + ncond]


def complete_abc_corridors(inventory, old_lines):
    """Require conductor identity 1->1, 2->2, 3->3 across a corridor.

    Separate phase line and regulator links are combined only at the same bus
    pair. Local three-node presence cannot substitute for a source path.
    """
    buses = {row["bus"]: row for row in inventory["buses"]}
    primary = {bus for bus, row in buses.items()
               if set(row["nodes"]) == {1, 2, 3}
               and abs(row["kv_base_ln"] * math.sqrt(3) - NOMINAL_KV_LL) <= KV_TOLERANCE}
    regulators = {"transformer." + r["transformer"].lower() for r in inventory["regcontrols"]}
    pairs = defaultdict(lambda: {"phase_pairs": set(), "elements": [], "line_elements": []})
    for row in inventory["lines"] + inventory["transformers"]:
        element = row["element"].lower()
        if not row["enabled"] or row["nterm"] != 2:
            continue
        if element.startswith("line."):
            old = old_lines[element]
            if old["any_open"]:
                continue
        elif element not in regulators:
            continue
        u, v = map(base_bus, row["buses"])
        if u not in primary or v not in primary or u == v:
            continue
        pair = tuple(sorted((u, v)))
        nodes = zip(terminal_nodes(row, 0), terminal_nodes(row, 1))
        if pair != (u, v):
            nodes = ((b, a) for a, b in nodes)
        pairs[pair]["phase_pairs"].update((a, b) for a, b in nodes if a in {1, 2, 3} and b in {1, 2, 3})
        pairs[pair]["elements"].append(element)
        if element.startswith("line."):
            pairs[pair]["line_elements"].append(element)
    return {pair: row for pair, row in pairs.items()
            if {(1, 1), (2, 2), (3, 3)}.issubset(row["phase_pairs"])}


@dataclass
class MVCandidateSet:
    candidates: list
    excluded: list
    parent: dict
    depth: dict
    edge_weights: dict
    coordinates: dict
    audit: dict

    def pair_metrics(self, bus_a, bus_b):
        """Original rooted-tree distance/shared-path metric, plus raw XY distance."""
        bus_a, bus_b = bus_a.lower(), bus_b.lower()
        require(bus_a in self.coordinates and bus_b in self.coordinates, "Unknown candidate bus")
        ancestors = set()
        cursor = bus_a
        while cursor is not None:
            ancestors.add(cursor)
            cursor = self.parent[cursor]
        cursor = bus_b
        while cursor not in ancestors:
            cursor = self.parent[cursor]
        shared = self.depth[cursor]
        electrical = self.depth[bus_a] + self.depth[bus_b] - 2 * shared
        denominator = self.depth[bus_a] + self.depth[bus_b] - shared
        raw_xy = math.dist(self.coordinates[bus_a], self.coordinates[bus_b])
        return {"electrical_tree_distance_ohm": electrical,
                "shared_upstream_path_ratio": shared / denominator if denominator else 1.,
                "source_xy_distance_unknown_units": raw_xy,
                "original_electrical_dispersion_gate_pass": electrical >= OLD_PAIR_ELECTRICAL_MIN_OHM,
                "original_xy_dispersion_gate_pass": raw_xy >= OLD_PAIR_XY_MIN_UNKNOWN_UNITS,
                "original_pair_gates_role": "AUDIT_AND_SCORE_NOT_PHYSICAL_INTERCONNECTION_LIMITS"}


def capture_source_inputs(root, original_root):
    """Copy only immutable static JSON to the new namespace and pin origin SHA."""
    root, original_root = Path(root).resolve(), Path(original_root).resolve()
    destination = root / "ieee8500_v42/data/mv_candidates"
    base_freeze = read_json(original_root / "FREEZE_MANIFEST.json")
    guard_freeze = read_json(original_root / "selection_v3_source_proximity/GUARDED_SELECTION_FREEZE_MANIFEST.json")
    pins = {r["path"]: r["sha256"] for r in base_freeze["files"]}
    pins.update({"selection_v3_source_proximity/" + r["path"]: r["sha256"] for r in guard_freeze["files"]})
    records = []
    for name, relative in SOURCE_INPUTS.items():
        source = original_root / relative
        require(relative in pins and file_sha(source) == pins[relative], "Source freeze mismatch: " + relative)
        records.append({"copy": name, "original_path": str(source), "original_relative_path": relative,
                        "sha256": pins[relative]})
    # All verification precedes any copy; source scripts are read only, never run.
    destination.mkdir(parents=True, exist_ok=True)
    for row in records:
        (destination / row["copy"]).write_bytes(Path(row["original_path"]).read_bytes())
    script_paths = ["compile_audit.py", "methodology_inputs.py", "selection_v3_source_proximity/select_sites.py"]
    receipt = {"schema": "IEEE8500_MV_STATIC_SOURCE_COPIES_V1", "files": records,
               "base_freeze_sha256": file_sha(original_root / "FREEZE_MANIFEST.json"),
               "guarded_freeze_sha256": file_sha(original_root / "selection_v3_source_proximity/GUARDED_SELECTION_FREEZE_MANIFEST.json"),
               "read_only_source_scripts": [{"path": str(original_root / p), "sha256": file_sha(original_root / p)}
                                             for p in script_paths],
               "historical_launcher_imports": 0, "Native_calls": 0, "OpenDSS_calls": 0}
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def build_candidates(root=None):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    data = root / "ieee8500_v42/data/mv_candidates"
    docs = root / "docs/ieee8500_v42_single_case"
    manifest = read_json(data / "SOURCE_MANIFEST.json")
    for row in manifest["files"]:
        require(file_sha(data / row["copy"]) == row["sha256"], "Copied static input SHA mismatch: " + row["copy"])
    inventory_path = docs / "ORIGINAL_FEEDER_INVENTORY.json"
    inventory = read_json(inventory_path)
    for name, expected in inventory["source_sha256"].items():
        require(file_sha(root / "ieee8500_v42/data/feeder" / name) == expected, "Current feeder source SHA mismatch: " + name)
    old_lines = {"line." + row["name"].lower(): row for row in read_json(data / "HISTORICAL_LINES.json")}
    current_lines = {row["element"].lower(): row for row in inventory["lines"]}
    require(set(old_lines) == set(current_lines), "Original/current line roster mismatch")
    for element, old in old_lines.items():
        current = current_lines[element]
        require(current["enabled"] == old["enabled"] and current["nphase"] == old["phases"]
                and [b.lower() for b in current["buses"]] == [old["bus1"].lower(), old["bus2"].lower()]
                and current["length"] == old["length"] and current["units"] == old["units"],
                "Original/current line physical metadata mismatch: " + element)

    corridors = complete_abc_corridors(inventory, old_lines)
    archived = {tuple(sorted((r["u"], r["v"]))): r for r in read_json(data / "PRIMARY_CORRIDORS.json")}
    require(set(corridors) == set(archived), "Actual conductor-level ABC graph differs from original corridors")
    adjacency = defaultdict(dict)
    corridor_length = {}
    for pair, row in corridors.items():
        diagonal_weights, lengths, unknown_elements = [], [], []
        for element in row["line_elements"]:
            line = old_lines[element]
            phases = line["phases"]
            require(len(line["r_matrix"]) == len(line["x_matrix"]) == phases * phases, "Non-primary matrix unexpectedly entered ABC graph")
            diagonal_weights.extend(math.hypot(line["r_matrix"][i * phases + i], line["x_matrix"][i * phases + i])
                                    * line["length"] for i in range(phases))
            length = line_length_km(line["length"], line["units"])
            if length is None:
                unknown_elements.append(element)
            else:
                lengths.extend([length] * phases)
        weight = sum(diagonal_weights) / len(diagonal_weights) if diagonal_weights else 0.
        require(math.isclose(weight, archived[pair]["weight_ohm"], abs_tol=1e-13), "Original corridor weight mismatch")
        require(set(row["elements"]) == set(archived[pair]["elements"]), "Original corridor elements mismatch")
        u, v = pair
        adjacency[u][v] = adjacency[v][u] = weight
        corridor_length[pair] = {"known_length_km": sum(lengths) / len(lengths) if lengths else 0.,
                                 "unknown_elements": unknown_elements}

    parent, depth, hops = {ROOT_BUS: None}, {ROOT_BUS: 0.}, {ROOT_BUS: 0}
    known_length, unknown_length = {ROOT_BUS: 0.}, {ROOT_BUS: []}
    queue = deque([ROOT_BUS])
    while queue:
        u = queue.popleft()
        for v, weight in sorted(adjacency[u].items()):
            if v in parent:
                continue
            parent[v], depth[v], hops[v] = u, depth[u] + weight, hops[u] + 1
            length_row = corridor_length[tuple(sorted((u, v)))]
            known_length[v] = known_length[u] + length_row["known_length_km"]
            unknown_length[v] = unknown_length[u] + length_row["unknown_elements"]
            queue.append(v)
    require(len(corridors) == len(parent) - 1 == 646, "ABC primary graph is not the original tree")

    # Source reachability uses all enabled original branches, including the
    # original source Reactor. ABC placement distance still starts at head.
    source_adjacency = defaultdict(set)
    historical_edges = read_json(data / "HISTORICAL_TOPOLOGY_EDGES.json")
    reactor_count = 0
    for row in inventory["lines"] + inventory["transformers"]:
        element = row["element"].lower()
        if not row["enabled"] or (element in old_lines and old_lines[element]["any_open"]):
            continue
        buses = list(dict.fromkeys(base_bus(b) for b in row["buses"]))
        for v in buses[1:]:
            source_adjacency[buses[0]].add(v)
            source_adjacency[v].add(buses[0])
    transformer_source = (root / "ieee8500_v42/data/feeder/Transformers.dss").read_text(encoding="utf-8-sig").lower()
    for edge in historical_edges:
        if edge["kind"] == "reactor":
            require(edge["element"].lower() in transformer_source, "Original source Reactor absent from source")
            require(edge["u"] == "sourcebus" and edge["v"] == "hvmv_sub_hsb", "Unexpected source Reactor topology")
            source_adjacency[edge["u"]].add(edge["v"])
            source_adjacency[edge["v"]].add(edge["u"])
            reactor_count += 1
    require(reactor_count == 1, "Expected one original source Reactor")
    source_parent = {"sourcebus": None}
    queue = deque(["sourcebus"])
    while queue:
        u = queue.popleft()
        for v in sorted(source_adjacency[u]):
            if v not in source_parent:
                source_parent[v] = u
                queue.append(v)
    require(ROOT_BUS in source_parent, "Original feeder head not connected to source")

    buses = {row["bus"]: row for row in inventory["buses"]}
    regulator_elements = {"transformer." + r["transformer"].lower() for r in inventory["regcontrols"]}
    exclusions = {"sourcebus"}
    for row in inventory["transformers"]:
        if row["element"].lower() in regulator_elements or row["element"].lower() == "transformer.hvmv_sub":
            exclusions.update(base_bus(b) for b in row["buses"])
    exclusions.update(bus for bus in buses if "hvmv_sub" in bus or bus.startswith("regxfmr_"))
    independently_eligible = sorted(bus for bus, row in buses.items()
        if abs(row["kv_base_ln"] * math.sqrt(3) - NOMINAL_KV_LL) <= KV_TOLERANCE
        and set(row["nodes"]) == {1, 2, 3} and row["coord_defined"]
        and bus not in exclusions and bus in parent and bus in source_parent)
    features = {row["bus"]: row for row in read_json(data / "ORIGINAL_STATIC_FEATURES.json")}
    require(independently_eligible == sorted(features) and len(features) == 638, "Original 638 eligibility roster mismatch")
    distance_error = max(abs(depth[bus] - features[bus]["primary_upstream_impedance_ohm"]) for bus in features)
    require(distance_error < 1e-12, "Reconstructed original root-distance mismatch")
    guard = read_json(data / "ROOT_DISTANCE_GUARD.json")
    q05 = quantile_linear([depth[b] for b in independently_eligible], GUARD_QUANTILE)
    require(q05 == guard["root_distance_q05_ohm"] == PINNED_Q05_OHM, "Original root q05 guard mismatch")
    kept = [bus for bus in independently_eligible if depth[bus] >= q05]
    historical_guarded = {r["bus"] for r in read_json(data / "ORIGINAL_GUARDED_POOL.json")}
    require(set(kept) == historical_guarded and len(kept) == 606, "Original 606 guarded roster mismatch")
    with (root / "ieee8500_v42/data/geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv").open(encoding="utf-8-sig", newline="") as stream:
        old_services = list(csv.DictReader(stream))
    service_labels = defaultdict(list)
    for row in old_services:
        service_labels[row["ieee8500_bus"].lower()].append(row["location_id"])
    input_sha = file_sha(data / "SOURCE_MANIFEST.json")
    rows = []
    for bus in independently_eligible:
        node = buses[bus]
        feature = features[bus]
        require(node["x"] == feature["x"] and node["y"] == feature["y"], "Original/current candidate XY mismatch")
        rows.append({"candidate_id": "MV:" + bus, "dss_bus": bus, "x": node["x"], "y": node["y"],
            "coordinate_crs_units_compass_certified": False, "phase_nodes": "1,2,3",
            "nominal_kv_ll": node["kv_base_ln"] * math.sqrt(3), "nominal_kv_ln": node["kv_base_ln"],
            "continuous_abc_from_feeder_head": True, "original_source_connected": True,
            "source_substation_regulator_exclusion_pass": True,
            "root_distance_ohm": depth[bus], "root_distance_q05_guard_ohm": q05,
            "source_proximity_guard_pass": depth[bus] >= q05,
            "root_distance_over_q05": depth[bus] / q05, "feeder_head_path_hops": hops[bus],
            "feeder_head_path_known_line_length_km": known_length[bus],
            "feeder_head_path_length_complete": not unknown_length[bus],
            "unknown_length_elements": "|".join(unknown_length[bus]),
            "lateral_group": feature["lateral_group"],
            "electrical_host_eligible": depth[bus] >= q05,
            "existing_historical_service_labels": "|".join(service_labels[bus]),
            "historical_service_label_is_physical_port_evidence": False,
            "physical_port_qualified": False, "port_derating_certified": False,
            "allowed_import_kw": None, "allowed_export_kw": None, "allowed_pcs_kva": None,
            "interconnection_protection_access_timing_evidence": "NOT_PROVIDED",
            "source_evidence_sha256": input_sha, "original_device_transformer_added": False})
    candidates = [row for row in rows if row["electrical_host_eligible"]]
    excluded = [row for row in rows if not row["electrical_host_eligible"]]
    audit = {"schema": "IEEE8500_INDEPENDENT_STATIC_MV_HOST_AUDIT_V1", "status": "606_ELECTRICAL_HOSTS_VERIFIED_PHYSICAL_PORTS_UNQUALIFIED",
        "original_candidate_count": 638, "guarded_candidate_count": len(candidates), "guard_excluded_count": len(excluded),
        "original_abc_tree_buses": len(parent), "original_abc_tree_corridors": len(corridors),
        "root_distance_reconstruction_error_max_ohm": distance_error, "root_distance_q05_ohm": q05,
        "original_source_reactor_explicitly_included": True,
        "native_calls": 0, "OpenDSS_calls": 0, "historical_launcher_imports": 0,
        "physical_ports_qualified": 0, "selection_executed": False, "final_scenario_frozen": False,
        "original_hard_host_gates": ["12.47kV within original 0.1 percent tolerance", "exact ABC nodes",
            "continuous conductor-identity ABC path from feeder head", "source/substation/regulator terminals excluded",
            "source connected including original Reactor", "source coordinate available", "root impedance >= original638 q05"],
        "original_pair_dispersion_audit_thresholds": {"electrical_distance_ohm": OLD_PAIR_ELECTRICAL_MIN_OHM,
            "source_xy_distance_unknown_units": OLD_PAIR_XY_MIN_UNKNOWN_UNITS,
            "role": "AUDIT_AND_SCORE_PER_LATEST_USER_SCOPE_NOT_PHYSICAL_INTERCONNECTION_LIMITS"},
        "original_shape_audit_thresholds": {"E_coord": .20, "E_pair": .20, "two_nearest_neighbor_retention": .50},
        "joint_selection_hard_gates": ["strict all276 traffic pair signs", "one common frozen proper similarity", "24 distinct PCC buses and service IDs"],
        "derating_or_capacity_allowance_assumed": False,
        "source_manifest_sha256": input_sha, "actual_inventory_sha256": file_sha(inventory_path),
        "module_sha256": file_sha(Path(__file__)),
        "inputs": manifest["files"], "known_path_length_incomplete_count": sum(not r["feeder_head_path_length_complete"] for r in candidates),
        "path_length_note": "DSS Units=0 cannot be converted to km; report known segments and unknown original elements explicitly"}
    return MVCandidateSet(candidates, excluded, parent, depth, adjacency,
                          {b: (features[b]["x"], features[b]["y"]) for b in features}, audit)


def write_outputs(root, candidate_set):
    docs = Path(root) / "docs/ieee8500_v42_single_case"
    for name, rows in (("MV_AIDC_CANDIDATES.csv", candidate_set.candidates),
                       ("MV_AIDC_EXCLUDED_SOURCE_PROXIMITY.csv", candidate_set.excluded)):
        with (docs / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    audit = dict(candidate_set.audit)
    audit["output_sha256"] = {name: file_sha(docs / name) for name in
        ("MV_AIDC_CANDIDATES.csv", "MV_AIDC_EXCLUDED_SOURCE_PROXIMITY.csv")}
    (docs / "MV_AIDC_CANDIDATE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-original", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.capture_original:
        capture_source_inputs(root, args.capture_original)
    result = build_candidates(root)
    audit = write_outputs(root, result)
    print(json.dumps({k: audit[k] for k in ("status", "original_candidate_count", "guarded_candidate_count",
        "guard_excluded_count", "root_distance_reconstruction_error_max_ohm", "physical_ports_qualified",
        "native_calls", "OpenDSS_calls")}))


if __name__ == "__main__":
    main()
