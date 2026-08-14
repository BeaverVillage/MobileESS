# R25L / B5 — Monolithic Go/No-Go Gate

B5 performs one diagnostic-only issue152 run using the exact R25K/B4 formulation and solver policy. It does not commit h0 physical state. The screen is capped at 600 seconds.

The gate is production-oriented: achieving 3% inside the screen is an immediate GO for Stage-1 monolithic closure. A non-certified run is accepted as promising only if root exit, branching volume/throughput, gap, certificate-closure fraction, and projected remaining bound time all pass the frozen thresholds. Otherwise B6 exact decomposition is mandatory and additional monolithic parameter tuning is forbidden.

The scientific `main.py` is byte-identical to B4. No physical constraint, objective, H54, 5-minute cadence, 3% MIPGap, causal input contract, or Fresh Exact OpenDSS requirement is changed.
