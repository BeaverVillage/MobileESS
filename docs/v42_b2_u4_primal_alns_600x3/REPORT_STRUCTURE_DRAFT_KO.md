# B2 U4 Primal ALNS 600초 × 3 — 보고서 구성 초안

이 파일은 결과 확정 전의 구성 초안이다. 최종 보고서는 세 알고리즘의 모든 호출, 원본 FULL 검증, 예산·Source·자원 독립 감사를 완료한 뒤 작성한다.

1. 검증된 최종 UB, 유지한 K48 Global LB, Global Gap, 우승 알고리즘과 채택 범위.
2. PR215 정확한 base, Source18r/Case/원본 FULL matrix·domain/초기 U4 point SHA와 같은 시작점 증거.
3. PR169/179/183/194/207/211/214/215 원문 결과 비교. U4 38.507초 제한 OPTIMAL의 의미와 전체 FULL 전역 최적성의 구분.
4. 현재 Source18r U4의 실제 Mode/Pch/Pdis/Q/SOC/이동 분석. 별도 SHA인 RAW00와 권위 초기 FINAL point의 구분.
5. N1 전체 384 Mode 개방, N2 한 차량 96 Mode와 경로 개방, N3 두 차량 192 Mode와 경로 개방의 정확한 차이. 전체 96슬롯·97 SOC·PCS16·ETA·이동에너지·모든 Grid 유지.
6. 실제 signed thermal/전압/current 민감도, 실제 중심점의 점유 DAG vertex와 원본 허용 Arc, 사전 충전·ETA·방전·후속 SOC 복원을 이용한 유한 후보 정책. 새 중심점마다 원본 Security 814,560행 재선정·정확한 helper 복원·독립 감사.
7. 제한영역이 원본 FULL에 포함되는 증명, 중심점 Hamming 거리 0, 차량별 이산 고정과 continuous route/alias 고정, 연속 P/Q/SOC bound 불변. 제한 BestBound는 Global LB가 아님.
8. 모든 Native 호출의 후보·중심 UB·개방 Binary·radius·TimeLimit·실측 Runtime·build/replay wall·incumbent·제한 bound/gap·종료 상태·Peak RSS/Private Commit. 건너뛴 동일 signature와 실패도 보존.
9. 모든 Raw incumbent/FULL Replay 성공·실패와 iteration별 UB 궤적. 첫 개선 시각은 이후 FULL PASS한 Raw point의 Native 발견 시각이며 FULL 검증은 worker 종료 뒤 수행됨.
10. 필수 Original U4/N1/N2/N3 비교표, 차량별 96슬롯 운전계획과 이동·충방전·Q·SOC·terminal·rebound, 원본 Critical Row 변화.
11. N1 실행 중 준비 파일 변경 사건: 정확한 epoch01 bytes·Native 모델·정식화 동등성 증거, N1 재실행 0, N2/N3 새로운 Native0/epoch02 seal, 원본 Source 불변.
12. 600초 actual 누적 예산과 정상 OPTIMAL 조기 종료. 요청 TimeLimit 합계/실제 Native/반환 overhead/모델 생성/검증/보고 wall을 구분. 관측 worktree 생성 UTC 2026-10-12T03:11:44Z부터 보고 시점까지의 wall을 별도 표시하며 그 이전 chat 읽기는 미계측.
13. 같은 시작점·각 600초 상한의 성능 비교 한계. N1은 4대 Mode, N2는 1대, N3는 2대 Mode를 개방하므로 순수 이동 효과만을 분리한 비교는 아님.
14. 유지 K32 기본 LB 및 같은 Source/Case K48 stronger LB provenance. 추가 LB 최적화 0, unrestricted Full B&B 0, Actual=ACTUAL_NOT_RUN.
15. B1 worker/task/supervisor·예약 비활성/원본 Source/과거 결과 보존 감사, 5월 전체 캠페인·B3·IEEE8500 실행 0. 한 날짜 연구 결과의 후속 채택 판단과 캠페인 적용을 실제 실행하는 일은 구분.

최종 비교표에는 초기·최종 검증 UB, 절대·상대 개선, 최초/최선 확보 Native 시각, 개선 횟수, 총 Native/전체 wall, 이동 횟수·에너지, 충방전 AC kWh, SOC 범위, FULL Replay, 최종 Global Gap을 넣는다. Original U4는 역사적 38.507초이므로 신규 600초 상한과 같은 실제 사용시간이라고 표현하지 않는다.
