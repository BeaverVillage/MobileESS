# R25N B6-C5R3 — Final algorithm correction candidate

Purpose: use the actual C5R2 runtime forensic result to make one final B6 certificate attempt before B7.

Frozen scientific contract remains unchanged: H54, 5-min rolling cadence, modeled-total-objective 3% global certificate, causal state chain, no future actual arrivals, no future D2 reinjection, and final Fresh Exact OpenDSS gate in B7.

Runtime/numerical corrections:
- Threads=4 selected by C5R2 actual screen (1/2/4/8); 8 threads was only ~3% faster in mean root-RMP time and therefore lost the 5% smaller-thread rule.
- BarQCPConvTol=1e-9 is the QCP dual authority, with strictly tighter retry values only if Pi/QCPi/RC are unavailable.
- Dual stabilization and QCP strong-branch probes remain disabled because prior user runtime showed negative wall-time value / unusable probe scores.
- Root and child pricing batch=16.
- Restricted primal master gets heuristic effort 0.20; its bound remains non-authoritative.
- C5R2 gap-source forensic identified mobility/path integrality as the dominant block, so exact branch ordering is mobility-first.
- The fixed-root-dual certificate prepass now supports exact multiway time-layer service partitions. Each partition has explicit require-service children plus one REST child forbidding those service nodes. This partitions the entire parent path set; exact restricted-DAG pricing remains the bound authority.

B6 FINAL FREEZE is allowed only if the actual issue152 runtime gate obtains a globally valid gap <= 3% and all numerical/causality guards pass.
