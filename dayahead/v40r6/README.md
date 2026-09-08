# V40R6 cumulative arriving GPU-service work

The native R5 authority is 349 fixed-AEST days of 96 original 15-minute
arriving-service-work values. H1/H4/H8/H24 are within-day sums over 4/16/32/96
slots. These values are GPUh service-work mass, not instantaneous occupancy or
electrical power. No optimizer or power-system interface is enabled.

R5R1 was closed before this worktree was created from receipt
`528716aa36b02bbe0ebff3cf9639984c6b2c535e`. Both R5 and R5R1 are immutable.

Completed stages use the existing interpreter
`C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe`:

1. `python -m dayahead.v40r6.phase0`: freeze native target identity, cumulative
   labels, distributions, splits and causal features. No forecast fitting.
2. `python -m dayahead.v40r6.preregister`: prepare the exact scientific contract.
   Run `python tests/dayahead/test_v40r6_contracts.py --prefit`, commit, then record
   the preregistration receipt. The preregistration commit is `46220b7`.
3. `python -m dayahead.v40r6.train fit`: execute three fixed LightGBM settings,
   select one common setting from DEVELOPMENT, and persist all model bytes.
4. `python -m dayahead.v40r6.train select`: calibrate only on CAL_FIT; evaluate
   only CAL_SELECT; independently repeat eight final fits once. Freeze selection
   and commit before any EXPOSED candidate evaluation.
5. `python -m dayahead.v40r6.evaluate`: evaluate every preregistered candidate as
   historical diagnostics while preserving the frozen selection, including NONE.
6. `python -m dayahead.v40r6.finalize audit`: protected scope, negative prediction
   diagnostics and the Korean 54-item scientific review. Then run postfit tests,
   commit science, write and commit its receipt, and perform read-only closure.

These are historical execution instructions. Re-running mutation stages is not
an authorized retuning procedure. Use the read-only closure command to verify:

```powershell
& 'C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe' tests/dayahead/test_v40r6_contracts.py --closure --read-only
```

The initial first H1 Q50 fit produced substantive negative `expm1` predictions.
An overly strict execution assertion stopped the process. The logged correction
preserves those raw values and clips only numerical negative epsilon, as the
user required. It changes no target, model configuration, inverse formula,
selection objective, calibration formula or safety gate. The existing first
model was reused byte-for-byte; its unpersisted timing is null, not estimated.
The original preregistration remains immutable, with exact old/new source hashes
and a separate Git-bound execution-correction receipt.

CAL contains 29 calendar days. Its first 15 and last 14 form CAL_FIT/CAL_SELECT;
the inherited maturity exclusions leave 15 and 11 usable days. The original
stage cutoff remains in force: this is offline historical split calibration,
not a claim of a live rolling calibration available before every CAL_SELECT
issue. Feature inputs independently obey their per-issue maturity proof.

H1/H4/H8 rolling windows overlap. Their summed under/over GPUh count common
atomic work repeatedly; these are forecast-loss summaries, not distinct daily
work volumes. Coverage is reported both pooled and averaged equally across
eligible calendar days. All exposed months remain visible. Overall coverage is
diagnostic only. Exposed historical evidence is not independent confirmation.

The paper-facing correction is horizon-specific split-calibration-style, not
guaranteed finite-sample conformal coverage under exchangeability. Cumulative
quantiles are trained directly; they are not sums of marginal Q90 forecasts.

No synthetic jobs, burst classifier, eta, robust burst envelope, new external
source, May scientific query, shadow row query, optimizer/Gurobi/OpenDSS/Fresh
call, A0/A1/M1/MF change, migration/WAN/terminal change, event trigger, local
repair or rolling MPC is introduced. Metadata and sparse-checkout discovery
are separately disclosed in the May firewall artifact.
