# Source35 양수 LB 이후 스케줄의 읽기 전용 근거

세 날짜에서 RMP 시간 제한은 전체 알고리즘을 중단하지 않았다. L2·L3의 실제 결과는 status11/Sol0와 `NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN`이며, 원본 호출자는 그 선택에 gain0 기록을 추가한 뒤 `continue`한다. 이후 L4 가격·검증과 UB 작업이 실제로 진행됐다. 이 보고서는 원본 소스와 이미 기록된 호출·선택·인증 파일만 읽고 복사했다. 새로운 solver, 모델, checker replay, 테스트, 프로세스 조회나 운영 변경을 하지 않았다.

| 날짜 | 첫 L1 인증 LB | 저장 선택 수 | 완료 L1/L2/L3/L4 수 | L2/L3 실제 Native 초 |
|---|---:|---:|---|---|
| 2025-05-01 | 0.388959008677 | 44 | 1/1/1/1 | 30.050/30.047 |
| 2025-05-02 | 0.387952576469 | 36 | 1/1/1/1 | 30.054/30.103 |
| 2025-05-03 | 0.139321405834 | 28 | 1/1/1/1 | 30.081/30.059 |

각 날짜 L4는 L1과 **동일한 exact rational LB 및 full-original-dual SHA**를 만들었고 adoptedfalse/gain0이었다. 저장 Frontier의 LB 인증 SHA는 첫 L1이며, 해당 이벤트 CSV에는 양수 LB 개선 이벤트가 하나뿐이다. L4의 MILP 가격 결과도 원본 algorithms171–187에서 exact integer closure를 NOT_PROVEN으로 기록한다. Native OPTIMAL/ObjBound를 새 LB로 승격하지 않는다. 이는 저장 파일의 비교이며 독립 수학 checker를 새로 실행한 결과가 아니다.

원본 `core.py174–193`의 처음8선택은 U1/U2/U3/U4/L1/L2/L3/L4이다. 이후 점수는 각 track 최근3개 인증 gain 합/실제 wall 비용이다. **line184는 L1·L4를 완료 history count<1, L2·L3를 count<2일 때만 eligible로 둔다.** 따라서 첫 L1의 양수 점수가 남아 있어도 재선택할 수 없다. 실제 L2·L3 gain0은 eligible 점수0이다. 다른 eligible 양수 점수가 없으면185–187은 최소 사용 UB만 선택하고,188–190의 주기적 다양화도 UB만 고른다. 실제 세 trace의 pilot 이후 선택은 전부 UB이다. RMP 실패에 따른 전체 abort나 인증값 상실이 아니라, 이 원본 count 제한과 gain/비용 선택이 계속된 결과다.

Source35와36의 관련 원본9파일 SHA 및 원본1007 manifest map은 같다. Source36 `rmp_presolve.py203–224`는 complete same-current P/D와 original/Native-scaled rows/bounds가 literal1e-9 이내일 때 기존 단일30초 RMP 경계의 computationalMethod0만 선택한다. Original budget admission1, cold/ineligible/nonfeasible1, total5400, precision/physics/domain와 후속 코드는 유지된다. RMP는 **feedback_master 호출당 한30초**이지 attempt당 한 호출이 아니다. 실제35는 L2에 Pi가 없어 L3가 다시 RMP를 호출했다.

향후36에서 finite Pi가 나오면 `dw.py99–113`이 row transport 후 원본 부호를 처리하고 정확 dual/convexity packet을 만든다. OPTIMAL이나 SolCount가 이 분기의 조건은 아니며, None만 건너뛰고 {}도 입력으로 진행한다. `m_stage247–251`은 L2에는 RMP dual, L3에는 retained certified dual과의1/8·1/4·1/2 혼합을 기존 가격 호출에 보낸다. `algorithms156–170`의 원본 four45초 unit LP 가격 → selected exact unit dual → independent full signed checker → producer/fullsum 일치 → Frontier strict case/SHA/exact value/bracket 검증이 그대로 필요하다. 실제 강한 인증 개선이 채택됐을 때만 retained authoritative dual이 바뀐다. L2의 추가 missing-column 검증도 RMP objective를 GlobalLB로 만들지 않는다.

L2·L3 첫 pilot 이후 각 track에는 원본상 **최대 한 번의 추가 선택**만 남는다. 양수 certified gain/cost 점수가 생겨야 일반 순위에서 경쟁할 수 있고, UB 다양화·Native reserve(일반LB600/L4 1000)·전체Gap/예산 종료 조건도 적용된다. Pi만 나왔다고 개선이나 추가 선택을 보장하지 않는다. 오류266–270은 전체 루프를 종료할 수 있지만, 이번 관측의 missingPi는245–246의 current-track continue였다. 새로운 무한 LB 반복이나 후속 fullLP continuation은 없다.

파일별 원본 경로·SHA·크기와 소스 line 범위는 JSON과 provenance index에 있다. Native prefix는 이전 fairness audit의 자체 UTC를 보존했으며 현재 Runtime0/최종 Runtime으로 주장하지 않는다. Source36의 실제 usable Pi, 인증 LB 개선, 속도와 finalGlobalGap<=.03/FULL/Actual/Fresh PASS는 본 점검에서 미관측이다.
