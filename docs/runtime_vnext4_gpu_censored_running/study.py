"""GPU-weighted remaining quantiles and archive-conditional censored AFT."""
import os
for variable in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[variable]='1'
import argparse,gzip,hashlib,importlib.util,json,pickle,platform,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,'C:/codex_mobileess_workspace/v40s_runtime_dependencies/lightgbm_4_6_0')
import lightgbm as lgb
import xgboost as xgb
from scipy.stats import norm
from prepare import ROOT,BASE,JOBS,sha,need,transform
from censor_proxy import asof_rows,weight,FEATURES
PARENT=ROOT.parent/'runtime_vnext3_adaptive_running_bound'
spec=importlib.util.spec_from_file_location('readonly_vnext2',ROOT.parent/'runtime_vnext2_q95_operational_bound/study.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
PRE=['DEVELOPMENT','CALIBRATION'];EVAL=['EXPOSED_EVALUATION','MAY_HISTORICAL'];TAUS=[.5,.9,.95]
LGB=dict(n_jobs=4,random_state=4005,deterministic=True,force_col_wise=True,verbosity=-1,subsample=1.,subsample_freq=0,
 colsample_bytree=1.,reg_alpha=0.,reg_lambda=1.,device_type='cpu',max_depth=-1,max_bin=255,min_child_weight=.001,min_split_gain=0.,
 data_random_seed=4005,feature_fraction_seed=4005,bagging_seed=4005,num_leaves=31,learning_rate=.02,n_estimators=800,min_child_samples=100)
AFT=dict(objective='survival:aft',eval_metric='aft-nloglik',aft_loss_distribution='normal',aft_loss_distribution_scale=1.0,
 tree_method='hist',max_depth=5,learning_rate=.03,min_child_weight=5,reg_lambda=1.,reg_alpha=0.,max_bin=256,subsample=1.,colsample_bytree=1.,seed=4005,nthread=4,verbosity=0)
J=None

def now():return pd.Timestamp.now(tz='UTC').isoformat()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(name,value):
    path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))
def code():return {n:sha(ROOT/n) for n in ['study.py','prepare.py','censor_proxy.py','test_contract.py']}
def guard():need(code()==read(ROOT/'REGISTRATION.json')['code'],'SCIENTIFIC_SOURCE_DRIFT')
def data():
    global J
    if J is None:
        need(sha(JOBS)==read(ROOT/'PREPARATION.json')['jobs_sha256'],'JOBS_SOURCE_DRIFT');J=pd.read_parquet(JOBS)
    return J
