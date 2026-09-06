"""Additional frozen-predictor/placement forensic. No fitting, optimization or AC generation."""
from pathlib import Path
from collections import Counter
import math
import json
import subprocess
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40h.identity import file_record, verify_file
from .may01_forensic import ROOT as BASIC, SMOKE, G, ISSUE, AXIS, SLOT, SITES, vector, actual_segments

ROOT=Path('dayahead/artifacts/v40i_authority_electrical_closure/pending_runtime_forensic')
RUNTIME=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v35r3d_kestrel_runtime_authority_closure')
HPC=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR_scheduler_authority/07_hpc-oda-commons')
CACHE=RUNTIME/'dayahead/cache/v35r3d_kestrel_runtime_authority_closure'
ART=RUNTIME/'dayahead/artifacts/v35r3d_kestrel_runtime_authority_closure'
Q=5576.44921875
SLOT_SECONDS=900


def metrics(frame,prediction):
    """Positive signed error means underprediction. Zero-GPU jobs have zero GPU weight."""
    if frame.empty:return {'sample_count':0}
    y=frame.actual_runtime_seconds.to_numpy(float);p=frame[prediction].to_numpy(float)
    w=frame.num_gpus_req.fillna(0).to_numpy(float);assert np.all(w>=0)
    e=y-p;ae=np.abs(e);total=float(w.sum());long=y>14400
    nactual=np.ceil(y/900).astype(int);npred=np.ceil(np.maximum(p,0)/900).astype(int)
    missed=np.maximum(nactual-npred,0)
    return {'sample_count':len(frame),'GPU_count':total,'MAE_seconds':float(ae.mean()),
      'median_absolute_error_seconds':float(np.median(ae)),'RMSE_seconds':float(np.sqrt(np.mean(e**2))),
      'signed_mean_error_seconds':float(e.mean()),'median_signed_error_seconds':float(np.median(e)),
      'underprediction_rate':float(np.mean(e>0)),'overprediction_rate':float(np.mean(e<0)),
      'P90_absolute_error_seconds':float(np.quantile(ae,.9)),'P95_absolute_error_seconds':float(np.quantile(ae,.95)),
      'long_job_over_4h_count':int(long.sum()),'long_job_underprediction_rate':float(np.mean(e[long]>0)) if long.any() else None,
      'requested_GPU_weighted_MAE_seconds':float(np.dot(w,ae)/total) if total else None,
      'requested_GPU_weighted_underprediction_rate':float(np.dot(w,e>0)/total) if total else None,
      'GPU_WEIGHTED_UNDERPREDICTION_SECONDS':float(np.dot(w,np.maximum(e,0))),
      'GPU_WEIGHTED_UNDERPREDICTION_SECONDS_PER_REQUESTED_GPU':float(np.dot(w,np.maximum(e,0))/total) if total else None,
      'CRITICAL_SLOT_MISS_RATE':float(missed.sum()/nactual.sum()) if nactual.sum() else None,
      'GPU_WEIGHTED_CRITICAL_SLOT_MISS_RATE':float(np.dot(w,missed)/np.dot(w,nactual)) if np.dot(w,nactual) else None,
      'critical_slot_metric_definition':'Runtime-only service-axis exposure: count 15-minute slots predicted finished but actual active, divided by actual active service slots; same admission at service origin. This is NOT a feeder-critical-slot validation rate.'}


def buckets(frame,prediction):
    x=frame.copy()
    y=x.actual_runtime_seconds
    x['runtime_bucket']=np.select([y<900,y<1800,y<3600,y<7200,y<=14400],
        ['<15m','15-30m','30-60m','1-2h','2-4h'],default='>4h')
    x['GPU_bucket']=x.num_gpus_req.fillna(0).map(lambda g: str(int(g)) if g in (0,1,2,4,8) else '16+' if g>=16 else 'other_'+str(g))
    return {field:[{'bucket':str(k),**metrics(v,prediction)} for k,v in x.groupby(field,observed=False)] for field in ['runtime_bucket','GPU_bucket']}


def error_class(actual,point,safe,effective,authority=True):
    if not authority:return 'AUTHORITY_MISMATCH'
    if actual>effective and actual<=safe:return 'ROUNDING_INDUCED_UNDER'
    if actual>point:return 'RAW_UNDER_SAFE_COVERED' if actual<=effective else 'RAW_UNDER_SAFE_STILL_UNCOVERED'
    if actual<point:return 'RAW_OVER'
    return 'OTHER'


class Evidence:
    def __init__(self,repo):self.repo=repo;self.records={}
    def path(self,p):
        p=Path(p);p=p if p.is_absolute() else self.repo/p
        if str(p) not in self.records:self.records[str(p)]=file_record(p)
        return p
    def js(self,p):return read(self.path(p))
    def frame(self,p,**kw):return pd.read_parquet(self.path(p),**kw)
    def verify(self,out):
        for r in self.records.values():verify_file(r)
        write_json(out/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json',{'status':'PASS','pre_read_records':list(self.records.values()),
            'post_read_hashes_identical':True,'source_and_input_modified':False})


