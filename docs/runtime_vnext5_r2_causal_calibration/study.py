"""Frozen PR71 R2 Q90 with strictly prior mature OOS residual calibration only."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,platform,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'runtime_vnext4_gpu_censored_running';BASE=ROOT.parent/'runtime_vnext_causal_tail'
spec=importlib.util.spec_from_file_location('readonly_vnext2',ROOT.parent/'runtime_vnext2_q95_operational_bound/study.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
PRE=['DEVELOPMENT','CALIBRATION'];EVAL=['EXPOSED_EVALUATION','MAY_HISTORICAL'];ARMS=['R1','R2','R3'];MIN_SUPPORT=100;TAU=.9;PINBALL_MARGIN=1.02
SEED=20260927;DRAWS=2000
COLS=['row_id','job_id','job_issue_id','issue_time','role','state','elapsed_seconds','submit_time','requested_seconds','num_gpus_req','partition','qos','Q90']
METRICS=['coverage','GPU_coverage','long_under','missed_GPU_slots','overreserved_GPUh','reserved_GPUh','reserve_vs_requested','pinball_Q90','MAE_bound_seconds','overreserve_vs_requested','missed_slots_reduction']
def need(ok,message):
    if not ok:raise AssertionError(message)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def now():return pd.Timestamp.now(tz='UTC').isoformat()
def save(name,value):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))
def code():return {n:sha(ROOT/n) for n in ['study.py','test_contract.py']}
def guard():need(code()==read(ROOT/'REGISTRATION.json')['code'],'FROZEN_CODE_DRIFT')
def preserve(name):
    records=[]
    for n in ['runtime_vnext_causal_tail','runtime_vnext2_q95_operational_bound','runtime_vnext3_adaptive_running_bound','runtime_vnext4_gpu_censored_running']:
        folder=ROOT.parent/n;manifest=read(folder/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:need(sha(folder/r['path'])==r['sha256'],'PARENT_DRIFT '+n+'/'+r['path'])
        records.append(dict(parent=n,N=len(manifest['files']),manifest_sha256=sha(folder/'DELIVERY_MANIFEST.json')))
    save(name,dict(time=now(),PASS=True,parents=records))
def prepare():
    need(not (ROOT/'SOURCE_FORECASTS.parquet').exists(),'ALREADY_PREPARED');preserve('PARENT_PRESERVATION_START.json')
    jobs=pd.read_parquet(BASE/'JOB_MEMBERSHIP.parquet');issue=pd.read_csv(BASE/'ISSUES.csv');parts=[];audit=[]
    for row in issue[issue.role.ne('TRAIN')].itertuples():
        t=pd.Timestamp(row.issue_time);key=t.strftime('%Y%m%dT%H%M');folder=PARENT/'fits/R2'/key;receipt=read(folder/'RECEIPT.json');path=PARENT/'predictions/R2'/(key+'.parquet')
        need(sha(path)==receipt['prediction_sha256'],'FROZEN_RAW_DRIFT')
        ids=np.load(folder/'ROW_IDS.npz')['row_id'];proof=read(folder/'PORTABLE_MEMBERSHIP.json');need(sha(folder/'ROW_IDS.npz')==proof['ordered_row_ids_sha256'],'TRAINING_MEMBERSHIP_DRIFT')
        train=jobs.set_index('row_id').loc[ids];need(train.end_time.lt(t).all(),'RAW_MODEL_LABEL_NOT_MATURE')
        pre=read(BASE/'fits/LGBM_180_14'/key/'RUNNING/preprocessing.json');need(pd.Timestamp(pre['latest_end'])<t,'PREPROCESSOR_NOT_MATURE')
        f=pd.read_parquet(path)[COLS].copy();need(f.state.eq('RUNNING').all() and f.role.eq(row.role).all() and f.issue_time.eq(t).all(),'RAW_SOURCE_ROLE')
        f=f.merge(jobs[['row_id','start_time','end_time','label_valid']],on='row_id',validate='many_to_one')
        need(f.submit_time.le(t).all() and f.start_time.le(t).all() and f.end_time.gt(t).all(),'SOURCE_NOT_RUNNING')
        need(np.array_equal(f.elapsed_seconds,(t-f.start_time).dt.total_seconds()),'SOURCE_ELAPSED')
        f=f.rename(columns={'Q90':'raw_Q90'});parts.append(f)
        audit.append(dict(issue_time=t,role=row.role,query_N=len(f),training_N=len(ids),latest_training_end=train.end_time.max(),latest_preprocessing_end=pre['latest_end'],source_prediction_sha256=sha(path),source_receipt_sha256=sha(folder/'RECEIPT.json'),training_membership_sha256=sha(folder/'ROW_IDS.npz')))
    f=pd.concat(parts,ignore_index=True);need(f.job_issue_id.is_unique,'SOURCE_DUPLICATE');f.to_parquet(ROOT/'SOURCE_FORECASTS.parquet',index=False)
    pd.DataFrame(audit).to_csv(ROOT/'SOURCE_MODEL_MATURITY_AUDIT.csv',index=False)
    issue['new_calibration_issue']=issue.role.ne('TRAIN');issue['new_model_fit']=False;issue.to_csv(ROOT/'EXACT_SPLITS.csv',index=False)
    save('PREPARATION.json',dict(time=now(),base_commit='1702abdd14db3ad6e5a63211459b9b99d6a8a054',source_forecasts_sha256=sha(ROOT/'SOURCE_FORECASTS.parquet'),source_rows=len(f),issues=len(audit),source_model_maturity_PASS=True,source_query_state_PASS=True,TRAIN_R2_forecasts_available=False,model_fits=0,request_proxy='D1_SCHEDULER_REQUEST_STATE_PROXY_V1',provenance='UNVERIFIED/UNOBSERVED',operational_feature_availability_certified=False,May='previously exposed historical diagnostic'))
    print('PREPARATION_PASS',len(audit),len(f),flush=True)
def register():
    need((ROOT/'PREPARATION.json').exists(),'PREPARE_FIRST')
    save('REGISTRATION.json',dict(time=now(),code=code(),source_forecasts_sha256=sha(ROOT/'SOURCE_FORECASTS.parquet'),base_PR=71,
        R0='current frozen production Q90; authoritative May only, Running total-minus-elapsed transport',R1='exact PR71 R2 raw elapsed-conditioned Q90',R2='global empirical one-sided residual Q90 correction',R3='GPU-weighted empirical one-sided residual Q90 correction',Pending='exact R0 unchanged in all arms; unavailable DEV/CAL/April is not replayed backwards',
        base_model_policy='frozen PR71 R2; no model/feature/temporal changes or fits; no Q95/AFT/selector search',calibration_history='expanding available frozen OOS forecast history; separate from unchanged base training temporal policy',
        eligibility='source forecast issue < current issue AND job_end < current issue AND valid finite remaining outcome; filter before dedup',residual='job_end - SOURCE forecast issue - SOURCE raw Q90, in seconds; never end-currentissue for historical residual',dedup='latest eligible source forecast per Job; stable tie-break by job_issue_id; one Job one residual per calibration pool',minimum_distinct_mature_Jobs=MIN_SUPPORT,fallback='if support<100, delta=0 on every current query, retain all fallback rows in metrics',
        quantile='inverse empirical CDF at .90: first residual with cumulative positive weight >= .90*total; no interpolation; unweighted rank ceil(.90*N), NOT conformal ceil(.90*(N+1))',global_weights='1 per distinct Job',GPU_weights='source requested GPU count, finite and strictly positive; user-authorized proxy',correction='max(0, empirical residual quantile); bound=rawQ90+correction; no scaling/capping',finite_sample_coverage_guarantee=False,
        selection='R2/R3 must BOTH DEV and CAL meet coverage>=.90,GPUcoverage>=.90,longtotal>4hunder<=.15 and Q90pinball<=1.02*raw. Prefer overreserve<=requested-overreserve in BOTH roles; then lowest mean role reserved/requested ratio, then arm ID. If none retain raw R1. R0 unavailable beforeevaluation.',pinball_ratio_limit=PINBALL_MARGIN,
        support_verdict='True only if preselected R2/R3 meets same hard safety/pinball gates in BOTH diagnostic roles and paired7issue missed-slot delta upper95CI<0 vs rawR1 in BOTH roles, plus vsR0 onMay. Reserve is PREFERRED and reported separately, not a hard calibration-support gate. OtherwiseFalse.',
        reserve_algebra='nonnegative correction implies pointwise overreserve/reserve cannot decrease from raw for ANY fixedcohort; calibration is not a mechanism for reducing inherited reserve excess',scope_correction='Before registration or DEV metrics, proposal clarified to honor user reserve PREFERRED hierarchy; no reserve hardgate added to calibration-support verdict',
        uncertainty=dict(draws=DRAWS,seed=SEED,blocks=[1,7],unit='paired observed-issue-day circularblocks; all nonlinear ratios recomputed per draw'),May='already-exposed historical diagnostic, never untouched confirmation',request_proxy='D1_SCHEDULER_REQUEST_STATE_PROXY_V1; UNVERIFIED/UNOBSERVED; no historical exactness/immutability/census claim',TEMPORAL_POLICY_CHANGED=False,NEW_MODEL_SEARCHED=False,PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False,optimizer_executions=0,grid_executions=0))
    save('ENVIRONMENT.json',dict(time=now(),python=platform.python_version(),executable=sys.executable,numpy=np.__version__,pandas=pd.__version__,model_training_executions=0))
    print('REGISTERED BEFORE DEV METRICS',flush=True)
def sources():
    need(sha(ROOT/'SOURCE_FORECASTS.parquet')==read(ROOT/'REGISTRATION.json')['source_forecasts_sha256'],'SOURCE_FORECAST_DRIFT');return pd.read_parquet(ROOT/'SOURCE_FORECASTS.parquet')
def pool_at(catalog,issue):
    t=pd.Timestamp(issue)
    f=catalog[catalog.issue_time.lt(t)&catalog.end_time.lt(t)&catalog.label_valid].copy()
    eligible=len(f);f=f.sort_values(['job_id','issue_time','job_issue_id'],kind='stable').drop_duplicates('job_id',keep='last').sort_values('job_id',kind='stable').copy()
    f['residual_seconds']=(f.end_time-f.issue_time).dt.total_seconds()-f.raw_Q90
    need(np.isfinite(f.residual_seconds).all(),'NONFINITE_MATURE_RESIDUAL');need(np.isfinite(f.num_gpus_req).all() and f.num_gpus_req.gt(0).all(),'INVALID_GPU_WEIGHT')
    return f,eligible
def inverse_ecdf(values,weights):
    values=np.asarray(values,float);weights=np.asarray(weights,float)
    need(len(values)>0 and len(values)==len(weights),'EMPTY_QUANTILE')
    need(np.isfinite(values).all() and np.isfinite(weights).all() and (weights>0).all(),'INVALID_QUANTILE_INPUT')
    need(np.isfinite(np.sum(weights)),'NONFINITE_TOTAL_WEIGHT')
    ix=np.argsort(values,kind='stable');values=values[ix];weights=weights[ix];k=np.searchsorted(np.cumsum(weights),TAU*np.sum(weights),side='left')
    return float(values[k])
def corrections(pool):
    if len(pool)<MIN_SUPPORT:return {'R1':0.,'R2':0.,'R3':0.}
    return {'R1':0.,'R2':max(0.,inverse_ecdf(pool.residual_seconds,np.ones(len(pool)))),'R3':max(0.,inverse_ecdf(pool.residual_seconds,pool.num_gpus_req))}
def apply_roles(roles):
    guard();catalog=sources();parts=[]
    for (t,role),q in catalog[catalog.role.isin(roles)].groupby(['issue_time','role'],sort=True):
        p,eligible=pool_at(catalog,t);need(not (set(p.job_id)&set(q.job_id)),'CURRENT_QUERY_JOB_IN_RESIDUAL_POOL');delta=corrections(p);key=t.strftime('%Y%m%dT%H%M');folder=ROOT/'calibration'/key;folder.mkdir(parents=True,exist_ok=True)
        membership=p[['job_id','row_id','job_issue_id','issue_time','end_time','elapsed_seconds','raw_Q90','num_gpus_req','residual_seconds']].rename(columns={'issue_time':'source_issue_time','job_issue_id':'source_job_issue_id'})
        membership.to_parquet(folder/'MEMBERSHIP.parquet',index=False)
        weights=p.num_gpus_req.to_numpy();receipt=dict(time=now(),issue_time=t,role=role,eligible_forecast_rows=eligible,distinct_mature_Jobs=len(p),duplicate_source_forecasts_removed=eligible-len(p),prior_source_issue_count=p.issue_time.nunique(),latest_source_issue=p.issue_time.max() if len(p) else None,latest_mature_end=p.end_time.max() if len(p) else None,support_fallback=len(p)<MIN_SUPPORT,correction_seconds=delta,GPU_weight_sum=float(weights.sum()),GPU_weight_ESS=float(weights.sum()**2/(weights@weights)) if len(p) else None,membership_sha256=sha(folder/'MEMBERSHIP.parquet'))
        save(folder.relative_to(ROOT)/'RECEIPT.json',receipt)
        for arm in ARMS:
            z=q.copy();z['arm']=arm;z['correction_seconds']=delta[arm];z['bound_seconds']=z.raw_Q90+delta[arm];z['nominal_quantile']=.9;z['support_fallback']=len(p)<MIN_SUPPORT
            z['runtime_seconds']=(z.end_time-z.start_time).dt.total_seconds();z['actual_seconds']=(z.end_time-z.issue_time).dt.total_seconds();z['actual_seconds']=z.actual_seconds.where(z.label_valid)
            need((z.bound_seconds>=z.raw_Q90).all(),'NON_ONE_SIDED_BOUND');parts.append(z)
    return pd.concat(parts,ignore_index=True)
def stats(f):
    m=old.stats(f);m.pop('pinball_Q95');g=f[f.actual_seconds.notna()];m['MAE_bound_seconds']=float(abs(g.actual_seconds-g.bound_seconds).mean());return m
def metrics(f):return pd.DataFrame([dict(role=r,arm=a,state=s,**stats(g)) for (r,a,s),g in f.groupby(['role','arm','state'])])
def choose(table):
    options=[]
    for arm in ['R2','R3']:
        a=table[table.arm.eq(arm)].sort_values('role');raw=table[table.arm.eq('R1')].sort_values('role')
        need(set(a.role)==set(PRE) and np.array_equal(a.role,raw.role),'SELECTION_ROLES')
        finite_columns=['coverage','GPU_coverage','long_under','pinball_Q90','reserve_vs_requested','overreserved_GPUh','requested_overreserved_GPUh']
        need(np.isfinite(a[finite_columns]).all().all() and np.isfinite(raw[finite_columns]).all().all(),'INVALID_SELECTION_METRIC')
        safe=bool((a.coverage>=.9).all() and (a.GPU_coverage>=.9).all() and (a.long_under<=.15).all());loss=bool((a.pinball_Q90.to_numpy()<=PINBALL_MARGIN*raw.pinball_Q90.to_numpy()).all());reserve=bool((a.overreserved_GPUh<=a.requested_overreserved_GPUh).all())
        options.append(dict(arm=arm,safety_pass=safe,pinball_margin_pass=loss,eligible=safe and loss,reserve_preferred_pass=reserve,mean_role_reserve_ratio=float(a.reserve_vs_requested.mean())))
    eligible=[r for r in options if r['eligible']];selected=min(eligible,key=lambda r:(not r['reserve_preferred_pass'],r['mean_role_reserve_ratio'],r['arm']))['arm'] if eligible else 'R1'
    return selected,options
def development():
    guard();f=apply_roles(PRE);f.to_parquet(ROOT/'DEV_CAL_PREDICTIONS.parquet',index=False);m=metrics(f);m.to_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv',index=False);selected,options=choose(m)
    save('FINAL_SELECTION_FREEZE.json',dict(time=now(),selected_running=selected,Pending='R0 exact',options=options,code=code(),registration_sha256=sha(ROOT/'REGISTRATION.json'),metrics_sha256=sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv'),DEV_CAL_predictions_sha256=sha(ROOT/'DEV_CAL_PREDICTIONS.parquet'),new_evaluation_metrics_computed=False,May_already_exposed=True))
    print('FINAL_SELECTION_FREEZE',selected,options,flush=True)
def vector(f):return np.r_[old.daily_values(f),abs(f.actual_seconds-f.bound_seconds).sum()]
def summarize(v):
    s=old.summarize(v[:13]);s['MAE_bound_seconds']=v[13]/v[0];return s
def paired(a,b,block):
    a=a.sort_values('job_issue_id');b=b.sort_values('job_issue_id');need(a.job_issue_id.is_unique and np.array_equal(a.job_issue_id,b.job_issue_id),'UNPAIRED_COHORT')
    need(np.array_equal(a.actual_seconds,b.actual_seconds,equal_nan=True),'PAIRED_OUTCOME_MISMATCH')
    a=a[a.actual_seconds.notna()];b=b[b.actual_seconds.notna()];va=np.array([vector(g) for _,g in a.groupby('issue_time',sort=True)]);vb=np.array([vector(g) for _,g in b.groupby('issue_time',sort=True)]);n=len(va)
    def effect(ix):
        x,y=summarize(va[ix].sum(0)),summarize(vb[ix].sum(0));return [x[k]-y[k] for k in METRICS[:-1]]+[1-x['missed_GPU_slots']/y['missed_GPU_slots'] if y['missed_GPU_slots']>0 else np.nan]
    rng=np.random.default_rng(SEED);point=effect(np.arange(n));samples=[]
    for _ in range(DRAWS):
        starts=rng.integers(n,size=int(np.ceil(n/block)));ix=((starts[:,None]+np.arange(block))%n).ravel()[:n];samples.append(effect(ix))
    samples=np.array(samples);rows=[]
    for k,name in enumerate(METRICS):
        finite=np.isfinite(samples[:,k]);lo,hi=np.quantile(samples[finite,k],[.025,.975]) if finite.any() else [np.nan,np.nan]
        rows.append(dict(metric=name,estimate=point[k],CI95_low=lo,CI95_high=hi,nonfinite_draws=int((~finite).sum()),N_days=n,N_pairs=len(a),block_days=block,draws=DRAWS))
    return rows
def evaluation():
    guard();freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');need(freeze['code']==code() and freeze['metrics_sha256']==sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv'),'FREEZE_DRIFT')
    f=apply_roles(EVAL);legacy=pd.read_parquet(PARENT/'PREDICTIONS.parquet');r0=legacy[legacy.arm.eq('R0')].copy();need(r0.role.eq('MAY_HISTORICAL').all(),'R0_AUTHORITY')
    r0['raw_Q90']=r0.bound_seconds;r0['correction_seconds']=0.;r0['support_fallback']=False
    parts=[f,r0[list(f.columns)]]
    for arm in ARMS:
        p=r0[r0.state.eq('PENDING')].copy();p['arm']=arm;parts.append(p[list(f.columns)])
    f=pd.concat(parts,ignore_index=True);f.to_parquet(ROOT/'PREDICTIONS.parquet',index=False);m=metrics(f);m.to_csv(ROOT/'MODEL_METRICS.csv',index=False)
    running=f[f.state.eq('RUNNING')].copy();h=running.elapsed_seconds/3600;running['elapsed_regime']=np.select([h<1,h<2,h<4,h<=8],['<1h','1-2h','2-4h','4-8h'],default='>8h');running['GPU_bucket']=np.select([running.num_gpus_req.eq(1),running.num_gpus_req.le(4)],['1 GPU','2-4 GPU'],default='>4 GPU')
    for column in ['elapsed_regime','GPU_bucket']:
        rows=[dict(role=r,arm=a,**{column:v},**stats(g)) for (r,a,v),g in running.groupby(['role','arm',column])];pd.DataFrame(rows).to_csv(ROOT/('RUNNING_'+column.upper()+'_METRICS.csv'),index=False)
    ci=[]
    for (role,state),g in f.groupby(['role','state']):
        comparisons=[('R2','R1'),('R3','R1'),('R3','R2')]+([(a,'R0') for a in ARMS] if role=='MAY_HISTORICAL' else [])
        for a,b in comparisons:
            for block in [1,7]:ci.extend(dict(role=role,state=state,candidate=a,reference=b,**r) for r in paired(g[g.arm.eq(a)],g[g.arm.eq(b)],block))
    pd.DataFrame(ci).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    save('EVALUATION_COMPLETE.json',dict(time=now(),rows=len(f),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),evaluation_reselection=False,May='historical exposed diagnostic'))
    print('EVALUATION_COMPLETE',len(f),flush=True)
def audit():
    guard();catalog=sources();ledger=[]
    for path in sorted((ROOT/'calibration').glob('*/RECEIPT.json')):
        r=read(path);p,eligible=pool_at(catalog,r['issue_time']);m=pd.read_parquet(path.parent/'MEMBERSHIP.parquet');need(sha(path.parent/'MEMBERSHIP.parquet')==r['membership_sha256'],'MEMBERSHIP_HASH')
        need(np.array_equal(m.source_job_issue_id,p.job_issue_id) and np.array_equal(m.residual_seconds,p.residual_seconds),'EXACT_RESIDUAL_POOL')
        need(corrections(p)==r['correction_seconds'] and eligible==r['eligible_forecast_rows'],'CALIBRATION_REPLAY');need(m.job_id.is_unique,'REPEATED_JOB')
        t=pd.Timestamp(r['issue_time']);need(m.source_issue_time.lt(t).all() and m.end_time.lt(t).all(),'IMMATURE_RESIDUAL')
        ledger.append(dict(issue_time=t,role=r['role'],distinct_mature_Jobs=len(p),duplicate_source_forecasts_removed=eligible-len(p),support_fallback=r['support_fallback'],global_correction_seconds=r['correction_seconds']['R2'],GPU_correction_seconds=r['correction_seconds']['R3'],GPU_weight_ESS=r['GPU_weight_ESS'],membership_sha256=r['membership_sha256']))
    need(len(ledger)==59,'MISSING_ISSUE_AUDIT');pd.DataFrame(ledger).to_csv(ROOT/'CALIBRATION_MEMBERSHIP_LEDGER.csv',index=False)
    f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');p=f[f.state.eq('PENDING')];r0=p[p.arm.eq('R0')].sort_values('job_issue_id')
    for arm in ARMS:
        a=p[p.arm.eq(arm)].sort_values('job_issue_id');need(np.array_equal(a.job_issue_id,r0.job_issue_id) and np.array_equal(a.bound_seconds,r0.bound_seconds),'PENDING_CHANGED')
    for (_,state),g in f.groupby(['role','state']):
        raw=g[g.arm.eq('R1')].sort_values('job_issue_id')
        for arm in ['R2','R3']:
            a=g[g.arm.eq(arm)].sort_values('job_issue_id');need(np.array_equal(a.job_issue_id,raw.job_issue_id) and (a.bound_seconds.to_numpy()>=raw.bound_seconds.to_numpy()).all(),'NEGATIVE_CORRECTION')
    preserve('PARENT_PRESERVATION_END.json');save('VALIDATION.json',dict(time=now(),PASS=True,issues=59,exact_residual_memberships=True,strict_source_issue_and_job_end=True,latest_per_Job_dedup=True,residual_uses_source_issue=True,Pending_R0_bit_exact=True,raw_R1_PR71_R2_unchanged=True,one_sided_no_scaling_capping=True,model_fits=0,feature_changes=0,optimizer_executions=0,grid_executions=0,PRODUCTION_PROMOTED=False))
    print('VALIDATION_PASS',len(ledger),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','register','development','evaluation','audit']);a=p.parse_args();globals()[a.stage]()
