from pathlib import Path
from collections import Counter
import json,re,subprocess,xml.etree.ElementTree as ET,hashlib
repo=Path.cwd();root=repo/'dayahead/artifacts/v40i_authority_electrical_closure';base=Path('C:/codex_mobileess_workspace/v40i_prechange_tests')
orig=json.loads((root/'V40I_FULL_REPOSITORY_FAILURES.json').read_text(encoding='utf-8'))
baseline=json.loads((root/'V40I_PRECHANGE_FAILURES.json').read_text(encoding='utf-8'))
lookup={(r['classname'],r['name']):r for r in baseline}
for tc in ET.parse(root/'prechange_tests/same_preexisting_fixtures.xml').iter('testcase'):
 e=tc.find('failure')
 if e is not None:lookup[(tc.get('classname'),tc.get('name'))]={'message':e.get('message'),'details':e.text,'same_fixture_baseline':True}
changed=subprocess.check_output(['git','diff','--name-only','67458be58fa5923fa27c566b1d9ff77d9d10ec0c','--','*.py'],text=True).splitlines()
assert set(changed)<={'dayahead/v40i/electrical.py','tests/dayahead/test_v40i_electrical.py','dayahead/v40i/__init__.py'},changed
rows=[]
for i,r in enumerate(orig):
 p=Path(r['file']);name=r['test']['classname']+'::'+r['test']['name'];b=lookup[(r['test']['classname'],r['test']['name'])]
 m=r['message'];detail=r['details']; testname=r['test']['name']
 version=re.search(r'test_(v\d+[a-z0-9]*|g\d+|pfr|shared)',p.stem);version=version.group(1) if version else p.stem.removeprefix('test_')
 if 'torch' in m: cause='DEPENDENCY_MISSING: torch (legacy frozen Torch 2.8.0 assertion)';category='UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE';env=True
 elif 'POSIX' in m:cause='PLATFORM_UNSUPPORTED: Windows environment lacks POSIX locking required by old source-cache test';category='UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE';env=True
 elif i in (12,14,16,17,18,21,22,62):
  cause='HISTORICAL_GIT_IDENTITY_CONTRACT: old branch/starting HEAD/base comparison is incompatible with later V40H/V40I branch; legacy source differences predate I'
  category='UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE';env=True
 elif i==49:
  cause='LEGACY_SYNTHETIC_QCP_ASSERTION: mock exact verifier rejects projected control; same assertion with H source and current solver environment. Numerical/library root cause not further established.'
  category='UNRELATED_PREEXISTING_LEGACY_TEST_FAILURE';env=False
 elif i==30:
  cause='PREEXISTING_MUTABLE_V39H_GATE_FIXTURE: release mask differs from old expected mask; file already modified in V40I START_GIT_STATUS'
  category='UNRELATED_PREEXISTING_LEGACY_STATE_FAILURE';env=False
 elif i==31:
  cause='LEGACY_MIGRATION_COUNT_FIXTURE: expected 76 vs persisted 105; same H-source assertion'
  category='UNRELATED_PREEXISTING_LEGACY_STATE_FAILURE';env=False
 elif i==32:
  cause='LEGACY_REPAIRED_SCHEDULE_LOADER_MISMATCH: 8/96 occupancy slots differ by 1 GPU; H source with identical existing fixtures reproduces exactly'
  category='UNRELATED_PREEXISTING_LEGACY_STATE_FAILURE';env=False
 elif any(s in m for s in ['FileNotFoundError','MISSING','missing','is_file','exists()','Final evidence']) or i in (53,54,55,56):
  cause='HISTORICAL_ARTIFACT_OR_SOURCE_MISSING: see exact original/baseline failure message; current workspace lacks required historical cache/source/result'
  category='UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE';env=True
 else:
  cause='HISTORICAL_FROZEN_ARTIFACT_HASH_OR_SIZE_MISMATCH: inherited files do not match older version seal; reproduced before I code exists'
  category='UNRELATED_PREEXISTING_FROZEN_ARTIFACT_FAILURE';env=False
 a=(repo/p).read_bytes();bb=(base/p).read_bytes()
 assert a==bb,str(p)
 tracefiles=set(re.findall(r'(?m)^((?:dayahead|pfr|tests|tools)[\\/][^\n:]+\.py):\d+',detail))
 dependencies=[]
 for rel in sorted(tracefiles):
  local=repo/rel;old=base/rel
  dependencies.append({'path':rel.replace('\\','/'),'same_baseline_source_bytes':local.is_file() and old.is_file() and local.read_bytes()==old.read_bytes()})
 assert all(x['same_baseline_source_bytes'] for x in dependencies),dependencies
 rows.append({'index':i,'failure_test_name':name,'failure_file':str(p),'failure_namespace_version':version,
   'failure_kind':r['kind'],'classification':category,'failure_cause':cause,
   'dependency_on_V40I_source_changes':False,'dependency_evidence':dependencies,
   'test_source_identical_to_pre_I':True,'test_source_SHA256':hashlib.sha256(a).hexdigest(),
   'pre_existing_failure_reproduced_without_V40I_source':True,'baseline_commit':'67458be58fa5923fa27c566b1d9ff77d9d10ec0c',
   'baseline_mode':'PRE_I_SOURCE_SAME_EXISTING_WORKSPACE_FIXTURES' if b.get('same_fixture_baseline') else 'ISOLATED_PRE_I_DETACHED_CHECKOUT',
   'independent_environment_or_missing_dependency':env,'original_message':m,'baseline_message':b['message'],
   'branch_test_note':'Baseline detached HEAD also fails old branch assertion; START_GIT_STATUS and V40I start branch record establish current V40A branch predated I.' if i==17 else None,
   'forensic_source_changes_to_force_pass':False})