def preserve(name):
    records=[]
    for folder in [BASE,ROOT.parent/'runtime_vnext2_q95_operational_bound',PARENT]:
        manifest=read(folder/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:need(sha(folder/r['path'])==r['sha256'],'PARENT_DRIFT '+r['path'])
        records.append(dict(folder=folder.name,N=len(manifest['files']),manifest_sha256=sha(folder/'DELIVERY_MANIFEST.json')))
    save(name,dict(time=now(),PASS=True,parents=records))

def register():
    need(read(ROOT/'PROXY_AUTHORIZATION.json')['R3_status']=='AUTHORIZED_ARCHIVE_CONDITIONAL_PROXY','PROXY_SCOPE_NOT_AUTHORIZED')
    preserve('PARENT_PRESERVATION_START.json')
    save('REGISTRATION.json',dict(time=now(),code=code(),base_PR=68,
        proxy='User-authorized V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1; archive request fields assumed scheduler-visible; actual historical exactness/immutability/zerochange NOT claimed; provenance UNVERIFIED/UNOBSERVED',
        temporal='180-day observation/end window,14-day half-life,each inherited issue refit. For R3 still-active rows observation_time=currentissue, not futureend.',
        R0='current frozen production Q90; Running naive total-minus-elapsed; May only',R1='fixed PR65 elapsed-conditioned remaining MULTI_QUANTILE',
        R2='same R1 completed landmark membership,representation,LightGBM hyperparameters; only trainingweight changes',
        R3='fixed log-normal XGBoost AFT remaining lifetime on identical completed landmarks plus observed archive-conditional rightcensored running landmarks',
        pending='allarms exact frozenR0; no Pendingmodel/quantilechanges; noDEV/CAL/AprilbackwardsR0replay',
        train_weight='recency * requested_GPU_count * (2 if asof_observed_total_runtime>4h else1); divideGPU/longfactor by its recency-weighted mean to preserve total recency weight. R2 allcompleted observedtotal=actualtotal. R3 censored observedtotal=issue-start, neverfuturetotal.',
        long_weight_multiplier=2.0,weight_tuning=False,LGB=LGB,AFT=AFT,AFT_rounds=800,quantiles=TAUS,operational_quantile=.9,
        R3_label='At stableJob-hash elapsed landmark, completed end<issue -> exact remaining; stillrunning -> lower=issue-start-landmark, upper=inf. Retain lower>0; never label_valid/futurecompletion basedfilter for censored.',
        AFT_quantiles='exp(raw_margin + fixed_sigma * standard_normal_ppf(tau)); targetalreadyremaininggivenelapsed, nottotal-minuselapsed',
        selection='DEV/CAL Q90 only; safetycoverage>=.90,GPUcoverage>=.90,longtotal>4hunder<=.15 in BOTH roles; preferoverreserve<=requestedreference inBOTH,thenlowestmeanreserved/requested ratio. Noeligiblecandidate->R0. R0missedslotscomparisonMayonly unavailablepre-eval. Q50/Q95 diagnostics only, noquantileselectorsearch.',
        features='unchanged nineMOEinputs +log1p(elapsed),exactfrozenpreprocessingportableexport; no newfeatures',
        bootstrap=dict(draws=2000,seed=20260927,blocks=[1,7],unit='paired observedissue-day circularblocks; ratiosrecomputedperdraw'),
        exposure='Mayalreadyexposed historicaldiagnostic,notuntouchedconfirmation',
        censor_population='ALL relevant GPU rows in observedarchive; incompleteness/outcome-dependentinclusion NOT ruledout; noactualhistoricalcensusclaim',
        optimizer_executions=0,grid_executions=0,PRODUCTION_PROMOTED=False))
    save('ENVIRONMENT.json',dict(time=now(),executable=sys.executable,python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,lightgbm=lgb.__version__,xgboost=xgb.__version__))
    print('REGISTERED fixedGPU/longweights and archive-conditionalAFT beforeDEV metrics',flush=True)

def cohort(t,family):
    f=asof_rows(data(),t)
    if family=='R2':f=f[~f.right_censored].copy()
    w,normalizer=weight(f,t);f['sample_weight']=w
    return f,normalizer

def fit_one(issue):
    guard();t=pd.Timestamp(issue);key=t.strftime('%Y%m%dT%H%M');raw=BASE/'predictions/LGBM_180_14'/(key+'.parquet')
    original=read(BASE/'fits/LGBM_180_14'/key/'PREDICTION_RECEIPT.json');need(sha(raw)==original['prediction_sha256'],'R1_PREDICTION_DRIFT')
    q=pd.read_parquet(raw);q=q[q.state.eq('RUNNING')].drop(columns=['Q99'],errors='ignore').copy()
    artifactpath=ROOT/'preprocessing'/(key+'.pkl.gz');bridge={pd.Timestamp(r['issue_time']).strftime('%Y%m%dT%H%M'):r for r in read(ROOT/'PREPROCESSING_BRIDGE.json')['issues']}
    need(sha(artifactpath)==bridge[key]['portable_sha256'],'PREPROCESSOR_DRIFT')
    with gzip.open(artifactpath,'rb') as f:artifact=pickle.load(f)
    xp=np.column_stack([transform(q[FEATURES],artifact),np.log1p(q.elapsed_seconds)])
    for family in ['R2','R3']:
        predpath=ROOT/'predictions'/family/(key+'.parquet')
        if predpath.exists():
            need(sha(predpath)==read(ROOT/'fits'/family/key/'RECEIPT.json')['prediction_sha256'],'CACHE_DRIFT');continue
        began=time.perf_counter();train,normalizer=cohort(t,family);folder=ROOT/'fits'/family/key;folder.mkdir(parents=True,exist_ok=True)
        train[['row_id','job_id','observed_end','observation_time','elapsed_seconds','observed_total_seconds','label_lower','label_upper','right_censored','sample_weight']].to_parquet(folder/'MEMBERSHIP.parquet',index=False)
        if family=='R2':
            proof=read(BASE/'fits/LGBM_180_14'/key/'RUNNING/preprocessing.json')
            digest=hashlib.sha256(('\n'.join(sorted(map(str,train.job_id)))+'\n').encode()).hexdigest()
            need(len(train)==proof['training_N'] and digest==proof['landmark_jobs_hash'],'R2_MEMBERSHIP_NOT_R1')
        xt=np.column_stack([transform(train[FEATURES],artifact),np.log1p(train.elapsed_seconds)])
        need(not np.isinf(xt).any() and not np.isinf(xp).any(),'INFINITE_FEATURES')
        if family=='R2':
            predictions=[]
            for tau in TAUS:
                model=lgb.LGBMRegressor(objective='quantile',alpha=tau,**LGB).fit(xt,train.label_lower,sample_weight=train.sample_weight).booster_
                path=folder/f'Q{int(tau*100)}.txt.gz';path.write_bytes(gzip.compress(model.model_to_string().encode(),mtime=0))
                predictions.append(model.predict(xp,num_threads=1))
            values=np.maximum.accumulate(np.maximum(np.column_stack(predictions),0),axis=1)
        else:
            dm=xgb.DMatrix(xt,weight=train.sample_weight.to_numpy(),nthread=4)
            dm.set_float_info('label_lower_bound',train.label_lower.to_numpy());dm.set_float_info('label_upper_bound',train.label_upper.to_numpy())
            model=xgb.train(AFT,dm,num_boost_round=800)
            model.save_model(folder/'AFT.ubj')
            margin=model.predict(xgb.DMatrix(xp,nthread=1),output_margin=True)
            values=np.exp(margin[:,None]+AFT['aft_loss_distribution_scale']*norm.ppf(TAUS)[None,:])
        need(np.isfinite(values).all() and (values>=0).all(),'INVALID_FORECAST')
        result=q.copy()
        for k,tau in enumerate(TAUS):result[f'Q{int(100*tau)}']=values[:,k]
        result['point']=result.Q50
        predpath.parent.mkdir(parents=True,exist_ok=True);result.to_parquet(predpath,index=False)
        models={p.name:sha(p) for p in folder.iterdir() if p.suffix=='.ubj' or p.name.endswith('.txt.gz')}
        save(folder.relative_to(ROOT)/'RECEIPT.json',dict(time=now(),issue_time=t,family=family,N_train=len(train),N_censored=int(train.right_censored.sum()),
            weight_normalizer=normalizer,weight_sum=float(train.sample_weight.sum()),membership_sha256=sha(folder/'MEMBERSHIP.parquet'),preprocessing_sha256=sha(artifactpath),
            N_query=len(q),prediction_sha256=sha(predpath),models=models,feature_columns=FEATURES+['log1p(elapsed_seconds)'],
            targets_passed_to_query_transform=[],elapsed_seconds_used=True,seconds=time.perf_counter()-began))
        print('FIT',family,key,len(train),int(train.right_censored.sum()),round(time.perf_counter()-began,2),flush=True)

def forecast(roles):
    guard();from concurrent.futures import ProcessPoolExecutor
    issues=pd.read_csv(BASE/'ISSUES.csv');dates=issues[issues.role.isin(roles)].issue_time.tolist()
    with ProcessPoolExecutor(max_workers=2) as pool:list(pool.map(fit_one,dates))

def outputs(roles):
    pieces=[];issues=pd.read_csv(BASE/'ISSUES.csv')
    for row in issues[issues.role.isin(roles)].itertuples():
        key=pd.Timestamp(row.issue_time).strftime('%Y%m%dT%H%M')
        for family in ['R1','R2','R3']:
            path=BASE/'predictions/LGBM_180_14'/(key+'.parquet') if family=='R1' else ROOT/'predictions'/family/(key+'.parquet')
            f=pd.read_parquet(path);f=f[f.state.eq('RUNNING')].copy();f=old.label_join(f)
            f['arm']=family;f['bound_seconds']=f.Q90;f['nominal_quantile']=.9;pieces.append(f)
    return pd.concat(pieces,ignore_index=True)

def stats(f):
    m=old.stats(f);valid=f.actual_seconds.notna();g=f[valid]
    m['MAE_bound_seconds']=float(abs(g.actual_seconds-g.bound_seconds).mean())
    m['MAE_Q50_seconds']=float(abs(g.actual_seconds-g.Q50).mean()) if np.isfinite(g.Q50).all() else np.nan
    return m

def choose(table):
    columns=['coverage','GPU_coverage','long_under','overreserved_GPUh','requested_overreserved_GPUh','reserve_vs_requested']
    need(np.isfinite(table[columns]).all().all(),'NONFINITE_SELECTION_METRIC');options=[]
    for family,g in table.groupby('arm'):
        need(set(g.role)==set(PRE),'SELECTION_SPLIT_MISSING')
        safe=bool((g.coverage>=.9).all() and (g.GPU_coverage>=.9).all() and (g.long_under<=.15).all())
        reserve=bool((g.overreserved_GPUh<=g.requested_overreserved_GPUh).all())
        options.append(dict(arm=family,safety_pass=safe,reserve_preferred_pass=reserve,reserve_ratio=float(g.reserve_vs_requested.mean())))
    eligible=[r for r in options if r['safety_pass']]
    selected=min(eligible,key=lambda r:(not r['reserve_preferred_pass'],r['reserve_ratio'],r['arm']))['arm'] if eligible else 'R0'
    return selected,options

def select():
    guard();f=outputs(PRE);rows=[]
    for (role,arm),g in f.groupby(['role','arm']):rows.append(dict(role=role,arm=arm,state='RUNNING',**stats(g)))
    table=pd.DataFrame(rows);table.to_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv',index=False);selected,options=choose(table)
    save('FINAL_SELECTION_FREEZE.json',dict(time=now(),selected=selected,options=options,operational_quantile=.9,Pending='R0 unchanged',
        code=code(),registration_sha256=sha(ROOT/'REGISTRATION.json'),selection_metrics_sha256=sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv'),
        current_evaluation_metrics_computed=False,May_previously_exposed=True))
    print('SELECTION_FREEZE',selected,options,flush=True)

METRICS=old.METRICS+['MAE_bound_seconds','overreserve_vs_requested','missed_slots_reduction']
def vector(f):
    return np.r_[old.daily_values(f),np.abs(f.actual_seconds-f.bound_seconds).sum()]
def summary(v):
    s=old.summarize(v[:13]);s['MAE_bound_seconds']=v[13]/v[0];return s
def paired(a,b,block):
    a=a.sort_values('job_issue_id');b=b.sort_values('job_issue_id');need(np.array_equal(a.job_issue_id,b.job_issue_id) and np.array_equal(a.actual_seconds,b.actual_seconds),'PAIR_MISMATCH')
    va=np.array([vector(g) for _,g in a.groupby('issue_time',sort=True)]);vb=np.array([vector(g) for _,g in b.groupby('issue_time',sort=True)]);n=len(va)
    def effect(ix):
        x,y=summary(va[ix].sum(0)),summary(vb[ix].sum(0));return [x[k]-y[k] for k in METRICS[:-1]]+[1-x['missed_GPU_slots']/y['missed_GPU_slots'] if y['missed_GPU_slots']>0 else np.nan]
    rng=np.random.default_rng(20260927);point=effect(np.arange(n));samples=[]
    for _ in range(2000):
        starts=rng.integers(n,size=int(np.ceil(n/block)));ix=((starts[:,None]+np.arange(block))%n).ravel()[:n];samples.append(effect(ix))
    samples=np.array(samples);rows=[]
    for k,name in enumerate(METRICS):
        finite=np.isfinite(samples[:,k]);lo,hi=np.quantile(samples[finite,k],[.025,.975]) if finite.any() else [np.nan,np.nan]
        rows.append(dict(metric=name,estimate=point[k],CI95_low=lo,CI95_high=hi,nonfinite_draws=int((~finite).sum()),N_days=n,N_pairs=len(a),block_days=block,draws=2000))
    return rows

def evaluate():
    guard();freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');need(freeze['code']==code(),'FINAL_CODE_DRIFT')
    f=outputs(EVAL);parent=pd.read_parquet(BASE/'PREDICTIONS.parquet');r0=parent[parent.model.eq('PR42_FROZEN_LGBM_NAIVE_REMAINING')].copy()
    r0['arm']='R0';r0['bound_seconds']=r0.Q90;r0['nominal_quantile']=.9
    # R0 only has an authoritative Q90 output: other inherited diagnostic fields remain unavailable.
    r0['Q50']=np.nan;r0['Q95']=np.nan;r0['Q99']=np.nan
    columns=list(f.columns);parts=[f,r0[columns]]
    for arm in ['R1','R2','R3']:
        p=r0[r0.state.eq('PENDING')].copy();p['arm']=arm;parts.append(p[columns])
    f=pd.concat(parts,ignore_index=True);f.to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
    rows=[];strata=[];quantiles=[]
    for (role,arm,state),g in f.groupby(['role','arm','state']):
        rows.append(dict(role=role,arm=arm,state=state,**stats(g)))
        for tau in TAUS:
            col=f'Q{int(tau*100)}'
            if np.isfinite(g[col]).all():
                z=g.copy();z['bound_seconds']=z[col];loss=z.actual_seconds-z.bound_seconds
                quantiles.append(dict(role=role,arm=arm,state=state,quantile=tau,proper_pinball=float(np.maximum(tau*loss,(tau-1)*loss).mean()),**stats(z)))
        if state=='RUNNING':
            e=g.elapsed_seconds/3600;regime=np.select([e<1,e<2,e<4,e<=8],['<1h','1-2h','2-4h','4-8h'],default='>8h')
            for value in ['<1h','1-2h','2-4h','4-8h','>8h']:
                z=g[regime==value]
                if len(z):strata.append(dict(role=role,arm=arm,elapsed_regime=value,**stats(z)))
    pd.DataFrame(rows).to_csv(ROOT/'MODEL_METRICS.csv',index=False);pd.DataFrame(quantiles).to_csv(ROOT/'QUANTILE_DIAGNOSTICS.csv',index=False);pd.DataFrame(strata).to_csv(ROOT/'RUNNING_ELAPSED_METRICS.csv',index=False)
    ci=[]
    for (role,state),g in f.groupby(['role','state']):
        comparisons=[('R2','R1'),('R3','R1'),('R3','R2')]
        if role=='MAY_HISTORICAL':comparisons += [(a,'R0') for a in ['R1','R2','R3']]
        for candidate,reference in comparisons:
            for block in [1,7]:ci.extend(dict(role=role,state=state,candidate=candidate,reference=reference,**r) for r in paired(g[g.arm.eq(candidate)],g[g.arm.eq(reference)],block))
    pd.DataFrame(ci).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    save('EVALUATION_COMPLETE.json',dict(time=now(),rows=len(f),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),May='exposed historicaldiagnostic',evaluation_reselection=False))
    print('EVALUATION_COMPLETE',len(f),flush=True)

