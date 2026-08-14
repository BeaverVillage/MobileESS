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
   global 3% certificate, meaningful-incumbent stall, 600 seconds, or 200,000
   nodes. These are phase-transition limits, not total solve limits.
4. Map any feasible restricted incumbent back to the original variables as a
   Gurobi-validated MIP start.
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
the hash-locked `v2` science copy; this migration changes only the copy audit.
During execution it reports either
`BOUNDED_RESTRICTED_PRIMAL` or `COMPACT_EXACT_BB`, and
`GLOBAL_CERTIFIED_GAP` remains the sole Stage-1 acceptance metric.

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
