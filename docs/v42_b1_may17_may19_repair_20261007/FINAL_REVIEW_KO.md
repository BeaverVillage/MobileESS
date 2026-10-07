# May17·May19 원본 불가능성 감사

최종 상태: **MAY17_MAY19_TRUE_INFEASIBILITY_PROVEN**. 두 날짜 모두 **고정된 PR134 A1 원본 수학 모델과 그 R0 시작/배치 권한에서** 불가능함을 정확한 유리수 증명으로 확인했다. 현재 FCFS B0 계획이나 실제 전력망에 가능한 스케줄이 없다는 주장은 아니다. 과학적 모델·입력·허용 시간창·전압 기준을 바꾸지 않았다.

## 날짜별 원인

| 날짜 | 독립적으로 증명된 충돌 | 원본 native 진단 | 정확한 증명 |
|---|---|---|---|
| May17 | R0 시작창과 서비스/클래스 수 요구를 유지하면 선택된 초기 issue 슬롯들의 GPU 용량을 충족할 수 없다. | 첫 목적함수 infeasible, 2.134초. 원본 IIS 150행. | `known_GPU_binding` 26행 + `class_exact_cardinality` 48행 및 원본 경계. 결합식의 최솟값 −1153이 요구 상한 −1254보다 **101** 크다. |
| May19 | day 슬롯1·2, node-phase 축239의 1.05pu 전압 상한을 충족하는 부하 조합을, 원래 known-job 경계와 cohort0의 초기 CC4 누적 서비스 상한으로 만들 수 없다. | 원본도 presolve infeasible, 6.843초. 원본 IIS 52행. | known GPU 19행, `CC4_CDF_U[0,2]`, site partition 2행, `voltage_upper` 2행, 원래 headroom 2행. 정확한 양의 모순 여유 **328616596283819402486007603421651 / 633825300114114700748351602688**, 약518.466. |

증명 여유는 선형 결합의 정규화된 값이며 GPU나 pu의 직접 차이가 아니다. 두 원인은 동일하지 않다. May17 증명에는 grid/CC4 행이 필요하지 않으며, May19 증명에는 초기 CC4와 전압 상한 행이 필요하다.

원래 checker의 행/경계 허용 오차1e−5를 모든 증명 항에 최악 방향으로 적용해도 증명은 유지된다. 허용 잔차의 정확한 보수적 합계는 May17 약0.00116, May19 약4.39182로, 각각 모순 여유101과518.466보다 작다. 작은 원시 잔차를 무시해서 내린 판정이 아니다.

May19의 원시 Farkas ray에는 `anonymous_GPU[AIDC10,1]`과 `[AIDC10,2]`의 무한 상한에 대한 작은 음의 잔차가 있었다. **원시 ray는 exact certificate FAIL로 보존했다.** 이를 tolerance로 무시하지 않고, 원본 행17379·17382의 정확한 양의 유리수 배수를 증명에 추가했다. 모든 계수·RHS·bound term을 독립적으로 처음부터 계산했으며, 무한 경계의 미해결 항0·잘못된 행 부호0·버린 잔차0으로 PASS했다. 추가 optimize나 원래 행/경계 변경은 없었다. 따라서 ray의 수치 잔차와 모델의 numerical false infeasibility는 구별된다.

## B0 무개입 해와 nesting

같은 날짜의 검증된 B0 Planning 권한을 먼저 읽었으며, optimize 전에 nesting/domain 감사를 완료했다. 두 날짜 모두 job ID·GPU·현재 Runtime/Q50 서비스·C0 Q50/Q90·GPU/랙 권한·C1 endpoint 계수는 일치한다. PENDING elapsed `None`과0, 물리 랙에서 재구성되는 호환 사이트는 의미를 정규화해 비교했다. 초기 입력 비교의 raw-field 차이 개수는 곧바로 의미적 오류를 뜻하지 않는다.

