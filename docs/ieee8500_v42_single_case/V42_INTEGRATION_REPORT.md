# V42 통합 상태 및 실제 미연결 경계

**연구용 LV 포트 설계와 6대 MESS 구성은 명시적으로 허용됐으며, 전체 IEEE8500 V42 Native 이식과 운영 시나리오 인증은 미완료다.** 최신 사용자 지시에 따라 실물 설치 기록이 없는 경우에도 SHA로 고정한 `SIMULATION_DESIGN`의 연구용 P/Q 한계를 허용한다. `ieee8500_v42/integration.py`는 동일 동결 입력의 B0/B1/B2/B3 요청, source byte 검증, 연구·Production 구분, 원본 M 변수에 추가할 위치별 제한 및 독립 수치 replay를 구현했다. 기존 IEEE123 Authority, 4대 차량 및 SOC 식을 실제 IEEE8500·6대·LV 효율 연결로 이식한 상태는 아니다. B1/B2/B3 Native optimize와 실제 FULL model build는 실행하지 않았다.

최신 실제 AC 결과에서 BG=0.552, GPU=1 기준의 전체 계통 최대 전압은 **1.05272588 pu**이며 0.95–1.05 pu 조건의 위반 셀은 **1373개**다. 12개 계통·GPU 스케일 조합 모두 전체 전압 조건을 통과하지 못했다. 선택된 12개 LV 지점의 8개 명령×96슬롯 및 추가 48개 유한 동작의 국소 정격 검사를 통과한 사실이 전체 계통의 운영 PASS 또는 연속 P/Q 영역의 인증을 뜻하지 않는다. 따라서 연구 구성은 검토 가능한 초안이며, 운영 가능한 단일 시나리오는 선택되지 않았다.

## 보존한 비교 계약

| Arm | 유연성 | 단계 | 각 단계 수용 Gap | Native 예산 및 설정 |
|---|---|---|---|---|
| B0 | AIDC OFF, MESS OFF | 기준 AC | 해당 없음 | Native 없음 |
| B1 | AIDC ON, MESS OFF | A1 | ≤0.5% | 측정된 Native Runtime 누적 5400초, Threads=1, P2=0 |
| B2 | AIDC OFF, MESS ON | M1 | ≤3% | 동일 |
| B3 | AIDC ON, MESS ON | A1→M1→A2→M2 | A≤0.5%, M≤3% | 네 단계별 독립 ledger; model/point/LB/UB/예산 이전 없음 |

모든 Arm 요청의 `scenario_sha`가 동일하다. B3에서는 원본 bridge의 A2에 M1 전체 경로·SOC·P/Q를 고정하고 M2에 A2 전체 AIDC 결정을 고정하는 계약을 유지해야 한다. P1의 `min rho_max`, 원본 16-face inner polygon, 0.95–1.05 pu 전압, 전체 선로 current/NormalAmps, 변압기 current와 winding kVA를 유지한다. 현재 승인된 P2=0과 기존 P1/P2 목적함수 의미는 별개다. 현 작업은 기존 목적함수 목록을 삭제하거나 재정의하지 않는다.

## 실제 source와의 불일치