def predictor_lineage(e,out):
    runtime=e.js(ART/'V35R3D_RUNTIME_CALIBRATION.json');fit=e.js(CACHE/'issue_fit_audit.json')
    audit=e.js(ART/'V35R3D_HPCODA_SOURCE_AUDIT.json')
    causal=e.js(Path('dayahead/artifacts/v37_r4a_per_day_aidc/V37_R4A_AIDC_CAUSALITY_AUDIT.json'))
    paths=[HPC/'src/hpc_oda_commons/ingest/jobs_parquet/apply.py',
       HPC/'src/hpc_oda_commons/models/job_runtime_moe_xgboost/model.py',
       HPC/'src/hpc_oda_commons/models/rolling_tabular/base.py',HPC/'src/hpc_oda_commons/models/feature_policy.py',
       HPC/'src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml',
       HPC/'src/hpc_oda_commons/recipes/job-runtime/kestrel_moe_best_rolling.yml',
       RUNTIME/'dayahead/v35r3d/data.py',RUNTIME/'dayahead/v35r3d/runtime.py',RUNTIME/'dayahead/v35r3d/contracts.py',
       e.repo/'dayahead/v37/aidc_materializer.py',e.repo/'dayahead/v40f/common_service.py',
       e.repo/'dayahead/v40g/domain.py',e.repo/'dayahead/v40g/optimizer.py']
    refs={p.name+'::'+str(p.parent):file_record(e.path(p)) for p in paths}
    head=subprocess.check_output(['git','-C',str(HPC),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(HPC),'diff','--name-only','--','src/hpc_oda_commons/models',
        'src/hpc_oda_commons/ingest/jobs_parquet','src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml'],text=True).strip()
    assert head==audit['actual_HEAD']==causal['runtime']['model_source_HEAD'] and not dirty
    base={'cutoff_date':'2025-03-31T08:00:00Z','training_date_range':'[2024-12-01T08:00Z,2025-03-31T08:00Z) by completed end_time for final issue model',
       'validation_date_range':'[2025-03-24T00:00+10:00,2025-03-31T00:00+10:00) by submit_time; 28 frozen rolling 6h windows',
       'target_definition':'max(0,(end_time-start_time).total_seconds())',
       'feature_list':fit['feature_order'],'model_family':'Requested-walltime-bin MoE XGBoost, pooled users, global fallback',
       'loss_objective':'reg:absoluteerror; time decay exp(-0.05 * days_old); no GPU-weighted loss',
       'calibration_method':'Empirical 0.90 quantile of positive held-window residual max(actual-point,0), numpy linear; pooled across 87,824 jobs',
       'safety_margin_rule':'min(requested_seconds,max(point+5576.44921875,900))',
       'slot_rounding_rule':'ceil(safe_seconds/900), minimum one slot; 15 minutes, NOT 5 minutes'}
    chain=[
      ('raw historical Kestrel',causal['source']['archive'],RUNTIME/'dayahead/v35r3d/data.py',CACHE/'kestrel_preissue_raw.parquet',
       'Only archive members through March 2025; rows end before issue; normalized history starts early enough for rolling windows.'),
      ('descriptor normalization',CACHE/'kestrel_preissue_raw.parquet',HPC/'src/hpc_oda_commons/ingest/jobs_parquet/apply.py',CACHE/'kestrel_preissue_normalized.parquet',
       'UTC temporal normalization, duration wallclock to seconds, Slurm memory conversion, label end-start, required nonnull targets.'),
      ('training cohort',CACHE/'kestrel_preissue_normalized.parquet',e.repo/'dayahead/v37/aidc_materializer.py',CACHE/'issue_fit_audit.json',
       'Final April-01 fixed state uses 1,288,805 finite-runtime completed rows within 120 days; not refit on May labels.'),
      ('feature construction',CACHE/'kestrel_preissue_normalized.parquet',HPC/'src/hpc_oda_commons/models/rolling_tabular/base.py',CACHE/'issue_fit_audit.json',
       'Submission allowlist; numeric columns + categorical one-hot with infrequent grouping/SVD 95% target max256; target encoding disabled.'),
      ('model and raw prediction',CACHE/'kestrel_preissue_normalized.parquet',HPC/'src/hpc_oda_commons/models/job_runtime_moe_xgboost/model.py',
       e.repo/'dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_JOB_LEDGER.parquet',
       'Wallclock modal bins (up to5 modes plus open tail), min100 expert rows, global fallback. Power-user experts disabled. Model state not persisted; stored predictions retained.'),
      ('safety correction',CACHE/'calibration_predictions.parquet',RUNTIME/'dayahead/v35r3d/runtime.py',ART/'V35R3D_RUNTIME_CALIBRATION.json',
       'A pooled empirical positive-error percentile, not a conditional/conformal guaranteed upper bound. Requested cap may reduce coverage.'),
      ('slot conversion and safe duration',e.repo/'dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_JOB_LEDGER.parquet',
       e.repo/'dayahead/v37/aidc_materializer.py',e.repo/G/'common_service/COMMON_DA_SERVICE_AUTHORITY.json',
       'Seconds retained as common service identity; ceil slots consumed by both B0 and B1.'),
      ('B0/B1 Planning optimizer consumption',e.repo/G/'common_service/COMMON_DA_SERVICE_AUTHORITY.json',e.repo/'dayahead/v40g/optimizer.py',
       e.repo/SMOKE/'PRE_MESS_JOBS.json','Same per-job safe service and terminal obligation; only existing frozen decisions used.')]
    stages=[]
    for label,src,code,artifact,note in chain:
        stages.append({'stage':label,**base,'source':file_record(e.path(src)),
            'code':file_record(e.path(code)),'artifact':file_record(e.path(artifact)),'note':note})
    questions={
       'exact_target':'TOTAL_JOB_ELAPSED_EXECUTION_RUNTIME_SECONDS; consumed as a service-duration proxy, not queue delay/GPU hours/remaining runtime',
       'execution_service_runtime':'End-start elapsed during execution. It is not independently measured active compute time.',
       'queueing_delay_in_label':False,
       'migration_pause_in_label':'Synthetic counterfactual migration pause is absent from raw target and modeled separately. Raw internal suspensions/pauses are not subtracted; their occurrence is not independently established.',
       'requested_walltime':'Feature, MoE routing variable and safety cap; NOT target',
       'GPU_role':'num_gpus_req is an input feature. Target seconds are not multiplied by GPU count.',
       'heteroscedasticity':'No explicit GPU-conditional variance/quantile model, no GPU-weighted training loss, no GPU-conditional safety margin. Tree splits may learn conditional point effects.',
       'long_runtime_tail':'Requested-wallclock bins plus an open tail/fallback; no survival/censoring model or explicit long-actual-runtime uncertainty bound.'}
    result={'status':'LINEAGE_TRACED','frozen_HPC_HEAD':head,'vendor_source_unchanged':True,'source_files':refs,
       'chain':stages,'target_questions':questions,'resolved_model_config':fit['resolved_model_config'],
       'May_data_used_in_training':False,'May_Actual_used_in_calibration':False,'predictor_retrained':False,
       'runtime_causality_audit':causal['runtime'],'original_preMay_calibration':runtime,
       'training_cohort_limitation':'Completed-before-cutoff training and validation do not retain not-yet-completed long jobs; preMay calibration is pooled across the full system, not specific to May D1 backlog or GPU/standby conditional coverage.',
       'validation_scope_limitation':'Existing rolling-window predictions precede final issue fit; metrics describe the frozen recipe/calibration evidence, not an independent holdout of the final April-01 fitted state. That state was discarded by original code; no refit performed.'}
    write_json(out/'V40I_PENDING_RUNTIME_PREDICTOR_LINEAGE.json',result)
    md=['# PENDING runtime predictor lineage','',base['target_definition'],'',
      'Target은 total elapsed execution runtime이다. Queueing delay는 제외되지만 raw internal pause를 빼는 label code는 없다. 합성 counterfactual migration pause는 원본 label에 없고 replay에서 별도 처리한다.',
      '',f"학습 cutoff: {base['cutoff_date']}; 학습 범위: {base['training_date_range']}. May label 사용 NO.",
      '',f"모델: {base['model_family']}. 목적: {base['loss_objective']}.",
      '', 'Features: '+', '.join(fit['feature_order']), '',
      '전처리는 제출 시점 allowlist, numeric와 categorical one-hot/SVD다. Target encoding은 꺼져 있다. 요청 walltime은 feature/routing/cap이고 GPU 수는 feature이며 label은 GPU-hour가 아니다.',
      '',base['calibration_method'], '',base['safety_margin_rule'], '',base['slot_rounding_rule'],'',
      'q90은 조건부 coverage나 distribution-free conformal 보장이 아니다. 기존 pooled calibration coverage는 88.3790%다. Requested-walltime cap 및 GPU/standby·long-job 분포 차이를 별도로 기록한다.',
      '',result['validation_scope_limitation'],'','각 단계의 정확한 source/code/artifact 경로와 SHA-256, 날짜, feature, label, 보정·반올림 규칙은 JSON chain에 있다. 원본 소스·모델·q는 수정하지 않았다.','']
    (out/'V40I_PENDING_RUNTIME_PREDICTOR_LINEAGE.md').write_text('\n'.join(md),encoding='utf-8')
    return result


