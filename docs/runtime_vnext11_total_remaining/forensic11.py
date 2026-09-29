from common11 import *
import pandas as pd,numpy as np
from scipy.stats import ks_2samp,wasserstein_distance
from scipy.spatial.distance import jensenshannon
NUM=['requested_seconds','num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib']
CATS=['qos','partition','account','array_status']
THRESH=[900,1800,3600,7200,14400,28800,43200,86400,172800]
def numeric(a,b):
    a=np.asarray(pd.to_numeric(a,errors='coerce').dropna(),float);b=np.asarray(pd.to_numeric(b,errors='coerce').dropna(),float);a=a[np.isfinite(a)];b=b[np.isfinite(b)]
    if not len(a) or not len(b):return dict(TRAIN_N=len(a),VALID_N=len(b))
    edges=np.unique(np.quantile(a,np.linspace(0,1,11)));edges=np.r_[-np.inf,edges[1:-1],np.inf]
    pa=np.histogram(a,edges)[0]/len(a);pb=np.histogram(b,edges)[0]/len(b);pa=np.maximum(pa,1e-6);pb=np.maximum(pb,1e-6);pa/=pa.sum();pb/=pb.sum()
    iq=np.quantile(a,.75)-np.quantile(a,.25);scale=max(iq,1.)
    return dict(TRAIN_N=len(a),VALID_N=len(b),PSI=float(np.sum((pa-pb)*np.log(pa/pb))),Wasserstein=float(wasserstein_distance(a,b)),KS=float(ks_2samp(a,b,method='asymp').statistic),
      standardized_median_shift=float((np.median(b)-np.median(a))/scale),standardized_IQR_shift=float(((np.quantile(b,.75)-np.quantile(b,.25))-iq)/scale),TRAIN_IQR=float(iq),scale_floor=1.)
def summary(f,field):
    x=pd.to_numeric(f[field],errors='coerce').dropna().to_numpy();x=x[np.isfinite(x)]
    return dict(N=len(x),mean=float(np.mean(x)),zero_rate=float((x==0).mean()),**{f'Q{int(q*100)}':float(np.quantile(x,q)) for q in [.1,.25,.5,.75,.9,.95,.99]}) if len(x) else dict(N=0)
def decorate(f,train):
    f=f.copy();f['array_status']=np.where(f.array_index.notna()&f.array_index.ge(0),'ARRAY','NOT_ARRAY_OR_UNKNOWN')
    f['walltime_bucket']=pd.cut(f.requested_seconds,[0,900,1800,3600,7200,14400,43200,86400,604800,np.inf],include_lowest=True).astype(str)
    f['GPU_range']=pd.cut(f.num_gpus_req,[0,1,2,4,8,16,64,np.inf],include_lowest=True).astype(str)
    count=train.account.astype('string').fillna('__MISSING__').value_counts();n=f.account.astype('string').fillna('__MISSING__').map(count).fillna(0)
    f['account_support_bucket']=np.select([n.eq(0),n.lt(100),n.lt(1000)],['UNSEEN','RARE_LT100','100_999'],default='GE1000')
    f['runtime_walltime_ratio']=f.runtime_seconds/f.requested_seconds.where(f.requested_seconds>0)
    return f
def exact_keys(f):
    return pd.util.hash_pandas_object(f[RAW].astype('string').fillna('__MISSING__'),index=False).to_numpy()
