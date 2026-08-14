# Conversation A — R25M B6/7 changelog

- Bound B5 decision: `NO_GO_MONOLITHIC_ADVANCE_B6_EXACT_DECOMPOSITION`.
- Added exact matrix-driven Dantzig–Wolfe projection of STAY/MOVE/node-occupancy variables into complete MESS path columns.
- Added exact DAG negative-reduced-cost pricing for the full continuous path-master relaxation.
- Added a global 3% certificate using the exact all-column relaxation lower bound and any feasible restricted integer path-master incumbent.
- Restricted-master internal bound is explicitly non-authoritative; pricing must close.
- No same-issue post-hoc MIP Start; H54, 5-min cadence, 3% target, causal inputs, Rack/WAN/Grid/OpenDSS semantics unchanged.
