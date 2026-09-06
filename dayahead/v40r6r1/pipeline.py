from .common import *
from .calibration import rolling
from .metrics import metrics,monthly,gates,select
import sys

def summarize(outputs,phase):
    reports={}; flat=[]; comparisons=[]
    for h in HORIZONS:
        reports[h]={}
        for candidate in CANDIDATES:
            f=outputs[(outputs.horizon==h)&(outputs.candidate==candidate)].sort_values(['day','window_start_slot'])
            y=f.target_GPUh.to_numpy(); u=f.rolling_upper.to_numpy(); days=f.day.to_numpy()
            m=metrics(y,u,days); months=monthly(y,u,days)
            raw=metrics(y,f.base_upper.to_numpy(),days); static=metrics(y,f.static_U2.to_numpy(),days)
            anchor=r6('SELECTION_FREEZE')['TRAIN_Q95_anchors'][h]['TRAIN_Q95']; anchor_over=float(np.maximum(anchor-y,0).sum())
            g=gates(m,months,raw['under_GPUh'],anchor_over,static['over_GPUh'])
            comparators={name:metrics(y,f[column].to_numpy(),days) for name,column in [
                ('R6_U0_STATIC_B1_Q90','base_B1_Q90'),('R6_U1_STATIC_B2_Q90','base_B2_Q90'),('R6_U2_STATIC_90_CALIBRATED','static_U2')]}
            reports[h][candidate]={'metrics':m,'monthly':months,'gates':g,'raw_base_metrics':raw,'static_U2_metrics':static,
                'TRAIN_Q95_anchor':anchor,'TRAIN_Q95_anchor_over_GPUh':anchor_over,'comparators':comparators}
            flat.append({'phase':phase,'horizon':h,'candidate':candidate,
                **{k:v for k,v in m.items() if k not in ['day_clusters','safe_to_actual_ratio']},
                'raw_base_under_GPUh':raw['under_GPUh'],'TRAIN_Q95_anchor_over_GPUh':anchor_over,
                'R6_static_U2_over_GPUh':static['over_GPUh'],'PASS':g['PASS'],'failure_reasons':'|'.join(g['failure_reasons'])})
            if m.get('support_complete'):
                comparisons.append({'phase':phase,'horizon':h,'candidate':candidate,'reference':'R6_STATIC_U2_90',
                    'positive_coverage_delta':m['positive_coverage']-static['positive_coverage'],
                    'mean_day_coverage_delta':m['mean_day_positive_coverage']-static['mean_day_positive_coverage'],
                    'under_GPUh_delta':m['under_GPUh']-static['under_GPUh'],'over_GPUh_delta':m['over_GPUh']-static['over_GPUh'],
                    'upper_WAPE_delta':m['positive_upper_WAPE']-static['positive_upper_WAPE'],
                    'safe_to_actual_ratio_delta':{k:m['safe_to_actual_ratio'][k]-static['safe_to_actual_ratio'][k] for k in ['median','P90','P95','P99']}})
    return reports,flat,comparisons

def save_phase(phase,outputs,ledger,proof):
    outputs.to_parquet(OUT/f'{phase.lower()}_rolling_predictions.parquet',index=False)
    ledger.to_parquet(OUT/f'{phase.lower()}_calibration_ledger.parquet',index=False)
    proof.to_parquet(OUT/f'{phase.lower()}_availability_proof.parquet',index=False)

