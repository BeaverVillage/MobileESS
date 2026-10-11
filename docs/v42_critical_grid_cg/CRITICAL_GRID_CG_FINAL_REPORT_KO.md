# V42 Critical-Grid Constraint Generation Global LB 최종 보고

작성 기준 시각: 2026-10-12T02:07:06+09:00 (Asia/Seoul). 대상: IEEE123 / B2 / 2025-05-01.

종료 판정은 **CG_LB_MATERIAL_IMPROVEMENT**이다. 독립 인증을 통과한 누적 Global LB는 **0.4649848700**이며, 검증된 원본 FULL U4 UB **0.6760534504652341** 대비 Global Gap은 **31.22069421%**다. Joint16 기준 개선량은 **0.0395070868**이다. 3% 목표는 **미달**이다.

새 Native 요청은 2회 / 최대 2회, 요청 한도 합은 360초 / 최대 360초다. 실제 Native Runtime 합은 360.083000초이고 Optimize Wall 합은 361.435716초다. 원본 FULL MILP·별도 FULL LP·Column Generation·DW·Benders·가중치 최적화·공식 캠페인·추가 날짜 실행은 모두 0회다. 기존 K16을 재최적화하거나 시간만 연장하지 않았다.

## 1. 기준 및 재사용 증거

| 기준 | 정확한 commit / 수치 | 역할 |
| --- | --- | --- |
| Source18r / PR207 | 497609b46faa14ea7e32a9483a333ab32fd264ef | FULL 저장 행렬·Forecast·AIDC·물리 모델의 Authority |
| 차량별 LB / PR209 | 9383a99f1bdcabbd49c79b3ad9f9ee36d523868a | 원본 helper 소거 및 이전 LB 증거 |
| Joint16 / PR210 부모 | 6a8fd44f59f1f461c60d2d14f5f5be605e4ed640 | 새 브랜치의 정확한 부모, 360초 한도 저장 결과 재사용 |
| 원본 검증 U4 UB | 0.6760534504652341 | Global Gap에 사용하는 유일한 UB |
| Joint16 Global LB | 0.42547778318693985 | 검증된 이전 하한 계승 |
| Joint16 최종 정수해 목적값 | 0.4258955562455018 | 첫 Separation의 입력; FULL UB로 사용하지 않음 |
| 3% 목표 LB | 0.6557718469512771 | 성능 목표이며 달성 가정 없음 |

FULL case SHA: `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`. FULL CSR SHA: `0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec`. FULL domain SHA: `9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e`.

PR210 `native360/JOINT_INCUMBENT.npz`, `JOINT_A.npz`, `JOINT_DATA.npz`, `JOINT_AXES.npz`, `INDEPENDENT_CERTIFICATE.json`, `RESULT.json` 및 `K16_EXACT_ROWS.json`을 재사용했다. 소스·결과 파일의 실제 SHA는 각 단계의 `SEPARATION.json`, `NATIVE0.json`, `INDEPENDENT_NATIVE0.json`과 최종 인증서에 보존했다. 원본 CSR/domain SHA와 PR209 저장 파일 SHA도 다시 대조했다.

추가 재사용 감사 `PR210_REUSE_AUDIT.json`: PASS, PR210에서 상속한 실제 파일 74개의 SHA를 저장 index와 비교했다. 기존 tracked 파일 변경 목록: `[]`. 상속 index SHA: `67bb2e4a5f4f7d25a63f769414c140be5a6d8f4d4ab299470c94170d823dd064`.

## 2. 원본 FULL 가능영역 포함관계

원본 FULL 가능영역을 F라 하고, PR210에서 검증된 Compact 사영을 T라 한다. T는 원본 96슬롯 경로를 변경하지 않고 Node-Activity 이진변수와 연속 route_flow, 저장 Static Presolve 역매핑 및 Exact C3A 증명을 사용한다. 네 차량의 물리 행, Bounds, 열, 타입, 목적함수와 기존 K16을 bitwise 보존했다. 초기/종단 SOC·에너지 보존·Mode·Pch/Pdis/Q·PCS16·이동 시간/에너지·접속·복귀 경로 가능성을 그대로 유지하며, 종단은 원래 slot96 도착 조건이다. PCS16은 상속한 Exact C3A의 검증된 중복/함의 제거 후 동등한 영역을 유지한다. 새 출발지 복귀 조건이나 경로 제거·고정·Binary 추가는 없다.

