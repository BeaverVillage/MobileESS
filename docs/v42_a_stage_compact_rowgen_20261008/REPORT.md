# Overnight A-stage practical exact solver

Current classification: **A_PRACTICAL_SOLVER_P1_GAP_LE_0P5**. This report is refreshed during execution; the final repository handoff records the final HEAD and remote match separately.

## Scope and immutable budget

Stacked on Draft PR178, exact `e8c7634002cb6249ef79aacd585017b3cfaf0bd2`. Immutable UTC start 2026-10-07 16:53:17; deadline 2026-10-08 00:53:17 (KST 09:53:17). Every native solve uses Threads=1 and the inherited tolerances/objective hierarchy. Pricing is sequential, below the maximum four workers. RAM and system commit are sampled; the M lane is untouched. No production, Planning, Actual or Fresh AC execution is authorized.

## Exact representation actually used

Pure physical path lambdas fail to represent the original fractional native migration LP: with unshared Big-M links, fractional ACTIVE can coexist with zero WAN bytes. Bounded N=1/2/3 STAY/migration fixtures preserve that counterexample and verify the exact hybrid instead. Identical continuous optional lanes are summed exactly; a perspective residual kernel retains every nonprojectable fractional direction. Concrete path mass is lifted together with the residual, with exact coefficient checks for all couplings. Inverse lift uses zero path mass and retains the native fractional point. HIST counts remain unchanged. SUM migration lanes are never integerized: P1 integers restore actual original N native lanes and types. See `EXACT_PROJECTION.json`, `QUALIFICATION_TESTS.json`, `INTEGER_TESTS.json` and the source-bound archives.

| Model | Rows | Columns | nnz |
|---|---:|---:|---:|
| Frozen64 expanded original | 1,046,444 | 362,044 | 14,820,623 |
| Frozen64 full hybrid, artificial-free | 739,158 | 82,458 | 13,797,701 |
| Initial reduced Phase-I | 58,842 | 97,566 | 1,377,612 |
| Closed full Phase-I with artificials | 739,158 | 777,882 | see closure identity |
| P1 original integer control | 1,046,444 | 362,044 | 14,820,623 |
| Complete relevant MIG=0 integer domain | 732,455 | 255,356 | 23,972,931 |
| Same integer domain with inherited valid cuts | 732,618 | 255,356 | 23,979,160 |

## Frozen64 Phase-I and row closure

The exact PR178 batch was activated once: 32 STAY + 32 migration. No repricing or reselection preceded materiality. Phi before `0.006627342398282464`; certified Phi after **0**, reduction **100%**. S0 through S18 each returned raw Phi=0 but failed omitted-row closure; none was treated as scientific zero. `PHASE1_ITERATION_TRACE.csv` records every master solve, added rows, runtime, work and factor memory. All violated omitted rows above 1e-6 were added. After measured small-cut tail behavior, all remaining original rows were promoted in the same experiment. The final all-row solve took 137.900s; original expanded artificial-free replay had maximum row violation 9.095e-13 and zero bound violation. All artificials were removed before P1. Positive-Phi adaptive pricing was unnecessary; no stagnation classification was made.

Phase-I total native time **729.724s**, Work **1102.553**, recorded wall through closure **1571.568s**. Maximum factor 17.73M nnz / 0.5GB. The intentional source-bound architecture handoff and earlier segment remain archived; there was no candidate reset.

## Original P1 closure and global integer gap

One full original-row P1 LP and one complete pricing round covered all 150 classes, including 197,537 STAY and 97,724,022 migration options and their original fractional kernels. All omitted-block reduced-cost lower bounds were nonnegative. Artificial-free original replay passed. Rational dual correction gives full-domain LB **0.7302103658992288** (`6577150263531681/9007199254740992`). LP value **0.7302103660786277**. Pricing wall was 176.939s. `M19/P1/S0/PRICE/FULL_PRICING_RESULT.json` retains complete class coverage and individual oracle certificates.

The original integer control returned a fully replayed 1,023-job A1 point in 27.968s / Work31.885, one native node. UB **0.7302103660786277**. Full-domain gap ratio **2.456810221537103e-10**, or **2.456810221537103e-08%**, below 0.5%. The control's active-only MIP bound was **not** used as the global P1 LB. The independently closed root LP plus original integer primal sufficed, so the external deterministic best-bound queue has one closed root and zero P1 children. P1 native node rate is approximately 128.7/hour; no multi-node P1 tractability claim is implied. The checkpoint contains the root, incumbent, closure and hashes.

## P2 under inherited locks

Rho lock is the inherited +1e-7 rule. Migration count **0** is globally certified by a fully replayed original integer point and the universal nonnegative objective bound. Only then is the complete MIG=0 relevant integer domain built: all full STAY options, all remaining original singleton native kernels, all original global rows, and exact zero projection of optional lanes. Migration candidates remain in the scientific domain and are excluded only within this certified prior-objective query.

The first full-domain Shift control produced UB950 / native bound946. Independent external LP children retained both branches; one interval dual certificate failed because an unbounded variable had a tiny wrong-sign reduced cost, so that open child was not pruned. Inherited integer-valid histogram cuts add 163 rows / 6,229 nnz and preserve integer schedules/objectives; they strengthen the LP.

A complete-domain objective partition Shift≤949 OR Shift≥950 was preserved. The left native search processed 2,009 nodes in 1,186.011s / Work2,220.580 without a new primal, terminating at its component allocation with current ObjBound948. It was not called infeasible. A separate recovery combines that current verified full-domain bound with the analytic right-child LB950, yielding stage LB948 / UB950. The actual Gurobi CSR, boxes, types, senses, RHS and objectives were independently read back and matched exactly. This is the repository's current-native complete-integer-model bound authority, **not an independent rational MIP dual proof**. [Gurobi ObjBound contract](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound) defines the post-solve bound, including objective-integrality rounding.

The continuing exact-Z architecture adds Z=the inherited integer affine objective, preserving the original LP projection and integer schedules. Both Z=k and Z≥k+1 children remain recorded. A feasible fixed-value case plus the full-domain lower bound certifies the integer optimum; proven current full-domain integer infeasibility advances k; a time-limited case stays open. Checkpoints are written every ten native nodes or five minutes. Prestart follows only a certified Shift lock. Current final-case result: `None`.

## Conditional canaries and measured totals

May17 → May12 → May10 can execute only after May19 A1 acceptance with at least 5,400s remaining at the trigger. The same completed architecture and policies are used without retuning. No other date is included. Individual results, when present, live in `CANARIES/<date>/RESULT.json`; prepared code is not evidence of execution.

Completed solves: **163**; total native **2204.588s**, Work **3777.349**; maximum observed own-process RSS **9,705,512,960 bytes**; elapsed wall **8309.574s**. In-flight work is excluded until its native result persists. `ALL_COMPLETED_NATIVE_SOLVES.csv` is the deduplicated per-folder ledger. Static build, serialization, full physical replay and source hashing contribute to wall time separately. The P1 target is already reached; the current measured bottleneck is exact P2 Shift integer closure, not P1 gap.

Source freezes record each actually executed commit, exact source file hashes and immutable ZIP archive. Matrix/point binaries remain in the external static directory with SHA256 receipts; repository evidence includes the replay, identity, source, trace and certificate JSON/CSV/log files.