report={'status':'CLASSIFIED','total':64,'failures':55,'errors':9,'reproduced_on_pre_I_source':64,'V40I_failures':0,
 'classification_counts':dict(Counter(r['classification'] for r in rows)),'all_legacy_test_and_trace_source_bytes_unchanged':True,
 'baseline_reproduction_scope':'Same Python/site-packages. Fresh detached H checkout; three differing initial failure points rerun with unchanged H code and the existing original artifact fixtures. No I imports in same-fixture run.',
 'source_diff_since_pre_I':changed,'source_changes_to_force_old_tests_pass':0,'rows':rows}
(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
import pandas as pd
pd.DataFrame(rows).drop(columns=['dependency_evidence']).to_csv(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.csv',index=False,encoding='utf-8-sig')
text=['# 전체 저장소 테스트 실패 분류','',
 '전체 저장소 2,200개 결과는 2,132 PASS, 55 failures, 9 errors, 4 skipped다. 전체 PASS로 보고하지 않는다. 실패/error 64개는 V40I 이전 H 커밋 67458be58fa5923fa27c566b1d9ff77d9d10ec0c의 독립 체크아웃에서 모두 다시 실패했다.',
 '',
 '실패 test와 traceback에 등장하는 저장소 Python 소스는 H와 byte 동일하다. 초기 baseline의 실패 지점이 달랐던 V39H 3개는 H 코드를 유지하고 현재의 기존 artifact fixture를 읽도록 한 별도 pytest plugin에서 동일 실패를 재현했다. 이 실행의 V40I import는 0개다. 소스를 바꾸거나 과거 테스트를 통과시키기 위한 환경 설치·artifact 교체는 하지 않았다.',
 '',
 'V33만의 문제가 아니다. 누락된 Torch, Windows POSIX-locking 부재, 과거 branch/HEAD 강제, legacy cache/결과 누락, 과거 봉인 hash/size 불일치와 V39H 상태 불일치도 포함한다. 환경 문제만 UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE로, 실제 기존 assertion/state/artifact 문제는 별도 분류했다. PFR synthetic QCP assertion의 더 세부적인 수치 원인은 미확정이며 환경 누락으로 단정하지 않았다.',
 '',
 '| 분류 | 수 |','|---|---:|']
for k,v in report['classification_counts'].items():text.append(f'| {k} | {v} |')
text.extend(['','각 test name/version/cause/V40I dependency/baseline reproduction/environment 구분과 원문 오류는 JSON 및 CSV에 모두 기록했다. 필수 V40H 106 + 기존 V40I 60의 166개 PASS를 사용자 승인 scope로 사용하며 이후 추가된 회귀도 함께 요구한다.',''])
(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.md').write_text('\n'.join(text),encoding='utf-8')
print(report['classification_counts'])

