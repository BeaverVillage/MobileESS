import os,sys,json,csv,time,hashlib,shutil,math,argparse,datetime
from pathlib import Path
sys.dont_write_bytecode=True
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
H=Path(__file__).resolve().parent;W=H.parent.parent
OP=W/'IEEE8500_operating_point_20260911';PCC=W/'IEEE8500_pcc_overlay_20260911'
sys.path.insert(0,str(OP))
import run_b0_screen as core
from prepare_inputs import verify_raw
V41=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
DAY='2025-05-06'; DA=V41/f'frozen_artifacts/v41r4_may/loop_wall_v4/{DAY}/B0/dayahead'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8388608),b''):h.update(b)
 return h.hexdigest()
def rec(p):
 p=Path(p);st=p.stat();return dict(path=str(p),bytes=st.st_size,mtime_ns=st.st_mtime_ns,sha256=sha(p))
def save(name,v):
 p=H/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def table(p,rows):
 with (H/p).open('w',newline='',encoding='utf-8-sig') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
def status(stage,**kw):save('STATUS.json',dict(stage=stage,pid=os.getpid(),timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw))
def prepare(pv_mode):
 assert not (H/'PRE_EXECUTION_FREEZE.json').exists(),'No overwrite or repeated preparation'
 fp=W/f'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days/{DAY}/aemo_forecast.json'
 ep=DA/'authority/DAYAHEAD_EXOGENOUS_INPUTS.json';f=read(fp);e=read(ep)
 assert e['target_day']==DAY and e['role']=='DAYAHEAD_ONLY' and f['cutoff_fixed_aest']=='2025-05-05T18:00:00+10:00'
 assert [v for k,v in e['electrical_input_sources'].items() if k.endswith('aemo_forecast.json')]==[sha(fp)]
 raw=[verify_raw(Path(f['cross_month_archive_authority'][k+'_path']),k,f) for k in ['demand','pv']]
 D=np.array(f['demand_mw_96']);PV=np.array(f['pv_mw_96']);bg=e['background'];gross=np.array([sum(r.values()) for r in bg['gross_p_kw_96']]);pv=np.array([sum(r.values()) for r in bg['pv_generation_kw_96']]);ratio=float(pv.max()/gross.max())
 assert np.allclose(pv/pv.max(),PV/PV.max(),atol=1e-12,rtol=0)
 with np.load(DA/'FROZEN_AIDC_POWER.npz') as z:
  assert z['pcc'].shape==(96,12) and np.allclose(z['qcc'],z['pcc']*np.tan(np.arccos(.95)),atol=1e-9,rtol=0)
 for src,name in [(fp,'D1_AEMO_VIC1_FORECAST.json'),(ep,'MAY06_B0_EXOGENOUS_INPUTS.json'),(DA/'FROZEN_AIDC_POWER.npz','MAY06_B0_AIDC_POWER.npz'),(DA/'FROZEN_JOINT_DECISION.json','MAY06_B0_REFERENCE_DECISION.json')]:shutil.copyfile(src,H/name)
 rule=dict(study='OUTCOME_CONDITIONED_EXPLORATORY_SCREENING_NOT_CONFIRMATORY_COMPARISON',date=DAY,background_alpha_grid=[.60,.65,.70],AIDC_scale_grid=[1.,1.25,1.50],source_pu=1.0400,all_Vreg_V=123.5,CAPBank3='OFF',MESS_units=4,MESS_P_kW=300,MESS_PCS_kVA=400,MESS_energy_kWh=1200,AIDC_count=12,AIDC_PCC_kVA=1500,MESS_service_PCC_kVA=750,service_locations=24,voltage_limits=[.95,1.05],line_current_limit=1.,transformer_phase_current_limit=1.,transformer_winding_kVA_limit=1.,comparison_scope='DAY_AHEAD_EXACT_AC_PENDING_USER_SCOPE_REPLY',alpha_selection='feasible only; prefer loading[.83,.88], then abs(loading-.855), then lower alpha; no feasible -> STOP',AIDC_scale_definition='external multiplier on all12 sites PCC P and fixed-PF Q; preserve original unscaled workload/GPU/PUE/C1/candidate/P1-P5 semantics; scale electrical control binding consistently',AIDC_scale_selection='among exact-feasible B0 and B1, minimize B1_AC-B0_AC, then lower AIDC multiplier; no improvement -> stop before B2/B3',PV_mode=pv_mode,PV_alpha_fixed=.50 if pv_mode=='fixed' else None,PV_ratio=ratio,PV_definition='PV(t)=PV_alpha*May06_B0_exogenous_peak_PV_to_gross_ratio*native_base_P_i*normalized_D1_PV(t); P/Q native load=alpha*normalized_D1_demand*native P/Q',B1_search_loop_seconds=14400,B3_A1_search_loop_seconds=14400,checkpoint_seconds=[1800,3600,7200,14400],read_May06_IEEE123_policy_performance=False,May21_results_modified=False,Actual_inputs_used=False,no_additional_tuning=True)
 save('SCREENING_RULE.json',rule)
 table('DEMAND_PV_PROFILES.csv',[dict(slot=t,demand_DA_MW=float(D[t]),PV_DA_MW=float(PV[t]),demand_multiplier=float(D[t]/D.max()),PV_multiplier=float(PV[t]/PV.max())) for t in range(96)])
 save('FORECAST_CAUSALITY_AUDIT.json',dict(status='PASS',date=DAY,cutoff=f['cutoff_fixed_aest'],demand_issue=f['demand_issue'],PV_issue=f['pv_issue'],raw=raw,exogenous=rec(ep),PV_ratio=ratio,Actual_read=False))
 # Bind source models, settings, inventories, helpers and B0 inputs before any AC solve.
 paths=[H/'screen_b0.py',H/'SCREENING_RULE.json',H/'D1_AEMO_VIC1_FORECAST.json',H/'MAY06_B0_AIDC_POWER.npz',H/'MAY06_B0_REFERENCE_DECISION.json',H/'MAY06_B0_EXOGENOUS_INPUTS.json',fp,ep,DA/'FROZEN_AIDC_POWER.npz',DA/'FROZEN_JOINT_DECISION.json',OP/'run_b0_screen.py',OP/'prepare_inputs.py',OP/'select_date.py']
 for directory in [W/'IEEE8500_scalability_20260910/source',PCC]:
  paths.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in ['.dss','.json','.csv','.py'])
 protected=[rec(p) for p in sorted(set(paths))]
 save('PRE_EXECUTION_FREEZE.json',dict(rule_sha256=sha(H/'SCREENING_RULE.json'),files=protected,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scientific_solves_before_freeze=0))
 print('INPUT_FREEZE_PASS',json.dumps(dict(date=DAY,PV_mode=pv_mode,PV_ratio=ratio,source_files=len(protected))),flush=True)
