> PR 중단 스냅샷 안내: 아래 초기 진행 기록은 역사 자료이며 현재 실행 상태가 아니다. 현재 결과는 [최종 검토](FINAL_UNIFIED_REVIEW_KO.md), [AIDC 실측](AIDC_SITE_ONLY_PR_SUMMARY_KO.md), [MESS 압축 실측](MESS_EXACT_COMPRESSION_BENCHMARK.json), [벡터화 실측](MESS_EXACT_VECTORIZED_PROOF_BENCHMARK.json)을 따른다. 60분/Runtime Repair/Migration·새 Known Heavy·4단계 Heavy는 중단되어 있다.

# Signed Sensitivity 기반 AIDC 알고리즘 및 증거 범위

현재 실행 범위는 May01 IEEE123 B1이다. B3 및 다른 May 날짜는 실행하지 않는다. 신규 Known A1은 원래 MESS OFF와 원래 96슬롯 물리식을 사용하며, 완료 후 동일 Known 계획을 C0 Basic, C2 Signed, C3 Signed+RuntimeRepair에 전달한다. 부분 Actual Canary가 통과하기 전 Full96 Actual이나 Fresh AC 결과를 주장하지 않는다.

## Known 계획과 Actual 경계

과거 PR230 명령은 그대로 보관한다. 과거 명령을 Dday 초기 Pending 상태에 억지로 적용하면 886 UID의 예정 시각이 이미 지나 실행 관측이 없어 실패한다. 이 실패를 숨기거나 과거 명령을 현재로 이동하지 않는다.

별도의 신규 ISSUE_ONLY_DDAY_FCFS_REFERENCE_V1을 issue 시점에 만든다. 공개 issue Known, GPU/Gang/Site/Rack, 공개 Q50와 elapsed만 사용하고 Pending 시작 바닥을 native24=Dday00으로 둔다. 실제 Dday 도착이나 완료를 Planning 입력으로 사용하지 않는다. 신규 연구 60분 entitlement는 이 신규 baseline에 대해 한 번만 발급한다. 원래 submit부터의 baseline queuewait 및 horizon 선택 비용은 QoS 개선으로 계산하지 않는다.

Native0 source census에서는 원래 1395 Pending 모두 신규 허용 창이 비어 있지 않았고 FCFS 기준 시작은 native24–30이었다. 원래 service, hard earliest/latest/deadline, provider 및 representation completion ceiling을 유지했다. 초기 RUNNING의 Q50 예상 종료는 Planning 예측이며 Actual의 완료 관측 대신 자원을 해제하지 않는다. source Dday 초기 placement/queue는 선언된 모델 가정이고 Kestrel의 관측 placement 복원이라는 주장은 하지 않는다.

신규 동결 execution rule은 ATTEMPT_AT_FROZEN_START_THEN_UNAVOIDABLE_RESOURCE_WAIT_SAME_SITE다. 정확한 예정 시각의 시도 receipt가 있고 자원 용량 때문에 막힌 경우에만 같은 site/service로 원래 명령을 실행한다. 원래 예정 시각과 intentional budget은 보존하며 Actual 자원 대기 시간을 별도 기록한다. 중간 grid/QoS/기타 veto가 나오면 대기 권한을 영구 취소한다. 관측하지 못한 과거 886 명령에는 적용하지 않는다. named Actual witness에서 예정900, Running overrun 후 release2700, Known 실제 시작2700이 확인됐고 intentional900와 unavoidable1800을 분리했다.

## Signed all-line 목적과 정확한 현재 C1

후보를 추가한 뒤 모든 선로·상·잔여 슬롯의 최대 부하율을 최소화한다. 최대값 동점일 때 loading-hours, 공개 위험량, intentional delay와 안정적인 site/start 순서로 비교한다. 민감도 절댓값이나 기존 혼잡 선로 한 개만 비교하지 않는다. Voltage, NormalAmps, 모든 Transformer current/kVA 행과 GPU/Gang/Rack, WAN/Residency 및 공유 QoS를 유지한다.