| source / 함수 | 확인한 구체적 제한 | IEEE8500에서 필요한 조치 및 현 상태 |
|---|---|---|
| `v42_integrated.contract.physical_authority` | 44개 transformer, 120 phase rows, RegControl 7개, capacitor 4개를 assert | IEEE8500 장치·도체·권선 roster 기반 source hook 필요; 미연결 |
| `v42_thermal.authority.current_authority` | `full_ieee123_g11_v16_1._oriented_branches`와 PR127/IEEE123 compile 사용 | IEEE8500 도체와 모든 권선을 다시 bind하고 검증해야 함; 현재 Authority 재사용 불가 |
| `v42_thermal.planning.require_coefficient` | 정규화 분모 및 certificate를 위 IEEE123 current authority에 대조 | IEEE8500 전용 hook/certificate 필요; 이를 건너뛰면 실제 인증 아님 |
| `v42_may_campaign_native90.bindings.check_coefficients` | 120 transformer phase rows 및 60개 control axis | 새 feeder branch/node/winding/control 축의 독립 verifier 필요; 미연결 |
| `v42_bootstrap.m1.native_inputs` | `len(initial_MESS_sites)==4`, 서비스 위치 24개 | 차량 6개를 수용하는 정확한 axis adapter와 독립 재검증 필요; 원본 자체는 수정하지 않음 |
| `v42_may_campaign.m_model.build_case` | identity `units=4`; 고정 thermal row 수 | PR191 일부 feeder metadata routing은 존재하나 six-unit/추가 port-row routing 완료 아님 |
| `v42_native.mess.solve` | 차량 battery 정격을 모든 위치에 동일 적용; 위치별 device/phase/aggregate 제약 없음 | 기존 `strengthening_hook`에 새 제한을 append할 수 있음. 추가 hook 및 독립 validator 구현 완료, 생산 생성기 연결/동치성 미검증 |
| `v42_may_campaign_native90.operations._accepted/fresh` | `(96,4)` MESS/PQ/location, `(97,4)` SOC, MESS01–04, `all_7_RegControls_enabled`, CapControl 0 | six-unit 및 IEEE8500 controls의 독립 replay adapter 필요; 미연결 |
| 외부 `FrozenTrajectory`, `opendss_mapping`/`opendss_backend` | 현 소비 축 `mess_locations_96x4`; IEEE123 source-backed engine와 injection binding | split-phase nodal injection 및 six-unit 동일 스케줄 replay 필요; 미연결 |
| PR191 `InjectionAuthority` | feeder별 hook/validity/phase mapping/96 coefficient SHA를 주입하는 API 존재 | 이식 경로는 있으나 현재 IEEE8500 source-certified hook packet 없음 |
| PR191 `SourceRegistry`/`policy.require_production_authorization` | 실제 source import/실행에도 Production guard가 무조건 닫힘 | Caller bool/env로 unlock 불가; 별도 검토된 실제 실행 구현 필요 |

`v42_native.grid.add_grid` 자체는 전달된 branch/control 축으로 행을 만든다. 그러나 source에 포함된 thermal certificate, 압축 표현, independent source verifier, Actual injection까지 모두 같은 IEEE8500 물리 Authority를 소비해야 한다. Master DSS 파일만 교체하는 것으로 통합 완료라 할 수 없다.

### 원본 rho_max 측정 범위

현재 실제 source `v42_thermal.measurement.branch_measurement`와 외부 `dayahead/v28r2/opendss_backend.py::_branch_measurement`는 각 oriented branch의 **parent Bus가 속한 terminal**에서 `NodeOrder == phase`인 도체를 선택한다. phase는 A/B/C에 대응하는 1/2/3이다. 선로 분모는 원본 `Line.NormAmps()`다. 원본 topology `_phase_edges`는 enabled branch의 처음 두 terminal에서 공통인 `{1,2,3}` 노드만 생성하고, `_oriented_branches`는 IEEE123 root `150.1/2/3`을 고정한다.

따라서 현재 canonical objective는 line의 oriented-parent terminal phase-current rows 전체에 대한 최대값이다. **모든 terminal 또는 neutral을 합친 최대값과 동일한 정의라고 증명된 상태가 아니다.** IEEE8500에서는 Primary/Secondary/Triplex의 실제 접속 node mapping으로 새로운 canonical phase roster를 만들어야 하며, 3차 권선과 primary phase 3→split-phase secondary 1/2 같은 경우를 ABC 이름의 단순 교집합으로 삭제해서는 안 된다.

전 단자·전 도체의 current/정격 및 모든 transformer 권선 전류/kVA는 추가 physical audit로 반드시 검사한다. 이 더 넓은 audit의 최대값을 기존 canonical `rho_max`와 구분해서 표시한다. Audit 기준을 추가했다고 기존 목적함수의 범위를 몰래 바꾸지 않는다. LV 도체의 분모 및 phase/neutral 구분, full feeder canonical objective mapping이 입증될 때까지 IEEE123과 IEEE8500의 `min rho_max` 동일 의미 검증은 미완료다. 측정 source의 read-only SHA는 `OBJECTIVE_SCOPE_AUDIT.json`에 기록했다.

원본 M `RouteArc`는 물리 도착 `arrive`와 접속 가능 `connect`를 구분하지만 time-network 이동 arc의 끝은 `connect`다. 과거 PR45의 도착 후 아직 접속 준비 중인 차량의 재출발 보정은 현재 V42 모델에 그대로 존재하지 않는다. 이번 구현은 과거 알고리즘으로 교체하지 않았다. 이 동작 차이는 미래 통합 검토에서 명시적으로 다뤄야 한다.

## 추가 LV PCC 제한 구현

