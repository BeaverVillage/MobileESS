"""B2-only clean Actual replay. Frozen DA clocks; causal mobility; original QSAFE V2."""
import sys,os
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import json,hashlib,time,math,copy,importlib.util,csv,traceback
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import availability_gating as gating

H=Path(__file__).absolute().parent
W=H.parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
F=ROOT/'frozen_artifacts'
OLD=W/'IEEE8500_actual_20260912_r3'
PRIOR=W/'IEEE8500_B2_actual_availability_gating_20260912'
spec=importlib.util.spec_from_file_location('frozen_actual_backend',OLD/'actual8500.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
backend.H=H;backend.W=W
read,save,sha,rec=backend.read,backend.save,backend.sha,backend.rec
DA=None

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def snapshot(p):
    p=Path(p);r=rec(p);r['mtime_ns']=p.stat().st_mtime_ns;return r
def csvout(name,rows):
    with (H/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['no_events'])
        writer.writeheader();writer.writerows(rows)
def b2_selected():
    b0=read(W/'IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json')
    b2=read(W/'IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json')
    assert b0['status']==b2['status']=='PASS'
    assert len(b0['jobs'])==708 and len(b2['final_slots'])==384
    return {'B2':(b0['jobs'],b2['final_slots'])}

def freeze():
    assert not (H/'RULE_FREEZE.json').exists()
    refs={}
    for r in read(PRIOR/'RULE_FREEZE.json')['source_files']:
        assert sha(r['path'])==r['sha256'],r['path']
        refs[str(Path(r['path']).resolve())]=snapshot(r['path'])
    for p in list(H.glob('*.py'))+list(PRIOR.glob('*.json'))+list((ROOT/'pfr').glob('*.py'))+[
        ROOT/'pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json',ROOT/'dayahead/paper_analysis/storage.py',
        ROOT/'dayahead/v35/execution.py',ROOT/'dayahead/v41/actual_dispatch.py',ROOT/'dayahead/mess_physics.py']:
        refs[str(p.resolve())]=snapshot(p)
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    da=MessElectricalAuthority.from_repository();da.validate()
    assert (da.capacity_kwh,da.pcs_kva,da.active_power_limit_kw,da.charge_efficiency,da.discharge_efficiency)==(1200.,400.,300.,.95,.95)
    assert da.energy_min_kwh==440. and da.energy_max_kwh==1080.
    original=read(OLD/'RULE_FREEZE.json')
    rule=dict(status='FROZEN_BEFORE_REGRESSION_AND_B2_EXECUTION',rule='REALIZED_MOBILITY_CAUSAL_AVAILABILITY_GATING',revision=2,
              date='2025-05-21',policies=['B2'],
              DA_command_clock='unchanged: original command at original slot; transit/delay or wrong frozen PCC discards DA P/Q with no later catch-up',
              actual_departure='max(planned_departure_k, previous_move_actual_connection_ready_slot)',
              movement_identity='same vehicle, visit order, origin, destination, frozen route links; no route search',
              traffic='original SUMO realized link TT lookup at 3*actual_departure + floor(elapsed_seconds/300)',
              connection_delay_seconds=600,slot_seconds=900,
              QSAFE='Original robust V2 unchanged: actual physically connected MESS at its ACTUAL PCC; early arrival allowed even when frozen PCC is None. Q-only; P unchanged.',
              QSAFE_vs_DA_gate='DA command eligibility and QSAFE physical availability are distinct; no QSAFE during actual transit/connection delay',
              battery=dict(capacity_kWh=1200.,minimum_kWh=440.,maximum_kWh=1080.,eta_charge=.95,eta_discharge=.95,dt_h=.25,
                           recurrence='subtract actual travel at actual departure; execute only current-slot P with original physical actuator; no terminal compensation'),
              source_pu=1.04,all_Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF',hard_limits=original['hard_limits'],
              prohibited={k:0 for k in gating.FORBIDDEN},
              gate='IEEE123 124 policy-days baseline exact identity plus original final QSAFE physical-eligibility compatibility before B2',
              historical_strict_gate=rec(PRIOR/'GATE_RESULT.json'),historical_collision=rec(OLD/'B2/ACTUAL_INPUT_FAILURE.json'),
              original_Actual_rule=rec(OLD/'RULE_FREEZE.json'),original_backend=rec(OLD/'actual8500.py'),
              unchanged_QSAFE_function_bindings=original['function_bindings'],
              backend_reuse='Original inputs/job replay/power model/Electrical/continuous/run_policy functions imported byte-exact; selected policies restricted to B2; new mobility and independent battery audit callbacks only.',
              source_files=list(refs.values()),frozen_at=datetime.now(timezone.utc).isoformat())
    save(H/'RULE_FREEZE.json',rule);save(H/'RULE_FREEZE_SHA256.json',rec(H/'RULE_FREEZE.json'))
    (H/'BATTERY_EFFICIENCY_AUTHORITY.json').write_bytes((OLD/'BATTERY_EFFICIENCY_AUTHORITY.json').read_bytes())
    print('RULE_FROZEN',sha(H/'RULE_FREEZE.json'),len(refs),flush=True)

def verify_originals():
    backend.verify()
    for r in read(H/'RULE_FREEZE.json')['source_files']:
        assert Path(r['path']).stat().st_mtime_ns==r['mtime_ns'],r['path']

def regression():
    assert not (H/'IEEE123_REGRESSION_GATE.json').exists()
    from dayahead.v40d_actual.mess_replay import project_command
    totals=dict(policy_days=0,moves=0,baseline_record_differences=0,departure_shifts=0,
                final_P_gate_violations=0,final_Q_gate_violations=0,QSAFE_availability_mask_differences=0)
    rows=[];early=[]
    for auth in read(F/'v41r4_restoration_revision_v1/FINAL_AUDIT.json')['rows']:
        day,policy=auth['day'],auth['policy'];p=(F/'v41r4_revision_monitor_view/replays'/day/policy).resolve()
        saved=read(p.parents[2]/'common_inputs'/day/policy/'ACTUAL_MESS_AUDIT.json')
        initial={s['vehicle_id']:s['frozen_initial_location'] for s in saved['initial_states']}
        oldmoves={(m['mess_id'],m['departure_slot']):m for m in saved['moves']}
        def unchanged(c,departure):
            assert departure==c['departure_slot']
            return oldmoves[c['mess_id'],departure]
        moves=gating.realize_sequence(saved['frozen_commands'],initial,unchanged)
        replay=gating.replay(saved['frozen_commands'],moves,saved['initial_energy'],initial,project_command,
                             capacity_kwh=1200.,e_min=440.,e_max=1080.,pcs_kva=400.,eta_charge=.95,eta_discharge=.95,dt_hours=.25)
        stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_ACTUAL'
        finalstage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
        baseline=read(p/stage/'ACTUATOR.json')['trajectory'];final=read(p/finalstage/'ACTUATOR.json')['trajectory']
        assert len(baseline)==len(final)==len(replay['trajectory'])==384
        by={(r['mess_id'],r['slot']):r for r in replay['trajectory']};gate={(r['mess_id'],r['slot']):r for r in replay['availability']}
        differences=[(r['mess_id'],r['slot']) for r in baseline if by[r['mess_id'],r['slot']]!=r]
        local=dict(day=day,policy=policy,moves=len(moves),baseline_differences=len(differences),
                   departure_shifts=sum(m['departure_shift_slots']>0 for m in moves),P_gate_violations=0,Q_gate_violations=0,QSAFE_mask_changes=0)
        for old in final:
            ga=gate[old['mess_id'],old['slot']]
            local['P_gate_violations']+=int(not ga['command_eligible'] and old['P_EXEC']!=0)
            local['Q_gate_violations']+=int(not ga['qsafe_eligible'] and old['Q_EXEC']!=0)
            local['QSAFE_mask_changes']+=int(ga['qsafe_eligible']!=old['connected'])
            if ga['qsafe_eligible'] and not ga['command_eligible']:
                early.append(dict(day=day,policy=policy,mess_id=old['mess_id'],slot=old['slot'],
                                  original_Q_EXEC=old['Q_EXEC'],actual_PCC=old['actual_service_id'],frozen_PCC=old['frozen_service_id'],preserved=True))
        rows.append(local);totals['policy_days']+=1;totals['moves']+=len(moves)
        for k,d in [('baseline_record_differences','baseline_differences'),('departure_shifts','departure_shifts'),
                    ('final_P_gate_violations','P_gate_violations'),('final_Q_gate_violations','Q_gate_violations'),('QSAFE_availability_mask_differences','QSAFE_mask_changes')]:totals[k]+=local[d]
    passed=totals['policy_days']==124 and totals['moves']==95 and all(v==0 for k,v in totals.items() if k not in ('policy_days','moves'))
    result=dict(status='PASS' if passed else 'FAIL_CLOSE',totals=totals,early_arrival_QSAFE_preserved=early,
                proof='All baseline records identical, same actual PCC/physical connected mask and frozen Q target; unchanged original QSAFE algorithm/electrical inputs. Saved final corrections remain admissible. No IEEE123 AC or result regeneration.',
                QSAFE_algorithm_SHA=rec(backend.METHOD/'robust_search.py'),policy_rows=rows)
    save(H/'IEEE123_REGRESSION_GATE.json',result);assert passed,'IEEE123_EQUIVALENCE_GATE_FAILED'
    print('IEEE123_REGRESSION_PASS',totals,flush=True)

class Traffic:
    def __init__(self,repo,day):
        from dayahead.v33m.road_graph_authority import load_road_graph_authority
        from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter
        a=read(Path(repo)/'dayahead/artifacts/v40d_actual_realized_replay/V40D_TRAFFIC_COMPLETENESS.json')
        self.source=next(d['source'] for d in a['days'] if d['day']==day)
        refs=[a['link_order'],*a['geometry_sources']]
        for r in refs+[self.source]:assert sha(r['path'])==r['sha256']
        self.graph=load_road_graph_authority(*(Path(r['path']) for r in refs))
        self.order=pd.read_csv(refs[0]['path']).sort_values('tensor_index').reduced_link_id.astype(str).tolist()
        table=pd.read_parquet(self.source['path'],columns=['slot5','reduced_link_id','final_tt_sec'])
        assert not table.duplicated(['slot5','reduced_link_id']).any()
        self.table=table.set_index(['slot5','reduced_link_id'])
        self.array=table.pivot(index='slot5',columns='reduced_link_id',values='final_tt_sec').reindex(index=range(288),columns=self.order).to_numpy()
        self.physics=PhysicsMobilityEnergyAdapter()
    def geometry(self,links):
        return self.physics.geometry_for_path(tuple(links),self.graph.links_by_id).physics_mapping()
    def energy(self,links,elapsed):return self.physics.physics.energy_kwh(self.geometry(links),elapsed)
    def realize(self,c,departure,source):
        from dayahead.v40d_actual.mess_replay import traverse
        from dayahead.paper_analysis.storage import digest as route_digest
        links=[self.graph.links_by_id[k] for k in c['route_link_ids']]
        assert links and links[0].from_node==self.graph.service_to_road_node[c['origin_service_id']]
        assert links[-1].to_node==self.graph.service_to_road_node[c['destination_service_id']]
        assert all(a.to_node==b.from_node for a,b in zip(links,links[1:]))
        actual=traverse(c['route_link_ids'],departure,self.order,self.array,self.energy,connection_delay_seconds=600)
        return dict(**actual,mess_id=c['mess_id'],origin_service_id=c['origin_service_id'],destination_service_id=c['destination_service_id'],
                    frozen_route_SHA=route_digest(c['route_link_ids']),physics_contract_SHA=self.physics.physics_contract_sha,
                    route_origin_destination_identity='PASS',frozen_command_source=source,actual_traffic_source=self.source,route_graph_SHA=self.graph.route_graph_sha)

def independent_audit(saved,rows,eta,da,q_safety=False):
    """Separate event/energy derivation; never calls gating.replay/project_command/traverse."""
    from dayahead.v41.data import SOURCE_REPO
    from dayahead.mess_physics import pcs_inner_polygon_satisfied
    traffic=Traffic(SOURCE_REPO,'2025-05-21')
    commands={(r['mess_id'],r['slot']):r for r in saved['frozen_commands']}
    actual={(r['mess_id'],r['slot']):r for r in rows}
    assert len(commands)==len(actual)==len(rows)==384 and set(commands)==set(actual)
    plan={(r['mess_id'],r['slot']):r for r in commands.values() if r.get('departure_slot')==r['slot']}
    move_map={(m['mess_id'],m['planned_departure_slot']):m for m in saved['moves']}
    assert len(move_map)==len(saved['moves']) and set(plan)==set(move_map)
    energy_errors=[];vehicles=[]
    for vehicle,initial in sorted(saved['initial_energy'].items()):
        location0=next(s['frozen_initial_location'] for s in saved['initial_states'] if s['vehicle_id']==vehicle)
        pm=sorted([p for p in plan.values() if p['mess_id']==vehicle],key=lambda p:p['slot'])
        ready=0;prev_location=location0;vm=[]
        for order,c in enumerate(pm):
            m=move_map[vehicle,c['slot']];departure=max(c['slot'],ready)
            assert m['actual_departure_slot']==m['departure_slot']==departure
            assert m['frozen_visit_order']==order and m['departure_shift_slots']==departure-c['slot']
            assert c['origin_service_id']==prev_location
            for k in ('route_link_ids','origin_service_id','destination_service_id'):assert m[k]==c[k]
            assert m['actual_traffic_source']==traffic.source
            assert [x['link_id'] for x in m['link_entries']]==c['route_link_ids']
            elapsed=0.
            for e in m['link_entries']:
                step=3*departure+int(elapsed//300);assert step==e['entry_step5']
                seconds=float(traffic.table.loc[(step,e['link_id']),'final_tt_sec']);assert seconds==e['travel_seconds'];elapsed+=seconds
            assert elapsed==m['actual_eta_seconds']
            assert m['actual_arrival_slot']==departure+elapsed/900
            ready=departure+math.ceil((elapsed+600)/900)
            assert ready==m['actual_connection_ready_slot']
            expected_energy=traffic.energy(c['route_link_ids'],elapsed)
            assert abs(expected_energy-m['actual_travel_energy_kWh'])<1e-12
            prev_location=c['destination_service_id'];vm.append(m)
        energy=initial;total_travel=charged=discharged=0.;min_energy=energy;max_energy=energy
        for t in range(96):
            c=commands[vehicle,t];r=actual[vehicle,t]
            arrived=[m for m in vm if m['actual_connection_ready_slot']<=t]
            location=arrived[-1]['destination_service_id'] if arrived else location0
            active=[m for m in vm if m['actual_departure_slot']<=t<m['actual_connection_ready_slot']]
            assert len(active)<=1
            physical=not active;eligible=physical and c['service_id'] is not None and c['service_id']==location
            assert r['connected']==physical and r['actual_service_id']==(location if physical else None)
            travel=sum(m['actual_travel_energy_kWh'] for m in vm if m['actual_departure_slot']==t)
            available=energy-travel;assert da.energy_min_kwh-1e-9<=available<=da.energy_max_kwh+1e-9
            p=0. if not eligible else min(max(c['p_kw'],-max(0.,(da.energy_max_kwh-available)/(.95*.25))),max(0.,(available-da.energy_min_kwh)*.95/.25))
            qlim=math.sqrt(max(0.,da.pcs_kva**2-p*p))
            q=0. if not eligible else min(max(c['q_kvar'],-qlim),qlim)
            if q_safety:
                q=r['Q_EXEC'];assert physical or q==0.
                assert math.hypot(p,q)<=da.pcs_kva+1e-9 and pcs_inner_polygon_satisfied(p,q)
            after=available+.95*max(-p,0)*.25-max(p,0)*.25/.95
            expected=dict(P_CMD=c['p_kw'],Q_CMD=c['q_kvar'],P_EXEC=p,Q_EXEC=q,energy_before_kWh=energy,
                          travel_energy_kWh=travel,energy_after_kWh=after,SoC_before=energy/1200.,SoC_after=after/1200.)
            energy_errors.extend(abs(r[k]-v) for k,v in expected.items())
            assert da.energy_min_kwh-1e-9<=after<=da.energy_max_kwh+1e-9
            total_travel+=travel;charged+=max(-p,0)*.25;discharged+=max(p,0)*.25
            min_energy=min(min_energy,available,after);max_energy=max(max_energy,available,after);energy=after
        assert abs(energy-(initial-total_travel+.95*charged-discharged/.95))<1e-8
        vehicles.append(dict(mess_id=vehicle,initial_energy_kWh=initial,actual_travel_energy_kWh=total_travel,
                             charged_AC_kWh=charged,discharged_AC_kWh=discharged,final_energy_kWh=energy,final_SoC=energy/1200.,
                             min_energy_kWh=min_energy,max_energy_kWh=max_energy,
                             terminal_energy_deviation_from_760_kWh=energy-760.,terminal_compensation=0))
    assert max(energy_errors,default=0)<1e-9,max(energy_errors,default=0)
    return dict(status='PASS',independent_max_error=max(energy_errors,default=0),route_order_vehicle_destination_identity='PASS',
                causal_departure_and_SUMO_entries='PASS',battery_physical_audit='PASS',vehicles=vehicles,
                original_PQ_clock_verified=True,executed_P_unchanged_by_QSAFE=q_safety,forbidden_counters={k:0 for k in gating.FORBIDDEN})

def actual_mobility(repo,binding):
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.v40d_actual.mess_audit import resolve_initial_states
    from dayahead.v40d_actual.mess_replay import project_command
    from dayahead.paper_analysis.storage import digest as storage_digest
    assert binding['day']=='2025-05-21'
    folder=H/'B2';full=read(binding['final_PQ_source'])['MESS_trajectory']
    assert full==b2_selected()['B2'][1]
    allowed=('mess_id','slot','service_id','p_kw','q_kvar','departure_slot','origin_service_id','destination_service_id',
             'route_link_ids','connection_ready_slot','mode','battery_energy_kwh','soc_fraction')
    commands=[{k:c[k] for k in allowed} for c in full]
    initial_energy={c['mess_id']:c['battery_energy_kwh'] for c in commands if c['slot']==0}
    assert len(initial_energy)==4 and set(initial_energy.values())=={760.}
    initial,states=resolve_initial_states(commands,MESS_INITIAL,initial_energy,
        {'D00_trajectory':rec(binding['final_PQ_source']),'energy_contract':rec(ROOT/'dayahead/mess_physics.py')},binding['day'])
    traffic=Traffic(repo,binding['day'])
    moves=gating.realize_sequence(commands,initial,lambda c,d:traffic.realize(c,d,rec(binding['final_PQ_source'])))
    result=gating.replay(commands,moves,initial_energy,initial,project_command,capacity_kwh=1200.,e_min=440.,e_max=1080.,
                         pcs_kva=400.,eta_charge=.95,eta_discharge=.95,dt_hours=.25)
    saved=dict(frozen_commands=commands,moves=moves,initial_energy=initial_energy,initial_states=states)
    save(folder/'CAUSAL_MOBILITY_PRE_AUDIT.json',saved)
    audit=independent_audit(saved,result['trajectory'],dict(eta_charge=.95,eta_discharge=.95),DA)
    frame=pd.DataFrame(result['trajectory']);frame['physical_location']=frame.actual_service_id.where(frame.connected,'TRANSIT_OR_CONNECTION_DELAY')
    ids=sorted(initial_energy)
    def vals(field):return frame.pivot(index='slot',columns='mess_id',values=field).reindex(index=range(96),columns=ids).to_numpy()
    locations=vals('actual_service_id').astype(object);locations[pd.isna(locations)]='TRANSIT_UNAVAILABLE'
    save(folder/'AVAILABILITY_GATE_SLOTS.json',result['availability'])
    by={(c['mess_id'],c['slot']):c for c in full}
    move_rows=[]
    for m in moves:
        c=by[m['mess_id'],m['planned_departure_slot']]
        move_rows.append(dict(mess_id=m['mess_id'],visit_order=m['frozen_visit_order'],origin=m['origin_service_id'],destination=m['destination_service_id'],
                              planned_departure=m['planned_departure_slot'],actual_departure=m['actual_departure_slot'],departure_shift_slots=m['departure_shift_slots'],
                              planned_safe_arrival=c['departure_slot']+c['route_safe_eta_sec']/900,
                              actual_arrival=m['actual_arrival_slot'],planned_connection_ready=c['connection_ready_slot'],actual_connection_ready=m['actual_connection_ready_slot'],
                              actual_eta_seconds=m['actual_eta_seconds'],actual_travel_energy_kWh=m['actual_travel_energy_kWh'],route_links='|'.join(m['route_link_ids'])))
    csvout('B2_MOVE_TIMELINE.csv',move_rows)
    missed=[]
    for ga in result['availability']:
        if ga['missed_nonzero_command']:
            c=by[ga['mess_id'],ga['slot']]
            missed.append(dict(**ga,P_CMD=c['p_kw'],Q_CMD=c['q_kvar'],active_command_kWh=c['p_kw']*.25,reactive_command_kvarh=c['q_kvar']*.25))
    csvout('B2_MISSED_COMMANDS.csv',missed)
    stats=dict(total_moves=len(moves),departure_shift_count=sum(m['departure_shift_slots']>0 for m in moves),
               maximum_departure_shift_slots=max(m['departure_shift_slots'] for m in moves),
               physically_unavailable_vehicle_slots=sum(not ga['physically_connected'] for ga in result['availability']),
               DA_command_ineligible_vehicle_slots=sum(not ga['command_eligible'] for ga in result['availability']),
               missed_nonzero_PQ_vehicle_slots=len(missed),missed_nonzero_P_vehicle_slots=sum(r['P_CMD']!=0 for r in missed),
               missed_nonzero_Q_vehicle_slots=sum(r['Q_CMD']!=0 for r in missed),
               availability_curtailed_active_abs_kWh=sum(abs(r['active_command_kWh']) for r in missed),
               availability_curtailed_reactive_abs_kvarh=sum(abs(r['reactive_command_kvarh']) for r in missed),
               availability_curtailed_discharge_kWh=sum(max(r['active_command_kWh'],0) for r in missed),
               availability_curtailed_charge_kWh=sum(max(-r['active_command_kWh'],0) for r in missed),
               availability_curtailed_active_signed_kWh=sum(r['active_command_kWh'] for r in missed),
               availability_curtailed_reactive_signed_kvarh=sum(r['reactive_command_kvarh'] for r in missed),
               total_baseline_P_command_execution_abs_difference_kWh=sum(abs(r['P_CMD']-r['P_EXEC'])*.25 for r in result['trajectory']),
               total_baseline_Q_command_execution_abs_difference_kvarh=sum(abs(r['Q_CMD']-r['Q_EXEC'])*.25 for r in result['trajectory']),
               count_definition='Vehicle-slots; missed requires nonzero frozen P or Q. Planned transit zero commands are counted unavailable but not missed energy.',
               battery_audit=audit,forbidden_counters=result['counters'])
    save(folder/'MOBILITY_SUMMARY.json',stats)
    return dict(p=vals('P_EXEC'),q=vals('Q_EXEC'),locations=locations.astype(str),ids=ids,frame=frame,
                moves=moves,counters=result['counters'],frozen_commands_SHA=storage_digest(commands),
                initial_states=states,audit=audit,frozen_commands=commands,initial_energy=initial_energy)

def finish():
    complete=read(H/'B2/COMPLETE.json');mob=read(H/'B2/MOBILITY_SUMMARY.json')
    actor=read(H/'B2/FINAL_ACTUAL/ACTUATOR.json');ind=read(H/'B2/CONTINUOUS_VERIFICATION.json')
    assert read(H/'B2/FROZEN_MESS_COMMANDS.json')['MESS_trajectory']==b2_selected()['B2'][1]
    independent=independent_audit(read(H/'B2/ACTUAL_MESS_AUDIT.json'),actor['trajectory'],dict(eta_charge=.95,eta_discharge=.95),DA,q_safety=True)
    save(H/'B2/FINAL_BATTERY_IDENTITY_AUDIT.json',independent)
    a=np.load(H/'B2/ACTUAL_INPUTS.npz');b=np.load(H/'B2/FINAL_ACTUAL/EXECUTION.npz')
    assert np.array_equal(a['P_EXEC'],b['P_EXEC']) and np.array_equal(a['energy_after'],b['energy_after'])
    a.close();b.close()
    verify_originals()
    passed=complete['AC_feasible'] and ind['status']=='PASS' and independent['status']=='PASS' and complete['ROBUST_Q_ONLY_UNRESOLVED_slots']==0
    result=dict(status='PASS' if passed else 'FAIL_CLOSE',policy='B2',date='2025-05-21',rule=rec(H/'RULE_FREEZE.json'),
                regression=rec(H/'IEEE123_REGRESSION_GATE.json'),mobility=mob,summary=complete['summary'],
                QSAFE_intervention_slots=complete['Q_intervention_slots'],QSAFE_unresolved_slots=complete['ROBUST_Q_ONLY_UNRESOLVED_slots'],
                independent_AC_replay=ind,independent_battery_identity_audit=independent,
                executed_P_unchanged_by_QSAFE=True,all_original_frozen_SHA_and_mtime_preserved=True,
                frozen_source_files_verified=len(read(H/'RULE_FREEZE.json')['source_files']),
                runtime_s=complete['runtime_s'],new_B2_Actual_result_only=True,completed_at=datetime.now(timezone.utc).isoformat())
    save(H/'FINAL_ACCEPTANCE.json',result)
    save(H/'FROZEN_IDENTITY_PRESERVATION.json',dict(status='PASS',files=read(H/'RULE_FREEZE.json')['source_files'],all_SHA_and_mtime_unchanged=True))
    s=complete['summary']
    report=['# IEEE8500 B2 Actual — causal availability gating', '',f"**{result['status']}** — B2 Actual만 새로 실행했습니다.",'',
            'DA P/Q clock을 고정하고 unavailable/wrong-PCC command는 버렸습니다. 차량 출발만 실제 available 최초 slot으로 지연했습니다. '
            'QSAFE robust V2는 실제 연결 PCC에서만 작동하며 early arrival을 허용합니다. Executed P는 변경하지 않았습니다.','',
            'IEEE123 regression: 124 policy-days / 95 moves, baseline 기록 차이 0, departure shift 0, QSAFE availability mask 차이 0, 기존 final Q 배제 0 — PASS.','',
            '기존 collision: MESS04 STA08 → IDC05, planned next departure=41, previous actual ready=42. 기존 FAIL-CLOSE evidence는 보존했습니다.','',
            '| 항목 | 결과 |','|---|---:|',
            f"| 이동 수 | {mob['total_moves']} |",f"| departure shift 수 / 최대 slot | {mob['departure_shift_count']} / {mob['maximum_departure_shift_slots']} |",
            f"| 실제 unavailable 차량-slot | {mob['physically_unavailable_vehicle_slots']} |",
            f"| nonzero missed P/Q 차량-slot | {mob['missed_nonzero_PQ_vehicle_slots']} |",
            f"| missed P / missed Q 차량-slot | {mob['missed_nonzero_P_vehicle_slots']} / {mob['missed_nonzero_Q_vehicle_slots']} |",
            f"| availability curtailed active energy (absolute kWh) | {mob['availability_curtailed_active_abs_kWh']:.9f} |",
            f"| availability curtailed reactive energy (absolute kvarh) | {mob['availability_curtailed_reactive_abs_kvarh']:.9f} |",
            f"| QSAFE intervention slots | {complete['Q_intervention_slots']} |",
            f"| QSAFE unresolved slots | {complete['ROBUST_Q_ONLY_UNRESOLVED_slots']} |",
            f"| Vmin / Vmax pu | {s['Vmin_pu']:.12f} / {s['Vmax_pu']:.12f} |",
            f"| max phase-line loading pu | {s['max_phase_line_loading_pu']:.12f} |",
            f"| max transformer phase-current pu | {s['max_transformer_phase_current_pu']:.12f} |",
            f"| max transformer winding kVA pu | {s['max_transformer_winding_kva_pu']:.12f} |",
            f"| convergence / controls settled | {s['converged_slots']}/96 / {s['controls_settled_slots']}/96 |",
            f"| independent clean AC replay | {ind['status']} |",'',
            '| MESS | final energy kWh | final SoC |','|---|---:|---:|']
    for v in independent['vehicles']:report.append(f"| {v['mess_id']} | {v['final_energy_kWh']:.9f} | {v['final_SoC']:.9%} |")
    report+=['','Battery bounds/conservation audit PASS. Terminal SoC를 맞추기 위한 보상 또는 재최적화는 없습니다. '
             'Missed energy는 availability로 버린 원래 DA command의 절대값 적분이며 QSAFE correction과 구분합니다. '
             '순방향/역방향 에너지와 actuator 전체 차이는 B2/MOBILITY_SUMMARY.json에 있습니다.','',
             'Move별 계획/실제 departure·arrival·ready는 B2_MOVE_TIMELINE.csv, missed commands는 B2_MISSED_COMMANDS.csv에 있습니다. '
             '기존 frozen 입력 SHA 및 수정시각 전후 동일. rerouting/route search/destination/vehicle/order 변경, DA/MESS optimization, command time shift, catch-up은 모두 0입니다.','']
    (H/'REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    backend.state(status=result['status'],stage='B2_ACTUAL_FINISHED')
    save(H/'FINAL_SHA256_MANIFEST.json',dict(files=[rec(p) for p in H.rglob('*') if p.is_file() and p.name not in ('FINAL_SHA256_MANIFEST.json','run.stdout.log','run.stderr.log','PROCESS.json')]))
    print('FINAL_B2_ACCEPTANCE',json.dumps(dict(status=result['status'],summary=result['summary'],mobility={k:v for k,v in mob.items() if k!='battery_audit'})),flush=True)

def main():
    global DA
    if sys.argv[1:]==['freeze']:freeze();return
    assert sys.argv[1:]==['run']
    assert not (H/'EXECUTION_STARTED.json').exists(),'NO_AUTOMATIC_RESTART'
    verify_originals();backend.protect()
    import gurobipy as gp
    gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DA_MESS_OPTIMIZATION_FORBIDDEN'))
    save(H/'EXECUTION_STARTED.json',dict(pid=os.getpid(),started=time.time(),rule=rec(H/'RULE_FREEZE.json')))
    backend.state(status='RUNNING',stage='IEEE123_REGRESSION_GATE')
    regression();verify_originals()
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    DA=MessElectricalAuthority.from_repository();DA.validate()
    ns=backend.kernel();ns['independent_audit']=independent_audit
    backend.selected=b2_selected
    import dayahead.v40d_actual.mobility_inputs as mi
    mi.actual_mobility=actual_mobility
    backend.inputs(ns)
    assert (H/'B2/INPUT_READY.json').exists()
    assert not any((H/p).exists() for p in ('B0','B1','B3'))
    backend.run_policy('B2',ns,DA)
    finish()

if __name__=='__main__':
    try:main()
    except BaseException as e:
        save(H/'TECHNICAL_FAILURE.json',dict(status='FAIL_CLOSE',error=repr(e),traceback=traceback.format_exc()))
        backend.state(status='FAIL_CLOSE',stage='STOPPED',error=repr(e));raise
