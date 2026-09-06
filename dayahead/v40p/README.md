# V40P forecast forensic

This namespace contains validation code and diagnostic clones only. The final scientific verdict is `V40P_FORECAST_CAUSALITY_FAIL`.

Read `dayahead/artifacts/v40p_lightgbm_forecast_forensic/V40P_FINAL_REVIEW.md` first. The May zero-read protocol failed because the initial source search exposed embedded scientific summaries in two V40I source files. No May outcome data records were decoded; do not present that narrower fact as complete zero-exposure compliance.

Python 3.11, LightGBM 4.6.0, pandas 2.2.3, numpy, scipy, scikit-learn, pyarrow, PyYAML. Exact runtime versions are in the test report.

Run the committed evidence checks without fitting:

```powershell
python -m dayahead.v40p.test_forensic
```

There are 35 checks: 32 pass and 3 remain expected scientific failures (#11 future features, #12 rolling right edge, #27 May reads). `OK (expected failures=3)` is a successful audit harness, not scientific approval.

The original execution order was:

1. `discover`: exact start commit and read-only source/artifact discovery. Do not rerun on the finished branch; its start-HEAD assertion is intentional.
2. `prepare`: frozen inference and preregistration, with no fitting. Do not rerun on the finished branch because it writes preregistration files.
3. Commit preregistration JSON and MD at `f0af75759bda4611734d44d4627bc84e0d76f164`.
4. `backtest`: 27 fixed-spec diagnostic fits, then metrics. Existing clone files are reused only after SHA/parameter verification. `registration()` checks the committed specification before and after work.
5. `job_audit`: raw pre-May job-identity and availability witnesses, with endpoint row-group guards.
6. `audit`: original feature/target reconstruction and lineage. Uses exact external source paths from `common.py`; never scans mixed May row groups and filters after decoding.
7. `finalize`, `test_forensic`, `finalize --review`: protection/firewall receipts, automated checks, Korean review.
8. Commit research outputs. Run `receipt` to bind those outputs to the research commit, then commit the receipt separately.

The external K5A input parquet and raw ZIP are not copied in full. Safe witnesses, frozen predictions, diagnostic predictions, model copies, source snapshots and numerical reports are committed. Full rebuilding needs the original source paths listed in the census and access log. Source snapshots are verbatim forensic evidence; their style is not rewritten.

Only these paths may change:

- `dayahead/v40p/`
- `dayahead/artifacts/v40p_lightgbm_forecast_forensic/`

Never modify the registered model specification, folds, candidate set, scales, thresholds, baselines or production consumers after seeing the results. Current V40A submitted-job planning does not invoke the legacy K5B2 horizon predictor.
