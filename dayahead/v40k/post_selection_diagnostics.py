"""Outcome-stratified diagnostics only; no model fit/predict or selection mutation."""
import math
import numpy as np
import pandas as pd
from .common import *
from .data import frame,train_mask
from .models import features
from .protocol import SPLIT,POINT_GATE
from dayahead.v40j.methods import SupportGuard

QUANTILES=[.05,.25,.5,.75,.9,.95]
LABELS=['P5','P25','P50','P75','P90','P95']
def quantiles(a):
    return dict(zip(LABELS,np.quantile(a,QUANTILES,method='linear').tolist())) if len(a) else {k:None for k in LABELS}
def wilson(k,n):
    if not n:return [None,None]
    z=1.959963984540054;p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [center-half,center+half]
def basic(y,p):
    e=np.asarray(y)-np.asarray(p);n=len(e)
    if not n:return {'N':0,'Q50_pinball_loss':None,'MAE':None,'underprediction_rate':None,'mean_signed_error':None,'median_signed_error':None,'median_calibration_error':None}
    mae=float(np.abs(e).sum()/n);rate=float(np.count_nonzero(e>0)/n)
    return {'N':n,'Q50_pinball_loss':mae/2,'MAE':mae,'underprediction_rate':rate,
      'mean_signed_error':float(e.sum()/n),'median_signed_error':float(np.median(e)),
      'median_calibration_error':abs(rate-.5)}

