"""Read-only V41R1 capacity audit. All writes are confined to this folder.

No policy optimizer, Actual replay, electrical generator or production writer
is imported. Only the pure frozen first-fit materializer is loaded by path.
"""
from pathlib import Path
from collections import Counter
from types import SimpleNamespace
import csv, hashlib, importlib.util, json, math, os, subprocess, sys
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('V41R2_AUTHORITY_ROOT','D:/codex_mobileess_workspace/MobileESS_v41r1_premay_voltage_security_margin'))
SOURCE=Path(os.environ.get('V41R2_SOURCE_ROOT','D:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt'))
RUNTIME=ROOT/'frozen_artifacts/v41r1_migration'
ART=ROOT/'dayahead/artifacts'
CAP=ART/'v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json'
RACK=ART/'v39d_independent_daily_temporal_first_migration/V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json'
WEIGHTS=ART/'v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv'
SITES=[f'AIDC{i:02}' for i in range(1,13)]
DAYS=[f'2025-05-{i:02}' for i in range(1,32)]
INPUTS={}

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def record(p):
 p=Path(p).resolve();r=dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p));INPUTS[str(p)]=r;return r
def read(p):
 record(p);return json.loads(Path(p).read_text(encoding='utf-8'))
def serial(x):
 if isinstance(x,np.ndarray):return x.tolist()
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,Path):return str(x)
 raise TypeError(type(x))
def write(name,value):
 p=OUT/name;assert p.parent==OUT
 p.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=serial,allow_nan=False)+'\n',encoding='utf-8')
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True,encoding='utf-8').strip()
def provenance(p,field=None):
 p=Path(p);rel=p.relative_to(ROOT).as_posix()
 commits=git('log','--follow','--format=%H','--',rel).splitlines()
 return dict(**record(p),field=field,creating_commit=commits[-1] if commits else None,
             github=f'https://github.com/BeaverVillage/MobileESS/blob/{commits[-1]}/{rel}' if commits else None)
def stats(a):
 a=np.asarray(a,dtype=float)
 return dict(mean=float(a.mean()),**{f'P{q}':float(np.percentile(a,q)) for q in (10,50,90,95,99)},max=float(a.max()),min=float(a.min()))
def trace_stats(a):return dict(**stats(a),GPU_hours=float(np.sum(a)/4))
def hist(a):return {str(k):int(v) for k,v in sorted(Counter(np.asarray(a).tolist()).items())}

def preserve_start():
 p=OUT/'PROTECTED_BEFORE.json'
 if p.exists():return json.loads(p.read_text())
 files=set()
 for base in (ROOT/'dayahead',ROOT/'frozen_artifacts',ROOT/'tests'):
  for f in base.rglob('*'):
   if not f.is_file() or '__pycache__' in f.parts:continue
   rel=f.relative_to(ROOT).as_posix()
   if rel.startswith('frozen_artifacts/') or ('/artifacts/v41' in rel) or (f.suffix=='.py' and '/artifacts/' not in rel):files.add(f)
 # All evidence and coefficients receive byte hashes; no result values are parsed.
 rows=[]
 for f in sorted(files):rows.append(dict(path=str(f),bytes=f.stat().st_size,sha256=sha(f)))
 value=dict(git_HEAD=git('rev-parse','HEAD'),git_status=git('status','--porcelain'),files=rows,
            scope='All frozen_artifacts; V41/V41R1 artifact directories; Python source/tests. Hashing evidence is not reading outcomes for selection.')
 write(p.name,value);return value