def run_cal():
    reg,pre=authority()
    assert not (OUT/'cal_rolling_predictions.parquet').exists(),'CAL evaluation can execute only once'
    f=source_frame(False); outputs,ledger,proof=rolling(f,['CALIBRATION'])
    save_phase('cal',outputs,ledger,proof)
    report,flat,comparison=summarize(outputs,'CALIBRATION')
    csv('CAL_RESULTS',flat); dump('CAL_EVALUATION',{'by_horizon':report,'time_UTC':utc(),'preregistration_commit':pre})
    dump('CAL_COMPARISON',{'rows':comparison})
    chosen={h:select(report[h]) for h in HORIZONS}; selected_count=sum(v!='NONE' for v in chosen.values())
    frozen={}
    for name in ['cal_rolling_predictions.parquet','cal_calibration_ledger.parquet','cal_availability_proof.parquet',
        'V40R6R1_CAL_RESULTS.csv','V40R6R1_CAL_EVALUATION.json','V40R6R1_CAL_COMPARISON.json']:
        p=OUT/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    dump('SELECTION_FREEZE',{'time_UTC':utc(),'selected_H4':chosen['H4'],'selected_H24':chosen['H24'],
        'selected_candidates':chosen,'selection_scope':'Full CALIBRATION prequential block only',
        'service_level':.85,'coverage_band':[.85,.925],'temporal_floor':.8,'calibration_policy':reg['calibration'],
        'candidate_registry':CANDIDATES,'gates':reg['gates'],'R6_BASE_SKILL_LIMITATION':'PRESENT',
        'R6_raw_Q90_skill_gate_used_as_automatic_disqualifier':False,'candidate_comparators_selectable':False,
        'PRIMARY_WORKLOAD_RESERVE_CANDIDATE_AVAILABLE':selected_count==2,'PARTIAL_HORIZON_ONLY':selected_count==1,
        'JOINT_WORKLOAD_MODEL_SELECTED':selected_count==2,'exposed_evaluated':False,'frozen_hashes':frozen})
    print(pd.DataFrame(flat)[['horizon','candidate','positive_coverage','mean_day_positive_coverage','under_GPUh','over_GPUh','positive_upper_WAPE','PASS','failure_reasons']].to_string(index=False),flush=True)
    print('FROZEN SELECTION',chosen,flush=True)

