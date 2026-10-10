# B2 May01 Actual 과전압 — 원본 Fresh 재현 및 P/Q 원인 분리

원본 B2 May01의 19건은 실제 과전압이며, 기존 `ACTUAL_AC_FAILED` 판정을 유지합니다. 원본 P/Q를 적용한 Fresh 재실행은 전압·전류·탭·capacitor 등을 포함한 13개 AC 배열을 비트 단위로 재현했습니다. 동일 Actual 외생 입력에서 MESS P/Q를 모두 제거하면 전압 위반은 0건입니다. 원래 19개 셀 중 Q-only에서 18개가 계속 위반하고 P-only에서는 0개이므로, 이 19개 위반의 주된 노출은 MESS Q를 포함한 전일 운전입니다. P-only 전일 실험에는 원래 19개와 다른 셀의 위반 4개가 있습니다.

B0/B1/B2의 7개 RegControl 설정·활성 상태·초기 탭과 capacitor 설정은 동일합니다. 공통 제어 설정이나 Fresh 실행 경로의 결함은 이번 감사에서 확인되지 않았습니다. Planning의 고정 affine 전압 예측과 Actual의 비선형 전력조류·자율 탭 응답 사이의 차이는 확인했습니다. 다만 예측 오차, 비선형 응답, 탭 변화의 개별 원인을 하나로 고유하게 식별한 실험은 아닙니다.

## 1. 재현과 입력 보존

원본 실행 commit은 `1e691988dce2cf0f54f44851cd1a19634bbe68ff`, execution Source SHA는 `9df4e1dfba249aad77a0eca8077aeca951108dff55c6a29d891e192aab20297a`입니다. 원본 AC NPZ와 Full P/Q 진단 NPZ의 SHA는 모두 `6d1591cd20759465c215ce80fe786f286eebe6182c038d5ce1fbe79e966443dc`입니다. AIDC NPZ, 실현 AEMO 입력, base load/PV 설정, MESS 위치·unit ID 및 나머지 저장 배열은 보존했습니다. 전일 base/AIDC load 및 비-MESS solar의 실제 엔진 주입 관측 파일 SHA도 네 실험 모두 같습니다.

실행 경로는 원본 `operations.fresh → _fresh_port(v42_pr134_b1.replay.fresh) → dayahead.v28r2.opendss_backend.run_fresh_opendss`입니다. 기존 96슬롯 backend와 SolveSnap 연산을 수정하지 않고 외부 진단 NPZ를 기존 Actual 입력 바인딩에 연결했습니다. 관측 훅은 주입값·설정·탭·반복 횟수를 읽기만 합니다. RegControl·capacitor·tap 설정을 수동으로 지정하거나 Planning 탭을 Actual에 강제하지 않았습니다. 원본 소스·입력의 전후 SHA 검증이 통과했으며 optimizer/Native 호출은 0회입니다. 공식 캠페인 결과는 작성하거나 변경하지 않았습니다.

[전체 실행·입력·소스 receipt](D:/v42_actual_voltage_audit_20261010/FACTORIAL_REPLAY_STATUS.json), [재현 스크립트](D:/v42_actual_voltage_audit_20261010/FACTORIAL_FRESH_REPLAY.py), [원본 제어 감사](D:/v42_actual_voltage_audit_20261010/CONTROL_AUDIT_RESULT.json)

## 2. 동일 Actual 입력의 네 가지 전일 실험

| 실험 | 전압 위반 셀 | Vmin (pu) | Vmax (pu) | Actual 최대선로부하율 | 수렴/제어 완료 |
|---|---:|---:|---:|---:|---:|
| Full P/Q, 원본 정확 재현 | 19 | 0.9558012512 | 1.0583754891 | 59.90347230% | 96/96, 96/96 |
| P-only, Q=0 | 4 | 0.9796027820 | 1.0533898455 | 61.92684301% | 96/96, 96/96 |
| Q-only, P=0 | 34 | 0.9558012524 | 1.0583754891 | 69.69615013% | 96/96, 96/96 |
| P=Q=0 | 0 | 0.9777019158 | 1.0488395651 | 71.33046366% | 96/96, 96/96 |

