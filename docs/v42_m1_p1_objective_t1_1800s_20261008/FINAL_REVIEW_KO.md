# 원래 M1 P1 minimize rho 복원 + T1 / 1800초 최종 검토

분류: **P1_ORIGINAL_T1_TIME_LIMIT_NO_VALID_WITNESS**. Native 상태 **TIME_LIMIT**. 요청한 새 native solve를 정확히 한 번 실행했고 이후 추가 실험은 실행하지 않았다.

기준은 Draft PR175 exact HEAD `5177d4609783f512b3b9d7e2812bc43b88399674`이며 실행 소스 커밋은 `3e8f1d19613dd74b29ba7897c2cca8b43f3ba960`이다. 최종 공개 HEAD는 새 Draft PR 본문과 최종 대화에서 확인할 수 있다. PR175 위에 적층하며 기존 증거 파일은 모두 그대로 보존한다.

| 항목 | 기존 | 이번 결과 |
|---|---:|---:|
| 전역 LB | 0.5687116003498334 | 0.5687116003498334 |
| 검증된 UB | 0.6306505800203936 | 0.6306505800203936 |
| 전역 gap | 9.821441799% | 9.821441799% |
| T1 | 0.5996810901851135 | 동일 |
| TimeLimit | 1800초 | 1800초 |
| 과학적 목적 | PR175의 잘못된 zero objective | PR162 원래 minimize rho 복원 |

Runtime=1800.043000초, Work=3350.742200053, NodeCount=1.0, SolCount=0, MIPSOL=0. 원래 모델 replay-PASS witness=False. 저장한 고유 정수 후보는 0개이다. 후보가 존재하면 모두 독립 검증한다. 후보가 없으면 replay는 해당 없음이며 검증 FAIL을 의미하지 않는다.

| 단계/관측 | 초 |
|---|---:|
| Build (native 예산 밖) | 6.928446 |
| Presolve (native 출력) | 15.54 |
| Barrier 완료 누적 시각 (native 출력) | 148.19 |
| Barrier 관측 구간 (콜백 경계 차이) | 121.04899978637695 |
| Crossover (native 출력) | 85.34 |
| Root relaxation (native 출력, barrier/crossover 포함) | 215.95 |
| Root relaxation 완료 시각 | 233.91200017929077 |
| 최초 MIPNODE | 340.25999999046326 |
| 최초 nonroot MIPNODE | None |
| 최초 분기 관측 상한 | None |
| 최초 feasible witness | None |
| Root relaxation 이후 구간 | 1566.130999803543 |
| 관측된 nonroot search 구간 | None |

Root relaxation 완료=True, nonroot 관측=False. Root relaxation 이후 구간에는 root의 MIP 컷·분기 준비 시간이 포함된다. 정확한 분기 시작 시각은 native 공개 콜백에서 노출되지 않아 null로 기록했으며 관측 상한과 구분했다. 콜백이 없는 구간의 Work·노드는 보간하지 않는다. 단계별 경계 차이는 PHASE_LEDGER.json에 저장했으며 native barrier 출력의 148.19초는 누적 시각으로 구분했다. 노드 변화 시각은 NODE_PROGRESSION.json, 콜백 관측 시 5초/노드 변화 궤적은 BOUND_NODE_TRAJECTORY.csv, incumbent의 모든 벡터·이벤트는 INCUMBENT_TRACE.csv와 CANDIDATE_REPLAYS.json에 보존했다.

2초 간격 native solve 관측 peak RSS=2664677376 bytes. Build/replay를 포함한 전체 관측 peak RSS=2664677376 bytes (2.481674 GiB), Windows lifetime peak working set=2732593152 bytes. Native root/barrier/crossover 원문은 NATIVE_SOLVER.log와 ROOT_TIMELINE.json에 보존한다.

전체 모델 583173행/306040열/5373861 nnz, binary 9322/continuous 296718, 원래 C3A 582808행과 기존 검증된 364개 컷, 새 Fingerprint 614298284이다. 목적 복원으로 Fingerprint가 바뀌었으며 행렬·변수 범위·타입·기존 컷·T1은 PR175와 동일하다. 원래 행렬·bounds·types를 동일성으로 검사했고 목적계수·ObjCon·변수 축은 PR162 Git 객체를 별도 검증기로 bit-for-bit 비교했다. Objective identity=True, objective SHA256=`0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`, variable-axis SHA256=`a9613e108820333920047d0bacc98fa34690db8c83a5d099a870e22e213ddf8a`, ObjCon bits=`0000000000000000`이다. 전체 유효 파라미터에서 출력 로그 경로만 다르다. TimeLimit과 모든 과학적 solver 설정은 PR175와 동일하다. MIP start/basis/checkpoint/tree를 공급하지 않았고 새 모델에서 시작했다. Hamming/추가 threshold/컷 변경·추가/파라미터 sweep/별도 presolve는 없다.

기존 coefficient-range 안내는 동일 행렬·bounds와 기존 수치 판정 권위에 따라 기록했다. 새 수치 경고/오류는 NUMERICAL_AUTHORITY.json에서 별도로 구분한다. T1 추가모델의 원래 목적 native ObjBound=0.5687116103665997는 rho의 전역 LB로 사용하지 않았다. TIME_LIMIT에서 유효 원래 모델 witness나 불가능 증명이 없으면 양쪽 bound를 유지한다. TIME_LIMIT에서도 원래 전체 모델 replay-PASS 정수 witness이며 rho<=T1이면 UB를 갱신할 수 있다. INFEASIBLE의 LB 승격에는 원래 전체 영역·모델·컷·수치 권위가 모두 PASS여야 하며, feasible UB에는 원래 C3A 및 route/movement/SOC/PQ/PCS/grid/A1 독립 replay PASS가 필요하다.

PR175 비교: Runtime 1800.032000 → 1800.043000초, Work 3258.255542082 → 3350.742200053, 노드 1.0 → 1.0, 정수 해 0 → 0. 기존 root 완료 240.89100003242493초 → 이번 233.91200017929077. Crossover 187.2 → 85.34초, 최초 MIPNODE 326.78200006484985 → 340.25999999046326초. 비교 원문은 VS_PR175_ZERO_OBJECTIVE.json에 저장한다. 기존 zero-objective 실행은 원래 과학적 목적을 보존하지 못한 기록으로 남기며 이를 올바른 P1 목적 실행이라고 해석하지 않는다.

요청한 단일 1800초 실행을 마쳤다. 추가 solve나 MIPFocus=1, May/A2/M2/P2 실험은 실행하지 않는다.

Draft PR: [#177](https://github.com/BeaverVillage/MobileESS/pull/177), PR175 위에 적층. 최종 40자리 HEAD는 PR 본문의 `Final HEAD`와 최종 대화에 기록한다.
