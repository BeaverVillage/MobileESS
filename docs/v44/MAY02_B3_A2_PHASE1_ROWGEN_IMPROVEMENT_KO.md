# May02 B3 A2 Phase I Row Generation 개선

기록 시각 UTC: 2026-10-17T14:32:41.624387+00:00. 상태: **RUNNING**. 대상: `D:\MobileESS_V44\runtime\v43_planning_svr12_actual_v1\campaign004\2025-05-02\B3\attempt005`. PR: https://github.com/BeaverVillage/MobileESS/pull/233

r021에서 19회 후 및 Column Activation 후 전체 행을 강제 투입하던 두 분기를 V44 전용 어댑터에서 제거했다. 원본 동결 파일은 수정하지 않았다. 기존 certified_separate/restricted/elastic_master/verify_zero와 원본 inclusion/Fraction/primal/dual 검증을 재사용한다.

활성 글로벌 행은 resource의 family/site/slot, voltage의 family/slot/node, 기타 행의 원본 Source Row 및 전체 글로벌 계수·RHS·Sense·Bounds SHA로 대응시킨다. 새 Local Hard 제약은 모두 유지한다. 실제 3개 클래스의 열 확장에서 대응 및 이전 Phi 보존을 Native0로 검증했다.

모든 누락 원본 행을 검사한다. 행별 위반이 1e-6 이하여도 Full Phi 기여가 남으면 선택적으로 추가한다. 원시 Solver 인공변수는 그대로 복사하고, 누락 행의 residual은 별도 full lift에 포함한다. 종료는 Full Phi ≤1e-8 및 원본 최대 위반 ≤1e-6이다. 초기 batch256, 정체 시 최대16384까지 늘리며, 횟수에 따른 전체 행 승격은 없다. P1 본문은 원본과 동일하다.

B1은 실제 A1, B3는 A2 실행 경로에 연결했다. 공통 B1/B3 A2 어댑터도 지원한다. May02 B3 A2 pilot PASS 후 이후 미실행 단계에 적용하며 기존 PASS는 재계산하지 않는다. 스케일링 Revision은 적용하지 않았다.

실제 May02 입력의 동일 잔여량 분석: 93.089초 → 3.612초. 결과·순위·CSV가 일치했다. 희소행렬 원소 반복 조회를 묶음 조회로 바꾸고 축 인덱스를 재사용했다. 전체 가중 Phi의 정확한 Fraction 합도 일치했다. 이 수치를 A2 전체 속도 향상률로 해석하지 않는다.

| 측정 | 기존 attempt004 | r022 attempt005 |
|---|---:|---:|
| 최대 Phase I 행 | 804735 | 미측정 |
| 최대 변수 | 789851 | 미측정 |
| 최대 NNZ | 14853629 | 미측정 |
| 측정 최대 RSS bytes | 15157084160 | 미측정 |
| Phase I LP Native 초 | 378.960000038147 | 0.0 |
| 최대 추정 Kappa | 1.260680997159824e+18 | 미측정 |
| Barrier iteration | 0.0 | 0.0 |
| A2 Native 누계 초 | 486.14000034332275 | 0.0 |
| A2 원장 Wall 초 | 4445.492863599997 | 1.5300000086426735e-05 |

기존 S7 참고값: 행791672, 원래변수94158, 인공변수689928(88.0%), NNZ14771533, Native33.817초, 추정 Kappa1.051286e18. 표의 최대값은 중단 시점까지 전체 Phase I 구간이다. 새 모델의 지원 후보와 반복 수가 달라질 수 있어 각 solve를 동일 문제 크기의 속도 비교로 주장하지 않는다.

Full Phase I Zero: False. P1 Full Pricing: False. A2 PASS: 미완료. M2: 미실행. Actual/Fresh 최종 PASS: 미완료.

기존 PASS 13개 Case와 May02 B3 M1의 원본 파일을 SHA로 보존 검증한다. 같은 날 B1 A1 및 M1의 원본 FULL 가능해, Fixed Plan SHA, Q250, Physical Domain, Hardware, Time Axis를 Native0로 독립 재검산했다. 새 A2는 완료 M1을 읽고 새 Attempt의 독립5400초 원장을 0초부터 사용한다. 과거486.140000343초 및381개 호출은 attempt004에 그대로 남아 있다.

세부 원장: `AUTONOMOUS_RECOVERY/R022_MEASURED_COMPARISON.json`, `R022_CHANGE_AND_VALIDATION.json`, `R022_SEALED.json`, `R022_PASS_AND_M1_PRESERVATION_BASELINE.json`, 새 Attempt의 `PARENT_VERIFICATION/R022_PARENT_COMPATIBILITY.json` 및 `FRESH_A2_RESTART_ADMISSION.json`. 미완료 인증 및 아직 측정되지 않은 전체 속도·조건수 개선은 주장하지 않는다.