원본 행 aᵀz ≶ r의 Sense를 실제 저장 값에 따라 ≤로 통일한다. 원본 injection/response/correction 정의 등식을 저장 binary64의 정확한 Fraction으로 소거하고, Compact 역매핑을 대입하면 cᵀy ≤ R을 얻는다. 이 식은 원본 FULL에서 실제 존재하는 행의 정확한 대입 결과이므로 모든 z∈F에 대해 cᵀT(z)≤R이다. 고정 AIDC·Forecast·Response Correction과 원본 RHS의 기여는 소거 상수에 포함되며 새 AC/OpenDSS 계수나 Actual 입력을 사용하지 않았다.

Native 계수 c̃ⱼ는 Fraction cⱼ의 binary64 전환값이다. 유한한 원본 유지 Bounds [lⱼ,uⱼ]에서 E=Σⱼmax((c̃ⱼ−cⱼ)lⱼ,(c̃ⱼ−cⱼ)uⱼ)를 정확히 계산하고, Native RHS R̃=ceil_binary64(R+E)로 정한다. 그러면 c̃ᵀy≤cᵀy+E≤R+E≤R̃이다. 계수를 임의 삭제하지 않고, underflow·overflow·무한 반올림 Box를 거부한다. 이 보수적 행은 원본 가능해를 배제하지 않는다.

따라서 T(F)⊆J̃_K가 모든 단계에서 유지되고 min(J̃_K)≤min(F)다. 이전 Native 행 자체를 그대로 보존하고 검증된 행만 추가하므로 J̃_next⊆J̃_current이며, 수학적 최소 목적값은 감소하지 않는다. TIME_LIMIT의 개별 ObjBound가 항상 증가한다고 가정하지 않는다. 각 단계에서 새 모델 포함관계·Source·Bounds·목적함수 무결성이 PASS한 경우에만 LB_published=max(LB_previous, LB_new_certified)로 계승한다.

## 3. Separation 및 원본 전체 계통 위반 분석

저장 Joint 정수해를 C2 축과 원본 역매핑으로 복원하고 원본 FULL의 109,440개 injection/response helper 정의를 재구성했다. 경로·Mode·Node 정수 패턴을 반올림하거나 변경하지 않는다. Sparse Matrix 연산과 전파된 부동소수점 오차 envelope는 탐색에만 사용한다. 채택할 행은 독립 Fraction 소거·원본 Row SHA·Sense·RHS·좌표·Phase 검사와 정확한 양의 위반량을 모두 통과해야 한다. 외향 보정 후의 Native 행도 이전 정수해를 실제로 배제하는지 Fraction으로 확인한다.

thermal은 부하율 pu, transformer facet은 kVA, NormalAmps는 전류 부하율 pu, voltage는 원본 저장 식의 전압 제곱 pu² 단위다. thermal/NormalAmps는 정격 1, transformer는 원본 kVA×cos(π/16), voltage는 행 기준 1 pu²로 정규화한다. 서로 다른 단위를 직접 순위 비교하지 않는다. 고정 quota는 thermal 10, transformer 2, voltage upper 2, lower 2다. 각 Family 내부 정규화 순위를 사용하고 같은 asset/phase/slot의 Facet 대표성을 먼저 확보한다. 정확히 동일한 소거 계수/RHS 행만 중복 제거하고, 부족 quota는 정해진 Family 순서에서 보충한다. 수학적으로 다른 유효 행을 다양성 기준만으로 영구 제외하지 않는다.

### 1차 Separation

검사한 원본 Security 행은 814,560개, 탐색 후보 6,737개, 채택 16개다. Wall 10.961950초. 원본 정수 패턴 최대 잔차 0.000000000000, helper 숫자 replay 최대 잔차 2.273737e-13.