`LocationPort`는 서비스 정체성, Bus/Node, MV/240 V split-phase/120 V 단상 종류, 충전/방전 kW, 무효전력 kvar, PCS kVA, 차량 roster, 가능한 슬롯 및 근거 SHA를 저장한다. 일반 미검증 포트의 양수 P/Q는 거부한다. 최신 사용자 허용 범위에 해당하는 `SIMULATION_DESIGN`은 아래 두 파일의 SHA가 일치할 때 **RESEARCH에서만** 양수 한계를 허용한다.

- `integration_contracts/RESEARCH_SIMULATION_AUTHORITY.json`: 이미 받은 사용자의 시뮬레이션 설계 허용을 기록하며 `scope=RESEARCH_ONLY`, `production_authorized=false`다.
- `LV_PORT_SIMULATION_DESIGN.json`: 240 V split-phase `.1.2` 접속, 충전·방전 각각 5 kW 이하, \(|Q|\le3\) kvar, \(S\le6\) kVA, 각 hot 27 A 이하의 연구 설계다. 원래 service transformer와 Triplex 정격은 변경하지 않는다.

이 포트는 `certified=false`, `field_certified=false`를 유지한다. 450 kW 차량 정격이 저압 포트에 적용되지 않으며, 120 V leg 진단 모드가 이 상용 장치 설계로 승인되는 것도 아니다. Production에서는 실제 설치 장치, 계통 접속, 보호·접지, anti-islanding/grid profile, 차량 DC–DC/BMS 및 물리 접근의 전체 파일·SHA 근거가 필요하다. Boolean 또는 연구 권한을 바꿔 Production으로 승격할 수 없다. 실제 인증 체인을 제출하더라도 현재 `execute_production()` 실행 경로는 닫혀 있다.

`make_location_strengthening_hook()`는 원본 `StrengtheningContext`의 `x`, `stay`, `Pch`, `Pdis`, `Q`에만 추가 행을 붙인다. 각 차량의 올바른 위치/자격/시간을 통한 출력 gating, 포트별 PCS16, 동일 포트의 여섯 차량 합산 충전·방전·무효전력 한계와 PCS16을 적용한다. 공유 포트의 총 충전·총 방전 한계를 각각 적용하는 것은 보수적인 물리 조건이다. 연구용 5/3/6 한계도 개별 차량과 공유 포트에 동시에 적용한다. 원본 vehicle PCS, mode, SOC, 이동시간·에너지, grid 및 목적함수 행을 제거하지 않으며 새 변수를 만들지 않는다. 실제 전압에 따른 hot-current 한계와 원본 선로·권선 정격은 별도의 실제 AC 검사에서 확인해야 한다.

`validate_location_limits()`는 전체 site-variable 값을 독립적으로 검사해 shared-PCC 초과, 자격/시간 위반, TRANSIT 및 다른 위치의 출력, 누락된 변수, 잘못된 차량 축을 거부한다. 연결 위치는 별도로 성공한 원본 route replay에서 받아야 한다. 이 validator는 원본 SOC/경로/grid 검사나 실제 OpenDSS split-phase injection 검사를 대체하지 않는다. 새 행을 포함한 FULL→Compact→C3A exact transport, strict UB와 exact LB 및 source physical replay는 **NOT_TESTED**다.

## 6대 연구 구성과 AC 포트→battery SOC

`integration_contracts/RESEARCH_FLEET_CONFIGURATION.json`은 원래 6대의 초기 위치와 B2/B3 공통 배치를 보존한다.

| 차량 | 원래 초기 위치 | 연구 차량 정격 | 초기/종단 에너지 | 허용 에너지 범위 |
|---|---|---|---|---|
| MESS01 | STA01 | 450 kW / 600 kVA / 1800 kWh | 1140 / 1140 kWh | 660–1620 kWh |
| MESS02 | STA12 | 동일 | 동일 | 동일 |
| MESS03 | STA08 | 동일 | 동일 | 동일 |
| MESS04 | STA06 | 동일 | 동일 | 동일 |
| MESS05 | STA03 | 동일 | 동일 | 동일 |
| MESS06 | STA10 | 동일 | 동일 | 동일 |

원래 300 kW / 400 kVA / 1200 kWh와 440–1080 kWh, 초기·종단 760 kWh를 모두 1.5배하여 에너지 비율을 보존했다. 차량 main PCS의 원래 충·방전 효율 0.95와 연결 지연 600초를 유지한다. LV 포트는 별도 저출력 dock이며 추가 변환 효율 **0.90을 연구 가정으로** 기록한다. 그러므로 LV AC에서 battery로의 결합 효율은 \(0.95\times0.90=0.855\)다.

