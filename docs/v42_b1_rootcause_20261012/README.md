# B1 원인 감사 및 중지 상태의 복구안

기준은 PR212 `4a969c59823c67dc5f52474491b24a9d55107e3d`, 역사적 비교 기준은 PR189 `625bbcb8b9a54a00c1660c26d96f7737c2f75457`이다. 이 PR은 원인 감사, 별도 정확한 Pricing 인증 도구, 엄격한 날짜별 운영 분류 및 재개 방지 장치를 제출한다. **B1을 재개하거나 May01/May03을 재최적화하지 않았다.** 과거 FAIL은 유지하며, 현재의 두 FAIL을 해결 완료/PASS로 표시하지 않는다.

## 현재 실행 영수증과 권한

원본 결과 SHA와 Native 원장을 재확인한 상태는 다음과 같다.

| 날짜 | 원본 상태 | 측정 Native 초 | Native 호출 | FULL | Global Gap | Actual |
|---|---|---:|---:|---|---|---|
| May01 | FAIL: PHASE_I_RAW_REPLAY_FAIL | 2.0370001792907715 | 1 | 미인증 | 미인증 | 미실행 |
| May02 | PASS | 1647.2899985313416 | 305 | 인증 | 0.002318863287110073% | Fresh AC96 PASS |
| May03 | FAIL: P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT | 1337.0120010375977 | 270 | 미인증 | 미인증 | 미실행 |
| May04–31 | 미실행 | 없음 | 0 | 없음 | 없음 | 없음 |

기존 manifest의 `retry_max_attempts=1`, `retry_new_attempt_starts_zero=false`와 May01 continuation의 `Native_retry_authorized=false`를 확인했다. 기존 두 날짜의 새 Native 시도 권한을 발견하지 못했다. 이후 사용자가 B2 작업을 위해 B1 실행 중지를 명시했다. B1 프로세스 0개, V3/V4 B1 Windows 작업 Disabled, 이 대화 예약 PAUSED를 확인하고 STOP_REQUEST와 [중지 영수증](USER_B1_STOP_RECEIPT.json)을 남겼다. root05 생성·Worker 배정·V5 작업 등록은 수행하지 않았다.

## 과거 성공 모델과 현재 모델

[비교 JSON](HISTORICAL_MODEL_COMPARISON.json)은 실제 입력 영수증의 SHA를 확인하고 저장된 초기 Matrix, 원래 Bounds/Types, 완전 Class Oracle, Solver Parameter, Native Log와 Pricing 영수증을 비교한다. 대형 checkpoint 전체를 로드하지 않고 첫 Matrix 객체에서 읽기를 종료한다. 과거 결과를 현재 결과로 복사하지 않는다.

| 날짜 | 과거/현재 Class roster Job 수 | Class 수 | 초기 모델 행: 과거 → 현재 | 초기 모델 열 |
|---|---:|---:|---:|---:|
| May01 | 1499 / 1499 | 117 / 117 | 698213 → 838853 | 68026 |
| May02 | 1386 / 1386 | 138 / 138 | 698341 → 838981 | 60958 |
| May03 | 1324 / 1324 | 133 / 133 | 706452 → 847092 | 92631 |

모든 날짜에서 140640행이 증가했다. Builder의 `jobs_complete`와 Class roster cardinality는 다른 저장된 census이므로 같은 수로 대체하지 않는다. 각 census의 과거/현재 값은 JSON에 그대로 보존했다.

Native 입력에서 달라진 최상위 항목은 `electrical_certificate`, `grid_outputs` 두 가지다. `known_population`, C0_Q50/Q90, Runtime provider/binding, CC4 reserve/survival kernel, traffic forecast SHA, capacities, racks, WAN, reference 및 나머지 입력은 일치한다. `WINDOWS.json`과 실제 Native 입력 영수증도 확인했다.

