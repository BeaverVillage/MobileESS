"""Read stored selection outputs; no fit, model prediction, or protocol mutation."""
import math
import pickle
import numpy as np
import pandas as pd
from .common import *
from .data import frame,base_features,keys
from .protocol import IDS,BUCKETS

def distribution(a):
    a=np.asarray(a,float)
    return {'N':len(a),'mean':float(a.mean()),'min':float(a.min()),'P50':float(np.quantile(a,.5)),'P90':float(np.quantile(a,.9)),'P95':float(np.quantile(a,.95)),'max':float(a.max())} if len(a) else {'N':0}
def gate(value,threshold,passed,*,hard=True,n=None,status=None):
    return {'value':value,'threshold':threshold,'status':status or ('PASS' if passed else 'FAIL'),'hard_gate':hard,'N':n}

def main():
    protected=['V40L_TAIL_SELECTION_COMPARISON.json','SELECTION_PREDICTIONS.parquet','V40L_TAIL_METHOD_FREEZE.json','V40L_FINAL_STATUS.json','V40L_FINAL_SHADOW_REPORT.json','V40L_TAIL_CANDIDATE_REGISTRY.json','V40L_TAIL_ESTIMAND_CONTRACT.json','V40L_CALIBRATION_FREEZE.json','V40L_PRECALIBRATION_EXECUTION_FREEZE.json']
    before={n:sha(OUT/n) for n in protected}
    frozen=read('V40L_PRECALIBRATION_EXECUTION_FREEZE.json')['file_SHA']
    frozen.update(read('V40L_CALIBRATION_FREEZE.json')['file_SHA'])
    assert read('V40L_TAIL_SELECTION_COMPARISON.json')['winner'] is None
    assert read('V40L_FINAL_STATUS.json')['classification']=='V40L_TAIL_MODEL_INSUFFICIENT'
    assert not read('V40L_FINAL_SHADOW_REPORT.json')['opened']
    with Firewall('post_selection_tail_diagnostic'):
        c=read('V40L_TAIL_SELECTION_COMPARISON.json');f=frame(OUT/'SELECTION_PREDICTIONS.parquet')
        # Join selection's immutable support lookup. No Support.transform or predictor call.
        lookup=pickle.loads((OUT/'models/SUPPORT.pkl').read_bytes());x=base_features(f)
        assert (f.submit_time.astype('datetime64[ns, UTC]').astype('int64')>=lookup.freeze).all()
        exact=np.array([len(lookup.tables[0].get(k,())) for k in keys(x,F9)],int)
        near=np.array([len(lookup.tables[1].get(k,())) for k in keys(x,F9[1:])],int)
        state=np.where(exact>=100,'STRONG_SUPPORT',np.where(exact>0,'SPARSE_SUPPORT',np.where(near>=100,'REGIME_MISMATCH','OUT_OF_SUPPORT')))
        counts=pd.Series(state).value_counts().to_dict();support_receipt=read('V40L_SELECTION_SUPPORT_VERIFICATION.json')
        assert counts==support_receipt['support_class_counts']
        h=x.hardware.eq('H100').to_numpy();standby=x.standby.eq(1).to_numpy();critical=h&standby&(exact>=100)
        assert int(critical.sum())==support_receipt['strong_H100_standby_N']==4
        y=f.runtime_seconds.to_numpy(float);k0=f.K0.to_numpy(float);gpu=f.num_gpus_req.to_numpy(float)
        table={};gate_table={}
        for cid in IDS:
            record=c['candidates'][cid]
            if 'metrics' not in record:
                table[cid]={'status':record['status'],'evaluated':False,'metrics':None};gate_table[cid]={'availability':gate(False,'causal censor authority required',False,status='NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE')};continue
            a=f[cid+'_Q90'].to_numpy(float);b=f[cid+'_Q95'].to_numpy(float);finite=np.isfinite(a)&np.isfinite(b)
            o=record['metrics']['overall']['Q90'];hm=record['metrics']['H100']['Q90'];sm=record['metrics']['H100-standby']['Q90'];cm=record['metrics']['STRONG_SUPPORT H100-standby']['Q90']
            raw_cross=c['crossing_before_repair'].get(cid,c['fallback'].get(cid,{}))
            if 'crossing' in raw_cross:raw_cross=raw_cross['crossing']
            cross=int(np.sum(finite&(b<a)));below=int(np.sum(finite&(a<k0)));abst=int((~finite).sum())
            r={'evaluated':True,'N':len(f),'overall_Q90_coverage':o['coverage'],'H100_Q90_coverage':hm['coverage'],'H100_standby_Q90_coverage':sm['coverage'],
              'support_sufficient_H100_standby_Q90_coverage':cm['coverage'],'support_sufficient_H100_standby_N':cm['N'],'GPU_weighted_Q90_coverage':o['GPU_weighted_coverage'],
              'active_miss_GPU_5min_slots':o['active_miss_GPU_5min_slots'],'GPU_weighted_underprediction_seconds':o['GPU_weighted_underprediction_seconds'],
              'overreserved_GPU_hours':o['overreserved_GPU_hours'],'mean_safe_duration_inflation_seconds':o['mean_safe_inflation_seconds'],
              'raw_Q90_Q95_crossing_count':raw_cross.get('raw_Q95_below_Q90'),'post_repair_Q90_Q95_crossing_count':cross,
              'safe_below_K0_count':below,'abstention_count':abst,'insufficient_historical_exact_support_job_count':int((exact<100).sum()),
              'insufficient_required_evaluation_subgroup_count':len(record['required_insufficient_subgroups']),
              'critical_subgroup_N_shortfall':max(0,100-cm['N']),'eligible':record['eligible']}
            table[cid]=r
            gates={}
            for name,m in [('overall',o),('H100',hm),('support_sufficient_H100_standby',cm)]:
                ok=m['N']>=100 and m['coverage']>=.9
                gates[name]=gate(m['coverage'],'coverage >= 0.90 AND evaluation N >= 100',ok,n=m['N'],status='INSUFFICIENT_SUPPORT' if m['N']<100 else None)
            gates['H100_standby_all_rows']=gate(sm['coverage'],'reference 0.90; diagnostic only, not an additional preregistered hard gate',sm['coverage']>=.9,hard=False,n=sm['N'])
            gates['GPU_weighted_coverage']=gate(o['GPU_weighted_coverage'],'>= 0.90',o['GPU_weighted_coverage']>=.9)
            gates['abstention']=gate(abst,'== 0',abst==0)
            gates['Q90_Q95_monotonicity']=gate(cross,'post-repair crossing count == 0 on served rows',cross==0)
            gates['safe_ge_K0']=gate(below,'served-row violation count == 0',below==0)
            gates['finite_predictions']=gate(bool(finite.all()),'all predictions finite; no abstentions',bool(finite.all()))
            for name,metric in [('overreservation','overreserved_GPU_hours'),('inflation','mean_safe_inflation_seconds'),('active_miss','active_miss_GPU_5min_slots')]:
                gates[name]=gate(o[metric],'no absolute threshold; lexicographic efficiency among eligible candidates',False,hard=False,status='NOT_REACHED_NO_ELIGIBLE_CANDIDATE')
            gates['GPU_underprediction_seconds']=gate(o['GPU_weighted_underprediction_seconds'],'diagnostic only; no absolute threshold',False,hard=False,status='NOT_A_HARD_GATE')
            gate_table[cid]=gates

        a=f.T7_Q90.to_numpy(float);b=f.T7_Q95.to_numpy(float);miss=y>a
        excess=np.maximum(y-a,0);mass=gpu*excess;total=float(mass.sum());nmiss=int(miss.sum())
        starts=f.start_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy()/1e9
        slots=gpu*np.maximum(0,np.ceil((starts+y)/300)-np.ceil((starts+a)/300))
        assert abs(total-table['T7']['GPU_weighted_underprediction_seconds'])<1e-7
        assert float(slots.sum())==table['T7']['active_miss_GPU_5min_slots']
        cohort=f.loc[miss,['job_id','submit_time','start_time','end_time','runtime_seconds','requested_seconds','num_gpus_req','partition','qos','job_state','K0','T7_Q90','T7_Q95']].copy()
        cohort['hardware']=x.hardware.to_numpy()[miss];cohort['standby']=standby[miss]
        cohort['support_class']=state[miss];cohort['historical_exact_support_count']=exact[miss];cohort['historical_near_support_count']=near[miss]
        cohort['K0_residual_seconds']=(y-k0)[miss];cohort['T7_Q90_excess_seconds']=excess[miss]
        cohort['GPU_underprediction_seconds']=mass[miss];cohort['GPU_miss_mass_share']=mass[miss]/total
        cohort['active_miss_GPU_5min_slots']=slots[miss]
        cohort['requested_GPU_hours']=(gpu*f.requested_seconds.to_numpy(float)/3600)[miss]
        cohort['requested_walltime_bucket']=x.wall_bucket.to_numpy()[miss].astype(int)
        cohort['job_state_role']='RETROSPECTIVE_DIAGNOSTIC_ONLY'
        cohort=cohort.sort_values(['GPU_underprediction_seconds','job_id'],ascending=[False,True],kind='stable').reset_index(drop=True)
        cohort.to_csv(OUT/'V40L_TAIL_MISS_COHORT.csv',index=False,encoding='utf-8',lineterminator='\n')
        group_reports={}
        for cols in [['hardware'],['standby'],['num_gpus_req'],['support_class'],['requested_walltime_bucket'],['partition','qos'],['job_state']]:
            groups=[]
            for key,g in cohort.groupby(cols,dropna=False,sort=True):
                if not isinstance(key,tuple):key=(key,)
                groups.append({'group':dict(zip(cols,[v.item() if hasattr(v,'item') else v for v in key])),'N':len(g),'requested_GPU_count_sum':float(g.num_gpus_req.sum()),
                  'job_count_share':len(g)/nmiss,'GPU_underprediction_seconds':float(g.GPU_underprediction_seconds.sum()),'GPU_miss_mass_share':float(g.GPU_underprediction_seconds.sum()/total),
                  'active_miss_GPU_5min_slots':float(g.active_miss_GPU_5min_slots.sum()),'excess_seconds':distribution(g.T7_Q90_excess_seconds)})
            group_reports['+'.join(cols)]=groups
        pareto={}
        for universe,denom in [('miss_jobs',nmiss),('all_selection_jobs',len(f))]:
            pareto[universe]={}
            for pct in [.01,.05,.10]:
                k=math.ceil(pct*denom);top=cohort.head(k)
                pareto[universe][str(pct)]={'denominator_jobs':denom,'top_job_count_in_universe':k,'positive_miss_jobs_in_top':len(top),
                  'GPU_underprediction_seconds':float(top.GPU_underprediction_seconds.sum()),'share_of_total_GPU_underprediction_seconds':float(top.GPU_underprediction_seconds.sum()/total),
                  'requested_GPU_count_sum':float(top.num_gpus_req.sum()),'mean_actual_runtime_seconds':float(top.runtime_seconds.mean()),'multi_GPU_job_count':int(top.num_gpus_req.gt(1).sum())}
        summary={'N':nmiss,'selection_N':len(f),'miss_job_rate':nmiss/len(f),'requested_GPU_count_sum':float(cohort.num_gpus_req.sum()),'GPU_count_distribution':distribution(cohort.num_gpus_req),
          'hardware_counts':cohort.hardware.value_counts().to_dict(),'standby_counts':{str(k):int(v) for k,v in cohort.standby.value_counts().items()},
          'requested_walltime_seconds':distribution(cohort.requested_seconds),'actual_runtime_seconds':distribution(cohort.runtime_seconds),
          'K0_residual_seconds':distribution(cohort.K0_residual_seconds),'T7_Q90_excess_seconds':distribution(cohort.T7_Q90_excess_seconds),
          'GPU_underprediction_seconds':total,'active_miss_GPU_5min_slots':float(slots.sum()),'support_class_counts':cohort.support_class.value_counts().to_dict(),
          'retrospective_status_counts':cohort.job_state.value_counts().to_dict(),'group_breakdowns':group_reports,
          'requested_walltime_bucket_upper_seconds':BUCKETS,'pareto':pareto,'pareto_sort':'GPU_underprediction_seconds descending; job_id ascending for ties; ceil(p*N); denominators reported separately'}
        pairs={}
        for cid,base in [('T3_R','T1'),('T3_D','T2'),('T4_N100','T0'),('T4_N200','T0'),('T4_N500','T0'),('T8_N100','T1'),('T8_N200','T1'),('T8_N500','T1')]:
            r,br=table[cid],table[base]
            pairs[cid]={'reference':base,'comparison_type':'same underlying raw bound plus CQR' if cid.startswith('T3') else 'same cohort different registered method; not an isolated treatment effect',
              'overall_coverage_delta':r['overall_Q90_coverage']-br['overall_Q90_coverage'],'H100_standby_coverage_delta':r['H100_standby_Q90_coverage']-br['H100_standby_Q90_coverage'],
              'GPU_weighted_coverage_delta':r['GPU_weighted_Q90_coverage']-br['GPU_weighted_Q90_coverage'],
              'overreserved_GPU_hours_delta':r['overreserved_GPU_hours']-br['overreserved_GPU_hours'],'active_miss_GPU_slots_delta':r['active_miss_GPU_5min_slots']-br['active_miss_GPU_5min_slots'],
              'abstentions':r['abstention_count']}
        t7=table['T7'];hard_failures=[k for k,v in gate_table['T7'].items() if v['hard_gate'] and v['status']!='PASS']
        assert hard_failures==['support_sufficient_H100_standby']
        decomposition={'T7_overall_Q90_coverage':t7['overall_Q90_coverage'],'gates':gate_table['T7'],'failed_mandatory_gates':hard_failures,
          'H100_failure':False,'all_H100_standby_reference_failure':False,'GPU_weighted_coverage_failure':False,'abstention_failure':False,
          'support_sufficient_H100_standby_failure':'INSUFFICIENT_SUPPORT: N=4 <100; observed 4/4 coverage does not validate this gate',
          'conservatism_failure':'NOT_A_PREREGISTERED_ABSOLUTE_GATE; efficiency comparison not reached because no eligible candidate',
          'overreservation_vs_T0_ratio':t7['overreserved_GPU_hours']/table['T0']['overreserved_GPU_hours'],
          'GPU_miss_mass_not_GPU_coverage_failure':'Remaining miss mass concentration is a diagnostic; T7 GPU-weighted job coverage passes >=90%',
          'Q95_overall_diagnostic':c['candidates']['T7']['metrics']['overall']['Q95']['coverage'],'Q95_not_used_to_rescue_Q90':True,
          'selection_unchanged':True,'winner':None,'classification':'V40L_TAIL_MODEL_INSUFFICIENT','shadow':'SEALED'}
        classification='MIXED_FAILURE'
        evidence={
          'ML_distribution_error':{'observed':True,'evidence':'T1 and T2 raw Q90 under-cover overall/H100/standby/GPU on this selection cohort; T7 passes aggregate coverage, so failure is not universal across ML families.'},
          'calibration_inadequacy':{'observed':True,'evidence':'T3_R/T3_D lower selection coverage than their frozen raw T1/T2 bounds. Calibration-block signed corrections were negative; no correction is changed here. This demonstrates transfer inadequacy on this cohort, not a causal proof of why the population changed.'},
          'support_fallback_inadequacy':{'observed':True,'evidence':'Critical strong-support standby subgroup N=4 blocks every candidate; T8 abstains on 1164 OOD jobs; T4 variants still under-cover.'},
          'excessive_conservatism':{'observed':'reservation inefficiency, not a new hard-gate FAIL','evidence':'T4 and T6 reserve substantially more GPU-hours than T0 while failing coverage; T7 reservation ratio is diagnostic only.'},
          'GPU_extreme_tail':{'observed':'remaining miss contribution concentration quantified separately','evidence':'T7 GPU-weighted coverage passes; Pareto concentration alone is not classified as a GPU-weighted coverage gate failure.'}}
        censor={'status':'CENSOR_AUTHORITY_INSUFFICIENT','XGBoost_AFT_dependency':'AVAILABLE_SYNTHETIC_CPU_PROBE_PASS','preMay_alive_state_authority':'NOT_AVAILABLE_IN_REGISTERED_INPUTS',
          'missing':['cutoff-timestamp job alive/status snapshot','job identity and start_time known by cutoff for still-active jobs','observation timestamp supporting lower=cutoff-start for each censored job without future completion lookup'],
          'available':'Static retrospective April Parquet and aggregate footer bounds; these do not identify individual cutoff-alive jobs without forbidden completion/status value reads.',
          'censored_job_count':None,'no_undeclared_authority_search_or_payload_open':True,'May_completion_reads':0,'censored_rows_imputed':0,'V40L_T5_status_unchanged':'NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE'}
        assert all(sha(OUT/n)==h for n,h in before.items())
        assert all(sha(ROOT/rel)==h for rel,h in frozen.items())
        integrity={'status':'PASS','unchanged_selection_and_freeze_SHA':before,'frozen_source_model_calibration_SHA_unchanged':True,'new_fits':0,'new_runtime_predictions':0,
          'new_raw_payload_reads':0,'threshold_changes':0,'support_rule_changes':0,'conformal_retuning':0,'winner_reselection':0,'shadow_opened':False,
          'support_reconstruction':'Read-only join of existing frozen lookup tables to stored selection rows; no fit/predict/transform invocation; counts match pre-existing selection support verification',
          'support_lookup_SHA':sha(OUT/'models/SUPPORT.pkl'),'support_counts':counts,'CSV_SHA':sha(OUT/'V40L_TAIL_MISS_COHORT.csv')}
        diagnostic={'created_at':now(),'scope':'POST_SELECTION_DIAGNOSTIC_ONLY; no change to V40L acceptance','classification':classification,'selection_classification':'V40L_TAIL_MODEL_INSUFFICIENT','winner':None,'shadow':'SEALED',
          'exact_metric_table':table,'exact_gate_table':gate_table,'T7_failure_decomposition':decomposition,'T7_undercovered_cohort':summary,
          'raw_vs_calibrated':pairs,'failure_classification_evidence':evidence,'T5_censoring':censor,'integrity':integrity,
          'insufficient_support_count_definition':'Job-level count with historical exact_count<100 is distinct from number of insufficient required evaluation groups (1) and their N (4). Do not conflate these counts.',
          'gate_semantics':'Only preregistered hard gates determine eligibility. All-H100-standby is a diagnostic reference. Efficiency has no absolute cutoff and was not reached. Raw crossing is repaired; only post-repair monotonicity and finite availability are hard requirements.'}
        write('V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json',diagnostic,immutable=True)
        write('V40L_T7_FAILURE_DECOMPOSITION.json',decomposition,immutable=True)
        lines=['# V40L post-selection tail failure diagnostic','',f'추가 진단 분류: **{classification}**. 기존 **V40L_TAIL_MODEL_INSUFFICIENT / winner NONE / shadow SEALED**는 유지한다.','',
          '새 fit/runtime prediction/threshold/support-rule/conformal retuning은 0회다. 이미 저장된 selection 예측과 기존 동결 support lookup만 사용했다.','',
          'T7은 overall 90.827%, H100 90.373%, 전체 H100-standby 91.268%, GPU-weighted 91.385%다. 유일한 필수 gate 실패는 strong-support H100-standby의 **N=4 <100**이다. 관측 4/4=100%를 충분한 검증으로 인정하지 않았다.','',
          'Conservatism의 절대 FAIL threshold는 사전등록에 없다. 모든 후보가 필수 gate를 통과하지 못해 efficiency 순위 단계는 도달하지 않았다. T7의 overreservation 증가를 사후 hard gate로 만들지 않는다.','',
          '| Candidate | Overall Q90 | H100 Q90 | H100-standby Q90 | Support-sufficient standby Q90 | GPU Q90 | Active-miss GPU slots | GPU-underprediction seconds | Overreserved GPUh | Mean inflation s | Crossing raw→repaired | Abstentions | Historical insufficient jobs | Required insufficient groups |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for cid,r in table.items():
            if not r['evaluated']:lines.append(f'| {cid} | NOT EVALUATED: censor authority unavailable | — | — | — | — | — | — | — | — | — | — | — | — |');continue
            lines.append(f"| {cid} | {r['overall_Q90_coverage']:.3%} | {r['H100_Q90_coverage']:.3%} | {r['H100_standby_Q90_coverage']:.3%} | {r['support_sufficient_H100_standby_Q90_coverage']:.3%} (N=4) | {r['GPU_weighted_Q90_coverage']:.3%} | {r['active_miss_GPU_5min_slots']:,.0f} | {r['GPU_weighted_underprediction_seconds']:,.3f} | {r['overreserved_GPU_hours']:,.3f} | {r['mean_safe_duration_inflation_seconds']:,.3f} | {r['raw_Q90_Q95_crossing_count']}→{r['post_repair_Q90_Q95_crossing_count']} | {r['abstention_count']} | {r['insufficient_historical_exact_support_job_count']} | {r['insufficient_required_evaluation_subgroup_count']} |")
        lines+=['','| Candidate | Overall ≥90%, N≥100 | H100 ≥90%, N≥100 | Support standby ≥90%, N≥100 | GPU ≥90% | Abstentions=0 | Repaired crossings=0 | Safe<K0 violations=0 | Efficiency |','|---|---|---|---|---|---|---|---|---|']
        for cid,g in gate_table.items():
            if 'availability' in g:lines.append(f'| {cid} | NOT EVALUATED | — | — | — | — | — | — | — |');continue
            names=['overall','H100','support_sufficient_H100_standby','GPU_weighted_coverage','abstention','Q90_Q95_monotonicity','safe_ge_K0']
            lines.append('| '+cid+' | '+' | '.join(g[n]['status'] for n in names)+' | NOT REACHED |')
        lines+=['','전체 H100-standby ≥90%는 진단용 reference이며 추가 hard gate가 아니다. Underprediction seconds에는 절대 threshold가 없고, overreservation/inflation/active-miss는 eligible 후보끼리 최소화할 값이다. Historical insufficient jobs는 exact support<100인 개별 job 수로, critical subgroup 표본 N=4와 다른 개념이다.','',
          f"T7 miss cohort: N={nmiss}, requested GPU count 합={summary['requested_GPU_count_sum']:,.0f}, GPU-underprediction seconds={total:,.3f}, active-miss GPU 5분 slots={summary['active_miss_GPU_5min_slots']:,.0f}. 상세 job CSV 및 hardware/standby/walltime/support/partition/QoS/status 분해는 JSON에 저장했다. 최종 status는 retrospective diagnostic만 사용한다.",'',
          '| Pareto denominator | Top share | Selected jobs | GPU-underprediction mass share |','|---|---:|---:|---:|']
        for universe,values in pareto.items():
            for pct,r in values.items():lines.append(f"| {universe} | {float(pct):.0%} | {r['top_job_count_in_universe']} | {r['share_of_total_GPU_underprediction_seconds']:.3%} |")
        lines+=['','실패 분류는 MIXED_FAILURE다. T1/T2 raw conditional undercoverage, calibration correction의 selection 이전 적합성 부족, support 이질성과 fallback/abstention이 함께 관측됐다. T7은 aggregate coverage를 통과하므로 모든 ML tail model이 실패했다고 일반화하지 않는다. Pareto 집중도는 남아 있는 miss mass의 진단이며 GPU-weighted coverage FAIL을 뜻하지 않는다.','',
          'T5는 CENSOR_AUTHORITY_INSUFFICIENT다. AFT objective는 사용 가능하지만 registered inputs에 cutoff 시점 alive/status snapshot과 그 시점에 알려진 start-time 관측 근거가 없다. Static retrospective completion/footer만으로 이를 대체하지 않았다. Censored count는 unknown이며 새 authority 탐색이나 May completion read는 하지 않았다.','',
          '이 진단은 차기 revision 설계 근거다. V40L 모델·threshold·선택 결과를 변경하거나 Apr24–30 shadow를 열지 않았다.']
        (OUT/'V40L_TAIL_FAILURE_CLASSIFICATION.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
        print(json.dumps({'diagnostic':classification,'T7_failed_gates':hard_failures,'miss_N':nmiss,'GPU_miss_seconds':total,'pareto':pareto,'integrity':'PASS'}),flush=True)
if __name__=='__main__':main()
