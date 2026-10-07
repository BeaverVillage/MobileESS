# M1 TARGET-RHO T1 / 1800s 사전 등록

기준: Draft PR173 exact HEAD `a47dde78046852a34356cd61e292c6a15845dd46`.
PR173의 원래 C3A 전체 모델, T1 `0.5996810901851135`, 검증된 364개 컷, 변수 범위·물리·목적·허용오차를 그대로 사용한다. 모델 Fingerprint `-2109380076`, 583173행/306040열/5373861 nnz를 요구한다.

유일한 실험 변경은 TimeLimit 600 → 1800초이다. Threads=1, Method=2, NodeMethod=1, Crossover=2, MIPFocus=3, MIPGap=0.005, FeasibilityTol=OptimalityTol=IntFeasTol=1e-8, Seed=20260929, DegenMoves=0. 모든 유효 파라미터를 PR173과 비교하며 로그 저장 경로만 부수적으로 변경한다.

새 gp.Model로 native optimize를 정확히 한 번 호출한다. 기존 해·basis·트리·checkpoint를 공급하지 않는다. 별도 presolve/추가 solve/컷 변경·추가/범위 축소/Hamming/D-W/B&P/추가 threshold/파라미터 sweep은 금지한다. 디스크 단일 실행 토큰과 optimize guard로 재실행을 막는다.

기존 LB=0.5687116003498334, UB=0.6306505800203936. 유효 원래 모델 및 컷의 native INFEASIBLE은 LB=T1. 정수 witness는 전체 원래 C3A 행·범위·정수성과 원래 route/SOC/PQ/PCS/grid/A1을 독립 replay하며 PASS만 후보 UB로 인정한다. TIME_LIMIT/INTERRUPTED는 witness 유무와 관계없이 양쪽 전역 bound를 유지한다. 0 목적의 제한모델 ObjBound는 rho 전역 LB가 아니다.

모든 MIPSOL 벡터를 검증 전에 저장하고 종료 후 중복을 제외한 모든 후보를 검증한다. presolve/root/crossover, 최초 MIPNODE, 분기 관측 증거, 최초 witness, 노드·Work·Runtime·bound/incumbent 궤적 및 RSS를 기록한다. 정확한 분기 시작 시각은 공개 콜백이 제공하지 않으므로 관측 상한과 구분해 null로 기록한다.

기존 coefficient-range 안내는 PR173의 동일 모델·동일 Fingerprint 및 기존 수치 판정 권위에 따라 보존하고, 새로운 수치 경고/오류는 별도 기록한다. Kappa를 얻기 위한 추가 solve는 없다.

이 단일 실행 후 결과와 한국어 검토를 저장하고 PR173 위에 새 Draft PR을 생성한다. 추가 실험은 실행하지 않는다.
