"""Fixed-route traversal and memoryless actuator projection; no search API."""
from copy import deepcopy
import math
import numpy as np
from dayahead.paper_analysis.storage import digest
from .contracts import ReplayError, ZERO_COUNTERS
from dayahead.mess_physics import P_LIMIT_KW,PCS_KVA


def traverse(links, departure_slot, link_ids, travel_seconds, energy_function, *, connection_delay_seconds):
    """Energy callback is the frozen physics evaluator, not a predictor or optimizer."""
    values = np.asarray(travel_seconds)
    if values.shape != (288, len(link_ids)) or not np.isfinite(values).all() or np.any(values <= 0):
        raise ReplayError("ACTUAL_TRAFFIC_AXIS_OR_VALUE")
    if not links or len(set(link_ids)) != len(link_ids):
        raise ReplayError("ACTUAL_ROUTE_OR_LINK_AXIS")
    index = {v: i for i, v in enumerate(link_ids)}
    elapsed = 0.0
    entries = []
    for link in links:
        step = departure_slot * 3 + int(elapsed // 300)
        if link not in index or not 0 <= step < 288:
            raise ReplayError("ACTUAL_ROUTE_LINK_ENTRY_UNAVAILABLE")
        duration = float(values[step, index[link]])
        entries.append({"link_id": link, "entry_step5": step, "travel_seconds": duration})
        elapsed += duration
    energy = float(energy_function(tuple(links), elapsed))
    if not math.isfinite(energy) or energy < 0:
        raise ReplayError("ACTUAL_TRAVEL_ENERGY")
    return {"route_link_ids": list(links), "route_SHA": digest(list(links)),
        "departure_slot": departure_slot, "actual_eta_seconds": elapsed,
        "actual_arrival_slot": departure_slot + elapsed / 900,
        "actual_connection_ready_slot": departure_slot + math.ceil((elapsed + connection_delay_seconds) / 900),
        "actual_travel_energy_kWh": energy, "link_entries": entries}


def project_command(p_cmd, q_cmd, energy, *, connected, travel_energy=0.0,
                    e_min=440.0, e_max=1080.0, pcs_kva=PCS_KVA,
                    eta_charge=1.0, eta_discharge=1.0, dt_hours=.25):
    values = (p_cmd, q_cmd, energy, travel_energy, e_min, e_max, pcs_kva, eta_charge, eta_discharge, dt_hours)
    if not all(math.isfinite(v) for v in values) or travel_energy < 0:
        raise ReplayError("NONFINITE_ACTUATOR_INPUT")
    available = energy - travel_energy
    if available < e_min - 1e-9 or available > e_max + 1e-9:
        raise ReplayError("ACTUAL_TRAVEL_ENERGY_BOUND_FAILURE")
    reasons = []
    if not connected:
        p = q = 0.0
        reasons.append("NOT_CONNECTED")
    else:
        discharge_limit = max(0.0, (available - e_min) * eta_discharge / dt_hours)
        charge_limit = max(0.0, (e_max - available) / (eta_charge * dt_hours))
        p = min(max(p_cmd, -charge_limit), discharge_limit)
        if p != p_cmd:
            reasons.append("BATTERY_ENERGY_SATURATION")
        if abs(p_cmd)>P_LIMIT_KW+1e-9:
            raise ReplayError('INVALID_FROZEN_ACTIVE_COMMAND_RATING')
        if abs(p) > pcs_kva:
            raise ReplayError("INVALID_FROZEN_ACTIVE_COMMAND_PCS")
        q_limit = math.sqrt(max(0, pcs_kva * pcs_kva - p * p))
        q = min(max(q_cmd, -q_limit), q_limit)
        if q != q_cmd:
            reasons.append("PCS_Q_CLIPPING")
    after = available + eta_charge * max(-p, 0) * dt_hours - max(p, 0) * dt_hours / eta_discharge
    return {"P_CMD": p_cmd, "Q_CMD": q_cmd, "P_EXEC": p, "Q_EXEC": q,
        "P_CURTAILED": p_cmd - p, "Q_CURTAILED": q_cmd - q,
        "curtailment_reason": reasons or ["EXECUTED"],
        "energy_before_kWh": energy, "travel_energy_kWh": travel_energy,
        "energy_after_kWh": after}


def replay_commands(slots, moves, initial_energy, *, initial_locations=None, capacity_kwh=1200.0, **projection):
    """Execute original commands at original slots, gated at their original PCC."""
    slots = deepcopy(list(slots))
    before = digest(slots)
    output = []
    for vehicle in sorted(initial_energy):
        commands = sorted((r for r in slots if r["mess_id"] == vehicle), key=lambda r: r["slot"])
        if [r["slot"] for r in commands] != list(range(96)):
            raise ReplayError("FROZEN_COMMAND_SLOT_AXIS")
        committed = sorted((m for m in moves if m["mess_id"] == vehicle), key=lambda m: m["departure_slot"])
        if len({m["departure_slot"] for m in committed}) != len(committed):
            raise ReplayError("DUPLICATE_FROZEN_DEPARTURE")
        location = initial_locations[vehicle] if initial_locations is not None else commands[0]["service_id"]
        if not location:
            raise ReplayError("MISSING_INITIAL_MESS_LOCATION")
        energy = initial_energy[vehicle]
        for r in commands:
            slot = r["slot"]
            active, travel = None, 0.0
            for m in committed:
                if slot == m["departure_slot"]:
                    if any(old["departure_slot"] < slot < old["actual_connection_ready_slot"] for old in committed):
                        raise ReplayError("ACTUAL_DEPARTURE_BEFORE_PREVIOUS_ARRIVAL")
                    if location != m["origin_service_id"]:
                        raise ReplayError("ACTUAL_DEPARTURE_ORIGIN_UNAVAILABLE")
                    travel += m["actual_travel_energy_kWh"]
                if m["departure_slot"] <= slot < m["actual_connection_ready_slot"]:
                    active = m
                elif slot >= m["actual_connection_ready_slot"]:
                    location = m["destination_service_id"]
            # Original zero commands during planned transit remain zero even if arrival is early.
            connected = active is None
            if connected and (r["p_kw"] or r["q_kvar"]) and location != r["service_id"]:
                raise ReplayError("FROZEN_COMMAND_PCC_UNAVAILABLE")
            row = project_command(r["p_kw"], r["q_kvar"], energy,
                                  connected=connected, travel_energy=travel, **projection)
            output.append({"mess_id": vehicle, "slot": slot, "frozen_service_id": r["service_id"],
                "actual_service_id": location if active is None else None,
                "connected": connected, "SoC_before": energy / capacity_kwh,
                **row, "SoC_after": row["energy_after_kWh"] / capacity_kwh})
            energy = row["energy_after_kWh"]
    if digest(slots) != before:
        raise ReplayError("FROZEN_COMMAND_MUTATION")
    return {"status": "PASS", "trajectory": output, "frozen_commands_SHA": before,
            "counters": dict.fromkeys(ZERO_COUNTERS, 0), "command_time_shift_count": 0}
