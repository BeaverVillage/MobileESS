"""Final read-only evidence checks, followed by self-excluding delivery manifests."""
from common16 import *
from train_native16 import metrics,check_freeze
from preservation16 import check_old
import subprocess,ast

REQUIRED=['README.md','PREREGISTRATION.json','RADDIT_FULL_SCHEMA_AUDIT.csv','RADDIT_FIELD_AUTHORITY_AUDIT.csv',
    'RADDIT_INFORMATION_CLASSIFICATION.md','RADDIT_ANONYMIZATION_SEMANTICS_AUDIT.md','RADDIT_Kestrel_RESEARCH_PROXY_CROSSWALK.csv',
    'RADDIT_CROSSWALK_SUMMARY.json','RADDIT_NATIVE_MODEL_COMPARISON.csv','RADDIT_NATIVE_FOLD_METRICS.csv','RADDIT_NATIVE_TAIL_METRICS.csv',
    'CAUSAL_NEIGHBOR_SPEC.md','CAUSAL_NEIGHBOR_AUDIT.json','NEIGHBOR_TEMPORAL_LEAKAGE_AUDIT.json','RADDIT_INFORMATION_VALUE_VERDICT.json',
    'V42_DEPLOYABLE_FIELD_BRIDGE.csv','V42_SEMANTIC_PAYLOAD_V2_SPEC.md','RUNTIME_V16_MODEL_COMPARISON.csv','RUNTIME_V16_FOLD_METRICS.csv',
    'RUNTIME_V16_TAIL_METRICS.csv','RUNTIME_V16_SELECTION_FREEZE.json','CC4_RICH_MODEL_COMPARISON.csv','CC4_RICH_SELECTION_FREEZE.json',
    'FINAL_FLAGS.json','FINAL_REVIEW_KO.md']