def run_exposed():
    reg,freeze,commit=selection_authority()
    assert not (OUT/'exposed_rolling_predictions.parquet').exists(),'No repeated EXPOSED evaluation'
    f=source_frame(True); outputs,ledger,proof=rolling(f,['EXPOSED_EVALUATION'])
    save_phase('exposed',outputs,ledger,proof); report,flat,comparison=summarize(outputs,'EXPOSED_EVALUATION')
    selected=freeze['selected_candidates']; passed={h:selected[h]!='NONE' and report[h][selected[h]]['gates']['PASS'] for h in HORIZONS}
    joint=all(passed.values())
    if joint: classification='V40R6R1_85PCT_GPUWORK_RESERVE_PREVALIDATED'
    elif all(not r['metrics'].get('support_complete',False) for h in HORIZONS for r in report[h].values()): classification='V40R6R1_CALIBRATION_SUPPORT_INSUFFICIENT'
    elif not passed['H4'] and passed['H24']: classification='V40R6R1_H4_RESERVE_SAFETY_FAIL'
    elif passed['H4'] and not passed['H24'] and selected['H24']!='NONE' and any(k.startswith('over_') or 'WAPE' in k for k in report['H24'][selected['H24']]['gates']['failure_reasons']): classification='V40R6R1_H24_RESERVE_EFFICIENCY_FAIL'
    else: classification='V40R6R1_JOINT_GPUWORK_RESERVE_FAIL'
    dump('EXPOSED_RESULTS',{'time_UTC':utc(),'classification':classification,'selection_freeze_commit':commit,
        'by_horizon':report,'selected_candidates':selected,'selected_horizon_pass':passed,'joint_pass':joint,
        'reselection':False,'rule_changes':False,'base_refit':False,'scope':'Causal prequential EXPOSED historical evidence; no untouched confirmation',
        'unselected_candidates':'Diagnostic only; cannot replace a frozen NONE or a selected family'})
    csv('EXPOSED_METRICS',flat)
    dump('R6_90_VS_R6R1_85_COMPARISON',{'rows':read('CAL_COMPARISON')['rows']+comparison,'difference':'rolling85 minus static90',
        'selected_only_claims':False,'unselected_candidates_are_diagnostics':True})
    cal=read('CAL_EVALUATION')['by_horizon']
    for h in HORIZONS: dump(h+'_RESULTS',{'CALIBRATION':cal[h],'EXPOSED_EVALUATION':report[h],
        'selected_candidate':selected[h],'final_selected_pass':passed[h]})
    all_outputs=pd.concat([pd.read_parquet(OUT/'cal_rolling_predictions.parquet'),outputs],ignore_index=True)
    all_ledger=pd.concat([pd.read_parquet(OUT/'cal_calibration_ledger.parquet'),ledger],ignore_index=True)
    all_proof=pd.concat([pd.read_parquet(OUT/'cal_availability_proof.parquet'),proof],ignore_index=True)
    all_ledger.to_parquet(OUT/'V40R6R1_DAILY_CALIBRATION_LEDGER.parquet',index=False)
    all_proof.to_parquet(OUT/'V40R6R1_RESIDUAL_AVAILABILITY_PROOF.parquet',index=False)
    audit_outputs(cal,report,all_ledger,all_proof)
    repeat(f,all_outputs,all_ledger,all_proof,cal,report)
    if joint: bootstrap(outputs,selected)
    else: dump('BOOTSTRAP_STATUS',{'status':'NOT_EXECUTED_SAFETY_FAIL','draws':0,'resampling_unit':'calendar day'})
    interface(outputs,ledger,selected,joint)
    dump('FINAL_DECISION',{'classification':classification,'joint_pass':joint,'selected_candidates':selected,
        'FUTURE_WORKLOAD_MODEL_STATUS':'FROZEN_PREVALIDATED_85PCT_RESERVE' if joint else 'NO_MODEL_PROMOTED',
        'FURTHER_FUTURE_WORKLOAD_MODEL_WORK':'DEFER_UNTIL_NEW_DATA_OR_AUTHORITY','current_authority_research_status':'CLOSED',
        'NO_R6R2':True,'NO_R7':True,'no_new_model_horizon_calibration_family_or_service_level_search':True,
        'R6_90pct_classification_unchanged':True,'R6_BASE_SKILL_LIMITATION':'PRESENT','service_level':.85,
        'grid_security_probability':False,'optimizer_integration':'NO','production_ready':'NO',
        'new_LightGBM_fits':0,'new_statistical_model_fits':0,'new_classifier_fits':0,'new_feature_engineering':0,'new_target_construction':0,
        'holds':HOLDS,'TRUE_CONFIRMATORY_AVAILABLE':'NO'})
    print(pd.DataFrame(flat)[['horizon','candidate','positive_coverage','mean_day_positive_coverage','under_GPUh','over_GPUh','positive_upper_WAPE','PASS','failure_reasons']].to_string(index=False),flush=True)
    print('FINAL',classification,flush=True)

