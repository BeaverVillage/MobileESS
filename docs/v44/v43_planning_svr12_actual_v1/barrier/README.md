# May02 Root Barrier numerical correction

The measured May02 first Joint call exhausted 300 seconds with no incumbent.
Its root relaxation used 451.29 work units; crossover consumed 189.03 seconds
and restarted. May01's same phase used 99.98 work units and 19.68 seconds of
crossover. This is a numerical/root-relaxation bottleneck, not a proof of
physical infeasibility and not an increase in the original model dimensions.

The user's latest instruction keeps Root Barrier. The production policy is
`V44_B2_GAP3_MAY02_ROBUST_BARRIER_FRESH_M_V1`, implemented by `v44.barrier` with the
versioned adapter in `v44.numeric`. The earlier dual-simplex proposal remains
a separate pre-campaign diagnostic and is not used by this dispatcher.

For May02 B2 M1 Joint only, retain `Method=2`, explicitly select homogeneous
barrier (`BarHomogeneous=1`) and robust crossover basis construction
(`CrossoverBasis=1`). May01, other dates, K48 and all A stages retain their
original Root numerical parameters. No matrix coefficient, row, bound, route,
P/Q/SOC constraint, feasibility tolerance or original FULL admission check is relaxed.

At the user's later instruction, every B2 Joint MILP uses `MIPGap=0.03` (3%),
with `MIPGapAbs=1e-10` unchanged. B3 retains its original inner Gap 0.5%.
The relative Gap change can stop integer search earlier once an incumbent
exists; it does not directly solve the root LP/crossover bottleneck.
The fixed-route four-MESS P/Q/SOC scoring problem is a continuous HiGHS LP,
with a maximum two-second call and no MIP Gap setting. It is a heuristic
ranking score with continuous mode relaxation, not a FULL UB certificate.
The independent global gap target remains 3%; restricted Pool ObjBound is
never promoted to global LB.

The fresh campaign root is `campaign002`. May01 and May02 start with a new M
model build, separate new K48 300-second and Joint 900-second clocks, no
inherited incumbent and no previous Native time deduction. Joint calls remain
capped at 300 seconds, with one Solver thread per independent date Worker.
Two B2 date Workers run first, then the single Main Worker runs B0/B1/B3 per
date. Golden003 reuse and SVR12 Actual/Fresh remain as previously specified.

All old Raw and ledgers stay in `campaign001`; stopped trial metadata records
that both active Native calls returned and reconciled before process shutdown.
Numerical validation is a bounded pre-campaign diagnostic; no extra validation
loop is added to the production campaign. Its measurements and the actual
restart receipt determine execution status; implementation alone does not
establish a speed improvement or campaign PASS.

Reference: [Gurobi numerical parameters](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/numeric_parameters.html).
