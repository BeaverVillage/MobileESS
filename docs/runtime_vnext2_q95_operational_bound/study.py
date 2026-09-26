"""Fixed PR65 quantile-bound study. No training or downstream simulation imports."""
from pathlib import Path
import argparse, hashlib, json, platform, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'runtime_vnext_causal_tail'
SEED = 20260927
DRAW = 2000
ROLES = ['DEVELOPMENT', 'CALIBRATION']
EVAL = ['EXPOSED_EVALUATION', 'MAY_HISTORICAL']
MODELS = {'R1': ('Q90', .90), 'R2': ('Q95', .95)}
METRICS = ['coverage', 'GPU_coverage', 'long_under', 'missed_GPU_slots',
           'overreserved_GPUh', 'reserved_GPUh', 'reserve_vs_requested', 'pinball_Q90', 'pinball_Q95']

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def need(ok, reason):
    if not ok:
        raise AssertionError(reason)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def save(name, obj, exclusive=True):
    with (ROOT/name).open('x' if exclusive else 'w', encoding='utf-8') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False,
                  default=lambda x: x.item() if hasattr(x, 'item') else str(x))

def now():
    return pd.Timestamp.now(tz='UTC').isoformat()

def source_hashes():
    return {p.name: sha(p) for p in sorted(ROOT.glob('*.py')) if p.name in ['study.py', 'test_contract.py']}

def verify_sources():
    need(source_hashes() == read(ROOT/'REGISTRATION.json')['code_hashes'], 'REGISTERED_CODE_DRIFT')

def parent_audit(output):
    manifest = read(BASE/'DELIVERY_MANIFEST.json')
    for entry in manifest['files']:
        need(sha(BASE/entry['path']) == entry['sha256'], 'PARENT_DRIFT ' + entry['path'])
    save(output, dict(time=now(), PASS=True, files=len(manifest['files']),
         parent_delivery_sha256=sha(BASE/'DELIVERY_MANIFEST.json'),
         parent_commit='d3ec564854f65f62b3587f49c857d2f86575ad2c'))

def register():
    need(not (ROOT/'REGISTRATION.json').exists(), 'ALREADY_REGISTERED')
    parent_audit('PARENT_PRESERVATION_START.json')
    save('REGISTRATION.json', dict(time=now(), version='runtime-vNext2-q90-q95-v1',
        base_PR=65, code_hashes=source_hashes(),
        temporal_policy=dict(window_days=180, half_life_days=14, rate=float(np.log(2)/14),
                             cadence='unchanged: every inherited issue'),
        architecture='unchanged PR65 MULTI_QUANTILE LightGBM; reuse exact frozen predictions',
        models={'R0': 'current frozen PR42 production Q90; May only; Running total-minus-elapsed naive transport',
                'R1': 'MULTI_QUANTILE Q90', 'R2': 'MULTI_QUANTILE Q95'},
        features='unchanged; Running explicitly conditioned on elapsed; no new features',
        selection_roles=ROLES, selection_unit='separate Pending and Running',
        selection_rule='candidate must have coverage >=0.90 AND overreserved_GPUh < requested_overreserved_GPUh in BOTH DEVELOPMENT and CALIBRATION. Among eligible candidates prefer those with GPU_coverage >=0.90 AND long_under <=0.15 in BOTH roles; then choose lower quantile. If none eligible retain R0 with no candidate adoption. Missing metrics fail closed.',
        selection_current_baseline='R0 unavailable in DEV/CAL; never replay May-trained models backwards; missed-slot superiority vs R0 cannot enter selection',
        evaluation_roles=EVAL, exposure='post-May-exposure follow-up model development; May historical diagnostic, not untouched confirmation',
        long_job='actual total runtime >4h; underprediction uses total for Pending and remaining for Running',
        slots='sum GPU * max(min(ceil(actual/900),96)-min(ceil(bound/900),96),0); 24h runtime-origin occupancy proxy',
        reserve='bound*GPU/3600; overreserve=max(bound-actual,0)*GPU/3600; walltime reference=max(requested-elapsed,0)',
        losses='both tau=.90 and tau=.95 pinball for every bound; Q95 never renamed Q90',
        no_scaling=True, no_capping=True, no_exclusions='retain all inherited Job-issues; only inherited invalid labels unscorable',
        uncertainty=dict(paired=True, draws=DRAW, seed=SEED, blocks=[1,7], unit='observed issue days, circular blocks in chronological order'),
        target_authority='offline event-time proxy only; request-version/ingestion provenance remains UNVERIFIED',
        TEMPORAL_POLICY_CHANGED=False, NEW_ARCHITECTURE_SEARCHED=False, PRODUCTION_PROMOTED=False,
        optimizer_executions=0, grid_executions=0))
    save('ENVIRONMENT.json', dict(time=now(), executable=sys.executable, python=platform.python_version(),
         numpy=np.__version__, pandas=pd.__version__, training_executions=0))
    print('REGISTRATION frozen; no new outcome metrics accessed', flush=True)

