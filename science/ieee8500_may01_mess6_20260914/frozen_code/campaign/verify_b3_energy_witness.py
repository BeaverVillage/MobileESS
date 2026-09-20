"""Independent arithmetic and frozen mobility-energy verification; no controls change."""
from bootstrap import *
from dayahead.v41.data import SOURCE_REPO
from dayahead.v33m.road_graph_authority import load_road_graph_authority
from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter
R=H/'b3_actual_energy_diagnostic_20260914_v2'
w=read(R/'FAILURE_WITNESS.json');inputs=read(R/'REPLAY_INPUTS.json')
da=next(c for c in read(H/'B3/FINAL_AUTHORITY.json')['trajectory_slots'] if c['mess_id']==w['vehicle'] and c['slot']==w['slot'])
refs=read(SOURCE_REPO/'dayahead/artifacts/v40d_actual_realized_replay/V40D_TRAFFIC_COMPLETENESS.json')
graph=load_road_graph_authority(*(Path(r['path']) for r in [refs['link_order'],*refs['geometry_sources']]))
physics=PhysicsMobilityEnergyAdapter()
geometry=physics.geometry_for_path(tuple(da['route_link_ids']),graph.links_by_id)
move=w['starting'][0]
elapsed=sum(e['travel_seconds'] for e in move['link_entries'])
actual=physics.physics.energy_kwh(geometry.physics_mapping(),elapsed)
nominal,safe=physics.route_energy_kwh(geometry,da['route_q10_eta_sec'],da['route_q50_eta_sec'],da['route_q90_eta_sec'])
assert abs(actual-move['actual_travel_energy_kWh'])<1e-12
assert abs(safe-da['energy_safe_kwh'])<1e-12
energy=inputs['initial_energy'][w['vehicle']]
for row in w['prior_vehicle_rows']:
    x=row['result'];p=x['P_EXEC'];energy=energy-x['travel_energy_kWh']+.95*max(-p,0)*.25-max(p,0)*.25/.95
assert abs(energy-w['energy_before'])<1e-12
available=energy-actual;shortfall=440.-available
assert shortfall>1e-9 and abs(shortfall-w['energy_shortfall'])<1e-12
summary=dict(status='B3_ACTUAL_PHYSICAL_ENERGY_INFEASIBLE',independent_verification='PASS',vehicle=w['vehicle'],slot=w['slot'],display_slot=w['slot']+1,route=f"{da['origin_service_id']} -> {da['destination_service_id']}",energy_before_kWh=energy,planned_safe_energy_kWh=safe,actual_travel_energy_kWh=actual,available_after_travel_kWh=available,minimum_kWh=440.,shortfall_kWh=shortfall,shortfall_Wh=1000*shortfall,hard_tolerance_kWh=1e-9,excess_over_tolerance=shortfall/1e-9,planned_q10_seconds=da['route_q10_eta_sec'],actual_seconds=elapsed,actual_minus_q10_seconds=elapsed-da['route_q10_eta_sec'],departure_shift_slots=move['departure_shift_slots'],connection_ready_unchanged=move['actual_connection_ready_slot']==da['connection_ready_slot'],M1='PASS',A1_continuous_seconds=14400,MF='PASS',Actual_AC='NOT_STARTED',QSAFE_calls=0,new_scheduling_optimization_calls=0,controls_changed=False,physical_limits_changed=False,prior_vehicles_completed=sorted(set(x['mess_id'] for x in inputs['commands'])-{w['vehicle']}),reason='Actual route time is below the forecast q10; frozen nonlinear physics gives travel energy above max(q10,q50,q90) DA energy_safe. MESS06 departs with only that forecast-safe reserve.')
save(R/'INDEPENDENT_VERIFICATION.json',summary)
save(R/'FINAL_SHA.json',dict(files=[record(p) for p in R.iterdir() if p.is_file() and p.name!='FINAL_SHA.json']+[record(H/'B3/FINAL_AUTHORITY.json'),record(H/'B3_M1/FINAL_AUTHORITY.json'),record(H/'FOUR_HOUR_A1_INCUMBENT.json'),record(H/'DEADLINE_ENFORCEMENT.json'),record(Path(__file__)),record(H/'actual_B3/B3/FROZEN_MESS_COMMANDS.json'),record(H/'actual_binding.py'),record(H/'availability_gating.py'),record(ROOT/'dayahead/v40d_actual/mess_replay.py'),record(physics.contract_path)]))
print(summary)