def audit_outputs(cal,exposed,ledger,proof):
    miss=[]; over=[]; temporal=[]
    for phase,report in [('CALIBRATION',cal),('EXPOSED_EVALUATION',exposed)]:
        for h,by_candidate in report.items():
            for c,r in by_candidate.items():
                for month,m in [('ALL',r['metrics']),*[(m['month'],m) for m in r['monthly']]]:
                    ids={'phase':phase,'horizon':h,'candidate':c,'month':month}
                    miss.append({**ids,**{k:m.get(k) for k in ['under_GPUh','positive_shortfall_ratio','miss_N','mean_miss_GPUh','P90_miss_GPUh','P95_miss_GPUh','maximum_miss_GPUh']}})
                    over.append({**ids,**{k:m.get(k) for k in ['over_GPUh','positive_upper_WAPE','safe_to_actual_ratio']}})
                temporal += [{'phase':phase,'horizon':h,'candidate':c,**m} for m in r['monthly']]
    dump('MISS_SEVERITY_AUDIT',{'rows':miss,'miss_quantiles':'Conditional on positive shortfall; diagnostic quantiles use linear interpolation',
        'rolling_window_GPUh_warning':'Overlapping H4 windows count the same atomic work multiple times'})
    dump('OVERRESERVATION_AUDIT',{'rows':over,'WAPE_guardrail':2.,'two_anchors':'Frozen R6 TRAIN Q95 and static U2-90; each recomputed on identical split rows'})
    dump('TEMPORAL_STABILITY_AUDIT',{'rows':temporal,'month_support_min_positive_days':5,'day_support_min_positive_windows':1,
        'day_month_floor':.8,'overlapping_windows_not_independent':True})
    delta=[]
    for (h,c),g in ledger.groupby(['horizon','candidate']):
        for month,v in [('ALL',g),*list(g.groupby(g.target_day.str[:7]))]:
            x=v.delta.dropna().to_numpy()
            delta.append({'horizon':h,'candidate':c,'month':month,'issues':len(v),'minimum':x.min() if len(x) else None,
                'median':np.median(x) if len(x) else None,'P90':np.quantile(x,.9) if len(x) else None,'maximum':x.max() if len(x) else None,
                'support_days_min':v.eligible_residual_days.min(),'support_days_max':v.eligible_residual_days.max(),
                'support_rows_min':v.eligible_residual_rows.min(),'support_rows_max':v.eligible_residual_rows.max(),
                'negative_q85_floored_count':int(v.negative_q85_floored.sum())})
    dump('DELTA_EVOLUTION_AUDIT',{'rows':delta,'smoothing':False,'quantile_selection':'Exact finite-sample order statistic; no interpolation'})
    support=[]
    for (h,c,role),g in ledger.groupby(['horizon','candidate','role']):
        g=g.sort_values('target_day'); support.append({'horizon':h,'candidate':c,'phase':role,'first_day':g.target_day.iloc[0],
            'last_day':g.target_day.iloc[-1],'initial_days':g.eligible_residual_days.iloc[0],'final_days':g.eligible_residual_days.iloc[-1],
            'initial_rows':g.eligible_residual_rows.iloc[0],'final_rows':g.eligible_residual_rows.iloc[-1],
            'monotone_support':bool((g.eligible_residual_rows.diff().dropna()>=0).all()),'insufficient_issues':int((g.status!='SUPPORTED').sum())})
    dump('RESIDUAL_LIBRARY_AUDIT',{'rows':support,'proof_rows':len(proof),'all_complete_and_mature_before_issue':bool((proof.effective_available_at<proof.issue_time).all()),
        'TRAIN_residual_rows':0,'initial_authority':'Frozen DEVELOPMENT OOS with respect to TRAIN fitting; R6 config was selected on DEV, so not an untouched tuning holdout',
        'policy':'FULL_EXPANDING_CAUSAL_HISTORY','discard_or_decay':False,'base_residuals':'Residuals against raw frozen base, never calibrated outputs'})

def repeat(frame,original,ledger,proof,cal,exposed):
    out2,led2,pro2=rolling(frame,['CALIBRATION','EXPOSED_EVALUATION'])
    keys=['horizon','candidate','day','window_start_slot']
    a=original.sort_values(keys).reset_index(drop=True); b=out2.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a,b,check_exact=True)
    lk=['horizon','candidate','target_day']; pk=['horizon','candidate','target_day','residual_day']
    pd.testing.assert_frame_equal(ledger.sort_values(lk).reset_index(drop=True),led2.sort_values(lk).reset_index(drop=True),check_exact=True)
    pd.testing.assert_frame_equal(proof.sort_values(pk).reset_index(drop=True),pro2.sort_values(pk).reset_index(drop=True),check_exact=True)
    differences=[]
    for role,expected in [('CALIBRATION',cal),('EXPOSED_EVALUATION',exposed)]:
        actual,_,_=summarize(out2[out2.role==role],role)
        assert clean(actual)==clean(expected)
        for h in HORIZONS:
            for c in CANDIDATES:
                differences.append({'phase':role,'horizon':h,'candidate':c,'metrics_max_difference':0.})
    dump('REPRODUCIBILITY_AUDIT',{'entire_calibration_repeated_once':True,'new_model_fits':0,'better_repeat_selection':False,
        'delta_sequence_max_difference':float(np.nanmax(np.abs(a.delta-b.delta))),
        'upper_prediction_max_difference':float(np.nanmax(np.abs(a.rolling_upper-b.rolling_upper))),
        'metrics_max_difference':0.,'rows':differences,'membership_proof_exact':True,'PASS':True})

