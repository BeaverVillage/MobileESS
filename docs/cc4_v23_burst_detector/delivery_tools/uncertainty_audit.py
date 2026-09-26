"""Independent post-freeze bootstrap audit from stored hourly predictions.

Does not import study.py, call its metric/bootstrap functions, fit a model,
change a prediction, or mutate scientific evidence. AP is implemented directly
with tied-score groups, independently of sklearn's average_precision_score.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
NAMES=['Q90_pinball','coverage','positive_coverage','burst_coverage',
       'requirement_ratio','detector_recall','precision','false_positive_rate',
       'pinball_minus_2pct_margin','PR_AUC']

def need(ok,message):
    if not ok:raise AssertionError(message)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def average_precision_binary(labels,scores):
    """Non-interpolated AP: sum recall increments times tied-threshold precision."""
    labels=np.asarray(labels,dtype=bool).ravel();scores=np.asarray(scores,float).ravel()
    need(len(labels)==len(scores) and np.isfinite(scores).all(),'BAD_AP_INPUT')
    positives=labels.sum();need(positives>0,'AP_NO_POSITIVES')
    order=np.argsort(-scores,kind='stable');ranked=labels[order];ranked_scores=scores[order]
    endpoints=np.r_[np.flatnonzero(ranked_scores[:-1]!=ranked_scores[1:]),len(labels)-1]
    tp=np.cumsum(ranked)[endpoints]
    increments=np.diff(np.r_[0,tp])/positives
    precision=tp/(endpoints+1)
    return float(np.dot(increments,precision))

def quantities(y,q,risk,threshold,burst):
    """Direct pooled-hour metrics; no daily-vector helper reused from study."""
    y=np.asarray(y,float).ravel();q=np.asarray(q,float).ravel();risk=np.asarray(risk,float).ravel()
    positive=y>0;bursty=y>burst;covered=q>=y;gate=risk>=threshold
    need(positive.any() and bursty.any() and (~bursty).any() and y.sum()>0,'UNDEFINED_AUDIT_METRIC')
    errors=y-q;loss=np.where(errors>=0,.9*errors,-.1*errors)
    return np.array([loss.mean(),covered.mean(),covered[positive].mean(),covered[bursty].mean(),
        q.sum()/y.sum(),gate[bursty].mean(),bursty[gate].mean() if gate.any() else 0.,
        gate[~bursty].mean(),average_precision_binary(bursty,risk)],float)

def differences(y,q,p,t,bq,bp,burst):
    candidate=quantities(y,q,p,t,burst);baseline=quantities(y,bq,bp,.1,burst)
    delta=candidate-baseline
    return np.r_[delta[:8],candidate[0]-1.02*baseline[0],delta[8]]

def main():
    need((ROOT/'EVALUATION_COMPLETE.json').exists(),'WAIT_FOR_EVALUATION_COMPLETE')
    need(not (ROOT/'UNCERTAINTY_AUDIT.json').exists(),'AUDIT_ALREADY_RECORDED')
    protocol=read(ROOT/'PROTOCOL.json');freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');complete=read(ROOT/'EVALUATION_COMPLETE.json')
    for name,digest in freeze['code'].items():need(sha(ROOT/name)==digest,'FROZEN_SOURCE_DRIFT '+name)
    need(sha(ROOT/'PREDICTIONS.parquet')==complete['prediction_sha256'],'PREDICTION_DIGEST')
    need(sha(ROOT/'FINAL_SELECTION_FREEZE.json')==complete['freeze_sha256'],'FREEZE_DIGEST')
    # Tied-score AP hand examples: all ties reduce AP to prevalence.
    need(average_precision_binary([1,0],[.5,.5])==.5,'AP_TIE_TEST')
    need(np.isclose(average_precision_binary([1,0,1],[.8,.7,.6]),5/6),'AP_STEP_TEST')
    p=pd.read_parquet(ROOT/'PREDICTIONS.parquet');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv')
    need(len(ci)==80,'EXPECTED_80_CI_ROWS')
    key=['role','model','metric','block_observed_days'];need(not ci.duplicated(key).any(),'DUPLICATE_CI')
    burst=float(protocol['burst_threshold']['value']);seed=int(protocol['bootstrap']['seed']);draws=int(protocol['bootstrap']['draws'])
    need(draws==2000 and protocol['bootstrap']['blocks_observed_days']==[1,7],'BOOTSTRAP_PROTOCOL_DRIFT')
    findings=[];max_error=0.;old_detector_days=0
    for role in sorted(ci.role.unique()):
        rolep=p[p.role.eq(role)];baseline=rolep[rolep.model.eq('C0')].sort_values(['day','hour'])
        need(baseline.threshold.eq(.1).all(),'REFERENCE_IS_NOT_OLD_DETECTOR_GATE_010')
        need(not baseline.duplicated(['day','hour']).any(),'DUPLICATE_BASELINE_HOUR')
        days=sorted(baseline.day.unique());n=len(days)
        need(len(baseline)==n*24 and all(g.hour.tolist()==list(range(24)) for _,g in baseline.groupby('day')),'INCOMPLETE_DAYS')
        for day,g in baseline.groupby('day',sort=True):
            old=np.load(ROOT.parent/'cc4_v22_burst_tail'/'raw'/(str(day)+'.npz'))['risk']
            need(np.array_equal(g.risk.to_numpy(),old),'C0_NOT_OLD_DETECTOR '+str(day));old_detector_days+=1
        y=baseline.actual.to_numpy().reshape(n,24);bq=baseline.Q90.to_numpy().reshape(n,24);bp=baseline.risk.to_numpy().reshape(n,24)
        for model in ['C1','C2']:
            f=rolep[rolep.model.eq(model)].sort_values(['day','hour'])
            need(np.array_equal(f[['day','hour']].to_numpy(),baseline[['day','hour']].to_numpy()),'NOT_PAIRED_HOURS')
            need(np.array_equal(f.actual.to_numpy(),baseline.actual.to_numpy()),'PAIR_TARGET_DRIFT')
            threshold=float(freeze['choices'][model]['config']['threshold'])
            need(f.threshold.eq(threshold).all(),'FROZEN_THRESHOLD_DRIFT')
            q=f.Q90.to_numpy().reshape(n,24);risk=f.risk.to_numpy().reshape(n,24)
            point=differences(y,q,risk,threshold,bq,bp,burst)
            for block in [1,7]:
                # Draw one sample at a time, independent of the study's batched
                # index construction and daily sufficient-statistic reduction.
                rng=np.random.default_rng(seed);samples=[]
                for _ in range(draws):
                    starts=rng.integers(0,n,size=int(np.ceil(n/block)))
                    indices=np.concatenate([(start+np.arange(block))%n for start in starts])[:n]
                    samples.append(differences(y[indices],q[indices],risk[indices],threshold,bq[indices],bp[indices],burst))
                samples=np.asarray(samples);need(np.isfinite(samples).all(),'NONFINITE_AUDIT_RESAMPLE')
                lower,upper=np.quantile(samples,[.025,.975],axis=0)
                for j,metric in enumerate(NAMES):
                    stored=ci[ci.role.eq(role)&ci.model.eq(model)&ci.metric.eq(metric)&ci.block_observed_days.eq(block)]
                    need(len(stored)==1,'MISSING_CI_ROW');stored=stored.iloc[0]
                    actual=np.array([point[j],lower[j],upper[j]])
                    expected=stored[['delta','CI95_low','CI95_high']].to_numpy(float)
                    error=float(np.max(np.abs(actual-expected)));max_error=max(max_error,error)
                    need(np.allclose(actual,expected,rtol=2e-12,atol=1e-9),'CI_MISMATCH '+str((role,model,metric,block,actual,expected)))
                    need(stored.N_days==n and stored.draws==draws,'CI_MEMBERSHIP_COUNT')
                    findings.append(dict(role=role,model=model,metric=metric,block_observed_days=block,
                        delta=float(actual[0]),CI95_low=float(actual[1]),CI95_high=float(actual[2]),max_abs_difference=error,PASS=True))
    result=dict(time=pd.Timestamp.now(tz='UTC').isoformat(),PASS=True,rows_checked=len(findings),bootstrap_samples_recomputed=16000,
        old_detector_reference_days_checked=old_detector_days,max_absolute_difference=max_error,
        method='Direct pooled hourly metrics per paired resample; independent tied-score noninterpolated average precision; ratios recomputed each draw',
        reference='C0 forecast / PR67 D0 old detector with gate0.10',
        source_sha256=sha(Path(__file__)),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),uncertainty_sha256=sha(ROOT/'PAIRED_UNCERTAINTY.csv'),
        frozen_code_unchanged=True,findings=findings,
        interpretation_limits=['Conditional on frozen forecasts; excludes selector/model-selection uncertainty',
            'No multiplicity-adjusted simultaneous CI; many candidate/metric comparisons are descriptive',
            'May was already exposed; not untouched confirmation',
            '2% pinball margin is candidate loss minus1.02times baseline loss per resample; CI upper<0 would support conditional noninferiority only',
            'Seven observed-day blocks may not capture longer dependencies'])
    with (ROOT/'UNCERTAINTY_AUDIT.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False)
    print('UNCERTAINTY_AUDIT PASS',len(findings),'max_abs_difference',max_error,flush=True)

if __name__=='__main__':main()
