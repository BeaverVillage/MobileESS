from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, logging, math
import lightgbm as lgb
import numpy as np, pandas as pd
from lightgbm import LGBMRegressor, LGBMClassifier
from .context import PipelineContext
from .data import DataBundle
from .baselines import Baselines
from .metrics import regression,event_metrics,choose_threshold,choose_scale
from .utils import write_json

@dataclass
class Results:
    validation_predictions_path: Path; frozen_predictions_path: Path; walkforward_predictions_path: Path
    validation_metrics: pd.DataFrame; frozen_metrics: pd.DataFrame; walkforward_metrics: pd.DataFrame
    event_metrics_df: pd.DataFrame; selection: pd.DataFrame; calibration: pd.DataFrame; model_metadata: list[dict[str,Any]]

FIXED_VARIANTS=['residual_l1','residual_l2','residual_huber']
FLEX_HURDLE=['hurdle_log_l1_expected','hurdle_log_l2_expected','hurdle_log_l1_gate','hurdle_log_l2_gate']
TWEEDIE_VARIANTS=['tweedie_1.1','tweedie_1.3','tweedie_1.5','tweedie_1.7']
BASELINES=['zero','historical_mean','persistence','seasonal_daily','seasonal_weekly']

def _base(ctx, objective, n_estimators, extra=None):
    p=dict(ctx.config['models']['base_parameters']); p.update({'objective':objective,'n_estimators':int(n_estimators),'random_state':int(ctx.config['resources']['random_seed']),'n_jobs':int(ctx.config['resources']['lightgbm_threads']),'verbosity':-1,'deterministic':True,'force_col_wise':True})
    if extra:p.update(extra)
    return p

def _fit_reg(ctx,X,y,Xv,yv,objective,extra=None):
    m=LGBMRegressor(**_base(ctx,objective,int(ctx.config['models']['max_estimators']),extra))
    m.fit(X,y,eval_set=[(Xv,yv)],callbacks=[lgb.early_stopping(int(ctx.config['models']['early_stopping_rounds']),verbose=False),lgb.log_evaluation(0)])
    return m,int(m.best_iteration_ or ctx.config['models']['max_estimators'])
def _fit_cls(ctx,X,y,Xv,yv):
    m=LGBMClassifier(**_base(ctx,'binary',int(ctx.config['models']['max_estimators']),{'metric':'binary_logloss'}))
    m.fit(X,y,eval_set=[(Xv,yv)],callbacks=[lgb.early_stopping(int(ctx.config['models']['early_stopping_rounds']),verbose=False),lgb.log_evaluation(0)])
    return m,int(m.best_iteration_ or ctx.config['models']['max_estimators'])
def _fit_final_reg(ctx,X,y,objective,n,extra=None):
    m=LGBMRegressor(**_base(ctx,objective,n,extra)); m.fit(X,y); return m
def _fit_final_cls(ctx,X,y,n):
    m=LGBMClassifier(**_base(ctx,'binary',n,{'metric':'binary_logloss'})); m.fit(X,y); return m

def _fold_masks(dev,fold):
    t=dev.timestamp_utc; return (t<=fold.train_feature_end_utc).to_numpy(),((t>=fold.validation_start_utc)&(t<=fold.validation_feature_end_utc)).to_numpy()
def _positive_peak(y,q):
    a=np.asarray(y,float); a=a[a>0]; return float(np.quantile(a,q)) if len(a) else 0.0
def _smear(ylog,predlog):
    s=float(np.mean(np.exp(np.clip(ylog-predlog,-4,4)))) if len(ylog) else 1.0
    return float(np.clip(s,0.5,3.0))
def _safe_mag(predlog,smear): return np.maximum(np.expm1(np.clip(predlog,-1,20))*smear,0)

