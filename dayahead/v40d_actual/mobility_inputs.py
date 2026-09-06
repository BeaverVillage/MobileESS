"""Actual traversal adapter for the final AC-accepted saved MESS commands."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, sha, digest, reference
from .contracts import ReplayError
from .mess_replay import traverse, replay_commands
from .mess_audit import resolve_initial_states,audit_mess


def actual_mobility(repo, binding):
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.mess_physics import E_INITIAL_KWH, CAPACITY_KWH
    from dayahead.v33m.contracts import CONNECTION_DELAY_SECONDS
    from dayahead.v33m.road_graph_authority import load_road_graph_authority
    from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter
    day, case = binding["day"], binding["case"]
    if case == "B3":
        allowed=("mess_id","slot","service_id","p_kw","q_kvar","departure_slot","origin_service_id",
            "destination_service_id","route_link_ids","connection_ready_slot","mode","battery_energy_kwh","soc_fraction")
        rows = [{k:r[k] for k in allowed} for r in read(binding["final_PQ_source"])["MESS_trajectory"]]
        source=reference(binding["final_PQ_source"])
    else:
        f = pd.read_parquet(binding["MESS_final_source"],columns=["vehicle_id","slot","current_location","state",
            "P_kW","Q_kvar","SoC_fraction","route_ID","connection_ready_slot","departure_slot","origin","destination",
            "route_link_node_sequence_reference"])
        source=reference(binding["MESS_final_source"])
        if source["sha256"]!=binding["binding_components"]["MESS_executed_file_SHA"]:
            raise ReplayError("FROZEN_MESS_EXECUTION_SHA_DRIFT")
        rows = []
        for r in f.to_dict("records"):
            rows.append({"mess_id": r["vehicle_id"], "slot": int(r["slot"]),
                "service_id": r["current_location"] if r["state"]=="SERVICE" else None,
                "p_kw": r["P_kW"], "q_kvar": r["Q_kvar"],
                "mode":"CONNECTED" if r["state"]=="SERVICE" else "TRANSIT",
                "soc_fraction":r["SoC_fraction"],"route_id":r["route_ID"],
                "connection_ready_slot":None if pd.isna(r["connection_ready_slot"]) else int(r["connection_ready_slot"]),
                "departure_slot": None if pd.isna(r["departure_slot"]) else int(r["departure_slot"]),
                "origin_service_id": r["origin"], "destination_service_id": r["destination"],
                "route_link_ids": json.loads(r["route_link_node_sequence_reference"])})
    if not rows:
        rows = [{"mess_id": m, "slot": t, "service_id": site, "p_kw": 0., "q_kvar": 0.,
                 "departure_slot": None,"mode":"CONNECTED","battery_energy_kwh":E_INITIAL_KWH}
                for m,site in sorted(MESS_INITIAL.items()) for t in range(96)]
        source={**source,"zero_MESS_case_initial_location_contract":reference(Path(repo)/"dayahead/v35/execution.py")}
    initial_energy={}
    for r in rows:
        if r["slot"]!=0:continue
        energy=r.get("battery_energy_kwh",E_INITIAL_KWH)
        if abs(energy-E_INITIAL_KWH)>1e-9 or abs(r.get("soc_fraction",energy/CAPACITY_KWH)*CAPACITY_KWH-energy)>6.1e-7:
            raise ReplayError("FROZEN_D00_MESS_ENERGY_AUTHORITY_MISMATCH")
        initial_energy[r["mess_id"]]=energy
    initial_locations,initial_states=resolve_initial_states(rows,MESS_INITIAL,initial_energy,
        {"D00_trajectory":source,"energy_contract":reference(Path(repo)/"dayahead/mess_physics.py")},day)
    commitments = [r for r in rows if r.get("departure_slot") == r["slot"]]
    moves = []
    if commitments:
        authority = read(Path(repo)/"dayahead/artifacts/v40d_actual_realized_replay/V40D_TRAFFIC_COMPLETENESS.json")
        daily = next(r for r in authority["days"] if r["day"]==day)
        refs = [authority["link_order"]]+authority["geometry_sources"]
        for ref in refs+[daily["source"]]:
            if sha(ref["path"]) != ref["sha256"]:
                raise ReplayError("ACTUAL_MOBILITY_AUTHORITY_DRIFT")
        graph = load_road_graph_authority(*(Path(r["path"]) for r in refs))
        order = pd.read_csv(refs[0]["path"]).sort_values("tensor_index").reduced_link_id.astype(str).tolist()
        traffic = pd.read_parquet(daily["source"]["path"],columns=["slot5","reduced_link_id","final_tt_sec"])
        if traffic.duplicated(["slot5","reduced_link_id"]).any():
            raise ReplayError("ACTUAL_TRAFFIC_DUPLICATE")
        array = traffic.pivot(index="slot5",columns="reduced_link_id",values="final_tt_sec").reindex(index=range(288),columns=order).to_numpy()
        physics = PhysicsMobilityEnergyAdapter()
        def energy(links, elapsed):
            geometry = physics.geometry_for_path(tuple(links),graph.links_by_id)
            return physics.physics.energy_kwh(geometry.physics_mapping(),elapsed)
        for r in commitments:
            route=[graph.links_by_id[k] for k in r["route_link_ids"]]
            if not route or route[0].from_node!=graph.service_to_road_node[r["origin_service_id"]] or route[-1].to_node!=graph.service_to_road_node[r["destination_service_id"]] or any(x.to_node!=y.from_node for x,y in zip(route,route[1:])):
                raise ReplayError("FROZEN_ROUTE_ORIGIN_DESTINATION_IDENTITY_MISMATCH")
            result = traverse(r["route_link_ids"],r["departure_slot"],order,array,energy,connection_delay_seconds=CONNECTION_DELAY_SECONDS)
            moves.append({**result,"mess_id":r["mess_id"],"origin_service_id":r["origin_service_id"],
                "destination_service_id":r["destination_service_id"],
                "frozen_route_SHA": digest(r["route_link_ids"]), "physics_contract_SHA":physics.physics_contract_sha,
                "route_origin_destination_identity":"PASS","frozen_command_source":source,
                "actual_traffic_source":daily["source"],"route_graph_SHA":graph.route_graph_sha})
    result = replay_commands(rows,moves,initial_energy,initial_locations=initial_locations,capacity_kwh=CAPACITY_KWH)
    independent=audit_mess(rows,moves,result["trajectory"],initial_energy,initial_states)
    frame = pd.DataFrame(result["trajectory"])
    frame["physical_location"]=frame.actual_service_id.where(frame.connected,"TRANSIT_OR_CONNECTION_DELAY")
    ids = sorted(MESS_INITIAL)
    def values(field):
        return frame.pivot(index="slot",columns="mess_id",values=field).reindex(columns=ids).to_numpy()
    locations = values("actual_service_id").astype(object)
    locations[locations==None] = "TRANSIT_UNAVAILABLE"  # noqa: E711
    return {"p":values("P_EXEC"),"q":values("Q_EXEC"),"locations":locations.astype(str),"ids":ids,
        "frame":frame,"moves":moves,"counters":result["counters"],"frozen_commands_SHA":result["frozen_commands_SHA"],
        "initial_states":initial_states,"audit":independent,"frozen_commands":rows,"initial_energy":initial_energy}