Class ID 문자열은 전부 바뀌었다. 이를 Domain 변경으로 해석하지 않고 원래 Job member 집합으로 대응시켰다. 대응시킨 **117/138/133개 전체 Class의 완전 Graph SHA와 완전 Local Snapshot SHA가 각각 일치**한다. Local Snapshot hash는 Matrix/RHS/Bounds/Senses/Types를 포함한다. 원래 Global 변수 이름과 인덱스도 일치한다. 초기 열 수와 Lower/Types 배열은 일치하지만 Upper 배열의 위치별 비교는 다르다. Class ID 정렬에 따른 열 배치 변경을 고려하지 않은 위치별 차이는 수학적 Bounds 변경의 증거로 쓰지 않는다. 초기 전체 행 비교 역시 행 순열·Class 열 재배치를 완전히 정규화한 비교가 아니며, 독립적인 전기계통 계수와 Local Snapshot 비교를 구분해서 제시한다.

전기계통에는 실제 변경이 있다. 기존 sensitivity의 branch phase 축 383개가 새 SVR11에서 416개가 됐고, 기존 transformer phase current 120행에 새 SVR 33행이 추가된다. 제어 축은 동일한 60개다. 기존 voltage sensitivity node 축 386개와 새 serialized 838행은 동일한 축이 아니다. 새 코드가 419개 node의 LDC endpoint 축을 두 번 저장하므로 이를 838개 물리 node로 해석하지 않는다. RegControl, SVR11 및 새 설비에서 재생성한 voltage/current/P/Q 계수를 과거 계수로 대체하지 않는다. 원래 전압 0.95–1.05, current/transformer/SVR 정격 및 고정 capacitor 권위는 유지한다.

`phase.py`와 `pricing.py`의 두 Git 기준 bytes SHA는 동일하다. 전체 과학 Python 집합은 PR189 `e835cac171b7aaf2ca9a6bcb696740aa82e4e059b21e6a5631801476501e761e`(1064파일), PR212 `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8`(1264파일)로 다르다. A-stage anytime 인수·SVR11 coefficient binding 등의 변경과 Phase-I/Pricing 알고리즘 자체를 구분한다.

역사적 Native freeze의 실제 Git HEAD는 May01 `1423be901cea5d53e60f0e5f48501a9280227b4c`, May02/03 `2791ca66702e1ff1e952e4590bf10ae53a902c39`다. 이를 PR189 제출 commit과 동일한 실행 commit으로 표기하지 않는다. 실제 source freeze의 Phase/Pricing SHA는 두 제출 기준과 일치한다. 과거 May01/03은 P1 S0에서 Pricing을 닫았고 May02는 S1에서 닫았다. 현재 May03은 S1에서도 닫지 못했다. Serialized coefficient 변경이 실제 실행 입력의 차이임은 입증했지만, 특정 SVR 한 대나 Barrier 단계만의 인과 영향은 재실행 실험 없이 단정하지 않는다.

## May01: 큰 GPU 배분량의 상쇄와 원래 좌표의 실제 위반

[수치 증거](MAY01_NUMERIC_EXHIBIT.json)에 17개 항, Matrix/attribute/raw SHA, 원래 parameter와 iteration 수를 보존했다. **저장된 restricted Phase-I 행 6526**의 원본 전체 초기 모델 대응 행은 **16078**이다. 두 인덱스를 혼동하지 않는다.

원래 등식은 slot 11의 CC4 GPU 배분 합계다. 세 CC4 allocation 변수 `CC4_x[0,11]`, `[1,11]`, `[2,11]`의 계수는 -4이고, 12개 AIDC의 anonymous GPU 배분 변수 계수는 +1이다. Phase-I에 추가된 두 artificial 계수는 +1/-1이며 반환값은 0이다. RHS는 0이다. 열 12000은 AIDC01의 slot 11 P-control 식에 들어가는 GPU 항으로 확인했다.

두 개의 nonzero 항은 다음과 같다.

```
-4 * 11936181269.420158 = -47744725077.68063
     47744725077.68064 =  47744725077.68064
exact residual = 1/131072 = 7.62939453125e-6 > 1e-6
```

정확한 binary64-rational 재검증에서도 실제 위반이다. 합산 순서를 바꾸거나 더 정밀한 덧셈만으로 PASS가 되지 않는다. Compiler read-back PASS, Matrix 입력 변환 일치, dual sign replay PASS와 primal FAIL을 구분한다. 제한된 초기 Phase-I에서 unbounded GPU 변수의 반환량이 매우 커진 것이 상쇄 오차의 직접 수치 조건이다. 과거 May01 S0의 최대 |X|는 약 106.50, 현재는 약 4.774e10이다. 다른 날짜도 초기 Phase-I에서 큰 값을 반환하므로 큰 값 자체를 infeasibility 증명으로 쓰지 않는다.

