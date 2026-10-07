# M1 TARGET-RHO T1 / 1800초 최종 검토

분류: **TARGET_RHO_T1_1800_TIME_LIMIT_INCONCLUSIVE**. Native 상태 **TIME_LIMIT**. 요청한 새 native solve를 정확히 한 번 실행했고 이후 추가 실험은 실행하지 않았다.

기준은 Draft PR173 exact HEAD `a47dde78046852a34356cd61e292c6a15845dd46`이며 실행 소스 커밋은 `e8445a90834337c74db6cae3d0b871c8d5b51f01`이다. 최종 공개 HEAD는 새 Draft PR 본문과 최종 대화에서 확인할 수 있다. PR173 위에 적층하며 기존 증거 파일은 모두 그대로 보존한다.

| 항목 | 기존 | 이번 결과 |
|---|---:|---:|
| 전역 LB | 0.5687116003498334 | 0.5687116003498334 |
| 검증된 UB | 0.6306505800203936 | 0.6306505800203936 |
| 전역 gap | 9.821441799% | 9.821441799% |
| T1 | 0.5996810901851135 | 동일 |
| TimeLimit | 600초 | 1800초 |

Runtime=1800.032000초, Work=3258.255542082, NodeCount=1.0, SolCount=0, MIPSOL=0. 원래 모델 replay-PASS witness=False. 저장한 고유 정수 후보는 0개이다. 후보가 존재하면 모두 독립 검증한다. 후보가 없으면 replay는 해당 없음이며 검증 FAIL을 의미하지 않는다.

| 단계/관측 | 초 |
|---|---:|
| Build (native 예산 밖) | 4.220792 |
| Presolve (native 출력) | 10.78 |
| Barrier 완료 누적 시각 (native 출력) | 53.36 |
| Barrier 관측 구간 (콜백 경계 차이) | 36.53200006484985 |
| Crossover (native 출력) | 187.2 |
| Root relaxation (native 출력, barrier/crossover 포함) | 228.39 |
| Root relaxation 완료 시각 | 240.89100003242493 |
| 최초 MIPNODE | 326.78200006484985 |
| 최초 nonroot MIPNODE | None |
| 최초 분기 관측 상한 | None |
| 최초 feasible witness | None |
| Root relaxation 이후 구간 | 1559.141000032425 |
| 관측된 nonroot search 구간 | None |

Root relaxation 완료=True, nonroot 관측=False. Root relaxation 이후 구간에는 root의 MIP 컷·분기 준비 시간이 포함된다. 정확한 분기 시작 시각은 native 공개 콜백에서 노출되지 않아 null로 기록했으며 관측 상한과 구분했다. 콜백이 없는 구간의 Work·노드는 보간하지 않는다. 단계별 경계 차이는 PHASE_LEDGER.json에 저장했으며 native barrier 출력의 53.36초는 누적 시각으로 구분했다. 노드 변화 시각은 NODE_PROGRESSION.json, 콜백 관측 시 5초/노드 변화 궤적은 BOUND_NODE_TRAJECTORY.csv, incumbent의 모든 벡터·이벤트는 INCUMBENT_TRACE.csv와 CANDIDATE_REPLAYS.json에 보존했다.

2초 간격 native solve 관측 peak RSS=2631491584 bytes. Build/replay를 포함한 전체 관측 peak RSS=2631491584 bytes (2.450768 GiB), Windows lifetime peak working set=2741751808 bytes. Native root/barrier/crossover 원문은 NATIVE_SOLVER.log와 ROOT_TIMELINE.json에 보존한다.

전체 모델 583173행/306040열/5373861 nnz, binary 9322/continuous 296718, 원래 C3A 582808행과 기존 검증된 364개 컷, Fingerprint -2109380076이 PR173과 동일하다. 원래 행렬·bounds·types·zero objective·ObjCon을 비트 동일성으로 검사했다. 전체 유효 파라미터에서 TimeLimit과 출력 로그 경로만 다르다. MIP start/basis/checkpoint/tree를 공급하지 않았고 새 모델에서 시작했다. Hamming/추가 threshold/컷 변경·추가/파라미터 sweep/별도 presolve는 없다.

기존 coefficient-range 안내는 PR173의 동일 모델과 동일 수치 판정 권위에 따라 기록했다. 새 수치 경고/오류는 NUMERICAL_AUTHORITY.json에서 별도로 구분한다. Native zero-objective ObjBound=0.0는 rho의 전역 LB로 사용하지 않았다. TIME_LIMIT/INTERRUPTED는 정수 후보 유무와 관계없이 양쪽 bound를 유지한다. INFEASIBLE의 LB 승격에는 원래 전체 영역·모델·컷·수치 권위가 모두 PASS여야 하며, feasible UB에는 원래 C3A 및 route/movement/SOC/PQ/PCS/grid/A1 독립 replay PASS가 필요하다.

요청한 단일 1800초 실행을 마쳤다. 추가 solve나 MIPFocus=1, May/A2/M2/P2 실험은 실행하지 않는다.

Draft PR: [#175](https://github.com/BeaverVillage/MobileESS/pull/175), PR173 위에 적층. 최종 40자리 HEAD는 PR 본문의 `Final HEAD`와 최종 대화에 기록한다.