def verify():
 for r in read(H/'PRE_EXECUTION_FREEZE.json')['files']:
  p=Path(r['path']);assert p.stat().st_size==r['bytes'] and p.stat().st_mtime_ns==r['mtime_ns'] and sha(p)==r['sha256'],p
def case(alpha):
 rule=read(H/'SCREENING_RULE.json');folder=H/'background_screen'/f'alpha_{alpha:.2f}';folder.mkdir(parents=True,exist_ok=False)
 started=time.perf_counter();d=core.engine(folder/'runtime');d.Basic.DataPath(str(folder/'runtime'))
 d.Text.Command('Edit Vsource.source pu=1.0400');d.Text.Command('BatchEdit RegControl..* Vreg=123.5');d.Text.Command('Edit Capacitor.CAPBank3 Enabled=no')
 assert d.RegControls.Count()==12
 for name in d.RegControls.AllNames():
  d.RegControls.Name(name);assert d.RegControls.ForwardVreg()==123.5 and d.RegControls.PTRatio()==60 and d.RegControls.ForwardBand()==2
 base=core.static_inputs(d);loads=core.native_inventory(d);ax=core.measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames());inv=read(PCC/'PCC_OVERLAY_INVENTORY.json');aidcs=sorted([r for r in inv if r['PCC_role']=='AIDC'],key=lambda r:r['location_id'])
 P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);f=read(H/'D1_AEMO_VIC1_FORECAST.json');md=np.array(f['demand_mw_96']);md/=md.max();mpv=np.array(f['pv_mw_96']);mpv/=mpv.max();pv_alpha=.5 if rule['PV_mode']=='fixed' else alpha
 with np.load(H/'MAY06_B0_AIDC_POWER.npz') as z:ap=z['pcc'].copy();aq=z['qcc'].copy()
 resources=core.add_resources(d,loads,rule['PV_ratio'],inv);(folder/'RESOURCE_OBJECTS.dss').write_text(resources,encoding='utf-8')
 v=[];li=[];tx=[];kv=[];rows=[];states=[]
 for t in range(96):
  d.Solution.LoadMult(1.);d.Solution.Hour(t//4);d.Solution.Seconds((t%4)*900)
  for i,r in enumerate(loads):
   d.Loads.Name(r['load']);d.Loads.kW(float(alpha*md[t]*P[i]));d.Loads.kvar(float(alpha*md[t]*Q[i]));d.Generators.Name(f'op8500_pv_{i:04d}');value=float(pv_alpha*rule['PV_ratio']*P[i]*mpv[t]);d.CktElement.Enabled(value>0)
   if value>0:d.Generators.kW(value);d.Generators.kvar(0.)
  for j,r in enumerate(aidcs):d.Loads.Name('op8500_'+r['location_id'].lower());d.Loads.kW(float(ap[t,j]));d.Loads.kvar(float(aq[t,j]))
  d.Solution.SolveSnap();conv=bool(d.Solution.Converged());settled=bool(d.Solution.ControlActionsDone());assert d.Error.Number()==0
  vv=np.asarray(d.Circuit.AllBusMagPu());current=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)[:,0];pw=np.asarray(d.PDElements.AllPowers()).reshape(-1,2);ll=current[ax['line_pos']]/ax['line_rating'];tt=current[ax['tx_pos']]/ax['tx_rating'];sp=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],0]);sq=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],1]);kk=np.hypot(sp,sq)/ax['kva_rating']
  assert all(np.isfinite(x).all() for x in [vv,ll,tt,kk]);v.append(vv.copy());li.append(ll.copy());tx.append(tt.copy());kv.append(kk.copy())
  feasible=conv and settled and vv.min()>=.95-1e-9 and vv.max()<=1.05+1e-9 and max(ll.max(),tt.max(),kk.max())<=1+1e-9
  rows.append(dict(date=DAY,alpha_BG=alpha,AIDC_scale=1.,policy='B0',slot=t,Vmin=float(vv.min()),Vmax=float(vv.max()),max_phase_line_loading=float(ll.max()),transformer_phase_current_max=float(tt.max()),transformer_winding_kVA_max=float(kk.max()),converged=conv,controls_settled=settled,feasible=feasible,Vmin_node=str(nodes[vv.argmin()]),Vmax_node=str(nodes[vv.argmax()]),line_witness=str(ax['line_label'][ll.argmax()])))
  regs=[]
  for name in d.RegControls.AllNames():d.RegControls.Name(name);regs.append(dict(name=name,tap=int(d.RegControls.TapNumber())))
  caps=[]
  for name in d.Capacitors.AllNames():d.Capacitors.Name(name);caps.append(dict(name=name,enabled=bool(d.CktElement.Enabled()),states=list(d.Capacitors.States())))
  states.append(dict(slot=t,regulators=regs,capacitors=caps))
  if t%24==23:status('B0_BACKGROUND_SCREEN',alpha=alpha,slots=t+1);print('B0',alpha,t+1,flush=True)
 for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
 final=core.static_inputs(d);changed=[n for n in base if base[n]!=final[n]];assert not changed,changed
 d.Basic.ClearAll()
 result=dict(date=DAY,alpha_BG=alpha,AIDC_scale=1.,B0_max_phase_line_loading=max(r['max_phase_line_loading'] for r in rows),B1_max_phase_line_loading=None,B2_max_phase_line_loading=None,B3_max_phase_line_loading=None,B1_minus_B0=None,B2_minus_B1=None,B3_minus_B2=None,Vmin=min(r['Vmin'] for r in rows),Vmax=max(r['Vmax'] for r in rows),transformer_phase_current_max=max(r['transformer_phase_current_max'] for r in rows),transformer_winding_kVA_max=max(r['transformer_winding_kVA_max'] for r in rows),exact_AC_feasible=all(r['feasible'] for r in rows),converged_slots=sum(r['converged'] for r in rows),control_settled_slots=sum(r['controls_settled'] for r in rows),runtime_s=time.perf_counter()-started,scope='DAY_AHEAD_EXACT_AC',PV_alpha=pv_alpha)
 core.table(folder/'SLOT_EXTREMA.csv',rows);core.save(folder/'SUMMARY.json',result);core.save(folder/'CONTROL_STATES.json',states);core.save(folder/'NATIVE_STATIC_PRESERVATION.json',dict(status='PASS',elements_compared=len(base),changed=changed,sha_before=core.digest(base),sha_after=core.digest({n:final[n] for n in base})))
 np.savez_compressed(folder/'ALL_PHASE_ARRAYS.npz',voltage_pu=np.array(v),line_current_loading_pu=np.array(li),transformer_current_loading_pu=np.array(tx),transformer_kva_loading_pu=np.array(kv),node_names=nodes,line_labels=ax['line_label'],transformer_current_labels=ax['tx_label'],transformer_kva_labels=ax['kva_label'])
 return result