실제 parameter는 Threads=1, Method=2, NodeMethod=1, MIPFocus=3, Seed=20260929, FeasibilityTol/OptimalityTol=1e-6, IntFeasTol=1e-5였다. Barrier 22회, simplex 34130회가 기록됐지만 crossover 내부 궤적은 로그에 없다. 최종 postsolve raw point에서 위반을 측정했으며, Barrier/Crossover/Postsolve 각각의 원인 비율을 확정하지 않았다.

개선 방향은 원래 GPU capacity 행을 초기 restricted Phase-I에 우선 보존하는 것과, **양의 dyadic Row/Column scaling**을 별도 입력 변환으로 검증하는 것이다. `x=D y`, `A'=R A D`, `b'=R b`, `c'=D c`, 원래 dual `Pi=R Pi'`, 원래 RC `RC=D^-1 RC'`를 명시해야 한다. Integer/Binary 변수의 column scaling은 격자까지 보존하지 않으면 금지한다. 새 후보는 되돌린 원래 좌표에서 모든 행·Bounds·원래 정수 패턴·목적함수와 원래 FULL physical validator를 다시 통과해야 한다.

행을 2^-35로만 스케일하면 작은 native 잔차가 되어도 원래 잔차 1/131072는 그대로다. 저장된 점은 이에 대한 반례로 보존했다. 따라서 scaling 자체를 해결 성공으로 표시하지 않는다. Solver 안정화 선택은 [Gurobi 수치 지침](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/numeric_parameters.html)과 [원래 좌표의 절대 허용오차 지침](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/tolerances_scaling.html)을 참고하되, parameter 변경이나 재실행은 수행하지 않았다. **May01은 원본 FAIL이며 새 후보·FULL 검증 개선 성공은 아직 없다.**

## May03: 인증 하한 손실과 유효한 추가 지원 후보

[정확한 Class별 수치](MAY03_CERTIFICATE_STRENGTHENING.json)에 모든 값의 rational 문자열을 저장했다. 아래 표는 읽기 위한 근사값이며 인증 권위는 JSON의 정확한 값이다.

| Class prefix | Active raw 값 | Active LB | Full 인증 LB | 실제 Full 후보 값 | 원본 oracle_point_price |
|---|---:|---:|---:|---:|---:|
| 0947fed158a3 | 0 | 0 | -7.256952782975129e-7 | 0 | 0 |
| 365fba0e68db | 0 | 0 | -7.256952782975129e-7 | 0 | 0 |
| 40d063a5e1b6 | 0 | 0 | -6.773037809523618e-7 | 4.049382815803366e-11 | 4.049382815803366e-11 |
| c5e7a1d47c6d | 1.3216268669389934e-8 | -7.401110454858363e-7 | 0 | 0 | 7.401110454858363e-7 |
| f602a64977f1 | 2.5579874843980516e-8 | -1.48363274095087e-6 | 0 | 0 | 1.48363274095087e-6 |

원래 `minimum_rc_lower_bound = Full LB - Active raw point price`, `oracle_point_price = Full candidate price - Active local LB`다. 동일한 기준을 빼는 두 값이 아니므로 혼동하면 안 된다. 하한이 음수이고 source 기준의 음의 지원이 없다는 사실은 지원의 수학적 비존재 증명이 아니다.

5개 모두 `corrected_certificate.exact_box_roundoff_correction=0`이다. 첫 3개는 근사 local dual의 exact residual을 유한 box에서 각각 최소화한 결과 인증 하한이 음수가 된 경우다. 이 Class들의 원래 Pricing 목적계수와 variable Lower Bound는 음수가 아니므로, **별도 zero-dual 인증의 정확한 Full-domain LB는 0**이다. 이 PR의 `b1_exact_pricing.py`는 원래 binary64 coupling을 rational로 재구성하고 direct true-objective bound 및 별도 zero-dual bound 중 가장 강한 유효 하한을 선택한다. 저장된 Pi/X를 변경하지 않는다. 첫 3개는 원래 Active raw 값 기준과 1e-8 epsilon 그대로 인증된다.

