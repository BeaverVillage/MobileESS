# May-04 first-improvement F&O acceptance

**May-04 B1: PASS.** 첫 개선해 탐색과 현재 critical-line 기반 공동 이동 탐색을 적용했습니다. 과학적 feasible set, 전체 MPS, 후보·목적함수·물리 제약은 유지했습니다.

**원인: 탐색군 구성 + 종료 규칙.** 0.0988 GPUh 개선 작업은 기존 두 실행의 P2 부분문제에 전혀 포함되지 않았습니다. 다른 검증된 개선 작업이 포함된 과거 P2 부분문제를 정확한 경계·P1 잠금·시작 해·TimeLimit(60초/5초)로 재현하자, 각각 gap 0.9047%와 1.7884%에서 B0를 반환했습니다. 해당 재현에서는 시간 제한이나 수락 거절이 원인이 아니었습니다.

| 지표 | B0 | 기존 F&O (100% 방문) | 기존 early-stop F&O | 새 first-improvement F&O |
|---|---:|---:|---:|---:|
| P1 | 0.538347519737 | 0.538347519737 | 0.538347519737 | 0.535802697713 |
| P2 | 1604.76193778 | 1604.76193778 | 1604.76193778 | 1550.87922173 |
| P3 | 0 | 0 | 0 | 25 |
| P4 | 0 | 0 | 0 | 10938 |
| P5 | 957282143 | 957282143 | 957282143 | 954860197 |
| 최적화 시간(분; 새 값은 복구 포함 상한) | — | 29.497901 | 18.624656 | 29.586271 |
| 총 경과시간(분; 새 값은 수정·회귀검사 중단 포함) | — | 33.424436 | 21.080793 | 37.823045 |
| 원시 후보 방문률(%) | — | 100 | 46.157565 | 25.698213 |
| 선택 prestart relocation | — | 0 | 0 | 66 |
| 선택 checkpoint migration | — | 0 | 0 | 25 |
| Fresh AC rho | — | 0.53869735 | 0.53869735 | 0.53610664 |
| Actual AC rho | — | 0.54814645 | 0.54814645 | 0.54640532 |

새 B1 − B0 목적값 차이(P1–P5): `[-0.0025448220240326114, -53.88271604938291, 25.0, 10938.0, -2421946.0]`.
P3/P4 증가는 상위 P1/P2 개선에 따른 lexicographic 선택입니다. 모든 목적이 동시에 개선된다는 의미는 아닙니다.
알려진 P2 개선 복구: PASS. P1을 유지하며 P2 1604.7619377782 → 1604.6631723461 GPUh. B0로 시작했고 oracle 해를 warm start로 주입하지 않았습니다.
단일 이동 ΔP1=0.0; pair ΔP1=-0.00135661656817; triple ΔP1=-0.00135661656817; 강한 coupled 진단 ΔP1=-0.00203469445909.
Cross-region 강제 추가 검사는 이미 coupled 개선이 발견되어 실행 조건이 발동하지 않았습니다. 목적지·동일 지역 후보는 계속 유지했습니다.

전체 유효 경로의 수락 개선 수: {'P1': 27, 'P2': 8, 'P3': 0, 'P4': 0, 'P5': 0}. 아래 단계별 표는 복구 실행(first02) 부분만 표시합니다.

| 단계 | 복구 후 개선 수 | 복구 시간(초) | 복구 탐색군 방문률 | 복구 원시 후보 방문률 | 종료 |
|---|---:|---:|---:|---:|---|
| P1 | 1 | 25.10 | 20.00% | 2.72% | STAGE_SOFT_GUARD_REACHED |
| P2 | 0 | 18.43 | 20.00% | 0.26% | STAGE_SOFT_GUARD_REACHED |
| P3 | 0 | 7.11 | 0.00% | 0.00% | STAGE_SOFT_GUARD_REACHED |
| P4 | 0 | 7.15 | 0.00% | 0.00% | STAGE_SOFT_GUARD_REACHED |
| P5 | 0 | 7.36 | 0.00% | 0.00% | POLICY_DAY_HARD_CAP_REACHED |

