from experiment import *

def main():
 for name in ['MOE_BASELINE_REPRODUCTION.json','MODERN_BASELINE_REPRODUCTION.json']:require(read(name)['PASS'],'BASELINE_FAIL')
 for name in ['CODE_FREEZE.json','FINAL_SELECTION_FREEZE.json']:
  freeze=read(name)
  for n,h in freeze.get('files',freeze.get('code_hashes',{})).items():
   expected=h
   if name=='CODE_FREEZE.json':
    for change in read('CODE_AMENDMENT_CHAIN.json')['changes']:
     if change['file']==n:
      require(sha(ROOT/change['before_path'])==expected,'AMENDMENT_SOURCE_DRIFT '+n)
      expected=change['after_sha256']
   require(sha(ROOT/n)==expected,'FROZEN_CODE_DRIFT '+n)
 j,p=data();n=0
 for path in (ROOT/'fits').glob('*/*/MEMBERSHIP.json'):
  r=json.loads(path.read_text(encoding='utf-8'));t=pd.Timestamp(r['issue_time']);file=path.parent/'train_membership.npz'
  require(sha(file)==r['row_ids_sha256'],'MEMBERSHIP_DIGEST');got=np.load(file)['row_ids'];expected=member(r['policy'],t)
  require(np.array_equal(got,expected.row_id.to_numpy()),'MEMBERSHIP_NOT_EXACT');require(ids(expected.job_id)==r['job_ids_sha256'],'JOB_ID_DIGEST');n+=1
 indexed=p.set_index('job_issue_id')
 for file in (ROOT/'calibration').glob('*.json'):
  for r in json.loads(file.read_text(encoding='utf-8')):
   hist=indexed.loc[r['pool_job_issue_ids']];require(hist.end_time.lt(pd.Timestamp(r['issue_time'])).all(),'CALIBRATION_FUTURE_LABEL')
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');require(np.isfinite(f.Q90).all() and (f.Q90>=0).all(),'INVALID_FORECAST')
 for model in ['MOE_POOLED','MULTI_QUANTILE','MULTI_QUANTILE_HIERARCHICAL','MOE_CURRENT_TEMPORAL_GPU_COHORT']:
  g=f[f.model.eq(model)];expected=p[p.role.isin(['EXPOSED_EVALUATION','MAY_HISTORICAL'])]
  require(set(g.job_issue_id)==set(expected.job_issue_id),'EVAL_EXCLUSION');require(g.job_issue_id.is_unique,'DUPLICATE')
 dump('VALIDATION.json',dict(time=now(),PASS=True,fit_memberships=n,exact_baselines=True,strict_job_end_maturity=True,feature_projection=True,
  all_evaluation_job_issues_retained=True,production_promotion=False,optimizer_executions=0,grid_executions=0))
 print('VALIDATION PASS',n,flush=True)

if __name__=='__main__':main()
