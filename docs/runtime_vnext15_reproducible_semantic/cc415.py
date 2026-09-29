"""T0/B0 semantic-feature-only comparison, using bounded pre-April source arrays."""
from common15 import *
sys.path.insert(0,str(REPO))
from v42.semantic_adapter import SemanticFeatureAdapter,historical_payload
from v42.semantic_state import numeric_state
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits
import time,gc
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
PARAMS=dict(num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,
            deterministic=True,force_col_wise=True,random_state=20260924,verbosity=-1)

def load():
    z=np.load(LOCAL/'CC4_BASE_PREAPRIL.npz');l=pd.read_csv(LOCAL/'CC4_DAY_LEDGER_PREAPRIL.csv')
    return dict(x=z['X'],y=z['y'],q0=z['q'],days=z['days'].astype(str),ledger=l,
        issue=pd.to_datetime(l.issue_time,utc=True),mature=pd.to_datetime(l.label_matured_at,utc=True))

def guard():
    f=read(ROOT/'CC4_EXECUTION_FREEZE.json')
    assert sha(ROOT/'PREREGISTRATION.json')==read(ROOT/'PREREGISTRATION_HASH.json')['sha256']
    for p,h in f['code'].items():assert sha(REPO/p)==h,p

def register():
    assert not (ROOT/'CC4_EXECUTION_FREEZE.json').exists()
    code=[ROOT/'cc415.py',ROOT/'prepare_cc415.py',REPO/'v42/semantic_adapter.py',REPO/'v42/semantic_state.py']
    write('CC4_EXECUTION_FREEZE.json',dict(time=now(),code={p.relative_to(REPO).as_posix():sha(p) for p in code},
        preregistration_sha256=sha(ROOT/'PREREGISTRATION.json'),baseline_input=rec(ROOT/'CC4_BASELINE_INPUT_RECEIPT.json'),
        before_CC4_training=True,heavy_workers=4,threads_per_model=1))

def prepare():
    guard();assert (ROOT/'RUNTIME_SELECTION_FREEZE.json').exists()
    if (LOCAL/'CC4_SEMANTIC_STATES.npz').exists():return
    d=load();l=d['ledger'];g=pd.read_parquet(LOCAL/'GPU_SUBMISSION_METADATA.parquet').sort_values(['submit_time','id']).reset_index(drop=True)
    train_days=set(d['days'][l.split.eq('TRAIN')&l.eligible])
    cutoff=d['issue'][l.split.eq('DEVELOPMENT')&l.eligible].min()
    allowed=g.submit_time.dt.tz_convert('Etc/GMT-10').dt.strftime('%Y-%m-%d').isin(train_days)&g.submit_time.lt(cutoff)
    idx=np.flatnonzero(allowed);assert len(idx)>=32
    membership=hashlib.sha256(('\n'.join(sorted(g.loc[allowed,'id'].astype(str)))+'\n').encode()).hexdigest()
    payload=[historical_payload(r) for r in g.to_dict('records')]
    folder=LOCAL/'cc4_adapter'
    print(now(),'CC4_SVD_FIT',len(idx),flush=True)
    if (folder/'adapter.json').exists():adapter=SemanticFeatureAdapter.load(folder)
    else:
        adapter=SemanticFeatureAdapter().fit([payload[i] for i in idx],training_receipt=dict(TRAIN_ONLY=True,
            membership_sha256=membership,fit_cutoff=str(cutoff),TRAIN_days=sorted(train_days),rows=len(idx),target_input=False))
        adapter.save(folder)
    sem,recurrence=adapter.transform(payload)
    with threadpool_limits(limits=4):
        km=KMeans(n_clusters=8,random_state=1401,n_init=10).fit(sem[idx]);clusters=km.predict(sem)
    np.save(folder/'kmeans_centers.npy',km.cluster_centers_,allow_pickle=False)
    times=g.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()/1e6
    values=[];names=None;base=None
    for issue in d['issue']:
        v,n,b=numeric_state(times,sem,recurrence,issue.timestamp(),clusters)
        values.append(v);names=n;base=b
    states=np.asarray(values,np.float32)
    # Random issue-time perturbations alter every future numeric representation,
    # including recurrence/cluster values; the feature builder must not access them.
    rng=np.random.default_rng(1401);checks=[]
    oos=np.flatnonzero(l.target_day.ge('2024-09-01')&l.preApril_maturity)
    for i in sorted(rng.choice(oos,size=min(12,len(oos)),replace=False)):
        issue=d['issue'].iloc[i].timestamp();future=times>=issue
        s2=sem.copy();r2=recurrence.copy();c2=clusters.copy()
        s2[future]=np.nan;r2[future]=np.nan;c2[future]=-999
        changed,_,_=numeric_state(times,s2,r2,issue,c2)
        np.testing.assert_array_equal(changed,states[i])
        recent=np.flatnonzero((times<issue)&(times>=issue-72*3600))
        positive=None
        if len(recent):
            j=int(recent[-1])
            # Perturb one actual past payload field using a distinct TRAIN-known identity.
            replacement=None
            for k in idx:
                if payload[j].user!=payload[k].user:replacement=int(k);break
            if replacement is not None:
                sp=sem.copy();rp=recurrence.copy();cp=clusters.copy()
                altered_payload=replace(payload[j],user=payload[replacement].user)
                new_sem,new_rec=adapter.transform([altered_payload])
                sp[j]=new_sem[0];rp[j]=new_rec[0];cp[j]=km.predict(new_sem)[0]
                altered,_,_=numeric_state(times,sp,rp,issue,cp)
                positive=not np.array_equal(altered,states[i]);assert positive
        checks.append(dict(day=d['days'][i],future_rows_perturbed=int(future.sum()),future_identical=True,past_positive_control=positive,past_field_perturbed='user',past_window_rows=len(recent)))
    np.savez_compressed(LOCAL/'CC4_SEMANTIC_STATES.npz',values=states,names=np.asarray(names),base_count=np.array(base))
    write('CC4_SEMANTIC_CAUSALITY_AUDIT.json',dict(PASS=True,CC4_SEMANTIC_FUTURE_PERTURBATION_PASS=True,
        future_leakage_count=0,strict_boundary='submit_time < issue_time',checks=checks,
        synthetic_payload_positive_control=read(ROOT/'SEMANTIC_UNIT_TEST_RESULTS.json')['PASS'],
        fit_TRAIN_only=True,train_membership=membership,TRAIN_N=len(idx),fit_cutoff=str(cutoff),
        K=8,random_state=1401,base_state_dimensions=base,cluster_augmented_dimensions=len(names),
        unavailable_account_script_family_features='OMITTED_AUTHORITY_UNPROVEN',source_ingestion_certified=False))
    print('CC4_STATES_READY',states.shape,base,flush=True)

