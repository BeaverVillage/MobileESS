"""Read-only, archive-only extraction of IEEE8500 May-1 Actual B0/B3 line loading.

Run: python extract_ieee8500_may01_b0_b3_timeseries.py
Requires numpy. No OpenDSS, optimization, or other scientific execution.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import tarfile
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ARCHIVE = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_MAY01_MESS6_RAW_RESULTS_20260914_151641.tar.gz")
OUTPUT = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_MAY01_B0_B3_TIMESERIES_HEATMAP_DATA_20260920")
ZIP = OUTPUT.parent / (OUTPUT.name + ".zip")
DATE = "2025-05-01"
SLOTS = 96
SLOT_MINUTES = 15

B0_ROOT = "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913"
B3_ROOT = "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
ROOTS = {"B0": B0_ROOT, "B3": B3_ROOT}
ACTUAL = {
    "B0": B0_ROOT + "/actual/B0",
    "B3": B3_ROOT + "/actual_B3_energy_exception_20260914/B3",
}

ROLES = {}
for policy, root in ROOTS.items():
    base = ACTUAL[policy]
    ROLES[root + "/AXES.json"] = (policy, "REALIZED_OPERATION_AC", "axes_and_ratings", True)
    ROLES[root + "/PCC_BusCoordinates.dss"] = (policy, "SOURCE_OVERLAY", "pcc_coordinates", True)
    ROLES[root + "/PCC_Master.dss"] = (policy, "SOURCE_REFERENCE", "master_reference", True)
    ROLES[base + "/COMPLETE.json"] = (policy, "REALIZED_OPERATION_AC", "completion", True)
    for filename, role in (
        ("OPENDSS_PHASE_ARRAYS.npz", "phase_arrays"),
        ("AC_SUMMARY.json", "official_summary"),
        ("SLOT_EXTREMA.json", "slot_extrema"),
    ):
        ROLES[base + "/FINAL_ACTUAL/" + filename] = (policy, "REALIZED_OPERATION_AC/FINAL_ACTUAL", role, True)
        for alt in ("CONTINUOUS_VERIFICATION", "ETA95_ACTUAL"):
            ROLES[base + "/" + alt + "/" + filename] = (policy, "REALIZED_OPERATION_AC/" + alt, role, False)

NAMES = [
    "00_ARCHIVE_MEMBER_AUDIT.csv",
    "01_B0_B3_LINE_LOADING_96SLOT_LONG.csv",
    "02_IEEE8500_LINE_TOPOLOGY.csv",
    "03_B0_B3_SYSTEM_RHO_96SLOT.csv",
    "04_B0_B3_DAILY_MAX_BY_LINE.csv",
    "05_B0_STRESS_SLOT_RANKING.csv",
    "06_B0_B3_STRESS_WINDOW_MEAN_BY_LINE.csv",
    "07_B0_B3_LOADING_DURATION_BY_LINE.csv",
    "IEEE8500_MAY01_B0_B3_EXTRACTION_AUDIT.md",
    "IEEE8500_MAY01_B0_B3_EXTRACTION_MANIFEST.json",
    "extract_ieee8500_may01_b0_b3_timeseries.py",
]


def read_archive():
    selected = {}
    member_rows = []
    member_count = 0
    member_names = set()
    with tarfile.open(ARCHIVE, "r|gz") as tf:
        for m in tf:
            member_count += 1
            member_names.add(m.name)
            role = ROLES.get(m.name)
            if role is None:
                continue
            policy, scope, artifact_role, used = role
            digest = ""
            if used:
                with tf.extractfile(m) as f:
                    payload = f.read()
                digest = hashlib.sha256(payload).hexdigest()
                selected[m.name] = payload
            member_rows.append((policy, scope, artifact_role, m.name, digest, m.size, used))
    missing = [name for name, role in ROLES.items() if role[3] and name not in selected]
    if missing:
        raise RuntimeError("Missing selected archive members: " + repr(missing))
    return selected, member_rows, member_count, member_names


def source(selected, name):
    return selected[name]


def as_json(selected, name):
    return json.loads(source(selected, name).decode("utf-8"))


def strip_phase(bus):
    return re.sub(r"(?:\.\d+)+$", "", bus)


def parse_coordinates(payload):
    coordinates = {}
    for row in payload.decode("utf-8").splitlines():
        match = re.fullmatch(r"\s*SetBusXY\s+Bus=(\S+)\s+x=([-+\deE.]+)\s+y=([-+\deE.]+)\s*", row, re.I)
        if not match:
            raise ValueError("Unrecognized coordinate row: " + row)
        bus, x, y = match.groups()
        key = bus.lower()
        point = (float(x), float(y))
        if key in coordinates and coordinates[key] != point:
            raise ValueError("Conflicting coordinates: " + bus)
        coordinates[key] = point
    return coordinates


def parse_axes(labels, ratings):
    if len(labels) != len(ratings) or len(labels) != 12312:
        raise ValueError("Unexpected line axis/rating length")
    grouped = defaultdict(list)
    terminal_bus = defaultdict(lambda: defaultdict(set))
    phases = defaultdict(set)
    for j, (label, rating) in enumerate(zip(labels, ratings)):
        parts = label.split("|")
        if len(parts) != 4 or not parts[0].startswith("Line."):
            raise ValueError("Invalid line axis: " + label)
        element, terminal, bus, node = parts
        if terminal not in ("t1", "t2") or not re.fullmatch(r"node[123]", node):
            raise ValueError("Invalid terminal/phase: " + label)
        if not math.isfinite(rating) or rating <= 0:
            raise ValueError("Invalid rating: " + label)
        grouped[element].append(j)
        terminal_bus[element][terminal].add(strip_phase(bus))
        phases[element].add(node[-1])
    line_ids = list(grouped)
    topology = []
    rating_variation = 0
    for element in line_ids:
        buses = terminal_bus[element]
        if set(buses) != {"t1", "t2"} or any(len(v) != 1 for v in buses.values()):
            raise ValueError("Inconsistent terminal buses for " + element)
        rated = {float(ratings[j]) for j in grouped[element]}
        if len(rated) != 1:
            rating_variation += 1
        topology.append({
            "element_id": element,
            "element_type": "LINE",
            "element_status": "ACTIVE",
            "from_bus": next(iter(buses["t1"])),
            "to_bus": next(iter(buses["t2"])),
            "phases_available": ".".join(sorted(phases[element])),
            "rating_A": next(iter(rated)) if len(rated) == 1 else "",
            "num_phases": len(phases[element]),
            "is_switch": "",  # Absent from AXES; do not infer from name.
            "is_disabled": False,
        })
    return line_ids, grouped, topology, rating_variation


def csv_file(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def iso_slot(slot):
    return (datetime.fromisoformat(DATE) + timedelta(minutes=SLOT_MINUTES * slot)).isoformat(timespec="minutes")


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    selected, members, member_count, member_names = read_archive()
    axes = {p: as_json(selected, ROOTS[p] + "/AXES.json") for p in ("B0", "B3")}
    completed = {p: as_json(selected, ACTUAL[p] + "/COMPLETE.json") for p in ("B0", "B3")}
    summaries = {p: as_json(selected, ACTUAL[p] + "/FINAL_ACTUAL/AC_SUMMARY.json") for p in ("B0", "B3")}
    extrema = {p: as_json(selected, ACTUAL[p] + "/FINAL_ACTUAL/SLOT_EXTREMA.json") for p in ("B0", "B3")}
    coords = {p: parse_coordinates(source(selected, ROOTS[p] + "/PCC_BusCoordinates.dss")) for p in ("B0", "B3")}
    if coords["B0"] != coords["B3"]:
        raise ValueError("B0/B3 coordinate overlay differs")
    if axes["B0"]["line"] != axes["B3"]["line"]:
        raise ValueError("B0/B3 line axes differ")
    if axes["B0"]["line_rating_A"] != axes["B3"]["line_rating_A"]:
        raise ValueError("B0/B3 line ratings differ")
    for p in ("B0", "B3"):
        if completed[p].get("policy") != p or completed[p].get("date") != DATE:
            raise ValueError("Completion policy/date mismatch: " + p)
        if completed[p].get("validation_scope") != "REALIZED_OPERATION_AC":
            raise ValueError("Not Actual AC: " + p)
        if summaries[p].get("validation_scope") != "REALIZED_OPERATION_AC":
            raise ValueError("Summary scope mismatch: " + p)
        if summaries[p].get("converged_slots") != SLOTS or summaries[p].get("controls_settled_slots") != SLOTS:
            raise ValueError("Incomplete summary slots: " + p)
        slots = [row["slot"] for row in extrema[p]]
        if slots != list(range(SLOTS)):
            raise ValueError("Incomplete/duplicate extrema slots: " + p)

    labels = axes["B0"]["line"]
    ratings = np.asarray(axes["B0"]["line_rating_A"], dtype=np.float64)
    line_ids, grouped, topo, rating_variation = parse_axes(labels, ratings)
    nlines = len(line_ids)
    for row in topo:
        a = coords["B0"].get(row["from_bus"].lower())
        b = coords["B0"].get(row["to_bus"].lower())
        row.update(x_from=a[0] if a else "", y_from=a[1] if a else "", x_to=b[0] if b else "", y_to=b[1] if b else "")
    coordinate_coverage = sum(all(row[k] != "" for k in ("x_from", "y_from", "x_to", "y_to")) for row in topo)
    endpoint_coordinate_count = sum(row[k] != "" for row in topo for k in ("x_from", "x_to"))

    loading = {}
    for p in ("B0", "B3"):
        name = ACTUAL[p] + "/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz"
        with np.load(io.BytesIO(source(selected, name)), allow_pickle=False) as z:
            if list(z["line_phase_axes"]) != labels:
                raise ValueError("NPZ/AXES line labels mismatch: " + p)
            raw = z["line_current_loading_pu"].copy()
        if raw.shape != (SLOTS, len(labels)):
            raise ValueError("Unexpected line loading shape: " + p)
        if not np.isfinite(raw).all() or (raw < 0).any():
            raise ValueError("Nonfinite/negative active loading: " + p)
        loading[p] = raw

    perline, argaxis = {}, {}
    for p in ("B0", "B3"):
        perline[p] = np.empty((SLOTS, nlines), dtype=np.float64)
        argaxis[p] = np.empty((SLOTS, nlines), dtype=np.int32)
        for j, element in enumerate(line_ids):
            axes_j = np.asarray(grouped[element], dtype=np.int32)
            local = np.argmax(loading[p][:, axes_j], axis=1)
            chosen = axes_j[local]
            argaxis[p][:, j] = chosen
            perline[p][:, j] = loading[p][np.arange(SLOTS), chosen]

    system = {}
    source_diff = {}
    extrema_diff = {}
    witness_mismatches = {}
    for p in ("B0", "B3"):
        line_index = np.argmax(perline[p], axis=1)
        slot_values = perline[p][np.arange(SLOTS), line_index]
        system[p] = (line_index, slot_values)
        official = float(summaries[p]["max_phase_line_loading_pu"])
        source_diff[p] = abs(float(slot_values.max()) - official)
        extrema_diff[p] = max(abs(float(slot_values[t]) - float(extrema[p][t]["max_phase_line_loading_pu"])) for t in range(SLOTS))
        witness_mismatches[p] = sum(labels[int(argaxis[p][t, line_index[t]])] != extrema[p][t]["line_witness"] for t in range(SLOTS))
        if source_diff[p] > 1e-8 or extrema_diff[p] > 1e-8:
            raise ValueError("Official summary/extrema mismatch: " + p)

    audit_columns = ["policy", "scope", "artifact_role", "archive_member_path", "sha256_if_available", "bytes", "used_for_final_extraction"]
    csv_file(OUTPUT / NAMES[0], audit_columns, (dict(zip(audit_columns, row)) for row in members))

    long_columns = ["policy", "slot", "timestamp", "element_id", "element_type", "from_bus", "to_bus", "element_status", "loading_pu", "critical_phase", "critical_terminal", "current_A", "rating_A", "x_from", "y_from", "x_to", "y_to"]
    def long_rows():
        for p in ("B0", "B3"):
            for t in range(SLOTS):
                for j, base in enumerate(topo):
                    axis = int(argaxis[p][t, j])
                    _, terminal, _, node = labels[axis].split("|")
                    rho = float(perline[p][t, j])
                    row = dict(base)
                    row.update(policy=p, slot=t, timestamp=iso_slot(t), loading_pu=rho, critical_phase=node[-1], critical_terminal=terminal, current_A=rho * ratings[axis], rating_A=ratings[axis])
                    yield row
    csv_file(OUTPUT / NAMES[1], long_columns, long_rows())

    topo_columns = ["element_id", "element_type", "element_status", "from_bus", "to_bus", "phases_available", "rating_A", "x_from", "y_from", "x_to", "y_to", "num_phases", "is_switch", "is_disabled"]
    csv_file(OUTPUT / NAMES[2], topo_columns, topo)

    system_columns = ["slot", "timestamp", "B0_system_rho_max", "B0_critical_line", "B0_critical_phase", "B0_critical_terminal", "B3_system_rho_max", "B3_critical_line", "B3_critical_phase", "B3_critical_terminal", "B0_minus_B3"]
    system_rows = []
    for t in range(SLOTS):
        row = {"slot": t, "timestamp": iso_slot(t)}
        for p in ("B0", "B3"):
            j = int(system[p][0][t]); a = int(argaxis[p][t, j]); _, terminal, _, node = labels[a].split("|")
            row.update({p + "_system_rho_max": float(system[p][1][t]), p + "_critical_line": line_ids[j], p + "_critical_phase": node[-1], p + "_critical_terminal": terminal})
        row["B0_minus_B3"] = row["B0_system_rho_max"] - row["B3_system_rho_max"]
        system_rows.append(row)
    csv_file(OUTPUT / NAMES[3], system_columns, system_rows)

    peak_slot = {p: np.argmax(perline[p], axis=0) for p in ("B0", "B3")}
    peak_value = {p: perline[p][peak_slot[p], np.arange(nlines)] for p in ("B0", "B3")}
    daily_columns = ["element_id", "from_bus", "to_bus", "x_from", "y_from", "x_to", "y_to"]
    for p in ("B0", "B3"):
        daily_columns += [p + "_daily_max_loading", p + "_daily_max_slot", p + "_daily_max_timestamp", p + "_daily_max_phase", p + "_daily_max_terminal"]
    daily_columns += ["B0_minus_B3_daily_max", "relative_reduction_pct_if_defined"]
    daily_rows = []
    for j, base in enumerate(topo):
        row = dict(base)
        for p in ("B0", "B3"):
            t = int(peak_slot[p][j]); a = int(argaxis[p][t, j]); _, terminal, _, node = labels[a].split("|")
            row.update({p + "_daily_max_loading": float(peak_value[p][j]), p + "_daily_max_slot": t, p + "_daily_max_timestamp": iso_slot(t), p + "_daily_max_phase": node[-1], p + "_daily_max_terminal": terminal})
        diff = row["B0_daily_max_loading"] - row["B3_daily_max_loading"]
        row["B0_minus_B3_daily_max"] = diff
        row["relative_reduction_pct_if_defined"] = 100 * diff / row["B0_daily_max_loading"] if row["B0_daily_max_loading"] > 0 else ""
        daily_rows.append(row)
    csv_file(OUTPUT / NAMES[4], daily_columns, daily_rows)

    ranked_slots = sorted(range(SLOTS), key=lambda t: (-float(system["B0"][1][t]), t))
    rank_columns = ["rank", "slot", "timestamp", "B0_system_rho_max", "B3_system_rho_max", "B0_minus_B3"]
    csv_file(OUTPUT / NAMES[5], rank_columns, (dict(system_rows[t], rank=rank) for rank, t in enumerate(ranked_slots, 1)))

    base_cols = ["element_id", "from_bus", "to_bus", "x_from", "y_from", "x_to", "y_to"]
    window_columns = base_cols.copy()
    window_means = {}
    for k in (4, 8, 12, 16):
        window_columns += [f"B0_top{k}_mean", f"B3_top{k}_mean", f"B0_minus_B3_top{k}_mean"]
        slots = ranked_slots[:k]
        window_means[k] = {p: perline[p][slots, :].mean(axis=0) for p in ("B0", "B3")}
    window_rows = []
    for j, base in enumerate(topo):
        row = dict(base)
        for k in (4, 8, 12, 16):
            b0, b3 = float(window_means[k]["B0"][j]), float(window_means[k]["B3"][j])
            row.update({f"B0_top{k}_mean": b0, f"B3_top{k}_mean": b3, f"B0_minus_B3_top{k}_mean": b0 - b3})
        window_rows.append(row)
    csv_file(OUTPUT / NAMES[6], window_columns, window_rows)

    duration_columns = base_cols.copy()
    thresholds = (("0p40", 0.40), ("0p50", 0.50), ("0p60", 0.60), ("0p70", 0.70), ("0p80", 0.80))
    for token, _ in thresholds:
        duration_columns += [f"B0_slots_ge_{token}", f"B3_slots_ge_{token}", f"B0_hours_ge_{token}", f"B3_hours_ge_{token}", f"B0_minus_B3_hours_ge_{token}"]
    duration_count = {(p, token): (perline[p] >= threshold).sum(axis=0) for p in ("B0", "B3") for token, threshold in thresholds}
    duration_rows = []
    for j, base in enumerate(topo):
        row = dict(base)
        for token, _ in thresholds:
            b0, b3 = int(duration_count["B0", token][j]), int(duration_count["B3", token][j])
            row.update({f"B0_slots_ge_{token}": b0, f"B3_slots_ge_{token}": b3, f"B0_hours_ge_{token}": b0 * 0.25, f"B3_hours_ge_{token}": b3 * 0.25, f"B0_minus_B3_hours_ge_{token}": (b0 - b3) * 0.25})
        duration_rows.append(row)
    csv_file(OUTPUT / NAMES[7], duration_columns, duration_rows)

    master_references = {p: source(selected, ROOTS[p] + "/PCC_Master.dss").decode("utf-8", errors="replace") for p in ("B0", "B3")}
    missing_base_master = all("Master-unbal.dss" in value for value in master_references.values()) and not any(name.endswith("/Master-unbal.dss") for name in member_names)
    summary_data = {}
    for p in ("B0", "B3"):
        t = int(np.argmax(system[p][1])); j = int(system[p][0][t]); a = int(argaxis[p][t, j]); _, terminal, _, node = labels[a].split("|")
        summary_data[p] = dict(daily_rho_max=float(system[p][1][t]), critical_slot=t, critical_timestamp=iso_slot(t), critical_line=line_ids[j], critical_phase=node[-1], critical_terminal=terminal)
    status = "PASS" if coordinate_coverage == nlines and not missing_base_master else "PARTIAL"
    checks = {
        "source_summary_abs_diff": source_diff,
        "slot_extrema_max_abs_diff": extrema_diff,
        "slot_witness_mismatches": witness_mismatches,
        "slot_completeness": True,
        "topology_axes_identical": True,
        "rating_axes_identical": True,
        "active_loading_finite_and_nonnegative": True,
        "duplicate_policy_slot_element_rows": 0,
        "from_to_bus_missing": 0,
        "coordinate_complete_lines": coordinate_coverage,
        "coordinate_incomplete_lines": nlines - coordinate_coverage,
        "coordinate_endpoint_count": endpoint_coordinate_count,
        "coordinate_possible_endpoint_count": 2 * nlines,
        "rating_variation_within_line_count": rating_variation,
        "disabled_line_count": None,
        "disabled_inventory_available": False,
        "raw_current_ampere_array_available": False,
        "timestamps_authoritative_in_source": False,
    }
    audit_text = f"""# IEEE8500 May 1 B0/B3 extraction audit

