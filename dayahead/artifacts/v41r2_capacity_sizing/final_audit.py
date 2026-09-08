"""Final user-steered audit: include D-day UNASSIGNED in system demand.

This is a separate read-only study. No production capacity, job, electrical,
policy, model, manifest or reference is written. See audit.py for helpers.
"""
from audit import *
from copy import deepcopy
import ast, heapq

def psource(relative,needles):
 p=ROOT/relative;lines=p.read_text(encoding='utf-8').splitlines()
 return dict(**provenance(p),locations=[dict(line=i+1,text=l.strip()) for i,l in enumerate(lines) if any(n in l for n in needles)])

def source_authority():
 a=read(CAP);r=read(RACK);w=pd.read_csv(WEIGHTS);c=np.array(a['canonical_GPU_vector'])
 current=read(OUT/'CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json')
 current['case']='A'
 current['decision']='Preserve frozen V39C engineering heterogeneity through one common multiplier. The exact historical allocator is fixed-total and not a scalable general apportioner; extending its one-pass rank loop beyond 12 blocks loses total capacity. This permitted CASE A fallback retains its service floors/ranks and 4-GPU-node architecture without fitting May geography.'
 exact=psource('dayahead/v39c/freeze.py',['def construct_capacity','nodes =','full_blocks, residual_nodes','for site in order[:full_blocks]','nodes[order[0]]','nodes !=','sum(nodes.values())'])
 current['exact_allocator']=dict(source=exact,formula='base 8 nodes/site; divmod((156 - 12*8),8) -> 7 blocks,4 residual nodes; add one 8-node block to top seven facility weights; add residual four nodes to highest-weight site.',
    reconstructed_vector=[(8+(8 if s in a['facility_weight_order'][:7] else 0)+(4 if s==a['facility_weight_order'][0] else 0))*4 for s in SITES],
    scalable_domain='One-pass numeric rule conserves total only for fewer than 13 full residual blocks; hard-coded NODE_TOTAL and EXPECTED_NODE_CAPACITY assertions additionally restrict actual production function to 624.',
    decision='Do not invent a cycling or proportional-residual allocator. Use original task CASE A common-alpha enlargement of the independently frozen vector.',
    latest_user_preference='Reuse exact V39C philosophy/algorithm where possible; no equalization, no per-site May utilization fitting.')
 assert current['exact_allocator']['reconstructed_vector']==a['canonical_GPU_vector']
 for row in current['rows']:
  s=row['site'];row['source_field']=f'site_table[{SITES.index(s)}].synthetic_H100_equivalent_GPU_capacity'
  row['source_line']=next(i+1 for i,l in enumerate(CAP.read_text().splitlines()) if f'"AIDC": "{s}"' in l)
  row['source_SHA256']=sha(CAP);row['creating_commit']=current['source']['creating_commit']
 current['rack_compatibility_source']=psource('dayahead/v38/authority.py',['class RackPool','class CapacityAuthority','def eligible_racks','row.historical_gpu_capacity +'])
 write('CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json',current)
 history=read(OUT/'HISTORICAL_SITE_SCALE_AUTHORITY.json')
 blob=subprocess.check_output(['git','-C',str(ROOT),'show','499d5793ed4b725fa5d0b38691b07752c4f88482:'+WEIGHTS.relative_to(ROOT).as_posix()])
 history['PR12_weight_blob_SHA256']=hashlib.sha256(blob).hexdigest()
 history['PR12_weights_exact_bytes_equal_local']=blob==WEIGHTS.read_bytes();assert blob==WEIGHTS.read_bytes()
 history['historical_generator']=psource('dayahead/tools/build_v22sr1_final_operating_scale.py',['site_specs =','capacity_total =','weights =','"GPU_weight_authority"'])
 history['field_name_note']='Prompt display phrase resolves to repository field primary_IT_equivalent_capacity_MW; the field label is not quoted as a literal repository header.'
 write('HISTORICAL_SITE_SCALE_AUTHORITY.json',history)
 return current,history,c,r

