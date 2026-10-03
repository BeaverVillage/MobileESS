# M1 exact formulation strengthening from PR136

Base: Draft PR136 exact `37ffd404e7d0d598ddb84fec084e3ac332ed99c0`.
Branch: `codex/v42-m1-exact-formulation-strengthening-v1`.

**Selected: BASE. No material strengthening certificate; no MIP canary or May production.**

The existing single-thread continuous primal vector is reused after its exact
model axes, full-row feasibility and objective are verified. Reference root LB
is 0.5687116103498322; the reused primal objective is 0.5687116107773678.
All 208,312 binary columns are classified. The 138,644 fractional columns
include 131,350 movement arcs, 6,910 stay arcs and all 384 charge modes.
377 unit/slot states split across sites, with up to 24 sites at once.

| Candidate | Baseline violation | Optimal LP objective | Decision |
|---|---:|---:|---|
| CUT_A | 254, max 13.368823 kW, all A3 | 0.5687116104305803 | Material gate fails |
| SOC envelope (without unselected A) | 18, max 5.124232 kWh | 0.5687116102532198 | Material gate fails |
| SOC flow | Exact native bounded prototype and matrix gate pass | NULL: 300s TIME_LIMIT; no primal vector | Inconclusive; not adopted |

A/B's approximately 1e-10 objective differences are numerical variation.
They cannot establish an objective-level cause of the relaxation gap. The
SOC-flow matrix adds 207,928 continuous columns, 443,344 rows and 2,559,730
nonzeros (+30.30%). Its final barrier log is diagnostic; the printed primal
and dual values are not accepted as root bound certificates.

All original rows, names, coefficients, RHS, senses, columns, bounds, binary
semantics and P1/P2 objectives remain unchanged. A uses redundant integer-valid
aggregate cuts. B uses exact interval unions on the frozen DAG, backward
terminal reachability, and explicit transit states. C adds one continuous
departure-energy commodity per original arc; original scalar SOC rows are
retained. Proofs and rational/native exhaustive projection tests cover the
continuous primary domains, rather than only a grid of power samples.

The zero-action reference 0.6715884801665905 is diagnostic only. Selected
diagnostic gap remains 15.318438725%. It is never a new UB certificate.

Execution: baseline fresh LP=0, candidate LP calls=3, gated 600s MIP=0,
1800s production MIP=0. Gurobi Threads=1 and four BLAS/OpenMP environment
limits=1; scientific optimization and pytest are sequential. LP parameters
are exactly inherited from the prior continuous LP, including its 300s cap.
No retries, horizon/domain/rating/objective changes or parameter sweeps.
The initial Windows Unicode absolute log-path preparation error occurred
before optimize; its log is preserved. ASCII relative paths fix logging.

Campaign sources and the 1,458-stage dry plan remain byte-identical to PR136,
and the freshly built semantic plan is identical. Campaign optimizer/Actual/
Fresh AC calls are zero. Full pytest includes existing bounded synthetic
orchestration and retains its native import exception traces in the log.

Read [the ordered Korean review](FINAL_REVIEW_KO.md),
[selection](M1_STRENGTHENING_SELECTION.json),
[verification](VERIFICATION.json), and [manifest](SHA256_MANIFEST.json).

Implementation is in `v42_strengthening`. Scientific stages have external
exclusive started markers in `../STRENGTHENING_LOCAL`; **do not rerun them**.
Read-only postprocessing is `python -m v42_strengthening.postprocess`.
Post-heavy tests are `python -m v42_strengthening.testing -q`.
Post-test verification/report is `python -m v42_strengthening.finalize`.
These commands never register or execute a production campaign backend.

One next hypothesis: exact route/location-conditioned PCS and grid epigraph
coupling, motivated by fractional spatial pooling. No additional experiment
is included in this task. Problem13 FINAL_VALIDATED remains false.
