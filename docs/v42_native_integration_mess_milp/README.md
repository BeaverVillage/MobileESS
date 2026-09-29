# V42 native adapters and MESS MILP

Stacked on Draft PR #90, base `87be27b68829afc2fb1e915c0ae26f3cbd787ccb`.
The implementation advances the native physical architecture, but **native scientific activation remains BLOCKED**. No native day or Fresh OpenDSS solve was run; native timing/gap cells are null. The preregistered day remains 2025-04-01, at most one day and 600 external wall seconds per block.

`v42_native` now provides complete-option AIDC MILP, full-service/tail accounting, joint MESS route/P/Q/SOC MILP, all-face grid row binding, uncertainty-envelope P2, provider protocols, bounded fixed-discrete Actual P/Q repair, and supervised A1→M1→A2→M2 coordination. A concrete frozen native backend/data bundle is still required. Synthetic workers exercise the solvers and warm starts independently; they are not a coupled native electrical canary.

Validation: 188 tests pass (including 39 unchanged PR90 tests); MESS production constructor has zero quadratic/SOS/general constraints and linear objectives. The bounded fixture retains travel energy, transit P/Q zero, SOC and terminal energy. Its old-circle-only comparison is conservative, not exact equivalence. All 2124 protected source/evidence files retain their hashes.

Read `FINAL_REVIEW_KO.md` for all 50 requested answers, `FINAL_FLAGS.json` for scope-qualified flags, `NATIVE_GATE_EVIDENCE.json` for unresolved authority versus unfinished final binding, and `PR79_RESOURCE_CONFLICT_ROOT_CAUSE.md` for the attempted reconciliation.

Reproduce from the repository root with Python, numpy, pandas, pytest and a licensed gurobipy installation:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
python -m pytest tests/test_v42_native.py tests/test_v42_job_capability.py -q --junitxml=docs/v42_native_integration_mess_milp/TEST_RESULTS.xml
python docs/v42_native_integration_mess_milp/audit.py
python docs/v42_native_integration_mess_milp/write_report.py
python docs/v42_native_integration_mess_milp/verify_delivery.py
```

The source audit requires the historical local artifacts listed in SOURCE_MANIFEST; they are read-only and are not copied or fabricated when absent. Unit tests need no historical dataset. `verify_delivery.py --write-manifest` refreshes the delivery manifest deliberately; normal verification does not rewrite it. No command above launches native/May/full IEEE campaigns or retrains ML.
