import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from pathlib import Path
import json,time,hashlib,sys,platform,subprocess,copy
import numpy as np,pandas as pd,lightgbm as lgb
from prepare_data import OUT,BASE,R5,R6,sha,dump
from models_offline import fit_predict,predict_saved,pinball,DEVICE
import torch
DATA=np.load(OUT/'DATA.npz');L=pd.read_parquet(OUT/'DAY_LEDGER.parquet');DAYS=DATA['days'];N=len(DAYS);ALL=np.arange(N)
TRAIN=np.flatnonzero((L.role=='TRAIN')&L.stage_maturity_eligible);DEV=np.flatnonzero((L.role=='DEVELOPMENT')&L.stage_maturity_eligible)
AV=np.maximum(pd.to_datetime(L.target_end,utc=True).astype('int64'),pd.to_datetime(L.target_label_available_at,utc=True).astype('int64')).to_numpy()
ISS=pd.to_datetime(L.forecast_origin,utc=True).astype('int64').to_numpy()
OOS=((L.role.isin(['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']))&L.stage_maturity_eligible)|L.role.isin(['OOS_EXTENSION','MAY_HISTORICAL'])
SEEDS=[20260924,20260925,20260926];RUNS=[]
def quant(v,t):
 k=min(max(int(np.ceil(t*(len(v)+1))),1),len(v));return float(np.partition(np.asarray(v),k-1)[k-1]),k
def calibrate(q,h,level=.9):
 y=DATA[f'y{h}'];cal=q[:,:,1].copy();delta=np.zeros(N);counts=np.zeros(N,int);nd=np.zeros(N,int);hist=np.zeros(N);members=[]
 for i in range(N):
  ix=np.flatnonzero(OOS.to_numpy()&(AV<ISS[i])&(ALL<i)&np.isfinite(q[:,:,1]).all(1));nd[i]=len(ix);counts[i]=len(ix)*y.shape[1]
  if len(ix):
   res=(np.log1p(y[ix])-np.log1p(q[ix,:,1])).ravel();dd,rank=quant(res,level);delta[i]=max(0,dd)
  cal[i]=np.expm1(np.log1p(q[i,:,1])+delta[i])
  capix=np.flatnonzero((AV<ISS[i])&(ALL<i));hist[i]=quant(y[capix].ravel(),.99)[0] if len(capix) else 0
  members.append({'day':str(DAYS[i]),'source_days':[str(d) for d in DAYS[ix]],'N_days':len(ix),'N_windows':len(ix)*y.shape[1],'membership_sha256':hashlib.sha256(('\n'.join(DAYS[ix])+'\n').encode()).hexdigest()})
 return cal,delta,counts,nd,hist,members
def devscore(q,h):
 c,_,_,nd,_,_=calibrate(q,h);ix=DEV[nd[DEV]>=20]
 assert len(ix)>0
 return float(pinball(DATA[f'y{h}'][ix],c[ix])),float(c[ix].mean()),len(ix)
def record(meta,tag,h,phase):
 m={k:v for k,v in meta.items() if k!='history'};m.update(run_id=tag,horizon=h,phase=phase,environment='ENVIRONMENT.json',protocol_sha256=sha(OUT/'EXPERIMENT_PROTOCOL.json'));RUNS.append(m);pd.DataFrame(RUNS).to_csv(OUT/'TRAINING_RUN_LEDGER.csv',index=False)
def tree(h,train,ids,seed,tag,frozen=False):
 folder=OUT/'fits'/tag;folder.mkdir(parents=True,exist_ok=True);X=DATA[f'X{h}'];Y=DATA[f'y{h}'];res=[];start=time.perf_counter();params=0
 for tau in [.5,.9]:
  path=folder/f'Q{int(100*tau)}.txt'
  if not path.exists():
   if frozen:
    import shutil
    shutil.copyfile(R6/f'fits/L0/H{h}_Q{int(100*tau)}.txt',path)
   else:
    model=lgb.LGBMRegressor(objective='quantile',alpha=tau,num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,deterministic=True,force_col_wise=True,random_state=seed,verbosity=-1)
    model.fit(X[train].reshape(-1,71),np.log1p(Y[train].ravel()));path.write_text(model.booster_.model_to_string(),encoding='utf-8')
  model=lgb.Booster(model_str=path.read_text(encoding='utf-8'));params+=sum(t['num_leaves'] for t in model.dump_model()['tree_info'])
 train_s=time.perf_counter()-start;start=time.perf_counter()
 for tau in [.5,.9]:res.append(np.expm1(lgb.Booster(model_str=(folder/f'Q{int(100*tau)}.txt').read_text(encoding='utf-8')).predict(X[ids].reshape(-1,71),num_threads=1)).reshape(len(ids),-1))
 q=np.maximum(np.stack(res,-1),0);q[:,:,1]=np.maximum(q[:,:,0],q[:,:,1]);meta={'family':'LGBM','seed':seed,'training_seconds':train_s,'inference_seconds':time.perf_counter()-start,'N_training_days':len(train),'N_inference_days':len(ids),'parameter_count':params,'parameter_count_definition':'tree leaf values across Q50/Q90; not neural parameter count','gpu_peak_memory_bytes':0,'device':'cpu','cpu_threads':1,'frozen_reuse':frozen,'model_sha256':sha(folder/'Q90.txt')}
 record(meta,tag,h,'fixed' if 'refit' not in tag else 'refit');return q,meta
