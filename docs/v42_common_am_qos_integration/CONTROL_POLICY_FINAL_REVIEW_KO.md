# 조건부 정책 V5 Offline/Fixture 독립 검토

별도 Fixture에서 복수 행동의 P1 점수와 원본 근사 Hard Constraint를 비교하고 정책을 선택·동결·Reload했다. 이 범위는 `OFFLINE_POLICY_OPTIMIZATION_VALIDATED`다. 이 보고서의 실행은 Native Optimize, Actual Replay 및 Fresh AC를 호출하지 않았다. 실제 May01 효과 또는 실제 Full96 Fresh AC PASS는 이 증거로 인증하지 않는다.

## 비교 결과

`C_FIXED`는 기준 시작을 유지한다. `C_GREEDY`는 자원이 허용하는 가장 빠른 시작·사이트를 선택하는 Resource-only 기준이며 이 Fixture에서 C_FIXED와 같다. 두 기준을 일부러 다르게 만들기 위해 지연을 강제하지 않았다. 별도 항목에서 기존 Compiler의 signed-effect 사전식 순위와 현재 한 슬롯의 부하 감소만 보는 지연 반례도 기록했다.

| 합성 Fixture | C_FIXED Peak | C_GREEDY Peak | C_GRID Peak | C_GRID 행동 |
| --- | ---: | ---: | ---: | --- |
| Rebound 반례 | 0.90 | 0.90 | 0.65 | B 사이트 Pre-place +15분 지연 |
| Placement 개선 | 0.90 | 0.90 | 0.40 | B 사이트 Pre-place |
| 개선 여지가 없는 불변 미래 Peak | 0.90 | 0.90 | 0.90 | START_NOW, 추가 행동 0 |

Rebound 반례에서 현재 슬롯만 줄이는 DELAY_15는 현재 부하율을 0.60으로 낮추지만 미래 Peak를 1.15로 높인다. 새 정책은 이 원본 선로 제약 위반 후보를 거부한다. 기존 signed-effect Compiler의 즉시 B Pre-place는 같은 반례에서 Peak 0.85이고, 새 정책은 남은 전체 시간축을 비교해 0.65를 선택한다. 개선 여지가 없는 Fixture는 0.90을 유지하며 행동을 강제하지 않았다. 이 비율은 실제 May 계통 측정값이 아니다.

모든 채택된 Fixture 행동의 추가 QoS·Resource 위반은 0이고 Migration·Queue·Carryout도 이 비교의 Pending 사례에서는 0이다. Source-capability가 확인된 Running Migration과 공유 예산·서비스 보존은 별도 집중 회귀 및 Actual 통합 Fixture 증거에 있다.

## 회귀와 측정

새 정책 집중 회귀 17개가 통과했다. Signed response와 MESS 부호, 96슬롯 Rebound, 전압/선로/모든 변압기 Current·kVA 거부, Q50/Q90 질량·Carryout, Burst 부족, 잘못된 Anchor, Reload, 단일 Budget, Runtime Bucket, Whole-gang Atomic Reservation, Known 서비스 차용 금지, Source Rack, Migration Phase 불일치와 Off-grid 거부를 확인했다.

2-site/2-branch 합성 측정에서 96개 Pending/Running Prototype, 528개 후보를 컴파일하는 데 약 0.420초가 걸렸다. Grid 평가 1,184회와 Cache Hit 2,161회를 기록했다. 프로세스 Peak RSS는 106,041,344 bytes이며 Python·NumPy 및 Source Packet Load를 포함한 프로세스 전체 측정이다. 정책 파일 크기는 353,586 bytes였다. 이 숫자를 12-AIDC 실제 Production 성능으로 외삽하지 않는다.

Placement Fixture의 고정 후보 조회와 Resource Guard 500회에서 Median은 약 0.0426ms, P95는 약 0.0513ms였다. 예약을 변경하지 않는 측정이며 실제 Event Engine 전체 처리시간과는 다르다. Online Grid 평가 증가 0, Global Optimize 0을 확인했다.

## 실제 연결과 남은 제한

Production 연결은 B1의 최종 A 결과, B3의 최종 A2+M2 결과와 동결 DD00 초기 상태를 소비한다. B0/B2는 이 Grid-aware 제어를 활성화하지 않는다. Source V5의 Native A1 결과 및 후속 M1/A2/M2·실제 Actual/Fresh AC 상태는 Root의 별도 실행 영수증으로 판정해야 한다. 이 Offline 보고서는 그 실행 결과를 선행해서 PASS로 승격하지 않는다.

