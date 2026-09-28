"""Audit mathematical zero support separately from floored likelihood diagnostics."""
from common9 import *
from metrics9 import calibration
import numpy as np,pandas as pd
def main():
    fd=pd.read_csv(ROOT/'FOLD_LEVEL_METRICS.csv');edges=np.array(read(ROOT/'HAZARD_BIN_CONTRACT.json')['edges_seconds']);rows=[]
    for i in range(1,6):
        folder=LOCAL/f'fold{i}';val=pd.read_parquet(folder/'VALID.parquet');cal=pd.read_parquet(folder/'CAL.parquet')
        observed=val.event.to_numpy(bool);t=val.duration_lower.to_numpy();idx=np.searchsorted(edges[1:],t,side='left')
        right=np.where(idx<len(edges)-1,edges[np.minimum(idx+1,len(edges)-1)],np.inf)
        for r in fd[fd.fold.eq(i)&fd.arm.str.startswith(('D1','D2'))].itertuples():
            arm,mode=r.arm.split('__');saved=np.load(folder/(arm+'.npz'));d,_=calibration(cal,val,saved['cal_quantiles'],saved['val_quantiles'],mode)
            zero=observed & ((right<=d) if arm=='D1' else (right<d))
            hard=int(zero.sum());floors=int(r.log_probability_floor_N);unresolved=max(floors-hard,0)
            proper='INFINITE' if hard else 'NUMERICAL_FLOOR_UNRESOLVED' if unresolved else str(r.coarsened_survival_NLL)
            rows.append(dict(fold=i,arm=r.arm,N=int(r.NLL_N),zero_support_event_N=hard,numerical_floor_other_N=unresolved,
                proper_coarsened_survival_NLL=proper,floored_NLL_diagnostic=r.coarsened_survival_NLL))
    out=pd.DataFrame(rows);out.to_csv(ROOT/'PROPER_DISTRIBUTION_SCORE_AUDIT.csv',index=False);pooled=[]
    for arm,g in out.groupby('arm'):
        proper='INFINITE' if g.zero_support_event_N.sum() else 'NUMERICAL_FLOOR_UNRESOLVED' if g.numerical_floor_other_N.sum() else str(np.average(g.floored_NLL_diagnostic,weights=g.N))
        pooled.append(dict(arm=arm,proper_coarsened_survival_NLL=proper,zero_support_event_N=int(g.zero_support_event_N.sum()),numerical_floor_other_N=int(g.numerical_floor_other_N.sum())))
    pd.DataFrame(pooled).to_csv(ROOT/'POOLED_PROPER_DISTRIBUTION_SCORES.csv',index=False)
    write('PROPER_SCORE_INTERPRETATION.json',dict(time=now(),MODEL_COMPARISON_NLL='Numerically floored diagnostic; true proper score is in POOLED_PROPER_DISTRIBUTION_SCORES.csv',
        zero_support='Positive additive shift can assign exactly zero event-interval probability: true negative log likelihood is infinite, never epsilon-corrected into a scientific success',
        numeric_floor='Other numerically floored cells marked unresolved; no claim of exact proper log score',
        model_or_selection_changed=False,April_payload_read=False))
    print('PROPER_SCORE_AUDIT_COMPLETE')
if __name__=='__main__':main()
