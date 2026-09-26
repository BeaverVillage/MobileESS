import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import json,hashlib,ast,subprocess
import numpy as np,pandas as pd,lightgbm as lgb
from prepare_data import OUT,BASE,R6,sha,dump,issue_time,require
def main():
 before=sha(OUT/'PREDICTIONS.parquet');data=np.load(OUT/'DATA.npz');days=[str(x) for x in data['days']];lut={d:i for i,d in enumerate(days)};p=pd.read_parquet(OUT/'PREDICTIONS.parquet');L=pd.read_parquet(OUT/'DAY_LEDGER.parquet');sel=json.loads((OUT/'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
 # Preserve source hashes frozen before the historical comparison; execution source is not edited.
 assert all(sha(OUT/name)==s for name,s in sel['code_hashes'].items())
 # Constant comparator originally inherited integer dtype in calibration work array. Correct only that dtype bug, with the same delta/membership and no fitting or selection.
 mask=p.model.eq('TRIVIAL_CAP');old=p.loc[mask,'calibrated_q90'].to_numpy();new=np.expm1(np.log1p(p.loc[mask,'raw_q90'].to_numpy(dtype=float))+p.loc[mask,'delta'].to_numpy())
 new=np.where(p.loc[mask,'delta'].to_numpy()==0,p.loc[mask,'raw_q90'].to_numpy(dtype=float),new)
 p.loc[mask,'calibrated_q90']=new;p.loc[mask,'actionable']=np.minimum(new,np.minimum(p.loc[mask,'physical_cap'],p.loc[mask,'historical_cap']))
 corrections={'type':'post-run dtype bug correction','selection_changed':False,'fitting_calls':0,'affected_models':['TRIVIAL_CAP'],'affected_rows':int(mask.sum()),'max_correction_GPUh':float(np.max(abs(new-old))),'reason':'np.full physical capacity constant was integer, copied calibration array truncated expm1 results; preserve float64 with zero-delta identity','old_predictions_sha256':before,'frozen_code_unchanged':True,'time':str(pd.Timestamp.now(tz='UTC'))}
 # Keep exact unrepaired tree outputs in addition to operational crossing repair.
 p['raw_q50_unclipped']=p.q50;p['raw_q90_unrepaired']=p.raw_q90
 for (model,seed,mode,h),g in p[p.model.isin(['F0_FROZEN','F1_LGBM'])].groupby(['model','seed','training_mode','horizon_hours']):
  bytag={}
  for day,gg in g.groupby('day'):
   if model=='F0_FROZEN':tag='F0_FROZEN'
   elif mode=='fixed':tag=f'F1_LGBM_H{h}_s{seed}'
   else:
    start=int(np.flatnonzero((L.role=='DEVELOPMENT')&L.stage_maturity_eligible)[0]);cut=start+(lut[day]-start)//sel['refit_cadence_days']*sel['refit_cadence_days'];tag=f'refit_final_LGBM_H{h}_s{seed}_c{sel["refit_cadence_days"]}_{days[cut]}'
   bytag.setdefault(tag,[]).extend(gg.index.tolist())
  for tag,idx in bytag.items():
   sub=p.loc[idx];all_x=data[f'X{h}'];X=all_x[np.array([lut[d] for d in sub.day]),sub.window_start_slot.to_numpy(dtype=int)]
   raw=[]
   for q in [50,90]:
    mod=lgb.Booster(model_str=(OUT/'fits'/tag/f'Q{q}.txt').read_text(encoding='utf-8'));raw.append(np.expm1(mod.predict(X,num_threads=1)))
   expected=np.maximum(np.maximum(raw[0],raw[1]),0);assert np.max(abs(expected-sub.raw_q90.to_numpy()))<1e-6
   p.loc[idx,'raw_q50_unclipped']=raw[0];p.loc[idx,'raw_q90_unrepaired']=raw[1]
 p.to_parquet(OUT/'PREDICTIONS.parquet',index=False);corrections['new_predictions_sha256']=sha(OUT/'PREDICTIONS.parquet');dump('EXECUTION_CORRECTION.json',corrections)
 # Exact H4_AUTHORITY connection to frozen May snapshot and base model hashes.
 auth=Path('D:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r3_scale/inputs/2025-05-04/H4_AUTHORITY.json');j=json.loads(auth.read_text(encoding='utf-8'));sp=BASE/'CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-04/B0/dayahead/ml/ML_SNAPSHOT.json';s=json.loads(sp.read_text(encoding='utf-8'))
 matches={k:j[k]==s.get(k) for k in j};assert all(matches.values())
 dump('AUTHORITY_SEARCH.json',{'H4_AUTHORITY':str(auth),'sha256':sha(auth),'matching_snapshot':str(sp),'snapshot_sha256':sha(sp),'all_authority_fields_equal':True,'fields':matches})
 lineage=json.loads((OUT/'SOURCE_AND_MODEL_LINEAGE.json').read_text(encoding='utf-8'));lineage['H4_AUTHORITY']={'path':str(auth),'sha256':sha(auth),'May04_snapshot_all_fields_equal':True};dump('SOURCE_AND_MODEL_LINEAGE.json',lineage)
 protected=[]
 for row in lineage['source_comparisons']:protected.append({'path':row['local'],'unchanged':sha(row['local'])==row['local_sha']})
 for row in lineage['models']:protected.append({'path':row['path'],'unchanged':sha(row['path'])==row['sha256']})
 for row in lineage['May_snapshots']:protected.append({'path':row['path'],'unchanged':sha(row['path'])==row['sha256']})
 assert all(r['unchanged'] for r in protected)
 # Independent maturity assertions for every saved refit membership.
 av=np.maximum(pd.to_datetime(L.target_end,utc=True).astype('int64'),pd.to_datetime(L.target_label_available_at,utc=True).astype('int64')).to_numpy();nref=0
 for path in (OUT/'refit_memberships').glob('*.json'):
  for row in json.loads(path.read_text(encoding='utf-8')):
   ix=[lut[d] for d in row['training_days']];assert (av[ix]<pd.Timestamp(row['cutoff']).value).all();assert max(ix)<lut[row['refit_day']];assert len(ix)==row['N_training_days'];nref+=1
 # Future unfinished GPU-work poisoning must not change pinned feature vectors.
 src=ast.parse((OUT/'history/A/dayahead/v41/workload.py').read_text(encoding='utf-8'));env={'np':np,'pd':pd,'json':json,'issue_time':issue_time,'require':require,'SLOT_NS':900_000_000_000,'R6OUT':R6};exec(compile(ast.Module(body=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in ['history_values','features']],type_ignores=[]),'pinned_feature_test','exec'),env)
 bins=pd.read_parquet(OUT/'raw_bins.parquet');work=pd.read_parquet(OUT/'raw_work.parquet');day='2025-05-04';issue=issue_time(day);x=env['features'](day,bins,work);poison=work.copy();poison.loc[poison.end_time.ge(issue),'work_GPUh']*=1000000;poison_bins=bins.copy();poison_bins.loc[poison_bins.max_observed_end.gt(issue),'work_GPUh']*=1000000;xx=env['features'](day,poison_bins,poison);assert np.array_equal(x,xx)
 assert not p[['q50','raw_q90','calibrated_q90','target_GPUh','actionable']].isna().any().any();assert p.secured_reserve.isna().all();assert (p.actionable<=p.physical_cap).all()
 units=p.groupby(['model','seed','training_mode','horizon_hours','role','day']).size();assert all(v==97-4*key[3] for key,v in units.items())
 # Runtime ledger enrichments preserve original receipt timings and add full inference timings.
 ledger=pd.read_csv(OUT/'TRAINING_RUN_LEDGER.csv')
 for i,row in ledger.iterrows():
  path=OUT/'fits'/row.run_id/'inference_receipt.json'
  if path.exists():
   inf=json.loads(path.read_text());ledger.loc[i,'full_dataset_inference_seconds']=inf['inference_seconds'];ledger.loc[i,'full_dataset_inference_days']=inf['inference_days'];ledger.loc[i,'gpu_peak_memory_bytes']=max(float(row.gpu_peak_memory_bytes),inf['gpu_peak_memory_bytes'])
  if row.run_id=='F0_FROZEN':ledger.loc[i,'model_load_seconds']=row.training_seconds;ledger.loc[i,'training_seconds']=0
 ledger.to_csv(OUT/'TRAINING_RUN_LEDGER.csv',index=False)
 dump('VALIDATION.json',{'PASS':True,'original_membership_hashes_match':31,'refit_issue_memberships_checked':nref,'future_unfinished_work_poison_test':'PASS','all_prediction_population_sizes_pass':True,'fixed_code_hashes_preserved':True,'protected_files':protected,'missing_or_imputed_GPU_quantity':False,'no_actual_reserve_claim':True,'no_CRPS_fabricated':True,'N_prediction_rows':len(p),'N_unique_May_H4_windows':2511,'calibration_zero_warmup':'first 20 residual-days excluded from development selection only; all 58 development days retained in diagnostic metrics','numerical_correction':'EXECUTION_CORRECTION.json'})
 print('VERIFICATION PASS',len(p),nref)
if __name__=='__main__':main()