def main():
    contract=read('V40K_POST_SELECTION_DIAGNOSTIC_CONTRACT.json')
    before={n:sha(OUT/n) for n in ['V40K_POINT_SELECTION.json','V40K_POINT_MODEL_COMPARISON.json','V40K_PREHOLDOUT_EXECUTION_FREEZE.json','POINT_HOLDOUT_PREDICTIONS.parquet']}
    assert read('V40K_POINT_SELECTION.json')['winner'] is None
    with Firewall('post_selection_diagnostics'):
        f=frame(OUT/'POINT_HOLDOUT_PREDICTIONS.parquet')
        history=frame(J/'DEVELOPMENT_GPU_ROWS.parquet');history=history.loc[train_mask(history,SPLIT['final_point_fit_before'])]
        hx=features(history);qx=features(f)
        # Only diagnostic support keys: numerical equality must not depend on int/float repr.
        for col in set(FEATURES)-set(CATS):
            hx[col]=hx[col].astype(float);qx[col]=qx[col].astype(float)
        support=SupportGuard(hx,POINT_GATE['support_threshold']).predict(qx)
        for cols,count_column in [(FEATURES9,'exact_count'),(FEATURES9[1:],'near_count')]:
            counts=hx.groupby(cols,dropna=False,observed=True).size().rename('expected_count').reset_index()
            query=qx[cols].copy();query['original_order']=np.arange(len(query))
            check=query.merge(counts,on=cols,how='left',validate='many_to_one').sort_values('original_order').expected_count.fillna(0).to_numpy(int)
            assert np.array_equal(check,support[count_column].to_numpy()),'SUPPORT_NUMERIC_GROUPBY_MISMATCH'
        h=f.partition.str.contains('h100',case=False,na=False).to_numpy();s=f.qos.eq('standby').to_numpy();c=f.job_state.eq('COMPLETED').to_numpy()
        masks={'overall':np.ones(len(f),bool),'H100':h,'H100-standby':h&s,
          'retrospective COMPLETED H100':h&c,'retrospective COMPLETED H100-standby':h&s&c}
        edges=POINT_GATE['wall_buckets'];bucket=np.searchsorted(edges,f.requested_seconds,side='left')
        labels=['walltime <=1h','walltime >1h to6h','walltime >6h to24h','walltime >24h to72h','walltime >72h']
        masks.update({name:bucket==i for i,name in enumerate(labels)})
        masks.update({name:f.requested_seconds.to_numpy()==hours*3600 for name,hours in [('12h exact',12),('24h exact',24),('48h exact',48)]})
        for state in ['STRONG_SUPPORT','SPARSE_SUPPORT','REGIME_MISMATCH','OUT_OF_SUPPORT']:
            masks[state]=support.support_class.eq(state).to_numpy()
        for name,m in list(masks.items())[:5]:
            if name!='overall':masks[name+' / STRONG_SUPPORT']=m&masks['STRONG_SUPPORT']
        dates=f.submit_time.dt.strftime('%Y-%m-%d').to_numpy();days=sorted(set(dates));rng=np.random.default_rng(SEED)
        resamples=rng.integers(0,len(days),size=(2000,len(days)))
        y=f.runtime_seconds.to_numpy(float);p=f.K0.to_numpy(float);g=f.num_gpus_req.to_numpy(float);req=f.requested_seconds.to_numpy(float)
        start=f.start_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy()/1e9
        residual=y-p
        slot_miss=np.maximum(0,np.ceil((start+y)/300)-np.ceil((start+p)/300))
        actual_slots=np.where(y>0,np.maximum(0,np.ceil((start+y)/300)-np.floor(start/300)),0)
        reports={};distributions={};deltas={}
        candidates=list(read('V40K_POINT_MODEL_COMPARISON.json')['candidates'])
        for name,mask in masks.items():
            yy=y[mask];pp=p[mask];e=residual[mask];n=int(mask.sum());r=basic(yy,pp)
            if n:
                counts=np.array([np.sum(mask&(dates==d)) for d in days]);positives=np.array([np.sum(mask&(dates==d)&(residual>0)) for d in days])
                bn=counts[resamples].sum(axis=1);bp=positives[resamples].sum(axis=1);valid=bn>0;boot=bp[valid]/bn[valid]
                r.update({'Wilson95_underprediction_interval':wilson(int((e>0).sum()),n),
                  'UTC_day_block_bootstrap95_underprediction':np.quantile(boot,[.025,.975]).tolist(),
                  'observed_UTC_days':int((counts>0).sum()),'daily_N':dict(zip(days,counts.tolist())),
                  'support_sufficient_at_frozen_N100':n>=100})
                positive=e[e>0];normalized=e/req[mask];gpu=g[mask]
                miss_weight=float(np.sum(slot_miss[mask]*gpu));actual_weight=float(np.sum(actual_slots[mask]*gpu))
                distributions[name]={'N':n,'residual_seconds':quantiles(e),'strict_positive_residual_N':len(positive),
                  'positive_residual_Q90_seconds':float(np.quantile(positive,.9)) if len(positive) else None,
                  'positive_residual_Q95_seconds':float(np.quantile(positive,.95)) if len(positive) else None,
                  'predicted_finished_but_actually_active_job_rate':r['underprediction_rate'],
                  'GPU_weighted_any_active_miss_rate':float(np.sum(gpu*(e>0))/gpu.sum()),
                  'GPU_weighted_active_miss_5min_slots':miss_weight,
                  'actual_active_GPU_5min_slots':actual_weight,
                  'GPU_active_miss_slot_rate':miss_weight/actual_weight if actual_weight else None,
                  'GPU_weighted_underprediction_seconds':float(np.sum(gpu*np.maximum(e,0))),
                  'nominal_overreserved_GPU_hours':float(np.sum(gpu*np.maximum(-e,0))/3600),
                  'requested_walltime_normalized_residual':{'definition':'(actual-K0)/requested_seconds','quantiles':quantiles(normalized),'mean':float(normalized.mean()),'median':float(np.median(normalized))},
                  'metric_scope':'Frozen V40K workload-layer duration/grid-slot accounting; job-level active-miss rate is identical to underprediction rate, not an independent metric.'}
            else:
                r.update({'Wilson95_underprediction_interval':[None,None],'UTC_day_block_bootstrap95_underprediction':[None,None],'observed_UTC_days':0,'daily_N':{d:0 for d in days},'support_sufficient_at_frozen_N100':False})
                distributions[name]={'N':0,'status':'NO_ROWS'}
            reports[name]=r;deltas[name]={}
            for cid in candidates:
                z=basic(yy,f.loc[mask,cid].to_numpy(float))
                deltas[name][cid]={'N':n,'pinball_delta_candidate_minus_K0':z['Q50_pinball_loss']-r['Q50_pinball_loss'] if n else None,
                  'MAE_delta_candidate_minus_K0':z['MAE']-r['MAE'] if n else None,
                  'median_calibration_error_delta_candidate_minus_K0':z['median_calibration_error']-r['median_calibration_error'] if n else None}
        primary=contract['primary_diagnostic_populations']
        too_small=[n for n in primary if reports[n]['N']<100]
        excludes=[n for n in primary if reports[n]['N']>=100 and not (reports[n]['Wilson95_underprediction_interval'][0]<=.5<=reports[n]['Wilson95_underprediction_interval'][1])]
        if too_small:decision='INSUFFICIENT_SUBGROUP_SUPPORT'
        elif excludes:decision='CONDITIONAL_POINT_BIAS_REMAINS'
        else:decision='POINT_CENTRAL_MODEL_ADEQUATE_TAIL_MODEL_PRIMARY'
        scope={'post_selection_only':True,'no_new_predictions_or_models':True,'selection_unchanged':True,
          'input_holdout_SHA':before['POINT_HOLDOUT_PREDICTIONS.parquet'],'support_population_rows':len(history),
          'support_numeric_key_normalization':'float values on both sides; exact/near counts independently match numeric pandas groupby; no threshold or model change',
          'support_population_max_end':str(history.end_time.max()),'support_freeze_before':'2025-04-01T00:00:00Z',
          'status_fields':'Retrospective stratification only; never production input','job_level_interval_caveat':'Wilson treats jobs as independent. Seven-day blocked bootstrap is a descriptive dependence sensitivity, not evidence of generalization beyond this selection cohort.'}
        write('V40K_K0_APRIL_SUBGROUP_DIAGNOSTICS.json',{'scope':scope,'subgroups':reports})
        write('V40K_K0_ERROR_DISTRIBUTION.json',{'scope':scope,'subgroups':distributions})
        write('V40K_POST_SELECTION_CANDIDATE_DELTAS.json',{'scope':scope,'delta_direction':'positive is worse for all three metrics','subgroups':deltas})
        completed_rate=reports['retrospective COMPLETED H100-standby']['underprediction_rate']
        history_compare=[{'revision':'V40I','population':'forensic COMPLETED H100','time_split':'historical V40I forensic cohort; distinct from V40J/V40K','underprediction_approx':.6413,'provenance':'User-supplied historical summary; no V40I outcome artifact reread'},
          {'revision':'V40J','population':'development validation C0 COMPLETED H100-standby','time_split':'F1/F2/F3 February15-March07 UTC','underprediction_approx':.7364,'provenance':'Frozen V40J result; separate cohort'},
          {'revision':'V40K','population':'April pooled K0','time_split':'April01-07 point-selection complete-case cohort','N':len(f),'underprediction':reports['overall']['underprediction_rate']},
          {'revision':'V40K','population':'April retrospective COMPLETED H100-standby K0','time_split':'April01-07 point-selection complete-case cohort','N':reports['retrospective COMPLETED H100-standby']['N'],'underprediction':completed_rate}]
        write('V40K_HISTORICAL_POPULATION_COMPARISON.json',{'populations':history_compare,'pooled_or_paired_cross_revision_estimate':None,'reason':'Different conditioning populations and time splits; not a like-for-like trend or treatment effect.'})
        write('V40K_POST_SELECTION_DIAGNOSTIC_DECISION.json',{'decision':decision,'classification':'V40K_POINT_MODEL_INSUFFICIENT','point_winner':None,
          'primary_conditional_populations_excluding_50pct':excludes,'insufficient_groups':too_small,
          'pooled_K0':reports['overall'],'primary_conditional_results':{n:reports[n] for n in primary},
          'not_only_upper_tail':decision=='CONDITIONAL_POINT_BIAS_REMAINS',
          'inference_boundary':'Descriptive conditional error remains in supported subgroups. Retrospective completed-group results do not redefine the unconditional causal Q50 estimand or authorize a status feature.',
          'next_revision_direction':'Study conditional central calibration and tail shape separately under a new preregistration; no work added inside V40K.',
          'safe_fit_opened':False,'shadow_opened':False,'selection_changed':False})
        lines=['# V40K post-selection 진단','',f'진단 분류: **{decision}**. V40K의 **V40K_POINT_MODEL_INSUFFICIENT / winner NONE**은 그대로다.','',
          '이미 개봉한 13,060행의 저장된 예측만 사용했다. 모델 fit/predict, 새 candidate, threshold 변경, safe calibration, shadow open은 수행하지 않았다. Support는 기존 N=100 기준과 Apr01 이전 end-known 역사만 사용했다.','',
          '| K0 subgroup | N | Pinball50 s | MAE s | Underprediction | Mean residual s | Median residual s |',
          '|---|---:|---:|---:|---:|---:|---:|']
        for name,r in reports.items():
            if r['N']:lines.append(f"| {name} | {r['N']:,} | {r['Q50_pinball_loss']:.3f} | {r['MAE']:.3f} | {r['underprediction_rate']:.3%} | {r['mean_signed_error']:.3f} | {r['median_signed_error']:.3f} |")
            else:lines.append(f'| {name} | 0 | — | — | — | — | — |')
        lines+=['','| 주요 subgroup residual s | P5 | P25 | P50 | P75 | P90 | P95 | Positive-only Q90 | Positive-only Q95 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for name in ['overall']+primary:
            d=distributions[name]
            if d['N']:lines.append('| '+name+' | '+' | '.join(f"{d['residual_seconds'][k]:.1f}" for k in LABELS)+f" | {d['positive_residual_Q90_seconds']:.1f} | {d['positive_residual_Q95_seconds']:.1f} |")
        lines+=['','V40I forensic COMPLETED H100 ≈64.13%, V40J development COMPLETED H100-standby ≈73.64%, V40K April pooled 50.061%, V40K April COMPLETED H100-standby '+f'{completed_rate:.3%}'+'. Population과 time split이 다르므로 개선 추세처럼 합치지 않는다.','',
          '진단용 Wilson 95% 구간과 UTC-day block bootstrap 민감도는 JSON에 함께 기록했다. 이는 새 point selection gate가 아니다. 최종 status는 평가 층화에만 사용했으며, conditional error 진단은 기존 causal Q50 정의를 바꾸지 않는다.','',
          '| Candidate pooled delta vs K0 | Pinball delta s | MAE delta s | Median-calibration-error delta |','|---|---:|---:|---:|']
        for cid,d in deltas['overall'].items():lines.append(f"| {cid} | {d['pinball_delta_candidate_minus_K0']:+.3f} | {d['MAE_delta_candidate_minus_K0']:+.3f} | {d['median_calibration_error_delta_candidate_minus_K0']:+.6f} |")
        lines+=['','Subgroup별 candidate delta와 requested-walltime-normalized residual, GPU active miss 전체 표는 JSON에 저장했다. 이 진단으로 winner를 재선정하거나 V40K holdout을 학습·튜닝에 재사용하지 않았다.']
        (OUT/'V40K_POST_SELECTION_DIAGNOSTICS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
        assert all(sha(OUT/n)==h for n,h in before.items())
        assert sha(OUT/'V40K_POINT_SELECTION.json')==contract['selection_result_SHA_before']
        assert not (OUT/'V40K_POINT_MODEL_FREEZE.json').exists()
        assert not any((OUT/(s+'_ROWS.parquet')).exists() for s in ['SAFE_FIT','SAFE_SELECTION','FINAL_SHADOW'])
        assert sum(reports[k]['N'] for k in ['STRONG_SUPPORT','SPARSE_SUPPORT','REGIME_MISMATCH','OUT_OF_SUPPORT'])==len(f)
        assert abs(reports['overall']['Q50_pinball_loss']*2-reports['overall']['MAE'])<1e-10
        assert distributions['overall']['predicted_finished_but_actually_active_job_rate']==reports['overall']['underprediction_rate']
        write('V40K_POST_SELECTION_DIAGNOSTIC_INTEGRITY.json',{'status':'PASS','unchanged_before_after_SHA':before,
          'support_partition_counts_sum_to_N':True,'pinball_equals_half_MAE':True,'active_miss_job_rate_equals_underprediction':True,
          'exact_and_near_support_verified_by_independent_numeric_groupby':True,
          'new_scientific_fits':0,'new_model_predictions':0,'new_candidate_count':0,'threshold_changes':0,'new_data_partitions_opened':0,
          'safe_fit_and_shadow_opened':False,'V40K_selection_unchanged':True,'classification_unchanged':'V40K_POINT_MODEL_INSUFFICIENT'})
        event('post_selection_diagnostics_completed',decision=decision,selection_changed=False)
        print(json.dumps({'decision':decision,'primary_groups':{k:reports[k] for k in ['overall']+primary},'support_counts':support.support_class.value_counts().to_dict()},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
