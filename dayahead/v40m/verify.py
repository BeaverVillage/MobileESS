"""Data regressions and protected-scope/receipt verification."""
from .forensic import *
import unittest
import io

def verify():
    checks=[]
    def check(name,ok,detail=None):
        checks.append({'name':name,'passed':bool(ok),'detail':detail})
        if not ok:raise AssertionError(name)
    identity=read(OUT/'V40M_72_BLOCKER_IDENTITY.json')
    ledger=read(OUT/'V40M_72_CASE_AUTHORITY_LEDGER.json')
    trans=read(OUT/'V40M_AUTHORITY_TRANSITION_MATRIX.json')
    start=read(OUT/'V40M_START_STATE.json')
    keys=[c['case_id'] for c in identity['cases']]
    check('original_122_identity_preservation',len(keys)==122 and digest(keys)==identity['original_122_case_key_sha256'])
    blockerkeys=[c['case_id'] for c in identity['cases'] if c['old_status']==MISS]
    check('exact_72_blocker_identity',sorted(x['case_id'] for x in ledger)==blockerkeys and digest(blockerkeys)==identity['blocker_72_case_key_sha256'])
    children=[x for c in ledger for x in c['uid_evidence']]
    childkeys=sorted((x['case_id'],x['UID']) for x in children)
    check('exact_5126_UID_case_identity',len(childkeys)==5126 and len(set(childkeys))==5126 and digest(childkeys)==identity['blocker_5126_UID_case_key_sha256'])
    check('duplicate_UID_handling',len({x['UID'] for x in children})==1634)
    check('no_Planning_to_Actual_substitution',all(not x['planning_fallback_used'] for x in children))
    check('no_inferred_site_authority',all(not x['inferred_site_used'] and x['actual_site'] is None for x in children))
    check('case_count_conservation',sum(trans['new'].values())==sum(t['case_count'] for t in trans['transitions'])==122)
    raw=read(OUT/'V40M_RAW_UID_EVIDENCE.json')
    check('raw_source_hash_and_duplicate_conflicts_recorded',raw['record_sha256']==digest(raw['records']))
    check('timestamp_chronology',all(pd.Timestamp(x['actual_start'])<pd.Timestamp(x['actual_end']) for x in raw['records']))
    check('pending_historical_timestamp_not_promoted',all(x['actual_start'] is None and x['actual_end'] is None for x in children))
    table=pd.read_parquet(OUT/'V40M_72_CASE_AUTHORITY_LEDGER.parquet')
    columns={'UID','required_authority_type','source_SHA256','searched_sources','uid_evidence'}
    decoded=[{k:json.loads(v) if k in columns else v for k,v in r.items()} for r in table.to_dict('records')]
    check('JSON_Parquet_ledger_equivalence',decoded==ledger)
    check('all_source_families_present',set(read(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json')['families'])==set(FAMILIES))
    searches=pd.read_parquet(OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet')
    manifest=read(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json')
    addendum=read(OUT/'V40M_INVENTORY_RECOVERY_ADDENDUM.json')
    check('census_search_count_conservation',len(searches)==manifest['file_count']+addendum['recovered_file_count'] and int(searches.bytes.sum())==manifest['total_bytes']+addendum['recovered_bytes'])
    check('all_unparsed_sources_explain_reason',searches.reason.notna().all())
    check('V40L_namespace_never_inventoried_or_parsed',not searches.path.str.lower().str.contains('v40l').any())
    # Rehash all unique sources used in case proofs, the raw archive, typed
    # search results and original identity. Other parsed files were hashed at
    # read time after checking the frozen inventory metadata.
    used={r['path']:r for r in read(OUT/'V40M_BOUND_SOURCE_HASH_VERIFICATION.json')}
    for r in raw['records']:used[r['source_path']]={'path':r['source_path'],'sha256':r['source_sha256']}
    for r in identity['sources']:used[r['path']]=r
    verified=[]
    for p,r in used.items():
        h=sha(p);check_value=h==r['sha256']
        if not check_value:raise AssertionError('Source hash drift: '+p)
        verified.append({'path':p,'sha256':h})
    write('V40M_FINAL_SOURCE_HASH_VERIFICATION.json',verified)
    check('source_hash_verification',len(verified)>0,{'files_rehashed':len(verified)})
    after=protected();before=start['protected_file_sha256']
    changed=[p for p,h in before.items() if after.get(p)!=h]
    added=sorted(set(after)-set(before));removed=sorted(set(before)-set(after))
    scope={'protected_files':len(before),'changed':changed,'added':added,'removed':removed,'unchanged':not(changed or added or removed),
       'V40L':'No namespace enumeration/content read/write; deliberate no V40L before/after hash read',
       'starting_commit':START,'git_changed_paths':git('diff','--name-only',START).splitlines(),
       'new_namespace_allowlist':['dayahead/v40m/','dayahead/artifacts/v40m_authority72_closure/']}
    check('protected_V40I_V40J_V40K_unchanged',scope['unchanged'],len(before))
    changedpaths=git('diff','--name-only',START).splitlines()
    check('tracked_protected_scope_unchanged',all(p.startswith(tuple(scope['new_namespace_allowlist'])) for p in changedpaths))
    write('V40M_PROTECTED_SCOPE_DIFF.json',scope)
    check('electrical_generation_HOLD',trans['31_DAY_ELECTRICAL_REGENERATION']=='HOLD' and trans['certified_electrical_outputs_created']==0)
    check('optimization_and_science_changes_NO',all(trans[k]=='NO' for k in ('B0_B1_B2_B3','FULL_MAY','optimization','MODEL_RETRAINING','q_change','K0_change','tail_model_change','PF_change','Q_control_change')))
    from . import test_authority
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromModule(test_authority)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/'V40M_UNIT_TESTS.log').write_text(stream.getvalue(),encoding='utf-8')
    check('adversarial_authority_unit_tests',result.wasSuccessful(),{'tests_run':result.testsRun})
    report={'created_at':now(),'status':'PASS','unit_tests':result.testsRun,'data_regressions':len(checks),
      'total_checks':len(checks)+result.testsRun,'checks':checks,'source_hash_files_reverified':len(verified),
      'scientific_models_or_optimization_runs':0,'census_errors_not_hidden':len(addendum['remaining_inventory_errors']),
      'not_a_claim_all_sources_readable':True}
    write('V40M_TEST_REPORT.json',report)
    print('TEST PASS',report['total_checks'],'checks',len(verified),'source hashes',len(before),'protected files',flush=True)
    return report

def review():
    i=read(OUT/'V40M_72_BLOCKER_IDENTITY.json');t=read(OUT/'V40M_AUTHORITY_TRANSITION_MATRIX.json')
    c=read(OUT/'V40M_AUTHORITY_SOURCE_CENSUS.json');m=read(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json');tests=read(OUT/'V40M_TEST_REPORT.json')
    source=pd.read_parquet(OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet')
    errors=source[source.reason=='READ_OR_PARSE_ERROR'][['path','error']].to_dict('records')
    addendum=read(OUT/'V40M_INVENTORY_RECOVERY_ADDENDUM.json')
    write('V40M_SEARCH_LIMITATIONS.json',{'inventory_errors':addendum['remaining_inventory_errors'],'original_inventory_errors':len(m['inventory_errors']),'parse_errors':errors,
       'not_parsed_reasons':dict(Counter(source.loc[~source.parsed,'reason'])),
       'scope':'Local available roots only; unreadable files and excluded formats are not evidence of absence.'})
    text=['# V40M Actual execution authority closure','',f"판정: **{t['classification']}**.",'',
      f"시작 commit: `{START}`. Branch: `{git('branch','--show-current')}`. Worktree: `{REPO}`.",
      '최종 연구 commit SHA는 post-commit V40M_FINAL_COMMIT_RECEIPT.json에 기록한다. 그 receipt는 자신의 commit SHA를 내장하지 않는다.','',
      '72는 UID 수가 아니라 날짜/B0–B3 case 수다. 원래 122 case / 8,786 UID–case 행을 V40H·V40I 사이에서 정확히 대조했다. '
      '72 blocker는 5,126 UID–case 행과 고유 UID 1,634개다. V40K receipt의 72는 count 확인이며 새 identity 목록으로 해석하지 않았다.',
      f"72 case-key SHA256: `{i['blocker_72_case_key_sha256']}`.",
      f"5,126 UID–case-key SHA256: `{i['blocker_5126_UID_case_key_sha256']}`.",
      '과거 44 jobs는 2025-05-01/B1에 해당하고 기존 44-case blockers와의 일치는 0이었다. 숫자로 cohort를 합치지 않았다.','',
      '| Classification | Old | New |','|---|---:|---:|']
    for k in (PRE,AUTH,CONFLICT,MISS):text.append(f"| {k} | {t['old'][k]} | {t['new'][k]} |")
    text += ['',f"기존 72건 중 해결 {t['resolved_original_72']}건. 신규 pre-day-complete {t['new'][PRE]-50}건, 신규 execution-site {t['new'][AUTH]}건, 충돌 {t['new'][CONFLICT]}건, 잔여 missing {t['new'][MISS]}건.",'',
      f"50개 root, 최초 {m['file_count']:,}개 + 확장 경로 metadata 복구 {addendum['recovered_file_count']}개 = {len(source):,}개 파일, {int(source.bytes.sum()):,} bytes를 목록화했다. 최초 inventory SHA256: `{m['inventory']['sha256']}`. 복구 addendum은 원래 error 경로에 한정된다.",
      f"실제 parsed/동일-content 재사용 {int(source.parsed.sum()):,}개; 미파싱 {int((~source.parsed).sum()):,}개. 최초 inventory 오류 691건 중 잔여 {len(addendum['remaining_inventory_errors'])}건, 파싱/읽기 오류 {len(errors)}건은 별도 limitations에 공개했다. 긴 UNC 경로 14,236건을 재검색해 복구했다.",
      '검색 제외는 dependency/VCS/cache, 다른 power benchmark의 job domain, 이전 mobility/electrical solver audit, 비실행기록 형식 등이다. 전체 저장소가 완전히 읽혔다거나 외부 증거가 존재하지 않는다는 주장이 아니다.','',
      '| 순서 | Source family | Files | Bytes | Parsed | Not parsed |','|---|---|---:|---:|---:|---:|']
    for f in c['families']:text.append(f"| {f['family']} | {f['title']} | {f['file_count']:,} | {f['total_bytes']:,} | {f['parsed_files']:,} | {f['not_parsed_files']:,} |")
    text += ['', '원본 Kestrel ZIP 및 member SHA256/정확한 row key를 다시 확인했다. 원래 전체 UID 2,543개의 raw timing·GPU가 frozen observation과 일치한다. '
       '물리 nodelist는 복구 가능하지만 현재 12개 합성 AIDC의 case별 실제 allocation은 아니다. '
       '미해결 5,126행은 PENDING이어서 과거 관측 종료를 현재 case의 실제 admission/end로 바꿀 수 없다. '
       '기존 완료 3,660행은 RUNNING 연속 실행 규약과 실제 timestamp로 재검증했다.','',
       '주요 근거: V40M_RAW_UID_EVIDENCE.json, V40M_TYPED_UID_SIGHTINGS.parquet, V40M_SOURCE_ADJUDICATION.json. '
       '72-case JSON/Parquet 원장에는 UID별 실제 관측 시각, 물리 노드, source/member hash, exact row key와 미해결 이유를 기록했다. '
       'Parquet의 복합 열은 canonical JSON 문자열이며 scalar case 열은 native 형식이다.','',
       f"검증: unit {tests['unit_tests']}개 + data regression {tests['data_regressions']}개 = {tests['total_checks']}개 PASS. "
       'V40I/V40J/V40K source·artifact 해시 보존, V40L 내부 접근/수정 없음, 허용 namespace 외 tracked 변경 없음.',
       '', '31_DAY_ELECTRICAL_REGENERATION = HOLD. B0_B1_B2_B3 = NO. FULL_MAY = NO. '
       '재학습, q/K0/tail/PF/Q-control 변경, optimization 및 certified electrical output 생성은 모두 0/NO.']
    (OUT/'V40M_FINAL_REVIEW.md').write_text('\n'.join(text)+'\n',encoding='utf-8')

if __name__=='__main__':verify();review()
