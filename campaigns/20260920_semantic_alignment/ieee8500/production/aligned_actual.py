"""Aligned Actual only after current Planning/Fresh pass. Shared controller, isolated runtime."""
from bootstrap import *
import ast,math,itertools,traceback,csv
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc
from threadpoolctl import threadpool_limits
from actual_controller import Controller,Limits,ac_feasible
from actual_native import Native,Evaluator
import actual_campaign_current as adapter
import actual_binding as binding
A=P/'Actual';METHOD=P/'actual_method';threadpool_limits(limits=4)

def verify():
 for r in read(A/'RULE_FREEZE.json')['source_files']:assert sha(r['path'])==r['sha256'],('ACTUAL_SOURCE_DRIFT',r['path'])
def choices():
 zero=[dict(mess_id=m,slot=t,service_id=s,p_kw=0.,q_kvar=0.,departure_slot=None,origin_service_id=None,destination_service_id=None,route_link_ids=[],connection_ready_slot=None,mode='CONNECTED',battery_energy_kwh=1520.,soc_fraction=1520/2400) for m,s in binding.fb.INITIAL.items() for t in range(96)]
 out={}
 for policy in ('B0','B1','B2','B3'):
  v=read(P/policy/'ALIGNED_SELECTED.json');out[policy]=(v['jobs'],zero if policy in ('B0','B1') else v['trajectory_slots'])
 return out
def kernel():
 spec=read(METHOD/'METHOD_FREEZE.json');ns=dict(np=np,pd=pd,math=math,itertools=itertools,time=time,minimize=minimize,qmc=qmc,RULES=spec['search'],PAPER_WORDING=spec['paper_facing_wording'],HARD_TOLERANCE=1e-9)
 for file,names in [('qsafe.py',['q_bounds','constraints','feasible']),('robust_search.py',['correct_slot'])]:
  source=METHOD/file;other=P.parent.parent/'IEEE123_ACTUAL_QFIRST_MINP_20260920/inherited'/file;assert sha(source)==sha(other)
  tree=ast.parse(source.read_text(encoding='utf-8'))
  for name in names:
   node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name);exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
 ns['independent_audit']=binding.independent_audit;return ns
def freeze():
 assert not (P/'SEMANTIC_ALIGNMENT_STOP.json').exists()
 gate=read(P/'ALIGNED_PLANNING_GATE.json');assert gate['status']=='PASS' and gate['all_Fresh_PASS']
 assert read(P/'scale_audit/PHYSICAL_SCALE_AUDIT.json')['status']=='PASS'
 native_proof=read(P/'performance_verification/native_forecast/RESULT.json')
 assert native_proof['status']=='PASS' and native_proof['source']['sha256']==sha(P/'actual_native.py'),'NATIVE_REPLAY_EQUIVALENCE_REQUIRED'
 own=sha(P/'actual_controller.py');other=P.parent.parent/'IEEE123_ACTUAL_QFIRST_MINP_20260920/actual_controller.py';assert own==sha(other)==gate['controller']['sha256']
 files=[P/n for n in ('actual_controller.py','actual_native.py','aligned_actual.py','actual_campaign_current.py','electrical_engine.py','actual_binding.py','actual_power_binding.py','availability_gating.py','fleet_binding.py','CODE_DIFF.json','PHYSICAL_SCALE_CONTRACT.json','HEADROOM_AUTHORITY.json','headroom_authority.py','PCC_OVERLAY.dss','PCC_OVERLAY_INVENTORY.json','D1_AEMO_VIC1_FORECAST.json','ALIGNED_PLANNING_GATE.json')]
 files += [METHOD/n for n in ('METHOD_FREEZE.json','qsafe.py','robust_search.py','BATTERY_EFFICIENCY_AUTHORITY.json')]
 files += [P/'performance_verification/native_forecast/RESULT.json']
 files += [Path(r['path']) for r in gate['Actual_inputs']]
 for row in read(P/'CODE_DIFF.json'):files += [Path(row['source']),Path(row['override'])]
 A.mkdir(exist_ok=True)
 if not (A/'RULE_FREEZE.json').exists():save(A/'RULE_FREEZE.json',dict(status='FROZEN_BEFORE_NEW_ACTUAL',day='2025-05-01',physical_scales=read(P/'PHYSICAL_SCALE_CONTRACT.json'),controller_SHA=own,same_controller_source_as_IEEE123=True,algorithm='Q-first -> minimal current-slot delta P -> causal energy recovery',no_fresh_decision_reoptimization=True,source_files=[record(f) for f in sorted(set(files))]))
 verify()
