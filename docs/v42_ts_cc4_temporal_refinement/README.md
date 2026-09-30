# V42 TS and CC4 temporal refinement

Base: Draft PR96, `d9787338fa5995a62628b9a2958bae60e7411ded`. The preregistration was committed before May capability and resource evaluation. All pre-existing files, including the negative PR96 certificate, remain unchanged. Supersession is recorded only in the new receipts.

The hierarchical empirical wait rule still grants **0/1,605 TS jobs and 0% nominal GPUh**. All 1,395 PENDING jobs fail support even at L4; their conditional counts are 3, 8 or 50, below the frozen minimum 100. Waiting ages range from 120,931 to 291,228 seconds. Backoff repairs the sparse-cohort interface but cannot manufacture historical observations for these old pending jobs. No further rule relaxation or target share was used.

The CC4 timing envelope uses **3,748 completed TRAIN submission-hour cohorts**, Q10/Q90 only, and 6,731 supported lags. It excludes 21 incomplete cohorts and four zero-work cohorts. No monotonic correction was needed. The original execution-lag kernel remains the soft nominal reference, with the original mass and bytes preserved. See [the service contract](CC4_SCHEDULABLE_SERVICE_CONTRACT.md) for GPUh conservation, reserve timing, carry-out and objective order.

The new **diagnostic necessary condition passes**, including a simultaneous anonymous-service LP under the complete active cumulative envelope. Its maximum independent slot lower bound is 509 GPU at May-01 23:45 AEST: known lower bound 509, minimum anonymous service in that individual slot 0, TS relief 0, excess 0 against capacity 780. Individual slot minima need not be simultaneous; the separate saved LP witness proves the anonymous part can also respect all slots jointly with the relaxed known bounds. This pass is neither full A1 feasibility nor an accepted plan. Runtime/CC4 achieved reserve is relaxed to zero only in this diagnostic.

The old `795.2690276 > 780` at 05:00 is byte-preserved in `docs/v42_final_integration/`. Its new receipt status is `SUPERSEDED_BY_TS_AND_CC4_TEMPORAL_FLEXIBILITY_INTERFACE`.

Native canary results and the exact subsequent blocker are recorded in [FINAL_VERDICT.json](FINAL_VERDICT.json), [A1_MODEL_STATS.json](A1_MODEL_STATS.json) and [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md). Missing native model/solver measurements are null, never borrowed from the small diagnostic LP. No response kernel is authorized without an accepted four-stage plan and matching Fresh AC.

Reproduce empirical receipts only in a fresh output directory/checkout; one-shot guards prevent silently overwriting their seals:

```powershell
$env:PYTHONUTF8='1'
python -m v42_temporal.timeshift
python -m v42_temporal.envelope
python -m v42_temporal.resource
python -m v42_temporal.canary
```

The TRAIN parquet and frozen native source files are local evidence, with hashes in the manifests. Reading the committed CSVs and JSON does not require inference or training. Verification:

```powershell
$env:PYTHONUTF8='1'
python -m pytest tests/test_v42_temporal.py tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_temporal.verify
git diff --check
```
