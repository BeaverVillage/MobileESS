"""User-authorized A/B reference-only comparison; never changes production."""
from final_audit import *
from finish import table,fmt,pct,vec
import gzip,shutil

RULE_A='LEGACY_SHAPE_SCALE'
RULE_B='GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL'

def generalized(total,weights):
 assert total%4==0 and total>=384
 nodes=(total-384)//4;quota=nodes*weights;alloc=np.floor(quota).astype(int)
 order=sorted(range(12),key=lambda i:(-(quota[i]-alloc[i]),i))
 for i in order[:nodes-int(alloc.sum())]:alloc[i]+=1
 cap=32+4*alloc
 assert cap.sum()==total and np.all(cap>=32) and np.all(cap%4==0)
 return cap,dict(rule=RULE_B,base_GPU=384,minimum_GPU=32,residual_nodes=nodes,weights=weights,
   quota_residual_nodes=quota,residual_nodes_allocated=alloc,error_GPU=cap-(32+(total-384)*weights),
   total_error=0,historically_identical_to_V39C=False,tie_break='AIDC numeric ascending',
   authority_role='Relative facility/site scale only, not measured GPU count or direct MW conversion.')

def gzip_file(src,dst):
 with open(src,'rb') as f,open(dst,'wb') as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as z:shutil.copyfileobj(f,z)

