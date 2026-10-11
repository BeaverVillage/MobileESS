# Exact Forecast generation performance release

Epoch13 continues the scientific campaign introduced in Epoch12. Its only
scientific source edit is `v42_svr11/model.py`: precompute immutable, ordered
Forecast setter arguments and read each terminal's measurement arrays once.
Every original setter and readback guard remains. Fresh contexts, causal slot
prefixes, clock/settle calls, AUTO controls, perturbations, LDC math and physical
limits remain unchanged. No Actual inputs or solver decisions enter this cache.

Original execution SHA: `ec6a8a1a69164dfba4d2a110f9da06d36e7422ee6b2dc0f3f6b6e7e36ae27a95`.
Successor execution SHA: `bfb1b3f434d5d2a501ed613cda17fb483f0d787ba76a53396c01c4767c210b6b`.
Equipment SHA: `41c00f9b190d568b318284dfbc4a02ef27397eae69a27796cf17f6e64a9af75d`.

Validation covers all 31 Forecast dates and 2,976 ordered setter streams, plus
five complete 121-response comparisons: May01 slots 00/47/95, May16 slot47,
May18 slot51. All nine coefficient fields, native response arrays, controller
taps, queues, clock times and solve counts are bitwise identical. The actual
candidate generator produced an identical slot00 NPZ (121 fresh compiles).
Strict AST review rejects altered inputs, setter order, measurements, clock
calls, secants and helper wiring. The final regression suite passed 70 cases.

Sixteen interleaved probe pairs at May01 slot95 reduced median wall time from
0.164630 to 0.149158 seconds (9.4%); input-setting time fell 23.6% and measurement
time about 69.8%. These are bounded probe measurements under live campaign load.
Ordered full batches varied with concurrent disk/CPU work; May16 and May18 were
slower in those batches. No monthly speedup or global voltage-safety claim follows.

Other bottlenecks were inspected. Exact Fraction allocation already runs once
per input slot, NPZ fields already decompress once per load, completed native
owners already retire, and unused EventLog copies are already disabled. The
remaining repeated compile/installation, complete causal history and native
settling protect independent control behavior and are retained. Same-date
Forecast models remain shared between B1/B2/B3; policy optimizations stay separate.

Deployment pauses only the Epoch12 dispatcher. Healthy workers complete
naturally. The existing two Windows tasks then release the successor and admit
only qualified completed Source12 results/models, preserving original SHA,
runtime and failure evidence. Completed checkpoints retain the V2 model and LDC
contract fields. No earlier scientific epoch's plans or coefficients are admitted.
The strict handoff auditor follows the frozen direct-Actual contract: Actual96
is required; a postoptimization Forecast96 is not executed or labelled PASS.
All 124 campaign outcomes remain required, measured from the Source12 repair.

The release helper is retryable before its ready seal. Its pending gate leaves
the old monitor and healthy workers running until predecessor workers reach zero.
Only then can the ordinary singleton migration/watchdog start new workers.
The existing hourly heartbeat follows the same pending/ready transition.

`VALIDATION.json`, `GENERATOR_CONNECTION_VALIDATION.json`,
`INTERLEAVED_BENCHMARK.json`, `EQUIVALENCE.json` and `REGRESSION_70.json` hold the
evidence. Diagnostic scripts reproduce the bounded comparisons; their stored
paths deliberately identify original execution roots rather than relabelling
the evidence as an Epoch13 campaign outcome.
