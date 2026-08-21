# R25M B6R4 — Continuous-Relaxation Dual Fix + Exact Root Reuse

This revision fixes the B6R3 runtime failure `AttributeError: Unable to retrieve attribute 'Pi'` without changing the scientific model.

* The external branch-and-price base is created with `Model.relax()` so every branch-price node is an explicitly continuous QCP relaxation before dual pricing.
* Runtime guards require `NumIntVars == 0` and `NumBinVars == 0` before any branch-node pricing solve. Dual unavailability fails closed with diagnostics.
* The exact all-column root lower bound and root fractional branching candidate are cached at the original root pricing closure and reused by the B&P tree. The root is not redundantly re-solved/re-priced after the restricted integer primal phase.
* Child nodes still perform exact node-restricted DAG pricing to all-column closure before their lower bound is admitted to the global certificate.
* The restricted-master bound remains non-authoritative. No same-issue post-hoc MIP start is introduced.

Scientific contract unchanged: H54, 5-minute cadence, 3% global certificate, Threads=1, causal state chain, no future actual, no future D2 reinjection, no physical h0 commit in the B6 screen.