def categorize(cohorts,jobrows):
 categorized=[];counts=Counter();gpuwork=Counter();amb=[]
 for r in jobrows:
  row=dict(r)
  if r['D00_state']=='COMPLETE':cat='PRE_D00_COMPLETE';reason='Reference service already complete before D00; no resurrection.'
  elif not r['assigned'] and r['D00_state']=='RUNNING':
   cat='AMBIGUOUS_UNASSIGNED';reason='RW finished before D00 so no site assigned; Q90 extension overlaps D00. No physical running site exists. Conservative residual counted in system demand only.';amb.append(row)
  elif r['D00_state']=='RUNNING':cat='D_DAY_RUNNING_RESIDUAL';reason='Frozen D00 source/rack and remaining Q90/requested-residual execution held fixed.'
  else:
   cat='D_DAY_PENDING_OFFERED';reason='Known and PENDING at D-1 issue; V37 _first_fit starts search at 0 and has no exogenous not-before field. At fixed D00 boundary, job remains eligible immediately. Old start >=120 is capacity waiting, not a future release.'
  row.update(cohort=cat,classification_reason=reason,nominal_start=24 if cat=='D_DAY_PENDING_OFFERED' else r['reference_start'],
    nominal_start_basis='Existing causal readiness clipped to D00; removes resource waiting only; no temporal objective.' if cat=='D_DAY_PENDING_OFFERED' else 'Preserved reference state')
  counts[cat]+=1;gpuwork[cat]+=r['GPU']*(r['D00_residual_slots'] if r['D00_state']=='RUNNING' else r['duration_slots'])/4
  categorized.append(row)
 pd.DataFrame(categorized).to_csv(OUT/'UNASSIGNED_AND_DDAY_COHORT_CLASSIFICATION.csv',index=False)
 u=[r for r in categorized if not r['assigned']]
 audit=dict(rules=dict(D_DAY='Frozen D00 residual plus issue-visible ready pending, including missing sites.',
    POST_H='Require independent pre-capacity nominal release >=120; constrained RW/Q90 start alone is not sufficient.',
    AMBIGUOUS='No invented source for Q90-expanded preday UNASSIGNED intervals.'),
    cohort_counts=dict(counts),cohort_full_remaining_GPU_hours=dict(gpuwork),
    unassigned_counts=dict(Counter(r['cohort'] for r in u)),
    historical_POST_H_UNASSIGNED_job_observations=sum(not r['assigned'] and r['reference_start']>=120 for r in categorized),
    POST_H_BACKLOG=dict(authoritative_future_release_job_count=0,GPU_hours=0,reason='No independent future release exists in this issue-visible cohort. Historical post-H timestamps are endogenous 624-GPU queue outputs.'),
    AMBIGUOUS_UNASSIGNED=dict(job_observations=len(amb),Day_D_GPU_hours=11.0,rows=amb,
       treatment='Include conservatively in aggregate denominator; exclude from fixed-source site rematerialization and report unresolved. No fabricated AIDC.'),
    authority=psource('dayahead/v37/aidc_materializer.py',['def _first_fit','start = 0','def schedule','start = _first_fit']),
    site_filter=psource('dayahead/v39a/spatial.py',['def production_activity','start = max(TARGET_OFFSET_SLOTS','end = min(TARGET_OFFSET_SLOTS','if start >= end']),
    boundary_condition='Independent Day-D counterfactual anchored at D00. Does not claim a capacity-free evolution before D00. All ready pending starts nominally at slot24; their old delayed starts are not input releases.')
 write('UNASSIGNED_CAUSE_AND_COHORT_AUDIT.json',audit)
 return categorized,audit

