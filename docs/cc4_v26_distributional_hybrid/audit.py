"""Separate-formula source, checkpoint, probability and bootstrap replay audit."""
import os
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import argparse,hashlib,json,tarfile,gzip,time
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import lognorm
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'cc4_v2_hourly_future_workload';REFIT=ROOT.parent/'cc4_v21_causal_refit_hurdle'
Z=np.load(BASE/'DATA.npz');X,Y,D=Z['X'],Z['y'],Z['days'].astype(str);L=pd.read_csv(BASE/'DAY_LEDGER.csv')
AV=pd.to_datetime(L.label_matured_at,utc=True);ISS=pd.to_datetime(L.issue_time,utc=True)
BURST=json.loads((BASE/'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))['TRAIN_positive_Q95_burst_threshold_GPUh']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def write(p,v):
    with (ROOT/p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,allow_nan=False)
def membership(i):return np.flatnonzero((AV<ISS.iloc[i])&(ISS<ISS.iloc[i])&L.split.ne('PURGE'))
def weights(tr,i):return np.asarray(np.exp2(-np.maximum((ISS.iloc[i]-pd.to_datetime(D[tr],utc=True)).total_seconds()/86400,0)/30))
def role_ids(role):return np.flatnonzero(L.split.eq(role)&L.eligible)


def reuse():
    manifest=json.loads((REFIT/'FIT_AUDIT_BUNDLE_MEMBERS.json').read_text(encoding='utf-8'))
    assert sha(REFIT/'FIT_AUDIT_BUNDLE.tar.gz')==manifest['archive_sha256']
    expected={r['path']:r for r in manifest['members']};cache={};cost=[];count=0;members=[]
    seeds=[20260924,20260925,20260926]
    for fam in ['LGBM','TFT','DEEPAR']:
        for seed in ([seeds[0]] if fam=='LGBM' else seeds):cache[f'{fam}_weighted_c1_s{seed}']=np.load(REFIT/'predictions'/f'{fam}_weighted_c1_s{seed}.npz')['q']
    with tarfile.open(REFIT/'FIT_AUDIT_BUNDLE.tar.gz') as archive:
        for entry in archive:
            if not entry.isfile():continue
            content=archive.extractfile(entry).read();assert hashlib.sha256(content).hexdigest()==expected[entry.name]['sha256']
            parts=entry.name.split('/');tag=parts[1]
            if tag not in cache:continue
            name=parts[-1];i=int(np.flatnonzero(D==parts[2]).item());tr=membership(i)
            if name=='MEMBERSHIP.json':
                m=json.loads(content);assert m['train_days']==D[tr].tolist();assert pd.Timestamp(m['cutoff'])==ISS.iloc[i]
                # PR64 serialized pandas Index as a truncated display string.
                # Validate that exact display, reconstruct full numeric weights from frozen formula.
                if isinstance(m['weights'],str):assert m['weights']==str(pd.Index(weights(tr,i)))
                else:np.testing.assert_array_equal(m['weights'],weights(tr,i))
                assert m['policy']=='weighted' and m['cadence']==1
                target=ROOT/'reused_numeric_membership'/f'{D[i]}.npz'
                if not target.exists():
                    target.parent.mkdir(exist_ok=True);np.savez_compressed(target,day_indices=tr,weights=weights(tr,i))
                members.append(dict(tag=tag,day_index=i,day=D[i],membership_sha256=hashlib.sha256(content).hexdigest(),training_days=len(tr)))
            elif name.startswith('PREDICTION_') and name.endswith('.json'):
                r=json.loads(content);ix=[int(np.flatnonzero(D==day).item()) for day in r['issued_days']]
                assert hashlib.sha256(cache[tag][ix].tobytes()).hexdigest()==r['forecast_sha256'];assert r['evaluation_labels_in_fit']==0
                count+=1
                if tag.startswith('LGBM'):cost.append(dict(arm='B0',seed=seeds[0],day=D[i],phase='historical_reuse',training_seconds=None,inference_seconds=None,total_fit_forecast_seconds=r['seconds']))
            elif name=='receipt.json':
                r=json.loads(content);assert r['epochs_run']==(8 if tag.startswith('TFT') else 18)
                assert r['learning_rate']==.001 and r['N_training_days']==len(tr)
                assert all(h['dev_Q90_pinball_GPUh'] is None for h in r['history'])
                cost.append(dict(arm='B4' if tag.startswith('TFT') else 'B5',seed=r['seed'],day=D[i],phase='historical_reuse',
                    training_seconds=r['training_seconds'],inference_seconds=r['inference_seconds'],total_fit_forecast_seconds=r['training_seconds']+r['inference_seconds']))
    assert count==7*273 and len(members)==7*273
    pd.DataFrame(members).to_csv(ROOT/'REUSED_EXACT_MEMBERSHIP.csv',index=False,lineterminator='\n')
    pd.DataFrame(cost).to_csv(ROOT/'HISTORICAL_COMPUTATIONAL_COST.csv',index=False,lineterminator='\n')
    write('REUSE_AUDIT.json',dict(PASS=True,time=pd.Timestamp.now(tz='UTC').isoformat(),prediction_receipts=count,exact_memberships=len(members),
        bundle_members_checked=len(expected),prediction_arrays_byte_bound=True,new_neural_training_executions=0,
        limitations='Original weight receipts are truncated pandas Index display strings: exact display checked, full numeric weights reconstructed from frozen code and dates and saved, not claimed as historical numeric receipt bytes. Compact model/128-sample scope; no fresh neural checkpoint replay or hardware-comparable timings'))
    print('REUSE PASS',count,flush=True)


def scores(y,q):
    e=y-q[...,1];pos=y>0;burst=y>BURST;total=y.sum();n=y.size
    return dict(Q90_pinball=np.maximum(.9*e,-.1*e).mean(),Q90_coverage=(e<=0).mean(),
        requirement_ratio=q[...,1].sum()/total if total else np.nan,
        burst_coverage=(e[burst]<=0).mean() if burst.any() else np.nan,
        positive_coverage=(e[pos]<=0).mean() if pos.any() else np.nan,Q50_MAE=np.abs(y-q[...,0]).mean())


def final():
    assert read('REUSE_AUDIT.json')['PASS'];f=read('FINAL_SELECTION_FREEZE.json');sigma=read('DISTRIBUTION_PARAMETERS.json')['sigma']
    for name,digest in f['code'].items():assert sha(ROOT/name)==digest
    assert sha(ROOT/'PROTOCOL.json')==f['protocol_sha256'];assert sha(ROOT/'DISTRIBUTION_PARAMETERS.json')==f['distribution_sha256']
    for name,digest in read('SOURCE_MANIFEST.json')['files'].items():assert sha(ROOT.parent/name)==digest
    residual=pd.read_parquet(ROOT/'DISPERSION_OOS_MEMBERSHIP.parquet');cut=role_ids('DEVELOPMENT')[0]
    assert L.iloc[residual.day_index].split.eq('TRAIN').all();assert (pd.to_datetime(residual.label_matured_at,utc=True)<ISS.iloc[cut]).all()
    rr=np.log(residual.actual_GPUh)-residual.predicted_log_location
    np.testing.assert_array_equal(rr,residual.residual)
    np.testing.assert_allclose(np.sqrt(np.average(rr**2,weights=residual.weight)),sigma,rtol=0,atol=1e-14)
    for row in residual.itertuples():
        assert row.actual_GPUh==Y[row.day_index,row.hour];assert row.weight==weights(np.array([row.day_index]),cut)[0]
    pred=np.load(ROOT/'FROZEN_PREDICTIONS.npz');cost=[];models=0;members=0;maxdiff=0.
    for receipt in sorted((ROOT/'fits').glob('*/*/RECEIPT.json')):
        r=json.loads(receipt.read_text());i=r['day_index'];folder=receipt.parent;tr=membership(i)
        m=np.load(folder/'TRAIN_MEMBERSHIP.npz');np.testing.assert_array_equal(m['day_indices'],tr);np.testing.assert_array_equal(m['weights'],weights(tr,i))
        assert sha(folder/'TRAIN_MEMBERSHIP.npz')==r['membership_sha256'];assert sha(folder/'PARAMETERS.npz')==r['parameters_sha256']
        z=np.load(folder/'PARAMETERS.npz');params=[]
        for name,key in [('occurrence','p'),('positive_location','mu')]:
            path=folder/(name+'.txt.gz');assert sha(path)==r['model_sha256'][path.name]
            booster=lgb.Booster(model_str=gzip.decompress(path.read_bytes()).decode());v=booster.predict(X[i],num_threads=1)
            np.testing.assert_array_equal(v,z[key]);params.append(v);models+=1
        p,mu=params
        if folder.parent.name=='train_oos':
            part=residual[residual.day_index==i]
            np.testing.assert_array_equal(part.predicted_log_location.to_numpy(),mu[part.hour.to_numpy()])
        else:
            q=np.zeros((24,2))
            for k,tau in enumerate([.5,.9]):
                mask=tau>1-p;q[mask,k]=lognorm.ppf((tau-1+p[mask])/p[mask],s=sigma,scale=np.exp(mu[mask]))
                positive=q[:,k]>0;cdf=1-p+p*lognorm.cdf(q[:,k],s=sigma,scale=np.exp(mu))
                np.testing.assert_allclose(cdf[positive],tau,atol=2e-14,rtol=0)
            maxdiff=max(maxdiff,float(np.max(abs(q-pred['B1'][i]))));np.testing.assert_allclose(q,pred['B1'][i],atol=1e-10,rtol=1e-13)
            risk=p*lognorm.sf(BURST,s=sigma,scale=np.exp(mu));np.testing.assert_allclose(risk,pred['risk'][i],atol=1e-14,rtol=1e-13)
        members+=1;cost.append(dict(arm='B1',seed=20260924,day=D[i],phase=folder.parent.name,training_seconds=r['training_seconds'],inference_seconds=r['inference_seconds'],total_fit_forecast_seconds=r['training_seconds']+r['inference_seconds']))
    oos=np.flatnonzero(D>='2024-09-01')
    def cached(fam,seed):return np.load(REFIT/'predictions'/f'{fam}_weighted_c1_s{seed}.npz')['q']
    np.testing.assert_array_equal(pred['B0'][oos],cached('LGBM',20260924)[oos])
    for a,fam in [('B4','TFT'),('B5','DEEPAR')]:np.testing.assert_array_equal(pred[a][oos],np.mean([cached(fam,s) for s in [20260924,20260925,20260926]],axis=0)[oos])
    gate=pred['risk'][oos]>=f['gate'];np.testing.assert_array_equal(pred['B2'][oos],np.where(gate[...,None],pred['B1'][oos],pred['B0'][oos]))
    np.testing.assert_array_equal(pred['B3'][oos],(1-f['weight'])*pred['B0'][oos]+f['weight']*pred['B5'][oos])
    mm=pd.read_csv(ROOT/'MODEL_METRICS.csv');metricerror=0.
    for row in mm.itertuples():
        ix=role_ids(row.role);m=scores(Y[ix],pred[row.arm][ix])
        for name,v in m.items():metricerror=max(metricerror,abs(v-getattr(row,name)));np.testing.assert_allclose(v,getattr(row,name),rtol=1e-12,atol=1e-12)
    records=pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    for a in ['B0','B1','B2','B3','B4','B5']:
        rows=records[records.arm==a];np.testing.assert_array_equal(rows.actual_GPUh,Y[rows.day_index,rows.hour]);np.testing.assert_array_equal(rows.Q90,pred[a][rows.day_index,rows.hour,1]);np.testing.assert_array_equal(rows.Q50,pred[a][rows.day_index,rows.hour,0])
    ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');cierror=0.;drawcount=0
    for role in ['EXPOSED_EVALUATION','MAY_HISTORICAL']:
        ii=role_ids(role);n=len(ii)
        for block in [1,7]:
            rng=np.random.default_rng(20260928+block);starts=rng.integers(0,n,size=(2000,int(np.ceil(n/block))))
            ix=((starts[...,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
            # Independent per-day sums then weighted count multiplication (not study bootstrap indexing).
            count=np.array([np.bincount(row,minlength=n) for row in ix],dtype=float)
            vals={}
            for arm in ['B0','B1','B2','B3','B4','B5']:
                y=Y[ii];q=pred[arm][ii];err=y-q[...,1];positive=y>0;burst=y>BURST
                with np.errstate(divide='ignore',invalid='ignore'):
                    vals[arm]=dict(Q90_pinball=count@np.maximum(.9*err,-.1*err).sum(1)/(n*24),Q90_coverage=count@(err<=0).sum(1)/(n*24),
                        requirement_ratio=(count@q[...,1].sum(1))/(count@y.sum(1)),burst_coverage=(count@((err<=0)&burst).sum(1))/(count@burst.sum(1)),
                        positive_coverage=(count@((err<=0)&positive).sum(1))/(count@positive.sum(1)),Q50_MAE=count@np.abs(y-q[...,0]).sum(1)/(n*24))
            for row in ci[(ci.role==role)&(ci.block_days==block)].itertuples():
                v=vals[row.arm][row.metric]-vals['B0'][row.metric];invalid=int((~np.isfinite(v)).sum());assert invalid==row.invalid_draws
                if not invalid:
                    lo,hi=np.quantile(v,[.025,.975]);cierror=max(cierror,abs(lo-row.low),abs(hi-row.high));np.testing.assert_allclose([lo,hi],[row.low,row.high],rtol=1e-10,atol=1e-9)
                else:assert np.isnan(row.low) and np.isnan(row.high)
                drawcount+=len(v)
    pd.DataFrame(cost).to_csv(ROOT/'NEW_COMPUTATIONAL_COST.csv',index=False,lineterminator='\n')
    write('VALIDATION.json',dict(PASS=True,time=pd.Timestamp.now(tz='UTC').isoformat(),exact_memberships=members,checkpoint_replays=models,
        maximum_alternative_ppf_difference=maxdiff,prediction_rows=len(records),metric_maximum_difference=metricerror,
        paired_CI_rows=len(ci),bootstrap_metric_draws=drawcount,CI_maximum_difference=cierror,invalid_CI_rows=int((ci.invalid_draws>0).sum()),
        normal_hour_exact_B0=True,source_bytes_unchanged=True,mathematically_valid_zero_mass_quantiles=True))
    print('VALIDATION PASS',members,models,len(ci),cierror,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['reuse','final']);args=p.parse_args();globals()[args.stage]()
