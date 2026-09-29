from common11 import *
from fit11 import *
from metrics11 import *
from queue9 import replay
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
import shutil,numpy as np,pandas as pd,lightgbm as lgb,time
def main():
    selected=read(ROOT/'BASE_SELECTION_RESULT.json');win=selected['window'];target=selected['target'];basearm=selected['selected']['arm']
    rows=[];ts=[];qs=[];parts={};classrows=[];calrows=[];crparts=[];expertrows=[];gpus=[];fitrows=[]
    candidates=[('GATE0_L0','GATE0','L0')]+[(g+'_'+w,g,w) for g in ['GATE1','GATE2'] for w in ['L1','L2']]
    for i in range(1,6):
        tr=window(i,win);exact=tr[tr.event];val=data(i,'VALID');base=Quantiles.load(LOCAL/'BASE_MODELS'/f'fold{i}'/basearm);pre=base.pre
        dest=ROOT/'FOLD_MODELS'/f'fold{i}';base.save(dest/'total_base');cache=LOCAL/f'fold{i}'/'TAIL.npz'
        m=val.event.to_numpy();y=val.loc[m,'runtime_seconds'].to_numpy();gpu=val.loc[m,'num_gpus_req'].to_numpy();yt=exact.runtime_seconds.to_numpy();x=features(exact,pre)[pre['columns']];xv=features(val,pre)[pre['columns']]
        cfg=read(ROOT/'EXPERIMENT_PROTOCOL.json')['learner'];t=time.perf_counter();classifier=lgb.LGBMClassifier(**cfg,objective='binary')
        if (dest/'classifier.txt').exists():classifier=lgb.Booster(model_str=(dest/'classifier.txt').read_text(encoding='utf-8'))
        else:classifier.fit(x,(yt>14400).astype(int),categorical_feature=['qos','partition','account']);classifier=classifier.booster_;(dest/'classifier.txt').write_text(classifier.model_to_string(),encoding='utf-8')
        fitrows.append(dict(fold=i,component='classifier',seconds=time.perf_counter()-t,TRAIN_N=len(exact),threads=4));risk=classifier.predict(xv,num_threads=4)
        baseq=np.load(LOCAL/f'fold{i}'/(basearm+'.npz'))['quantiles'];expert={'L0':baseq[:,1]}
        for weight in ['L1','L2']:
            w=np.where(yt>43200,4, np.where(yt>14400,2,1)) if weight=='L2' else np.where(yt>14400,2,1)
            path=dest/(weight+'.txt')
            if path.exists():boost=lgb.Booster(model_str=path.read_text(encoding='utf-8'));seconds=0.
            else:boost,seconds=fit_tail(exact,pre,target,w);path.write_text(boost.model_to_string(),encoding='utf-8')
            fitrows.append(dict(fold=i,component=weight,seconds=seconds,TRAIN_N=len(exact),threads=4));expert[weight]=tail_predict(boost,val,pre,target)
        np.savez_compressed(cache,risk=risk,base=baseq,**expert)
        truth=y>14400;prob=risk[m];pred=prob>=.5;tp=int((truth&pred).sum());fp=int((~truth&pred).sum());fn=int((truth&~pred).sum());baseline=float(np.mean((truth-float((yt>14400).mean()))**2))
        classrows.append(dict(fold=i,N=len(y),long4_N=int(truth.sum()),long12_N=int((y>43200).sum()),ROC_AUC=roc_auc_score(truth,prob),PR_AUC=average_precision_score(truth,prob),prevalence=float(truth.mean()),Brier=brier_score_loss(truth,prob),TRAIN_constant_Brier=baseline,
          recall=tp/(tp+fn),precision=tp/(tp+fp) if tp+fp else 0.,gt12h_recall=float(pred[y>43200].mean()),threshold=.5,TRAIN_N=len(yt),TRAIN_long4_N=int((yt>14400).sum())))
        crparts.append(pd.DataFrame(dict(y=y,prob=prob,baseline_error=(truth-float((yt>14400).mean()))**2)))
        for b in range(10):
            mask=(prob>=b/10)&((prob<(b+1)/10) if b<9 else (prob<=1))
            if mask.any():calrows.append(dict(fold=i,bin_lower=b/10,bin_upper=(b+1)/10,N=int(mask.sum()),mean_probability=float(prob[mask].mean()),observed_long4_rate=float(truth[mask].mean())))
        for weight,predq in expert.items():
            qq,_=ordered(np.column_stack([baseq[:,0],predq]))
            expertrows.extend(dict(fold=i,weight=weight,**r) for r in tails(y,gpu,qq[m]))
        support=True
        for arm,gate,weight in candidates:
            q=baseq.copy()
            if gate=='GATE1':q[:,1]=np.where(risk>=.5,expert[weight],q[:,1])
            elif gate=='GATE2':q[:,1]=(1-risk)*q[:,1]+risk*expert[weight]
            q,rep=ordered(q);np.savez_compressed(LOCAL/f'fold{i}'/(arm+'.npz'),quantiles=q)
            rows.append(dict(fold=i,arm=arm,gate=gate,weight=weight,window=win,target=target,support_sufficient=True,TRAIN_N=len(exact),VALID_censored_N=int(val.censored.sum()),quantile_repair_N=rep,**stats(y,gpu,q[m])))
            ts.extend(dict(fold=i,arm=arm,**r) for r in tails(y,gpu,q[m]));qs.append(dict(fold=i,arm=arm,**replay(val,q[:,1],read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['queue_day'])))
            parts.setdefault(arm,[]).append(pd.DataFrame(dict(y=y,gpu=gpu,q50=q[m,0],q90=q[m,1])))
            for threshold in [16,64]:
                gm=gpu>=threshold;s=stats(y[gm],gpu[gm],q[m][gm]);s['status']='INSUFFICIENT_SUPPORT' if s['N']<100 else 'PASS' if s['Q90_coverage']>=.85 else 'FAIL';gpus.append(dict(fold=i,arm=arm,GPU_min=threshold,**s))
        print('TAIL_FOLD',i,classrows[-1],flush=True)
    fd=pd.DataFrame(rows);td=pd.DataFrame(ts);qd=pd.DataFrame(qs);summary,checks=aggregate(parts,fd,td,qd);chosen,n=select(checks)
    c=pd.concat(crparts,ignore_index=True);truth=c.y.to_numpy()>14400;prob=c.prob.to_numpy();pred=prob>=.5;cf=pd.DataFrame(classrows)
    auc=roc_auc_score(truth,prob);ap=average_precision_score(truth,prob);lift=ap/truth.mean();brier=brier_score_loss(truth,prob);skill=1-brier/c.baseline_error.mean();recall=float(pred[truth].mean())
    meaningful=auc>=.65 and lift>=1.5 and cf.ROC_AUC.min()>=.55;validated=bool(meaningful and skill>0 and recall>=.5)
    write('TAIL_CLASSIFIER_VERDICT.json',dict(time=now(),ROC_AUC=auc,PR_AUC=ap,prevalence=float(truth.mean()),PR_prevalence_lift=lift,Brier=brier,TRAIN_constant_Brier=float(c.baseline_error.mean()),Brier_skill=float(skill),recall=recall,precision=float(truth[pred].mean()) if pred.any() else 0.,gt12h_recall=float(pred[c.y.to_numpy()>43200].mean()),min_fold_AUC=float(cf.ROC_AUC.min()),meaningful=bool(meaningful),TAIL_CLASSIFIER_VALIDATED=validated,threshold=.5,threshold_source='fixed before training',April_read=False))
    for name,frame in [('TAIL_CLASSIFIER_METRICS.csv',cf),('TAIL_CLASSIFIER_CALIBRATION.csv',pd.DataFrame(calrows)),('TAIL_EXPERT_METRICS.csv',pd.DataFrame(expertrows)),('TAIL_WEIGHT_COMPARISON.csv',pd.DataFrame(expertrows)),('TOTAL_FOLD_METRICS.csv',fd),('TOTAL_LONG_TAIL_METRICS.csv',td),('TOTAL_GPU_WEIGHTED_METRICS.csv',pd.DataFrame(gpus)),('TOTAL_GATING_COMPARISON.csv',summary),('TOTAL_GATING_GATES.csv',checks),('TOTAL_SELECTED_STAGE_QUEUE.csv',qd),('TAIL_FIT_TIMINGS.csv',pd.DataFrame(fitrows))]:frame.to_csv(ROOT/name,index=False)
    # Stop unsafe tail use if discrimination is not meaningful; no fabricated success.
    if not meaningful:chosen=checks[checks.arm.eq('GATE0_L0')].iloc[0].to_dict();chosen['eligible']=False
    gate,weight=chosen['arm'].split('_')
    write('TOTAL_SELECTION_RESULT.json',dict(time=now(),selected=chosen,eligible_candidates=n if meaningful else 0,window=win,target=target,base_arm=basearm,gate=gate,weight=weight,threshold=.5,smooth_alpha='p_long4',diagnostic_only=not chosen['eligible'],tail_classifier_meaningful=bool(meaningful),tail_classifier_validated=validated,April_read=False))
    for i in range(1,6):shutil.copyfile(LOCAL/f'fold{i}'/(chosen['arm']+'.npz'),LOCAL/f'fold{i}'/'SELECTED_TOTAL.npz')
    print('TOTAL_SELECTED',chosen,'CLASSIFIER',meaningful,validated,flush=True)
if __name__=='__main__':main()
