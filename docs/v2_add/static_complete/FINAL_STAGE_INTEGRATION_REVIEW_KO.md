# V2_add PR #236 May01 최종 Stage 통합 검토

**판정: READY_FOR_MAY01_CAMPAIGN_APPROVAL**. 이 문서는 공식 실행 전 관문이다. 격리 수치 Canary는 별도 원장으로 기록하며 공식 결과로 사용하지 않는다.

사용자의 추가 지시에 따라 RAM 최적화와 비교 실험을 종료했다. 공식 캠페인과 Native0 준비 모두 RSS·가용 RAM 기준 거부·대기·중단을 하지 않는다. Gurobi 두 메모리 제한은 양의 Infinity다. 기존 RAM 비교 결과는 과거 증거로만 보존한다.

Source-YY, 배경배율2.00, Actual SVR3, GPU780 및 MESS8을 유지했다. 선로3,703개/Triplex1,177개와 전체 Parent Terminal 최대 선로부하율 목적함수는 보존했다. Planning12 RegControl과 Actual 추가9개 단상 제어기(3 Bank)는 역할이 다르다.

보존한 B0 평가96의 전체/MV 최대 선로부하율은75.711008%, LV46.810643%, 차이28.900365pp다. 전압은0.951568~1.040377pu다. 새 엔진 두 개의120슬롯 Fresh에서 선로·전압·변압기 배열 최대 오차0, 상태와 Queue 일치를 확인했다. Prefix23초 저전압/18초 과전압 등 모든 이벤트 진단은 삭제하지 않았다. 공식 판정은 원본 최종 틱 계약이다.

| 증거 | 상태 |
|---|---|
| A1_VARIABLE_AIDC_FULL_NATIVE0.json | PASS |
| A2_FIXED_M1_FULL_NATIVE0.json | PASS |
| M2_FIXED_A2_STATIC_NATIVE0.json | PASS |
| M1_ORIGINAL_FULL_VALIDATOR_BINDING.json | PASS |
| M2_ORIGINAL_FULL_VALIDATOR_BINDING.json | PASS |
| A_PRODUCTION_ENTRY_BINDING.json | PASS |
| K48_WHOLE_CASE_PACKET_BINDING.json | PASS |
| K48_ACTUAL_NATIVE0_READBACK.json | PASS |
| STAGE_M_RUNTIME_BINDING.json | PASS |
| BEAM_DIRECT_JOINT_MESS8_BINDING.json | PASS |
| PRODUCTION_M1_CURRENT_CASE_NATIVE0.json | PASS |
| PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json | PASS |
| ACTUAL_SOURCE_POLICY_PREPARATION.json | PASS |
| ACTUAL_MIGRATION_EVENT_FIXTURE.json | PASS |
| ACTUAL_FULL120_FRESH_HANDLER_FIXTURE.json | PASS |
| CAMPAIGN_PRESTART_EXECUTION_GUARDS.json | PASS |
| CAMPAIGN_MEMORY_POLICY.json | PASS |
| GUROBI_ASCII_FILE_IO_CERTIFICATION.json | PASS |
| SIGNED_ACTUAL_POLICY_GRID_BINDING.json | PASS |
| A_STAGE_R043_TIMING_AUTHORITY_20261023.json | PASS |
| V2_ADD_OPTIMIZATION_VERIFICATION_20261023.json | PASS |

A1/A2 Native0는 원본 canonical active kernel과117개 완전 로컬 Pricing 블록을 모두 구성한 결과다. 단일 거대 Monolithic Job Native 모델 PASS로 보고하지 않는다. M2는 비영 A2 유한 Witness의 C1을 고정해 새 RHS·Bound·정적 제거 증명과 Native0/독립 FULL 복원을 검사했다. Witness는 최적화된 M1/A2나 공식 캠페인 결과가 아니다.

