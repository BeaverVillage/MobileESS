# PR189 대비 V42.2 B1 구조 원인 분석

상태: **초기 구조 분석 완료, 세부 Family 전수 분류 및 실제 신규 정책 성능은 미완료**. 이 문서는 생산 인증이나 개선 성공 보고서가 아니다.

## 확인된 Restricted Master 행 증가 위치

PR189 May01의 보존된 `STATIC/INITIAL_STATE.pkl.gz`에서 `compact`는 698,213행이고 `grows`는 693,624행이다. 따라서 Restricted Master에 항상 포함되는 local hard 행은 4,589개다. 당시 Phase I 코드는 `range(len(G), compact.rows)`를 초기 포함 집합에 넣는다.

현재 A07의 실제 압축 행렬은 1,026,045행이고 `CLASS_COMPRESSION_BUILD_PROFILE.json`의 원본 local witness는 261,414행이다. 현재 코드도 이 local 행 전체를 Restricted Master에 유지한다. local pricing cache가 있다는 사실만으로 이 행들이 Master에서 제거된 것은 아니다.

| 전처리 전 행 구분 | PR189 May01 | 현재 동일 May01 Case |
|---|---:|---:|
| 항상 포함되는 local hard 행 | 4,589 | 261,414 |
| S0 총행 | 15,129 | 276,433 |
| S1 총행 | 21,091 | 279,966 |
| S1에서 활성화된 global 분류 행 | 16,502 | 18,552 |

S1 총행 증가는 258,875개이고 local hard 행 증가는 256,825개다. **전처리 전 S1 행 증가의 99.208%가 local hard 구간에서 발생했다.** 이는 행 수 증가 위치를 확인한 결과다. 개별 물리 Family의 Factor fill-in 기여도를 증명한 결과는 아니다.

## Presolve와 Factorization의 실제 관측

| S1 항목 | PR189 | 현재 Attempt004 |
|---|---:|---:|
| Presolved rows | 6,029 | 168,195 |
| Presolved columns | 57,004 | 118,692 |
| Factor NZ | 400,000 | 65,730,000 |
| Factor Ops | 4.8e7 | 8.631e10 |
| Matrix coefficient range | 4e-10 ~ 6 | 1e-13 ~ 3e5 |

원본 행과 Presolve 후 행의 정확한 대응은 이 로그만으로 복원할 수 없다. 따라서 local hard 행 증가가 실제 Factor NZ 증가의 몇 %를 설명하는지는 아직 미확인이다. dense/global coupling과 local 그래프 구조가 만드는 fill-in을 분리해야 한다.

Job 수는 1,499→1,555, Class 수는 117→229다. Class 수 증가율만으로 local hard 행의 약 57배 증가를 설명할 수 없다. D0 잔여 서비스와 E1/FLEX30/checkpoint의 local 표현, 기존 kernel과 현재 명시적 flow/state 표현의 차이를 세부 Family별로 조사해야 한다. 이 목록은 조사 대상이며 아직 개별 기여가 입증된 것은 아니다.

## Solver 정책 실험과 구분

Attempt004의 cold Barrier는 S0 basis를 사용하지 않았고 S1에서 numerical trouble 후 TIME_LIMIT를 반환했다. 실제 S0 basis를 원본 S1에 확장한 A07 Native0는 최대 행 잔차 8.640199666842818e-12, 정확한 VBasis/CBasis readback, Method=0/LPWarmStart=1/Presolve=0을 확인했다. Native0는 Optimize를 호출하지 않았으므로 실제 성능이나 Phi=0 완료를 뜻하지 않는다.

## 남은 필수 분석

- 요청된 UID-local, start/service, GPU/rack, backlog, D0 residual, CC4, E1/QoS, checkpoint/migration, WAN, PCC, voltage, line, transformer, linking, artificial의 row/column/NNZ/계수/자유변수/부호 전수 분석.
- 원본 이름 또는 descriptor에 근거한 의미 분류와 support 기반 추론을 구분하고, 분류 불가 및 중복 의미를 명시.
- 실제 동일 S1 정책 실측과 Presolve/Factor 기여 진단을 분리.
- 필요 시 local feasible polytope를 Pricing에 유지하는 Master 축소를 검토하되, 투영·복원·목적·완전 pricing·weak duality 증명 없이 행을 삭제하지 않음.
- 기존 4,800 tail projection은 완료된 과거 개선으로 유지하며 새 개선으로 중복 계상하지 않음.

