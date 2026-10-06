# Current-authority exact supercompact preregistration

Base PR160 exact head: 8513a281615d9e0fd0af2b7cb3d36b6f8a1fb962.
PR124 c7d808a315e04aefc1bcfc537b84cc38d895a9ab is a design/proof reference only.
This checkout, output namespace and solver logs are separate. N_MESS=4; H=96.
No scientific physical limit, grid authority, objective, integer route or numerical tolerance changes.

C0 retains all current original columns and scientific rows, relaxes route arcs
to nonnegative continuous flows (except parallel-edge selectors), and appends
binary visited-node activity linked to outgoing flow, or incoming flow at H.
Explicit stays initially preserve sparse connected P/Q/PCS rows. C1 removes
only independently replayed PR160 LP-safe certificates. C2 runs deterministic
exact fixed-point presolve, retaining any unknown or integer-only implication.
All mappings and deletions must be independently checked before heavy solves.
Parallel edges require original binary selectors. No blanket TU assertion.

Substitution uses exact stored binary-rational coefficients. Accept only if
the resulting coefficients/RHS are exactly representable by IEEE binary64,
variable bounds are retained as necessary, and nnz/fill do not increase.
No observation of previous solution zeros is used in presolve.
SOC endpoint/interval propagation and PCS bounds use original stored rows.
All-variable and all-row scans repeat to a fixed point. Nondeterministic paths
and chains with scientific decisions/events remain explicit.

Mandatory gates: current signature; 190280 PR160 certificates independently
replayed if recomputed count agrees; 1536 original physical assignments across
F0/F1/C0/C1/C2; exhaustive bounded route states; fractional/adversarial proofs;
full-original validated start mapped without changing physical decisions.
Size gate: >=95% binary reduction and C2 vs C0 >=20% rows OR nnz OR continuous.
If a proof/start gate fails, do not optimize. If size gate fails, classify
SUPER_COMPACT_LOW_EXPECTED_VALUE. Resource conflict delays heavy execution.

Optional root-LP microchecks are skipped initially. No automatic sweeps.
If all gates pass, one sequential C0,C1,C2 comparison only: 300 seconds HARD
per-arm wall budget including model build; native TimeLimit at most270 seconds
and further capped by remaining wall budget. Identical PR159/160 POLICY plus
PreCrush=1, LazyConstraints=0, Threads=1, MIPGap=.005. Read-only incumbent/bound
callbacks; no cuts, row generation, pricing or parameters sweep.
Native process resource gate before build and optimize; no other solve killed.

Raw native BestBd, safely downward-adjusted native bound, inherited certified
full-domain LB and valid final global LB reported separately. Restricted DW
bounds are never used. Same validated original start and inherited LB all arms.
Select only exact domain+material compression+meaningful computation: root
completion when compact baselines fail, >=20% matched root time/Work improvement,
material valid gap improvement or genuine branching progress. Unfinished root
Work and memory alone do not select. Freeze selected C2 then stop heavy work.
Tournament is design only; no DW/BAP/Benders/rowgen/one-tree/3600s execution.
