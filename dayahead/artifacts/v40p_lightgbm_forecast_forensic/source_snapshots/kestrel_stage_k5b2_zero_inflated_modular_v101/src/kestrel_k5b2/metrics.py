from __future__ import annotations
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, precision_recall_fscore_support

def safe_div(a,b): return float(a/b) if abs(float(b))>1e-12 else float('nan')
def regression(y,p,positive_peak_threshold=None,under_w=2.0,over_w=1.0):
    y=np.asarray(y,float); p=np.asarray(p,float); e=p-y; ae=np.abs(e); under=np.maximum(y-p,0); over=np.maximum(p-y,0)
    pos=y>0; peak=pos if positive_peak_threshold is None else y>=positive_peak_threshold
    return {'count':len(y),'mae':float(ae.mean()),'rmse':float(np.sqrt(np.mean(e*e))),'nmae':safe_div(ae.sum(),np.abs(y).sum()),
            'wape':safe_div(ae.sum(),np.abs(y).sum()),'bias_mean':float(e.mean()),'underprediction_mean':float(under.mean()),
            'overprediction_mean':float(over.mean()),'underprediction_total':float(under.sum()),'overprediction_total':float(over.sum()),
            'asymmetric_loss':float((under_w*under+over_w*over).mean()),'positive_count':int(pos.sum()),
            'positive_mae':float(ae[pos].mean()) if pos.any() else float('nan'),'positive_underprediction_mean':float(under[pos].mean()) if pos.any() else float('nan'),
            'positive_peak_threshold':positive_peak_threshold,'positive_peak_count':int(peak.sum()),'positive_peak_mae':float(ae[peak].mean()) if peak.any() else float('nan'),
            'top1pct_mae':float(ae[y>=np.quantile(y,0.99)].mean()) if len(y) else float('nan')}
def event_metrics(y,p,threshold):
    z=np.asarray(y,float)>0; prob=np.clip(np.asarray(p,float),0,1); pred=prob>=threshold
    try: pr=float(average_precision_score(z,prob))
    except: pr=float('nan')
    try: roc=float(roc_auc_score(z,prob))
    except: roc=float('nan')
    try: brier=float(brier_score_loss(z,prob))
    except: brier=float('nan')
    precision,recall,f1,_=precision_recall_fscore_support(z,pred,average='binary',zero_division=0)
    beta=2.0; f2=(1+beta**2)*precision*recall/(beta**2*precision+recall) if (precision+recall)>0 else 0.0
    return {'event_rate':float(z.mean()),'threshold':float(threshold),'pr_auc':pr,'roc_auc':roc,'brier':brier,'precision':float(precision),'recall':float(recall),'f1':float(f1),'f2':float(f2)}
def choose_threshold(y,p,grid):
    best=(0.5,-1.0)
    for t in grid:
        m=event_metrics(y,p,float(t))
        if m['f2']>best[1]: best=(float(t),m['f2'])
    return best[0]
def choose_scale(y,p,grid,under_w,over_w):
    best=(1.0,float('inf'))
    for s in grid:
        m=regression(y,np.maximum(np.asarray(p)*float(s),0),under_w=under_w,over_w=over_w)
        if m['asymmetric_loss']<best[1]: best=(float(s),m['asymmetric_loss'])
    return best[0]