_DATA=None
def init_worker():
    global _DATA
    d=load();z=np.load(LOCAL/'CC4_SEMANTIC_STATES.npz');state=z['values'];base=int(z['base_count'])
    d['features']={arm:np.concatenate([d['x'],np.repeat(state[:,:n,None].transpose(0,2,1),24,axis=1)],axis=2)
                   for arm,n in [('C1',base),('C2',state.shape[1])]}
    _DATA=d

def one(task):
    import lightgbm as lgb
    arm,i=task;d=_DATA;path=LOCAL/'cc4_runs'/arm/(d['days'][i]+'.npz')
    if path.exists():return arm,i,True
    path.parent.mkdir(parents=True,exist_ok=True)
    tr=np.flatnonzero((d['mature']<d['issue'].iloc[i])&(d['issue']<d['issue'].iloc[i])&d['ledger'].split.ne('PURGE'))
    w=np.asarray(np.exp2(-np.maximum((d['issue'].iloc[i]-pd.to_datetime(d['days'][tr],utc=True)).total_seconds()/86400,0)/30))
    assert len(tr)>=20
    x=d['features'][arm];a=x[tr].reshape(-1,x.shape[-1]);b=np.log1p(d['y'][tr].ravel());weight=np.repeat(w,24)
    predictions=[];hashes=[];started=time.perf_counter()
    for tau in [.5,.9]:
        model=lgb.LGBMRegressor(objective='quantile',alpha=tau,**PARAMS).fit(a,b,sample_weight=weight).booster_
        predictions.append(np.maximum(0,np.expm1(model.predict(x[i],num_threads=1))))
        hashes.append(hashlib.sha256(model.model_to_string().encode()).hexdigest())
    q=np.column_stack(predictions);q[:,1]=np.maximum(q[:,0],q[:,1]);assert np.isfinite(q).all()
    np.savez_compressed(path,q=q,training_days=tr,weights=w,model_sha256=np.asarray(hashes),
        latest_maturity_ns=np.array(d['mature'].iloc[tr].max().value),issue_ns=np.array(d['issue'].iloc[i].value),seconds=np.array(time.perf_counter()-started))
    return arm,i,False

