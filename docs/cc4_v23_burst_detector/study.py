"""CC4-v2.3: high-recall detector development with frozen workload magnitude models."""
import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import argparse,gzip,hashlib,importlib.util,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import average_precision_score
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'cc4_v22_burst_tail';BASE=ROOT.parent/'cc4_v2_hourly_future_workload'
spec=importlib.util.spec_from_file_location('cc4_v22_readonly_authority',PARENT/'study.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
Z,Y,C0,L,DAYS,AV,ISS,TR,OOS=(getattr(old,n) for n in ['Z','Y','C0','L','DAYS','AV','ISS','TR','OOS'])
PARAMS=old.PARAMS.copy();BURST=old.threshold();ROLES=old.ROLES
THRESHOLDS=[.0025,.005,.01,.02,.05,.10];TAIL_LEVELS=[.5,.75,.9];DETECTORS=['D1_BASE71_BALANCED','D2_EXTENDED_BALANCED']
TAIL_ROOT=Path(os.environ.get('CC4_V23_TAIL_CHECKPOINTS','D:/ChatGPT/Mobile ESS 2/cc4_v22_burst_tail_pr/docs/cc4_v22_burst_tail'))
TAIL_HASHES={r['path']:r['sha256'] for r in json.loads((PARENT/'MODEL_CHECKPOINT_MANIFEST.json').read_text(encoding='utf-8'))['files']}
FX=None
def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def now():return pd.Timestamp.now(tz='UTC').isoformat()
def clean(x):
 if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray,pd.Index,pd.Series)):return [clean(v) for v in x]
 if isinstance(x,(np.integer,np.bool_)):return x.item()
 if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
 return x
def dump(p,x,exclusive=False):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x' if exclusive else 'w',encoding='utf-8',newline='\n') as f:json.dump(clean(x),f,indent=2,ensure_ascii=False,default=str,allow_nan=False)
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def csv(name,rows):pd.DataFrame(rows).to_csv(ROOT/(name+'.csv'),index=False,lineterminator='\n')
def feature_data():
 global FX
 if FX is None:
  stored=np.load(ROOT/'FEATURES.npz');FX=stored['X'] if 'X' in stored.files else stored['X_extended']
 return FX
def guard(final=False):
 r=read('FINAL_SELECTION_FREEZE.json' if final else 'CODE_FREEZE.json')
 for n,h in r['code'].items():require(sha(ROOT/n)==h,'CODE_DRIFT '+n)
 require(sha(ROOT/'PROTOCOL.json')==r['protocol_sha256'],'PROTOCOL_DRIFT')
 require(sha(ROOT/'FEATURES.npz')==read('FEATURE_RECEIPT.json')['feature_sha256'],'FEATURE_DRIFT')
def source_guard():
 for n,h in read('SOURCE_MANIFEST.json')['files'].items():require(sha(ROOT.parent/n)==h,'SOURCE_DRIFT '+n)
def prepare():
 require(not (ROOT/'FEATURE_RECEIPT.json').exists(),'FEATURES_ALREADY_REGISTERED')
 from causal_features import build_features
 x,names,audit,membership=build_features(BASE)
 require(x.shape[:2]==Y.shape and x.shape[2]>71,'FEATURE_SHAPE');require(np.array_equal(x[:,:,:71],Z['X']),'BASE_FEATURE_CHANGED');require(np.isfinite(x).all(),'FEATURE_NONFINITE')
 if (ROOT/'FEATURES.npz').exists():require(np.array_equal(feature_data(),x),'EXISTING_FEATURE_DRIFT')
 else:np.savez_compressed(ROOT/'FEATURES.npz',X=x)
 if (ROOT/'FEATURE_NAMES.json').exists():require(read('FEATURE_NAMES.json')==clean(names),'EXISTING_NAMES_DRIFT')
 else:dump('FEATURE_NAMES.json',names,True)
 if (ROOT/'FEATURE_MEMBERSHIP.json').exists():require(read('FEATURE_MEMBERSHIP.json')==clean(membership),'EXISTING_MEMBERSHIP_DRIFT')
 else:dump('FEATURE_MEMBERSHIP.json',membership,True)
 dump('FEATURE_AVAILABILITY_AUDIT.json',audit,True)
 dump('FEATURE_RECEIPT.json',dict(time=now(),feature_sha256=sha(ROOT/'FEATURES.npz'),feature_source_sha256=sha(ROOT/'causal_features.py'),N_features=x.shape[2],selection_used=False,post_May_exposure=True),True)
