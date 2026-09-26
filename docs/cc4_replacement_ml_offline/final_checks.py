import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import json
from pathlib import Path
import numpy as np,pandas as pd
from prepare_data import OUT,sha,dump
L=pd.read_parquet(OUT/'DAY_LEDGER.parquet');av=np.maximum(pd.to_datetime(L.target_end,utc=True).astype('int64'),pd.to_datetime(L.target_label_available_at,utc=True).astype('int64')).to_numpy();lookup={d:i for i,d in enumerate(L.operating_day)};issued=pd.to_datetime(L.forecast_origin,utc=True).astype('int64').to_numpy();count=0
for path in OUT.glob('calibration_*.json'):
 for row in json.loads(path.read_text(encoding='utf-8')):
  i=lookup[row['day']];ii=[lookup[d] for d in row['source_days']]
  assert all(j<i and av[j]<issued[i] and L.role.iloc[j]!='TRAIN' for j in ii)
  assert row['N_days']==len(ii);count+=1
p=pd.read_parquet(OUT/'PREDICTIONS.parquet');metrics=pd.read_csv(OUT/'MODEL_METRICS.csv');err=np.max(np.abs(metrics.calibrated_coverage-(metrics.N_zero/metrics.N_windows+(metrics.N_positive/metrics.N_windows)*metrics.positive_coverage)));assert err<1e-12
fixed=p[(p.model=='F1_LGBM')&(p.horizon_hours==4)&(p.training_mode=='fixed')];frozen=p[p.model=='F0_FROZEN'];rr=fixed.merge(frozen,on=['day','window_start_slot'],suffixes=('','_frozen'));fiterr=float(abs(rr.raw_q90-rr.raw_q90_frozen).max());assert fiterr<1e-7
required=json.loads((OUT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['required_files'];assert all(sha(OUT/n)==r['sha256'] for n,r in required.items())
checks={'PASS':True,'calibration_issue_memberships_checked':count,'no_TRAIN_or_immature_residual':True,'zero_positive_coverage_identity_max_error':float(err),'new_LGBM_retraining_raw_Q90_max_error_vs_frozen':fiterr,'all_required_deliverables_hash_verified':True,'N_predictions':len(p),'seed_counts':p[p.model.isin(['F1_LGBM','F2_TFT','F3_DEEPAR'])].groupby(['model','training_mode','horizon_hours']).seed.nunique().to_dict()}
checks['seed_counts']={str(k):v for k,v in checks['seed_counts'].items()};dump('FINAL_CHECKS.json',checks);print(json.dumps({k:v for k,v in checks.items() if k!='seed_counts'}))
