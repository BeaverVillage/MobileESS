# 물리 Global LB 파일럿 독립 결과 검토

최종 검토 결론은 `VALID_GLOBAL_LB_NONMATERIAL`이며, 이번 고정 가중치 방식의 후속 확대는 기각한다. 네 차량 하위 문제를 실제 정수 다기간 영역으로 푸는 계산 자체는 이번 시간·RAM 안에서 가능했지만, 얻은 Global LB는 3% 목표에 크게 못 미쳤다. 네 하위 문제 모두 Gurobi 수치 계약 아래 OPTIMAL로 끝났으므로 미완료 차량 B&B에 시간을 더 주는 방식으로 이 고정 가중치의 약한 결과를 개선할 근거는 없다.

이 검토자는 Native Solver를 호출하지 않았다. 실제 차량별 RESULT.json, NATIVE_GUROBI.log, NATIVE_LEDGER.json, WEIGHTS.json, 사전 오류 원본과 복구 receipt를 읽고 아래 내용을 독립 재계산했다. 원본 영역의 포함관계와 정확한 열·행 분리 검토는 MATH_REVIEW_KO.md에 기록했다. 원본 CSR 재소거와 전체 숫자 인증의 기계 검증 결과는 INDEPENDENT_NATIVE0.json 및 INDEPENDENT_CERTIFICATE.json에서 별도로 확인한다.

## 차량별 Bound와 로그 대조

| 차량 | Native 상태 | Solver Global Bound | 반올림 보정 후 LB | Incumbent | Solver Gap | Native 초 | 모델 생성 초 |
|---|---|---:|---:|---:|---:|---:|---:|
| MESS01 | OPTIMAL | -0.11441770278501288 | -0.11441770278501298 | -0.11441770278501288 | 0% | 8.090999842 | 0.236387400 |
| MESS02 | OPTIMAL | -0.11441787420275673 | -0.11441787420275683 | -0.11441787420275673 | 0% | 27.921000004 | 0.215048700 |
| MESS03 | OPTIMAL | -0.11441787420275674 | -0.11441787420275684 | -0.11441787420275674 | 0% | 8.934000015 | 0.226198300 |
| MESS04 | OPTIMAL | -0.11441787420275676 | -0.11441787420275686 | -0.11441787420275676 | 0% | 12.145999908 | 0.209842000 |

각 로그에 Threads=1과 `Optimal solution found (tolerance 0.00e+00)`가 존재한다. 로그의 출력 자릿수로 반올림된 best bound는 전정밀 RESULT의 선택 Solver Bound와 4.33×10^-14 이내로 일치했다. RESULT의 정수 상태 2, 유효 Bound 표시, incumbent와 Bound의 순서도 일치했다. 모델은 모든 원본 차량 Binary 타입을 유지했고, 모델 자체를 연속 경로 문제로 바꾸지 않았다. 이번 결과에는 Box fallback 사용이 없다.

각 차량 LB의 유리수는 `Fraction(selected_solver_bound) + coefficient_rounding_box_correction`과 정확히 일치했다. 이 보정은 원본 유한 Bounds로 목적계수 반올림 차이의 최솟값을 계산한 것이며, 성능에 유리하도록 Bound를 올리는 보정이 아니다. 표시된 LB는 정확한 유리수에서 아래 방향으로 반올림됐다. Solver Bound의 유효성은 Gurobi의 현재 Global B&B Bound와 수치 계약을 전제로 하며, 이번 검토가 Solver의 exact B&B proof trace를 인증한 것은 아니다.

## 정확한 합산과 예산

고정항은 0.5743359823311205이며, WEIGHTS.json의 정확한 유리수 고정항에 네 개의 `certified_LB_exact`를 합산한 결과는 다음 RESULT와 정확히 일치했다.

- Global LB: **0.11666465693783702**.
- 검증 Source18r U4 UB: **0.6760534504652341**.
- 검증 UB 대비 Gap: **82.7432791212658%**.
- 사용자 3% 목표에 필요한 LB: 약 **0.6557718469512771**.

Global LB는 검증 UB 이하이고, Global_LB_exact와 저장된 표시 값의 아래 방향 반올림도 확인했다. 실제 네 Runtime의 합은 RESULT 및 NATIVE_LEDGER의 **57.091999769210815초**와 정확히 일치했다. 모든 차량 Native Runtime은 30초 이하이고 총 Runtime은 120초 이하이다. 1개 Worker를 순차 사용했으며 각 로그가 Threads=1을 확인한다. 실제 optimize는 네 번, Full MILP/Full Root/캠페인 호출은 0회, 가중치 벡터는 한 개, 반복 최적화는 0회이다.

