import sys,time,json,pickle,gzip,cProfile,pstats
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v42_may_campaign_native90.common import atomic,read,record,now
from v42_may_campaign_native90.preflight import native_zero
from v42_may_campaign_native90.a_stage import prepare,verify_case
from v42_may_campaign_native90.build_reuse import CheckpointMemo,checkpoint_memo,domain_hash
from v42_a_stage_domain_v2.domain import physical_starts,physical_domain
from v42_a_stage_domain_v2.fast_census import load_physical_cache
import v42_job_capability as cp
old=Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01')
root=Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01')
root.mkdir(exist_ok=True);checks=root/'validation';checks.mkdir(exist_ok=True)
source=old/'preflight_cases/B1/2025-05-01_attempt2'
with (source/'STATIC/DATA/DATA.pkl').open('rb') as f:data=pickle.load(f)
memo=CheckpointMemo(cp.checkpoint_records);count=0;records=0;start=time.perf_counter()
for uid,job in data[1].items():
 for s in physical_starts(job,data[2][uid],data[3].control_end):
  for end in set((s+job.service_slots,min(s+job.service_slots,data[3].control_end))):
   original=cp.checkpoint_records(job,s,end)
   assert original==memo(job,s,end)==memo(replace(job,uid='DIFFERENT_UID'),s,end)
   count+=1;records+=len(original)
atomic(checks/'CHECKPOINT_COMPLETE_EQUIVALENCE.json',dict(PASS=True,job_count=len(data[1]),conditions=count,
    full_records=records,wall_seconds=time.perf_counter()-start,Native_calls=0,memo=memo.report(),input=record(source/'STATIC/DATA/DATA.pkl')))
request=dict(root=str(root),input_authority_root=str(old),day='2025-05-01',arm='B1',
    input_folder=str(old/'inputs/B1/2025-05-01'),output=str(root/'preflight_cases/B1/2025-05-01'),
    _current_date_physical_cache=str(source))
def progress(value):atomic(checks/'BUILD_PROGRESS.json',dict(value,timestamp_UTC=now()))
start=time.perf_counter()
if '--resume-validation' in sys.argv:
 receipt=read(Path(request['output'])/'A_PREPARE_RECEIPT.json')
 assert record(receipt['state']['path'])==receipt['state']
 with gzip.open(receipt['state']['path'],'rb') as f:state=pickle.load(f)
 with native_zero() as denied:verification=verify_case(state)
 elapsed=receipt['preparation_wall_seconds']
else:
 with native_zero() as denied:
  state=prepare(request,progress)
  verification=verify_case(state)
 elapsed=time.perf_counter()-start
baseline=read(old/'preflight_receipts/B1/2025-05-01.json')['case_verification']
assert verification==baseline and not denied
old_blocks=read(source/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
new_blocks=read(Path(request['output'])/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
byclass={r['class_id']:r for r in old_blocks};equivalent=[]
for row in new_blocks:
 prior=byclass[row['class_id']]
 with gzip.open(row['external_full_block_cache']['path'],'rb') as f:new=pickle.load(f)
 with gzip.open(prior['external_full_block_cache']['path'],'rb') as f:previous=pickle.load(f)
 assert new['snapshot'].fingerprint()==previous['snapshot'].fingerprint()
 import numpy as np
 assert np.array_equal(new['constant'],previous['constant']) and (new['B']!=previous['B']).nnz==0
 def equal(a,b):
  if isinstance(a,np.ndarray):return isinstance(b,np.ndarray) and a.dtype==b.dtype and np.array_equal(a,b,equal_nan=True) if np.issubdtype(a.dtype,np.number) else isinstance(b,np.ndarray) and a.dtype==b.dtype and np.array_equal(a,b)
  if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
  if isinstance(a,(tuple,list)):return type(a)==type(b) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
  if hasattr(a,'__dict__'):return type(a)==type(b) and equal(vars(a),vars(b))
  return a==b
 from v42_a_stage_domain_v2.domain import graph_content_hash
 assert equal(new['units'],previous['units']) and graph_content_hash(new['graph'])==graph_content_hash(previous['graph'])
 equivalent.append(dict(class_id=row['class_id'],snapshot_SHA=new['snapshot'].fingerprint(),PASS=True))
cache=read(Path(request['output'])/'CURRENT_DATE_PHYSICAL_CACHE_REUSE.json')
atomic(checks/'BUILD_MODEL_EQUIVALENCE.json',dict(PASS=True,Native_calls=0,verification=verification,
    construction_seconds=elapsed,cache_hit=cache['cache_hit'],complete_domain_hashes=cache['recalculated_complete_domain_hashes'],
    full_blocks=equivalent,reference_matrix_objective_RHS_bounds_types_identical=True,
    old_cached_model_build_seconds=540.4632838999969,old_uncached_worker_not_complete=True,UTC=now()))
print('MODEL_EQUIVALENCE_PASS',elapsed,flush=True)
# Independently time unchanged original physical_domain and the memo route for
# the exact class observed in the stopped Worker, with fresh Generators each.
key='d807aefaf249be3b75afc5b2fa9d9707ead785fad79f88e5b4bd7441175fb26d';uid=data[7]['classes'][key][0]
job,bound,resources=data[1][uid],data[2][uid],data[3]
profiles=[];outputs=[]
for cached in (False,True):
 profile=cProfile.Profile();begin=time.perf_counter()
 if cached:
  with checkpoint_memo() as exact:
   profile.enable();domain=physical_domain(job,bound,resources);profile.disable();memo_stats=exact.report()
 else:
  profile.enable();domain=physical_domain(job,bound,resources);profile.disable();memo_stats=None
 duration=time.perf_counter()-begin;outputs.append(domain)
 profile.dump_stats(str(checks/('physical_memo.prof' if cached else 'physical_original.prof')))
 stats=pstats.Stats(profile)
 cp_rows=[dict(function=str(k),calls=v[1],self_seconds=v[2],cumulative_seconds=v[3])
     for k,v in stats.stats.items() if k[2]=='checkpoint_records']
 profiles.append(dict(memo=cached,uid=uid,class_id=key,seconds=duration,checkpoint=cp_rows,memo_stats=memo_stats))
assert outputs[0].stays==outputs[1].stays and outputs[0].blocks==outputs[1].blocks
assert domain_hash(job,bound,outputs[0])==domain_hash(job,bound,outputs[1])==state['domains'][uid].sha
atomic(checks/'CHECKPOINT_INDEPENDENT_PROFILE.json',dict(PASS=True,Native_calls=0,profiles=profiles,
    exact_same_job_start_site_and_full_domain=True,Domain_SHA=outputs[0].sha,job_start_site_counts=dict(starts=len(physical_starts(job,bound)),sites=len(job.initial_sites))))
print('PHYSICAL_PROFILE_PASS',profiles,flush=True)
