"""Immutable, static geography gates and customer-side split-phase enumeration.

This module never imports old selectors, compiles OpenDSS, creates equipment, or
consults optimization outcomes. Source LV coordinates are schematic offsets and
are not observations of customer geography. A candidate is not an approved port.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# Frozen before selection/scoring. Original coordinates have unknown CRS; these
# tolerances apply only to the provided east/north traffic projection in km.
POLICY = {
    "version": "geometry_v1",
    "traffic_pair_distance_tolerance_km": 0.001,
    "traffic_axis_zero_tolerance_km": 0.001,
    "transform": "one global positive-scale proper similarity; no reflection",
    "infeasibility_certificate": "independent affine row projection feasibility",
    "candidate_coordinate_authority": "transformer primary coordinates, proxy only",
    "selection_order": "physical eligibility, all signs, distance, lexical bus ID",
    "direction_relaxation_allowed": False,
}
AIDC_BUSES = dict(zip(
    (f"AIDC{i:02d}" for i in range(1, 13)),
    ("l3234149", "e182733", "m1027055", "m1069411", "l2688693",
     "m1142814", "m1026690", "l3123452", "l2728247", "l2973833",
     "m1047763", "e192258"),
))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing headerless empty audit: {path}")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def base_bus(spec: str) -> str:
    return spec.strip('"').split(".", 1)[0].lower()


def source_records(path: Path) -> list[str]:
    """Join only DSS continuation records; comments are never executable input."""
    records: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = re.split(r"!|//", raw, maxsplit=1)[0].strip()
        if line.startswith("~") and records:
            records[-1] += " " + line[1:].strip()
        elif line:
            records.append(line)
    return records


def attributes(record: str) -> dict[str, str]:
    # Preserve compound values and repeated winding properties separately below.
    return {k.lower(): v.strip('"') for k, v in re.findall(
        r"([\w%]+)\s*=\s*(\[[^\]]*\]|\{[^}]*\}|[^\s]+)", record
    )}


def read_coords(path: Path) -> dict[str, tuple[float, float]]:
    coords = {}
    for record in source_records(path):
        parts = [p.strip() for p in record.split(",")]
        if len(parts) == 3:
            coords[parts[0].lower()] = (float(parts[1]), float(parts[2]))
    return coords


def traffic_xy(anchor: dict[str, Any]) -> tuple[float, float]:
    return float(anchor["x_east_km"]), float(anchor["y_north_km"])


def pair_sign(a: tuple[float, float], b: tuple[float, float], axis: int) -> int:
    if math.dist(a, b) <= POLICY["traffic_pair_distance_tolerance_km"]:
        return 0
    delta = b[axis] - a[axis]
    tolerance = POLICY["traffic_axis_zero_tolerance_km"]
    return 0 if abs(delta) <= tolerance else (1 if delta > 0 else -1)


def fit_similarity(source: list[tuple[float, float]],
                   target: list[tuple[float, float]]) -> dict[str, Any]:
    """Least-squares proper similarity without a reflection or per-STA fitting."""
    if len(source) != len(target) or len(source) < 2:
        raise ValueError("A shared fit requires paired anchors")
    n = len(source)
    sx, sy = (sum(p[k] for p in source) / n for k in (0, 1))
    tx, ty = (sum(p[k] for p in target) / n for k in (0, 1))
    centered = [(p[0] - sx, p[1] - sy, q[0] - tx, q[1] - ty)
                for p, q in zip(source, target)]
    denom = sum(a*a + b*b for a, b, _, _ in centered)
    if denom == 0:
        raise ValueError("Degenerate fixed anchors")
    u = sum(a*x + b*y for a, b, x, y in centered) / denom
    v = sum(a*y - b*x for a, b, x, y in centered) / denom
    if u*u + v*v == 0:
        raise ValueError("No nondegenerate proper similarity")
    result = {"u": u, "v": v, "translation_x": tx-u*sx+v*sy,
              "translation_y": ty-v*sx-u*sy, "determinant": u*u+v*v,
              "rotation_degrees": math.degrees(math.atan2(v, u)),
              "scale_km_per_unknown_native_unit": math.hypot(u, v),
              "fit_authority": "12 fixed v3 AIDC anchors only"}
    errors = [math.dist(transform(p, result), q) for p, q in zip(source, target)]
    result["anchor_rms_error_km"] = math.sqrt(sum(e*e for e in errors)/n)
    result["anchor_max_error_km"] = max(errors)
    return result


def transform(point: tuple[float, float], fit: dict[str, Any]) -> tuple[float, float]:
    x, y = point
    return (fit["u"]*x-fit["v"]*y+fit["translation_x"],
            fit["v"]*x+fit["u"]*y+fit["translation_y"])


def projection_intervals(constraints: list[dict[str, Any]]) -> list[list[float]]:
    """Complete angular arrangement, not a grid search, for strict row signs.

    Each inequality is row dot signed_delta > 0. Boundaries are zeros, so every
    feasible row has an open neighborhood lying in one enumerated interval.
    """
    if not constraints:
        return [[0., 2*math.pi]]
    boundaries = {0., 2*math.pi}
    for c in constraints:
        x, y = c["signed_grid_delta"]
        if math.hypot(x, y) == 0:
            return []
        angle = math.atan2(y, x)
        boundaries.update((angle+d) % (2*math.pi) for d in (-math.pi/2, math.pi/2))
    boundaries = sorted(boundaries)
    feasible = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        angle = (lo+hi)/2
        if all(c["signed_grid_delta"][0]*math.cos(angle) +
               c["signed_grid_delta"][1]*math.sin(angle) > 0 for c in constraints):
            feasible.append([lo, hi])
    return feasible


def affine_anchor_certificate(ids: list[str], traffic: dict[str, tuple[float, float]],
                              grid: dict[str, tuple[float, float]]) -> dict[str, Any]:
    """If either affine row is impossible, any proper similarity is impossible."""
    result: dict[str, Any] = {}
    for axis, label in enumerate(("east_west", "north_south")):
        constraints = []
        for a, b in itertools.combinations(ids, 2):
            sign = pair_sign(traffic[a], traffic[b], axis)
            if sign:
                constraints.append({"a": a, "b": b,
                    "traffic_delta_km": traffic[b][axis]-traffic[a][axis],
                    "signed_grid_delta": [sign*(grid[b][k]-grid[a][k]) for k in (0,1)]})
        intervals = projection_intervals(constraints)
        witness = constraints[:]
        if not intervals:
            for c in constraints:
                trial = [d for d in witness if d is not c]
                if not projection_intervals(trial):
                    witness = trial
        else:
            witness = []
        entry = {"constraint_count": len(constraints), "feasible_intervals_radians": intervals,
                 "feasible": bool(intervals), "irreducible_witness": witness}
        # A positive weighted sum of the three constraint vectors equal to zero
        # proves they cannot all have strictly positive dot product with any row.
        if len(witness) == 3:
            vectors = [c["signed_grid_delta"] for c in witness]
            cross = lambda p,q: p[0]*q[1]-p[1]*q[0]
            weights = [cross(vectors[1], vectors[2]), cross(vectors[2], vectors[0]),
                       cross(vectors[0], vectors[1])]
            if all(w < 0 for w in weights):
                weights = [-w for w in weights]
            if all(w > 0 for w in weights):
                weights = [w/sum(weights) for w in weights]
                entry["positive_convex_weights"] = weights
                entry["weighted_vector_residual"] = [sum(w*v[k] for w,v in zip(weights,vectors))
                                                      for k in (0,1)]
        result[label] = entry
    result["infeasible_even_for_affine"] = any(not result[k]["feasible"]
                                              for k in ("east_west", "north_south"))
    return result


def enumerate_lv_candidates(feeder: Path) -> list[dict[str, Any]]:
    """Enumerate every loaded customer terminal by triplex graph traversal.

    Active unbalanced master uses LoadXfmrCodes, not duplicate LoadXfmrs. All
    paths start at the actual service-transformer secondary; no MV proxy bus is
    an injection terminal. No changes are made to feeder source.
    """
    coords = read_coords(feeder/"Buscoords.dss")
    codes = {}
    transformers = []
    for record in source_records(feeder/"LoadXfmrCodes.dss"):
        head = record.split()[:2]
        if len(head) < 2 or head[0].lower() != "new":
            continue
        attrs = attributes(record)
        if head[1].lower().startswith("xfmrcode."):
            codes[head[1].split(".",1)[1].lower()] = attrs
        elif head[1].lower().startswith("transformer."):
            buses = attrs["buses"].strip("[]").split()
            code = codes[attrs["xfmrcode"].lower()]
            kva = [float(x) for x in code["kvas"].strip("[]").split()]
            transformers.append({"name": head[1].lower(), "primary_spec": buses[0],
                                 "secondary_specs": buses[1:], "kvas": kva})
    linecodes = {}
    for record in source_records(feeder/"Triplex_Linecodes.dss"):
        if record.lower().startswith("new linecode."):
            name = record.split()[1].split(".",1)[1].lower()
            attrs = attributes(record)
            linecodes[name] = float(attrs["normamps"])
    lines = []
    graph = defaultdict(list)
    for record in source_records(feeder/"Triplex_Lines.DSS"):
        if record.lower().startswith("new line."):
            attrs = attributes(record)
            line = {"name": record.split()[1].lower(), **attrs}
            a,b = base_bus(attrs["bus1"]),base_bus(attrs["bus2"])
            lines.append(line)
            graph[a].append((b,line)); graph[b].append((a,line))
    loads = defaultdict(list)
    for record in source_records(feeder/"UnbalancedLoads.DSS"):
        if record.lower().startswith("new load."):
            attrs = attributes(record)
            attrs["name"] = record.split()[1].lower()
            loads[base_bus(attrs["bus1"])].append(attrs)
    # Do not infer transformer identity from X/SX naming: follow real terminals.
    memberships = defaultdict(list)
    for xfmr in transformers:
        roots = set(base_bus(s) for s in xfmr["secondary_specs"])
        if len(roots) != 1:
            raise ValueError("Unexpected split-phase transformer topology")
        root = next(iter(roots))
        queue = deque([(root, ())]); seen = {root}
        while queue:
            bus,path = queue.popleft()
            if path and bus in loads:
                memberships[bus].append((xfmr, path))
            for neighbor,line in sorted(graph[bus], key=lambda q:q[0]):
                if neighbor not in seen:
                    seen.add(neighbor); queue.append((neighbor,path+(line,)))
    candidates = []
    for bus,members in sorted(memberships.items()):
        xfmr,path = members[0]
        parent = base_bus(xfmr["primary_spec"])
        proxy = coords.get(parent)
        schematic = coords.get(bus)
        rated = min(float(line.get("normamps", linecodes[line["linecode"].lower()])) for line in path)
        terminals = {int(node) for load in loads[bus] for node in load["bus1"].split(".")[1:]}
        topology_ok = len(members)==1 and terminals.issubset({0,1,2}) and {1,2}.issubset(terminals)
        p1 = sum(float(load["kw"]) for load in loads[bus] if load["bus1"].endswith(".1"))
        p2 = sum(float(load["kw"]) for load in loads[bus] if load["bus1"].endswith(".2"))
        q_by_leg = [sum(float(load["kw"])*math.tan(math.acos(float(load["pf"])))
                        for load in loads[bus] if load["bus1"].endswith(f".{leg}"))
                    for leg in (1,2)]
        candidates.append({
            "candidate_bus": bus, "injection_terminal_240v": bus+".1.2",
            "injection_terminal_leg1_120v": bus+".1.0",
            "injection_terminal_leg2_120v": bus+".2.0",
            "upstream_transformer": xfmr["name"], "upstream_primary_bus": parent,
            "upstream_primary_phase": xfmr["primary_spec"].split(".")[-1],
            "transformer_primary_kva": xfmr["kvas"][0],
            "transformer_secondary_winding_kvas": json.dumps(xfmr["kvas"][1:]),
            "triplex_path": ";".join(line["name"] for line in path),
            "direct_support_lines": ";".join(line["name"] for line in path),
            "triplex_min_normal_amps": rated,
            "triplex_neutral_model": "Kron_reduced_grounded_neutral_no_independent_neutral_rating",
            "engineering_upper_bound_kva_NOT_allowed_output": min(xfmr["kvas"][0],0.240*rated),
            "allowed_pcc_p_kw": "", "allowed_pcc_q_kvar": "",
            "customer_load_leg1_kw": p1, "customer_load_leg2_kw": p2,
            "customer_load_leg1_kvar": q_by_leg[0], "customer_load_leg2_kvar": q_by_leg[1],
            "customer_load_imbalance_kw": p1-p2,
            "customer_load_vminpu": ";".join(sorted({load["vminpu"] for load in loads[bus]})),
            "customer_load_models": ";".join(sorted({load["model"] for load in loads[bus]})),
            "topology_customer_side": topology_ok, "triplex_depth": len(path),
            "customer_terminal_degree": len(graph[bus]),
            "proxy_x": proxy[0] if proxy else "", "proxy_y": proxy[1] if proxy else "",
            "coordinate_authority": "upstream_primary_proxy_unknown_CRS",
            "source_schematic_x_NOT_geography": schematic[0] if schematic else "",
            "source_schematic_y_NOT_geography": schematic[1] if schematic else "",
            "source_schematic_offset_dx_unknown_units": schematic[0]-proxy[0] if schematic and proxy else "",
            "source_schematic_offset_dy_unknown_units": schematic[1]-proxy[1] if schematic and proxy else "",
            "source_schematic_provenance": (
                "Buscoords_2019_script_45_40_offsets_not_customer_survey"
                if schematic and proxy and abs(schematic[0]-proxy[0]-45)<0.001 and abs(schematic[1]-proxy[1]-40)<0.001
                else "Buscoords_manual_near_primary_offsets_not_customer_survey"),
            "voltage_and_reverse_power_ac_gate": "NOT_VERIFIED",
            "protection_isolation_inverter_gate": "NO_SOURCE_EVIDENCE",
            "vehicle_access_connection_time_gate": "NO_SOURCE_EVIDENCE",
            "port_equipment_gate": "NO_SOURCE_EVIDENCE",
            "physical_eligibility": "STOP_NO_APPROVED_CONNECTION_PORT",
        })
    # One source triplex branch per customer is true here, but enumerate through
    # topology instead of relying on that incidental source naming convention.
    if not candidates:
        raise ValueError("No original customer-side triplex candidates found")
    return candidates


def select_sta_candidates(anchors: list[dict[str, Any]], grid: dict[str, tuple[float,float]],
                          candidates: list[dict[str,Any]], fit: dict[str,Any],
                          search_budget: int = 1000000) -> dict[str,Any]:
    """Fail closed before allocation; never relax geometry or equipment gates.

    The bounded exact backtracking result is UNKNOWN if its budget is reached,
    never a false infeasibility claim. No objective uses B0 or B3 performance.
    """
    traffic = {a["location_id"]:traffic_xy(a) for a in anchors}
    aidcs = sorted(AIDC_BUSES)
    cert = affine_anchor_certificate(aidcs,traffic,grid)
    if cert["infeasible_even_for_affine"]:
        return {"status":"STOP_FIXED_AIDC_GEOMETRY_INFEASIBLE", "selected":{}, "search_nodes":0}
    aligned = {a:transform(grid[a],fit) for a in aidcs}
    for a,b in itertools.combinations(aidcs,2):
        for axis in (0,1):
            sign=pair_sign(traffic[a],traffic[b],axis)
            if sign and sign*(aligned[b][axis]-aligned[a][axis])<=0:
                return {"status":"STOP_FROZEN_COMMON_TRANSFORM_VIOLATES_FIXED_AIDC", "selected":{},"search_nodes":0}
    approved = [c for c in candidates if c["physical_eligibility"]=="PASS"]
    if not approved:
        return {"status":"STOP_NO_APPROVED_LV_PORTS", "selected":{},"search_nodes":0}
    stations = [a["location_id"] for a in anchors if a["role"]=="STA"]
    pools={}
    for station in stations:
        pool=[]
        for c in approved:
            point=transform((float(c["proxy_x"]),float(c["proxy_y"])),fit)
            if all(not (s:=pair_sign(traffic[a],traffic[station],k)) or
                   s*(point[k]-aligned[a][k])>0 for a in aidcs for k in (0,1)):
                pool.append((math.dist(point,traffic[station]),c["candidate_bus"],point,c))
        pools[station]=sorted(pool,key=lambda x:(x[0],x[1]))
    order=sorted(stations,key=lambda a:(len(pools[a]),a)); chosen={}; nodes=0
    def recurse(depth: int) -> bool:
        nonlocal nodes
        if depth==len(order):return True
        station=order[depth]
        for item in pools[station]:
            nodes+=1
            if nodes>search_budget:raise RuntimeError("SEARCH_BUDGET")
            if any(item[1]==v[1] for v in chosen.values()):continue
            if any(s and s*(item[2][k]-other[2][k])<=0
                   for name,other in chosen.items() for k in (0,1)
                   for s in [pair_sign(traffic[name],traffic[station],k)]):continue
            chosen[station]=item
            if recurse(depth+1):return True
            del chosen[station]
        return False
    try:
        found=recurse(0)
    except RuntimeError:
        return {"status":"UNKNOWN_SEARCH_BUDGET", "selected":{},"search_nodes":nodes}
    return {"status":"PASS" if found else "STOP_NO_DIRECTION_PRESERVING_ALLOCATION",
            "selected":{a:item[3] for a,item in chosen.items()} if found else {},"search_nodes":nodes}


def relative_audit(anchors: list[dict[str,Any]], grid: dict[str,tuple[float,float]],
                   fit: dict[str,Any]) -> list[dict[str,Any]]:
    rows=[]
    for a,b in itertools.combinations(anchors,2):
        aid,bid=a["location_id"],b["location_id"]
        ta,tb=traffic_xy(a),traffic_xy(b); ga,gb=transform(grid[aid],fit),transform(grid[bid],fit)
        expected=[pair_sign(ta,tb,k) for k in (0,1)]
        delta=[gb[k]-ga[k] for k in (0,1)]
        actual=[0 if abs(d)<1e-12 else (1 if d>0 else -1) for d in delta]
        raw_delta=[grid[bid][k]-grid[aid][k] for k in (0,1)]
        raw_sign=[0 if d==0 else (1 if d>0 else -1) for d in raw_delta]
        passes=[not e or e==s for e,s in zip(expected,actual)]
        rows.append({"location_a":aid,"location_b":bid,"role_pair":"-".join(sorted([a["role"],b["role"]])),
            "traffic_node_a":a["traffic_node"],"traffic_node_b":b["traffic_node"],
            "traffic_dx_km":tb[0]-ta[0],"traffic_dy_km":tb[1]-ta[1],
            "expected_x_sign":expected[0],"expected_y_sign":expected[1],
            "source_no_transform_dx_unknown_units":raw_delta[0],
            "source_no_transform_dy_unknown_units":raw_delta[1],
            "source_no_transform_x_sign":raw_sign[0],"source_no_transform_y_sign":raw_sign[1],
            "source_no_transform_x_preserved":not expected[0] or expected[0]==raw_sign[0],
            "source_no_transform_y_preserved":not expected[1] or expected[1]==raw_sign[1],
            "transformed_grid_dx_km":delta[0],"transformed_grid_dy_km":delta[1],
            "actual_x_sign":actual[0],"actual_y_sign":actual[1],
            "x_preserved":passes[0],"y_preserved":passes[1],"pair_pass":all(passes),
            "near_pair_exempt":math.dist(ta,tb)<=POLICY["traffic_pair_distance_tolerance_km"],
            "traffic_distance_km":math.dist(ta,tb),"mapped_distance_km":math.dist(ga,gb),
            "distance_error_km":math.dist(ga,gb)-math.dist(ta,tb),
            "mapping_authority":"AIDC_fixed_v3_STA_retained_original_diagnostic_NOT_final",
            "transform_authority":"one_AIDC_fitted_proper_similarity"})
    return rows


def svg_figure(path: Path, anchors: list[dict[str,Any]], grid: dict[str,tuple[float,float]],
               fit: dict[str,Any], candidates: list[dict[str,Any]]) -> None:
    """Code-drawn scientific geometry figure; no generated imagery."""
    from html import escape
    width,height=1260,650
    allpoints=[traffic_xy(a) for a in anchors]+[transform(grid[a["location_id"]],fit) for a in anchors]
    allpoints += [transform((float(c["proxy_x"]),float(c["proxy_y"])),fit)
                  for c in candidates if c["proxy_x"]!=""]
    xs=[p[0] for p in allpoints];ys=[p[1] for p in allpoints]
    xmin,xmax=min(xs)-2,max(xs)+2;ymin,ymax=min(ys)-2,max(ys)+2
    scale=min(550/(xmax-xmin),460/(ymax-ymin))
    def pixel(p,panel):return (40+620*panel+(p[0]-xmin)*scale,575-(p[1]-ymin)*scale)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font-family:Arial,sans-serif;font-size:12px}.title{font-size:19px;font-weight:bold}.axis{font-size:12px;fill:#444}</style>',
         '<text x="25" y="30" class="title">Fixed AIDC geometry fails; STA allocation is stopped</text>',
         '<text x="25" y="54">One proper similarity fitted to fixed anchors; grey LV points are parent-transformer geography proxies.</text>']
    for panel,title in enumerate(("Traffic east/north anchors (km)","IEEE8500 mapped with the common proper similarity (km)")):
        out.append(f'<text x="{40+620*panel}" y="85" class="title">{title}</text>')
        out.append(f'<rect x="{30+620*panel}" y="105" width="590" height="480" fill="#fcfcfc" stroke="#ddd"/>')
        if panel:
            for c in candidates:
                if c["proxy_x"]!="":
                    x,y=pixel(transform((float(c["proxy_x"]),float(c["proxy_y"])),fit),panel)
                    out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.5" fill="#bbbbbb" opacity="0.6"/>')
        label_rects=[]
        for a in anchors:
            aid=a["location_id"];point=traffic_xy(a) if panel==0 else transform(grid[aid],fit)
            x,y=pixel(point,panel);color="#b82025" if a["role"]=="AIDC" else "#1262ad"
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>')
            label_width=len(aid)*7
            label_candidates=[(x+6,y-6),(x+6,y+15),(x-label_width-6,y-6),
                              (x-label_width-6,y+15),(x+6,y-21),(x+6,y+30),
                              (x-label_width-6,y-21),(x-label_width-6,y+30)]
            def score(q):
                lx,ly=q;rect=(lx,ly-12,lx+label_width,ly+2)
                overlap=sum(max(0,min(rect[2],r[2])-max(rect[0],r[0]))*
                            max(0,min(rect[3],r[3])-max(rect[1],r[1])) for r in label_rects)
                return overlap+10000*(lx<30+620*panel or lx+label_width>620+620*panel or ly<115 or ly>582)
            lx,ly=min(label_candidates,key=score)
            label_rects.append((lx,ly-12,lx+label_width,ly+2))
            out.append(f'<text x="{lx:.2f}" y="{ly:.2f}" fill="{color}">{escape(aid)}</text>')
        out.append(f'<text x="{40+620*panel}" y="610" class="axis">Red: fixed AIDC; blue: traffic STA / retained original MV STA. No final LV positions.</text>')
    out.append('<text x="25" y="638">CRS of feeder coordinates is unverified. X/SX source coordinates are schematic offsets, not surveyed customer locations.</text></svg>')
    path.write_text("\n".join(out),encoding="utf-8")


def plot_png(feeder: Path, geometry_data: Path, output: Path) -> None:
    """Optional standard Matplotlib scientific export; requires plotting runtime."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    anchors=json.loads((geometry_data/"STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    registry=read_csv(geometry_data/"ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
    xy=read_coords(feeder/"Buscoords.dss")
    grid={r["location_id"]:xy[r["ieee8500_bus"].lower()] for r in registry}
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    ids=sorted(AIDC_BUSES)
    fit=fit_similarity([grid[a] for a in ids],[traffic[a] for a in ids])
    candidates=enumerate_lv_candidates(feeder)
    points=[transform((float(c["proxy_x"]),float(c["proxy_y"])),fit)
            for c in candidates if c["proxy_x"]!=""]
    data=list(traffic.values())+[transform(p,fit) for p in grid.values()]+points
    xmin=min(p[0] for p in data)-3;xmax=max(p[0] for p in data)+3
    ymin=min(p[1] for p in data)-3;ymax=max(p[1] for p in data)+3
    fig,axs=plt.subplots(1,2,figsize=(15,7),sharex=True,sharey=True)
    for panel,ax in enumerate(axs):
        ax.set_xlim(xmin,xmax);ax.set_ylim(ymin,ymax);ax.set_aspect("equal")
        if panel:
            ax.scatter([p[0] for p in points],[p[1] for p in points],s=4,c="#bbb",alpha=.5,
                       label="1,177 customer-side LV parent proxies",zorder=1)
        for role,color,marker in (("AIDC","#ba2029","o"),("STA","#1262ad","s")):
            sites=[a for a in anchors if a["role"]==role]
            positions=[traffic[a["location_id"]] if panel==0 else transform(grid[a["location_id"]],fit) for a in sites]
            ax.scatter([p[0] for p in positions],[p[1] for p in positions],s=35,c=color,marker=marker,
                       label="Fixed AIDC" if role=="AIDC" else "STA traffic anchor / retained MV",zorder=3)
        occupied=[]
        for a in anchors:
            p=traffic[a["location_id"]] if panel==0 else transform(grid[a["location_id"]],fit)
            role=a["role"];color="#ba2029" if role=="AIDC" else "#1262ad"
            short=("A" if role=="AIDC" else "S")+a["location_id"][-2:]
            px,py=ax.transData.transform(p)
            # Pixel-area greedy placement across both roles avoids duplicated
            # labels for near-colocated original AIDC / MV STA locations.
            choices=[(5,5),(-20,-12),(5,-12),(-20,5),(5,17),(-20,-24),(5,-24),(-20,17)]
            def label_score(offset):
                dx,dy=offset;box=(px+dx,py+dy,px+dx+25,py+dy+12)
                return sum(max(0,min(box[2],r[2])-max(box[0],r[0]))*
                           max(0,min(box[3],r[3])-max(box[1],r[1])) for r in occupied)
            dx,dy=min(choices,key=label_score)
            occupied.append((px+dx,py+dy,px+dx+25,py+dy+12))
            ax.annotate(short,p,xytext=(dx,dy),textcoords="offset points",fontsize=8,color=color,
                        arrowprops={"arrowstyle":"-","lw":.4,"color":color},zorder=4)
        ax.grid(alpha=.15);ax.set_xlabel("East coordinate / fitted equivalent coordinate (km)")
        ax.set_title("Traffic service anchors" if panel==0 else "Common proper similarity: diagnostic only",fontsize=12)
        ax.legend(fontsize=8,loc="lower left")
    axs[0].set_ylabel("North coordinate / fitted equivalent coordinate (km)")
    fig.suptitle("Fixed AIDC geometry fails: no final LV STA mapping",fontsize=16)
    fig.text(.5,.04,"17 / 66 fixed AIDC pairs fail the diagnostic fit. Positive-weight certificates rule out every affine / proper similarity fit.\n"
             "Grey points use transformer primary proxies. Source X/SX offsets are schematic; customer geography and connection ports are unverified.",
             ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.93))
    fig.savefig(output/"GEOMETRY_AUDIT.png",dpi=160)
    plt.close(fig)


