# Runtime-vNext2 — Q90 vs Q95 operational bound

Start with [Korean final review](FINAL_REVIEW_KO.md). This is a post-May-exposure diagnostic follow-up to PR65, not an untouched confirmation. No new model training, architecture search, temporal change, calibration, or optimizer execution occurs.

R0 is the latest frozen production Q90 reference available for May. R1 is the exact inherited MULTI_QUANTILE Q90, R2 the exact inherited Q95. Pending uses total runtime; Running candidates use elapsed-conditioned remaining runtime. R0 Running is explicitly a naive total-minus-elapsed transport. Both state-specific decisions freeze to retain R0 because neither candidate meets DEVELOPMENT and CALIBRATION eligibility. This is not an assertion that R0 passes every operational gate.

## Reproduction

Use Python 3.11 with the versions in `ENVIRONMENT.json` and `REQUIREMENTS.txt`. The sibling `../runtime_vnext_causal_tail` evidence from base commit `d3ec564854f65f62b3587f49c857d2f86575ad2c` must exist. The study does not require raw data, original local model checkpoints, external scheduler code, or the parent's uncommitted cache: labels are reconstructed from its committed exact job membership. It only imports NumPy/Pandas and standard-library modules.

The delivered directory is sealed. To reproduce, copy `study.py`, `test_contract.py`, `review_addendum.py`, `delivery.py`, `plot_results.py`, `.gitattributes`, and `.gitignore` into a **new sibling directory** alongside the unchanged parent evidence. Do not run register/select/evaluate over this delivered directory. Outputs use exclusive creation for all freeze/audit JSON records.

```text
python -m unittest -v test_contract
python study.py register
python study.py select
python study.py evaluate
python study.py audit
python review_addendum.py
```

`select` accesses only DEVELOPMENT/CALIBRATION, and freezes separate Pending/Running choices before `evaluate`. The inherited May exposure is disclosed even though this run's evaluation metrics are subsequently computed. R0 has no verified DEV/CAL artifacts, so selection does not include a fabricated backward R0 replay.

The exact environment executable used here was `D:/ChatGPT/Mobile ESS 2/runtime_vnext_exact_environment/Scripts/python.exe`. Plotting uses a separate environment documented by `PLOT_ENVIRONMENT.json`; it cannot alter scientific choices. `delivery.py report` renders completed metrics without changing selection. `delivery.py verify` validates both delivered bytes and every parent delivery byte. Publishing also verifies the committed Git blob bytes against this delivery manifest.

## Scope and limitations

The training membership is inherited unchanged (180-day history, 14-day half-life, per-issue refit) and audited by row ID and Job ID hash for all 67 issues. Event-time feature availability is checked. Historical request-version and ingestion provenance remains unverified, and production replacement/integration is unsupported. Invalid labels are retained as unscorable and counted. All finite prediction rows are kept; no outcome-driven exclusions or quantile relabeling occurs.

Both .90 and .95 pinball losses are computed for every operational bound. A bound's .90 pinball score does not make that bound a Q90 forecast. Paired 95% CIs use 2,000 identical day/block resamples across compared candidates, with nonlinear quantities recalculated within each sample. The slot metric is a 15-minute, 24-hour runtime-origin occupancy proxy, not actual dispatch or an optimizer evaluation.

The parent frozen evidence is preserved byte for byte. No optimizer/MESS/IEEE123/8500/Actual/OpenDSS source or execution is involved.

See [independent review addendum](REVIEW_ADDENDUM_KO.md) for the registered selector's missing-preference-metric limitation and the additional finite-metric guard. All observed selection metrics are finite; the guard and frozen choice reproduction pass. The study is fixed historical evidence, not a prospective decision service. The addendum also provides paired CIs for percentage missed-slot reductions by recalculating the ratio within each resample.