| Family | 원본 행 | 누락 행 | 확인 탐색 후보 | 최대 원시 위반 | 0 부근/미확정 |
| --- | --- | --- | --- | --- | --- |
| line_thermal_face | 403968 | 403952 | 6237 | 0.4884263192 | 0 |
| transformer_kVA | 235008 | 235008 | 80 | 147.1516486002 | 0 |
| voltage_upper | 80448 | 80448 | 262 | 1.0306480985 | 0 |
| voltage_lower | 80448 | 80448 | 158 | 1.2453259934 | 0 |
| NormalAmps | 14688 | 14688 | 0 | -0.0695531822 | 0 |

전부 Sparse 검사했지만 전 행에 대한 Fraction 최적성 증명은 하지 않았다. `uncertainty`와 자동 채택 실패 사유는 별도 보존한다. 위반을 못 찾았다는 사실만으로 FULL 최적성을 주장하지 않는다.

### 2차 Separation

검사한 원본 Security 행은 814,560개, 탐색 후보 4,048개, 채택 16개다. Wall 10.692798초. 원본 정수 패턴 최대 잔차 0.000000000000, helper 숫자 replay 최대 잔차 2.273737e-13.

| Family | 원본 행 | 누락 행 | 확인 탐색 후보 | 최대 원시 위반 | 0 부근/미확정 |
| --- | --- | --- | --- | --- | --- |
| line_thermal_face | 403968 | 403942 | 3662 | 0.3583310451 | 0 |
| transformer_kVA | 235008 | 235006 | 24 | 16.3664437270 | 0 |
| voltage_upper | 80448 | 80446 | 222 | 1.4659857600 | 0 |
| voltage_lower | 80448 | 80446 | 140 | 0.3527015407 | 2 |
| NormalAmps | 14688 | 14688 | 0 | -0.2396198238 | 0 |

전부 Sparse 검사했지만 전 행에 대한 Fraction 최적성 증명은 하지 않았다. `uncertainty`와 자동 채택 실패 사유는 별도 보존한다. 위반을 못 찾았다는 사실만으로 FULL 최적성을 주장하지 않는다.

## 4. 실제 추가 행과 위반량

Row ID는 저장 FULL의 0 기반 CSR 행 번호다. 원시·정규화 위반량은 해당 단계 입력 정수해의 값이며, 행별 원본 계수/RHS SHA, 정확한 Fraction 위반량, helper 정의 SHA, 선정·제외 사유는 `CUTS_EXACT.json`과 `CANDIDATES.json`에 보존했다.

