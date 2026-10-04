# Canonical validation batches

`validate_batches` dispatches one immutable candidate batch per MESS with ThreadPoolExecutor,
at most four threads. Read-only block prototypes and the same immutable snapshot are supplied
by the caller. The task uses original Python physical/row audits and exact RC arithmetic;
it never builds or optimizes Gurobi models. Workers return immutable ValidationResult values.

Results are canonicalized by the full sorted JSON record and identical observations are
deduplicated. MESS, SHA, iteration, dual SHA, acceptance, reasons, true/search RC, maximum
residual and all original physical residual reports participate in equality. Different
observations of a trajectory, including stale-dual observations, keep their distinct reasons.
Accepted and rejected SHA sets describe observations and can overlap for a stale retry.

The bounded fixture validates 56 observations across four
synthetic MESS contexts, reverses worker and arrival order, and compares results exactly.
PASS includes smoothed-only negative, nonintegral, physical invalid, stale and duplicate inputs.
Thread wall time 0.133876 s is a toy measurement only.
Python GIL and original validator work may limit CPU scaling; no four full-size validators
were launched, and no production parallel speed claim is made. A future process variant
must transport solver-free prototypes and preserve identical canonical output.
