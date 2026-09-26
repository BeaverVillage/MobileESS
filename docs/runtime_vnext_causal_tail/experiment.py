"""Staged GPU-cohort runtime comparison with causal membership and residuals."""
from common import *
import argparse,dataclasses,lightgbm as lgb,pickle
J=None;P=None
POLICIES=[('120',.05,'current_decay')]+[(w,0. if h==0 else np.log(2)/h,str(h) if h else 'none') for w in ['120','180','expanding'] for h in [14,30,60,0]]

def data():
 global J,P
 if J is None:
  require(sha(ROOT/'cache/JOBS.parquet')==read('PREPARATION_COMPLETE.json')['jobs_sha256'],'SOURCE_DRIFT')
  J=pd.read_parquet(ROOT/'cache/JOBS.parquet');P=pd.read_parquet(ROOT/'cache/PANEL.parquet')
 return J,P

def register():
 require(read('MOE_BASELINE_REPRODUCTION.json')['PASS'] and read('MODERN_BASELINE_REPRODUCTION.json')['PASS'],'BASELINES_NOT_EXACT')
 dump('PROTOCOL.json',dict(time=now(),version='runtime-vNext-v1',policies=POLICIES,
  policy_validation_origins=['2025-03-22T08:00:00Z','2025-03-26T08:00:00Z','2025-03-30T08:00:00Z'],
  policy_objective='mean per-origin Pending point MAE; fixed three chronological origins within unchanged DEVELOPMENT, not chosen by outcomes',
  reference_population='PR27 all-job exact reproduction; PR42 positive-GPU exact prediction replay; common-cohort arms use all raw positive-GPU completed history',
  population_bridge='Temporal effect is identified within the common GPU cohort, not all-job PR27 production. Production-wide MoE refit superiority remains unsupported.',
  training='end_time < issue_time, start >= submit, runtime >0; every eligible GPU job within policy window; no sampling',
  cadence='refit at every scored issue; Stage A predefined three-origin validation',
  model_family=['MOE_POOLED','MULTI_QUANTILE','MULTI_QUANTILE_HIERARCHICAL'],quantiles=TAUS,
  moe='pinned MoE recipe; pooled positive residual causal empirical quantiles from prior issue predictions, minimum100 unique completed Jobs; no use of future frozen pooled scalar',
  hierarchy=['hardware','standby_state','requested_walltime_bucket','GPU_bucket'],min_group_jobs=100,min_group_issues=5,
  calibration='expanding chronological out-of-sample residuals; latest prior observation per Job/state; finite-sample signed quantile residual; causal parent backoff',
  pending='total runtime',running='remaining runtime with elapsed_seconds as an explicit feature',
  running_landmarks_hours=[.5,1.5,3.,6.,12.],landmark_assignment='one job-hash-selected landmark independent of duration; retain only historical Jobs surviving assigned landmark; all completed before fit issue',
  long_job='total runtime >4 hours, Q90 remaining/total underprediction as appropriate',
  slot_proxy='GPU-weighted positive difference in ceil(actual/900) and ceil(predicted/900), both censored at 96 slots; runtime-origin occupancy proxy, not optimizer/actual-grid output',
  model_selection='DEVELOPMENT/CALIBRATION equally weighted day-mean Q90 pinball; prefer aggregate coverage/long-job/overreserve gates in both, otherwise best pinball as research candidate only; final subgroup/missed-slot gates never cause evaluation reselection',
  calibration_model_selection_before_evaluation=True,feature_version_provenance='UNVERIFIED; event time availability only',
  gates=dict(Q90=[.90,.95],GPU_Q90=[.90,.95],major_min=.88,long_under_max=.15,long_under_target=.10,missed_slots_reduction=.50,overreserve_below_walltime=True),
  major_group='at least100 Job-issue rows and at least1% of total GPU weight, hardware/state/walltime/GPU subgroups',
  uncertainty=dict(unit='issue day',paired=True,draws=2000,block_days=[1,7],seed=20260926),
  LGBM=FIXED,MOE_threads=4,thread_only_change='exact reproduction uses original1; common-cohort study uses4 consistently across all MoE arms',
  optional_survival='not evaluated; no verified censoring mechanism or historical request-state/version log; no censoring claim',
  evaluation=['EXPOSED_EVALUATION','MAY_HISTORICAL'],evaluation_adaptation='mature earlier evaluation labels may enter later fixed refits/residuals; never tuning',
  optimizer_executions=0,grid_executions=0,promotion=False),exclusive=True)
 dump('CODE_FREEZE.json',dict(time=now(),files={p.name:sha(p) for p in ROOT.glob('*.py')}),exclusive=True)

