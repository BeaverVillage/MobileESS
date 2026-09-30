# Exact root-LP sparse compression

Scientific base: PR102 `cd7e40762097b6c20303bd2238edf7ffeba87aa4`.
Recovered pushed science checkpoint: `a88879fdb4e6c51dae35656feee90f68ed19ad8f`.
Windows worktree is isolated from the ongoing environment rollback.

Implementation, bounded exactness and structural census ran during VHD compaction under the user's 2026-10-01 instruction. Structural build seconds collected during concurrent work are **not performance benchmarks**. The user subsequently confirmed rollback completion and explicitly instructed performance measurement immediately. `USER_ROLLBACK_COMPLETION.json` records that instruction. Timing still requires the actual successful 100% compaction receipt, sealed Windows runtime/preservation/restoration receipts and no active compaction or rollback workers; availability of the separate final rollback report files no longer blocks timing.

The six scientific objectives and complete physical domains remain authoritative. The final event-rank tie is a separate representative-selection policy. No GPU computation, IEEE8500 data changes, M1, A2, M2 or Fresh AC are authorized here.

`python -m v42_sparse.census` builds the complete original PR102 matrix without optimization. `v42_sparse.setup` was used once to record restoration and input receipts; it is an initial setup operation and must not overwrite this run's preregistration or preservation manifest. Evidence from the inherited WIP remains in its original directory.

F2-A uses only the measured F0/nonmigration-state substitutions. Its complete structural matrix equals the separately measured STATE variant, as recorded by the explicit structural alias. DA1/DA2/DA3 increased full-May nonzeros and LINK produced no full-May matrix improvement, so neither is included in final A/CRA. F2-CRA adds exact completion counts, certified staying histograms with individual migration lanes, existing lane-cardinality auxiliaries, and a power-of-two MiB conversion for WAN matrix units. Physical byte values and every capacity remain unchanged. Provisional all-auxiliary matrices are retained in `PROVISIONAL_ALL_AUX_STRUCTURES`.

Run `python -m v42_sparse.gates` and `python -m v42_sparse.real` for complete bounded and native equivalence; then `python -m v42_sparse.audits` and `python -m v42_sparse.freeze --performance-freeze`. Frozen Pareto candidates are measured sequentially with `python -m v42_sparse.diagnostic KIND`; `python -m v42_sparse.select` commits the preregistered choice before `python -m v42_sparse.production` validates the start and runs one cumulative 3600-second A1. `python -m v42_sparse.report` produces the final measured review. Diagnostic and production retries are rejected by persisted markers/receipts.

## Measured outcome

F2-CRA completed the continuous P1 LP in **100.56 s** (64,998 iterations); F2-A reached its 3,600 s limit without an optimal LP. The preregistered completed-LP rule selected CRA before production. The final full matrix has 7,449,002 columns, 9,126,514 rows and 53,621,850 nonzeros; Runtime completion plus count definitions total 2,521,610 nonzeros, down from 34,923,402.

The complete 1,499-job source start passed independent Runtime/CC4/WAN/gang/grid checks and was accepted by Gurobi. The first production MIP root relaxation took **86.83 s**, versus the inherited 1,557.90 s reference (17.94 times the observed time ratio). This historical comparison includes the new validated start and must not be attributed solely to one matrix family. P1 completed in 331.00 s with UB=LB=0.6715924043100266 and independent physical PASS. The final schedule has P1 UB 0.6715925043100266, the same P1 bound and relative global gap 1.488998154470192e-7, with independent physical PASS.

**P1 acceptance is achieved; all six lex levels are not complete.** P2 reserve shortfall reached its time limit inside the root LP, with incumbent 768.1501457253, bound 0 and gap 100%. Its root took 2,904.19 s and 420,473 iterations. Each level reported one root node; no branch-tree progression was observed. The four subsequent levels were not started. Total optimize-call wall was 3,601.3247 s, including a 1.3247 s native return overshoot within the preregistered 5 s grace. M1/A2/M2/Fresh AC were not run.

The standalone LP and fresh MIP bounds are slightly below the inherited PR102 root reference; the review reports the differences and does not claim an unweakened continuous relaxation. Integer physical-set and six-objective preservation have separate exactness evidence. Verification: 440 tests; 35 complete bounded cases across 13 successors; 21 full-native case/formulation solves with all 96 electrical slots.

`python docs/v42_root_lp_sparse_compression/finalize_receipts.py` applies the measured review addenda after the report generator. It reconciles full-build metadata, explains raw-versus-normalized global reserve categories, retains raw callback telemetry and adds clearly labeled native-log observations for delayed 1,200/1,800 s callbacks. Missing intermediate incumbent/bound/RSS fields remain null. It does not rerun optimization or change frozen solver sources.

New source/output directories preserve exact receipt bytes through `.gitattributes`. The inherited tests attribute file is frozen. On a fresh Windows checkout with `core.autocrlf=true`, restore only the new test's recorded LF bytes before immutable receipt checks: `python -c "from pathlib import Path; p=Path('tests/test_v42_sparse.py'); p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))"`. Its Python content is unchanged; inherited test bytes remain untouched.
