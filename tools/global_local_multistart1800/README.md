# Four-MESS joint original-DAG route-pool canary above exact PR220

The user's urgent correction replaces the initial, unexecuted multi-start
draft. Native Optimize count at correction was zero; no budget was reset.
`initial_multistart_draft/` preserves that unexecuted design as text.

The proposed algorithm jointly selects all four vehicles' routes in one
Source18r Exact C3A+Dense MILP. Each unit initially has six complete original
96-slot paths including STAY, multiple actual MOVE paths and its verified
PR220 path. Added binary `lambda[u,r]` selects exactly one path per unit.
Exact source Node/Route Flow links and an independent affine inverse-alias
proof reproduce every original Arc/Node. All 9,322 source binary types,
384 Charge Modes, Pch/Pdis/Q/SOC97, original physical/Grid rows, ETA/travel
energy, fixed AIDC, SVR/Cap and min rho_max remain unchanged. Candidate-pool
restrictions are a subset of original FULL feasibility; no restricted bound
is a Global LB. No MOVE is forced. All-four-moving combinations are selectable
by the route domain; their joint SOC/Grid feasibility is established only by
the actual MILP and FULL replay.

The original FULL center remains included with its unchanged raw Start and
literal one-hot lambda Start. Native0 builds and disposes the actual extended
model without Optimize; the worker repeats independent proofs and complete
Native readbacks before its one Optimize call. Stagnation changes/expands
all four route pools, using exact pool/model signatures to prohibit repeated
model solves. Cartesian path combinations are never enumerated as separate
MILPs. Source numerical tolerances are unchanged; raw points are never repaired.

Solo and pair experiments are limited ablation/comparison calls. Their UBs
are separately labelled; the main proposed result is the joint MILP. New
Global best may seed the next joint pool, while inherited and previously
accepted points are never labelled new discoveries.

One preselected K32 selective-integrality experiment retains approximately
288 original binaries over three fractional-mixing adjacent slot pairs.
The remaining original binaries relax on their original [0,1] bounds. All
K32 coefficients/RHS/objective/outward projection remain unchanged, proving
FULL integer projection is contained. The existing K48 certificate is kept
unless a separately admissible actual ObjBound is higher. This new type
pattern has not been executed in PR215; failed Grid16 models are not repeated.
Only one new Dual Optimize is allowed, requested175s within180s, after joint
integrity and inside the same cumulative1,800s budget.

```powershell
python -X utf8 -m tools.global_local_multistart1800.prepare
python -X utf8 -m tools.global_local_multistart1800.controller
```

The completed run is one-shot latched. Do not reset it or reuse these commands
as an implicit restart. Threads1, one heavy worker, RAM4GiB/Commit6GiB plus
measured build-growth reserve and callback protection apply. B1/HOLD/schedules
and predecessors stay read-only. ACTUAL_NOT_RUN; no B1/B3/8500/campaign/other-date
or unrestricted FULL B&B. Original FULL feasibility and the numerical Native
Global-bound contract do not establish exact rational global optimality.