def run():
    guard();assert (ROOT/'RUNTIME_SELECTION_FREEZE.json').exists();prepare()
    d=load();ids=np.flatnonzero(d['ledger'].target_day.ge('2024-09-01')&d['ledger'].preApril_maturity)
    tasks=[(arm,int(i)) for i in ids for arm in ['C1','C2']]
    with ProcessPoolExecutor(max_workers=4,initializer=init_worker) as pool:
        for j,(arm,i,reused) in enumerate(pool.map(one,tasks,chunksize=1)):
            if j%10==0:print(now(),'CC4_FIT',j+1,len(tasks),arm,d['days'][i],reused,flush=True)
    collect()

def metric(y,q,burst):
    y=np.asarray(y);q=np.asarray(q);res=y-q[:,:,1];e=y-q[:,:,0];total=float(y.sum())
    return dict(days=len(y),hourly_Q90_coverage=float(np.mean(res<=0)),
        daily_Q90_coverage=float(np.mean(y.sum(1)<=q[:,:,1].sum(1))),
        daily_Q90_semantics='Coverage of summed marginal hourly Q90 requirements; not a joint daily .90 quantile',
        Q90_pinball=float(np.maximum(.9*res,-.1*res).mean()),
        requirement_ratio=float(q[:,:,1].sum()/total) if total else None,
        burst_N=int((y>burst).sum()),burst_coverage=float(np.mean(res[y>burst]<=0)) if (y>burst).any() else None,
        Q50_MAE=float(abs(e).mean()),WAPE=float(abs(e).sum()/total) if total else None,
        actual_GPUh=total,required_GPUh=float(q[:,:,1].sum()),
        daily_coverage_std=float(np.mean(res<=0,axis=1).std()),
        minimum_day_hourly_coverage=float(np.mean(res<=0,axis=1).min()))

def role_ids(d,role):
    l=d['ledger'];return np.flatnonzero(l.split.eq(role)&l.preApril_maturity&(True if role=='OOS_EXTENSION' else l.eligible))

def calibration(d,q):
    dev=role_ids(d,'DEVELOPMENT');cal=role_ids(d,'CALIBRATION');ev=role_ids(d,'EXPOSED_EVALUATION')
    final=cal[np.asarray(d['mature'].iloc[cal]<d['issue'].iloc[ev[0]])]
    def delta(ids):
        rank=int(np.ceil(.9*(len(ids)+1)))
        return np.sort(d['y'][ids]-q[ids,:,1],axis=0)[rank-1]
    frozen=delta(final);out=q.copy();pool=np.r_[dev,cal]
    for i in np.flatnonzero(d['ledger'].target_day.ge('2024-09-01')&d['ledger'].preApril_maturity):
        if d['days'][i]>='2024-12-01':shift=frozen
        else:
            past=pool[(pool<i)&np.asarray(d['mature'].iloc[pool]<d['issue'].iloc[i])]
            shift=delta(past) if len(past)>=20 else np.zeros(24)
        out[i,:,1]=np.maximum(out[i,:,0],np.maximum(0,out[i,:,1]+shift))
    return out,dict(calibration_days=d['days'][final].tolist(),delta=frozen.tolist(),evaluation_updates=False)

def paired_ci(y,candidate,baseline,block):
    rc=y-candidate[:,:,1];rb=y-baseline[:,:,1]
    diff=(np.maximum(.9*rc,-.1*rc)-np.maximum(.9*rb,-.1*rb)).mean(1)
    rng=np.random.default_rng(20260928);n=len(diff);starts=rng.integers(0,n,size=(2000,int(np.ceil(n/block))))
    idx=((starts[:,:,None]+np.arange(block)[None,None,:])%n).reshape(2000,-1)[:,:n]
    score=diff[idx].mean(1);lo,hi=np.quantile(score,[.025,.975])
    return dict(mean=float(diff.mean()),lower=float(lo),upper=float(hi),block_days=block,draws=2000)