검증에서 거절한 제안: 14개(실행별 {'first02': 0, 'first01': 14}). 사후 무효화한 수락 1건은 별도입니다. 첫 개선의 기록된 policy-day 계산 예산 시점은 132.29초입니다(빌드·시작 해 검증 포함, 해당 반복의 검증·저장 비용 최종 합산 전).
전체 시도의 단계별 탐색군 방문률: {'P1': 0.4, 'P2': 0.6, 'P3': 1.0, 'P4': 0.2, 'P5': 0.0}. 중단한 시도와 복구 시도의 합집합이며 최종 incumbent 주위의 완전한 sweep 증명은 아닙니다.
전체 원시 후보 3,847,255개를 유지했습니다. 방문률의 분모는 실제 탐색 대상 3,847,248개이며, 차이 7개는 고정 singleton입니다. 미방문 후보는 NOT_VISITED_WITHIN_COMPUTE_BUDGET이며 PRUNED가 아닙니다.
복구 경위: first01의 77번 수락이 당시 현재 P1을 악화시켜 첫 시도의 수락 결과를 무효화했습니다. 원래 제약을 통과한 최선 체크포인트 72번에서 V4로 복구했고, Fresh/Actual은 복구된 최종 결정으로 수행했습니다. 기존 성공 증거는 보존했습니다.
계산 시간은 기록된 합계 28.086분, 중단 시점 미계측 구간의 보수적 90초 여유를 더한 상한 29.586분입니다. 추가 최적화 제한 3분에 모델 재구성·검증도 포함했습니다. 중단 없는 새 방식의 실행 시간은 별도로 측정하지 않았습니다.
선택 migration의 D00 상태 구분: {'RUNNING': 6, 'PENDING': 19}. PENDING의 최초 배치 변경과 RUNNING 상태가 된 뒤 checkpoint 이동을 구분했습니다.
**수치 처리:** P1/P2 개선 조건은 각각 절대 1e-8 / 1e-7, 독립 개선 판정의 noise tolerance는 1e-9 / 1e-8입니다. 검증된 baseline 재계산 noise envelope 1e-10에서 고정한 안전 배수이며, 물리·정수 feasibility tolerance 1e-9와 기존 상위 목적 잠금을 바꾸지 않았습니다.
각 부분문제는 개선 조건을 추가한 상수 목적 feasibility 문제이며 SolutionLimit=1을 사용합니다. Gurobi의 상수 목적 zero-gap 메시지는 P1/P2 최적성 인증이 아닙니다. 기존 solver incumbent를 초기화하고 검증된 incumbent만 시작 값으로 제공합니다. 상위 목적이 다른 단계에서 우연히 개선되어도 그 최신 개선을 되돌리지 못하도록 추가 임시 잠금과 독립 수락 검사를 적용했습니다.
최종 유지한 수락 경로는 독립 job/GPU/rack/WAN/AIDC/grid/P1–P5 재계산, 원래 전체 행 검사, 저장 및 hash/readback을 통과했습니다. 유효하지 않은 제안은 보존·거절하고 이전 incumbent로 계속 탐색합니다.

**물리 검증:** Fresh OpenDSS PASS, Actual replay PASS. Actual 결과는 탐색이나 선택에 사용하지 않았습니다.
**회귀검사:** V4 단위·회귀검사 195개 PASS. 원래 May-04 전체 모델의 알려진 P2 개선 및 P1 공동 이동 회귀검사도 PASS했습니다.
**해석 제한:** 진단에서 RUNNING checkpoint 이후 23시간 대기와 day horizon 밖 서비스 이동이 개선에 기여했습니다. 이는 원래 UID-WAN 규칙에서 가능한 해이며 순수 공간 분산 효과와 동일시하면 안 됩니다. 새 production의 작업별 대기·종료 시간은 JSON `migration_wait_and_service`에 기록했습니다.
진단 중 동일 부분문제에서 더 나은 feasible witness가 앞선 solver bound를 반박한 사례도 보존했습니다. 그 최적성 주장은 철회했으며 이번 생산 결과 역시 전역 최적성으로 주장하지 않습니다.

**전체 5월:** 실행하지 않았습니다. May-04 수락만 완료했으며, 31일/B3 통합 release 재검증과 campaign frozen-release 교체까지 수행한 상태는 아닙니다. 사용자 보류 상태를 유지하고 종료합니다.

근거와 SHA-256은 [JSON 보고서](V41R1_MAY04_FIRST_IMPROVEMENT_ACCEPTANCE.json)에 있습니다.
Solver 사용 근거: [Gurobi feasibility objectives](https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/objectives.html), [SolutionLimit](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#solutionlimit).
