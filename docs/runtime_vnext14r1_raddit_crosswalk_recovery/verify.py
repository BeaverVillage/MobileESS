from common import *
import csv, sys
before=read(ROOT/'V14_BASE_VERIFICATION.json');checks={}
for r in before['files']:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
checks['prior_tracked_scientific_files_unchanged']=len(before['files'])
checks['prior_delivery_manifests_verified']=len(before['manifests'])
raw_count=0
with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
        assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p)
        raw_count+=1
checks['raw_size_mtime_unchanged']=raw_count
calls=read(ROOT/'NEW_JOB_SEMANTIC_CALLABILITY_AUDIT.json')
assert sha(calls['source']['path'])==calls['source']['sha256']
checks['inspected_V42_contract_unchanged']=True
oldlocal=read(V14/'LOCAL_EVIDENCE_MANIFEST.json');local_verified=0
for r in oldlocal['files']:
    p=Path(r['path']) if 'path' in r else V14/r['relative']
    assert sha(p)==r['sha256'],str(p);local_verified+=1
checks['V14_local_evidence_hashes_reverified']=local_verified
a=read(ROOT/'EMBEDDING_EXACT_AUDIT_DETAIL.json');schema=read(ROOT/'EMBEDDING_SCHEMA_AUDIT.json')
assert schema['embedding_rows']==1780972 and schema['historic_rows']==2557884
for s in a['stats']:
    assert s['unique_1to1']+s['ambiguous_embedding_rows']+s['unmatched_embedding_rows']==1780972
    assert s['matched_historic_rows']+s['unmatched_historic_rows']==2557884
    assert s['consistent_1to1_rows']+s['contradictory_1to1_rows']==s['unique_1to1']
    assert s['contradictory_1to1_rows']==0
checks['exact_key_population_conservation']=True
meta=pd.read_parquet(LOCAL/'EMBEDDING_SHARED_METADATA.parquet',columns=['submit_time','start_time','end_time'])
assert (meta.to_numpy()<pd.Timestamp('2025-04-01').as_unit('us').value).all()
assert (meta.to_numpy()!=np.iinfo(np.int64).min).all()
checks['embedding_all_shared_timestamps_preApril_and_nonnull']=True
order=read(ROOT/'EMBEDDING_ORDER_AUDIT.json');assert order['matched_key_multiplicity_identical']
assert order['total_pair_inversions_unique_raw_candidates']>=order['adjacent_inversions']
checks['order_and_matched_key_multiplicities_verified']=True
assert read(ROOT/'EMBEDDING_FRESH_PROCESS_REPLAY.json')['pass_replay'];checks['fresh_process_replay']=True
f=read(ROOT/'FINAL_VERDICT.json');assert f['NEW_ML_FITS']==0
for k in ['EMBEDDING_TO_RADDIT_MAPPING_PROVEN','RADDIT_TO_KESTREL_MAPPING_PROVEN','END_TO_END_CROSSWALK_PROVEN','NEXT_SEMANTIC_RUNTIME_ML_AUTHORIZED','NEW_JOB_SEMANTIC_INPUT_AVAILABLE','NEW_JOB_EMBEDDING_PIPELINE_REPRODUCIBLE','APRIL_RUNTIME_EVALUATED','MAY_PAYLOAD_OPENED','V42_CHANGED','CC4_CHANGED','MESS_CHANGED','OPTIMIZER_CHANGED','OPENDSS_EXECUTED','APPROXIMATE_MATCHING_USED','FUZZY_MATCHING_USED','LEARNED_TIME_OFFSET_USED','EMBEDDING_VECTOR_PAYLOAD_DECODED']:assert f[k] is False,k
checks['fail_closed_flags']=True
for n in ['RADDIT_EMBEDDING_TO_HISTORIC.parquet','RADDIT_HISTORIC_TO_KESTREL.parquet','RADDIT_KESTREL_EMBEDDING_CROSSWALK.parquet']:assert not (LOCAL/n).exists()
checks['no_fake_success_ledgers']=True
for name in ['RADDIT_KESTREL_FINGERPRINT_AUDIT.csv','RADDIT_KESTREL_MATCH_CONSISTENCY.csv','NEGATIVE_CONTROL_MATCH_AUDIT.csv','SEMANTIC_JOIN_SELECTION_BIAS.csv']:
    d=pd.read_csv(ROOT/name);assert d.status.str.startswith(('NOT_RUN','NOT_ELIGIBLE')).all()