def neural(family,h,seed,lr,tag,train=TRAIN,dev=DEV,ids=DEV,frozen=None,epochs=None):
 folder=OUT/'fits'/tag
 if (folder/'receipt.json').exists():
  meta=json.loads((folder/'receipt.json').read_text());q=np.load(folder/'prediction.npy');cfg=torch.load(folder/'model.pt',weights_only=False,map_location='cpu')['config']
 else:q,meta,cfg=fit_predict(family,DATA['past'],DATA[f'X{h}'],DATA[f'y{h}'],train,dev,ids,seed,lr,folder,frozen,epochs)
 record(meta,tag,h,'development_search' if 'trial' in tag else 'refit' if 'refit' in tag else 'selected_3seed');return q,meta,cfg
def blank(h):return np.full((N,97-4*h,2),np.nan)
def seasonal(h):
 y=DATA[f'y{h}'];q=np.zeros((*y.shape,2));weekday=np.array([pd.Timestamp(str(d)).weekday() for d in DAYS])
 for i in range(N):
  mature=TRAIN[AV[TRAIN]<ISS[i]]
  if not len(mature):continue
  same=mature[weekday[mature]==weekday[i]];pool=same if len(same)>=8 else mature
  q[i]=np.quantile(y[pool],[.5,.9],axis=0).T
 return q
def frozen_repro():
 q,meta=tree(4,TRAIN,ALL,20260907,'F0_FROZEN',True);a=np.load(R6/'exposed_predictions.npz');frame=pd.read_parquet(R6/'V40R6_CUMULATIVE_TARGET.parquet');selected=frame.iloc[a['row_ids']];mask=selected.horizon.eq('H4').to_numpy();expected=a['q'][mask];actual=q[selected.loc[mask,'day_index'],selected.loc[mask,'window_start_slot']]
 error=float(abs(expected-actual).max());assert error<1e-7
 repro=[];c,de,_,_,hc,members=calibrate(q,4,.85)
 for i in np.flatnonzero(L.role.eq('MAY_HISTORICAL')):
  root=BASE/'CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4'/str(DAYS[i])/'B0/dayahead/ml';j=json.loads((root/'ML_SNAPSHOT.json').read_text())
  errx=float(abs(DATA['X4'][i]-np.asarray(j['H4_features'])).max());errq=float(abs(q[i,:,1]-j['H4_BASE_L0_upper']).max());errc=float(abs(c[i]-j['H4_RAW_R85_B2_GPUh']).max())
  repro.append({'day':str(DAYS[i]),'features_max_error':errx,'base_Q90_max_error':errq,'delta85_error':float(abs(de[i]-j['H4_delta85'])),'uncapped_max_error':errc,'cap_hist_error':abs(hc[i]-j['H4_CAP_HIST']),'original_membership_rows':j['H4_calibration_support']['rows'],'reconstructed_membership_rows':members[i]['N_windows']})
 dump('FROZEN_REPRODUCTION.json',{'exposed_q_max_error':error,'May':repro})
 assert max(v['base_Q90_max_error'] for v in repro)<1e-6
 assert max(v['uncapped_max_error'] for v in repro)<1e-5
 np.save(OUT/'FROZEN_Q.npy',q);print('FROZEN REPRODUCTION PASS',flush=True);return q