def validation_oof(ctx,data,logger):
    X=data.development[data.features]; base=Baselines(data.combined,int(ctx.config['analysis']['interval_minutes']),int(ctx.config['analysis']['daily_seasonal_steps']),int(ctx.config['analysis']['weekly_seasonal_steps']))
    frames=[]; iter_map={}; raw_event=[]
    for _,row in data.targets.iterrows():
        target=row.target_column; source=row.source_metric; family='fixed' if row.target_type=='point_at_horizon' else 'flexible'; iter_map[target]={}
        logger.info('OOF target=%s family=%s',target,family)
        for _,fold in data.folds.iterrows():
            tr,va=_fold_masks(data.development,fold); ytr=data.development.loc[tr,target].to_numpy(float); yv=data.development.loc[va,target].to_numpy(float); ts=data.development.loc[va,'timestamp_utc']
            b=base.predict(ts,row,float(np.mean(ytr))); out=pd.DataFrame({'timestamp_utc':ts.to_numpy(),'fold_id':fold.fold_id,'target_column':target,'target_family':family,'actual':yv,**b})
            if data.k5b_validation is not None:
                bench=data.k5b_validation.loc[(data.k5b_validation.target_column==target)&(data.k5b_validation.timestamp_utc.isin(ts)),['timestamp_utc','lgbm_point']]
                out=out.merge(bench.rename(columns={'lgbm_point':'standard_l1'}),on='timestamp_utc',how='left')
            if family=='fixed':
                current=data.development.loc[va,source].to_numpy(float); resid_tr=ytr-data.development.loc[tr,source].to_numpy(float)
                out['current']=current
                for variant,obj in [('residual_l1','regression_l1'),('residual_l2','regression_l2'),('residual_huber','huber')]:
                    m,it=_fit_reg(ctx,X.loc[tr],resid_tr,X.loc[va],yv-current,obj)
                    out[variant]=np.maximum(current+m.predict(X.loc[va]),0); iter_map[target].setdefault(variant,[]).append(it)
            else:
                ztr=(ytr>0).astype(int); zv=(yv>0).astype(int)
                cls,itc=_fit_cls(ctx,X.loc[tr],ztr,X.loc[va],zv); prob=cls.predict_proba(X.loc[va])[:,1]
                out['event_probability']=prob; iter_map[target].setdefault('classifier',[]).append(itc)
                raw_event.append(pd.DataFrame({'target_column':target,'fold_id':fold.fold_id,'actual':yv,'probability':prob}))
                pos=ztr==1
                for key,obj in [('log_l1','regression_l1'),('log_l2','regression_l2')]:
                    if pos.sum()<10:
                        mag=np.full(len(yv),float(np.mean(ytr[ytr>0])) if np.any(ytr>0) else 0); it=1; smear=1
                    else:
                        yt=np.log1p(ytr[pos]); posv=zv==1
                        X_eval_mag=X.loc[va].loc[posv] if posv.any() else X.loc[tr].loc[pos]
                        y_eval_mag=np.log1p(yv[posv]) if posv.any() else yt
                        m,it=_fit_reg(ctx,X.loc[tr].loc[pos],yt,X_eval_mag,y_eval_mag,obj)
                        train_pred=m.predict(X.loc[tr].loc[pos]); smear=_smear(yt,train_pred); mag=_safe_mag(m.predict(X.loc[va]),smear)
                    out[f'magnitude_{key}']=mag; out[f'hurdle_{key}_expected_raw']=prob*mag; iter_map[target].setdefault(f'magnitude_{key}',[]).append(it)
                for power in [1.1,1.3,1.5,1.7]:
                    name=f'tweedie_{power:.1f}'; m,it=_fit_reg(ctx,X.loc[tr],ytr,X.loc[va],yv,'tweedie',{'tweedie_variance_power':power,'metric':'mae'})
                    out[name+'_raw']=np.maximum(m.predict(X.loc[va]),0); iter_map[target].setdefault(name,[]).append(it)
            frames.append(out)
    pred=pd.concat(frames,ignore_index=True)
    calibration=[]
    under=float(ctx.config['selection']['underprediction_weight']); over=float(ctx.config['selection']['overprediction_weight'])
    scales=ctx.config['selection']['scale_grid']; thresholds=ctx.config['selection']['event_threshold_grid']
    for _,row in data.targets.iterrows():
        t=row.target_column; g=pred[pred.target_column==t].copy(); y=g.actual.to_numpy(float)
        if row.target_type=='point_at_horizon': continue
        threshold=choose_threshold(y,g.event_probability.to_numpy(float),thresholds)
        for key in ['log_l1','log_l2']:
            raw=g[f'hurdle_{key}_expected_raw'].to_numpy(float); scale=choose_scale(y,raw,scales,under,over); gidx=g.index
            pred.loc[gidx,f'hurdle_{key}_expected']=raw*scale
            pred.loc[gidx,f'hurdle_{key}_gate']=g[f'magnitude_{key}'].to_numpy(float)*(g.event_probability.to_numpy(float)>=threshold)*scale
            calibration.append({'target_column':t,'method':f'hurdle_{key}','scale':scale,'event_threshold':threshold})
        for power in [1.1,1.3,1.5,1.7]:
            name=f'tweedie_{power:.1f}'; raw=g[name+'_raw'].to_numpy(float); scale=choose_scale(y,raw,scales,under,over); pred.loc[g.index,name]=raw*scale
            calibration.append({'target_column':t,'method':name,'scale':scale,'event_threshold':threshold})
    return pred,pd.DataFrame(calibration),iter_map