def audit():
    guard();ledger=[]
    for row in pd.read_csv(BASE/'ISSUES.csv').query("role != 'TRAIN'").itertuples():
        t=pd.Timestamp(row.issue_time);key=t.strftime('%Y%m%dT%H%M')
        for arm in ['R2','R3']:
            folder=ROOT/'fits'/arm/key;stored=pd.read_parquet(folder/'MEMBERSHIP.parquet');expected,normalizer=cohort(t,arm);receipt=read(folder/'RECEIPT.json')
            need(np.array_equal(stored.row_id,expected.row_id),'FIT_MEMBERSHIP')
            for col in ['label_lower','label_upper','elapsed_seconds','observed_total_seconds','sample_weight']:
                need(np.array_equal(stored[col],expected[col]),'ASOF_LABEL_WEIGHT_DRIFT '+col)
            need(sha(folder/'MEMBERSHIP.parquet')==receipt['membership_sha256'],'MEMBERSHIP_HASH')
            for name,digest in receipt['models'].items():need(sha(folder/name)==digest,'MODEL_DRIFT')
            need(sha(ROOT/'predictions'/arm/(key+'.parquet'))==receipt['prediction_sha256'],'PREDICTION_DRIFT')
            need(stored.loc[stored.right_censored,'observed_end'].isna().all(),'FUTURE_END_STORED')
            ledger.append(dict(issue_time=t,role=row.role,arm=arm,N_train=len(stored),N_censored=int(stored.right_censored.sum()),weight_normalizer=normalizer,membership_sha256=receipt['membership_sha256']))
    pd.DataFrame(ledger).to_csv(ROOT/'TRAINING_MEMBERSHIP_LEDGER.csv',index=False)
    f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');baseline=f[f.arm.eq('R0')&f.state.eq('PENDING')].sort_values('job_issue_id')
    for arm in ['R1','R2','R3']:
        p=f[f.arm.eq(arm)&f.state.eq('PENDING')].sort_values('job_issue_id');need(np.array_equal(p.job_issue_id,baseline.job_issue_id) and np.array_equal(p.bound_seconds,baseline.bound_seconds),'PENDING_CHANGED')
    preserve('PARENT_PRESERVATION_END.json')
    save('VALIDATION.json',dict(time=now(),PASS=True,exact_training_memberships=len(ledger),safe_censor_labels=True,asof_weights_reproduced=True,
        all_model_prediction_digests=True,Pending_R0_bit_exact=True,request_proxy='D1_SCHEDULER_REQUEST_STATE_PROXY_V1',
        provenance='UNVERIFIED/UNOBSERVED',historical_census_claimed=False,historical_request_exactness_claimed=False,
        production_promoted=False,optimizer_executions=0,grid_executions=0))
    print('VALIDATION_PASS',len(ledger),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','development','select','evaluation','audit']);a=p.parse_args()
    if a.stage=='development':forecast(PRE)
    elif a.stage=='evaluation':guard();need((ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'SELECT_FIRST');forecast(EVAL);evaluate()
    else:globals()[a.stage]()