def collect():
    d=load();l=d['ledger'];train=np.flatnonzero(l.split.eq('TRAIN')&l.eligible)
    # Exact current threshold, computed only from the inherited TRAIN target.
    burst=float(np.quantile(d['y'][train][d['y'][train]>0],.95))
    q={'C0':d['q0']};cal={};cal_receipts={}
    for arm in ['C1','C2']:
        a=np.full_like(d['q0'],np.nan)
        for p in (LOCAL/'cc4_runs'/arm).glob('*.npz'):
            i=int(np.searchsorted(d['days'],p.stem));a[i]=np.load(p)['q']
        q[arm]=a
    development=[]
    for arm in q:
        cal[arm],cal_receipts[arm]=calibration(d,q[arm])
        for role in ['DEVELOPMENT','CALIBRATION']:
            idx=role_ids(d,role)
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:
                development.append(dict(arm=arm,role=role,variant=variant,**metric(d['y'][idx],p[idx],burst)))
    f=pd.DataFrame(development);rank=f[f.role.eq('DEVELOPMENT')&f.variant.eq('RAW')].copy()
    rank['calibration_error']=(rank.hourly_Q90_coverage-.9).abs()
    band=rank[rank.hourly_Q90_coverage.between(.88,.92)];pool=band if len(band) else rank
    winner=pool.sort_values(['Q90_pinball','calibration_error','requirement_ratio','arm']).iloc[0].arm
    write('CC4_DEVELOPMENT_SELECTION_FREEZE.json',dict(time=now(),candidate=winner,selection_role='DEVELOPMENT_RAW',
        nominal_band_available=bool(len(band)),calibrations=cal_receipts,April_used=False,May_used=False,
        preregistration_sha256=sha(ROOT/'PREREGISTRATION.json')))
    rows=development.copy();period=[];ci=[];gates={}
    for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
        idx=role_ids(d,role)
        for arm in q:
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:rows.append(dict(arm=arm,role=role,variant=variant,**metric(d['y'][idx],p[idx],burst)))
            if arm!='C0':
                for block in [1,7]:ci.append(dict(arm=arm,role=role,**paired_ci(d['y'][idx],q[arm][idx],q['C0'][idx],block)))
    frame=pd.DataFrame(rows)
    for arm in ['C1','C2']:
        rolechecks={}
        for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
            a=frame[frame.arm.eq(arm)&frame.role.eq(role)].set_index('variant')
            b=frame[frame.arm.eq('C0')&frame.role.eq(role)].set_index('variant')
            rolechecks[role]=dict(pinball_CI_all_upper_negative=all(r['upper']<0 for r in ci if r['arm']==arm and r['role']==role),
                WAPE_noninferior=bool(a.loc['RAW','WAPE']<=b.loc['RAW','WAPE']),
                requirement_noninferior=bool((a.requirement_ratio<=b.requirement_ratio).all()),
                calibrated_nominal=bool(.88<=a.loc['CALIBRATED','hourly_Q90_coverage']<=.92),
                burst_noninferior=bool(a.loc['CALIBRATED','burst_coverage']>=b.loc['CALIBRATED','burst_coverage']))
        gates[arm]=dict(periods=rolechecks,passed=all(all(v.values()) for v in rolechecks.values()))
    selected=winner if winner!='C0' and gates[winner]['passed'] else 'C0'
    for arm in q:
        for month in sorted(set(d['days'][l.target_day.ge('2024-09-01')&l.preApril_maturity].astype('U7'))):
            idx=np.flatnonzero(np.char.startswith(d['days'],month)&l.preApril_maturity)
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:period.append(dict(arm=arm,period=month,variant=variant,**metric(d['y'][idx],p[idx],burst)))
    frame.to_csv(ROOT/'CC4_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(period).to_csv(ROOT/'CC4_FOLD_METRICS.csv',index=False)
    frame[['arm','role','variant','burst_N','burst_coverage']].assign(TRAIN_Q95_threshold=burst).to_csv(ROOT/'CC4_BURST_METRICS.csv',index=False)
    pd.DataFrame(ci).to_csv(ROOT/'CC4_PAIRED_PINBALL_CI.csv',index=False)
    write('CC4_SELECTION_FREEZE.json',dict(time=now(),selected=selected,semantic_model_selected=selected!='C0',
        development_candidate=winner,gates=gates,C0_retrained=False,TRAIN_burst_threshold=burst,
        April_used_for_selection=False,May_payload_opened=False,target_changed=False,model_family_changed=False,
        source_request_version_certified=False,automatic_optimizer_integration=False,
        exact_daily_refit_counts={arm:len(list((LOCAL/'cc4_runs'/arm).glob('*.npz'))) for arm in ['C1','C2']}))
    print('CC4_COMPLETE',selected,flush=True)

if __name__=='__main__':
    phase=sys.argv[1] if len(sys.argv)>1 else 'run'
    {'register':register,'prepare':prepare,'run':run,'collect':collect}[phase]()
