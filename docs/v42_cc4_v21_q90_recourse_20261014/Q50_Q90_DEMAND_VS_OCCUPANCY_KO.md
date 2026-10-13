# CC4 시간별 수요와 A-stage 서비스 배분 — D Native0 감사

원래 CC4 바인딩은 PASS다. 동결 모델은 `LGBM_weighted_c1_s20260924`이며 PR64·74 NPZ blob과 PR129 외부 prediction 바인딩의 동일 NPZ SHA `8a8a5e6ffd81ce4d2a619fbea61d8d5cb1de4ad08aa391e4c52fb7137d326077`를 원본 Commit blob 및 재검증한 외부 NPZ bytes로 확인했다. PR129 branch는 prediction NPZ 사본 대신 정확한 외부 경로·SHA 바인딩을 보존한다. PR64의 별도 DeepAR 연구 선택은 현 V42 생산 입력으로 승격되지 않았다. 예측은 24개 시간 각각에 도착할 작업의 lifetime GPUh Q50/Q90이다. 24개 주변 Q90 합계 24408.063227 GPUh는 하루 총수요의 Q90 분위수가 아니다.

원본 `bind_service`의 x[h,t]는 hour h의 익명 수요 중 slot t에서 처리할 GPUh다. `sum x + carryout = remaining W`를 보존하고 `GPU[t] = 4*sum_h x[h,t]`로 15분 평균 GPU를 계산한다. 12개 사이트 분배 합은 이 값과 같다. 원래 pre-day issue에서는 served_before=0이며 중간 재계획에서는 이미 처리된 서비스가 누적 CDF와 전체 수요의 양쪽에 보존된다.

A2의 Q50 수요·서비스·이월은 각각 5503.441472·3225.157483·2278.283989 GPUh다. Q90−Q50 target의 수요·서비스 시점 목표·이월은 18904.621755·18904.358834·0.262922 GPUh다. 모든 24개 hour의 질량과 원래 TRAIN Q10/Q90 누적 서비스 범위를 재검증했다. TRAIN kernel은 참조 시점 및 deviation 기준이며 실제 x를 고정하지 않는다.

물리 capacity 식은 Known+Q50 익명 nominal+달성된 CC4 reserve+달성된 runtime reserve≤site capacity다. 저장된 A2 FULL은 유지되며 최대 capacity 위반은 0 GPU다. 원본 A-stage의 achieved reserve와 target 사이 shortfall은 허용된 모델 항이다. P1은 원래 최대 선로부하율이고 이번 감사는 목적함수를 변경하지 않았다. P2 호출은 0회였다. reserve target을 실제 달성 reserve 또는 전기 부하로 부르면 안 된다.

제어표의 불일치는 target reserve를 고정 Q90 실행 부하로 더하고 모든 scenario의 hard-feasible을 요구한 경계에 있다. A-stage의 서비스·carry 모델이 없어서 생긴 결함이 아니다. 새 D recourse는 저장된 A2 Q50 x·site GPU·carry를 고정하고 Q90−Q50 추가 GPUh만 원래 서비스 범위와 잔여 용량에서 처리한다. 미처리 GPUh는 시점별 backlog와 horizon 종료 carry로 한 번만 계상해야 한다. service carry와 QoS 준수는 별도 판정이며 익명 집계 recourse는 Job별 whole-gang 최적해 증명이 아니다.

이 감사는 Source 및 저장된 A2 산출물을 읽은 Native0 검증이다. 새 모델 생성·Optimize·Actual·Fresh AC·fit·calibration은 0회이며 과거 PR223 Full96/Fresh 증거를 새 정책의 결과로 이전하지 않는다. PR224 수정은 완료된 기존 경계로 유지한다. 새로운 Q90 제어 정책과 E1/E2 계약은 별도 과학 정책이며 새 Full96/Fresh AC는 NOT_RUN이다. B2/B3 및 31일 캠페인 HOLD를 유지한다.