def evaluate_validation(ctx,data,pred,calibration):
    rows=[]; events=[]; selection=[]; q=float(ctx.config['analysis']['positive_peak_quantile']); uw=float(ctx.config['selection']['underprediction_weight']); ow=float(ctx.config['selection']['overprediction_weight'])
    minimp=float(ctx.config['selection']['fixed_minimum_mae_improvement_fraction'])
    for _,tr in data.targets.iterrows():
        t=tr.target_column; g=pred[pred.target_column==t]; y=g.actual.to_numpy(float); peak=_positive_peak(y,q)
        if tr.target_type=='point_at_horizon':
            methods=['persistence']+FIXED_VARIANTS+(['standard_l1'] if 'standard_l1' in g and g.standard_l1.notna().all() else [])
            for m in methods: rows.append({'split':'validation','target_column':t,'family':'fixed','method':m,**regression(y,g[m],peak,uw,ow)})
            md=pd.DataFrame([r for r in rows if r['target_column']==t]); pmae=float(md.loc[md.method=='persistence','mae'].iloc[0])
            selectable=md[md.method.isin(['persistence']+FIXED_VARIANTS)].sort_values('mae'); best=selectable.iloc[0]
            selected=str(best.method) if str(best.method)!='persistence' and float(best.mae)<=pmae*(1-minimp) else 'persistence'
            selection.append({'target_column':t,'family':'fixed','selected_method':selected,'selection_metric':'mae_with_persistence_fallback','persistence_mae':pmae,'selected_validation_mae':float(md.loc[md.method==selected,'mae'].iloc[0])})
        else:
            methods=BASELINES+FLEX_HURDLE+TWEEDIE_VARIANTS+(['standard_l1'] if 'standard_l1' in g and g.standard_l1.notna().all() else [])
            for m in methods: rows.append({'split':'validation','target_column':t,'family':'flexible','method':m,**regression(y,g[m],peak,uw,ow)})
            cal=calibration[calibration.target_column==t].iloc[0]; events.append({'split':'validation','target_column':t,**event_metrics(y,g.event_probability,float(cal.event_threshold))})
            md=pd.DataFrame([r for r in rows if r['target_column']==t])
            structured=md[md.method.isin(FLEX_HURDLE+TWEEDIE_VARIANTS)].sort_values(['asymmetric_loss','mae'])
            best=structured.iloc[0]; selected=str(best.method)
            zero_loss=float(md.loc[md.method=='zero','asymmetric_loss'].iloc[0])
            selection.append({'target_column':t,'family':'flexible','selected_method':selected,'selection_metric':f'asymmetric_loss_under_{uw:g}x_among_structured_models','selected_validation_asymmetric_loss':float(best.asymmetric_loss),'selected_validation_mae':float(best.mae),'zero_baseline_asymmetric_loss':zero_loss,'structured_beats_zero_operational_loss':bool(float(best.asymmetric_loss)<zero_loss)})
    return pd.DataFrame(rows),pd.DataFrame(events),pd.DataFrame(selection)

