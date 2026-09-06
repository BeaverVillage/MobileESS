from .common import *
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss

def pinball(y,q,t=.9):return np.maximum(t*(y-q),(t-1)*(y-q))
def positive_primary(y,q):
    pos=y>0
    return float(pinball(y[pos],q[pos]).sum()/y[pos].sum()) if pos.any() else None
def point(y,q):
    return {'N':len(y),'MAE':np.abs(y-q).mean() if len(y) else None,'RMSE':np.sqrt(np.mean((y-q)**2)) if len(y) else None,
      'WAPE':np.abs(y-q).sum()/y.sum() if y.sum()>0 else None,'bias':(q-y).mean() if len(y) else None}
def aggregate(y,q50,safe,u):
    pos=y>0;burst=y>u;miss=np.maximum(y-safe,0);over=np.maximum(safe-y,0)
    return {'N':len(y),'primary':positive_primary(y,safe),'Q90_style_pinball_mean':pinball(y,safe).mean(),
      'point_q50':point(y,q50),'point_positive_q50':point(y[pos],q50[pos]),'safe_point':point(y,safe),'positive_safe_point':point(y[pos],safe[pos]),
      'coverage':{k:{'N':int(mask.sum()),'value':float((y[mask]<=safe[mask]).mean()) if mask.any() else None,'error_from_90':float(abs((y[mask]<=safe[mask]).mean()-.9)) if mask.any() else None} for k,mask in [('overall',np.ones(len(y),bool)),('positive',pos),('burst',burst)]},
      'overprediction_GPUh':over.sum(),'underprediction_GPUh':miss.sum(),'missed_burst_GPUh':miss[burst].sum(),
      'captured_burst_GPUh':np.minimum(y[burst],safe[burst]).sum(),'captured_burst_fraction':np.minimum(y[burst],safe[burst]).sum()/y[burst].sum() if burst.any() else None,
      'mean_burst_shortfall_GPUh':miss[burst].mean() if burst.any() else None,'negative_outputs':int((safe<0).sum())}
def body_metrics(y,q,u,days):
    mask=y<=u;pos=mask&(y>0);v=aggregate(y[mask],q[mask,0],q[mask,1],u)
    coverage=v['coverage']['overall']['value'];pc=v['coverage']['positive']['value'];monthly=[]
    for month in sorted(set(d[:7] for d in days)):
        ix=mask&np.array([d[:7]==month for d in days]);n=int(ix.sum());c=float((y[ix]<=q[ix,1]).mean()) if n else None
        monthly.append({'month':month,'N':n,'coverage':c,'gate':'INSUFFICIENT_SUPPORT' if n<100 else ('PASS' if c>=.88 else 'FAIL'),'metrics':aggregate(y[ix],q[ix,0],q[ix,1],u) if n else None})
    passed=mask.sum()>=100 and pos.sum()>=100 and .9<=coverage<=.95 and .9<=pc<=.95 and all(r['gate']!='FAIL' for r in monthly)
    return {'metrics':v,'temporal':monthly,'all_pass':bool(passed),'OVERCONSERVATIVE_BODY_WARNING':bool(coverage>.975 or pc>.975),'oracle_BODY_only':True}
def detector(y,p,eta,u):
    truth=y>u;flag=p>=eta;n=int(truth.sum());tp=int((flag&truth).sum());fn=n-tp;tn=int((~flag&~truth).sum());fp=int((flag&~truth).sum())
    ece=0.;bins=[]
    for k in range(10):
        ix=(p>=k/10)&((p<(k+1)/10) if k<9 else (p<=1))
        if ix.any():
            pred=p[ix].mean();actual=truth[ix].mean();ece+=ix.mean()*abs(pred-actual);bins.append({'low':k/10,'high':(k+1)/10,'N':int(ix.sum()),'predicted':pred,'observed':actual})
    captured=y[truth&flag].sum();mass=y[truth].sum();recall=tp/n if n else None;wr=captured/mass if mass else None
    return {'N':len(y),'burst_N':n,'eta':float(eta),'ROC_AUC':roc_auc_score(truth,p) if 0<n<len(y) else None,'PR_AUC':average_precision_score(truth,p) if n else None,
      'Brier':brier_score_loss(truth,p),'ECE':float(ece),'ECE_bins':bins,'TP':tp,'FN':fn,'TN':tn,'FP':fp,
      'recall':recall,'precision':tp/(tp+fp) if tp+fp else 0.,'specificity':tn/(tn+fp) if tn+fp else None,'FNR':fn/n if n else None,'FPR':fp/(tn+fp) if tn+fp else None,
      'GPUh_weighted_recall':wr,'captured_burst_GPUh':captured,'captured_burst_GPUh_fraction':wr,'missed_burst_GPUh':mass-captured,
      'mean_missed_burst_GPUh':y[truth&~flag].mean() if fn else 0.,'flagged_fraction':flag.mean(),
      'gate_PASS':bool(n>=30 and recall>=.9 and wr>=.9 and wr>=.8 and ece<=.05)}
