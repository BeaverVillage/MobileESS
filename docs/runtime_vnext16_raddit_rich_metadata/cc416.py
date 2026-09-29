"""Conditional CC4 feature-only study; never reads April/May target payloads."""
from common16 import *
sys.path.insert(0,str(V15))
import cc415 as prior
from concurrent.futures import ProcessPoolExecutor
import time
PARAMS=dict(prior.PARAMS)

def load():
    z=np.load(V15/'.local/CC4_BASE_PREAPRIL.npz');l=pd.read_csv(V15/'.local/CC4_DAY_LEDGER_PREAPRIL.csv')
    return dict(x=z['X'],y=z['y'],q0=z['q'],days=z['days'].astype(str),ledger=l,
        issue=pd.to_datetime(l.issue_time,utc=True),mature=pd.to_datetime(l.label_matured_at,utc=True))

def register():
    assert read(ROOT/'CC4_RICH_AUTHORIZATION.json')['authorized']
    assert read(ROOT/'RUNTIME_V16_SELECTION_FREEZE.json')['status']=='COMPLETED'
    if (ROOT/'CC4_RICH_EXECUTION_FREEZE.json').exists():return
    write('CC4_RICH_EXECUTION_FREEZE.json',dict(time=now(),before_new_CC4_fit=True,code=rec(ROOT/'cc416.py'),
        baseline='Exact T0/B0, hourly submitted-GPUh, log1p target, frozen LightGBM learner and daily maturity/30day weights',
        parameters=PARAMS,workers=4,threads_per_model=1,fields=['user','submit_line'],
        C3='TRAIN top16 per field plus OTHER and FIELD_MISSING; log arrival counts, shares, entropy/concentration across1/6/24/72h. No labels or future unsubmitted metadata.',
        C4='C3 plus TRAIN top16 user-command pair composition, only after C3 DEVELOPMENT_RAW trigger',
        C4_trigger='C3 DEVELOPMENT_RAW pinball<C0, abs(hourly coverage-.9)<=C0, daily coverage>=C0, burst coverage>=C0',
        ranking_and_final_gates='Exact V15 frozen development/calibration/exposed/OOS recipe; C0 cannot be replaced by T2_F0/T3_F2',
        evaluation_history='Existing exposed/OOS periods are reported as inherited; not falsely called a fresh untouched evaluation',
        family_or_target_changed=False,April_selection=False,May_opened=False))

def state(times,codes,issue,with_pairs=False):
    result=[]
    for fields in ([[0,1],[2]] if with_pairs else [[0,1]]):
        for hours in [1,6,24,72]:
            ix=(times<issue)&(times>=issue-hours*3600)
            for j in fields:
                count=np.bincount(codes[ix,j],minlength=18).astype(float);n=count.sum();share=count/max(n,1)
                pos=share>0
                result.extend(np.log1p(count));result.extend(share)
                result.extend([np.log1p(n),float(-np.sum(share[pos]*np.log(share[pos]))),float(np.sum(share**2))])
    return np.asarray(result,np.float32)

