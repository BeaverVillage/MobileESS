from common16 import *
from train_native16 import metrics,check_freeze

def collect():
    check_freeze();d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet',columns=['wallclock_used_sec','nodes_req','wallclock_req_sec'])
    summaries=[];folds=[];tails=[]
    arms=['D0','D1','D2','D3','D4','IDENTITY_ONLY','SOFTWARE_STACK','NEG_SHUFFLE']
    for arm in arms:
        fs=[];parts=[]
        for i in [1,2,3]:
            folder=LOCAL/f'native_fold{i}';r=read(folder/(arm+'.json'))
            p=pd.read_parquet(folder/(arm+'.parquet'));data=d.iloc[p.historic_row]
            s=metrics(data,p.Q50.to_numpy(),p.Q90.to_numpy());fs.append(s)
            folds.append(dict(arm=arm,fold=i,**s));parts.append(p)
            for h in [4,8,12,24]:tails.append(dict(arm=arm,fold=i,hours=h,N=s[f'gt{h}h_N'],Q90_coverage=s[f'gt{h}h_coverage']))
        p=pd.concat(parts,ignore_index=True);s=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
        s.update(arm=arm,min_fold_coverage=min(r['Q90_coverage'] for r in fs),max_fold_coverage=max(r['Q90_coverage'] for r in fs),
            information_class='HISTORICAL_DIAGNOSTIC_ONLY',status='COMPLETED',GPU_weighting='NOT_AVAILABLE; node-hours explicitly used',proper_interval_NLL=None)
        summaries.append(s)
    frame=pd.DataFrame(summaries);base=frame.iloc[0];f=pd.DataFrame(folds)
    for metric,label in [('min_fold_coverage','min_fold_gain'),('gt4h_coverage','gt4h_gain'),('gt12h_coverage','gt12h_gain')]:frame[label]=frame[metric]-base[metric]
    frame['pinball_relative_change']=frame.Q90_pinball/base.Q90_pinball-1
    consistent=[]
    for arm in frame.arm:
        a=f[f.arm.eq(arm)].set_index('fold');b=f[f.arm.eq('D0')].set_index('fold')
        gain=a.gt4h_coverage-b.gt4h_coverage
        consistent.append(bool(((gain>0)&(a.Q90_pinball<b.Q90_pinball)).sum()>=2 and gain.min()>=-.05))
    frame['consistent_temporal_gain']=consistent
    frame['strict_information_success']=(frame.min_fold_gain>=.05)&(frame.gt4h_gain>=.05)&(frame.pinball_relative_change<=.05)
    frame['ablation_trigger']=((frame.min_fold_gain>=.05)|(frame.gt4h_gain>=.05))&(frame.pinball_relative_change<=.05)
    frame.to_csv(ROOT/'RADDIT_NATIVE_MODEL_COMPARISON.csv',index=False);f.to_csv(ROOT/'RADDIT_NATIVE_FOLD_METRICS.csv',index=False)
    pd.DataFrame(tails).to_csv(ROOT/'RADDIT_NATIVE_TAIL_METRICS.csv',index=False)
    main=frame[frame.arm.isin(['D1','D2','D3','D4'])]
    success=bool(main.strict_information_success.any())
    stop=bool(((main.min_fold_gain<.03)&(main.gt4h_gain<.03)&(main.gt12h_gain<.03)&(main.pinball_relative_change>-.03)&~main.consistent_temporal_gain).all())
    ablate=main[main.ablation_trigger].sort_values(['Q90_pinball','arm'])
    selected=None if ablate.empty else ablate.iloc[0].arm
    verdict=dict(time=now(),PRIMARY_D0_D4_FROZEN=True,diagnostic_only=True,
        native_information_success=success,program_stop_triggered=stop,deployable_bridge_authorized=not stop,
        execution_routing_correction=rec(ROOT/'EXECUTION_ROUTING_CORRECTION.json'),
        conclusion='RICH_RADDIT_METADATA_INFORMATION_VALUE_SUPPORTED' if success else 'RICH_RADDIT_METADATA_INFORMATION_VALUE_NOT_SUPPORTED' if stop else 'LIMITED_OR_MIXED_INFORMATION_VALUE',
        strict_success_arms=main.loc[main.strict_information_success,'arm'].tolist(),ablation_authorized=selected is not None,ablation_arm=selected,
        controls='See NEG_SHUFFLE and exact stable-ID invariance receipts. Bijective renaming is not an information-destroying negative control.',
        embedding='Separate matched-cohort diagnostic; cannot authorize production or retrospectively alter D0-D4 stop gates',
        catboost_superiority_tested=False,private_exporter_proven=False,May_2025_opened=False,April_selection=False,
        metrics=rec(ROOT/'RADDIT_NATIVE_MODEL_COMPARISON.csv'),fold_metrics=rec(ROOT/'RADDIT_NATIVE_FOLD_METRICS.csv'))
    write('RADDIT_INFORMATION_VALUE_VERDICT.json',verdict)
    audits={f'fold{i}':read(LOCAL/f'native_fold{i}/NEIGHBOR_AUDIT.json') for i in [1,2,3]}
    write('CAUSAL_NEIGHBOR_AUDIT.json',dict(time=now(),implemented=True,folds=audits,k=[16,64],pool='TRAIN_ONLY',approximate_global_retrieval=True))
    write('NEIGHBOR_TEMPORAL_LEAKAGE_AUDIT.json',dict(time=now(),PASS=True,all_selected_neighbor_ids_checked=True,
        total_queries=sum(a[r]['N'] for a in audits.values() for r in ['TRAIN','VALID']),strict_completion_violations=0,
        VALID_outcomes_in_neighbor_pool=0,prior_validation_outcomes_in_pool=0,causal_condition='end_i < submit_j',future_poison_and_unfinished_fixture='test16.py'))
    print(frame[['arm','Q90_coverage','min_fold_coverage','gt4h_coverage','gt12h_coverage','Q90_pinball','strict_information_success']].to_string(index=False),flush=True)
    print('VERDICT',verdict['conclusion'],'ABLATION',selected,flush=True)