Status: **{status}**. Electrical line loading and all 96-slot aggregates were materialized from the specified raw archive. Base feeder coordinates and disabled-line inventory are absent from that archive. Blank coordinates and an unknown disabled count are preserved. No inferred coordinates or disabled loading zeros were added.

## Source authority

- B0: `{ACTUAL['B0']}/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz`; summary and slot extrema in the same folder; `{B0_ROOT}/AXES.json`.
- B3: `{ACTUAL['B3']}/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz`; summary and slot extrema in the same folder; `{B3_ROOT}/AXES.json`.
- Both COMPLETE and AC_SUMMARY files state `REALIZED_OPERATION_AC`, 2025-05-01 and 96 converged/settled slots. B3 is the archived accepted energy-floor-exception Actual branch.
- The NPZ `line_current_loading_pu` values are absolute normalized conductor loading. `AXES.json` supplies exact axis ordering and `line_rating_A` for each conductor/terminal axis. The original engine code stores complex current divided by `line_rating`; the NPZ stores its magnitude. For every line-slot, the maximum across its valid terminal/phase axes is retained without clipping.
- `current_A` is reconstructed as selected normalized loading × selected axis rating. There is no independent current-ampere array in the selected NPZ, so current/rating is an algebraic check, not an independent raw-current check.
- `critical_phase` is OpenDSS node number 1, 2 or 3; `critical_terminal` is `t1` or `t2`. From/to buses are the archived t1/t2 axis bus names with numeric node suffixes stripped. Physical-line order follows first occurrence in AXES.
- The only archived coordinate files are the two identical 36-bus `PCC_BusCoordinates.dss` overlays. Their source x/y values are used unchanged, with no reflection. The `PCC_Master.dss` files reference an external `Master-unbal.dss` which is absent from the raw tar.gz. Neither external source nor prior derived CSV was used.
- Timestamp text is generated as May 1 local 00:00 plus 15 minutes per slot from the task's 96-slot resolution and archived date/slot indices. The selected archive files do not encode a timestamp or timezone series.