def main():
    assert not (ROOT/'TRAINING_STARTED.json').exists()
    distribution=[];features=[];labels=[];prevalence=[];category=[];relationships=[];conditional=[];classes=[];recencies=[]
    for i in range(1,6):
        tr=data(i,'TRAIN');va=data(i,'VALID');ca=data(i,'CAL')
        for role,f in [('TRAIN',tr),('CAL',ca),('VALID',va)]:
            assert f.job_id.is_unique
            exact=f[f.event];assert (exact.end_time<exact.observation_cutoff).all()
            assert np.max(abs((exact.end_time-exact.start_time).dt.total_seconds()-exact.runtime_seconds))<1e-8
            ff=decorate(f,tr);ee=ff[ff.event]
            for field in NUM+['runtime_seconds','runtime_walltime_ratio']:
                distribution.append(dict(fold=i,role=role,field=field,**summary(ee if field.startswith('runtime') else ff,field),submitted_N=len(f),censored_rate=float(f.censored.mean()),unresolved_rate=float((~f.event).mean()),GPU_ge16_N=int(f.num_gpus_req.ge(16).sum()),GPU_ge64_N=int(f.num_gpus_req.ge(64).sum())))
            for t in THRESH:prevalence.append(dict(fold=i,role=role,threshold_seconds=t,N=len(ee),long_N=int(ee.runtime_seconds.gt(t).sum()),rate=float(ee.runtime_seconds.gt(t).mean())))
            for field in ['walltime_bucket','qos','partition','account_support_bucket','GPU_range']:
                for value,g in ee.groupby(field,dropna=False,observed=True):
                    relationships.append(dict(fold=i,role=role,stratifier=field,stratum=str(value),N=len(g),mean=float(g.runtime_seconds.mean()),median=float(g.runtime_seconds.median()),Q90=float(g.runtime_seconds.quantile(.9)),gt4h=float(g.runtime_seconds.gt(14400).mean()),gt12h=float(g.runtime_seconds.gt(43200).mean()),median_runtime_walltime=float(g.runtime_walltime_ratio.median())))
        assert not set(tr.job_id)&set(va.job_id) and not set(ca.job_id)&set(va.job_id) and not set(ca.job_id)&set(tr.job_id)
        a=decorate(tr,tr);b=decorate(va,tr);c=decorate(ca,tr);ae=a[a.event];be=b[b.event]
        for field in NUM:
            features.append(dict(fold=i,field=field,type='continuous',**numeric(a[field],b[field]),TRAIN_missing=float(a[field].isna().mean()),VALID_missing=float(b[field].isna().mean())))
        for field in CATS:
            ac=a[field].astype('string').fillna('__MISSING__').value_counts();bc=b[field].astype('string').fillna('__MISSING__').value_counts();keys=ac.index.union(bc.index);aa=ac.reindex(keys,fill_value=0);bb=bc.reindex(keys,fill_value=0);pa=aa/aa.sum();pb=bb/bb.sum()
            unseen=float(bb[aa.eq(0)].sum()/bb.sum());rare=float(bb[aa.lt(100)&aa.gt(0)].sum()/bb.sum())
            features.append(dict(fold=i,field=field,type='categorical',JS_divergence=float(jensenshannon(pa,pb,base=2)**2),total_variation=float(abs(pa-pb).sum()/2),unseen_rate=unseen,rare_rate=rare))
            category.extend(dict(fold=i,field=field,category=str(k),TRAIN_N=int(aa[k]),VALID_N=int(bb[k]),TRAIN_share=float(pa[k]),VALID_share=float(pb[k]),unseen=aa[k]==0,rare=0<aa[k]<100) for k in keys)
        ls=numeric(ae.runtime_seconds,be.runtime_seconds);rel=numeric(ae.runtime_walltime_ratio,be.runtime_walltime_ratio)
        recent=ae[ae.submit_time.ge(pd.Timestamp(prep(i)['fit_cutoff'])-pd.Timedelta(days=30))];recent_ks=numeric(recent.runtime_seconds,be.runtime_seconds)['KS'];recencies.append(dict(fold=i,expanding_KS=ls['KS'],recent30_KS=recent_ks,relative_reduction=1-recent_ks/max(ls['KS'],1e-12)))
        labels.append(dict(fold=i,comparison='TRAIN_VALID',field='runtime_seconds',**ls))
        labels.append(dict(fold=i,comparison='TRAIN_VALID',field='runtime_walltime_ratio',**rel))
        labels.append(dict(fold=i,comparison='CAL_VALID',field='runtime_seconds',**numeric(c.loc[c.event,'runtime_seconds'],be.runtime_seconds)))
        # Match the entire permitted raw descriptor vector; no conditional claim from marginals alone.
        ta=ae.assign(cell=exact_keys(ae));vb=be.assign(cell=exact_keys(be));ga=ta.groupby('cell');gb=vb.groupby('cell');na=ga.size();nb=gb.size();keys=na[na>=50].index.intersection(nb[nb>=30].index)
        for key in keys:
            aa=ga.get_group(key).runtime_seconds;bb=gb.get_group(key).runtime_seconds
            conditional.append(dict(fold=i,cell=str(key),TRAIN_N=len(aa),VALID_N=len(bb),KS=float(ks_2samp(aa,bb,method='asymp').statistic),TRAIN_median=float(aa.median()),VALID_median=float(bb.median()),TRAIN_gt4h=float(aa.gt(14400).mean()),VALID_gt4h=float(bb.gt(14400).mean())))
        ff=[z for z in features if z['fold']==i];cs=[z for z in conditional if z['fold']==i];mass=sum(z['VALID_N'] for z in cs)/len(be);within=float(np.average([z['KS'] for z in cs],weights=[z['VALID_N'] for z in cs])) if cs else None
        cov=any(z.get('KS',0)>=.1 or z.get('total_variation',0)>=.1 for z in ff);lab=ls['KS']>=.1;support=any(z.get('unseen_rate',0)>=.1 for z in ff)
        censor=abs(float(a.censored.mean()-b.censored.mean()))>=.05
        cond=bool(mass>=.2 and within is not None and within>=.1)
        kinds=[x for x,v in [('COVARIATE_SHIFT',cov),('LABEL_SHIFT',lab),('CONDITIONAL_SHIFT',cond),('SUPPORT_LOSS',support),('CENSORING_SHIFT',censor)] if v]
        classes.append(dict(fold=i,primary='MIXED' if len(kinds)>1 else kinds[0] if kinds else 'INCONCLUSIVE',evidence=kinds,exact_x_common_VALID_mass=mass,within_exact_x_weighted_KS=within,conditional_identification='Within archived full raw x common support; observational evidence, not causal attribution',label_semantics_inconsistency=False))
        print('FORENSIC_FOLD',i,classes[-1],flush=True)
    outputs={'FOLD_DISTRIBUTION_SUMMARY.csv':distribution,'FOLD_FEATURE_SHIFT.csv':features,'FOLD_LABEL_SHIFT.csv':labels,'FOLD_LONG_TAIL_PREVALENCE.csv':prevalence,'FOLD_CATEGORY_SUPPORT.csv':category,'FOLD_RELATIONSHIP_SUMMARY.csv':relationships,'FOLD_EXACT_X_CONDITIONAL_SHIFT.csv':conditional,'FOLD_RECENCY_DIAGNOSTIC.csv':recencies}
    for name,rows in outputs.items():pd.DataFrame(rows).to_csv(ROOT/name,index=False)
    pp=pd.DataFrame(prevalence);p=pp[(pp.role.isin(['TRAIN','VALID']))&(pp.threshold_seconds==14400)].pivot(index='fold',columns='role',values='rate')
    flags=dict(time=now(),TEMPORAL_DRIFT_FORENSIC_COMPLETE=True,DOES_RECENCY_MATTER='TRUE' if sum(x['relative_reduction']>.2 for x in recencies)>=3 else 'INCONCLUSIVE',
        DOES_RECENCY_MATTER_SCOPE='Descriptive proximity only; generalization must be tested in unchanged predeclared windows',
        DOES_LONG_TAIL_PREVALENCE_SHIFT=bool((abs(p.VALID-p.TRAIN)>.05).any()),
        DOES_REQUEST_RUNTIME_RELATIONSHIP_SHIFT=any(z.get('KS',0)>.1 for z in labels if z['field']=='runtime_walltime_ratio'),
        DOES_CATEGORY_SUPPORT_SHIFT=any(z.get('unseen_rate',0)>.01 or z.get('total_variation',0)>.1 for z in features if z['type']=='categorical'),
        fold_classifications=classes,STOP_UNRESOLVED_DATA_INCONSISTENCY=False,STOP_LABEL_SEMANTICS_DRIFT=False,stageB_allowed=True,April_read=False,May_read=False)
    write('STAGE_A_VERDICT.json',flags)
    def md(frame):return frame.to_csv(index=False)
    text='# 시간적 drift forensic\n\n새 모델 학습 전에 완료했다. 미래 VALID outcome은 진단 요약에만 사용하며 후보/feature/window를 변경하지 않는다. Runtime은 모든 역할에서 end-start와 일치했고 label semantics drift 또는 해결되지 않은 데이터 불일치는 발견하지 못했다. 미완결은 exact 분포에서 제외되어 censor/maturity selection 편향이 남는다.\n\n'
    text+='## Fold별 판정\n\n'+'\n'.join(f"- Fold {z['fold']}: {z['primary']}; {', '.join(z['evidence'])}; exact-x common VALID mass={z['exact_x_common_VALID_mass']:.3%}, within-cell KS={z['within_exact_x_weighted_KS']}." for z in classes)
    text+='\n\n조건부 변화는 runtime marginal만으로 추론하지 않았다. 9개 raw descriptor exact cell의 충분한 공통 지원에서 비교했으며 미측정 요인 및 archive proxy 한계 때문에 원인의 인과적 식별은 아니다.\n\n## TRAIN→VALID runtime CDF와 최근30일\n\n'+md(pd.DataFrame(recencies))
    text+='\n\n## Stage B 이전 플래그\n\n'+json.dumps(flags,ensure_ascii=False,indent=2)+'\n\n원본 상세: FOLD_DISTRIBUTION_SUMMARY.csv, FOLD_FEATURE_SHIFT.csv, FOLD_LABEL_SHIFT.csv, FOLD_LONG_TAIL_PREVALENCE.csv, FOLD_CATEGORY_SUPPORT.csv, FOLD_RELATIONSHIP_SUMMARY.csv, FOLD_EXACT_X_CONDITIONAL_SHIFT.csv. PSI는 TRAIN decile과 작은 descriptive 확률 보정을 사용한다. JS는 base2 divergence, Wasserstein은 원래 단위, KS는 CDF 최대 거리다. support가 희소한 exact-x 결과를 전체 모집단으로 확대하지 않는다.\n'
    (ROOT/'TEMPORAL_DRIFT_FORENSIC.md').write_text(text,encoding='utf-8')
    original=pd.read_csv(V10/'FOLD_LEVEL_METRICS.csv');f4=original[(original.fold==4)&original.arm.isin(['T1','T3_LOGISTIC_STATIC','T3_LOGISTIC_ROLLING14','T0_V9'])]
    f1=original[(original.fold==1)&original.arm.isin(['T1','T3_LOGISTIC_STATIC','T3_LOGISTIC_ROLLING14','T0_V9'])]
    detail='# Fold4 원인 감사\n\nV10 fold4 raw T1 88.33%에서 STATIC 보정 후39.56%로 하락한 것은 grid만의 문제가 아니다. CAL의 확률-결과 관계를 고정 이전한 보정이 이후 VALID와 맞지 않은 현상이다. 이는 보정 실패의 관측 증거이며 단일한 원인을 인과적으로 증명하지 않는다.\n\n'
    detail+='## V10 보존된 fold4 예측\n\n'+f4[['arm','Q90_coverage','Q90_pinball','reservation_actual_GPUh']].to_csv(index=False)
    detail+='\n## Fold1과 차이\n\n'+f1[['arm','Q90_coverage','Q90_pinball']].to_csv(index=False)
    detail+='\nFold1은 raw부터 실패했고 STATIC이 일부 회복했으나, fold4는 raw가 상대적으로 나은데 STATIC이 악화했다. 동일한 하나의 원인으로 묶지 않는다.\n\n'
    detail+='## Fold4 TRAIN/CAL/VALID 근거\n\n'+pd.DataFrame(distribution).query("fold==4 and field in ['runtime_seconds','runtime_walltime_ratio','requested_seconds']").to_csv(index=False)
    detail+='\n'+json.dumps(classes[3],ensure_ascii=False,indent=2)+'\n\n표본 및 지원 차이의 상세는 공통 forensic CSV를 참고한다. 새로운 후보군은 EXERIMENT_PROTOCOL.json에 forensic 실행 전 등록한 대로 유지한다.\n'
    (ROOT/'FOLD4_ROOT_CAUSE_AUDIT.md').write_text(detail,encoding='utf-8')
    names=list(outputs)+['STAGE_A_VERDICT.json','TEMPORAL_DRIFT_FORENSIC.md','FOLD4_ROOT_CAUSE_AUDIT.md']
    write('TEMPORAL_DRIFT_FREEZE.json',dict(time=now(),files=[record(ROOT/n) for n in names],before_V11_training=True,April_read=False))
    print('STAGE_A_COMPLETE',flags,flush=True)
if __name__=='__main__':main()
