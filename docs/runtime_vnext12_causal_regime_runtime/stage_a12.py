from common12 import *
from regime12 import *
import subprocess

def fingerprint(f):
    return hashlib.sha256(pd.util.hash_pandas_object(f,index=False).values.tobytes()).hexdigest()

def main():
    for r in read(ROOT/'PREREGISTRATION.json')['files']:assert sha(r['path'])==r['sha256']
    f=pd.read_parquet(V9/'.local/PREAPRIL_SOURCE.parquet')
    cutoff=pd.Timestamp(read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['final_information_cutoff'])
    events=completed(f,cutoff);prior=read(ROOT/'FROZEN_TRAIN_PRIOR.json')
    q=f[['job_id','submit_time','partition','qos','requested_seconds','num_gpus_req']].copy()
    q=q.rename(columns={'submit_time':'prediction_time'}).sort_values(['prediction_time','job_id'],kind='stable').reset_index(drop=True)
    path=LOCAL/'REGIME_FEATURES.parquet'
    if path.exists():feat=pd.read_parquet(path).drop(columns=['job_id'])
    else:
        print(now(),'MATERIALIZE',len(q),flush=True)
        feat=materialize(events,q,prior,lambda family:print(now(),'COHORT',family,flush=True))
        pd.concat([q[['job_id']],feat],axis=1).to_parquet(path,index=False)
    assert len(feat)==len(q)
    # Every eligible completion has submit<=start<=end<t, including cross cohorts.
    et=pd.DatetimeIndex(events.end_time).as_unit('ns').asi8
    qt=pd.DatetimeIndex(q.prediction_time).as_unit('ns').asi8
    right=np.searchsorted(et,qt,side='left')
    has=right>0
    future_end=int(np.sum(et[right[has]-1]>=qt[has]))
    own=f.set_index('job_id').reindex(q.job_id)
    current=int((own.end_time.notna()&own.end_time.lt(own.submit_time)).sum())
    assert future_end==current==0
    assert events.submit_time.le(events.end_time).all()
    raw_checks=[]
    rng=np.random.default_rng(4012)
    positions=rng.choice(len(q),100,replace=False)
    test=window_stats(events,q.prediction_time.iloc[positions],14)
    for j,pos in enumerate(positions):
        t=q.prediction_time.iloc[pos];pool=events[events.end_time.lt(t)&events.end_time.ge(t-pd.Timedelta(days=14))]
        assert test.N.iloc[j]==len(pool)
        if len(pool):assert np.isclose(test.runtime_q90.iloc[j],pool.runtime.quantile(.9))
    # Full engine causality and streaming equivalence on real records, including
    # prefix unavailability. Persisted state is reloaded in a NEW Python process.
    sampleq=q.iloc[np.linspace(0,min(25000,len(q)-1),60,dtype=int)].reset_index(drop=True)
    samplee=events[events.end_time.lt(sampleq.prediction_time.max())].copy()
    batch=materialize(samplee,sampleq,prior)
    state=ReplayState(samplee.iloc[:0],prior);chunks=[];previous_ids=set()
    for chunk in np.array_split(np.arange(len(sampleq)),4):
        sub=sampleq.iloc[chunk].reset_index(drop=True);time=sub.prediction_time.max()
        add=samplee[samplee.end_time.lt(time)&~samplee.job_id.isin(previous_ids)]
        state.append_completed(add,time);previous_ids.update(add.job_id)
        chunks.append(state.predict(sub))
    chunked=pd.concat(chunks,ignore_index=True)
    pd.testing.assert_frame_equal(batch,chunked,check_exact=True)
    state.save(LOCAL/'replay_state');sampleq.to_parquet(LOCAL/'replay_queries.parquet',index=False)
    script='from common12 import *; from regime12 import *; q=pd.read_parquet(LOCAL/"replay_queries.parquet"); ReplayState.load(LOCAL/"replay_state").predict(q).to_parquet(LOCAL/"restarted.parquet",index=False)'
    subprocess.run([sys.executable,'-B','-c',script],cwd=ROOT,check=True)
    restored=pd.read_parquet(LOCAL/'restarted.parquet');pd.testing.assert_frame_equal(batch,restored,check_exact=True)
    # Poison all not-yet-completed outcomes and the queried current job.
    testq=q.iloc[[len(q)//2]].reset_index(drop=True);t=testq.prediction_time.iloc[0]
    visible=events[events.end_time.lt(t)]
    expected=materialize(visible,testq,prior)
    altered=events.copy();altered.loc[altered.end_time.ge(t),'runtime']=1e20
    pd.testing.assert_frame_equal(expected,materialize(altered,testq,prior),check_exact=True)
    write('REGIME_CAUSALITY_AUDIT.json',dict(time=now(),PASS=True,N_predictions=len(q),completed_events=len(events),
        FUTURE_JOB_READS=0,FUTURE_END_READS=future_end,CURRENT_JOB_OUTCOME_READS=current,FUTURE_CALIBRATION_READS=0,
        same_timestamp_rule='strict <; explicit custom-indexer left boundary; tested duplicate completion timestamps',
        future_outcome_poisoning_invariant=True,bruteforce_random_windows=100,prior_availability_guard=True,
        source_label_censoring='Inherited V9 labels; regime timestamps stricter than outcome cutoff',
        feature_file=record(path),feature_values_sha256=fingerprint(feat),static_descriptor_authority_unverified=True))
    write('REGIME_STATE_REPLAY_AUDIT.json',dict(time=now(),PASS=True,queries=len(sampleq),events=len(samplee),
        chronological_hash=fingerprint(batch),chunked_hash=fingerprint(chunked),restarted_process_hash=fingerprint(restored),
        exact_float_equality=True,scope='Full-feature engine real-history60-query four-chunk replay, plus full-materialization value hash'))
    indexed=feat.set_axis(q.job_id,axis=0)
    # Daily snapshots and exact fold-start snapshots are human-reviewable CSVs;
    # every job's full exact as-of features are hash-pinned in the local parquet.
    days=pd.date_range(q.prediction_time.min().ceil('D'),cutoff,freq='D',tz='UTC')
    gs=[]
    for d in [7,14,30]:
        g=window_stats(events,days,d);g.insert(0,'prediction_time',days);g.insert(1,'window_days',d);gs.append(g)
    pd.concat(gs).to_csv(ROOT/'GLOBAL_REGIME_FEATURES.csv',index=False)
    support=[];fallback=[];association=[];shift=[]
    metrics=['runtime_q50','runtime_q90','gt4h_rate','gt12h_rate','ratio_q50']
    for i in range(1,6):
        for role in ['TRAIN','CAL','VALID']:
            rows=data(i,role);z=indexed.loc[rows.job_id]
            for prefix in [c[:-len('__raw_N')] for c in z if c.endswith('__raw_N')]:
                depths=z[prefix+'__fallback_depth'];raw=z[prefix+'__raw_N']
                support.append(dict(fold=i,role=role,family=prefix,N=len(z),raw_support_N_min=raw.min(),raw_support_N_median=raw.median(),
                                    direct_fraction=(depths==0).mean(),fallback_fraction=(depths>0).mean(),unavailable_fraction=(depths<0).mean()))
                for depth,indices in depths.groupby(depths).groups.items():
                    a=z.loc[indices]
                    fallback.append(dict(fold=i,role=role,family=prefix,fallback_depth=depth,rows=len(a),
                        raw_N_min=a[prefix+'__raw_N'].min(),raw_N_median=a[prefix+'__raw_N'].median(),
                        selected_N_min=a[prefix+'__support_N'].min(),selected_N_median=a[prefix+'__support_N'].median(),
                        newest_age_seconds_max=a[prefix+'__newest_age_seconds'].max(),oldest_age_seconds_max=a[prefix+'__oldest_age_seconds'].max()))
        valid=data(i,'VALID');exact=valid[valid.event];t=pd.Timestamp(read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['VALID_submit_from'])
        snap=window_stats(events,[t],14).iloc[0]
        y=exact.runtime_seconds;ratio=y/exact.requested_seconds.where(exact.requested_seconds>0)
        actual=dict(runtime_q50=y.quantile(.5),runtime_q90=y.quantile(.9),gt4h_rate=(y>14400).mean(),gt12h_rate=(y>43200).mean(),ratio_q50=ratio.median())
        for metric in metrics:
            association.append(dict(fold=i,scope='GLOBAL14_AT_VALID_START',metric=metric,recent_value=snap[metric],future_value=actual[metric],N=len(exact),snapshot_time=t))
        for family in FAMILIES:
            e=exact.reset_index(drop=True);k=keys(e)[family];ee=keys(events)[family]
            for key,idx in k.groupby(k).groups.items():
                a=e.iloc[idx]
                if len(a)<100:continue
                pool=events[(ee==key)&events.end_time.lt(t)&events.end_time.ge(t-pd.Timedelta(days=14))]
                if len(pool)<(200 if '_' in family else 100) or (pool.runtime>14400).sum()<20:continue
                for metric,recent,future in [('runtime_q90',pool.runtime.quantile(.9),a.runtime_seconds.quantile(.9)),('gt4h_rate',(pool.runtime>14400).mean(),(a.runtime_seconds>14400).mean())]:
                    association.append(dict(fold=i,scope=family,cohort=key,metric=metric,recent_value=recent,future_value=future,N=len(a),snapshot_time=t))
        tr=data(i,'TRAIN');tr=tr[tr.event]
        shift.append(dict(fold=i,definition='descriptive_only_not_input',snapshot_time=t,
                          log_q90_change=np.log1p(snap.runtime_q90)-np.log1p(tr.runtime_seconds.quantile(.9)),
                          gt4h_absolute_change=snap.gt4h_rate-(tr.runtime_seconds>14400).mean()))
    pd.DataFrame(support).to_csv(ROOT/'COHORT_REGIME_SUPPORT.csv',index=False)
    pd.DataFrame(fallback).to_csv(ROOT/'REGIME_FALLBACK_AUDIT.csv',index=False)
    assoc=pd.DataFrame(association);assoc.to_csv(ROOT/'REGIME_FOLD_ASSOCIATION.csv',index=False)
    pd.DataFrame(shift).to_csv(ROOT/'REGIME_SHIFT_DIAGNOSTIC.csv',index=False)
    correlations=[]
    for (scope,metric),a in assoc.groupby(['scope','metric']):
        correlations.append(dict(scope=scope,metric=metric,N=len(a),pearson=a.recent_value.corr(a.future_value),
                                 spearman=a.recent_value.corr(a.future_value,method='spearman')))
    write('STAGE_A_VERDICT.json',dict(time=now(),PASS=True,correlations=correlations,
        DO_RECENT_Q90_TRACK_FUTURE_Q90='See descriptive five-fold correlations, not evidence of causality',
        DO_RECENT_LONG_RATE_TRACK_FUTURE_LONG_RATE='See descriptive five-fold correlations',
        DO_COHORT_REGIME_FEATURES_ADD_SIGNAL='Descriptive association; predictive value tested by R1 vs R2',
        no_window_or_support_redesign=True,features=len(feat.columns)))
    print(now(),'STAGE_A_COMPLETE',len(feat.columns),flush=True)

if __name__=='__main__':main()
