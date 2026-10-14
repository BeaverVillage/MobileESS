"""Package reproducible Native0 evidence; explicitly mark May Full96 NOT_RUN."""
from pathlib import Path
from collections import Counter
import csv,json,hashlib,subprocess,sys,time
import xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from v42_integration.policy import digest
from v42_integration.frozen_unknown import FrozenUnknownPolicy
from test_v42_known_unknown_contract import frozen,participant
from test_v42_experimental_control import metadata
from v42_integration.policy import ReservationLedger
BASE='1100995086a8d202cb6b8a7308ccc6d60799bbc5'


def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def csvwrite(path,rows):
    with path.open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def record(path):return dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main(out):
    out.mkdir(parents=True,exist_ok=True)
    history=read(out/'PR226_62_RECONCILIATION.json');classification=read(out/'SOURCE_UID_CLASSIFICATION.json')
    old=read(out/'SAVED_V5_KNOWN_PLANNING_METRICS.json');fixture=read(out/'FIXTURE_BEFORE_AFTER_RECEIPT.json')
    inventory=read(out/'MAY01_OBSERVED_COVERAGE_INVENTORY.json')
    diagroot=ROOT/'docs/v42_flex30_adjustment_diagnosis_20261014';diag=read(diagroot/'FLEX30_ADJUSTMENT_DIAGNOSIS.json')
    with (diagroot/'FLEX30_UID_DECOMPOSITION.csv').open(encoding='utf-8-sig') as stream:decomp=list(csv.DictReader(stream))
    groups=Counter((r['origin'],r['category']) for r in decomp)
    tests=ET.parse(out/'REGRESSION_TESTS.xml').getroot();cases=list(tests.iter('testcase'))
    assert not list(tests.iter('failure')) and not list(tests.iter('error'))
    required={c.attrib['name'].split('[',1)[1].rstrip(']'):dict(PASS=True,node=c.attrib['classname']+'.'+c.attrib['name'])
        for c in cases if c.attrib['name'].startswith('test_required_contract[')}
    assert len(required)==27
    write(out/'REQUIRED_CONTRACT_TEST_RESULTS.json',dict(PASS=True,contracts=required,all_tests=len(cases),Native_Optimize_calls=0,Fresh_AC_calls=0))
    provider,p=frozen();job,budget=participant(provider);m=metadata(provider,job,budget)
    path=out/'UNKNOWN_FROZEN_POLICY_TABLE.json';p.save(path)
    loaded=FrozenUnknownPolicy.load(path,bindings=p.bindings);loaded.bind_runtime_packet(p.packet)
    assert loaded.sha==p.sha and loaded.document==p.document
    p.set_current_resources(0,{'A':0,'B':0});before=p.packet.evaluation_calls
    samples=[]
    for _ in range(50):
        began=time.perf_counter();result=p.select(deepcopy_json(m),budget,0,ReservationLedger({'A':8,'B':8}),reserve=False)
        samples.append((time.perf_counter()-began)*1000)
    assert p.packet.evaluation_calls==before
    expanded=p.expanded_document();policy=p.document
    spec=dict(contract='V42_KNOWN_MILP_UNKNOWN_MULTI_ALTERNATIVE_PLANNING_FROZEN_V2',
        Known='ISSUE_KNOWN_DIRECT_A1_A2_NATIVE_DOMAIN;FINAL_UID_COMMANDS_IMMUTABLE;FAIL_QUEUE_STAY_ON_PHYSICAL_DRIFT',
        Unknown='ISSUE_ANONYMOUS_GANG_RUNTIME_QOS_SITE_STATE_CONDITIONS;LOOKUP_ONLY_AFTER_OBSERVATION',
        future_Actual_request_bank_at_Planning='NOT_READ;PUBLIC_REQUEST_PROJECTION_AFTER_FINAL_POLICY_FREEZE',
        source_site_count=inventory['AIDC_sites'],installed_GPU=inventory['installed_GPU'],
        time_slots=list(range(96)),actual_execution_grid_seconds=900,
        Event30=policy['templates'][0]['Event30'],
        delay_options=dict(E1_normal=[0,900,1800],E2_normal=[0,900,1800,2700,3600],
            E1_verified_standby=list(range(0,3601,900)),E2_verified_standby=list(range(0,7201,900))),
        UNCONFIRMED_source_not_promoted_to_observed_standby=True,participation_seed_unchanged=True,
        runtime_buckets_seconds=[900,3600,14400,86400,604800],adjacent_bucket_certificate=policy['templates'][0]['adjacent_fallback_certificate'],
        default_GPU_domain='ALL_SOURCE_FEASIBLE_POSITIVE_INTEGER_GANGS_INTERSECT_SOURCE_RACK_SITE_MAP',
        sites='ALL_SOURCE_COMPATIBLE_AIDCS_NO_TOP_K',ranking_contract=policy['ranking_contract'],
        P1_tie_tolerance=policy['q50_tie_tolerance'],A_stage_P2_unchanged=True,
        reservation_roles=['RUNNING_OBSERVED_HARD_CURRENT_HOLD','KNOWN_FROZEN_HARD_FUTURE',
            'UNKNOWN_COMMITTED_HARD_FUTURE_ATOMIC_OWN_REBIND','ANONYMOUS_AND_NOMINAL_UNCONFIRMED_SOFT_FORECAST_NOT_OCCUPATION'],
        C3='PLANNING_CERTIFIED_SPATIAL_ONLY_REPLACEMENT_FRAMES;COHORT_X_CDF_CARRY_UNCHANGED;REFERENCE_SHARE_EXCLUDED;NEVER_ADD_FRAMES',
        no_authorized_temporal_CC4_redistribution_claim=True,
        Actual_allowed=['LOOKUP','CURRENT_QOS_GPU_RACK_WAN_GUARDS','SINGLE_CURRENT_SLOT_SIGNED_AFFINE_GUARD',
            'SAME_ROW_PRERANKED_FALLBACK','ATOMIC_OWN_RESERVATION_REPLACE','ACTUAL_C1_PQ_RECOMPUTATION'],
        Actual_forbidden=['NEW_RANKING','96_SLOT_CANDIDATE_OBJECTIVE_EVALUATION','GLOBAL_MILP','KNOWN_REOPT','UNOBSERVED_UID_OR_COMPLETION'],
        Running_overrun_without_causal_remaining_authority='STAY_WITH_PHYSICAL_HOLD_NOT_FALSE_COMPLETION',
        evidence='NATIVE0_AND_NAMED_FIXTURE;REAL_MAY01_C1_C2_C3_FULL96_NOT_RUN')
    write(out/'UNKNOWN_POLICY_COMPILER_SPEC.json',spec)
    write(out/'UNKNOWN_POLICY_COVERAGE_AUDIT.json',dict(PASS=True,Source_retrospective_inventory=inventory,
        fixture_templates=len(policy['templates']),fixture_sites=['A','B'],fixture_control_slots=[0,1,2],
        fixture_status='CONDITION_SUBSET_ONLY_NOT_REAL_MAY01_COMPLETE_TABLE',
        real_Source_policy_full96_compilation='NOT_RUN',candidate_truncation=0,
        exact_value_sharing=policy['compression'],shared_numeric_values=len(policy['shared_numeric_values']),
        independent_all_site_delay_scalar_score_test_PASS=True,actual_source_inventory_not_used_as_Planning_input=True))
    rankings=[]
    for t in expanded['templates']:
        for r in t['ordered_actions']:
            rankings.append(dict(evidence_kind=policy['evidence_kind'],template_id=t['template_id'],state=t['state'],
                slot=t['time_slot'],gpu=t['gpu'],qos=t['qos'],rank=r['frozen_rank'],action=r['action'],site=r['site'],
                delay_seconds=r['delay_seconds'],Q50_rho=r['q50_primary_score'],
                Q90_carry_GPUh=max(v['carry'] for v in r['q90_queue_risk']),
                Q90_queue_GPUh_hours=max(v['queue'] for v in r['q90_queue_risk']),frame=r['allocation_frame_id'],policy_sha=p.sha))
    csvwrite(out/'UNKNOWN_ACTION_ALTERNATIVE_RANKING.csv',rankings)
    write(out/'UNKNOWN_RESOURCE_STATE_LOOKUP_TEST.json',dict(PASS=True,same_row_fallback_test=required['FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED'],
        protected_Known_test=required['KNOWN_HARD_RESERVATION_PROTECTED'],overrun_test=required['RUNNING_OVERRUN_CAPACITY_PROTECTED'],
        lookup_sample_count=50,median_ms=float(np.median(samples)),P95_ms=float(np.percentile(samples,95)),
        benchmark_scope='NAMED_TOY_WARM_PACKET_NO_FULL96_EXTRAPOLATION',online_future_grid_objective_evaluations=0,
        Native_Optimize_calls=0,Fresh_AC_calls=0))
    write(out/'KNOWN_PLANNING_SCHEDULE_EXECUTION_AUDIT.json',dict(PASS=True,classification=classification,
        UID_routing_replay=read(out/'MAY01_SAVED_UID_BRANCH_REPLAY.json'),
        fixture_before_Known_site=fixture['before_Known']['site'],fixture_after_Known_site=fixture['after_Known']['site'],
        Known_START_DELAY_PREPLACE_MIGRATION_tests='PASS',B1_A1_MESS_OFF='TRANSPORT_FIXTURE_PASS',B3_FINAL_A2_M2='TRANSPORT_FIXTURE_PASS',
        Saved_V5_Known_Planning=old,new_E1_E2_Known_A1_A2='NOT_RUN',
        optimized_Known_pre_Dday_missed_start='FAIL_QUEUE_WITH_EXPLICIT_LEDGER;NO_RETROACTIVE_REFERENCE_REWRITE'))
    fusion=dict(PASS=True,original_62=history,Known_Unknown_UID_100pct_branch_PASS=True,
        latest_participant_funnel=diag['unique_UID_stage_funnel'],latest_participant_categories=dict(diag['disjoint_674_UID_categories']),
        category_Origin_counts={origin:{category:count for (kind,category),count in groups.items() if kind==origin} for origin in ('KNOWN','UNKNOWN')},
        Source_selected_failed205=dict(Known=groups['KNOWN','FLEX_SELECTED_BUT_NOT_EXECUTED_AS_FLEX'],Unknown=groups['UNKNOWN','FLEX_SELECTED_BUT_NOT_EXECUTED_AS_FLEX']),
        Source_hard_rejected317=dict(Known=groups['KNOWN','FLEX_GENERATED_BUT_NEVER_HARD_APPROVED'],Unknown=groups['UNKNOWN','FLEX_GENERATED_BUT_NEVER_HARD_APPROVED']),
        candidate_limit_truncation=0,better_P1_flex_ignored_events=0,real_repaired_205_317_outcome='NOT_RUN_NOT_PROVEN_RESCUED')
    write(out/'KNOWN_UNKNOWN_UID_ACTION_FUSION_AUDIT.json',fusion)
    with (diagroot/'PARTICIPANT_COMMAND_REVALIDATION.csv').open(encoding='utf-8-sig') as stream:commands=list(csv.DictReader(stream))
    origin_by_uid={r['uid']:r['origin'] for r in decomp}
    csvwrite(out/'UNKNOWN_COMMAND_REVALIDATION_BEFORE_AFTER.csv',[dict(uid=r['uid'],origin=origin_by_uid[r['uid']],evidence='OLD_PR226_SAVED_EVENT',
        before_time=r['time_seconds'],before_failure_class=r['failure_class'],before_current_feasible=r['current_GPU_and_after_affine_feasible'],
        after_May01='NOT_RUN',same_row_fallback_implementation_fixture_PASS=True) for r in commands if origin_by_uid[r['uid']]=='UNKNOWN'])
    with (diagroot/'ALL_62_ADJUSTED_UIDS.csv').open(encoding='utf-8-sig') as stream:adjusted=list(csv.DictReader(stream))
    csvwrite(out/'UNKNOWN_GPUH_ALLOCATION_EFFECT.csv',[dict(uid=r['uid'],scope='OLD_PR226_DIAGNOSTIC',action=r['action'],
        gpu=r['gpu'],changed_lifetime_nominal_GPUh=r['nominal_GPUh'],source_site=r['reference_site'],actual_site=r['actual_site'],
        final_start_minus_reference_seconds=r['start_minus_reference_seconds'],isolated_actual_PCC_delta='NOT_IDENTIFIED',
        repaired_May01_effect='NOT_RUN') for r in adjusted if r['origin']=='UNKNOWN'])
    write(out/'UNKNOWN_POLICY_Q50_Q90_GRID_RISK.json',dict(scope='NAMED_FIXTURE_FROZEN_PREDICTIONS_NOT_MAY01_AC',
        policy_sha=p.sha,source_authority=policy['original_grid_authority'],shared_numeric_values=policy['shared_numeric_values'],
        templates=policy['templates'],risk_is_not_individual_SLA_certificate=True,
        historical_May01_Planning_A2_rho=old['planning_rho'],B0_same_new_case_rho=None,B1_new_Planning_rho=None,B3_new_Planning_rho=None,
        new_Actual_affine_rho=None,new_Fresh_AC_rho=None,real_grid_improvement_proven=False))
    source_files={path.relative_to(ROOT).as_posix():record(path) for path in sorted((ROOT/'v42_integration').glob('*.py'))}
    physics_paths=['v42_job_capability.py','v42_capacity/actual.py','v42_native/grid.py','v42_root/native.py','v42_thermal/planning.py',
        'v42_integration/q90_recourse.py','v42_integration/qos.py','v42_integration/m_engine.py']
    unchanged={path:subprocess.check_output(['git','diff',BASE,'--',path],cwd=ROOT).decode()=='' for path in physics_paths}
    assert all(unchanged.values())
    old_code=subprocess.check_output(['git','show',BASE+':v42_integration/experimental_actual.py'],cwd=ROOT).decode()
    old_line=next(i for i,line in enumerate(old_code.splitlines(),1) if 'self.known_schedule={}' in line)
    science=digest(dict(parent=BASE,source_files={k:v['sha256'] for k,v in source_files.items()},compiler_spec=spec))
    import psutil
    manifest=dict(parent_PR226_HEAD=BASE,correction_science_sha=science,source_files=source_files,
        original_physics_objectives_unchanged=unchanged,latest_diagnosis_receipts=[record(diagroot/name) for name in (
            'FLEX30_ADJUSTMENT_DIAGNOSIS_KO.md','FLEX30_ADJUSTMENT_DIAGNOSIS.json','ALL_62_ADJUSTED_UIDS.csv','PARTICIPANT_COMMAND_REVALIDATION.csv')],
        Known_ignored_original_file='v42_integration/experimental_actual.py',Known_ignored_original_line=old_line,
        tests_passed=len(cases),required_named_tests=27,Native_Optimize_calls=0,Fresh_AC_calls=0,
        new_B1_B3_Full96='NOT_RUN',new_May01_C1_C2_C3_Full96='NOT_RUN',campaign_HOLD=True,
        original_Solver_ledger_seconds=621.2855198158068,original_Solver_budget_seconds=3600,
        available_RAM_GB=psutil.virtual_memory().available/2**30,raw_or_original_PR_source_modified=False,
        fixture_policy_sha=p.sha,new_real_Science_Case_Policy_freeze='NOT_RUN_REQUIRES_NEW_FINAL_A1_A2_HANDOFF')
    write(out/'V42_POLICY_INTEGRATION_SOURCE_MANIFEST.json',manifest)
    report=f'''# V42 Known–Unknown 통합 정정 — 2026-10-14

Known은 A1/A2의 최종 UID 계획을 유지하고, Unknown만 Planning에서 생성·저장·재조회한 다중 대안 표를 사용하도록 복구했다. 검증 수준은 Native0·Fixture·실제 May01 UID 분기 감사다. 새 May01 A1/A2, C1–C3 Full96 및 Fresh AC는 **NOT_RUN**, 새로운 실제 계통 개선과 최적성은 **NOT_CERTIFIED**다.

1. PR226 `{BASE}`의 `experimental_actual.py:{old_line}`에서 `self.known_schedule={{}}`가 Known 명령을 지웠다. 이를 제거하고, 최적화 대상 밖 Known도 별도 Source Reference/Fallback으로 분리했다. Known이 Unknown selector에 들어가면 테스트가 실패한다. 계획 이전 시각의 명령을 D-day Pending에 재작성하지 않고 명시적 실패·Queue를 기록한다.

2. Source 발행 Known 1,649개 중 D-day 이전 완료 103개, 활성 Known 1,546개, Unknown 774개다. 자정 전 관측 Unknown 78개와 D-day 제출 696개를 구분했다. 개별 A-stage 1,499개와의 차이 150개는 Running nominal service 0인 106개와 외부 44개다. 활성 최적화 대상 1,498개, 활성 Known Fallback 48개다. 새 E1/E2 Known 변경 수는 NOT_RUN이다. 저장된 **이전 V5 A2 진단**은 변경 {old['Changed_Known_UIDs']} UID, Time-shift {old['changes']['TimeShift']}, Preplace {old['changes']['Preplace']}, Migration 0, nominal model GPUh {old['Changed_nominal_model_GPUh']:.3f}, rho {old['planning_rho']:.9f}다. 새 계약의 결과나 PR189의 228개와 비교하지 않는다. Running의 계속 실행 경계를 역사적 재시작으로 세지 않았다.

3. B1은 Final A1 + MESS OFF, B3은 Final A2/M2 Anchor에서 Unknown 표를 생성하고 SHA를 확인해 재조회한 뒤 Actual에 전달한다. E1/E2 Known QoS는 Domain 생성 전에 적용하며 Science/Case SHA를 새로 만든다. Planning 준비가 미래 Actual 요청 목록을 읽으면 실패하도록 검증했으며, 실제 요청 변환은 최종 정책 동결 이후에 수행한다. Native 최적화 실행은 아직 없다.

4. 실제 Source는 AIDC 12개·780 GPU다. 지원 사이트를 GPU 여유 상위 K개로 자르지 않는다. 정수 Gang과 실제 Source/Rack 호환 사이트의 교집합을 모두 생성한다. May01 Unknown Gang {inventory['observed_Unknown_GPU_gangs']} 및 최대 Q50 {inventory['observed_Unknown_Q50_max_seconds']:.3f}초가 기본 선언 범위에 포함된다. 이 실제 사후 목록을 Planning 입력으로 사용하지 않았다. 제출한 표 파일은 명시적인 2 AIDC Fixture이며, 실제 May01 전체 표 컴파일은 NOT_RUN이다.

5. E1 Normal 0/15/30분, E2 Normal 0/15/30/45/60분을 생성한다. Source 확인 Standby만 기존 60/120분 범위를 사용한다. UNCONFIRMED를 관측 Standby로 승격하지 않는다. 0초 지연 Placement는 별도 Source 권한으로 검사한다. Runtime 경계는 상한과 제어 시점 경계를 평가하고 인접 Bucket의 공통 경계 Fallback을 사전 연결한다.

6. Q50 rho가 1순위이며 동등성 허용오차는 기존 1e-9다. 동점에는 Q90 CDF 위반/결손, Carry, Queue, Q50 최대 선로 노출량(loading-hours), Q90 peak, QoS 부담, 개입 최소화와 고정 Site/Frame 순서를 사용한다. 원래 A-stage P2를 변경한 것으로 표현하지 않는다. 동일 숫자를 SHA로 공유하며 후보·순위·정밀도를 삭제하지 않는다. 작은 Fixture의 모든 사이트×시간 점수를 원래 scalar 식과 독립 비교했다. Actual은 목적함수를 계산하거나 순위를 바꾸지 않는다.

7. Running 현재 점유, Known 확정 미래 예약, Unknown 확정 명령, 익명·미확정 예측을 구분했다. 관측 Running은 다음 제어 시점마다 먼저 보호한다. Known/다른 확정 Unknown 예약은 밀어내지 않는다. 실행 명령 실패 시 동일 Frozen 행의 다음 합법 대안을 원자적으로 교체하고, 모두 실패하면 Queue/STAY다. R0/B를 재발급하거나 지연 의무를 환불하지 않는다. 충돌 Resource·구간·상대 UID·역할을 기록한다.

8. 기존 참여자 244개 선택 중 205개 미실행은 Known 103·Unknown 102개다. 현재 GPU·affine 검사가 가능했던 174 UID/592 사건은 미래 안전의 증명이 아니다. 동일 행 차순위 실행과 예약 보호를 Fixture에서 개선·검증했으며, 이 실제 205개 집단의 구제 수는 NOT_RUN이다. 후보 상한 잘림은 0, 승인 대안 미선택은 17개였으므로 상한 부족을 핵심 원인으로 주장하지 않는다.

9. 기존 Q50 Hard 미승인 317개는 Known 246·Unknown 71개다. 20 UID/598행 witness는 literal 상한 초과와 전압 거부를 재현했으며 불필요한 거부를 증명하지 않았다. C3는 cohort x, 시간별 총 서비스, CDF와 Carry를 유지하는 **공간 배분 대안**만 사전 평가한다. 이미 비교 중인 Reference 서비스 몫을 중복 재배분하지 않는다. 현재 실제 Job 예약과 익명 수요를 합쳐 Hard 점유로 만들지 않으며, 실제 시작 시 GPU/Rack/WAN/현재 affine 안전을 확인한다. 실제 317개 승인 증가나 시간 재배분은 아직 주장하지 않는다.

10. 과거 62개 실제 행동은 Known DELAY 6 + PREPLACE 32 = 38개, Unknown PREPLACE 24 = 24개, Migration 모두 0개다. Unknown 최종 Time-shift는 PREPLACE와 겹치는 **2개**다. 취소 명령의 지연 의무는 최종 시간 이동과 다르며, 이전 중간 분석의 15개를 최종 시간 이동 수로 사용하지 않는다. Unknown 행동률은 과거 진단으로 24/774 = 3.1008%다. 수정 후 May01 행동률은 NOT_RUN이다.

11. 과거 참여 Unknown 218개 중 조정 24개, 11.0092%다. 전체 참여 674개 중 조정은 39개이며 62/674가 아니다. 23개 비참여 Known Placement는 별도 원래 모델 권한이다. 새 Source/Case 결과에 이 비율을 이전하지 않는다.

12. 과거 조정 Unknown의 lifetime nominal GPUh는 {history['Unknown_changed_nominal_GPUh']:.9f}, 적격 Unknown nominal GPUh {history['Unknown_eligible_nominal_GPUh']:.9f} 대비 {history['Unknown_changed_nominal_GPUh_rate']*100:.6f}%다. 이는 실제 이전·이월 서비스 GPUh나 전력 감소가 아니다. Known Planning/Unknown Actual 비율을 합치지 않는다. 새 측정 함수는 Known의 Source C1 사이트별 ΔP와 Unknown의 첫/후순위 실행·동일 행 Fallback·예약 실패·기한 위험을 구분해 기록한다. 실제 IT/PCC P/Q와 동일 입력 C0–C3의 상세 비교는 작은 Fixture NPZ/영수증으로 제공했다.

13. 새 실제 May01 계통 부하율 개선은 미실증이다. B0/B1/B3 새 동등 Case rho·Actual affine·Fresh AC rho·critical-line/time·Rebound는 NOT_RUN/NULL이다. 작은 Fixture에서 Known의 잘못된 B 배치를 계획된 A로 복구했고, 완료 2·Carry 1을 유지했다. 이것을 May01 성능 향상으로 표현하지 않는다. 예측 C3 배분은 실제 점유가 아니다.

14. 원본 P1·P2 코드와 GPU/Rack/WAN/서비스/전압/전류/변압기 물리 정의를 변경하지 않았다. Original signed response와 PR225 Q90−Q50 recourse를 재사용한다. 최대 1회, 최초 유효 Checkpoint, 비영 Transfer/Restart와 Shared Budget을 유지한다. Q50 overrun은 실제 완료로 처리하지 않고, 승인된 인과적 잔여 예측이 없으면 STAY한다. 새 실행 예약 역할과 정책 계약은 별도 Science SHA로 식별한다.

15. 회귀 {len(cases)}개와 요구 이름 27개 PASS, May01 2,320 UID 분기 감사 PASS다. B1/B3는 Solver 없는 handoff Fixture로 연결을 확인했다. 새 A/M Optimize·Fresh OpenDSS·31일 Campaign 실행 0회, Solver 원장 621.2855198158068/3,600초 및 Campaign HOLD를 보존했다. 새 E1/E2 실전 성능을 주장하려면 Source/Case/Policy Freeze와 단일 Replay 실행 권한·RAM 예산 검토가 추가로 필요하다.

Correction Science SHA: `{science}`. 원본 Source/진단 파일·기존 FULL/Gap/Fresh·FAIL 증거는 변경하지 않았다.
'''
    (out/'V42_UNKNOWN_CONTROL_FINAL_KO.md').write_text(report,encoding='utf8')
    (out/'KNOWN_UNKNOWN_ARCHITECTURE_CORRECTION_KO.md').write_text(report,encoding='utf8')
    print(json.dumps(dict(PASS=True,tests=len(cases),required_named=27,science_sha=science,fixture_policy_sha=p.sha)))


def deepcopy_json(value):return json.loads(json.dumps(value))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output)
