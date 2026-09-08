# Final future-workload calibration revision

R6R1 evaluates an explicitly specified **85% workload-reserve service level**.
It is not an electrical or grid-security probability. H4/H24 alone receive a
new calibration layer. All base targets, features and B1/B2 L0 predictions are
read from the closed R6 authority without fitting or recomputation.

The user explicitly resolved the discovered label-latency issue: a residual
enters only after **both its full target day ends and its full-day GPUh label
becomes available**, strictly before the new issue. Membership is therefore
`max(day_end, target_label_available_at) < issue_time`. Partial-day windows,
TRAIN in-sample residuals, and immature eventual-runtime labels are excluded.

The only policy is full expanding OOS residual history. Initial DEVELOPMENT
residuals are OOS with respect to TRAIN fitting, though R6 used DEVELOPMENT for
configuration selection. Earlier CAL/EXPOSED residuals enter when mature. No
old residual is discarded or downweighted. For n eligible rows, use the
clamped kth order statistic where k=ceil((n+1)*17/20), without interpolation.
The correction is nonnegative and is applied to the frozen base Q90.

All scientific outcomes are computed after a committed preregistration.
CAL selection is committed before EXPOSED; a frozen NONE cannot be replaced by
an exposed diagnostic candidate. The raw-Q90 R6 skill limitation remains
explicit but is not an automatic eligibility gate for this new calibration
question. Static U0/U1/U2 remain comparison-only.

Completed execution commands use
`C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe`:

1. `python -m dayahead.v40r6r1.initialize`
2. `python -m dayahead.v40r6r1.preregister`; prefit tests; preregistration commit
   and receipt before any CAL candidate evaluation.
3. `python -m dayahead.v40r6r1.pipeline cal`; independent CAL result verification;
   selection freeze commit and receipt.
4. `python -m dayahead.v40r6r1.pipeline exposed`; one deterministic repeat of
   the entire calibration, with no repeat selection.
5. `python -m dayahead.v40r6r1.finalize audit`; final tests and scientific commit;
   `python -m dayahead.v40r6r1.finalize receipt`; receipt commit and read-only
   closure verification.

Do not rerun mutation stages as an exploratory experiment. Read-only command:

```powershell
& 'C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe' tests/dayahead/test_v40r6r1_contracts.py --closure --read-only
```

Daily calibration evolution is reported without smoothing in
`V40R6R1_DAILY_DELTA_SEQUENCE.csv` and the full parquet ledger. Availability
proofs enumerate every included historical day for each issue/horizon/base,
with full row counts and hashes of original row IDs. Metrics include pooled
positive coverage, equal-weight day coverage, supported-month stability,
conditional miss magnitude and two overreservation anchors. H4 rolling sums
reuse atomic work; they are not distinct service-work totals.

No optimizer/Gurobi/OpenDSS/Fresh call, synthetic future job, A0/A1/M1/MF,
migration/WAN/terminal/MESS change, event trigger, local repair or rolling MPC
is introduced. May/shadow scientific reads remain zero; metadata discovery is
disclosed separately. R6 and all inherited authorities remain immutable.

**Current-authority future-workload research closes with this revision,
regardless of success or failure.** No R6R2/R7, new horizon, model, classifier,
calibration family, or service-level search follows. Further work is deferred
until new data or authority. No optimizer integration is authorized here.
