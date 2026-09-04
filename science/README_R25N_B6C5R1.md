# R25N B6-C5R1 — Gap Authority / Target Certificate Cleanup

C5R1 is a solver-certificate correction on the frozen Stage-1 scientific model. It does not change H54, the 5-minute rolling cadence, the objective function, the physical feasible set, the 3% Stage-1 acceptance semantics, causality, or Fresh Exact OpenDSS.

## Why C5 failed
The actual C5 issue152 run obtained U=-1937.9964663366604 and exact root L=-2017.405996772834, so the frozen full-scalar relative gap was 4.097506%. With the current incumbent, 3% requires L >= -1996.1363603267603: an additional 21.269636 objective units of valid lower-bound lift. The decision-independent constant makes this frozen relative gap easier, not harder; removing it would yield a diagnostic translated gap of about 23.26%, so constant translation is not the computational blocker.

## Corrections
- Stage-1 B6 requires an explicit 0.03 target; silent 0.015 fallback is forbidden.
- `certificate_lower_bound` is the single global-bound authority in acceptance and audit.
- Restricted-master native MIPGap is diagnostic only.
- Full-scalar relative gap, translated decision-dependent relative gap, absolute gap, target lower bound, and shortfall are reported separately.
- The 1e-5 route-energy tie-break is explicitly part of the frozen scalar objective; no procurement-only bound is fabricated.
- Restricted-column RMP infeasibility is unresolved unless exact Phase-I/Farkas pricing proves full-node infeasibility.
- An incomplete child no longer aborts the whole B&P tree; its valid ancestor bound is retained while siblings continue.
- Child lower bounds inherit the maximum of the valid parent bound and the separately priced child bound.

## Exact target-specific prepass
After all-column root pricing closes, C5R1 reuses the true root dual. For a mobility-only child, exact restricted DAG pricing computes each MESS block's minimum reduced cost. Shifting each path-convexity dual by that minimum gives a conservative child bound without another QCP solve. A complete mobility partition can therefore lift the global lower bound cheaply toward the exact target L >= U-0.03|U|. If it does not close the certificate, external exact B&P remains the fallback.

## Runtime policy
The actual C5 evidence showed C3 stabilization reduced iterations but increased wall time by about 19.7%, and C4 QCP strong probes returned no useful score. C5R1 therefore keeps both implementations available but disables them in the runtime gate. True-dual batch pricing is increased instead, and the fallback child-CG budget is lengthened.
