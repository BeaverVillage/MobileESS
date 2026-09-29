"""User-requested cross-version extension; existing TOTAL quantile arrays only."""
from common import *
import sys
FOLDERS={6:'runtime_vnext6_callable_total',8:'runtime_vnext8_trace_feature_total',9:'runtime_vnext9_distributional_runtime',10:'runtime_vnext10_tail_calibrated_hazard',11:'runtime_vnext11_total_remaining',12:'runtime_vnext12_causal_regime_runtime',13:'runtime_vnext13_current_workload_state',15:'runtime_vnext15_reproducible_semantic',16:'runtime_vnext16_raddit_rich_metadata'}
def folder(v):return REPO/'docs'/FOLDERS[v]

def register():
    assert not (ROOT/'CROSS_VERSION_PREREGISTRATION.json').exists()
    items=[];inventory=[]
    for p in sorted((folder(9)/'.local').glob('*_evaluation.parquet')):
        arm=p.name.removesuffix('_evaluation.parquet')
        if arm=='W0':continue
        version=6 if arm=='Bconst' else 8 if arm=='V8' else 9
        scope='NONCAUSAL_RETROSPECTIVE_REFERENCE' if arm in ['B0','Bconst','V8'] else 'FROZEN_CAUSAL_TOTAL'
        items.append(dict(Model=f'V{version}::{arm}',version=version,arm=arm,kind='v9_parquet',files=[rec(p)],scope=scope))
    for v in [10,11,12,13,15,16]:
        parent=folder(v)/'.local';prefix='runtime_fold' if v>=15 else 'fold'
        allnames=set()
        for i in range(1,6):
            candidates=(parent/f'{prefix}{i}').glob('*.npz' if v in [10,11] else '*.parquet')
            for p in candidates:
                n=p.name
                if v==10 and not (n.startswith('T1_') or n.endswith('_calibrated.npz')):continue
                if v==11 and n=='TAIL.npz':continue # Conditional tail component, not full TOTAL predictor.
                if v==15 and n not in ['R1.parquet','R2.parquet']:continue
                if v==16 and n not in ['R16-A.parquet','R16-B.parquet','R16-C.parquet']:continue
                allnames.add(n)
        for name in sorted(allnames):
            paths=[parent/f'{prefix}{i}'/name for i in range(1,6)]
            available=[i for i,p in enumerate(paths,1) if p.exists()]
            item=dict(Model=f'V{v}::{Path(name).stem}',version=v,arm=Path(name).stem,kind='positional_npz' if v in [10,11] else 'id_parquet',scope='FROZEN_CAUSAL_TOTAL',available_folds=available,files=[rec(p) for p in paths if p.exists()])
            if len(available)!=5:
                inventory.append(dict(version=v,Model=item['Model'],status='NOT_POOLED_INCOMPLETE_FROZEN_FOLDS',detail=','.join(map(str,available))))
            else:items.append(item)
    early={1:('runtime_vnext_causal_tail','Different historical issue/state cohort with May exposure; no exact common pre-April TOTAL arrays established; payload not opened'),2:('runtime_vnext2_q95_operational_bound','Inherited Q90/Q95 operational bound study; different state/issue population, May exposure; no new Q50 payload opened'),3:('runtime_vnext3_adaptive_running_bound','Adaptive Running upper-bound selector, inherited Pending; not a new common TOTAL Q50'),4:('runtime_vnext4_gpu_censored_running','Running remaining-runtime model study; not common TOTAL Q50'),5:('runtime_vnext5_r2_causal_calibration','Running Q90 residual calibration, not new common TOTAL Q50'),7:('runtime_vnext7_feature_authority_recovery','Forensic source-authority audit; no new trained model'),14:('runtime_vnext14_multisource_information_recovery','J0/J1 reproduce V13; J2-J5 NOT_RUN source-authority failure; R1/R2 forensic recovery adds no TOTAL model')}
    metadata=[]
    for v,(name,reason) in early.items():
        p=REPO/'docs'/name/'README.md';metadata.append(rec(p));inventory.append(dict(version=v,Model=f'V{v}',status='NOT_A_NEW_COMPARABLE_TOTAL_Q50',detail=reason))
    for v in [6,8,9,10,11,12,13,15,16]:inventory.append(dict(version=v,Model=f'V{v}',status='FROZEN_COMMON_POPULATION_AUDIT',detail=f'{sum(x["version"]==v for x in items)} frozen variants; v6/v8 only existing V9 retrospective replay, not fresh model inference'))
    for v in [10,11]:
        for name in ['TEMPORAL_FOLD_CONTRACT.json',f'common{v}.py', 'evaluate_calibration10.py' if v==10 else 'train_total11.py']:
            metadata.append(rec(folder(v)/name))
    metadata.append(rec(folder(9)/'BASELINE_REPRODUCTION.json'));metadata.append(rec(folder(9)/'TEMPORAL_FOLD_CONTRACT.json'))
    write('CROSS_VERSION_PREREGISTRATION.json',dict(time=now(),user_extension='v13이나 다른 16개의 버전 모델의 Q50도 살펴봐.',
        prior_exposure='Original six-arm Q50 metrics already evaluated. This addendum freezes the expanded inventory before computing expanded Q50 results.',
        scope='Inventory V1-V16; compute every readily stored, complete five-fold TOTAL prediction variant in V9-V16, including completed ablations; V6/V8 existing retrospective references separately. No missing fold values fabricated.',
        metric_contract='Identical original Q50 arithmetic, strata, <= convention and zero handling. No GPU, inference, training, CAL, April/May payload or new population.',
        positional_identity='V10/V11 NPZ arrays carry no IDs; require original producer row-order contract, inherited full VALID membership hash and exact array length. Join only via original V9 VALID order then event mask; verify identical PR94 mature IDs/labels. No arbitrary sorting of NPZ rows.',
        decision_scope='Exploratory comparison only; no new automatic winner or numerical gate; original six-arm table and PR94 scalar NONE remain unchanged. Report duplicate Q50 arrays and retrospective leakage explicitly.',
        items=items,metadata_sources=metadata))
    csv('RUNTIME_VERSION_INVENTORY.csv',inventory)
    write('CROSS_VERSION_PREREGISTRATION_HASH.json',rec(ROOT/'CROSS_VERSION_PREREGISTRATION.json'))
    print('EXPANSION_FROZEN',len(items),'complete variants',flush=True)

