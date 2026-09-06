"""D00 state resolution and independent fixed-route energy accounting."""
from datetime import datetime, timedelta
import math
from .contracts import ReplayError
from dayahead.paper_analysis.storage import digest


def resolve_initial_states(rows, frozen_initial_locations, initial_energy, source, day):
    states=[];locations={}
    for vehicle in sorted(initial_energy):
        commands=sorted((r for r in rows if r["mess_id"]==vehicle),key=lambda r:r["slot"])
        if not commands or commands[0]["slot"]!=0:
            raise ReplayError("MISSING_FROZEN_MESS_D00_STATE")
        zero=commands[0];dep=zero.get("departure_slot");mode=zero.get("mode","CONNECTED" if zero.get("service_id") else "TRANSIT")
        departures=[r for r in commands if r.get("departure_slot")==r["slot"]]
        first=departures[0] if departures else zero
        origin=first.get("origin_service_id");links=first.get("route_link_ids",[])
        if dep is not None and dep<0:
            ready=zero.get("connection_ready_slot")
            if mode in ("CONNECTED","SERVICE") and ready is not None and ready<=0:
                location=zero.get("service_id")
                if not location or location!=zero.get("destination_service_id"):
                    raise ReplayError("PRE_D00_ARRIVAL_DESTINATION_AUTHORITY_MISMATCH")
                kind="ARRIVED_BEFORE_D00"
            else:
                state=zero.get("frozen_D00_transit_state")
                needed=("current_edge_at_D00","route_progress_at_D00","remaining_route_at_D00","authority_source_SHA")
                if not isinstance(state,dict) or any(state.get(k) is None for k in needed):
                    raise ReplayError("MISSING_AUTHORITATIVE_D00_TRANSIT_PROGRESS")
                # Never reset a pre-D00 trip or bill its whole route at D00.
                # Current freezes have no such cases. A residual traversal authority,
                # including carried energy and the current edge entry time, is required.
                raise ReplayError("D00_TRANSIT_RESIDUAL_EXECUTION_AUTHORITY_REQUIRED")
        elif dep==0:
            location=zero.get("origin_service_id")
            if not location or not links or location!=frozen_initial_locations[vehicle]:
                raise ReplayError("D00_DEPARTURE_ORIGIN_IDENTITY_MISMATCH")
            kind="DEPARTURE_EXACTLY_D00"
        else:
            location=zero.get("service_id")
            if mode not in ("CONNECTED","SERVICE") or not location:
                raise ReplayError("MISSING_AUTHORITATIVE_D00_TRANSIT_PROGRESS")
            kind="CONNECTED_AT_D00_DEPARTURE_LATER" if departures else "STAY_CONNECTED_AT_D00"
            # Preserve the D00 slot's location, not a future route's origin.
        locations[vehicle]=location
        departure=first.get("departure_slot")
        states.append({"vehicle_id":vehicle,"state_at_D00":kind,"frozen_initial_location":location,
            "departure_time":None if departure is None else (datetime.fromisoformat(day)+timedelta(minutes=15*departure)).isoformat()+"+10:00",
            "departure_slot":departure,"departure_origin":origin,"route_id":first.get("route_id") or (digest(links) if links else None),
            "route_sha":digest(links) if links else None,"current_edge_at_D00":None,
            "route_progress_at_D00":0 if dep==0 else None,"remaining_route_at_D00":links if dep==0 else [],
            "actual_initial_state_source":source,"initial_energy_kWh":initial_energy[vehicle],
            "initial_state_resolution":"PASS_FROZEN_D00_STATE","origin_reset_performed":False})
    return locations,states


