# Conversation A — R25M B6R3 changelog

- Preserved B6R2 exact root column-generation and numerical lower-bound guard.
- Added deterministic primal pool enrichment: final-dual, raw-objective, previous-plan-hint, and Safe-energy k-best complete MESS paths.
- Added exact node-repriced branch-and-price fallback when root relax-and-price alone cannot certify 3%.
- Mobility branches use node-occupancy include/exclude disjunctions; pricing enforces required/forbidden nodes exactly.
- Non-mobility integer branches use original variable floor/ceil bounds.
- Every branch node must reach exact pricing closure before its lower bound can enter the global certificate.
- Restricted integer-master bound remains diagnostic only.
- No same-issue post-hoc MIP Start and no physical commit in the screen.
