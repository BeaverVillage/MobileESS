# May01 최종 알고리즘 실행 상태

최종 AIDC 압축·반복 MESS·PR222 정차 고착 수정·M1→M2 재검증 Warm Start·공통 QoS 평가를 통합했다. 기존 1,096개와 신규 18개를 포함한 전체 회귀 1,114개 PASS. 최종 May01 AIDC Native0에서 229 Class, DW 1,030,845행 / 195,578변수 / 11,165,284 NNZ 및 229개 전체 Pricing 범위를 확인했다. 원본 FULL 정수 MILP는 그대로 유지한다. 실제 MESS 두 Pool/384 Mode readback도 PASS. 원본 FULL 1,130,336행 / 344,967열 / 16,432,980 NNZ, 선택 표현 715,142행 / 354,332열 / 7,903,837 NNZ, Direct Joint 두 Pool 각각 715,146행 / 137,690열을 검증했다. 각 차량의 STAY/단일/복수 MOVE가 모두 포함되며 정적 Cache 재사용도 확인했다. Native0 Structural Center는 실행 가능한 UB로 인증하지 않는다. 최종 Launch Gate 후 Heavy에 진입한다. 실제 Heavy 결과를 아직 주장하지 않는다.

현재 실행 Epoch는 RC04/TABLE_V/EXECUTION06이다. B0/B1/B2/B3 모두 현재 Source에서 독립 검증·실행하며 과거 B0 FULL_PASS와 중단 B1 Native 1,736.792초는 읽기 전용 보존한다. 실행 순서는 B0 → B1 → B2 → B3이다. 각 Arm의 Planning FULL-feasible, 인증 LB/UB/Gap, 실제 Native/Wall/메모리, Actual96/Fresh96 및 공통 평가 지표를 완료 후 원본 기록에서 갱신한다.

May02–31 Heavy와 잔여 월간 대형 Native0는 실행하지 않는다. 전체 5월 Launch 승인은 May01 네 Arm, 대표 날짜 증거, 최종 Source/Case/Policy/Release 및 별도 예산 승인 확인이 완료될 때까지 HOLD이다.
