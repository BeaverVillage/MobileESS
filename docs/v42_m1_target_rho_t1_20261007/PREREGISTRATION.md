# T1 full-domain exact feasibility pilot

Base PR171: `5d5718f5cfdc173eb2dd0a4c9f1ee3da8a833667`.
Scientific PR162: `1d922c91eb27056a5ccc79c92ef18146707099ab`.
LB=0.5687116003498334, UB=0.6306505800203936,
T1=0.5996810901851135 (the specified stored binary64 value).

All 582808 original C3A rows, 306040 columns, 9322 binary variables,
all original bounds/types and inverse are retained. Objective is identically
zero, with exactly one decision row rho_max<=T1. No start is supplied.
The PR171 incumbent and stored PR167 LP are read only for ranking/comparison.

Before native optimize: derive rational support certificates from original
PCS16, power/connection bounds and SOC recurrence; derive route compatibility
from the full original time DAG and exact movement energies. Critical-row
ranking selects one original thermal row per time 66..95, using stored LP
activity followed by incumbent activity and row index. Generate single-time
cross-fleet covers and two-time route-compatible cross-fleet support covers
for all selected time pairs with 1<=u-t<=8. Keep rho symbolic: these cuts
preserve all original integer schedules, including schedules above T1.
For each connected state at t, the two-time cap includes every compatible
connected state at u and a zero-power transit alternative. Free boundary
SOC envelopes are conservative, never fitted to incumbent trajectories.
If SOC bounds are nonbinding, report that explicitly.

Selected exact cut budget (static revision, still ZERO optimize): at most512;
at most32 single-time support envelopes,128 single-time integer covers,
224 two-time envelopes/integer covers,128 route/SOC incompatibilities.
The first362 support/conflict candidates had zero stored-LP violations.
Therefore also enumerate rho-dependent integer covers of low-capacity
cross-fleet state assignments. At most four highest-LP-mass states per unit
and time, and two per unit/time for compatible two-time pairs, rank the
candidate enumeration; this NEVER restricts the native scientific domain.
The bounded state candidate pool also includes up to four smallest exact
capacities per unit/time (two for two-time enumeration), to investigate
low-capacity assignments. Two-time pair pools retain the four highest stored
LP-mass pairs and four smallest exact-capacity compatible pairs per unit.
These are cut-candidate pools only; all original states remain in the model.
For any exact assignment implying rho>=delta>T1, insert only the proven
global inequality delta*(sum of k selected states-(k-1))<=rho.
If any indicator is absent, RHS is nonpositive and original rho>=0 proves
validity; if all are present, the exact grid/support proof proves delta.
All generated
route conflicts are counted and ranked streaming; only the best128 are
serialized. Rank by stored LP violation, near-active critical-row relevance,
nnz, and deterministic identifiers. Ranking does not establish validity.
An independent verifier does not import the production constructor; it
reconstructs grid bindings by iterative exact equation substitution, checks
nonnegative support duals, verifies original flow/energy incidence, and uses
backward route DP instead of the constructor's forward DP. Every selected
cut must pass exact algebra, outward native rounding, mutation and reference
point/adversarial gates. No static optimize or separate presolve calls.

Exactly ONE gp.Model.optimize: TimeLimit600, Threads1, Method2, NodeMethod1,
Crossover2, MIPFocus3, MIPGap.005, FeasibilityTol/OptimalityTol/IntFeasTol1e-8,
Seed20260929, DegenMoves0. No sweeps, repeated solves, additional thresholds,
old local hull/PCS cut loops, D-W, B&P or domain restriction.
Save all MIPSOL vectors before any replay. Callback telemetry only; no cuts
are added by callbacks. Save native matrix-transport identity and all parameters.

Bound gate: native INFEASIBLE with all identity/validity/numerical checks PASS
updates LB to T1 under the repository's frozen floating native authority;
this is not a rational branch-tree proof. Native OPTIMAL feasibility with a
full original integer witness and independent replay PASS updates UB to its
original rho (strictly <=T1). TIME_LIMIT/INTERRUPTED or numerical ambiguity
retains BOTH existing bounds, even if a saved point merits diagnostic replay.
Warnings, callback errors or identity failures forbid a bound claim.
Record unavailable factor/memory/root timestamps as null rather than infer them.

Stop after this pilot. Recommend exactly one next action after observing it.
No May/P2/M2/A2 work is authorized in this experiment.