def prepare():
    register();d=load();l=d['ledger'];g=pd.read_parquet(V15/'.local/GPU_SUBMISSION_METADATA.parquet').sort_values(['submit_time','id']).reset_index(drop=True)
    train_days=set(d['days'][l.split.eq('TRAIN')&l.eligible]);cut=d['issue'][l.split.eq('DEVELOPMENT')&l.eligible].min()
    mask=g.submit_time.dt.tz_convert('Etc/GMT-10').dt.strftime('%Y-%m-%d').isin(train_days)&g.submit_time.lt(cut)
    values=[g.user_hash.fillna('<FIELD_MISSING>').astype(str),g.submit_line_hash.fillna('<FIELD_MISSING>').astype(str)]
    values.append((values[0]+'\x1f'+values[1]).where(values[0].ne('<FIELD_MISSING>')&values[1].ne('<FIELD_MISSING>'),'<FIELD_MISSING>'));codes=[];vocab=[]
    for s in values:
        counts=s[mask&s.ne('<FIELD_MISSING>')].value_counts();ordered=sorted(counts.index,key=lambda v:(-int(counts[v]),v))[:16]
        mapping={v:i+1 for i,v in enumerate(ordered)};mapping['<FIELD_MISSING>']=17
        vocab.append(mapping);codes.append(s.map(mapping).fillna(0).to_numpy(np.int16))
    codes=np.column_stack(codes);times=g.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()/1e6
    states={arm:np.array([state(times,codes,t.timestamp(),arm=='C4') for t in d['issue']],np.float32) for arm in ['C3','C4']}
    np.testing.assert_array_equal(states['C3'],states['C4'][:,:states['C3'].shape[1]])
    checks=[];ids=np.flatnonzero(l.target_day.ge('2024-09-01')&l.preApril_maturity)
    for i in sorted(np.random.default_rng(1601).choice(ids,12,replace=False)):
        issue=d['issue'].iloc[i].timestamp();future=times>=issue;poison=codes.copy();poison[future]=-999
        for arm in ['C3','C4']:np.testing.assert_array_equal(state(times,poison,issue,arm=='C4'),states[arm][i])
        past=np.flatnonzero((times<issue)&(times>=issue-72*3600));positive=None
        if len(past):
            changed=codes.copy();j=past[-1];changed[j,0]=1 if changed[j,0]!=1 else 2
            positive=not np.array_equal(state(times,changed,issue),states['C3'][i]);assert positive
        checks.append(dict(day=d['days'][i],future_rows=int(future.sum()),future_unchanged=True,past_positive_control=positive))
    np.savez_compressed(LOCAL/'CC4_RICH_STATES.npz',**states)
    write('.local/CC4_CATEGORY_BUNDLE.json',dict(fields=['user','submit_line','user_submit_line_pair'],maps=vocab,TRAIN_only=True,fit_cutoff=str(cut),TRAIN_N=int(mask.sum()),labels_used=False))
    write('CC4_RICH_CAUSALITY_AUDIT.json',dict(time=now(),PASS=True,strict_boundary='submit_time < issue_time',checks=checks,
        no_runtime_or_future_job_labels_in_state=True,fit_TRAIN_only=True,dimensions={k:v.shape[1] for k,v in states.items()},
        conditional_C4_state_prepared_not_model_run=True,source=rec(V15/'.local/GPU_SUBMISSION_METADATA.parquet')))
    print('CC4_RICH_STATES',[(k,v.shape) for k,v in states.items()],flush=True)

DATA=None
def init_worker():
    global DATA
    d=load();s=np.load(LOCAL/'CC4_RICH_STATES.npz')
    d['features']={arm:np.concatenate([d['x'],np.repeat(s[arm][:,None,:],24,axis=1)],axis=2) for arm in ['C3','C4']};DATA=d

def one(task):
    import lightgbm as lgb
    arm,i=task;d=DATA;path=LOCAL/'cc4_rich_runs'/arm/(d['days'][i]+'.npz')
    if path.exists():return arm,i,True
    path.parent.mkdir(parents=True,exist_ok=True)
    tr=np.flatnonzero((d['mature']<d['issue'].iloc[i])&(d['issue']<d['issue'].iloc[i])&d['ledger'].split.ne('PURGE'))
    w=np.asarray(np.exp2(-np.maximum((d['issue'].iloc[i]-pd.to_datetime(d['days'][tr],utc=True)).total_seconds()/86400,0)/30))
    old=np.load(V15/'.local/cc4_runs/C1'/(d['days'][i]+'.npz'))
    np.testing.assert_array_equal(tr,old['training_days']);np.testing.assert_allclose(w,old['weights'],rtol=1e-14,atol=1e-15)
    x=d['features'][arm];a=x[tr].reshape(-1,x.shape[-1]);y=np.log1p(d['y'][tr].ravel());weight=np.repeat(w,24)
    pred=[];hashes=[];start=time.perf_counter()
    for q in [.5,.9]:
        model=lgb.LGBMRegressor(objective='quantile',alpha=q,**PARAMS).fit(a,y,sample_weight=weight).booster_
        pred.append(np.maximum(0,np.expm1(model.predict(x[i],num_threads=1))))
        model_text=model.model_to_string();hashes.append(hashlib.sha256(model_text.encode()).hexdigest())
        mp=LOCAL/'cc4_rich_models'/arm/f'{d["days"][i]}_q{int(q*100)}.txt';mp.parent.mkdir(parents=True,exist_ok=True)
        mp.write_text(model_text,encoding='utf-8',newline='\n')
    q=np.column_stack(pred);q[:,1]=np.maximum(q[:,0],q[:,1]);assert np.isfinite(q).all()
    np.savez_compressed(path,q=q,training_days=tr,weights=w,model_sha256=np.asarray(hashes),seconds=np.array(time.perf_counter()-start),
        latest_maturity_ns=np.array(d['mature'].iloc[tr].max().value),issue_ns=np.array(d['issue'].iloc[i].value))
    return arm,i,False