def _median_iter(iter_map,target,key,ctx):
    v=iter_map.get(target,{}).get(key,[ctx.config['models']['default_final_estimators']]); return int(np.clip(round(np.median(v)),int(ctx.config['models']['minimum_final_estimators']),int(ctx.config['models']['maximum_final_estimators'])))

def fit_predict_target(ctx,data,row,method,train,evalf,iter_map,calrow,save_dir=None):
    Xtr=train[data.features]; Xe=evalf[data.features]; y=train[row.target_column].to_numpy(float); source=row.source_metric; out={}
    if row.target_type=='point_at_horizon':
        current=evalf[source].to_numpy(float); out['persistence']=current
        if method=='persistence': out['selected_prediction']=current; return out,[]
        obj={'residual_l1':'regression_l1','residual_l2':'regression_l2','residual_huber':'huber'}[method]; n=_median_iter(iter_map,row.target_column,method,ctx)
        model=_fit_final_reg(ctx,Xtr,y-train[source].to_numpy(float),obj,n); out['selected_prediction']=np.maximum(current+model.predict(Xe),0)
        if save_dir: save_dir.mkdir(parents=True,exist_ok=True); model.booster_.save_model(str(save_dir/f'{row.target_column}__{method}.txt'))
        return out,[{'target_column':row.target_column,'method':method,'model_role':'fixed_residual','n_estimators':n}]
    # flexible
    b=Baselines(pd.concat([train,evalf],ignore_index=True).sort_values('timestamp_utc'),int(ctx.config['analysis']['interval_minutes']),int(ctx.config['analysis']['daily_seasonal_steps']),int(ctx.config['analysis']['weekly_seasonal_steps']))
    hist=float(y.mean()); out.update(b.predict(evalf.timestamp_utc,row,hist))
    if method in BASELINES: out['selected_prediction']=out[method]; return out,[]
    meta=[]
    if method.startswith('hurdle_'):
        key='log_l1' if 'log_l1' in method else 'log_l2'; obj='regression_l1' if key=='log_l1' else 'regression_l2'
        z=(y>0).astype(int); nc=_median_iter(iter_map,row.target_column,'classifier',ctx); cls=_fit_final_cls(ctx,Xtr,z,nc); prob=cls.predict_proba(Xe)[:,1]
        pos=z==1; nm=_median_iter(iter_map,row.target_column,f'magnitude_{key}',ctx)
        magm=_fit_final_reg(ctx,Xtr.loc[pos],np.log1p(y[pos]),obj,nm); smear=_smear(np.log1p(y[pos]),magm.predict(Xtr.loc[pos])); mag=_safe_mag(magm.predict(Xe),smear)
        scale=float(calrow.scale); threshold=float(calrow.event_threshold); out['event_probability']=prob; out['positive_magnitude']=mag
        if method.endswith('_expected'): pred=prob*mag*scale
        else: pred=(prob>=threshold)*mag*scale
        out['selected_prediction']=np.maximum(pred,0)
        if save_dir:
            save_dir.mkdir(parents=True,exist_ok=True); cls.booster_.save_model(str(save_dir/f'{row.target_column}__classifier.txt')); magm.booster_.save_model(str(save_dir/f'{row.target_column}__magnitude_{key}.txt'))
        meta=[{'target_column':row.target_column,'method':method,'model_role':'hurdle_classifier','n_estimators':nc},{'target_column':row.target_column,'method':method,'model_role':'hurdle_magnitude','n_estimators':nm,'smearing_factor':smear,'scale':scale,'event_threshold':threshold}]
    elif method.startswith('tweedie_'):
        power=float(method.split('_')[1]); n=_median_iter(iter_map,row.target_column,method,ctx); m=_fit_final_reg(ctx,Xtr,y,'tweedie',n,{'tweedie_variance_power':power,'metric':'mae'}); scale=float(calrow.scale); out['selected_prediction']=np.maximum(m.predict(Xe)*scale,0)
        # Event probability remains an independent diagnostic even when Tweedie is selected.
        z=(y>0).astype(int); nc=_median_iter(iter_map,row.target_column,'classifier',ctx); cls=_fit_final_cls(ctx,Xtr,z,nc); out['event_probability']=cls.predict_proba(Xe)[:,1]
        if save_dir:
            save_dir.mkdir(parents=True,exist_ok=True); m.booster_.save_model(str(save_dir/f'{row.target_column}__{method}.txt')); cls.booster_.save_model(str(save_dir/f'{row.target_column}__event_classifier.txt'))
        meta=[{'target_column':row.target_column,'method':method,'model_role':'tweedie','n_estimators':n,'variance_power':power,'scale':scale},{'target_column':row.target_column,'method':method,'model_role':'event_classifier_diagnostic','n_estimators':nc,'event_threshold':float(calrow.event_threshold)}]
    else: raise ValueError(method)
    return out,meta

