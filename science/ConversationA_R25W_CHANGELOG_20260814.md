# R25W thread-cap and KKT round-trip correction

- Corrected the issue-157 post-solve false failure. `Threads=4` is a maximum
  worker setting; a root-closed solve may legitimately report one worker.
- The audit now requires the configured parameter to remain four and every
  observed worker count to be between one and four. It still fails closed on a
  missing observation, parameter drift, or oversubscription.
- Tested exact root pricing at 64 negative-reduced-cost paths per MESS/QCP
  solve, then rejected it. On issue 157 it regressed from 17 iterations and
  187.5 seconds at batch 32 to 24 iterations and 324.5 seconds at batch 64.
  Production remains at 32; exact true-dual pricing closure is unchanged.
- Runtime evidence showed KKT count = CG iterations + numerical retries:
  issue154 25=24+1, issue155 23=23+0, issue156 23=23+0, and
  issue157 18=17+1. There was no redundant retry loop to delete.
- Issue 157 reached a global certified gap of 2.999394% before the wrapper audit
  failed. Because h0 was not committed, resume must rerun issue 157 from the
  immutable issue-156 POST state.
- Corrected a follow-up control-flow regression: the thread-cap audit
  assignments are unconditional `build_full` statements, not part of the
  non-B6 multiobjective fallback branch. An AST regression test enforces this
  scope before release.
