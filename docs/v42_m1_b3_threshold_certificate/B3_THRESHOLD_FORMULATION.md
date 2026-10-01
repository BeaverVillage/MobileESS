# B3 threshold decision

Let F_B3 be the exact PR113 partial-integrality set (85,744 restored binaries; all 954,560 original F3 rows). The scientific decision set is F_B3 intersect {rho_max <= 0.5732125039436496}; objective is identically zero. Its native axis has 316,743 variables and exactly one additional nonzero/row. Original rho epigraph semantics, full96 physics/grid/PCS16 and terminal equalities remain unchanged.

A validated threshold witness gives opt_B3 <= T and hence opt_B3-S2 <=0.001. Proven infeasibility of the unrestricted decision model gives opt_B3 >T. A failed route-fixed subset never proves that the unrestricted set is empty. S2 is a reference, not an installed lower floor on B3. At exact threshold equality the user's nonmaterial ceiling includes equality; acceptance conservatively requires a 1e-6 margin without changing the hard row.

Root candidates fix only restored route bounds, as upper-witness generators. The exact direct model has no fixed bounds, omitted arcs, additional SOC/voltage relaxations, or route candidate restrictions. One mandatory direct solve follows candidate search even if a witness was found; a complete safe witness makes its feasibility acceptance terminate at the first solution. No B1/B2/prod/decomposition solve follows.

Constant objectives describe feasibility problems in the [Gurobi objective documentation](https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/objectives.html). Native status3 is a solver-certified floating-point MIP infeasibility result at registered tolerances; it is not a rational-arithmetic proof. Numerical-boundary points are never declared certificates.
