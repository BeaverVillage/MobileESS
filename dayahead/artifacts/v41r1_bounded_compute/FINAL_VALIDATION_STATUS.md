# 검증 완료 및 실행 보류 기록

2026-09-07 기준, 수정본 May-04 B1 전체 수락검증 `fa/early03`은 PASS입니다. Day-ahead, Fresh OpenDSS, Actual replay, 저장 결과 재읽기 및 A–O 수락 조건을 모두 통과했습니다.

| 검증 대상 | 결과 | 범위 |
|---|---|---|
| 조기 종료 이전 May-04 B1 `fa/03` | 기존 PASS 유지 | 원본과 보존 사본의 해시 유지 |
| 수정본 May-04 B1 `fa/early03` | 최종 PASS | 전체 최적화 + Fresh + Actual |
| 수정본 B3 `fo_early_coordinated_04` | 구성요소 PASS | M1/A1/MF 공유 예산 297.57/300초; B3 전체 일일 실험은 아님 |
| 기존 핵심 회귀검사 | 218 PASS | FULL_REGRESSIONS.xml |
| F&O 회귀검사 | 78 PASS | BOUNDED_REGRESSIONS.xml |
| 조기 종료·시간 제어 검사 | 49 PASS | EARLY_STOP_REGRESSIONS.xml; 일부 F&O 검사와 중복 |
| 실행 관리 검사 | 12 PASS | FO_OPERATIONS_REGRESSIONS.xml |
| 원본 모델·후보 집합 동일성 | PASS | 전체 MPS와 권위 후보 SHA 동일 |
| 전기계수 | 31/31 PASS | 기존 전기계수 입력 유지 |

기존 F&O 대비 최적화 시간은 1769.87초에서 1117.48초로 36.86% 감소했습니다. Fresh·Actual 포함 총 시간은 2005.47초에서 1264.85초로 감소했습니다. 30분 최적화 예산 중 682.52초를 사용하지 않았습니다.

P1–P5는 기존 F&O 및 동일 기준의 B0 독립 평가 원장과 같습니다. 이번 날짜에서 B0 대비 목적값 개선은 없으며, 전역 최적성도 인증하지 않았습니다. 자세한 표는 `B0_VS_B1_OBJECTIVES.md`와 `EARLY_STOP_BEFORE_AFTER.md`에 있습니다.

권위 후보 3,847,255개를 유지했습니다. 방문률 모수인 탐색 대상 3,847,248개 중 1,775,796개를 열었고, 2,071,452개는 `NOT_VISITED_WITHIN_COMPUTE_BUDGET`으로 남았습니다. 후보 제거는 0입니다. 탐색군 방문률과 원시 후보 방문률은 별도 기록했습니다.

중간 시도 `early01`은 너무 짧은 solver 시간 조각에서 초기해를 처리하지 못한 문제, `early02`는 Windows 파일 공유 잠금으로 상태 저장이 실패한 문제로 중단됐습니다. 두 시도와 해당 소스는 보존했으며, 수정 후 `early03`에서 전체 검증을 완료했습니다. 중간 회귀검사 PASS와 최종 일일 수락검증 PASS는 구분합니다.

사용자의 “5월 전체 실행은 우선 하지말고 작업 끝나면 종료해” 지시에 따라 Full May는 보류합니다. 캠페인 재개·수락 결과 편입·watchdog·예약 실행을 수행하지 않습니다. 기존 중지 요청과 일시정지 상태를 유지합니다. B0 비교를 위해 추가 최적화는 실행하지 않았습니다.
