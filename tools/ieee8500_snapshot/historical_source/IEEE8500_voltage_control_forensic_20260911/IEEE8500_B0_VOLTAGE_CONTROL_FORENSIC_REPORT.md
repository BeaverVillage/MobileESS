# IEEE8500 B0 voltage-control compatibility forensic

**결론: NATIVE_VOLTAGE_CONTROL_COMPATIBILITY_MISMATCH.** 기존 `NO_FEASIBLE_ALPHA_ON_FROZEN_GRID`, selected alpha=null, FINAL 24-location mapping, PCC overlay, AIDC/MESS 규모와 hard limits를 모두 보존했다. 이 문서는 root-cause classification이며 production parameter 제안·선정·변경이 아니다.

## Native 96-slot 재현과 witness

대표 alpha 1.00, 0.60, 0.55, 0.25, 0.00의 총 480 slots를 새 엔진에서 재실행했다. 모든 슬롯이 수렴했고, 원본의 모든 전압·선로 current·transformer current/kVA 배열과 accepted tap/cap states가 일치했다. 최대 배열 차이는 0이다. 입력은 동결된 2025-05-21 B0 forecast/PQ이며 Actual 및 B1/B2/B3를 사용하지 않았다.

| Alpha | Witness | Slot (0-based) | Bus.local node | Upstream primary phase | Voltage pu |
|---:|---|---:|---|---|---:|
| 1.00 | Vmax | 40 | _hvmv_sub_lsb.3 | C | 1.062024870 |
| 1.00 | Vmin | 70 | sx2748781a.2 | A | 0.906247684 |
| 0.60 | Vmax | 50 | regxfmr_190-8581.3 | C | 1.066308339 |
| 0.60 | Vmin | 30 | sx2802481a.1 | A | 0.977057870 |
| 0.55 | Vmax | 50 | regxfmr_190-8581.2 | B | 1.070915190 |
| 0.55 | Vmin | 71 | sx2710504b.1 | B | 0.985617167 |
| 0.25 | Vmax | 51 | regxfmr_190-7361.3 | C | 1.053585239 |
| 0.25 | Vmin | 69 | sx3101194c.1 | C | 1.011610371 |
| 0.00 | Vmax | 37 | regxfmr_190-7361.3 | C | 1.058661486 |
| 0.00 | Vmin | 0 | x2748157a.1 | A | 1.038218133 |

Local secondary node 2는 primary B상이 아니다. 각 witness는 service transformer의 실제 primary phase로 역추적했다. Source bus부터 frozen feeder root `_hvmv_sub_lsb`를 거치는 경로와 모든 bank의 accepted tap을 저장했다. Substation delta/wye의 phase label은 topology label이며 위상각이 보존된다는 뜻이 아니다.

## 분리된 원인

1. **Feeder-root regulator 제어 목표와 1.05 pu hard ceiling의 불일치.** Vreg=126.5 V, PT ratio=60, band=2 V는 compiled nominal base에서 target **1.054231406 pu**, deadband **1.045897561–1.062565251 pu**에 해당한다. Alpha 1.00의 global Vmax는 FEEDER_REGC 출구이며 accepted tap은 +2, 1.0125 pu다. Native controller가 자신의 허용 범위에 도달해도 uniform 1.05 pu hard limit는 위반할 수 있다.

2. **Fixed/uncontrolled CAPBank3의 light-load voltage rise.** Native model은 controlled capacitor 9개와 별도 uncontrolled 900-kvar three-phase CAPBank3를 포함한다. Alpha=0 Vmax witness에서 controlled capacitors는 OFF이고 CAPBank3는 약 **992.074821 kvar**를 주입한다. 독립 실행에서 native background P=Q=0, PV disabled를 모두 직접 확인했지만 Vmax **1.058661486 pu**가 재현됐다. AIDC 부하는 약 **550.730351 kW**로 그대로 남는다. 따라서 alpha=0은 전체 feeder 무부하 조건이 아니다.