def _calibration_for(calibration,target,method):
    c=calibration[calibration.target_column==target]
    if c.empty: return pd.Series({'scale':1.0,'event_threshold':0.5})
    key=method
    if method.startswith('hurdle_log_l1'): key='hurdle_log_l1'
    elif method.startswith('hurdle_log_l2'): key='hurdle_log_l2'
    m=c[c.method==key]
    return m.iloc[0] if len(m) else c.iloc[0]

def frozen_test(ctx,data,selection,calibration,iter_map,validation_pred,logger):
    frames=[]; meta=[]; model_dir=ctx.model_dir/'frozen_selected'
    for _,row in data.targets.iterrows():
        selected=selection.loc[selection.target_column==row.target_column,'selected_method'].iloc[0]; cal=calibration[calibration.target_column==row.target_column]
        calrow=cal.iloc[0] if len(cal) else pd.Series({'scale':1.0,'event_threshold':0.5})
        out,m=fit_predict_target(ctx,data,row,selected,data.development,data.test,iter_map,calrow,model_dir); meta+=m
        f=pd.DataFrame({'timestamp_utc':data.test.timestamp_utc,'target_column':row.target_column,'family':'fixed' if row.target_type=='point_at_horizon' else 'flexible','actual':data.test[row.target_column].to_numpy(float),'selected_method':selected,**out})
        if data.k5b_test is not None:
            bench=data.k5b_test[data.k5b_test.target_column==row.target_column][['timestamp_utc','lgbm_point']].rename(columns={'lgbm_point':'standard_l1'}); f=f.merge(bench,on='timestamp_utc',how='left')
        # marginal conformal interval from OOF selected residuals
        vg=validation_pred[validation_pred.target_column==row.target_column]; sel=selected if selected in vg else 'persistence'; resid=vg.actual.to_numpy(float)-vg[sel].to_numpy(float); lo,hi=np.quantile(resid,[0.1,0.9]); point=f.selected_prediction.to_numpy(float)
        f['prediction_p10']=np.maximum(point+lo,0); f['prediction_p50']=point; f['prediction_p90']=np.maximum(point+hi,0); f[['prediction_p10','prediction_p50','prediction_p90']]=np.sort(f[['prediction_p10','prediction_p50','prediction_p90']].to_numpy(float),axis=1)
        frames.append(f)
    return pd.concat(frames,ignore_index=True),meta

