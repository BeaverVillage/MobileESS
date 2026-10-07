# May12 B1 A1 P1 ROOT LP 읽기 전용 진단

**최종 분류: INCONCLUSIVE.** 지연된 단계는 확정했지만, LP 퇴화·수치 조건·날짜별 LP 기하 중 하나를 유일한 원인으로 확정할 저장 자료는 없다.

완료 campaign `B1_PR134_SC_202505_20261006T183422_4fb25507`의 May12가 대상이다. 실행 소스 `b99f2778e47f8bfee22b4eb54f14af8eb9a2e3d1`, scientific SHA `8c1173caca09b9c32707b9f8a4ff38e4998ffb90926dd7f22595e24ea58b28eb`, 입력 SHA `3ae2b544ae510aeaba3176e56b4c717eb65f219df1550608a2048075d65c35d6`, 압축 matrix SHA `1ff8d61ffd774554facc0d529f1e875d07224ca21bb5d326053345bb23a1e222`를 고정했다. 기준 작업 트리의 publish 커밋은 `67a352b1145410c6def8129cffcc10abf1b17adb`다. 과거 PR150/PR151 실패 모델과 혼동하지 않았다.

May11·May13을 필수 비교하고, 나머지 PASS 중 May12 이상의 nnz를 가진 가장 작은 모델 May20과 가장 큰 모델 May01을 추가했다. May10·May17·May19의 stage/input/model은 읽거나 실행하지 않았다. 별도 May17/May19 복구 작업과 독립 작업 트리에서 병행했고, campaign·복구 파일을 변경하지 않았다.

## 1. 3,600초가 소진된 단계

| 단계 | native 예산 안 소요 시간 | 근거 |
|---|---:|---|
| BUILD | 0초 | worker의 사전 domain/build/compression/verification/materialization 약 329.02초는 native 3600초 바깥 |
| PRESOLVE | 31.58초 | 기존 native log |
| ROOT SIMPLEX | 3562.46초 | dual simplex, Method=1 |
| ROOT BARRIER | 0초 | 실행 흔적 없음, Method=1 |
| CROSSOVER | 0초 | 실행 흔적 없음 |
| OTHER | 6.085초 | Runtime에서 presolve/root를 뺀 잔여값; 초기화·종료 내부 분할은 미기록 |
| 합계 | 3600.125초 | native receipt |

root에 native Runtime의 **98.95%**를 사용했다. 초기 식 구축은 119.35초, exact compression은 74.97초로 별도 기록돼 있으나 사전 약 329초 전체의 세부 분할은 모두 남아 있지 않다. callback 6.26초는 native 시간에 포함되므로 더하지 않았다. native 출력은 0.01초 정밀도, worker/telemetry 정렬은 약 1초 정밀도다.

## 2. 같은 campaign의 크기와 root 비교

| 날짜 | modeled jobs | 압축 rows / cols / nnz | presolved rows / cols / nnz | presolve 초 | root 초 / 반복 / Work |
|---|---:|---|---|---:|---|
| 2025-05-11 | 3,144 | 532,312 / 333,045 / 5,489,960 | 327,767 / 263,111 / 1,350,496 | 3.85 | 238.44 / 182,399 / 477.05 |
| 2025-05-12 | 1,782 | 3,040,170 / 2,669,123 / 17,558,423 | 2,745,448 / 2,583,727 / 11,396,870 | 31.58 | 3562.46 / 885,048 / 4936.57 |
| 2025-05-13 | 1,220 | 7,030,012 / 6,236,718 / 37,307,447 | 6,543,182 / 6,069,985 / 26,932,202 | 55.42 | 14.35 / 14,229 / 33.59 |
| 2025-05-20 | 783 | 3,853,688 / 3,443,304 / 23,255,427 | 3,553,856 / 3,339,932 / 15,113,652 | 40.90 | 22.14 / 38,393 / 47.32 |
| 2025-05-01 | 1,499 | 7,828,869 / 6,852,953 / 42,419,133 | 7,239,861 / 6,658,798 / 31,474,154 | 69.49 | 30.44 / 22,684 / 51.72 |

May12 raw(압축 전) 3,703,395행/2,708,445열/26,985,809 nnz, 압축 solver 입력 3,040,170행/2,669,123열/17,558,423 nnz다. Presolved는 2,745,448행/2,583,727열/11,396,870 nnz다. May13·May20·May01은 이 세 단계 모두 더 크고 root 완료는 훨씬 빠르다. 상세 binary/continuous/other integer, 제거 수, 범위와 memory는 CSV에 있다. Native presolve는 추가 integrality를 추론했으며 그 type 변화를 원래 formulation 수정으로 해석하지 않았다.

