V40R3 independently forecasts next-operating-day incremental arriving GPU-service demand.

Final classification: V40R3_FUTURE_GPUWORK_SAFETY_FAIL. No model selected. No production/optimizer integration.
V40R2 is SUPERSEDED_BY_V40R3; never resume, fit, import, merge, modify or delete it.

Authoritative preregistration commit: fbde550fee28065ad1b9946b430c1b3e69cefe42.
Frozen target/model/split/loss/metric code must not be edited to improve this completed experiment.
Detailed Korean results and provenance are in ../artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_FINAL_REVIEW.md.

Existing-run read-only-science verification (from this worktree, using the recorded isolated runtime):

    python -m dayahead.v40r3.final_audit
    python -m dayahead.v40r3.test_contracts --final
    python -m dayahead.v40r3.final_review

These commands write reporting/audit artifacts only and do not fit models. final_audit must follow evaluate
because it disambiguates intermediate array-value equality from byte identity and pairwise from overall
proposed-model superiority. The original frozen train/evaluate code and the original fit predictions remain
unchanged. Synthetic gradient tests never call optimizer.step.

Do not rerun initialize/preregister in this completed checkout. A separate explicitly scoped reproduction
must retain the original frozen contracts and preserve these results; use the exact environment and run
ledger, not the superseded V40R2 implementation. The confirmatory block is unavailable; exposed-history
evaluation and test passes are not production validation.
