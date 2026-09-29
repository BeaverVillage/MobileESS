"""Finalize provenance receipts without running training, inference or Level2 joins."""
from common import *
import csv, sys, io, unittest, platform
import pyarrow as pa
import pyarrow.parquet as pq
from transforms import digest_frame

required = '''README.md PREREGISTRATION.json V14R1_BASE_VERIFICATION.json
RADDIT_GIT_LINEAGE_SEARCH.md EMBEDDING_EXPORT_PIPELINE_FORENSIC.md
NOTEBOOK_PROVENANCE_EVIDENCE.csv LFS_VERSION_LINEAGE.csv LOCAL_INTERMEDIATE_ARTIFACT_SEARCH.csv
HISTORIC_TIMESTAMP_AUTHORITY.json EMBEDDING_TIMESTAMP_SCHEMA_AUDIT.csv
TIMESTAMP_TRANSFORMATION_TESTS.csv DST_TIMESTAMP_DIAGNOSTIC.csv
PUBLIC_EXPORT_AUTHORITY_SEARCH.md RADDIT_PAPER_METHOD_LINEAGE.md SUBSET_FILTER_CANDIDATES.csv
SUBSET_FILTER_FORENSIC.md AMBIGUOUS_MAPPING_FORENSIC.csv LEVEL1_MAPPING_AUDIT.json
NEW_JOB_SEMANTIC_INPUT_GAP.csv EMBEDDING_PIPELINE_REPRODUCIBILITY.json FINAL_VERDICT.json
FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LOCAL_EVIDENCE_MANIFEST.json DELIVERY_MANIFEST.json
VERIFICATION.json'''.split()