def walkforward(ctx,data,selection,calibration,iter_map,logger):
    frames=[]; allf=data.combined.copy(); months=pd.period_range('2025-01','2025-12',freq='M')
    interval=int(ctx.config['analysis']['interval_minutes'])
    for month in months:
        start=pd.Timestamp(month.start_time,tz='UTC'); end=pd.Timestamp(month.end_time,tz='UTC')
        evalf=data.test[(data.test.timestamp_utc>=start)&(data.test.timestamp_utc<=end)]
        if evalf.empty: continue
        logger.info('Walk-forward month %s rows=%d',month,len(evalf))
        for _,row in data.targets.iterrows():
            purge=pd.Timedelta(minutes=int(row.horizon_steps)*interval); train=allf[allf.timestamp_utc < start-purge].copy()
            selected=selection.loc[selection.target_column==row.target_column,'selected_method'].iloc[0]; calrow=_calibration_for(calibration,row.target_column,selected)
            out,_=fit_predict_target(ctx,data,row,selected,train,evalf,iter_map,calrow,None)
            payload={'timestamp_utc':evalf.timestamp_utc,'calendar_month':str(month),'target_column':row.target_column,'family':'fixed' if row.target_type=='point_at_horizon' else 'flexible','actual':evalf[row.target_column].to_numpy(float),'selected_method':selected,'selected_prediction':out['selected_prediction'],'training_rows':len(train),'training_end_utc':train.timestamp_utc.max()}
            if 'event_probability' in out: payload['event_probability']=out['event_probability']
            frames.append(pd.DataFrame(payload))
    return pd.concat(frames,ignore_index=True)

def evaluate_final(ctx,data,frozen,walk,selection,calibration):
    rows=[]; events=[]; wrows=[]; q=float(ctx.config['analysis']['positive_peak_quantile']); uw=float(ctx.config['selection']['underprediction_weight']); ow=float(ctx.config['selection']['overprediction_weight'])
    for _,tr in data.targets.iterrows():
        t=tr.target_column; g=frozen[frozen.target_column==t]; y=g.actual.to_numpy(float); peak=_positive_peak(data.development[t],q)
        methods=['selected_prediction']+[m for m in BASELINES if m in g]+(['standard_l1'] if 'standard_l1' in g and g.standard_l1.notna().all() else [])
        for m in methods:
            rec={'split':'test_2025_frozen','target_column':t,'family':g.family.iloc[0],'method':m,**regression(y,g[m],peak,uw,ow)}
            if m=='selected_prediction':
                rec['interval_80_coverage']=float(((y>=g.prediction_p10.to_numpy(float))&(y<=g.prediction_p90.to_numpy(float))).mean())
                rec['interval_mean_width']=float((g.prediction_p90-g.prediction_p10).mean())
            rows.append(rec)
        if tr.target_type!='point_at_horizon' and 'event_probability' in g:
            c=calibration[calibration.target_column==t].iloc[0]; events.append({'split':'test_2025_frozen','target_column':t,**event_metrics(y,g.event_probability,float(c.event_threshold))})
        wg=walk[walk.target_column==t];
        for month,mg in wg.groupby('calendar_month'): wrows.append({'split':'test_2025_walkforward','calendar_month':month,'target_column':t,'family':mg.family.iloc[0],'method':'selected_prediction',**regression(mg.actual,mg.selected_prediction,peak,uw,ow)})
        wrows.append({'split':'test_2025_walkforward','calendar_month':'ALL','target_column':t,'family':wg.family.iloc[0],'method':'selected_prediction',**regression(wg.actual,wg.selected_prediction,peak,uw,ow)})
    return pd.DataFrame(rows),pd.DataFrame(events),pd.DataFrame(wrows)