def scheduler(day,rows,cap):
 """Resource-only adaptation of tier/FIFO + current site/rack eligibility.

 V39D first placement permits all compatible sites with numeric AIDC tie.
 V41R1 baseline only fits within frozen sites and cannot re-admit. Therefore
 this pure replay adapts these source rules, it does not claim to call the
 existing globally solved V39D cohort placement oracle.
 """
 maxend=max(120,max(r['duration_slots'] for r in rows)+24)+sum(r['duration_slots'] for r in rows)+1
 # Dense 120+tail array avoids capacity interval approximations. Tail bound
 # serializes all finite admitted work and is therefore conservative.
 load=np.zeros((maxend,12),dtype=np.int32)
 results=[];pending=[];events={24};now=24
 for row in rows:
  r=dict(row);cat=r['cohort']
  if cat=='D_DAY_RUNNING_RESIDUAL':
   i=SITES.index(r['site']);b=r['reference_start']+r['duration_slots']
   load[24:b,i]+=r['GPU'];assert np.all(load[24:b,i]<=cap[i]);events.add(b)
   r.update(new_site=r['site'],new_start=r['reference_start'],new_end=b,status='FIXED_RUNNING',rack=r['site']+'_LP01');results.append(r)
  elif cat=='D_DAY_PENDING_OFFERED':pending.append(r)
  elif cat=='AMBIGUOUS_UNASSIGNED':
   r.update(new_site=None,new_start=None,new_end=None,status='AMBIGUOUS_NO_FROZEN_SOURCE',rack=None);results.append(r)
 pending.sort(key=lambda r:tuple(r['priority_key']))
 compatible={r['job_uid']:[i for i in range(12) if cap[i]>=r['GPU']] for r in pending}
 remaining=[]
 for r in pending:
  if compatible[r['job_uid']]:remaining.append(r)
  else:r.update(new_site=None,new_start=None,new_end=None,status='GANG_EXCEEDS_EVERY_SITE',rack=None);results.append(r)
 pending=remaining;clock=sorted(events);heapq.heapify(clock);seen=set(clock)
 while pending and clock:
  t=heapq.heappop(clock);remain=[]
  for r in pending:
   b=t+r['duration_slots'];g=r['GPU']
   i=next((i for i in compatible[r['job_uid']] if np.all(load[t:b,i]+g<=cap[i])),None)
   if i is None:remain.append(r);continue
   load[t:b,i]+=g
   r.update(new_site=SITES[i],new_start=t,new_end=b,status='ADMITTED_DDAY' if t<120 else 'QUEUED_BEYOND_D24',rack=SITES[i]+'_LP01')
   results.append(r)
   if b not in seen:heapq.heappush(clock,b);seen.add(b)
  pending=remain
 assert not pending and np.all(load<=cap)
 # Independent interval endpoint conservation, not a mirror of the array update.
 bysite={s:Counter() for s in SITES};hours=0
 for r in results:
  if r['new_site'] is None:continue
  a=max(24,r['new_start']);b=min(120,r['new_end']);g=r['GPU']
  if b>a:bysite[r['new_site']][a]+=g;bysite[r['new_site']][b]-=g;hours+=(b-a)*g/4
 for i,s in enumerate(SITES):
  n=0
  for t,d in sorted(bysite[s].items()):n+=d;assert 0<=n<=cap[i]
  assert n==0
 assert hours==load[24:120].sum()/4
 return load[24:120].copy(),results