나머지 2개는 Full LB가 이미 0이지만 Active raw upper가 1e-8보다 조금 크다. 별도 zero-dual만으로 이 차이는 닫히지 않는다. 저장된 Full Oracle 후보는 **AIDC05, start slot 3의 STAY count 31/60**이며, 각각 모든 Full Local Matrix 행과 Bounds의 정확한 rational primal 검증을 통과하고 목적값은 0이다. 해당 STAY는 초기 Active 지원에는 없다. 이는 유효한 추가 지원 후보의 증거이며, `Full candidate - saved Active upper`는 음수지만 `Full candidate - certified Active lower`는 양수다. **Active의 실제 최솟값보다 개선한다는 증명으로 승격하지 않는다.**

후속 방법은 해당 유효 STAY 지원을 원래 prior-point inclusion 증명과 함께 별도로 확장한 뒤, 원래 P1을 새 권한·Native 예산 안에서 다시 검증하는 것이다. Active 내 정확한 zero-cost witness를 찾을 때 사용할 모든 행·Bounds rational 검사도 제공한다. 현재 정지 지시에 따라 재최적화·추가 지원의 production activation·새 전체 후보 생성은 수행하지 않았다. **3/5의 저장된 인증 구간은 강화됐고, 2/5는 유효 후보와 검증 증거까지 준비했다. May03 전체 Pricing closure/FULL/PASS는 인증하지 않는다.**

## 캠페인 전체 중단과 날짜별 실패의 분리

[엄격한 dispatch 감사](MAY03_DISPATCH_AUDIT.json)는 Source18r SHA, request/manifest/input/hardware 권위, Native=0 preparation, 실제 P1 compiled model와 원래 raw primal/dual, 모든 Full Oracle의 optimal 종료 및 raw replay, 전체 133개 class coverage와 rational verifier를 재검증했다. Native 원장 270회와 1337.0120010375977초는 그대로다. 이 검증은 날짜별 `DATE_LOCAL_PRICING_CERTIFICATION_INCOMPLETE` 운영 분류의 근거이며, scientific classification `IMPLEMENTATION_FAILURE`나 결과 FAIL을 수정하지 않는다.

V5는 정확히 이 오류 문자열과 독립 감사가 성공할 때만 FAIL-continue를 허용한다. Source/Input/공통 무결성 오류, 알 수 없는 IMPLEMENTATION_FAILURE, 실패한 감사는 계속 차단한다. 과거 3일의 원본 결과와 Native 원장 영수증을 봉인하고 첫 새 배정이 May04가 되도록 원래 세 날짜의 request를 금지했다. Threads=1, Worker=1, 5400초, Gap 0.005, 원래 resource/Heavy peer guard와 science는 유지한다.

현재 릴리스는 **검토용**이다. V5 `prepare`는 사용자 중지 상태에서 새 캠페인을 만들지 않고, run/safeguard/task registration은 새 명시적 사용자 재개 권한과 봉인된 continuation 없이는 차단된다. 현재 권한 영수증이나 새 root를 만들지 않았다. 31일 terminal 최종 보고와 May04–31 실행 성공을 주장하지 않는다.

## 검증과 남은 작업

- 21개 회귀 테스트 PASS: 음수 실제 비용을 0으로 인증하지 않음, sign/unbounded guard, 모든 행·Bounds witness 검사, unknown/global 실패 차단, immutable 결과 보존, 과거 날짜 재시도 금지, 사용자 재개 권한 없는 실행 차단.
- 과거·현재 실제 세 날짜의 입력 및 완전 Local Oracle 모델 비교 완료; protected scientific Python bytes 변경 없음.
- 전체 133개 May03 인증 독립 감사 PASS; 추가 Native 호출 0.
- May03 첫 3개 하한 강화와 나머지 2개 Full STAY의 exact local primal 증거 확보; production integration 미실행.
- May01 scaling/초기 GPU capacity 행 보존의 Native 효과와 새 후보 FULL 통과는 아직 검증하지 못했다.
- 사용자 재개 및 Retry Authority가 확인되기 전에는 B1 Native를 실행하지 않는다. PR207/211, Source18r/U4, B2/B3 결과·정책·프로세스는 수정하지 않았다.
