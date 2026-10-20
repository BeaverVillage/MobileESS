# V1_add — 기준 r043 MESS8 정적 이식 감사

기준은 `affc7226a519adbe072d7debbc3ae25ea71c3487`이다. Production, 알고리즘, Solver 정책은 수정하지 않았다. 8대 모델 생성·최적화·실행시간 측정은 하지 않았다. 독립 FCFS 재생의 Native 호출은 0회다.

| 소스 | 확인한 4대 결합 | 필요한 차원 이식 검토 |
|---|---|---|
| `v44/inputs.py:49` | `len(initial_MESS_sites)!=4` | 8대 입력 roster 검증 |
| `v44/initial_states.py:22` | MESS01~04 초기 STA literal | 신규 4대의 실제 PCC/경로 검증 후 초기화 |
| `v42_may_campaign_native90/traffic.py:146` | 정확히 4대 검증 | 동일 RouteArc domain에 8대 검증 |
| `v42_may_campaign_native90/operations.py:63` | 4개 unit_ids 출력 배열 | 입출력 및 독립 replay axis |
| `v42_may_campaign_native90/m_model.py:539` | units=4 metadata | FULL/압축/증명 metadata 일치 |
| `v43_actual/planning_reference.py:63` | units=4 | Planning/Actual 전달 계약 |
| `v44/svr11_ac.py:139` | `(len(rows),4)` MESS P/Q와 위치 배열 | Actual/Fresh 및 캐시 identity |
| `v43_arms/current_ac.py:61` | `mess_locations_96x4` 계약 | 시간·차량·위치 축 검증 |
| `v44/svr11_frozen/v42_voltage_control/authority.py:231` | hardware roster 4대 | 원본 독립 물리 검증기 계약 |

`v42_native/mess.py`는 `sorted(initial_sites.items())`로 차량을 순회한다. 이는 하위 수학식이 차량 인덱스에 대해 일반적이라는 정적 증거이며, 상위 입력·출력·검증기를 포함한 8대 통합 PASS는 아니다. `m_candidates.py`의 `heuristic_MOVE_depth=4`는 탐색 깊이이며 차량 수 4의 하드코딩과 구분한다. CC4의 4개 quarter도 차량 축이 아니다.

원본 Route Table은 55,296행(24×24×96)이다. 동일 사이트 stay 및 기존 시간 계약을 적용한 원본 이동 arc는 51,322개다. 다음은 reachability 제거 전 **분석 상한**이다. Gurobi 모델을 생성해 측정한 수치가 아니다.

| 항목 | 4대 | 8대 |
|---|---:|---:|
| 이동+stay binary 상한 `U×(51322+24×96)` | 214,504 | 429,008 |
| charge-mode binary `U×96` | 384 | 768 |
| SOC continuous `U×97` | 388 | 776 |
| Pch/Pdis/Q continuous 상한 `3×U×24×96` | 27,648 | 55,296 |
| flow 행 상한 `U×24×96` | 9,216 | 18,432 |
| PCS16 행 상한 `16×U×24×96` | 147,456 | 294,912 |

실제 초기 위치, 도달 가능성, 제거된 0열과 FULL 표현에 따라 크기가 달라진다. K16→K32→K48는 원본 FULL 물리 좌표/행을 투영하므로 FULL과 모든 단위 identity를 다시 검증해야 한다. K=48을 유지해도 8대 변수 차원은 자동으로 동결되지 않는다. Beam의 경로 조합은 단순 2배가 아니며 `B^U` 형태의 조합 위험과 폭 제한을 구분해야 한다. 실제 탐색 성능은 NOT_VERIFIED다.

계통 교체의 영향은 별도다. 측정된 Greensboro 12,749 electrical nodes를 모든 슬롯에 사용하면 전압 상·하한만 `2×12749×96=2,447,808`행의 직접 표현 상한이다. 차량 4→8대는 고정된 PCC별 집계 전력에서 이 계통 행 수를 직접 2배로 만들지 않는다. 반면 차량 flow/SOC/경로/PCS 차원은 증가한다. 현재 60개 제어축을 유지하는 조밀한 전압 민감도 tensor만 가정해도 `96×60×12749×8=587,473,920 bytes`다. 이는 저장 배열의 산술 크기이며 MILP RSS나 실제 Sparse 모델 메모리 측정치가 아니다.

물리 계약도 별도 차단 사유다. r043은 Planning RegControl 7개, Actual은 SVR12를 더한 RegControl 43개다. Greensboro 원본은 RegControl 1개, capacitor 5개다. 7/43 계약을 그대로 구현했다고 주장할 수 없으며 원본 설비를 복사·개조하지 않았다. 원본 모델을 존중하는 전기적 adapter의 계약 정합성, 8대 초기 STA, 다중 접속과 전체 독립 검증은 NOT_VERIFIED다.