checks['downstream_not_run_explicit']=True
required=['README.md','PREREGISTRATION.json','V14_BASE_VERIFICATION.json','FIELD_LINEAGE_MAP.csv','TIMEZONE_AND_UNIT_CANONICALIZATION.md','EMBEDDING_SCHEMA_AUDIT.json','EMBEDDING_HISTORIC_KEY_AUDIT.csv','EMBEDDING_SUBSET_FILTER_FORENSIC.md','EMBEDDING_ORDER_AUDIT.json','RADDIT_KESTREL_FINGERPRINT_AUDIT.csv','RADDIT_KESTREL_MATCH_CONSISTENCY.csv','NEGATIVE_CONTROL_MATCH_AUDIT.csv','PUBLIC_CROSSWALK_AUTHORITY_SEARCH.md','CROSSWALK_RECOVERY_SUMMARY.json','SEMANTIC_SUPPORT_COVERAGE.csv','SEMANTIC_JOIN_SELECTION_BIAS.csv','SEMANTIC_JOIN_SELECTION_BIAS_KO.md','NEW_JOB_SEMANTIC_CALLABILITY_AUDIT.json','FINAL_VERDICT.json','FINAL_REVIEW_KO.md']
assert all((ROOT/n).is_file() for n in required)
assert len(re.findall(r'^## \d+\.',(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8'),re.M))==45
checks['required_scientific_artifacts']=len(required);checks['final_report_questions']=45
p=subprocess.run([sys.executable,'-B',str(ROOT/'test_forensic.py')],cwd=REPO,capture_output=True,text=True)
write('TEST_RESULTS.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
assert p.returncode==0,p.stderr
checks['synthetic_adversarial_unit_tests']=6
# Syntax only; never import or execute external source/model code.
for script in ROOT.glob('*.py'):compile(script.read_text(encoding='utf-8'),str(script),'exec')
checks['all_R1_python_sources_compile']=True
changed=git('diff','--name-only',BASE).splitlines();assert all(x.startswith('docs/runtime_vnext14r1_raddit_crosswalk_recovery/') for x in changed)
write('SOURCE_MANIFEST.json',dict(base=BASE,raw_revalidation='V14_BASE_VERIFICATION.json / VERIFICATION.json',sources=schema['inputs'],inherited_authority=[dict(path=str(p),sha256=sha(p)) for p in [V14/'SOURCE_MANIFEST.json',V14/'LOCAL_EVIDENCE_MANIFEST.json',V14/'RADDIT_EMBEDDING_PROVENANCE_AUDIT.json',V14/'RAW_SOURCE_INVENTORY.csv',V14/'RAW_SCHEMA_METADATA.json',V14/'ORIGINAL_KESTREL_PROJECTION_AUDIT.json']],read_only_V42=calls['source'],public_search='PUBLIC_CROSSWALK_AUTHORITY_SEARCH.md / PUBLIC_GITHUB_RECEIPTS.json',source_history='GIT_HISTORY_SOURCE_AUDIT.json / .local/HISTORICAL_SOURCE_TEXT.json'))
localrecords=[record(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()]
write('LOCAL_EVIDENCE_MANIFEST.json',dict(scope='New R1 numeric projections, diagnostic negative ledgers, source text and execution logs. No vector payload or successful crosswalk.',files=localrecords))
checks['local_evidence_files_hash_bound']=len(localrecords)
write('VERIFICATION.json',dict(status='PASS',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=checks,limitations=['No source-backed naive timestamp UTC conversion established','No Kestrel physical fingerprint / negative controls / V13 bias calculation after Level1 stop','No claim that unknown physical matches equal zero'],NEW_ML_FITS=0))
write('DELIVERY_MANIFEST.json',dict(base=BASE,status=f['STATUS'],scope='V14R1 only; excludes .local payloads and this self-referential manifest',files=[record(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='DELIVERY_MANIFEST.json']))
for r in read(ROOT/'DELIVERY_MANIFEST.json')['files']:assert sha(ROOT/r['relative'])==r['sha256']
print(json.dumps(checks,indent=2))
