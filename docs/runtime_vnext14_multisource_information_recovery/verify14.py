"""Verify immutable inputs, exact baseline parity receipts, and honest fail-closed delivery."""
from common14 import *
import subprocess,re
from finalize14 import ARMS
from close_sources14 import STOP


def main():
    before=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')
    for r in before['files']:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
    assert len(before['files'])==1309
    # Original requested scientific manifests independently verified too.
    for name in before['prior_manifests']:
        p=REPO/name
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256'],r['relative']
    inv=pd.read_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',keep_default_na=False)
    dec=pd.read_csv(ROOT/'RAW_SOURCE_DECISION_MATRIX.csv',keep_default_na=False)
    assert inv.source_id.is_unique and inv.relative_path.is_unique and len(inv)==23601
    assert set(dec.source_id)==set(inv.source_id) and not dec.include_in_v14_ml.any()
    assert inv.source_category.str.match(r'^[A-H]\.').all()
    # This checks every inventoried entry without reading/hash-scanning all raw payloads.
    for _,r in inv.iterrows():
        st=Path('\\\\?\\'+str(RAW_A/r.relative_path)).lstat()
        assert st.st_size==r.size_bytes and st.st_mtime_ns==r.mtime_ns,r.relative_path
    assert read(ROOT/'RAW_INVENTORY_RECEIPT.json')['complete']
    join=read(ROOT/'RADDIT_KESTREL_JOIN_SUMMARY.json')
    assert join['original_archive_identity_verified_for_all_V13_jobs']
    assert join['RADDiT_ID_equals_zero_based_row_position']
    assert join['original_identity_hierarchy'][0]['common_keys']>0
    assert join['original_identity_hierarchy'][1]['common_keys']==0
    assert all(r['common_keys']==0 for r in join['V13_GPU_hierarchy'])
    ledger=pd.read_parquet(LOCAL/'RADDIT_KESTREL_JOIN_LEDGER.parquet')
    assert len(ledger)==621583 and not ledger.raddit_match.any()
    v13data=pd.read_parquet(V9/'.local/PREAPRIL_SOURCE.parquet',columns=['job_id'])
    assert set(ledger.v13_job_id.astype(str))==set(v13data.job_id.astype(str))
    projection=read(ROOT/'ORIGINAL_KESTREL_PROJECTION_AUDIT.json')
    assert not projection['postApril_members_opened'] and not projection['runtime_columns_decoded']
    for name in projection['permitted_members']:
        match=re.search(r'year=(\d+)/month=(\d+)/',name);assert (int(match[1]),int(match[2]))<(2025,4)
    base=read(ROOT/'V13_BASELINE_REPRODUCTION.json');assert base['PASS'] and base['no_fit']
    assert len(base['checks'])==10 and sum(r['VALID_N'] for r in base['checks'])==468072
    for r in base['checks']:
        src=r['saved_predictions'];assert sha(src['path'])==src['sha256']
        q=np.load(src['path'])['q'];assert hashlib.sha256(q.tobytes()).hexdigest()==r['prediction_sha256']
        assert r['all_VALID_quantiles_bit_identical'] and r['max_abs_error']==0
    comp=pd.read_csv(ROOT/'MODEL_COMPARISON.csv');assert comp.arm.tolist()==ARMS
    original=pd.read_csv(V13/'TOTAL_MODEL_COMPARISON.csv').set_index('arm')
    for a,b in [(ARMS[0],'EXPANDING_S0'),(ARMS[1],'EXPANDING_S4')]:
        row=comp[comp.arm.eq(a)].iloc[0]
        for key in ['N','Q90_coverage','min_fold_coverage','gt4h_coverage','gt12h_coverage','gt24h_coverage','Q90_pinball','proper_interval_NLL']:
            assert np.isclose(row[key],original.loc[b,key],rtol=1e-13,atol=0),(a,key)
    for name in ['MODEL_COMPARISON.csv','FOLD_METRICS.csv','LONG_TAIL_METRICS.csv','SHARPNESS_METRICS.csv','PROPER_SCORE_METRICS.csv']:
        table=pd.read_csv(ROOT/name);unrun=table[table.arm.isin(ARMS[2:])]
        assert not unrun.empty and unrun.status.eq(STOP).all() and not unrun.metrics_available.any()
        for key in ['Q90_coverage','Q90_pinball','proper_interval_NLL','eligible','min_fold_coverage','gt4h_coverage']:
            if key in unrun:assert unrun[key].isna().all(),(name,key)
    alignment=read(ROOT/'RADDIT_EMBEDDING_ALIGNMENT_AUDIT.json')
    assert alignment['total_embedding_rows']==1780972 and alignment['chunk_count']==45
    assert alignment['RADDIT_EMBEDDING_ROW_MAPPING_PROVEN'] is False
    assert alignment['RADDIT_EMBEDDING_AMBIGUOUS_ROWS'] is None and alignment['RADDIT_EMBEDDING_MISSING_ROWS'] is None
    assert alignment['vectors_decoded'] is False
    provenance=read(ROOT/'RADDIT_EMBEDDING_PROVENANCE_AUDIT.json')
    assert not provenance['RADDIT_EMBEDDING_OUTCOME_INPUT_FOUND'] and not provenance['RADDIT_NEW_JOB_SEMANTIC_CALLABLE']
    for r in provenance['LFS_payload_identity_verified']:assert r['payload']['sha256']==re.search(r'oid sha256:([0-9a-f]+)',Path(r['pointer']['path']).read_text()).group(1)
    verdict=read(ROOT/'FINAL_VERDICT.json')
    assert verdict['status']=='STOPPED_SOURCE_AUTHORITY_FAILURE' and verdict['SELECTED_V14_ARM']=='NONE'
    for key in ['TOTAL_RUNTIME_MODEL_VALIDATED','C1_ROLLING14_EVALUATED','STAGE_C_AUTHORIZED','REMAINING_MODEL_RUN',
                'REMAINING_RUNTIME_MODEL_VALIDATED','V42_RESEARCH_RUNTIME_PROVIDER_READY','STRICT_CAUSAL_RUNTIME_PROVIDER_READY',
                'REQUEST_VERSION_AUTHORITY_FOUND','APRIL_USED_FOR_SELECTION','APRIL_MODEL_CHANGED_AFTER_EVALUATION',
                'MAY_PAYLOAD_OPENED','MAY_USED_FOR_SELECTION','MAY_USED_FOR_EVALUATION','EAGLE_USED_AS_KESTREL_FEATURE']:
        assert verdict[key] is False,key
    assert verdict['NEW_ML_FITS']==verdict['SEMANTIC_REDUCER_FITS']==0
    contract=read(ROOT/'FEATURE_CONTRACT.json');assert contract['preprocessing_fits']==0
    assert not read(ROOT/'AUTHORIZED_FEATURE_FAMILIES.json')['ML_AUTHORIZED']
    assert not (ROOT/'FOLD_MODELS').exists() and not (ROOT/'RUNTIME_PROVIDER').exists()
    for r in read(ROOT/'FINAL_SELECTION_FREEZE.json')['files']:assert sha(r['path'])==r['sha256']
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    portion=request.split('36. REQUIRED V14 ARTIFACTS',1)[1].split('37. REQUIRED FINAL KOREAN',1)[0]
    required=set(re.findall(r'(?m)^([A-Z][A-Z0-9_]*\.(?:json|csv|md))\s*$',portion))
    for name in required-{'SOURCE_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json','DELIVERY_MANIFEST.json','VERIFICATION.json'}:
        assert (ROOT/name).is_file(),name
    report=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(n) for n in re.findall(r'(?m)^## (\d+)\.',report)]==list(range(1,51))
    tests=subprocess.run([sys.executable,'-B',str(ROOT/'test14.py')],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert tests.returncode==0,tests.stdout+tests.stderr
    logs=read(ROOT/'EXECUTION_LOG_PRESERVATION.json')
    for r in logs['logs']:assert sha(r['original']['path'])==r['original']['sha256']==sha(r['archived']['path'])
    # Exact original fold files are reused, never regenerated or split differently.
    for r in read(V13/'SOURCE_MANIFEST.json')['roles']:
        assert sha(r['path'])==r['sha256'],r['path']
    fold_inputs=[record(V9/'.local'/f'fold{i}'/(role+'.parquet')) for i in range(1,6) for role in ['TRAIN','CAL','VALID']]
    selected=read(ROOT/'SELECTED_FORENSIC_INPUTS.json')['files']+join['inputs']
    docs=read(ROOT/'LOCAL_AUTHORITY_SEARCH.json')['inspected_files']
    unique={r['path']:r for r in selected+docs}
    for r in unique.values():assert sha(r['path'])==r['sha256'],r['path']
    state_record=read(V13/'CURRENT_STATE_CAUSALITY_AUDIT.json')['feature_file']
    assert sha(state_record['path'])==state_record['sha256']
    write('SOURCE_MANIFEST.json',dict(time=now(),base=BASE,user_request=record(ROOT/'USER_REQUEST.txt'),
        preregistration=record(ROOT/'PREREGISTRATION.json'),prior_evidence=record(ROOT/'BASE_PRESERVATION_RECEIPT.json'),
        raw_and_document_inputs=list(unique.values()),original_fold_files=fold_inputs,
        V13_state_features=state_record,V13_baseline_quantiles=[r['saved_predictions'] for r in base['checks']],
        new_code=[record(p) for p in sorted(ROOT.glob('*.py'))],
        hash_scope='Selected scientific inputs and inspected authority documents only; initial raw inventory did not hash multi-GB files.',
        May_record_payload_decoded=False,raw_data_modified=False))
    local=[record(p) for p in sorted(LOCAL.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    write('LOCAL_EVIDENCE_MANIFEST.json',dict(time=now(),retained=True,git_included=False,files=local))
    for r in local:assert sha(r['path'])==r['sha256']
    changed=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO,text=True).splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=REPO,text=True).splitlines()
    assert all(p.startswith('docs/runtime_vnext14_multisource_information_recovery/') for p in changed+untracked)
    write('VERIFICATION.json',dict(time=now(),PASS=True,scope='Negative source-authority forensic delivery; not V14 predictive validation',
        prior_tracked_files_byte_identical=len(before['files']),prior_manifests_verified=len(before['prior_manifests']),
        raw_inventory_entries_size_and_mtime_unchanged=len(inv),raw_inventory_complete=True,
        selected_raw_and_document_hashes_verified=len(unique),local_evidence_files_verified=len(local),
        baseline_all_VALID_predictions_bit_identical=True,baseline_prediction_rows=468072,
        original_temporal_fold_files_reused=True,original_archive_identity_verified_for_all_V13_jobs=True,
        exact_GPU_join_matches=0,no_approximate_identity_join=True,no_challenger_metrics_fabricated=True,
        unknown_alignment_counts_left_null=True,no_new_fit=True,no_reducer_fit=True,unit_test_output=tests.stdout+tests.stderr,
        Korean_questions_answered=50,required_artifacts=sorted(required),V14_only_changes=True,
        Stage_C_authorized=False,provider_created=False,April_evaluated=False,May_payload_opened=False,
        external_search_executed=False,local_gap_summary_scope='metadata/documentation closure, not Stage G model-failure experiment'))
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ['.local','__pycache__']) or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scientific_status=verdict['status'],scope='V14 only',files=files))
    for name in required:assert (ROOT/name).is_file(),name
    for r in files:assert sha(ROOT/r['relative'])==r['sha256']
    print('V14_VERIFICATION_PASS',len(before['files']),'prior;',len(inv),'raw entries;',len(files),'delivery files',flush=True)


if __name__=='__main__':main()