3. **일부 과전압 witness는 regulator의 제어 대상 downstream bus가 아닌 upstream terminal이다.** Alpha 0.60/0.55는 VREG3 입구 `regxfmr_190-8581`, alpha 0.25/0.00은 VREG4 입구 `regxfmr_190-7361`에서 global Vmax가 발생한다. 해당 regulator의 buck tap으로 downstream voltage를 낮춰도 upstream witness는 직접 clamp되지 않는다. 각 phase의 입·출구 전압과 accepted tap은 별도 CSV에 있다.

4. **Source-only 변경에 대한 regulator의 보상 반응.** Source setpoint 1.05 pu는 이미 hard upper ceiling에 놓여 있다. Alpha=0의 동일 witness에서 source만 1.00으로 낮추면 taps-held Vmax는 **1.007828619 pu**로 내려가지만, native control response 후 **1.059430218 pu**로 다시 상승한다. 이는 source 설정 하나의 효과와 regulator feedback을 분리해 보여준다.

5. **Global scaling은 진단이며 안정한 production 해가 아니다.** Algebraic factor 20/21을 source 및 12개 Vreg에 함께 적용했다. Native bands와 capacitor settings는 유지했다. 일부 조건은 undervoltage/thermal 문제가 남고, 아래 세 조건은 native control response가 1000 iterations 안에 settle하지 않았다. 원래 native trajectories는 모두 수렴했으므로 이 진단에서 발생한 미수렴을 native alpha screen의 원인으로 혼동하면 안 된다.

## 동일 alpha=0 Vmax witness (slot 37) 비교

모든 case는 같은 native prefix, 같은 AIDC/background/PV/time, 같은 accepted tap/cap state에서 시작한다. State-held는 제어 실행을 멈추어 직접 전기적 효과를 보며, control-settled는 intervention 후 native feedback을 허용한다. 두 비교 모두 진단용이다.

| Diagnostic case | State-held global Vmax | Control-settled Vmin | Control-settled Vmax | Line max pu |
|---|---:|---:|---:|---:|
| Native | 1.058661486 | 1.038352767 | 1.058661486 | 0.108933 |
| All capacitors disabled | 1.049999979 | 1.039017236 | 1.049999979 | 0.076266 |
| Fixed CAPBank3 only disabled | 1.049999979 | 1.039017236 | 1.049999979 | 0.076266 |
| Source pu=1.00 only | 1.007828619 | 1.000000051 | 1.059430218 | 0.109012 |
| Source + all Vreg ×20/21 | 1.007828621 | 0.988263556 | 1.007828559 | 0.103703 |

이 witness에서는 all-capacitor 제거와 fixed CAPBank3만 제거한 결과가 거의 동일하다. Native controlled banks가 이미 OFF였다는 state evidence와 일치한다. 이 조건부 비교는 fixed shunt의 기여를 보여주며, production에서 capacitor를 제거하라는 결론이 아니다. 다른 alpha/witness에서는 controlled capacitor와 regulator feedback이 함께 작용하므로 차이를 additive 기여율로 합산하지 않는다.

## Counterfactual control 미수렴과 검증 범위

Primary 비교는 `diagnostic_no_instrumentation/`와 `COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv`이다. 10 native witness conditions ×5 cases ×2 views=100 비교를 모두 저장했다. 아래 CONTROL_SETTLED 요청은 실제로 **CONTROL_ITERATION_LIMIT_EXCEEDED**이며, 저장값은 converged 해가 아닌 last iterate다:

- alpha=0.60, Vmin, slot 30: 1000 control iterations; pending queue ['120, 7, 2202, 2, 0, capbank1c_ctrl '].
- alpha=0.55, Vmin, slot 71: 1000 control iterations; pending queue ['217, 17, 3101, 2, 0, capbank1b_ctrl '].
- alpha=0.25, Vmax, slot 51: 1000 control iterations; pending queue ['2579, 12, 2780, 1, 0, capbank0a_ctrl ', '2580, 12, 2802, 2, 0, capbank0c_ctrl '].

