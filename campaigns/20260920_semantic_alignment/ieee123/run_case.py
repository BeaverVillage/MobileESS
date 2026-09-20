"""Frozen IEEE123 decisions; isolated causal Actual replay only."""
from bootstrap123 import *
import time,traceback,math
import numpy as np,pandas as pd
from types import SimpleNamespace
from actual_controller import Controller,Limits,ac_feasible


def main(day,policy):
 if (OUT/'ACTIVE_SCOPE.json').exists():
  scope=read(OUT/'ACTIVE_SCOPE.json');assert day in scope['days'] and scope['threads']==4,'OUTSIDE_CURRENT_USER_SCOPE'
 round1='--round1' in sys.argv
 manifest=OUT/('ROUND1_INPUT_AUTHORITY.json' if round1 else 'INPUT_AUTHORITY.json')
 started=time.time();controller_start_sha=sha(OUT/'actual_controller.py')
 if '--case-id' in sys.argv:
  key=sys.argv[sys.argv.index('--case-id')+1]
  scoped=OUT/('MONTHLY_INPUT_AUTHORITY.json' if read(OUT/'ACTIVE_SCOPE.json')['scope']=='FULL_MAY_3DAY_PARALLEL' else 'THREE_DAY_ROUND_INPUT_AUTHORITY.json')
  case=next(c for c in read(scoped)['cases'] if c['case_id']==key)
  round1=case['round']=='1R'
 else:case=next(c for c in read(manifest)['cases'] if (c['day'],c['policy'])==(day,policy))
 folder=OUT/('replays_1round' if round1 else 'replays')/day/policy;folder.mkdir(parents=True,exist_ok=True)
 ci=Path(case['common_inputs']);saved=read(ci/'ACTUAL_MESS_AUDIT.json');ready=read(ci/'READY.json')
 source_snapshot=read(ci/'DA_FRESH_INPUT_SNAPSHOT.json')
 assert all(sha(p)==h for p,h in source_snapshot.items()),'DA_FRESH_AUTHORITY_DRIFT'
 # Native power/electrical modules load immutable forecast authority; no solver.
 import dayahead.v40e.electrical as loader
 def verify_npz(p,**values):
  old=arrays(p);assert set(old)==set(values) and all(np.array_equal(old[k],v) for k,v in values.items())
 loader.write_npz=verify_npz
 loader.write_json=lambda p,v:None if read(p)==json.loads(json.dumps(v)) else (_ for _ in ()).throw(AssertionError('LOADER_JSON_DRIFT'))
 from v41r4_electrical import configure
 print('LOAD_CONTEXT',day,policy,flush=True);ctx=configure(day).load(day)
 from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
 a=MessElectricalAuthority.from_repository();eta=read(OUT/'inherited/BATTERY_EFFICIENCY_AUTHORITY.json')
 assert a.charge_efficiency==a.discharge_efficiency==eta['eta_charge']==eta['eta_discharge']==.95
 limits=Limits(a.active_power_limit_kw,a.pcs_kva,a.energy_min_kwh,a.energy_max_kwh,a.charge_efficiency,a.discharge_efficiency,a.interval_hours,a.pcs_polygon_faces)
 import gurobipy as gp
 gp.Model.optimize=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('PLANNING_OPTIMIZER_FORBIDDEN_IN_ACTUAL'))
 original=pd.read_parquet(ci/'ACTUAL_MESS_TIMESERIES.parquet');ids=sorted(saved['initial_energy'])
 def values(field):return original.pivot(index='slot',columns='mess_id',values=field).reindex(index=range(96),columns=ids).to_numpy()
 connected=values('connected').astype(bool);locations=values('actual_service_id').astype(object)
 locations[pd.isna(locations)]='TRANSIT_UNAVAILABLE';locations=locations.astype(str)
 commands={(r['mess_id'],r['slot']):r for r in saved['frozen_commands']}
 pda=np.array([[commands[mid,t]['p_kw'] for mid in ids] for t in range(96)])
 qda=np.array([[commands[mid,t]['q_kvar'] for mid in ids] for t in range(96)])
 power=arrays(ci/'ACTUAL_AIDC_POWER.npz');ef=pd.read_parquet(ci/'authority/ACTUAL_EXOGENOUS_96.parquet').sort_values('slot')
 exo=dict(timestamps=[t.tz_convert('Etc/GMT-10').isoformat() for t in ef.timestamp],demand_mw=ef.demand_MW.to_numpy(),pv_mw=ef.PV_MW.to_numpy())
 from dayahead.v28r2.electrical_context import source_root,with_realized_background
 from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
 legacy=list(ctx.electrical.legacy_context)
 if legacy[0] is None:legacy[0]={}
 base=SimpleNamespace(legacy_context=tuple(legacy),source_root=source_root(SOURCE_DATA_REPOSITORY),voltage=ctx.electrical.voltage,current=ctx.electrical.current,voltage_path=ctx.electrical.voltage_path,current_path=Path(ctx.electrical.voltage_path).with_name(f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'))
 actual=with_realized_background(SOURCE_DATA_REPOSITORY,base,timestamps_96=exo['timestamps'],demand_mw_96=exo['demand_mw'],pv_mw_96=exo['pv_mw'],aidc_plan_kw_96x12=power['PCC_P'])
 from dayahead.v28r2.trajectory import FrozenTrajectory
 from dayahead.v40e.mapping import corrected_mapping,NativeAllocation
 from dayahead.v40d_actual.grid_replay import replay
 from dayahead.v28r2 import opendss_backend as backend
 tr=FrozenTrajectory(day,'ACTUAL',policy,power['PCC_P'].copy(),power['PCC_Q'].copy(),np.zeros_like(pda),np.zeros_like(qda),tuple(ids),locations.copy(),ready['identity'])
 old_alloc=NativeAllocation.allocate;allocation_cache={}
 def allocate(self,p,q):
  key=(id(p),id(q))
  if key not in allocation_cache:allocation_cache[key]=(p,q,old_alloc(self,p,q))
  return allocation_cache[key][2]
 NativeAllocation.allocate=allocate
 control=Controller(limits,[saved['initial_energy'][mid] for mid in ids],robust_search.correct_slot)
 # Travel physics/route/availability are immutable. Reserve known DA safe
 # energy at departure; reveal realized energy only when arrival is observed.
 da_commands=read(Path(case['dayahead'])/'FROZEN_MESS_COMMANDS.json')['MESS_trajectory']
 da_by={(r['mess_id'],r['slot']):r for r in da_commands};reservations={};travel_evidence=[]
 events=[];rows=[];physical_energy=[];trial_failures=[]
 with corrected_mapping():
  engine=cached_engine.CachedPrefixEngine(actual,ctx.electrical.voltage,tr,folder)
  line_mask=np.array([not b.branch_id.startswith('transformer.') for b in engine.branches])
  for t in range(96):
   travel=np.zeros(len(ids))
   for move in saved['moves']:
    mid=move['mess_id'];j=ids.index(mid);dep=move['departure_slot'];key=(mid,dep)
    if dep==t:
     reserve=float(da_by[mid,dep].get('energy_safe_kwh',0.));reservations[key]=reserve;travel[j]+=reserve
     travel_evidence.append(dict(slot=t,vehicle=mid,kind='FROZEN_FORECAST_TRAVEL_RESERVATION',kwh=reserve,Actual_traffic_reads=0))
    if move['actual_connection_ready_slot']==t:
     assert max(e['entry_step5'] for e in move['link_entries'])<=t*3
     realized=float(move['actual_travel_energy_kWh']);travel[j]+=realized-reservations.pop(key)
     travel_evidence.append(dict(slot=t,vehicle=mid,kind='OBSERVED_ARRIVAL_ENERGY_SETTLEMENT',actual_trip_kwh=realized,max_traffic_step_observed=max(e['entry_step5'] for e in move['link_entries'])))
   template=None
   def evaluate(p,q):
    nonlocal template
    tr.mess_p_kw[t]=p
    try:r=engine.evaluate(t,q)
    except (AssertionError,Exception) as error:
     # Only numerical nonconvergence is an infeasible trial. Do not suppress
     # authority, native-state, readback or other programming errors.
     if not any(s in str(error) for s in ('NONCONVERGENCE','does not converge','Max Control Iterations')):raise
     trial_failures.append(dict(slot=t,P=np.asarray(p).tolist(),Q=np.asarray(q).tolist(),error=repr(error)))
     if template is None:
      r=dict(v=np.ones(len(engine.nodes)),ia=np.zeros(len(engine.branches)),ipu=np.zeros(len(engine.branches)),kva=np.zeros(len(engine.branches)),losses=np.zeros(2),taps=engine.accepted_taps[-1] if t else ctx.electrical.voltage['regulator_taps'][0].tolist(),caps=ctx.electrical.voltage['capacitor_states'][t].tolist(),converged=False)
     else:r={**template,'converged':False}
     r={**r,'v':np.full_like(r['v'],.90),'ipu':np.full_like(r['ipu'],2.)}
    if r['converged']:template=r
    return r
   p,q,r,event=control.step(slot=t,p_da=pda[t],q_da=qda[t],connected=connected[t],travel_energy=travel,evaluate=evaluate,allow_correct=policy in ('B2','B3'))
   tr.mess_p_kw[t]=p;tr.mess_q_kvar[t]=q;engine.accepted_taps.append(r['taps']);rows.append(r);events.append(event)
   physical_energy.append(control.energy.copy())
   save(folder/'PROGRESS.json',dict(status='RUNNING',day=day,policy=policy,stage='Q_FIRST_MINIMAL_P_CAUSAL_RECOVERY',slots_complete=t+1,pid=os.getpid(),elapsed_seconds=time.time()-started,Q_interventions=sum(e['Q_intervention'] for e in events),P_interventions=sum(e['P_intervention'] for e in events),exact_rho_so_far=max(float(row['ipu'][line_mask].max()) for row in rows),rho_scope='ACCEPTED_ACTUAL_PREFIX; final requires independent 96-slot verification',updated_at=time.time()))
   if t%8==0:print('SLOT',day,policy,t,'AC',event['AC_PASS'],'P',event['P_intervention'],flush=True)
  result=engine.result(rows,time.time()-started)
 # Independent uninterrupted replay of the accepted P/Q trajectory.
 verify=folder/'CONTINUOUS_VERIFICATION';verify.mkdir(exist_ok=True)
 mess=dict(p=tr.mess_p_kw,q=tr.mess_q_kvar,ids=ids,locations=locations)
 with corrected_mapping():validation,binding=replay(SOURCE,day,policy,ctx,power,exo,mess,ready['identity'],verify)
 v_error=float(np.max(np.abs(validation.voltage_pu-result.voltage_pu)));i_error=float(np.max(np.abs(validation.phase_current_loading_pu-result.phase_current_loading_pu)))
 assert max(v_error,i_error)<1e-9 and np.array_equal(validation.regulator_taps,result.regulator_taps),'ACCEPTED_CONTINUOUS_REPLAY_MISMATCH'
 zold=arrays(Path(case['old_grid'])/'OPENDSS_PHASE_ARRAYS.npz')
 regression=dict(Vmax_absolute_difference=float(np.max(np.abs(validation.voltage_pu-zold['voltage_pu']))),current_loading_max_absolute_difference=float(np.max(np.abs(validation.phase_current_loading_pu-zold['phase_current_loading_pu']))))
 if policy in ('B0','B1'):assert max(regression.values())<1e-9,'B0_B1_REGRESSION_FAILED'
 assert np.array_equal(tr.pcc_p_kw,power['PCC_P']) and np.array_equal(tr.mess_locations_96x4,locations)
 assert all(sha(p)==h for p,h in source_snapshot.items())
 # Independent SOC recurrence from persisted execution and causal reservations.
 e=np.array([saved['initial_energy'][mid] for mid in ids],float);error=0.
 for t,event in enumerate(events):
  e=e-np.asarray(event['travel_energy_kwh'])+a.charge_efficiency*np.maximum(-tr.mess_p_kw[t],0)*a.interval_hours-np.maximum(tr.mess_p_kw[t],0)*a.interval_hours/a.discharge_efficiency
  error=max(error,float(np.max(np.abs(e-np.asarray(event['energy_after_kwh'])))))
 assert error<1e-9
 np.savez_compressed(folder/'EXECUTION.npz',P_EXEC=tr.mess_p_kw,Q_EXEC=tr.mess_q_kvar,PCC_P=tr.pcc_p_kw,PCC_Q=tr.pcc_q_kvar,locations=locations,energy_after=np.array(physical_energy))
 save(folder/'EVENTS.json',events);save(folder/'TRAVEL_CAUSAL_LEDGER.json',travel_evidence);save(folder/'REJECTED_NUMERICAL_TRIALS.json',trial_failures)
 old=read(Path(case['old_grid'])/'OPENDSS_SUMMARY.json')
 summary=dict(status='COMPLETE',day=day,policy=policy,old_Actual_rho=old['rho_max_AC'],new_Actual_rho=validation.summary['rho_max_AC'],
  Q_interventions=sum(e['Q_intervention'] for e in events),P_interventions=sum(e['P_intervention'] for e in events),
  max_abs_delta_P_DA=float(np.max(np.abs(tr.mess_p_kw-pda))),max_abs_corrective_delta_P=float(np.max(np.abs([e['corrective_delta_P'] for e in events]))),
  energy_recovery_kwh=float(sum(np.sum(np.maximum(-np.array(e['recovery_P']),0))*a.charge_efficiency*a.interval_hours for e in events)),
  final_energy_deviation_from_causal_baseline=events[-1]['energy_deviation_kwh'],terminal_energy_kwh=e.tolist(),
  AC_PASS=not validation.summary['physical_violation'],summary=validation.summary,regression=regression,controller_SHA=sha(OUT/'actual_controller.py'),
  runtime_seconds=time.time()-started,threads=4,independent_energy_audit_error=error,continuous_replay_max_error=max(v_error,i_error),
  Planning_Fresh_preserved=True,Planning_optimizer_calls=0,future_Actual_exposure=0,outstanding_travel_reservations=str(reservations))
 assert sha(OUT/'actual_controller.py')==controller_start_sha,'CONTROLLER_CHANGED_DURING_EXECUTION'
 summary.update(case_id=case.get('case_id'),round=case.get('round','1R' if round1 else '2R' if policy=='B3' else 'COMMON'),input_common_directory=str(ci),decision_sha256=case['decision_sha256'])
 save(folder/'COMPLETE.json',summary);env.save_audit(folder/'IO_AUDIT.json')
 print('COMPLETE',json.dumps(summary),flush=True)

if __name__=='__main__':
 try:main(sys.argv[1],sys.argv[2])
 except BaseException as exc:
  save(OUT/'failures'/f'{sys.argv[1]}_{sys.argv[2]}_{time.time_ns()}.json',dict(error=repr(exc),traceback=traceback.format_exc()))
  raise