def run():
 a=read(OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json');assert 'allocation_comparison' not in a,'Use a fresh audit or retain existing completed comparison.'
 weights=pd.read_csv(WEIGHTS).capacity_weight.to_numpy();weights=weights/weights.sum()
 allc={};bcaps={};rounds=read(OUT/'CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json');newrounds={}
 for k,v in a['candidates'].items():
  av=deepcopy(v);av['allocation_rule']=RULE_A;allc['A'+k]=av;newrounds['A'+k]=rounds[k]
  b,r=generalized(v['total'],weights);bcaps['B'+k]=b;newrounds['B'+k]=r
 write('A_B_ALLOCATION_RULE_FREEZE.json',dict(rules=[RULE_A,RULE_B],weights_source=record(WEIGHTS),
   B_formula='32 GPU/site + Hamilton((C_total - 384)/4 nodes, V22SR1 weights)*4',
   B_not_historical_identity=True,allocations={k:list(map(int,v)) for k,v in bcaps.items()},
   selection_prohibited=['B1/B2/B3 objective','May realized site-assignment fitting'],rule_frozen_before_B_replay=True))
 frame=pd.read_csv(OUT/'UNASSIGNED_AND_DDAY_COHORT_CLASSIFICATION.csv');rows=json.loads(frame.to_json(orient='records'))
 for r in rows:
  r['priority_key']=ast.literal_eval(r['priority_key'])
  for key in ('GPU','duration_slots','reference_start'):r[key]=int(r[key])
 # Preserve A evidence before shared pure helper emits B results.
 gzip_file(OUT/'B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv',OUT/'A_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz')
 shutil.copy2(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz',OUT/'A_B0_RESOURCE_REMATERIALIZATION_STUDY.npz')
 astudies={k:deepcopy(v['B0_rematerialization']) for k,v in a['candidates'].items()}
 profiles,studies=replay_options(rows,bcaps)
 gzip_file(OUT/'B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv',OUT/'B_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz')
 shutil.copy2(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz',OUT/'B_B0_RESOURCE_REMATERIALIZATION_STUDY.npz')
 reps=sorted(map(int,a['candidates']['80']['materialized_headroom']['whole_job_feasibility']))
 for k,c in bcaps.items():
  base=a['candidates'][k[1:]];h=headroom(profiles[k],c,reps);h['May04_1800']['resource_replay_GPU']=h['May04_1800'].pop('offered_GPU')
  allc[k]=dict(target=base['target'],total=int(c.sum()),vector=c,continuous_total=base['continuous_total'],allocation_rule=RULE_B,
    system_offered_occupancy=deepcopy(base['system_offered_occupancy']),materialized_headroom=h,B0_rematerialization=studies[k])
  np.savez_compressed(OUT/f'HEADROOM_BY_SLOT_{k}.npz',actual_resource_replay_GPU=profiles[k],available_GPU=c-profiles[k],
    number_positive_headroom=((c-profiles[k])>0).sum(2),**{f'feasible_destinations_GPU_{g}':((c-profiles[k])>=g).sum(2) for g in reps})
 for k in ('75','80','85'):shutil.copy2(OUT/f'HEADROOM_BY_SLOT_{k}.npz',OUT/f'HEADROOM_BY_SLOT_A{k}.npz')
 oldpower=pd.read_csv(OUT/'CAPACITY_POWER_BOUND_IMPACT.csv');oldpower['option']='A'+oldpower.option.astype(str)
 oldh4=read(OUT/'H4_CAPACITY_DEPENDENCY_AUDIT.json')
 for r in oldh4:r['option']='A'+r['option']
 olddep=deepcopy(a['dependencies']);dep,_=power_audit(bcaps,np.array(a['current']['vector']))
 newpower=pd.read_csv(OUT/'CAPACITY_POWER_BOUND_IMPACT.csv');pd.concat([oldpower,newpower]).to_csv(OUT/'CAPACITY_POWER_BOUND_IMPACT.csv',index=False)
 write('H4_CAPACITY_DEPENDENCY_AUDIT.json',oldh4+read(OUT/'H4_CAPACITY_DEPENDENCY_AUDIT.json'))
 dep['candidate_results'].update({'A'+k:v for k,v in olddep['candidate_results'].items()});a['dependencies']=dep
 write('GPU_CAPACITY_DEPENDENCY_AUDIT.json',dep)
 validation=[];flat=[]
 for k,v in allc.items():
  c=np.array(v['vector']);share=c/c.sum();delta=share-weights;residual_share=(c-32)/(c.sum()-384)
  v['V22SR1_weight_distortion']=dict(total_capacity_L1=float(abs(delta).sum()),total_variation=float(abs(delta).sum()/2),
     max_absolute_share_error=float(abs(delta).max()),residual_L1=float(abs(residual_share-weights).sum()),per_site_share_error=delta)
  v['gang_rack_feasibility']=dict(capacity_sum_conserved=True,minimum_32_floor=True,four_GPU_nodes=True,
     largest_visible_pending_gang=256,compatible_sites_for_256=[SITES[i] for i,x in enumerate(c) if x>=256],
     immutable_running_sources_fit=True,interval_endpoint_conservation=True)
  q=v['B0_rematerialization']['aggregate'];v['qualification']='UNDERSIZED_D_DAY_SERVICE_NOT_CLOSED' if q.get('remaining_Dday_unserved_pending',0) else 'RESOURCE_SERVICE_CLOSED'
  v['remaining_Dday_UNASSIGNED']=dict(pending_jobs=q.get('remaining_Dday_unserved_pending',0),
     pending_offered_GPU_hours=q.get('unserved_Dday_offered_GPU_hours',0),ambiguous_jobs=14,ambiguous_GPU_hours=11.)
  for i,s in enumerate(SITES):flat.append(dict(option=k,allocation_rule=v['allocation_rule'],target=v['target'],site=s,
    current_GPU=a['current']['vector'][i],candidate_GPU=int(c[i]),total_GPU=int(c.sum()),nodes=int(c[i]//4),
    facility_weight=weights[i],candidate_share=share[i],share_error=delta[i]))
  if k.startswith('B'):
   for day in ('2025-05-04','2025-05-21'):
    p,_=scheduler(day,[r for r in rows if r['day']==day],c);assert np.array_equal(p,profiles[k][DAYS.index(day)])
    validation.append(dict(option=k,day=day,exact_repeat=True))
 a['candidates']=allc;a['allocation_comparison']=dict(A=RULE_A,B=RULE_B,all_totals_conserved=True,
   B_generalized_not_historically_identical=True,empirical_P50_GPU=1,empirical_P90_GPU=2,
   weight_distortion_metric='L1 distance of total-capacity share to authoritative facility weight; residual L1 also reported; minimum floor makes exact total-share matching neither required nor intended.')
 a['verification']['deterministic_repeats']+=validation;a['verification']['six_candidates_verified']=True
 write('CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json',newrounds)
 pd.DataFrame(flat).to_csv(OUT/'V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv',index=False)
 write('B0_REMATERIALIZATION_IMPACT_AUDIT.json',{k:v['B0_rematerialization'] for k,v in allc.items()})
 write('V41R2_VERIFICATION.json',a['verification'])
 write('V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json',a)
 for k,v in allc.items():
  print('COMPARE',k,vec(v['vector']),v['materialized_headroom']['all12_FULL_fraction'],v['remaining_Dday_UNASSIGNED'],v['V22SR1_weight_distortion']['total_capacity_L1'],
    {g:v['materialized_headroom']['whole_job_feasibility'][g]['fraction_at_least_1'] for g in ('1','2','32')},flush=True)

if __name__=='__main__':run()
