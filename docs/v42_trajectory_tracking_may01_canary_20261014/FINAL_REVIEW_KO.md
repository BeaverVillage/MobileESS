# May01 4시간 실제 Tracking Canary 검토

신규 A1: **NEW_A1_NOT_CERTIFIED**. C0/C2/C3는 기존 Source18r V5 A1을 공통 동결한 **별도 Diagnostic**이다. 과거 Case `3df8856647274066035c4e81e5073eea2c3d3eec8043494ed5868fa4a1197efb`와 현재 Case `17066bfc24eb21594dfb7e4abfe74580a1a020617aadcf27b93a4692e6d3e5f9`는 다르다. 새 E1 최적성/P2/global gap 성과로 이전하지 않는다.

1. 과거 B1 May31 fixed replay는 저장된 Planning PCC P/Q를 그대로 복사했다. 이번 Actual은 관측된 Job의 배치·대기·실행·완료 점유에서 원본 C1 exact 전력을 계산한다. Legacy PCC 동일성 검사도 원본 그대로 보존했다.
2. Known/Unknown Q50/Total GPU, IT, PCC P/Q 96×12와 Known 명령, CC4 Q50/Q90, CDF/service/carry 및 Source/Case/Anchor/Runtime/C1/Grid SHA를 동결했다. Target SHA `dbba918b3768b5bfbfcac0dbcf80233e413b0ab5be94fb09e3c100260ec29074`.
3. Unknown 관측 후 전체 compatible site 및 원본 QoS 허용 시작시각을 열거했다. GPU/Rack/WAN/QoS/signed grid hard 검사 후 Aggregate Unknown service 배분 부족분, grid stress/loading-hours, 공개 runtime/carry risk, 부담 순으로 결정했다. class별 Y*의 정확한 재현이 아니다.
4. 도착이 적으면 존재하지 않는 Job이나 익명 GPU를 생성하지 않는다. 도착이 많으면 capacity/예약/권한을 우선하며 불가피 Queue와 carry를 남긴다. Known/Unknown 오차와 nonnegative residual, 미도착 nominal volume 한계를 별도 기록했다.
5. Actual Global MILP/LP/Gurobi Optimize는 **0회**다. 경량 Job 후보 비교와 original signed row 계산만 수행했다.
6. C2 제어 1642회: 평균 0.160622s, P50 0.042237s, P95 0.799038s, 최대 1.615831s. 전체 후보 21598개. Queue 재시도와 checkpoint STAY 결정을 포함한다.
7. Known 명령 SHA 변경 없음=True. Issue Known 1649 UID, Native 계획 대상 1499 UID; 기존 Anchor의 Preplace 1150, TimeShift 969, Migration 0, 변경 unique 1282, 변경 nominal 7797.500000 GPUh이다. 이는 source native remaining service slot 기준이다. 4시간 Known 관측 1546 UID, 최적 명령 대상 관측 1498 UID. 실제 start deviation 33건, 명시적 pre-DDay 실행 실패 886 unique UID / 14176 재시도 event다. 불변 명령이 모든 실제 시작의 일치를 뜻하지 않는다.
8. C2 Unknown 관측 295 UID, 권한 적격 295, FLEX 참여 84; 변경 unique 0, Preplace 0, TimeShift 0, Migration 0. 행동 집합은 중복 가능하며 unique union을 별도 집계했다.
9. 변경 nominal GPUh=0.000000; C2 Unknown 실제 compute=198.420000 GPUh. nominal Q50량과 실제 computing은 같은 지표가 아니다.
10. C0 대비 C2 전체 GPU L1 오차 감소량=0.000000 GPUh, PCC P L1 오차 감소량=0.000000 kWh. 양수는 감소, 음수는 악화다. 사이트/시간별 Known/Unknown/P/Q 및 share 차이는 CSV에 있다.
11. 4시간 exact-C1 PCC를 넣은 original affine rho: C0=0.520116150, C2=0.520116150, ΔC2−C0=+0.000000000. C2 critical=line.sw1::A / slot 1. 추종 오차와 계통 변화는 별개다. 일간 최대/Fresh AC 개선으로 주장하지 않는다.
12. C1 Frozen 표는 **NOT_RUN**이다. Source-only 전체 grammar 비용 추정은 {'whole_GPU_gangs': 100, 'templates': 1497600, 'candidate_variants': 37152000, 'ranking_and_risk_records_minimum_bytes': 38043648000, 'Source_only': True, 'Actual_future_UIDs_read': 0}; 1KiB/후보 record 가정은 휴리스틱이고 실제 dedup 후 최소 RAM의 증명이 아니다. 실제 compile wall=0, compile peak RSS=NULL이며 비용 측정 실행은 미시도다. fixture를 실제 제어표로 사용하지 않았다. Frozen 대비 우수성은 미검증이다.
13. C2 Migration=0, C3 Migration=0. C2 funnel unique={'CHECKPOINT': 66, 'AUTHORITY': 6, 'DESTINATION': 6, 'REMAINING': 2, 'WAN': 2, 'GPU_RACK': 0, 'BUDGET': 0, 'SELECTED': 0}. 적격 checkpoint 계약 6 UID 중 4 UID는 Q50 remaining이 없었고 2 UID는 shared interruption budget으로 거부됐다. Preplace를 제거해도 Migration이 증가하지 않았다. 일반 대체 관계는 미확정이며 본 구간은 실행 가능한 Migration 기회가 부족한 INSUFFICIENT_MIGRATION_OPPORTUNITY다.
14. C2 QoS intentional budget excess=0, physical GPU violations=0, affine grid violation rows=2, Known/Unknown overlap=0. Source hard windows와 Migration/WAN guard 유지. Queue/latest-start/CDF 위험이 0이라는 추가 보장은 하지 않는다. Latest-start excess UID=611. 독립 Anchor 96슬롯 affine PASS=True이며 새 E1 FULL MILP 인증은 아니다.
15. 실제 16슬롯 실행·C1 재계산·동일 입력·독립 상태·optimizer0을 검증했다. 회귀 242 PASS. Native=0.0s, A1 시도 wall=442.227s, 이번 diagnostic watchdog wall=629.600s, 준비 중단과 진단 실행의 누적 wall=1078.553s. 개발 수정·회귀 시간은 별도이며 Native 재시도는 없다. Full96 Actual, 일간 peak, 31일, 새 E1 A1/P2, C1 비교 및 Fresh AC는 미검증이다. OpenDSS는 PARTIAL_AC_NOT_AUTHORIZED/NULL. 04:00 Running/Pending과 private continuation 상태를 보존했다.