원래 계수는 AUTO causal-prefix SIGNED SECANTS와 LDC interval 권위를 유지한다. 현재 슬롯에는 원래 FrozenPowerModel authority를 검증하고 관측 Running과 후보 Gang으로 정확한 PCC P/Q를 재계산한다. weather callback은 현재 tick만 반환하며 미래 Actual weather는 정책에 주지 않는다. 미래 열은 원래 D-1 C1 예측 secant를 사용하므로 근사 위험이며 Fresh 11SVR AC 인증을 대신하지 않는다. REAL context에서 정확한 현재 C1/model authority가 없으면 fail closed한다.

동일한 공개 Unknown 5 UID(8713774, 8713785, 8713845, 8713846, 8713847) 진단에서는 현재 placement/rack/capacity 통과 사이트 수는 1/1/1/7/1이고 모두 현재 정확한 C1을 사용한 선형 전력망 검사를 통과했다. 다만 이5 UID의 동결 FCFS 기준은 Dday+5400초이므로 Dday00 START 권한은 없다. 허용된90분 이후 후보도 미래26슬롯 전압 행 때문에 모두 QUEUE였다. 이는 현재 실행 가능성과 미래 예측 guard의 차이를 보여주는 진단이지 실제 실행 성공이나 전력망 개선이 아니다. CURRENT_C1_CANDIDATE_WITNESSES.json에 60개 사이트 후보의 현재 P/Q, deltaP/Q, weather, 원래 MESS OFF와 source SHA를 보존했다. 독립 Fresh AC는 Supervisor가 수행한다.

## Hard 관측과 Soft CC4 보존

관측 Running, Known 동결 명령 및 Unknown 확정 예약은 Hard다. 익명 CC4, 아직 실행하지 않은 공개 Q50/Running 잔여 예측은 Soft이며 GPU 확정 예약으로 승격하지 않는다. 같은 UID의 겹친 점유는 구간별 최대값으로 합친다.

원래 hour×time x와 time×site GPU marginal을 canonical transportation product로 연결한다. sum_site z[h,t,site]=4*x[h,t], sum_hour z[h,t,site]=nominalSiteGPU[t,site]를 검증한다. 원래 Q50/Q90, CDF, x 및 carryout은 수정하지 않는다. source.submit cohort를 사용해 관측 Unknown UID마다 nominal work를 한 번만 차감하고, pre-Dday Unknown carry 및 source excess/expiry를 별도 기록한다. 남은 cohort의 in-day service+carryout 질량을 검증한 뒤 익명 잔량을 미래 Soft grid expectation으로만 더한다. 검증 실패는 CONSERVATION_NOT_CERTIFIED로 표시하고 안전 후보로 승격하지 않는다. 현재는 익명량을 실제 GPU에 더하지 않는다.

## Runtime repair, Backfill 및 Migration

Overrun Running은 실제 완료를 관측할 때까지 GPU를 보존하며 Pending Unknown 예약을 재검사한다. Unknown 예약 repair는 동일 entitlement를 재사용하고 예산을 갱신하지 않는다. Short Runtime은 원래 15분 release control 계약을 유지한다. 다음 확정 예약 앞의 REAL nonpreemptive Backfill은 검증된 runtime upper-bound registry가 없으므로 비활성화한다. 임의 metadata source_sha는 certificate가 아니다. 다음 확정 예약이 없는 경우의 기존 admission은 원래 guard를 따른다. Q50/Q90는 완료 보장이 아니며 conditional remaining Q90 provider는 NOT_CERTIFIED다.

Checkpoint Migration은 관측 RUNNING/checkpoint, 1회 한도, Source/Destination capability, WAN/Residency/Transfer/Restart, 공유 QoS, 잔여 service, GPU/Rack 및 전체 grid guard를 통과한 경우에만 선택한다. STAY가 infeasible하더라도 MIGRATE가 모든 hard 행을 통과하면 비교 후보가 될 수 있다. 단순 nonworsening은 PASS가 아니다. 0건도 UID funnel과 이유를 남긴다.

## 계산 시간과 검증

정확한 baseline96 결과를 전체 baseline bytes, clock, source response/coefficients, 전압/branch axes, 현재 C1 authority/weather 및 observed GPU를 key로 캐시한다. 후보가 바꾼 슬롯만 원래 scalar row로 다시 계산하며 모든96슬롯 max/위반 평가를 유지한다. scalar 대비 동일 결과, baseline/clock/coefficient 변경 시 무효화가 named tests에서 확인됐다.

