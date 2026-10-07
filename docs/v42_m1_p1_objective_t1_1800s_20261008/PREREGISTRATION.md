# 원래 P1 목적함수 복원 + T1 / 1800초 사전 등록

기준은 Draft PR175 exact HEAD `5177d4609783f512b3b9d7e2812bc43b88399674`이다. PR173/175의 zero-objective 치환은 과학적 목적을 보존하지 못했으므로 이번 실행에서 원래 PR162 C3A의 minimize rho를 정확히 복원한다. 기존 기록을 덮어쓰지 않는다.

원본 PR162 Git 객체의 C3A_DATA.npz를 별도 검증기가 독립적으로 읽는다. 파일 SHA256, 목적계수 raw IEEE bytes, ObjCon raw bytes, 변수 축 dtype/shape/bytes를 bit-for-bit 비교한다. Native 모델의 목적 및 ModelSense도 독립 확인한다. signed zero를 정규화하거나 허용오차를 사용하지 않는다. 실제 목적 identity가 실패하면 optimize=0으로 중단한다. 마지막 optimize 직전에도 다시 확인한다.

T1 `rho<=0.5996810901851135`은 추가 제약으로만 남긴다. 전체 원래 C3A 582808행/306040열/9322 binary/296718 continuous, 기존 검증된 364개 컷 및 모든 물리/bounds/types/변수 축을 보존한다. 컷 추가·변경·재생성은 없다. 기존 모델의 목적 관련 필드만 원본으로 복원한다.

TimeLimit=1800, Threads=1, Method=2, NodeMethod=1, Crossover=2, MIPFocus=3, MIPGap=0.005, FeasibilityTol=OptimalityTol=IntFeasTol=1e-8, Seed=20260929, DegenMoves=0. 전체 유효 파라미터를 PR175와 비교하며 로그 저장 경로만 달라야 한다. 기존 모델 이름은 메타데이터 보존을 위해 유지하지만 과학적 목적은 반드시 minimize rho이다.

새 native 모델에서 optimize를 정확히 한 번 실행한다. start/basis/tree/checkpoint를 읽지 않는다. 별도 presolve/추가 solve/MIPFocus=1/sweep/새 컷/Hamming/D-W/B&P/A2/M2/P2/May 실행은 없다. 디스크 토큰과 optimize guard로 재실행을 차단한다.

기존 LB=0.5687116003498334, UB=0.6306505800203936. 전체 모델+T1의 유효 INFEASIBLE만 T1을 LB로 승격한다. 정수 후보는 먼저 모두 저장하고 원래 C3A/route/movement/SOC/PQ/PCS/grid/A1을 독립 검증하여 PASS이며 rho<=T1이면 UB를 갱신한다. TIME_LIMIT에서도 유효 witness가 있으면 UB 갱신이 가능하다. witness/증명 없이 TIME_LIMIT이면 양쪽 bound를 유지한다. T1 추가모델의 native bound는 기록만 하고 전역 LB로 사용하지 않는다.

Presolve/root/barrier/crossover/root-processing 시간, 최초 MIPNODE/nonroot/분기 관측/witness, native incumbent/bound/node 궤적과 RSS를 기록한다. 관측되지 않은 구간은 보간하지 않는다. 공개 API가 제공하지 않는 정확한 분기 시각은 null로 두고 관측 상한과 구분한다. 후보 replay는 목적계수·물리·오차 기준을 수정하거나 해를 보정하지 않는다.

사전 등록 후 단일 1800초 실행만 수행하고 결과를 PR175 위의 새 Draft PR에 저장한 뒤 멈춘다.
