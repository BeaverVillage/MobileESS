"""Validate the sealed plotting snapshot using only the Python standard library.

Reads CSV/JSON and hashes packaged files. Never imports the electrical model,
loads raw result archives, invokes a simulator, or writes to the package.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


DEFAULT_PACKAGE = Path(__file__).resolve().parents[1] / "docs/ieee8500/b0_plotting_data"
TOLERANCE = 1e-12
CSV_NAMES = {
    "coordinates": "00_ieee8500_bus_coordinates.csv",
    "topology": "01_ieee8500_branch_topology.csv",
    "critical": "02_B0_critical_time_summary.csv",
    "lines": "03_B0_line_loading_at_critical_time.csv",
    "phases": "04_B0_phase_loading_at_critical_time.csv",
    "plotting": "05_B0_plotting_ready.csv",
    "b3": "06_B3_same_time_loading_TEMPLATE.csv",
    "checks": "07_plotting_validation.csv",
    "ac": "08_B0_stored_AC_phase_loading_at_B0_critical_time.csv",
}
MANIFEST = "IEEE8500_B0_PLOTTING_MANIFEST.json"
AUDIT = "IEEE8500_B0_PLOTTING_AUDIT.md"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    result = float(value)
    require(math.isfinite(result), "Nonfinite numeric value")
    return result


def unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), "Duplicate " + key)
    return result


def load_tables(package):
    tables = {}
    for key, name in CSV_NAMES.items():
        with (package / name).open(encoding="utf-8-sig", newline="") as handle:
            tables[key] = list(csv.DictReader(handle))
    return tables


def validate_tables(tables, manifest):
    coordinates = unique(tables["coordinates"], "bus")
    topology = unique(tables["topology"], "element_id")
    lines = unique(tables["lines"], "element_id")
    plotting = unique(tables["plotting"], "element_id")
    require(len(coordinates) == 4912 and len(topology) == 4930, "Topology counts")
    require(set(topology) == set(plotting), "Plotting topology join")
    native_lines = {key for key, row in topology.items() if row["element_type"] == "LINE"}
    active = {key for key in native_lines if topology[key]["enabled"] == "TRUE"}
    inactive = native_lines - active
    require(len(native_lines) == 3703 and len(active) == 3698 and len(inactive) == 5, "Active/inactive line counts")
    require(set(lines) == native_lines, "Full LINE provenance preservation")
    for key in inactive:
        for row in (topology[key], lines[key], plotting[key]):
            require(row["rho_line_max"] == "NA" and row["loading_status"] == "INACTIVE_TIE", "Inactive tie must remain NA / INACTIVE_TIE")
            require(row["enabled"] == "FALSE" and row["plot_enabled"] == "FALSE", "Inactive tie plotting mask")
    for key in active:
        for row in (topology[key], lines[key], plotting[key]):
            require(row["plot_enabled"] == "TRUE" and row["loading_status"] == "RESOLVED", "Active plotting mask")
    for key, row in topology.items():
        for endpoint in (1, 2):
            coordinate = coordinates[row[f"bus{endpoint}"]]
            for axis in ("x", "y"):
                for scope in ("raw", "plot"):
                    require(Decimal(row[f"{axis}{endpoint}_{scope}"]) == Decimal(coordinate[f"{axis}_{scope}"]), "Topology coordinate join")
                require(plotting[key][f"{axis}{endpoint}_plot"] == row[f"{axis}{endpoint}_plot"], "Plotting coordinate identity")
        require(plotting[key]["bus1"] == row["bus1"] and plotting[key]["bus2"] == row["bus2"], "Plotting endpoint identity")
        if row["element_type"] != "LINE":
            require(plotting[key]["rho_line_max"] == "NA", "Non-LINE loading must be NA")
    for row in coordinates.values():
        for field in ("x_raw", "y_raw", "x_plot", "y_plot"):
            number(row[field])
        expected = Decimal(row["x_raw"])
        if manifest["horizontal_reflection"]:
            expected = Decimal(manifest["xmin"]) + Decimal(manifest["xmax"]) - expected
        require(Decimal(row["x_plot"]) == expected and row["y_plot"] == row["y_raw"], "Exact geometry/reflection preservation")
    require(Decimal(coordinates["sourcebus"]["x_plot"]) < (Decimal(manifest["xmin"]) + Decimal(manifest["xmax"])) / 2, "Substation must be left")
    require(len(tables["critical"]) == 1, "One critical summary row required")
    critical = tables["critical"][0]
    require(critical["metric_scope"] == "PLANNING", "Primary metric scope")
    require(critical["critical_interval"] == "31" and critical["critical_timestamp"] == "2025-05-21T07:45:00+10:00", "B0 interval-start authority")
    require(critical["critical_element"] == "Line.tpx21459660c0" and critical["critical_phase"] == "t2_node1", "Critical witness authority")
    require(abs(number(critical["rho_max"]) - 0.8487691403696187) <= TOLERANCE, "Critical peak authority")
    grouped = defaultdict(list)
    phase_keys = set()
    for row in tables["phases"]:
        key = (row["element_id"], row["conductor_label"])
        require(key not in phase_keys, "Duplicate phase/conductor key")
        phase_keys.add(key)
        require(row["phase"] == row["conductor_label"] == "t" + row["terminal_of_max_loading"] + "_" + row["conductor"], "Terminal/conductor identity")
        require(row["phase_of_max_loading"] in {"A", "B", "C"}, "Resolved native primary phase")
        rating = number(row["rating_A"])
        require(rating > 0 and abs(number(row["current_A"]) / rating - number(row["rho_phase"])) <= TOLERANCE, "Stored current/rating identity")
        require(row["metric_scope"] == "PLANNING", "Mixed metric scope")
        require(row["critical_interval"] == critical["critical_interval"] and row["critical_timestamp"] == critical["critical_timestamp"], "Phase critical timestamp")
        grouped[row["element_id"]].append(row)
    require(len(phase_keys) == 12312 and set(grouped) == active, "Active phase loading coverage")
    for key, phase_rows in grouped.items():
        representative = max(phase_rows, key=lambda row: number(row["rho_phase"]))
        for row in (lines[key], plotting[key], topology[key]):
            require(abs(number(row["rho_line_max"]) - number(representative["rho_phase"])) <= TOLERANCE, "Phase-to-LINE maximum mismatch")
        for field in ("terminal_of_max_loading", "phase_of_max_loading", "conductor_label"):
            require(lines[key][field] == representative[field] == plotting[key][field], "Representative conductor mismatch")
        for endpoint in ("bus1", "bus2"):
            require(all(row[endpoint] == topology[key][endpoint] for row in phase_rows), "Phase endpoint join")
        for field in ("P_from_kW", "Q_from_kvar", "P_to_kW", "Q_to_kvar"):
            require(lines[key][field] == "NA", "Unstored terminal power must remain NA")
    require(not tables["b3"], "B3 template must have no data rows")
    require([key for key, row in plotting.items() if row["is_critical_line"] == "TRUE"] == [critical["critical_element"]], "Critical plotting flag")
    checks = unique(tables["checks"], "check")
    require(len(checks) == 34 and all(row["status"] == "PASS" for row in checks.values()), "Stored validation gates")
    require(checks["ACTIVE_LINE_LOADING_COVERAGE"]["status"] == "PASS" and checks["INACTIVE_TIE_PRESERVATION"]["status"] == "PASS", "Required active/inactive gates")
    ac_keys = {(row["element_id"], row["conductor_label"]) for row in tables["ac"]}
    require(ac_keys == phase_keys and len(tables["ac"]) == 12312, "Auxiliary AC phase coverage")
    require(all(row["metric_scope"] == "B0_REPLAY_AC" and row["critical_timestamp"] == critical["critical_timestamp"] for row in tables["ac"]), "Auxiliary AC scope/time")
    require(manifest["scientific_execution_count"] == 0 and manifest["result"] == "PASS", "Extraction execution accounting")
    return {"status": "PASS", "topology_lines": len(native_lines), "active_scientific_lines": len(active),
            "inactive_tie_lines": len(inactive), "active_result_matched_lines": len(grouped),
            "active_line_loading_coverage": len(grouped) / len(active), "stored_gates": len(checks),
            "scientific_execution_count": 0}


def validate_package(package):
    expected_names = set(CSV_NAMES.values()) | {MANIFEST, AUDIT}
    checksums = {}
    for line in (package / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        require(name not in checksums, "Duplicate checksum entry")
        checksums[name] = digest
    require(set(checksums) == expected_names, "Snapshot checksum inventory")
    for name, expected in checksums.items():
        require(hashlib.sha256((package / name).read_bytes()).hexdigest() == expected, "SHA256 mismatch: " + name)
    manifest = json.loads((package / MANIFEST).read_text(encoding="utf-8"))
    for record in manifest["output_files"]:
        require(record["filename"] in checksums and checksums[record["filename"]] == record["sha256"], "Original manifest checksum mismatch")
    return validate_tables(load_tables(package), manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    try:
        result = validate_package(args.package)
    except (ValueError, KeyError, OSError, ArithmeticError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