def main():
    checks = {}
    baseline = read(ROOT/'V14R1_BASE_VERIFICATION.json')
    assert git('merge-base', BASE, 'HEAD') == BASE
    prefix = ROOT.relative_to(REPO).as_posix() + '/'
    for args in [('diff', '--name-only', BASE), ('ls-files', '--others', '--exclude-standard')]:
        assert all(p.startswith(prefix) for p in git(*args).splitlines()), args
    checks['only_R2_namespace_changed'] = True
    whitespace = subprocess.run(['git', '-c', 'core.whitespace=cr-at-eol', 'diff',
                                 '--check', BASE, '--', prefix], cwd=REPO, capture_output=True, text=True)
    assert whitespace.returncode == 0, whitespace.stdout + whitespace.stderr
    checks['git_diff_check_passed'] = True
    for r in baseline['files']:
        assert sha(REPO/r['relative']) == r['sha256'], r['relative']
    for r in baseline['delivery_manifests']:
        p = Path(r['path'])
        assert sha(p) == r['sha256']
        for f in read(p)['files']:
            assert sha(p.parent/f['relative']) == f['sha256'], f['relative']
    for r in baseline['local_inputs']:
        assert sha(r['path']) == r['sha256'], r['path']
    checks.update(prior_tracked_hashes_verified=len(baseline['files']),
                  prior_delivery_manifests_verified=len(baseline['delivery_manifests']),
                  prior_local_hashes_verified=len(baseline['local_inputs']))
    print('PRIOR HASHES VERIFIED', checks, flush=True)
    raw_count = 0
    with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            p = Path(r['directory'])/r['filename']
            st = Path('\\\\?\\'+str(p)).lstat()
            assert (st.st_size, st.st_mtime_ns) == (int(r['size_bytes']), int(r['mtime_ns'])), str(p)
            raw_count += 1
    assert raw_count == baseline['raw_size_mtime_verified'] == 23601
    checks['raw_size_mtime_verified'] = raw_count
    for r in read(ROOT/'V42_READONLY_INTERFACE_RECEIPT.json')['files']:
        assert sha(r['path']) == r['sha256'], r['path']
    checks['V42_interface_hashes_unchanged'] = 3
    print('RAW FINGERPRINTS VERIFIED', raw_count, flush=True)

    # Independent datetime-valued calculation, directly from one original source column.
    # No integer timestamp cutoff or cached end-time field is used here.
    original = RAD/'data/historic_job_trace.parquet'
    end = pq.ParquetFile(original).read(columns=['end_time']).to_pandas()['end_time']
    cutoff = pd.Timestamp('2024-04-23T00:00:00-06:00')
    keep = end.ge(cutoff).to_numpy()
    members = pd.read_parquet(R1/'.local/HISTORIC_RAW_MEMBERSHIP_NEGATIVE_LEDGER.parquet').sort_values('historic_row')
    assert np.array_equal(members.historic_row.to_numpy(), np.arange(len(end)))
    np.testing.assert_array_equal(keep, members.embedding_count.notna().to_numpy())
    assert len(end) == 2557884 and int(keep.sum()) == 1780972
    checks['independent_original_aware_end_date_membership'] = dict(
        comparison='original end_time >= 2024-04-23T00:00:00-06:00',
        method='datetime-valued comparison, independently of cached integer units',
        tested=len(end), kept=int(keep.sum()), removed=int((~keep).sum()),
        row_membership_identical=True, original_historic_sha256=sha(original),
        interpretation='Confirms observed subset, not original exporter or source-backed timezone transformation')
    h = pd.read_parquet(R1/'.local/HISTORIC_SHARED_METADATA.parquet')
    e = pd.read_parquet(R1/'.local/EMBEDDING_SHARED_METADATA.parquet')
    assert len(h) == 2557884 and len(e) == 1780972
    assert pd.to_datetime(h.submit_time_utc, unit='us', utc=True).max() < pd.Timestamp('2025-04-01', tz='UTC')
    assert pd.to_datetime(e.submit_time, unit='us').max() < pd.Timestamp('2025-04-01')
    checks['projected_population_pre_April_datetime_checked'] = True
    run = read(ROOT/'TRANSFORM_RUN_RECEIPT.json')
    replay = read(ROOT/'TRANSFORM_REPLAY_RECEIPT.json')
    assert run['metadata_digest'] == replay['metadata_digest'] == digest_frame(e)
    for t in ['T0', 'T1']:
        cols = [c+('_utc' if t == 'T1' else '') for c in ['submit_time', 'start_time', 'end_time']]
        digest = hashlib.sha256(np.ascontiguousarray(h[cols].to_numpy()).tobytes()).hexdigest()
        assert digest == run['timestamp_digests'][t] == replay['timestamp_digests'][t]
    assert replay['fresh_process'] and replay['canonical_sort_restores_metadata']
    assert sorted(replay['shuffled_chunk_order']) == list(range(45))
    assert replay['T0_EKEY2_mapping_digest'] == read(R1/'EMBEDDING_EXACT_AUDIT_DETAIL.json')['ledger_digests'][2]
    for i in range(3):
        ledger = pd.read_parquet(LOCAL/f'T1_EKEY{i}_DIAGNOSTIC_LEDGER.parquet')
        digest = digest_frame(ledger)
        detail = read(ROOT/f'T1_EKEY{i}_DETAIL.json')
        assert digest == detail['ledger_content_sha256'] == run['T1_mapping_digests'][i] == replay['T1_mapping_digests'][i]
        assert len(ledger) == 1780972 and ledger.embedding_global_row.is_unique
        assert not ledger.holdout_consistent.eq(True).any()
    checks['diagnostic_replay_receipts_and_content_digests_verified'] = True
    print('ORIGINAL DATE MEMBERSHIP AND REPLAY VERIFIED', flush=True)

    t = pd.read_csv(ROOT/'TIMESTAMP_TRANSFORMATION_TESTS.csv')
    assert len(t) == 6 and not t.approved.any()
    for _, r in t.iterrows():
        assert r.matched_embedding_rows + r.unmatched_embedding_rows == 1780972
        assert r.matched_historic_rows + r.unmatched_historic_rows == 2557884
        assert r.unique_1to1 + r.ambiguous_embedding_rows == r.matched_embedding_rows
        assert r.contradictory_1to1_rows + r.consistent_1to1_rows == r.unique_1to1
    assert t[t.transformation.eq('T0')].unique_1to1.tolist() == [1380258,1504066,1775514]
    assert t[t.transformation.eq('T1')].matched_embedding_rows.tolist() == [11,1,0]
    assert t[t.transformation.eq('T1')].contradictory_1to1_rows.tolist() == [8,1,0]
    a = pd.read_csv(ROOT/'AMBIGUOUS_MAPPING_FORENSIC.csv')
    assert a.ambiguous_groups.sum() == 2514 and a.unresolved_rows.sum() == 5458
    assert not a.exact_disambiguation_possible.any() and not a.row_order_used.any()
    f = pd.read_csv(ROOT/'EMBEDDING_TIMESTAMP_SCHEMA_AUDIT.csv')
    assert len(f) == 90 and f.chunk.nunique() == 45
    assert f.arrow_type.eq('timestamp[us]').all() and not f.timezone_metadata_present.any()
    assert f.physical_type.eq('INT64').all() and f.logical_type.str.contains('isAdjustedToUTC=false').all()
    assert f.drop_duplicates('chunk').rows.sum() == 1780972
    s = pd.read_csv(ROOT/'SUBSET_FILTER_CANDIDATES.csv')
    assert len(s) == 29 and s.historic_kept.notna().sum() == 28
    assert s.membership_exact_match.eq(True).sum() == 2
    d = pd.read_csv(ROOT/'DST_TIMESTAMP_DIAGNOSTIC.csv')
    assert d.matches_local_wall_clock.eq(True).sum() == 20
    assert d.matches_utc_wall_clock.eq(True).sum() == 0 and d.historic_timestamp.isna().sum() == 10
    lfs = pd.read_csv(ROOT/'LFS_VERSION_LINEAGE.csv')
    assert len(lfs) == lfs.path.nunique() == 46
    prior_sources = read(R1/'SOURCE_MANIFEST.json')['sources']
    sources_by_path = {r['path']:r for r in prior_sources if 'path' in r}
    for _, r in lfs.iterrows():
        source = sources_by_path[str(RAD/r.path)]
        assert source['sha256'] == r.lfs_oid and source['bytes'] == r['size']
    git_receipt = read(ROOT/'GIT_DEEP_SEARCH_RECEIPT.json')
    assert git_receipt['commits'] == 21 and git_receipt['stored_outputs_inspected'] == 59
    assert len(pd.read_csv(ROOT/'NOTEBOOK_PROVENANCE_EVIDENCE.csv')) == 28
    gaps = pd.read_csv(ROOT/'NEW_JOB_SEMANTIC_INPUT_GAP.csv')
    assert len(gaps) == 8 and gaps.available_in_v42.sum() == 2
    checks['csv_conservation_schema_subset_ambiguity_source_checks'] = True

    v = read(ROOT/'FINAL_VERDICT.json')
    assert v['STATUS'] == 'STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED'
    assert v['EMBEDDING_PROVENANCE_GRADE'] == 'PARTIAL' and v['TIMESTAMP_TRANSFORMATION'] == 'UNRESOLVED'
    for key in ['EMBEDDING_TO_RADDIT_MAPPING_PROVEN', 'LEVEL2_FINGERPRINT_RUN',
                'NEGATIVE_CONTROLS_RUN', 'RADDIT_TO_KESTREL_MAPPING_PROVEN',
                'END_TO_END_CROSSWALK_PROVEN', 'NEXT_SEMANTIC_RUNTIME_ML_AUTHORIZED',
                'APRIL_RUNTIME_EVALUATED', 'MAY_PAYLOAD_OPENED', 'V42_CHANGED',
                'CC4_CHANGED', 'MESS_CHANGED', 'OPTIMIZER_CHANGED', 'OPENDSS_EXECUTED',
                'EMBEDDING_VECTOR_PAYLOAD_DECODED', 'MODEL_DOWNLOADED', 'FUZZY_MATCHING_USED',
                'LEARNED_TIME_OFFSET_USED', 'ARBITRARY_OFFSET_SEARCH_USED',
                'STAGE_C_EXECUTED', 'PROVIDER_GENERATED', 'QUEUE_REPLAY_RUN']:
        assert v[key] is False, key
    for key in ['RADDIT_TO_KESTREL_UNIQUE_MATCHES', 'RADDIT_TO_KESTREL_AMBIGUOUS',
                'V13_SEMANTIC_MAPPED_JOBS', 'V13_SEMANTIC_JOIN_RATE',
                'GT4H_SEMANTIC_JOIN_RATE', 'GT12H_SEMANTIC_JOIN_RATE', 'GT24H_SEMANTIC_JOIN_RATE']:
        assert v[key] is None, key
    assert v['NEW_ML_FITS'] == v['REEMBEDDING_ROWS'] == v['APPROVED_LEVEL1_MAPPING_ROWS'] == 0
    assert not all(read(ROOT/'LEVEL1_MAPPING_AUDIT.json')['criteria'].values())
    for name in ['RADDIT_KESTREL_FINGERPRINT_AUDIT.csv', 'NEGATIVE_CONTROL_MATCH_AUDIT.csv',
                 'LEVEL2_MAPPING_AUDIT.json', 'SEMANTIC_SUPPORT_COVERAGE.csv',
                 'SEMANTIC_JOIN_SELECTION_BIAS.csv', 'SEMANTIC_JOIN_SELECTION_BIAS_KO.md']:
        assert not (ROOT/name).exists(), name
    review = (ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(x) for x in re.findall(r'^## (\d+)\.', review, re.M)] == list(range(1,51))
    checks['fail_closed_flags_and_50_answers_consistent'] = True
    checks['execution_scope_basis'] = 'Recorded task commands, receipt review and namespace/hash verification; not a system-wide process attestation'

    import test_authority
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_authority))
    write('TEST_RESULTS.json', dict(tests=result.testsRun, failures=len(result.failures),
          errors=len(result.errors), output=stream.getvalue(), passed=result.wasSuccessful()))
    assert result.wasSuccessful() and result.testsRun == 4
    scripts = sorted(ROOT.glob('*.py'))
    for p in scripts:
        compile(p.read_text(encoding='utf-8'), str(p), 'exec')
    checks['unit_tests_passed'] = result.testsRun
    checks['python_syntax_files_verified'] = len(scripts)

    write('SOURCE_MANIFEST.json', dict(base=BASE,
        raw_payload_hash_policy='Reuse frozen V14/R1 hashes bound to unchanged raw size/mtime; independently rehash 91MB historic. No vector decoding.',
        raw_sources=[sources_by_path[str(RAD/p)] for p in lfs.path],
        original_historic_independent_hash=rec(original),
        cached_local_inputs=baseline['local_inputs'],
        raw_inventory=rec(V14/'RAW_SOURCE_INVENTORY.csv'),
        prior_delivery_manifests=baseline['delivery_manifests'],
        raddit_git_head=git_receipt['head'],
        raddit_history_receipt=deliver_rec(ROOT/'GIT_DEEP_SEARCH_RECEIPT.json'),
        raddit_lfs_lineage=deliver_rec(ROOT/'LFS_VERSION_LINEAGE.csv'),
        official_public_receipts=deliver_rec(ROOT/'PUBLIC_SOURCE_RECEIPTS.json'),
        public_search_scope=deliver_rec(ROOT/'PUBLIC_EXPORT_AUTHORITY_SEARCH.md'),
        v42_readonly_sources=read(ROOT/'V42_READONLY_INTERFACE_RECEIPT.json')['files']))
    local_files = [rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()]
    write('LOCAL_EVIDENCE_MANIFEST.json', dict(files=local_files, files_count=len(local_files),
        scope='New R2 diagnostic ledgers and logs; prior ledgers remain hash-bound inputs in SOURCE_MANIFEST',
        vector_payload_decoded=False, approved_crosswalk=False))
    checks['new_local_evidence_files_hashed'] = len(local_files)
    write('VERIFICATION.json', dict(status='PASS', verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        base=BASE, checks=checks, runtime=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, pyarrow=pa.__version__),
        limitations=['Timestamp stripping/export authority unresolved; verification does not authorize mapping.',
                    'Public inaccessible full paper/PDF and OSTI timeout are not claims of absence.',
                    'Raw payload reuse uses prior content hashes plus unchanged size/mtime; vectors not reread.']))
    files = [deliver_rec(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name != 'DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json', dict(files=files, self_excluded=True,
        local_evidence='LOCAL_EVIDENCE_MANIFEST.json binds ignored .local artifacts',
        base=BASE, scientific_status=v['STATUS']))
    for name in required:
        assert (ROOT/name).is_file(), name
    for r in read(ROOT/'DELIVERY_MANIFEST.json')['files']:
        assert sha(ROOT/r['relative']) == r['sha256'], r['relative']
    print('VERIFICATION PASS', json.dumps(clean(checks)), flush=True)

if __name__ == '__main__':
    main()