def apportion(continuous,weights,current):
 # Hardware unit is one 4-GPU equivalent H100 node, not a logical rack.
 units=int(math.floor(continuous/4+0.5));target=units*4
 quota=target*np.asarray(weights)/4;allocation=np.floor(quota).astype(int)
 order=sorted(range(12),key=lambda i:(-(quota[i]-allocation[i]),i))
 for i in order[:units-int(allocation.sum())]:allocation[i]+=1
 cap=4*allocation
 assert cap.sum()==target and np.all(cap%4==0)
 return cap,dict(continuous_total=continuous,nearest_valid_total=target,total_rounding_error=target-continuous,
    alpha_continuous=continuous/sum(current),alpha_rounded=target/sum(current),unit_GPU=4,
    rule='Nearest total multiple of four (half upward); Hamilton largest remainders in nodes; AIDC numeric tie-break.',
    rows=[dict(site=s,continuous_ideal=continuous*weights[i],rounded_total_ideal=target*weights[i],capacity=int(cap[i]),
      error_vs_continuous=cap[i]-continuous*weights[i],error_vs_rounded_ideal=cap[i]-target*weights[i]) for i,s in enumerate(SITES)])

def headroom(a,cap,sizes):
 a=a.reshape(-1,12);u=a/cap;total=a.sum(1)/cap.sum();net=cap-a;spare=np.maximum(net,0);full=a>=cap
 site={s:dict(**stats(u[:,i]),FULL_fraction=float(full[:,i].mean()),
   available_GPU_mean=float(spare[:,i].mean()),available_GPU_P10=float(np.percentile(spare[:,i],10)),
   available_GPU_P50=float(np.percentile(spare[:,i],50)),headroom_GPU_hours=float(spare[:,i].sum()/4),
   overload_GPU_hours=float(np.maximum(-net[:,i],0).sum()/4),net_headroom_GPU_hours=float(net[:,i].sum()/4)) for i,s in enumerate(SITES)}
 available=(net>0).sum(1);feas={}
 for size in sizes:
  n=(net>=size).sum(1) # exact instantaneous compatibility under nonadditive full-site envelopes
  feas[str(size)]=dict(job_GPU=size,distribution=hist(n),**{f'fraction_at_least_{k}':float((n>=k).mean()) for k in (1,2,3)})
 return dict(system=dict(**stats(total),**{f'fraction_ge_{k}':float((total>=k/100).mean()) for k in (90,95,100)}),
   sites=site,all12_FULL_fraction=float(full.all(1).mean()),ge10_FULL_fraction=float((full.sum(1)>=10).mean()),
   sites_positive_headroom_every_slot=[s for i,s in enumerate(SITES) if (net[:,i]>0).all()],
   number_sites_positive_headroom_every_slot=int((net>0).all(0).sum()),available_destination_count_distribution=hist(available),
   fraction_any_positive_headroom=float((available>=1).mean()),whole_job_feasibility=feas,
   May04_1800=dict(offered_GPU=a[3*96+72],net_headroom_GPU=net[3*96+72],available_GPU=spare[3*96+72],available_sites=int(available[3*96+72])),
   compatibility_scope='Instantaneous whole-job GPU/rack compatibility only; no duration reservation, source exclusion, WAN, power or policy feasibility claimed.')

