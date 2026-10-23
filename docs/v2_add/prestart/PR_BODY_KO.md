## V2_add IEEE8500 캠페인 전 준비 — PRESTART_BLOCKED_WITH_EVIDENCE

동일 PR #236과 기준 `d3b9f38c473a9304a7cd1d652ba2bd51cf2f51c2`에서 추가했다. 공식 캠페인/장시간 Native/Worker는 실행하지 않았다.

- 두 피크 에너지 분할 실제 AC/Fresh: B0 75.710958% → P-only73.790090%, Q50지원73.744139%. 평가96 이벤트 PASS, 새 피크76. Prefix 저23초/고18초는 그대로이며 B3 성과가 아니다.
- 원본 FULL1499 Job 검증으로 기존 캐시414개 START_WINDOW 위반을 실제 수용 Adapter에서 거부한다. 인과적 사전배치 진단은 재생/Fresh를 했으나 기존 FCFS 전력 및 작업량/tail 동등성이 없어 인증 witness로 거부했다.
- 실제 원본 이동/P300/Q250/PCS400/SOC/Route Native0를4대와8대로 생성했다.8대 각각 MOVE/STAY 자유를 보존한다. 전체 IEEE8500 계수/Grid/K48/Beam/Joint/FULL 연결과 IDC12 충전설비는 미완료다.
- PCC72개 교란과24개 서비스 방향276쌍, May01–07 원본 입력 SHA, Stage scheduler/checkpoint/resume/중복 실행/HOLD를 추가했다. GIS/모든 날짜8500 AC/실제 FULL Stage handlers 미인증을 숨기지 않는다.
- 기존308개 V2_add 파일/과거 AC 기록 보존. 새 검사 13개 PASS=True, Native optimizer0.

최종 한국어 보고: docs/v2_add/prestart/FINAL_PRESTART_REVIEW_KO.md. 필수16개 산출물 및 Runtime SHA Manifest 포함. READY/Primary를 인증하지 않으며 자동 실행을 차단한다.