그러나 B0는 **현재 FCFS/Q50 nominal-release reference**를 사용하고, PR134 B1은 **원래 R0 배치·시작 및 허용 시간창**을 유지한다. 같은 서비스량이 같은 시작/배치점을 뜻하지 않는다.

- May17 positive-service 2,024개 중 2,024개에서 무개입 조건 또는 도메인이 달라진다. B0 시작/사이트가 B1 전체 도메인에 없는 경우는1,935개다. 예: job8772829는 B0 AIDC01/시작0이지만 B1 R0 AIDC08/시작5, 허용 시작 `[5]`다.
- May19 positive-service 1,023개 중 1,021개에서 무개입 조건 또는 도메인이 달라진다. B0 시작/사이트가 도메인에 없는 경우는991개다. 예: job9017248은 B0 AIDC01/시작0이지만 B1 R0 AIDC10/시작78, 허용 시작78–119다.

따라서 원본 B1과 압축 B1 모두에 쓸 수 있는 **해당 B0의 개입0 integer witness는 만들 수 없었다.** 빈 witness-violation CSV는 NO_WITNESS이며 PASS가 아니다. 다른 해가 가능한지를 가정하지 않고, 이후 원본 모델 자체의 불가능성을 증명했다. B0의 capacity-queue carryout 규칙과 B1의 cohort CDF/work-conservation 규칙, FreshAC와 frozen affine grid 표현도 동일하다고 가정하지 않았다.

## 원본과 압축 비교

세 모델을 날짜별로 **최적화 없이** 먼저 재구성했다. 원본을 PR134 소스와 실패 날짜의 데이터로 다시 만들고, 실패 당시 원본 snapshot과 모든 계수·RHS·sense·LB/UB·변수 유형·네 목적함수를 비교해 차이0을 확인했다. 세 번째 모델은 integrality만 완화했다. 실제 native 변수/행 이름도 별도로 보존했다.

| 날짜/모델 | rows | cols | binary | integer | continuous | nnz |
|---|---:|---:|---:|---:|---:|---:|
| May17 ORIGINAL_FULL | 701,771 | 25,809 | 1,677 | 924 | 23,208 | 12,653,654 |
| May17 CURRENT_COMPRESSED | 144,568 | 23,089 | 1,675 | 924 | 20,490 | 3,241,610 |
| May17 COMPRESSED_RELAXED | 144,568 | 23,089 | 0 | 0 | 23,089 | 3,241,610 |
| May19 ORIGINAL_FULL | 3,731,730 | 2,738,613 | 930,588 | 28,812 | 1,779,213 | 27,743,601 |
| May19 CURRENT_COMPRESSED | 3,028,050 | 2,684,461 | 929,216 | 28,812 | 1,726,433 | 18,244,129 |
| May19 COMPRESSED_RELAXED | 3,028,050 | 2,684,461 | 0 | 0 | 2,684,461 | 18,244,129 |

원래 reducer를 import하지 않는 독립 verifier로 두 날짜의 모든 alias·삭제·경계 강화·중복·signed domination·목적함수 projection을 다시 검사했다. **FULL_LP equivalence 양방향 PASS**다. 발견한 잘못된 reduction/certificate는0이다. 정수성을 완화해도 원본의 정확한 모순이 남으므로 단순 정수 반올림 문제도 아니다.

모든 reduction의 실제 implication은 해당 날짜 행렬에서 다시 계산된다. 상대 lag Runtime/CC4 kernel의 모양은 GLOBAL이며 cohort 질량·날짜축·입력 및 reduction 증명은 DATE_RECOMPUTED다. 다른 날짜의 절대 bound/grid/alias 증명을 잘못 운반한 사례는0이다. 전체 원본 변수 경계를 검사했고, 바뀐 경계/유형/0 제거는 May17과 May19의 forensic CSV에 원본 이름과 증명 SHA로 기록했다. LB>UB는 원본·압축 모두0이다.

## 바인딩·잠금·수치 판정