def predictions(d,arm):
    q=np.full_like(d['q0'],np.nan)
    for p in (LOCAL/'cc4_rich_runs'/arm).glob('*.npz'):q[int(np.searchsorted(d['days'],p.stem))]=np.load(p)['q']
    return q

def run_arm(arm):
    assert np.__version__=='1.26.4','Use the exact inherited CC4 interpreter, not the Runtime feature-preparation environment'
    freeze=read(ROOT/'CC4_RICH_EXECUTION_FREEZE.json');assert sha(ROOT/'cc416.py')==freeze['code']['sha256']
    d=load();ids=np.flatnonzero(d['ledger'].target_day.ge('2024-09-01')&d['ledger'].preApril_maturity)
    with ProcessPoolExecutor(max_workers=4,initializer=init_worker) as pool:
        for j,result in enumerate(pool.map(one,[(arm,int(i)) for i in ids],chunksize=1)):
            if j%10==0:print('CC4_RICH_FIT',arm,j+1,len(ids),result,flush=True)

def decide_c4():
    d=load();train=np.flatnonzero(d['ledger'].split.eq('TRAIN')&d['ledger'].eligible)
    burst=float(np.quantile(d['y'][train][d['y'][train]>0],.95));ix=prior.role_ids(d,'DEVELOPMENT')
    b=prior.metric(d['y'][ix],d['q0'][ix],burst);a=prior.metric(d['y'][ix],predictions(d,'C3')[ix],burst)
    yes=a['Q90_pinball']<b['Q90_pinball'] and abs(a['hourly_Q90_coverage']-.9)<=abs(b['hourly_Q90_coverage']-.9) and a['daily_Q90_coverage']>=b['daily_Q90_coverage'] and a['burst_coverage']>=b['burst_coverage']
    write('CC4_C4_AUTHORIZATION.json',dict(time=now(),authorized=bool(yes),selection_role='DEVELOPMENT_RAW_ONLY',C0=b,C3=a,April_used=False,May_used=False))
    return yes

