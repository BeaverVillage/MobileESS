from copy import deepcopy
import pytest
from dayahead.v40d_actual.mess_audit import resolve_initial_states,audit_mess
from dayahead.v40d_actual.mess_replay import replay_commands
from dayahead.v40d_actual.contracts import ReplayError


def commands(departure=None,initial="S"):
    return [{"mess_id":"m","slot":t,"service_id":initial if departure is None or t<departure else None if t==departure else "T",
        "p_kw":0.,"q_kvar":0.,"mode":"TRANSIT" if t==departure else "CONNECTED",
        "departure_slot":departure if departure is not None and t==departure else None,
        "origin_service_id":"S" if t==departure else None,"destination_service_id":"T" if t==departure else None,
        "route_link_ids":["edge1"] if t==departure else []} for t in range(96)]


def resolve(rows):
    return resolve_initial_states(rows,{"m":"S"},{"m":760.},"frozen-test-source","2025-05-01")


def test_connected_D00_preserves_location_not_route_origin():
    rows=commands(None,initial="T");rows[0]["origin_service_id"]="S"
    locations,states=resolve(rows)
    assert locations["m"]=="T" and states[0]["state_at_D00"]=="STAY_CONNECTED_AT_D00"


def test_departure_exact_D00_origin_identity():
    locations,states=resolve(commands(0))
    assert locations["m"]=="S" and states[0]["state_at_D00"]=="DEPARTURE_EXACTLY_D00"
    bad=commands(0);bad[0]["origin_service_id"]="WRONG"
    with pytest.raises(ReplayError,match="ORIGIN_IDENTITY"):
        resolve(bad)


def test_departure_later_keeps_D00_location_and_start_slot():
    rows=commands(5);loc,states=resolve(rows)
    moves=[{"mess_id":"m","departure_slot":5,"actual_connection_ready_slot":6,"origin_service_id":"S",
        "destination_service_id":"T","route_link_ids":["edge1"],"actual_travel_energy_kWh":1.}]
    x=replay_commands(rows,moves,{"m":760.},initial_locations=loc)
    assert all(r["actual_service_id"]=="S" for r in x["trajectory"][:5])
    assert x["trajectory"][5]["actual_service_id"] is None
    assert states[0]["state_at_D00"]=="CONNECTED_AT_D00_DEPARTURE_LATER"


def test_transit_before_D00_never_resets_origin_without_authority():
    rows=commands(0);rows[0]["departure_slot"]=-1
    with pytest.raises(ReplayError,match="MISSING_AUTHORITATIVE_D00_TRANSIT_PROGRESS"):
        resolve(rows)


def test_arrived_before_D00_preserves_destination():
    rows=commands(None,initial="T")
    rows[0].update(departure_slot=-3,connection_ready_slot=-1,origin_service_id="S",destination_service_id="T",route_link_ids=["edge1"])
    locations,states=resolve(rows)
    assert locations["m"]=="T" and states[0]["state_at_D00"]=="ARRIVED_BEFORE_D00"


def scenario():
    rows=commands(0)
    rows[1].update(p_kw=10.,q_kvar=20.)
    moves=[{"mess_id":"m","departure_slot":0,"actual_connection_ready_slot":2,"origin_service_id":"S",
        "destination_service_id":"T","route_link_ids":["edge1"],"actual_travel_energy_kWh":3.}]
    loc,states=resolve(rows)
    result=replay_commands(rows,moves,{"m":760.},initial_locations=loc)
    return rows,moves,result,states


def test_delayed_connection_discards_command_no_shift_and_SOC_conserves():
    rows,moves,x,states=scenario()
    assert x["trajectory"][1]["P_EXEC"]==x["trajectory"][1]["Q_EXEC"]==0
    assert x["trajectory"][2]["P_EXEC"]==x["trajectory"][2]["Q_EXEC"]==0
    a=audit_mess(rows,moves,x["trajectory"],{"m":760.},states)
    assert a["SOC_BALANCE_MAX_ERROR"]==0 and a["MESS_COMMAND_NONEXECUTION_COUNT"]==1


def test_independent_SOC_rejects_double_travel_energy_and_state_drift():
    rows,moves,x,states=scenario()
    bad=deepcopy(x["trajectory"]);bad[1]["travel_energy_kWh"]=3.
    with pytest.raises(ReplayError,match="TRAVEL_ENERGY_DOUBLE"):
        audit_mess(rows,moves,bad,{"m":760.},states)
    bad=deepcopy(x["trajectory"]);bad[3]["energy_after_kWh"]+=1
    with pytest.raises(ReplayError,match="SOC_CONSERVATION"):
        audit_mess(rows,moves,bad,{"m":760.},states)


def test_route_and_departure_and_command_identity_mutations_fail():
    rows,moves,x,states=scenario()
    bad=deepcopy(moves);bad[0]["route_link_ids"]=["other"]
    with pytest.raises(ReplayError,match="FROZEN_ROUTE"):
        audit_mess(rows,bad,x["trajectory"],{"m":760.},states)
    bad=deepcopy(x["trajectory"]);bad[2]["P_CMD"]=10.
    with pytest.raises(ReplayError,match="COMMAND_SHIFT"):
        audit_mess(rows,moves,bad,{"m":760.},states)
