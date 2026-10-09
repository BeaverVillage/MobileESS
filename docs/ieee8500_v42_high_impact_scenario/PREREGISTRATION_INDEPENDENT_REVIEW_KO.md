# 원본·날짜·선택·일정 독립 검토

원본 입력과 사전등록을 읽기만 하고 새 source/schedule 테스트 11개를 실행했다. 모든 검사는 PASS이며 AC·Native·FULL 호출은 없다. 테스트는 root artifact writer를 가로채 일정 계산의 진짜 함수를 메모리에서 검증하므로 사전등록·현재 AC 결과·원본 캠페인을 수정하지 않는다. 정확한 검토 대상 SHA는 `PREREGISTRATION_INDEPENDENT_REVIEW.json`, 실행 증거는 `SOURCE_AUTHORITY_TEST_RECEIPT.json`에 있다.

BG/GPU 후보는 미리 정한 15개이고 Planning-only다. 후보 사이를 보간하지 않으며 Actual FAIL 후 BG·GPU·정책을 재선정하지 않는다. May02는 가장 이른 완비 별도 날짜로 고정했지만 IEEE123에서 이미 노출되었으므로 전역 미노출 holdout으로 주장하지 않는다. 현재 구현은 원본 C0만 승격하며, C1/C2는 추가 hardware bound가 없는 counterfactual로 남긴다. 원 사전등록의 일반적인 C0→C1→C2 우선순위를 모두 구현했다고 주장하면 안 된다. 초기 idle-only screen과 source-preserving reference/queue 재계산 screen을 분리하고 전자를 그대로 보존한 것은 최신 workload 보존 지시와 일치한다.

원래 JSON의 `40slots` 문구와 충전 상한 누락은 원래 bytes를 바꾸지 않고 `SCHEDULE_PREREGISTRATION_CLARIFICATION.json`으로 보완했다. 원래 구체적 시각인 8..15 충전, 68..75 방전은 유지한다. 같은 길이의 충·방전은 `Pdis ≤ Pcharge_max × eta_ch × eta_dis`를 만족해야 한다. L0의 main·auxiliary 효율을 모두 적용한 η=.855에서 차량별 충전은 5 kW, 방전은 3.655125 kW다. 동일한 원본 6개 초기 STA, 완전한 slot0 접속 차단, Q=0, 이동거리·도로 에너지 0을 유지한다. 96개 구간을 별도 배터리 에너지 식으로 검증해 SOC 범위와 terminal 1140 kWh를 확인했다.

일정 테스트가 처음에는 `5.000000000000001 kW`의 충전값을 발견했고, 그대로 유지한 원본 5 kW interface 검증이 이를 거부했다. parent가 새 일정 계산에서 충전을 먼저 5 kW로 제한하고 방전을 η로 다시 결합했다. 원본 `integration.py`의 전력 상한은 변경하지 않았다. 이 수정 후 11개 검사가 통과했다.

일정/SOC 재현은 saved AC의 모든 port 전류·P/Q·1152개 행을 검증한 것과 다르다. saved AC 측에는 96×12 고유 행, 유한 P/Q와 모든 conductor, 실제 slot0 전력 0 및 전체 grid security/Fresh 상태 검사가 필요하다고 전달했다. field GIS·protection·접근권, 움직이는 MESS dispatch, Native 최적화, 전체 연속 정책/SoC 영역 인증은 여전히 남아 있다. proposed MV의 삼상 균형을 최종 L0 split-phase comparator에 그대로 붙여 설명하면 안 된다. joint all-MV geometry 진단도 최종 Production case로 승격되지 않았다.

누락·중복 port 행, NaN readback, 접속 전 slot0 전력을 거부하는 네 가지 negative fixture 검사도 통과했다. 이는 validator 동작 검사이며 새 물리 AC solve 증거로 계산하지 않는다.