def choose_eta(y,p,u,recall_target=.9):
    truth=y>u;thresholds=np.unique(p)[::-1];order=np.argsort(-p,kind='stable');sp=p[order];t=truth[order];w=y[order]*t
    ends=np.searchsorted(-sp,-thresholds,side='right')-1
    recall=np.cumsum(t)[ends]/truth.sum();weighted=np.cumsum(w)[ends]/y[truth].sum()
    okay=(recall>=recall_target)&(weighted>=recall_target)
    assert okay.any(),'No threshold support'
    ix=np.flatnonzero(okay)[0];eta=float(thresholds[ix])
    return {'eta':eta,'target_recall':recall_target,'CAL_metrics':detector(y,p,eta,u),'candidate_threshold_count':len(thresholds),'rule':'Largest observed CAL probability with recall and GPUh-weighted recall at least target; p>=eta inclusive','source':'CALIBRATION only'}
def log_score(y,q):
    pos=y>0;s=np.sort(np.log1p(y[pos])-np.log1p(q[pos]));assert len(s)>0
    return float(s[min(len(s),int(np.ceil((len(s)+1)*.9)))-1])
def calibrate_body(q,score,u):return np.clip(np.expm1(np.log1p(q)+score),0,u)
def hybrid(q,p,eta,upper):return np.where(p>=eta,upper,q[:,1])
def safety(y,q50,safe,u,days):
    m=aggregate(y,q50,safe,u);cov={};monthly=[]
    for key,hi in [('overall',.95),('positive',.95),('burst',.975)]:
        row=m['coverage'][key];enough=row['N']>=(30 if key=='burst' else 100)
        cov[key]={'N':row['N'],'value':row['value'],'gate':'INSUFFICIENT_SUPPORT' if not enough else ('PASS' if .9<=row['value']<=hi else 'FAIL')}
    for month in sorted(set(d[:7] for d in days)):
        ix=np.array([d[:7]==month for d in days]);v=aggregate(y[ix],q50[ix],safe[ix],u);b=v['coverage']['burst']
        monthly.append({'month':month,'metrics':v,'burst_gate':'INSUFFICIENT_SUPPORT' if b['N']<100 else ('PASS' if b['value']>=.9 else 'FAIL'),
          'catastrophic_safe_WAPE':bool(v['safe_point']['WAPE']>2)})
    passed=all(x['gate']=='PASS' for x in cov.values()) and all(x['burst_gate']!='FAIL' and not x['catastrophic_safe_WAPE'] for x in monthly) and m['primary']<.9 and m['negative_outputs']==0
    return {'coverage':cov,'temporal':monthly,'primary_better_than_ZERO':m['primary']<.9,'all_pass':bool(passed),'WAPE_gate_semantics':'Monthly selected-safe envelope WAPE <=2.0, not body Q50 WAPE'}
def cumulative_reserve(y,safe):
    y=y.reshape(-1,96);s=safe.reshape(-1,96);c=y.cumsum(1);p=s.cumsum(1)
    return {'WAPE':np.abs(c-p).sum()/c.sum(),'MAE_GPUh':np.abs(c-p).mean(),'daily_total_MAE_GPUh':np.abs(c[:,-1]-p[:,-1]).mean(),
      'daily_total_bias_GPUh':(p[:,-1]-c[:,-1]).mean(),'maximum_underreserve_GPUh':np.maximum(c-p,0).max(),
      'horizon_crossing':int((np.diff(p,axis=1)<0).sum()),'semantics':'Sum of selected-safe reserves; conservative envelope curve, NOT a true cumulative Q90'}
def block_bootstrap(y,base,p,seed=SEED):
    y=y.reshape(-1,96);base=base.reshape(-1,96);p=p.reshape(-1,96);pos=y>0
    d=np.where(pos,pinball(y,base)-pinball(y,p),0).sum(1);mass=y.sum(1);rng=np.random.default_rng(seed);n=len(y);reps=[]
    for _ in range(5000):
        ix=((rng.integers(n,size=int(np.ceil(n/7)))[:,None]+np.arange(7))%n).ravel()[:n];reps.append(d[ix].sum()/mass[ix].sum())
    ci=np.quantile(reps,[.025,.975]);return {'delta':d.sum()/mass.sum(),'CI95':ci,'samples':5000,'block_days':7,'seed':seed,'superiority':bool(ci[0]>0)}
