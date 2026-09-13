"""Frozen-clock command gating; independent vehicle availability clock.

No optimizer, route search, electrical engine, or filesystem writes here.
The realization callback must traverse frozen links using realized link-entry times.
"""
import copy

FORBIDDEN = ('actual_rerouting', 'route_search', 'destination_change', 'vehicle_substitution',
             'visit_order_change', 'DA_reoptimization', 'MESS_optimization',
             'command_time_shifting', 'missed_energy_catch_up')

def realize_sequence(commands, initial_locations, realize):
    """realize(command, actual_departure) returns actual ETA/ready/energy evidence."""
    moves = []
    for vehicle in sorted(initial_locations):
        planned = sorted((c for c in commands if c['mess_id'] == vehicle
                          and c.get('departure_slot') == c['slot']), key=lambda c:c['slot'])
        previous_ready = 0
        location = initial_locations[vehicle]
        for order, command in enumerate(planned):
            assert command['origin_service_id'] == location, 'FROZEN_VISIT_ORIGIN_CHAIN_MISMATCH'
            planned_departure = command['departure_slot']
            departure = max(planned_departure, previous_ready)
            actual = copy.deepcopy(realize(copy.deepcopy(command), departure))
            assert actual['departure_slot'] == departure
            assert actual['actual_connection_ready_slot'] >= departure
            for key in ('route_link_ids', 'origin_service_id', 'destination_service_id', 'mess_id'):
                assert actual[key] == command[key], 'FROZEN_MOVE_IDENTITY_CHANGED'
            actual.update(planned_departure_slot=planned_departure, actual_departure_slot=departure,
                          planned_connection_ready_slot=command['connection_ready_slot'],
                          departure_shift_slots=departure-planned_departure, frozen_visit_order=order)
            previous_ready = actual['actual_connection_ready_slot']
            location = command['destination_service_id']
            moves.append(actual)
    return moves

def command_gate(physically_connected, actual_location, frozen_pcc):
    # Strict interpretation of the user's per-clock-slot P=Q=0 requirement.
    # None means the frozen clock has no service PCC (planned transit/delay).
    return bool(physically_connected and frozen_pcc is not None and actual_location == frozen_pcc)

def qsafe_eligible(physically_connected, actual_location, frozen_pcc):
    # Never undo the required P=Q=0 gating through a later Q correction.
    return command_gate(physically_connected, actual_location, frozen_pcc)

def replay(commands, moves, initial_energy, initial_locations, project_command,
           capacity_kwh=1200., **projection):
    original = copy.deepcopy(commands)
    rows, gate_rows = [], []
    for vehicle in sorted(initial_energy):
        cs = sorted((c for c in commands if c['mess_id']==vehicle),key=lambda c:c['slot'])
        assert [c['slot'] for c in cs] == list(range(96))
        vm = sorted((m for m in moves if m['mess_id']==vehicle),key=lambda m:m['actual_departure_slot'])
        energy = initial_energy[vehicle]
        for c in cs:
            t = c['slot']
            arrived = [m for m in vm if m['actual_connection_ready_slot'] <= t]
            location = arrived[-1]['destination_service_id'] if arrived else initial_locations[vehicle]
            active = [m for m in vm if m['actual_departure_slot'] <= t < m['actual_connection_ready_slot']]
            assert len(active) <= 1, 'OVERLAPPING_ACTUAL_MOVES'
            starting = [m for m in vm if m['actual_departure_slot']==t]
            assert len(starting) <= 1
            if starting:
                assert starting[0]['origin_service_id'] == location
            travel = sum(m['actual_travel_energy_kWh'] for m in starting)
            physical = not active
            allowed = command_gate(physical,location,c['service_id'])
            # Keep the original projection's arithmetic and baseline zero-command behavior.
            blocked_nonzero = physical and not allowed and bool(c['p_kw'] or c['q_kvar'])
            projected = project_command(0. if blocked_nonzero else c['p_kw'],
                                        0. if blocked_nonzero else c['q_kvar'],energy,
                                        connected=physical,travel_energy=travel,**projection)
            if blocked_nonzero:
                projected.update(P_CMD=c['p_kw'],Q_CMD=c['q_kvar'],
                                 P_CURTAILED=c['p_kw'],Q_CURTAILED=c['q_kvar'],
                                 curtailment_reason=['FROZEN_PCC_UNAVAILABLE'])
            if not allowed:
                assert projected['P_EXEC']==projected['Q_EXEC']==0.
            rows.append(dict(mess_id=vehicle,slot=t,frozen_service_id=c['service_id'],
                             actual_service_id=location if physical else None,connected=physical,
                             SoC_before=energy/capacity_kwh,**projected,
                             SoC_after=projected['energy_after_kWh']/capacity_kwh))
            gate_rows.append(dict(mess_id=vehicle,slot=t,physically_connected=physical,
                                  frozen_pcc=c['service_id'],actual_location=location if physical else None,
                                  command_eligible=allowed,qsafe_eligible=qsafe_eligible(physical,location,c['service_id']),
                                  missed_nonzero_command=not allowed and bool(c['p_kw'] or c['q_kvar'])))
            energy = projected['energy_after_kWh']
    assert commands == original, 'FROZEN_COMMAND_MUTATION'
    return dict(trajectory=rows,availability=gate_rows,counters={k:0 for k in FORBIDDEN})