| 단계 | FULL Row ID / 이름 | Asset / Phase | Slot / Facet | 원시 위반 | 정규화 위반 | 원시 단위 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 498265 / line_thermal_face[30,26,1] | line.l10 / A | 30 / 1 | 0.4884263192 | 0.4884263192 | thermal_loading_pu |
| 1 | 498151 / line_thermal_face[30,20,1] | line.l7 / A | 30 / 1 | 0.4569692261 | 0.4569692261 | thermal_loading_pu |
| 1 | 498056 / line_thermal_face[30,15,1] | line.l3 / A | 30 / 1 | 0.4519237055 | 0.4519237055 | thermal_loading_pu |
| 1 | 497831 / line_thermal_face[30,3,1] | line.sw1 / A | 30 / 1 | 0.4512048672 | 0.4512048672 | thermal_loading_pu |
| 1 | 498380 / line_thermal_face[30,32,2] | line.l13 / A | 30 / 2 | 0.4425744575 | 0.4425744575 | thermal_loading_pu |
| 1 | 497888 / line_thermal_face[30,6,1] | line.l115 / A | 30 / 1 | 0.4409810802 | 0.4409810802 | thermal_loading_pu |
| 1 | 498341 / line_thermal_face[30,30,1] | line.l10 / C | 30 / 1 | 0.3754576101 | 0.3754576101 | thermal_loading_pu |
| 1 | 498398 / line_thermal_face[30,33,1] | line.sw2 / A | 30 / 1 | 0.3593468534 | 0.3593468534 | thermal_loading_pu |
| 1 | 508488 / line_thermal_face[31,64,1] | line.l52 / A | 31 / 1 | 0.3504807949 | 0.3504807949 | thermal_loading_pu |
| 1 | 1030545 / line_thermal_face[86,26,1] | line.l10 / A | 86 / 1 | 0.3400320603 | 0.3400320603 | thermal_loading_pu |
| 1 | 513075 / transformer_kVA[31,307,10] | transformer.mess_idc02_tx / A | 31 / 10 | 147.1516486002 | 0.6001380793 | kVA |
| 1 | 513394 / transformer_kVA[31,324,10] | transformer.mess_idc02_tx / C | 31 / 10 | 147.1252356604 | 0.6000303577 | kVA |
| 1 | 981326 / voltage_upper[81,238] | 83 / 1 | 81 / None | 1.0306480985 | 1.0306480985 | voltage_squared_pu |
| 1 | 981616 / voltage_upper[81,383] | mess_sta12_pcc / 1 | 81 / None | 1.0306479758 | 1.0306479758 | voltage_squared_pu |
| 1 | 506075 / voltage_lower[31,238] | 83 / 1 | 31 / None | 1.2453259934 | 1.2453259934 | voltage_squared_pu |
| 1 | 506365 / voltage_lower[31,383] | mess_sta12_pcc / 1 | 31 / None | 1.2453259737 | 1.2453259737 | voltage_squared_pu |
| 2 | 1088650 / line_thermal_face[92,83,0] | line.l53 / A | 92 / 0 | 0.3583310451 | 0.3583310451 | thermal_loading_pu |
| 2 | 1117505 / line_thermal_face[95,101,0] | line.l55 / A | 95 / 0 | 0.3407318269 | 0.3407318269 | thermal_loading_pu |
| 2 | 1088990 / line_thermal_face[92,101,0] | line.l55 / A | 92 / 0 | 0.3401185625 | 0.3401185625 | thermal_loading_pu |
| 2 | 1117898 / line_thermal_face[95,122,0] | line.l58 / A | 95 / 0 | 0.3391384878 | 0.3391384878 | thermal_loading_pu |
| 2 | 1089383 / line_thermal_face[92,122,0] | line.l58 / A | 92 / 0 | 0.3386117463 | 0.3386117463 | thermal_loading_pu |
| 2 | 1116807 / line_thermal_face[95,64,0] | line.l52 / A | 95 / 0 | 0.3202613085 | 0.3202613085 | thermal_loading_pu |
| 2 | 1116222 / line_thermal_face[95,33,0] | line.sw2 / A | 95 / 0 | 0.3173847811 | 0.3173847811 | thermal_loading_pu |
| 2 | 1116412 / line_thermal_face[95,43,0] | line.l116 / A | 95 / 0 | 0.3140967258 | 0.3140967258 | thermal_loading_pu |
| 2 | 1117165 / line_thermal_face[95,83,0] | line.l53 / A | 95 / 0 | 0.2903472141 | 0.2903472141 | thermal_loading_pu |
| 2 | 1117052 / line_thermal_face[95,77,0] | line.l52 / C | 95 / 0 | 0.2870993591 | 0.2870993591 | thermal_loading_pu |
| 2 | 511281 / transformer_kVA[31,212,6] | transformer.mess_idc06_tx / A | 31 / 6 | 16.3664437270 | 0.0667483253 | kVA |
| 2 | 511564 / transformer_kVA[31,227,6] | transformer.mess_idc06_tx / C | 31 / 6 | 16.3513492033 | 0.0666867643 | kVA |
| 2 | 1076378 / voltage_upper[91,239] | 83 / 2 | 91 / None | 1.4659857600 | 1.4659857600 | voltage_squared_pu |
| 2 | 1076668 / voltage_upper[91,384] | mess_sta12_pcc / 2 | 91 / None | 1.4659856123 | 1.4659856123 | voltage_squared_pu |
| 2 | 1028936 / voltage_lower[86,281] | idc_idc02_pcc / 1 | 86 / None | 0.3527015407 | 0.3527015407 | voltage_squared_pu |
| 2 | 1028948 / voltage_lower[86,287] | idc_idc04_pcc / 1 | 86 / None | 0.3523700104 | 0.3523700104 | voltage_squared_pu |

## 5. Native0 검증과 모델 규모

