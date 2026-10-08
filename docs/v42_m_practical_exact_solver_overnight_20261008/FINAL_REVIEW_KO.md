# M-stage practical exact solver 야간 최종 검토

**M_EXACT_BB_TRACTABILITY_FAIL**. 최종 유효 LB는 **0.5687116104049206**, UB는 **0.6306505800203936**, 전역 gap은 **9.821440204%**입니다. 원본 C3A/route/SOC/PQ/PCS/grid/A1 incumbent replay 및 모든 OPEN 분할 감사는 PASS입니다. 목표 달성 여부: False. P2 실행: False.

| 지표 | 초기 | 최종 | 변화 |
|---|---:|---:|---:|
| LB | 0.5687116003498334 | 0.5687116104049206 | +1.0055087207305746e-08 |
| UB | 0.6306505800203936 | 0.6306505800203936 | 개선 0 |
| gap | 9.821441799% | 9.821440204% | GLOBAL_BOUND_TRAJECTORY.csv |

## 과학적 권한과 범위

PR177 `b86486a6f58d6c39a1ea4ff2c7e984372b6087a5`에서 분기했으며 PR162 selected C3A의 `minimize rho`를 유지했습니다. objective coefficients/ObjCon/변수 축의 bit identity를 독립 Git blob reader로 검증했습니다. objective hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`. full MILP에는 원본 types/bounds/physics를 유지하고, external LP에는 원본 B relaxation 및 경로에 기록한 0/1 bound fixing만 적용했습니다. T1, 새 cuts, objective 교체, May/A-stage/downstream 실행은 없습니다.

## 단계 결과

- **M0**: 기존 ROOT의 수치 정체를 보존하고 운영자 중단. 기존 OPTIMAL ROOT의 정확한 인증을 재사용하여 새 ROOT 재실행 없이 20개 자식 벤치마크 및 OPEN 후속 탐색 완료.
- **M1**: 600s 기존 canary 반복 없이 Cuts=0/Heuristics=0 native 대조 1회와 external 성능을 비교.
- **M2**: 양쪽 자식, best-bound, 정확한 인증, fixing SHA, checkpoint, crash-safe 복구 및 volatile 독립 감사 캐시를 패키징.
- **M3**: native production 1회가 첫 60분 동안 유효 bound/tree 진전을 보이지 않아 clean stop 후 external로 전환.
- **M4**: 조건부 primal 개입 0회. 노드의 실제 LB 상승 또는 exact fathoming이 없으면 실행하지 않는 등록 gate 적용.
- **M5**: fractional family와 현재 쌍대 row support 분석 후 certified pseudocost/fractionality/dual relevance로 분기 순서 조정. pruning에는 사용하지 않음.
- **M6**: P1 0.5% 목표 및 inherited acceptance가 없으면 P2 실행하지 않음. 원본 energy/count 목적함수와 기존 lock만 사전 준비.
- **M7**: 재시작 가능한 전체 OPEN proof ledger, full original replay, source identity, 독립 감사 CLI 및 exactness fixture 제공.
- **M8**: M_EXACT_BB_TRACTABILITY_FAIL

## Backend 비교

| 실행 | 상태 | Runtime s | Work | nodes | ROOT 누적 s | 첫 nonroot s | peak RSS bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| cuts0_control | 9 | 1800.183 | 3803.525 | 2.0 | 237.75600004196167 | 286.80200004577637 | 2539651072 |
| native_production_initial | 11 | 3603.095 | 7504.217 | 1.0 | 220.43099999427795 | None | 2368479232 |

Native node 수에는 ROOT가 포함됩니다. first branch는 API에서 최초로 관측한 상한 시각이며 정확한 내부 branch 시각으로 주장하지 않습니다. ROOT LP, barrier/crossover/presolve와 first MIPNODE 세부 시각은 각 RESULT.json 및 원본 log에 있습니다. native control의 post-root 정체를 strong-branching/probing으로 단정하지 않습니다.

| 자식 LP 설정 | 시도/OPTIMAL | 중앙값 s | p90 s | raw 행 replay PASS | 최대 raw 행 위반 | LP 목적값−exact 인증 중앙값 |
|---|---:|---:|---:|---:|---:|---:|
| Method2_Crossover0_BarConvTol1e-08 | 53/52 | 197.566 | 275.129 | 1 | 5.334702217063558e-05 | 0.0031157596757308004 |
| Method1_Crossover2_BarConvTol1e-08 | 2/0 | 900.058 | 900.071 | 0 | 58093423973.62045 | None |
| Method2_Crossover0_BarConvTol1e-12 | 1/0 | 190.388 | 190.388 | 0 | 1.1559510193492883e-07 | None |

| external 세션 | LP 호출 | controller wall s | LP 시도/시간 |
|---|---:|---:|---:|
| barrier_accuracy_one_child_result.json | 1 | 337.134 | 10.678 |
| cold_barrier_20node_result.json | 20 | 4937.545 | 14.582 |
| production_tail_1_result.json | 33 | 7443.144 | 15.961 |

위 external wall은 controller loop이며 startup build/첫 restart 감사는 제외합니다. 전체 작업 wall은 아래 자원 항목에 별도로 기록했습니다. Native Runtime 기준 처리율과 wall 기준 처리율을 혼동하지 않습니다. 서로 다른 child fixing domain이므로 paired warm-start 또는 cache speedup을 주장하지 않습니다.

Basis supplied/accepted는 2/2입니다. 두 warm child는 구조적 basis를 수용했지만 TIME_LIMIT와 큰 원본 잔차 및 Kappa 약 1e16 때문에 깨끗한 optimal parent basis로 인정하지 않았습니다. Crossover=0 cold 경로는 basis를 공급하지 않으며 새로운 basis 생성도 주장하지 않습니다. tighter BarConvTol 1회는 SUBOPTIMAL로 끝나 인증을 거부하고 해당 OPEN domain을 원본 byte archive와 함께 cold 경로로 넘겼습니다.

원본 raw primal replay 실패가 있어도 OPTIMAL 이후 sign-clipped exact bounded-Lagrangian 인증은 모든 원본 feasible point에 유효한 하한입니다. LP 목적값이나 infeasible/fractional point는 LB/UB로 사용하지 않았습니다. `CERTIFICATE_LOSS_ATTRIBUTION.json`은 injection_P/Q stationarity 잔차와 넓은 변수 경계가 인증값 손실을 증폭하는 것을 보여줍니다. arithmetic-only injection 등식 보정은 저장된 인증값을 개선했지만 inherited LB를 넘지 않아 production/OPEN에 적용하지 않았습니다.

## 현재 proof 상태와 재시작

`fractional_binaries`는 각 저장된 LP 점의 통계입니다. 특히 Crossover=0 barrier의 interior point를 최적 simplex vertex의 fractionality와 같다고 해석하지 않습니다. 기본 raw LP 잔차가 있는 점에서 큰 fractional count만으로 추가 integrality gap이나 infeasibility를 증명하지 않았습니다.

생성 노드 107, 처리 54, OPEN 54, unresolved OPEN [53]. pruning counts: `{'EXACT_LP_INFEASIBILITY': 0, 'CERTIFIED_LB_AT_LEAST_VALIDATED_UB': 0, 'INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM': 0}`. 양쪽 자식을 모두 유지하고 전역 LB를 모든 OPEN의 최솟값으로 계산합니다. heuristic 분기 점수는 pruning 근거가 아닙니다.

마지막 cold node 53은 고정 게시 예비 시간에 도달한 callback이 종료해 native status **11 (INTERRUPTED)**, Runtime **101.613s**입니다. 이 노드를 native TIME_LIMIT(9)로 바꿔 기록하지 않으며 인증 없이 OPEN에 보존했습니다.

`selected_external_controller.py`와 `OPEN_CHECKPOINT.json`은 실제 OPEN 큐 복구를 지원합니다. `package_audit.py`는 native optimize를 차단하고 원본 배열의 모든 인증/현재 incumbent/fixing-history/SHA를 독립 감사합니다. volatile arithmetic cache는 감사의 동일 수학 입력만 재사용하며 재시작 시 비웁니다. 원래 oracle의 첫 인증 계산은 캐시하지 않습니다. 원본 증명 파일과 모든 입력 hash/replay는 계속 확인합니다. native Gurobi tree는 재시작 가능하다고 주장하지 않습니다.

Primal 개입 0회. restricted neighborhood ObjBound를 전역 LB로 사용한 사례는 없습니다. P2 목적함수 energy→count와 inherited `P1_EPS=1e-7`, `COMPONENT_EPS=1e-8`만 준비했으며 acceptance gate 없이 실행하지 않았습니다.

## 자원, 검증 및 한계

선정된 external 프로세스의 Windows lifetime peak와 완료 receipt의 관측치를 합친 known peak RSS는 **2999205888 bytes**입니다. `OWNED_RESOURCE_MONITOR_RESULT.json`의 PID/creation-time/cwd/script를 결속해 build/LP/replay/audit 구간을 관측했습니다. 과거 종료된 프로세스에서 solve 바깥의 미관측 peak는 사후 복원할 수 없으며, 이 한계를 0으로 표시하지 않습니다.

Native production의 raw derived LB에 CLI 소수 반올림 문제가 있었으나 그 값을 전역 ledger에 채택하지 않았습니다. `DERIVED_GLOBAL_LB_CORRECTION.json`과 독립 감사의 정확한 native ObjBound를 사용합니다. 또 과거 cold-dual receipt의 infinite parameter sentinel 정규화 오류는 원본 checkpoint byte를 보존하고 optimize=0으로 고쳤습니다. 모델이나 수학적 bound를 바꾸는 복구는 아닙니다.

완료 receipt Native Runtime 합계 **23681.525s**, Work 합계 **46878.216**, 완료 receipt peak RSS **2999205888 bytes**. 새 완료 optimize 호출 61. 보고 시점 task wall **28731.708s**. 고정 시작 `2026-10-07T16:53:34.812972+00:00`, deadline `2026-10-08T00:53:34.812972+00:00`. build/replay/audit/Git 게시도 이 한 기한에 포함됩니다.

기존 M0는 야간 시작 전부터 실행되었고 native 최종 status/Runtime/Work가 없어 partial elapsed 및 process CPU/RSS를 `M0_OPERATOR_ABORTED.json`에 별도로 보존했습니다. partial lifetime을 새 완료 Runtime 합계에 더하지 않았습니다. 기존 archived ROOT의 251.318s/481.275 Work 역시 이번 새 실행 비용에서 제외했습니다. 따라서 Runtime 합계는 wall과 같지 않습니다.

9개 fixture 묶음 PASS, 모두 optimize=0. 원본 full replay, 완전한 binary partition, unresolved 보존, exact pruning, deterministic tie, crash 단계별 복구, SHA/fixing/receipt 변조 거부, owned-process 구분, known-witness proof conflict 및 one-bit arithmetic-cache invalidation을 확인했습니다. `PACKAGE_AUDIT.json`과 RESULT.json에 개별 근거가 있습니다.

남은 병목: native는 ROOT 완료 후 실질적인 tree/bound 진전이 없었다. cold barrier는 새 자식 52개를 OPTIMAL로 끝냈지만 중앙값 약 198초와 인증값 손실 중앙값 약 0.0031을 보였고, 원본 injection_P/Q의 stationarity 잔차와 넓은 경계가 그 손실을 주도했다. inherited global floor를 넘는 노드 LB나 exact fathoming이 전혀 없어 gap 9.821440204%가 유지되었다. warm child 2개는 basis가 수용됐어도 큰 잔차/Kappa와 TIME_LIMIT 때문에 속도 개선 근거가 되지 못했다.

선정 설정: 재시작 가능한 external best-bound OPEN 큐와 cold child LP(Method=2, Crossover=0, LPWarmStart=0, BarConvTol=1e-8, Threads=1, 기존 오차/Seed), 원본 행렬에 대한 OPTIMAL 후 exact dyadic bounded-Lagrangian 인증, full incumbent replay, 양쪽 binary 자식 보존 및 crash-safe ledger. 현재는 측정된 후속 조사용 production candidate이며 0.5% 달성에 실용적인 solver로 승인하지 않음.

다음 한 가지 권고: 저장된 OPTIMAL LP 쌍대 벡터에 대해 injection_P/Q와 연결된 PCS 등식 블록의 stationarity 잔차를 함께 보정하고, 원본 목적함수·행렬·경계를 그대로 사용해 exact bounded-Lagrangian 인증이 inherited LB를 넘는지 검사하는 optimize=0 파일럿을 정확히 한 번 사전 등록한다. 이번 작업에서는 실행하지 않는다.

## Git 전달

[Draft PR179](https://github.com/BeaverVillage/MobileESS/pull/179), PR177 위에 stacked. 이 파일의 reporting HEAD는 `f4c3b3248328f4efe76f849dd80852301ba4a973`이며 final commit HEAD·remote match·clean tree는 보고서 commit/push 후 PR 본문과 최종 답변에서 확인합니다. 자체 commit SHA를 자기 파일에 삽입하는 순환을 만들지 않습니다. SHA256_MANIFEST.json은 모든 최종 package 파일의 raw bytes를 결속합니다.
