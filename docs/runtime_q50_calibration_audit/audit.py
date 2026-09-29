"""Pure arithmetic over SHA-verified PR94 VALID arrays; no inference or fitting imports."""
from common import *

def pareto(x):
    x=np.asarray(x,float)
    return [not any(np.all(other<=row) and np.any(other<row) for other in x) for row in x]

def main():
    assert sha(ROOT/'PREREGISTRATION.json')==read(ROOT/'PREREGISTRATION_HASH.json')['sha256']
    for r in read(ROOT/'IMPLEMENTATION_FREEZE.json')['files']:assert sha(r['path'])==r['sha256']
    published={r['relative']:r for r in read(PR94/'DELIVERY_MANIFEST.json')['files']}
    for name,r in published.items():assert sha(PR94/name)==r['sha256'],name
    local={r['path']:r for r in read(PR94/'LOCAL_EVIDENCE_MANIFEST.json')['files']}
    old=read(PR94/'BASE_PRESERVATION_RECEIPT.json')
    tracked=old['tracked_files']+[dict(relative=(PR94/name).relative_to(REPO).as_posix(),bytes=r['bytes'],sha256=r['sha256']) for name,r in published.items()]
    tracked.append(dict(relative=(PR94/'DELIVERY_MANIFEST.json').relative_to(REPO).as_posix(),bytes=(PR94/'DELIVERY_MANIFEST.json').stat().st_size,sha256=sha(PR94/'DELIVERY_MANIFEST.json')))
    loc=old['local_inputs']+list(local.values())
    for r in tracked:assert sha(REPO/r['relative'])==r['sha256'],r
    for r in loc:assert sha(r['path'])==r['sha256'],r
    write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,tracked_files=tracked,local_files=loc,old_sources_unchanged=True))
    original=pd.read_csv(PR94/'FINAL_RUNTIME_MODEL_COMPARISON.csv',float_precision='round_trip').set_index('Model')
    oldratio=pd.read_csv(PR94/'PER_JOB_RATIO_DISTRIBUTION.csv',float_precision='round_trip')
    oldfold=pd.read_csv(PR94/'RUNTIME_TIME_RATIO_METRICS.csv',float_precision='round_trip')
    mem=pd.read_csv(PR94/'COMMON_RUNTIME_MEMBERSHIP.csv',dtype={'job_id':str})
    assert len(mem)==230237 and not mem[['fold','job_id']].duplicated().any()
    oldmembership=read(PR94/'COMMON_RUNTIME_POPULATION_AUDIT.json')
    sources=[rec(PR94/n) for n in ['DELIVERY_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json','FINAL_RUNTIME_MODEL_COMPARISON.csv','PER_JOB_RATIO_DISTRIBUTION.csv','RUNTIME_TIME_RATIO_METRICS.csv','COMMON_RUNTIME_MEMBERSHIP.csv','COMMON_RUNTIME_POPULATION_AUDIT.json','FINAL_SELECTION_FREEZE.json','FINAL_FLAGS.json']]
    assert read(PR94/'FINAL_FLAGS.json')['SELECTED_RUNTIME_MODEL']=='NONE' and read(PR94/'FINAL_FLAGS.json')['SELECTED_ALPHA'] is None
    pooled=[];folds=[];buckets=[];tails=[];distributions=[];summary=[];receipts=[];reproduction=[]
    for arm in ARMS:
        parts=[];fr=[]
        for i in range(1,6):
            p=PR94/'.local'/f'{arm}_fold{i}_VALID.parquet';r=local[str(p)];assert sha(p)==r['sha256'];sources.append(rec(p))
            f=pd.read_parquet(p);assert list(f.columns)==['fold','job_id','submit_time','runtime_seconds','q50','q90']
            assert f.fold.eq(i).all() and not f.job_id.duplicated().any()
            expected=mem[mem.fold==i].set_index('job_id').loc[f.job_id]
            assert set(f.job_id)==set(mem[mem.fold==i].job_id)
            np.testing.assert_array_equal(f.runtime_seconds,expected.runtime_seconds)
            np.testing.assert_array_equal(f.submit_time,pd.to_datetime(expected.submit_time,utc=True))
            assert ids(f)==oldmembership['folds'][i-1]['membership']
            assert np.isfinite(f[['runtime_seconds','q50','q90']]).all().all() and (f.runtime_seconds>=0).all() and (f.q50>=0).all() and (f.q90>=f.q50).all()
            s=dict(Model=arm,fold=i,**metrics(f));z=f[f.runtime_seconds>43200];s['GT12H_Q50_coverage']=metrics(z)['Q50_coverage']
            prior=oldfold[(oldfold.Model==arm)&(oldfold.fold==str(i))].iloc[0]
            assert s['Q50_time_ratio']==prior.TIME_RATIO_Q50
            folds.append(s);fr.append(s);parts.append(f)
            receipts.append(dict(Model=arm,fold=i,N=len(f),membership=ids(f),source_sha256=r['sha256'],prediction_bytes_unchanged=True))
        f=pd.concat(parts,ignore_index=True);m=metrics(f);rr=ratios(f);old=original.loc[arm]
        assert len(f)==230237 and m['zero_runtime_N']==1290
        for field,prev in [('Q50_MAE_seconds','Q50_MAE_seconds'),('Q50_MAE_hours','Q50_MAE_hours'),('Q50_time_ratio','TIME_RATIO_Q50'),('Raw_Q90_coverage','Q90_coverage')]:
            assert m[field]==old[prev],(arm,field,m[field],old[prev])
        past=oldratio[(oldratio.Model==arm)&(oldratio.fold=='POOLED')&(oldratio['quantile']=='q50')].iloc[0]
        assert rr['median']==past['median']
        s=dict(Model=arm,**m,Q50_per_job_ratio_median=rr['median'],min_fold_Q50_coverage=min(x['Q50_coverage'] for x in fr),max_fold_Q50_coverage=max(x['Q50_coverage'] for x in fr),fold_coverage_std=float(np.std([x['Q50_coverage'] for x in fr],ddof=0)),max_fold_calibration_error=max(x['Q50_calibration_error'] for x in fr),worst_calibration_fold=max(fr,key=lambda x:x['Q50_calibration_error'])['fold'],time_ratio_distance_from_one=abs(m['Q50_time_ratio']-1))
        for h in [4,12,24]:s[f'GT{h}H_Q50_coverage']=metrics(f[f.runtime_seconds>h*3600])['Q50_coverage']
        z=f[f.runtime_seconds>43200];s['GT12H_Raw_Q90_coverage']=metrics(z)['Raw_Q90_coverage'];assert s['GT12H_Raw_Q90_coverage']==old.GT12H_Q90_coverage
        summary.append(s);pooled.append(dict(Model=arm,**m));reproduction.append(dict(Model=arm,exact_float_reproduction=True,**{k:m[k] for k in ['Q50_MAE_seconds','Q50_MAE_hours','Q50_time_ratio','Raw_Q90_coverage']},GT12H_Raw_Q90_coverage=s['GT12H_Raw_Q90_coverage'],per_job_median=rr['median']))
        for fold,z in [('POOLED',f)]+[(i,f[f.fold==i]) for i in range(1,6)]:
            distributions.append(dict(Model=arm,fold=fold,**ratios(z)))
            for name,lo,hi in BUCKETS:
                zz=z[(z.runtime_seconds>lo)&(z.runtime_seconds<=hi)];buckets.append(dict(Model=arm,fold=fold,bucket=name,**metrics(zz)))
            buckets.append(dict(Model=arm,fold=fold,bucket='EXACT_ZERO_DIAGNOSTIC',**metrics(z[z.runtime_seconds==0])))
            for h in [4,12,24]:tails.append(dict(Model=arm,fold=fold,threshold_hours=h,**metrics(z[z.runtime_seconds>h*3600])))
    c=pd.DataFrame(summary);core=['Q50_MAE_hours','Q50_calibration_error','time_ratio_distance_from_one']
    c['pareto_core']=pareto(c[core]);c['pareto_with_stability']=pareto(c[core+['max_fold_calibration_error','fold_coverage_std']])
    # Nominal candidate decision is a separate transparent qualitative review, not a derived numerical gate.
    c['primary_nominal_candidate']=False
    c.to_csv(ROOT/'FINAL_Q50_COMPARISON.csv',index=False)
    csv('Q50_POOLED_METRICS.csv',pooled);csv('Q50_FOLD_METRICS.csv',folds);csv('Q50_RUNTIME_BUCKET_METRICS.csv',buckets);csv('Q50_LONG_RUNTIME_METRICS.csv',tails);csv('Q50_RATIO_DISTRIBUTION.csv',distributions)
    write('SOURCE_AUDIT.json',dict(time=now(),PASS=True,pr94_base=BASE,models=ARMS,reproduction=reproduction,prediction_source='Original PR94 VALID parquet bytes only; no inference, CAL use, fitting, or output modification.',prior_result_unchanged=True))
    write('COMMON_POPULATION_RECHECK.json',dict(time=now(),PASS=True,N=230237,zero_runtime_N=1290,positive_runtime_N=228947,membership_file=rec(PR94/'COMMON_RUNTIME_MEMBERSHIP.csv'),candidate_folds=receipts,source_manifest_hashes_verified=True,prediction_timestamps='Same stored submit-time proxies as PR94, no new immutable receipt claim.',same_labels_and_quantiles=True))
    write('SOURCE_MANIFEST.json',dict(time=now(),files=sources,read_scope='Existing pre-April PR94 VALID and published frozen reports/manifests only; historical evidence byte-hashed without opening new label populations.'))
    print(c[['Model','Q50_MAE_hours','Q50_coverage','Q50_time_ratio','min_fold_Q50_coverage','max_fold_Q50_coverage','GT12H_Q50_coverage','pareto_core','pareto_with_stability']].to_string(index=False),flush=True)
if __name__=='__main__':main()