\[
\Delta E=\Delta t\left(\eta_{main}\eta_{LV}P_{ch,AC}
-\frac{P_{dis,AC}}{\eta_{main}\eta_{LV}}\right)-E_{route},
\qquad \eta_{LV}=0.90\text{ at LV dock},\;1.0\text{ at main PCS}.
\]

15분 동안 LV에서 5 kW를 충전하면 battery 증가분은 1.06875 kWh이고, 5 kW를 방전하면 감소분은 1.461988304 kWh다. 원본 route energy는 별도로 차감하며, 이상적인 Q의 에너지 의미를 유지한다. 추가 var/idle 손실의 실물 인증은 없다. `port_battery_energy_delta()`는 이 변환의 독립 수치 함수이며 실제 Native SOC 행의 구현을 주장하지 않는다.

현재 원본 Native SOC equality는 site AC 변수에 직접 효율 0.95를 적용한다. 따라서 **append-only 포트 행으로 추가 LV 손실이 구현되지는 않는다.** 두 번째 충돌하는 SOC equality를 붙이지 않았고 원본 식을 수정하지 않았다. 실제 위치 의존 효율 adapter와 6대 Native/Actual/Fresh 축 adapter는 **UNVERIFIED**다. 원래 이동시간·safe ETA·이동 에너지식을 변경하지 않았으며, 원래 28000 kg 차량 질량이 새로운 1800 kWh pack에 실제로 적용되는지는 미검증이다.

## 남은 통합 검증

연구용 포트의 실물 기록이 없다는 이유만으로 연구 검사를 막지는 않는다. 남은 실제 모델 검증은 다음과 같다.

- 위 source 표의 IEEE123 장치·control·열 정격 Authority 및 source verifier를 원본 IEEE8500 객체·도체·권선으로 연결해야 한다. 별도 OpenDSS screening engine의 구현이 전체 V42 source 연결을 대신하지 않는다.
- 현재 pinned Native 입력은 `network=IEEE123` 및 초기 차량 4대다. 선언한 원래 6대 연구 배치를 실제 FULL/Compact/C3A 및 Actual/Fresh의 6대 축으로 운반하고 SOC·목적함수·정격 의미가 동일함을 검증해야 한다.
- 현재 `WINDOWS.json`의 1605행은 Job의 시작 허용 창이며 접속·도로 접근 창이 아니다. 현재 B0 reference와 Native B1의 알려진 job 배치는 위치 1290개, 시작 1024개가 다르다. 임의 window 해석 또는 단순 복사로 동일 workload/route authority를 인증할 수 없다. 연결 지연 600초의 연구 가정과 실제 접근 창의 근거를 구분해야 한다.
- 실제 자동 RegControl 검사에서 fresh 양/음 endpoint의 tap이 다른 행은 독립 조사 16행 중 4행이었다. 고정 tap의 4개 witness 슬롯 중앙 차분과 96슬롯의 유한 명령 AC PASS는 모든 슬롯의 연속 제어 영역·원본 controls를 포함한 affine certificate를 제공하지 않는다.
- 모든 96슬롯의 전체 계통 전압, 전 단자 도체와 transformer 모든 권선의 정격 및 독립 Actual/Fresh 검사를 통과해야 한다. 현재 12개 스케일의 전체 전압 실패가 운영 가능한 단일 시나리오 선택을 막고 있다.

## 적격성 gate와 실행 범위

단일 동결 설정, 원본 branch/conductor identity, 모든 전압/권선 정격, 상대 위치, LV 장치 적격성, 원본 causal Job/GPU/Rack/WAN/QoS, 96슬롯 민감도 유효 영역, feeder source hooks, six-unit 표현 동치성, 추가 위치제약 replay, Planning/Actual/Fresh hook, 모든 96슬롯 실제 AC 실현 가능성을 각각 검증해야 한다. Gate receipt는 동결 scenario SHA, 검사 source SHA 및 파일 SHA가 일치해야 한다. Fixture 또는 fake source PASS는 실제 gate PASS로 승격되지 않는다.

