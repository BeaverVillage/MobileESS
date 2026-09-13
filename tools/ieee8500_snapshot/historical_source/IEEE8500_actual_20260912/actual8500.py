"""IEEE8500 Actual adapter. Frozen V41R4 dispatch/actuation/Q search; no DA optimizer."""
import os,sys,pathlib,json,hashlib,ast,time,math,itertools,traceback,copy
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
H=Path(__file__).absolute().parent; W=H.parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
METHOD=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(W/'IEEE8500_numerical_preflight_20260911'))
import numpy as np,pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(v):
 if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
 if isinstance(v,(list,tuple,np.ndarray)):return [clean(x) for x in v]
 if isinstance(v,np.generic):return clean(v.item())
 if isinstance(v,float) and not math.isfinite(v):return None
 if isinstance(v,(pd.Timestamp,Path)):return str(v)
 return v
def save(p,x):
 p=Path(p);assert p.absolute().is_relative_to(H)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def rec(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
def state(**x):save(H/'STATUS.json',dict(updated_unix=time.time(),pid=os.getpid(),**x))
def protect():
 def check(p):
  if isinstance(p,(str,bytes,os.PathLike)):
   path=Path(os.path.abspath(os.fsdecode(p)))
   if any(path.is_relative_to(Path(r)) for r in ('C:/codex_mobileess_workspace','D:/codex_mobileess_workspace','D:/ChatGPT','C:/Users/kjw39/OneDrive')) and not (path.is_relative_to(H) or path.is_relative_to(H.resolve())):raise PermissionError('FROZEN_SOURCE_WRITE_BLOCKED: '+str(path))
 def hook(event,args):
  if event=='open':
   p,mode,flags=args
   if (mode and any(c in mode for c in 'wax+')) or (flags and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):check(p)
  elif event in ('os.remove','os.rmdir','os.mkdir'):check(args[0])
  elif event in ('os.rename','os.replace'):check(args[0]);check(args[1])
 sys.addaudithook(hook)
def selected():
 R=W/'IEEE8500_v41r4_production_20260911_r2'; B=W/'IEEE8500_B3_production_20260912'; C=W/'IEEE8500_B2_physical_closure_20260912_r2'
 b0=read(R/'B0/FINAL.json');b1=read(R/'B1/ACCEPTED_AIDC.json');b2=read(C/'B2_RESTORED_ACCEPTANCE.json');b3=read(B/'B3/FINAL_AUTHORITY.json')
 for p in (R/'B0/FINAL.json',R/'B1/FINAL_AUTHORITY.json',C/'B2_RESTORED_ACCEPTANCE.json',B/'B3/FINAL_AUTHORITY.json'):assert read(p)['status']=='PASS'
 assert sha(R/'B1/ACCEPTED_AIDC.json')==read(R/'B1/FINAL_AUTHORITY.json')['decision']['sha256']
 assert sha(C/'B2_RESTORED_ACCEPTANCE.json')==read(B/'PRODUCTION_RULES.json')['B2_required_closure_gate']['sha256']
 assert sha(B/'B3/FINAL_AUTHORITY.json')==read(B/'CAMPAIGN_COMPLETE.json')['B3']['sha256']
 return {'B0':(b0['jobs'],[]),'B1':(b1['jobs'],[]),'B2':(b0['jobs'],b2['final_slots']),'B3':(b3['jobs'],b3['trajectory_slots'])}
FUNCTION_BINDINGS=[]
def original_functions(path,names,namespace):
 tree=ast.parse(Path(path).read_text(encoding='utf-8'))
 for name in names:
  node=next(x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name==name)
  payload=ast.dump(node,include_attributes=False)
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
  FUNCTION_BINDINGS.append(dict(name=name,source=rec(path),unaltered_AST_SHA256=hashlib.sha256(payload.encode()).hexdigest(),body_changes=0))
def kernel():
 spec=read(METHOD/'METHOD_FREEZE.json');assert spec['version']=='V41R4_ACTUAL_ETA95_QSAFE_ROBUST_V2'
 assert sha(METHOD/'robust_search.py')==read(METHOD/'METHOD_CODE_BINDING.json')['files']['robust_search.py']
 ns=dict(np=np,pd=pd,math=math,itertools=itertools,time=time,minimize=minimize,qmc=qmc,RULES=spec['search'],PAPER_WORDING=spec['paper_facing_wording'],HARD_TOLERANCE=1e-9,sha=sha,OUT=H)
 original_functions(METHOD/'frozen_code/qsafe.py',['q_bounds','constraints','feasible'],ns)
 original_functions(METHOD/'robust_search.py',['correct_slot'],ns)
 original_functions(METHOD/'frozen_code/worker.py',['independent_audit'],ns)
 return ns
def freeze():
 assert not (H/'RULE_FREEZE.json').exists(),'RULE_ALREADY_FROZEN'
 selected(); ns=kernel();spec=read(METHOD/'METHOD_FREEZE.json')
 from dayahead.v41.data import SOURCE_REPO
 source=Path(SOURCE_REPO); audit=source/'dayahead/artifacts/v40d_actual_realized_replay'
 files=[Path(__file__),METHOD/'METHOD_FREEZE.json',METHOD/'METHOD_CODE_BINDING.json',METHOD/'EXECUTION_BINDING.json',METHOD/'robust_search.py',METHOD/'frozen_code/worker.py',METHOD/'frozen_code/qsafe.py',METHOD/'BATTERY_EFFICIENCY_AUTHORITY.json']
 for sub in ['v41','v41r1','v40d_actual','v40g_segments','v39a','v33m']:
  files.extend((ROOT/'dayahead'/sub).glob('*.py'))
 files += [ROOT/'dayahead/mess_physics.py',ROOT/'dayahead/v28r2/c1_affine.py',ROOT/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json',audit/'V40D_FROZEN_JOB_OBSERVATIONS.parquet']
 for n in ['V40D_AEMO_COMPLETENESS.json','V40D_WEATHER_COMPLETENESS.json','V40D_TRAFFIC_COMPLETENESS.json']:
  files.append(audit/n)
 a=read(audit/'V40D_AEMO_COMPLETENESS.json');we=read(audit/'V40D_WEATHER_COMPLETENESS.json');tr=read(audit/'V40D_TRAFFIC_COMPLETENESS.json')
 refs=[a['demand']['source'],a['pv']['source'],we['derived'],tr['link_order'],*tr['geometry_sources'],next(x for x in tr['days'] if x['day']=='2025-05-21')['source']]
 for r in refs:assert sha(r['path'])==r['sha256'];files.append(Path(r['path']))
 for directory in ['IEEE8500_scalability_20260910/source','IEEE8500_pcc_overlay_20260911']:
  files.extend(p for p in (W/directory).rglob('*') if p.is_file())
 files += [W/'IEEE8500_stress_calibration_20260911/IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json',W/'IEEE8500_stress_calibration_20260911/overlays/Source_1.0400_Vreg_123.5.dss',W/'IEEE8500_operating_point_20260911/D1_AEMO_VIC1_FORECAST_AUTHORITY.json',W/'IEEE8500_operating_point_20260911/PV_PENETRATION_RATIO_AUTHORITY.json',W/'IEEE8500_numerical_preflight_20260911/AXES.json']
 for folder in ['IEEE8500_numerical_preflight_20260911','IEEE8500_stress_calibration_20260911','IEEE8500_source_grid_compatibility_20260911','IEEE8500_production_compatibility_20260911','IEEE8500_operating_point_20260911','IEEE8500_v41r4_binding_reconstruction_20260911']:files.extend((W/folder).glob('*.py'))
 for folder,subpaths in [('IEEE8500_v41r4_production_20260911_r2',['B0/FINAL.json','B0/exact/AC_VALIDATION.json','B1/ACCEPTED_AIDC.json','B1/FINAL_AUTHORITY.json','B1/final_exact/AC_VALIDATION.json']),('IEEE8500_B2_physical_closure_20260912_r2',['B2_RESTORED_ACCEPTANCE.json','accepted_clean_exact/AC_VALIDATION.json']),('IEEE8500_B3_production_20260912',['B3/FINAL_AUTHORITY.json','B3/final_exact/AC_VALIDATION.json','CAMPAIGN_COMPLETE.json','PRODUCTION_RULES.json'])]:files += [W/folder/p for p in subpaths]
 domain=read(ROOT/'frozen_artifacts/v41r4_may/audit/2025-05-21/domain/DAILY_DOMAIN_AUTHORITY.json')
 for r in [domain['capacity'],domain['rack']]:assert sha(r['path'])==r['sha256'];files.append(Path(r['path']))
 rule=dict(status='FROZEN_BEFORE_ACTUAL_EXECUTION',date='2025-05-21',policies=['B0','B1','B2','B3'],original_Actual_method=rec(METHOD/'METHOD_FREEZE.json'),search=spec['search'],function_bindings=FUNCTION_BINDINGS,source_pu=1.04,all_Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF',AIDC=12,MESS_service_locations=24,MESS_vehicles=4,GPUs=780,DA_schedule_optimizer_calls_allowed=0,ML_prediction_calls_allowed=0,allowed_Actual_control='Original causal Q-only robust V2 for B2/B3; B0/B1 control replay only',MESS_eta_charge=.95,MESS_eta_discharge=.95,background='native_PQ * 0.50 * actual_VIC_demand(t) / frozen_DA_demand_peak; PV native P allocation * 0.50 * frozen penetration ratio * actual_PV(t) / frozen_DA_PV_peak',actual_peak_renormalization=False,forecast_scale_and_error_preserved=True,dayahead_inputs_and_decisions_immutable=True,IEEE123_electrical_results_used=False,allowed_electrical_difference='IEEE8500 topology/PCC/axes/ratings and frozen operating point; replace electrical backend only',causal_trial_rule=spec['trials'],independent_continuous_96_slot_verification=True,hard_limits=spec['hard_limits'],unresolved='Retain original physically executable Q and P, record ROBUST_Q_ONLY_UNRESOLVED; no tuning or P fallback',source_files=[rec(p) for p in sorted(set(files),key=str)],freeze_unix=time.time())
 save(H/'RULE_FREEZE.json',rule);save(H/'RULE_FREEZE_SHA256.json',rec(H/'RULE_FREEZE.json'))
 (H/'BATTERY_EFFICIENCY_AUTHORITY.json').write_bytes((METHOD/'BATTERY_EFFICIENCY_AUTHORITY.json').read_bytes())
 print('RULE_FROZEN',sha(H/'RULE_FREEZE.json'),len(files),flush=True)
def verify():
 assert sha(H/'RULE_FREEZE.json')==read(H/'RULE_FREEZE_SHA256.json')['sha256']
 for r in read(H/'RULE_FREEZE.json')['source_files']:assert sha(r['path'])==r['sha256'],r['path']
def inputs(ns):
 from dayahead.v41.data import SOURCE_REPO,issue_time
 from dayahead.v40d_actual.inputs import observations
 from dayahead.v40d_actual.exogenous import load
 from dayahead.v40d_actual.rack_dispatch import Rack
 from dayahead.v41.actual_dispatch import replay_jobs,power_from_execution,persist
 from dayahead.v38.authority import load_wan_authority
 from dayahead.v41r1.migration import FrozenWanView
 from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
 from dayahead.v40d_actual.mess_replay import replay_commands
 import dayahead.v40d_actual.mobility_inputs as mobility
 da=MessElectricalAuthority.from_repository();da.validate();assert (da.capacity_kwh,da.pcs_kva,da.active_power_limit_kw,da.charge_efficiency,da.discharge_efficiency)==(1200,400,300,.95,.95)
 domain=read(ROOT/'frozen_artifacts/v41r4_may/audit/2025-05-21/domain/DAILY_DOMAIN_AUTHORITY.json');cap=read(domain['capacity']['path'])['site_capacity'];rk=read(domain['rack']['path']);assert sum(cap.values())==780
 racks=[Rack(r['aidc_id'],r['rack_pool_id'],r['compatibility_GPU_limit']) for r in rk['logical_Rack_pools']];wan=FrozenWanView(load_wan_authority(ROOT))
 state(status='RUNNING',stage='ACTUAL_EXOGENOUS_INPUTS',policies_complete=[])
 exo=load(SOURCE_REPO,'2025-05-21');obs=observations(Path(SOURCE_REPO)/'dayahead/artifacts/v40d_actual_realized_replay')
 forecast=read(W/'IEEE8500_operating_point_20260911/D1_AEMO_VIC1_FORECAST_AUTHORITY.json')
 df=exo['weather'].reset_index(drop=True).copy();df['slot']=range(96);df['timestamp_start']=exo['timestamps'];df['demand_MW']=exo['demand_mw'];df['PV_MW']=exo['pv_mw'];df['demand_multiplier']=exo['demand_mw']/max(forecast['demand_mw_96']);df['PV_multiplier']=exo['pv_mw']/max(forecast['pv_mw_96'])
 save(H/'ACTUAL_EXOGENOUS_AUTHORITY.json',dict(original=exo['authority'],forecast=rec(W/'IEEE8500_operating_point_20260911/D1_AEMO_VIC1_FORECAST_AUTHORITY.json'),demand_denominator=max(forecast['demand_mw_96']),PV_denominator=max(forecast['pv_mw_96']),alignment='Original V40D Actual reader: demand interval ending +15min, PV +30min repeated twice; weather start timestamp; same slot index as frozen DA intervals'))
 df.to_parquet(H/'ACTUAL_EXOGENOUS_96.parquet',index=False)
 eta=dict(eta_charge=.95,eta_discharge=.95)
 def eta_replay(*a,**k):k.update(e_min=da.energy_min_kwh,e_max=da.energy_max_kwh,pcs_kva=da.pcs_kva,eta_charge=.95,eta_discharge=.95,dt_hours=da.interval_hours);return replay_commands(*a,**k)
 def audit(commands,moves,executed,initial_energy,initial_states):return ns['independent_audit'](dict(frozen_commands=commands,moves=moves,initial_energy=initial_energy,initial_states=initial_states),executed,eta,da)
 mobility.replay_commands=eta_replay;mobility.audit_mess=audit
 for policy,(jobs,commands) in selected().items():
  folder=H/policy;folder.mkdir(exist_ok=True);state(status='RUNNING',stage='ACTUAL_INPUT_REPLAY',policy=policy)
  assert len(jobs)==708 and all(j['operating_day']=='2025-05-21' for j in jobs)
  original=json.dumps(jobs,sort_keys=True);jr=replay_jobs(jobs,obs,issue_time=issue_time('2025-05-21'),site_capacity=cap,racks=racks,wan=wan);assert original==json.dumps(jobs,sort_keys=True)
  save(folder/'ACTUAL_JOB_REPLAY.json',jr);persist(folder,jr,obs,issue_time('2025-05-21'),cap,racks)
  power=power_from_execution(ROOT,jr,cap,exo['weather']);np.savez_compressed(folder/'ACTUAL_AIDC_POWER.npz',**{k:power[k] for k in ('occupancy','IT','PCC_P','PCC_Q')});save(folder/'POWER_AUDIT.json',power['power_audit'])
  save(folder/'FROZEN_MESS_COMMANDS.json',dict(MESS_trajectory=commands))
  mess=mobility.actual_mobility(SOURCE_REPO,dict(day='2025-05-21',case='B3',final_PQ_source=str(folder/'FROZEN_MESS_COMMANDS.json')))
  save(folder/'ACTUAL_MESS_AUDIT.json',{k:v for k,v in mess.items() if k not in ('frame','p','q','locations')});mess['frame'].to_parquet(folder/'ACTUAL_MESS_TIMESERIES.parquet',index=False)
  ids=mess['ids'];frame=mess['frame']
  def vals(field):return frame.pivot(index='slot',columns='mess_id',values=field).reindex(index=range(96),columns=ids).to_numpy()
  np.savez_compressed(folder/'ACTUAL_INPUTS.npz',PCC_P=power['PCC_P'],PCC_Q=power['PCC_Q'],P_EXEC=mess['p'],Q_EXEC=mess['q'],Q_DA=vals('Q_CMD'),locations=mess['locations'],connected=vals('connected'),ids=ids,md=df.demand_multiplier.to_numpy(),mpv=df.PV_multiplier.to_numpy(),energy_after=vals('energy_after_kWh'),SoC_after=vals('SoC_after'))
  save(folder/'INPUT_READY.json',dict(status='PASS',jobs=708,capacity=cap,policy=policy,actual_decision_reoptimization=False,ML_calls=0,frozen_jobs_sha256=hashlib.sha256(original.encode()).hexdigest(),inputs=rec(folder/'ACTUAL_INPUTS.npz'),independent_MESS_audit=mess['audit']))
  print('ACTUAL_INPUT_READY',policy,flush=True)
 verify();save(H/'INPUT_FREEZE_MANIFEST.json',dict(status='PASS',rule=rec(H/'RULE_FREEZE.json'),files=[rec(p) for p in H.rglob('*') if p.is_file() and p.name not in ['STATUS.json','run.stdout.log','run.stderr.log','PROCESS.json']]))
 return da

class Electrical:
 def __init__(self,folder,data):
  from electrical_engine import Engine
  self.e=Engine(folder);self.e.md=data['md'];self.e.mpv=data['mpv'];self.e.ap=data['PCC_P'];self.e.aq=data['PCC_Q'];self.data=data;self.solves=0
 def apply(self,t,q):
  e=self.e;x=np.r_[self.data['PCC_P'][t],np.zeros(48)]
  for j,s in enumerate(self.data['locations'][t]):
   if self.data['connected'][t,j]:
    assert s in e.services;sidx=e.services.index(s);x[12+sidx]+=self.data['P_EXEC'][t,j];x[36+sidx]+=q[j]
   else:assert self.data['P_EXEC'][t,j]==0 and q[j]==0
  e.inputs(t,x);e.solve();self.solves+=1;vv,ll,tt,ss=e.arrays();st=e.state(t)
  v=np.sqrt(vv);line=np.abs(ll);tx=np.abs(tt);kva=np.abs(ss)/e.ax['kva_rating']
  taps=[r['tap_number'] for r in st['regulators']];caps=[c['step_states'] for c in st['capacitors']]
  return dict(v=v,line=line,tx=tx,ipu=np.r_[line,tx],kva=kva,taps=taps,caps=caps,converged=bool(e.d.Solution.Converged() and e.d.Solution.ControlActionsDone()),controls_settled=bool(e.d.Solution.ControlActionsDone()),state=st)
 def close(self):self.e.close()

def summary(rows):
 return dict(Vmin_pu=min(float(r['v'].min()) for r in rows),Vmax_pu=max(float(r['v'].max()) for r in rows),max_phase_line_loading_pu=max(float(r['line'].max()) for r in rows),max_transformer_phase_current_pu=max(float(r['tx'].max()) for r in rows),max_transformer_winding_kva_pu=max(float(r['kva'].max()) for r in rows),voltage_violations=sum(int(((r['v']<.95-1e-9)|(r['v']>1.05+1e-9)).sum()) for r in rows),line_violations=sum(int((r['line']>1+1e-9).sum()) for r in rows),transformer_current_violations=sum(int((r['tx']>1+1e-9).sum()) for r in rows),transformer_kVA_violations=sum(int((r['kva']>1+1e-9).sum()) for r in rows),converged_slots=sum(r['converged'] for r in rows),controls_settled_slots=sum(r['controls_settled'] for r in rows))
def outputs(folder,rows,data,axes):
 folder.mkdir(exist_ok=True,parents=True);sm=summary(rows);sm['AC_feasible']=sm['converged_slots']==96 and sm['controls_settled_slots']==96 and sum(sm[k] for k in ['voltage_violations','line_violations','transformer_current_violations','transformer_kVA_violations'])==0
 save(folder/'AC_SUMMARY.json',dict(validation_scope='REALIZED_OPERATION_AC',**sm))
 np.savez_compressed(folder/'OPENDSS_PHASE_ARRAYS.npz',node_names=axes['nodes'],line_phase_axes=axes['line'],transformer_current_axes=axes['tx'],transformer_kva_axes=axes['winding'],voltage_pu=np.array([r['v'] for r in rows]),line_current_loading_pu=np.array([r['line'] for r in rows]),transformer_current_loading_pu=np.array([r['tx'] for r in rows]),transformer_winding_kva_loading_pu=np.array([r['kva'] for r in rows]),regulator_taps=np.array([r['taps'] for r in rows]))
 save(folder/'CONTROL_STATES.json',[r['state'] for r in rows]);save(folder/'SLOT_EXTREMA.json',[dict(slot=t,Vmin_pu=float(r['v'].min()),Vmin_node=axes['nodes'][int(r['v'].argmin())],Vmax_pu=float(r['v'].max()),Vmax_node=axes['nodes'][int(r['v'].argmax())],max_phase_line_loading_pu=float(r['line'].max()),line_witness=axes['line'][int(r['line'].argmax())],feasible=all([r['converged'],r['v'].min()>=.95-1e-9,r['v'].max()<=1.05+1e-9,r['ipu'].max()<=1+1e-9,r['kva'].max()<=1+1e-9])) for t,r in enumerate(rows)])
 return sm
def continuous(folder,data,q):
 engine=Electrical(folder/'runtime',data);rows=[]
 try:
  for t in range(96):rows.append(engine.apply(t,q[t]))
 finally:engine.close()
 return rows
def run_policy(policy,ns,da):
 folder=H/policy;start=time.time();a=np.load(folder/'ACTUAL_INPUTS.npz');data={k:a[k].copy() for k in a.files};a.close();axes=read(W/'IEEE8500_numerical_preflight_20260911/AXES.json');q=data['Q_EXEC'].copy();state(status='RUNNING',stage='ACTUAL_BASELINE_AC',policy=policy)
 baseline=continuous(folder/'ETA95_ACTUAL',data,q);bs=outputs(folder/'ETA95_ACTUAL',baseline,data,axes)
 accepted=[];events=[];trials=[];engine_count=0;solve_count=0
 if policy in ('B0','B1'):accepted=baseline
 else:
  for t in range(96):
   lo,hi=ns['q_bounds'](data['P_EXEC'][t],data['connected'][t],da);assert np.all(q[t]>=lo-1e-7) and np.all(q[t]<=hi+1e-7)
   def evaluate(qtrial):
    nonlocal engine_count,solve_count
    e=Electrical(folder/'q_trials_runtime',data);engine_count+=1;prior=None
    try:
     for s in range(t+1):
      r=e.apply(s,qtrial if s==t else q[s]);solve_count+=1
      if s<t:
       assert r['taps']==accepted[s]['taps'] and np.array_equal(r['v'],accepted[s]['v']),'ACCEPTED_PREFIX_DRIFT'
       prior=r['taps']
     trials.append(dict(slot=t,Q=qtrial.tolist(),prefix_max_slot=t,engine=engine_count,start_taps=prior,final_taps=r['taps'],Vmin=float(r['v'].min()),Vmax=float(r['v'].max()),feasible=ns['feasible'](r)))
     if engine_count%25==0:state(status='RUNNING',stage='CAUSAL_Q_CORRECTION',policy=policy,slot=t,trial_engines=engine_count,physical_solves=solve_count,elapsed_s=time.time()-start)
     return r
    finally:e.close()
   qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t]);q[t]=qt;accepted.append(r);event.update(slot=t,Q_accepted=qt.tolist(),P_EXEC=data['P_EXEC'][t].tolist());events.append(event)
   save(folder/'Q_CONTROL_EVENTS.json',events);save(folder/'Q_ACCEPTED_CHECKPOINT.json',dict(slots=t+1,Q=q[:t+1],rule_sha=sha(H/'RULE_FREEZE.json')));state(status='RUNNING',stage='ACTUAL_QSAFE',policy=policy,slots_complete=t+1,interventions=sum(x['status']=='Q_CORRECTED' for x in events),unresolved=sum(x['status']=='ROBUST_Q_ONLY_UNRESOLVED' for x in events),trial_engines=engine_count,elapsed_s=time.time()-start)
   if t%8==0 or event['status']!='UNCHANGED':print('ACTUAL_SLOT',policy,t,event['status'],event['evaluations'],flush=True)
  save(folder/'NATIVE_TRIAL_AUDIT.json',dict(trials=trials,clean_engines=engine_count,physical_solves=solve_count,prefix_verified=True,no_future_actual_applied=True))
 final=outputs(folder/'FINAL_ACTUAL',accepted,data,axes)
 independent=continuous(folder/'CONTINUOUS_VERIFICATION',data,q);diff={key:max(float(np.max(np.abs(x[key]-y[key]))) for x,y in zip(accepted,independent)) for key in ['v','line','tx','kva']};assert max(diff.values())<1e-10 and all(x['taps']==y['taps'] for x,y in zip(accepted,independent))
 outputs(folder/'CONTINUOUS_VERIFICATION',independent,data,axes);save(folder/'CONTINUOUS_VERIFICATION.json',dict(status='PASS',max_errors=diff,taps_identical=True))
 saved=read(folder/'ACTUAL_MESS_AUDIT.json');rows=pd.read_parquet(folder/'ACTUAL_MESS_TIMESERIES.parquet').to_dict('records');ids=list(data['ids'])
 for r in rows:r['Q_EXEC']=float(q[r['slot'],ids.index(r['mess_id'])]);r['Q_SAFE_CMD']=r['Q_EXEC'];r['Q_CURTAILED']=r['Q_CMD']-r['Q_EXEC']
 audit=ns['independent_audit'](saved,rows,dict(eta_charge=.95,eta_discharge=.95),da,q_safety=True)
 save(folder/'FINAL_ACTUAL/ACTUATOR.json',dict(trajectory=rows,independent_audit=audit));np.savez_compressed(folder/'FINAL_ACTUAL/EXECUTION.npz',P_EXEC=data['P_EXEC'],Q_EXEC=q,PCC_P=data['PCC_P'],PCC_Q=data['PCC_Q'],locations=data['locations'],energy_after=data['energy_after'],SoC_after=data['SoC_after'])
 save(folder/'COMPLETE.json',dict(status='COMPLETE',AC_feasible=final['AC_feasible'],policy=policy,date='2025-05-21',validation_scope='REALIZED_OPERATION_AC',summary=final,baseline=bs,Q_intervention_slots=sum(x['status']=='Q_CORRECTED' for x in events),ROBUST_Q_ONLY_UNRESOLVED_slots=sum(x['status']=='ROBUST_Q_ONLY_UNRESOLVED' for x in events),runtime_s=time.time()-start,scheduling_optimizer_calls=0,ML_calls=0,independent_replay_PASS=True,DA_decisions_unchanged=True,rule=rec(H/'RULE_FREEZE.json')))
 print('ACTUAL_POLICY_COMPLETE',policy,json.dumps(final),flush=True)
def main():
 if len(sys.argv)>1 and sys.argv[1]=='freeze':freeze();return
 assert not (H/'EXECUTION_STARTED.json').exists(),'NO_AUTOMATIC_RESTART'
 verify();protect();ns=kernel()
 import gurobipy as gp
 gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DAYAHEAD_OPTIMIZER_FORBIDDEN_IN_ACTUAL'))
 save(H/'EXECUTION_STARTED.json',dict(pid=os.getpid(),started_unix=time.time(),rule=rec(H/'RULE_FREEZE.json')))
 da=inputs(ns)
 for policy in ['B0','B1','B2','B3']:run_policy(policy,ns,da);verify()
 save(H/'CAMPAIGN_COMPLETE.json',dict(status='COMPLETE',policies={p:read(H/p/'COMPLETE.json') for p in ['B0','B1','B2','B3']},scheduling_optimizer_calls=0,ML_calls=0,completed_unix=time.time()))
 save(H/'FINAL_SHA256_MANIFEST.json',dict(files=[rec(p) for p in H.rglob('*') if p.is_file() and p.name not in ['STATUS.json','run.stdout.log','run.stderr.log','PROCESS.json']]))
 state(status='COMPLETE',stage='ALL_ACTUAL_POLICIES_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:
  save(H/'TECHNICAL_FAILURE.json',dict(status='FAIL_CLOSE',error=repr(e),traceback=traceback.format_exc()));state(status='FAIL_CLOSE',error=repr(e));raise
