"""Fixed LightGBM burst-tail follow-up. No production/optimizer imports."""
import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']: os.environ[k]='1'
import argparse,gzip,hashlib,json,sys,tarfile,time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'cc4_v21_causal_refit_hurdle'
BASE=ROOT.parent/'cc4_v2_hourly_future_workload'
TZ='Etc/GMT-10'
PARAMS=dict(num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,deterministic=True,force_col_wise=True,random_state=20260924,verbosity=-1)
GRID=np.array([.1,.25,.5,.75,.9])
GATE=.1
ROLES=['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','MAY_HISTORICAL']
Z=np.load(BASE/'DATA.npz'); DAYS=Z['days'].astype(str); L=pd.read_csv(BASE/'DAY_LEDGER.csv')
AV=pd.to_datetime(L.label_matured_at,utc=True); ISS=pd.to_datetime(L.issue_time,utc=True)
TR=np.flatnonzero(L.split.eq('TRAIN')&L.eligible)
OOS=np.flatnonzero(DAYS>='2024-09-01')
Y=Z['y']; C0=np.load(PARENT/'predictions/LGBM_weighted_c1_s20260924.npz')['q']

def require(ok,msg):
 if not ok: raise AssertionError(msg)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def now():return pd.Timestamp.now(tz='UTC').isoformat()
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def clean(x):
 if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
 if isinstance(x,(np.integer,np.bool_)):return x.item()
 if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
 return x
def dump(p,x,exclusive=False):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x' if exclusive else 'w',encoding='utf-8') as f:json.dump(clean(x),f,indent=2,ensure_ascii=False,default=str,allow_nan=False)
def threshold():
 y=Y[TR];return float(np.quantile(y[y>0],.95))
def membership(i):return np.flatnonzero((AV<ISS.iloc[i])&(ISS<ISS.iloc[i])&L.split.ne('PURGE'))
def weights(tr,i):return np.exp2(-np.maximum((ISS.iloc[i]-pd.to_datetime(DAYS[tr],utc=True)).total_seconds()/86400,0)/30)
def code_guard(name='CODE_FREEZE.json'):
 for p,h in read(name)['code'].items():
  expected=h
  if name=='CODE_FREEZE.json' and (ROOT/'AUDIT_AMENDMENT.json').exists() and p=='study.py':
   amendment=read('AUDIT_AMENDMENT.json');require(sha(ROOT/amendment['before_path'])==h,'AMENDMENT_BEFORE_DRIFT');expected=amendment['after_sha256']
  require(sha(ROOT/p)==expected,'FROZEN_CODE_DRIFT '+p)
 require(sha(ROOT/'PROTOCOL.json')==read(name)['protocol_sha256'],'PROTOCOL_DRIFT')
def source_guard():
 for p,h in read('SOURCE_MANIFEST.json')['files'].items():require(sha(ROOT.parent/p)==h,'SOURCE_DRIFT '+p)

