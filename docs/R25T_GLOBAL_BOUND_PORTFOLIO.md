# R25T Stage-1 global-bound portfolio

R25T changes solver orchestration without changing the Stage-1 scientific
model. The five-minute cadence, H54 horizon, h0-only commit, causal state chain,
AC-aware convex QCP, Fresh nonlinear OpenDSS gate, four-thread policy, scalar
objective, and globally certified 3% acceptance rule are unchanged.

## Why R25T exists

R25R solved the generated-path restricted integer master with `MIPGap=0` until
the exact priced-root lower bound certified its incumbent. The restricted
master was scientifically useful only as an incumbent generator: its native
`ObjBound` omitted ungenerated paths and could not certify the original model.
On issue 149 this phase explored more than one million nodes for more than 6,000
seconds while the globally certified gap remained above 3%.

## Solver lifecycle

1. Preserve the untouched original compact MIQCP and verify its working copy
   before projection by hashing the complete mathematical structure: variable
   domains and objective, the full sparse linear matrix, every linear row, and
   every quadratic row. Gurobi `Fingerprint` values are retained as diagnostics
   only because search-guidance attributes can make a copied large model report
   a different fingerprint without changing its mathematical problem.
2. Run exact root column generation on the working copy and close pricing under
   the retained-optimal-dual numerical-envelope rules.
3. Run the restricted integer master only as a bounded primal phase. Stop at a
   global 3% certificate, a 60-second meaningful-incumbent stall after at least
   30 seconds, 300 seconds, or 200,000
   nodes. Its tree spills to disk from 0.1 GB and is capped at 4 GB because the
   original compact authority remains resident. An out-of-memory signal in this
   heuristic phase is also a phase transition: any feasible incumbent is kept,
   the restricted working model is released, and no restricted bound is used.
   These are phase-transition limits, not total solve limits.
4. Map any feasible restricted incumbent back to the original variables as a
   Gurobi-validated MIP start and integer VarHints. R25V also shifts the previous
   causal optimizer plan by one slot and submits it as a separate partial native
   start. The terminal extension is left undefined, and Gurobi must complete and
   check both starts against the current model; either can be rejected without
   affecting correctness. Before root pricing, seed
   the working master with several exact feasible paths ranked by the previous
   plan hint and raw route objective. These are search-guidance additions only:
   no path is removed and pricing closure remains exact.
5. Solve the untouched original compact MIQCP with no overall time or node
   limit. Its native `ObjBound` is valid for the complete original problem.
6. At every callback compute

   ```text
   GLOBAL_LOWER_BOUND = max(EXACT_PRICED_ROOT_LB,
                            ORIGINAL_COMPACT_MIQCP_OBJBOUND)
   ```

   and terminate only when the resulting global gap is at most 3%.
7. Fix every original discrete variable at the certified compact incumbent,
   reoptimize the unchanged continuous convex QCP under strict numerical
   tolerances, and run all existing transition and Fresh OpenDSS gates.

The restricted-master native bound is never included in the global bound.
The existing external Python branch-and-price tree is disabled in this
portfolio because the original compact model gives Gurobi access to its native
presolve, cuts, propagation, branching, heuristics, node management, and valid
global bound.

R25V first reduced exact root-CG synchronization cost from 16 to 32 negative-
reduced-cost paths per MESS and QCP solve. R25W raises the batch to 64 after
issues 154--157 showed that 17--24 CG iterations caused 18--25 KKT dual solves,
with only zero or one numerical retry. Pricing is still run to the same
conservative closure gate, so this changes the number of round trips, not the
all-column relaxation or its certified lower bound.

`Threads=4` is a maximum worker policy. Gurobi may legitimately report one
worker when a valid start closes the certificate at the root or during a small
polish phase. The runtime audit therefore verifies that `Params.Threads` is
four and every observed worker count lies in `[1,4]`; it rejects a missing
observation, a parameter mismatch, or use above the configured cap. It no
longer mistakes the final one-worker message for a policy failure.

## Retry policy

R25T retains the R25R bounded reduced-cost envelope. A fully optimal finite
dual snapshot inside the hard envelope is preserved, no more than two stricter
retries are attempted when such a snapshot exists, and the measured error is
subtracted conservatively from the minimization lower bound. The first
fixed-integer polish attempt that passes the numerical gates ends polishing.

## Resume and progress

The R25T driver imports only completed, verified R25R/R25S POST states. An
incomplete issue is quarantined and recomputed; completed causal commits are
not overwritten. A legacy `r25t.resumable.v1` directory is upgraded in place to
the hash-locked `v2` science copy; this migration changes solver orchestration
and runtime safety only, not the mathematical authority.
Every full run and preflight holds the same exclusive process lock. A second
invocation fails before touching the runtime, and the lock descriptor is
inherited by the solver child so an orphaned child remains protected. Preflight
returns before resume-authority writes, failure archival, or incomplete-issue
quarantine, so it cannot rename a live Gurobi `LogFile`/`NodefileDir` path.
During execution it reports either
`BOUNDED_RESTRICTED_PRIMAL` or `COMPACT_EXACT_BB`, and
`GLOBAL_CERTIFIED_GAP` remains the sole Stage-1 acceptance metric.

Early R25T result files stored the correct final compact certificate inside
`compact_exact_global_phase` but could retain a pre-compact value in the
top-level convenience field. New results write the final certificate to both
locations. Resume validation uses the nested compact/polished value for those
already committed early files, so issues 151 and 152 remain immutable.

Preflight only:

```bash
MOBILEESS_R25T_PREFLIGHT_ONLY=1 \
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```

Full resume:

```bash
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```