def run_refit(family,h,seed,cadence,selection,stage):
 cfg=selection[family];q=blank(h);start=DEV[0];until=DEV[-1] if stage=='cadence' else N-1
 fixed=OUT/'fits'/cfg['seed_tags'][str(seed)];fixedconf=torch.load(fixed/'model.pt',weights_only=False,map_location='cpu')['config'] if family!='LGBM' else None
 # Include the fixed predictor before first refit and retain causal OOS predictions from each deployment.
 if family=='LGBM':fq,_=tree(h,TRAIN,np.arange(until+1),seed,f'refit_initial_LGBM_s{seed}_{stage}_{cadence}')
 else:fq,_=predict_saved(fixed,DATA['past'],DATA[f'X{h}'],np.arange(until+1))
 q[:until+1]=fq;receipts=[]
 for cut in range(start,until+1,cadence):
  ids=np.arange(cut,min(cut+cadence,until+1));tr=np.flatnonzero((ALL<cut)&(AV<ISS[cut])&(DAYS>=str(DAYS[TRAIN[0]])))
  assert np.all(AV[tr]<ISS[cut])
  tag=f'refit_{stage}_{family}_H{h}_s{seed}_c{cadence}_{DAYS[cut]}'
  if family=='LGBM':qq,_=tree(h,tr,ids,seed,tag)
  else:qq,_,_=neural(family,h,seed,cfg['lr'],tag,train=tr,dev=DEV,ids=ids,frozen=fixedconf,epochs=cfg['epochs'])
  q[ids]=qq
  for i in ids:receipts.append({'family':family,'seed':seed,'cadence':cadence,'stage':stage,'issue_day':str(DAYS[i]),'refit_day':str(DAYS[cut]),'cutoff':str(L.forecast_origin.iloc[cut]),'training_days':[str(d) for d in DAYS[tr]],'N_training_days':len(tr),'N_training_windows':len(tr)*(97-4*h),'range_start':str(DAYS[tr[0]]),'range_end':str(DAYS[tr[-1]])})
 (OUT/'refit_memberships').mkdir(exist_ok=True);dump(f'refit_memberships/{stage}_{family}_{seed}_{cadence}.json',receipts);return q
