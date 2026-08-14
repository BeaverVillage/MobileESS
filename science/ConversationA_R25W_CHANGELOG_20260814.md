# R25W thread-cap and KKT round-trip correction

- Corrected the issue-157 post-solve false failure. `Threads=4` is a maximum
  worker setting; a root-closed solve may legitimately report one worker.
- The audit now requires the configured parameter to remain four and every
  observed worker count to be between one and four. It still fails closed on a
  missing observation, parameter drift, or oversubscription.
- Increased exact root pricing from 32 to 64 negative-reduced-cost paths per
  MESS/QCP solve. Exact true-dual pricing closure and reduced-cost audits are
  unchanged.
- Runtime evidence showed KKT count = CG iterations + numerical retries:
  issue154 25=24+1, issue155 23=23+0, issue156 23=23+0, and
  issue157 18=17+1. There was no redundant retry loop to delete.
- Issue 157 reached a global certified gap of 2.999394% before the wrapper audit
  failed. Because h0 was not committed, resume must rerun issue 157 from the
  immutable issue-156 POST state.
