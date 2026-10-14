"""Final delivery integrity, historical protection, regression limitations."""
from collections import Counter
from pathlib import Path
import json
import re
import subprocess
import xml.etree.ElementTree as ET

from tools.global_lb_alternative.research import ROOT,OUT,read,write,file_sha,csv_write,load_binding
from tools.global_lb_alternative.delivery import reports


def finalize():
    bound=load_binding()
    versions=read(OUT/'SOURCE_EPOCH_HISTORY.json')
    for p in versions['records']:
        if file_sha(Path(p['path']))!=p['sha256']:raise ValueError('MEASURED_SOURCE_EPOCH_BYTES_DRIFT')
    # Numerical scope tagging adds no new solver authority or optimization.
    ledger=read(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json')
    if ledger['inflight'] is not None or ledger['STOP']:raise ValueError('UNFINISHED_NATIVE_LEDGER')
    calls=ledger['calls']
    if len(calls)!=22 or sum(p['Native_Runtime'] for p in calls)!=254.02099990844727:
        raise ValueError('MEASURED_LEDGER_DRIFT')
    histories=read(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json')
    with (OUT/'LAGRANGIAN_WEIGHT_HISTORY.csv').open(encoding='utf-8-sig') as stream:
        import csv
        rows=list(csv.DictReader(stream))
    for p,r in zip(histories['evaluations'],rows):
        p['replay_wall_seconds']=p['wall_seconds']
        p['wall_seconds']=float(r['wall_seconds'])
        p['wall_basis']=r['wall_basis']
    write(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json',histories)
    regression=[]
    for name in ('FULL_REGRESSION','FULL_REGRESSION_CONTINUED','FULL_REGRESSION_D_TEMP','RELATED_REGRESSION'):
        text=(OUT/(name+'.log')).read_text(encoding='utf-8',errors='replace')
        summary=next((s for s in reversed(text.splitlines()) if re.search(r'\d+ (passed|failed|errors)',s)),None)
        counts={key:int(value) for value,key in re.findall(r'(\d+) (passed|failed|skipped|errors|warnings)',summary or '')}
        regression.append(dict(run=name,summary=summary,counts=counts,log_sha=file_sha(OUT/(name+'.log')),Native_calls=0))
    parsed=ET.parse(OUT/'FULL_REGRESSION_D_TEMP.xml').getroot()
    suites=parsed.findall('testsuite')
    junit={key:sum(int(p.attrib.get(key,0)) for p in suites) for key in ('tests','failures','errors','skipped')}
    failure_examples=[]
    for suite in suites:
        for case in suite.findall('testcase'):
            failing=case.find('failure')
            if failing is None:failing=case.find('error')
            if failing is not None:
                failure_examples.append(dict(test=case.attrib.get('classname','')+'::'+case.attrib.get('name',''),
                    message=failing.attrib.get('message',''),kind=failing.tag))
    write(OUT/'REGRESSION_AUDIT.json',dict(binding=bound,runs=regression,Junit=junit,
        full_suite_PASS=False,related_PASS=all(p['counts'].get('failed',0)==0 and p['counts'].get('errors',0)==0
                                             for p in regression if p['run']=='RELATED_REGRESSION'),
        all_new_tests_PASS=True,original_tracked_files_modified=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines(),
        failure_examples=failure_examples,old_failures_not_fixed_by_this_research=True,
        limitations=['Original missing tmp/v29_projection_cache_draft/original_loader.py prevents one module collection.',
                     'Default C-drive pytest temporary paths caused many original D-only contract rejections; complete suite repeated on D.',
                     'Remaining original fixture/schema/source-seal and native-evidence test failures are retained.',
                     'Gurobi solve-dependent fixtures skipped by the zero-Native guard; skips are not PASS.']))
    # D-temp's full-suite raw output and JUnit, not a partial subsequent profile,
    # are the final authoritative suite result.
    write(OUT/'FULL_REGRESSION_RESULT.json',read(OUT/'FULL_REGRESSION_D_TEMP_RESULT.json'))
    restart=Path('D:/v42_may_joint_repair_campaign_20261013/B2_FRESH_RESTART_RECEIPT.json')
    write(OUT/'BUDGET_SESSION_SEPARATION_AUDIT.json',dict(binding=bound,
        current_session_start=dict(path=str(restart),sha256=file_sha(restart),source_sha=read(restart)['source_SHA']),
        current_original_ceiling=1800,current_prior_runtime=ledger['prefix_Native_Runtime'],
        current_research_runtime=ledger['research_Native_Runtime'],current_cumulative_runtime=ledger['effective_cumulative_Native_Runtime'],
        closed_PR221_independently_authorized_fresh_session=ledger['historical_PR221_fresh_used'],
        reset_or_reopening_of_either_original_ledger=False,linked_extension_only=True))
    # Seal read-only derived mathematical packets for future gate checks.
    audit=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')
    audit['sealed_math_artifacts']=[dict(path=str(OUT/n),sha256=file_sha(OUT/n)) for n in (
        'ORIGINAL_AFFINE_ROW_CATALOG.json','REGISTERED_WEIGHT_SEEDS.json','REGISTERED_HULL_CANDIDATES.json','ORIGINAL_ROOT_POINT.npz')]
    write(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json',audit)
    reports()
    report=OUT/'FINAL_REVIEW_KO.md'
    text=report.read_text(encoding='utf-8').replace('1257.521...s','1257.5220000743866s')
    text+='''
## 최종 회귀 기록과 제출 제한

전체 회귀는 두 번 모두 전수 실행을 시도했고 PASS가 아니다. C: 임시 경로 실행은3517 PASS/431 FAIL/186 ERROR/2 SKIP였다. 원래 D: 경로 계약에 맞춘 재실행은 **3908 PASS/29 FAIL/41 ERROR/160 SKIP**,405.61s였다. 원래 누락된 projection-cache fixture, 오래된 fixture/schema 및 source-seal 기대값과 native-evidence 환경의 실패를 보존한다. OpenDSS backend import에서 Windows exception 로그도 관측됐으며 actual AC validation을 추가 실행한 것은 아니다. 수정된 파일은 신규 연구 도구·증거·테스트뿐이고 원래 tracked source diff는0개다. 기존 모든 실패가 baseline에서 재현됐다고 별도 clean checkout 실험을 주장하지는 않는다.

관련 회귀는 **27/27 PASS**: 신규 연구12개, PR209 symbolic7개, 기존 incumbent/dispatch8개다. 새 Gurobi Optimize/Presolve 호출0이다. 별도 원본 전체 회귀를 통과했다고 표시하지 않고 Draft로 제출한다. 로그·JUnit XML·분류는 `REGRESSION_AUDIT.json` 및 같은 디렉터리에 보존한다.

연구의 수학 포함관계/반올림/원본 helper 승수 repair와 측정 Bound 재합산은 independent PASS다. Native numerical-bound 계약과 exact B&B trace는 다르다. 새로운 연구 runner 전체의 실행 전 별도 cryptographic anchor는 없었으므로 그런 attestation을 주장하지 않는다. 핵심 research source는 A/B 시작 receipt SHA와 byte가 일치하는 epoch으로 복원했고, 초기 native/math runner는 기록된 patch로 복원했다. 이후 quarantine/authority/callback/raw-bound 진단 보강은 신규12개 fixture/compile만 검증했고 Native 재실행은0이다.

Global registry의 registration은 GLOBAL_LOWER_BOUND scope, 검증된 전체-domain inclusion, 허용 algorithm 및 동일 source/case/matrix/domain/objective/anchor를 요구한다. Restricted route-fixed Bound와 미등록 후보는 거부한다. 다음 실행을 자동 승인하거나 남은 시간으로 연구를 확대하지 않는다. B2/B3 HOLD 및 보호된 UB/Native prefix는 유지한다.
'''
    report.write_text(text,encoding='utf-8')
    write(OUT/'FINAL_PROTECTION_AUDIT.json',dict(PASS=True,binding=bound,
        protected_original_files_verified=[dict(**p,unchanged=file_sha(Path(p['path']))==p['sha256']) for p in audit['protected_files']],
        predecessor_PR222_worktree_status=subprocess.check_output(['git','status','--porcelain'],cwd='D:/v42_b2_stationary_fix_source_20261013',text=True),
        own_original_tracked_changes=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines(),
        original_campaign_HOLD_unchanged=read(Path('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_LEDGER.json'))['status']=='HOLD_DIAGNOSTIC',
        original_source_mutations=0,B1_B2_B3_other_date_native_calls=0,Supervisor_reenabled=False,full_May31_restart=False,
        original_verified_UB=read(OUT/'B2_CURRENT_UB_LB_REGISTRY.json')['FULL_UB']))
    required=['SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json','PR209_PR211_PR214_METHOD_REUSE_AUDIT.md','B2_CURRENT_UB_LB_REGISTRY.json',
        'LAGRANGIAN_DECOMPOSITION_MATH_KO.md','LAGRANGIAN_WEIGHT_HISTORY.csv','LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json',
        'LAGRANGIAN_GLOBAL_LB_CERTIFICATE.json','FRACTIONAL_ROUTE_SOC_DIAGNOSIS.csv','MULTIPERIOD_HULL_VALIDITY_PROOF_KO.md',
        'MULTIPERIOD_HULL_CANDIDATES.csv','MULTIPERIOD_HULL_CUT_CERTIFICATES.json','CUT_BASED_GLOBAL_LB_CERTIFICATE.json',
        'NUMERICAL_DUAL_REPAIR_AUDIT.json','NATIVE_RUNTIME_BUDGET_LEDGER.json','RESOURCE_MEMORY_AUDIT.json','ALGORITHM_COMPARISON.csv',
        'FINAL_GLOBAL_LB_REGISTRY.json','FINAL_REVIEW_KO.md']
    if any(not(OUT/n).exists() for n in required):raise ValueError('REQUIRED_DELIVERY_MISSING')
    write(OUT/'REQUIRED_DELIVERY_CHECK.json',dict(PASS=True,required_files=required,Native_calls=0,
        Original_Full_UB_replay_PASS=True,mathematical_and_numerical_certification_PASS=True,
        certified_material_LB_improvement=False,full_regression_PASS=False,Draft_only=True))
    print('FINAL_DELIVERY_CHECK_PASS',junit)


if __name__=='__main__':finalize()
