# Runtime-vNext3 — adaptive Running Q90/Q95 bound

Read [Korean final review](FINAL_REVIEW_KO.md). This is post-May-exposure historical development, not untouched confirmation. Fixed underlying PR65 runtime Q90/Q95 forecasts are reused; Pending remains exact current production R0 in every arm. A single fixed logistic selector, trained only on mature prior Running OOS labels, selects Q95 for high-risk Running rows and Q90 otherwise. DEV/CAL froze threshold 0.10 as a **research-only** candidate; no candidate passed safety and reserve criteria. Production remains R0.

## Reproduction

Require the unchanged sibling folders `../runtime_vnext2_q95_operational_bound` and `../runtime_vnext_causal_tail` from PR66 base commit `9835f3b3a4dea6f34439f31e10773b3d2b2b8237`. No raw archive, local external model checkpoint, private scheduler module, or uncommitted parent cache is needed. Underlying prediction labels are reconstructed from committed exact job membership. `study.py` imports the frozen vNext2 utility module only for read-only input and metric helpers; it never calls parent model training or mutates parent files.

Use Python 3.11 with `REQUIREMENTS.txt`. To reproduce into a fresh sibling directory, copy only `study.py`, `test_contract.py`, `delivery.py`, `plot_results.py`, `.gitattributes`, and `.gitignore`. Do not overwrite this sealed delivery.

```text
python -m unittest -v test_contract
python study.py register
python study.py select
python study.py evaluate
python study.py audit
python delivery.py report
```

Freeze and audit JSONs use exclusive writes. Selector model coefficients and exact mature OOS membership are saved per issue. New selector training uses expanding previous OOS support, which is distinct from the unchanged underlying 180-day/14-day runtime temporal policy. All threshold/model choices are fixed before this run's new evaluation metrics, with already exposed May history explicitly disclosed.

The exact executable was `D:/ChatGPT/Mobile ESS 2/runtime_vnext_exact_environment/Scripts/python.exe`. Plotting runs only in the separate environment recorded in `PLOT_ENVIRONMENT.json`. After tests and independent review, `delivery.py package` writes the seal; `delivery.py verify` checks new delivery and both parent manifests. Git publication checks staged scope and committed bytes against the seal.

## Interpretation

- R0 latest frozen production exists for May only. No backward R0 replay is fabricated for DEV/CAL/April. Pending is therefore evaluated only on May and never modified.
- R1/R2/R3 Pending all equal R0. Their Running bounds are respectively Q90, Q95, and the exact selected Q90 or Q95. `nominal_quantile` for R3 records the source quantile per row, not a claim that the adaptive policy is a calibrated fixed quantile.
- Every selector training label satisfies prior OOS issue time and `job_end_time < current issue`. Latest observation per Job avoids repeated support; minimum support fallback is Q90. Feature transformation reads only the registered issue-available inputs; request/version ingestion provenance remains unverified.
- Bootstrap reports paired day and 7-observed-issue circular block 95% CIs (2,000 draws). Ratios, including missed-slot reductions, are recalculated within every draw; undefined draws would be counted. No actual evaluation draw was nonfinite.
- The May pointwise envelope proves that any binary selector has GPU coverage at most Q95's 89.4945% and overreservation at least Q90's 1.3996× walltime reference. These are diagnostic feasibility limits, not threshold tuning.
- Historical event-time interface only. No production replacement, optimizer readiness, or promotion claim. No optimizer/MESS/IEEE123/8500/Actual/OpenDSS edit or execution.
