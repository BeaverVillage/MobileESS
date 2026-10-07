# Reproduce and inspect the rescue diagnostics

Scientific base is PR134. The implementation base is exact PR163
`fe0f5cf253bb08e3f96fe1e2c0af677e8b541144`. This package is experimental;
it does not freeze or adopt `ADAPTIVE_MINIMAL_PRESCREENING_V1`.

The four requested CSVs exist under this directory on the task host. Git stores
their lossless `.csv.gz` representations because the May19 CSV exceeds the
GitHub per-file size limit. `ARTIFACT_ARCHIVE_INDEX.json` records gzip and
uncompressed SHA256/size. Decompress the corresponding gzip to obtain the exact
required CSV filename; never reconstruct only a sample of lazy blocks.

The original source/input/static authorities remain at
`C:/v42_b1_may17_may19_repair_20261007` and
`C:/v42_pr134_sc_execution_20261007`. Restricted native matrices, row/column axes,
raw Farkas arrays and raw unrounded native points are preserved at
`C:/v42_b1_adaptive_prescreening_rescue_20261007`. Reports reference exact file
SHA256. The original production byte manifest and source closure are audited.

The pool generator never creates a native MILP. The independent pool verifier
prices every logical option and checks causal timing, class counts, service,
GPU/rack capacity, immutable occupancy, WAN payload, fixed WAN and transfer
concurrency, restart and carryout. Migration blocks contain every transfer start
and are lossless; the representative is not an approximation or pruning rule.

Large projected-objective JSON is likewise preserved as exact gzip. Its `.json`
file records `lossless_gzip`, compressed/original SHA and roundtrip PASS. Decode
that payload to inspect every coefficient; this avoids a multi-million-line
generated diff. The original case JSON and all objective forms remain unchanged.

`build_only` snapshots one restricted full model before any optimize call.
`solve_snapshot` verifies snapshot hashes, creates fresh LP then MIP with zero
objective and original settings, and replays all rows/bounds/integrality and
independent physical interfaces. It refuses duplicate tests and concurrent
heavy optimizers. No point, basis, warm start or previous native clock is loaded.
Each LP/MIP diagnostic has a preregistered 600-second native limit.

`compress_static` regenerates the existing exact reduction against this specific
expanded matrix. The original independent verifier replays every implication,
both LP directions and all four objective projections. It performs no optimize.

`physical_support` forms a signed combination of unchanged rows and a complete
physical-path support lower bound. `verify_support` recomputes the global
combination and an independent graph-path superset lower bound without importing
the generator or optimizer. No floating residual is ignored. This is an integer
physical contradiction, not an LP status or full-universe infeasibility proof.

`support_select` uses exact necessary cover bounds and exact Pareto dynamic
programming to select a small next same-site batch. `verify_cover` separately
recomputes all breaking effects and proves its rank/class/option/displacement
bounds. These are conditional single-certificate bounds, not the minimum of the
entire scientific MILP. The deterministic unique tie is not certified.

`minimum_probe` includes ALL physical same-site options of an earlier rank in a
necessary GPU-prefix outer relaxation. Neutral options are used only for this
lower-bound proof and are never added to the production model. The six earlier
rank rays are independently checked by `verify_minimum_prefix`. A strict better
domain probe ending at TIME_LIMIT is UNRESOLVED and blocks minimality.

Normal four-pass A1, Planning freeze, fixed Actual and Fresh OpenDSS remain
blocked until BOTH dates pass full integer feasibility and independently proven
domain minimality. No Actual/PQ repair, P2, B&P, May10/May12 optimization,
parameter sweep, memory policy or recurring Windows task is introduced.
