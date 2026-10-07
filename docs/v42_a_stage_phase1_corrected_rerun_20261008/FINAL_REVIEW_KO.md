# PR174 corrected May19 rerun 최종 검토

분류: **PHASE1_TRACTABILITY_FAIL** / 과학적 상태 **INCONCLUSIVE**. 종료 사유: EARLY_SINGLE_CUMULATIVE_900_BUDGET.

정확한 base HEAD: `5d88890fe7ade1afff6f9faf69cc914aa69567e0` ([Draft PR174](https://github.com/BeaverVillage/MobileESS/pull/174)). 실제 실행 소스 HEAD: `108178b64a3148dc0375aeed9491f9d4995821ae`. [새 Draft PR](https://github.com/BeaverVillage/MobileESS/pull/176).

May19를 단 한 번 실행했다. 900초 누적 예산, Threads=1, 최대4 pricing workers, 고정16-column/24-class 규칙, 연속3회1% 미만 stagnation 규칙을 유지했다. 원래 초기 모델에서 시작했으며 이전 실험 raw point를 warm start로 재사용하지 않았다.

| Master | status | raw Phi | native s | Work | certified zero |
|---|---:|---:|---:|---:|---|
| R0 | 2.0 | 0.0066267766210857523 | 278.3310000896454 | 473.49557240539525 | False |
| R1 | 2.0 | 0.0066274496879938976 | 128.32699990272522 | 362.8752659003294 | False |
| R2 | 2.0 | 0.0066266827273885193 | 210.46199989318848 | 401.7188458926357 | False |

OPTIMAL(status2) solve만 인증된 궤적에 포함한다. TIME_LIMIT9 / INTERRUPTED11의 저장된 raw point는 진단값이며 최적값 인증이 아니다. zero는 unchanged1e-8 기준 및 원래 artificial-free rows/bounds1e-6 replay를 함께 요구한다.

- **인증된 Phi trajectory:** [0.006626776621085752, 0.006627449687993898, 0.006626682727388519]
- **Phase-I master solves:** 3
- **activation rounds:** 3
- **활성화 STAY / migration:** (48, 0)
- **완료 partial batches:** 3
- **iteration별 consumed / exact receipts / valid negative / actual native class calls:** [('R0', 17, 17, 16, 19), ('R1', 18, 18, 16, 18), ('R2', 19, 19, 16, 17), ('R3', 0, 0, 0, 0)]
- **native seconds / Work:** (622.385000705719, 1243.191191441634)
- **wall / accounted / persistence overshoot seconds:** (904.3412208999798, 904.3412231999973, 4.34122319999733)
- **final original active rows/cols/nnz:** {'rows': 713288, 'cols': 83863, 'nnz': 13756154}
- **maximum factor nnz / estimated GB:** (16100000.0, 0.4)
- **certified Phi=0 / stagnation:** (False, False)
- **prior-point witnesses:** [('R1', True, '488969809451242447/73786976294838206464', '488969809451242447/73786976294838206464'), ('R2', True, '489019473023238619/73786976294838206464', '489019473023238619/73786976294838206464'), ('R3', True, '488962881319230465/73786976294838206464', '488962881319230465/73786976294838206464')]
- **1-worker/4-worker exact equivalence:** True
- **verification / qualification tests:** (True, 130)
- **영구 삭제 / physics or tolerance 변경:** (0, 0)

| Iteration | original rows / cols / nnz | auxiliary rows / cols / nnz | active STAY / migration |
|---|---|---|---|
| 0 | 712791 / 83751 / 13751140 | 712791 / 779175 / 14446564 | 35893 / 128 |
| 1 | 713105 / 83819 / 13752921 | 713105 / 779243 / 14448345 | 35909 / 128 |
| 2 | 713105 / 83835 / 13754519 | 713105 / 779259 / 14449943 | 35925 / 128 |
| 3 | 713288 / 83863 / 13756154 | 713288 / 779287 / 14451578 | 35941 / 128 |

raw Phi가 증가해도 이전 해가 같은 Phi로 확장 모델에 포함되면 실제 악화로 분류하지 않는다. 이전 raw 해를 보존하고 별도의 포함 증명을 검증했다. raw Phi는 덮어쓰지 않으며, stagnation 감소율도 raw Phi 그대로 적용했다.

P1, final closure, May17/May12/May10, production/Planning/Actual/Fresh AC는 미실행이다. 어떤 과학적 후보도 영구 삭제하지 않았다. 완전150/150 closure, full-domain infeasibility, integer feasibility 또는 production acceptance를 주장하지 않는다. 재실행, parameter sweep 또는 자동 후속 실행은 하지 않았다.

가격 완료 클래스와 실제 lookahead/중단 배치의 호출은 PRICING_CLASS_CENSUS.json 및 NATIVE_RUN_SOURCES.csv에 구분한다. 모든 실제 native 모델 크기/factor/RSS는 ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv에 기록한다. 추가 solve 없이 저장된 자료만 재검증했다.

활성화 수는 독립 검증된 concrete class-column 수다. 각 column은 해당 클래스의 모든 job을 같은 물리 경로에 배정한다. 실제 native primitive 변수 증가 수는 모델 cols 차이로 별도 기록한다.

총48개 활성화 중 마지막16개는 budget 종료로 재-solve되지 않았다. 마지막 인증 Phi는32개 추가 상태의 R2 값이다. R3 빌드 모델에 이전 R2 해가 동일 Phi로 포함되는지도 solve 없이 검증했다. 네 번째 optimize는 미진입이다.

정확한 최종 HEAD / remote / Draft / clean tree는 외부 [FINAL_PUBLICATION_RECEIPT.json](C:/Users/kjw39/Documents/Codex/2026-10-07/v42-a-stage-corrected-static/FINAL_PUBLICATION_RECEIPT.json)에 고정한다. 자기 commit 해시 순환참조를 피하기 위한 출판 영수증이다.