def main():
 dump('ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'torch':torch.__version__,'lightgbm':lgb.__version__,'numpy':np.__version__,'pandas':pd.__version__,'device':DEVICE,'GPU':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'CUDA':torch.version.cuda,'CPU_THREADS':1,'DATALOADER_WORKERS':0,'nvidia_smi':subprocess.check_output(['nvidia-smi'],text=True),'time':pd.Timestamp.now(tz='UTC')})
 frozen=frozen_repro();selection={};scores=[]
 for family in ['TFT','DEEPAR']:
  trials=[]
  for ti,lr in enumerate([.001,.0003]):
   tag=f'trial_{family}_H4_{ti}';qq,meta,cfg=neural(family,4,SEEDS[0],lr,tag);q=blank(4);q[DEV]=qq;score,req,nd=devscore(q,4);trials.append((score,req,ti,lr,tag,meta));scores.append({'family':family,'lr':lr,'score':score,'mean_requirement':req,'N_score_days':nd,'selected_epoch':meta['selected_epoch']})
  winner=min(trials);_,_,ti,lr,tag,meta=winner;seed_tags={str(SEEDS[0]):tag};epochs=[meta['selected_epoch']];seed_scores=[]
  for seed in SEEDS:
   if seed==SEEDS[0]:qq=np.load(OUT/'fits'/tag/'prediction.npy')
   else:
    st=f'selected_{family}_H4_s{seed}';qq,mm,_=neural(family,4,seed,lr,st);seed_tags[str(seed)]=st;epochs.append(mm['selected_epoch'])
   q=blank(4);q[DEV]=qq;seed_scores.append(devscore(q,4)[0])
  selection[family]={'lr':lr,'seed_tags':seed_tags,'seed_development_scores':seed_scores,'mean_development_score':float(np.mean(seed_scores)),'epochs':int(np.median(epochs)),'all_best_epochs':epochs}
 best=min(selection,key=lambda f:selection[f]['mean_development_score']);selection['best_neural_family']=best
 selection['LGBM']={'seed_tags':{str(s):'NA' for s in SEEDS},'epochs':400,'lr':.03}
 dump('DEVELOPMENT_H4_SELECTION.json',selection);pd.DataFrame(scores).to_csv(OUT/'DEVELOPMENT_SEARCH.csv',index=False)
 print('H4 DEV FROZEN',best,selection[best]['mean_development_score'],flush=True)
 # Select cadence on DEVELOPMENT only, primary fixed seed, identical update rule for both families.
 cadence_rows=[]
 for cadence in [28,56]:
  for fam in ['LGBM',best]:
   q=run_refit(fam,4,SEEDS[0],cadence,selection,'cadence');score,req,nd=devscore(q,4);cadence_rows.append({'family':fam,'cadence':cadence,'score':score,'mean_requirement':req,'N_days':nd});np.save(OUT/f'cadence_{fam}_{cadence}.npy',q)
 cdf=pd.DataFrame(cadence_rows);cdf.to_csv(OUT/'REFIT_DEVELOPMENT_SELECTION.csv',index=False);cadence=int(cdf.groupby('cadence').score.mean().sort_values().index[0]);selection['refit_cadence_days']=cadence
 # Freeze horizon candidates using H4 evidence; no additional hyperparameter search.
 for h in [1,2,8]:
  for seed in SEEDS:
   tag=f'selected_{best}_H{h}_s{seed}';neural(best,h,seed,selection[best]['lr'],tag,epochs=selection[best]['epochs'])
 selection['frozen_at']=str(pd.Timestamp.now(tz='UTC'));selection['code_hashes']={p.name:sha(p) for p in [OUT/'models_offline.py',OUT/'run_experiment.py',OUT/'prepare_data.py']};selection['protocol_sha256']=sha(OUT/'EXPERIMENT_PROTOCOL.json');dump('FINAL_SELECTION_FREEZE.json',selection)
 print('ALL SETTINGS FROZEN; historical evaluation begins',flush=True)
 predictions=[]
 for h in [4,1,2,8]:
  modelqs=[]
  if h==4:modelqs.append(('F0_FROZEN',20260907,'fixed',frozen))
  for seed in SEEDS:
   q,_=tree(h,TRAIN,ALL,seed,f'F1_LGBM_H{h}_s{seed}');modelqs.append(('F1_LGBM',seed,'fixed',q))
  for fam in (['TFT','DEEPAR'] if h==4 else [best]):
   for seed in SEEDS:
    tag=selection[fam]['seed_tags'][str(seed)] if h==4 else f'selected_{fam}_H{h}_s{seed}'
    q,meta=predict_saved(OUT/'fits'/tag,DATA['past'],DATA[f'X{h}'],ALL);np.save(OUT/'fits'/tag/'all_prediction.npy',q);dump(f'fits/{tag}/inference_receipt.json',meta);modelqs.append(('F2_TFT' if fam=='TFT' else 'F3_DEEPAR',seed,'fixed',q))
  modelqs.append(('SEASONAL',0,'fixed',seasonal(h)))
  y=DATA[f'y{h}']
  for name,const in [('TRIVIAL_CAP',780*h),('TRIVIAL_TRAIN_MAX',float(y[TRAIN].max()))]:modelqs.append((name,0,'fixed',np.full((*y.shape,2),const)))
  if h==4:
   for fam in ['LGBM',best]:
    for seed in SEEDS:
     q=run_refit(fam,h,seed,cadence,selection,'final');modelqs.append(('F1_LGBM' if fam=='LGBM' else 'F2_TFT' if fam=='TFT' else 'F3_DEEPAR',seed,'expanding',q))
  for name,seed,mode,q in modelqs:
   c,delta,nres,nd,hist,members=calibrate(q,h,.85 if name=='F0_FROZEN' else .9);dump(f'calibration_{name}_H{h}_{seed}_{mode}.json',members)
   for i in np.r_[DEV,np.flatnonzero(L.role.isin(['EXPOSED_EVALUATION','MAY_HISTORICAL']))]:
    n=y.shape[1];phys=np.full(n,780*h);hc=hist[i]
    if h==4 and L.role.iloc[i]=='MAY_HISTORICAL':
     sp=BASE/'CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4'/str(DAYS[i])/'B0/dayahead/ml/ML_SNAPSHOT.json';ss=json.loads(sp.read_text());phys=np.array(ss['H4_CAP_PHYS']);hc=ss['H4_CAP_HIST']
    predictions.append(pd.DataFrame({'model':name,'seed':seed,'training_mode':mode,'horizon_hours':h,'day':str(DAYS[i]),'issue_time':L.forecast_origin.iloc[i],'role':L.role.iloc[i],'window_start_slot':np.arange(n),'lead_hours':6+np.arange(n)/4,'target_GPUh':y[i],'q50':q[i,:,0],'raw_q90':q[i,:,1],'calibrated_q90':c[i],'delta':delta[i],'calibration_N_days':nd[i],'calibration_N_windows':nres[i],'physical_cap':phys,'historical_cap':hc,'actionable':np.minimum(c[i],np.minimum(phys,hc)),'secured_reserve':np.nan,'burst_threshold':float(np.quantile(y[TRAIN][y[TRAIN]>0],.95))}))
  pd.concat(predictions,ignore_index=True).to_parquet(OUT/'PREDICTIONS.parquet',index=False)
 dump('EXECUTION_COMPLETE.json',{'time':str(pd.Timestamp.now(tz='UTC')),'N_runs':len(RUNS),'N_predictions':sum(len(p) for p in predictions),'selected_family':best,'cadence':cadence,'NEW_MODEL_AUTO_DEPLOYED':False,'OPTIMIZER_CHANGED':False,'GRID_CAMPAIGN_EXECUTIONS':0,'EXISTING_PRODUCTION_MODIFIED':False})
 print('EXPERIMENT COMPLETE',flush=True)
if __name__=='__main__':main()