| 단계 | Rows | Columns | Binary | NNZ | 추가 K / 누적 K | 생성 Wall(초) | Native0 독립 인증 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 143292 | 244265 | 9322 | 1252450 | 16 / 32 | 0.944571 | PASS |
| 2 | 143308 | 244265 | 9322 | 1257052 | 16 / 48 | 0.950504 | PASS |

크기 게이트: Columns=244,265 유지, Binary=9,322 유지, Rows≤160,000, NNZ≤1,800,000. 원본 FULL 행렬 재생성이나 Joint16 재최적화 없이 기존 Joint CSR의 행 prefix를 그대로 유지한 채 검증 행만 붙였다. Bounds·Objective·타입·축·기존 K16·모든 물리 행의 bitwise 보존과 U4 MIP Start replay를 독립 검증했다. 실제 Gurobi CSR/RHS/Sense/Bounds/types/objective/readback을 Optimize 전에 다시 대조했다.

| 단계 | 모델 CSR SHA | 모델 domain SHA | CUTS_EXACT 파일 SHA |
| --- | --- | --- | --- |
| 1 | 38de5a40e834b9c20bd5ead6fa50fafa564bb1bd3f132fcd75825343b96efda2 | a9cccdf8c9f704c44911d96db3cdb3ea738c62dc0f350947d18654755e562fd1 | 288814541b8123c2437542d34955389775dbeb67d0adfd1dfac223e7087b6c9f |
| 2 | 9dd79e0f033df5317dc038ac4278f04460d36627b621cbf9834cd9928fab7b45 | aa5241e7aae73cdc42fc7f7f5bb9963cae66653fe6aa2d4adbcfa7717ee46414 | d5954b0058aafcef761d891673a0266371abeb39024832d8094e40e3051d2a80 |

| 단계 | U4 새 모델 최대 잔차 | Row ID 변조 | Phase 변조 | RHS 부호 변조 | 계수 변조 | Source SHA 변조 | 반올림 방향 변조 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.000000000000002 | 거부 | 거부 | 거부 | 거부 | 거부 | 거부 |
| 2 | 0.000000000000002 | 거부 | 거부 | 거부 | 거부 | 거부 | 거부 |

U4 저장점의 검증은 수치 replay 허용오차 1e−8을 사용한다. 채택 행의 Fraction 평가에서 최대 양의 잔차는 1.265767e-17다. 저장 binary64 U4 점 자체가 정확한 유리수 가능해라고 주장하지 않는다. 미소 양의 잔차를 실제 물리 위반으로 오인하지 않으며, 모든 정확한 FULL 가능해의 사영을 보존한다는 별도의 Fraction 포함관계 증명은 이 numerical Start replay와 구분한다.

## 6. Solver 결과와 누적 Global LB

각 새 실행은 Worker=1, Threads=1, TimeLimit=180초, MIPGap=0.03, MIPFocus=3, Seed=42, FeasibilityTol=IntFeasTol=OptimalityTol=1e−8을 유지했다. MIP Start는 새 제약까지 검증한 기존 U4를 사용했다. 이전 Joint 해는 새 채택 행을 위반하므로 무조건 Start로 전달하지 않았다.

| 단계 | Status | Root 완료 | Nodes | ObjBound / 새 LB | ObjVal(축소 해) | 축소 MIPGap(%) | 누적 LB | 직전 단계 대비 개선 | FULL Global Gap(%) | 최종 인증 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 9 | PASS | 1 | 0.4649761764 | 0.4812227125 | 3.37609503 | 0.4649761764 | 0.0394983932106444 | 31.22198014 | PASS |
| 2 | 9 | PASS | 1 | 0.4649848700 | 0.6760534505 | 31.22069421 | 0.4649848700 | 0.0000086935778974 | 31.22069421 | PASS |

1차 Presolve/Root 원시 로그 요약:

```text
Presolve removed 100 rows and 100 columns
Presolved: 143192 rows, 244165 columns, 1055012 nonzeros
Root relaxation: objective 4.649762e-01, 109530 iterations, 65.47 seconds (115.85 work units)
Explored 1 nodes (286335 simplex iterations) in 180.04 seconds (364.96 work units)
```

마지막 Root/Node 진행 행 (`IntInf` 포함, 원시 로그):

```text
     0     0    0.46498    0   19    0.48122    0.46498  3.38%     -  176s
```

