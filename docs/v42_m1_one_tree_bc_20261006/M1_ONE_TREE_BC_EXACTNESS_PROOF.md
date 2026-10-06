# Exactness proof and supported callback semantics

Let F be the original explicit-variable mixed-integer feasible set, and S0 be
all non-security rows (including every exact affine definition). For any set
of original grid rows R, F is a subset of F(S0 union R). Therefore minimization
over each relaxation gives a lower bound on the original M1 optimum. User cuts
are original rows and preserve every point in F, even if they tighten a node.
This is full original variable-domain authority, never restricted-column LB.

All MIPSOL points are exhaustively tested against every deferred row. A violation
triggers cbLazy with original coefficients, sense and RHS. Gurobi rejects that
candidate; even a previously added lazy row is resubmitted when necessary under
explicit user authorization. No rejected objective is admitted as UB. A passing
point must also pass the original nongrid/mobility/SOC/PCS/mode/connection,
bounds/integer and objective audits. Thus every recorded UB belongs to F under
the unchanged numerical authority. Registry uniqueness is an accounting
property, not an assumption that a native usercut/lazy pool is enforced forever.

Separator is PR158's direct sparse affine evaluator with cached CSR/absolute
CSR, outward floating-point enclosure and exact binary-rational fallback for
ambiguous rows at1e-8. It performs no LP or recourse optimization. <= and >= use
opposite residual signs, equality uses absolute residual. No coefficient/RHS
transformation occurs. All 81,216 grid auxiliary definitions stay in S0.

MIPNODE ranking/batches only affect acceleration; they cannot declare feasibility
or terminate successful certification. No application cut deletion, restart,
point rounding or scientific threshold modification occurs. Any unhandled
error/deadline-truncated lazy batch is fail-closed. OPTIMAL/TIME_LIMIT labels
alone never establish scientific acceptance. One optimize maintains one tree.

12 inherited bounded physical constructors are used only to construct tiny
original MILPs, never Benders recourse. 1,536 binary assignments are checked
against complete monolithic feasible statuses/optima. A separate fractional
node fixture exercises cbCut; direct reconstruction covers all three senses.
An explicit duplicate re-rejection protocol fixture confirms registry uniqueness
with authorized native cbLazy reuse. Fullscale gate also checks saved starting
point on the entire original unreduced matrix, all grid rows and native physical
validators. Full result is independently rechecked after the one optimize call.
