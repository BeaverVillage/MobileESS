# Current objective audit

Historical `dayahead/v41/objectives.py` independently evaluates `[rho_max, mean_xi_GPUh, migration_count, reference_deviation, deterministic_tie]`. `dayahead/v40g/optimizer.py` builds the same hierarchy. P2 is H4 uncertainty reserve shortfall, not permission to drop known compute service.

`dayahead/v40a/grid.py:add_grid/evaluate_grid` defines rho from non-transformer phase-line loading. Transformer phase current and kVA/polygon rows are separate hard limits. Voltage is hard. This definition is preserved in the proposed interface: **MAX_LINE_LOADING**, transformer excluded from primary and separately constrained.

Latest local V42 differs from a fixed five-objective claim:

| Block | Source | Actual objective assembly |
|---|---|---|
| A1/A2 | checkpoint_planning → blocks.solve_aidc | grid callback first objective; optional negative absorbable uncertainty reserve; remaining callback objectives; migration count |
| M1/M2 | blocks.solve_mess → joint_mobility.solve | caller's grid objective list, sequential locks |
| Outer acceptance | canonical.run | M2 recomputed against M1 at fixed A2; lex no-regret |

The native grid callback is a dependency, not specified by the generic block. Therefore its exact complete P1–P5 semantics cannot be uniquely certified from the supplied canonical entry alone. The generic A block does not itself append start-shift, placement-change or deterministic tie objectives. No five-level native hierarchy is fabricated in this audit.

`joint_mobility.py:solve` has `addQConstr(net*net+q*q <= pcs_kva**2*x)` as well as linear polygon rows. It is MISOCP, despite historical requests referring to both blocks as MILP. We do not remove its quadratic security condition or change MESS in this task. A/M formulation type and preference among multiple feasible optima remain separate questions.

P2 cannot currently be deleted. `envelope.add_envelope` has absorbable reserve bounded by Q90−Q50, with `secondary=-sum(reserve)`. It permits uncovered uncertainty; hard full known-job service does not prove all uncertainty reserve can be hard. The generic cohort service contract remains integration pending and is not promoted. Native production keeps existing P2. The new synthetic solver accepts required shortfall before interventions and tests that ordering; this small option-cost test is not a native envelope validation.

The new objective is proposed and tested only in a bounded synthetic A block. Final native adoption is blocked by service authority, native grid binding and MESS objective integration. Existing production P1–P5/trust/epsilon bytes remain intact.