네 실험의 선로전류·변압기전류·변압기 kVA 위반은 모두 0건입니다. 최대선로부하율은 저장된 normalized 지표를 복사하지 않고, 원본 263개 line-phase 및 동일 NormalAmps를 사용하여 `100 × max(|raw current_a| / NormalAmps)`로 재계산했습니다. 저장 loading 배열과의 차이는 0입니다. [raw 전류 검증](D:/v42_actual_voltage_audit_20261010/B2_MAY01_FACTORIAL_RAW_LINE_LOADING.csv)

각 실험은 4대 MESS의 **96슬롯 전체** P 또는 Q를 제거합니다. 기존 자율 제어를 매 슬롯 수행하여 그 운전 이력에 따른 탭이 형성됩니다. 따라서 셀별 조건부 효과에는 직접 전력 주입, 네트워크 비선형 응답, 전일 제어 이력의 영향이 함께 들어 있습니다. 특정 슬롯·장치의 국소 편미분이나 순수 고정 탭 효과가 아닙니다. SOC 배열이 보존되었다고 해서 바뀐 P-only/Q-only 입력의 SOC·PCS·목적함수·전체 최적화 제약을 검증한 것은 아닙니다. 이러한 입력은 새로운 가능 최적화점이나 실제 운전 계획으로 승인하지 않습니다.

## 3. 원래 19개 셀과 최대 위반

19건은 모두 MESS PCC의 상한 위반입니다. 위치는 STA01.B, STA06.A/B/C, STA08.A/B/C, STA12.A/B이고, 0-based 슬롯은 0, 2, 3, 10, 13, 15, 19, 95입니다. 동일 19개 셀을 추적하면 Full=19, Q-only=18, P-only=0, zero=0입니다. Q 제거의 조건부 효과는 원래 P를 유지했을 때 19개 모두 +0.01539873~+0.04593765 pu입니다. 따라서 Q가 이 노출에 기여한다는 결과는 직접적인 입력 개입으로 확인됩니다. 한 셀은 Full에서만 위반하므로 전일 P/Q 상호작용도 무시할 수 없습니다.

최대 위반은 `mess_sta08_pcc.1` / STA08 A상, 슬롯 11 (0-based 10), 2025-05-01 02:45 AEST 구간 종료입니다.

| 같은 셀의 값 | pu |
|---|---:|
| 원본 Planning Full | 1.0455284095019148 |
| Actual Full | 1.0583754890888868 |
| Actual P-only | 1.0262251105954137 |
| Actual Q-only | 1.0583754890888868 |
| Actual zero | 1.0327267471742596 |
| Actual Full − Planning Full | +0.0128470795869720 |
| Actual 상한 1.050 초과 | +0.0083754890888867 |
| Q 효과: P=0일 때 Q-only−zero | +0.0256487419146272 |
| Q 효과: 원본 P일 때 Full−P-only | +0.0321503784934731 |
| P 효과: Q=0일 때 P-only−zero | −0.0065016365788459 |
| P 효과: 원본 Q일 때 Full−Q-only | 0 |
| P/Q 상호작용: Full−P-only−Q-only+zero | +0.0065016365788459 |

이 셀에는 MESS03이 연결되어 원본 Q=+363.391878885411 kvar, P≈−1.14×10⁻¹³ kW입니다. 같은 슬롯의 네 MESS P는 모두 수치상 거의 0이고 Q는 각각 −290.53435, −392.31411, +363.39188, −392.31411 kvar입니다. 그러나 효과 수치는 **모든 장치의 전일 개입**에서 얻었으므로 전부를 STA08의 Q 하나에 귀속하지 않습니다. 현재 P가 0에 가까워도 P-only 운전 이력에서 탭이 달라질 수 있습니다.

전수 셀별 전압·조건부 P/Q 효과·상호작용·원본 P/Q·위치·7개 탭은 [19-cell factorial CSV](D:/v42_actual_voltage_audit_20261010/B2_MAY01_19CELL_PQ_FACTORIAL.csv)에 저장했습니다.