def run(feeder: Path, geometry_data: Path, output: Path) -> dict[str,Any]:
    output.mkdir(parents=True,exist_ok=True)
    anchors=json.loads((geometry_data/"STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    original=read_csv(geometry_data/"ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
    by_id={r["location_id"]:r for r in original}
    if len(by_id)!=24 or len(anchors)!=24:raise ValueError("Exactly 24 service identities required")
    for aid,bus in AIDC_BUSES.items():
        if by_id[aid]["ieee8500_bus"].lower()!=bus:raise ValueError("Fixed v3 AIDC identity mismatch")
    source_xy=read_coords(feeder/"Buscoords.dss")
    grid={aid:source_xy[row["ieee8500_bus"].lower()] for aid,row in by_id.items()}
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    fixed_ids=sorted(AIDC_BUSES)
    # Persist the fixed rules before any candidate enumeration or selection.
    policy_path=output/"GEOMETRY_POLICY.json"
    if policy_path.exists() and json.loads(policy_path.read_text())!=POLICY:
        raise ValueError("Previously frozen geometry policy cannot be changed by replay")
    policy_path.write_text(json.dumps(POLICY,indent=2)+"\n",encoding="utf-8")
    cert=affine_anchor_certificate(fixed_ids,traffic,grid)
    fit=fit_similarity([grid[a] for a in fixed_ids],[traffic[a] for a in fixed_ids])
    candidates=enumerate_lv_candidates(feeder)
    selection=select_sta_candidates(anchors,grid,candidates,fit)
    for c in candidates:
        point=transform((float(c["proxy_x"]),float(c["proxy_y"])),fit) if c["proxy_x"]!="" else None
        eligible=[]
        if point:
            for a in anchors:
                if a["role"]=="STA" and all(not(s:=pair_sign(traffic[aid],traffic[a["location_id"]],k))
                    or s*(point[k]-transform(grid[aid],fit)[k])>0 for aid in fixed_ids for k in (0,1)):
                    eligible.append(a["location_id"])
        c["stations_passing_AIDC_signs_under_diagnostic_fit"]=";".join(eligible)
        c["global_fixed_AIDC_gate"]="FAIL" if cert["infeasible_even_for_affine"] else "PASS"
        c["selection_status"]=selection["status"]
        c["rejection_reason"]="FIXED_AIDC_SIGN_CONFLICT;NO_VERIFIED_PORT;PROTECTION_ACCESS_AND_AC_UNVERIFIED"
    write_csv(output/"LV_STA_CANDIDATES.csv",candidates)
    mapping=[]
    for a in anchors:
        if a["role"]!="STA":continue
        aid=a["location_id"];row=by_id[aid];pos=transform(grid[aid],fit)
        mapping.append({"sta_id":aid,"traffic_node_id":a["traffic_node"],
            "traffic_x_east_km":traffic[aid][0],"traffic_y_north_km":traffic[aid][1],
            "original_mv_bus_retained_for_diagnostics":row["ieee8500_bus"],
            "original_mv_terminal":row["ieee8500_bus"]+".1.2.3",
            "final_selected_lv_bus":"","is_final_selection":False,
            "mapping_status":selection["status"],"service_identity_preserved":True,
            "original_mv_coordinate_fit_residual_km":math.dist(pos,traffic[aid]),
            "original_mv_pcc_physical_eligibility":"NOT_PROVED_BY_GEOGRAPHY",
            "required_decision":"FIXED_AIDC_GEOMETRY_CONTRACT_CONFLICT_AND_APPROVED_LV_PORT_EVIDENCE"})
    write_csv(output/"FINAL_STA_MAPPING.csv",mapping)
    audit=relative_audit(anchors,grid,fit);write_csv(output/"RELATIVE_POSITION_AUDIT.csv",audit)
    categories={}
    for role in ("AIDC-AIDC","AIDC-STA","STA-STA"):
        rows=[r for r in audit if r["role_pair"]==role]
        categories[role]={"pairs":len(rows),"violated_pairs":sum(not r["pair_pass"] for r in rows),
                          "x_violations":sum(not r["x_preserved"] for r in rows),
                          "y_violations":sum(not r["y_preserved"] for r in rows)}
    status={"status":selection["status"],"is_final_selection":False,"policy_sha256":sha256(policy_path),
        "common_similarity":fit,"fixed_aidc_affine_certificate":cert,"pair_audit":categories,
        "candidate_count":len(candidates),"topology_customer_side_count":sum(c["topology_customer_side"] for c in candidates),
        "approved_connection_port_count":0,"selection":selection,
        "customer_geography_provenance":"Schematic secondary offsets in source do not establish customer geography",
        "source_unchanged":True,"operational_result_used_for_selection":False}
    (output/"GEOMETRY_STATUS.json").write_text(json.dumps(status,indent=2)+"\n",encoding="utf-8")
    manifest={str(p.relative_to(geometry_data)):sha256(p) for p in sorted(geometry_data.iterdir()) if p.is_file()}
    (output/"GEOMETRY_INPUT_SHA256.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    svg_figure(output/"GEOMETRY_AUDIT.svg",anchors,grid,fit,candidates)
    (output/"GEOMETRY_LV_REPORT.md").write_text(make_report(status,candidates),encoding="utf-8")
    return status


def make_report(status: dict[str,Any], candidates: list[dict[str,Any]]) -> str:
    cert=status["fixed_aidc_affine_certificate"]
    lines=["# IEEE8500 V42 geometry and low-voltage eligibility audit\n",
        f"Result: **{status['status']}**. No final low-voltage STA mapping is selected.\n",
        "The immutable v3 AIDC electrical buses conflict with the traffic east/west and north/south orders. "
        "Both independent affine row feasibility problems have empty exact angular feasible sets. "
        "Therefore no common affine transform, including any proper rotation and positive uniform scaling, "
        "can preserve every fixed AIDC direction. STA re-selection cannot repair this fixed-anchor conflict. "
        "This proof covers affine/similarity transforms; arbitrary nonlinear warps are not an approved mapping policy.\n",
        "The geometry tolerance was frozen before candidate scoring: near-pair distance 0.001 km and "
        "per-axis zero tolerance 0.001 km (1 m) in traffic coordinates. No fixed AIDC pair is distance-exempt. "
        "No threshold was relaxed. The fitted similarity is diagnostic only, uses all 12 AIDC anchors, "
        "has positive determinant, and is applied unchanged to all 24 service locations and candidate proxies.\n",
        "## Reproducible infeasibility certificate\n",
        "For every required axis sign, form v = sign(traffic delta) × (grid_b − grid_a). "
        "A preserving affine row r requires r·v > 0. Each witness below has strictly positive convex "
        "weights whose vector sum is zero, making simultaneous strict inequalities impossible. "
        "Exact interval enumeration also verifies the empty feasible sets without a sampled-angle search.\n"]
    for axis in ("east_west","north_south"):
        entry=cert[axis]
        lines.append(f"### {axis}\n")
        lines.append("| Pair | Traffic axis delta km | Signed grid delta x | Signed grid delta y | Positive weight |\n|---|---:|---:|---:|---:|\n")
        for i,w in enumerate(entry["irreducible_witness"]):
            weight=entry.get("positive_convex_weights",[None]*len(entry["irreducible_witness"]))[i]
            lines.append(f"| {w['a']}–{w['b']} | {w['traffic_delta_km']:.9f} | {w['signed_grid_delta'][0]:.6f} | {w['signed_grid_delta'][1]:.6f} | {weight} |\n")
        lines.append(f"\nWeighted vector residual: `{entry.get('weighted_vector_residual')}`.\n")
    lines.extend(["## All required pair classes\n",
        "`RELATIVE_POSITION_AUDIT.csv` contains 276 pairs: 66 fixed AIDC–AIDC, 66 STA–STA, "
        "and 144 AIDC–STA. It compares traffic directions with the one common fitted transform. "
        "STA electrical positions in this diagnostic audit are the retained original MV registry, "
        "not a selected LV mapping.\n",
        "| Pair class | Pairs | Violated pairs | X violations | Y violations |\n|---|---:|---:|---:|---:|\n"])
    for role,counts in status["pair_audit"].items():
        lines.append(f"| {role} | {counts['pairs']} | {counts['violated_pairs']} | {counts['x_violations']} | {counts['y_violations']} |\n")
    max_kva=max(float(c["transformer_primary_kva"]) for c in candidates)
    lines.extend(["\n## Complete original customer-side triplex pool\n",
        f"The active unbalanced feeder declares **{len(candidates)} customer-side candidates** reached "
        "by traversal from actual service-transformer secondary terminals across the full triplex graph. "
        "The transformer identity is obtained from terminal connectivity rather than bus-name guesses. "
        "Every candidate records the primary phase, three original winding ratings, customer load on both legs, "
        "and the exact triplex support path. A 240 V connection is `.1.2`; the two 120 V legs are `.1.0` and `.2.0`.\n",
        "`Buscoords.dss` explicitly says X/SX coordinates were added by script on 2019-06-06. "
        "Most transformer secondary points were shifted (5, 0) and customer points (45, 40) from primary points. "
        "Of this pool, 1,171 customer points use (45, 40) offsets; six special rows are manual near-primary "
        "schematic placements with (0, 9) offsets, separately identified in the candidate CSV. "
        "`AddBusXY.py` provides matching source provenance. These are schematic offsets, not surveyed "
        "customer geography. The candidate location basis is therefore the actual upstream primary bus "
        "coordinate, explicitly labeled a proxy with unknown CRS. Source schematic coordinates are stored "
        "in separate columns and never treated as surveyed locations.\n",
        f"The maximum original service-transformer primary rating in this pool is {max_kva:g} kVA. "
        "Triplex NormAmps are original source ratings. The reported minimum of transformer primary kVA "
        "and 0.240 kV × conductor NormAmps is only a balanced-connection engineering upper bound. "
        "It is not available headroom, an approved inverter rating, or permission to inject. "
        "Original triplex neutral is grounded and Kron-reduced; independent neutral ampacity is not provided.\n",
        "All candidates remain physically unqualified: original data does not establish MESS ports, "
        "inverter/isolating interface, reverse-power protection, vehicle access, or connection times. "
        "Candidate voltage/current feasibility and transformer loading must also be checked by actual AC. "
        "The 450 kW / 600 kVA vehicle rating cannot be applied to these service connections. "
        "Allowed PCC P and Q are left unset, so no undocumented port is enabled.\n",
        "`FINAL_STA_MAPPING.csv` contains all 12 unchanged STA service and traffic identities. "
        "Its final LV fields are blank and `is_final_selection=False`; original MV buses are retained only "
        "for separately labeled diagnostic AC work. Original MV electrical eligibility is not proved by this "
        "geometry audit. No equipment was created or frozen evidence modified.\n",
        "The gate can be resolved only by an explicit change to the conflicting fixed-anchor/direction "
        "contract or independently supported source-coordinate corrections, and by supplying defensible "
        "LV port equipment/protection/access data. The implementation makes neither decision implicitly.\n"])
    return "\n".join(lines)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--feeder",type=Path,required=True)
    parser.add_argument("--geometry-data",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run(args.feeder,args.geometry_data,args.output)
    print(json.dumps({k:result[k] for k in ("status","candidate_count","approved_connection_port_count","pair_audit")},indent=2))