def label_join(raw):
    jobs = pd.read_parquet(BASE/'JOB_MEMBERSHIP.parquet', columns=['row_id','start_time','end_time','label_valid'])
    f = raw.merge(jobs, on='row_id', validate='many_to_one')
    f['runtime_seconds'] = (f.end_time-f.start_time).dt.total_seconds()
    f['actual_seconds'] = np.where(f.state.eq('RUNNING'), (f.end_time-f.issue_time).dt.total_seconds(), f.runtime_seconds)
    f['actual_seconds'] = f.actual_seconds.where(f.label_valid)
    return f

def load_candidates(roles):
    issue = pd.read_csv(BASE/'ISSUES.csv')
    parts = []
    for row in issue[issue.role.isin(roles)].itertuples():
        key = pd.Timestamp(row.issue_time).strftime('%Y%m%dT%H%M')
        path = BASE/'predictions/LGBM_180_14'/(key+'.parquet')
        receipt = read(BASE/'fits/LGBM_180_14'/key/'PREDICTION_RECEIPT.json')
        need(sha(path) == receipt['prediction_sha256'], 'PREDICTION_DRIFT')
        raw = pd.read_parquet(path)
        need(raw.role.eq(row.role).all(), 'ROLE_MISMATCH')
        need((raw.Q95 >= raw.Q90).all(), 'QUANTILE_ORDER')
        raw = label_join(raw)
        for arm, (column,tau) in MODELS.items():
            f = raw.copy(); f['arm'] = arm; f['bound_seconds'] = f[column]; f['nominal_quantile'] = tau
            parts.append(f)
    return pd.concat(parts, ignore_index=True)

def daily_values(f):
    f = f[f.actual_seconds.notna()]
    y,q,g = f.actual_seconds.to_numpy(),f.bound_seconds.to_numpy(),f.num_gpus_req.to_numpy()
    e = y-q; long = f.runtime_seconds.to_numpy()>14400; covered=y<=q
    rw=np.maximum(f.requested_seconds.to_numpy()-f.elapsed_seconds.to_numpy(),0)
    return np.array([len(f),g.sum(),covered.sum(),(covered*g).sum(),long.sum(),((~covered)&long).sum(),
        (g*np.maximum(np.minimum(np.ceil(y/900),96)-np.minimum(np.ceil(q/900),96),0)).sum(),
        (np.maximum(q-y,0)*g).sum()/3600,(q*g).sum()/3600,(rw*g).sum()/3600,
        (np.maximum(rw-y,0)*g).sum()/3600,np.maximum(.9*e,-.1*e).sum(),np.maximum(.95*e,-.05*e).sum()],float)

def summarize(v):
    n,g,c,cg,nlong,under,slots,over,reserve,requested,reqover,p90,p95=v
    return dict(N=int(n),GPU_weight=g,coverage=c/n,GPU_coverage=cg/g,long_N=int(nlong),
        long_under=under/nlong if nlong else np.nan,missed_GPU_slots=slots,overreserved_GPUh=over,
        reserved_GPUh=reserve,requested_reserved_GPUh=requested,requested_overreserved_GPUh=reqover,
        reserve_vs_requested=reserve/requested if requested else np.nan,
        overreserve_vs_requested=over/reqover if reqover else np.nan,pinball_Q90=p90/n,pinball_Q95=p95/n)