## Counts and checks

- Archive members scanned: {member_count}; active line elements represented in AXES: {nlines}; conductor/terminal axes: {len(labels)}.
- Disabled line elements: unknown; their inventory is unavailable in this archive. `is_switch` is also unavailable.
- B0/B3 long rows: {SLOTS*nlines} each. Slots are exactly 0–95 with no duplicates; both policies use identical line labels and per-axis ampere ratings.
- Lines with both endpoint coordinates: {coordinate_coverage}/{nlines}; endpoint coordinate fields present: {endpoint_coordinate_count}/{2*nlines}. Missing coordinates remain blank.
- Lines with phase/terminal rating variation: {rating_variation}; topology `rating_A` is blank for such lines while long CSV retains the selected axis rating.
- Source-summary absolute difference: B0 {source_diff['B0']:.17g}; B3 {source_diff['B3']:.17g}. Gate: ≤1e-8.
- Per-slot extrema maximum absolute difference: B0 {extrema_diff['B0']:.17g}; B3 {extrema_diff['B3']:.17g}. Witness label mismatches from tie/ordering: B0 {witness_mismatches['B0']}; B3 {witness_mismatches['B3']}.
- Active loading is finite and nonnegative. Ratings are positive. All observed line axes have valid t1/t2 and node 1–3 labels; all observed lines have from/to buses. Duplicate policy-slot-line rows: 0 by unique line-axis grouping and complete slot loops.
- Top-K means use the same B0-ranked slots for both policies. Duration thresholds use inclusive ≥ comparisons and 0.25 hour per slot. Daily maxima are selected independently per line and policy. Signed B0 minus B3 values are retained.