def run_policy(policy,ns,authority):
 started=time.time();folder=A/policy;data=dict(np.load(folder/'ACTUAL_INPUTS.npz'));ids=list(data['ids']);saved=read(folder/'ACTUAL_MESS_AUDIT.json');selected=choices()[policy][1]
 commands={(r['mess_id'],r['slot']):r for r in selected};gates={(r['mess_id'],r['slot']):r for r in saved['availability']}
 pda=np.array([[commands[m,t]['p_kw'] if gates[m,t]['command_eligible'] else 0. for m in ids] for t in range(96)])
 qda=np.array([[commands[m,t]['q_kvar'] if gates[m,t]['command_eligible'] else 0. for m in ids] for t in range(96)])
 a=authority;assert (a.active_power_limit_kw,a.pcs_kva,a.capacity_kwh,a.energy_min_kwh,a.energy_max_kwh,a.initial_energy_kwh,a.terminal_energy_kwh)==(600,800,2400,880,2160,1520,1520)
 fc=read(P/'D1_AEMO_VIC1_FORECAST.json');ef=pd.read_parquet(A/'ACTUAL_EXOGENOUS_96.parquet')
 assert np.max(abs(data['md']-ef.demand_MW.to_numpy()/max(fc['demand_mw_96'])))<1e-12
 assert np.max(abs(data['mpv']-ef.PV_MW.to_numpy()/max(fc['pv_mw_96'])))<1e-12
 # These are fixed input bindings. No controller sees these future rows.
 control=Controller(Limits(a.active_power_limit_kw,a.pcs_kva,a.energy_min_kwh,a.energy_max_kwh,a.charge_efficiency,a.discharge_efficiency,a.interval_hours,a.pcs_polygon_faces),[saved['initial_energy'][m] for m in ids],ns['correct_slot'])
 engine=Evaluator(folder,data);events=[];energy=[];ledger=[];reservations={};rows=[];pp=[];qq=[]
 try:
  for t in range(96):
   travel=np.zeros(len(ids))
   for move in saved['moves']:
    mid=move['mess_id'];j=ids.index(mid);dep=move['actual_departure_slot'];key=(mid,dep)
    if dep==t:
     original=commands[mid,move['planned_departure_slot']];reserve=float(original.get('energy_safe_kwh',0.));reservations[key]=reserve;travel[j]+=reserve
     ledger.append(dict(slot=t,vehicle=mid,kind='FROZEN_FORECAST_TRAVEL_RESERVATION',kwh=reserve,Actual_traffic_reads=0))
    if move['actual_connection_ready_slot']==t:
     entries=move['link_entries'];assert max(e['entry_step5'] for e in entries)<=t*3
     realized=float(move['actual_travel_energy_kWh']);travel[j]+=realized-reservations.pop(key)
     ledger.append(dict(slot=t,vehicle=mid,kind='OBSERVED_ARRIVAL_ENERGY_SETTLEMENT',actual_trip_kwh=realized,max_traffic_step_observed=max(e['entry_step5'] for e in entries)))
   p,q,r,event=control.step(slot=t,p_da=pda[t],q_da=qda[t],connected=data['connected'][t].astype(bool),travel_energy=travel,evaluate=lambda p,q:engine.evaluate(t,p,q),allow_correct=policy in ('B2','B3'))
   engine.accept(p,q,r);events.append(event);rows.append(r);pp.append(p);qq.append(q);energy.append(control.energy.copy())
   event['frozen_DA_P']=[commands[m,t]['p_kw'] for m in ids];event['physical_locations']=data['locations'][t].tolist()
   save(folder/'EVENTS.json',events);progress=dict(status='RUNNING',policy=policy,stage='Q_FIRST_MINIMAL_P_CAUSAL_RECOVERY',slots_complete=t+1,pid=os.getpid(),Q_interventions=sum(e['Q_intervention'] for e in events),P_interventions=sum(e['P_intervention'] for e in events),unresolved=sum(not e['AC_PASS'] for e in events),updated_unix=time.time())
   progress.update(exact_rho_so_far=max(float(row['line'].max()) for row in rows),rho_scope='ACCEPTED_ACTUAL_PREFIX; final requires independent 96-slot verification')
   save(folder/'PROGRESS.json',progress);save(A/'STATUS.json',progress)
   if t%8==0:print('ACTUAL_SLOT',policy,t,event['status'],flush=True)
 finally:engine.close()
 pp=np.array(pp);qq=np.array(qq);axes=read(P/'AXES.json');summary=adapter.outputs(folder/'FINAL_ACTUAL',rows,data,axes)
 # Independently reconstruct the complete accepted prefix in one new engine.
 fresh=Native(folder/'CONTINUOUS_VERIFICATION/runtime',data);independent=[];input_rows=[]
 try:
  for t in range(96):
   independent.append(fresh.apply(t,pp[t],qq[t]));e=fresh.e;maxerr=0.
   for j,r in enumerate(e.loads):
    e.d.Loads.Name(r['load']);maxerr=max(maxerr,abs(e.d.Loads.kW()-.45*data['md'][t]*e.P[j]),abs(e.d.Loads.kvar()-.45*data['md'][t]*e.Q[j]))
    e.d.Generators.Name(f'op8500_pv_{j:04d}');val=e.d.Generators.kW() if e.d.CktElement.Enabled() else 0.;maxerr=max(maxerr,abs(val-.5*e.ratio*data['mpv'][t]*e.P[j]))
   assert maxerr<1e-9,'ACTUAL_PHYSICAL_SCALE_MISMATCH'
   input_rows.append(dict(slot=t,BG_scale=.45,BG_profile=float(data['md'][t]),BG_native_base_kw=float(e.P.sum()),PV_scale=.5,PV_profile=float(data['mpv'][t]),PV_native_base_kw=float(e.ratio*e.P.sum()),AIDC_scale=2.1,AIDC_kw=float(data['PCC_P'][t].sum()),MESS_scale=2.,native_input_readback_error=maxerr))
 finally:fresh.close()
 errors={k:max(float(np.max(abs(x[k]-y[k]))) for x,y in zip(rows,independent)) for k in ('v','line','tx','kva')}
 assert max(errors.values())<1e-9 and all(x['taps']==y['taps'] for x,y in zip(rows,independent)),'CACHED_VS_CONTINUOUS_EXACT_MISMATCH'
 final=adapter.outputs(folder/'CONTINUOUS_VERIFICATION',independent,data,axes)
 assert np.all(np.hypot(pp,qq)<=800+1e-7) and np.max(abs(pp))<=600+1e-7
 assert np.all(np.asarray(energy)>=880-1e-7) and np.all(np.asarray(energy)<=2160+1e-7)
 independent_energy=np.array([saved['initial_energy'][m] for m in ids],dtype=float);energy_error=0.
 for t,event in enumerate(events):
  independent_energy=independent_energy-np.asarray(event['travel_energy_kwh'])+.95*np.maximum(-pp[t],0)*.25-np.maximum(pp[t],0)*.25/.95
  energy_error=max(energy_error,float(np.max(abs(independent_energy-np.asarray(event['energy_after_kwh'])))))
 assert energy_error<1e-9 and not reservations,'CAUSAL_ENERGY_LEDGER_NOT_CLOSED'
 save(folder/'INDEPENDENT_ENERGY_AUDIT.json',dict(status='PASS',maximum_recurrence_error=energy_error,terminal_energy_kwh=independent_energy.tolist(),terminal_deviation_from_causal_baseline=events[-1]['energy_deviation_kwh']))
 if policy=='B2':save(folder/'SLOT30_DIAGNOSTIC.json',dict(slot=30,event=events[30],rho=float(np.max(independent[30]['line'])),Vmin=float(np.min(independent[30]['v'])),Vmax=float(np.max(independent[30]['v'])),physical_scale=dict(BG=.45,AIDC=2.1,MESS=2.,PV=.5)))
 regression=None
 if policy in ('B0','B1'):
  baseline=Native(folder/'B0_B1_REGRESSION/runtime',data)
  try:plain=[baseline.apply(t,data['P_EXEC'][t],data['Q_EXEC'][t]) for t in range(96)]
  finally:baseline.close()
  regression={k:max(float(np.max(abs(x[k]-y[k]))) for x,y in zip(plain,independent)) for k in ('v','line','tx','kva')};assert max(regression.values())<1e-9
 np.savez_compressed(folder/'EXECUTION.npz',P_EXEC=pp,Q_EXEC=qq,PCC_P=data['PCC_P'],PCC_Q=data['PCC_Q'],locations=data['locations'],energy_after=np.array(energy))
 save(folder/'TRAVEL_CAUSAL_LEDGER.json',ledger);save(folder/'PHYSICAL_SCALE_EACH_SLOT.json',dict(status='PASS',slots=input_rows,MESS_rating=read(P/'PHYSICAL_SCALE_CONTRACT.json')['MESS']))
 result=dict(status='COMPLETE',policy=policy,summary=final,AC_PASS=final['AC_feasible'],AC_feasible=final['AC_feasible'],Q_interventions=sum(e['Q_intervention'] for e in events),P_interventions=sum(e['P_intervention'] for e in events),max_abs_delta_P_DA=float(np.max(abs(pp-np.array([e['frozen_DA_P'] for e in events])))),max_abs_corrective_delta_P=float(np.max(np.abs([e['corrective_delta_P'] for e in events]))),energy_recovery_kwh=float(sum(np.sum(np.maximum(-np.asarray(e['recovery_P']),0))*.95*.25 for e in events)),terminal_energy_kwh=energy[-1].tolist(),final_energy_deviation=events[-1]['energy_deviation_kwh'],controller_SHA=sha(P/'actual_controller.py'),continuous_replay_errors=errors,regression=regression,runtime_seconds=time.time()-started,threads=4,source_revision_same_as_IEEE123=True,Actual_future_rows_exposed=0,outstanding_travel_reservations=str(reservations),physical_scale_PASS=True)
 verify();save(folder/'COMPLETE.json',result);return result
def main():
 freeze();protect();adapter.H=A;adapter.selected=choices;adapter.verify=verify
 ns=kernel();binding.install_actual()
 import gurobipy as gp
 gp.Model.optimize=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('PLANNING_OPTIMIZER_FORBIDDEN_IN_ACTUAL'))
 authority=adapter.inputs(ns)
 for policy in ('B0','B1','B2','B3'):
  if not (A/policy/'COMPLETE.json').exists():run_policy(policy,ns,authority)
  else:assert read(A/policy/'COMPLETE.json')['controller_SHA']==sha(P/'actual_controller.py')
  verify()
 results={policy:read(A/policy/'COMPLETE.json') for policy in ('B0','B1','B2','B3')};save(A/'CAMPAIGN_COMPLETE.json',dict(status='COMPLETE',policies=results,all_AC_PASS=all(r['AC_PASS'] for r in results.values()),same_physical_scale=True))
if __name__=='__main__':
 try:main()
 except Exception as e:save(A/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
