# V2_add PR #236 최종 Prestart 검토

**PRESTART_BLOCKED_WITH_EVIDENCE**. READY가 아니다. 공식 B0/B1/B2/B3 캠페인·장시간 A1/M1/A2/M2/K48·월간 Worker를 실행하지 않았다. 같은 Draft PR #236, 기준 `d3b9f38c473a9304a7cd1d652ba2bd51cf2f51c2`, 원본 `affc7226a519adbe072d7debbc3ae25ea71c3487`를 유지했다.

실제 진척은 두 피크의 전체96 AC/Fresh Pilot,72개 위치별 AC 응답, 원본 FULL Job 캐시 수용 차단, 거부 사유를 포함한 인과적 Job 재생,4/8대 원본 이동/PQ/SOC Native0 모델 생성과 실행 HOLD/Checkpoint 스케줄러이다. 기존308개 V2_add 파일과 과거 S0/S1 기록은 변경하지 않았다.

| 이동 블록 실측 | Binary | Continuous | Rows | Nonzeros | Build초 | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
|4대|208,312|27,215|207,488|1,263,916|28.45|389.4|
|8대|417,296|54,513|414,440|2,531,845|31.81|667.4|

이 표는 **Grid rows가 없는 원본 이동 블록+Q250+STA 점유의 실제 생성**이다. 실제 IEEE8500 FULL 모델 생성이나 성능 인증으로 표현하지 않는다. IEEE8500 DSS 모델/AC 배열과 Native 이동 모델을 각각 만들었지만 둘을 합친96슬롯 FULL 계수/Matrix는 미완료다. K48 Root/Pricing/DirectJoint 시간과 FULL Native 예상 시간은 null이다. 원래 budget을 줄이거나 Route를 추가 삭제하지 않았다. 첫 생성의 과도한 자원 관측 overhead는 자체 진단만 종료하여 보존했고 동일 수학으로 다시 생성했다. 생산 Worker는 종료하지 않았다.

1. **SVR3으로 Prefix/전체 시간대를 인증했는가?** 아니다. 평가96 PASS, Prefix 저23초/고18초 및 Planning TIME 과전압이 남는다.
2. **최종 β와 모든 날짜 안전성은?** β2.00은 우선 후보이며 최종 동결이 아니다. May02–07 IEEE8500 안전 재생은 미실행이다.
3. **원본780GPU 실제 유연전력은?** 인증된 비영 값은 미확정. 관측 비영 사전배치 재생은 기준 FCFS/C1 불일치와 작업량/tail/FULL 미완료로 거부했다.
4. **AIDC 확대가 필요한가?** 입증하지 못했다. GPU/kW/UID 복제로 확대하지 않았고 원본780을 유지한다.
5. **C2 위치와 교통망은 적합한가?** MV3상 연결과 공통 도식 방향276쌍 PASS. layout 오차2.54–14.73km 상당이며 실제 GIS/도로 접근성은 미인증이다.
6. **MESS8 초기 위치 유지가 적합한가?** 기준으로 유지한다. 추가4대는 기존 사전 등록 가정이며 우월한 최적 배치 인증은 아니다.
7. **8대로 오전/저녁 피크를 동시에 낮출 수 있는가?** 평가96에서 유한 STAY Pilot 개선1.920869/1.966819%p와 Fresh를 확보했다. 새 피크76이며 B3/MOVE 최적화는 아니다.
8. **8대 P/Q/SOC/MOVE/STAY가 원본과 일치하는가?** 원본 이동/PQ/SOC 생성자와 Q250 overlay로8대 Native0를 만들었다. STA 점유 추가 물리 계약, IDC 충전, 전체 Grid FULL 동등성은 미완료다.
9. **A1–M1–A2–M2/K48/Beam/Joint 이식이 끝났는가?** 아니다. Native 네 Stage 소형 호출 경로와 이동 모델은 확인했지만 전체 IEEE8500 계수·원본 case/authority·K48/Beam/Joint 연결은 남았다.
10. **FULL 및 UB/LB/Gap 계약은 정상인가?** 기존 함수/수학은 보존하고 캐시414를 실제 Adapter에서 거부한다. 새 FULL feasible point/독립 Global LB/Gap은 미인증이다.
11. **May01–07 입력과 환경은 준비됐는가?** 7일 원본 파일 SHA는 모두 PASS. 신규8500 날짜별 AC/Fresh/전체 Native0 및 실제 Stage handlers가 없어 캠페인 환경 전체는 미완료다.
12. **공식 캠페인 전 차단 사유는?** 초기 인과 운전 이력/전체 전압, AIDC 동일 기준 FULL witness, IDC12 차량 포트, 전체8500 FULL/K48/Joint 이식, 날짜 간 검증이 남는다.

## 비교 계약과 후속 구현

Planning은 기본 IEEE8500 Reg12, Actual은 Reg12+SVR3 후보이며 같은 Actual 설비·정책을 모든 arm/날짜에 적용해야 한다. 기존 IEEE1237/43 및120개 변압기 current-row guard를 숫자만 치환해 통과시키지 않았다. 원본3703선로/1177Triplex/Parent 목적함수/양단 안전/.95–1.05/모든 원본 변압기와 신규 SVR 정격은 AC에서 유지한다. Native FULL에 같은 축의 계수를 생성·바인딩해야 한다.

`prestart_acceptance`는 캐시 및 새 A1/A2 결과를 Original FULL Job·공동 자원·동일 case Grid·독립 LB/Gap에 연결하는 수용 경로이다. `prestart_execution`은 원본 CHAINS, 동일 case hash, artifact SHA, 실패 날짜 격리, 재시작 시 미정산 ledger 차단과 OS 중복 방지를 구현한다. 테스트용 handler는 실제 Stage 연결 인증이 아니다. 실제 r043 Worker/Current AC/독립 FULL/프리픽스 상태·계수 Authority와 연결한 전체 검증이 남아있으므로 `real_FULL_stage_adapters_bound=false`로 유지한다.

May01은 이미 노출된 개발일이다. May02–07 원본 Forecast/Actual/PV/Weather/Job/GPU/C1/교통/초기 상태의 파일들은 manifest로 확인했으며 신규 계통 날짜 간 적합성을 확인한 것은 아니다. May08–31 확장은 별도이며 새 Worker를 만들지 않았다.

실행 명령과 Runtime/budget/worker/시작 점검은 CAMPAIGN_EXECUTION_HOLD.json에 기록했다. 명령은 현재 차단된다. 모든 Gate가 실제로 통과한 뒤 동일 시나리오·원본 정책을 동결하고 별도의 명시적 사용자 캠페인 실행 허가가 필요하다. 현 단계에서는 실행 허가를 요청하지 않는다.

검증 결과: 13개 새 검사, PASS=True. 이전17개 검사는 기존 봉인 결과로 재사용하며 이번 실행 숫자에 합치지 않는다. Fixture 통과만으로 READY를 만들지 않는다.