차량 Worker의 최대 Windows 프로세스 peak RSS는 371,912,704bytes = **354.68359375MiB**, 최대 private commit은 1,556,099,072bytes = **1.4492301940917969GiB**이다. 이 두 값은 같은 측정량이 아니다. Gurobi MaxMemUsed는 차량별 0.2395–0.4203GB로 따로 기록됐다. 메모리 부족이나 수치 실패를 나타내는 최종 상태 또는 resource_failure는 없다. Native0 원본 CSR 준비 과정의 메모리·시간을 차량 Worker RAM 또는 Native Runtime으로 혼동하지 않는다.

## Native0 로그 경로 오류의 별도 보존

첫 진입은 Gurobi10013 `Unable to write file`로 Params.LogFile 설정 중 실패했다. 원본 traceback은 model.optimize 이전을 가리키며, ERROR·STOP·Ledger에 Native_Runtime=0, optimize_calls=0, optimize_started=false가 기록됐고 STARTED.json은 없었다. 따라서 수치·메모리 실패 또는 실행한 Solver를 재시도한 상황이 아니었다.

`repair_pre_native_logpath`는 정확히 이 오류와 0 Runtime·0 optimize·MESS01 최초 진입·다른 차량 폴더 부재를 요구한다. 원본 오류 파일과 이전 Ledger·STOP·PILOT_STARTED를 `failed_pre_native_logpath`에 보존했고, 이동 대상의 resolve 결과가 소유 OUT 안에 있는지 확인한다. 이번 독립 검토에서도 보존된 모든 파일 SHA가 PRE_NATIVE_LOGPATH_REPAIR.json의 값과 일치했다. NATIVE0.json, WEIGHTS.json, INDEPENDENT_NATIVE0.json의 SHA도 복구 전 값과 정확히 일치했다.

수정은 같은 소유 출력 파일을 가리키는 LogFile의 ASCII 상대경로 사용이다. 원본 행렬·Bounds·RHS·타입·목적계수·단일 가중치는 바뀌지 않았다. 실행 commit은 PILOT_STARTED.json에 `9e3b091273e5ec1775e88d9e97cc4f8f866624e5`로 동결됐다. 최초 기술 오류의 Native 사용량은 0이므로 최종 네 optimize의 Runtime 합을 줄이거나 예산을 초기화한 일은 없다. 같은 복구 경로는 NUMERIC/MEM_LIMIT 또는 optimize 이후 실패에 사용할 수 없다.

## 채택 판단

실제 물리 운전영역을 네 차량에 유지하는 독립 하한 계산은 수학적으로 유효하고 계산 자원도 이번 제한 안에 들어왔다. 그러나 차량별 최적의 기여가 약 -0.114418씩 합산되어 고정항 0.574336의 대부분을 상쇄했다. 이것은 미완료 Solver Bound가 원인인 결과가 아니다. 현재 단일 가중치에 대해 네 하위 문제 최적화가 모두 끝난 상태에서도 합산 하한이 약하다.

이 증거로 이번 방식의 후속 확대를 채택하지 않는다. 가중치 재조정·추가 벡터·다중 iteration·DW Master·Column Generation·Branch-and-Price·추가 Solver를 실행하지 않는다. 유효하고 유의미한 LB라는 후속 조건을 만족하지 못했으므로 Critical-Grid Reduced MILP도 이번 작업에서 후속 채택하거나 실행하지 않는다. 이 판단은 검증한 단일 파일럿의 결과에 대한 것이며, 측정하지 않은 다른 가중치나 모든 독립 LB 방법이 불가능하다고 확대 해석하지 않는다.

PR147/203의 과거 LB·Column·Dual·Pricing 결과 또는 과거 Full Root LB를 이번 Global LB의 항으로 사용하지 않았다. 원본 Source18r, U4 UB 엔진, PR207 기존 결과와 캠페인 HOLD·예약 비활성 상태를 바꾸는 근거로 이 하한 전용 모델을 사용하지 않는다. 차량별 최적점을 원본 Planning 가능해나 Actual PASS로 승인하지 않는다.
