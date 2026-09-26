from experiment import *

def main():
 source=read('SOURCE_MANIFEST.json')
 for n,h in source['hashes'].items():require(sha(BASE/n)==h,'ORIGINAL_EVIDENCE_CHANGED '+n)
 amendment=read('OPERATIONAL_AMENDMENT.json')
 for n,h in read('CODE_FREEZE.json')['files'].items():
  if n=='experiment.py':
   require(sha(ROOT/'registration_sources'/n)==h,'REGISTERED_SOURCE_BACKUP_DRIFT')
   require(sha(ROOT/'operational_sources'/n)==amendment['amended_experiment_sha256'],'AMENDMENT_BACKUP_DRIFT')
   require(sha(ROOT/'timestamp_sources'/n)==read('TIMESTAMP_CORRECTION.json')['corrected_experiment_sha256'],'TIMESTAMP_SOURCE_DRIFT')
   require(sha(ROOT/n)==read('CALIBRATION_SUPPORT_AMENDMENT.json')['corrected_experiment_sha256'],'SUPPORT_AMENDMENT_DRIFT')
  else:require(sha(ROOT/n)==h,'REGISTERED_CODE_DRIFT '+n)
 for n,h in read('FINAL_SELECTION_FREEZE.json')['code_hashes'].items():require(sha(ROOT/n)==h,'FINAL_CODE_DRIFT '+n)
 count=0;mar_apr=[]
 for p in (ROOT/'fits').glob('*/*/MEMBERSHIP.json'):
  r=json.loads(p.read_text(encoding='utf-8'));cut=pd.Timestamp(r['cutoff']);tr=np.flatnonzero(np.isin(DAYS,r['train_days']))
  require(DAYS[tr].tolist()==r['train_days'],'MEMBERSHIP_ORDER');require((AV.iloc[tr]<cut).all(),'IMMATURE_LABEL')
  require(np.array_equal(tr,membership(r['policy'],cut)),'MEMBERSHIP_POLICY')
  if p.parent.name>='2025-05-01' and r['policy']!='fixed':require(r['Mar_Apr_2025_days']>0,'LATEST_HISTORY_MISSING');mar_apr.append(r['Mar_Apr_2025_days'])
  count+=1
 for p in (ROOT/'calibration').glob('*.json'):
  for r in json.loads(p.read_text(encoding='utf-8')):
   ix=np.flatnonzero(np.isin(DAYS,r['source_days']));require((AV.iloc[ix]<pd.Timestamp(r['issue_time'])).all(),'RESIDUAL_LEAK')
 for r in read('IDENTICAL_COMPONENT_CACHE_REUSE.json'):
  for name,digest in r['files'].items():
   require(sha(ROOT/r['source']/name)==digest and sha(ROOT/r['target']/name)==digest,'CACHE_REUSE_DRIFT')
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');require(np.isfinite(f[['actual_GPUh','Q50','Q90']]).all().all(),'NONFINITE');require((f.Q90>=f.Q50).all() and (f.Q50>=0).all(),'SUPPORT')
 for (split,tag,variant),g in f.groupby(['split','tag','variant']):
  expected=DAYS[(L.split.eq(split)&L.eligible).to_numpy()];require(sorted(g.target_day.unique())==list(expected),'EVAL_EXCLUSION');require(len(g)==24*len(expected),'DUPLICATE_EVAL')
 dump('VALIDATION.json',dict(time=now(),PASS=True,fit_memberships=count,Mar_Apr_days_min=min(mar_apr),Mar_Apr_days_max=max(mar_apr),
   prediction_rows=len(f),source_unchanged=True,code_unchanged=True,causality=True,production_changed=False,grid_executions=0))
 print('VALIDATION PASS',count,len(f),flush=True)

if __name__=='__main__':main()
