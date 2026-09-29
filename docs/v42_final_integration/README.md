# V42 final interfaces — native activation blocked

The approved V10 Isotonic Q50 study provider reproduces frozen fold5 predictions exactly. CC4 lifetime GPUh now passes through a TRAIN execution-lag kernel. The new May-01 input still fails a **different necessary resource condition**, so the user-required gate stops before A1. No accepted native schedule, Fresh AC result, or final response kernel is claimed.

Implementation base: PR93 `c07a981299ab4d065e401cc86d0d93ccaa9be8e5`. Read-only runtime evidence: PR95 `b50a42439de9f1df05ab4b223c082d4b224394ee`. No wholesale merge, Runtime training, calibration-map refit, CC4 retraining, parameter search, or May Actual outcome access.

## Frozen results

| Quantity | Result |
|---|---:|
| Common Runtime population | 230,237 |
| Q50 MAE | 2.72735049 h |
| Q50 coverage (reference 50%) | 46.7874408% |
| Q50 aggregate time ratio | 0.853214958 |
| Matched fold5 prediction maximum error | 0 seconds |
| Runtime reserve gamma90, folds 1–4 only | 2.423057443558147 |
| CAL system overrun coverage | 90.0086806% |
| Fold5 reserve holdout coverage, no retuning | 91.2431319% |
| CC4 TRAIN lag kernel | 6,729 slots, sum 1 within floating precision |
| May nominal unknown work inside / after D-day | 3,697.092936 / 1,806.348536 GPUh |

Reserve coverage refers to each OOF submission cohort's system-wide concurrency on its validation interval, **not full-cluster reliability**. Historical site assignments are not invented. The kernel uses completed observations; right-censored observations contribute only observed concurrency up to each fold cutoff. See the calibration preregistration and temporal validation for scope and burden. Fold5 was previously exposed for intrinsic ML metrics but never used to select this reserve kernel or gamma.

The original preregistration is preserved. `PREREGISTRATION_AUTHORITY_ADDENDUM.json` records the subsequent explicit user decisions authorizing the matched fold5 study snapshot and the folds1–4/fold5 reserve split. These do not change the original ML fold membership or PR94/PR95 `NONE` conclusions.

## Why A1 must stop

At issue-origin slot 44 (May-01 05:00 AEST), 416 nominally live jobs require 443 GPU. With no authorized timeshift, any such job is computing unless suspended for its single checkpoint migration. Full service prevents a migrated job from finishing earlier than its unshifted nominal end.

Map each suspended job to the last slot of its transfer. For restart length `r`, suspension at `t` implies `last_transfer >= t-r`; `restart_end < H` implies `last_transfer <= H-r-2`. At one active transfer per slot there can be at most `H-t-1` suspended jobs. This permits arbitrary checkpoint waiting and any transfer duration; it does not assume immediate transfers.

Here `H=120`, so at most 75 jobs can be suspended at slot44. Even removing the 75 largest live gangs removes only 102 GPU. Therefore:

`443 - 102 + 454.2690275946556 = 795.2690275946557 > 780`.

The **15.2690276 GPU deficit** holds with zero achieved uncertainty reserve and without site, rack, checkpoint-eligibility, route, or electrical restrictions. Adding these restrictions cannot repair it. This is an analytic necessary-condition proof, independently checked against exhaustive small complete-option combinations; it is not a full A1 solve or a new timing benchmark.

The two earlier relaxed LP checks passed because they erased post-checkpoint service permanently. Their receipts remain intact. The final certificate retains the consequence of resumed full service and supersedes those loose PASS results. The old PR93 same-hour GPUh certificate remains byte-identical and is obsolete for this interface.

## Implemented interfaces and limits

`v42_final.runtime.FrozenQ50` loads only the matched fold5 model, preprocessing and frozen March31 mapping. Its availability is March31; it cannot run retrospectively at earlier events. Historic reproduction uses the corresponding original daily mappings. Five-fold intrinsic metrics are not advertised as deployment performance of one fixed mapping.

`v42_final.native.canonical_jobs` is the consumer view of the source-preserving bundle. It recomputes Q50 mass, carry-out and local checkpoint candidate masks. Inherited PR93 requested-duration forensic fields in the raw bundle are **not** current nominal authority; the exact field list is in `NATIVE_INPUT_FIELD_AUTHORITY.json`.

`EpisodeLedger` preserves full physical RUNNING occupancy past Q50 and returns capacity only after observed completion at a valid boundary. PENDING has no current physical occupancy. Migration requires an externally validated frozen checkpoint/WAN receipt. This component does not itself grant migration authority, process transfer events, activate Event30, or certify a native Actual replay.

`ForecastBook` replaces anonymous cohort work once per submission and closes unused anonymous cohorts at the hour boundary. The delivered native depletion ledger is the D-1 initial state; event tests validate updates without opening May Actual jobs.

`bind_headroom` supplies linear, separately reported runtime/CC4 reserve shortfalls in P2. Reserve is never electrical load or an Actual add-on. The adapter is tested on constructed models; no May full optimizer binding was executed because the necessary condition fails even when both reserve achievements are zero.

A1/M1/A2/M2 stats and gaps are `null`/`NOT_RUN`. The configured future canary cap is 600 seconds per optimize call with MIP gap0.001. Existing MESS route/P/Q/SOC and inner16 code remains unchanged and regression-tested. Native scalability, accepted placement, Fresh AC and final response-kernel authority remain open. Do not launch a campaign or relax trust, epsilon, service, capacities, TS support or WAN/restart rules to force a pass.

## Verification and reproduction

Run from this checkout:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_final.verify
```

The first command exercises new contracts plus inherited complete-option, carry-out, MESS and security tests. The second verifies byte/hash authority and saved results without inference, fitting, or repeating fold5 reserve validation. `calibrate_reserve`, `freeze_provider`, and certificate materialization have one-shot guards; do not delete their seals to rerun or retune. Large local arrays and diagnostic LPs are SHA-bound in `LOCAL_EVIDENCE_MANIFEST.json` and are not uploaded as a replacement dataset.

See [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md) for the 50 requested answers and [FINAL_VERDICT.json](FINAL_VERDICT.json) for the machine-readable scope.
