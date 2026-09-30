# V42 exact compact AIDC state-flow

Base PR98 `e9f9387769bd2500e48654d0aa1752ad7f7d6aa4`; preregistration commit `0af0d851`. All 334 available tracked base files remain byte-identical. The explicitly authorized new trigger is MODEL_CONSTRUCTION_FAILURE_AFTER_COMPLETE_DOMAIN.

The compact MILP separates start, checkpoint, source-ready wait, WAN transfer, restart entry and completion. Checkpoint and WAN start have no joint product index. Continuous [0,1] states are integral conditional on binary events by their zero-initial cumulative balance equations. Full service, exact checkpoint phase, deterministic WAN/restart, whole gangs and inherited carryout are preserved. The builder is shared by A1/A2; MESS is untouched.

All A-J synthetic fixtures match the legacy complete path set and six scientific objective levels. A deterministic real two-job subset matches with the full native grid and PR97 CC4 interface. The primary mapping audit tests 100 paths in each direction with zero failures; additional randomized/adversarial tests cover zero-rate WAN, fixed capacity, timing, gaps and fractional states. This bounded evidence and the mathematical proof are distinguished from a claim that every May trajectory was explicitly enumerated. The compact production path never loads or enumerates PR98's 349M trajectories.

Full sparse indices cover all 1,499 jobs (6 constant singleton schedules). Event binaries: **9,802,075**, versus **349,215,815** old trajectory indices: **35.6267x**, **97.1931%** reduction. y=569,882, q=590,221, w=6,910,461, f0=569,882, f1=1,161,629. These are full measured graph index counts, not an invented final Gurobi model size. r0/h/r1 contain 2,740,637 continuous state indices in total. Preparation=4.3827s; graph construction=4.1884s.

**Result: COMPACT_A1_PRESOLVE_TIME_LIMIT_DIAGNOSTIC_WRITE_FAILURE.** Build-only external wall=422.4070s, completed model=True. Actual completed/partial rows, nonzeros, memory and family counts are in MAY_COMPACT_MODEL_BUILD.json. No build time is labeled solve time. A1 optimizer called=True; no accepted native plan. The separate A1 canary has a 600s total budget including reconstruction of the same model; optimization receives the remaining time. M1/A2/M2 and Fresh AC are NOT_RUN, and no final response kernel exists. Problem 8 remains open.

The authoritative solve reached presolve and TIME_LIMIT (status 9), with no incumbent and no finite bound. Last presolve observation was 164.85055479999573 seconds. Writing the final diagnostic failed on `-inf`; the partial JSON and traceback establish status/no-incumbent, but exact final Runtime and nodes were not preserved and remain null. Diagnostic normalization and validation-budget retention are repaired and unit-tested; May optimization was not repeated. An earlier canary construction was interrupted before optimize to correct overly strict incumbent acceptance; both attempts and executed code versions remain SHA-bound. The completed build-only model and physical formulation are unchanged.

The dominant remaining event dimension is w, 70.5000% of event binaries. The user stop rule is respected. NEXT_EXACT_DECOMPOSITION.md prepares one exact Dantzig-Wolfe/branch-and-price design without executing it, pruning paths, approximating jobs or changing physical authority.

Verification: **421 tests pass**, with one inherited frozen calibration RuntimeWarning. No new ML, Runtime/Q50/gamma90, TS (1,024 candidates), CC4 envelope, 780-GPU capacity, grid coefficients, MESS, PCS, Event30 or local-repair changes. Live TS support remains the unchanged fail-closed limitation. FINAL_REVIEW_KO.md answers all 50 questions.

```powershell
$env:PYTHONUTF8='1'
python -m pytest v42_compact/tests.py v42_boundary/tests.py tests/test_v42_temporal.py tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_compact.verify
git diff --check
```

Local process receipts, graph indices and test XML are SHA-bound by LOCAL_EVIDENCE_MANIFEST.json. Do not rerun one-shot production folders or overwrite historical receipts. Final solver counts and presolved size remain null when unmeasured.