`comparison_plan()`은 준비 요청만 만든다. `execute_production()`은 항상 `IEEE8500_V42_CERTIFIED_PRODUCTION_PORT_NOT_AVAILABLE`로 차단한다. 최종 시나리오가 과학적으로 검증·동결된 뒤 사용자의 별도 승인과 실제 source 실행 구현을 갖추어야 한다. 현재 캠페인 permit/ledger를 빌려 쓰지 않는다.

검증은 `python -B -m unittest discover -s tests -p test_ieee8500_v42_integration.py -v`의 **16개 fixture/contract 테스트 PASS**다. 새 검사는 SHA 없는 양수 한계, 다른 설계 SHA, 사용자 허용 없는 권한, 5/3/6 초과, Production 승격 및 실제 certificate 대신 Boolean을 쓰는 경우를 거부한다. 허용된 연구용 nonzero P/Q가 추가 행을 만족하고 공유 Q=4 kvar가 3 kvar 행에 의해 거부되는지, 기존 변수 수·행·목적함수가 보존되는지, 원래 6대 위치·에너지 비율과 LV 효율 변환을 확인했다. 이전 독립 검사의 원본 **962개 source byte identity PASS**는 `INTEGRATION_LIGHTWEIGHT_VALIDATION.json`에 기록되어 있다. 최신 계약 테스트 receipt는 `integration_contracts/INTEGRATION_CONTRACT_TEST_RECEIPT.json`이다.

Fixture row count·불변 objective 검사와 수치 replay는 실제 Native 생성/solve 또는 AC PASS가 아니다. 실제 Feeder AC Screening·RegControl·민감도 결과는 해당 산출물에 독립적으로 기록한다. 전체 B0/B1/B2/B3 Actual 성능 비교, Global LB/UB, native Gap, full-model 성능/RSS는 **NOT_RUN**다.

## 검토 이후 최신 V42 source에 대한 추가 기록

위 원본 API 검토는 동결 기준 `de6f79cd2cd215f0ed657b99d24b9ac26980ddc1`에 대한 기록이다. 확인 시점 GitHub `v42` HEAD는 `87480938c4c3eb9faca9eadef7a87e8e12a44d18`로 진전했으며, 추가된 V10 복구 코드·기록 41개 외에 기존 파일 수정·삭제는 없다. 기존 962개 source의 작업트리 SHA와 두 커밋의 Git blob identity 모두 PASS다. 기존 checkout, 구성 SHA `8f1ad20d…`, mapping 및 AC 결과는 수정하지 않았다.

최신 V10 `numerical.precision_enabled/set_precision`은 B1의 `INTEGER_CONTROL`도 FeasibilityTol/OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2로 처리한다. Phase I Presolve=0과 기존 Method/IntFeasTol/Heuristics는 유지된다. `a_stage.native_port/run_port`는 원 V6 계산을 versioned execution/numerical metadata로 route하며 `failure_classification`이 LB/UB 수치 충돌과 callback 오류의 분류를 구분한다. 새 DateBudget은 외부 May31 재시도의 이전 measured Runtime을 SHA-bound ledger에서 합산한다. 새 IEEE8500 연구 ledger의 이전 Runtime은 **0초**이며 외부194.442초·point·LB/UB·campaign permit는 이전하지 않는다.

V10 M/operations/execution/full-validation 대응 파일은 V9와 byte-identical이다. 기존 IEEE123 Authority·4대 차량 축과 실제 물리 replay가 남아 있고, 직접 수치 정책의 허용 arm은 B1/B2다. V10 소스 추가만으로 IEEE8500·6대·LV Native/Actual/Fresh 또는 B3 A1/A2 정책 연결이 구현된 것은 아니다. 원 Operations PASS는 Fresh/authority 완료를 검사하고 physical violation을 별도로 전달하므로 무위반 인증과 구분한다. 최신 전체 source 연결·FULL/Compact/C3A added-row 동치성 및 Native 실행은 계속 **UNVERIFIED/NOT_RUN**이다.

이 추가 감사는 격리 Git ref/object 읽기와 SHA 비교만 수행했다. Source import, Worker, Native, FULL build, 새 AC 및 외부 campaign mutation은 0회다. 정확한 최신 source SHA·함수 signature·line·구성 보존은 `SOURCE_ADVANCE_SINCE_REVIEW.json`, 짧은 설명은 `SOURCE_ADVANCE_SINCE_REVIEW_KO.md`에 기록했다. 외부 V10 May31 성공 기록을 본 IEEE8500의 전역 AC FAIL이나 운영 적격성 PASS로 이전하지 않는다.