def member(window,t):
 j,_=data();mask=j.label_valid&j.end_time.lt(t)
 if window!='expanding':mask &=j.end_time.ge(t-pd.Timedelta(days=int(window)))
 f=j[mask].sort_values(['end_time','job_id'],kind='stable').copy();require(len(f)>100 and f.end_time.lt(t).all(),'TRAIN_SUPPORT_OR_LEAK');return f

def query(t):
 _,p=data();cols=['job_id','row_id','job_issue_id','issue_time','role','state','elapsed_seconds','submit_time',*MOE_FEATURES,*CLOCK]
 f=p.loc[p.issue_time.eq(t),list(dict.fromkeys(cols))].copy();require(f.submit_time.le(t).all(),'FUTURE_FEATURE');return f

def groupkeys(f):
 part=f.partition.fillna('').astype(str).str.lower();qos=f.qos.fillna('').astype(str).str.lower()
 hardware=np.select([part.str.contains('h100'),part.str.contains('a100'),part.str.contains('hpe')],['H100','A100','HPE'],default='OTHER')
 standby=np.where(part.str.contains('stdby|standby')|qos.str.contains('standby'),'standby','regular')
 wall=pd.cut(f.requested_seconds,[-np.inf,3600,21600,86400,259200,np.inf],labels=['<=1h','1-6h','6-24h','24-72h','>72h']).astype(str)
 gpu=pd.cut(f.num_gpus_req,[-np.inf,1,4,8,32,np.inf],labels=['<=1','2-4','5-8','9-32','>32']).astype(str)
 return pd.DataFrame(dict(hardware=hardware,standby_state=standby+'_'+f.state.to_numpy(),wall_bucket=wall.to_numpy(),GPU_bucket=gpu.to_numpy()),index=f.index)

def fit_moe(train,q,rate,folder):
 model=exact_moe(rate=rate);model.config=dataclasses.replace(model.config,estimator_n_jobs=4)
 keep=MOE_FEATURES+['end_time','runtime_seconds'];rows=train[keep].to_dict('records');qr=q[MOE_FEATURES].to_dict('records')
 # Row feature ordering follows the pinned source. Preprocessing cannot receive query labels.
 path=folder/'moe.pkl.gz'
 if path.exists():
  with gzip.open(path,'rb') as f:art,state=pickle.load(f)
  x=model._transform_rows(qr,art);point=np.asarray(state.fallback.predict(x),float)
  routes={}
  for i,r in enumerate(qr):routes.setdefault(state.routing.key(r),[]).append(i)
  for key,ix in routes.items():
   if key in state.experts:point[ix]=state.experts[key].predict(x[ix])
 else:
  art=model._build_daily_preprocessing_artifacts(rows);xt=model._transform_rows(rows,art);xp=model._transform_rows(qr,art)
  split=type('IssueSplit',(),{'split_epoch':int(pd.Timestamp(q.issue_time.iloc[0]).timestamp())})()
  weight=model._time_decay_weights(rows,split)
  state,point=model._fit_predict(xt,train.runtime_seconds.to_numpy(),xp,train_rows=rows,test_rows=qr,artifacts=art,sample_weight=weight)
  with gzip.open(path,'wb',compresslevel=3) as f:pickle.dump((art,state),f,protocol=5)
 return np.maximum(point,0.)

def landmarks(train):
 # Stable integer hash only; no label-based choice of elapsed time.
 h=pd.util.hash_pandas_object(train.job_id,index=False).to_numpy();elapsed=np.array([1800.,5400.,10800.,21600.,43200.])[h%5]
 f=train.copy();f['elapsed_seconds']=elapsed;f=f[f.runtime_seconds>f.elapsed_seconds].copy();f['remaining_seconds']=f.runtime_seconds-f.elapsed_seconds
 return f