def stats(f):
    return {**summarize(daily_values(f)), 'unscorable_N':int(f.actual_seconds.isna().sum()), 'query_N':len(f)}

def metric_table(f):
    rows=[]
    for (role,arm,state),g in f.groupby(['role','arm','state']):
        rows.append(dict(role=role,arm=arm,state=state,nominal_quantile=g.nominal_quantile.iloc[0],**stats(g)))
    return pd.DataFrame(rows)

def choose(table):
    choices={}; proof=[]
    for state in ['PENDING','RUNNING']:
        candidates=[]
        for arm in MODELS:
            g=table[table.state.eq(state)&table.arm.eq(arm)]
            need(set(g.role)==set(ROLES), 'SELECTION_SPLIT_INCOMPLETE')
            eligible=bool((g.coverage>=.9).all() and (g.overreserved_GPUh<g.requested_overreserved_GPUh).all())
            preferred=bool(eligible and (g.GPU_coverage>=.9).all() and (g.long_under<=.15).all())
            proof.append(dict(state=state,arm=arm,eligible=eligible,preferred=preferred))
            if eligible:candidates.append((not preferred,MODELS[arm][1],arm))
        choices[state]=min(candidates)[2] if candidates else 'R0'
    return choices,proof

def select():
    verify_sources(); need(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(), 'ALREADY_SELECTED')
    f=load_candidates(ROLES); table=metric_table(f)
    table.to_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv',index=False)
    choices,proof=choose(table)
    save('FINAL_SELECTION_FREEZE.json',dict(time=now(),selected_by_state=choices,eligibility=proof,
        source_sha256=sha(ROOT/'REGISTRATION.json'), code_hashes=source_hashes(),
        selection_metrics_sha256=sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv'),
        evaluation_metrics_computed=False, May_already_exposed=True,
        R0_pre_evaluation_metrics_available=False,production_adoption_authorized=False))
    print(json.dumps(dict(selected_by_state=choices,eligibility=proof),indent=2),flush=True)

def paired(a,b,block):
    need(a.job_issue_id.is_unique and b.job_issue_id.is_unique, 'DUPLICATE_PAIRS')
    common=set(a.job_issue_id)&set(b.job_issue_id)
    aa=a[a.job_issue_id.isin(common)&a.actual_seconds.notna()].sort_values('job_issue_id')
    bb=b[b.job_issue_id.isin(common)&b.actual_seconds.notna()].sort_values('job_issue_id')
    need(np.array_equal(aa.job_issue_id,bb.job_issue_id) and np.array_equal(aa.actual_seconds,bb.actual_seconds), 'PAIR_MISMATCH')
    va=np.array([daily_values(g) for _,g in aa.groupby('issue_time',sort=True)])
    vb=np.array([daily_values(g) for _,g in bb.groupby('issue_time',sort=True)])
    n=len(va);need(n>0,'EMPTY_PAIRS')
    def difference(x,y):
        sa,sb=summarize(x.sum(0)),summarize(y.sum(0))
        return [sa[k]-sb[k] for k in METRICS]
    point=difference(va,vb);rng=np.random.default_rng(SEED);samples=[]
    for _ in range(DRAW):
        starts=rng.integers(n,size=int(np.ceil(n/block)))
        idx=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        samples.append(difference(va[idx],vb[idx]))
    samples=np.asarray(samples);rows=[]
    for i,metric in enumerate(METRICS):
        lo,hi=np.nanquantile(samples[:,i],[.025,.975])
        rows.append(dict(metric=metric,delta=point[i],CI95_low=lo,CI95_high=hi,block_days=block,draws=DRAW,
            N_days=n,N_pairs=len(aa),candidate_unmatched=len(a)-len(aa),reference_unmatched=len(b)-len(bb)))
    return rows