## 4. 원본 Planning 모델과 Actual의 차이

Planning 전압은 당시 strict FULL 점을 원래 affine **제곱전압** 행에 대입하여 복원한 값입니다. 별도 Planning AC 재실행 값이 아닙니다. 원본 FULL 행과 원본 export 계수의 독립 복원 차이는 최대 2.22×10⁻¹⁶입니다. P-only/Q-only/zero Planning 계산에서는 원래 non-MESS 좌표를 모두 유지했습니다. 이 가상 좌표 평가 역시 새로운 strict 가능점을 뜻하지 않습니다.

원본 source는 슬롯별 forecast base/PV와 원래 reference AIDC, MESS P/Q=0을 적용한 뒤 활성 native controls를 수렴시켜 anchor 탭·capacitor 상태를 저장합니다. 이후 그 탭·capacitor를 고정하고 controls를 비활성화하여 finite differences를 계산합니다. export된 Planning H에는 원래 고정된 April joint-gradient 1,728쌍이 반영되어 있고 같은 AC anchor에 다시 맞춰져 있습니다. raw D1 H만 사용하지 않고 **당시 export 계수 및 FULL readback**으로 검증했습니다. May 결과를 이용해 기존 gradient를 바꾸지 않았습니다.

최대 위반 셀에서 Planning zero=1.0327644720068856, Planning Q-only=1.0455284095019148입니다. 따라서 Planning Q 효과 +0.0127639374950292 pu에 비해 Actual Q-only 효과는 +0.0256487419146272 pu입니다. 다음 항등식이 19개 셀 모두 잔차 0으로 성립합니다.

`ActualFull−PlanFull = (Actualzero−Planzero) + [(ActualFull−Actualzero)−(PlanFull−Planzero)]`

최대 셀의 +0.0128470795869720 pu 차이는 zero 기준 차이 −0.0000377248326260 pu와 MESS 응답 예측 오차 +0.0128848044195979 pu의 합입니다. 이 셀에서는 zero 기준 차이가 작고 MESS 응답 차이가 대부분입니다. Actual P-only 효과 오차 −0.0065016365788457 pu와 상호작용 오차 +0.0065016365788457 pu가 상쇄됩니다. 고정 affine 제곱전압 모델의 P/Q 상호작용은 수치 오차 수준이고, pu로 변환하는 제곱근에서 생기는 상호작용은 별도로 구분했습니다.

zero 기준 잔차에는 forecast–Actual 외생 입력 차이, 고정 AIDC의 anchor 대비 차이, affine 모델 오차와 자율 제어 응답이 함께 포함됩니다. 전일 forecast–Actual AEMO demand 최대 절대 차이는 469.19 MW, PV는 68.698 MW이고, 고정 Planning AIDC는 anchor 대비 565 slot-site 좌표에서 달라지며 최대 차이는 54.77240 kW입니다. AEMO MW 차이는 feeder에 실제 주입된 kW 차이와 같은 값으로 해석하지 않습니다. 이번 비교만으로 forecast 오류 또는 탭 선형화 중 어느 하나를 유일한 원인으로 확정하지 않습니다.

[Planning–Actual 19셀 분해](D:/v42_actual_voltage_audit_20261010/B2_MAY01_PLANNING_ACTUAL_FACTORIAL_19CELLS.csv), [계수·anchor·source proof](D:/v42_actual_voltage_audit_20261010/B2_MAY01_PLANNING_ACTUAL_FACTORIAL_AUDIT.json)

## 5. 제어기 설정, 실제 탭과 반복 횟수

7개 RegControl은 모든 슬롯에서 활성화되며, Fresh 시작 탭은 모두 1.0, 모드는 snapshot/static, MaxControlIterations=100입니다. 4개 capacitor는 고정 ON이고 CapControl은 0개입니다. 공통 설정 SHA는 `3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf`입니다.

| Arm | 관측 근거 | 최대 ControlIterations | 최대 Solution.Iterations 합계 | 제어 완료 | 설정 MaxIterations |
|---|---|---:|---:|---:|---:|
| B0 | 기존 RAW 로그 | 3 | 9 | 96/96 | 기존 로그 미기록 |
| B1 | 원본 13개 AC 배열 비트 재현 진단 | 3 | 9 | 96/96 | 15 |
| B2 | 원본 Full P/Q 비트 재현 진단 | 5 | 17 | 96/96 | 15 |

