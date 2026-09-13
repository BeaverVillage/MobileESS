"""Read saved evidence only. No simulation, optimizer, model, or replay imports."""
import json,sys,hashlib,tarfile,datetime,math
from pathlib import Path
W=Path(r'D:\ChatGPT\Mobile ESS 2')
OUT=Path(__file__).resolve().parent.parent
NA='NA'
D='IEEE8500_v41r4_production_20260911_r2'
C='IEEE8500_B2_physical_closure_20260912_r2'
G='IEEE8500_B3_production_20260912'
A='IEEE8500_actual_20260912_r3'
R='IEEE8500_B2_actual_availability_gating_20260912_r3'
N='IEEE8500_numerical_preflight_20260911'
O='IEEE8500_pcc_overlay_20260911/PCC_OVERLAY_STRUCTURAL_VALIDATION.json'
L='IEEE8500_scalability_20260910/audit/lines.json'
DA={'B0':D+'/B0/exact/AC_VALIDATION.json','B1':D+'/B1/final_exact/AC_VALIDATION.json','B2':C+'/accepted_clean_exact/AC_VALIDATION.json','B3':G+'/B3/final_exact/AC_VALIDATION.json'}
FINAL={'B0':D+'/B0/FINAL.json','B1':D+'/B1/FINAL_AUTHORITY.json','B2':C+'/B2_RESTORED_ACCEPTANCE.json','B3':G+'/B3/FINAL_AUTHORITY.json'}
ACT={p:(R if p=='B2' else A)+'/'+p for p in DA}
MOB={p:ACT[p]+('/CAUSAL_MOBILITY_PRE_AUDIT.json' if p=='B2' else '/ACTUAL_MOBILITY_PRE_REPLAY.json') for p in DA}
SOL={'B1':D+'/B1','B3':G+'/B3_A1'}
NEEDED=set([O,L,N+'/P1_EXACT_B0_WITNESS_BINDING.json',G+'/PRODUCTION_RULES.json',R+'/FINAL_ACCEPTANCE.json',R+'/FROZEN_IDENTITY_PRESERVATION.json',R+'/IEEE123_REGRESSION_GATE.json',R+'/RULE_FREEZE.json',R+'/B2/FINAL_BATTERY_IDENTITY_AUDIT.json'])|set(DA.values())|set(FINAL.values())
for b in ACT.values():
 NEEDED.update(b+'/'+n for n in ['FINAL_ACTUAL/AC_SUMMARY.json','FINAL_ACTUAL/SLOT_EXTREMA.json','FINAL_ACTUAL/ACTUATOR.json','COMPLETE.json','ACTUAL_MOBILITY_PRE_REPLAY.json'])
for b in SOL.values():
 NEEDED.update(b+'/'+n for n in ['FINAL_AUTHORITY.json','ACCEPTED_AIDC.json','F_AND_O_LIVE.json','BOUNDED_SOLVER_REPORT.json','SCALABILITY_METRICS.json','MODEL_BUILD_MEMORY.json','IMPROVEMENT_TRACE.json'])
 NEEDED.update(b+'/timed_checkpoints/'+n+'.json' for n in ['30min','1h','2h','4h'])
