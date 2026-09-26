"""Causal Q90/Q95 selector; frozen runtime models and Pending R0 never change."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, platform, sys, warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
import sklearn

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'runtime_vnext2_q95_operational_bound'
BASE=ROOT.parent/'runtime_vnext_causal_tail'
spec=importlib.util.spec_from_file_location('frozen_vnext2',PARENT/'study.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha,need,now=old.sha,old.need,old.now
SEED=20260927;DRAWS=2000;THRESHOLDS=[i/10 for i in range(1,10)]
PRE=['TRAIN','DEVELOPMENT','CALIBRATION'];EVAL=['EXPOSED_EVALUATION','MAY_HISTORICAL']
FEATURES=['log_spread','normalized_spread','log_elapsed_hours','elapsed_over_requested',
          'log_remaining_requested_hours','log_gpu_count','hardware_H100','hardware_A100',
          'hardware_HPE','hardware_OTHER','standby','elapsed_lt1','elapsed_1to2','elapsed_2to4','elapsed_4to8','elapsed_gt8']
METRICS=old.METRICS+['overreserve_vs_requested','missed_slots_reduction']

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(name,obj):
    path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))

def code_hashes():return {n:sha(ROOT/n) for n in ['study.py','test_contract.py']}
def check_code():need(code_hashes()==read(ROOT/'REGISTRATION.json')['code_hashes'],'FROZEN_SOURCE_DRIFT')
def parent_audit(name):
    details=[]
    for base in [PARENT,BASE]:
        manifest=read(base/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:need(sha(base/r['path'])==r['sha256'],'PARENT_DRIFT '+r['path'])
        details.append(dict(folder=base.name,delivery_sha256=sha(base/'DELIVERY_MANIFEST.json'),files=len(manifest['files'])))
    save(name,dict(time=now(),PASS=True,parents=details))

def register():
    parent_audit('PARENT_PRESERVATION_START.json')
    save('REGISTRATION.json',dict(time=now(),version='Runtime-vNext3-v1',base_PR=66,code_hashes=code_hashes(),
        underlying_runtime=dict(temporal_policy='PR65 180-day,14-day half-life,original issue refits',model='fixed MULTI_QUANTILE Q90/Q95',new_training_executions=0),
        pending='all arms use exact latest frozen production R0 Q90; May only. R0 unavailable DEV/CAL/April, no backward replay or fabricated Pending baseline.',
        running='R0 naive frozen total-minus-elapsed; R1 exact Q90; R2 exact Q95; R3 Q95 iff risk_probability >= frozen threshold, Q90 otherwise',
        selector=dict(family='single fixed standardized logistic regression; no model-family search',C=1.0,solver='lbfgs',max_iter=5000,class_weight=None,seed=SEED,
            target='historical elapsed-conditioned Q90 underprediction: actual_remaining_seconds > Q90',
            training='prior Running OOS issue < current issue AND job_end_time < current issue AND valid label; latest observation per Job; expanding selector history',
            minimum_unique_jobs=100,minimum_each_class=10,insufficient_support='probability=0, selects Q90 for every registered positive threshold',
            features=FEATURES,standardization='training-only mean/std; fixed feature schema, no fitted categories',thresholds=THRESHOLDS),
        selection='DEVELOPMENT/CALIBRATION Running only. Safety means coverage>=.90,GPUcoverage>=.90,long-total-runtime>4h-under<=.15 separately in BOTH roles. Reserve preferred means overreservedGPUh<=requested-overreservedGPUh in BOTH. Among safety-passing candidates prefer reserve-passing, then lowest average(role total reservedGPUh/requestedGPUh), then highest threshold. If none safety-passing choose lowest mean normalized safety deficit then reserve ratio then highest threshold as research-only candidate. All selection metrics must be finite.',
        safety_deficit='mean across DEV/CAL of max(.9-cov,0)/.9 + max(.9-GPUcov,0)/.9 + max(longunder-.15,0)/.15',
        R0_comparison='current R0 not available in DEV/CAL; missed-slot advantage cannot be selected there. May diagnostic only; no reselection.',
        long_job='actual total runtime >4h; remaining underprediction for Running',
        slot_metric='GPU-weighted positive ceil(actual/900)-ceil(bound/900), each truncated to96 slots; runtime-origin occupancy proxy, not actual dispatch',
        reserve='requested reference=max(requested_seconds-elapsed_seconds,0); total reserve and overreserve both reported',
        bootstrap=dict(paired=True,draws=DRAWS,seed=SEED,blocks=[1,7],unit='observed issue-days; circular chronological blocks; all ratios recomputed each draw'),
        feature_authority='issue event-time only; request-version and ingestion provenance UNVERIFIED',
        exposure='post-May-exposure development; May diagnostic historical, never untouched confirmation',
        TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,PRODUCTION_PROMOTED=False,
        flags_scope='underlying runtime model/policy unchanged; newly trained risk selector explicitly disclosed',optimizer_executions=0,grid_executions=0))
    save('ENVIRONMENT.json',dict(time=now(),python=platform.python_version(),executable=sys.executable,numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__))
    print('REGISTERED; no new selection or evaluation metrics computed',flush=True)

def features(f):
    need(f.state.eq('RUNNING').all(),'SELECTOR_NOT_RUNNING')
    spread=f.Q95.to_numpy()-f.Q90.to_numpy();need((spread>=0).all(),'UNORDERED_QUANTILES')
    q90=f.Q90.to_numpy();elapsed=f.elapsed_seconds.to_numpy()/3600;requested=f.requested_seconds.to_numpy()/3600
    need((requested>0).all() and (elapsed>=0).all(),'INVALID_REQUEST_OR_ELAPSED')
    part=f.partition.fillna('').astype(str).str.lower();qos=f.qos.fillna('').astype(str).str.lower()
    hw=np.select([part.str.contains('h100'),part.str.contains('a100'),part.str.contains('hpe')],['H100','A100','HPE'],default='OTHER')
    standby=part.str.contains('stdby|standby')|qos.str.contains('standby')
    x=np.column_stack([np.log1p(spread),spread/np.maximum(q90,1.),np.log1p(elapsed),elapsed/requested,
        np.log1p(np.maximum(requested-elapsed,0)),np.log1p(f.num_gpus_req.to_numpy()),
        *[hw==v for v in ['H100','A100','HPE','OTHER']],standby,
        elapsed<1,(elapsed>=1)&(elapsed<2),(elapsed>=2)&(elapsed<4),(elapsed>=4)&(elapsed<=8),elapsed>8]).astype(float)
    need(x.shape[1]==len(FEATURES) and np.isfinite(x).all(),'NONFINITE_FEATURE')
    return x

def eligible_history(raw,t):
    hist=raw[raw.issue_time.lt(t)&raw.end_time.lt(t)&raw.actual_seconds.notna()].copy()
    hist=hist.sort_values(['issue_time','job_issue_id'],kind='stable').drop_duplicates('job_id',keep='last')
    return hist.sort_values('job_id',kind='stable')

def forecast(raw,roles):
    raw=raw[raw.state.eq('RUNNING')].copy();parts=[]
    for t,q in raw[raw.role.isin(roles)].groupby('issue_time',sort=True):
        key=t.strftime('%Y%m%dT%H%M');out=ROOT/'selector_predictions'/(key+'.parquet')
        hist=eligible_history(raw,t);target=(hist.actual_seconds>hist.Q90).astype(int).to_numpy()
        if out.exists():
            receipt=read(ROOT/'selector_fits'/key/'FIT.json')
            need(sha(out)==receipt['prediction_sha256'],'SELECTOR_CACHE_DRIFT');parts.append(pd.read_parquet(out));continue
        folder=ROOT/'selector_fits'/key;folder.mkdir(parents=True,exist_ok=True)
        fitfile=folder/'MEMBERSHIP.parquet'
        hist[['job_issue_id','job_id','row_id','issue_time','end_time','Q90','actual_seconds']].to_parquet(fitfile,index=False)
        support=len(hist)>=100 and min(np.sum(target==0),np.sum(target==1))>=10
        xq=features(q);description={}
        if support:
            xt=features(hist);scaler=StandardScaler().fit(xt)
            model=LogisticRegression(C=1.0,solver='lbfgs',max_iter=5000,class_weight=None,random_state=SEED)
            with warnings.catch_warnings():
                warnings.simplefilter('error',ConvergenceWarning);model.fit(scaler.transform(xt),target)
            probability=model.predict_proba(scaler.transform(xq))[:,1]
            description=dict(mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),coefficient=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),iterations=int(model.n_iter_[0]))
        else:probability=np.zeros(len(q))
        p=q.copy();p['risk_probability']=probability
        out.parent.mkdir(parents=True,exist_ok=True);p.to_parquet(out,index=False)
        save(folder.relative_to(ROOT)/'FIT.json',dict(time=now(),issue_time=t,N_training=len(hist),positive_labels=int(target.sum()),negative_labels=int((1-target).sum()),
            learned=bool(support),fallback='Q90' if not support else None,features=FEATURES,training_membership_sha256=sha(fitfile),
            latest_training_issue=hist.issue_time.max() if len(hist) else None,latest_training_end=hist.end_time.max() if len(hist) else None,
            prediction_sha256=sha(out),N_predictions=len(q),model=description,feature_available_time='issue_time of each OOS prediction; known request/elapsed only'))
        parts.append(p)
    return pd.concat(parts,ignore_index=True)

def raw_data(roles):
    f=old.load_candidates(roles);return f[f.arm.eq('R1')].drop(columns=['arm','bound_seconds','nominal_quantile']).copy()

def bound(f,arm,threshold=None):
    g=f.copy();g['arm']=arm
    if arm=='R1':q=g.Q90.to_numpy();tau=np.full(len(g),.90)
    elif arm=='R2':q=g.Q95.to_numpy();tau=np.full(len(g),.95)
    else:
        high=g.risk_probability.to_numpy()>=threshold;q=np.where(high,g.Q95,g.Q90);tau=np.where(high,.95,.9)
    g['bound_seconds']=q;g['nominal_quantile']=tau;g['uses_Q95']=tau==.95
    return g

def stats(f):
    return {**old.stats(f),'Q95_fraction':float(f.uses_Q95.mean()),'Q95_GPU_fraction':float(np.average(f.uses_Q95,weights=f.num_gpus_req))}

def select_threshold(table):
    mandatory=['coverage','GPU_coverage','long_under','overreserved_GPUh','requested_overreserved_GPUh','reserve_vs_requested']
    need(np.isfinite(table[mandatory].to_numpy(float)).all(),'NONFINITE_SELECTION_METRIC')
    candidates=[]
    for threshold,g in table.groupby('threshold'):
        need(set(g.role)=={'DEVELOPMENT','CALIBRATION'} and len(g)==2,'MISSING_SELECTION_ROLE')
        safe=bool((g.coverage>=.9).all() and (g.GPU_coverage>=.9).all() and (g.long_under<=.15).all())
        reserve=bool((g.overreserved_GPUh<=g.requested_overreserved_GPUh).all())
        deficit=float((np.maximum(.9-g.coverage,0)/.9+np.maximum(.9-g.GPU_coverage,0)/.9+np.maximum(g.long_under-.15,0)/.15).mean())
        candidates.append(dict(threshold=float(threshold),safety_pass=safe,reserve_pass=reserve,deficit=deficit,reserve_ratio=float(g.reserve_vs_requested.mean())))
    safe=[c for c in candidates if c['safety_pass']]
    winner=min(safe,key=lambda c:(not c['reserve_pass'],c['reserve_ratio'],-c['threshold'])) if safe else min(candidates,key=lambda c:(c['deficit'],c['reserve_ratio'],-c['threshold']))
    return winner,candidates

def select():
    check_code();need(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'ALREADY_FROZEN')
    raw=raw_data(PRE);f=forecast(raw,PRE);f=f[f.role.ne('TRAIN')];rows=[];baseline=[]
    for role,g in f.groupby('role'):
        for tau in THRESHOLDS:rows.append(dict(role=role,threshold=tau,**stats(bound(g,'R3',tau))))
        for arm in ['R1','R2']:baseline.append(dict(role=role,arm=arm,**stats(bound(g,arm))))
    table=pd.DataFrame(rows);table.to_csv(ROOT/'SELECTOR_DEVELOPMENT_CALIBRATION.csv',index=False)
    pd.DataFrame(baseline).to_csv(ROOT/'REFERENCE_DEVELOPMENT_CALIBRATION.csv',index=False)
    winner,allchoices=select_threshold(table)
    save('FINAL_SELECTION_FREEZE.json',dict(time=now(),R3_threshold=winner['threshold'],research_candidate=winner,all_candidates=allchoices,
        selector='fixed logistic P(actual_remaining>Q90); Q95 iff probability>=threshold',pending='R0 unchanged',
        development_candidate_supported=bool(winner['safety_pass'] and winner['reserve_pass']),
        operational_adoption='R0 retained; no production authority in this study',code_hashes=code_hashes(),
        registration_sha256=sha(ROOT/'REGISTRATION.json'),selection_metrics_sha256=sha(ROOT/'SELECTOR_DEVELOPMENT_CALIBRATION.csv'),
        new_evaluation_metrics_computed=False,May_exposure_already_known=True))
    print('FINAL_SELECTION_FREEZE',json.dumps(winner),flush=True)

def paired(a,b,block):
    a=a.sort_values('job_issue_id');b=b.sort_values('job_issue_id')
    need(np.array_equal(a.job_issue_id,b.job_issue_id) and np.array_equal(a.actual_seconds,b.actual_seconds),'UNPAIRED')
    va=np.array([old.daily_values(g) for _,g in a.groupby('issue_time',sort=True)])
    vb=np.array([old.daily_values(g) for _,g in b.groupby('issue_time',sort=True)])
    n=len(va)
    def effect(idx):
        sa,sb=old.summarize(va[idx].sum(0)),old.summarize(vb[idx].sum(0))
        return [sa[k]-sb[k] for k in METRICS[:-1]]+[1-sa['missed_GPU_slots']/sb['missed_GPU_slots'] if sb['missed_GPU_slots']>0 else np.nan]
    point=effect(np.arange(n));rng=np.random.default_rng(SEED);samples=[]
    for _ in range(DRAWS):
        starts=rng.integers(n,size=int(np.ceil(n/block)));idx=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        samples.append(effect(idx))
    samples=np.asarray(samples);rows=[]
    for i,metric in enumerate(METRICS):
        finite=np.isfinite(samples[:,i]);lo,hi=np.quantile(samples[finite,i],[.025,.975]) if finite.any() else (np.nan,np.nan)
        rows.append(dict(metric=metric,estimate=point[i],CI95_low=lo,CI95_high=hi,block_days=block,draws=DRAWS,
            nonfinite_draws=int((~finite).sum()),N_days=n,N_pairs=len(a),interpretation='relative reduction' if metric=='missed_slots_reduction' else 'candidate-minus-reference'))
    return rows

def evaluate():
    check_code();freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');need(freeze['code_hashes']==code_hashes(),'FREEZE_DRIFT')
    need(sha(ROOT/'SELECTOR_DEVELOPMENT_CALIBRATION.csv')==freeze['selection_metrics_sha256'],'SELECTION_DRIFT')
    need(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'EVAL_ALREADY_DONE')
    raw=raw_data(PRE+EVAL);pred=forecast(raw,EVAL);pieces=[]
    for arm in ['R1','R2','R3']:pieces.append(bound(pred,arm,freeze['R3_threshold']))
    legacy=pd.read_parquet(BASE/'PREDICTIONS.parquet');r0=legacy[legacy.model.eq('PR42_FROZEN_LGBM_NAIVE_REMAINING')].copy()
    r0['bound_seconds']=r0.Q90;r0['arm']='R0';r0['nominal_quantile']=.9;r0['uses_Q95']=False;r0['risk_probability']=np.nan
    cols=pieces[0].columns.tolist();pieces.append(r0[cols])
    for arm in ['R1','R2','R3']:
        pending=r0[r0.state.eq('PENDING')].copy();pending['arm']=arm;pieces.append(pending[cols])
    f=pd.concat(pieces,ignore_index=True);f.to_parquet(ROOT/'BOUND_PREDICTIONS.parquet',index=False)
    rows=[];strata=[]
    for (role,arm,state),g in f.groupby(['role','arm','state']):
        rows.append(dict(role=role,arm=arm,state=state,**stats(g)))
        if state=='RUNNING':
            elapsed=g.elapsed_seconds/3600;regime=np.select([elapsed<1,elapsed<2,elapsed<4,elapsed<=8],['<1h','1-2h','2-4h','4-8h'],default='>8h')
            for value in ['<1h','1-2h','2-4h','4-8h','>8h']:
                z=g[regime==value]
                if len(z):strata.append(dict(role=role,arm=arm,elapsed_regime=value,**stats(z)))
    pd.DataFrame(rows).to_csv(ROOT/'MODEL_METRICS.csv',index=False);pd.DataFrame(strata).to_csv(ROOT/'RUNNING_ELAPSED_METRICS.csv',index=False)
    ci=[]
    for (role,state),g in f.groupby(['role','state']):
        comparisons=[('R3','R1'),('R3','R2')]
        if role=='MAY_HISTORICAL':comparisons += [(a,'R0') for a in ['R1','R2','R3']]
        for candidate,reference in comparisons:
            a=g[g.arm.eq(candidate)];b=g[g.arm.eq(reference)]
            for block in [1,7]:ci += [dict(role=role,state=state,candidate=candidate,reference=reference,**r) for r in paired(a,b,block)]
    pd.DataFrame(ci).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    save('EVALUATION_COMPLETE.json',dict(time=now(),rows=len(f),predictions_sha256=sha(ROOT/'BOUND_PREDICTIONS.parquet'),
        final_freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),evaluation_reselection=False,May='exposed historical diagnostic'))
    print('EVALUATION_COMPLETE',len(f),flush=True)

def audit():
    check_code();freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');raw=raw_data(PRE+EVAL);running=raw[raw.state.eq('RUNNING')];ledger=[]
    for t,q in running.groupby('issue_time',sort=True):
        key=t.strftime('%Y%m%dT%H%M');folder=ROOT/'selector_fits'/key;receipt=read(folder/'FIT.json')
        got=pd.read_parquet(folder/'MEMBERSHIP.parquet');expected=eligible_history(running,t)
        need(np.array_equal(got.job_issue_id,expected.job_issue_id),'SELECTOR_MEMBERSHIP_NOT_EXACT')
        need(got.end_time.lt(t).all() and got.issue_time.lt(t).all() and got.job_id.is_unique,'IMMATURE_OR_DUPLICATE_SELECTOR_LABEL')
        need(sha(folder/'MEMBERSHIP.parquet')==receipt['training_membership_sha256'],'MEMBERSHIP_DIGEST')
        p=pd.read_parquet(ROOT/'selector_predictions'/(key+'.parquet'));need(np.array_equal(p.job_issue_id,q.job_issue_id),'SELECTOR_QUERY_EXCLUSION')
        need(p.submit_time.le(t).all(),'FUTURE_REQUEST_FEATURE');need(np.isfinite(features(p)).all(),'FEATURE_FAIL')
        if receipt['learned']:
            model=receipt['model'];z=(features(p)-model['mean'])/model['scale'];expected_p=1/(1+np.exp(-(z@np.array(model['coefficient'])+model['intercept'])))
            need(np.allclose(p.risk_probability,expected_p,rtol=1e-12,atol=1e-12),'SELECTOR_REPLAY_FAIL')
        else:need((p.risk_probability==0).all(),'FALLBACK_DRIFT')
        need(sha(ROOT/'selector_predictions'/(key+'.parquet'))==receipt['prediction_sha256'],'PREDICTION_DRIFT')
        ledger.append(dict(issue_time=t,role=q.role.iloc[0],N_training=len(got),N_queries=len(q),learned=receipt['learned'],
            latest_training_end=got.end_time.max(),membership_sha256=receipt['training_membership_sha256'],feature_available_time=t))
    pd.DataFrame(ledger).to_csv(ROOT/'SELECTOR_CAUSAL_MEMBERSHIP_LEDGER.csv',index=False)
    f=pd.read_parquet(ROOT/'BOUND_PREDICTIONS.parquet');pending=f[f.state.eq('PENDING')]
    r0=pending[pending.arm.eq('R0')].sort_values('job_issue_id')
    for arm in ['R1','R2','R3']:
        p=pending[pending.arm.eq(arm)].sort_values('job_issue_id')
        need(np.array_equal(p.job_issue_id,r0.job_issue_id) and np.array_equal(p.bound_seconds,r0.bound_seconds),'PENDING_R0_CHANGED')
    r3=f[f.state.eq('RUNNING')&f.arm.eq('R3')]
    expected=np.where(r3.risk_probability>=freeze['R3_threshold'],r3.Q95,r3.Q90)
    need(np.array_equal(r3.bound_seconds,expected),'R3_NOT_EXACT_BOUND')
    need((r3.bound_seconds>=r3.Q90).all() and (r3.bound_seconds<=r3.Q95).all(),'POINTWISE_BOUNDS_FAIL')
    for arm in ['R1','R2','R3']:
        a=f[f.arm.eq(arm)&f.state.eq('RUNNING')]
        e=running[running.role.isin(EVAL)];need(set(a.job_issue_id)==set(e.job_issue_id),'RUNNING_EVAL_EXCLUSION')
    data=pd.read_csv(ROOT/'MODEL_METRICS.csv');may=data[data.role.eq('MAY_HISTORICAL')&data.state.eq('RUNNING')].set_index('arm')
    need(may.loc['R1','GPU_coverage']<=may.loc['R3','GPU_coverage']<=may.loc['R2','GPU_coverage'],'COVERAGE_ENVELOPE')
    need(may.loc['R1','overreserved_GPUh']<=may.loc['R3','overreserved_GPUh']<=may.loc['R2','overreserved_GPUh'],'RESERVE_ENVELOPE')
    save('POINTWISE_FEASIBILITY.json',dict(time=now(),interpretation='historical diagnostic mathematical envelope, never tuning input',
        proof='For every Job-issue Q90<=R3<=Q95. Coverage indicators are monotone in bound, as is max(bound-actual,0). Therefore Q95 GPU coverage is an upper bound and Q90 overreserve a lower bound for every binary selector.',
        GPU_coverage_upper=float(may.loc['R2','GPU_coverage']),GPU_coverage_target=.9,
        overreserve_GPUh_lower=float(may.loc['R1','overreserved_GPUh']),walltime_overreserve_GPUh=float(may.loc['R1','requested_overreserved_GPUh']),
        jointly_feasible_on_May=bool(may.loc['R2','GPU_coverage']>=.9 and may.loc['R1','overreserved_GPUh']<=may.loc['R1','requested_overreserved_GPUh'])))
    parent_audit('PARENT_PRESERVATION_END.json')
    save('VALIDATION.json',dict(time=now(),PASS=True,exact_selector_memberships=len(ledger),selector_prediction_replay=True,
        mature_labels_only=True,prior_OOS_only=True,latest_unique_Job=True,Pending_R0_bit_exact=True,R3_exact_Q90_or_Q95=True,
        parent_runtime_membership_validation_sha256=sha(PARENT/'VALIDATION.json'),parent_67_runtime_memberships_unchanged=True,
        event_time_feature_availability_checked=True,request_ingestion_provenance='UNVERIFIED',no_scaling_or_capping=True,
        TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,PRODUCTION_PROMOTED=False,optimizer_executions=0,grid_executions=0))
    print('VALIDATION PASS',len(ledger),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['register','select','evaluate','audit']);args=parser.parse_args();globals()[args.stage]()
