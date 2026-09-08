"""Verification and report assembly, confined to audit output folder."""
from final_audit import *

def pct(v):return f'{100*v:.3f}%'
def fmt(v):return f'{v:,.3f}'
def vec(v):return '['+', '.join(str(int(x)) for x in v)+']'
def table(headers,rows):
 return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(v) for v in row)+' |' for row in rows])+'\n'

def audit_current_and_verify(a):
 # Static source binding and numerical rack/PCC limits are read, never regenerated.
 c=np.array(a['current']['vector']);power=pd.read_csv(OUT/'CAPACITY_POWER_BOUND_IMPACT.csv')
 all_rating_rows=[]
 for day in DAYS:
  cert=read(RUNTIME/'e'/day.replace('-','')/'V41_ELECTRICAL_CERTIFICATE.json')
  with np.load(cert['outputs']['planning_coefficients']['path'],allow_pickle=False) as p,np.load(cert['outputs']['current']['path'],allow_pickle=False) as z,np.load(cert['outputs']['transformer_coefficients']['path'],allow_pickle=False) as t:
   names=list(map(str,p['branch_names']));tx=[i for i,n in enumerate(names) if n.startswith('transformer.')]
   assert len(tx)==len(t['ratings'])
   for j,i in enumerate(tx):
    n=names[i]
    if 'transformer.idc_idc' not in n:continue
    site='AIDC'+n.split('idc_idc')[1][:2]
    assert np.all(p['branch_limits'][:,i]==p['branch_limits'][0,i])
    all_rating_rows.append(dict(day=day,site=site,branch=n,phase=n.split('::')[1],rating_A=float(z['rating_a'][i]),
       limit_kVA=float(p['branch_limits'][0,i]),transformer_rating_kVA=float(t['ratings'][j]),source=cert['outputs']['planning_coefficients']))
 assert len(all_rating_rows)==31*12*3
 for row in a['current']['rows']:
  rr=[x for x in all_rating_rows if x['site']==row['site']];assert {x['transformer_rating_kVA'] for x in rr}=={500.}
  row['PCC_current_rating_A_per_phase']=rr[0]['rating_A'];row['PCC_apparent_limit_kVA_per_phase']=500.
  row['PCC_ceiling']='Dedicated AIDC transformer phase limits: 500 kVA per phase, 208.179183602 A current rating. Shared feeder and voltage constraints additionally apply. No independent P and Q box ceiling.'
  row['PCC_limit_source']=rr[0]['source'];row['PCC_limit_field']='branch_limits[:, branch_names==transformer.idc_idcXX_tx::phase]; transformer ratings subset'
  row['PCC_limits_31day_invariant']=True
  row['rack_architecture_source']=a['current']['rack_source']
  assert sha(SOURCE/CAP.relative_to(ROOT))==row['source_SHA256']
 a['dependencies']['runtime_PCC_ceiling']='500 kVA per AIDC transformer phase, all 31 days; historical V22SR1 0.3 MVA interface does not match current coefficient-bound 1.5 MVA three-phase interface.'
 write('CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json',a['current'])
 write('CURRENT_PCC_CEILING_AUDIT.json',all_rating_rows)
 # Reproduce all saved B0 tables with the unmodified pure baseline function.
 spec=importlib.util.spec_from_file_location('frozen_pure_baseline',ROOT/'dayahead/v41r1/migration_baseline.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 racks=read(RACK)
 class Cap:
  aidc_ids=tuple(SITES);site_capacity=dict(zip(SITES,map(int,c)))
  rack_pools=tuple(SimpleNamespace(aidc_id=r['aidc_id'],rack_pool_id=r['rack_pool_id'],historical_gpu_capacity=int(r['compatibility_GPU_limit'])) for r in racks['logical_Rack_pools'])
  def eligible_racks(self,s,g):return [r for r in self.rack_pools if r.aidc_id==s and r.historical_gpu_capacity>=g]
 exact=[]
 for day in DAYS:
  p=RUNTIME/'inputs'/day/'common_q90_v3';jj=read(p/'COMMON_B0_REFERENCE_JOBS.json');b=read(p/'Q90_BASELINE_MATERIALIZATION.json');br={r['job_id']:r for r in b['rows']}
  data=deepcopy(jj)
  for j in data:j['start_slot']=br[j['job_uid']]['old_start_issue_slot'];j['end_slot']=j['start_slot']+j['safe_duration_slots']
  ss=[SimpleNamespace(job_id=j['job_uid'],priority_key=tuple(br[j['job_uid']]['priority_key'])) for j in data]
  actual,_=mod.materialize(data,ss,Cap())
  old={j['job_uid']:j for j in jj}
  assert all((x['AIDC_site'],x['Rack_label'],x['start_slot'],x['end_slot'])==(old[x['job_uid']]['AIDC_site'],old[x['job_uid']]['Rack_label'],old[x['job_uid']]['start_slot'],old[x['job_uid']]['end_slot']) for x in actual)
  exact.append(dict(day=day,exact_job_site_rack_start_end_equal=True,jobs=len(actual)))
 write('CURRENT_B0_EXACT_REPRODUCTION_CHECK.json',exact)
 # Independent serialized job ledger reconstructs offered GPU-hours and cohort counts.
 frame=pd.read_csv(OUT/'UNASSIGNED_AND_DDAY_COHORT_CLASSIFICATION.csv')
 expected=0.
 for r in frame.itertuples():
  if r.cohort=='PRE_D00_COMPLETE':continue
  start=int(r.nominal_start);end=start+r.duration_slots
  expected+=max(0,min(120,end)-max(24,start))*r.GPU/4
 with np.load(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz') as z:
  assert expected==z['D_GPU_offered_total'].sum()/4
  assert np.array_equal(z['D_GPU_offered_total'],z['D_GPU_offered_known_site'].sum(2)+z['D_GPU_offered_UNASSIGNED'])
  assert z['D_GPU_offered_total'].shape==(31,96)
 # Deterministic replay repeated for a heavy day and the critical day.
 rows=json.loads(frame.to_json(orient='records'))
 for r in rows:
  r['priority_key']=ast.literal_eval(r['priority_key'])
  for key in ('GPU','duration_slots','reference_start'):r[key]=int(r[key])
 deterministic=[]
 with np.load(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz') as stored:
  for day in ('2025-05-04','2025-05-21'):
   for name,v in a['candidates'].items():
    p,result=scheduler(day,[r for r in rows if r['day']==day],np.array(v['vector']))
    assert np.array_equal(p,stored[name][DAYS.index(day)])
    deterministic.append(dict(day=day,option=name,exact_repeat=True))
 check=dict(status='PASS',current_B0_reproduced_days=31,serialized_offered_GPU_hours=expected,
   system_equals_known_plus_unknown=True,all_candidate_interval_endpoint_conservation=True,
   deterministic_repeats=deterministic,current_authority_source_and_production_copy_equal=True,
   PCC_rating_days=31,policy_solver_calls=0,production_files_written=0)
 write('V41R2_VERIFICATION.json',check)
 return check

def write_report(a,verify):
 o=a['offered'];cs=a['candidates'];old=a['current_materialized_headroom'];dep=a['dependencies']
 for name,v in cs.items():
  q=v['B0_rematerialization']['aggregate']
  v['qualification']='UNDERSIZED_D_DAY_SERVICE_NOT_CLOSED'
  v['why_rejected']=dict(remaining_Dday_unserved_jobs=q.get('remaining_Dday_unserved_pending',0),
    unserved_Dday_offered_GPU_hours=q.get('unserved_Dday_offered_GPU_hours',0),
    system_offered_saturation_fraction=v['system_offered_occupancy']['fraction_ge_100'])
  for key in ('materialized_headroom',):
   crit=v[key]['May04_1800'];crit['resource_replay_GPU']=crit.pop('offered_GPU',crit.get('resource_replay_GPU'))
 # Recommend the authority disposition, not an invalid production vector.
 rec=dict(disposition='DO_NOT_APPLY_ANY_TESTED_VECTOR',recommended_total=None,recommended_per_site_vector=None,
    nominal_80_total=cs['80']['total'],nominal_80_vector=cs['80']['vector'],
    largest_reference_only_review_candidate=dict(target=.75,total=cs['75']['total'],vector=cs['75']['vector']),
    reason='All three aggregate-mean-sized candidates retain material D-day work beyond D24. 80% is therefore not a healthy operating recommendation; 75% is the least constrained tested sensitivity but still fails. This is an observed burst/service deficit, not a refusal caused merely by missing job sites.',
    safe_to_apply=False,approval_required_after_new_scientific_authority=True,
    physical_source_ambiguity=dict(jobs=14,GPU_hours=11,share_of_offered_GPU_hours=11/o['aggregate']['GPU_hours']),
    next_authority_needed='Resolve the engineering objective for burst/backlog service versus mean idle installed capacity, and review the study first-placement adaptation. Do not change WAN/terminal semantics to hide unmet service. No additional capacity, schedule or power freeze is authorized here.')
 a['recommendation']=rec;a['status']='RECOMMENDED_CAPACITY_AUTHORITY_FAIL_CLOSED';a['verification']=verify
 write('V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json',a)
 write('RECOMMENDED_CAPACITY_AUTHORITY.json',rec)
 sections=[]
 sections.append('# V41R2 AIDC GPU capacity sizing and authority audit\n\n**RECOMMENDED CAPACITY AUTHORITY: FAIL-CLOSED — do not apply any tested vector.** Full May remains HOLD. No policy optimization, migration optimization, Actual replay, Fresh solve, ML training or coefficient regeneration was executed. All changes are confined to this audit folder.\n')
 sections.append(f'The 31-day D-day offered mean is **{fmt(o["aggregate"]["mean"])} GPU slots**, including D-day jobs whose old site was UNASSIGNED. The nominal 80% installed total is **{cs["80"]["total"]:,} GPU slots**. This is not GPU compute utilization. At that capacity, offered demand exceeds/equal capacity in **{pct(cs["80"]["system_offered_occupancy"]["fraction_ge_100"])}** of slots; **766 job-day observations** still do not begin before D24. The larger 75% candidate leaves 708. No tested candidate meets the requested healthy-service criterion.\n')
 sections.append('## Current authority and historical lineage\n')
 sections.append(f'Current total **624**; vector **{vec(a["current"]["vector"])}**. Four-GPU equivalent H100 node granularity; four nonadditive logical rack pools per site. Physical rack count and GPU-per-physical-rack are unavailable, so 48 logical pools must not be presented as 48 installed physical racks.\n')
 sections.append(table(['AIDC','GPU','4-GPU nodes','Logical pools','Each pool envelope','IT idle kW','IT full kW'],[[r['site'],r['GPU'],r['equivalent_H100_nodes'],r['logical_pool_count'],r['GPU'],fmt(r['site_IT_idle_kW']),fmt(r['site_IT_full_active_kW'])] for r in a['current']['rows']]))
 sections.append(f'GPU source SHA-256: `{a["current"]["source"]["sha256"]}`; creating commit `{a["current"]["source"]["creating_commit"]}`. Rule commit `{a["current"]["upstream_rule_commit"]}`. Rack authority commit `{a["current"]["rack_source"]["creating_commit"]}`. Complete fields, line locations, hashes and per-site ceilings are in CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json. Current coefficient-bound PCC interfaces are **500 kVA per phase** and **208.179184 A per phase**, identical across all 31 days; shared network/voltage constraints also apply. The historical V22SR1 0.3-MVA interface is not the current runtime limit.\n')
 sections.append('The exact V39C construction gives eight nodes to every site, then one eight-node/32-GPU block to each of the seven highest facility-weight sites, then four residual nodes/16 GPUs to AIDC05. The pre-May gang audit documents recurrent 32-GPU jobs; this is a defensible frozen synthetic engineering allocation (CASE A), not a GPU census. V22SR1 is a soft facility-size prior, not a MW-to-GPU conversion.\n')
 sections.append('The historical function has fixed total/expected-vector assertions. Its one-pass `order[:full_blocks]` loop cannot distribute more than twelve blocks. Applying it verbatim to these much larger totals loses capacity. Therefore the permitted CASE A common-alpha rule preserves the existing unequal vector and rounds in 4-GPU nodes. No new weighted-residual or cycling allocator has been silently invented. This is an explicit limit on the latest preference to reuse the exact allocator.\n')
 sections.append(f'[GitHub PR #12](https://github.com/BeaverVillage/MobileESS/pull/12), head `499d5793ed4b725fa5d0b38691b07752c4f88482`, contains the exact same weight-file bytes (SHA `{a["historical"]["source"]["sha256"]}`). Retrieved PR metadata says open/unmerged; its artifact is verified in current Git history, rather than assumed merged. Repository field `primary_IT_equivalent_capacity_MW` is the primary site-scale authority. Total **{a["historical"]["primary_total_MW"]:.12f} MW**.\n')
 sections.append(table(['Site','Facility','Primary IT-equivalent MW','Weight','Classification / source'],[[r['site_id'],r['site_name'],fmt(r['primary_IT_equivalent_capacity_MW']),f'{r["capacity_weight"]:.12f}',r['preregistered_classification']+' / '+r['source_id']] for r in a['historical']['rows']]))
 sections.append('All twelve historical GPU weights are `UNAVAILABLE_NOT_INFERRED`; V22S records zero MW-equals-GPU-weight calls. Primary classifications include engineering MVA and generator conversions as well as source-backed facility capacities. Values are not uniformly measured IT capacities.\n')
 sections.append('## Offered demand and UNASSIGNED causes\n')
 sections.append('Daily forecasts are independent D-1 18:00 fixed-AEST snapshots. Slot 24 is D00; slot 120 is D24. Preserve reference work already complete before D00 and exact D00 RUNNING residuals. Causally known PENDING jobs are ready before D00: V37 `_first_fit` starts at issue slot 0 and accepts no independent future not-before/release field. In a D00-anchored capacity-free counterfactual their earliest nominal Day-D start is 24. This removes capacity waiting, not an exogenous release or a policy time-shift. The trace is conditional on the fixed D00 state; an issue-time release sensitivity is also saved and must not be substituted silently.\n')
 sections.append('There are 25,597 UNASSIGNED pending job-day observations with old starts >=120. `production_activity` dropped intervals outside [24,120) before placement; their timestamps were produced by the 624-GPU queue. **None has an independent nominal future release >=120**, so they are D-day offered demand, not true future-service exclusions. 1,464 UNASSIGNED jobs are already pre-D00 complete. Another 14 have Q90-expanded preday intervals overlapping D00 but no physical source site; their 11 GPU-hours are included conservatively in system demand and remain explicitly ambiguous for site replay. Their offered share is '+pct(11/o['aggregate']['GPU_hours'])+'. No site was fabricated.\n')
 sections.append(table(['Cohort','Job-day observations'],list(o['cohort_classification']['cohort_counts'].items())))
 sections.append('Authoritative POST_H_BACKLOG / FUTURE_SERVICE_DEMAND in this issue-visible, capacity-free cohort: **0 jobs / 0 GPU-hours**. This does not assert that no jobs arrive in the future; future arrivals are outside the frozen visible cohort. Historical post-H queue backlog is reported separately and remains in the D-day demand until service is delivered.\n')
 sections.append(table(['Mean','P50','P90','P95','P99','Max','GPU-hours'],[[fmt(o['aggregate'][k]) for k in ('mean','P50','P90','P95','P99','max','GPU_hours')]]))
 sections.append(table(['Site component','Mean GPU','P50','P90','P95','P99','Max','GPU-hours','Total share'],[[s]+[fmt(v[k]) for k in ('mean','P50','P90','P95','P99','max','GPU_hours')]+[pct(v['share'])] for s,v in list(o['per_site'].items())+[('UNKNOWN_SITE',o['UNKNOWN_SITE'])]]))
 sections.append('The known-site statistics are a partial decomposition, not the complete spatial workload. `D_GPU_offered_total == sum(D_GPU_offered_known_site, axis=2) + D_GPU_offered_UNASSIGNED` exactly. The NPZ alias `D_GPU_offered` holds the known-site component only; the aggregate sizing array is `D_GPU_offered_total`.\n')
 sections.append(table(['Day','Mean','P95','Max','GPU-hours','Unknown-site mean'],[[r['day'],fmt(r['mean']),fmt(r['P95']),fmt(r['max']),fmt(r['GPU_hours']),fmt(r['unknown_site_mean'])] for r in o['day_by_day']]))
 sections.append('Time-of-day statistics for every 15-minute slot are in OFFERED_DEMAND_TIME_OF_DAY.csv and the JSON report. Quantiles use linear percentile interpolation and equal slot weights. Counts/GPU-hours sum independent job-day forecast observations; repeated job IDs on different days are not unique real executions.\n')
 sections.append(f'May-04 offered mean/P95/max: **{fmt(o["May04"]["aggregate"]["mean"])}/{fmt(o["May04"]["aggregate"]["P95"])}/{fmt(o["May04"]["aggregate"]["max"])} GPU**. Offered at 18:00: **308 GPU**, vector {vec(o["May04"]["known_by_site"])}; old materialized demand is 624 at that slot. The old May-04 mean is {fmt(o["May04"]["old_mean"])} ({pct(o["May04"]["old_mean"]/624)}). Thus relieving queueing can lower late-day demand by completing work earlier.\n')
 sections.append(f'Across May, old materialized mean is {fmt(o["old_vs_offered"]["old_mean"])} GPU. Net offered-minus-old Day-D demand is {fmt(o["old_vs_offered"]["net_GPU_hours"])} GPU-hours. The final Q90 queue layer added delays to {o["old_vs_offered"]["Q90_additional_queue_jobs"]} job-day observations; most waiting was inherited from RW. May-04 has zero added final-layer delays, so merely undoing that layer would leave its 624-GPU queue intact.\n')
 sections.append('## Capacity options and integer apportionment\n')
 sections.append('Continuous total = all-D-day 31-day offered mean / target. Round to the nearest multiple of four (half upward); allocate nodes by Hamilton largest remainders using the current frozen relative vector, with AIDC numeric ties. This minimizes deviation from common scaling at the nearest valid total. No per-site demand or B1 outcome enters allocation.\n')
 rounding=read(OUT/'CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json')
 sections.append(table(['Target','Continuous total','Integer total','Total rounding error','Vector'],[[k+'%',fmt(v['continuous_total']),v['total'],fmt(rounding[k]['total_rounding_error']),vec(v['vector'])] for k,v in cs.items()]))
 sections.append(table(['Site','75% rounding error','80% rounding error','85% rounding error'],[[SITES[i]]+[fmt(rounding[k]['rows'][i]['error_vs_continuous']) for k in ('75','80','85')] for i in range(12)]))
 sections.append('## System demand versus installed capacity\n')
 sections.append(table(['Target','Mean','P50','P90','P95','P99','Max','>=90% slots','>=95% slots','>=100% slots'],[[k+'%']+[pct(v['system_offered_occupancy'][f]) for f in ('mean','P50','P90','P95','P99','max','fraction_ge_90','fraction_ge_95','fraction_ge_100')] for k,v in cs.items()]))
 sections.append('Values above 100% are offered overload, not feasible GPU occupancy. The 80% mean is obtained arithmetically, but the P95 is 304.469% and P99 is 368.750%. Peaks are pervasive under every sensitivity. The data do not support interpreting a universal P95 <=90% rule; no such standard is claimed.\n')
 sections.append('## Resource-only rematerialization and spatial headroom\n')
 sections.append('D00 RUNNING site/residual stays fixed. All ready D-day PENDING jobs (including previous UNASSIGNED) use frozen service-tier/FIFO order, earliest resource-feasible event, whole-gang capacity, numeric AIDC preference and first logical-rack ID. Existing V39D permits all compatible sites and uses numeric site preference; current V41R1 baseline fixes old sites and skips UNASSIGNED. The study adapts these rules to re-admit pending work, as requested. **It is not the unchanged production routine or a proof of global placement optimality.** No grid, migration or temporal-flexibility objective is evaluated. Full-duration resource reservations extend into a queue ledger after D24; no inter-day carry is propagated.\n')
 sections.append(table(['Target','Materialized mean','P95/P99','12/12 FULL','>=10 FULL','At least one spare site','Sites spare every slot'],[[k+'%',pct(v['materialized_headroom']['system']['mean']),pct(v['materialized_headroom']['system']['P95'])+' / '+pct(v['materialized_headroom']['system']['P99']),pct(v['materialized_headroom']['all12_FULL_fraction']),pct(v['materialized_headroom']['ge10_FULL_fraction']),pct(v['materialized_headroom']['fraction_any_positive_headroom']),v['materialized_headroom']['number_sites_positive_headroom_every_slot']] for k,v in cs.items()]))
 for k,v in cs.items():
  sections.append(f'### {k}% candidate: per-site resource replay\n')
  sections.append(table(['Site','Mean','P90','P95','P99','Max','FULL','Spare mean','Spare P10/P50','Headroom GPUh'],[[s]+[pct(x[f]) for f in ('mean','P90','P95','P99','max','FULL_fraction')]+[fmt(x['available_GPU_mean']),fmt(x['available_GPU_P10'])+' / '+fmt(x['available_GPU_P50']),fmt(x['headroom_GPU_hours'])] for s,x in v['materialized_headroom']['sites'].items()]))
  sections.append('Number of AIDCs with positive headroom, slot-count distribution: `'+json.dumps(v['materialized_headroom']['available_destination_count_distribution'])+'`.\n')
 sections.append('Numeric AIDC preference creates higher occupancy at earlier sites; this is a scheduler placement tendency, not evidence to fit site capacities to May. All D00 RUNNING reservations fit every candidate; 256-GPU gangs have compatible candidate sites. The main failure is system burst/backlog service, not a missing small-site gang floor.\n')
 sections.append('### Whole-job destination availability\n\nInstantaneous GPU/rack acceptance only: no source exclusion, future-duration availability, WAN or electrical feasibility is claimed. Nonadditive rack envelopes equal the site capacity, so site spare >= job size suffices for this instantaneous metric. Slot-by-slot counts are saved in HEADROOM_BY_SLOT_75/80/85.npz.\n')
 sections.append(table(['Target','Job GPU','>=1 destination','>=2','>=3'],[[k+'%',g,pct(x['fraction_at_least_1']),pct(x['fraction_at_least_2']),pct(x['fraction_at_least_3'])] for k,v in cs.items() for g,x in v['materialized_headroom']['whole_job_feasibility'].items()]))
 sections.append('### May-04 18:00 headroom\n')
 sections.append(table(['AIDC','Old spare','75% spare','80% spare','85% spare'],[[s,0]+[cs[k]['materialized_headroom']['May04_1800']['available_GPU'][i] for k in ('75','80','85')] for i,s in enumerate(SITES)]))
 sections.append(f'All twelve sites have headroom at this slot in each candidate. Across all 31 days, 12/12 FULL changes from **{pct(old["all12_FULL_fraction"])}** to **{pct(cs["75"]["materialized_headroom"]["all12_FULL_fraction"])}/{pct(cs["80"]["materialized_headroom"]["all12_FULL_fraction"])}/{pct(cs["85"]["materialized_headroom"]["all12_FULL_fraction"])}**. A favorable May-04 slot does not resolve whole-month overload.\n')
 sections.append('## B0 timing, completion and D24 implications\n')
 keys=['reference_jobs_no_longer_delayed','start_change_jobs','newly_admitted_former_UNASSIGNED','remaining_Dday_unserved_pending','unserved_Dday_offered_GPU_hours','queue_reduction_job_hours','queue_reduction_GPU_hours','same_day_completions_old','same_day_completions_new','D24_running_old','D24_running_new','old_carryout_GPU_hours','new_carryout_GPU_hours']
 sections.append(table(['Metric','75%','80%','85%'],[[f]+[fmt(cs[k]['B0_rematerialization']['aggregate'].get(f,0)) for k in ('75','80','85')] for f in keys]))
 sections.append('The unresolved 14 ambiguous source jobs / 11 GPU-hours are additional to the pending counts above. For candidate 75%, unserved D-day offered work is 523,296 GPU-hours (31.93% of raw D-day offered GPU-hours); it is material. These are job-day observations. Detailed changes and daily completion/carry totals are saved in B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv and B0_REMATERIALIZATION_IMPACT_AUDIT.json.\n')
 sections.append('## Rack, power, H4 and electrical dependencies\n')
 sections.append('Power model CASE 2: installed GPU capacity already contributes idle IT power. `P_IT_i = (104.1606964512843*C_i + 547.7239090195797*active_GPU_i)/1000` kW. Full-active per-GPU IT power is 651.884605470864 W. No idle coefficient is invented. Enlarging logical-rack labels does not add another idle term. Per-site GPU-to-PCC tables use unchanged C1/weather; P/Q change, while C1 coefficients and fixed PF=0.95 do not. Historical PUE=1.30 is not applied again.\n')
 sections.append(table(['Target','Added idle IT kW','Full-active total IT kW','H4 physical cap GPUh'],[[k+'%',fmt(dep['candidate_results'][k]['installed_idle_IT_delta_kW']),fmt(dep['candidate_results'][k]['full_active_IT_kW']),4*v['total']] for k,v in cs.items()]))
 sections.append('A capacity application requires GPU/rack authority and hashes, aggregate power range/conservation constants, all 31-day GPU-to-PCC lookup tables, H4 capacity/actionable reserve snapshots, reference materialization, candidate manifests and model contexts to be rebuilt/rebound consistently. Reusing the old fixed 624-GPU aggregate power equation would fail conservation. Physical rack-count changes cannot be asserted from logical labels; the modeled four-pool-per-site structure stays the same, and all envelopes must be refrozen.\n')
 sections.append('Electrical coefficients: **A — no numerical regeneration required if the existing exogenous AC anchor and all generation inputs remain byte-identical.** Exact source trace shows capacity/B0 are not coefficient arguments; power tables are built after the coefficient tuple. This is a mathematical dependency result, not a new AC accuracy certificate. Context/dependency manifests must be updated and existing generated outputs may only be reused as exact-equivalent prior outputs. If a resized B0/load anchor is selected, **full 31-day regeneration is required**. No coefficients or anchors were changed here. Shared-feeder physical safety at the much larger candidate loads is unverified, so SAFE TO APPLY remains NO.\n')
 sections.append('H4 raw forecasts and historical caps remain frozen. Physical cap changes from 2,496 GPUh to 4×candidate capacity; actual actionable-window differences are recorded in H4_CAPACITY_DEPENDENCY_AUDIT.json. Migration eligibility, available reserve and all capacity SHA guards depend on the new vector.\n')
 sections.append('## WAN and final recommendation\n')
 sections.append('More GPU headroom can remove one reason to wait for a destination. It cannot certify or repair UID-serialized WAN waits, the approximately 23-hour wait issue, checkpoint timing, restart or D24 service-shift semantics. The resource-only study still has substantial D24 backlog even with no WAN/migration activity. That scientific-contract audit remains separate.\n')
 sections.append('**WHY NOT 80%:** the offered mean hides severe bursts and long known pending work. All three candidates leave material D-day service unstarted; even the largest candidate has offered overload in 24.160% of slots and 708 pending observations after D24. Therefore none is recommended for production. The nominal 80% point is fully determined (2,752 GPU); the least-constrained comparison vector is the 75%/2,936-GPU option, but it is not an accepted installed-capacity authority. The blocker is the demonstrated service/peak tradeoff, not lack of per-job site assignments. No new arbitrary peak threshold or untested larger vector is substituted.\n')
 sections.append('## Verification and preservation\n\n31/31 saved current B0 tables reproduced exactly using the unmodified pure baseline. Offered GPU-hours independently reconciled from the serialized job ledger. All candidate per-site interval endpoint sweeps conserve service and respect site/rack envelopes; May-04 and heavy May-21 replay repeated exactly for each vector. Authority/copy hashes and all 31-day PCC limits verified. PROTECTED_BEFORE.json and PROTECTED_AFTER_AUDIT.json record pre-existing evidence preservation. The initial admitted-only calculation was superseded by the user-steered all-D-day audit; only this final report and final NPZ/manifest define the reported results.\n')
 sections.append('![Capacity sensitivity](capacity_sizing_overview.png)\n')
 (OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.md').write_text('\n'.join(sections),encoding='utf-8')
 graph='''# GPU capacity dependency graph\n\n```mermaid\nflowchart TD\n C[V39C site GPU authority] --> R[V39D nonadditive rack envelopes]\n C --> I[Installed idle IT load]\n C --> F[Active GPU range and full IT ceiling]\n R --> B[Deterministic B0 resource feasibility]\n C --> B\n B --> G[Per-slot reserved GPU profile]\n G --> P[Site IT power]\n I --> P\n P --> Q[C1 weather-dependent PCC P/Q tables]\n C --> H[H4 physical cap and available reserve]\n C --> M[Initial placement and migration eligibility]\n A[Immutable exogenous AC anchor] --> E[Planning electrical coefficients]\n X[Topology, ratings, D1 background, generator] --> E\n E --> N[Planning evaluation at changed PCC P/Q]\n Q --> N\n Q -. only if explicitly recentered .-> A\n```\n\n- CASE 2: installed capacity contributes existing idle power, 104.1606964512843 W/GPU.\n- Rack pools are four/site, nonadditive, not physical racks. Envelope update YES; modeled topology change NO; physical rack count unknown.\n- Per-GPU power/C1 coefficients unchanged; aggregate 624-specific range and conservation authority must change.\n- H4 physical cap, capped actionable reserve, power tables, B0 reference, candidate identities and eligibility require propagation.\n- Electrical coefficient class A under exact unchanged exogenous anchor and generator inputs; reuse must be recertified, not relabeled as fresh generation.\n- Recentered anchor means full 31-day regeneration. No generation performed in this audit.\n- Capacity and baseline do not directly enter existing electrical coefficient arithmetic; they do enter the context power tables after coefficients.\n- Current PCC: 500 kVA and 208.179183602 A per AIDC transformer phase, plus shared network constraints.\n\nExact file/line/hash dependencies are in GPU_CAPACITY_DEPENDENCY_AUDIT.json and ELECTRICAL_COEFFICIENT_IMPACT_AUDIT.json.\n'''
 (OUT/'GPU_CAPACITY_DEPENDENCY_GRAPH.md').write_text(graph,encoding='utf-8')
 return a

def plot(a):
 try:
  import matplotlib
 except ModuleNotFoundError:
  path=OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.md'
  path.write_text(path.read_text(encoding='utf-8').replace('![Capacity sensitivity](capacity_sizing_overview.png)',''),encoding='utf-8')
  return
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 z=np.load(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz');d=z['D_GPU_offered_total'];known=z['D_GPU_offered_known_site'].sum(2)
 fig,ax=plt.subplots(2,2,figsize=(13,8),layout='constrained');fig.suptitle('V41R2 | Reference-only capacity audit — no candidate qualifies',fontsize=16)
 days=np.arange(1,32)
 ax[0,0].bar(days,known.mean(1),label='Known site component',color='#287d8e');ax[0,0].bar(days,(d-known).mean(1),bottom=known.mean(1),label='UNASSIGNED D-day offered',color='#e4a750')
 ax[0,0].axhline(2752,color='#a52a40',ls='--',label='80% capacity: 2,752');ax[0,0].set(xlabel='May day (independent forecasts)',ylabel='Mean offered GPU slots');ax[0,0].legend(fontsize=8)
 for k,color in [('75','#287d8e'),('80','#a52a40'),('85','#66589b')]:
  u=np.sort(d.ravel()/a['candidates'][k]['total']);ax[0,1].plot(100*np.arange(1,len(u)+1)/len(u),100*u,label=f'{k}% target',color=color)
 ax[0,1].axhline(100,color='gray',ls='--');ax[0,1].set(xlabel='Offered-demand percentile',ylabel='Offered / installed capacity (%)');ax[0,1].legend()
 x=np.arange(96)/4;ax[1,0].step(x,z['D_GPU_materialized_624'][3].sum(1),where='post',label='Old queued reference',color='#66589b');ax[1,0].step(x,d[3],where='post',label='D00-anchored offered',color='#287d8e');ax[1,0].axvline(18,color='gray',ls='--');ax[1,0].set(xlabel='May-04 fixed AEST hour',ylabel='GPU slots');ax[1,0].legend()
 for k,color in [('75','#287d8e'),('80','#a52a40'),('85','#66589b')]:
  s=np.load(OUT/f'HEADROOM_BY_SLOT_{k}.npz')['feasible_destinations_GPU_32'];ax[1,1].plot(days,(s>=1).mean(1)*100,label=f'{k}% target',color=color)
 ax[1,1].set(xlabel='May day',ylabel='Slots with a 32-GPU destination (%)',ylim=(-3,103));ax[1,1].legend();fig.savefig(OUT/'capacity_sizing_overview.png',dpi=160);plt.close(fig)

def preserve_end():
 before=read(OUT/'PROTECTED_BEFORE.json');changed=[];missing=[];checked=0;totalbytes=0
 for row in before['files']:
  p=Path(row['path'])
  if not p.exists():missing.append(str(p));continue
  if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:changed.append(str(p))
  checked+=1;totalbytes+=row['bytes']
  if checked%1000==0:print('VERIFY_PROTECTED',checked,flush=True)
 after=git('status','--porcelain');head=git('rev-parse','HEAD')
 result=dict(status='PASS' if not changed and not missing and after==before['git_status'] and head==before['git_HEAD'] else 'FAIL',
    files_checked=checked,bytes_checked=totalbytes,changed=changed,missing=missing,git_status_unchanged=after==before['git_status'],git_HEAD_unchanged=head==before['git_HEAD'],
    original_manifest=record(OUT/'PROTECTED_BEFORE.json'),production_mutations=0)
 write('PROTECTED_AFTER_AUDIT.json',result);assert result['status']=='PASS'
 manifest=[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ('V41R2_ARTIFACT_SHA256.json','finish_run.log')]
 write('V41R2_ARTIFACT_SHA256.json',dict(files=manifest,status='PASS'))
 print('PROTECTED_PASS',checked,totalbytes,flush=True)

if __name__=='__main__':
 a=read(OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json');v=audit_current_and_verify(a);a=write_report(a,v);plot(a);preserve_end()