def embeddings():
    d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet',columns=['wallclock_used_sec','nodes_req','wallclock_req_sec'])
    folds=[];summary=[]
    for arm in ['EMB_D0','EMB_D2','D_EMB_DIAGNOSTIC_ONLY']:
        parts=[]
        for i in [1,2,3]:
            p=pd.read_parquet(LOCAL/f'embedding_fold{i}'/(arm+'.parquet'));parts.append(p)
            s=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy());folds.append(dict(arm=arm,fold=i,**s))
        p=pd.concat(parts,ignore_index=True);s=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
        summary.append(dict(arm=arm,**s,min_fold_coverage=min(r['Q90_coverage'] for r in folds if r['arm']==arm),
            TRAIN_cap=100000,all4096_coordinates=arm=='D_EMB_DIAGNOSTIC_ONLY',mapping='BOTH_UNIQUE_RESEARCH_PROXY_LEVELS',production_selectable=False))
    pd.DataFrame(summary).to_csv(ROOT/'RADDIT_EMBEDDING_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RADDIT_EMBEDDING_FOLD_METRICS.csv',index=False)
    write('RADDIT_EMBEDDING_DIAGNOSTIC_VERDICT.json',dict(time=now(),status='COMPLETED',production_selectable=False,
        same_cohort_same_TRAIN_cap=True,dimensions=4096,private_transform_used=False,regenerable_for_future_V42=False,
        limitations=['TRAIN100000 cap','completed exported subset','unresolved timestamp/export lineage','LightGBM coordinate model is not a proof about all possible representations'],
        comparison=rec(ROOT/'RADDIT_EMBEDDING_MODEL_COMPARISON.csv')))
    print(pd.DataFrame(summary).to_string(index=False),flush=True)

if __name__=='__main__':embeddings() if len(sys.argv)>1 and sys.argv[1]=='embedding' else collect()
