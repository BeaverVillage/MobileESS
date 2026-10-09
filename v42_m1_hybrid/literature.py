"""Primary-source reading receipts and scoped fast-hybrid applicability notes.

This module writes only the new literature review; it never fetches code,
imports historical failed solvers, runs Native, or licenses a pruning rule.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'docs/v42_m1_fast_hybrid_20261008'

SOURCES=(
    dict(key='DW1960',authors='G. B. Dantzig; P. Wolfe',year=1960,
         title='Decomposition Principle for Linear Programs',
         url='https://pubsonline.informs.org/doi/10.1287/opre.8.1.101',
         primary=True,scope='Original decomposition paper: block subproblems and coordinating program.'),
    dict(key='LD2005',authors='M. E. Lübbecke; J. Desrosiers',year=2005,
         title='Selected Topics in Column Generation',
         url='https://pubsonline.informs.org/doi/abs/10.1287/opre.1050.0234',
         primary=True,scope='Authors survey: dual viewpoint, restricted master and pricing.'),
    dict(key='BADF2009',authors='H. Ben Amor; J. Desrosiers; A. Frangioni',year=2009,
         title='On the Choice of Explicit Stabilizing Terms in Column Generation',
         url='https://arpi.unipi.it/retrieve/e0d6c92c-d34e-fcf8-e053-d805fe0aa794/StabCG.pdf',
         primary=True,scope='Author institutional postprint: stabilization, dual feasibility, complete pricing.'),
    dict(key='ID2005',authors='S. Irnich; G. Desaulniers',year=2005,
         title='Shortest Path Problems with Resource Constraints',
         url='https://www.gerad.ca/en/papers/G-2004-11',
         primary=True,scope='Author research report, revised July2004; Springer chapter2005. Resource-constrained path modeling and methods.'),
    dict(key='RS2006',authors='G. Righini; M. Salani',year=2006,
         title='Symmetry helps: Bounded bi-directional dynamic programming for the elementary shortest path problem with resource constraints',
         url='https://transp-or.epfl.ch/academic/SALANI.html',
         primary=True,scope='Author institutional publication record and abstract: bounded bidirectional dynamic programming.'),
    dict(key='IDDD2010',authors='S. Irnich; G. Desaulniers; J. Desrosiers; A. Hadjar',year=2010,
         title='Path-Reduced Costs for Eliminating Arcs in Routing and Scheduling',
         url='https://pubsonline.informs.org/doi/10.1287/ijoc.1090.0341',
         primary=True,scope='Original paper, online2009/volume2010: path reduced costs and bidirectional arc elimination preserving optimality.'),
    dict(key='GUROBI_STATUS',authors='Gurobi Optimization',year=2026,
         title='Optimization Status Codes',
         url='https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/statuscodes.html',
         primary=True,scope='Official documentation: TIME_LIMIT means a time cap was exceeded, OPTIMAL is subject to tolerances.'),
)


TEXT='''# V42 M1 fast-hybrid 문헌 검토 및 적용 계약

이번 적용 판단은 May01 1,499-job/4차량/96슬롯, 동일 C3A 물리 문제를 대상으로 한 연구 설계다. 문헌이 이 사례의 속도 향상이나 5% Gap을 증명한 것은 아니다. 신규 Native 호출 0이며, 과거 과학적 판정과 production 설정을 변경하지 않는다.

## 분해와 전역 bound

Dantzig–Wolfe 원 논문은 부분 문제의 해를 열로 만들고 coordinating program으로 연결하는 구조를 제시한다. [Dantzig–Wolfe1960](https://pubsonline.informs.org/doi/10.1287/opre.8.1.101)

Dual 관점에서 restricted master와 pricing을 구분하는 것이 핵심이다. 제한된 trajectory 집합의 master를 푸는 것만으로 모든 원본 열에 대한 dual feasibility가 확보되지 않는다. [Lübbecke–Desrosiers2005](https://pubsonline.informs.org/doi/abs/10.1287/opre.1050.0234)

V42 적용 판단: 원래 CSR을 네 차량의 모든 시간대 물리 block, pure nonunit grid block, mixed coupling rows로 정확히 분할한다. 각 원본 행과 열이 한 번씩 포함되고 bounds/types/RHS/계수가 보존되어야 한다. 가격 λ와 local LP dual을 original global row multiplier로 재조립한 뒤 `ObjCon + bᵀy + min_box((c−Aᵀy)ᵀx)`를 exact rational로 독립 계산하면, pricing 종료 여부와 별개로 모든 원본 정수 운전에 유효한 LB를 얻는다. Native 가격 objective의 반올림은 이 증명에 사용하지 않는다.

이 LP dual bound는 compact LP의 정수성 손실을 제거했다는 증거가 아니다. MILP pricing incumbent는 trajectory 후보이고 Native MILP ObjBound는 exact 증명이 아니다. 정수 block convex hull을 쓰는 DW bound에는 전체 정수 block의 missing-column lower bound/완전 pricing 증명이 추가로 필요하다. 작은 catalog나 fractional ROOT 제외는 이를 대신하지 않는다.

## 안정화

Ben Amor·Desrosiers·Frangioni는 dual 안정화 항의 형태·파라미터와 초기 dual 추정 품질이 column generation의 불안정성 및 성능에 영향을 준다고 연구했다. 논문의 restricted dual도 missing columns의 제약을 만족하는지 pricing으로 확인한다. [기관 보관 원문](https://arpi.unipi.it/retrieve/e0d6c92c-d34e-fcf8-e053-d805fe0aa794/StabCG.pdf)

V42 적용 판단: 이전에 독립 검증된 signed grid multipliers를 가격 중심으로 사용하고 제한된 업데이트/convex mixing을 시도할 수 있다. 후보 가격마다 inequality sign과 exact bound를 다시 검사한다. 안정화 penalty나 제한된 master 값은 원래 `min rho_max` objective에 더하지 않는다. 새로운 가격이 실제 인증 LB를 개선했는지와 단순 numerical certificate loss가 줄었는지를 별도로 기록한다. 안정화는 5% 목표 달성 보장이 아니다.

## 자원 경로, dominance 및 양방향 bound

Irnich·Desaulniers는 resource-constrained shortest-path의 자원 모델과 해법을 분류한다. Righini·Salani는 차량 경로 pricing에서 bounded bidirectional dynamic programming을 제안하고 평가했다. [Irnich–Desaulniers 원 연구보고](https://www.gerad.ca/en/papers/G-2004-11), [Righini–Salani 저자 자료](https://transp-or.epfl.ch/academic/SALANI.html)

Path-reduced costs 논문은 최적성을 해치지 않는 arc 제거를 위해 양방향 탐색으로 계산한 경로 reduced cost를 사용한다. 이것은 비용순으로 임의의 k개 route를 남기는 규칙과 다르다. [Irnich 외 원 논문](https://pubsonline.informs.org/doi/10.1287/ijoc.1090.0341)

V42 적용 판단: forward/backward relaxation의 값이 남은 모든 연장 경로 비용의 **하한**임을 증명한 경우에만 reduced-cost pruning에 사용한다. 각 label은 같은 차량·지점·시간·접속 가능 상태와 SOC 자원, terminal SOC 도달 조건, 충방전 mode 및 연속 P/Q feasible region을 표현해야 한다. 이동·connection 동안 P/Q=0, 이동 에너지, PCS16, 초기/terminal SOC와 96슬롯 전체 연결을 보존한다. 대기·충전·방전이 SOC를 양방향으로 바꾸고 상한과 terminal equality가 있으므로, 단순히 SOC가 높다는 이유로 다른 label을 지배한다고 판단하지 않는다.

안전 dominance의 충분조건은 제거되는 label의 모든 가능한 연장에 대해 살아남는 label에 자원/연속 P/Q feasible continuation이 존재하고 가격 비용이 더 크지 않다는 증명이다. 이러한 inclusion/extension 정리가 없다면 label을 유지한다. 이 사례의 일반적인 SOC bucket, ε rounding, 시간별 P/Q 대표점, top-k trajectory prescreen은 **NOT_PROVEN**이며 전역 pricing oracle로 채택하지 않는다.

후보 catalog의 sparsification은 UB 휴리스틱/제한 master 작업량 감소에만 쓸 수 있다. 전역 LB에는 원본 route 전체에 대한 complete pricing 또는 검증된 missing-column lower bound가 필요하다. 지점·시간별 dual P/Q vector와 전체 SOC/경로를 유지해야 하며 총 capacity나 scalar 지원량으로 대체하지 않는다.

## 종료와 증명 수준

공식 Gurobi 문서에서 TIME_LIMIT은 시간제한 종료이고 OPTIMAL은 tolerance 조건의 최적화 상태다. TIME_LIMIT, 발견한 negative reduced-cost column 수, Native Gap 자체를 complete pricing으로 표시하지 않는다. [공식 status 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/statuscodes.html)

이번 verifier는 모든 원본 block을 유지한 signed-dual LB와 complete-domain LP pricing lower bound를 구현한다. 각 차량에 대해 original coupling 가격으로 재구성한 exact β가 모든 정수 trajectory의 가격 목적값 하한이고 convexity dual이 η이면, β−η≥0은 그 차량의 모든 missing columns의 reduced cost가 음수가 아님을 증명한다. 네 차량 모두에서 성립한 경우에만 이 부분의 pricing closure를 인증한다. 하나라도 음수 **하한**이면 정수 negative column이 존재한다는 뜻도 아니며 closure는 NOT_PROVEN이다. MILP가 TIME_LIMIT이어도 이러한 별도 LP 증명이 성립할 수 있지만 TIME_LIMIT 자체는 근거가 아니다.

RMP primal 최적성, nonunit residual과 원래 Global LB는 별도 증명이며 Native RMP objective를 그대로 승격하지 않는다. 자원 DP의 완전 탐색 및 위 dominance 정리는 **NOT_IMPLEMENTED/NOT_PROVEN**이다. 이전 완료 연구의 exact LB는 동일 case/source/hash authority로 보존한 증거이며, 신규 가격 증명과 구분한다. M1/M2의 이번 연구 목표는 5%, A1/A2는 기존 0.5%다. P2 없는 `M1_ACCEPTED=false`는 유지한다.

실행 전 우선순위는 (1) 이전 strict RAW와 exact 임계값, (2) zero-Native 분해/가격 원래 signed-dual 재구성, (3) 제한된 four-unit pricing으로 신규 trajectory 및 local LP dual 수집, (4) full original physical UB replay와 exact Global LB/Gap 판정이다. 완전한 DP oracle이나 대규모 hull을 이번 canary에서 구현했다고 주장하지 않는다.
'''


def generate():
    if ROOT.resolve().drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
    REPORTS.mkdir(parents=True,exist_ok=True)
    path=REPORTS/'LITERATURE_REVIEW_KO.md'
    path.write_text(TEXT,encoding='utf8')
    return dict(path=str(path),sources=list(SOURCES),primary_sources_only=True,
        Native_optimize_calls=0,new_pruning_rule_claimed=False,applicability_is_scoped_inference=True)


if __name__=='__main__':
    print(generate())