초기 실행의 첫 control-limit 예외를 보존하고 동일 조건으로 재검증했다. 중간 EventLog property 편집이 일부 control response를 바꾸는 현상이 확인돼, 최종 원인 분류는 **계측용 property 편집도 없는** 독립 비교만 사용한다. 이전 실행도 `diagnostic_only/` 및 비교 audit에 보존했으며 숨기거나 정상 해로 대체하지 않았다. Visible initial tap/cap states는 같았지만 내부 controller-state reset 여부는 인증하지 않았으므로 해당 runtime 내부 원인은 단정하지 않는다. Solver iteration cap이나 hard limits를 늘리지 않았다.

Native의 모든 96-slot data는 전체 trajectory 검증이다. Counterfactual은 두 global witness 조건만의 비교이므로, 어떤 variant에 대해서도 하루 전체 feasibility나 production 적합성을 주장하지 않는다.

## 과전압 시작 위치의 해석

`OVERVOLTAGE_ONSET_FRONTIERS_ALL_480_SLOTS.csv`는 모든 native slot에서 1.05+1e-9 경계를 아래에서 위로 통과하는 모든 oriented bus-phase link를 기록한다. Witness path의 재진입 crossing도 별도로 저장했다. Source terminal이 이미 threshold보다 약 1e-8 pu 높게 계산되는 경우에는 첫 crossing이 없을 수 있어 source-origin flag를 함께 기록한다. 이 작은 source-terminal 수치와 downstream의 0.0036–0.0209 pu 수준 rise를 구분한다. Hard threshold 자체는 변경하지 않았다.

## 최종 판정과 보존

**Background scaling alone은 원래 21-point grid에서 insufficient하다.** 원본 alpha=0의 Vmax>1.05 사실은 독립적으로 재현됐고 원본 전체 screen도 유지된다. 이는 미시험 continuous alpha 전체에 대한 불가능성 정리가 아니라, 동결된 model·limits·grid에 대한 결과다.

주요 산출물:

- `GLOBAL_WITNESSES.csv`, `GLOBAL_WITNESSES_FULL.json`, `native/alpha_*/Vmax_ROOT_TO_BUS_PATH.csv`, `Vmin_ROOT_TO_BUS_PATH.csv`
- `REGULATOR_BANK_ACCEPTED_TAPS_ALL_480_SLOTS.csv`, `CAPACITOR_BANK_STATES_AND_KVAR_ALL_480_SLOTS.csv`, `SOURCE_VOLTAGES_ALL_480_SLOTS.csv`
- `REGULATOR_UPSTREAM_DOWNSTREAM_AT_WITNESSES.csv`, `WITNESS_PATH_VOLTAGE_INCREMENTS.csv`, `OVERVOLTAGE_ONSET_CLASSIFICATION_AT_WITNESSES.json`
- `COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv`, `PAIRED_COUNTERFACTUAL_DELTAS.csv`, 각 case의 `DIAGNOSTIC_RESULT.json` 및 voltage array
- `DIAGNOSTIC_CONTROL_NONSETTLING_CASES.json`, `INDEPENDENT_ALPHA_ZERO_CONFIRMATION.json`, `ROOT_CAUSE_CLASSIFICATION.json`
- `IMMUTABILITY_FINAL_AUDIT.json`: 이전 source/PCC/topology 및 alpha-screen **2219개 파일**의 SHA256·size·mtime 변경 0
- `FORENSIC_EVIDENCE_FREEZE_MANIFEST.json`와 `.sha256`: 진단 evidence만의 seal. Production parameter authority가 아니다.

AIDC/MESS 규모 변경 0, 24-location/PCC 변경 0, hard voltage/thermal limit 변경 0, production parameter 채택 0, B1/B2/B3 실행 0.