역사적 B1/B2의 미기록 반복 횟수는 UNKNOWN으로 남겨두고, 새 측정값을 외부 진단 receipt에 기록했습니다. `Iterations`는 제어 반복을 포함한 전체 합계이며, 개별 제어 pass의 최대치인 `MostIterationsDone`과 다릅니다. 따라서 합계 17만으로 설정 15 위반이라고 판정하지 않습니다. 이번 훅은 `MostIterationsDone`을 측정하지 않았습니다. [공식 API 정의](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.Iterations), [MostIterationsDone](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.MostIterationsDone)

Full과 zero의 탭은 672개 slot-regulator 상태 중 502개에서 의미 있게 다릅니다. 최대 차이는 0.025이며 96개 슬롯 모두 적어도 한 regulator가 다릅니다. P-only는 205개, Q-only는 475개에서 zero와 다릅니다. capacitor는 네 실험 모두 같습니다. floating ULP 차이를 탭 동작으로 세지 않도록 |차이|>10⁻¹²를 사용했으며, literal 차이 570개도 별도 저장했습니다. 원래 tap step 0.00625를 바꾸지 않았습니다.

Planning anchor와 Actual Full의 의미 있는 탭 차이는 418/672개, zero와는 314/672개입니다. 원래 Planning sensitivity가 참조한 탭 상태와 Actual 제어 응답은 다릅니다. 이 차이는 source 설정 변경의 증거가 아니며, 탭의 단독 인과 기여를 수치로 분리하려면 별도 제어 개입이 필요합니다. 본 감사에서는 그러한 개입을 수행하지 않았습니다.

[실험별 탭 전수](D:/v42_actual_voltage_audit_20261010/B2_MAY01_FACTORIAL_TAP_TRAJECTORIES.csv), [Planning anchor 비교](D:/v42_actual_voltage_audit_20261010/B2_MAY01_PLANNING_ANCHOR_ACTUAL_TAPS.csv), [B0/B1/B2 반복 횟수 receipt](D:/v42_actual_voltage_audit_20261010/CONTROL_DIAGNOSTIC_SUPPLEMENT.json)

## 6. 과학적 판정과 후속 실험의 경계

확인된 물리적 노출은 동일 Actual 입력·원래 제어 아래의 MESS P/Q 전일 운전이며, 원래 19개 셀에서는 Q를 포함한 응답이 지배적입니다. 원본 Planning은 이 응답을 충분히 예측하지 못했습니다. 공통 RegControl 설정 오류, 제어 미완료, 원본 Actual에 Planning 탭 강제 등의 증거는 없습니다. 비선형 전기 응답과 자율 탭 이력, 외생 입력 및 anchor 차이 중 하나만을 유일 원인으로 단정할 수는 없습니다.

Planning 상한 1.048 pu 후보는 별도의 과학적 정책 실험입니다. 이 감사의 응답 오차로 그 정책의 성공을 보장하거나 결과를 미리 계산하지 않습니다. 기존 1.050 결과 및 Actual 0.950~1.050 기준을 보존한 실제 재최적화·96슬롯 Fresh 결과로 판단해야 합니다. 이 자료는 May01 진단이며 독립 holdout 성능이나 31일 전환 근거로 단독 사용하지 않습니다.

재현 명령은 `python -B -I D:\v42_actual_voltage_audit_20261010\FACTORIAL_FRESH_REPLAY.py`와 `python -B -I D:\v42_actual_voltage_audit_20261010\ANALYZE_FACTORIAL_CELLS.py`입니다. Fresh 재현은 외부 진단 출력만 생성합니다. 모든 상세 SHA·물리 입력·출력 receipt는 위 JSON과 최종 [통합 감사 receipt](D:/v42_actual_voltage_audit_20261010/B2_MAY01_CAUSAL_AUDIT_RECEIPTS.json)에 포함했습니다.