def evaluate():
    verify_sources();freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json')
    need(freeze['code_hashes']==source_hashes(),'FINAL_CODE_DRIFT')
    need(sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')==freeze['selection_metrics_sha256'],'SELECTION_DRIFT')
    need(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'EVALUATION_ALREADY_COMPLETE')
    f=load_candidates(EVAL)
    legacy=pd.read_parquet(BASE/'PREDICTIONS.parquet')
    r0=legacy[legacy.model.eq('PR42_FROZEN_LGBM_NAIVE_REMAINING')].copy()
    need(r0.role.eq('MAY_HISTORICAL').all(),'R0_OUTSIDE_AUTHORITY')
    r0['arm']='R0';r0['bound_seconds']=r0.Q90;r0['nominal_quantile']=.9
    common_cols=list(f.columns)
    f=pd.concat([f,r0[common_cols]],ignore_index=True)
    need(np.isfinite(f.bound_seconds).all() and (f.bound_seconds>=0).all(),'BAD_BOUND')
    f.to_parquet(ROOT/'BOUND_PREDICTIONS.parquet',index=False)
    table=metric_table(f);table.to_csv(ROOT/'MODEL_METRICS.csv',index=False)
    rows=[]
    running=f[f.state.eq('RUNNING')].copy();elapsed=running.elapsed_seconds/3600
    running['regime']=np.select([elapsed<1,elapsed<2,elapsed<4,elapsed<=8],['<1h','1-2h','2-4h','4-8h'],default='>8h')
    for (role,arm,regime),g in running.groupby(['role','arm','regime']):
        rows.append(dict(role=role,arm=arm,elapsed_regime=regime,**stats(g)))
    pd.DataFrame(rows).to_csv(ROOT/'RUNNING_ELAPSED_METRICS.csv',index=False)
    ci=[];matched=[]
    for role,d in f.groupby('role'):
        comparisons=[('R2','R1')]+([('R1','R0'),('R2','R0')] if role=='MAY_HISTORICAL' else [])
        for state in ['PENDING','RUNNING']:
            for candidate,reference in comparisons:
                a=d[d.state.eq(state)&d.arm.eq(candidate)];b=d[d.state.eq(state)&d.arm.eq(reference)]
                need(set(a.job_issue_id)==set(b.job_issue_id),'NONIDENTICAL_EVAL_COHORT')
                ma,mb=stats(a),stats(b)
                matched.append(dict(role=role,state=state,candidate=candidate,reference=reference,
                    missed_slots_reduction=1-ma['missed_GPU_slots']/mb['missed_GPU_slots'] if mb['missed_GPU_slots'] else np.nan,
                    overreserve_delta_GPUh=ma['overreserved_GPUh']-mb['overreserved_GPUh']))
                for block in [1,7]:
                    ci += [dict(role=role,state=state,candidate=candidate,reference=reference,**r) for r in paired(a,b,block)]
    pd.DataFrame(ci).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    pd.DataFrame(matched).to_csv(ROOT/'MATCHED_COMPARISONS.csv',index=False)
    save('EVALUATION_COMPLETE.json',dict(time=now(),N_rows=len(f),predictions_sha256=sha(ROOT/'BOUND_PREDICTIONS.parquet'),
        final_freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),evaluation_reselection=False,
        exposure='historical diagnostic only; no untouched confirmation'))
    print('EVALUATION_COMPLETE',len(f),flush=True)

