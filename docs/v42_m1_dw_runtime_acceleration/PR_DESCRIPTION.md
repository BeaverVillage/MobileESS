Prepare four independently opt-in Discovery runtime adapters against PR143 exact head
ce5d30fb9bcb91ab8395d1313e868d24f5fde517: fully validated true-RC quota stop,
canonical per-MESS thread validation, authority-bound immutable receipts/audit tiers,
and append-only persistent RMP construction with reset(0)/LPWarmStart=0.

Production scientific modules and callers remain untouched; flags default off.
Certification continues to use true unstabilized duals and original global BestBd/
exact corrected LB. Warm basis remains unselected. New helpers need later production integration.

Validation: Lane C unit tests and bounded native Gurobi fixtures only. Threads=1,
TimeLimit=5 s, sequential native calls. Early quota returns 4 legal true-negative
columns with INTERRUPTED, including a smoothed-only rejection. Sequential/thread
validation matches exactly. Four RMP append iterations and disk reconstruction
match matrix identity, objective, primal and duals. No production/full-scale solve,
May execution or repo-wide pytest. Timings are toy-only; no speedup extrapolation.

Evidence and Korean review: docs/v42_m1_dw_runtime_acceleration/.