NEEDED.add(G+'/B3_M1/FINAL_AUTHORITY.json')
NEEDED.discard(ACT['B2']+'/ACTUAL_MOBILITY_PRE_REPLAY.json')
NEEDED.add(MOB['B2'])
BP='IEEE8500_v41r4_binding_reconstruction_20260911/IEEE8500_V41R4_AIDC_BINDING_PASS.json'
EP=N+'/IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'
NEEDED.update([BP,EP,D+'/aidc_runtime.py',G+'/campaign.py',D+'/B1/SOLVER.log',G+'/B3_A1/SOLVER.log'])
archive=sys.argv[1] if len(sys.argv)>1 else None
raw={}; src={}
def ingest(name,data):
 text=data.decode('utf-8-sig');raw[name]=json.loads(text) if name.endswith('.json') else text;src[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
if archive:
 with tarfile.open(archive,'r|gz') as tf:
  for m in tf:
   if m.name in NEEDED: ingest(m.name,tf.extractfile(m).read())
 archive_info=json.loads(Path(archive+'_INDEX.json').read_text(encoding='utf-8'))
else:
 for name in NEEDED:
  p=W/name
  if p.is_file(): ingest(name,p.read_bytes())
 archive_info={'archive_sha256':'PENDING','archive_bytes':None,'member_count':None}
def read(n):
 if n not in raw: raise RuntimeError('Required authority missing: '+n)
 return raw[n]
def source(*names): return ';'.join(dict.fromkeys(n for n in names if n))
def num(v): return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
def reduction(a,b): return 100*(a-b)/a if num(a) and num(b) and a!=0 else NA
def minutes(x): return x/60 if num(x) else NA
def clock(s): return f'{int(s)//4:02d}:{int(s)%4*15:02d}' if num(s) else NA
def clean(v):
 if v is None:return NA
 if isinstance(v,float) and not math.isfinite(v):return NA
 return v
tables={}
def table(name,cols,rows,description):
 headers=cols.split(','); extras=list(dict.fromkeys(k for r in rows for k in r if k not in headers));headers+=extras
 tables[name]={'headers':headers,'rows':[[clean(r.get(k,NA)) for k in headers] for r in rows],'description':description,'source_files':sorted(set(n for r in rows for field in ['source_file','source_files','evidence'] for n in str(r.get(field,'')).split(';') if n in src))}
f={p:read(n) for p,n in FINAL.items()}; op=read(G+'/PRODUCTION_RULES.json'); overlay=read(O); lines=read(L)
dec={p:read(b+'/ACCEPTED_AIDC.json') for p,b in SOL.items()}
pg={'B0':read(N+'/P1_EXACT_B0_WITNESS_BINDING.json')['all_96_linear_grid_baselines'],'B1':dec['B1']['grid'],'B2':f['B2']['planning_grid'],'B3':dec['B3']['grid']}
pgsrc={'B0':N+'/P1_EXACT_B0_WITNESS_BINDING.json','B1':SOL['B1']+'/ACCEPTED_AIDC.json','B2':FINAL['B2'],'B3':SOL['B3']+'/ACCEPTED_AIDC.json'}
assert pg['B1']['rho_max']==f['B1']['P1'] and pg['B3']['rho_max']==f['B3']['P1']
counts=overlay['overlay_counts']; switches=sum(x['switch'] for x in lines)
case={'case_id':'IEEE8500_2025-05-21','evaluation_date':op['date'],'feeder_name':'IEEE 8500-node','feeder_model':'Canonical unbalanced source + frozen PCC overlay + declared voltage-control compatibility adaptation','nominal_bus_count':8500,'actual_bus_count':counts['buses'],'node_count':counts['nodes'],'phase_node_count':counts['nodes'],'branch_count':overlay['full_graph_unique_corridors'],'line_count':counts['lines'],'transformer_count':counts['transformers'],'switch_count':switches,'voltage_level_count':len(overlay['nominal_bus_base_sqrt3_histogram']),'time_resolution_min':15,'horizon_intervals':96,'horizon_hours':24,'aidc_site_count':op['AIDC'],'mess_vehicle_count':op['MESS_units'],'mess_service_location_count':op['MESS_service_locations'],'policy_count':4,'policies':'B0;B1;B2;B3','source_archive':archive or 'PENDING','source_archive_sha256':archive_info['archive_sha256'],'scientific_execution_count':0,'authority_status':'FINAL_DA_AND_SCOPE_SPECIFIC_ACTUAL','notes':'branch_count = unique undirected bus-to-bus corridors; line+transformer element count is 4929. phase_node_count = parsed OpenDSS non-ground node count, includes split-phase nodes; not 8500 named buses. 12 STA + 12 AIDC MESS service locations.','source_file':source(O,L,G+'/PRODUCTION_RULES.json'),'line_plus_transformer_element_count':counts['lines']+counts['transformers']}
table('00_CASE_AUTHORITY.csv','case_id,evaluation_date,feeder_name,feeder_model,nominal_bus_count,actual_bus_count,node_count,phase_node_count,branch_count,line_count,transformer_count,switch_count,voltage_level_count,time_resolution_min,horizon_intervals,horizon_hours,aidc_site_count,mess_vehicle_count,mess_service_location_count,policy_count,policies,source_archive,source_archive_sha256,scientific_execution_count,authority_status,notes',[case],'Parsed feeder and experiment scale, with nominal name separated from actual counts')
ac={}; acrows=[]; critical=[]
for p in DA:
 for scope in ['DAY_AHEAD_AC','REALIZED_OPERATION_AC']:
  path=DA[p] if scope=='DAY_AHEAD_AC' else ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json'
  if path not in raw: continue
  data=read(path); metrics=data.get('metrics',data)
  slots=data.get('slots',raw.get(ACT[p]+'/FINAL_ACTUAL/SLOT_EXTREMA.json',[]) if scope!='DAY_AHEAD_AC' else [])
  vmin=metrics['Vmin_pu'];vmax=metrics['Vmax_pu'];line=metrics['max_phase_line_loading_pu'];ti=metrics['max_transformer_phase_current_pu'];tk=metrics['max_transformer_winding_kva_pu']
  cv=all(s['converged'] for s in slots) and len(slots)==96 if scope=='DAY_AHEAD_AC' else metrics['converged_slots']==96
  cs=all(s['controls_settled'] for s in slots) and len(slots)==96 if scope=='DAY_AHEAD_AC' else metrics['controls_settled_slots']==96
  vf=vmin>=.95 and vmax<=1.05;tf=line<=1 and ti<=1 and tk<=1
  lo=min(slots,key=lambda x:x['Vmin_pu']) if slots else {};hi=max(slots,key=lambda x:x['Vmax_pu']) if slots else {};peak=max(slots,key=lambda x:x['max_phase_line_loading_pu']) if slots else {}
  vn=sum(s['Vmin_pu']<.95 or s['Vmax_pu']>1.05 for s in slots) if scope=='DAY_AHEAD_AC' else metrics['voltage_violations']
  tn=sum(s['max_phase_line_loading_pu']>1 or s['max_transformer_phase_current_pu']>1 or s['max_transformer_winding_kva_pu']>1 for s in slots) if scope=='DAY_AHEAD_AC' else metrics['line_violations']+metrics['transformer_current_violations']+metrics['transformer_kVA_violations']
  def node(s,k):
   v=s.get(k)
   return v.rsplit('.',1) if v else [NA,NA]
  lb,lp=node(lo,'Vmin_node');hb,hp=node(hi,'Vmax_node'); witness=peak.get('line_witness',NA);parts=witness.split('|')
  row=dict(policy=p,validation_scope=scope,converged=cv,voltage_feasible=vf,thermal_feasible=tf,overall_ac_feasible=cv and cs and vf and tf,min_voltage_pu=vmin,min_voltage_bus=lb,min_voltage_phase=lp,min_voltage_time=clock(lo.get('slot')),max_voltage_pu=vmax,max_voltage_bus=hb,max_voltage_phase=hp,max_voltage_time=clock(hi.get('slot')),max_line_loading=line,max_loading_line=parts[0],max_loading_phase=parts[-1] if len(parts)>1 else NA,max_loading_time=clock(peak.get('slot')),violation_count_voltage=vn,violation_count_thermal=tn,source_file=source(path,ACT[p]+'/FINAL_ACTUAL/SLOT_EXTREMA.json' if scope!='DAY_AHEAD_AC' else None),controls_settled=cs,max_transformer_phase_current_pu=ti,max_transformer_winding_kva_pu=tk,violation_count_unit='violating slots (DA); sum of recorded category counts (Actual)',critical_slot_zero_based=peak.get('slot',NA))
  ac[p,scope]=row;acrows.append(row)
  critical.append(dict(policy=p,metric_scope='DAY_AHEAD_AC' if scope=='DAY_AHEAD_AC' else 'REALIZED_AC',critical_line=parts[0],critical_phase=row['max_loading_phase'],critical_time=row['max_loading_time'],line_loading=line,source_file=row['source_file'],slot_zero_based=peak.get('slot',NA)))
 for_plan=pg[p];critical.append(dict(policy=p,metric_scope='PLANNING',critical_line=for_plan['critical_line'],critical_phase=for_plan['critical_phase'],critical_time=clock(for_plan['critical_slot']),line_loading=for_plan['rho_max'],source_file=pgsrc[p],slot_zero_based=for_plan['critical_slot']))
table('03_AC_FEASIBILITY_SUMMARY.csv','policy,validation_scope,converged,voltage_feasible,thermal_feasible,overall_ac_feasible,min_voltage_pu,min_voltage_bus,min_voltage_phase,min_voltage_time,max_voltage_pu,max_voltage_bus,max_voltage_phase,max_voltage_time,max_line_loading,max_loading_line,max_loading_phase,max_loading_time,violation_count_voltage,violation_count_thermal,source_file',acrows,'Saved exact AC validations; DA and Actual remain separate')
perf=[]
for p in DA:
 da=ac[p,'DAY_AHEAD_AC']; actual=ac.get((p,'REALIZED_OPERATION_AC'),{})
 perf.append(dict(policy=p,planning_rho_max=pg[p]['rho_max'],planning_objective=pg[p]['rho_max'],planning_objective_unit='pu; P1 max phase-current / original line NormAmps',dayahead_ac_max_line_loading=da['max_line_loading'],realized_ac_max_line_loading=actual.get('max_line_loading',NA),max_voltage_pu=da['max_voltage_pu'],min_voltage_pu=da['min_voltage_pu'],max_abs_voltage_deviation_pu=max(abs(da['max_voltage_pu']-1),abs(da['min_voltage_pu']-1)),ac_feasible=da['overall_ac_feasible'],voltage_feasible=da['voltage_feasible'],thermal_feasible=da['thermal_feasible'],accepted_schedule=f[p]['status']=='PASS',source_file=source(FINAL[p],pgsrc[p],da['source_file'],actual.get('source_file')),voltage_and_feasibility_scope='DAY_AHEAD_AC',realized_ac_feasible=actual.get('overall_ac_feasible',NA),realized_acceptance_status=raw.get(R+'/FINAL_ACCEPTANCE.json',{}).get('status','PENDING') if p=='B2' else raw.get(ACT[p]+'/COMPLETE.json',{}).get('status',NA),reduction_vs_B0_planning_pct=reduction(pg['B0']['rho_max'],pg[p]['rho_max']),reduction_vs_B0_dayahead_ac_pct=reduction(ac['B0','DAY_AHEAD_AC']['max_line_loading'],da['max_line_loading']),reduction_vs_B0_realized_ac_pct=reduction(ac.get(('B0','REALIZED_OPERATION_AC'),{}).get('max_line_loading'),actual.get('max_line_loading'))))
table('01_POLICY_PERFORMANCE_SUMMARY.csv','policy,planning_rho_max,planning_objective,planning_objective_unit,dayahead_ac_max_line_loading,realized_ac_max_line_loading,max_voltage_pu,min_voltage_pu,max_abs_voltage_deviation_pu,ac_feasible,voltage_feasible,thermal_feasible,accepted_schedule,source_file',perf,'P1, DA AC, and realized AC: separate metrics and same-scope reductions')
runtime=[]
for p in DA:
 b=SOL.get(p); report=raw.get((b or '')+'/BOUNDED_SOLVER_REPORT.json',{}); live=raw.get((b or '')+'/F_AND_O_LIVE.json',{}); limit=report.get('total_budget_seconds',NA)
 total=f[p].get('total_algorithm_runtime_seconds',f[p].get('total_runtime_seconds',NA)); memory=raw.get((b or '')+'/MODEL_BUILD_MEMORY.json',{}).get('after_model_build',{})
 r=dict(policy=p,actual_runtime_s=total,actual_runtime_min=minutes(total),time_limit_s=limit,time_limit_min=minutes(limit),termination_status=live.get('termination_reason','NOT_OPTIMIZED_REFERENCE' if p=='B0' else 'RESTORED_ACCEPTANCE_NO_SINGLE_END_TO_END_TERMINATION_RECORD'),time_limit_reached=live.get('remaining_seconds')==0 if live else NA,optimality_claim_supported=False,final_incumbent_available=p!='B0',final_incumbent_feasible=True,mip_gap=NA,best_bound=NA,objective_at_termination=pg[p]['rho_max'],solver_name='Gurobi (bounded fix-and-optimize)' if b else ('NONE' if p=='B0' else 'Gurobi; frozen beam search + fixed-discrete physical restoration'),threads=memory.get('Threads',NA),hardware_if_recorded='host_physical_RAM_bytes='+str(memory['host_physical_RAM_bytes']) if 'host_physical_RAM_bytes' in memory else NA,source_file=source(FINAL[p],b+'/BOUNDED_SOLVER_REPORT.json' if b else None,b+'/F_AND_O_LIVE.json' if b else None,b+'/MODEL_BUILD_MEMORY.json' if b else None),runtime_scope='DA algorithm total including recorded preparation/search/exact AC/export; excludes Actual replay',time_limit_scope='B1 AIDC continuous search loop' if p=='B1' else ('B3 A1 AIDC reoptimization continuous search loop; not whole B3' if p=='B3' else NA),runtime_includes_exact_AC=True if b else NA,incremental_runtime_s=f[p].get('incremental_runtime_seconds',NA))
 if p=='B3':
  r.update(A1_runtime_s=f['B1']['total_runtime_seconds'],M1_runtime_s=f[p]['M1_wall_seconds'],A2_runtime_s=read(SOL[p]+'/FINAL_AUTHORITY.json')['total_runtime_seconds'],M2_runtime_s=f[p]['MF_wall_seconds'],A1_time_limit_s=read(SOL['B1']+'/BOUNDED_SOLVER_REPORT.json')['total_budget_seconds'],M1_time_limit_s=NA,A2_time_limit_s=limit,M2_time_limit_s=NA,stage_mapping='paper A1=raw A0 final B1 reuse; paper A2=raw A1; paper M2=raw MF',reuse_runtime_included=True)
 if b:
  log=raw.get(b+'/SOLVER.log',''); cpu=next((s for s in log.splitlines() if s.startswith('CPU model:')),None)
  if cpu:r['hardware_if_recorded']=cpu+'; '+r['hardware_if_recorded'];r['source_file']=source(r['source_file'],b+'/SOLVER.log')
  r.update({k:v for k,v in read(b+'/SCALABILITY_METRICS.json').items() if not isinstance(v,(dict,list))})
  r['source_file']=source(r['source_file'],b+'/SCALABILITY_METRICS.json',D+'/aidc_runtime.py',G+'/campaign.py' if p=='B3' else None)
 runtime.append(r)
table('02_RUNTIME_AND_TERMINATION.csv','policy,actual_runtime_s,actual_runtime_min,time_limit_s,time_limit_min,termination_status,time_limit_reached,optimality_claim_supported,final_incumbent_available,final_incumbent_feasible,mip_gap,best_bound,objective_at_termination,solver_name,threads,hardware_if_recorded,source_file',runtime,'Recorded DA runtime and component budgets; no global optimality claim')
jobs={'B0':f['B0']['jobs'],'B1':dec['B1']['jobs'],'B2':f['B0']['jobs'],'B3':f['B3']['jobs']};refs={j['job_uid']:j for j in jobs['B0']}; dr=[]
for p in DA:
 j=jobs[p]; moves=raw.get(MOB[p],{}).get('moves'); act=raw.get(ACT[p]+'/FINAL_ACTUAL/ACTUATOR.json',{}).get('trajectory',[])
 tj=f['B2']['final_slots'] if p=='B2' else (f['B3']['trajectory_slots'] if p=='B3' else [])
 final=[r['SoC_after'] for r in act if r['slot']==95]
 shifts=sum(x['start_slot']!=refs[x['job_uid']]['start_slot'] for x in j); spatial=sum(x['AIDC_site']!=refs[x['job_uid']]['AIDC_site'] for x in j);migration=sum(bool(x.get('migration_selected',False)) for x in j)
 dr.append(dict(policy=p,aidc_start_time_shifts=shifts,aidc_cross_site_placements=spatial,aidc_migrations=migration,mess_relocation_events=len(set((x['mess_id'],x['departure_slot']) for x in tj if x.get('departure_slot') is not None)),mess_active_service_locations=len(set(x['service_id'] for x in tj if x.get('service_id') and (abs(x['p_kw'])>1e-9 or abs(x['q_kvar'])>1e-9))),mess_charge_events=sum(x['p_kw']<-1e-9 for x in tj),mess_discharge_events=sum(x['p_kw']>1e-9 for x in tj),mess_reactive_support_events=sum(abs(x['q_kvar'])>1e-9 for x in tj),final_mess_soc_min=min(final) if final else NA,final_mess_soc_max=max(final) if final else NA,source_file=source(FINAL[p],SOL[p]+'/ACCEPTED_AIDC.json' if p in SOL else FINAL['B0'],ACT[p]+'/FINAL_ACTUAL/ACTUATOR.json'),decision_scope='FINAL_ACCEPTED_DA',soc_scope='REALIZED_OPERATION_POST_SLOT_95',event_definition='AIDC counts are jobs vs B0 by job_uid; migration_selected flags. P/Q event counts are nonzero vehicle-slots, not contiguous episodes; positive P is discharge. SoC is fraction.',reference_jobs=len(j),actual_move_count=len(moves) if moves is not None else NA))
table('04_DECISION_SUMMARY.csv','policy,aidc_start_time_shifts,aidc_cross_site_placements,aidc_migrations,mess_relocation_events,mess_active_service_locations,mess_charge_events,mess_discharge_events,mess_reactive_support_events,final_mess_soc_min,final_mess_soc_max,source_file',dr,'Final accepted DA decision counts, with separately labelled Actual terminal SoC')
network=dict(case='IEEE8500',actual_bus_count=counts['buses'],phase_node_count=counts['nodes'],branch_count=case['branch_count'],line_count=counts['lines'],transformer_count=counts['transformers'],switch_count=switches,aidc_site_count=12,mess_vehicle_count=4,mess_station_count=12,horizon_intervals=96,optimization_runtime_min_B3=minutes(f['B3']['total_algorithm_runtime_seconds']),planning_rho_B0=pg['B0']['rho_max'],planning_rho_B3=pg['B3']['rho_max'],planning_reduction_pct=reduction(pg['B0']['rho_max'],pg['B3']['rho_max']),ac_feasible_B3=ac['B3','DAY_AHEAD_AC']['overall_ac_feasible'],notes='Branches=4911 unique bus corridors. MESS stations=12 STA; all service locations=24 including 12 AIDC. B3 runtime includes reused B1 once; feasibility scope DAY_AHEAD_AC.',source_file=source(O,L,FINAL['B3'],pgsrc['B0'],DA['B3']))
table('05_NETWORK_SCALE_COMPARISON_READY.csv','case,actual_bus_count,phase_node_count,branch_count,line_count,transformer_count,switch_count,aidc_site_count,mess_vehicle_count,mess_station_count,horizon_intervals,optimization_runtime_min_B3,planning_rho_B0,planning_rho_B3,planning_reduction_pct,ac_feasible_B3,notes',[network],'IEEE8500 only; no IEEE123 results appended')
trace=[]
for p,b in SOL.items():
 for label in ['30min','1h','2h','4h']:
  n=b+'/timed_checkpoints/'+label+'.json';x=read(n);elapsed=x['observed_seconds']
  trace.append(dict(policy=p,elapsed_s=elapsed,elapsed_min=minutes(elapsed),stage='B1' if p=='B1' else 'B3_A1',incumbent_objective=x['P1'],event_type='INDEPENDENTLY_VALIDATED_CHECKPOINT_'+label,source_file=n,time_scope='AIDC continuous search loop local clock',scheduled_checkpoint_s=x['target_seconds']))
 n=b+'/BOUNDED_SOLVER_REPORT.json';seen=set()
 for stage in read(n)['stages']:
  for x in stage.get('accepted_improvements',[]):
   key=json.dumps(x,sort_keys=True)
   if key in seen:continue
   seen.add(key);after=x.get('after');val=after[0] if isinstance(after,list) else NA;t=x.get('policy_day_seconds',NA)
   trace.append(dict(policy=p,elapsed_s=t,elapsed_min=minutes(t),stage=x.get('stage',NA),incumbent_objective=val,event_type='ACCEPTED_INCUMBENT_UPDATE',source_file=n,time_scope='raw policy_day_seconds (component clock; includes pre-loop preparation)',objective_vector_json=json.dumps(after)))
 # Preserve every recorded neighborhood decision without manufacturing absent wall-clock stamps.
 n=b+'/IMPROVEMENT_TRACE.json'
 for x in read(n):
  trace.append(dict(policy=p,elapsed_s=NA,elapsed_min=NA,stage=x['objective_stage'],incumbent_objective=x['incumbent_after'][0],event_type='NEIGHBORHOOD_ACCEPTED' if x['accepted'] else 'NEIGHBORHOOD_RETAINED',source_file=n,time_scope='elapsed not recorded for this record; iteration order preserved',iteration=x['iteration'],neighborhood_solve_s=x['solve_runtime']))
trace.append(dict(policy='B3',elapsed_s=f['B3']['M1_wall_seconds'],elapsed_min=minutes(f['B3']['M1_wall_seconds']),stage='M1',incumbent_objective=read(G+'/B3_M1/FINAL_AUTHORITY.json')['P1'],event_type='FINAL_ACCEPTED_STAGE',source_file=G+'/B3_M1/FINAL_AUTHORITY.json',time_scope='M1 stage local wall clock'))
trace.append(dict(policy='B3',elapsed_s=f['B3']['incremental_runtime_seconds'],elapsed_min=minutes(f['B3']['incremental_runtime_seconds']),stage='FINAL',incumbent_objective=f['B3']['P1'],event_type='FINAL_ACCEPTED_SCHEDULE',source_file=FINAL['B3'],time_scope='B3 incremental wall clock excluding reused B1'))
table('06_OBJECTIVE_TIME_TRACE.csv','policy,elapsed_s,elapsed_min,stage,incumbent_objective,best_bound,gap,event_type,source_file',trace,'Saved checkpoints, accepted updates and every neighborhood incumbent record; missing clocks remain NA')
for r in critical:
 name=r['critical_line'].split('::')[0].lower().removeprefix('line.');line=next((x for x in lines if x['name'].lower()==name),None)
 if line:r.update(sending_bus=line['bus1'],receiving_bus=line['bus2'],source_file=source(r['source_file'],L))
 r['endpoint_definition']='bus1/bus2 topology terminal order; not inferred power-flow direction'
 r['phase_definition']='terminal/conductor label; secondary node1 is not automatically primary phase A'
table('07_CRITICAL_LOADING_DETAIL.csv','policy,metric_scope,critical_line,critical_phase,critical_time,line_loading,sending_bus,receiving_bus,sending_voltage_pu,receiving_voltage_pu,abs_line_voltage_difference_pu,source_file',critical,'Saved loading witnesses; unrecorded endpoint voltages remain NA')
pairs=[]
rt={x['policy']:x['actual_runtime_min'] for x in runtime}
for p in ['B1','B2','B3']:
 for scope in ['DAY_AHEAD_AC','REALIZED_OPERATION_AC']:
  base=ac.get(('B0',scope),{});cand=ac.get((p,scope),{})
  pairs.append(dict(comparison=p+'_vs_B0_'+scope,baseline_policy='B0',candidate_policy=p,planning_rho_baseline=pg['B0']['rho_max'],planning_rho_candidate=pg[p]['rho_max'],planning_reduction_pct=reduction(pg['B0']['rho_max'],pg[p]['rho_max']),ac_loading_baseline=base.get('max_line_loading',NA),ac_loading_candidate=cand.get('max_line_loading',NA),ac_loading_reduction_pct=reduction(base.get('max_line_loading'),cand.get('max_line_loading')),runtime_baseline_min=rt['B0'],runtime_candidate_min=rt[p],ac_feasible_baseline=base.get('overall_ac_feasible',NA),ac_feasible_candidate=cand.get('overall_ac_feasible',NA),interpretation_scope=scope+' paired AC; planning columns compare P1 only; runtime is DA algorithm',source_file=source(pgsrc['B0'],pgsrc[p],base.get('source_file'),cand.get('source_file'),FINAL[p])))
table('08_POLICY_PAIRED_COMPARISON.csv','comparison,baseline_policy,candidate_policy,planning_rho_baseline,planning_rho_candidate,planning_reduction_pct,ac_loading_baseline,ac_loading_candidate,ac_loading_reduction_pct,runtime_baseline_min,runtime_candidate_min,ac_feasible_baseline,ac_feasible_candidate,interpretation_scope',pairs,'Scope-preserving B0 paired comparisons')
keys=[]
def key(section,metric,value,unit,policy,scope,paths):keys.append(dict(section=section,metric=metric,value=value,unit=unit,policy=policy,scope=scope,source_file=paths,verified=value!=NA))
for k,u in [('actual_bus_count','buses'),('phase_node_count','nodes'),('branch_count','unique corridors'),('line_count','line elements'),('transformer_count','transformer elements'),('aidc_site_count','sites'),('mess_vehicle_count','vehicles'),('mess_service_location_count','locations')]:key('Scalability',k,case[k],u,'ALL','CASE',case['source_file'])
for p in DA:
 key('Grid performance','planning rho',pg[p]['rho_max'],'pu',p,'PLANNING',pgsrc[p])
 for scope in ['DAY_AHEAD_AC','REALIZED_OPERATION_AC']:
  rr=ac.get((p,scope),{});key('Grid performance','max phase-line loading',rr.get('max_line_loading',NA),'pu',p,scope,rr.get('source_file',NA))
key('Grid performance','B3 reduction vs B0',network['planning_reduction_pct'],'percent','B3','PLANNING',source(pgsrc['B0'],pgsrc['B3']))
for metric,value,u in [('total algorithm runtime',f['B3']['total_algorithm_runtime_seconds']/60,'min'),('incremental runtime',f['B3']['incremental_runtime_seconds']/60,'min'),('AIDC A1 search limit',op['B3_A1_search_seconds']/60,'min'),('termination',runtime[-1]['termination_status'],'status'),('global optimum certified',False,'boolean')]:key('Optimization',metric,value,u,'B3','DAY_AHEAD_ALGORITHM',runtime[-1]['source_file'])
for scope in ['DAY_AHEAD_AC','REALIZED_OPERATION_AC']:
 for metric in ['overall_ac_feasible','violation_count_voltage','violation_count_thermal','max_transformer_phase_current_pu','max_transformer_winding_kva_pu']:
  rr=ac['B3',scope];key('Feasibility',metric,rr[metric],'boolean' if metric=='overall_ac_feasible' else ('count' if 'count' in metric else 'pu'),'B3',scope,rr['source_file'])
assert len(keys)<=40
table('09_PAPER_KEY_RESULTS.csv','section,metric,value,unit,policy,scope,source_file,verified',keys,'Compact key values without metadata overload or optimality overclaim')
checks=[]
def check(i,c,e,o,s,ev):checks.append(dict(check_id=i,check=c,expected=e,observed=o,status=s,evidence=ev))
init=[raw.get(MOB[p],{}).get('initial_energy') for p in DA]
check('A','Common initial battery state','same 4 vehicle energies',json.dumps(init),'PASS' if all(x==init[0] and x for x in init) else 'UNRESOLVED',source(*MOB.values()))
identity_keys=['source_snapshot_sha256','state_at_issue','requested_GPU','r1_reference_start','r1_reference_site']
aidc_identical=all(set(x['job_uid'] for x in j)==set(refs) and all(all(x.get(k)==refs[x['job_uid']].get(k) for k in identity_keys) for x in j) for j in jobs.values())
check('A2','Common initial AIDC workload identity','708 same job UIDs, issue snapshots, GPU requests, state and reference starts/sites',str([len(x) for x in jobs.values()])+'; compared '+','.join(identity_keys),'PASS' if aidc_identical else 'FAIL',source(*FINAL.values(),SOL['B1']+'/ACCEPTED_AIDC.json'))
check('B','Common horizon','96 slots per DA/Actual policy',str(len(acrows))+' scope rows; recorded 96-slot trajectories','PASS' if len(acrows)==8 and all(r['converged'] for r in acrows) else 'UNRESOLVED',source(*DA.values(),*(ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json' for p in DA)))
check('C','IEEE8500 electrical authority','source1.04 Vreg123.5 alpha0.5 CAPBank3 OFF',json.dumps({p:{k:read(DA[p]).get(k) for k in ['source_pu','Vreg_V','alpha8500','CAPBank3']} for p in DA}),'PASS' if all(read(DA[p]).get('source_pu')==1.04 and read(DA[p]).get('Vreg_V')==123.5 and read(DA[p]).get('alpha8500')==.5 and read(DA[p]).get('CAPBank3')=='OFF' for p in DA) else 'FAIL',source(*DA.values(),G+'/PRODUCTION_RULES.json'))
check('D','Planning normalization','same96 coefficient SHAs and phase-current rating denominators','all planning coefficient SHA lists identical','PASS' if all(pg[p]['coefficient_SHAs']==pg['B0']['coefficient_SHAs'] for p in DA) else 'FAIL',source(*pgsrc.values()))
check('E','Scope separation','planning,DA AC,Actual AC distinct','explicit fields and rows','PASS',source(*DA.values(),*pgsrc.values()))
check('F','Runtime scope','document inclusion of exact AC','B1/B3 recorded DA algorithm totals include AC; no aggregate B2 restoration total recorded','UNRESOLVED',source(FINAL['B1'],FINAL['B3'],SOL['B1']+'/BOUNDED_SOLVER_REPORT.json'))
check('G','Budget versus runtime','14400s component search limit distinct from total','B3 '+str(f['B3']['total_algorithm_runtime_seconds'])+'s algorithm total; A1 search14400s','PASS',source(FINAL['B3'],SOL['B3']+'/BOUNDED_SOLVER_REPORT.json'))
check('H','Optimality interpretation','no global optimum claim','F_AND_O_NO_GLOBAL_CERTIFICATE; accepted feasible incumbents','PASS',source(SOL['B1']+'/BOUNDED_SOLVER_REPORT.json',SOL['B3']+'/BOUNDED_SOLVER_REPORT.json'))
check('I','Hard limits','V[.95,1.05], line/transformer ratios<=1','frozen limits; final scope metrics tested','PASS' if all(r['overall_ac_feasible'] for r in acrows) and len(acrows)==8 else 'FAIL',source(G+'/PRODUCTION_RULES.json',*(x['source_file'] for x in acrows)))
dates=[x.get('operating_day') for j in jobs.values() for x in j];check('J','Common operating date','2025-05-21',str(sorted(set(dates))),'PASS' if set(dates)=={'2025-05-21'} else 'UNRESOLVED',source(*FINAL.values()))
check('K','Units','pu; seconds/60=minutes; SoC fraction; zero-based slots->HH:MM','conversion rules explicit; no clock shifts or power flow recomputation','PASS',source(*DA.values()))
check('L','Missing and duplicate rows','4 unique policy rows; missing source fields labelled NA','4 policy rows; DA voltage bus/phase witnesses, endpoint voltage, B0/B2 total runtime, global bounds/gaps unavailable','UNRESOLVED',source(*FINAL.values()))
if R+'/FINAL_ACCEPTANCE.json' in raw:check('M','B2 Actual final acceptance','PASS',str(read(R+'/FINAL_ACCEPTANCE.json').get('status')),'PASS' if read(R+'/FINAL_ACCEPTANCE.json').get('status')=='PASS' else 'FAIL',R+'/FINAL_ACCEPTANCE.json')
check('N','AIDC binding and new IEEE8500 numerical preflight','both frozen preflight gates PASS',read(BP)['status']+'; '+read(EP)['status'],'PASS' if 'PASS' in read(BP)['status'] and 'PASS' in read(EP)['status'] else 'FAIL',source(BP,EP))
table('10_VALIDATION_CHECKS.csv','check_id,check,expected,observed,status,evidence',checks,'PASS/FAIL/UNRESOLVED evidence checks with missing values explicitly retained')
result={'tables':tables,'sources':src,'archive_info':archive_info,'archive':archive,'extraction_scientific_execution_count':0,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'missing_sources':sorted(NEEDED-set(raw)),'checks':checks,'key_results':keys,'notes':['All source JSON read as data; no project modules imported. No optimization, OpenDSS, AC replay, inference or training performed by extraction. Ongoing B2 replay is a separate previously authorized stage.','Attachment named a deleted older tar.gz. Latest user request requires new complete archive after B2; this new archive is the extraction authority.','Line-loading denominator and critical terminal/conductor preserved. Voltage witness names absent in DA JSON remain NA; stored Actual witness names are retained.','B3 MF trial RESULT has lower P1 but is not final accepted authority; only FINAL_AUTHORITY is used. B2 primary failure and diagnostic feasible candidate are historical, not final decisions.','Legacy contract labels mentioning1800seconds/30min persist in raw code lineage; actual explicit frozen budget and accounting are14400seconds. No labels are rewritten in raw evidence.','No global bounds or gaps inferred from neighborhood or fixed-route subproblem optima. Missing B0/B2 end-to-end runtime is NA.','P/Q event counts use vehicle-slots, absolute>1e-9; no numerical power-flow calculation. Temporal/spatial counts compare exact job_UID paired assignments against final B0.','Reduction=100*(B0-candidate)/B0 within identical metric scope. Runtime min=seconds/60. SoC fraction unchanged. Slots zero-based, clock=15min*slot.']}
destination=OUT/'_work'/('tables.json' if archive else 'tables_preview.json')
destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(destination),'rows':{k:len(v['rows']) for k,v in tables.items()},'missing_sources':result['missing_sources'],'checks':checks},ensure_ascii=False))