기준 Direct Joint Native0는1,740,221행·1,011,235열·49,178,740 Nonzero, 238.982초·Peak RSS3.597GiB다. 새 동일 패킷의 실제 Native 행렬 전체 CSR SHA가 e47d287bb577206eb5d76a7c78d30807ceffe8a4c2ba253880bfaf0ca4b7fa7b와 일치해야 한다. RHS·Sense·Bounds·Types·목적함수 검사는 유지한다. 별도 수치 Canary는 실제 K48·HiGHS Beam·Direct Joint 및 원본 A elastic LP를 실행하며, 해당 수치와 Runtime은 공식 결과로 이식하지 않는다. 수치 Canary의 PASS와 현재 Source 재검증은 최종 관문의 필수 조건이다.

| 동일 입력 측정 구간 | Before 초 | After 초 |
|---|---:|---:|

A1의 이전 broader-domain 준비는 부분 실행 중 종료되어 완전한 Before 시간을 주장하지 않는다. A2의 과거 좁은 WINDOW 결과는 복원한 원본 도메인과 같은 문제의 성능 비교로 사용하지 않는다. 사용자의 추가 지시로 별도 성능 비교는 중단했다. 추가 중복 행78개의 제거와 미검증 active-key 압축은 채택하지 않았으며 정적 모델 행·열·Nonzero 규모와 원본 후보를 유지했다.

시작시간 권위 판정: 원본 소스는 reference start와 WINDOW 끝을 hard release로 정의하지 않으며 latest_completion은 표현 범위다. protected/high/urgent/unknown 고정 시점, submit/event, 정확한 service와 모든 Capacity/QoS/Carryout 검증은 유지했다. 따라서 과거 Adapter의 WINDOW 교차를 제거했다. 전체1,499개 Job 중1,395개에 걸친121,313개 복원 시작은 원본 local hard validation을 통과했다. 모든 후보의 동시 실행 가능성을 주장하지 않으며, reference joint schedule의 전체 자원 검증과 각 최적화 Incumbent의 독립 FULL 검증을 별도로 수행한다.

실제 B0 Handler는2,498개 Job의 서비스·Carryout·GPUh·C1을 재생했다. B1/B3의 비영 Migration은 별도 명명 Fixture에서 원본 Controller와 WAN/보류/재시작 구간으로 검증했다. Source 의도적 QoS 예산, 실제 시작/완료 초과, 연구용 Known 정책을 구분하며 고객 SLA 인증을 주장하지 않는다. 최적화된 B1/B2/B3 Actual 물리 결과는 캠페인에서 계산한다.

캐시와 재개: 동일 수치 입력의 순수 Native0 K16 구성만 원본 독립 Verifier로 재인증할 수 있다. 과거 UB/LB/Point/Native clock은 가져오지 않는다. 완료 Stage는 파일/결과/날짜/Source SHA로 복원한다. 실패 M은 명시적 재진입과 원본 원장 조정 후 남은 예산으로만 재개하며 A/Actual의 비저장 실시간 상태는 자동 재개하지 않는다.

사용자의2026-10-23 지시는 모든 관문 통과 후 May01 전체 Arm 실행을 승인한다. 승인 파일은 지시 원문·최종 인증·현재 Source/Hardware/Input/Budget 및 V44 중단 증거의 SHA와 연결된다. Runtime은 `static_complete/official_stage_campaign/<새 디렉터리>` 하위다. Worker1/A Threads1/M Threads4, A각7200초·Gap0.005, K48각300초 별도/Joint각3600초·단일300초·M Gap0.03이다. Native 측정 Runtime만 차감하며 생성·검증 Wall/CPU 시간은 별도로 보존한다.

현장 GIS/보호 설비 검증은 FIELD_INSTALLATION_UNVERIFIED로 별도 표시한다. 연구용 시뮬레이션 물리 인증과 혼동하지 않는다. 기존 V44/V1_add 소스·Worker·원장·캠페인과 May02~07은 변경하지 않았다.

남은 필수 증거: 없음. 수치 최적화 성과는 승인 후 캠페인의 계산 대상이다.