기존 통합 원장 621.2855198158068/3600초와 B2 별도 원장 1257.5220000743866/1800초의 바이트 SHA를 보존했다. 이번 모델 준비/Native/Actual wall은 별도 원장에 기록했다. B2/B3/May31 자동 실행 및 외부 worker 종료는 없다.

실제 후보 거부 원인(C2)은 {'PREPLACE_SOURCE_AUTHORITY_OR_ABLATION': 7326, 'PREDICTED_COMMITTED_GPU_CAPACITY': 13696, 'NO_CAPACITY': 3813, 'Q50_OVERRUN_NO_NOMINAL_MIGRATION_ENVELOPE': 44, 'SHARED_DELAY_INTERRUPTION_BUDGET_EXCEEDED': 22, 'SHARED_QOS_BUDGET': 3696, 'CURRENT_OBSERVED_ORIGINAL_PLANNING_VOLTAGE': 327}다. UID별 거부 집합은 중복 가능하다. 특히 공개 Q50 예상 점유와 Known 확정 예약이 capacity를 초과하는 후보를 배제했으며, 이 예측을 실제 미래 완료의 증거로 사용하지 않았다. 현재 실험에서는 Tracking이 실제 변경을 만들지 못했고, 2개 슬롯의 exact-C1/signed voltage hard 위반과 Queue/latest-start 위험이 남았다. **실측 Canary의 과학 Gate는 FAIL/CLOSED**다. 구현·파일 전달 검증 PASS를 물리·QoS·Full96 PASS로 표시하지 않는다.
