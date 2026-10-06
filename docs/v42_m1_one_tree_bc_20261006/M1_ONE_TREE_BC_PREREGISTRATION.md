# M1 one-tree original-grid callback preregistration

Base: PR158 a6045405b254703285a9d8469105746e3fc1b904. All inherited files remain untouched.

One fresh initial compact master and one optimize(callback) per full-scale arm.
Original objective, all route/mode/P/Q/SOC/rho variables, 81,216 affine auxiliaries,
all initial/terminal SOC and PCS16 constraints remain explicit. No pricing, RMP,
D-W columns, B&P queue or giant recourse solver is imported or executed.

MIPSOL exhaustively scans all 598,465 security rows, including previously
submitted rows. Every violation above 1e-8 is submitted as its exact original
row with cbLazy before the candidate can count as valid. Each grid-feasible
candidate also passes original full-matrix, exact integer, route, SOC, PCS and
mode/connection validators, with independent original objective recomputation.
Existing affine postsolve tolerance1e-6 is retained, bounds/route1e-8 and
unchanged native FeasibilityTol/OptimalityTol/IntFeasTol1e-8. No point repairs.

At optimal fractional MIPNODE, scan every security row; rank genuinely violated
not-yet-submitted original rows by violation/max(1, original coefficient L1
norm), ties by original row index. K_LINE=128, K_VOLTAGE=64 (both senses
combined), K_TRANSFORMER_CURRENT=32 (NormalAmps included), K_TRANSFORMER_KVA=32.
Submit via cbCut; PreCrush=1. No near-critical rows, gamma or result tuning.
All are original valid rows, so preserve every full-original integer point.

Unique original-row registry entries are immutable. No application cut deletion.
Gurobi can internally disregard cuts or present repeated lazy violations.
The user explicitly authorized cbLazy rejection resubmission (2026-10-06).
Record unique rows, avoided duplicate registry entries, usercut-to-lazy
promotion and native lazy resubmissions separately. Never assume submitted
rows are respected and never skip incumbent separation based on the registry.
Official semantics: https://docs.gurobi.com/projects/optimizer/en/current/reference/python/model.html#Model.cbLazy

Freeze source commit, hashes, fixture gate, scientific input/start hashes and
policy before the only comparison. One exclusive run marker forbids reruns.
Same Seed20260929, Threads1, Method2, NodeMethod1, Crossover2, MIPFocus3,
DegenMoves0, MIPGap.005, original numerical settings in both arms.
Both use PreCrush1; LazyConstraints1 only for callback arm, necessarily.
Sequential monolithic then one-tree. Continuous supervisor wall<=600s including
common input validation, model builds, starts, callback work and serialization;
each arm gets at most280s wall, native termination requested5s before its end.
Read-only1s RSS/process-commit/system-commit/free-RAM telemetry; no resource
threshold, waiting, kill or solver modification. Only fixed wall deadline acts.
Native logs preserved with OutputFlag1/LogToConsole0.

Use the same validated original point and already-certified full-original global
floor from PR158 in both arms. No D-W RMP duals/bounds/columns are loaded.
Native subset-tree bounds are full-domain lower bounds, conservatively nudged
down1e-8 (native numerical authority, not a new rational proof). Never use raw
invalid candidate objective as UB. Any callback exception/incomplete batch/
invalid terminal native solution invalidates new native-bound certification,
retaining only previously valid authorities and reporting INCONCLUSIVE.

Primary: reduction of valid global relative gap per end-to-end arm wallsecond.
Selected only with exactness PASS and >=20% improvement in a positive rate;
or materially stronger full-domain LB (>=1% of startingUB) at <=2s matched
wall difference, or genuine nonroot progress where baseline has none and
challenger has positive valid gap reduction. Both zero improvements=>false.
No memory-only selection. No additional policy comparison unless there is
positive promising progress and evidence a cut policy causes missed20% target;
default skip. Selected policy freezes and STOP. No3600s/P2/M2/B2/B3.
