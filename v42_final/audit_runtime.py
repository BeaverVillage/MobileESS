"""Reproduce only the user-selected stored model. No import of training code."""
from .common import *
import subprocess


def main():
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=RUNTIME,text=True).strip()==RUNTIME_HEAD,'PR95_HEAD')
    sources=[]
    spec=read(PR95/'CROSS_VERSION_PREREGISTRATION.json')
    arm=next(x for x in spec['items'] if x['Model']==MODEL)
    authority=read(PR95/'CROSS_VERSION_SOURCE_MANIFEST.json')['files']
    expected={str(Path(r['path']).resolve()):r['sha256'] for r in authority}
    def source(p):
        row=rec(p);require(row['sha256']==expected[str(Path(p).resolve())],'PR95_SOURCE_SHA')
        sources.append(row);return row
    source(V10/'TEMPORAL_FOLD_CONTRACT.json')
    contract=read(V10/'TEMPORAL_FOLD_CONTRACT.json');parts=[];rows=[];states=[]
    for i,item in enumerate(arm['files'],1):
        p=Path(item['path']);source(p)
        vpath=V9/f'.local/fold{i}/VALID.parquet';source(vpath)
        f=pd.read_parquet(vpath,columns=['job_id','event','runtime_seconds','submit_time'])
        membership=hashlib.sha256(('\n'.join(sorted(f.job_id.astype(str)))+'\n').encode()).hexdigest()
        require(membership==contract['folds'][i-1]['membership']['VALID'],'VALID_MEMBERSHIP')
        with np.load(p,allow_pickle=False) as z:q=z['quantiles']
        require(q.shape==(len(f),5),'STORED_QUANTILE_AXIS')
        m=f.event.to_numpy(bool);y=f.loc[m,'runtime_seconds'].to_numpy(float);q50=q[m,0]
        require(np.isfinite(q50).all() and (q50>=0).all(),'Q50_SECONDS')
        rows.append(dict(fold=i,N=len(y),Q50_MAE_hours=float(abs(y-q50).mean()/3600),Q50_coverage=float((y<=q50).mean()),Q50_time_ratio=float(q50.sum()/y.sum())))
        parts.append((y,q50))
        sp=V10/f'CALIBRATION_STATES/fold{i}_ISOTONIC_ROLLING14.json';s=read(sp);keys=sorted(s['states'])
        sources.append(rec(sp));co=contract['folds'][i-1]
        state_times=[pd.Timestamp(k) for k in keys]
        states.append(dict(fold=i,model_fit_cutoff=co['TRAIN_cutoff'],CAL_from=co['CAL_submit_from'],CAL_end=co['CAL_end_before'],
            first_persisted_calibration_state=keys[0],last_persisted_calibration_state=keys[-1],
            states_available_during_own_CAL=sum(pd.Timestamp(co['CAL_submit_from'])<=t<pd.Timestamp(co['CAL_end_before']) for t in state_times),
            max_completion_used_last=s['states'][keys[-1]]['max_completion_used'],state_file=rec(sp)))
        require(all(pd.Timestamp(v['max_completion_used'])<pd.Timestamp(v['day']) and v['FUTURE_CALIBRATION_EVENT_READS']==0 and v['FUTURE_CALIBRATION_RESIDUAL_READS']==0 for v in s['states'].values()),'FROZEN_ROLLING_CAUSALITY')
    y=np.concatenate([r[0] for r in parts]);q=np.concatenate([r[1] for r in parts])
    actual=dict(N=len(y),Q50_MAE_hours=float(abs(y-q).mean()/3600),Q50_coverage=float((y<=q).mean()),Q50_time_ratio=float(q.sum()/y.sum()),
        min_fold_Q50_coverage=min(r['Q50_coverage'] for r in rows),max_fold_Q50_coverage=max(r['Q50_coverage'] for r in rows),GT12H_Q50_coverage=float((y[y>43200]<=q[y>43200]).mean()))
    table=pd.read_csv(PR95/'CROSS_VERSION_Q50_COMPARISON.csv').set_index('Model').loc[MODEL]
    for k,v in actual.items():require(abs(v-float(table[k]))<1e-10,'PR95_METRIC_DRIFT:'+k)
    require(actual['N']==230237,'COMMON_POPULATION')
    final=read(V10/'RUNTIME_PROVIDER/runtime_contract.json')
    audit=dict(PASS=True,selected_architecture=MODEL,metrics=actual,folds=rows,
        metrics_scope='Exact PR95 stored five-fold population; not a score for a newly assembled deployment bundle',
        no_training=True,no_new_calibration=True,May_labels_read=False,VALID_used_to_choose_reserve=False,
        existing_callable_bundle_family=final['family'],existing_callable_bundle_mode=final['mode'],
        callable_bundle_matches_selected_provider=False,fold_state_availability=states,
        calibration_replay_issue='All matching per-fold rolling states start at VALID, after that fold CAL closes; using those maps in its CAL replay leaks later calibration information.',
        latest_matched_frozen_pair=dict(fold=5,model=str(V10/'FOLD_MODELS/fold5/G1'),preprocessing=str(V9/'FOLD_5_PREPROCESSING.json'),
            state_file=str(V10/'CALIBRATION_STATES/fold5_ISOTONIC_ROLLING14.json'),state_key=states[-1]['last_persisted_calibration_state']),
        source_files=sources)
    dump('V42_RUNTIME_PROVIDER_SOURCE_AUDIT.json',audit);csv('RUNTIME_Q50_REPRODUCTION.csv',rows+[dict(fold='POOLED',**actual)])
    dump('V42_RUNTIME_PROVIDER_FREEZE.json',dict(frozen_at=now(),provider=MODEL,nominal_quantile='Q50',unit='seconds',
        architecture_selection_authority='Explicit current user decision',PR94_SELECTED_RUNTIME_MODEL_preserved='NONE',
        PR95_PRIMARY_NOMINAL_RUNTIME_CANDIDATE_preserved='NONE',retroactive_evidence_rewrite=False,
        reason='Near-tied MAE; closer pooled median calibration/time ratio, stronger long-runtime and temporal calibration than logistic rolling14',
        intrinsic_metrics=actual,coverage_reference=.5,GPU_weighted_intrinsic_metrics=False,
        deployment_pair_status='PENDING_EXACT_FROZEN_PAIR_BINDING',training_allowed=False,calibration_refit_allowed=False,
        Q90_hard_duration=False,Q50_Q90_alpha_interface=False))
    print(json.dumps(dict(metrics=actual,matching_final_bundle=False,own_CAL_states=[r['states_available_during_own_CAL'] for r in states]),indent=2))


if __name__=='__main__':main()
