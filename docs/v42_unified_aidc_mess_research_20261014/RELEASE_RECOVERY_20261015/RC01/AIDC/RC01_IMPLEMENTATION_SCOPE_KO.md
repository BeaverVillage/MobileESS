# RC01 AIDC 검증 범위

이 비교는 승인된 PR223 자정 초기 상태(324 Running / 472 GPU / 1300 Pending), 원본 Reference Queue 및 PRE_DDAY_START_COMMAND_NOT_REPLAYED fallback, 저장된 B3 M2를 재사용하는 Actual 진단이다. 새 D0 A1→M1→A2→M2 체인의 결과가 아니다.

- Known의 원본 명령과 fallback을 보존한다. 실제 현재 GPU 충돌이 발생한 Pending Known에만 Source 권한·준비·QoS·현재 후보 AC를 확인하는 corrective 경로를 적용한다. C0/C1에 공통이다.
- Unknown 최초 사이트는 기존 인과적 Reference Scheduler의 기본 사이트다. Signed Sensitivity는 최초 지정에 사용하지 않는다. 기존 연구 최초 배치 권한은 고객 Source 승인이나 사이트 변경 권한을 뜻하지 않는다. GPU는 실제 Start에서만 등록한다.
- C0는 기본 사이트 STAY다. C1은 Pending 상태의 승인된 대체 사이트만 평가하고, 공개 Q50 관련 구간의 조건부 후보 AC 최대 phase-line loading이 STAY보다 작은 경우에만 변경한다. 대안 부재·미준비·예측 미인증 시 STAY를 유지한다.
- Unknown의 QoS 비교용 reference_start는 기존 CurrentEvent 승인 계약상 hard earliest가 아니다. Source Submit/Release/Hard earliest/표현 가능한 시작 시각과 현재 물리 실행 가능성을 적용한다. 과거 shadow FCFS 대기시간의 완전 재현을 주장하지 않는다.
- 현재 후보 AC는 관측·원본 LASTCHANGED가 모두 현재 시각 이하인 Demand/PV 및 NOAA 시간 관측을 사용한다. 시간 관측의 가용성을 관측 시각으로 보는 모델이며 과거 실제 ingestion 시각 인증은 아니다. 미래 시간 보간을 사용하지 않는다.
- 과거 prefix는 이미 관측된 Start/Completion의 [start, completion) 구간을 적분한 평균 GPU와 Original C1 P/Q다. 미래 완료를 사용하지 않는다. 현재 입장은 현재 Running GPU에 후보 전체 gang을 더해 재확인한다.
- 원본 11 SVR, 7 RegControl, 0 CapControl, .95–1.05 pu, 선로 NormalAmps, 변압기 전류·kVA·추가 SVR nameplate를 유지한다. 과거 완료 슬롯의 AUTO substeps와 현재 시각 SolveSnap을 구분한다.
- Forecast/off-anchor AUTO secant Affine는 현재 입장이나 Pre-site 순위의 인증 근거가 아니다. 조건부 공개 입력 예측의 미래 AUTO 동작은 Actual tap 관측이나 현재 admission 상태가 아니다.

실제 실행 수치와 상태는 각 시도별 EXECUTED_SOURCE 및 결과 파일로만 확인한다. 중단된 첫 시도는 INCOMPLETE이며 실제 첫 Unknown 또는 16슬롯 PASS로 사용할 수 없다. Native optimize/presolve/IIS를 전역 차단한다.