2차 Presolve/Root 원시 로그 요약:

```text
Presolve removed 100 rows and 100 columns
Presolved: 143208 rows, 244165 columns, 1059526 nonzeros
Root relaxation: objective 4.649849e-01, 116512 iterations, 119.18 seconds (127.83 work units)
Explored 1 nodes (220073 simplex iterations) in 180.03 seconds (196.62 work units)
```

마지막 Root/Node 진행 행 (`IntInf` 포함, 원시 로그):

```text
     0     0    0.46498    0 1152    0.67605    0.46498  31.2%     -  180s
```

ObjVal은 축소 모델의 정수 incumbent 목적값이며 Global LB가 아니다. 새 LB는 실제 Gurobi `ObjBound`를 사용하고 최종 인증이 PASS한 단계만 누적한다. 축소 incumbent를 원본 FULL UB나 Actual OpenDSS PASS로 승격하지 않았다.

## 7. 2차 조건부 실행 및 예산

2차는 1차 최종 인증 완료, 신규 Certified LB 개선≥0.005, 유효한 새 정수해, 미포함 실제 위반 행, 재통과한 크기·RAM 게이트, 완전한 1차 종료 Ledger가 모두 확인될 때만 허용했다. 한 단계 최대 16행, 누적 최대 32행 추가, K 최대 48, 전체 Optimize 최대 2회 / 요청 360초 계약이다.

조건 및 실제 판단 기록:

```json
{
  "PASS": true,
  "phase": "STAGE2_PRE_BUILD_ADMISSION",
  "checks": {
    "stage1_final_certificate_PASS": true,
    "stage1_inclusion_integrity_PASS": true,
    "certified_improvement_at_least_005": true,
    "valid_new_integer_incumbent": true,
    "first_call_safe_and_complete": true,
    "complete_single_call_ledger": true,
    "no_stage1_result_hash_drift": true,
    "new_validated_violated_original_rows": true,
    "exact_cut_Native0_PASS": true,
    "model_size_PASS": true,
    "fresh_resource_HOLD_PASS": true,
    "new_cuts_exclude_previous_incumbent": true
  },
  "previous_certificate_sha256": "1111aeea18e486bb2b3b7bb03e5c769b7593a6e5d63c8ec859dea18a3fe29a73",
  "stage1_Global_LB": 0.46497617639758426,
  "delta_Joint16": 0.03949839321064441,
  "remaining_requested_Native_seconds": 180,
  "Native_optimize_calls": 0,
  "independent_native0_sha256": "2ab8c6f30cd4643cb14096b2c40a16bfc605a5c09685eb3fa633e0e878207b31",
  "selected_original_rows": [
    1088650,
    1117505,
    1088990,
    1117898,
    1089383,
    1116807,
    1116222,
    1116412,
    1117165,
    1117052,
    511281,
    511564,
    1076378,
    1076668,
    1028936,
    1028948
  ],
  "post_build_memory_and_native_readback_required_before_Optimize": true
}
```

실제 Ledger 호출 수: 2, 요청 예산: 360초. Native Runtime 합: 360.083000초. 종료 영수증이 없으면 Runtime을 임의로 0으로 만들지 않는다. 중단·TimeLimit·실패 실행의 latch나 예산을 초기화하지 않았다. 추가 Solver 실행·제약 확장·같은 모델 재실행은 수행하지 않았다.

1차 종료 시점의 1회 Ledger는 `NATIVE_LEDGER_STAGE1.json`으로 보존했고, 최종 2회 Ledger와 구분한다. Solver의 실제 TimeLimit 종료 시점에는 미세한 종료 오버헤드가 있을 수 있으므로 요청 예산과 측정 Runtime을 별도로 보고한다.

실제 Runtime의 요청 합 대비 종료 초과는 0.083000초다. 각각의 요청 TimeLimit는 180초로 고정했고 추가 Optimize나 재시작을 하지 않았다. 실행 Ledger snapshot 감사는 PASS이며, 1차 snapshot SHA `c516315a9ae2946cce36f2316a8ab2505afb4621cd2a21934445352069a406cb`, 2차 최종 SHA `f6972f5bf39ec3835926c27bf64f90b7565d5554e92df07171407c810aa3fb17`를 각 최종 인증서의 실행 당시 SHA와 대조했다. 1차 실행 소스는 `PILOT_STAGE1_EXECUTED.py`로 별도 보존했다. 2차 전에는 gate 필드와 admission 인증서 SHA 검사를 강화했으며 모델과 Native 수치 파라미터를 바꾸지 않았다.

