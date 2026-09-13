# IEEE123 Actual 이동 지연·다음 출발 충돌 read-only audit

최종 authoritative May 31일 × B0/B1/B2/B3 = 124건을 확인했습니다. 충돌은 0건입니다.

| 항목 | 결과 |
|---|---:|
| 총 이동 수 | 95 |
| Actual ETA > planned Safe ETA | 4 |
| Actual ETA > nominal Q50 ETA (보조 비교) | 46 |
| Actual ETA > Q90 ETA (보조 비교) | 10 |
| actual connection-ready slot > planned slot | 0 |
| 물리적 도착의 15분 경계 crossing (Safe ETA 대비, 별도 지표) | 1 |
| collision edge case | 0 |
| 최대 collision slot | 0 |
| 같은 day/policy/vehicle의 연속 이동 쌍 | 0 |

충돌 영향을 받은 day/policy/vehicle: **없음**..

ETA 비교의 기본 기준은 frozen 계획이 connection-ready slot을 산정할 때 사용한 `route_safe_eta_sec`입니다. 명목 예측 Q50을 의미하는 경우의 지연 수는 별도로 기재했습니다. 슬롯은 운영일 기준 0부터 시작하며 1 slot = 15분입니다. 실제 도착 slot은 연속값이고 connection-ready slot은 실제 ETA에 600초를 더한 후 900초 단위로 올림한 정수입니다.

물리적 도착의 slot boundary crossing과 connection-ready boundary crossing을 구분했습니다. 물리적 도착 crossing은 `ceil(actual_eta/900) > ceil(planned_safe_eta/900)`입니다. May20 B2 MESS02는 planned safe arrival slot 23.985970196에서 actual 24.000478096으로 물리적 도착 경계를 넘었으나, connection-ready는 계획·실제 모두 slot 25로 동일하며 다음 이동은 없습니다.

**해석 한계:** 이동한 95개 day/policy/vehicle은 각각 한 번만 이동했습니다. 따라서 다음 출발과 비교할 연속 이동 쌍 자체가 0개입니다. 이 결과는 현재 IEEE123 결과가 해당 edge case를 경험하지 않았다는 뜻이며, 여러 번 이동하는 스케줄에서 replay rule이 안전하다는 검증은 아닙니다. 서로 다른 날짜 또는 정책의 독립 실행을 이어 붙이지 않았습니다.

## Safe ETA를 넘긴 이동

| Day | Policy | MESS | Origin → destination | Safe ETA (s) | Actual ETA (s) | Planned ready | Actual arrival slot | Actual ready | 다음 출발 | 분류 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 2025-05-04 | B2 | MESS02 | STA12 → IDC05 | 2352.809357 | 2396.181567 | 18 | 16.662423963 | 18 | 없음 | ETA 지연, ready-slot crossing 없음 |
| 2025-05-19 | B2 | MESS02 | STA12 → STA06 | 2731.365631 | 2889.474401 | 44 | 43.210527112 | 44 | 없음 | ETA 지연, ready-slot crossing 없음 |
| 2025-05-20 | B2 | MESS02 | STA12 → IDC05 | 2687.373177 | 2700.430287 | 25 | 24.000478096 | 25 | 없음 | ETA 지연, ready-slot crossing 없음 |
| 2025-05-22 | B3 | MESS02 | STA12 → IDC05 | 2244.676399 | 2291.171720 | 13 | 11.545746355 | 13 | 없음 | ETA 지연, ready-slot crossing 없음 |

## Authority 및 read-only 검증

최종 revision monitor의 junction을 실제 경로로 해석해 perf1 122건과 selective revision의 May31 B2/B3 2건을 사용했습니다. 모든 124건의 DA trajectory SHA가 restoration FINAL_AUDIT의 최종 SHA와 일치합니다. 저장된 COMPLETE/최종 ACTUATOR는 receipt SHA와 일치하고, Actual moves와 frozen command의 canonical SHA는 최종 binding과 일치합니다. 384개 차량-slot 명령을 각 policy-day마다 대조했으며 모든 계획 이동과 Actual 이동의 일대일 대응을 확인했습니다.

읽은 입력 877개는 감사 전후 SHA256 및 수정시각이 동일합니다. 기존 파일에 쓰기를 하지 않았습니다. 기존 SUMO 이동 기록의 ETA를 사용했으며 SUMO/Actual/OpenDSS를 재실행하지 않았습니다. 원래 이동 기록에 포함된 독립 traffic-source 검증 PASS를 확인했습니다.

전체 95건의 상세는 ALL_MOVEMENTS.csv, 충돌 사건 전용 표는 COLLISION_EVENTS.csv(발생 0건이므로 헤더만), 124건 coverage는 DAY_POLICY_COVERAGE.csv, 전체 496개 차량별 이동 수는 VEHICLE_MOVEMENT_COUNTS.csv에 있습니다. INPUT_READ_ONLY_MANIFEST.json은 읽은 원본의 SHA 전후 비교, OUTPUT_SHA256_MANIFEST.json은 이 별도 감사 산출물의 SHA입니다.