동일5 UID에 대한 이전 P95는 C2 13.706초/C3 12.243초, 이번 P95는 C2 1.339초/C3 1.238초였다. 이번 revision은 cache와 함께 정확한 현재 C1 및 cohort 보존을 추가했으므로 독립적인 cache speedup이라고 주장하지 않는다. 각 C2/C3는 baseline cache60hit/3miss였다. 전체87.309초 중 측정된 decision phase 합은10.370초이고 나머지는 source preparation, projection/controller materialization 및 보고 작업이다. Cold/warm component profiler는 신규 A1에서 이미 만들어진 packet을 재사용하며 baseline96/changed/current row 수, exact C1, hard reservation, candidate scoring 및 hash/serialization 시간을 별도 기록한다. 작은5개 표본은 운영 latency SLA나 power improvement 인증이 아니다.

최종 native-free 회귀 테스트는63개 PASS였다. Known 실제 시작, overrun 대기, noncapacity veto 취소, frozen policy mutation 거절, 실제 B1 C0/C2/C3 prefix 전달, reference 교체 방지, migration, Backfill authority 및 cohort/cache 수치가 포함된다. 이 named 증거와 실제 source diagnostics를 구분한다. 신규 A1/Actual/Fresh AC의 최종 판정은 Supervisor의 현재 case artifact를 따른다.
후속 검증에서는 현재 Native A1 case/stage/arm/FULL replay/Native receipt와 모든 공통 SHA 및 resource_distribution_sha를 추가로 검증한다. C0/C2/C3 각각의 실행 정책을 파일로 동결하고 reload한 정책 SHA 및 파일 SHA를 receipt에 남긴다. Cache key에는 실제 voltage/current/P/Q matrix/constant, anchor/limits, polygon/correction/bias/ap까지 numeric fingerprint를 포함하며,17개 배열 변경 테스트에서 선언된 coefficient SHA가 그대로여도 cache를 재사용하지 않았다. 이번 hash 보강의 실시간 비용은 최종 A1 cold/warm profile에서 따로 측정하며 이전5개 timing에 소급하지 않는다. Carry-only CC4 cohort도 원래 CDF/carry authority와 질량 보존을 검증한다.

추가 source-only 검증에서1395 Pending의 공개 Q50 ceil-release는 Native service_slots와 모든 UID에서 일치했고, FCFS의 Native interval 점유에도 capacity 위반이 없었다. 894UID는3slot,216UID는63slot,285UID는61slot 서비스다. 다만 이 FCFS STAY 기준은 Dday0–5slot의780GPU를 모두 사용해 원래 CC4 Q10 cumulative 최소 서비스(2slot0.085989GPUh,3slot4.853125GPUh,4slot8.929704GPUh,5slot12.052863GPUh)를 수용하지 못한다. 고정 reference seed INFEASIBLE은 이 coupled capacity/CDF 충돌로 설명할 수 있으며 전체60분 도메인의 infeasibility 증거가 아니다. 현재 동결 baseline/예산을 보존하는 participant-only delay warm point를 원래 FULL row로 확인하는 것이 다음 단계다. Actual 및 Fresh AC는 아직 시작하지 않았다.

같은 reference/receipt/3600초 예산을 유지하는 source-only 후보에서21개 같은-site short pair(42UID)가 선택됐다. First24→28, Second27→30이며 원래 service/wholeGPU/native ceiling을 지킨다. 슬롯0–5 cumulative freeGPUh는5.25/10.5/15.75/21/21/21로 원래 Q10 필요량을 넘겼고 전체96슬롯의 necessary capacity 검사는 통과했다. Original FULL grid/CDF LP는 Supervisor 검증 대상이고 이 후보는 incumbent이나 feasibility 인증이 아니다.

Actual 직전에 동결 Dday 파일의 SHA/bytes 및 payload commonInitialStateSHA, 공통Case/Science와 경계시각을 검증해103개의 originKnown=False historical-completed 증거를 전달한다. 완료와 control-release 모두경계이전인 UID만 runtime protectedKnown booking과 미래 점유예상에서 제외하며, 원래 Planning 명령/인구/reference는 보존한다. 같은 proof SHA를 모든 C0/C2/C3에 쓰고 취소 ledger를 남긴다. 잘못된SHA/미래시각/mixed UID/재제출은 거절한다.