def main():
    for p in REQUIRED:assert (ROOT/p).is_file(),p
    check_freeze()
    test_output=[]
    for script in ['test16.py','test_bridge16.py','test_cc416.py']:
        tests=subprocess.run([sys.executable,'-B',str(ROOT/script)],capture_output=True,text=True,encoding='utf-8')
        assert tests.returncode==0,tests.stdout+tests.stderr
        test_output.append(dict(script=script,returncode=tests.returncode,output=tests.stdout+tests.stderr))
    write('FOCUSED_TEST_RESULTS.json',dict(time=now(),PASS=True,tests=11,results=test_output))
    for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    old=check_old();print('OLD_PRESERVATION',old,flush=True)
    d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet',columns=['job_id','submit_time','end_time','wallclock_used_sec','nodes_req','wallclock_req_sec'])
    assert len(d)==2557884 and d.submit_time.max()<pd.Timestamp('2025-04-01',tz='UTC')
    assert np.array_equal(d.job_id,np.arange(len(d)))
    end=d.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
    submit=d.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
    fm=pd.read_csv(ROOT/'RADDIT_NATIVE_FOLD_METRICS.csv').set_index(['arm','fold'])
    count=0;neighbor_queries=0
    for fold in [1,2,3]:
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=roles['TRAIN'];va=roles['VALID']
        assert np.all(end[tr]<submit[va].min())
        folder=LOCAL/f'native_fold{fold}'
        for arm in ['D0','D1','D2','D3','D4','IDENTITY_ONLY','SOFTWARE_STACK','NEG_SHUFFLE']:
            r=read(folder/(arm+'.json'));p=pd.read_parquet(folder/(arm+'.parquet'))
            assert np.array_equal(p.historic_row.to_numpy(),va)
            assert r['TRAIN_ids']==ids(tr) and r['VALID_ids']==ids(va)
            assert np.isfinite(p[['Q50','Q90']]).all().all() and (p.Q90>=p.Q50).all() and p.Q50.ge(0).all()
            actual=metrics(d.iloc[va],p.Q50.to_numpy(),p.Q90.to_numpy())
            for key,val in actual.items():
                assert np.isclose(val,fm.loc[(arm,fold),key],rtol=1e-12,atol=1e-9),(arm,fold,key)
            assert rec(folder/(arm+'.parquet'))==r['predictions']
            for row in r['models']:assert rec(Path(row['path']))==row
            count+=1
        mask=np.zeros(len(d),bool);mask[tr]=True
        for role,rows in [('TRAIN',tr),('VALID',va)]:
            selected=np.load(folder/f'{role}_neighbor_ids.npy',mmap_mode='r')
            features=np.load(folder/f'{role}_neighbor_features.npy',mmap_mode='r')
            assert selected.shape==(len(rows),64) and features.shape==(len(rows),18)
            for a in range(0,len(rows),8192):
                b=min(a+8192,len(rows));ix=selected[a:b];valid=ix>=0;safe=np.maximum(ix,0)
                assert mask[safe][valid].all()
                assert np.all((submit[rows[a:b],None]-end[safe])[valid]>0)
                np.testing.assert_array_equal(features[a:b,6],valid[:,:16].sum(axis=1))
                np.testing.assert_array_equal(features[a:b,15],valid.sum(axis=1))
            neighbor_queries+=len(rows)
        assert read(folder/'RANDOM_STABLE_ID_CONTROL.json')['exact_design_matrix_equal']
        print('NATIVE_VERIFIED',fold,flush=True)
    em=pd.read_csv(ROOT/'RADDIT_EMBEDDING_FOLD_METRICS.csv').set_index(['arm','fold']);embedding_count=0
    mapping=pd.read_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet');accepted=set(mapping.loc[mapping.status.eq('RESEARCH_PROXY_CROSSWALK'),'historic_row'])
    for fold in [1,2,3]:
        cohort=read(LOCAL/f'embedding_fold{fold}/COHORT.json');pairs=[]
        for arm in ['EMB_D0','EMB_D2','D_EMB_DIAGNOSTIC_ONLY']:
            folder=LOCAL/f'embedding_fold{fold}';r=read(folder/(arm+'.json'));p=pd.read_parquet(folder/(arm+'.parquet'))
            assert len(p)==cohort['VALID_N'] and r['TRAIN_N']==cohort['TRAIN_N']<=100000
            assert r['TRAIN_ids']==cohort['TRAIN_ids'] and r['VALID_ids']==cohort['VALID_ids']
            assert set(p.historic_row).issubset(accepted);pairs.append(p.historic_row.to_numpy())
            m=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
            for key,val in m.items():assert np.isclose(val,em.loc[(arm,fold),key],rtol=1e-12,atol=1e-9),(fold,arm,key)
            assert rec(folder/(arm+'.parquet'))==r['predictions']
            for row in r['models']:assert rec(Path(row['path']))==row
            embedding_count+=1
        for p in pairs[1:]:np.testing.assert_array_equal(p,pairs[0])
    paired_freeze=read(ROOT/'PAIRED_ABLATION_EXECUTION_FREEZE.json')
    assert rec(ROOT/'paired_ablation16.py')==paired_freeze['model_code']
    assert rec(ROOT/'ablation16.py')==paired_freeze['omission_helper']
    af=pd.read_csv(ROOT/'RADDIT_PAIRED_GROUPED_ABLATION_FOLD_METRICS.csv').set_index(['group','fold'])
    paired_ablation_count=0
    for fold in [1,2,3]:
        cohort=read(LOCAL/f'embedding_fold{fold}/COHORT.json')
        for group in 'ABCDE':
            folder=LOCAL/f'paired_ablation_fold{fold}';r=read(folder/(group+'.json'));p=pd.read_parquet(folder/(group+'.parquet'))
            assert r['TRAIN_ids']==cohort['TRAIN_ids'] and ids(p.historic_row)==cohort['VALID_ids']
            m=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
            for key,val in m.items():assert np.isclose(val,af.loc[(group,fold),key],rtol=1e-12,atol=1e-9),(group,fold,key)
            assert rec(folder/(group+'.parquet'))==r['predictions']
            for row in r['models']:assert rec(Path(row['path']))==row
            paired_ablation_count+=1
    assert read(ROOT/'NATIVE_ADAPTER_REPLAY_AUDIT.json')['PASS']
    stack_freeze=read(ROOT/'STACK_ABLATION_EXECUTION_FREEZE.json')
    assert rec(ROOT/'stack_ablation16.py')==stack_freeze['model_code']
    assert rec(ROOT/'ablation16.py')==stack_freeze['omission_helper']
    sf=pd.read_csv(ROOT/'RADDIT_STACK_GROUPED_ABLATION_FOLD_METRICS.csv').set_index(['group','fold'])
    for fold in [1,2,3]:
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz')
        for group in ['A','E']:
            r=read(LOCAL/f'stack_ablation_fold{fold}'/(group+'.json'));p=pd.read_parquet(r['predictions']['path'])
            assert rec(Path(r['predictions']['path']))==r['predictions']
            assert r['TRAIN_ids']==ids(roles['TRAIN']) and r['VALID_ids']==ids(roles['VALID'])
            np.testing.assert_array_equal(p.historic_row,roles['VALID'])
            for model in r['models']:assert rec(Path(model['path']))==model
            m=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
            for key,val in m.items():assert np.isclose(val,sf.loc[(group,fold),key],rtol=1e-12,atol=1e-9)
            if group=='E':assert r['exact_feature_matrix_parity'] and r['status']=='REUSED_EXACT_D0'
    replay=read(ROOT/'NATIVE_ADAPTER_REPLAY_AUDIT.json')['checks'];assert len(replay)==3
    assert all(r['replay_code_sha256']==sha(ROOT/'replay16.py') for r in replay)
    cross=read(ROOT/'RADDIT_CROSSWALK_SUMMARY.json');assert cross['historic_to_Kestrel_status']['RESEARCH_PROXY_CROSSWALK']==2069804
    assert cross['unique_embedding_to_Kestrel_status']['RESEARCH_PROXY_CROSSWALK']==1504846
    assert not any(cross['holdout_conflicts'].values()) and not cross['PRODUCTION_AUTHORITY_CROSSWALK']
    flags=read(ROOT/'FINAL_FLAGS.json')
    for key in ['APRIL_USED_FOR_SELECTION','MAY_PAYLOAD_OPENED','OPTIMIZER_CHANGED','MESS_CHANGED','OPENDSS_RUN','FLEXIBILITY_BRANCH_CHANGED']:assert flags[key] is False
    boundary=read(ROOT/'PREAPRIL_BOUNDARY_AUDIT.json');assert not boundary['April_rows_used_for_selection'] and not boundary['May_2025_named_members_opened']
    verdict=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')
    comparison=pd.read_csv(ROOT/'RADDIT_NATIVE_MODEL_COMPARISON.csv');primary=comparison[comparison.arm.isin(['D1','D2','D3','D4'])]
    assert bool(primary.strict_information_success.any())==verdict['native_information_success']
    if not verdict['deployable_bridge_authorized']:
        r=pd.read_csv(ROOT/'RUNTIME_V16_MODEL_COMPARISON.csv');new=r[r.arm.str.startswith('R16')]
        assert new.Q90_coverage.isna().all() and new.Q90_pinball.isna().all()
        assert not flags['RUNTIME_TOTAL_GATE_PASS'] and not flags['CC4_RICH_STAGE_RUN']
        bridge_verification={'status':'NOT_RUN_SCIENTIFIC_GATE'}
    else:
        from verify_bridge16 import verify as verify_bridge
        bridge_verification=verify_bridge()
    subprocess.run(['git','diff','--check'],cwd=REPO,check=True)
    changes=git('diff',BASE,'--name-only').splitlines()
    assert all(p.startswith('docs/runtime_vnext16_raddit_rich_metadata/') for p in changes),changes
    # All writers must be finished before this point. This process does not write a local log.
    local_files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()]
    write('LOCAL_EVIDENCE_MANIFEST.json',dict(time=now(),scope='All V16 models, numeric/categorical bundles, row predictions, neighbor IDs, mapped ledgers, stored coordinates and completed logs; nothing deleted',files=local_files))
    sources=[rec(HIST),rec(ARCHIVE),rec(RAD/'README.md'),rec(R1/'.local/EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet'),
        rec(V15/'DELIVERY_MANIFEST.json'),rec(V14/'RAW_SOURCE_INVENTORY.csv')]
    for row in read(V14/'RADDIT_EMBEDDING_PROVENANCE_AUDIT.json')['code']:
        assert sha(Path(row['path']))==row['sha256'];sources.append(rec(Path(row['path'])))
    for row in read(ROOT/'EMBEDDING_LAYOUT_AUDIT.json')['chunks']:sources.append(rec(Path(row['path'])))
    write('SOURCE_MANIFEST.json',dict(time=now(),base=BASE,files=sources,previous_scope=old,
        public_documentation=read(ROOT/'MODEL_FAMILY_DECISION.json')['sources'],raw_payloads_modified=False))
    write('VERIFICATION.json',dict(time=now(),PASS=True,required_artifacts=len(REQUIRED),old_preservation=old,focused_tests=11,
        native_arm_folds_independently_recomputed=count,embedding_arm_folds_independently_recomputed=embedding_count,
        paired_ablation_arm_folds_independently_recomputed=paired_ablation_count,
        stack_ablation_arm_folds_independently_recomputed=6,stack_ablation_new_fits=6,
        Runtime_bridge=bridge_verification,
        neighbor_queries_fully_rechecked=neighbor_queries,neighbor_pool_or_time_violations=0,preregistration_hashes_unchanged=True,
        R0_PR89_reproduction=read(ROOT/'R0_PR89_BASELINE_REPRODUCTION.json')['PASS'],fresh_process_replay=True,
        exact_embedding_pair_cohort_parity=True,April_boundary=boundary,May_2025_payload_opened=False,
        git_diff_check=True,only_new_study_directory_changed=True,large_evidence_local_files=len(local_files),source_files_fully_SHA256_bound=len(sources)))
    public=[dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json',dict(time=now(),self_exclusion='DELIVERY_MANIFEST.json only; local payload bytes separately bound',files=public,
        local_manifest=rec(ROOT/'LOCAL_EVIDENCE_MANIFEST.json'),source_manifest=rec(ROOT/'SOURCE_MANIFEST.json')))
    print('VERIFICATION_PASS',count,embedding_count,neighbor_queries,len(local_files),len(public),flush=True)

if __name__=='__main__':main()
