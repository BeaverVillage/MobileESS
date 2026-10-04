"""Read-only continuity and cumulative native-budget checks; no solver imports."""
import json,hashlib,math
from pathlib import Path
ROOT=Path.cwd(); OUT=ROOT/'docs/v42_m1_dw_accelerated_root_integration'
def read(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def write(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
def union(rows):
 rows=sorted(rows);total=0.;start=end=None
 for a,b in rows:
  assert b>=a
  if start is None:start,end=a,b
  elif a<=end:end=max(end,b)
  else:total+=end-start;start,end=a,b
 return total+(end-start if start is not None else 0.)
old=read('PRE_RESUME_DW_CHECKPOINT_LATEST.json');new=read('DW_CHECKPOINT_LATEST.json');r=read('DW_ACCELERATED_FINAL_RESULT.json');b=read('DW_OPTIMIZE_INTERVALS.json');prior=read('PRE_RESUME_DW_OPTIMIZE_INTERVALS.json')
assert new['type']=='TERMINAL' and new['pool'][:len(old['pool'])]==old['pool']
for key in ['rmps','prices','columns']:
 assert new['restart_state'][key][:len(old['restart_state'][key])]==old['restart_state'][key],key
assert new['feature_selection_SHA']==old['feature_selection_SHA']==hashlib.sha256((OUT/'DW_RUNTIME_FEATURE_SELECTION.json').read_bytes()).hexdigest()
assert new['arc_floor']==old['arc_floor'] and new['threshold_authority']==old['threshold_authority']
assert abs(union(prior['intervals'])-prior['union_seconds'])<1e-8
assert b['budget_carried']==prior['union_seconds']==old['elapsed_budget']
calculated=b['budget_carried']+union(b['intervals']);assert abs(calculated-b['union_seconds'])<1e-8 and calculated==r['total_optimize_wall_union']<=1800
assert not (OUT/'DW_INFLIGHT.json').exists()
optimal={p['dual_SHA'] for p in new['restart_state']['rmps'] if p['status']==2}
for c in new['restart_state']['certs']:
 assert c['dual_SHA'] in optimal
 for name in c['pricing_receipts']:
  p=read(name);assert p['type']=='FINAL_CERTIFICATION' and p['dual_SHA']==p['true_dual_SHA']==c['dual_SHA']
  if c['certified']:assert p['native_status'] in (2,9) and p['valid_bound'] and math.isfinite(p['ObjBound'])
assert read('DW_FULL_POOL_FINAL_AUDIT.json')['PASS']
resources=[old['resource_usage'],new['resource_usage']]
summary=dict(peak_tree_RSS=max(x['observed_total_tree_peak_RSS'] for x in resources),min_available_RAM=min(x['min_available_RAM'] for x in resources),max_commit_percent=max(x['max_commit_percent'] for x in resources),separate_canary_resource_failure_excluded=True,segments=resources)
write('DW_CG_CUMULATIVE_RESOURCE_SUMMARY.json',summary)
write('DW_RESUME_CONTINUITY_VERIFICATION.json',dict(PASS=True,restored_columns=len(old['pool']),previous_completed_OPTIMAL_RMPs=sum(p['status']==2 for p in old['restart_state']['rmps']),preserved_pricing_receipts=len(old['restart_state']['prices']),preserved_validated_new_columns=len(old['new_columns']),completed_native_receipts_replayed=0,accepted_column_pool_preserved=True,feature_selection_SHA=new['feature_selection_SHA'],prior_optimize=prior['union_seconds'],resumed_optimize=union(b['intervals']),cumulative_optimize=calculated,remaining=1800-calculated,one1800_grant=True,incomplete_call_dual_used_in_certificate=False,full_pool_columns=len(new['pool'])))
print('SAVED_RESUME_CONTINUITY_PASS',len(new['pool']),calculated,flush=True)