def premay(e,out):
    x=e.frame(CACHE/'calibration_predictions.parquet')
    history=e.frame(CACHE/'kestrel_preissue_normalized.parquet',
       columns=['job_id','num_gpus_req','partition','qos','start_time','end_time','runtime_seconds','requested_seconds'])
    assert not history.job_id.duplicated().any()
    x=x.merge(history,on='job_id',validate='one_to_one',suffixes=('','_source'))
    assert len(x)==87824 and np.array_equal(x.actual_runtime_seconds,x.runtime_seconds)
    assert np.array_equal(x.requested_seconds,x.requested_seconds_source)
    label=(pd.to_datetime(x.end_time,utc=True)-pd.to_datetime(x.start_time,utc=True)).dt.total_seconds()
    assert np.array_equal(x.actual_runtime_seconds,label)
    assert (pd.to_datetime(x.end_time,utc=True)<pd.Timestamp('2025-03-31T08:00Z')).all()
    reproduced_q=float(np.quantile(np.maximum(x.actual_runtime_seconds-x.point_runtime_seconds,0),.9,method='linear'))
    assert reproduced_q==Q
    safe=np.minimum(x.requested_seconds,np.maximum(x.point_runtime_seconds+Q,900))
    np.testing.assert_array_equal(safe,x.safe_runtime_seconds)
    x['effective_runtime_seconds']=np.maximum(1,np.ceil(safe/900))*900
    scopes={'pooled_calibration':x,'GPU_positive':x[x.num_gpus_req>0],
       'gpu_h100_partition':x[x.partition.astype(str).str.startswith('gpu-h100')],
       'gpu_h100_standby':x[x.partition.astype(str).str.startswith('gpu-h100') & x.qos.astype(str).eq('standby')]}
    result={'status':'EXISTING_PREMAY_PREDICTIONS_EVALUATED_READ_ONLY','sample_count':len(x),'reproduced_q90':reproduced_q,
       'uncapped_safe_coverage':float(np.mean(x.actual_runtime_seconds<=np.maximum(x.point_runtime_seconds+Q,900))),
       'requested_cap_safe_coverage':float(np.mean(x.actual_runtime_seconds<=x.safe_runtime_seconds)),
       'conservative_ceil_coverage':float(np.mean(x.actual_runtime_seconds<=x.effective_runtime_seconds)),
       'validation_type':'28 rolling preMay windows; calibration sample reused to choose q, not independent final-state validation',
       'calendar_interval_AEST':['2025-03-24T00:00:00+10:00','2025-03-31T00:00:00+10:00'],
       'all_labels_available_before_April01_issue':True,'label_code_verified_end_minus_start':True,
       'predictor_retrained':False,'May_data_used':False,'exact_frozen_final_state_independent_validation':'UNAVAILABLE_STATE_NOT_SERIALIZED_NO_REFIT',
       'scopes':{s:{p:metrics(f,p) for p in ['point_runtime_seconds','safe_runtime_seconds','effective_runtime_seconds']} for s,f in scopes.items()},
       'bucket_analysis':{s:{p:buckets(f,p) for p in ['point_runtime_seconds','effective_runtime_seconds']} for s,f in scopes.items()},
       'feeder_critical_slot_validation_rate':None,
       'feeder_critical_slot_limitation':'PreMay source has no matching frozen placement/critical feeder coordinate. Report runtime service-axis miss-rate proxy only.',
       'cohort_selection_limitation':'Jobs completing after final issue are absent from normalized historical table; right truncation can underrepresent long unfinished jobs.',
       'GPU_weight_join_missing':int(x.num_gpus_req.isna().sum()),
       'GPU_weight_missing_rule':'Missing GPU request excluded from weighted interpretation; unweighted metrics still include row.'}
    write_json(out/'V40I_PREMAY_PENDING_RUNTIME_VALIDATION.json',result)
    x.to_parquet(out/'V40I_PREMAY_VALIDATION_RECOMPUTED_ROWS.parquet',index=False)
    return result


