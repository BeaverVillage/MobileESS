from pathlib import Path
import hashlib,json,time
import runtime_environment as env
ROOT=Path(__file__).parent
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def leaves(x):
 if isinstance(x,dict):
  if {'path','sha256','bytes'}<=x.keys():yield x
  for v in x.values():yield from leaves(v)
 elif isinstance(x,list):
  for v in x:yield from leaves(v)
def main():
 env.seed_aliases();rows=[];seen={};missing=[]
 freeze=read(ROOT/'M2_ROUND1_FINAL_BOUNDARY_FREEZE.json')
 assert len(freeze['days'])==31
 old=Path(r'D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
 for b in freeze['days']:
  day=b['day'];da=Path(b['input_joint']).parent
  assert sha(b['input_joint'])==b['file_SHA256']
  joint=read(b['input_joint']);assert joint['decision_SHA']==b['decision_SHA']
  receipt=read(da/'DAYAHEAD_RECEIPT.json');assert receipt['status']=='COMPLETE'
  coords=read(da/'PLANNING_RESULT.json')['stages']['COORDINATION']['counts']
  assert all(coords[k]==1 for k in ['MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS','AIDC_FEEDBACK_PASSES','FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS'])
  assert coords['SECOND_MESS_FULL_ROUTE_SEARCH_CALLS']==0
  refs=[]
  for p in [da/'GENERATION_INPUT_IDENTITY.json',da/'authority/INPUT_MANIFEST.json',da/'DAYAHEAD_RECEIPT.json']:
   refs+=list(leaves(read(p)))
  refs+=list(leaves(read(env.read_path(joint['decision']['electrical']['path'])))) if 'path' in joint['decision']['electrical'] else list(leaves(joint['decision']['electrical']))
  from authority_recovery import missing_leaf
  for r in refs:
   key=(r['path'],r['sha256'],r['bytes'])
   if key in seen:continue
   if missing_leaf(r):missing.append(r);continue
   p=Path(env.read_path(r['path']));assert p.is_file(),p
   assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'],('AUTHORITY_DRIFT',p)
   seen[key]=str(p)
  accepted=read(old/'frozen_artifacts/v41r4_restoration_revision_v1'/day/'B3/ACCEPTANCE.json')
  ac=old/('frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/replays' if accepted['actual_disposition']=='REUSE_ACTUAL' else 'frozen_artifacts/v41r4_selective_actual_revision_v1/replays')/day/'B3'
  assert read(ac/'COMPLETE.json')['status']=='PASS'
  a1=old/'frozen_artifacts/v41r4_may/loop_wall_v4'/day/'B1/dayahead/SEARCH_LOOP_WALL_CLOCK_AUDIT.json'
  a2=read(da/'SEARCH_LOOP_WALL_CLOCK_AUDIT.json')
  assert read(a1)['total_search_budget_seconds']==a2['total_search_budget_seconds']==1800
  rows.append(dict(day=day,final_joint=b,DA_receipt_sha256=sha(da/'DAYAHEAD_RECEIPT.json'),input_manifest_sha256=sha(da/'authority/INPUT_MANIFEST.json'),generation_sha256=sha(da/'GENERATION_INPUT_IDENTITY.json'),A1_budget=1800,A2_budget=1800,coordination=coords,Actual_complete_sha256=sha(ac/'COMPLETE.json'),Actual_root=str(ac),same_actual_method_sha256=sha(old/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/METHOD_FREEZE.json')))
  print('AUTHORITY',day,'PASS',flush=True)
 result=dict(status='PASS',dates=31,days=rows,verified_leaves=[dict(path=k[0],sha256=k[1],bytes=k[2],resolved_path=v) for k,v in seen.items()],documented_missing_historical_lineage=missing,baseline_optimizer_calls=0,verified_at=time.time())
 (ROOT/'AUTHORITY_VERIFIED.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print('AUTHORITY_PASS',len(seen))
if __name__=='__main__':main()
