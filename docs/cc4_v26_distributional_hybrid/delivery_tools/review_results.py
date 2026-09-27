"""Delivery review: independently check selection, all strata, and support flags."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent/'cc4_v2_hourly_future_workload'
Z=np.load(BASE/'DATA.npz');Y=Z['y'];D=Z['days'].astype(str);L=pd.read_csv(BASE/'DAY_LEDGER.csv')
P=np.load(ROOT/'FROZEN_PREDICTIONS.npz');F=json.loads((ROOT/'FINAL_SELECTION_FREEZE.json').read_text());B=json.loads((ROOT/'PROTOCOL.json').read_text())['burst_threshold']
ARMS=['B0','B1','B2','B3','B4','B5'];roles=['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','MAY_HISTORICAL']
def ids(r):return np.flatnonzero(L.split.eq(r)&L.eligible)
def score(y,p):
    n=y.size;v=y-p[...,1];total=y.sum();pos=y>0;burst=y>B
    return dict(N_hours=n,actual_GPUh=total,Q90_pinball=np.maximum(.9*v,-.1*v).mean() if n else np.nan,
        Q90_coverage=(v<=0).mean() if n else np.nan,calibration_error=abs((v<=0).mean()-.9) if n else np.nan,
        requirement_ratio=p[...,1].sum()/total if total else np.nan,Q50_MAE=np.abs(y-p[...,0]).mean() if n else np.nan,
        Q50_WAPE=np.abs(y-p[...,0]).sum()/total if total else np.nan,
        positive_coverage=(v[pos]<=0).mean() if pos.any() else np.nan,burst_coverage=(v[burst]<=0).mean() if burst.any() else np.nan)
def gate(m,b):return .88<=m['Q90_coverage']<=.92 and m['requirement_ratio']<2 and m['Q90_pinball']<=b['Q90_pinball'] and m['burst_coverage']>b['burst_coverage']
count=0;maxerror=0.
for file in ['MODEL_METRICS.csv','STRATIFIED_METRICS.csv','HORIZON_METRICS.csv']:
    for row in pd.read_csv(ROOT/file).itertuples():
        ix=ids(row.role);y=Y[ix];p=P[row.arm][ix]
        if file.startswith('STRATIFIED'):
            mask={'zero':y==0,'positive':y>0,'burst':y>B,'body':(y>0)&(y<=B),'hybrid_gate':P['risk'][ix]>=F['gate'],'normal_gate':P['risk'][ix]<F['gate']}[row.stratum]
            y,p=y[mask],p[mask]
        if file.startswith('HORIZON'):y,p=y[:,row.hour],p[:,row.hour]
        for k,v in score(y,p).items():
            a=getattr(row,k);np.testing.assert_allclose(v,a,atol=1e-9,rtol=1e-12,equal_nan=True)
            if np.isfinite(v):maxerror=max(maxerror,abs(v-a))
        count+=1
candidates=[];ix=ids('DEVELOPMENT')
for threshold in [.1,.2,.3]:
    q=np.where((P['risk'][ix]>=threshold)[...,None],P['B1'][ix],P['B0'][ix]);candidates.append(dict(arm='B2',parameter=threshold,**score(Y[ix],q)))
for w in [.25,.5,.75]:candidates.append(dict(arm='B3',parameter=w,**score(Y[ix],(1-w)*P['B0'][ix]+w*P['B5'][ix])))
for arm,param in [('B2','gate'),('B3','weight')]:
    rows=[r for r in candidates if r['arm']==arm];safe=[r for r in rows if r['requirement_ratio']<2]
    win=min(safe or rows,key=lambda r:(r['Q90_pinball'],r['calibration_error'],r['requirement_ratio'],r['parameter']))
    assert win['parameter']==F[param]
elig={a:all(gate(score(Y[ids(r)],P[a][ids(r)]),score(Y[ids(r)],P['B0'][ids(r)])) for r in roles[:2]) for a in ARMS[1:]}
assert elig==F['eligibility']
eligible=[a for a in ARMS[1:] if elig[a]]
def rank(a):
    mm=[score(Y[ids(r)],P[a][ids(r)]) for r in roles[:2]];bb=[score(Y[ids(r)],P['B0'][ids(r)]) for r in roles[:2]]
    return np.mean([m['Q90_pinball']/b['Q90_pinball'] for m,b in zip(mm,bb)]),np.mean([m['calibration_error'] for m in mm]),np.mean([m['requirement_ratio'] for m in mm]),a
assert F['primary']==(min(eligible,key=rank) if eligible else 'B0')
ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');support={}
for a in ARMS[1:]:
    good=elig[a]
    for r in roles[2:]:
        m=score(Y[ids(r)],P[a][ids(r)]);b=score(Y[ids(r)],P['B0'][ids(r)])
        rows=ci[(ci.role==r)&(ci.arm==a)&(ci.block_days==7)]
        loss=rows[rows.metric=='Q90_pinball'].iloc[0];burst=rows[rows.metric=='burst_coverage'].iloc[0]
        good=good and gate(m,b) and loss.invalid_draws==burst.invalid_draws==0 and loss.high<0 and burst.low>0
    support[a]=bool(good)
v=json.loads((ROOT/'FINAL_VERDICT.json').read_text());assert v['arm_support']==support
for key,arm in [('DISTRIBUTIONAL_MODEL_SUPPORTED','B1'),('HYBRID_SUPERIOR_TO_LGBM','B2'),('ENSEMBLE_SUPERIOR_TO_LGBM','B3')]:assert v[key]==support[arm]
for row in ci.itertuples():
    ii=ids(row.role);value=score(Y[ii],P[row.arm][ii])[row.metric]-score(Y[ii],P['B0'][ii])[row.metric]
    np.testing.assert_allclose(value,row.delta,atol=1e-9,rtol=1e-12,equal_nan=True)
times=[json.loads((ROOT/f).read_text())['time'] for f in ['CODE_FREEZE.json','DISTRIBUTION_PARAMETERS.json','FINAL_SELECTION_FREEZE.json','EVALUATION_COMPLETE.json']]
assert list(pd.to_datetime(times,utc=True))==sorted(pd.to_datetime(times,utc=True))
assert json.loads((ROOT/'EVALUATION_COMPLETE.json').read_text())['selection_sha256']==hashlib.sha256((ROOT/'FINAL_SELECTION_FREEZE.json').read_bytes()).hexdigest()
with (ROOT/'RESULT_REVIEW.json').open('x',encoding='utf-8') as f:json.dump(dict(PASS=True,time=pd.Timestamp.now(tz='UTC').isoformat(),metric_rows=count,maximum_metric_error=maxerror,selection_reproduced=True,all_support_flags_reproduced=True,freeze_chronology=True),f,indent=2)
print('RESULT REVIEW PASS',count,maxerror)
