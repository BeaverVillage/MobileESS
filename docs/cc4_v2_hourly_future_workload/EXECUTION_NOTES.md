# Execution notes and scope

These implementation issues occurred **before historical forecast evaluation**.
They did not cause target, split, architecture, hyperparameter or calibration
rule changes. Original failure logs and pre-fix code/partial fits are preserved.

1. `prepare_attempt01_failure.log`: pandas 2.2 requires conversion of NumPy
   string scalars before `Timestamp`. Fixed by `str(day)`.
2. `prepare_attempt02_failure.log`: Windows CP949 default could not read a UTF-8
   source path. Explicit UTF-8 reads now preserve Korean paths.
3. `failed_attempts/training_path_io/`: LightGBM's native model-file interface
   could not write the resolved Korean path. Python UTF-8 model-string I/O
   replaced native filename I/O, following the PR #59 approach.
4. `failed_attempts/training_support_check/`: a stricter-than-inherited assertion
   rejected negative pre-projection Q50 values (28 development hours, minimum
   −0.2374787194 GPU·h); this was **not merely numerical roundoff**, despite the
   historical diagnostic filename. The existing PR #59 nonnegative support
   projection was restored, as permitted by the registered support rule.
   Every LightGBM inference now records negative values and quantile crossings
   in `SUPPORT_*.json`. This is not upper-cap clipping. Q90 had no negative
   values in the failed development pass.

All final scientific code was frozen after those fixes and before successful
baseline/neural selection and historical evaluation. All registered neural runs
completed without OOM or GPU failure; no evaluation dates/hours were removed.
The successful `FAILURES.json` is empty and is separate from these preparation
and initial baseline failures.

The final report received an editorial interpretation paragraph after automatic
generation. It explains the existing numbers and estimator definitions; it
changes no prediction, metric, selected model, calibration or decision.
The paired bootstrap's calibration-error estimator is
`abs(mean(seed/day coverage)-0.90)`. `SEED_MEAN_METRICS.csv` instead averages
the per-seed absolute calibration errors. These nonlinear summaries need not
coincide. Pinball and requirement ratio use matching equal-day/seed populations.

No optimizer or production imports/executions occurred. The git change scope
is exclusively this new directory. Previous frozen evidence is retained byte
for byte in the parent commit and separately hash-verified locally.