def run_modeling(ctx,data,logger):
    vp,cal,iters=validation_oof(ctx,data,logger); vm,ve,sel=evaluate_validation(ctx,data,vp,cal)
    frozen,meta=frozen_test(ctx,data,sel,cal,iters,vp,logger); walk=walkforward(ctx,data,sel,cal,iters,logger); fm,fe,wm=evaluate_final(ctx,data,frozen,walk,sel,cal)
    vp_path=ctx.prediction_dir/'validation_oof_k5b2.parquet'; fr_path=ctx.prediction_dir/'test_2025_frozen_k5b2.parquet'; wf_path=ctx.prediction_dir/'test_2025_walkforward_k5b2.parquet'
    vp.to_parquet(vp_path,index=False,compression=ctx.config['resources']['parquet_compression']); frozen.to_parquet(fr_path,index=False,compression=ctx.config['resources']['parquet_compression']); walk.to_parquet(wf_path,index=False,compression=ctx.config['resources']['parquet_compression'])
    # Transparent sensitivity to the underprediction penalty and target event distributions.
    sensitivity=[]
    for target,g in vp.groupby('target_column'):
        family=str(g.target_family.iloc[0]); methods=(FIXED_VARIANTS+['persistence']) if family=='fixed' else (FLEX_HURDLE+TWEEDIE_VARIANTS+BASELINES+(['standard_l1'] if 'standard_l1' in g and g.standard_l1.notna().all() else []))
        for weight in [1.0,2.0,4.0]:
            ranked=[]
            for method in methods:
                if method not in g: continue
                met=regression(g.actual,g[method],_positive_peak(g.actual,float(ctx.config['analysis']['positive_peak_quantile'])),weight,1.0)
                ranked.append((method,met['asymmetric_loss'],met['mae']))
            ranked=sorted(ranked,key=lambda x:(x[1],x[2]))
            for rank,(method,loss,mae) in enumerate(ranked,1): sensitivity.append({'target_column':target,'family':family,'underprediction_weight':weight,'method':method,'rank':rank,'asymmetric_loss':loss,'mae':mae})
    distributions=[]
    for _,row in data.targets.iterrows():
        for split,frame in [('development_2024',data.development),('test_2025',data.test)]:
            y=frame[row.target_column].to_numpy(float); pos=y[y>0]
            distributions.append({'split':split,'target_column':row.target_column,'target_type':row.target_type,'horizon_steps':int(row.horizon_steps),'horizon_minutes':int(row.horizon_minutes),'count':len(y),'zero_ratio':float(np.mean(y==0)),'mean':float(np.mean(y)),'median':float(np.median(y)),'positive_count':len(pos),'positive_mean':float(np.mean(pos)) if len(pos) else np.nan,'positive_p50':float(np.quantile(pos,.5)) if len(pos) else np.nan,'positive_p95':float(np.quantile(pos,.95)) if len(pos) else np.nan,'positive_p99':float(np.quantile(pos,.99)) if len(pos) else np.nan,'maximum':float(np.max(y))})
    tables={'validation_metrics.csv':vm,'frozen_test_metrics.csv':fm,'walkforward_monthly_metrics.csv':wm,'event_metrics.csv':pd.concat([ve,fe],ignore_index=True),'model_selection.csv':sel,'calibration_parameters.csv':cal,'selection_weight_sensitivity.csv':pd.DataFrame(sensitivity),'target_event_distribution.csv':pd.DataFrame(distributions)}
    for n,df in tables.items(): df.to_csv(ctx.metric_dir/n,index=False,encoding='utf-8-sig')
    write_json(ctx.output_dir/'iteration_map.json',iters); write_json(ctx.output_dir/'final_model_metadata.json',meta)
    return Results(vp_path,fr_path,wf_path,vm,fm,wm,pd.concat([ve,fe],ignore_index=True),sel,cal,meta)
