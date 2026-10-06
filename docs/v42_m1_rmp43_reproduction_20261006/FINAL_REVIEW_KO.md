# RMP43 equivalent one-shot reproduction

EXACT_DUAL_AUTHORITY_PASS=false. 초기 재현 1회와 허용된 동일 RMP 재검증 1회를 실행했다. 600초 early-B&P는 실행하지 않았다.

Last valid RMP42 point/dual SHA와 1,841컬럼의 file/column SHA를 확인했다. 모델은 679,959행, 83,058변수, 7,514,086 비영 계수, fingerprint 0xf6cbcc5d이다. 두 실행의 최종 CSR, 행/변수 축, RHS, sense, bounds, objective, constant와 solver settings가 모두 동일하다. 초기 wrapper의 signed/unsigned fingerprint 비교 실패는 native 호출 전에 수정되었다.

두 실행에서 sign gate 전에 terminal primal X, raw Pi, native RC, 전체 CSR, row-axis SHA, sense, +1 scaling vector, lower/upper bound-dual decomposition, 지원 bound 항, primal/dual 목적값 availability를 저장했다. 선택된 무한 supporting bound에 비영 RC가 있어 finite dual objective는 null로 명시했다. 무한 항을 0으로 치환하지 않았다. BarPi/BarX도 저장했지만 terminal X/Pi/RC와 혼합하지 않았다.

최초 실패는 native 행 248399 / c454461 / original family transformer_kVA / sense <= / raw Pi +4.760779460063163e-11 이다. 기대 부호는 nonpositive이고 변환은 정확히 +1이다. 즉 행 반전/정규화/축 불일치/BarPi 혼합 문제가 아니다. Native terminal dual-cone 수치 불일치이며, 로그의 barrier Numerical trouble -> crossover Numeric-to-Optimal과 함께 확인했다. Gurobi 내부 연산의 구체적인 결함까지 증명한 것은 아니다.

재검증은 incremental column insertions 대신 저장된 최종 CSR을 native 모델로 한 번에 운반했다. 이 동등한 representation 변경은 native 수치 오류가 해결되었다는 증명이 아니다. solver setting이나 tolerances는 변경하지 않았고 새 snapshot에도 같은 실패가 남았다. 추가 재시도는 하지 않았다.

1,841컬럼 각각 및 전체 83,058변수 reduced-cost identity는 두 실행 모두 PASS이다. Primal feasibility와 snapshot/axis identity도 PASS이다. Strict row-sign 및 infinite-bound support를 포함한 strong-duality authority는 FAIL이다. 기존 승인된 RMP36의 same-dual corrected-bound rational arithmetic은 PASS로 재구성했으나 그 pricing bounds를 새 Pi에 섞지 않았다. 새 RMP43 full-domain bound를 인증하지 않았다. Inherited valid root LB 0.5687115725336208은 보존했고 restricted LP를 integer UB로 쓰지 않았다.

초기 Model.Runtime: 104.316000s. 재검증 Model.Runtime: 104.879000s. 두 native objective: 0.5729386154943963, 0.5729386154943963. 과거 RMP43와 39,300 simplex iterations / 126.13 work units 경로가 재현되었다. 벽시계 차이를 algorithm speedup/slowdown 근거로 사용하지 않았다.

기존 PR155 974개 파일은 byte-for-byte 보존했다. 메모리 기반 중단/대기/kill/parameter 변경은 없다. root CG continuation, additional pricing, 7200초 B&P, P2, sign gate 우회/완화는 모두 0회다.

상세 수치: INDEPENDENT_FINAL_AUDIT.json. 최초/재검증 원시 증거: RMP43_TERMINAL_BEFORE_GATE.npz / RMP43_REVALIDATION_BEFORE_GATE.npz. 이 결과는 안정적 numerical solver 경로의 추가 수정을 검증해야 함을 보여주며, 현재 같은 설정에서 accepted exact dual은 확보되지 않았다.