def run():
 assert not (H/'EXECUTION_STARTED.json').exists(),'Do not overwrite scientific execution'
 verify();save('EXECUTION_STARTED.json',dict(pid=os.getpid(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),freeze=rec(H/'PRE_EXECUTION_FREEZE.json')))
 rows=[]
 for alpha in read(H/'SCREENING_RULE.json')['background_alpha_grid']:
  row=case(alpha);rows.append(row);table('BACKGROUND_SCREEN_TABLE.csv',[{k:('NA' if v is None else v) for k,v in r.items()} for r in rows]);save('BACKGROUND_SCREEN_TABLE.json',rows);print(json.dumps(row),flush=True)
 feasible=[r for r in rows if r['exact_AC_feasible']];feasible.sort(key=lambda r:(not(.83<=r['B0_max_phase_line_loading']<=.88),abs(r['B0_max_phase_line_loading']-.855),r['alpha_BG']))
 verify();out=dict(status='B0_ALPHA_SELECTED' if feasible else 'NO_FEASIBLE_B0_ON_USER_GRID',selected=feasible[0] if feasible else None,screened_alpha_count=3,exact_AC_slots=288,B1_B2_B3_runs=0,no_extra_tuning=True,source_SHA_and_mtime_preserved=True)
 save('BACKGROUND_SELECTION.json',out);status(out['status'],selected_alpha=feasible[0]['alpha_BG'] if feasible else None)
 save('B0_STAGE_OUTPUT_SHA256.json',dict(files=[rec(p) for p in H.rglob('*') if p.is_file() and p.name not in ['B0_STAGE_OUTPUT_SHA256.json','run.stdout.log','run.stderr.log']]))
 print('BACKGROUND_STAGE_COMPLETE',json.dumps(out),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);parser.add_argument('--pv-mode',choices=['fixed','proportional'],default='fixed');args=parser.parse_args()
 try:
  if args.action=='prepare':prepare(args.pv_mode)
  else:run()
 except BaseException as e:status('FAIL_CLOSE',error=repr(e));raise