## 8. 시간 및 메모리

| 단계 | Oracle Wall(초) | CSR 추출/결합 Wall(초) | 독립 Native0 Wall(초) | 독립 최종 인증 Wall(초) |
| --- | --- | --- | --- | --- |
| 1 | 10.961950 | 0.944571 | 8.871793 | 0.173234 |
| 2 | 10.692798 | 0.950504 | 8.813545 | 0.171414 |

| 단계 | Native(초) | Optimize Wall(초) | Gurobi 생성(초) | Peak RSS(GiB) | Peak Private Commit(GiB) | 최소 Available RAM(GiB) | 최소 Commit Available(GiB) | Gurobi MaxMemUsed(원시 GB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 180.047000 | 180.706363 | 0.390990 | 1.1404 | 3.1752 | 15.1807 | 25.7974 | 2.084241 |
| 2 | 180.036000 | 180.729352 | 0.400557 | 0.7590 | 2.0015 | 15.2289 | 25.7732 | 0.863968 |

RAM은 시스템 Available RAM, Commit은 Windows Commit Limit−Commit Total, RSS는 프로세스 Working Set, Private Commit은 프로세스 전용 commit이며 서로 대체하지 않는다. Gurobi MaxMemUsed는 Solver가 보고한 원시 GB다. 모델 생성 후 4 GiB RAM·6 GiB Commit reserve 위에 max(2 GiB, 관측 생성 Private 증가×4)의 추가 성장 여유를 확보했다. 0.5초 간격 callback에서 reserve 위반·수치/메모리 오류가 있으면 정상 terminate하도록 유지했다. 다른 Heavy Worker가 없는지 실행 직전 조사했고 기존 프로세스를 강제 종료하지 않았다.

| 단계 | 생성 후 Available RAM(GiB) | 생성 후 Commit Available(GiB) | 추가 예상 성장(GiB) | Admission | 메모리 중단 | 수치 오류 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 15.8571 | 27.0234 | 2.0000 | PASS | False | [] |
| 2 | 15.9115 | 26.8400 | 2.0000 | PASS | False | [] |

FULL CSR는 Oracle와 독립 소거 검사 프로세스에서 읽기 전용으로 사용하고 Solver 생성 전에 해제했다. Native Worker에는 Joint CSR만 있다. 보고한 Peak RSS/Private Commit은 각 Native Worker의 실제 계측치다. Oracle의 프로세스 Peak RSS는 별도 계측하지 않았으므로 Native 계측값을 전체 연구의 모든 프로세스 peak로 확대 해석하지 않는다.

## 9. 비교, 인증 범위 및 후속 판단

| 방법 / 기준 | Global LB | 검증 U4 대비 Gap(%) | 수학적 차이 |
| --- | --- | --- | --- |
| PR209 차량별 단일 가중합 | 0.1166646569 | 82.74327912 | 차량별 물리 정수 영역의 독립 하한 합산; 계통 행은 가중 평균 |
| Source18r Full Solver ObjBound | 0.2894004911 | 57.19266119 | 원본 Full Solver의 수치 B&B 하한; Root 미완료 과거 결과 |
| PR210 Joint16 | 0.4254777832 | 37.06447576 | 같은 rho에 K16을 별도 적용, 네 차량 물리 운전 공동 최적화 |
| 이번 CG 누적 | 0.4649848700 | 31.22069421 | K16·물리를 그대로 유지하고 실제 위반하는 원본 계통 행만 추가 |

독립 인증은 원본 Source·파일 SHA·helper Fraction 소거·Compact 사영·원본 포함관계·보수적 반올림·실제 Gurobi readback·Ledger·수치 상태·Bound/Incumbent 순서·원시 로그를 감사했다. Fraction 수준의 행 및 포함관계 증명과 Solver 수치 ObjBound의 신뢰 계약을 명확히 구분한다. Exact rational B&B trace 인증이나 별도 LP 최적화는 수행하지 않았다.

최종 판단: **CG_LB_MATERIAL_IMPROVEMENT**. 선정된 소수의 원본 위반 행 추가는 Joint16보다 유의미한 하한 개선을 보였다. 3% 목표까지의 하한 차이는 0.1907869770이며 아직 미완료다. 이번 승인된 제한에서 연구를 종료하고 자동 확대하지 않는다. 생략 제약의 범위와 Root LP의 정수 분수화가 후속 분석 대상이지만, 어느 하나가 유일한 병목이라고 증명하지 않았다. 정수해가 위반한 행만 추가해도 Root LB가 반드시 크게 상승하는 것은 아니다. 마지막 정수해를 FULL 가능해로 인증하거나 FULL 최적성을 증명하지 않았다.

**2차 증분과 확대 기각:** 2차는 1차 대비 LB를 **0.0000086935778974** 높였다. 이 증분은 0.005보다 작다. 원래 Joint16 대비 총 개선량 **0.0395070867885418**에 따른 최종 Material 판정과 2차 증분의 Nonmaterial 판단을 구분한다. 2차 SolCount=1이고 축소 incumbent rho=0.6760534504652340이다. 새 정수 incumbent는 확보되지 않았고 U4 Start만 남았다. Start rho가 원본 검증 UB보다 한 ULP 작게 보고되어도 새 FULL UB로 사용하지 않는다. Global Gap 계산은 계속 원본 검증 UB 0.6760534504652341을 사용한다.

원시 로그의 Root 완료 시간은 1차 65.47초, 2차 119.18초이고, 2차 종료 Root의 IntInf는 1,152였다. Root에서 높은 분수성, 더 긴 Root 비용, 거의 변하지 않은 유효 하한이 관측되었다. 진행 중 simplex의 약 0.527 목적값은 primal infeasibility가 남은 중간 숫자이므로 유효 하한으로 쓰지 않았다. 최종 채택한 2차 하한은 완료 Root 및 최종 B&B ObjBound 0.46498486997548166이다.

같은 고정 quota를 맹목적으로 확대하는 추가 iteration, 더 큰 캠페인, Solver 시간 연장은 **기각**한다. 이번 Source와 cut transport의 유효성은 확인됐지만 3% 수렴이 확인되지 않았다. 후속은 별도로 승인된 연구가 있을 때 LP 분수성·계통 제약 coverage가 하한에 작용하는 구조를 분석하는 것부터 검토한다. 이번 작업에서 추가 Solver는 실행하지 않는다.

## 10. Scientific Source·HOLD·증거 보존

| 항목 | 실행 전 감사 | 실행 후 감사 |
| --- | --- | --- |
| PR207/209/210 HEAD 및 pristine checkout | PASS | PASS |
| 공식 May HOLD marker 동일 | PASS | PASS |
| Supervisor/Monitor 예약 Disabled | PASS | PASS |
| 관련 자동화 PAUSED 및 동일 | PASS | PASS |
| 기존 controller 자손 계산 Worker 없음 | PASS | PASS |
| 별도 Heavy Gurobi/Native Worker 없음 | PASS | PASS |

Source18r·U4 엔진·기존 PR207/209/210 소스·결과·증거, StageBudget, NativeStopRequested, A1/A2/M-stage 예산, 원본 Planning/Actual 실행 코드를 변경하지 않았다. 새 연구 코드는 `tools/critical_grid_cg/`, 증거는 `docs/v42_critical_grid_cg/`에만 작성했다. Controller 상태는 관측 시점의 상태와 byte identity로 보고하며 연속 무CPU 상태를 주장하지 않는다.

보존 산출물은 USER_REQUEST_KO/TASK_CONTRACT, 각 SEPARATION/CANDIDATES/CUTS_EXACT, Native0·독립 Native0·모델 SHA·원시 Native.log·Native events·memory trace·readback·admission·durable started latch·Global NATIVE_LEDGER·최종 독립 인증서·FINAL_RESULT·전후 Resource/HOLD 감사다. 새 Draft PR은 PR210 연구 브랜치를 Base로 한다.