def load_data():
 arrays={k:np.zeros((31,96,12),np.int64) for k in ('old','pre_q90','offered','issue_offered')}
 unassigned={k:np.zeros((31,96),np.int64) for k in ('offered','issue_offered')}
 cohorts=[];rows=[];audit=[];sizes=[];full_sizes=[];delay_rows=[]
 for di,day in enumerate(DAYS):
  p=RUNTIME/'inputs'/day;common=p/'common_q90_v3'
  jobs=read(common/'COMMON_B0_REFERENCE_JOBS.json');base=read(common/'Q90_BASELINE_MATERIALIZATION.json')
  snap=read(p/f'V41_ML_SNAPSHOT_{day}.json');record(common/'COMMON_DA_SERVICE_AUTHORITY.json')
  lp=SOURCE/'dayahead/artifacts/v37_r4a_per_day_aidc/days'/day/'V37_R4A_JOB_LEDGER.parquet';record(lp)
  df=pd.read_parquet(lp,columns=['job_id','state_at_issue','RSP_duration_slots','RSP_duration_seconds','duration_authority','RW_scheduled_start','submit_time'])
  ledger={str(r['job_id']):r for r in df.to_dict('records')};b={x['job_id']:x for x in base['rows']}
  assert len(jobs)==len(ledger)==len(b) and set(ledger)==set(b)
  queue_before=0
  for j in jobs:
   uid=j['job_uid'];g=int(j['requested_GPU']);dur=int(j['safe_duration_slots']);start=int(j['start_slot']);end=start+dur;l=ledger[uid]
   assert pd.Timestamp(j['submit_time'])<=pd.Timestamp(snap['issue_time']) and not j.get('migration_selected')
   if j['state_at_issue']=='PENDING':
    assert dur==snap['PENDING_JOB_DURATION_SLOTS'][uid] and j['safe_duration_seconds']==snap['PENDING_JOB_Q90_SECONDS'][uid]
   else:assert dur==int(l['RSP_duration_slots']) and j['safe_duration_seconds']==l['RSP_duration_seconds']
   oldstart=b[uid]['old_start_issue_slot'];assert oldstart==int(l['RW_scheduled_start'])
   queue_before+=oldstart>0 and j['state_at_issue']=='PENDING'
   # Day-D boundary is held fixed: completed jobs remain complete; D00 RUNNING
   # jobs retain their exact residual. Known pending backlog has no exogenous
   # future release field; remove inherited capacity waiting from D00 onward.
   release=start if start<24 else 24
   starts=dict(old=start,pre_q90=oldstart,offered=release,issue_offered=0)
   assigned=j['AIDC_site'] in SITES
   if assigned:idx=SITES.index(j['AIDC_site'])
   for k,s in starts.items():
    lo=max(24,s);hi=min(120,s+dur)
    if hi>lo:
     if assigned:arrays[k][di,lo-24:hi-24,idx]+=g
     elif k in unassigned:unassigned[k][di,lo-24:hi-24]+=g
   full_sizes.append(g)
   if assigned and end>24:sizes.append(g)
   row=dict(day=day,job_uid=uid,site=j['AIDC_site'],GPU=g,state_at_issue=j['state_at_issue'],
      D00_state='COMPLETE' if end<=24 else 'RUNNING' if start<24 else 'PENDING',
      duration_slots=dur,reference_start=start,pre_Q90_start=oldstart,offered_start=release,
      D00_residual_slots=max(0,end-24) if start<24 else None,capacity_wait_slots_removed=max(0,start-24),
      assigned=assigned,priority_key=b[uid]['priority_key'])
   rows.append(row)
  cohorts.append((day,jobs,base))
  audit.append(dict(day=day,jobs=len(jobs),assigned=sum(j['AIDC_site'] in SITES for j in jobs),
    unassigned=sum(j['AIDC_site']=='UNASSIGNED' for j in jobs),Q90_additional_delay_jobs=base['changed_start_jobs'],
    inherited_RW_queued_jobs=queue_before,Q90_issue=snap['issue_time'],
    D00_running=sum(j['start_slot']<24<j['end_slot'] for j in jobs)))
  print('READ',day,len(jobs),flush=True)
 pd.DataFrame(rows).to_csv(OUT/'OFFERED_JOB_REFERENCE_AUDIT.csv',index=False)
 return arrays,unassigned,cohorts,audit,rows,sizes,full_sizes

