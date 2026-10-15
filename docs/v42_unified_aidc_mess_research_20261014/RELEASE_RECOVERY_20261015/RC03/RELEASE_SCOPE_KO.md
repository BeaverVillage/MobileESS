# RC03 평가 범위와 후속 실행 조건

이번 변경의 주 연구 환경은 R1이다. 기존 FLEX30 적격 PENDING 작업에 대해 Source-Compatible 사이트에서 입력을 공통 접근할 수 있다는 가정을 별도 연구 계약으로 봉인한다. 이 계약은 Kestrel에서 관측한 데이터 복제, 고객 승인 또는 WAN 전송 완료 기록이 아니다. 원본의 명시적 금지와 기존 Release/Deadline/QoS는 그대로 적용한다. 근거 문헌과 적용 한계는 [문헌 검토](LITERATURE/RESEARCH_MODEL_JUSTIFICATION_KO.md)에 있다.

실행 순서는 `실제 Unknown 도착 → 기존 기본 사이트 지정 → PENDING Pre-site → 실제 Start`다. STAY는 항상 후보이며, 최초 배치에 계통 민감도를 적용하지 않는다. GPU Gang/Rack와 데이터 계약, QoS, 현재 후보 AC를 통과한 대안에만 공개 Q50 구간의 최대 선로·상 부하율 비교를 적용한다. RUNNING 이동과 추가 시간 이동 권한을 부여하지 않는다.

공식 물리 판정은 사용자 정정에 따른 **원본 900초 × 96슬롯의 `settle_slot → measure_full_network` 정착 AC**다. 원본 11-SVR, 7 RegControl, AUTO, LDC, Delay/TapDelay 및 제어 이력을 유지한다. 전압, 전체 선로·상 전류, 변압기 전류/kVA를 검사한다. ASOF substep에서 확인한 0.92035–1.08366 pu 위반은 별도 물리 진단으로 보존하며 공식 정착 Gate를 자동 차단하지 않는다. 정착 PASS는 슬롯 내부 연속시간 안전성 인증을 뜻하지 않는다.

다음 범위는 서로 승격하거나 합치지 않는다.

| 증거 | 해석 |
|---|---|
| Source-strict RC01 첫 16슬롯 | 기존 기본 배치와 권한 부재 조건의 역사 결과. Pre-site 0건 |
| RC03 R1/R2 첫 16슬롯 | 같은 초기 상태·Known 명령·원본 C1 모델·고정 PR223 M2를 사용한 별도 연구 Case의 실제 실행 비교 |
| 현재 D0 A1 P1 | 성공한 원본 FULL 실행 가능점 보존. Native P1 Gap 0%는 해당 Native 도메인의 결과 |
| 날짜별 31개 D0/CC4/공개 Actual 입력 | 입력 준비 완료. 31일 최적화 또는 Actual 실행 성공이 아님 |
| 현재 D0 M1/A2/M2 | 새 Native 승인 전 NOT_RUN. 과거 M2의 물리 PASS를 이전하지 않음 |
| 현재 D0 Full96·May31 | 새 단계의 FULL 수용과 현재 Case의 Actual/Fresh 이후에만 판정 |

Actual 평가 Case는 원래 Planning identity를 변경하지 않고, Planning Source, 최종 A2/M2 결과·수용 SHA, Actual 정책, 연구 계약, Initial SHA, 슬롯 수와 정착 Clock 계약을 묶어 별도로 계산한다. Source-strict/R1/R2와 C0/C1, 첫 16슬롯/96슬롯의 Case SHA가 구분된다. 원시 Actual 실행 원장, 실제 P/Q trace, Fresh 슬롯별 배열 및 Actual 전용 Source 동결 파일까지 재검증해야 생산 Gate가 통과한다. 호출자가 작성한 PASS 문자열이나 다른 Case의 요약은 Gate를 대신할 수 없다.

후속 Native 실행은 사용자 지시대로 **새로운 별도 승인**이 필요하다. 기존 318.681/360초 원장과 A1 전용 180초 원장(사용 50.622초)은 보존한다. A1 전용 잔여분을 재사용하지 않는다. 첫 제안은 M1 180 + A2 120 + M2 180초에 반환 30초와 overshoot 여유 60초를 더한 570초이며 아직 승인된 예산이 아니다. 이후 완료한 Planning 원장을 읽기 전용으로 보존하고, 현재 Case 포함성 검증이 끝난 K48에 별도 원장과 새 승인을 사용한다. K48 제안은 Native cap 180 + 반환 30 + overshoot 60 = 270초다. 두 승인 상한을 모두 합하면 840초이며 실제 소비량이나 완료시간 보장이 아니다. 앞선 750초 문서는 단일 원장을 상정했던 미승인 역사 제안으로 보존하며, 현재 두 원장 경로에 대한 실행 승인으로 사용하지 않는다.

P1-only `A1 → M1 → A2 → M2`, P2 Native 0회를 유지한다. 현재 D0 Full96 및 필요한 Gate가 통과하기 전에는 최종 Release Freeze, May31 캠페인 PASS 또는 캠페인 Pre-site 개선을 주장하지 않는다. RC01/RC02의 앞선 차단 설명은 각 작성 시점의 역사 기록으로 보존하며, ASOF 진단의 공식 Gate 사용 여부와 R1 연구 가정의 승인 범위에는 본 문서와 사용자의 최신 정정을 적용한다.
