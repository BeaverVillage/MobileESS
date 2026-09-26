import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from pathlib import Path
import json,hashlib,zipfile,re,ast,time,subprocess
import numpy as np,pandas as pd,pyarrow.parquet as pq
OUT=Path(__file__).resolve().parent
BASE=OUT.parent
R5=OUT/'history/B/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
R6=OUT/'history/B/dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork'
RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(n,v):
 def clean(x):
  if isinstance(x,dict):return {k:clean(a) for k,a in x.items()}
  if isinstance(x,(list,tuple)):return [clean(a) for a in x]
  if isinstance(x,(float,np.floating)) and not np.isfinite(x):return None
  if isinstance(x,(np.integer,np.bool_)):return x.item()
  return x
 (OUT/n).write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding='utf-8')
def issue_time(day):return pd.Timestamp(str(day),tz='Etc/GMT-10').tz_convert('UTC')-pd.Timedelta(hours=6)
def require(x,msg):
 if not x:raise ValueError(msg)
def main():
 protocol={'frozen_at':pd.Timestamp.now(tz='UTC').isoformat(),'scope':'forecast only; no optimizer/grid execution',
 'threads':1,'training_workers':1,'dataloader_workers':0,'gpu_concurrent_jobs':1,
 'seeds':[20260924,20260925,20260926],'horizons_hours':[4,1,2,8],
 'fixed_training':'exact original eligible TRAIN membership, 167 days; frozen stage mask',
 'development':'58 original eligible days; chronological OOS; first 20 eligible mature residual days warmup before calibrated development score',
 'families':{'F0':'frozen L0 H4 Q50/Q90 + original 85% expanding correction, historical only',
 'F1':'L0 LightGBM original log1p and 71 features, 90% expanding correction',
 'F2':'small TFT-based gated variable selection, LSTM history/known decoder, causal attention; direct window quantiles; log1p target',
 'F3':'DeepAR-based history encoder + autoregressive LSTM decoder, hurdle lognormal window distribution; zero mass explicit',
 'seasonal':'TRAIN same slot weekday if >=8 days, same slot if >=20, pooled fallback empirical quantiles',
 'trivial':['physical capacity 780*H','TRAIN target maximum constant']},
 'neural_search':{'hidden':16,'learning_rates':[0.001,0.0003],'dropout':0.1,'max_epochs':40,'patience':7,'batch_days':16,'gradient_clip':1.0,'weight_decay':0.0001,'trials_per_family':2,'search_seed':20260924,'selected_config_repeat_seeds':3,'early_stop':'minimum all-window original-unit raw Q90 pinball on eligible development; no positive-only mismatch for TFT','samples_deepar':128,'selection':'mean chronological calibrated development Q90 pinball; tie smaller mean requirement; fixed rules; no May reselection'},
 'postprocessing':{'repair':'nonnegative; Q90=max(Q50,Q90)','calibration':'log1p residual; one-sided finite-sample order statistic ceil(0.9*(n+1)); positive correction only; expanding chronological OOS; full-day maturity strictly before issue','budget':'exactly one 90% calibration rule all new models; no scale/cap/quantile search','caps':'same causal historical 99% finite-sample quantile and 780*H physical-cap scenario; May H4 exact frozen caps','actual_secured_reserve':'not computed; optimizer not run'},
 'expanding_refit':{'families':'LightGBM plus best neural family by H4 development mean score (at most 2 total)','cadence_candidates_days':[28,56],'choose_on_development':'paired same-day calibrated Q90 pinball averaged over both families; tie 56','cutoff':'scheduled issue; only full-day mature labels and operating dates before cutoff; frozen architecture, epochs, scaler and learning rate','membership':'save day IDs/ranges/count for every issue; never fit on an immature label'},
 'horizon_selection':'LightGBM plus best neural H4 development family; direct sums of common 15min targets; H1=93 H2=89 H4=81 H8=65; compare relative to same-H LightGBM; no cross-H raw-loss winner',
 'uncertainty':'paired moving 7-day blocks, 1000 bootstrap draws, seeds averaged within day; windows not independent',
 'burst':'TRAIN positive target Q95 separately for each horizon; threshold frozen',
 'evaluation':'Dec-Feb and May historical exposed; no unused holdout claim; NO_UNTOUCHED_CONFIRMATION',
 'stop_rule':'complete finite registered comparisons, no tuning on historical evaluation, report failures/OOM without population reduction',
 'NEW_MODEL_AUTO_DEPLOYED':False,'OPTIMIZER_CHANGED':False,'GRID_CAMPAIGN_EXECUTIONS':0,'EXISTING_PRODUCTION_MODIFIED':False}
 if not (OUT/'EXPERIMENT_PROTOCOL.json').exists():dump('EXPERIMENT_PROTOCOL.json',protocol)
 print('Protocol frozen',flush=True)
 lineage={'github':json.loads((OUT/'GITHUB_VERIFICATION.json').read_text()),'source_comparisons':[],'models':[]}
 for rel in ['dayahead/v41/workload.py','dayahead/v41/data.py','dayahead/v41/reserve.py','dayahead/v41/snapshot.py','dayahead/v41r2/authority.py','dayahead/v40r6/common.py','dayahead/v40r6/models.py']:
  p=BASE/'v41r4_final_results_pr'/rel;q=OUT/'history/A'/rel
  lineage['source_comparisons'].append({'path':rel,'local':str(p),'local_sha':sha(p),'github_commit_sha256':sha(q),'same':sha(p)==sha(q)})
 for q in [50,90]:
  p=Path('D:/codex_mobileess_workspace/MobileESS_v40r6r1_risk_calibrated_gpuwork/dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/fits/L0')/f'H4_Q{q}.txt'
  h=sha(p);assert h==sha(R6/'fits/L0'/p.name)
  lineage['models'].append({'quantile':q,'path':str(p),'sha256':h,'GitHub_B_model_equal':True})
 snaps=[]
 root=BASE/'CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4'
 for day in pd.date_range('2025-05-01','2025-05-31').strftime('%Y-%m-%d'):
  p=root/day/'B0/dayahead/ml/ML_SNAPSHOT.json';j=json.loads(p.read_text())
  assert [x['sha256'] for x in j['H4_model_authority']['models']]==[x['sha256'] for x in lineage['models']]
  snaps.append({'day':day,'path':str(p),'sha256':sha(p),'membership_sha256':j['H4_calibration_support']['membership_sha256']})
 lineage['May_snapshots']=snaps
 for name,p in [('feature_contract',R6/'V40R6_FEATURE_CONTRACT.json'),('training_receipt',R6/'V40R6_COMPUTE_LEDGER.json'),('maturity_ledger',R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')]:lineage[name]={'path':str(p),'sha256':sha(p)}
 dump('SOURCE_AND_MODEL_LINEAGE.json',lineage)
 if not (OUT/'raw_bins.parquet').exists():
  assert sha(RAW)=='3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f'
  groups=[];jobs=[];inventory=[];seen=set()
  with zipfile.ZipFile(RAW) as z:
   for name in sorted(z.namelist()):
    if not re.search(r'year=\d{4}/month=\d+/.*\.parquet$',name):continue
    with z.open(name) as f:r=pq.read_table(f,columns=['id','submit_time','start_time','end_time','gpus_requested'],use_threads=False).to_pandas()
    for c in ['submit_time','start_time','end_time']:r[c]=pd.to_datetime(r[c],utc=True).astype('datetime64[ns, UTC]')
    r['gpus_requested']=pd.to_numeric(r.gpus_requested,errors='raise').astype(float)
    assert r.id.astype(str).is_unique and not set(r.id.astype(str))&seen
    seen.update(r.id.astype(str));assert r.submit_time.notna().all()
    inventory.append({'member':name,'N':len(r),'submit_min':str(r.submit_time.min()),'submit_max':str(r.submit_time.max()),'end_max':str(r.end_time.max()),'missing_gpu':int(r.gpus_requested.isna().sum())})
    r['bin']=r.submit_time.dt.floor('30min');r['unresolved']=r.end_time.isna().astype(int);r['gpu_unresolved']=(r.gpus_requested.gt(0)&r.end_time.isna()).astype(int)
    groups.append(r.groupby('bin').agg(submit_count=('id','size'),max_observed_end=('end_time','max'),unresolved_end_count=('unresolved','sum'),gpu_unresolved=('gpu_unresolved','sum')))
    valid=r.gpus_requested.gt(0)&np.isfinite(r.gpus_requested)&r.start_time.notna()&r.end_time.notna()&r.end_time.gt(r.start_time)&r.start_time.ge(r.submit_time)
    w=r.loc[valid].copy();w['work_GPUh']=w.gpus_requested*(w.end_time-w.start_time).dt.total_seconds()/3600;jobs.append(w)
    print('raw',name,len(r),flush=True)
  w=pd.concat(jobs,ignore_index=True);b=pd.concat(groups).groupby(level=0).agg(submit_count=('submit_count','sum'),max_observed_end=('max_observed_end','max'),unresolved_end_count=('unresolved_end_count','sum'),gpu_unresolved=('gpu_unresolved','sum')).sort_index()
  b=b.reindex(pd.date_range(b.index.min(),b.index.max(),freq='30min'));b.index.name='arrival_bin'
  for c in ['submit_count','unresolved_end_count','gpu_unresolved']:b[c]=b[c].fillna(0).astype(int)
  b=b.join(w.groupby('bin').work_GPUh.sum());b.work_GPUh=b.work_GPUh.fillna(0)
  w.to_parquet(OUT/'raw_work.parquet',index=False);b.to_parquet(OUT/'raw_bins.parquet');dump('RAW_INVENTORY.json',{'archive':str(RAW),'sha256':sha(RAW),'partitions':inventory,'no_filename_month_filter':True,'N_unique':len(seen),'N_modeled':len(w),'unused_period':'NO_UNTOUCHED_CONFIRMATION; archive exposure not certified'})
 b=pd.read_parquet(OUT/'raw_bins.parquet');w=pd.read_parquet(OUT/'raw_work.parquet')
 ledger=pd.read_parquet(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet');a=np.load(R5/'data.npz');old=np.load(R5/'inputs/causal_dataset.npz')
 periods=[]
 for role,g in ledger.groupby('role'):
  e=g[g.stage_maturity_eligible];periods.append({'role':role,'calendar_start':g.operating_day.min(),'calendar_end':g.operating_day.max(),'eligible_start':e.operating_day.min(),'eligible_end':e.operating_day.max(),'N_eligible':len(e),'excluded_days':';'.join(g.loc[~g.stage_maturity_eligible,'operating_day'])})
 pd.DataFrame(periods).to_csv(OUT/'ORIGINAL_TRAINING_PERIODS.csv',index=False)
 # Execute only pure feature functions from pinned source; no production imports or writes.
 src=ast.parse((OUT/'history/A/dayahead/v41/workload.py').read_text());env={'np':np,'pd':pd,'json':json,'issue_time':issue_time,'require':require,'SLOT_NS':900_000_000_000,'R6OUT':R6}
 exec(compile(ast.Module(body=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in ['history_values','features']],type_ignores=[]),'pinned_workload_features','exec'),env)
 days=[str(v) for v in a['days']]+list(pd.date_range('2025-02-27','2025-05-31').strftime('%Y-%m-%d'));N=len(days)
 atomic=np.zeros((N,96));base61=np.zeros((N,96,61),np.float32);past=np.zeros((N,336,8),np.float32);sw=np.zeros((N,96,4));sm=np.zeros((N,96,4),bool)
 atomic[:349]=a['y'].reshape(349,96);base61[:349]=a['X'].reshape(349,96,61);past[:349]=old['past'];sw[:349]=a['seasonal_w'].reshape(349,96,4)
 sp=pd.read_parquet(R5/'seasonal_maturity_proof.parquet')
 for j,lag in enumerate([7,14,21,28]):sm[:349,:,j]=(a['seasonal_mask'][:,j]&(sp[sp.lag_days==lag].parent_available_ns.to_numpy()<a['origin_ns'])).reshape(349,96)
 raw_errors=[];extra=[]
 for i,day in enumerate(days):
  issue=issue_time(day);begin=issue+pd.Timedelta(hours=6);end=begin+pd.Timedelta(days=1);ss=w[w.submit_time.ge(begin)&w.submit_time.lt(end)]
  yy=np.bincount(((ss.submit_time.astype('int64').to_numpy()-begin.value)//900_000_000_000).astype(int),weights=ss.work_GPUh,minlength=96)
  if i<349:raw_errors.append(float(np.max(abs(yy-atomic[i]))));continue
  atomic[i]=yy
  hh=env['features'](day,b,w)
  # inherited features for all 96 slots have same history/seasonal construction; AST returns all rows here.
  src2=ast.parse((OUT/'history/A/dayahead/v41/workload.py').read_text())
  fun=next(n for n in src2.body if isinstance(n,ast.FunctionDef) and n.name=='features');cut=next(k for k,n in enumerate(fun.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='values2' for t in n.targets));fun.body=fun.body[:cut]+[ast.Return(ast.Name('inherited',ast.Load()))];ast.fix_missing_locations(fun)
  e2=dict(env);exec(compile(ast.Module(body=[fun],type_ignores=[]),'features61','exec'),e2);base61[i]=e2['features'](day,b,w)
  idx=pd.date_range(issue-pd.Timedelta(days=7),periods=336,freq='30min');hv=env['history_values'](b,idx,issue);local=idx.tz_convert('Etc/GMT-10');hr=local.hour+local.minute/60;dow=local.dayofweek
  past[i]=np.column_stack([hv,np.sin(2*np.pi*hr/24),np.cos(2*np.pi*hr/24),np.sin(2*np.pi*dow/7),np.cos(2*np.pi*dow/7)])
  for j,lag in enumerate([7,14,21,28]):
   starts=pd.date_range(begin-pd.Timedelta(days=lag),periods=96,freq='15min');ix=starts.floor('30min');bb=b.loc[ix]
   close=bb.max_observed_end.reset_index(drop=True);right=pd.Series(ix+pd.Timedelta(minutes=30));close=close.where(close.notna()&close.gt(right),right)
   sm[i,:,j]=(bb.unresolved_end_count.to_numpy()==0)&close.lt(issue).to_numpy()
   ww=w[w.submit_time.ge(starts[0])&w.submit_time.lt(starts[-1]+pd.Timedelta(minutes=15))]
   sw[i,:,j]=np.where(sm[i,:,j],np.bincount(((ww.submit_time.astype('int64').to_numpy()-starts[0].value)//900_000_000_000).astype(int),weights=ww.work_GPUh,minlength=96),0)
  # Full day closes only when every positive-GPU submitted job has ended; matches V41 extension.
  db=b.loc[(b.index>=begin)&(b.index<end)];av=max(end,ss.end_time.max()) if len(ss) else end
  if db.gpu_unresolved.sum():av=pd.Timestamp.max.tz_localize('UTC')
  extra.append({'operating_day':day,'forecast_origin':issue,'target_start':begin,'target_end':end,'target_label_available_at':av,'role':'MAY_HISTORICAL' if day>='2025-05-01' else 'OOS_EXTENSION','stage_cutoff':pd.NaT,'stage_maturity_eligible':True,'modeled_jobs':len(ss),'total_GPUh':yy.sum()})
 ledger=pd.concat([ledger,pd.DataFrame(extra)],ignore_index=True);ledger.to_parquet(OUT/'DAY_LEDGER.parquet',index=False)
 assert max(raw_errors)<1e-7,('historical raw target mismatch',max(raw_errors))
 frames=[];arrays={};feature_errors={}
 original=pd.read_parquet(R6/'V40R6_CUMULATIVE_TARGET.parquet');ox=np.load(R6/'features.npz')['X']
 for h in [1,2,4,8]:
  k=h*4;n=97-k;y=np.lib.stride_tricks.sliding_window_view(atomic,k,axis=1).sum(-1);xx=np.concatenate([base61[:,:n],np.broadcast_to(np.stack([np.arange(n),np.full(n,h)],-1),(N,n,2))],-1)
  for j in range(4):
   mask=np.lib.stride_tricks.sliding_window_view(sm[:,:,j],k,axis=1).all(-1);vals=np.lib.stride_tricks.sliding_window_view(sw[:,:,j],k,axis=1).sum(-1);xx=np.concatenate([xx,np.stack([np.where(mask,vals,0),mask],-1)],-1)
  xx=xx.astype('float32');arrays[f'X{h}']=xx;arrays[f'y{h}']=y
  if h!=2:
   expected=ox[original.horizon.eq(f'H{h}')].reshape(349,n,71);feature_errors[f'H{h}']=float(np.max(abs(expected-xx[:349])));assert np.array_equal(expected,xx[:349])
 arrays.update(atomic=atomic,past=past,days=np.array(days));np.savez_compressed(OUT/'DATA.npz',**arrays)
 dump('DATA_SPLITS_AND_MATURITY.json',{'original_ledger_sha256':sha(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet'),'membership_file':'DAY_LEDGER.parquet','periods':periods,'original_raw_target_max_error_GPUh':max(raw_errors),'original_feature_max_errors':feature_errors,'windows_per_day':{'H1':93,'H2':89,'H4':81,'H8':65},'available_days':[days[0],days[-1]],'full_day_maturity':'max(target_end,target_label_available_at) < issue','historical_membership_preserved':True,'synthetic_12site_augmentation':False,'NO_UNTOUCHED_CONFIRMATION':True})
 print('DATA READY',N,feature_errors,flush=True)
if __name__=='__main__':main()
