# 다음 작업

Threshold question은 INCONCLUSIVE다. Dependency closure의 earliest slot은0이며 후보 window는0–95다. 이는 가능한 물리 ancestry이고 전체 과거 integrality 복원이 필요·충분하거나 material하다는 증명이 아니다. 확대 B3를 이번에 실행하지 않는다. 사전등록 결과의 root/search/resource 병목을 감사하고 별도 후속 exact feasibility decomposition의 exactness와 bounded fixtures를 먼저 검토한다.

## Conditional exact feasibility decomposition design (not implemented)

Master x consists of precisely the 85,744 B3-restored route and charge-mode binaries. Recourse y includes all remaining original variables, including outside-B3 fractional route/modes, Pch/Pdis/Q/SOC and full96 grid auxiliaries. Preserve every original row, the fixed AIDC anchor, initial/terminal SOC, PCS16, voltage band, route authority and the exact rho<=T row. Do not replace B3 with a stronger full-binary original-M1 master.

Normalize recourse rows and all finite bounds as A y <= b-B x, replacing equalities by two inequalities. A Farkas ray lambda>=0 with lambda^T A=0 and lambda^T(b-B xbar)<0 proves infeasible recourse at xbar. The valid master feasibility cut is lambda^T(b-B x)>=0. Sign conventions, variable bounds, stationarity residual and strict ray margin must be independently verified before retaining a cut. An uncertified numerical ray or timed-out recourse generates no cut. Mixed native senses and bound contributions must never be omitted.

Exactness: every B3-feasible (x,y) satisfies each validated Farkas cut. A master assignment plus feasible full recourse is a B3 witness; infeasible master after valid cuts excludes all assignments. This preserves the projection of the original threshold feasible set; early timeout still remains inconclusive. This is a future design, not a production implementation, and no Dantzig-Wolfe/column generation replacement is proposed here.

Bounded fixture proposal: a two-slot legal-route/charge-mode battery instance with finite power/SOC bounds, terminal equality, 16 PCS faces and a grid threshold. Enumerate every binary master assignment and solve exact recourse, compare monolithic and decomposed feasible sets, verify every feasible assignment survives all generated cuts, and deliberately perturb ray sign/bound terms to ensure rejection. Include an outside-window fractional mode fixture, infeasible terminal energy, feasible threshold witness, and a numerical-borderline ray. Fixtures are design only in this PR; no new decomposition optimize calls.

[Gurobi infeasibility analysis](https://docs.gurobi.com/projects/optimizer/en/current/features/infeasibility.html) explains IIS availability and the expense of MIP IIS. Farkas certificates certify continuous recourse, not full-MIP infeasibility by themselves.
