# V2_add — PR236

실제 IEEE8500 Balanced G1 매핑·G2 B0 9개 beta·G3 제어 Pilot을 완료했다. 원래 59개 정적 검증은 재사용했다.

- [최신 한국어 결과](FINAL_V2_ADD_REVIEW_KO.md)
- [분리한 G1~G4 Gate](PREFLIGHT_GATES.json)
- [실제 Scale별 결과](BACKGROUND_SCALE_SCREENING.csv)
- [실행 가능한 Pilot의 전역 효과](CONTROL_PILOT_GLOBAL_COMPARISON.csv)
- [원본 설정 사전 동결](PHYSICAL_CONFIGURATION_FREEZE.json)

G1 PASS / G2 완료 / G3 MESS·Planning 제한 witness 완료/Actual 비영 AIDC 미검증 / G4 미실행. 허용 beta의 Actual B0가 모두70% 미만이므로 Primary Scenario는 없다.

실행 순서: `python -B -m v2_add_preflight.gates` → `screen` → `pilot` → `results`.
`screen`은 완료 case의 receipt를 재사용한다. `audit`/`verify`는 초기 준비 단계 전용이며 현 단계에서 재실행하지 않는다.
조밀한 원본 AC 배열은 독립 V2_add_runtime/phase2 아래에 보존하며 경로·SHA와 재계산 가능한 지표를 PR에 기록한다. 장시간 Native/Solver 호출은 없다.