def system(e,out,jobs,actual,diagnostics):
    from dayahead.v39a.contracts import CENTER_SWING_W_PER_GPU
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v39d.evaluate import _load_capacity
    from dayahead.v38.authority import load_wan_authority
    from dayahead.v38.contracts import RAW_WAN_TOPOLOGY,RAW_WAN_README,RAW_WAN_TRAFFIC,WAN_CONTRACT
    from dayahead.v40g.domain import options
    for path in (RAW_WAN_TOPOLOGY,RAW_WAN_README,RAW_WAN_TRAFFIC,e.repo/WAN_CONTRACT):
        e.path(path)
    for path in ['dayahead/v38/authority.py','dayahead/v38/wan.py','dayahead/v40g/domain.py',
        'dayahead/v40a/feedback.py','dayahead/v39d/evaluate.py','dayahead/v39a/power.py','dayahead/v39a/contracts.py',
        'dayahead/v28r2/c1_affine.py','dayahead/run_v16_3_voltage_candidate.py',
        'dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json',
        'dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_CAPACITY_FREEZE_CERTIFICATE.json']:
        e.path(path)
    capacity,_=_load_capacity(e.repo);wan=load_wan_authority(e.repo)
    ledger=e.frame(Path('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_JOB_LEDGER.parquet'))
    elapsed={str(r.job_id):float(r.elapsed_seconds_at_issue) for r in ledger.itertuples() if r.state_at_issue=='RUNNING'}
    flags={};counts=Counter()
    for row in jobs['B0']:
        opts=options(row,capacity,wan,elapsed)
        flags[row['job_uid']]={'temporal':len({o.start for o in opts})>1,'spatial':len({o.site for o in opts})>1,
           'migration':any(o.migrated for o in opts),'options':len(opts),'state':row['state_at_issue']}
        counts.update({k:int(flags[row['job_uid']][k]) for k in ('temporal','spatial','migration')})
    assert dict(counts)=={'temporal':616,'spatial':679,'migration':63},counts
    write_json(out/'V40I_FROZEN_CONTROLLABLE_UID_DOMAIN.json',{'counts':dict(counts),'rows':flags,'domain_changed':False,'optimization_calls':0})
    c1=load_c1(e.path(Path('dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')))
    results={};all_arrays={}
    for c in ['B0','B1']:
        comp=e.frame(SMOKE/c/'actual_readback/OPENDSS_COMPONENTS_96.parquet')
        ts=e.frame(SMOKE/c/'aidc_site_timeseries.parquet')
        rows=[]
        for t in range(96):
            eligible=np.zeros(12,dtype=int);pending=np.zeros(12,dtype=int)
            for uid,a in actual[c].items():
                if flags[uid]['spatial'] or flags[uid]['temporal']:
                    v=vector(actual_segments(a),a['requested_GPU'],t+24);eligible+=v
                    if flags[uid]['state']=='PENDING':pending+=v
            a=ts[ts.slot==t].sort_values('site_id')
            total=a.P_PCC_kW.to_numpy();occ=a.occupied_GPU.to_numpy(int)
            weather=a.iloc[0];residual=[];pending_residual=[]
            for i,s in enumerate(SITES):
                residual.append(float(exact_c1_pcc_kw(float(site_it_power_kw(capacity.site_capacity[s],int(occ[i]-eligible[i]))),float(weather.observed_t_wb_c),float(weather.observed_rh_pct),c1)))
                pending_residual.append(float(exact_c1_pcc_kw(float(site_it_power_kw(capacity.site_capacity[s],int(occ[i]-pending[i]))),float(weather.observed_t_wb_c),float(weather.observed_rh_pct),c1)))
            cc=comp[comp.slot==t].iloc[0]
            gross=float(cc.background_P_kw+cc.AIDC_P_kw);net=float(cc.P_net_kw)
            rows.append({'slot':t,'feeder_gross_load_kW':gross,'feeder_net_load_before_losses_kW':net,
              'total_AIDC_PCC_kW':float(total.sum()),'fixed_noncontrollable_AIDC_PCC_kW':float(sum(residual)),
              'flexible_AIDC_PCC_kW':float(sum(total-np.asarray(residual))),
              'B1_controllable_load_kW':float(sum(total-np.asarray(residual))),
              'PENDING_controllable_PCC_kW':float(sum(total-np.asarray(pending_residual))),
              'controllable_GPU':int(eligible.sum()),'pending_controllable_GPU':int(pending.sum()),
              'AIDC_PENETRATION':float(total.sum()/gross),'FLEXIBLE_AIDC_SHARE':float(sum(total-np.asarray(residual))/total.sum()),
              'CONTROLLABLE_FEEDER_PENETRATION':float(sum(total-np.asarray(residual))/gross)})
        f=pd.DataFrame(rows);f.to_csv(out/(c+'_CONTROLLABLE_PENETRATION_96.csv'),index=False)
        energies={k.replace('_kW','_kWh'):float(f[k].sum()*.25) for k in f if k.endswith('_kW')}
        results[c]={'critical_slot73':f[f.slot==73].iloc[0].to_dict(),'whole_day':{**energies,
          'AIDC_PENETRATION':energies['total_AIDC_PCC_kWh']/energies['feeder_gross_load_kWh'],
          'FLEXIBLE_AIDC_SHARE':energies['flexible_AIDC_PCC_kWh']/energies['total_AIDC_PCC_kWh'],
          'CONTROLLABLE_FEEDER_PENETRATION':energies['flexible_AIDC_PCC_kWh']/energies['feeder_gross_load_kWh']}}
        all_arrays[c]=ts[ts.slot==73].sort_values('site_id').P_PCC_kW.to_numpy()
    payload={'status':'CALCULATED_FROM_FROZEN_96_SLOT_ACTUAL_READBACK','cases':results,'controllable_domain_counts':dict(counts),
       'load_definition':'Feeder gross = native background consumption + AIDC PCC, excluding PV generation and losses; net-before-losses also reported. Whole-day ratios are ratios of integrated energy.',
       'flexible_definition':'Jobs with more than one frozen authorized start or site option, including 616 PENDING and 63 checkpoint-migratable RUNNING. Flex power is incremental CENTER+C1 load above a same-weather baseline removing only their active GPU for attribution.',
       'fixed_definition':'Idle/host baseline, noncontrollable job increments and residual C1 cooling retained; no arbitrary attribution of whole-site idle power to flexible jobs.',
       'simultaneous_dispatchability_caveat':'Domain eligibility is potential temporal/spatial control, not permission to curtail all service or guarantee all jobs can move simultaneously.',
       'Planning_domain_modified':False,'new_optimization_calls':0}
    write_json(out/'V40I_AIDC_CONTROLLABLE_PENETRATION.json',payload)
    path=e.path(G/'electrical/2025-05-01/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-05-01.npz')
    with np.load(path) as z:
        k=list(z['branch_names']).index('line.sw2::A');grad=z['current_sensitivity_pu_per_control'][73,:12,k].copy();rating=float(z['rating_a'][k])
    delta=all_arrays['B1']-all_arrays['B0'];rows=[]
    for i,s in enumerate(SITES):
        rows.append({'site':s,'delta_PCC_kW':float(delta[i]),'dloading_dPCC_per_kW':float(grad[i]),'dI_dPCC_A_per_kW':float(grad[i]*rating),
                     'first_order_delta_I_A':float(delta[i]*grad[i]*rating),'first_order_delta_loading':float(delta[i]*grad[i])})
    frozen=e.js(G/'V40G_MAY01_FINAL_REPORT.json')
    observed_delta=frozen['critical_metrics']['Actual_B1']['critical_current_A']-frozen['critical_metrics']['Actual_B0']['critical_current_A']
    for c in ['B0','B1']:
        source=frozen['critical_metrics']['Actual_'+c]['source']
        verify_file(source);e.path(source['path'])
    sensitivity={'status':'EXISTING_FROZEN_D1_SENSITIVITY_DIAGNOSTIC','line':'line.sw2','phase':'A','slot':73,
       'source':file_record(path),'rating_A':rating,'rows':rows,'first_order_delta_I_A':float(np.dot(delta,grad)*rating),
       'frozen_observed_delta_I_A':observed_delta,'linearization_residual_A':float(observed_delta-np.dot(delta,grad)*rating),
       'control_definition':'AIDC positive PCC kW with coupled Q=P*PF_TAN, as frozen original generator control',
       'interpretation':'Downstream locations have about 0.138 A/kW; upstream effects are about 0.00004-0.00063 A/kW. Small net downstream increments dominate over larger total upstream load reductions.',
       'limitations':'D1 anchor local linear approximation applied to Actual load delta; no new coefficient generation, no exact nonlinear causal certificate.',
       'new_coefficient_generation':False,'new_OpenDSS_calls':0}
    write_json(out/'V40I_FROZEN_SW2_PHASE_A_SENSITIVITY.json',sensitivity)
    pd.DataFrame(rows).to_csv(out/'V40I_FROZEN_SW2_PHASE_A_SENSITIVITY.csv',index=False)
    return payload,sensitivity


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;out.mkdir(parents=True,exist_ok=True);e=Evidence(repo)
    b=e.frame(BASIC/'DA_VS_ACTUAL_JOB_COMPARISON.parquet');parts=e.frame(BASIC/'JOB_SITE_RUNTIME_ADMISSION_DECOMPOSITION.parquet')
    jobs=e.js(SMOKE/'PRE_MESS_JOBS.json');by={c:{r['job_uid']:r for r in jobs[c]} for c in ['B0','B1']}
    actual={c:{r['job_uid']:r for r in e.frame(SMOKE/c/'job_ledger.parquet').to_dict('records')} for c in ['B0','B1']}
    cut=e.js(BASIC/'FROZEN_TOPOLOGY_CUT.json')['sites'];down=np.array([cut[s] for s in SITES])
    original=e.frame(Path('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_JOB_LEDGER.parquet')).set_index('job_id')
    first=b[b.case=='B1'].set_index('job_uid');cohorts={}
    for label,column,sign,expected in [('RUNTIME_UNDERPREDICTION','runtime_effect_GPU',1,29),('RUNTIME_OVERPREDICTION','runtime_effect_GPU',-1,-3),('ADMISSION_DELAY','admission_delay_effect_GPU',-1,-3)]:
        selected=parts[(parts.case=='B1')&parts.downstream&(parts.state=='PENDING')&(parts[column]*sign>0)];rows=[]
        for p in selected.itertuples():
            uid=p.job_uid;r=first.loc[uid];o=original.loc[uid];job=by['B1'][uid]
            point=float(o.diagnostic_point_total_seconds);safe=float(job['safe_duration_seconds']);effective=int(job['safe_duration_slots'])*900
            real=float(r.actual_service_seconds);authority=(safe==min(float(job['requested_walltime_seconds']),max(point+Q,900)) and effective==math.ceil(safe/900)*900)
            assert authority
            rows.append({'job_uid':uid,'requested_GPU':r.requested_GPU,'D1_state':r.D1_state,'service_tier':job['qos'],
               'source_runtime_authority':job['duration_authority'],'runtime_model_or_rule':'Frozen April-01 MoE XGBoost point + pooled q90 positive residual',
               'predicted_runtime_sec':point,'safety_margin_sec':Q,'safety_adjusted_runtime_sec':safe,
               'planning_effective_runtime_sec':effective,'actual_runtime_sec':real,
               'raw_prediction_error_sec':real-point,'effective_prediction_error_sec':real-effective,
               'safety_adjusted_prediction_error_sec':real-safe,'rounding_extra_sec':effective-safe,
               'planning_start_slot':r.DA_start_issue_slot,'planning_finish_slot':r.DA_finish_issue_slot,
               'actual_start_slot':r.actual_replay_start_issue_slot,'actual_finish_slot':r.actual_replay_finish_issue_slot,
               'slot_axis':'D_MINUS_1_ISSUE; operating73=issue97','B0_site':by['B0'][uid]['AIDC_site'],'B1_site':job['AIDC_site'],
               'actual_site_authority':r.execution_site_authority,
               'downstream_of_line_sw2_B0':cut.get(by['B0'][uid]['AIDC_site'],False),
               'downstream_of_line_sw2_B1':cut.get(job['AIDC_site'],False),
               'predicted_active_at_slot73':bool(r.critical_DA_GPU),'actual_active_at_slot73':bool(r.critical_Actual_GPU),
               'runtime_only_active_at_slot73':bool(p.runtime_only_GPU),
               'slot73_GPU_contribution':getattr(p,column),'contribution':getattr(p,column),
               'delay_slots':r.capacity_delay_slots,'delay_seconds':r.capacity_delay_slots*900,
               'classification':label,'error_classification':error_class(real,point,safe,effective,authority)})
        f=pd.DataFrame(rows);assert f.slot73_GPU_contribution.sum()==expected
        f.to_csv(out/('V40I_MAY01_SLOT73_PENDING_'+label+'.csv'),index=False,encoding='utf-8-sig');cohorts[label]=f
    under=cohorts['RUNTIME_UNDERPREDICTION']
    snap=e.frame(Path('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet'))
    snap=snap[snap.id.astype(str).isin(under.job_uid)]
    feature_fields=['wallclock_seconds','nodes_req','processors_req','gpus_requested','memory_req','partition','qos','user_hash','account_hash']
    feature_counts={k:int(snap[k].nunique(dropna=False)) for k in feature_fields}
    assert len(snap)==29 and all(v==1 for v in feature_counts.values())
    write_json(out/'V40I_UNDERPREDICTION_29_FEATURE_EQUIVALENCE.json',{'job_count':29,'distinct_count_per_feature':feature_counts,
        'unique_request':snap[feature_fields[:-2]].drop_duplicates().to_dict('records'),
        'all_nine_model_input_features_identical':True,'same_point_prediction_seconds':float(under.predicted_runtime_sec.iloc[0]),
        'interpretation':'These 29 identical observed request/identity feature vectors receive the same point estimate; realized execution duration remains heterogeneous. No new features were fitted or selected.',
        'safety_requested_cap_active_for_29':False,'five_minute_confusion':'WAN native step is 300s; workload/Planning discretization is 900s with ceil.'})
    cross=under.copy();cross['placement_group']=cross.downstream_of_line_sw2_B0.map({True:'downstream',False:'upstream'})+'->'+cross.downstream_of_line_sw2_B1.map({True:'downstream',False:'upstream'})
    crossing=[{'group':k,'job_count':len(v),'GPU_count':int(v.requested_GPU.sum()),'slot73_contribution':int(v.slot73_GPU_contribution.sum())} for k,v in cross.groupby('placement_group')]
    for k in ['upstream->downstream','downstream->downstream','downstream->upstream','upstream->upstream']:
        if k not in [x['group'] for x in crossing]:crossing.append({'group':k,'job_count':0,'GPU_count':0,'slot73_contribution':0})
    write_json(out/'V40I_UNDERPREDICTION_SPATIAL_CROSSING.json',{'groups':crossing,'rows':cross.to_dict('records')})
    labels=['B0_REFERENCE','TEMPORAL_ONLY','SPATIAL_ONLY_PENDING','JOINT_WITHOUT_RUNNING_MIGRATION','JOINT_B1']
    diagnostics={label:e.js(BASIC/(label+'_DIAGNOSTIC_LEDGER.json'))['jobs'] for label in labels}
    d={label:{r['job_uid']:r for r in rows} for label,rows in diagnostics.items()}
    reconciled=[];spatial=[]
    for uid in sorted(by['B0']):
        vals={label:int(vector(actual_segments(d[label][uid]),d[label][uid]['requested_GPU'])[down].sum()) for label in labels}
        a,t,s,j,m=[vals[k] for k in labels]
        row={'job_uid':uid,'GPU':by['B0'][uid]['requested_GPU'],'D1_state':by['B0'][uid]['state_at_issue'],
          'B0_site':by['B0'][uid]['AIDC_site'],'B1_site':by['B1'][uid]['AIDC_site'],
          'B0_downstream':cut.get(by['B0'][uid]['AIDC_site'],False),'B1_downstream':cut.get(by['B1'][uid]['AIDC_site'],False),
          **vals,'temporal':t-a,'spatial':s-a,'interaction':j-t-s+a,'migration':m-j,'total':m-a}
        for label in labels:
            seg=actual_segments(d[label][uid]);row[label+'_start']=seg[0]['start'] if seg else None;row[label+'_finish']=seg[-1]['end'] if seg else None
        assert row['temporal']+row['spatial']+row['interaction']+row['migration']==row['total']
        reconciled.append(row)
        if s!=a:
            spatial.append({**row,'uid':uid,'actual_active_slot73':bool(vector(actual_segments(d['SPATIAL_ONLY_PENDING'][uid]),row['GPU']).sum()),
              'delta_downstream_GPU':s-a,'note':'SPATIAL_ONLY actual fixed-dispatch intervention vs B0; frozen B0 start with B1 PENDING site.'})
    decomp=pd.DataFrame(reconciled);sums={k:int(decomp[k].sum()) for k in ['temporal','spatial','interaction','migration','total']}
    assert sums=={'temporal':-2,'spatial':9,'interaction':-4,'migration':-1,'total':2}
    decomp.to_csv(out/'V40I_SLOT73_ALL_UID_FACTORIAL_LEDGER.csv',index=False)
    decomp[decomp.interaction!=0].to_csv(out/'V40I_SLOT73_TEMPORAL_SPATIAL_INTERACTION_UIDS.csv',index=False)
    pd.DataFrame(spatial).to_csv(out/'V40I_MAY01_SLOT73_SPATIAL_EFFECT_LEDGER.csv',index=False)
    migration=[]
    for uid,j in by['B1'].items():
        if j.get('migration_selected'):
            a=actual['B1'][uid];r=decomp[decomp.job_uid==uid].iloc[0]
            migration.append({'job_uid':uid,'planned_migration':True,'actual_migration_executed':bool(a.get('migration_executed')),
              'completed_before_checkpoint':not bool(a.get('migration_executed')),'DA_segments':j['compute_segments'],
              'Actual_segments':actual_segments(a),'slot73_direct_migration_downstream_delta':int(r.migration)})
    write_json(out/'V40I_SLOT73_MIGRATION_10_JOB_AUDIT.json',{'rows':migration,
       'executed':sum(r['actual_migration_executed'] for r in migration),'completed_before_checkpoint':sum(r['completed_before_checkpoint'] for r in migration),
       'direct_selected_job_effect':sum(r['slot73_direct_migration_downstream_delta'] for r in migration),
       'including_dispatch_interactions':sums['migration'],'MIGRATION_PRIMARY_CAUSE':'NO'})
    running=parts[(parts.state=='RUNNING')&parts.downstream]
    running.to_csv(out/'V40I_SLOT73_RUNNING_RESIDUAL_UID_AUDIT.csv',index=False)
    reconciliation={'status':'PASS','pending_underprediction_GPU':int(under.slot73_GPU_contribution.sum()),
       'underprediction_jobs':len(under),'pending_overprediction_GPU':-3,'admission_delay_GPU':-3,
       'factorial':sums,'per_job_ledger':'V40I_SLOT73_ALL_UID_FACTORIAL_LEDGER.csv',
       'interaction_explanation':'For each UID interaction = joint_without_migration - temporal_only - spatial_only + B0. Changing start and site can change critical-slot membership and capacity admission jointly.',
       'migration_selected_count':len(migration),'MIGRATION_PRIMARY_CAUSE':'NO','RUNNING_RESIDUAL_RUNTIME_PRIMARY_CAUSE':'NO',
       'RUNNING_runtime_downstream_delta_from_DA':{c:int(running[running.case==c].runtime_effect_GPU.sum()) for c in ['B0','B1']}}
    reconciliation['interaction_nonzero_UIDs']=decomp[decomp.interaction!=0].to_dict('records')
    reconciliation['interaction_negative_UID_count']=int((decomp.interaction<0).sum())
    reconciliation['interaction_positive_UID_count']=int((decomp.interaction>0).sum())
    write_json(out/'V40I_SLOT73_FROZEN_DECISION_DECOMPOSITION.json',reconciliation)
    allpending=b[(b.case=='B1')&(b.D1_state=='PENDING')].copy()
    allpending=allpending.rename(columns={'actual_service_seconds':'actual_runtime_seconds','requested_GPU':'num_gpus_req','point_total_seconds':'point_runtime_seconds'})
    allpending['effective_runtime_seconds']=allpending.DA_compute_service_slots_ceil*900
    mayanalysis={'status':'DIAGNOSTIC_ONLY_NO_FITTING','all_pending':{p:metrics(allpending,p) for p in ['point_runtime_seconds','effective_runtime_seconds']},
       'all_pending_buckets':{p:buckets(allpending,p) for p in ['point_runtime_seconds','effective_runtime_seconds']},
       'underprediction_29_job_count':len(under),'underprediction_29_GPU':int(under.requested_GPU.sum()),
       'under_cohort_runtime_min_max_seconds':[float(under.actual_runtime_sec.min()),float(under.actual_runtime_sec.max())],
      'under_cohort_GPU_sizes':under.requested_GPU.value_counts().to_dict(),'under_cohort_error_class_counts':under.error_classification.value_counts().to_dict(),
       'under_cohort_all_features_identical':True,'under_cohort_requested_walltime_cap_inactive':True,
       'overlap_error_accounting':{'primary_mechanism':'Raw point error exceeds fixed safety margin and conservative ceil for all 29. Model error and uncovered margin describe the same 29 GPU, not additive independent causes.',
          'raw_model_error_and_margin_still_uncovered_GPU':29,'rounding_induced_under_GPU':0,'authority_mismatch_GPU':0,
          'admission_interaction_within_29_cohort_GPU':int(sum(parts[(parts.case=='B1')&parts.job_uid.isin(under.job_uid)&parts.downstream].admission_delay_effect_GPU)),
          'separate_admission_delay_cohort_GPU':-3},
       'spatial_crossing':crossing}
    write_json(out/'V40I_MAY01_PENDING_ERROR_BUCKETS.json',mayanalysis)
    print('ADDITIONAL exact job reconciliation',reconciliation,flush=True)
    lineage=predictor_lineage(e,out);validation=premay(e,out)
    penetration,sensitivity=system(e,out,jobs,actual,diagnostics)
    finalize(out,reconciliation,mayanalysis,lineage,validation,penetration,sensitivity)
    e.verify(out)
    return reconciliation