두 날짜의 R0 source SHA를 검증하고 PR134의 원래 `known_window`로 모든 시간창을 다시 계산했다. 저장된 창과 전부 일치한다. 발견한 **의도된 PR134 권한에 대한** input/model-binding 오류는0이다. 현재 FCFS 기준과의 불일치는 nesting의 차이이며, 이를 고치기 위해 R0 입력을 교체하면 scientific feasible set이 바뀐다.

두 실패 모두 첫 목적함수 `rho`에서 발생했다. 원본 행 이름을 전수 검사해 stale objective-lock 행0, 이전 objective pass0, 이전 날짜 point/clock 유입0을 확인했다. numerical-rescue 조건을 충족하는 valid integer witness는 없었고, 정확한 원본 모순을 확보했으므로 NumericFocus/Aggregate/Presolve 변경이나 parameter sweep을 실행하지 않았다.

## 보존·검증·재실행

production source **b99f2778e47f8bfee22b4eb54f14af8eb9a2e3d1**, PR134 base **52ef855a59144a7c561df44b81dc2ad265babdbd**는 그대로 유지했다. 신규 변경은 독립 진단/증명 코드와 이 보고서 namespace다. 기존 결과·실패 logs·checkpoint·inputs·reduction 증명·설정의 보존 manifest를 해시로 재검사했고 변경 파일0이다.

PR134 accepted raw witness의 원래 모든 행 replay PASS, 저장된 current May01 PASS raw witness의 원래 모든 행 replay PASS다. 기존 **27개 PASS 날짜와 135개 causal 단계 영수증**은 SHA/identity 검증 PASS이며 모두 재사용 가능하다. 기존 FreshAC는2,592/2,592 수렴, 물리위반0으로 보존되었다. 재optimize 또는 FreshAC 재실행은 없었다.

May17·May19 production 재실행은 **하지 않았다**. 고칠 구현 결함을 찾지 못했고, 원본 LP 불가능성을 독립 증명한 상태에서 같은 문제를 다시 풀어 PASS를 만들 수는 없다. 신규 Planning freeze/Actual/FreshAC/physical PASS를 주장하지 않는다. 진단 MIP는 날짜별1회, 작은 certificate LP는 총3회이며 진단/IIS 시간까지 보수적으로 합산한 사용량은 May17 약41.367초, May19 약204.442초로 사전등록 상한 안이다. 원래 production3600초 예산을 연장하지 않았다.

초기 May17 certificate-only IIS relaxation은 IISLB/IISUB가 암묵적 binary 경계를 포함하지 않는다는 점을 누락해 feasible을 반환했다. 그 증거를 보존하고 원래 변수 경계를 유지하는 certificate relaxation으로 정정했다. 이는 새 진단 코드의 정정이며 production 모델의 repair가 아니다.

May10·May12는 이번 작업에서 진단·최적화·예산 변경을 하지 않았다. 메모리 보호·감속·M-stage·B&P·B2/B3 실행을 추가하지 않았다.

## 해시와 검토 위치

날짜별 input/model SHA와 source identity: `MAY17_INPUT_IDENTITY.json`, `MAY19_INPUT_IDENTITY.json`, 날짜별 `MODEL_IDENTITY.json`. 전체 source/artifact 해시: `SHA256_MANIFEST.json`. 독립 판정: 날짜별 `INDEPENDENT_EXACT_CERTIFICATE.json`, `ROOT_CAUSE.json`, `VERIFICATION.json`. 기존27일 보존: `PASS27_REUSE_COMPATIBILITY.json`.

Draft PR: https://github.com/BeaverVillage/MobileESS/pull/163. 진단 전 사전등록 commit은 `ca19ea68`, 원본 진단/세 모델 gate commit은 `1cf56511`, 원래 경계를 유지하는 certificate 정정 commit은 `de9680fd`다. 최종 보고서·검증 패키지 commit은 PR head 및 최종 publication 영수증으로 확인한다.