def collect():
    d=load();l=d['ledger'];train=np.flatnonzero(l.split.eq('TRAIN')&l.eligible);burst=float(np.quantile(d['y'][train][d['y'][train]>0],.95))
    arms=['C3']+(['C4'] if read(ROOT/'CC4_C4_AUTHORIZATION.json')['authorized'] else [])
    q={'C0':d['q0'],**{arm:predictions(d,arm) for arm in arms}};cal={};receipts={};rows=[];ci=[];period=[]
    for arm in q:
        cal[arm],receipts[arm]=prior.calibration(d,q[arm])
        for role in ['DEVELOPMENT','CALIBRATION']:
            ix=prior.role_ids(d,role)
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:rows.append(dict(arm=arm,role=role,variant=variant,**prior.metric(d['y'][ix],p[ix],burst)))
    f=pd.DataFrame(rows);rank=f[f.role.eq('DEVELOPMENT')&f.variant.eq('RAW')].copy();rank['calibration_error']=(rank.hourly_Q90_coverage-.9).abs()
    band=rank[rank.hourly_Q90_coverage.between(.88,.92)];pool=band if len(band) else rank
    winner=pool.sort_values(['Q90_pinball','calibration_error','requirement_ratio','arm']).iloc[0].arm
    write('CC4_RICH_DEVELOPMENT_FREEZE.json',dict(time=now(),candidate=winner,selection_role='DEVELOPMENT_RAW',calibrations=receipts,April_used=False,May_used=False))
    for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
        ix=prior.role_ids(d,role)
        for arm in q:
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:rows.append(dict(arm=arm,role=role,variant=variant,**prior.metric(d['y'][ix],p[ix],burst)))
            if arm!='C0':
                for block in [1,7]:ci.append(dict(arm=arm,role=role,**prior.paired_ci(d['y'][ix],q[arm][ix],q['C0'][ix],block)))
    frame=pd.DataFrame(rows);gates={}
    for arm in arms:
        checks={}
        for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
            a=frame[frame.arm.eq(arm)&frame.role.eq(role)].set_index('variant');b=frame[frame.arm.eq('C0')&frame.role.eq(role)].set_index('variant')
            checks[role]=dict(pinball_CI_all_upper_negative=all(r['upper']<0 for r in ci if r['arm']==arm and r['role']==role),
                WAPE_noninferior=bool(a.loc['RAW','WAPE']<=b.loc['RAW','WAPE']),requirement_noninferior=bool((a.requirement_ratio<=b.requirement_ratio).all()),
                calibrated_nominal=bool(.88<=a.loc['CALIBRATED','hourly_Q90_coverage']<=.92),burst_noninferior=bool(a.loc['CALIBRATED','burst_coverage']>=b.loc['CALIBRATED','burst_coverage']))
        gates[arm]=dict(periods=checks,passed=all(all(v.values()) for v in checks.values()))
    chosen=winner if winner!='C0' and gates[winner]['passed'] else 'C0'
    for arm in q:
        for month in sorted(set(d['days'][l.target_day.ge('2024-09-01')&l.preApril_maturity].astype('U7'))):
            ix=np.flatnonzero(np.char.startswith(d['days'],month)&l.preApril_maturity)
            for variant,p in [('RAW',q[arm]),('CALIBRATED',cal[arm])]:period.append(dict(arm=arm,period=month,variant=variant,**prior.metric(d['y'][ix],p[ix],burst)))
    if 'C4' not in arms:frame=pd.concat([frame,pd.DataFrame([dict(arm='C4',status='NOT_RUN_C3_DEVELOPMENT_TRIGGER_NOT_MET')])],ignore_index=True)
    frame.to_csv(ROOT/'CC4_RICH_MODEL_COMPARISON.csv',index=False);pd.DataFrame(ci).to_csv(ROOT/'CC4_RICH_PAIRED_PINBALL_CI.csv',index=False)
    pd.DataFrame(period).to_csv(ROOT/'CC4_RICH_FOLD_METRICS.csv',index=False)
    write('CC4_RICH_SELECTION_FREEZE.json',dict(time=now(),status='COMPLETED',stage_run=True,selected=chosen,development_candidate=winner,gates=gates,
        C0='Frozen T0/B0 hourly submitted-GPUh LightGBM',C0_retrained=False,T2_F0_promoted=False,T3_F2_promoted=False,
        individual_future_unsubmitted_semantics_used=False,April_selection=False,May_opened=False,TRAIN_burst_threshold=burst,
        exact_daily_refit_counts={arm:len(list((LOCAL/'cc4_rich_runs'/arm).glob('*.npz'))) for arm in arms}))
    print('CC4_RICH_SELECTED',chosen,flush=True)

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='prepare':prepare()
    elif mode=='run':
        run_arm('C3')
        if decide_c4():run_arm('C4')
        collect()