실제 Source의 QoS·Batch·Protection 등이 확인되지 않은 작업은 추가 행동 권한을 얻지 않는다. Missing Migration Capability, TRAIN Burst, Event30 Threshold/Metric은 명시적으로 부족 상태다. Conditional Table은 제한된 시점·Gang·Runtime Prototype의 정책이므로 전체 시간·작업을 Dense하게 커버한다고 주장하지 않는다. No Rule, Resource Deviation, Hard Constraint 실패의 Queue/STAY Fallback도 계통 안전 보장으로 표현하지 않는다.

증거 경로는 `CONTROL_TABLE_ABLATION.json`, `CONTROL_POLICY_RUNTIME_MEMORY.json`, 각 Fixture의 `MEASURED_RUNTIME.json`, `OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json`, `CONTROL_POLICY_SHA_MANIFEST.json`, `CONTROL_POLICY_RELOAD_TEST.json`이다. 기존 Raw/Matrix/Ledger·B0/B1·PR222 비용 및 공유 예산은 변경하지 않았고 B2/B3 캠페인 HOLD를 유지했다.

## 최종 실제 실행 판정

Source `f488f3a99555eb2354ef52d0835078be816d2d988a2bf37010b9b09ff36568d8`에서 단계 {"A1": "FULL_FEASIBLE", "M1": "FULL_FEASIBLE", "A2": "FULL_FEASIBLE", "M2": "FULL_FEASIBLE"}, 실행 EXECUTED, Actual EXECUTED이다. Fresh AC: {"day": "2025-05-01", "arm": "B3", "status": "PASS", "PASS": true, "executed_actual_slots": 96, "full96_Actual_AC_established": true, "logical_scope": "FULL96_REAL_ACTUAL", "evidence_kind": "REAL_DATA", "original_full_case_certified": false, "science_version": "V42_COMMON_AM_JOB_ACTUAL_EMPIRICAL_QOS_DDAY_GRID_POLICY_V5", "SOURCE18R_NUMERICALLY_IDENTICAL": false, "common_initial_state_sha": "5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573", "evaluation_case_sha": "2da26249b27864cc346c95c478ced989b9433d15b334039d6988d7acab925342", "KESTREL_OBSERVED_SITE": false, "MESS_plan_sha": "49d136655fa762d45925ed8132aeb2b86b453d1495b15f0ff8f9e6dbe3075b3e", "frozen_MESS_PQ_consumed": true, "MESS_OFF": false, "initial_Planning_control_state_reads": 0, "global_reoptimization": 0, "MESS_PQ_repair": 0, "original_compiler_clock_SVR_and_measurement_reused": true, "original_Fresh96_body_executed": false, "voltage_violation_cells": 0, "line_current_violation_cells": 0, "transformer_current_violation_cells": 0, "transformer_kVA_violation_cells": 0, "physical_SolveSnap_count": 705, "solver_native_seconds": 0, "AC_wall_seconds": 14.822457399997802, "campaign_HOLD_preserved": true}. Fixture의 개선비율을 May 효과로 이전하지 않는다.

실제 May는 POLICY_COMPILER_ONLY: 144개 템플릿/4392개 생성 후보, 0개 승인된 순위 행동이다. 수치 평가309개 후보의 Q90 통과는0이며, 최종 stress 슬롯1009.8446 GPU가780 GPU 용량을 초과한다. 이는 단일 후보 평가 범위의 진단이고 전체 Queue 최적화 불가능성 증명은 아니다. Actual의5816 rule행은 Queue748/STAY5068 fallback이고 실제 추가 지연·migration은0이다. 모든2320 Job의 권한 미확인으로 B=0이며 Unknown 개선 효과는 미입증이다. 새 ML·예측 clipping·forecast target의 achieved capacity 대체는 하지 않았다. 세부 근거는 REAL_POLICY_FEASIBILITY_DIAGNOSTIC.json 및 FINAL_ACTUAL_FRESH_INDEPENDENT_AUDIT.json이다. M1/M2의 TIME_LIMIT와 약58% 제한 경로 진단 gap은 최적성 통과가 아니다.

CC4 소비 호출은 PlanningGridContext.bind → ForecastBook → v42_temporal.service.bind_forecast/bind_service이며 hourly GPUh를 x/carryout에 연결한다. 현재 V5 실제 Arm은 B3만 완료했고 B0/B1/B2는 NOT_RUN이다. 네 Arm 동일 초기 SHA는 loader/fixture 검증이다. Unavoidable wait 합계291483659초/최대312828초, hard-deadline 권한 Job0개이며 전체 SLA/QoS 준수 PASS는 주장하지 않는다.