def evaluate():
    assert sha(ROOT/'CROSS_VERSION_PREREGISTRATION.json')==read(ROOT/'CROSS_VERSION_PREREGISTRATION_HASH.json')['sha256']
    spec=read(ROOT/'CROSS_VERSION_PREREGISTRATION.json');authority={};sources=spec['metadata_sources'][:]
    for i in range(1,6):
        p=folder(9)/'.local'/f'fold{i}/VALID.parquet';sources.append(rec(p));v=pd.read_parquet(p);v.job_id=v.job_id.astype(str)
        core=pd.read_parquet(PR94/'.local'/f'{PRIMARY}_fold{i}_VALID.parquet').set_index('job_id')
        assert set(v.loc[v.event,'job_id'])==set(core.index)
        for vv in [10,11]:assert ids(v)==read(folder(vv)/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['membership']['VALID']
        authority[i]=(v,core)
    summary=[];foldrows=[];buckets=[];tails=[];ratio_rows=[];receipts=[];duplicates={}
    for item in spec['items']:
        for r in item['files']:assert sha(r['path'])==r['sha256'];sources.append(r)
        parts=[];fs=[];finger=hashlib.sha256()
        combined=pd.read_parquet(item['files'][0]['path']) if item['kind']=='v9_parquet' else None
        for i in range(1,6):
            v,core=authority[i]
            if item['kind']=='v9_parquet':
                p=combined[combined.fold==i].rename(columns={'y':'runtime_seconds'})
            elif item['kind']=='id_parquet':p=pd.read_parquet(item['files'][i-1]['path'])
            else:
                q=np.load(item['files'][i-1]['path'])['quantiles'];assert q.shape==(len(v),5 if item['version']==10 else 2)
                p=v.loc[v.event,['job_id','runtime_seconds','submit_time']].copy();p['q50']=q[v.event,0];p['q90']=q[v.event,3 if item['version']==10 else 1]
            p=p.copy();p.job_id=p.job_id.astype(str);assert not p.job_id.duplicated().any() and set(p.job_id)==set(core.index)
            p=p.set_index('job_id').loc[core.index]
            np.testing.assert_array_equal(p.runtime_seconds,core.runtime_seconds)
            if 'submit_time' in p:np.testing.assert_array_equal(p.submit_time,core.submit_time)
            p=p[['runtime_seconds','q50','q90']].copy();p['fold']=i
            assert np.isfinite(p).all().all() and (p.q50>=0).all() and (p.q90>=p.q50).all()
            s=dict(Model=item['Model'],version=item['version'],scope=item['scope'],fold=i,**metrics(p),GT12H_Q50_coverage=metrics(p[p.runtime_seconds>43200])['Q50_coverage'])
            fs.append(s);foldrows.append(s);parts.append(p);finger.update(p.q50.to_numpy(dtype='<f8').tobytes())
            receipts.append(dict(Model=item['Model'],fold=i,N=len(p),membership=ids(p.reset_index()),same_labels=True,row_order_authority='Inherited original VALID array order, masked by event then exact ID join' if item['kind']=='positional_npz' else 'Exact stored job ID join'))
        p=pd.concat(parts);m=metrics(p);rr=ratios(p);assert m['N']==230237 and m['zero_runtime_N']==1290
        digest=finger.hexdigest();duplicate=duplicates.get(digest);duplicates.setdefault(digest,item['Model'])
        row=dict(Model=item['Model'],version=item['version'],scope=item['scope'],**m,Q50_per_job_ratio_median=rr['median'],min_fold_Q50_coverage=min(s['Q50_coverage'] for s in fs),max_fold_Q50_coverage=max(s['Q50_coverage'] for s in fs),fold_coverage_std=float(np.std([s['Q50_coverage'] for s in fs])),Q50_array_sha256=digest,same_Q50_as=duplicate,
            GT12H_Raw_Q90_coverage=metrics(p[p.runtime_seconds>43200])['Raw_Q90_coverage'])
        for h in [4,12,24]:row[f'GT{h}H_Q50_coverage']=metrics(p[p.runtime_seconds>h*3600])['Q50_coverage']
        summary.append(row)
        for fold,z in [('POOLED',p)]+[(i,p[p.fold==i]) for i in range(1,6)]:
            ratio_rows.append(dict(Model=item['Model'],fold=fold,**ratios(z)))
            for name,lo,hi in BUCKETS:buckets.append(dict(Model=item['Model'],fold=fold,bucket=name,**metrics(z[(z.runtime_seconds>lo)&(z.runtime_seconds<=hi)])))
            buckets.append(dict(Model=item['Model'],fold=fold,bucket='EXACT_ZERO_DIAGNOSTIC',**metrics(z[z.runtime_seconds==0])))
            for h in [4,12,24]:tails.append(dict(Model=item['Model'],fold=fold,threshold_hours=h,**metrics(z[z.runtime_seconds>h*3600])))
        print('AUDITED',item['Model'],flush=True)
    csv('CROSS_VERSION_Q50_COMPARISON.csv',summary);csv('CROSS_VERSION_Q50_FOLDS.csv',foldrows);csv('CROSS_VERSION_Q50_BUCKETS.csv',buckets);csv('CROSS_VERSION_Q50_TAILS.csv',tails);csv('CROSS_VERSION_Q50_RATIOS.csv',ratio_rows)
    write('CROSS_VERSION_POPULATION_RECHECK.json',dict(PASS=True,N=230237,variants=len(summary),candidate_folds=receipts,unique_Q50_arrays=len(duplicates),no_missing_fold_imputation=True))
    write('CROSS_VERSION_SOURCE_MANIFEST.json',dict(time=now(),files=list({r['path']:r for r in sources}.values())))
    print('DONE',len(summary),'variants,',len(duplicates),'unique Q50 arrays',flush=True)
if __name__=='__main__':
    if sys.argv[1]=='register':register()
    elif sys.argv[1]=='evaluate':evaluate()
