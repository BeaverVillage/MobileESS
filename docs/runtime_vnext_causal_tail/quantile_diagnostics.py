"""Additional fixed quantile diagnostics; never participates in selection."""
from common import *

def main():
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');rows=[]
 for (role,model,state),g in f[f.model.isin(['MOE_POOLED','MULTI_QUANTILE','MULTI_QUANTILE_HIERARCHICAL'])].groupby(['role','model','state']):
  y=g.actual_seconds.to_numpy();gpu=g.num_gpus_req.to_numpy()
  for tau in TAUS:
   q=g[f'Q{int(100*tau)}'].to_numpy();e=y-q
   rows.append(dict(role=role,model=model,state=state,quantile=tau,N=len(g),coverage=float(np.mean(y<=q)),
    GPU_coverage=float(np.average(y<=q,weights=gpu)),pinball_seconds=float(np.maximum(tau*e,(tau-1)*e).mean()),
    MAE_seconds=float(abs(e).mean()),RMSE_seconds=float(np.sqrt(np.mean(e**2))),
    predicted_GPUh=float(np.sum(q*gpu)/3600),overreserved_GPUh=float(np.sum(np.maximum(q-y,0)*gpu)/3600)))
 pd.DataFrame(rows).to_csv(ROOT/'QUANTILE_DIAGNOSTICS.csv',index=False)
 dump('QUANTILE_DIAGNOSTICS_RECEIPT.json',dict(time=now(),input_sha256=sha(ROOT/'PREDICTIONS.parquet'),selection_used=False,
   notes='Q95/Q99 are reported for overreservation diagnostics only; no UARP or upper quantile is substituted for Q90.'))

if __name__=='__main__':main()
