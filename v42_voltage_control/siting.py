"""Source-derived PCC topology and a small physical series-SVR candidate set.

The 24 logical sites have 36 distinct existing service endpoints.  Candidate
coverage is the electrical downstream cut, never a promise of whole-day safety.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

from .svr import SCHEMA, _existing_branch, digest, validate_contract

LINE_CANDIDATES = {
    "BUS79": ("Line.l79", "78", "79"),
    "BUS108": ("Line.l105", "105", "108"),
    "BUS48": ("Line.l47", "47", "48"),
    "BUS50": ("Line.l49", "49", "50"),
}


def receipt(path):
    p = Path(path); b = p.read_bytes()
    return dict(path=str(p.resolve()), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def original_inventory(engine, *, source_receipts):
    """Read the compiled original network only; never install or solve."""
    endpoints = []; branches = []
    for name in engine.Transformers.AllNames():
        row = _existing_branch(engine, "Transformer."+name)
        branches.append(row)
        for terminal, spec in enumerate(row["buses"], 1):
            bus = spec.split(".")[0].lower()
            if bus.startswith("mess_sta") and bus.endswith("_pcc"):
                site = bus.removeprefix("mess_").removesuffix("_pcc").upper(); endpoint = "MESS"
            elif bus.startswith("mess_idc") and bus.endswith("_pcc"):
                site = bus.removeprefix("mess_").removesuffix("_pcc").upper(); endpoint = "MESS"
            elif bus.startswith("idc_idc") and bus.endswith("_pcc"):
                site = bus.removeprefix("idc_").removesuffix("_pcc").upper(); endpoint = "AIDC"
            else:
                continue
            engine.Circuit.SetActiveBus(bus)
            endpoints.append(dict(logical_site_id=site, endpoint_id=endpoint, physical_endpoint_id=site+"_"+endpoint,
                pcc_bus=bus, phases=list(map(int, engine.Bus.Nodes())), nominal_kv_ln=float(engine.Bus.kVBase()),
                service_transformer=row["element"], service_terminal=terminal, service_kva=row["windings"][terminal-1]["kva"],
                mv_parent_bus=row["buses"][0], source_branch=row))
    for name in engine.Lines.AllNames():
        branches.append(_existing_branch(engine, "Line."+name))
    if len(endpoints) != 36 or len({r["logical_site_id"] for r in endpoints}) != 24:
        raise ValueError("SVR_EXPECTED_24_LOGICAL_36_PHYSICAL_SOURCE_ENDPOINTS")
    return dict(schema="V42_SERIES_SVR_SOURCE_INVENTORY_V1", logical_site_count=24, physical_endpoint_count=36,
                original_endpoints=endpoints, original_branches=branches, source_receipts=source_receipts,
                Native_optimizer_calls=0, solve_calls=0, installations=0)


def _downstream_nodes(branches, cut_element):
    """Undirected radial-cut coverage; reject an alternate energized path."""
    selected = next(r for r in branches if r["element"].lower() == cut_element.lower())
    first, second = (x.split(".")[0].lower() for x in selected["buses"][:2])
    graph = {}
    for r in branches:
        if r["element"].lower() == cut_element.lower() or r["properties"].get("Enabled", "Yes").lower() == "no":
            continue
        # Three-winding branches are not silently collapsed into a radial proof.
        if len(r["buses"]) != 2:
            raise ValueError("SVR_MULTI_TERMINAL_TOPOLOGY_REQUIRES_EXPLICIT_PROOF")
        a, b = (x.split(".")[0].lower() for x in r["buses"])
        graph.setdefault(a, set()).add(b); graph.setdefault(b, set()).add(a)
    seen = set(); queue = [second]
    while queue:
        node = queue.pop()
        if node in seen:
            continue
        seen.add(node); queue.extend(graph.get(node, set())-seen)
    if first in seen:
        raise ValueError("SVR_SERIES_CUT_HAS_PARALLEL_BYPASS")
    return sorted(seen)


def candidate_unit(inventory, candidate_id, *, vreg_volts=120.0, band_volts=2.0):
    """Declare a primary-side series bank; existing service equipment unchanged."""
    cid = candidate_id.upper()
    if cid == "BUS83":
        row = next(r for r in inventory["original_branches"] if r["element"].lower() == "line.l84")
        old = row["buses"][0]; sensed = "83"; sensed_kv = 4.16/math.sqrt(3)
        kv = 4.16/math.sqrt(3); kva = row["norm_amps"]*kv
        logical, endpoint = "FEEDER_BUS83", "MV_BRANCH"
    elif cid in ("STA01", "STA06", "STA08", "STA12"):
        site = next(r for r in inventory["original_endpoints"] if r["physical_endpoint_id"] == cid+"_MESS")
        row = site["source_branch"]; old = row["buses"][0]; sensed = site["pcc_bus"]
        sensed_kv = site["nominal_kv_ln"]; kv = row["windings"][0]["kv"]/math.sqrt(3)
        kva = row["windings"][0]["kva"]/3; logical, endpoint = cid, "MESS"
    else:
        raise ValueError("SVR_UNSUPPORTED_UNOBSERVED_CANDIDATE")
    coverage = _downstream_nodes(inventory["original_branches"], row["element"])
    if sensed not in coverage:
        raise ValueError("SVR_SENSE_BUS_NOT_IN_DIRECT_DOWNSTREAM_CUT")
    return dict(id=cid, logical_site_id=logical, endpoint_id=endpoint, cut_element=row["element"], cut_terminal=1,
        original_bus_spec=old, series_orientation="UPSTREAM_OF_EXISTING_BRANCH", downstream_bus=sensed,
        sensed_bus=sensed, upstream_new_bus="svr_"+cid.lower()+"_regulated", phases=[1,2,3],
        nominal_kv_ln=kv, sensed_kv_ln=sensed_kv, phase_kva=kva, min_tap=.9, max_tap=1.1, num_taps=32,
        xhl_pct=1.0, winding_r_pct=.2, no_load_loss_pct=.05,
        vreg_volts=vreg_volts, band_volts=band_volts, ptratio=kv*1000/120,
        remote_ptratio=sensed_kv*1000/120, ctprim=kva/kv,
        delay_seconds=30.0, tap_delay_seconds=2.0, max_tap_change=1,
        reverse_policy="FORWARD_LOCAL_VOLTAGE_BIDIRECTIONAL_POWER",
        engineering_assumptions=["Three independent single-phase grounded-wye full-power 1:1 tapped transformers form one bank; not a bus-voltage setter.",
            "New bank nameplate is finite and no greater than the original service nameplate or original line normal-current capacity.",
            "New XHL=1%, each winding R=.2%, no-load loss=.05% are explicit development assumptions, not a manufacturer certification.",
            "Remote LV/MV PT ratio and native tap action must pass real compiled-model sign/readback tests before source qualification.",
            "Original7 AUTO remains unchanged; new Delay30s follows original Delay15s in native queue, TapDelay2s; STATIC iterations do not represent seconds.",
            "No reversal of monitored direction: local downstream voltage is controlled for either signed power flow, with R=X=0 and Reversible=No."],
        direct_downstream_bus_coverage=coverage, upstream_voltage_coverage_claim=False,
        source_receipts=inventory["source_receipts"])


def development_contract(inventory, candidates=("STA08",)):
    c = dict(schema=SCHEMA, status="DEVELOPMENT_NOT_FROZEN_NOT_CANARY", autonomous_native_control=True,
             tap_optimization_variables=0, bus_voltage_assignment=False, Q_injection_devices=0,
             design_data="April primary; May01 B2 and May28 B1 are previously observed development diagnostics",
             independent_holdout_claim=False, whole_network_success_claim=False,
             units=[candidate_unit(inventory, name) for name in candidates])
    return validate_contract(c)


def line_candidate_unit(inventory, candidate_id):
    """Add a finite downstream series bank to an existing observed line.

    The entire line and its impedance/rating remain; only terminal 2 is moved
    to the bank input bus. Both alternatives are exposed without selecting a
    position from a future Actual outcome or changing the original four units.
    """
    cid = str(candidate_id).upper()
    if cid not in LINE_CANDIDATES:
        raise ValueError("SVR_UNOBSERVED_LINE_CANDIDATE")
    element, upstream, downstream = LINE_CANDIDATES[cid]
    rows = [r for r in inventory["original_branches"] if r["element"].lower() == element.lower()]
    if len(rows) != 1:
        raise ValueError("SVR_EXACT_EXISTING_LINE_REQUIRED")
    row = rows[0]
    expected = [upstream+".1.2.3", downstream+".1.2.3"]
    if row["phases"] != 3 or [b.lower() for b in row["buses"]] != expected:
        raise ValueError("SVR_OBSERVED_THREE_PHASE_LINE_WIRING_REQUIRED")
    normal = float(row["norm_amps"])
    if not math.isfinite(normal) or normal <= 0:
        raise ValueError("SVR_FINITE_ORIGINAL_LINE_CURRENT_RATING_REQUIRED")
    endpoints = [r for r in inventory["original_endpoints"]
                 if r["mv_parent_bus"].split(".")[0].lower() == downstream]
    if not endpoints:
        raise ValueError("SVR_NATIVE_DOWNSTREAM_SERVICE_VOLTAGE_EVIDENCE_REQUIRED")
    nominal = {float(r["source_branch"]["windings"][0]["kv"])/math.sqrt(3) for r in endpoints}
    if len(nominal) != 1 or not all(math.isfinite(v) and v > 0 for v in nominal):
        raise ValueError("SVR_CONSISTENT_NATIVE_DOWNSTREAM_NOMINAL_VOLTAGE_REQUIRED")
    kv = next(iter(nominal))
    # Inherit the existing common finite transformer/native-control design,
    # while deriving this new bank's rating from its own original line.
    u = candidate_unit(inventory, "BUS83")
    u.update(id=cid, logical_site_id="FEEDER_"+cid, endpoint_id="MV_BRANCH",
             cut_element=row["element"], cut_terminal=2, original_bus_spec=row["buses"][1],
             series_orientation="DOWNSTREAM_OF_EXISTING_BRANCH", downstream_bus=downstream,
             sensed_bus=downstream, upstream_new_bus="svr_"+cid.lower()+"_series_input",
             nominal_kv_ln=kv, sensed_kv_ln=kv, phase_kva=normal*kv,
             ptratio=kv*1000/120, remote_ptratio=kv*1000/120, ctprim=normal,
             direct_downstream_bus_coverage=_downstream_nodes(inventory["original_branches"], row["element"]),
             source_receipts=inventory["source_receipts"])
    if downstream not in u["direct_downstream_bus_coverage"]:
        raise ValueError("SVR_NEW_SENSE_BUS_OUTSIDE_DIRECT_DOWNSTREAM_CUT")
    u["engineering_assumptions"] = list(u["engineering_assumptions"]) + [
        "The existing line keeps its full length, LineCode, impedance and normal/emergency current ratings; only Bus2 is reconnected to the series-bank input.",
        "The new bank is downstream of the original line and controls the original downstream MV bus. No fictitious direct line is created.",
        "Coverage is a source topology cut, not proof that every downstream LV phase is safe or that this candidate dominates its alternative.",
    ]
    return u


def additive_svr7_contract(frozen_svr4, inventory, *, alternative):
    """Copy all four exact unit DTOs and append only the declared three banks."""
    base = validate_contract(frozen_svr4)
    if [u["id"] for u in base["units"]] != ["STA01", "STA06", "STA08", "BUS83"]:
        raise ValueError("SVR_EXACT_ORIGINAL_FOUR_ORDER_REQUIRED")
    choice = str(alternative).upper()
    if choice not in ("BUS48", "BUS50"):
        raise ValueError("SVR_EXACTLY_ONE_DECLARED_ALTERNATIVE_REQUIRED")
    value = json.loads(json.dumps(base, allow_nan=False))
    value["status"] = "DEVELOPMENT_NOT_FROZEN_NOT_CANARY"
    value["units"].extend(line_candidate_unit(inventory, name) for name in ("BUS79", "BUS108", choice))
    value = validate_contract(value)
    if digest(value["units"][:4]) != digest(base["units"]):
        raise ValueError("SVR_ORIGINAL_FOUR_CANONICAL_UNIT_DRIFT")
    if len(value["units"]) != 7 or {u["id"] for u in value["units"][4:]} != {"BUS79", "BUS108", choice}:
        raise ValueError("SVR_ADDITIVE_EXACT_SEVEN_UNITS_REQUIRED")
    return value


def write_location_audit(path, inventory, original_cells):
    """Write all small candidates and exact direct coverage, not an installation decision."""
    rows = []
    for name in ("STA08", "STA06", "STA01", "STA12", "BUS83"):
        u = candidate_unit(inventory, name); coverage = set(u["direct_downstream_bus_coverage"])
        covered = [r for r in original_cells if r["node_phase"].split(".")[0] in coverage]
        rows.append(dict(candidate_id=name, status="DEVELOPMENT_NOT_INSTALLED_NOT_FROZEN", logical_site_id=u["logical_site_id"],
            endpoint_id=u["endpoint_id"], cut_element=u["cut_element"], cut_terminal=u["cut_terminal"],
            old_upstream_bus=u["original_bus_spec"], new_regulated_bus=u["upstream_new_bus"], sensed_bus=u["sensed_bus"],
            phases="1,2,3", phase_kva=u["phase_kva"], bank_kva=3*u["phase_kva"], nominal_kv_ln=u["nominal_kv_ln"],
            normal_current_a=u["phase_kva"]/u["nominal_kv_ln"], direct_known_cells=len(covered),
            direct_known_node_phases=";".join(sorted({r["node_phase"] for r in covered})), upstream_coverage_claim=False,
            physical_endpoint_count=36, logical_site_count=24, source_inventory_SHA=digest(inventory),
            actual_96slot_status="NOT_RUN", FULL_model_regeneration_required=True))
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    return rows