근거: `PR189_B1_MAY01_COMPARISON.json`, PR189 runtime `STATIC/INITIAL_STATE.pkl.gz`, 현재 `B1_NATIVE0_07/B1/A1/DW/CLASS_COMPRESSION_BUILD_PROFILE.json`, `B1_NATIVE0_07/ACTUAL_S1_BASIS_NATIVE0/RESULT.json`, Attempt004 S1 Native 원본 로그.

## 229 Class local support 전수 조사 추가 결과

`B1_LOCAL_BLOCK_SUPPORT_CENSUS.json`은 A07의 SHA-bound 전체 229개 실제 local block을 읽어 총 261,414행과 174,685개 block-local 열을 전수 검사했다. Original descriptor의 변수 Family 식별자를 사용했으며, 아래 공학적 그룹명은 변수 support에 따른 분류다. 혼합 행은 WAN link → WAN dynamics → migration → local state → start/service 순서로 한 번만 분류했다. 원본 native 행 이름에 의한 유일한 의미 분류나 Presolve lineage를 주장하지 않는다.

| Local support 그룹 | PR189 초기 Hybrid 행 | 현재 229 Class 행 | 현재 NNZ |
|---|---:|---:|---:|
| WAN link bytes/linking | 0 | 85,495 | 215,824 |
| WAN transfer dynamics/linking | 0 | 116,533 | 348,154 |
| Checkpoint/migration selection | 0 | 39,978 | 262,987 |
| Local service state | 4,505 | 19,312 | 100,363 |
| Job start/finish/service | 28 | 96 | 3,585 |
| Empty/unannotated local | 56 | 0 | 0 |

현재 local hard 행의 202,028개(약 77.3%)가 WAN 관련 변수 support를 포함하는 그룹에 속한다. PR189 초기 Hybrid의 local support에는 이 그룹이 없었다. 이것은 초기 Hybrid 표현의 차이를 보여주며, PR189가 전체 물리 migration domain을 삭제했다는 뜻은 아니다. 당시의 complete-domain pricing/activation과 현재의 complete-kernel 상시 포함을 구분해야 한다.

현재 초기 229-Class 경로는 `table_v_compression_adapter.prepare`에서 block diagonal local 행렬을 직접 포함한다. `phase.run`은 local 행을 상시 포함한다. 기존 `assembly.build`는 같은 Hybrid 결합 방식을 제공하지만, 현재 full-class 경로는 `complete_kernel_rebuilder`로 rebuild를 대체하므로 두 경로를 혼동하면 안 된다. 이 경로가 실제 성능에 미치는 인과 효과는 동일 Case의 동치 축소 파일럿으로 검증해야 한다.

ATTEMPT005와 생산 코드는 변경하지 않는다. 실행 정산 후 exact fixed-variable/affine elimination 및 exact redundancy부터 검증한다. Local polytope DW는 필요 시 별도 파일럿으로 검증하며, 유한 column pool을 full-domain pricing 또는 Global LB 증거로 승격하지 않는다.

## Local Hard 1차 정확 축소 검증

`LOCAL_REDUCTION_NATIVE0_01/RESULT.json`: 실제 229 Class, 1,555 UID를 대표하는 전체 continuous local polytope의 영 변수 함의·정확한 x=y 별칭·정확한 비례 중복 행을 독립 Fraction 검증기로 재검증했다. 모든 기존 local 행, bounds, P1 목적, global coupling 및 UID primitive expression을 검사했고 Gurobi에서 축소 행렬·변수형·목적을 다시 읽었다. Optimize와 Presolve는 차단했다.

| 항목 | Before | After |
|---|---:|---:|
| Local Hard rows | 261,414 | 210,067 |
| Local columns | 174,685 | 134,630 |
| Local NNZ | 930,913 | 789,632 |

Binary64에서 정확하게 표현할 수 없는 합은 반올림하지 않고 거부하도록 구현했다. 실제 229개 블록은 모두 정확한 readback을 통과했다. 회귀 1,305개 PASS이며 기존 682개 기준 및 과거 원장 byte가 보존됐다.

**현재 범위는 완전한 local polytope들의 동치 축소다. 전체 Hybrid Master 연결, global row/column mapping, pricing 인증 경로, 실제 Native 성능은 아직 미검증이다. 생산 채택이나 B1 PASS를 뜻하지 않는다.**