def rematerialize(cohorts,capacities,rack,jobrows):
 spec=importlib.util.spec_from_file_location('audited_frozen_baseline',ROOT/'dayahead/v41r1/migration_baseline.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 class Capacity:
  def __init__(self,c):
   self.aidc_ids=tuple(SITES);self.site_capacity=dict(zip(SITES,map(int,c)))
   self.rack_pools=tuple(SimpleNamespace(aidc_id=r['aidc_id'],rack_pool_id=r['rack_pool_id'],historical_gpu_capacity=self.site_capacity[r['aidc_id']]) for r in rack['logical_Rack_pools'])
  def eligible_racks(self,s,g):return [r for r in self.rack_pools if r.aidc_id==s and r.historical_gpu_capacity>=g]
 allrows=[];profiles={};summaries={};checks=[]
 for name,cap in capacities.items():
  result_days=[];profile=np.zeros((31,96,12),np.int64)
  for di,(day,jobs,baseline) in enumerate(cohorts):
   entries={r['job_id']:r for r in baseline['rows']};original={j['job_uid']:j for j in jobs}
   sched=[SimpleNamespace(job_id=j['job_uid'],priority_key=tuple(entries[j['job_uid']]['priority_key'])) for j in jobs]
   data=[]
   for j in jobs:
    row=dict(j)
    if name=='current_reproduction':row.update(start_slot=entries[j['job_uid']]['old_start_issue_slot'])
    else:
     if row['start_slot']<24:row['state_at_issue']='RUNNING'
     else:row['start_slot']=24
    row['end_slot']=row['start_slot']+row['safe_duration_slots'];data.append(row)
   new,evidence=mod.materialize(data,sched,Capacity(cap))
   if name=='current_reproduction':
    assert all((r['start_slot'],r['end_slot'],r['Rack_label'])==(original[r['job_uid']]['start_slot'],original[r['job_uid']]['end_slot'],original[r['job_uid']]['Rack_label']) for r in new)
    checks.append(dict(day=day,exact_current_reproduction=True));continue
   counts=Counter();wait_old=wait_new=GPUwait_old=GPUwait_new=0.;carry_old=carry_new=0.
   for n in new:
    old=original[n['job_uid']];uid=n['job_uid']
    if old['AIDC_site'] not in SITES:continue
    i=SITES.index(old['AIDC_site']);g=old['requested_GPU'];a=n['start_slot'];b=n['end_slot'];lo=max(24,a);hi=min(120,b)
    if hi>lo:profile[di,lo-24:hi-24,i]+=g
    o=old['start_slot'];oe=old['end_slot'];release=o if o<24 else 24
    wo=max(0,o-release);wn=max(0,a-release)
    assert a>=release and n['AIDC_site']==old['AIDC_site']
    if o<24:assert a==o and b==oe
    counts['start_change_jobs']+=a!=o;counts['earlier_jobs']+=a<o;counts['later_jobs']+=a>o
    counts['old_delayed_jobs']+=wo>0;counts['new_delayed_jobs']+=wn>0
    counts['old_delayed_now_no_delay']+=wo>0 and wn==0
    counts['same_day_completions_old']+=24<oe<=120;counts['same_day_completions_new']+=24<b<=120
    counts['carryout_jobs_old']+=oe>120;counts['carryout_jobs_new']+=b>120
    counts['D24_running_jobs_old']+=o<120<oe;counts['D24_running_jobs_new']+=a<120<b
    carry_old+=max(0,oe-max(120,o))*g/4;carry_new+=max(0,b-max(120,a))*g/4
    wait_old+=wo/4;wait_new+=wn/4;GPUwait_old+=wo*g/4;GPUwait_new+=wn*g/4
    allrows.append(dict(option=name,day=day,uid=uid,site=old['AIDC_site'],GPU=g,old_start=o,new_start=a,release=release,
      old_end=oe,new_end=b,old_wait_slots=wo,new_wait_slots=wn))
   assert np.all(profile[di]<=cap)
   result_days.append(dict(day=day,**counts,old_queue_job_hours=wait_old,new_queue_job_hours=wait_new,
      queue_reduction_job_hours=wait_old-wait_new,old_queue_GPU_hours=GPUwait_old,new_queue_GPU_hours=GPUwait_new,
      carryout_GPU_hours_old=carry_old,carryout_GPU_hours_new=carry_new))
  if name=='current_reproduction':continue
  summaries[name]=dict(days=result_days,aggregate={k:sum(d.get(k,0) for d in result_days) for k in result_days[0] if k!='day'},
    study='Independent 31-day fixed-site first fit, D00 running residual held fixed, known pending released D00. No optimization, no day-to-day carry propagation.')
  profiles[name]=profile
  print('REMATERIALIZED',name,summaries[name]['aggregate']['start_change_jobs'],flush=True)
 pd.DataFrame(allrows).to_csv(OUT/'B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv',index=False)
 np.savez_compressed(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz',**profiles)
 write('B0_REMATERIALIZATION_IMPACT_AUDIT.json',summaries)
 write('CURRENT_B0_EXACT_REPRODUCTION_CHECK.json',checks)
 return summaries,profiles

def main():
 before=preserve_start();print('PROTECTED',len(before['files']),flush=True)
 cap=read(CAP);rack=read(RACK);current=np.array(cap['canonical_GPU_vector']);assert current.sum()==cap['total_GPUs']==624
 weight=pd.read_csv(WEIGHTS);record(WEIGHTS)
 assert np.allclose(weight.primary_IT_equivalent_capacity_MW/weight.primary_IT_equivalent_capacity_MW.sum(),weight.capacity_weight,atol=1e-14)
 histcap=ART/'v22s_r1_final_operating_scale/V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv';hc=pd.read_csv(histcap);record(histcap)
 assert weight.GPU_weight_authority.eq('UNAVAILABLE_NOT_INFERRED').all()
 currentauthority=dict(total=624,vector=current,semantics=cap['capacity_semantics'],case='A',
    decision='Defensible frozen synthetic engineering allocation: 4-GPU nodes, recurrent pre-May 32-GPU gangs, 32-GPU service floor, primary facility-scale rank for residual blocks. Preserve its proportions with common alpha. Not a measured GPU census or a proportional MW-to-GPU conversion.',
    source=provenance(CAP,'canonical_GPU_vector; site_table[*].synthetic_H100_equivalent_GPU_capacity'),rack_source=provenance(RACK,'logical_Rack_pools'),
    upstream_rule_commit=cap['capacity_rule_source_commit'],weights=provenance(WEIGHTS,'capacity_weight'),
    rows=[dict(site=s,GPU=int(current[i]),equivalent_H100_nodes=int(current[i]//4),GPU_per_node=4,
       physical_rack_count=None,physical_GPU_per_rack=None,logical_pool_count=sum(r['aidc_id']==s for r in rack['logical_Rack_pools']),
       logical_pool_GPU_limits=[r['compatibility_GPU_limit'] for r in rack['logical_Rack_pools'] if r['aidc_id']==s],
       scheduling_ceiling_GPU=int(current[i]),site_IT_idle_kW=float(current[i]*.1041606964512843),
       site_IT_full_active_kW=float(current[i]*.651884605470864),
       other_site_IT_ceiling='No separate site IT inequality in current scheduler; power lookup range follows 0..C_GPU.',
       PCC_ceiling='Network line/transformer ratings; no independent scalar site-PCC scheduler ceiling found. Historical V22SR1 interface 0.3 MVA is not proof of current runtime binding.') for i,s in enumerate(SITES)],
    rack_semantics='48 nonadditive logical pools, four/site; each envelope equals entire site capacity. No physical racks/GPU-per-rack authority available.',
    single_gang_split_allowed=False)
 write('CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json',currentauthority)
 historical=dict(source=provenance(WEIGHTS),primary_source=provenance(histcap),primary_total_MW=float(weight.primary_IT_equivalent_capacity_MW.sum()),
    PR12='https://github.com/BeaverVillage/MobileESS/pull/12',PR12_head='499d5793ed4b725fa5d0b38691b07752c4f88482',
    rows=[dict(**r,**{k:v for k,v in hc.iloc[i].to_dict().items() if k not in r and not (isinstance(v,float) and math.isnan(v))}) for i,r in enumerate(weight.to_dict('records'))],
    historical_GPU_authority='UNAVAILABLE_NOT_INFERRED',MW_direct_GPU_conversion=False,
    role='Historical engineering IT-equivalent facility size, not metered power or GPU census.',
    upstream_evidence=[record(ART/'v22s_melbourne_12site_scale/V22S_SITE_GPU_WEIGHT_AUTHORITY.json'),record(ART/'v22s_r1_final_operating_scale/V22SR1_SCALING_METHOD_FREEZE.json'),record(ART/'v22s_r1_final_operating_scale/V22SR1_SOURCE_REVERIFICATION.json')])
 write('HISTORICAL_SITE_SCALE_AUTHORITY.json',historical)
 arrays,unassigned,cohorts,cohort_audit,jobrows,sizes,full_sizes=load_data()
 demand=arrays['offered'];system=demand.sum(2)
 empirical=dict(admitted_job_observations=dict(P50=float(np.percentile(sizes,50)),P90=float(np.percentile(sizes,90)),distribution=hist(sizes)),
   entire_frozen_ledger_job_observations=dict(P50=float(np.percentile(full_sizes,50)),P90=float(np.percentile(full_sizes,90)),distribution=hist(full_sizes)))
 reps=sorted({1,4,8,16,32,int(np.percentile(sizes,50)),int(np.percentile(sizes,90))})
 np.savez_compressed(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz',D_GPU_offered=demand,sites=np.array(SITES),days=np.array(DAYS),
    D_GPU_materialized_624=arrays['old'],D_GPU_pre_Q90_but_RW_queued=arrays['pre_q90'],D_GPU_issue_release=arrays['issue_offered'],
    D_GPU_UNASSIGNED=unassigned['offered'],D_GPU_UNASSIGNED_issue_release=unassigned['issue_offered'],
    local_slot_minutes=np.arange(96)*15)
 offered=dict(scope='ASSIGNED_REFERENCE_COHORT_D00_CONDITIONAL_OFFERED_DEMAND',
   construction='Independent days; fixed AEST UTC+10; issue D-1 18:00. Retain completed and D00 RUNNING reference execution/residual. Release all known D00 PENDING assigned jobs at D00 after stripping inherited GPU waiting. Keep frozen initial site and Q90 slot-rounded duration. No future arrivals or actual execution labels.',
   limitation='This removes post-D00 timing queueing but is conditional on legacy capacity-constrained admission/site assignment and D00 state. UNASSIGNED demand has no authoritative site and is reported separately, never treated as zero workload.',
   aggregate=trace_stats(system),per_site={s:dict(**trace_stats(demand[:,:,i]),share=float(demand[:,:,i].sum()/demand.sum())) for i,s in enumerate(SITES)},
   day_by_day=[dict(day=d,**trace_stats(system[i])) for i,d in enumerate(DAYS)],
   time_of_day=[dict(time=f'{k//4:02}:{k%4*15:02}',**trace_stats(system[:,k])) for k in range(96)],
   May04=dict(aggregate=trace_stats(system[3]),per_site={s:trace_stats(demand[3,:,i]) for i,s in enumerate(SITES)},critical_1800_GPU=demand[3,72]),
   unassigned=dict(aggregate=trace_stats(unassigned['offered']),day_by_day=[dict(day=d,**trace_stats(unassigned['offered'][i])) for i,d in enumerate(DAYS)]),
   all_ledger_system_D00_mean=float((system+unassigned['offered']).mean()),
   release_issue_sensitivity=dict(assigned=trace_stats(arrays['issue_offered'].sum(2)),unassigned=trace_stats(unassigned['issue_offered']),
      warning='Starts all issue-known pending jobs at issue; changes D00 RUNNING state and completes some work before Day D. Not chosen for sizing because D00 residual preservation was requested.'),
   old_trajectory=trace_stats(arrays['old'].sum(2)),old_vs_offered=dict(net_GPU_hours=float((demand-arrays['old']).sum()/4),
       absolute_site_slot_GPU_hours=float(np.abs(demand-arrays['old']).sum()/4),changed_site_slots=int((demand!=arrays['old']).sum()),
       May04_old_mean=float(arrays['old'][3].sum(1).mean()),May04_offered_mean=float(system[3].mean())),cohorts=cohort_audit,
   empirical_job_sizes=empirical,quantile_method='numpy percentile linear, equal 15-minute slot weights; days are independent scenario snapshots, not continuous observed May.')
 write('OFFERED_DEMAND_DISTRIBUTION.json',offered)
 pd.DataFrame(offered['day_by_day']).to_csv(OUT/'OFFERED_DEMAND_DAILY.csv',index=False)
 pd.DataFrame(offered['time_of_day']).to_csv(OUT/'OFFERED_DEMAND_TIME_OF_DAY.csv',index=False)
 pd.DataFrame([dict(site=s,**v) for s,v in offered['per_site'].items()]).to_csv(OUT/'OFFERED_DEMAND_PER_SITE.csv',index=False)
 candidates={};rounding={};flat=[];caps={}
 for target in (.75,.80,.85):
  name=f'{int(target*100)}';c,r=apportion(float(system.mean()/target),current/current.sum(),current)
  caps[name]=c;rounding[name]=r;candidates[name]=dict(target=target,total=int(c.sum()),vector=c,headroom=headroom(demand,c,reps))
  for i,s in enumerate(SITES):flat.append(dict(target_occupancy=target,site=s,current_GPU=int(current[i]),candidate_GPU=int(c[i]),
    equivalent_nodes=int(c[i]//4),total_GPU=int(c.sum()),continuous_total=r['continuous_total'],**{k:v for k,v in r['rows'][i].items() if k not in ('site','capacity')}))
 write('CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json',rounding)
 pd.DataFrame(flat).to_csv(OUT/'V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv',index=False)
 allcaps=dict(current_reproduction=current,dequeued_624=current,**caps)
 remat,profiles=rematerialize(cohorts,allcaps,rack,jobrows)
 for k,c in candidates.items():
  c['rematerialized_occupancy']=headroom(profiles[k],caps[k],reps)
  c['rematerialization']=remat[k]['aggregate']
  c['installed_idle_IT_increase_kW']=(c['total']-624)*.1041606964512843
  c['full_active_IT_ceiling_kW']=c['total']*.651884605470864
  counts={}
  for size in reps:counts[f'feasible_destinations_GPU_{size}']=((caps[k]-demand)>=size).sum(2)
  np.savez_compressed(OUT/f'HEADROOM_BY_SLOT_{k}.npz',net_GPU=caps[k]-demand,available_GPU=np.maximum(caps[k]-demand,0),
     number_positive_headroom=((caps[k]-demand)>0).sum(2),**counts)
 oldhead=headroom(arrays['old'],current,reps);offeredold=headroom(demand,current,reps)
 result=dict(status='RECOMMENDED_CAPACITY_AUTHORITY_AUDIT_ONLY',production_capacity_applied=False,Full_May='HOLD',
    current=currentauthority,historical=historical,offered=offered,candidates=candidates,
    current_materialized_headroom=oldhead,current_offered_headroom=offeredold,
    execution_counts=dict(B0_policy_optimizer=0,B1=0,B2=0,B3=0,Actual_replay=0,Fresh_AC=0,electrical_generation=0,ML_training=0),
    recommendation=None)
 write('V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json',result)
 write('MAY_31DAY_Q90_OFFERED_GPU_DEMAND_MANIFEST.json',dict(file=record(OUT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz'),
    shape=[31,96,12],dtype='int64',scope=offered['scope'],method=offered['construction'],limitations=offered['limitation'],
    conservation=dict(sum_GPU_hours=float(demand.sum()/4),per_site_sum_GPU_hours=sum(v['GPU_hours'] for v in offered['per_site'].values()),
      all_nonnegative=bool((demand>=0).all()),Q90_and_running_duration_checked=True,causal_submission_checked=True),inputs=list(INPUTS.values())))
 write('INPUT_SOURCE_MANIFEST.json',list(INPUTS.values()))
 print(json.dumps({k:dict(total=c['total'],vector=c['vector'],system=c['headroom']['system'],full=c['headroom']['all12_FULL_fraction'],
    dest4=c['headroom']['whole_job_feasibility']['4'],site_means={s:v['mean'] for s,v in c['headroom']['sites'].items()}) for k,c in candidates.items()},default=serial,indent=2))

if __name__=='__main__':main()