def register():
 require(not (ROOT/'PROTOCOL.json').exists(),'REGISTERED');require(np.isfinite(C0[OOS]).all(),'C0_MISSING')
 files=dict(json.loads((PARENT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files'])
 for n,h in read('FEATURE_AVAILABILITY_AUDIT.json')['source_sha256'].items():files[BASE.name+'/'+n]=h
 for r in json.loads((PARENT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['files']:
  require(sha(PARENT/r['path'])==r['sha256'],'PARENT_NOT_SEALED');files[PARENT.name+'/'+r['path']]=r['sha256']
 files[PARENT.name+'/DELIVERY_MANIFEST.json']=sha(PARENT/'DELIVERY_MANIFEST.json')
 dump('SOURCE_MANIFEST.json',dict(parent_PR=67,parent_commit='73c719186fdc460ca172632112ae595848bd36da',files=files),True);source_guard()
 require((AV.iloc[TR]<ISS.iloc[OOS[0]]).all(),'THRESHOLD_NOT_MATURE')
 dump('PROTOCOL.json',dict(time=now(),version='CC4-v2.3',May='exposed historical diagnostic; no untouched confirmation',
  fixed_base='raw PR64 expanding30day recency dailyLightGBM, unchanged predictions and temporal membership; fixed PR67 conditional-tail checkpoints reused',
  burst_threshold=dict(value=BURST,definition='unchanged TRAIN eligible positive-hour95th percentile',days=DAYS[TR]),
  detector_parameters=PARAMS,detectors=DETECTORS,old_detector='PR67 unweighted71-feature score reference only',
  imbalance='positive weight alpha=sum(recency weights for negative)/sum(for positive), computed from causal fit only; inverse prior odds q/(alpha-(alpha-1)*q) yields probability estimate, not a calibration guarantee',
  feature_ablation='balanced existing71 vs balanced extended features; same causal membership, weights, classifier parameters',
  threshold_grid=THRESHOLDS,tail_quantile_grid=TAIL_LEVELS,
  C1='expanding mature past OOS high-risk C0 residuals; finite-rank90th quantile positive correction; minimum50hours10days else0',
  C2='conditional burst-tail Q50/Q75/Q90 from unchanged PR67 expert, applied only inside detector gate, max(C0,conditional tail). Operational Q90 candidate, not an analytically calibrated unconditional quantile.',
  tail_sparse='same PR67 support below50hours10days -> C0',
  selection=dict(hard='separately in DEV and CAL: detector recall>=.60, final burst coverage>=.60, positive coverage>=.85, requirement ratio<2, Q90 pinball<=1.02*C0',
   meaningful_pinball_inferiority_fraction=.02,preferred='overall88..92; detector and final burst>=.70',
   feasible_rank='preferred overall both roles, preferred70% both roles, mean requirement ratio, negative precision, FPR, negative PR-AUC, pinball',
   research_fallback='equal sum normalized deficits for all hard criteria over both roles, then same reserve/precision/FPR/PR-AUC/pinball priorities; no adoption if infeasible',
   per_family='freeze one research candidate for C1 and C2; select C0 if no hard-feasible challenger; no evaluation reselection'),
  bootstrap=dict(draws=2000,blocks_observed_days=[1,7],seed=20260927,paired=True,conditional_on_frozen_forecasts=True),
  evaluation_updates='mature earlier labels may enter fixed refits, historical features and residuals; never tuning',
  TEMPORAL_POLICY_CHANGED=False,BASE_MODEL_CHANGED=False,PRODUCTION_PROMOTED=False,optimizer_executions=0),True)
 L.to_csv(ROOT/'DAY_MEMBERSHIP.csv',index=False,lineterminator='\n')
 dump('CODE_FREEZE.json',dict(time=now(),code={p.name:sha(p) for p in ROOT.glob('*.py')},protocol_sha256=sha(ROOT/'PROTOCOL.json')),True)

def corrected_probability(q,alpha):
 q=np.asarray(q,float);require(np.isfinite(q).all() and ((q>=0)&(q<=1)).all(),'CLASSIFIER_SCORE_INVALID')
 p=q/(alpha-(alpha-1)*q);require(np.isfinite(p).all() and ((p>=0)&(p<=1)).all(),'RISK_INVALID');return p
def fit_day(i):
 guard();path=ROOT/'raw'/f'{DAYS[i]}.npz'
 if path.exists():return
 tr=old.membership(i);w=np.repeat(np.asarray(old.weights(tr,i)),24);target=(Y[tr].ravel()>BURST).astype(int)
 require((AV.iloc[tr]<ISS.iloc[i]).all(),'TRAIN_IMMATURITY');require(len(np.unique(target))==2,'CLASS_SUPPORT')
 alpha=float(w[target==0].sum()/w[target==1].sum());folder=ROOT/'fits'/DAYS[i];folder.mkdir(parents=True,exist_ok=True);out={}
 for name in DETECTORS:
  x=Z['X'] if name==DETECTORS[0] else feature_data();width=x.shape[2]
  model=lgb.LGBMClassifier(objective='binary',scale_pos_weight=alpha,**PARAMS).fit(x[tr].reshape(-1,width),target,sample_weight=w).booster_
  modelpath=folder/(name+'.txt.gz');modelpath.write_bytes(gzip.compress(model.model_to_string().encode(),mtime=0))
  out[name]=corrected_probability(model.predict(x[i],num_threads=1),alpha)
 oldmeta=json.loads((PARENT/'fits'/DAYS[i]/'MEMBERSHIP.json').read_text(encoding='utf-8'));supported=bool(oldmeta['tail_supported']);full_tail=np.full((24,len(old.GRID)),BURST);tail_receipts={}
 if supported:
  for k,tau in enumerate(old.GRID):
   relative=f'fits/{DAYS[i]}/tail_{tau}.txt.gz';file=TAIL_ROOT/relative;require(file.exists() and sha(file)==TAIL_HASHES[relative],'FROZEN_TAIL_CHECKPOINT '+relative)
   model=lgb.Booster(model_str=gzip.decompress(file.read_bytes()).decode());full_tail[:,k]=np.maximum(BURST,np.expm1(model.predict(Z['X'][i],num_threads=1)));tail_receipts[relative]=sha(file)
 full_tail=np.maximum.accumulate(full_tail,axis=1);tail=full_tail[:,[list(old.GRID).index(t) for t in TAIL_LEVELS]];out['tail']=tail;out['tail_supported']=np.array(supported)
 out['D0_OLD']=np.load(PARENT/'raw'/f'{DAYS[i]}.npz')['risk']
 if supported:require(np.array_equal(old.tail_bound(out['D0_OLD'],full_tail,BURST),np.load(PARENT/'raw'/f'{DAYS[i]}.npz')['tail']),'TAIL_REPLAY_NOT_EXACT')
 path.parent.mkdir(exist_ok=True);np.savez_compressed(path,**out)
 np.savez_compressed(folder/'TRAIN_MEMBERSHIP.npz',day_indices=tr,weights=np.asarray(old.weights(tr,i)),burst_flat_indices=np.flatnonzero(target))
 dump(folder.relative_to(ROOT)/'RECEIPT.json',dict(issue=ISS.iloc[i],day_index=i,N_train_days=len(tr),latest_maturity=AV.iloc[tr].max(),alpha=alpha,
  membership_sha256=sha(folder/'TRAIN_MEMBERSHIP.npz'),models={p.name:sha(p) for p in folder.glob('*.gz')},tail_sources=tail_receipts,prediction_sha256=sha(path),feature_sha256=read('FEATURE_RECEIPT.json')['feature_sha256']))
 print('FIT',DAYS[i],len(tr),round(alpha,3),flush=True)
def forecast(through):
 guard();source_guard();from concurrent.futures import ProcessPoolExecutor
 with ProcessPoolExecutor(max_workers=2) as pool:list(pool.map(fit_day,map(int,OOS[DAYS[OOS]<=through])))
def raw(through):
 ids=OOS[DAYS[OOS]<=through];risk={n:np.full(Y.shape,np.nan) for n in DETECTORS+['D0_OLD']};tail=np.full((*Y.shape,3),np.nan);support=np.zeros(len(DAYS),bool)
 for i in ids:
  r=np.load(ROOT/'raw'/f'{DAYS[i]}.npz')
  for n in risk:risk[n][i]=r[n]
  tail[i]=r['tail'];support[i]=bool(r['tail_supported'])
 return ids,risk,tail,support
def compose(through,config,data=None):
 ids,risk,tail,support=raw(through) if data is None else data;p=risk[config['detector']];q=C0.copy();proof=[];threshold=config['threshold']
 for i in ids:
  gate=p[i]>=threshold
  if config['family']=='C1':
   prev=ids[(ids<i)&(AV.iloc[ids]<ISS.iloc[i]).to_numpy()&L.split.iloc[ids].ne('PURGE').to_numpy()];d,h=np.where(p[prev]>=threshold);days=prev[d]
   eligible=len(d)>=50 and len(np.unique(days))>=10;delta=old.residual_delta((Y[prev]-C0[prev,:,1])[p[prev]>=threshold]) if eligible else 0.
   q[i,gate,1]+=delta;proof.append(dict(day=DAYS[i],issue=ISS.iloc[i],pool_day_indices=days,pool_hours=h,delta=delta,supported=eligible))
  elif support[i]:q[i,gate,1]=np.maximum(C0[i,gate,1],tail[i,gate,TAIL_LEVELS.index(config['tail_quantile'])])
 return q,p,proof
def detector_metrics(y,p,threshold):
 b=y>BURST;g=p>=threshold;positive=int(b.sum());negative=int((~b).sum());tp=int((b&g).sum());pp=int(g.sum())
 return dict(detector_recall=tp/positive if positive else np.nan,precision=tp/pp if pp else 0.,false_positive_rate=int((~b&g).sum())/negative if negative else np.nan,
  PR_AUC=float(average_precision_score(b.ravel(),p.ravel())) if positive else np.nan,gated_fraction=float(g.mean()),gated_hours=pp)
def score(q,p,ix,threshold):return dict(**old.stats(Y[ix],q[ix,:,1]),**detector_metrics(Y[ix],p[ix],threshold))
def criteria(m,b):
 values=[m['detector_recall'],m['burst_coverage'],m['positive_coverage'],m['requirement_ratio'],m['Q90_pinball'],m['precision'],m['false_positive_rate'],m['PR_AUC']]
 require(np.isfinite(values).all(),'NONFINITE_SELECTION_METRIC')
 deficits=[max(0,1-m['detector_recall']/.60),max(0,1-m['burst_coverage']/.60),max(0,1-m['positive_coverage']/.85),max(0,m['requirement_ratio']/2-1),max(0,m['Q90_pinball']/(1.02*b['Q90_pinball'])-1)]
 feasible=sum(deficits)==0 and m['requirement_ratio']<2
 return feasible,sum(deficits)
def select():
 require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'ALREADY_SELECTED');guard();data=raw('2024-11-30');rows=[];choices={}
 baseline={r:old.stats(Y[old.role_ids(r)],C0[old.role_ids(r),:,1]) for r in ROLES[:2]}
 for family in ['C1','C2']:
  ranked=[]
  for detector in DETECTORS:
   for threshold in THRESHOLDS:
    for tau in ([None] if family=='C1' else TAIL_LEVELS):
     config=dict(family=family,detector=detector,threshold=threshold,tail_quantile=tau);q,p,_=compose('2024-11-30',config,data);m=[score(q,p,old.role_ids(r),threshold) for r in ROLES[:2]]
     checks=[criteria(v,baseline[r]) for r,v in zip(ROLES[:2],m)];valid=all(c[0] for c in checks)
     preferred=all(.88<=v['coverage']<=.92 for v in m);target=all(v['detector_recall']>=.7 and v['burst_coverage']>=.7 for v in m)
     rank=(not valid,0. if valid else sum(c[1] for c in checks),not preferred,not target,np.mean([v['requirement_ratio'] for v in m]),-np.mean([v['precision'] for v in m]),np.mean([v['false_positive_rate'] for v in m]),-np.mean([v['PR_AUC'] for v in m]),np.mean([v['Q90_pinball'] for v in m]))
     ranked.append((rank,config,valid))
     rows.extend(dict(role=r,**config,hard_feasible=checks[k][0],normalized_deficit=checks[k][1],**v) for k,(r,v) in enumerate(zip(ROLES[:2],m)))
  rank,config,valid=sorted(ranked,key=lambda v:v[0])[0];choices[family]=dict(config=config,hard_feasible=valid,rank=rank)
 eligible=[(v['rank'],family) for family,v in choices.items() if v['hard_feasible']];winner=sorted(eligible)[0][1] if eligible else 'C0'
 csv('SELECTION_METRICS',rows)
 dump('FINAL_SELECTION_FREEZE.json',dict(time=now(),choices=choices,selected=winner,code=read('CODE_FREEZE.json')['code'],protocol_sha256=sha(ROOT/'PROTOCOL.json'),selection_metrics_sha256=sha(ROOT/'SELECTION_METRICS.csv'),current_evaluation_computed=False,May_previously_exposed=True),True)
 print('FROZEN',winner,choices,flush=True)

def vector(y,q,p,t):
 b=y>BURST;pos=y>0;g=p>=t;e=y-q
 return np.column_stack([np.full(len(y),24),pos.sum(1),b.sum(1),y.sum(1),q.sum(1),(y<=q).sum(1),((y<=q)&pos).sum(1),((y<=q)&b).sum(1),np.maximum(.9*e,-.1*e).sum(1),(g&b).sum(1),g.sum(1),(~b).sum(1),(g&~b).sum(1)])
def summary(v):
 s=v.sum(-2);prec=np.divide(s[...,9],s[...,10],out=np.zeros_like(s[...,9]),where=s[...,10]>0)
 return np.stack([s[...,8]/s[...,0],s[...,5]/s[...,0],s[...,6]/s[...,1],s[...,7]/s[...,2],s[...,4]/s[...,3],s[...,9]/s[...,2],prec,s[...,12]/s[...,11]],axis=-1)
def paired(y,q,p,t,bq,bp,bt,block):
 va,vb=vector(y,q,p,t),vector(y,bq,bp,bt);n=len(y);rng=np.random.default_rng(20260927);starts=rng.integers(n,size=(2000,int(np.ceil(n/block))));ix=((starts[:,:,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
 ds=summary(va[ix])-summary(vb[ix]);point=summary(va)-summary(vb);require(np.isfinite(ds).all() and np.isfinite(point).all(),'BOOTSTRAP_METRIC_UNDEFINED');names=['Q90_pinball','coverage','positive_coverage','burst_coverage','requirement_ratio','detector_recall','precision','false_positive_rate'];rows=[]
 for k,name in enumerate(names):rows.append(dict(metric=name,delta=point[k],CI95_low=np.quantile(ds[:,k],.025),CI95_high=np.quantile(ds[:,k],.975),N_days=n,draws=2000,block_observed_days=block))
 # Noninferiority margin uses candidate minus 1.02*baseline loss on every resample.
 base=summary(vb[ix])[:,0];margin=ds[:,0]-.02*base
 rows.append(dict(metric='pinball_minus_2pct_margin',delta=point[0]-.02*summary(vb)[0],CI95_low=np.quantile(margin,.025),CI95_high=np.quantile(margin,.975),N_days=n,draws=2000,block_observed_days=block))
 ap=np.array([average_precision_score((y[j]>BURST).ravel(),p[j].ravel())-average_precision_score((y[j]>BURST).ravel(),bp[j].ravel()) for j in ix])
 require(np.isfinite(ap).all(),'BOOTSTRAP_AP_UNDEFINED')
 rows.append(dict(metric='PR_AUC',delta=average_precision_score((y>BURST).ravel(),p.ravel())-average_precision_score((y>BURST).ravel(),bp.ravel()),CI95_low=np.quantile(ap,.025),CI95_high=np.quantile(ap,.975),N_days=n,draws=2000,block_observed_days=block))
 return rows
def evaluate():
 require(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'EVALUATED');guard(True);source_guard();freeze=read('FINAL_SELECTION_FREEZE.json');data=raw('2025-05-31');ids,risk,tail,support=data
 configs={k:v['config'] for k,v in freeze['choices'].items()};outputs={'C0':(C0,risk['D0_OLD'],.1)};rows=[];strata=[];ci=[];pred=[];detector=[]
 for family,c in configs.items():
  q,p,proof=compose('2025-05-31',c,data);outputs[family]=(q,p,c['threshold']);dump(f'{family}_CALIBRATION_MEMBERSHIP.json',proof)
 for role in ROLES:
  ix=old.role_ids(role)
  for name,p in risk.items():
   for t in ([.1] if name=='D0_OLD' else THRESHOLDS):detector.append(dict(role=role,detector=name,threshold=t,**detector_metrics(Y[ix],p[ix],t)))
  for model,(q,p,t) in outputs.items():
   rows.append(dict(role=role,model=model,threshold=t,**score(q,p,ix,t)))
   for name,mask in [('zero',Y[ix]==0),('positive',Y[ix]>0),('burst',Y[ix]>BURST),('high_risk',p[ix]>=t),('low_risk',p[ix]<t)]:
    if mask.any():strata.append(dict(role=role,model=model,stratum=name,**old.stats(Y[ix][mask],q[ix,:,1][mask])))
   pred.append(pd.DataFrame(dict(day=np.repeat(DAYS[ix],24),hour=np.tile(np.arange(24),len(ix)),role=role,model=model,actual=Y[ix].ravel(),Q50=q[ix,:,0].ravel(),Q90=q[ix,:,1].ravel(),risk=p[ix].ravel(),threshold=t)))
   require(np.array_equal(q[ix][p[ix]<t],C0[ix][p[ix]<t]),'OUTSIDE_GATE_CHANGE');require(np.array_equal(q[ix,:,0],C0[ix,:,0]),'Q50_CHANGED')
   if role in ROLES[2:] and model!='C0':
    for block in [1,7]:ci.extend(dict(role=role,model=model,reference='C0 forecast / D0 old detector',**v) for v in paired(Y[ix],q[ix,:,1],p[ix],t,C0[ix,:,1],risk['D0_OLD'][ix],.1,block))
 for n,v in [('MODEL_METRICS',rows),('STRATIFIED_METRICS',strata),('PAIRED_UNCERTAINTY',ci),('DETECTOR_METRICS',detector)]:csv(n,v)
 pd.concat(pred,ignore_index=True).to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
 dump('EVALUATION_COMPLETE.json',dict(time=now(),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),historical_diagnostic_only=True),True)

def verify():
 guard(True);source_guard();require(sha(ROOT/'causal_features.py')==read('FEATURE_RECEIPT.json')['feature_source_sha256'],'FEATURE_SOURCE_DRIFT')
 from causal_features import build_features
 x,names,audit,membership=build_features(BASE);require(np.array_equal(x,feature_data()),'FEATURE_RECONSTRUCTION');require(names==read('FEATURE_NAMES.json'),'FEATURE_NAMES')
 require(clean(membership)==read('FEATURE_MEMBERSHIP.json'),'FEATURE_MEMBERSHIP_RECONSTRUCTION');require(clean(audit)==read('FEATURE_AVAILABILITY_AUDIT.json'),'FEATURE_AVAILABILITY_RECONSTRUCTION')
 for i in OOS:
  folder=ROOT/'fits'/DAYS[i];r=json.loads((folder/'RECEIPT.json').read_text(encoding='utf-8'));npz=np.load(folder/'TRAIN_MEMBERSHIP.npz');tr=old.membership(i)
  require(np.array_equal(npz['day_indices'],tr) and np.array_equal(npz['weights'],np.asarray(old.weights(tr,i))),'TEMPORAL_CHANGED')
  require(np.array_equal(npz['burst_flat_indices'],np.flatnonzero(Y[tr].ravel()>BURST)),'DETECTOR_LABEL_MEMBERSHIP')
  require((AV.iloc[tr]<ISS.iloc[i]).all(),'IMMATURE_TRAIN');require(sha(folder/'TRAIN_MEMBERSHIP.npz')==r['membership_sha256'],'MEMBERSHIP_HASH')
  require(sha(ROOT/'raw'/f'{DAYS[i]}.npz')==r['prediction_sha256'],'RAW_DRIFT')
  for n,h in r['models'].items():require(sha(folder/n)==h,'CLASSIFIER_DRIFT')
  for n,h in r['tail_sources'].items():require(sha(TAIL_ROOT/n)==h==TAIL_HASHES[n],'TAIL_CHANGED')
  p=np.load(ROOT/'raw'/f'{DAYS[i]}.npz')
  for n in DETECTORS:require(np.isfinite(p[n]).all() and ((p[n]>=0)&(p[n]<=1)).all(),'INVALID_RISK')
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');freeze=read('FINAL_SELECTION_FREEZE.json');data=raw('2025-05-31');expected_outputs={'C0':(C0,data[1]['D0_OLD'],.1)}
 for model,c in freeze['choices'].items():
  q,p,proof=compose('2025-05-31',c['config'],data);require(clean(proof)==read(model+'_CALIBRATION_MEMBERSHIP.json'),'CALIBRATION_MEMBERSHIP')
  expected_outputs[model]=(q,p,c['config']['threshold'])
 for model,(q,p,t) in expected_outputs.items():
  for role in ROLES:
   ix=old.role_ids(role);g=f[f.model.eq(model)&f.role.eq(role)];require(len(g)==24*len(ix),'EVAL_EXCLUSION')
   require(np.array_equal(g.day.to_numpy(),np.repeat(DAYS[ix],24)) and np.array_equal(g.hour.to_numpy(),np.tile(np.arange(24),len(ix))),'OUTPUT_MEMBERSHIP')
   for col,values in [('actual',Y[ix]),('Q50',q[ix,:,0]),('Q90',q[ix,:,1]),('risk',p[ix])]:require(np.array_equal(g[col].to_numpy(),values.ravel()),'OUTPUT_RECONSTRUCTION '+col)
   require((g.threshold==t).all(),'OUTPUT_GATE_DRIFT')
 require(np.isfinite(f[['Q50','Q90','risk']].to_numpy()).all() and (f.Q90>=f.Q50).all(),'INVALID_OUTPUT')
 require(sha(ROOT/'PREDICTIONS.parquet')==read('EVALUATION_COMPLETE.json')['prediction_sha256'],'FINAL_HASH')
 require(sha(ROOT/'FINAL_SELECTION_FREEZE.json')==read('EVALUATION_COMPLETE.json')['freeze_sha256'],'EVALUATION_FREEZE_DRIFT')
 dump('VALIDATION.json',dict(time=now(),PASS=True,exact_daily_memberships=len(OOS),feature_reconstruction=True,all_model_digests=True,parent_evidence_unchanged=True,strict_maturity=True,outside_gate_unchanged=True,base_predictions_unchanged=True,production_modified=False))

def report():
 f=pd.read_csv(ROOT/'MODEL_METRICS.csv');c=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');freeze=read('FINAL_SELECTION_FREEZE.json');rows=[]
 for role in ROLES[2:]:
  b=f[f.role.eq(role)&f.model.eq('C0')].iloc[0]
  for model in ['C0','C1','C2']:
   r=f[f.role.eq(role)&f.model.eq(model)].iloc[0];rows.append(dict(role=role,model=model,overall_preferred=.88<=r.coverage<=.92,positive=r.positive_coverage>=.85,detector_recall=r.detector_recall>=.6,burst_coverage=r.burst_coverage>=.6,requirement_ratio=r.requirement_ratio<2,pinball_noninferior_point=r.Q90_pinball<=1.02*b.Q90_pinball))
 csv('GATES',rows);flags=dict(PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False)
 dump('VERDICT.json',dict(**flags,selected=freeze['selected'],TEMPORAL_POLICY_CHANGED=False,BASE_MODEL_CHANGED=False,reason='historical exposed model development; no untouched confirmation and ingestion provenance unverified; operational gates reported separately'))
 lines=['# CC4-v2.3 최종 검토','',f"선택은 evaluation 전에 **{freeze['selected']}**로 고정했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다.",'',
  'Base raw LightGBM과 temporal policy, conditional-tail magnitude model을 고정했다. 기존71 feature와 burst 확장 feature의 balanced LightGBM detector를 비교하고 DEV/CAL에서 gate와 correction을 선택했다. gate 밖 Q50/Q90은 C0와 같고 전체 Q90 scaling/capping은 없다.','',
  'C1은 예측 risk로 조건화한 과거 causal residual 보정이다. C2는 고정 expert의 conditional burst-tail quantile로 만든 operational Q90 후보이며 unconditional quantile의 수학적 보장을 주장하지 않는다. 2%를 의미 있는 pinball 악화 경계로 사전 지정했다.','',
  '| 구간 | 모델 | coverage | positive | detector recall | precision | FPR | PR-AUC | burst coverage | ratio | pinball |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
 for _,r in f.iterrows():lines.append(f'| {r.role} | {r.model} | {r.coverage:.2%} | {r.positive_coverage:.2%} | {r.detector_recall:.2%} | {r.precision:.2%} | {r.false_positive_rate:.2%} | {r.PR_AUC:.4f} | {r.burst_coverage:.2%} | {r.requirement_ratio:.3f} | {r.Q90_pinball:.3f} |')
 lines+=['','## 고정 candidate','', '```json',json.dumps(freeze['choices'],ensure_ascii=False,indent=2),'```','',
  '## Paired 95% CI','','1일과 7개 관측 target-day circular block을 2,000회 resampling했다. 아래는 7일 결과다. 예측 loss는 C0 대비, detector metric은 PR67 old detector/gate0.10 대비이며 selection uncertainty는 포함하지 않는다.','',
  '| 구간 | 모델 | 지표 | delta | 95% CI |','|---|---|---|---:|---|']
 for _,r in c[c.block_observed_days.eq(7)&c.metric.isin(['Q90_pinball','burst_coverage','detector_recall','pinball_minus_2pct_margin'])].iterrows():lines.append(f'| {r.role} | {r.model} | {r.metric} | {r.delta:.4f} | [{r.CI95_low:.4f}, {r.CI95_high:.4f}] |')
 lines+=['','## 판정','']+[f'- {k} = **{str(v).upper()}**' for k,v in flags.items()]
 lines+=['','모든 후보의 DEV/CAL 결과는 SELECTION_METRICS.csv, feature ablation과 threshold별 detector 결과는 DETECTOR_METRICS.csv, risk/burst strata와 gate 결과는 별도 CSV에 있다. 연구 candidate는 hard gate 실패 시에도 보고하지만 adoption으로 해석하지 않는다.','',
  '과거 mature evaluation labels는 고정 prequential feature/refit/residual 규칙에만 들어간다. 실제 ingestion latency와 request-version provenance는 미인증이다. finite-rank residual은 시계열 의존성에 대한 distribution-free coverage 보장을 주지 않는다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 및 production을 수정·실행하지 않았다.','']
 (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','register','development','select','evaluation','verify','report']);a=p.parse_args()
 if a.stage=='prepare':prepare()
 elif a.stage=='register':register()
 elif a.stage=='development':forecast('2024-11-30')
 elif a.stage=='select':select()
 elif a.stage=='evaluation':guard(True);forecast('2025-05-31');evaluate()
 elif a.stage=='verify':verify()
 else:report()