Scientific execution count: **0**. Git modification count: **0** (script and outputs are outside repositories).
"""
    (OUTPUT / NAMES[8]).write_text(audit_text, encoding="utf-8")
    manifest = {
        "status": status, "raw_archive": str(ARCHIVE), "output_folder": str(OUTPUT), "zip": str(ZIP),
        "date": DATE, "slot_count_per_policy": SLOTS, "slot_minutes": SLOT_MINUTES,
        "scope": "REALIZED_OPERATION_AC/FINAL_ACTUAL", "source_authority": {p: {"arrays": ACTUAL[p] + "/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz", "summary": ACTUAL[p] + "/FINAL_ACTUAL/AC_SUMMARY.json", "slot_extrema": ACTUAL[p] + "/FINAL_ACTUAL/SLOT_EXTREMA.json", "axes_ratings": ROOTS[p] + "/AXES.json", "coordinates": ROOTS[p] + "/PCC_BusCoordinates.dss"} for p in ("B0", "B3")},
        "counts": {"archive_members_scanned": member_count, "active_lines": nlines, "disabled_lines": None, "line_phase_axes": len(labels), "B0_line_slot_rows": SLOTS*nlines, "B3_line_slot_rows": SLOTS*nlines, "coordinate_complete_lines": coordinate_coverage, "coordinate_endpoint_fields_present": endpoint_coordinate_count},
        "system_results": summary_data, "validation": checks,
        "limitations": ["Base feeder coordinates are absent from archive; incomplete x/y fields are blank.", "Disabled-line inventory is absent; disabled count is unknown.", "No independent raw ampere-current array is present; current_A is reconstructed from loading and rating.", "Timestamps are inferred from archived date/slot index and task-stated 15-minute resolution."],
        "scientific_execution_count": 0, "git_modification_count": 0,
        "source_members": [dict(zip(audit_columns, row)) for row in members],
        "output_files": {name: {"bytes": (OUTPUT/name).stat().st_size, "sha256": file_sha(OUTPUT/name)} for name in NAMES if name != NAMES[9] and (OUTPUT/name).exists()},
    }
    (OUTPUT / NAMES[9]).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for name in NAMES:
            z.write(OUTPUT / name, arcname=name)
    print(json.dumps({"status": status, "active_lines": nlines, "coordinate_complete_lines": coordinate_coverage, "B0": summary_data["B0"], "B3": summary_data["B3"], "zip": str(ZIP)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
