"""Freeze chronological membership and censored bounds before any model comparison."""
from common9 import *
import pandas as pd,numpy as np,shutil
v8path()
from features8 import engineer

def normalize(raw):
    r=raw.copy();f=pd.DataFrame({'job_id':r.id.astype(str)})
    for c in ['submit_time','start_time','end_time']:f[c]=r[c]
    f['requested_seconds']=r.requested_seconds
    for src,dst in [('gpus_requested','num_gpus_req'),('nodes_req','num_nodes_req'),('processors_req','num_cores_req'),('array_pos','array_index'),('account_hash','account'),('qos','qos'),('partition','partition')]:f[dst]=r[src]
    # Same v8/v6 memory numeric mapping; no claim of reconstructed total-memory scope.
    parts=r.memory_req.astype('string').str.extract(r'^([0-9.]+)([KMGTPkmgtp]?)[nN]?$',expand=True)
    f['requested_memory_mib']=pd.to_numeric(parts[0],errors='coerce')*parts[1].str.upper().map({'':1,'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3})
    return f

def observation(f,cutoff):
    c=pd.Timestamp(cutoff);g=f[f.submit_time.lt(c)].copy();started=g.start_time.notna()&g.start_time.lt(c)&g.start_time.ge(g.submit_time)
    known=g.end_time.notna()&g.end_time.le(c);valid_exact=known&g.end_time.ge(g.start_time)
    # Filter visibility first; never subtract a future endpoint for censored jobs.
    g['event']=started&valid_exact;g['censored']=started&~known
    g['duration_lower']=np.nan
    exact=g.event;cen=g.censored
    g.loc[exact,'duration_lower']=(g.loc[exact,'end_time']-g.loc[exact,'start_time']).dt.total_seconds()
    g.loc[cen,'duration_lower']=(c-g.loc[cen,'start_time']).dt.total_seconds()
    g['duration_upper']=g.duration_lower.where(g.event,np.inf)
    g['runtime_seconds']=g.duration_lower.where(g.event,np.nan)
    g.loc[~g.event,'end_time']=pd.NaT
    g['observation_cutoff']=c
    audit=dict(submitted=len(g),started=int(started.sum()),exact=int(exact.sum()),censored=int(cen.sum()),pending_or_future_start=int((~started).sum()),invalid_ended=int((started&known&~valid_exact).sum()),zero_exact=int((exact&g.duration_lower.eq(0)).sum()),FUTURE_END_USED_BEFORE_FOLD_CUTOFF=0)
    return g,audit

def main():
    LOCAL.mkdir(exist_ok=True);preserve=[]
    for folder in [V6,V7,V8]:
        m=read(folder/'DELIVERY_MANIFEST.json');assert all(sha(folder/r['relative'])==r['sha256'] for r in m['files'])
        preserve.append(dict(folder=folder.name,files=len(m['files']),manifest=record(folder/'DELIVERY_MANIFEST.json')))
    write('BASE_PRESERVATION_RECEIPT.json',dict(base=BASE,prior=preserve,mode='Byte hashes only; no April payload decoding',time=now()))
    cache=V7/'.local/GPU_PREAPRIL.parquet';assert sha(cache)==read(V7/'PREPARATION_RECEIPT.json')['gpu_local_data']['sha256']
    raw=pd.read_parquet(cache);f=normalize(raw);assert f.submit_time.lt(pd.Timestamp('2025-04-01T00Z')).all();f.to_parquet(LOCAL/'PREAPRIL_SOURCE.parquet',index=False)
    bounds=['2024-11-01T00Z','2024-12-01T00Z','2025-01-01T00Z','2025-02-01T00Z','2025-03-01T00Z','2025-03-31T08Z']
    queue_days=['2024-11-05','2024-12-03','2025-01-07','2025-02-04','2025-03-04']
    folds=[];support=[];membership=[];censor=[];col=read(V8/'RUNTIME_PROVIDER/model/model.json')['columns']
    for i,(begin,end) in enumerate(zip(bounds[:-1],bounds[1:]),1):
        begin=pd.Timestamp(begin);end=pd.Timestamp(end);fitcut=begin-pd.Timedelta(days=14);folder=LOCAL/f'fold{i}';folder.mkdir()
        observed,ca=observation(f,fitcut);tr=observed[observed.event|observed.censored].reset_index(drop=True)
        atval,_=observation(f,begin);cal=atval[atval.submit_time.ge(fitcut)].reset_index(drop=True)
        atlast,va=observation(f,end);val=atlast[atlast.submit_time.ge(begin)].reset_index(drop=True)
        maps={}
        for c in ['qos','partition','account']:
            counts=tr[c].astype('string').fillna('__MISSING__').value_counts();keep=counts[counts.ge(20 if c=='account' else 1)].index;maps[c]={v:k+1 for k,v in enumerate(sorted(keep))}
        for role,g in [('TRAIN',tr),('CAL',cal),('VALID',val)]:
            g.to_parquet(folder/f'{role}.parquet',index=False);membership.append(pd.DataFrame({'fold':i,'role':role,'job_id':g.job_id}))
            support.append(dict(fold=i,role=role,N=len(g),exact=int(g.event.sum()),censored=int(g.censored.sum()),no_runtime_information=int((~(g.event|g.censored)).sum()),
              observed_long_gt4h=int((g.event&g.duration_lower.gt(14400)).sum()),observed_gt12h=int((g.event&g.duration_lower.gt(43200)).sum()),high_GPU=int(g.num_gpus_req.ge(16).sum()),
              membership=ids(g),max_exact_end=str(g.end_time.max()),observation_cutoff=str(fitcut if role=='TRAIN' else begin if role=='CAL' else end)))
        entry=dict(fold=i,TRAIN_cutoff=fitcut.isoformat(),CAL_submit_from=fitcut.isoformat(),CAL_end_before=begin.isoformat(),VALID_submit_from=begin.isoformat(),VALID_end= end.isoformat(),queue_day=queue_days[i-1],
          maps=maps,membership={r:ids(g) for r,g in [('TRAIN',tr),('CAL',cal),('VALID',val)]},expanded_history='all available positive GPU trace history; no random sampling')
        folds.append(entry);censor.append(dict(fold=i,TRAIN=ca,VALID=va));write(f'FOLD_{i}_PREPROCESSING.json',dict(columns=col,categorical_mappings=maps,unknown_code=0,fit_cutoff=fitcut.isoformat()))
    # Final model fit reserves the same14-day calibration interval before logical cutoff.
    final_end=pd.Timestamp(bounds[-1]);final_cut=final_end-pd.Timedelta(days=14);observed,ca=observation(f,final_cut);tr=observed[observed.event|observed.censored].reset_index(drop=True)
    obs,_=observation(f,final_end);cal=obs[obs.submit_time.ge(final_cut)].reset_index(drop=True);folder=LOCAL/'final';folder.mkdir();tr.to_parquet(folder/'TRAIN.parquet',index=False);cal.to_parquet(folder/'CAL.parquet',index=False)
    maps={}
    for c in ['qos','partition','account']:
        counts=tr[c].astype('string').fillna('__MISSING__').value_counts();maps[c]={v:k+1 for k,v in enumerate(sorted(counts[counts.ge(20 if c=='account' else 1)].index))}
    write('FINAL_PREPROCESSING.json',dict(columns=col,categorical_mappings=maps,unknown_code=0,fit_cutoff=final_cut.isoformat()))
    first=pd.read_parquet(LOCAL/'fold1/TRAIN.parquet');maximum=float(first.duration_lower.max());tail_days=int(np.ceil(maximum/86400));tail_days=max(8,tail_days)
    edges=sorted(set([0,15,60,300]+list(range(900,14401,900))+list(range(18000,86401,3600))+list(range(108000,604801,21600))+list(range(691200,(tail_days+1)*86400,86400))))
    write('HAZARD_BIN_CONTRACT.json',dict(time=now(),edges_seconds=edges,tail_endpoint=edges[-1],earliest_TRAIN_max_observed_or_censored=maximum,
      bins_frozen_before_predictive_results=True,early_subbins='15/60/300 seconds within first15min slot preserve observed short executions; then15min to4h,1h to24h,6h to7days,1day tail',
      within_bin='Piecewise constant hazard rate inferred from bin event probability; log survival linear within bin',
      censored_partial_interval='Exclude partially observed last interval; never call it survival through full interval',
      tail='Beyond endpoint use final learned interval hazard rate; nonzero hazard clipped[1e-7,1-1e-7] for finite log-survival. No walltime cap.',
      zero_runtime='Exact0 termination assigned to first interval; acknowledged D1 coarsening; no PENDING as0'))
    write('AFT_MODEL_CONTRACT.json',dict(time=now(),distributions=['normal','logistic','extreme'],scales=[1.0,1.5],rounds=300,max_depth=6,learning_rate=.05,min_child_weight=100,reg_lambda=2,max_bin=127,
      objective='survival:aft',tree_method='hist',categoricals='frozen TRAIN codes, XGBoost feature_types categorical for account/qos/partition',
      time_variable='U=T+1 seconds, exact invertible shift handles observed0; prediction T=max(U-1,0), no queue',
      exact_bounds='runtime lower=upper=T; library lower=upper=T+1',censored_bounds='runtime lower=elapsed;upper=inf; library lower=elapsed+1;upper=inf',
      distribution_formulas='logU=mu+sigma Z; normal ZPhi, logistic ZCDFsigmoid, extreme ZCDF1-exp(-exp z); output margin mu, never mistake exp(mu) for all quantiles',
      source='https://xgboost.readthedocs.io/en/release_3.0.0/tutorials/aft_survival_analysis.html'))
    write('FEATURE_CONTRACT.json',dict(version='runtime-vnext9-trace-v1',provenance_mode='Kestrel_trace_proxy',columns=col,RESEARCH_TRACE_FEATURE_COUNT=len(col),STRICT_CAUSAL_FEATURE_COUNT=0,
      REQUEST_VERSION_AUTHORITY_FOUND=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,source=record(V8/'RUNTIME_PROVIDER/feature_contract.json'),transform=record(V8/'features8.py'),
      identity_policy='V8 evidence retained: account only; no user/script/name/submitline/workdir/jobtype or clock',maps='Each fold TRAIN only; FINAL_PREPROCESSING frozen independently from final TRAIN',unknown_code=0,
      predictor_forbidden=['start_time','end_time','runtime_seconds','state','queue_wait','actual_long_status','job_id'],hazard_age='Hypothetical interval age when predicting distribution; observed elapsed at remaining inference. No actual end or future duration.'))
    write('TEMPORAL_FOLD_CONTRACT.json',dict(time=now(),fold_count=5,folds=folds,final_fit_cutoff=final_cut.isoformat(),final_information_cutoff=final_end.isoformat(),final_TRAIN_membership=ids(tr),final_CAL_membership=ids(cal),
      final_TRAIN_N=len(tr),final_CAL_N=len(cal),time_boundary_fixed_before_training=True,
      baseline_causality='B0 March14 fit unavailable in earlier folds; Bconst/V8 incorporate later March calibration/selection. Report frozen baselines on all folds as noncausal retrospective references; selection pinball gate uses causal D3 all folds and B0 only submissions>=2025-03-14T08Z. No V8/Bconst historical results enter selection.',
      censoring='end<=cutoff exact; started<cutoff without observed end right-censored; not started no duration information',APRIL_STATUS='EXPOSED_REGRESSION_ONLY',MAY_OPENED=False))
    pd.concat(membership,ignore_index=True).to_csv(ROOT/'TEMPORAL_FOLD_MEMBERSHIP.csv',index=False);pd.DataFrame(support).to_csv(ROOT/'TEMPORAL_FOLD_SUPPORT.csv',index=False)
    write('RIGHT_CENSORING_AUDIT.json',dict(folds=censor,final_TRAIN=ca,RIGHT_CENSORING_SUPPORTED=True,FUTURE_END_USED_BEFORE_FOLD_CUTOFF=0,
      raw_source=record(cache),future_end_masked_before_subtraction=True,pending_not_zero=True,ingestion_time_limitation='Event-time as-of experiment; public trace arrival latency/request version not verified.',
      requeue_limit='Single recorded execution interval; no invented original attempt reconstruction.'))
    old=pd.read_parquet(V8/'PREAPRIL_JOBS.parquet');pair=old[old.label_valid].merge(f,on='job_id',suffixes=('_old','_raw'));y=(pair.end_time_raw-pair.start_time_raw).dt.total_seconds();err=float(np.abs(y-pair.runtime_seconds).max());assert err==0
    write('RUNTIME_TARGET_AUTHORITY_AUDIT.json',dict(TARGET_RUNTIME_AUTHORITY_PASS=True,TARGET_IS_EXECUTION_RUNTIME=True,QUEUE_WAIT_INCLUDED_IN_TARGET=False,REQUESTED_WALLTIME_USED_AS_LABEL=False,
      exact_v8_normalized_max_abs_seconds=err,verified_N=len(pair),target='end-start observed execution occupancy; failed/cancelled terminal intervals inherited; not CPU busy time or cumulative unobserved requeues',source=record(V8/'RUNTIME_TARGET_AUTHORITY_AUDIT.json')))
    write('EXPERIMENT_PROTOCOL.json',dict(time=now(),D1=dict(n_estimators=300,learning_rate=.05,num_leaves=31,max_depth=8,min_child_samples=200,reg_lambda=2,max_bin=127,random_state=4009,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True),
      D3='LightGBM log1p Q50/Q70/Q80/Q90/Q95 with same D1 tree settings and exact TRAIN only. Comparative reference, not full-distribution provider.',
      D2_grid='3 noise distributions x2 fixed scales; same300trees/depth6. One designated D2normal1.0 exact-only ablation isolates censoring contribution; no large search.',
      calibration_modes=['NONE','STATIC14','ROLLING14','ROLLING28'],calibration='One additive signed residual-order-statistic algorithm, ceil(.9*(n+1)); min200 matured out-of-training residuals otherwise0; rolling uses only end<UTC prediction day and end>=day-window. Base model never refit.',
      full_distribution_calibration='Tcal=max(0,Tbase+delta); conditional survival and quantiles computed from this same shifted distribution, including mass at0',
      gates=dict(pooled_coverage=[.88,.92],min_fold_coverage=.80,max_fold_coverage=.97,max_coverage_std=.06,long_gt4h_min=.85,per_fold_long_min_N=100,pinball_relative_to_causal_D3_max=1.02,pinball_relative_to_time_eligible_B0_max=1.02,reservation_to_W0_max=.8,queue_start_ltH_at_least_W0=True,capacity_violations=0,high_GPU_min_N=100,high_GPU_coverage_min=.85),
      selection='Reject safety/stability/long/pinball/reservation/queue gate failures first. Among eligible D1/D2 select lowest pooled rounded reservation, then pinball. If none pass, preserve one diagnostic D1/D2 by fewest failed gates then reservation; no promotion.',
      queue=dict(days=queue_days,capacity_GPU=780,slot_seconds=900,horizon_slots=96,drain_slots=1920,background='Empty common research background; same-day arriving jobs only; NOT historical full V42 state reconstruction',forecast='same submit/tier/id ordering, aggregate-capacity first-fit reservation ledger',causal='Separate current-slot dispatch with actual completion observer and retained overruns, no future end to dispatcher; missing duration stays occupied to drain horizon',validity='positive integer GPU,nodes; GPU<=4nodes and GPU<=780; walltimepositive',gate='forecast in-day starts>=W0 on each fold; all causal stress capacity violations0; horizon exhaustion fails'),
      distribution_scores='Quantile calibration .5/.7/.8/.9/.95; 72h truncated Brier integral on exact mature evaluation cohort and known-status censored observations; censor-aware grid survival likelihood for D1/D2. Brier observed-only labelled conditional/administratively censored, not unbiased IPCW population IBS; no unsupported CRPS claim.',
      benchmark='Selected final TRAIN CPU1/CPU4/explicit GPU identity with actual logs; before April. CPU inference mandatory. Backend recommendation only; selected CPU4 bytes retained.',
      conditional_remaining='logS(e+r)-logS(e); solve S(T)=S(e)*(1-q), return T-e >=0; SAME distribution, no separate remaining fit',
      remaining_gates=dict(Q90_coverage=[.88,.92],Q50_MAE_vs_Bconst_max=1.,long_running_coverage_min=.85),
      April_pristine=False,APRIL_STATUS='EXPOSED_REGRESSION_ONLY',April_not_used_for_any_selection=True,May_payload_allowed=False))
    write('TEMPORAL_FOLD_PREREGISTRATION.json',dict(time=now(),files=[record(ROOT/x) for x in ['TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_MEMBERSHIP.csv','TEMPORAL_FOLD_SUPPORT.csv','HAZARD_BIN_CONTRACT.json','AFT_MODEL_CONTRACT.json','FEATURE_CONTRACT.json','EXPERIMENT_PROTOCOL.json']],before_any_model_comparison=True))
    print('FROZEN_5_FOLDS',pd.DataFrame(support).to_string(index=False),'D1_BINS',len(edges)-1,flush=True)
if __name__=='__main__':main()
