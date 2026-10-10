"""Read actual compiled PCC topology; no allocation or electrical setters.

The 24 logical sites have 36 physical endpoints: twelve station MESS PCCs,
twelve IDC load PCCs, and twelve separate IDC MESS service branches.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


def receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("EMPTY_AUDIT_TABLE")
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, tuple)) else value
                             for key, value in row.items()})


def _properties(engine, names):
    return {name: engine.Properties.Value(name) for name in names}


def transformer_readback(engine, name):
    engine.Transformers.Name(name)
    if engine.Transformers.Name().lower() != name.lower():
        raise ValueError("SERVICE_TRANSFORMER_NOT_FOUND:" + name)
    buses = list(engine.CktElement.BusNames())
    node_order = list(map(int, engine.CktElement.NodeOrder()))
    phases, conductors = int(engine.CktElement.NumPhases()), int(engine.CktElement.NumConductors())
    windings = []
    for winding in range(1, int(engine.Transformers.NumWindings()) + 1):
        engine.Transformers.Wdg(winding)
        kv, kva = float(engine.Transformers.kV()), float(engine.Transformers.kVA())
        windings.append(dict(winding=winding, bus=buses[winding - 1], nominal_kv=kv,
            nominal_kva=kva, rated_current_a=kva / (math.sqrt(3) * kv) if phases == 3 else kva / kv,
            delta=bool(engine.Transformers.IsDelta()), tap=float(engine.Transformers.Tap()),
            node_order=node_order[(winding - 1)*conductors:winding*conductors],
            neutral_resistance_ohm=float(engine.Transformers.Rneut()),
            neutral_reactance_ohm=float(engine.Transformers.Xneut())))
    return dict(name=name.lower(), phases=phases, conductors=conductors, windings=windings,
                electrical_properties=_properties(engine, ("XHL", "%LoadLoss", "%NoLoadLoss", "%Rs")))


def _bus(engine, name):
    if name.lower() not in {bus.lower() for bus in engine.Circuit.AllBusNames()}:
        return dict(bus=name.lower(), exists=False, nodes=[], nominal_kv_ln=None)
    engine.Circuit.SetActiveBus(name)
    return dict(bus=name.lower(), exists=True, nodes=list(map(int, engine.Bus.Nodes())),
                nominal_kv_ln=float(engine.Bus.kVBase()), x=float(engine.Bus.X()), y=float(engine.Bus.Y()))


def inspect_sites(engine, *, source_receipts=()):
    """Return real 36 endpoints at 24 sites, not approved installations."""
    lines = []
    for name in engine.Lines.AllNames():
        engine.Lines.Name(name)
        lines.append(dict(name=name.lower(), buses=[bus.split(".", 1)[0].lower() for bus in engine.CktElement.BusNames()],
                          normal_amps=float(engine.Lines.NormAmps()), phases=int(engine.CktElement.NumPhases())))
    rows = []
    for family in ("STA", "IDC"):
        for index in range(1, 13):
            site = f"{family}{index:02d}"
            name = ("mess_" if family == "STA" else "idc_") + site.lower() + "_tx"
            tx = transformer_readback(engine, name)
            pcc_name = tx["windings"][1]["bus"].split(".", 1)[0]
            pcc = _bus(engine, pcc_name)
            parent_name = tx["windings"][0]["bus"].split(".", 1)[0]
            parent = _bus(engine, parent_name)
            phases = sorted(set(pcc["nodes"]) & {1, 2, 3})
            reasons = []
            if not pcc["exists"] or phases != [1, 2, 3]: reasons.append("ACTUAL_THREE_PHASE_PCC_ABSENT")
            if not pcc["nominal_kv_ln"] or pcc["nominal_kv_ln"] <= 0: reasons.append("INVALID_NOMINAL_KV")
            if any(w["nominal_kva"] <= 0 for w in tx["windings"]): reasons.append("INVALID_SERVICE_RATING")
            if any(w["delta"] for w in tx["windings"]): reasons.append("INDEPENDENT_PHASE_GROUND_CONNECTION_NOT_PROVEN")
            incident = [line for line in lines if parent_name.lower() in line["buses"]]
            mess_tx = transformer_readback(engine, "mess_" + site.lower() + "_tx") if family == "IDC" else tx
            rows.append(dict(site_id=site, logical_site_id=site, endpoint_id="MESS" if family == "STA" else "AIDC",
                device_id=site+"_"+("MESS" if family == "STA" else "AIDC"),
                site_family=family, pcc_bus=pcc_name.lower(), phases=phases,
                nominal_kv_ln=pcc["nominal_kv_ln"], nominal_kv_ll=pcc["nominal_kv_ln"]*math.sqrt(3) if pcc["nominal_kv_ln"] else None,
                connection_voltage_class="EXISTING_LV_PCC", mv_parent_bus=parent_name.lower(),
                mv_parent_phases=parent["nodes"], mv_parent_kv_ln=parent["nominal_kv_ln"],
                service_transformers=[name], service_transformer_kva=tx["windings"][1]["nominal_kva"],
                service_rating_primary_current_a=tx["windings"][0]["rated_current_a"],
                service_rating_secondary_current_a=tx["windings"][1]["rated_current_a"],
                service_transformer=tx, mess_pcc_bus=mess_tx["windings"][1]["bus"].split(".", 1)[0].lower(),
                mess_service_transformer=mess_tx, original_wiring="WYE_WYE_IMPLICIT_NODE0_CONFIRMED_BY_NODE_ORDER",
                original_neutral_nodes=[w["node_order"] for w in tx["windings"]],
                proposed_connection="THREE_SEPARATE_GROUNDED_SINGLE_PHASE_MODULES_VIA_1_TO_1_COUPLING_BANK_AT_SAME_LV_PCC",
                existing_service_rating_retained=True, service_spare_capacity_not_assumed=True,
                dedicated_coupling_transformer_required=True, upstream_incident_lines=incident,
                phase_cable_rating_authority="NEW_DEDICATED_CABLE_RATING_ENGINEERING_ASSUMPTION_REQUIRED",
                initial_design_rating_kvar=1500 if site == "STA08" else 750,
                installed=False, status="INVALID_SITE" if reasons else "VALID_CANDIDATE_NOT_APPROVED",
                invalid_reasons=reasons, x=pcc["x"] if pcc["exists"] else None, y=pcc["y"] if pcc["exists"] else None,
                source_receipts=list(source_receipts)))
            if family == "IDC":
                endpoint = dict(rows[-1])
                mess_bus = _bus(engine, endpoint["mess_pcc_bus"])
                endpoint.update(endpoint_id="MESS", device_id=site+"_MESS", pcc_bus=mess_bus["bus"],
                    phases=sorted(set(mess_bus["nodes"]) & {1,2,3}), nominal_kv_ln=mess_bus["nominal_kv_ln"],
                    nominal_kv_ll=mess_bus["nominal_kv_ln"]*math.sqrt(3),
                    service_transformers=[mess_tx["name"]], service_transformer_kva=mess_tx["windings"][1]["nominal_kva"],
                    service_rating_primary_current_a=mess_tx["windings"][0]["rated_current_a"],
                    service_rating_secondary_current_a=mess_tx["windings"][1]["rated_current_a"],
                    service_transformer=mess_tx, original_neutral_nodes=[w["node_order"] for w in mess_tx["windings"]])
                if endpoint["phases"] != [1,2,3]:
                    endpoint["status"]="INVALID_SITE";endpoint["invalid_reasons"]=["ACTUAL_THREE_PHASE_PCC_ABSENT"]
                rows.append(endpoint)
    if len(rows) != 36 or len({row["site_id"] for row in rows}) != 24 or len({row["device_id"] for row in rows}) != 36:
        raise ValueError("ACTUAL_24_LOGICAL_SITE_36_PHYSICAL_ENDPOINT_AXIS_REQUIRED")
    return rows


def canonical_24_sites(rows):
    """Select the required station MESS and IDC AIDC PCCs without merging buses.

    The separate IDC MESS endpoints remain original network nodes. They are
    explicitly excluded from the 24 installed-device contract.
    """
    expected = {f"STA{index:02d}_MESS" for index in range(1, 13)} | {
        f"IDC{index:02d}_AIDC" for index in range(1, 13)}
    selected = [dict(row) for row in rows if row.get("device_id") in expected]
    if len(selected) != 24 or {row["device_id"] for row in selected} != expected:
        raise ValueError("CANONICAL_24_DISTINCT_PCC_DEVICES_REQUIRED")
    if len({row["pcc_bus"] for row in selected}) != 24:
        raise ValueError("CANONICAL_24_DISTINCT_PCC_BUSES_REQUIRED")
    for row in selected:
        prefix = "mess_" if row["site_id"].startswith("STA") else "idc_"
        if (row["pcc_bus"] != prefix + row["site_id"].lower() + "_pcc"
                or row.get("phases") != [1, 2, 3]
                or row.get("status") == "INVALID_SITE"):
            raise ValueError("SOURCE_BACKED_CANONICAL_PCC_CONNECTION_REQUIRED")
        row["required_installed_endpoint"] = True
        row["initial_design_rating_kvar"] = 1500 if row["site_id"] == "STA08" else 750
    return sorted(selected, key=lambda row: (not row["site_id"].startswith("STA"), row["site_id"]))


def audit_sites(output):
    from v42_regcontrol import authority
    source = authority.source()
    receipts = [receipt(path) for path in source["assets"].__dict__.values()]
    engine, _adapter, inventory = authority.compile_verified()
    try:
        rows = inspect_sites(engine, source_receipts=receipts)
    finally:
        engine.Basic.ClearAll()
    output = Path(output)
    write_json(output / "DSTATCOM_SITE_INVENTORY.json", dict(schema="V42_DSTATCOM_REAL_PCC_INVENTORY_V1",
        logical_site_count=24, physical_endpoint_count=36, candidate_count=36,
        selected_count=0, installed_count=0, installation_approved=False,
        Native_optimizer_calls=0, Fresh_AC_replays=0, source_control_inventory=inventory, sites=rows,
        original_asset_receipts=receipts))
    write_csv(output / "DSTATCOM_SITE_SELECTION.csv", rows)
    phase_rows = [dict(site_id=row["site_id"], endpoint_id=row["endpoint_id"], device_id=row["device_id"],
        pcc_bus=row["pcc_bus"], phase="ABC"[phase-1], node=phase,
        nominal_kv_ln=row["nominal_kv_ln"], nominal_kv_ll=row["nominal_kv_ll"], status=row["status"],
        service_transformer_kva=row["service_transformer_kva"], coupling_required=True,
        existing_service_rating_retained=True, neutral_node_zero_present=all(0 in w["node_order"] for w in row["service_transformer"]["windings"]),
        connection=row["proposed_connection"], source_receipts=row["source_receipts"])
        for row in rows for phase in row["phases"]]
    write_csv(output / "DSTATCOM_PHASE_CONNECTION_AUDIT.csv", phase_rows)
    return rows