## 3. 가족별 구조와 압축 인증

| 압축 계열 | May11 rows / cols | May12 rows / cols | May13 rows / cols | May20 rows / cols | May01 rows / cols |
|---|---|---|---|---|---|
| job_time_resource | 94,377 / 144,792 | 1,050,784 / 1,595,700 | 2,434,602 / 3,714,107 | 1,358,577 / 2,082,918 | 2,761,068 / 4,100,286 |
| migration | 92,527 / 91,206 | 588,394 / 595,567 | 1,403,661 / 1,389,632 | 735,966 / 735,430 | 1,503,133 / 1,481,411 |
| WAN_flow_state | 194,940 / 68,473 | 1,242,976 / 440,702 | 2,999,130 / 1,060,990 | 1,569,243 / 555,460 | 3,367,267 / 1,194,626 |
| Runtime | 12,229 / 13,381 | 21,649 / 22,801 | 56,566 / 57,718 | 54,044 / 55,196 | 60,448 / 61,600 |
| CC4 | 10,896 / 9,552 | 10,896 / 9,552 | 10,896 / 9,552 | 10,896 / 9,552 | 10,896 / 9,552 |
| rack_GPU_gang | 4,488 / 3,336 | 3,648 / 2,496 | 3,564 / 2,414 | 3,565 / 2,443 | 4,325 / 3,173 |
| grid | 122,855 / 1 | 121,823 / 1 | 121,593 / 1 | 121,397 / 1 | 121,732 / 1 |
| global_other | 0 / 2,304 | 0 / 2,304 | 0 / 2,304 | 0 / 2,304 | 0 / 2,304 |

May12에서 May11 대비 가장 커진 주 블록은 job/time/resource다(열 144,792→1,595,700, 약 11.02배). WAN 열도 68,473→440,702, 약 6.44배 증가했다. 하지만 더 큰 PASS 날짜의 같은 블록은 모두 더 크므로 **May12만의 job/WAN state explosion은 확인되지 않았다**. CC4는 같은 9,552열, grid 행도 약 12.1만행으로 공통적이다. Runtime·rack/GPU/gang은 별도 계수했고 anonymous global helper 2,304열은 남겨 명시했다. Shift/prestart는 별도 disjoint P1 행 계열이 아니라 y/상태 도메인과 뒤쪽 목적에 공유되므로 별도 window/domain 기록으로 비교하고 이중 집계하지 않았다.

May12에서는 alias 38,090열, fixed-zero 1,232열, bound-safe 568,158행, duplicate 26,412행, proportional-dominated 68,655행, resource-bound 4,832건의 기존 인증이 있다. 총 663,225행 제거 및 FULL_LP 동치성은 기존 독립 verifier PASS다. 저장된 grid·WAN·job·약한 경계가 더 큰 PASS보다 특별히 많다는 증거가 없다. Native presolved family/uncrush mapping은 저장되지 않아 원래/압축 family를 presolved family로 추정하지 않았다.

일부 날짜의 variable-family 코드에는 uint16보다 큰 이름 사전이 있어 단순 디코딩을 신뢰할 수 없었다. 진단에서는 저장된 scientific interface의 first-seen ownership을 독립 재구성하고 기존 native family count와 맞춘 뒤 exact compressed roots mapping으로 옮겼다. Row-family 코드는 작은 사전이라 온전히 사용했다. 이 메타데이터 문제를 수정하거나 scientific matrix 변경의 증거로 간주하지 않았다.

## 4. LP 진행·퇴화·수치 조건

May12는 root 885,048 반복, 4,936.57 Work로 종료됐고 마지막 출력에서 primal infeasibility 16,273.7, dual infeasibility 0이었다. 출력 objective는 0.63199057→0.66711771로 계속 바뀌었으며 동일 printed objective interval은 0개였다. 따라서 ‘로그에 objective가 완전히 멈췄다’거나 ‘degenerate pivot 개수를 측정했다’고 주장하지 않는다. Primal feasibility를 확보하지 못한 dual-simplex 수렴 병목은 확정이다. 로그의 미완료 root objective는 valid LB로 승격하지 않았고 native receipt LB 0.6316300882361616을 구분했다.