def fit_lgb(train,q,rate,folder,running=False):
 require(read('THREAD_EQUIVALENCE.json')['PASS'],'THREAD_EQUIVALENCE_NOT_VERIFIED')
 target='remaining_seconds' if running else 'runtime_seconds';f=landmarks(train) if running else train
 require(len(f)>100,'RUNNING_SUPPORT')
 # Hold the input variables AND their fitted representation constant across
 # architectures. PR42's distinct production transform remains a reference only.
 source=folder.parent.parent.parent/folder.parent.parent.name.replace('LGBM_','MOE_',1)/folder.parent.name/'moe.pkl.gz'
 require(source.exists(),'COMMON_PREPROCESSING_AUTHORITY_MISSING')
 with gzip.open(source,'rb') as stream:art,_=pickle.load(stream)
 model=exact_moe();xt=model._transform_rows(f[MOE_FEATURES].to_dict('records'),art);xp=model._transform_rows(q[MOE_FEATURES].to_dict('records'),art)
 if running:xt=np.column_stack([xt,np.log1p(f.elapsed_seconds)]);xp=np.column_stack([xp,np.log1p(q.elapsed_seconds)])
 dump(folder.relative_to(ROOT)/'preprocessing.json',dict(common_MOE_artifact=str(source.relative_to(ROOT)),artifact_sha256=sha(source),
  input_features=MOE_FEATURES+(['elapsed_seconds'] if running else []),running=running,training_N=len(f),landmark_jobs_hash=ids(f.job_id),
  transform='exact shared MoE training-fitted OHE/SVD representation; additional log1p(elapsed) for remaining target',
  columns=len(xt[0]),latest_end=f.end_time.max()))
 out=[]
 age=(q.issue_time.iloc[0]-f.end_time).dt.total_seconds().to_numpy()/86400;weight=np.exp(-rate*age) if rate else None
 for tau in TAUS:
  path=folder/f'Q{int(tau*100)}.txt.gz'
  if path.exists():m=lgb.Booster(model_str=gzip.decompress(path.read_bytes()).decode())
  else:
   m=lgb.LGBMRegressor(objective='quantile',alpha=tau,**{**FIXED,'n_jobs':4}).fit(xt,f[target].to_numpy(),sample_weight=weight).booster_
   path.write_bytes(gzip.compress(m.model_to_string().encode(),mtime=0))
  out.append(m.predict(xp,num_threads=1))
 return np.maximum.accumulate(np.maximum(np.column_stack(out),0.),axis=1)

