# B0/B1/B2 공통 제어 감사 최종 보충 근거

이번 감사 범위에서 공통 제어 구현 오류는 발견되지 않았습니다. 7개 RegControl의 개별·전체 설정 SHA, 활성 상태, 초기 탭, snapshot/static 모드, maxcontroliter=100 및 4개 고정 ON capacitor 상태가 동일합니다. B1/B2 독립 진단 재실행은 기존 전압·전류·탭·capacitor AC 배열 13개를 비트 단위로 재현했습니다. 기존 결과·탭·제어 설정·모델·전압 한계(0.95~1.05 pu)는 보존했습니다.

| Arm | 관측 근거 | 최대 ControlIterations | 최대 Solution.Iterations (합계) | 제어 완료 슬롯 | MaxControlIterations | MaxIterations |
|---|---|---:|---:|---:|---:|---:|
| B0 | 기존 RAW 로그 | 3 | 9 | 96/96 | 100 | 기존 로그 미기록 |
| B1 | 원본 AC 배열 정확 재현 진단 | 3 | 9 | 96/96 | 100 | 15 |
| B2 | 원본 Full P/Q 정확 재현 진단 | 5 | 17 | 96/96 | 100 | 15 |

원래 B1/B2 로그의 반복 횟수는 미기록 상태로 남겨두고, 새 관측치는 별도 진단 자료로 기록했습니다. Solution.Iterations는 제어 반복을 포함한 전체 합계이며, 개별 제어 pass의 한도 카운터와 다릅니다. 따라서 B2 합계 17을 MaxIterations=15 위반으로 해석하지 않습니다. 개별 pass 최대치는 MostIterationsDone API이며 이번 훅에서 별도로 측정하지 않았습니다. [OpenDSSDirect API](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.Iterations), [MostIterationsDone](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.MostIterationsDone)

B2와 B1의 탭 위치는 672개 관측 중 403개에서 다르고, 최대 차이는 0.025입니다. 모든 capacitor 상태는 동일합니다. 실제 P/Q가 다른 상태에서 활성 RegControl이 자체적으로 움직인 기록이며, 설정 SHA 변경은 없습니다. 자세한 7개 설정은 CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv, 슬롯별 탭·활성·capacitor 비교는 CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv, 측정 반복 횟수는 CONTROL_MEASURED_ITERATIONS_288_SLOTS.csv에 있습니다.

B2 원본의 19개 과전압은 Actual 실패로 유지합니다. 이 결과는 이후 날짜의 전압 타당성을 보장하지 않으며, 공식 캠페인 결과를 변경하거나 통과로 승격하지 않습니다. B1 추가 진단은 96 AC 슬롯을 실행했고 optimizer/Native 호출은 0회입니다.