May12의 압축 matrix coefficient 절댓값 범위는 약 1.004e-13~76,293.9453, RHS는 약 8.406e-8~1,064,300.5371이다. 큰 coefficient range warning은 다섯 날짜 모두 공통이고 May11·May13·May01의 최대 coefficient는 약 305,175.7813으로 더 크다. Numerical failure, Markowitz/refactorization 또는 barrier/crossover warning은 기존 P1 log에서 찾지 못했다. Kappa/KappaExact·root RC·root X/basis는 미기록이다. Native presolved matrix/attributes가 없어 presolved coefficient/RHS/bound 범위는 계산할 수 없다. 기존 receipt의 FeasibilityTol=1e-6, OptimalityTol=1e-6, IntFeasTol=1e-5, NumericFocus=0을 그대로 기록했다.

목적계수는 rho 한 열에만 있고 나머지 99.99996253%는 0이다. rho는 121,607개 retained 행에 연결되며 upper-unbounded 열은 9,408개, 완전히 free인 열은 0이다. 같은 zero-objective 구조·약한 상한·고연결 rho는 PASS 날짜에도 있다. Root at-bound 비율과 zero RC 비율은 계산 불가이며, 저장된 PASS P1 integer incumbent at-bound 비율은 root basis 대용으로 쓰지 않았다. 2,876개 deterministic family-row 표본에서 exact duplicate는 0, 동일 LHS는 164개, 같은 support의 near-parallel pair는 444개였다. 이 표본과 단위 의존 cosine으로 전체 redundancy나 퇴화를 확정하지 않았다.

## 5. 자원과 시작해

May12 P1 구간 RSS peak 8.42 GiB, 최소 가용 RAM 12.24 GiB, CPU/wall 비 0.970(한 코어 기준)였다. Guard·인위 감속은 없었다. Paging/hard-fault/process-commit/system-commit counters는 저장되지 않아 paging의 절대적 부재를 증명하지는 않았다. 더 큰 PASS의 RAM pressure가 더 높았다는 관찰과 함께, May12의 resource pressure를 주원인으로 지지할 자료는 없다.

May12에는 authoritative B0 common reference 입력이 있었지만, 원래/압축 native 전 행을 검증한 B0/B1 MIP-start vector는 date output에 없다. BUILD_RECEIPT의 old_start_loaded=false, frozen source의 P1 전 Start/read-start 작업 없음, native start message 없음이 일치한다. 실제 supplied/accepted start는 둘 다 false다. 다른 PASS 날짜도 P1 start 없이 root를 완료했으므로 missing start만을 root timeout의 원인으로 선택하지 않았다. 공통 reference의 존재를 full native feasible start 존재로 바꾸어 말하지 않았다.

## 6. 결론과 다음 실험 하나

**확정:** native 예산의 98.95%가 ROOT dual simplex에서 소진됐고 root가 primal feasible LP 해를 완성하지 못했다. BUILD·presolve·barrier·crossover·단순 크기 폭증은 주 병목이 아니다. **미확정:** root basis/RC/Kappa와 paging 부재 때문에 LP 퇴화·날짜별 약한 LP 기하·conditioning 중 하나를 유일한 기제로 식별할 수 없다. 최종 분류는 INCONCLUSIVE로 둔다. TIMEOUT을 수학적 infeasibility로 해석하지 않는다.

**권고하는 실험은 하나:** frozen May12 P1 matrix/input/source를 그대로 사용하고 **Method만 1→2로 바꾼 단일 root-only 3,600초 실행**(NodeLimit=1, Threads=1, 기존 Crossover·나머지 parameter·tolerance 유지). Barrier/crossover phase별 시간·Work·완료 여부와 가능하면 root basis/RC를 기록해 dual simplex 특이적 병목인지 판별한다. Start 주입, formulation 변경, 뒤쪽 목적이나 다른 날짜 실행, sweep은 포함하지 않는다. **이번 작업에서는 실행하지 않았다.**

## 7. 진단 무변경 검증

저장 행렬·로그·입력·인증서만 읽었다. 새 native model build·presolve·optimize는 모두 0회다. 진단 코드에서 gurobipy 및 production module import를 fail-closed로 차단했고 AST로 optimizer/model API 호출 부재를 검사했다. 참조 파일 SHA256 전후 불변, 제외 날짜의 stage/input/model 접근 0, output namespace 격리를 별도 검증했다.
