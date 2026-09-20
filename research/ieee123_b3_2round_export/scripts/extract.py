"""Read-only raw extraction. No campaign modules or solvers are imported."""
from pathlib import Path
import ast,collections,csv,hashlib,json,math,os,time
from datetime import datetime,timezone
import numpy as np,pandas as pd
OUT=Path(__file__).parent;ROOT=OUT.parent;RUN=ROOT/'production_v4_corrected'
OLD=Path(r'D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
OA=OLD/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
REV=OLD/'frozen_artifacts/v41r4_selective_actual_revision_v1'
DAYS=[f'2025-05-{n:02}' for n in range(1,32)]
SOURCES={};TABLE_SOURCES=collections.defaultdict(set);CHECKS=[]
NAMES=['01_DAILY_1R_VS_2R_SUMMARY','02_2ROUND_STAGE_SUMMARY','03_ACTUAL_LINE_LOADING_TIMESERIES','04_ACTUAL_VOLTAGE_TIMESERIES','05_MESS_2ROUND_TRAJECTORY','06_AIDC_2ROUND_TRAJECTORY','07_ROUND2_DECISION_CHANGES','08_PAPER_AGGREGATE_METRICS']
ROWS={k:[] for k in NAMES}
def physical(p):return Path(str(p).replace('C:\\codex_mobileess_workspace\\','D:\\codex_mobileess_workspace\\'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def source(p,tables=()):
 p=physical(p).absolute();key=str(p)
 if key not in SOURCES:
  s=p.stat();SOURCES[key]=dict(path=key,sha256=sha(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
 for t in tables:TABLE_SOURCES[NAMES[t-1]].add(key)
 return p
def read(p,tables=()):return json.loads(source(p,tables).read_text(encoding='utf-8-sig'))
def arrays(p,tables=()):
 with np.load(source(p,tables),allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def parquet(p,tables=()):return pd.read_parquet(source(p,tables))
def exact(p,h,tables=()):assert SOURCES[str(source(p,tables))]['sha256']==h,(str(p),'SHA_MISMATCH')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def grid(folder,tables):
 paths=[folder/'OPENDSS_PHASE_ARRAYS.npz'] if (folder/'OPENDSS_PHASE_ARRAYS.npz').exists() else list(folder.rglob('OPENDSS_PHASE_ARRAYS.npz'));assert len(paths)==1,(str(folder),len(paths))
 p=paths[0];z=arrays(p,tables);m=read(p.parent/'OPENDSS_OUTPUT_MANIFEST.json',tables)
 exact(p,m['files'][p.name]['sha256'],tables)
 summary=read(p.parent/'OPENDSS_SUMMARY.json',tables)
 exact(p.parent/'OPENDSS_SUMMARY.json',m['files']['OPENDSS_SUMMARY.json']['sha256'],tables)
 assert len(z['convergence'])==96 and z['convergence'].all()
 indices=np.flatnonzero(z['branch_kinds']=='line');loading=z['phase_current_loading_pu'][:,indices]
 winners=loading.argmax(axis=1);values=loading[np.arange(96),winners]
 assert np.isfinite(loading).all() and np.isfinite(z['voltage_pu']).all()
 assert float(values.max())==summary['rho_max_AC']
 assert float(z['voltage_pu'].min())==summary['Vmin_pu'] and float(z['voltage_pu'].max())==summary['Vmax_pu']
 return dict(rho=values,vmin=z['voltage_pu'].min(axis=1),vmax=z['voltage_pu'].max(axis=1),
  line=z['branch_names'][indices[winners]],phase=z['branch_phases'][indices[winners]],summary=summary)
def jobs(v):
 result={str(x['job_uid']):x for x in v};assert len(result)==len(v);return result
JOB_FIELDS=['AIDC_site','Rack_label','start_slot','end_slot','compute_segments','migration_events','post_H_site']
ASSIGN_FIELDS=[k for k in JOB_FIELDS if k!='migration_events']
MIG_FIELDS=['migration_events','migration_selected']
inv=source(ROOT.parent/'v41r4_final_results_pr/dayahead/v40a/invariants.py',(2,7))
tree=ast.parse(inv.read_text());MOBILITY=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MOBILITY_FIELDS' for t in n.targets))
def jobcount(a,b):
 a=jobs(a);b=jobs(b);assert a.keys()==b.keys()
 return sum(any(a[k].get(f)!=b[k].get(f) for f in JOB_FIELDS) for k in a)
def slots(v):return {(x['mess_id'],x['slot']):x for x in v}
def routecount(a,b):
 a=slots(a);b=slots(b);assert a.keys()==b.keys()
 return sum(any(a[k].get(f)!=b[k].get(f) for f in MOBILITY) for k in a)
def timings(day,raw,coord,a1,acceptance):
 t=coord['runtime'];m=t['M1'];a=t['A1']
 if day=='2025-05-25':
  m+=read(raw/'M1/M1_RESULT.json',(1,2,8))['optimization_seconds']
  a+=read(raw/'A1/ACCEPTED_AIDC.json',(1,2,8))['wallclock_seconds']
  prior=read(ROOT/'repair_03_compound_readback/FAILED_DA_STATUS.json',(1,2,8))
  status=read(RUN/'status'/f'{day}_DA.json',(1,2,8))
  assert status['reused_prior_wall_seconds']==prior['wall_seconds']
 da=read(RUN/'status'/f'{day}_DA.json',(1,2,8))
 actual=read(RUN/'status'/f'{day}_Actual.json',(1,2,8));assert actual['status']=='COMPLETE'
 total=a1['wall_seconds']+da['wall_seconds']+acceptance['closure_wall_seconds']+actual['wall_seconds']
 return a1['wall_seconds'],m,a,t['MF'],total
state=read(RUN/'CAMPAIGN_STATUS.json',range(1,9));assert set(state['completed'])==set(DAYS) and not state['active'] and not state['errors']
gate=read(RUN/'PRODUCTION_GATE.json',range(1,9));assert gate['days']==31 and gate['status'].endswith('CORRECTED_PRODUCTION_PASS')
auth=read(RUN/'EXECUTION_AUTHORIZATION.json',range(1,9))
for n,h in auth['production_source_files'].items():exact(ROOT/n,h,range(1,9))
for n,h in auth['evidence_sha256'].items():exact(ROOT/n,h,range(1,9))
contract=read(ROOT/'authority_recovery/RECOVERY_CONTRACT.json',range(1,9));assert contract['FINAL_OPERATING_AUTHORITY']=='ORIGINAL_SHA_VERIFIED' and contract['regenerated_sensitivity_production_usage']==0
boundary={r['day']:r for r in read(ROOT/'M2_ROUND1_FINAL_BOUNDARY_FREEZE.json',range(1,9))['days']}
for name in ['METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','PERFORMANCE_FREEZE.json','BATTERY_EFFICIENCY_AUTHORITY.json']:
 exact(RUN/'actual'/name,sha(OA/name),range(1,9));source(OA/name,range(1,9))
revision=read(REV/'RESTORATION_EXECUTION_BINDING.json',range(1,9));assert revision['status']=='FROZEN'
for name in ['METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','PERFORMANCE_FREEZE.json','BATTERY_EFFICIENCY_AUTHORITY.json']:
 exact(REV/name,sha(OA/name),range(1,9))
def actualroot(day,policy):
 if (OA/'replays'/day/policy/actualfolder(policy)/'OPENDSS_PHASE_ARRAYS.npz').exists():return OA
 assert day=='2025-05-31' and policy in ('B2','B3')
 return REV
def actualfolder(policy):return 'CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
optional=all((actualroot(day,p)/'replays'/day/p/actualfolder(p)/'OPENDSS_PHASE_ARRAYS.npz').exists() for day in DAYS for p in ['B0','B1','B2'])
TOL=None
for day in DAYS:
 raw=RUN/'runs'/day/'B3/dayahead';acceptance=read(RUN/'closure'/day/'ACCEPTANCE.json',(1,2,5,6,7,8));assert acceptance['status']=='PASS'
 final=physical(acceptance['final_dayahead']);exact(acceptance['final_joint']['path'],acceptance['final_joint']['sha256'],(1,5,6,7,8))
 old=physical(boundary[day]['input_joint']).parent;exact(old/'FROZEN_JOINT_DECISION.json',boundary[day]['file_SHA256'],(1,2,7,8))
 j1=read(old/'FROZEN_JOINT_DECISION.json',(1,2,7,8));j2=read(final/'FROZEN_JOINT_DECISION.json',(1,2,5,6,7,8));assert j1['decision']['day']==j2['decision']['day']==day
 for base,j in [(old,j1),(final,j2)]:
  receipt=read(base/'DAYAHEAD_RECEIPT.json',(1,8));assert receipt['status']=='COMPLETE' and receipt['decision_SHA']==j['decision_SHA']
 if TOL is None:TOL=acceptance['tolerances'][0]
 assert TOL==acceptance['tolerances'][0]
 oldactual=actualroot(day,'B3')
 g1=grid(oldactual/'replays'/day/'B3/ETA95_QSAFE_ACTUAL',(1,3,4,8));g2=grid(RUN/'actual/replays'/day/'B3/ETA95_QSAFE_ACTUAL',(1,3,4,8))
 ci1=oldactual/'common_inputs'/day/'B3';ci2=RUN/'actual/common_inputs'/day/'B3'
 ex1=parquet(ci1/'authority/ACTUAL_EXOGENOUS_96.parquet',(1,3,4,5,6));ex2=parquet(ci2/'authority/ACTUAL_EXOGENOUS_96.parquet',(1,3,4,5,6))
 assert ex1.equals(ex2),'EXOGENOUS_MISMATCH'
 ts=pd.to_datetime(ex2['timestamp'],utc=True).dt.tz_convert('Australia/Brisbane')
 assert ex2['slot'].tolist()==list(range(96)) and (ts.diff().dropna()==pd.Timedelta(minutes=15)).all()
 assert all(x.strftime('%Y-%m-%d')==day for x in ts);timestamps=[x.isoformat() for x in ts]
 for root,ci,j in [(oldactual,ci1,j1),(RUN/'actual',ci2,j2)]:
  ready=read(ci/'READY.json',(1,3,4,8));done=read(root/'replays'/day/'B3/COMPLETE.json',(1,3,4,8))
  assert ready['status']==done['status']=='PASS' and ready['decision_SHA']==j['decision_SHA']
  assert ready['identity']==done['ETA95_QSAFE_ACTUAL']['schedule_sha256']
  assert read(root/'replays'/day/'B3/ETA95_QSAFE_ACTUAL/CONTINUOUS_VERIFICATION.json',(1,3,4,8))['status']=='PASS'
  # Bind actual inputs to the exact final DA artifacts; verify the retained snapshot.
  snapshot=read(ci/'DA_FRESH_INPUT_SNAPSHOT.json',(1,3,4,8))
  joint_refs=[(p,h) for p,h in snapshot.items() if Path(p).name=='FROZEN_JOINT_DECISION.json'];assert len(joint_refs)==1
  exact(*joint_refs[0],(1,3,4,8));assert sha(physical(joint_refs[0][0]))==sha(old/'FROZEN_JOINT_DECISION.json' if ci==ci1 else final/'FROZEN_JOINT_DECISION.json')
 f1=grid(old/'fresh',(1,8));f2=grid(final/'fresh',(1,8))
 obj1=read(old/'optimization/OBJECTIVE_LEDGER.json',(1,8));obj2=read(final/'optimization/OBJECTIVE_LEDGER.json',(1,8))
 p1=read(old/'PLANNING_RESULT.json',(1,8));p2=read(final/'PLANNING_RESULT.json',(1,8));rawp=read(raw/'PLANNING_RESULT.json',(1,2,8));coord=rawp['stages']['COORDINATION']
 a1=read(RUN/'a1'/day/'A1_ROUND2_COMPLETE.json',(1,2,8));a1accepted=read(a1['accepted']['path'],(2,));exact(a1['accepted']['path'],a1['accepted']['sha256'],(2,))
 a2=read(raw/'A1/ACCEPTED_AIDC.json',(2,));times=timings(day,raw,coord,a1,acceptance)
 peak1=int(g1['rho'].argmax());peak2=int(g2['rho'].argmax())
 daily=dict(date=day,B3_1R_DA_rho_max=obj1['OBJECTIVE_VECTOR'][0],B3_2R_DA_rho_max=obj2['OBJECTIVE_VECTOR'][0],DA_delta_1R_minus_2R=obj1['OBJECTIVE_VECTOR'][0]-obj2['OBJECTIVE_VECTOR'][0],
  B3_1R_Fresh_rho_max=float(f1['rho'].max()),B3_2R_Fresh_rho_max=float(f2['rho'].max()),Fresh_delta_1R_minus_2R=float(f1['rho'].max()-f2['rho'].max()),
  B3_1R_Actual_rho_max=float(g1['rho'].max()),B3_2R_Actual_rho_max=float(g2['rho'].max()),Actual_delta_1R_minus_2R=float(g1['rho'].max()-g2['rho'].max()))
 daily.update({'1R_Actual_Vmin':float(g1['vmin'].min()),'2R_Actual_Vmin':float(g2['vmin'].min()),'1R_Actual_Vmax':float(g1['vmax'].max()),'2R_Actual_Vmax':float(g2['vmax'].max()),
  '1R_critical_line':str(g1['line'][peak1]),'2R_critical_line':str(g2['line'][peak2]),'1R_critical_slot':peak1,'2R_critical_slot':peak2,
  '1R_feasible':p1['grid']['status']=='PASS' and not f1['summary']['physical_violation'] and not g1['summary']['physical_violation'],
  '2R_feasible':p2['grid']['status']=='PASS' and not f2['summary']['physical_violation'] and not g2['summary']['physical_violation'],
  '2R_incremental_runtime_s':times[-1],'1R_critical_phase':str(g1['phase'][peak1]),'2R_critical_phase':str(g2['phase'][peak2])})
 ROWS[NAMES[0]].append(daily)
 stage=lambda name:read(raw/'optimization/stages'/f'{name}.json',(2,))
 sM1=stage('M1_OUTPUT');sA2=stage('A1_OUTPUT');sM2=stage('MF_OUTPUT');a1j=stage('A0_OUTPUT')['AIDC_decision']
 sm1=slots(sM1['MESS_commands']);sm2=slots(sM2['MESS_commands'])
 st=dict(date=day,A1_2_rho=a1accepted['OBJECTIVE_VECTOR'][0],M1_2_rho=coord['objectives']['J_M1'],A2_2_rho=coord['objectives']['J_A1'],M2_2_rho=coord['objectives']['J_FINAL'],
  A1_2_runtime_s=times[0],M1_2_runtime_s=times[1],A2_2_runtime_s=times[2],M2_2_runtime_s=times[3],
  A1_2_job_decision_changes=jobcount(j1['decision']['AIDC_decision'],a1j),M1_2_route_changes=routecount(j1['decision']['MESS_trajectory'],sM1['MESS_commands']),
  A2_2_job_decision_changes=jobcount(a1j,sA2['AIDC_decision']),M2_2_PQ_changes=sum(sm1[k]['p_kw']!=sm2[k]['p_kw'] or sm1[k]['q_kvar']!=sm2[k]['q_kvar'] for k in sm1))
 st.update({f'A1_2_P{i+1}':v for i,v in enumerate(a1accepted['OBJECTIVE_VECTOR'])});st.update({f'A2_2_P{i+1}':v for i,v in enumerate(a2['OBJECTIVE_VECTOR'])})
 st.update(A2_candidate_accepted=coord['AIDC_FEEDBACK_ACCEPTED'],M2_candidate_accepted=coord['FINAL_PQ_RECOURSE_ACCEPTED'])
 ROWS[NAMES[1]].append(st)
 other={}
 if optional:
  for policy in ['B0','B1','B2']:
   policyroot=actualroot(day,policy)
   other[policy]=grid(policyroot/'replays'/day/policy/actualfolder(policy),(3,))
   rc=read(policyroot/'common_inputs'/day/policy/'READY.json',(3,))
   if policyroot==REV:
    selected=REV/'accepted_inputs'/day/policy/'dayahead'
    parent=read(selected/'RESTORATION_PARENT.json',(3,));exact(parent['original']['path'],parent['original']['sha256'],(3,));exact(parent['rule']['path'],parent['rule']['sha256'],(3,))
    assert parent['scientific_objectives_unchanged']
    jj=read(selected/'FROZEN_JOINT_DECISION.json',(3,))
   else:jj=read(OLD/'frozen_artifacts/v41r4_may/loop_wall_v4'/day/policy/'dayahead/FROZEN_JOINT_DECISION.json',(3,))
   assert rc['status']=='PASS' and rc['decision_SHA']==jj['decision_SHA']
   done=read(policyroot/'replays'/day/policy/'COMPLETE.json',(3,));assert done['status']=='PASS' and done['summary' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL']['schedule_sha256']==rc['identity']
   assert parquet(policyroot/'common_inputs'/day/policy/'authority/ACTUAL_EXOGENOUS_96.parquet',(3,)).equals(ex2)
 for t in range(96):
  row=dict(date=day,slot=t,timestamp_AEST=timestamps[t],B3_1R_actual_rho_max=float(g1['rho'][t]),B3_2R_actual_rho_max=float(g2['rho'][t]),B3_1R_critical_line=str(g1['line'][t]),B3_2R_critical_line=str(g2['line'][t]))
  for policy,g in other.items():row[policy+'_actual_rho_max']=float(g['rho'][t])
  row.update(B3_1R_critical_phase=str(g1['phase'][t]),B3_2R_critical_phase=str(g2['phase'][t]));ROWS[NAMES[2]].append(row)
  ROWS[NAMES[3]].append(dict(date=day,slot=t,timestamp_AEST=timestamps[t],**{'1R_Vmin':float(g1['vmin'][t]),'1R_Vmax':float(g1['vmax'][t]),'2R_Vmin':float(g2['vmin'][t]),'2R_Vmax':float(g2['vmax'][t])}))
 execution=arrays(RUN/'actual/replays'/day/'B3/ETA95_QSAFE_ACTUAL/EXECUTION.npz',(5,));actuator=read(RUN/'actual/replays'/day/'B3/ETA95_QSAFE_ACTUAL/ACTUATOR.json',(5,));actualslots=slots(actuator['trajectory']);daslots=slots(j2['decision']['MESS_trajectory'])
 ids=read(ci2/'ACTUAL_MESS_AUDIT.json',(5,))['ids'];assert len(ids)==4 and set(actualslots)==set(daslots)
 for t in range(96):
  for i,mid in enumerate(ids):
   da=daslots[mid,t];ac=actualslots[mid,t]
   assert execution['P_EXEC'][t,i]==ac['P_EXEC'] and execution['Q_EXEC'][t,i]==ac['Q_EXEC'] and execution['energy_after'][t,i]==ac['energy_after_kWh']
   ROWS[NAMES[4]].append(dict(date=day,slot=t,timestamp_AEST=timestamps[t],MESS_id=mid,station_or_location=str(execution['locations'][t,i]),connected=ac['connected'],
    DA_P_kW=da['p_kw'],DA_Q_kvar=da['q_kvar'],Actual_P_kW=ac['P_EXEC'],Actual_Q_kvar=ac['Q_EXEC'],SOC_kWh=ac['energy_after_kWh'],DA_SOC_kWh=da['battery_energy_kwh'],
    route_or_leg=canonical({k:da.get(k) for k in ['origin_service_id','destination_service_id','departure_slot','connection_ready_slot','route_link_ids']}),DA_station_or_location=da['service_id'],DA_mode=da['mode']))
 sites=parquet(final/'aidc/SITE_TRAJECTORIES_96.parquet',(6,));fieldauth=read(final/'aidc/AIDC_FIELD_AUTHORITY.json',(6,));assert len(sites)==1152 and not sites.duplicated(['slot','IDC_id']).any()
 frozenpower=arrays(final/'FROZEN_AIDC_POWER.npz',(6,));siteids=sorted(sites['IDC_id'].unique());assert len(siteids)==12
 for r in sites.sort_values(['slot','IDC_id']).to_dict('records'):
  t=int(r['slot']);i=siteids.index(r['IDC_id']);assert r['IT_load_kW']==frozenpower['it'][t,i] and r['known_scheduled_GPU']==frozenpower['gpu'][t,i]
  assert pd.Timestamp(r['timestamp']).tz_convert('Australia/Brisbane').isoformat()==timestamps[t]
  ROWS[NAMES[5]].append(dict(date=day,slot=t,timestamp_AEST=timestamps[t],AIDC_id=r['IDC_id'],IT_power_kW=r['IT_load_kW'],GPU_or_workload_quantity=r['known_scheduled_GPU'],flexible_workload=r['flexible_workload_GPU'],fixed_workload=r['fixed_workload_GPU'],stage='DA'))
 before=jobs(j1['decision']['AIDC_decision']);after=jobs(j2['decision']['AIDC_decision']);assert before.keys()==after.keys()
 for jid in sorted(before):
  for kind,fields in [('AIDC_assignment',ASSIGN_FIELDS),('migration',MIG_FIELDS)]:
   b={f:before[jid].get(f) for f in fields};a={f:after[jid].get(f) for f in fields}
   if b!=a:ROWS[NAMES[6]].append(dict(date=day,decision_type=kind,entity_id=jid,before_1R=canonical(b),after_2R=canonical(a),delta=None,slot=None,timestamp_AEST=None))
 s1=slots(j1['decision']['MESS_trajectory']);s2=daslots;assert s1.keys()==s2.keys()
 for key in sorted(s1):
  mid,t=key;b={f:s1[key].get(f) for f in MOBILITY};a={f:s2[key].get(f) for f in MOBILITY}
  if b!=a:ROWS[NAMES[6]].append(dict(date=day,decision_type='MESS_route',entity_id=mid,before_1R=canonical(b),after_2R=canonical(a),delta=None,slot=t,timestamp_AEST=timestamps[t]))
  for kind,f in [('MESS_P','p_kw'),('MESS_Q','q_kvar'),('MESS_SOC','battery_energy_kwh')]:
   b=s1[key][f];a=s2[key][f]
   if b!=a:ROWS[NAMES[6]].append(dict(date=day,decision_type=kind,entity_id=mid,before_1R=b,after_2R=a,delta=a-b,slot=t,timestamp_AEST=timestamps[t]))
 CHECKS.append(dict(day=day,final_joint_SHA_verified=True,original_boundary_SHA_verified=True,Actual_joint_binding_verified=True,common_exogenous_exact=True,actual_method_exact=True,slots=96,slot_minutes=15,optional_B0_B1_B2_exact=optional))
 print('EXTRACTED',day,flush=True)
daily=ROWS[NAMES[0]]
def metric(name,a,b):
 ROWS[NAMES[7]].append(dict(metric=name,B3_1R=a,B3_2R=b,absolute_change=None if a is None else b-a,relative_change_percent=None if a in (None,0) else 100*(b-a)/a))
for phase in ['DA','Fresh','Actual']:
 for prefix,fn in [('mean',np.mean),('max',np.max)]:metric(prefix+'_'+phase+'_rho',float(fn([r[f'B3_1R_{phase}_rho_max'] for r in daily])),float(fn([r[f'B3_2R_{phase}_rho_max'] for r in daily])))
for label,fn in [('mean_Vmin',np.mean),('worst_Vmin',np.min)]:metric(label,float(fn([r['1R_Actual_Vmin'] for r in daily])),float(fn([r['2R_Actual_Vmin'] for r in daily])))
metric('mean_incremental_runtime',None,float(np.mean([r['2R_incremental_runtime_s'] for r in daily])));metric('total_incremental_runtime',None,float(np.sum([r['2R_incremental_runtime_s'] for r in daily])))
for phase in ['Actual','DA','Fresh']:
 delta=np.array([r[phase+'_delta_1R_minus_2R'] for r in daily]);suffix='' if phase=='Actual' else '_'+phase
 for name,value in [('number_of_days_2R_better_than_1R',int((delta>TOL).sum())),('number_of_days_equal',int((abs(delta)<=TOL).sum())),('number_of_days_2R_worse_than_1R',int((delta<-TOL).sum()))]:metric(name+suffix,None,value)
for n in (1,2):TABLE_SOURCES[NAMES[7]].update(TABLE_SOURCES[NAMES[n-1]])
payload=dict(tables={name:dict(columns=list(rows[0]) if rows else ['date','decision_type','entity_id','before_1R','after_2R','delta','slot','timestamp_AEST'],rows=rows) for name,rows in ROWS.items()})
(OUT/'EXTRACTED_TABLES.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')
manifest=dict(schema='IEEE123_2ROUND_RAW_TO_PAPER_CSV_V1',created_at=datetime.now(timezone.utc).isoformat(),source_authority_consistency='PASS',checks=CHECKS,
 campaign_status=gate['status'],source_roots=[str(RUN),str(OLD)],sources=SOURCES,table_sources={k:sorted(v) for k,v in TABLE_SOURCES.items()},
 equality_tolerance=dict(absolute_rho=TOL,source='per-day closure/ACCEPTANCE.json tolerances[0]; original P1 tolerance',relative_tolerance=0),
 unsupported_fields=['5-minute electrical/AC observations are unavailable. Authoritative arrays contain 96 15-minute slots per day; no resampling or interpolation.',
 'Non-numeric assignment/migration/route deltas are blank; before/after retain exact structured decisions.',
 'Aggregate 1R incremental runtime and paired-day classification baselines are not applicable and blank.'],
 historical_lineage_complete=contract['HISTORICAL_LINEAGE_COMPLETE'],missing_historical_lineage=contract['missing_historical_lineage'],
 rules=dict(numeric_precision='Raw float64 values; no rounding. Only requested differences, extrema, means, counts and runtime sums are computed.',
  timestamp='Direct stored UTC timestamp converted to AEST (Australia/Brisbane, +10:00). Slot 0 is 00:00; slot 95 is 23:45.',
  original_Actual_selection='Original robust_v2_perf1; May31 B2/B3 use final selective_actual_revision_v1 whose restoration binding and all five method/implementation receipts are byte-identical, and whose exact accepted DA joint matches the frozen baseline.',
  critical_line='Max phase-current loading among branch_kinds=line. Exact ties use first stored phase/branch index, then earliest slot for daily critical. Phase exported separately.',
  feasible='DA grid PASS AND Fresh/Actual physical_violation=false AND all 96 AC converged AND completed continuous Actual verification PASS.',
  stage='A1 objective is accepted computing with retained Round1 MESS. M1/A2/M2 rho comes from original coordinator accepted stage outputs. A2 P1-P5 are raw ACCEPTED_AIDC solver output; acceptance flags included.',
  runtime='A1 complete wall + DA phase wall + closure wall + Actual wall. May25 stage M1/A2 add original completed solve wall to resumed validation wall. Its DA phase wall already includes failed-phase wall. No idle downtime counted.',
  trajectory='MESS P/Q/SOC Actual from final QSAFE ACTUATOR/EXECUTION, DA from accepted final joint. SOC_kWh is Actual energy after slot; DA_SOC_kWh retains the stored battery_energy_kwh. route_or_leg is frozen DA route metadata. AIDC table is DA only; workload fields are GPU counts.',
  changes='Compare exact final Round1 and Round2 accepted DA decisions; no tolerance filters actual decision changes. Job changes count jobs; route/PQ changes count MESS-slot records.',
  aggregate='absolute_change = 2R minus 1R; relative=100*(2R-1R)/1R. Daily delta is 1R minus 2R. Unsuffixed better/equal/worse counts refer to Actual; DA/Fresh counts explicitly suffixed.'),
 optional_B0_B1_B2_included=optional)
(OUT/'EXTRACTION_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('EXTRACTION_PASS',[(n,len(r),len(payload['tables'][n]['columns'])) for n,r in ROWS.items()],flush=True)