def replay_options(categorized,caps):
 allrows=[];profiles={};summaries={};unresolved={}
 for name,cap in caps.items():
  profile=[];daily=[];u=np.zeros((31,96),int)
  for di,day in enumerate(DAYS):
   rows=[r for r in categorized if r['day']==day];p,rr=scheduler(day,rows,cap);profile.append(p);counts=Counter()
   work=Counter()
   for r in rr:
    g=r['GPU'];dur=r['duration_slots'];o=r['reference_start'];oldend=o+dur;cat=r['cohort']
    if r['status']=='AMBIGUOUS_NO_FROZEN_SOURCE':
     lo=max(24,o);hi=min(120,oldend);u[di,lo-24:hi-24]+=g;counts['remaining_ambiguous_UNASSIGNED']+=1;work['ambiguous_Dday_GPU_hours']+=(hi-lo)*g/4
    elif r['new_start'] is None:
     counts['remaining_gang_UNASSIGNED']+=1;work['unresolved_Dday_offered_GPU_hours']+=min(96,dur)*g/4;u[di,:min(96,dur)]+=g
    else:
     a=r['new_start'];b=r['new_end'];wo=max(0,o-24);wn=max(0,a-24)
     counts['start_change_jobs']+=a!=o;counts['earlier_jobs']+=a<o;counts['later_jobs']+=a>o
     counts['reference_jobs_no_longer_delayed']+=wo>0 and wn==0
     counts['same_day_completions_old']+=r['assigned'] and 24<oldend<=120
     counts['same_day_completions_new']+=24<b<=120
     counts['D24_running_old']+=r['assigned'] and o<120<oldend
     counts['D24_running_new']+=a<120<b
     counts['carryout_jobs_old']+=oldend>120;counts['carryout_jobs_new']+=b>120
     counts['newly_admitted_former_UNASSIGNED']+=not r['assigned'] and a<120
     if a>=120:
      counts['remaining_Dday_unserved_pending']+=1
      counts['remaining_original_UNASSIGNED']+=not r['assigned']
      work['unserved_Dday_offered_GPU_hours']+=min(96,dur)*g/4
     work['old_queue_job_hours']+=wo/4;work['new_queue_job_hours']+=wn/4
     work['old_queue_GPU_hours']+=wo*g/4;work['new_queue_GPU_hours']+=wn*g/4
     work['old_carryout_GPU_hours']+=max(0,oldend-max(o,120))*g/4
     work['new_carryout_GPU_hours']+=max(0,b-max(a,120))*g/4
     counts['changed_PENDING_initial_site']+=cat=='D_DAY_PENDING_OFFERED' and r['site']!=r['new_site']
    allrows.append(dict(option=name,**r))
   work['queue_reduction_job_hours']=work['old_queue_job_hours']-work['new_queue_job_hours']
   work['queue_reduction_GPU_hours']=work['old_queue_GPU_hours']-work['new_queue_GPU_hours']
   daily.append(dict(day=day,**counts,**work))
  profile=np.array(profile);profiles[name]=profile;unresolved[name]=u
  keys=set().union(*(r.keys() for r in daily))-{'day'}
  summaries[name]=dict(days=daily,aggregate={k:sum(r.get(k,0) for r in daily) for k in sorted(keys)},
    rule='Fixed D00 RUNNING sources/residual; Dday PENDING tier/FIFO earliest event; whole gang; first compatible AIDC numeric order; first logical rack. Initial PENDING placement allowed; no migration, no grid objective, no temporal optimization.',
    exact_legacy_algorithm=False,adaptation='Uses frozen admissible-site domain and numeric AIDC preference from V39D, with V41R1 event-based first fit. Existing production baseline skips UNASSIGNED and cannot itself implement requested re-admission. This study implementation does; production untouched.')
  print('CANDIDATE',name,int(cap.sum()),summaries[name]['aggregate'],flush=True)
 pd.DataFrame(allrows).to_csv(OUT/'B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv',index=False)
 np.savez_compressed(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz',**profiles,**{k+'_UNRESOLVED':v for k,v in unresolved.items()})
 write('B0_REMATERIALIZATION_IMPACT_AUDIT.json',summaries)
 return profiles,summaries

def power_audit(caps,current):
 sys.path.insert(0,str(ROOT))
 from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
 from dayahead.v39a.contracts import C_REF_W_PER_GPU,CENTER_SWING_W_PER_GPU,IDLE_W_PER_GPU
 c1=load_c1(ART/'v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')
 coeff_days=[];power=[];h4=[];ratings=None;source_records=[]
 for day in DAYS:
  cert=read(RUNTIME/'e'/day.replace('-','')/'V41_ELECTRICAL_CERTIFICATE.json');inp=cert['input_identity']['identity']['inputs']
  wp=Path(inp['weather']['path']);assert sha(wp)==inp['weather']['sha256'];record(wp);weather=pd.read_parquet(wp,columns=['t_wb_c','rh_pct'])
  coeff_days.append(dict(day=day,anchor_input=inp['AC_anchor_input'],generation_input_keys=sorted(inp),
    outputs=cert['outputs'],capacity_in_numeric_generation_input=False,reference_B0_in_numeric_generation_input=False,
    capacity_in_context_dependency_copies=True))
  if ratings is None:
   with np.load(cert['outputs']['planning_coefficients']['path'],allow_pickle=False) as z:
    print('COEFF_KEYS',z.files,flush=True)
   with np.load(cert['outputs']['current']['path'],allow_pickle=False) as z:
    print('CURRENT_KEYS',z.files,flush=True)
   with np.load(cert['outputs']['transformer_coefficients']['path'],allow_pickle=False) as z:ratings=z['ratings'].copy()
  snap=read(RUNTIME/'inputs'/day/f'V41_ML_SNAPSHOT_{day}.json');raw=np.array(snap['H4_RAW_R85_B2_GPUh']);histcap=snap['H4_CAP_HIST'];oldact=np.array(snap['H4_ACTIONABLE_RESERVE_GPUh'])
  for name,cap in caps.items():
   for i,s in enumerate(SITES):
    idle=float(IDLE_W_PER_GPU)*cap[i]/1000;active=float(C_REF_W_PER_GPU)*cap[i]/1000
    oldidle=float(IDLE_W_PER_GPU)*current[i]/1000
    p0=np.array([float(exact_c1_pcc_kw(idle,r.t_wb_c,r.rh_pct,c1)) for r in weather.itertuples()])
    p1=np.array([float(exact_c1_pcc_kw(active,r.t_wb_c,r.rh_pct,c1)) for r in weather.itertuples()])
    prev=np.array([float(exact_c1_pcc_kw(oldidle,r.t_wb_c,r.rh_pct,c1)) for r in weather.itertuples()])
    power.append(dict(day=day,option=name,site=s,idle_IT_kW=idle,full_IT_kW=active,
       idle_PCC_P_mean_kW=float(p0.mean()),full_PCC_P_max_kW=float(p1.max()),full_PCC_Q_max_kvar=float(p1.max()*math.tan(math.acos(.95))),
       full_PCC_apparent_max_kVA=float(p1.max()/.95),idle_PCC_P_delta_mean_kW=float((p0-prev).mean())))
   h4.append(dict(day=day,option=name,old_H4_physical_GPUh=624*4,new_H4_physical_GPUh=int(cap.sum())*4,
      changed_actionable_windows=int((np.minimum(raw,np.minimum(histcap,cap.sum()*4))!=oldact).sum()),
      max_actionable_change_GPUh=float(abs(np.minimum(raw,np.minimum(histcap,cap.sum()*4))-oldact).max())))
 pd.DataFrame(power).to_csv(OUT/'CAPACITY_POWER_BOUND_IMPACT.csv',index=False)
 write('H4_CAPACITY_DEPENDENCY_AUDIT.json',h4)
 elec=dict(classification='A_CONDITIONAL_EXACT_NUMERICAL_EQUIVALENCE',regeneration_required='NO',
    reason='Current AC generator takes immutable exogenous anchor_control, background/forecasts, topology/ratings and generation method. V41R1 rematerialized B0 and installed GPU counts are not numerical arguments. Capacity-dependent C1 GPU-to-PCC lookup tables are built after coefficients in planning_context. Keeping frozen anchor and coefficients unchanged is exact for those arrays; new operating-point accuracy is not certified by this algebraic fact.',
    required_actions='Rebuild all 31-day GPU-to-PCC tables, H4 capacity fields and context identities; recertify coefficient equivalence under updated dependency manifests. Existing context certificates cannot be adopted unchanged.',
    conditional_full_regeneration='If AC anchor is recentered to resized installed load/B0, regenerate all 31 days. No partial-day recentering equivalence has been established. Future Fresh validation needed before claiming physical safety.',
    days=coeff_days,thermal_coefficients_unchanged=True,
    numerical_generation_source=psource('dayahead/v40e/electrical.py',['def upstream','control=np.asarray','def planning_context','coefficients=tuple(coeff)','capacity,_=_load_capacity','it=np.array']),
    slot_coefficients_source=psource('dayahead/v28r2/electrical_subproblem.py',['def slot_coefficients','transformer_limit_kva']))
 write('ELECTRICAL_COEFFICIENT_IMPACT_AUDIT.json',elec)
 dep=dict(case=2,GPU_idle_W=float(IDLE_W_PER_GPU),GPU_active_swing_W=float(CENTER_SWING_W_PER_GPU),GPU_full_W=float(C_REF_W_PER_GPU),
     equation='P_IT_i_kW=(C_i*104.1606964512843 + reserved_active_GPU_i*547.7239090195797)/1000',
     rack_architecture_change_required=False,rack_logical_limit_refreeze_required=True,physical_rack_count_authority=None,
     power_authority_change_required=True,power_parameters_change_required=False,B0_rematerialization_required=True,
     electrical_coefficients=elec,
     power_source=psource('dayahead/v39a/power.py',['def site_it_power_kw','Decimal(capacity) * IDLE','Decimal(active) *','def aggregate_it_power_kw']),
     parameters_source=psource('dayahead/v39a/contracts.py',['C_REF_W','CENTER_SWING_W','IDLE_W','FULL_ACTIVE_IT']),
     H4_source=psource('dayahead/v41/reserve.py',['def cap_reserve','physical = windows','actionable = np.minimum','headroom = DT_HOURS']),
     candidate_results={name:dict(installed_idle_IT_delta_kW=float((cap.sum()-624)*float(IDLE_W_PER_GPU)/1000),
       full_active_IT_kW=float(cap.sum()*float(C_REF_W_PER_GPU)/1000)) for name,cap in caps.items()},
     frozen_transformer_rating_values_kVA=sorted(set(float(x) for x in ratings if np.isfinite(x))))
 write('GPU_CAPACITY_DEPENDENCY_AUDIT.json',dep)
 return dep,power

def main():
 before=read(OUT/'PROTECTED_BEFORE.json')
 current,history,c,rack=source_authority()
 arrays,u,cohorts,cohort_audit,jobrows,sizes,full_sizes=load_data()
 categorized,cohort=categorize(cohorts,jobrows)
 known=arrays['offered'];unknown=u['offered'];total=known.sum(2)+unknown
 # Raw system demand is frozen before candidate generation; unknown sites are
 # not apportioned to sites. Per-site candidate use comes only from replay.
 offered=read(OUT/'OFFERED_DEMAND_DISTRIBUTION.json')
 offered.update(scope='ALL_D_DAY_OFFERED_COHORT_INCLUDING_UNASSIGNED_SYSTEM_DEMAND',aggregate=trace_stats(total),
   known_site_component=trace_stats(known.sum(2)),unassigned_site_component=trace_stats(unknown),
   construction=cohort['boundary_condition'],cohort_classification=cohort,
   limitation='Per-site offered trace has a separately conserved unknown-site component; no pre-sizing per-job site is fabricated. Candidate per-site occupancy is deterministic resource rematerialization, not offered/capacity at a fictional site.',
   day_by_day=[dict(day=day,**trace_stats(total[i]),known_site_mean=float(known[i].sum(1).mean()),unknown_site_mean=float(unknown[i].mean())) for i,day in enumerate(DAYS)],
   time_of_day=[dict(time=f'{k//4:02}:{k%4*15:02}',**trace_stats(total[:,k])) for k in range(96)],
   old_vs_offered=dict(old_mean=float(arrays['old'].sum(2).mean()),offered_mean=float(total.mean()),net_GPU_hours=float((total-arrays['old'].sum(2)).sum()/4),
      absolute_system_slot_GPU_hours=float(abs(total-arrays['old'].sum(2)).sum()/4),
      old_total_12full_fraction=float((arrays['old']>=c).all(2).mean()),
      Q90_additional_queue_jobs=sum(x['Q90_additional_delay_jobs'] for x in cohort_audit),
      inherited_RW_queue_jobs=sum(x['inherited_RW_queued_jobs'] for x in cohort_audit)),
   May04=dict(aggregate=trace_stats(total[3]),known_by_site=known[3,72],unknown_critical_GPU=int(unknown[3,72]),
     critical_total_GPU=int(total[3,72]),old_mean=float(arrays['old'][3].sum(1).mean())),
   site_share_denominator='All D-day offered GPU-hours, including unknown sites.')
 for i,s in enumerate(SITES):offered['per_site'][s]=dict(**trace_stats(known[:,:,i]),share=float(known[:,:,i].sum()/total.sum()),partial_known_site_component=True)
 offered['UNKNOWN_SITE']=dict(**trace_stats(unknown),share=float(unknown.sum()/total.sum()))
 write('OFFERED_DEMAND_DISTRIBUTION.json',offered)
 pd.DataFrame(offered['day_by_day']).to_csv(OUT/'OFFERED_DEMAND_DAILY.csv',index=False)
 pd.DataFrame(offered['time_of_day']).to_csv(OUT/'OFFERED_DEMAND_TIME_OF_DAY.csv',index=False)
 pd.DataFrame([dict(site=s,**v) for s,v in offered['per_site'].items()]+[dict(site='UNKNOWN_SITE',**offered['UNKNOWN_SITE'])]).to_csv(OUT/'OFFERED_DEMAND_PER_SITE.csv',index=False)
 np.savez_compressed(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz',D_GPU_offered_total=total,D_GPU_offered_known_site=known,
   D_GPU_offered_UNASSIGNED=unknown,D_GPU_offered=known,sites=np.array(SITES),days=np.array(DAYS),
   D_GPU_materialized_624=arrays['old'],D_GPU_pre_Q90_but_RW_queued=arrays['pre_q90'],
   D_GPU_issue_release_total=arrays['issue_offered'].sum(2)+u['issue_offered'],local_slot_minutes=np.arange(96)*15)
 assert np.array_equal(total,known.sum(2)+unknown)
 reps=sorted({1,4,8,16,32,60,128,256,int(np.percentile(full_sizes,50)),int(np.percentile(full_sizes,90))})
 candidates={};rounding={};caps={};flat=[]
 for t in (.75,.8,.85):
  name=str(int(t*100));cc,rr=apportion(float(total.mean()/t),c/c.sum(),c);caps[name]=cc;rounding[name]=rr
  nblocks=int((cc.sum()/4-96)//8);naive_total=384+min(nblocks,12)*32+int((cc.sum()/4-96)%8)*4
  rr['original_one_pass_algorithm_output_total_if_only_total_parameter_changed']=naive_total
  rr['original_one_pass_algorithm_total_deficit']=int(cc.sum()-naive_total)
  for i,s in enumerate(SITES):flat.append(dict(target=t,site=s,current_GPU=int(c[i]),candidate_GPU=int(cc[i]),candidate_total=int(cc.sum()),
    continuous_total=rr['continuous_total'],nodes=int(cc[i]//4),**{k:v for k,v in rr['rows'][i].items() if k not in ('site','capacity')}))
  v=total/cc.sum()
  candidates[name]=dict(target=t,total=int(cc.sum()),vector=cc,continuous_total=rr['continuous_total'],
      system_offered_occupancy=dict(**stats(v),**{f'fraction_ge_{k}':float((v>=k/100).mean()) for k in (90,95,100)}))
 write('CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json',rounding)
 pd.DataFrame(flat).to_csv(OUT/'V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv',index=False)
 profiles,replay=replay_options(categorized,caps)
 for name,cc in caps.items():
  hh=headroom(profiles[name],cc,reps);candidates[name]['materialized_headroom']=hh;candidates[name]['B0_rematerialization']=replay[name]
  # Known-site lower component yields an optimistic headroom bound only.
  candidates[name]['known_only_optimistic_offered_headroom_bound']=headroom(known,cc,reps)
  np.savez_compressed(OUT/f'HEADROOM_BY_SLOT_{name}.npz',actual_resource_replay_GPU=profiles[name],
    available_GPU=cc-profiles[name],system_offered_occupancy=total/cc.sum(),
    number_positive_headroom=((cc-profiles[name])>0).sum(2),
    **{f'feasible_destinations_GPU_{g}':((cc-profiles[name])>=g).sum(2) for g in reps})
 dep,power=power_audit(caps,c)
 result=dict(status='RECOMMENDED_CAPACITY_AUTHORITY_AUDIT_ONLY',production_capacity_applied=False,Full_May='HOLD',
    current=current,historical=history,offered=offered,candidates=candidates,dependencies=dep,
    current_materialized_headroom=headroom(arrays['old'],c,reps),
    execution_counts=dict(policy_optimization=0,B1=0,B2=0,B3=0,Actual_replay=0,Fresh_AC=0,electrical_generation=0,ML_training=0),recommendation=None)
 write('V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json',result)
 write('MAY_31DAY_Q90_OFFERED_GPU_DEMAND_MANIFEST.json',dict(file=record(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz'),
    scope=offered['scope'],axis=[31,96,12],D_GPU_offered_alias='known-site component only; total includes separate UNASSIGNED array',
    total_conservation_exact=True,system_GPU_hours=float(total.sum()/4),known_site_GPU_hours=float(known.sum()/4),unknown_site_GPU_hours=float(unknown.sum()/4),
    causal_cutoff_checked_all_jobs=True,pending_Q90_and_running_duration_verified=True,cohort_classification=record(OUT/'UNASSIGNED_CAUSE_AND_COHORT_AUDIT.json'),
    inputs=[v for k,v in INPUTS.items() if str(OUT) not in k]))
 write('INPUT_SOURCE_MANIFEST.json',[v for k,v in INPUTS.items() if str(OUT) not in k])
 print('FINAL_NUMBERS',json.dumps({k:dict(total=v['total'],vector=v['vector'],system=v['system_offered_occupancy'],
   actual_system=v['materialized_headroom']['system'],full=v['materialized_headroom']['all12_FULL_fraction'],
   unresolved=v['B0_rematerialization']['aggregate']) for k,v in candidates.items()},default=serial,indent=2),flush=True)

if __name__=='__main__':main()