def audit():
    verify_sources(); need((ROOT/'EVALUATION_COMPLETE.json').exists(),'EVAL_INCOMPLETE')
    jobs=pd.read_parquet(BASE/'JOB_MEMBERSHIP.parquet');issues=pd.read_csv(BASE/'ISSUES.csv')
    inherited=pd.read_parquet(BASE/'ISSUE_MEMBERSHIP.parquet');ledger=[]
    for row in issues.itertuples():
        t=pd.Timestamp(row.issue_time);key=t.strftime('%Y%m%dT%H%M');folder=BASE/'fits/LGBM_180_14'/key
        metadata=read(folder/'MEMBERSHIP.json');path=folder/'train_membership.npz'
        need(sha(path)==metadata['row_ids_sha256'],'MEMBERSHIP_HASH')
        actual=np.load(path)['row_ids']
        expected=jobs[jobs.label_valid&jobs.end_time.lt(t)&jobs.end_time.ge(t-pd.Timedelta(days=180))].sort_values(['end_time','job_id'],kind='stable')
        need(np.array_equal(actual,expected.row_id),'INEXACT_MEMBERSHIP')
        raw=pd.read_parquet(BASE/'predictions/LGBM_180_14'/(key+'.parquet'))
        query=inherited[inherited.issue_time.eq(t)]
        need(set(raw.job_issue_id)==set(query.job_issue_id),'QUERY_EXCLUSION')
        need(raw.submit_time.le(t).all(),'FUTURE_SUBMIT_FEATURE')
        need(not any(c in raw for c in ['actual_seconds','runtime_seconds','end_time','start_time']), 'LABEL_IN_PREDICTION_INPUT')
        expected_query=jobs[jobs.submit_time.le(t)&(jobs.end_time.gt(t)|jobs.end_time.isna())]
        need(set(query.row_id)==set(expected_query.row_id),'QUERY_MEMBERSHIP_INEXACT')
        rp=raw[raw.state.eq('RUNNING')]
        rj=rp.merge(jobs[['row_id','start_time']],on='row_id',validate='one_to_one')
        need(np.array_equal(rj.elapsed_seconds,(t-rj.start_time).dt.total_seconds()),'ELAPSED_FEATURE_MISMATCH')
        pre=read(folder/'RUNNING/preprocessing.json')
        need('elapsed_seconds' in pre['input_features'],'ELAPSED_NOT_TRAINED')
        h=pd.util.hash_pandas_object(expected.job_id,index=False).to_numpy()
        elapsed=np.array([1800.,5400.,10800.,21600.,43200.])[h%5]
        runtime=(expected.end_time-expected.start_time).dt.total_seconds()
        landmark=expected[runtime.to_numpy()>elapsed]
        ids_hash=hashlib.sha256(('\n'.join(sorted(map(str,landmark.job_id)))+'\n').encode()).hexdigest()
        need(len(landmark)==pre['training_N'] and ids_hash==pre['landmark_jobs_hash'],'RUNNING_LANDMARK_MEMBERSHIP')
        ledger.append(dict(issue_time=t,role=row.role,N_training=len(expected),N_running_landmarks=len(landmark),
            N_query=len(raw),latest_training_end=expected.end_time.max(),earliest_training_end=expected.end_time.min(),
            membership_path=str(path.relative_to(ROOT.parent)),membership_sha256=sha(path),
            prediction_sha256=sha(BASE/'predictions/LGBM_180_14'/(key+'.parquet')),feature_maturity_event_time_pass=True))
    pd.DataFrame(ledger).to_csv(ROOT/'CAUSAL_MEMBERSHIP_LEDGER.csv',index=False)
    f=pd.read_parquet(ROOT/'BOUND_PREDICTIONS.parquet')
    expected_eval=inherited[inherited.role.isin(EVAL)]
    for arm in MODELS:
        a=f[f.arm.eq(arm)];need(set(a.job_issue_id)==set(expected_eval.job_issue_id),'EVAL_EXCLUSION')
        raw=load_candidates(EVAL);b=raw[raw.arm.eq(arm)].sort_values('job_issue_id');a=a.sort_values('job_issue_id')
        need(np.array_equal(a.bound_seconds,b.bound_seconds),'BOUND_CHANGED')
    r0=f[f.arm.eq('R0')];need(set(r0.job_issue_id)==set(expected_eval[expected_eval.role.eq('MAY_HISTORICAL')].job_issue_id),'R0_EXCLUSION')
    parent_audit('PARENT_PRESERVATION_END.json')
    save('VALIDATION.json',dict(time=now(),PASS=True,exact_fit_memberships=len(ledger),exact_query_memberships=len(ledger),
        running_landmark_membership_checked=True,feature_available_event_time_le_issue=True,
        train_job_end_strictly_lt_issue=True,feature_request_version_and_ingestion='UNVERIFIED',
        no_new_training=True,no_quantile_relabel=True,no_scaling_or_capping=True,all_evaluation_rows_retained=True,
        temporal_policy_changed=False,new_architecture_searched=False,production_promoted=False,
        optimizer_executions=0,grid_executions=0))
    print('VALIDATION PASS',len(ledger),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['register','select','evaluate','audit']);args=parser.parse_args()
    globals()[args.stage]()
