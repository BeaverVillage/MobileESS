"""Assemble scoped D0 results without modifying historical scientific artifacts."""
from pathlib import Path
import csv
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.d0_case import REPORT,require_case,read
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.unified_resource import UnifiedResearchBudget


def main():
    manifest=read(REPORT/'D0_CASE_MANIFEST.json');require_case(manifest)
    pilot=read(REPORT/'A1_PILOT01/PILOT_RESULT.json')
    a=read(REPORT/'A1_PILOT01/SOLVE/A_RESULT.json')
    matrix=read(REPORT/'FINAL_NATIVE0/NATIVE0_MATRIX_RECEIPT.json')
    revision=read(REPORT/'FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json')
    if revision['status']!='PASS' or revision['current_identity']!=manifest['identity']:
        raise ValueError('D0_SOURCE_REVISION_EXACT_MODEL_PROOF_REQUIRED')
    regression=read(REPORT/'REGRESSION01/REGRESSION_RESULTS.json')
    if regression['status']!='PASS':raise ValueError('D0_FINAL_NATIVE0_REGRESSION_REQUIRED')
    before=read(REPORT/'A1_PILOT01/NATIVE_LEDGER_BEFORE.json')
    budget=UnifiedResearchBudget();after=read(budget.path)
    assert after['calls'][:len(before['calls'])]==before['calls'] and after['inflight'] is None
    budget.verify_parents()
    audit=ROOT/'runtime/D0_AUDIT_20261015'
    for name in ('D0_FORECAST_CAUSALITY_AUDIT.json','D0_PUBLIC_BACKLOG_SOURCE_AUDIT.json',
        'BASELINE555_RESULT.json','MESS_NEW_TESTS_RESULT.json','PRIOR_TRACKED_REPORT_BYTE_AUDIT.json',
        'NATIVE_BUDGET_PRESERVATION_AUDIT.json','INDEPENDENT_D0_CHANGE_REVIEW.json',
        'PILOT_SOURCE_REVISION_AUDIT.json','ACTUAL_CODE_SOURCE_BINDING_AUDIT.json'):
        source=audit/name
        if source.exists():shutil.copyfile(source,REPORT/name)
    _write(REPORT/'UNIFIED_NATIVE_LEDGER.json',dict(status='PASS',scope='CANONICAL_APPEND_ONLY_ACCOUNTING',
        canonical=file_record(budget.path),ledger=after,previous_used_seconds=before['conservative_solve_seconds'],
        used_seconds=budget.used(),limit_seconds=after['limit_seconds'],remaining_seconds=budget.remaining(),
        new_native_seconds=pilot['Native_used_seconds'],new_calls=1,pilot_cap_seconds=25.,
        actual_overshoot_seconds=pilot['Native_used_seconds']-25.,return_reserve_seconds=30.,
        old_calls_prefix_preserved=True,old_parent_ledgers_unchanged=True,
        D0_call_has_distinct_identity=True,new_session_budget_not_created=True,
        usage_reset=False,Heavy_workers=1,Threads=1,new_AC_calls=0))
    stage_rows=[dict(stage='A1_CURRENT_SOURCE',model='PASS_NATIVE0_EXACT_MATH_EQUIVALENCE',native='NOT_RUN',FULL='NOT_RUN',
        reason='NO_BOUND_OR_PRIMAL_TRANSFER',case_sha=matrix['case_sha']),
        dict(stage='A1_PILOT_SOURCE_REV1',model='PASS_NATIVE0',native='EXECUTED_TIME_LIMIT',FULL='NOT_CERTIFIED',
        reason='NO_FULL_PRIMAL',case_sha=a['case_sha']),
        dict(stage='A1_P2_SOURCE_REV1',model='ORIGINAL_LEX_OBJECTIVES_RETAINED',native='NOT_RUN',FULL='NOT_CERTIFIED',
        reason='P1_NOT_CERTIFIED',case_sha=a['case_sha'])]
    for stage in ('M1','A2','M2','D0_K48','Actual_First_Event','Actual_Short_Canary','Actual_16','Actual_96','Fresh_AC_11SVR'):
        stage_rows.append(dict(stage=stage,model='UPSTREAM_HANDOFF_REQUIRED',native='NOT_RUN',FULL='NOT_RUN',
            reason='CURRENT_D0_FULL_A1_AND_FINAL_A2_M2_NOT_ESTABLISHED',case_sha=''))
    with (REPORT/'D0_STAGE_EXECUTION_STATUS.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(stage_rows[0]));writer.writeheader();writer.writerows(stage_rows)
    ids=manifest['identity'];remaining=budget.remaining()
    science=f'''# D0 May01 Science/Case

평가 Issue와 시작은 승인 초기 상태의 2025-05-01 00:00, 종료는 2025-05-02 00:00이다. 원본 Source의 UTC+10 시각을 유지하며 96×900초를 평가한다. Epoch 시작은 {manifest['time_axis']['evaluation_begin_seconds']:.0f}이다. 새 계획의 상태 조건은 D0에서 공개된 관측 초기 정보다.

- Science SHA: `{ids['science_sha']}`
- Case SHA: `{ids['case_sha']}`
- Source SHA: `{manifest['source_sha']}`
- Current A1 Stage Case SHA: `{matrix['case_sha']}`
- Executed Pilot Source Rev1 A1 SHA: `{a['case_sha']}`
- Initial semantic SHA: `{ids['initial_state_sha']}`
- Initial byte SHA: `{manifest['initial_record']['sha256']}`

원본 초기 파일 6,973,987 bytes를 검증했다. Running324/472GPU와 Pending1300, 사이트·Gang·Elapsed·Episode를 보존했다. 원본 사이트151/296GPU, PR12920/20GPU, PR125153/156GPU 및 활성에서 제외된44를 변경하지 않았다. 이 사이트 배치는 승인된 모델 초기 상태이며 Kestrel 관측 사이트라고 주장하지 않는다.

모든 활성1624UID의 공개 Submit/Status로 D0 Known을 분류했다. 기존 D−1 Unknown78(23Running/55Pending)은 새 Known이다. D−1 Known1649 중103은 이미 완료되어 새 활성 모집단은1624다. 미래 Unknown 개별 UID/실현 완료시간을 Planning에 사용하지 않았다.

기존 내부 Native[24,120)는 새 D0 평가[0,96)에 명시적으로 대응한다. Native24는 D0이며, 0~23은 평가에 사용하지 않는 내부 좌표다. 과거 6시간 실행 영수증을 이 Case의 Gate로 사용하지 않는다. 과거253/886/888의 불일치, Full96/Fresh 및 Prefix NOT_CERTIFIED 결과는 역사 자료로 보존한다.

초기 Running255/285GPU는 양의 Q50 잔여 서비스로 표현하고, Q50가 이미 만료된69/187GPU는 D0 현재 슬롯에서 물리 점유를 유지한다. 이는 실제 완료가 아니다. Actual은 모든324를 실제 완료 이벤트까지 유지한다. 현재 만료 Gang의 Runtime 위험 Target38.06103955552418GPU 중복만 제외했고 미래 위험 계수는 원본 그대로다. Achieved CC4/Runtime Reserve는 결정변수이며 0으로 고정하지 않았다.

Pending1300을 D0 이후 Source 호환 사이트와 96개 시작 슬롯에서 최적화하도록 원본 F2-CRA에 입력했다. 연구 Backlog 기본 창은85500초이고 추가 의도적 지연은0이다. 원본 기다림/Release/Hard Deadline/보호 정보는 별도로 보존한다. 고객 SLA 및 보호 계약 충족을 인증하지 않는다. 확인되지 않은 Checkpoint 권한은 HOLD이며 이 기본 행동 도메인을 과거 무제한 Migration 도메인과 동일시하지 않는다.

원본 CC4 May01 row412를 그대로 재사용했다. 선언된 발행은 Apr30 18:00(UTC08:00), D0보다21600초 전이다. Q50합5503.441472156033GPUh, Q90합24408.063227293504GPUh이다. 초기78은 May01 도착 예측 cohort보다 앞서 제출되어 예측에서 차감하지 않는다. Saved feature71개 및 TRAIN400일의 as-of를 재검증했고 미래 학습 label0이었다. 예측 선택은 회고 연구 계약이다. 실제2025 운영 ingestion 및 checkpoint byte 가용성은 NOT_CERTIFIED다. Scaling/Clipping/Refit은0회다.

IEEE123, AIDC12/GPU780, 설치SVR11/원래RegControl7을 유지한다. 원본 day bundle에서 Source가 승인한 동일 day의 current electrical_certificate/grid_outputs/route_table 세 필드만 명시적으로 병합했다. Route bytes는 동일하며 수량/CC4/Runtime/Rack을 바꾸지 않았다. Source Raw를 덮어쓰지 않았다.

새 A1 Native0 모델은 {matrix['rows']:,}행/{matrix['columns']:,}변수/{matrix['nonzeros']:,}NNZ이다. Original P1/P2 layer와 전체 남은 서비스/CDF/Carry, GPU/Rack/WAN/Grid 제약을 유지한다. Source Rev1의25초 Pilot에서 실제 Native{pilot['Native_used_seconds']:.6f}초를 사용했으나 정수 incumbent0으로 FULL 실행 가능성 및 최적성은 NOT_CERTIFIED다. Phase I/전체 Migration Pricing 인증은 미확립이며 기존 인증을 이전하지 않는다.

Pilot 이후 명령의Native좌표·FULL bool·반환예산finite 검증과M단계의stage/anchor·성공한M1registry→A2 전달 검증을보강했다. Rev1 Source13파일과9개Case자료를`A1_PILOT01/EXECUTED_CASE`에Byte-identical 보존했고 원장은수정하지않았다. 현재Source를Native0로다시생성해Matrix SHA `{revision['current_binding']['matrix_sha']}` 및전체domain/objective SHA `{revision['current_binding']['domain_sha']}`가Rev1과동일함을확인했다. Source/Science/Case는새로구별한다. 현재Source Native호출0이며 Rev1 bound/primal/최적성인증을현재Case로이전하지않는다.

M1/A2/M2와 Actual은 현재 D0 FULL 계획의 Source/Case/Anchor를 확보한 후 진행한다. 과거 A1/A2, MESS UB/LB나 FCFS 진단 계획을 대신 입력하지 않는다. Actual 최종 실행에는 A2/M2가 필요하다.
'''
    (REPORT/'D0_MAY01_SCIENCE_CASE_KO.md').write_text(science,encoding='utf8')
    answers=[
        ('6시간 Prefix 없이 초기 상태 사용','PASS. 승인 원본의 Byte/semantic을 독립 확인하고 새 D0 Issue로 사용했다. 내부24오프셋은 좌표 변환이며 평가에6시간을 추가하지 않는다.'),
        ('324 Running /472GPU/1300Pending 불변','PASS. 사이트/Gang/Elapsed/Episode 및 완료44 제외를 보존했다. 상세 classification1624행과 initial authority를 확인한다.'),
        ('미복원 Prefix Gate 제외','PASS. 새 manifest에서 historical_prefix_gate_excluded=true. 이전 Prefix 인증은 NOT_CERTIFIED로 보존하며 새 Gate에 적용하지 않는다.'),
        ('Runtime·QoS/Deadline 보존','PASS 입력 보존. 실제 기다림, 원본 Q50/Elapsed/Hard metadata를 유지했다. Source protected/batch와 요청 proxy의 미확인성은 그대로이며 연구85500초 창은 실제 SLA가 아니다. 만료 Hard를 자동 연장하지 않는다.'),
        ('공개 정보 Known 분류·스케줄링','분류PASS:1624Known, 기존Unknown78 재분류. 합법 D0 Scheduling 도메인을 생성했으나 실행 가능한 최적 Known 계획은 NOT_CERTIFIED. 미래UID/완료 Planning 사용0.'),
        ('Known+CC4 A1 생성','Native0 모델PASS:844129행36931변수10920902NNZ. Known/UnknownQ50/Target/achieved reserve/shortfall/CDF/carry를 구별했다. Native Pilot은 실행했으나 계획 incumbent을 확보하지 못했다.'),
        ('A1/A2 FULL 및 최적성','Executed Rev1 A1 NOT_CERTIFIED:status9/Solution0. Executed Rev1 고정-MESS A행렬의 진단 ObjBound0.08280107490283846만 기록하며 현재Case Bound 또는 Joint Global LB로 쓰지 않는다. P2 호출0/NOT_RUN. 최종Source Native 및A2 NOT_RUN. Native FULL-feasible 또는 Global Optimality 인증을 주장하지 않는다.'),
        ('현재GPU·전체Signed Sensitivity Unknown','원본 CurrentEvent 알고리즘과 회귀PASS. 현재GPU/Rack/원본C1 P/Q/전체선로상 Signed minimax로 선택하며 미래Known 잠재예약을 사전veto로 쓰지 않는다. 실제D0배치는 NOT_RUN.'),
        ('실제Pending Known Pre-placement','Native0 원본 교정 회귀PASS. 실제Start+Pending+현재GPU충돌만 trigger, Source/데이터/WAN/준비/권한 재검증 후 atomic allocation한다. 실제D0교정은 NOT_RUN; 확인되지 않은 권한은 부여하지 않는다.'),
        ('Unknown Site Change UID/GPUh','실제D0 NOT_RUN. UID수와GPUh는 null이며0으로 보고하지 않는다. AIDC_ACTUAL_ALLOCATION_RESULTS.csv는 실제 이벤트가 없어 헤더만 포함한다.'),
        ('C0/C1/C2 실제 최대부하','세 군 모두D0 NOT_RUN/부하null. 같은 초기 상태/Planning/CC4/외생조건 계약을 공유하고 실제Known교정 결과는 정책별로 달라질 수 있다. 기존 named fixture를 실제 May01 성능으로 이전하지 않는다.'),
        ('Short/Overrun·Queue/Carry','원본회귀PASS:실제완료 전 Running보호/완료GPU해제/안전Backfill/Queue와서비스carry. Planning/Online allocator에 미래완료를 노출하지 않는다. Private simulator는기존Truth bank를보유한다. 새로운D0 측정은 NOT_RUN.'),
        ('11-SVR Fresh AC','새D0 NOT_RUN. 역사 V5 Original Full96/Fresh receipt는 초기화/현재D0 계획과 별개로 보존:활성2320/완료1690/Carry630, GPU위반0/Drop0, 설치11SVR/기존7RegControl. 과거Prefix 불일치 인증은 이전하지 않는다.'),
        ('공식MESS UB 유지','PASS. Adaptive Beam→4대Joint MILP→Original FULL→Incumbent Registry를 유지. Direct Compact 기본, experimental compression/cache 기본비활성 유지.'),
        ('K48 공식Global LB','PASS 방법유지. 신규D0 K48 Native와Global LB/gap은NOT_RUN/null. DW/S1/restricted Joint를 공식 방법으로 대체하지 않았다.'),
        ('S1 Route와Mode 원인 분리','저장Root의Arc4307/Mode192 분수, 다중위치187/동시충방전192를 원래CSR·P/Q·SOC·Grid row로 연결했다. B/C/D의검증STAY arc4525/mode192/둘4717 고정LP를준비했다. 세LP는NOT_RUN이므로5.02% gap의 지배원인 및 가족별인과분해는NOT_CERTIFIED.'),
        ('Root LP 시간 병목','역사S1 Root처리에집중:presolve6.96 및second4.76, barrier완료누적23.49, crossover6.52/rootrelax17.69, 최종Native40.174/Node1. 중첩값은 합하지 않는다. 계수1e-13~400은범위이며 조건수는미측정. 이번D0 A1은presolve12.97, barrier누적26.22에서time limit/정수해0.'),
        ('새Cut/분해 인증LB개선','없음. 같은Mode384/SOC384를 반복하지 않았고 새LB값은null. Hull/DW/full-domain pricing의선택은B/C/D인과결과와계산비용 확인 후다. 완전pricing+dualcertificate 없는restricted master는Global LB가 아니다.'),
        ('Beam 점수 예측력','실제PR221 후보384(고유284)와12pool을분석했다. 반복100은보호STAY/selected55와탐색중복45로 구분했다. 늦은연결/여러Critical slot 및critical switch를기록했지만12 FULL UB가모두동일하여예측력향상은NOT_CERTIFIED. 기존SignedP/Q/SOC/Rebound를새기능으로중복하지 않았다.'),
        ('4대24노드 UB/LB개선','신규개선 없음/NOT_RUN. 역사UB0.5398310226338695/K48LB0.46498486997548166/gap13.864737209%를그Case에서만보존한다. S1 UB0.6412659669740282/bound0.609063011458436/gap5.021778%는별개다.'),
        ('D0 A1→M1→A2→M2 완료','완료하지 못했다. A1 model/onePilot까지만실행했고 현재D0 FULL primal없어M1/A2/M2 Native0/Native/Actual handoff를진행하지않았다. 옛Prefix를이유로막은것이아니다.'),
        ('PASS/FAIL/NOT_RUN/NOT_CERTIFIED',f'PASS:승인초기/Source·time·forecast literal/native model/공식MESS유지/회귀{regression["total"]}개(기존555+신규{regression["new_tests"]}). FAIL로 판명된D0 모델은없다. Time limit는INFEASIBLE증명이아니다. NOT_CERTIFIED:A1 FULL/P1/P2전체closure/실제성능/새LB·Beam예측력. NOT_RUN:P2/M1/A2/M2/S1B-C-D/새K48/Actual/Fresh.'),
        ('추가Native 예산',f'현재남음{remaining:.6f}초,30초반환여유를유지하면11.319초뿐이다. 다음권고는D0 A1 P1 cap120초+반환30초(현재잔여포함총150초,추가최소108.681초→110초증액제안)이다. Presolve/Root완료와FULL incumbent검증을먼저하고인증된P1후P2각30초×3=90초별도배분한다. S1 B/C/D는각15초×3+반환30초=75초,현재상태단독진행시추가최소33.681초→35초다. 초기A1 성공후에만M1 UB120/K48 120, A2 P1 120/P2 90, M2 UB120/K48 120의단계별상한을검토한다. 모두탐색상한이며완료·최적성을보장하지않는다. 승인한360초를넘는실험을자동실행하지않았다.')]
    final=f'''# D0 통합 최종 검토

새 D0 공개상태 Case와 원본 A1 모델을 구성했고 SourceRev1에서25초Pilot을실행했다. 초기324/472/1300은 보존했으나 현재D0 정수FULL 계획은확보하지못했다. 원본MESS 공식UB/LB는그대로유지했다.

Pilot 후입력검증과M1/A2/M2 인터페이스를보강한최종Source는Native0 재생성에서Matrix/domain/objective의동일SHA를확인했다. Rev1 Source/Case와Native결과는별도snapshot으로보존했다. 현재Source는Native NOT_RUN이며 Rev1 Bound/Primal인증을이전하지않는다. 아래Pilot측정치는Executed Rev1에만속한다.

누적Native는292.4430000782013→318.68099999427795초, 남음41.319000005722046초다. 신규1호출의25초cap대비1.23799991607666초초과를실측그대로기록했다. Worker1/Threads1이며 원장초기화·별도예산재사용·추가자동Heavy는없다.

회귀는 기존555개ID를보존하여 총{regression['total']}PASS, fail0/skip0/blocked solver0다. Native0 guard는optimize/presolve/computeIIS를차단했다. Fixture는실제May01성능인증이아니다.

'''+''.join(f'## {i}. {title}\n\n{text}\n\n' for i,(title,text) in enumerate(answers,1))+'''## 검토 위치

`D0_CASE_MANIFEST.json`, `D0_MAY01_SCIENCE_CASE_KO.md`, `D0_KNOWN_BACKLOG_CLASSIFICATION.csv`, `D0_KNOWN_CC4_PLANNING_AUDIT.json`, `A1_PILOT01/SOLVE/A_RESULT.json`, `A1_PILOT01/SOLVE/NATIVE_SOLVER.log`, `D0_STAGE_EXECUTION_STATUS.csv`가新D0결과권위다. `REGRESSION01/REGRESSION_RESULTS.json`은Native0회귀다. MESS의기존source분석은S1/Beam별원본identity와scope를유지한다.

실제D0 성능/최적화통합완료는미확립이다. May31/IEEE8500/자동Scheduler는HOLD이며 새branch/worktree/PR를만들지않는다.

예산 외의 Source 제한도 남아 있다. 초기1624의 보호/batch 정보 및 요청버전 proxy는 미확인이고,55 Pending의Pre-placement 권한 False와데이터/WAN준비를확인 없이True로바꾸지않았다. D0 Actual provider/typed projection은준비된Native0코드범위다. 완성된A2/M2 Source/Matrix/FULL 및실제데이터권한 handoff가없어Actual factory는NOT_CERTIFIED로닫힌다. 예산증액만으로고객SLA나실행권한을인증하지않는다.
'''
    (REPORT/'FINAL_UNIFIED_REVIEW_KO.md').write_text(final,encoding='utf8')
    required=['D0_MAY01_SCIENCE_CASE_KO.md','D0_INITIAL_STATE_AUTHORITY.json',
        'D0_KNOWN_BACKLOG_CLASSIFICATION.csv','D0_KNOWN_CC4_PLANNING_AUDIT.json',
        'AIDC_ACTUAL_ALLOCATION_RESULTS.csv','KNOWN_CORRECTIVE_PREPLACEMENT.csv','AIDC_C0_C1_C2_RESULTS.csv',
        'MESS_OFFICIAL_ALGORITHM_AUDIT.json','S1_ROOT_BOTTLENECK_DIAGNOSIS_KO.md',
        'S1_ROUTE_MODE_SOC_EXPERIMENTS.json','K48_GLOBAL_LB_RESEARCH_STATUS.json',
        'BEAM_JOINT_UB_COMPARISON.csv','UNIFIED_NATIVE_LEDGER.json','FINAL_UNIFIED_REVIEW_KO.md']
    if any(not (REPORT/p).is_file() for p in required):raise FileNotFoundError('D0_ALL_REQUIRED_REPORTS_REQUIRED')
    _write(REPORT/'D0_REQUIRED_REPORT_DELIVERY.json',dict(status='PASS',required_reports=[file_record(REPORT/p) for p in required],
        regression=file_record(REPORT/'REGRESSION01/REGRESSION_RESULTS.json'),
        real_D0_performance='NOT_RUN',FULL_D0_A1='NOT_CERTIFIED',old_results_transferred=False))
    print(json.dumps(dict(status='PASS',reports=len(required),tests=regression['total'],
        used_seconds=budget.used(),remaining_seconds=budget.remaining()),indent=2))


if __name__=='__main__':main()