def finalize(out,recon,may,lineage,validation,penetration,sensitivity):
    classification={
      'A_PENDING_RUNTIME_UNDERPREDICTION':('CONFIRMED_PRIMARY','29 one-GPU jobs remain active after predicted finish; all raw errors exceed q and ceil padding.'),
      'B_INSUFFICIENT_SAFETY_MARGIN':('CONFIRMED_CONTRIBUTOR','Fixed pooled q fails to cover these same 29 jobs; not an independent additional 29-GPU cause or a proposal to retune q.'),
      'C_SLOT_ROUNDING_ERROR':('REJECTED','900-second conservative ceil; effective duration 22500s for the 29 jobs, longer than safe seconds.'),
      'D_PENDING_SPATIAL_PLACEMENT':('CONFIRMED_PRIMARY','Fixed spatial intervention adds 9 downstream GPU, interaction with runtime tails.'),
      'E_TEMPORAL_SHIFT':('CONFIRMED_CONTRIBUTOR','Offsetting effect -2 GPU; does not cause positive net degradation alone.'),
      'F_TEMPORAL_SPATIAL_INTERACTION':('CONFIRMED_CONTRIBUTOR','Offsetting effect -4 GPU, independently reconciled per UID.'),
      'G_MIGRATION_EXECUTION':('REJECTED','As primary worsening cause: net -1 GPU; 5 executed, 5 complete before checkpoint.'),
      'H_RUNNING_RESIDUAL_ERROR':('REJECTED','As primary worsening cause: absolute forecast-realization effects -41 B0/-32 B1; comparative +9 is preserved, not ignored.'),
      'I_POST_CUTOFF_ARRIVALS':('REJECTED','Zero added arrivals in either saved closed cohort.'),
      'J_LOW_CONTROLLABLE_PENETRATION':('CONFIRMED_CONTRIBUTOR','Contributes to limited magnitude, not sign inversion; measured ratios do not establish a universal small-effect theorem.'),
      'K_WEAK_FEEDER_SENSITIVITY':('REJECTED','As blanket explanation: sw2 downstream AIDC sensitivities are about 0.138 A/kW; upstream locations are weak. Location heterogeneity matters.')}
    final={'status':'FORENSIC_COMPLETE','reconciliation':recon,'predictor_type':'Requested-walltime-bin MoE XGBoost, reg:absoluteerror',
      'target':'total elapsed execution runtime = end-start; service proxy; not queue delay','training_cutoff':'2025-03-31T08:00:00Z',
      'safety_margin':'pooled empirical q90(max(actual-point,0))=5576.44921875s; cap at requested walltime then ceil to 900s',
      'May_data_used_in_training':False,'classification':{k:{'classification':v[0],'reason':v[1]} for k,v in classification.items()},
      'primary_root_cause':'PENDING runtime underprediction interacting with frozen spatial placement',
      'root_cause_statement':'B1 Planning expected 41 fewer sw2-downstream GPU. In Actual, 29 one-GPU PENDING jobs exceeded the point prediction, pooled safety margin and ceil duration and remained active. Frozen spatial placement contributed +9 downstream GPU, offset by temporal -2, interaction -4 and migration -1, reproducing the +2 GPU reversal. RUNNING residual error and migration are not primary worsening causes.',
      'uncertainties':['PreMay metrics are existing rolling calibration evidence, not independent validation of the discarded final fitted state.',
        'End-start labels do not separate raw internal execution pauses from compute.',
        'Synthetic actual site/segment lineage is frozen-policy replay, not an independent physical-node allocation certificate.',
        'Electrical sensitivity is a D1 local linear approximation, not an exact nonlinear causal current allocation.',
        'Closed cohort excludes future arrivals; no full-May significance or new-method superiority claim.'],
      'new_optimization_executed':False,'predictor_retrained':False,'Actual_informed_retuning':False,
      'electrical_31day_regeneration':False,'B2_B3_executed':False,'full_May_executed':False,
      'certified_electrical_regeneration_status':'HOLD_UNTIL_SEPARATE_AUTHORIZATION',
      'system':penetration['cases'],'sensitivity':sensitivity}
    write_json(out/'V40I_MAY01_WORKLOAD_FORENSIC_FINAL.json',final)
    p=penetration['cases']['B1']['critical_slot73'];v=validation['scopes']['GPU_positive']
    standby=validation['scopes']['gpu_h100_standby']
    lines=['# V40I May-01 workload forensic 최종','',
      '주원인은 PENDING runtime 과소예측과 frozen spatial placement의 결합이다. +29 GPU는 29개 1-GPU job으로 정확히 재현됐다.',
      '',
      '29개 모두 raw prediction 16,436.296875초 → q90 5,576.44921875초 추가 → safe 22,012.74609375초 → ceil 25×900=22,500초다. Actual은 28,577–43,227초로, 올림 이후에도 6,077–20,727초 부족했다. Raw prediction과 안전 여유 부족은 같은 29 GPU를 설명하므로 두 원인을 중복 합산하지 않는다. ROUNDING_INDUCED_UNDER와 AUTHORITY_MISMATCH는 0이다.',
      '29개는 관측된 9개 predictor input feature가 모두 동일하다(1 GPU, 1 node, 1 core, 85G memory, 43,200초 요청, gpu-h100-stdby/standby 및 같은 hashed user/account). 그러므로 동일 point prediction을 받은 것은 feature/모델 규칙과 일치한다. 이 cohort에서는 requested-walltime cap도 작동하지 않아 margin 부족을 cap 때문으로 설명하지 않는다.',
      '',
      f"위치 이동 교차 집계: {json.dumps(may['spatial_crossing'],ensure_ascii=False)}",'',
      'PENDING overprediction은 3 UID/−3 GPU, admission delay는 별도 3 UID/−3 GPU다. 해당 UID와 raw/safe/effective 오차, 시작·완료, 위치·권위는 각각 CSV에 있다.',
      '',
      '| 효과 | sw2 하류 GPU |','|---|---:|','| Temporal | −2 |','| Spatial PENDING | +9 |','| Interaction | −4 |','| Migration | −1 |','| 합계 | +2 |','',
      '각 항은 1,649 UID의 factorial ledger로 재현했다. 10개 계획 migration 중 5개는 실행되고 5개는 checkpoint 이전 완료했다. Migration은 primary cause가 아니다. RUNNING 잔여시간 realization은 B0 −41, B1 −32 GPU로 절대 부하를 감소시켰고 비교 차이 +9는 그대로 보존했다.',
      'Interaction −4는 −1인 7 UID와 +1인 3 UID의 합이다. 예를 들어 UID 8665994는 site만 AIDC02→AIDC10으로 바꾸면 slot 73의 하류에 1 GPU가 남지만 start까지 B1 값으로 바꾸면 이미 종료되어 0이 된다. UID 8666154–8666156은 AIDC12 admission 상호작용으로 각각 +1이다. 모든 시나리오의 start/finish와 active 상태를 CSV로 보존했다.',
      '',
      'PENDING predictor는 walltime-bin MoE XGBoost이며 label은 max(0,end−start) execution elapsed seconds다. Queue delay는 포함되지 않는다. Raw 내부 pause는 제거하는 코드가 없으므로 순수 compute-time 측정이라고 주장하지 않는다. 요청 walltime과 GPU는 feature이며, 요청 walltime은 routing과 cap에도 쓰인다. GPU 조건부 uncertainty/safety margin 또는 GPU-weighted loss는 없다.',
      '',
      '최종 model 학습은 2025-03-31 08:00 UTC 이전 120일의 완료 1,288,805행이다. May 학습·calibration은 NO. q는 3월 24–30일 AEST의 기존 28 rolling window, 87,824행 positive residual에서 계산한 pooled empirical 90% 분위수다. 보정 sample 자체의 coverage가 88.379%이며 독립 final-state holdout이 아니다.',
      '',
      f"Pre-May GPU-positive 표본 {v['point_runtime_seconds']['sample_count']:,}개: raw underprediction {v['point_runtime_seconds']['underprediction_rate']:.6%}, effective(ceil 포함) underprediction {v['effective_runtime_seconds']['underprediction_rate']:.6%}. GPU-weighted raw underprediction {v['point_runtime_seconds']['requested_GPU_weighted_underprediction_rate']:.6%}.",
      f"더 직접적인 H100-standby pre-May subgroup은 {standby['point_runtime_seconds']['sample_count']:,}개이며 raw underprediction {standby['point_runtime_seconds']['underprediction_rate']:.6%}, 보정·올림 후 {standby['effective_runtime_seconds']['underprediction_rate']:.6%}, GPU-weighted 보정·올림 후 {standby['effective_runtime_seconds']['requested_GPU_weighted_underprediction_rate']:.6%}다. 따라서 pooled calibration이 해당 subgroup의 조건부 tail coverage를 보장했다고 해석할 수 없다.",
      '전체·GPU·H100·H100-standby의 MAE/medianAE/RMSE/bias/P90/P95/long-job/가중 지표 및 시간·GPU bucket은 validation JSON에 있다. Feeder critical-slot의 preMay 검증 자료는 없어 service-axis miss-rate proxy로 명시했다.',
      '',
      f"B1 critical slot: feeder gross {p['feeder_gross_load_kW']:.6f} kW, AIDC {p['total_AIDC_PCC_kW']:.6f} kW, B1-controllable incremental PCC {p['B1_controllable_load_kW']:.6f} kW. AIDC/feeder {p['AIDC_PENETRATION']:.4%}, flexible/AIDC {p['FLEXIBLE_AIDC_SHARE']:.4%}, controllable/feeder {p['CONTROLLABLE_FEEDER_PENETRATION']:.4%}.",
      '전체 day 비율은 96-slot 에너지 적분의 비율로 계산했다. Frozen domain은 temporal 616, spatial 679(그중 RUNNING migration 가능 63) UID다. Idle/host/cooling 전체를 flexible job에 임의 배분하지 않았다. 제어 가능한 부하 규모는 효과의 크기를 제한하는 요인이지만 sign 역전을 단독 설명하지 않는다.',
      '',
      f"기존 sw2 phase-A sensitivity × Actual PCC 변화는 ΔI≈{sensitivity['first_order_delta_I_A']:.12f} A, 기존 AC 관측은 +0.146241726480 A다. 차이 {sensitivity['linearization_residual_A']:.12f} A는 선형화 잔차로 보존한다. 하류 AIDC05/09/10/11/12는 약 0.138 A/kW, 상류는 약 0.00004–0.00063 A/kW다. 따라서 total GPU 감소보다 위치가 중요하며 모든 AIDC가 weak sensitivity라는 가설은 기각한다.",
      '',
      'Claim boundary: Planning 개선과 이 May-01 폐쇄 cohort의 workload/placement realization 차이는 주장할 수 있다. 새로운 predictor/robust scheduling 우월성, full-May 통계 유의성, 미래 도착 예측 효과는 주장하지 않는다.',
      '',
      '실행: optimization NO; predictor retraining NO; Actual-informed retuning NO; 31일 electrical regeneration NO; B2/B3 NO; full May NO. 재생성은 별도 승인 전 HOLD다. 원인 분석 결과로 frozen 정책·모델·q·계수·도메인을 수정하지 않았다.','']
    (out/'V40I_MAY01_WORKLOAD_FORENSIC_FINAL.md').write_text('\n'.join(lines),encoding='utf-8')
    (out/'V40I_POST_CUTOFF_WORKLOAD_MODELING_GAP.md').write_text(
      '# Post-cutoff workload modeling gap\n\nPlanning은 D-1 18:00 AEST에 알려진 RUNNING 254와 PENDING 1,395 UID만 포함한다. 이후 도착은 예측·대체 workload로 추가되지 않는다. Actual도 같은 frozen UID universe의 service를 비교하므로 future arrivals는 현재 역전의 직접 원인이 아니다.\n\nPOST_CUTOFF_ARRIVAL_CAUSE_OF_CURRENT_REVERSAL = NO.\n\n이는 실제 다음 날 모든 도착 workload를 포괄하는 운영 예측 검증이 아니다. 새 도착·GPU 규모·runtime·위치의 공동 불확실성은 현 실험에서 평가하지 않는다. 이번 작업에서 future-arrival predictor를 만들거나 이 May 결과를 이용해 보정하지 않았다.\n',encoding='utf-8')
    (out/'V40I_POST_FORENSIC_METHOD_RECOMMENDATIONS.md').write_text(
      '# 별도 method revision 후보 — 제안만\n\n아래는 구현·학습·선택하지 않은 비교안이다. May Actual은 학습·validation·model selection·margin calibration에 사용하지 않는다. 별도 승인 후 pre-May 데이터를 시간 순으로 training/calibration/untouched validation으로 나누고 현재 방법과 사전 정의한 지표로 비교해야 한다. May-01에서 관측한 수치로 hyperparameter나 q를 결정하지 않는다.\n\n'
      '| 후보 | 기대 역할 | 한계/비용 | 필요한 pre-May 자료 |\n|---|---|---|---|\n'
      '| Conditional runtime regression | 요청 GPU·walltime·tier별 point bias 분석 | point만으로 tail coverage 보장 없음 | 제출 feature, start/end, GPU/tier 충분 표본 |\n'
      '| Quantile runtime prediction | 상단 조건부 runtime 예측 | quantile 선택·calibration 별도 필요 | 독립 시간 validation과 long-job 표본 |\n'
      '| Conformal upper bound | 보정 split에서 upper residual 관리 | 시간 drift·조건부/GPU coverage 별도 검증 필요 | 분리된 calibration/validation, drift 기록 |\n'
      '| Survival model | 미완료 job과 censoring 포함 | censoring/event 의미와 runtime/remaining 구분 필요 | 각 cutoff의 at-risk 상태와 종료/검열 시각 |\n'
      '| Distributionally robust envelope | runtime 불확실성을 사전 scheduling에 반영 | ambiguity set·보수성 및 계산 비용 | pre-May 오차 분포와 사전 결정한 stress 평가 |\n'
      '| GPU-weighted asymmetric loss | underprediction의 GPU-service 비용 반영 | 평균 point 정확도/큰 job 편향 tradeoff | GPU별 runtime·pre-May 비용 정의 |\n'
      '| Explicit scheduling reserve | 사전 headroom으로 overlap 위험 완화 | 활용률·서비스 완료와 tradeoff | pre-May feeder/scheduler 공동 validation |\n\n'
      'RUNNING requested-minus-elapsed 규칙, PENDING predictor, q, migration penalty, objective hierarchy는 이번 V40I에서 변경하지 않았다. 위 후보의 우월성을 주장하지 않는다.\n',encoding='utf-8')


if __name__=='__main__':run(Path.cwd())