def bootstrap(outputs,selected):
    rng=np.random.default_rng(SEED); report=[]
    for h in HORIZONS:
        f=outputs[(outputs.horizon==h)&(outputs.candidate==selected[h])]; contributions=[]
        for _,g in f.groupby('day'):
            y=g.target_GPUh.to_numpy(); u=g.rolling_upper.to_numpy(); s=g.static_U2.to_numpy(); p=y>0
            contributions.append([np.maximum(y-u,0).sum()-np.maximum(y-s,0).sum(),
                np.maximum(u-y,0).sum()-np.maximum(s-y,0).sum(),int((y[p]<=u[p]).sum())-int((y[p]<=s[p]).sum()),int(p.sum())])
        a=np.asarray(contributions); draws=[]
        for _ in range(1000):
            x=a[rng.integers(len(a),size=len(a))].sum(0); draws.append([x[0],x[1],x[2]/x[3] if x[3] else np.nan])
        x=np.asarray(draws)
        for j,name in enumerate(['under_GPUh','over_GPUh','positive_coverage']):
            report.append({'horizon':h,'metric':name,'difference':'selected rolling85 minus R6 static90','CI95':np.nanquantile(x[:,j],[.025,.975]),'mean':np.nanmean(x[:,j])})
    dump('BOOTSTRAP_STATUS',{'status':'EXECUTED_JOINT_EXPOSED_PASS','draws':1000,'seed':SEED,'resampling_unit':'calendar day',
        'independent_H4_window_resampling':False,'conditional_on_recorded_prequential_outputs':True,'rows':report})

def interface(outputs,ledger,selected,joint):
    rows=[]
    if joint:
        for d in sorted(outputs.day.unique()):
            row={'target_day':d,'issue_time':str(outputs[outputs.day==d].issue_time.iloc[0]),'service_level':.85,
                'model_status':'PREVALIDATED','proposal_only':True,'optimizer_use_allowed':False}
            for h in HORIZONS:
                f=outputs[(outputs.day==d)&(outputs.horizon==h)&(outputs.candidate==selected[h])].sort_values('window_start_slot')
                row[h+'_base_family']=CANDIDATES[selected[h]]; row[h+'_base_q90']=f.base_upper.tolist() if h=='H4' else float(f.base_upper.iloc[0])
                row[h+'_delta85']=float(f.delta.iloc[0]); row[h+'_upper85']=f.rolling_upper.tolist() if h=='H4' else float(f.rolling_upper.iloc[0])
                row[h+'_residual_support_days']=int(f.eligible_residual_days.iloc[0])
            row['H4_window_start_slots']=list(range(81)); rows.append(row)
    dump('OPTIMIZER_INTERFACE_PROPOSAL',{'recommended_rows':rows,'proposal_only':True,'optimizer_use_allowed':False,
        'H4_arrays':'81 within-day starts, 0 through 80, aligned by H4_window_start_slots','unit':'arriving service-work GPUh',
        'future_backlog_equation_proposal':'B[t+1]=B[t]+A[t]-S[t]; S[t]=0.25*r[t]; NOT IMPLEMENTED',
        'synthetic_jobs_created':0})

if __name__=='__main__': {'cal':run_cal,'exposed':run_exposed}[sys.argv[1]]()