def audit_mess(commands, moves, executed, initial_energy, states):
    from dayahead.mess_physics import CAPACITY_KWH,E_MIN_KWH,E_MAX_KWH,DT_HOURS,PCS_KVA
    tolerance=1e-9  # Existing dayahead.mess_physics bound tolerance, unchanged.
    cmd={(r["mess_id"],r["slot"]):r for r in commands}
    actual={(r["mess_id"],r["slot"]):r for r in executed}
    if len(actual)!=len(executed) or len(cmd)!=len(commands) or set(cmd)!=set(actual):
        raise ReplayError("MESS_COMMAND_SLOT_OR_VEHICLE_CHANGED")
    frozen_moves={(r["mess_id"],r["departure_slot"]):r for r in commands if r.get("departure_slot")==r["slot"]}
    real_moves={(m["mess_id"],m["departure_slot"]):m for m in moves}
    if len(real_moves)!=len(moves) or set(real_moves)!=set(frozen_moves):
        raise ReplayError("MESS_ROUTE_RESELECTED_DEPARTURE_OR_VEHICLE_CHANGED")
    for key,r in real_moves.items():
        f=frozen_moves[key]
        if r["route_link_ids"]!=f["route_link_ids"] or r["origin_service_id"]!=f["origin_service_id"] or r["destination_service_id"]!=f["destination_service_id"]:
            raise ReplayError("MESS_FROZEN_ROUTE_OR_DESTINATION_CHANGED")
    maxima=[];vehicles=[];nonexecution=0
    for vehicle,initial in sorted(initial_energy.items()):
        energy=float(initial);travel_total=charge=discharge=0.;errors=[]
        location=next(r["frozen_initial_location"] for r in states if r["vehicle_id"]==vehicle)
        vehicle_moves=sorted((r for r in moves if r["mess_id"]==vehicle),key=lambda r:r["departure_slot"])
        for t in range(96):
            row=actual[vehicle,t];f=cmd[vehicle,t]
            if row["P_CMD"]!=f["p_kw"] or row["Q_CMD"]!=f["q_kvar"]:
                raise ReplayError("MESS_COMMAND_SHIFT_OR_CHANGE")
            if not row["connected"] and (row["P_EXEC"]!=0 or row["Q_EXEC"]!=0):
                raise ReplayError("MESS_NONCONNECTED_COMMAND_EXECUTION")
            if (f["p_kw"]!=0 or f["q_kvar"]!=0) and (row["P_EXEC"]!=f["p_kw"] or row["Q_EXEC"]!=f["q_kvar"]):
                nonexecution+=1
            move=real_moves.get((vehicle,t));travel=0. if move is None else move["actual_travel_energy_kWh"]
            active=[m for m in vehicle_moves if m["departure_slot"]<=t<m["actual_connection_ready_slot"]]
            arrived=[m for m in vehicle_moves if m["actual_connection_ready_slot"]<=t]
            if arrived:location=arrived[-1]["destination_service_id"]
            if len(active)>1 or row["connected"]!=(len(active)==0) or row["actual_service_id"]!=(None if active else location):
                raise ReplayError("MESS_PHYSICAL_CONNECTION_OR_LOCATION_MISMATCH")
            available=energy-travel
            p=0. if active else min(max(f["p_kw"],-(E_MAX_KWH-available)/DT_HOURS),(available-E_MIN_KWH)/DT_HOURS)
            limit=math.sqrt(max(0.,PCS_KVA**2-p**2))
            q=0. if active else min(max(f["q_kvar"],-limit),limit)
            if max(abs(row["P_EXEC"]-p),abs(row["Q_EXEC"]-q))>tolerance:
                raise ReplayError("MESS_ACTUATOR_PROJECTION_MISMATCH")
            if abs(row["travel_energy_kWh"]-travel)>tolerance:
                raise ReplayError("TRAVEL_ENERGY_DOUBLE_COUNT_OR_MISSING")
            errors.append(abs(row["energy_before_kWh"]-energy))
            c=max(-row["P_EXEC"],0)*DT_HOURS;d=max(row["P_EXEC"],0)*DT_HOURS
            energy=energy-travel+c-d
            errors.extend((abs(row["energy_after_kWh"]-energy),abs(row["SoC_after"]-energy/CAPACITY_KWH)*CAPACITY_KWH))
            if energy<E_MIN_KWH-tolerance or energy>E_MAX_KWH+tolerance:
                raise ReplayError("SOC_BOUND_VIOLATION")
            travel_total+=travel;charge+=c;discharge+=d
        error=max(errors)
        final_identity=initial-travel_total+charge-discharge
        error=max(error,abs(final_identity-energy))
        if error>tolerance:raise ReplayError("MESS_SOC_CONSERVATION_FAIL")
        maxima.append(error)
        vehicles.append({"vehicle_id":vehicle,"initial_energy_kWh":initial,"travel_energy_kWh":travel_total,
            "executed_charge_kWh":charge,"executed_discharge_kWh":discharge,"final_energy_kWh":energy,
            "SOC_BALANCE_MAX_ERROR_kWh":error,"SOC_BOUND_VIOLATION_COUNT":0,"TRAVEL_ENERGY_DOUBLE_COUNT_COUNT":0})
    return {"status":"PASS","SOC_BALANCE_MAX_ERROR":max(maxima),"SOC_BALANCE_ERROR_UNIT":"kWh",
        "SOC_BALANCE_MAX_ERROR_fraction":max(maxima)/CAPACITY_KWH,"numerical_tolerance_kWh":tolerance,
        "SOC_BOUND_VIOLATION_COUNT":0,"TRAVEL_ENERGY_DOUBLE_COUNT_COUNT":0,
        "MESS_ROUTE_CHANGE_COUNT":0,"MESS_ROUTE_RESELECTION_COUNT":0,"MESS_DESTINATION_CHANGE_COUNT":0,
        "MESS_DEPARTURE_REOPTIMIZATION_COUNT":0,"MESS_ALTERNATE_VEHICLE_COUNT":0,
        "TRANSIT_AT_D00_RESET_TO_ORIGIN_COUNT":0,"CONNECTED_AT_D00_RESET_TO_ORIGIN_COUNT":0,"EARLY_DEPARTURE_STATE_LOSS_COUNT":0,
        "MESS_TRANSIT_RESET_TO_ORIGIN_COUNT":0,"MESS_COMMAND_NONEXECUTION_COUNT":nonexecution,
        "nonexecution_count_definition":"vehicle-slots with a nonzero frozen P/Q command partly or wholly unexecuted; no command shifting",
        "D00_states":states,"vehicles":vehicles,"energy_efficiency_authority":"existing unit charge/discharge efficiency",
        "realized_traffic_role":"same frozen edges; link-entry traversal timing only"}