def register():
 require(not (ROOT/'PROTOCOL.json').exists(),'REGISTERED')
 require(np.isfinite(C0[OOS]).all(),'BASELINE_INCOMPLETE')
 expected=json.loads((BASE/'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))['TRAIN_positive_Q95_burst_threshold_GPUh']
 require(threshold()==expected,'BURST_TRAIN_THRESHOLD_DRIFT')
 files={}
 for parent in [PARENT]:
  m=json.loads((parent/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
  for r in m['files']:
   require(sha(parent/r['path'])==r['sha256'],'PARENT_NOT_SEALED')
   files[(parent.name+'/'+r['path'])]=r['sha256']
  for n in ['DELIVERY_MANIFEST.json','POST_DELIVERY_ADDENDUM.json','RECEIPT_FIELD_CLARIFICATION_KO.md']:
   files[parent.name+'/'+n]=sha(parent/n)
 for n in ['DATA.npz','DAY_LEDGER.csv','FEATURE_MATURITY_PROOF.parquet','TARGET_RECONSTRUCTION_AUDIT.json','LEAKAGE_AUDIT.json']:
  files[BASE.name+'/'+n]=sha(BASE/n)
 dump('SOURCE_MANIFEST.json',dict(parent_PR=64,parent_commit='99a1d9d87eb1b6dd76ce41b734af8104099f992f',files=files),True)
 dump('PROTOCOL.json',dict(time=now(),version='CC4-v2.2',post_May_exposure_development=True,untouched_confirmation=False,
  temporal='unchanged expanding + 30-day half-life + daily refit; exact PR64 membership/weights',
  baseline='C0 raw refitted LGBM; exact PR64 weighted_c1 predictions; no architecture selection',
  burst_threshold=dict(value=threshold(),rule='TRAIN eligible positive-hour empirical95th percentile',train_days=DAYS[TR]),
  features='same71 causal PR63 features; inherited availability proof; actual ingestion authority unverified',parameters=PARAMS,
  risk_gate=dict(probability=GATE,rule='P(y>TRAIN burst threshold) >=0.10; fixed Q90 tail-mass boundary, never tuned'),
  C1='expanding past OOS high-risk-hour residuals of C0; only full-day labels matured before issue; omit PURGE; minimum50 hours and10 days; max(0, finite Q90 residual); outside gate exactly C0',
  C2=dict(rule='burst-only log1p LightGBM quantiles; invert tail mass at u=1-0.10/p, interpolate from threshold at u=0; max(C0,tail_quantile) only inside gate',grid=GRID,min_tail_hours=50,min_tail_days=10,sparse='C0 fallback'),
  calibration_no_future='earlier mature evaluation labels allowed by frozen prequential rule, never tuning',
  selection='C1/C2 eligible only if positive coverage>=.85, burst>=.60 and Q90 pinball<=C0 separately in DEVELOPMENT and CALIBRATION. Prefer both overall88..92 and ratio<2, then mean burst coverage, then mean pinball. If no eligible challenger retain C0; no evaluation reselection.',
  preferred=dict(overall=[.88,.92],requirement_ratio_lt=2,burst_target=.70),
  bootstrap=dict(draws=2000,block_observed_days=[1,7],seed=20260927,paired=True),
  TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,PRODUCTION_PROMOTED=False,optimizer_executions=0),True)
 L.to_csv(ROOT/'DAY_MEMBERSHIP.csv',index=False)
 dump('CODE_FREEZE.json',dict(time=now(),code={p.name:sha(p) for p in ROOT.glob('*.py')},protocol_sha256=sha(ROOT/'PROTOCOL.json')),True)

def train_model(x,y,w,path,binary=False,tau=.9):
 if binary and len(np.unique(y))==1:
  v=float(y[0]);path.write_bytes(gzip.compress(json.dumps({'constant':v}).encode(),mtime=0));return v
 model=(lgb.LGBMClassifier(objective='binary',**PARAMS) if binary else lgb.LGBMRegressor(objective='quantile',alpha=tau,**PARAMS))
 b=model.fit(x,y,sample_weight=w).booster_;path.write_bytes(gzip.compress(b.model_to_string().encode(),mtime=0));return b
def predict(m,x):return np.full(len(x),m) if isinstance(m,float) else m.predict(x,num_threads=1)
def tail_bound(p,v,b):
 u=1-.1/np.maximum(p,np.finfo(float).tiny)
 return np.array([np.interp(t,np.r_[0,GRID],np.r_[b,np.maximum.accumulate(np.maximum(row,b))]) for t,row in zip(u,v)])
def fit_day(i):
 code_guard();path=ROOT/'raw'/f'{DAYS[i]}.npz'
 if path.exists():return
 tr=membership(i);require((AV.iloc[tr]<ISS.iloc[i]).all(),'IMMATURE_TRAIN')
 x=Z['X'][tr].reshape(-1,71);y=Y[tr].ravel();w=np.repeat(weights(tr,i),24);xp=Z['X'][i]
 burst=y>threshold();folder=ROOT/'fits'/DAYS[i];folder.mkdir(parents=True,exist_ok=True)
 g=train_model(x,burst.astype(int),w,folder/'gate.txt.gz',binary=True);p=predict(g,xp)
 supported=burst.sum()>=50 and np.unique(np.repeat(tr,24)[burst]).size>=10
 v=np.full((24,len(GRID)),threshold())
 if supported:
  for k,tau in enumerate(GRID):
   m=train_model(x[burst],np.log1p(y[burst]),w[burst],folder/f'tail_{tau}.txt.gz',tau=float(tau))
   v[:,k]=np.maximum(0,np.expm1(predict(m,xp)))
 path.parent.mkdir(exist_ok=True);np.savez_compressed(path,risk=p,tail=tail_bound(p,v,threshold()),supported=np.array(supported))
 dump(folder.relative_to(ROOT)/'MEMBERSHIP.json',dict(issue=ISS.iloc[i],day_index=i,train_day_indices=tr,weights=weights(tr,i),latest_maturity=AV.iloc[tr].max(),tail_flat_indices=np.flatnonzero(burst),tail_supported=supported,
  model_sha256={p.name:sha(p) for p in folder.glob('*.gz')},prediction_sha256=sha(path),temporal_policy_changed=False))
 print('FIT',DAYS[i],len(tr),int(burst.sum()),flush=True)

def forecast(through,workers=2):
 code_guard();source_guard()
 from concurrent.futures import ProcessPoolExecutor
 ids=OOS[DAYS[OOS]<=through]
 with ProcessPoolExecutor(max_workers=workers) as pool:list(pool.map(fit_day,map(int,ids)))

def residual_delta(scores):
 rank=int(np.ceil(.9*(len(scores)+1)));require(rank<=len(scores),'CAL_SUPPORT')
 return max(0.,float(np.sort(scores)[rank-1]))
def compose(through):
 ids=OOS[DAYS[OOS]<=through];qs={k:C0.copy() for k in ['C0','C1','C2']};risk=np.full(Y.shape,np.nan);proof=[]
 for i in ids:
  a=np.load(ROOT/'raw'/f'{DAYS[i]}.npz');risk[i]=a['risk'];gate=risk[i]>=GATE
  past=ids[ids<i]
  past=past[(AV.iloc[past]<ISS.iloc[i]).to_numpy()&L.split.iloc[past].ne('PURGE').to_numpy()]
  high=risk[past]>=GATE;day,hour=np.where(high);caldays=past[day]
  support=len(day)>=50 and len(np.unique(caldays))>=10
  delta=residual_delta((Y[past]-C0[past,:,1])[high]) if support else 0.
  qs['C1'][i,gate,1]+=delta
  if bool(a['supported']):qs['C2'][i,gate,1]=np.maximum(C0[i,gate,1],a['tail'][gate])
  proof.append(dict(target_day=DAYS[i],issue=ISS.iloc[i],pool_day_indices=caldays,pool_hours=hour,N_days=len(np.unique(caldays)),delta=delta,supported=support))
 return qs,risk,proof

def stats(y,q,b=None):
 b=threshold() if b is None else b;y=np.asarray(y);q=np.asarray(q);pos=y>0;burst=y>b;e=y-q
 return dict(N_hours=y.size,coverage=float(np.mean(y<=q)),positive_coverage=float(np.mean(y[pos]<=q[pos])) if pos.any() else np.nan,
  burst_coverage=float(np.mean(y[burst]<=q[burst])) if burst.any() else np.nan,Q90_pinball=float(np.mean(np.maximum(.9*e,-.1*e))),
  requirement_ratio=float(q.sum()/y.sum()) if y.sum() else np.nan,actual_GPUh=float(y.sum()),predicted_GPUh=float(q.sum()),N_burst=int(burst.sum()))
def role_ids(role):return np.flatnonzero(L.split.eq(role)&L.eligible)
def eligible(m,b):return m['positive_coverage']>=.85 and m['burst_coverage']>=.60 and m['Q90_pinball']<=b['Q90_pinball']
def select():
 require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'ALREADY_SELECTED');code_guard()
 qs,risk,proof=compose('2024-11-30');rows=[]
 for model,q in qs.items():
  for role in ROLES[:2]:
   ix=role_ids(role);rows.append(dict(model=model,role=role,**stats(Y[ix],q[ix,:,1])))
 f=pd.DataFrame(rows);f.to_csv(ROOT/'SELECTION_METRICS.csv',index=False);valid=[]
 for model in ['C1','C2']:
  m=f[f.model.eq(model)];base=f[f.model.eq('C0')]
  if all(eligible(m[m.role.eq(r)].iloc[0],base[base.role.eq(r)].iloc[0]) for r in ROLES[:2]):
   preferred=bool(m.coverage.between(.88,.92).all() and (m.requirement_ratio<2).all())
   valid.append((not preferred,-m.burst_coverage.mean(),m.Q90_pinball.mean(),model))
 chosen=sorted(valid)[0][-1] if valid else 'C0'
 dump('PRE_EVALUATION_CALIBRATION.json',proof)
 dump('FINAL_SELECTION_FREEZE.json',dict(time=now(),model=chosen,eligible_challengers=[v[-1] for v in valid],reason='rule applied only to DEV/CAL; C0 retained if none passes',
  current_followup_evaluation_accessed=False,prior_May_exposure=True,code={p:sha(ROOT/p) for p in read('CODE_FREEZE.json')['code']},protocol_sha256=sha(ROOT/'PROTOCOL.json')),True)
 print('FROZEN',chosen,flush=True)

def daily_vector(y,q):
 pos=y>0;burst=y>threshold();e=y-q
 return np.column_stack([np.full(len(y),24),pos.sum(1),burst.sum(1),y.sum(1),q.sum(1),(y<=q).sum(1),((y<=q)&pos).sum(1),((y<=q)&burst).sum(1),np.maximum(.9*e,-.1*e).sum(1)])
def summary(v):
 s=v.sum(axis=-2);return np.stack([s[...,8]/s[...,0],s[...,5]/s[...,0],s[...,6]/s[...,1],s[...,7]/s[...,2],s[...,4]/s[...,3]],axis=-1)
def uncertainty(y,a,b,block):
 va,vb=daily_vector(y,a),daily_vector(y,b);n=len(y);rng=np.random.default_rng(20260927)
 starts=rng.integers(n,size=(2000,int(np.ceil(n/block))));ix=((starts[:,:,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
 ds=summary(va[ix])-summary(vb[ix]);point=summary(va)-summary(vb)
 return [dict(metric=m,delta=point[k],CI95_low=np.quantile(ds[:,k],.025),CI95_high=np.quantile(ds[:,k],.975),block_observed_days=block,N_days=n,draws=2000) for k,m in enumerate(['Q90_pinball','coverage','positive_coverage','burst_coverage','requirement_ratio'])]

def evaluate():
 require(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'EVALUATED');code_guard('FINAL_SELECTION_FREEZE.json');source_guard()
 qs,risk,proof=compose('2025-05-31');dump('CALIBRATION_MEMBERSHIP.json',proof)
 rows=[];strata=[];ci=[];pred=[];gate_rows=[]
 for role in ROLES:
  ix=role_ids(role);y=Y[ix];p=risk[ix]
  gate_rows.append(dict(role=role,N_hours=y.size,high_risk_hours=int((p>=GATE).sum()),burst_hours=int((y>threshold()).sum()),true_burst_recall=float(np.mean((p>=GATE)[y>threshold()]))))
  for model,q in qs.items():
   v=q[ix,:,1];rows.append(dict(role=role,model=model,**stats(y,v)))
   for name,mask in [('zero',y==0),('positive',y>0),('burst',y>threshold()),('high_risk',p>=GATE),('low_risk',p<GATE)]:
    if mask.any():strata.append(dict(role=role,model=model,stratum=name,**stats(y[mask],v[mask])))
   pred.append(pd.DataFrame(dict(day=np.repeat(DAYS[ix],24),hour=np.tile(np.arange(24),len(ix)),role=role,model=model,actual=y.ravel(),Q50=q[ix,:,0].ravel(),Q90=v.ravel(),risk=p.ravel())))
   if role in ROLES[2:] and model!='C0':
    for block in [1,7]:ci.extend(dict(role=role,model=model,reference='C0',**r) for r in uncertainty(y,v,C0[ix,:,1],block))
  require(np.array_equal(qs['C1'][ix][p<GATE],C0[ix][p<GATE]) and np.array_equal(qs['C2'][ix][p<GATE],C0[ix][p<GATE]),'OUTSIDE_GATE_CHANGE')
 for name,data in [('MODEL_METRICS',rows),('STRATIFIED_METRICS',strata),('PAIRED_UNCERTAINTY',ci),('GATE_DIAGNOSTICS',gate_rows)]:pd.DataFrame(data).to_csv(ROOT/(name+'.csv'),index=False)
 pd.concat(pred,ignore_index=True).to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
 dump('EVALUATION_COMPLETE.json',dict(time=now(),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),freeze_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),May='diagnostic historical; previously exposed'),True)

def verify():
 code_guard('FINAL_SELECTION_FREEZE.json');source_guard();proof=pd.read_parquet(BASE/'FEATURE_MATURITY_PROOF.parquet')
 require((pd.to_datetime(proof.feature_available_at,utc=True)<=pd.to_datetime(proof.issue_time,utc=True)).all(),'FEATURE_LEAK')
 require(threshold()==read('PROTOCOL.json')['burst_threshold']['value'],'THRESHOLD_DRIFT')
 n=0
 with tarfile.open(PARENT/'FIT_AUDIT_BUNDLE.tar.gz','r:gz') as bundle:
  for i in OOS:
   folder=ROOT/'fits'/DAYS[i];r=json.loads((folder/'MEMBERSHIP.json').read_text(encoding='utf-8'));tr=membership(i)
   require(np.array_equal(r['train_day_indices'],tr),'MEMBERSHIP');require(r['weights']==str(weights(tr,i)),'WEIGHT_STRING_RECONSTRUCTION')
   old=json.load(bundle.extractfile(f'fits/LGBM_weighted_c1_s20260924/{DAYS[i]}/MEMBERSHIP.json'))
   require(old['train_days']==DAYS[tr].tolist() and old['weights']==str(weights(tr,i)),'TEMPORAL_POLICY_CHANGED')
   require(sha(ROOT/'raw'/f'{DAYS[i]}.npz')==r['prediction_sha256'],'PREDICTION_DRIFT')
   for p,h in r['model_sha256'].items():require(sha(folder/p)==h,'MODEL_DRIFT')
   n+=1
 for r in read('CALIBRATION_MEMBERSHIP.json'):
  ix=np.asarray(r['pool_day_indices'],int);require((AV.iloc[ix]<pd.Timestamp(r['issue'])).all(),'IMMATURE_RESIDUAL')
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet')
 for role in ROLES:
  for model in ['C0','C1','C2']:
   g=f[f.role.eq(role)&f.model.eq(model)];require(len(g)==24*len(role_ids(role)),'EXCLUSION');require(np.isfinite(g.Q90).all(),'NONFINITE')
 require((f.Q90>=f.Q50).all(),'QUANTILE_ORDER')
 dump('VALIDATION.json',dict(time=now(),PASS=True,exact_fit_memberships=n,strict_maturity=True,feature_availability_checks=len(proof),outside_gate_unchanged=True,parent_evidence_unchanged=True,TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,PRODUCTION_PROMOTED=False))

def report():
 f=pd.read_csv(ROOT/'MODEL_METRICS.csv');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');selected=read('FINAL_SELECTION_FREEZE.json')['model'];checks=[]
 for role in ROLES[2:]:
  base=f[f.model.eq('C0')&f.role.eq(role)].iloc[0]
  for model in ['C0','C1','C2']:
   m=f[f.model.eq(model)&f.role.eq(role)].iloc[0];checks.append(dict(role=role,model=model,overall_preferred=.88<=m.coverage<=.92,positive=m.positive_coverage>=.85,burst_minimum=m.burst_coverage>=.60,burst_target=m.burst_coverage>=.70,ratio_preferred=m.requirement_ratio<2,pinball_noninferior=m.Q90_pinball<=base.Q90_pinball))
 pd.DataFrame(checks).to_csv(ROOT/'GATES.csv',index=False)
 flags=dict(TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False)
 dump('VERDICT.json',dict(**flags,selected=selected,reason='exposed historical development only; ingestion provenance unverified; see all frozen gates',untouched_confirmation=False))
 lines=['# CC4-v2.2 최종 검토','',f'고정 선택: **{selected}**. expanding + 30일 recency weighting + daily refit + LightGBM을 유지했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다.','',
  'C0는 PR64의 raw refitted LightGBM과 동일하다. C1은 과거 high-risk residual의 유한표본 Q90 보정, C2는 burst 확률을 반영한 conditional tail quantile이다. TRAIN positive-hour Q95로 burst 크기 threshold를 고정했고, risk gate 0.10은 Q90의 tail mass 경계로 사전 지정했다. 전체 scaling/capping은 없다. high-risk 밖은 Q50/Q90 모두 C0와 동일하다.','',
  '| 구간 | 모델 | coverage | positive | burst | ratio | Q90 pinball |','|---|---|---:|---:|---:|---:|---:|']
 for _,r in f.iterrows():lines.append(f'| {r.role} | {r.model} | {r.coverage:.2%} | {r.positive_coverage:.2%} | {r.burst_coverage:.2%} | {r.requirement_ratio:.3f} | {r.Q90_pinball:.3f} |')
 lines+=['','## Paired 95% CI','','7개 관측 target-day circular block, 2,000회. 음수 pinball delta는 개선이다. burst delta는 양수가 개선이다. 1-day 결과도 CSV에 보존한다.','', '| 구간 | 모델 | 지표 | delta | 95% CI |','|---|---|---|---:|---|']
 for _,r in ci[ci.block_observed_days.eq(7)&ci.metric.isin(['Q90_pinball','burst_coverage'])].iterrows():lines.append(f'| {r.role} | {r.model} | {r.metric} | {r.delta:.4f} | [{r.CI95_low:.4f}, {r.CI95_high:.4f}] |')
 lines+=['','## 판정','']+[f'- {k} = **{str(v).upper()}**' for k,v in flags.items()]
 lines+=['','DEV/CAL에서 hard gate를 모두 만족하는 challenger가 없으면 C0를 유지한다. 평가 후 재선택하지 않는다. 모든 gate 원값은 GATES.csv, burst/risk strata와 gate recall은 별도 CSV에 있다. 과거 mature evaluation label의 prequential refit/residual 사용은 허용하지만 선택에는 사용하지 않는다.','',
  '훈련·residual exact membership과 PR64 temporal membership/weight 일치를 검증한다. 실제 ingestion 시각은 미인증이며 운영 인과성 인증이 아니다. 비교는 post-exposure model development이고 신규 untouched confirmation을 확보하지 않았다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 수정·실행 및 production promotion은 없다.','']
 (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['register','development','select','evaluation','verify','report']);args=a.parse_args()
 if args.stage=='register':register()
 elif args.stage=='development':forecast('2024-11-30')
 elif args.stage=='select':select()
 elif args.stage=='evaluation':
  code_guard('FINAL_SELECTION_FREEZE.json');forecast('2025-05-31');evaluate()
 elif args.stage=='verify':verify()
 else:report()