def _forecast(family,window,rate,decay,t):
 t=pd.Timestamp(t);tag=f'{family}_{window}_{decay}';key=t.strftime('%Y%m%dT%H%M');path=ROOT/'predictions'/tag/(key+'.parquet')
 if path.exists():return pd.read_parquet(path)
 start=time.perf_counter();tr=member(window,t);q=query(t);folder=ROOT/'fits'/tag/key;folder.mkdir(parents=True,exist_ok=True)
 np.savez_compressed(folder/'train_membership.npz',row_ids=tr.row_id.to_numpy(np.int32))
 dump(folder.relative_to(ROOT)/'MEMBERSHIP.json',dict(issue_time=t,N=len(tr),latest_end=tr.end_time.max(),earliest_end=tr.end_time.min(),
  row_ids_sha256=sha(folder/'train_membership.npz'),job_ids_sha256=ids(tr.job_id),policy=window,rate=rate,decay=decay,
  future_or_equal_end_N=0,source_sha256=read('PREPARATION_COMPLETE.json')['jobs_sha256']))
 if family=='MOE':
  point=fit_moe(tr,q,rate,folder);q['point_total']=point;q['point']=np.maximum(point-q.elapsed_seconds,0.)
 else:
  for state in ['PENDING','RUNNING']:
   ix=q.state.eq(state)
   if not ix.any():continue
   d=folder/state;d.mkdir(exist_ok=True);pred=fit_lgb(tr,q[ix],rate,d,running=state=='RUNNING')
   for k,tau in enumerate(TAUS):q.loc[ix,f'Q{int(100*tau)}']=pred[:,k]
  q['point']=q.Q50
 require(np.isfinite(q.point).all(),'NONFINITE_PREDICTION');path.parent.mkdir(parents=True,exist_ok=True);q.to_parquet(path,index=False)
 dump(folder.relative_to(ROOT)/'PREDICTION_RECEIPT.json',dict(time=now(),prediction_sha256=sha(path),N=len(q),seconds=time.perf_counter()-start,
  target_columns_passed_to_predictor=[],label_access_after_prediction_hash=True,model_files={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*.gz')}))
 print('FIT',tag,key,len(tr),len(q),round(time.perf_counter()-start,2),flush=True);return q

def forecast(family,window,rate,decay,t):
 from cache_locks import file_lock
 key=pd.Timestamp(t).strftime('%Y%m%dT%H%M')
 with file_lock(f'{family}_{window}_{decay}_{key}'):return _forecast(family,window,rate,decay,t)

def outcomes(f):
 _,p=data();cols=['job_issue_id','actual_seconds','end_time','runtime_seconds'];g=f.merge(p[cols],on='job_issue_id',validate='one_to_one');return g

def stats(g,col='Q90'):
 valid=g.actual_seconds.notna();f=g[valid];y=f.actual_seconds.to_numpy();q=f[col].to_numpy();gpu=f.num_gpus_req.to_numpy();e=y-q;covered=y<=q
 long=f.runtime_seconds.to_numpy()>14400;rw=np.maximum(f.requested_seconds.to_numpy()-f.elapsed_seconds.to_numpy(),0)
 missed=lambda q:float(np.sum(gpu*np.maximum(np.minimum(np.ceil(y/900),96)-np.minimum(np.ceil(q/900),96),0)))
 return dict(N=len(f),unresolved_N=int((~valid).sum()),Q90_coverage=float(covered.mean()),GPU_coverage=float(np.average(covered,weights=gpu)),
  pinball=float(np.maximum(.9*e,-.1*e).mean()),MAE_seconds=float(abs(e).mean()),long_under=float((~covered[long]).mean()) if long.any() else None,
  missed_GPU_slots=missed(q),overreserved_GPUh=float((np.maximum(q-y,0)*gpu).sum()/3600),
  requested_overreserved_GPUh=float((np.maximum(rw-y,0)*gpu).sum()/3600),Q90_sum_GPUh=float((q*gpu).sum()/3600))

def residual_quantile(v,tau):
 n=len(v);rank=int(np.ceil(tau*(n+1)));require(rank<=n,'CALIBRATION_SUPPORT');return float(np.sort(v)[rank-1])

def calibrate(raw,kind):
 raw=raw.sort_values(['issue_time','job_issue_id']).copy();pool=[];parts=[];proof=[]
 for t,g in raw.groupby('issue_time',sort=True):
  hist=pd.concat(pool,ignore_index=True) if pool else raw.iloc[:0].copy();hist=hist[hist.end_time.lt(t)&hist.actual_seconds.notna()]
  hist=hist.sort_values('issue_time').drop_duplicates(['job_id','state'],keep='last');groups=groupkeys(hist);querygroups=groupkeys(g)
  routes={};out=g.copy()
  for idx,row in g.iterrows():
   best=np.arange(len(hist));chosen='root'
   if kind=='hierarchical':
    for depth in range(1,5):
     columns=list(groups.columns[:depth]);mask=np.ones(len(hist),bool)
     for c in columns:mask &=groups[c].to_numpy()==querygroups.loc[idx,c]
     ix=np.flatnonzero(mask)
     if hist.iloc[ix].job_id.nunique()>=100 and hist.iloc[ix].issue_time.nunique()>=5:best=ix;chosen='|'.join(str(querygroups.loc[idx,c]) for c in columns)
     else:break
   key=chosen
   if key not in routes:
    h=hist.iloc[best];delta=[]
    for tau in TAUS:
     qcol=f'Q{int(tau*100)}';pred=h.point if kind=='pooled' else h[qcol]
     residual=h.actual_seconds.to_numpy()-pred.to_numpy()
     if kind=='pooled':residual=np.maximum(residual,0.)
     delta.append(residual_quantile(residual,tau) if h.job_id.nunique()>=100 else None)
    routes[key]=dict(N=len(h),N_unique_jobs=int(h.job_id.nunique()),N_issues=int(h.issue_time.nunique()),latest_end=str(h.end_time.max()),delta=delta)
   delta=routes[key]['delta']
   for k,tau in enumerate(TAUS):
    col=f'Q{int(tau*100)}';base=row.point if kind=='pooled' else row[col]
    out.loc[idx,col]=np.nan if delta[k] is None else max(0.,base+delta[k])
   out.loc[idx,'calibration_route']=chosen
  qcols=[f'Q{int(t*100)}' for t in TAUS];out[qcols]=np.maximum.accumulate(out[qcols].to_numpy(),axis=1)
  proof.append(dict(issue_time=str(t),pool_job_issue_ids=hist.job_issue_id.tolist(),pool_latest_end=str(hist.end_time.max()),routes=routes));parts.append(out);pool.append(g)
 return pd.concat(parts,ignore_index=True),proof

def stage_a():
 require(not (ROOT/'STAGE_A_FREEZE.json').exists(),'A_ALREADY_FROZEN');rows=[]
 for window,rate,decay in POLICIES:
  for t in read('PROTOCOL.json')['policy_validation_origins']:
   g=outcomes(forecast('MOE',window,rate,decay,t));v=g[g.state.eq('PENDING')&g.actual_seconds.notna()]
   rows.append(dict(window=window,rate=rate,decay=decay,issue_time=t,N=len(v),MAE_seconds=float(abs(v.actual_seconds-v.point).mean())))
  pd.DataFrame(rows).to_csv(ROOT/'STAGE_A_DEVELOPMENT.csv',index=False)
 means=pd.DataFrame(rows).groupby(['window','rate','decay']).MAE_seconds.mean();winner=means.idxmin()
 dump('STAGE_A_FREEZE.json',dict(time=now(),window=winner[0],rate=winner[1],decay=winner[2],validation_MAE=float(means.min()),selection_role='DEVELOPMENT',evaluation_accessed=False),exclusive=True)

def runs(through_roles):
 a=read('STAGE_A_FREEZE.json');_,p=data();times=sorted(p.loc[p.role.isin(through_roles),'issue_time'].unique());results={}
 phase='evaluation' if 'EXPOSED_EVALUATION' in through_roles else 'pre_evaluation'
 for fam in ['MOE','LGBM']:
  f=pd.concat([outcomes(forecast(fam,a['window'],a['rate'],a['decay'],t)) for t in times],ignore_index=True)
  if fam=='MOE':
   c,proof=calibrate(f,'pooled');results['MOE_POOLED']=c;dump(f'calibration/{phase}_MOE_POOLED.json',proof)
  else:
   results['MULTI_QUANTILE']=f;c,proof=calibrate(f,'hierarchical');results['MULTI_QUANTILE_HIERARCHICAL']=c;dump(f'calibration/{phase}_MULTI_QUANTILE_HIERARCHICAL.json',proof)
 return results

def stage_b():
 require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'ALREADY_FROZEN');result=runs(['TRAIN','DEVELOPMENT','CALIBRATION']);rows=[]
 for model,f in result.items():
  for role in ['DEVELOPMENT','CALIBRATION']:
   g=f[f.role.eq(role)];require(g.Q90.notna().all(),'DEVELOPMENT_CAL_SUPPORT')
   for t,d in g.groupby('issue_time'):rows.append(dict(model=model,role=role,issue_time=t,**stats(d)))
 out=pd.DataFrame(rows);out.to_csv(ROOT/'MODEL_SELECTION_METRICS.csv',index=False)
 mean=out.groupby(['model','role']).mean(numeric_only=True)
 def key(m):
  r=mean.loc[m];passes=r.Q90_coverage.between(.9,.95).all() and r.GPU_coverage.between(.9,.95).all() and (r.long_under<=.15).all() and (r.overreserved_GPUh<r.requested_overreserved_GPUh).all()
  return (not passes,r.pinball.mean())
 chosen=min(result,key=key)
 dump('FINAL_SELECTION_FREEZE.json',dict(time=now(),temporal=read('STAGE_A_FREEZE.json'),model=chosen,
  calibration='fixed hierarchical rule for hierarchical arm; raw for MQ; causal pooled for MoE',evaluation_accessed=False,
  code_hashes={p.name:sha(p) for p in ROOT.glob('*.py')},protocol_sha256=sha(ROOT/'PROTOCOL.json'),promotion=False),exclusive=True)

def evaluate():
 freeze=read('FINAL_SELECTION_FREEZE.json');require(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'EVALUATED')
 for n,h in freeze['code_hashes'].items():require(sha(ROOT/n)==h,'POST_FREEZE_CODE_DRIFT')
 result=runs(['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','MAY_HISTORICAL']);frames=[]
 for model,f in result.items():f=f.copy();f['model']=model;frames.append(f)
 # The temporal baseline has the same GPU cohort and causal pooled calibration.
 _,panel=data();current=pd.concat([outcomes(forecast('MOE','120',.05,'current_decay',t)) for t in sorted(panel.issue_time.unique())],ignore_index=True)
 current,proof=calibrate(current,'pooled');current['model']='MOE_CURRENT_TEMPORAL_GPU_COHORT';frames.append(current);dump('calibration/MOE_CURRENT_TEMPORAL_GPU_COHORT.json',proof)
 # Matched legacy frozen reference is valid only after its pooled correction matured.
 f=frames[0].copy();old=pd.read_parquet(ROOT/'PR31_REFERENCE_PANEL.parquet');f=f.merge(old[['job_issue_id','reference_safe_sec']],on='job_issue_id',how='inner',validate='one_to_one')
 f=f[f.issue_time>=pd.Timestamp('2025-04-01T08:00Z')];f['Q90']=f.reference_safe_sec
 for c in ['Q50','Q95','Q99','point','point_total','calibration_route']:
  if c in f:f[c]=np.nan
 f['model']='PR31_FROZEN_MOE';frames.append(f)
 # Saved production total-runtime model, transported to Running only as a naive remaining baseline.
 _,p=data();parts=[];bridge=[]
 for t,g in p[p.role.eq('MAY_HISTORICAL')].groupby('issue_time'):
  day=(t+pd.Timedelta(hours=16)).strftime('%Y-%m-%d');snapshot=Path('D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4')/day/'B0/dayahead/ml/ML_SNAPSHOT.json'
  r=json.loads(snapshot.read_text(encoding='utf-8'));d=json.loads(Path(r['preprocessing']['path']).read_text(encoding='utf-8'));pre=Preprocess(t);pre.__dict__.update(d)
  m=lgb.Booster(model_str=gzip.decompress(Path(r['model']['path']).read_bytes()).decode());pred=m.predict(pre.transform(g[FEATURES]),num_threads=1)
  v=g.copy();v['Q90']=np.maximum(pred-v.elapsed_seconds,0.);v['model']='PR42_FROZEN_LGBM_NAIVE_REMAINING';parts.append(v)
  frozen=pd.read_parquet(ROOT/'baseline'/f'modern_{day}.parquet');shared=v[v.state.eq('PENDING')][['job_id','Q90']].merge(frozen[['job_id','Q90_seconds']],on='job_id',validate='one_to_one')
  require(np.array_equal(shared.Q90,shared.Q90_seconds),'FROZEN_PENDING_FEATURE_OR_PREDICTION_DRIFT')
  bridge.append(dict(day=day,common_pending_N=len(shared),raw_pending_N=int(v.state.eq('PENDING').sum()),frozen_pending_N=len(frozen),exact_on_intersection=True,running_transport_N=int(v.state.eq('RUNNING').sum())))
 dump('PRODUCTION_POPULATION_BRIDGE.json',bridge)
 frames.append(pd.concat(parts,ignore_index=True))
 full=pd.concat(frames,ignore_index=True);full=full[full.role.isin(['EXPOSED_EVALUATION','MAY_HISTORICAL'])]
 require(full.Q90.notna().all(),'EVAL_CAL_SUPPORT_OR_EXCLUSION');full.to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
 dump('EVALUATION_COMPLETE.json',dict(time=now(),N=len(full),sha256=sha(ROOT/'PREDICTIONS.parquet'),freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json')),exclusive=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','a','b','evaluate']);a=p.parse_args();{'register':register,'a':stage_a,'b':stage_b,'evaluate':evaluate}[a.stage]()
