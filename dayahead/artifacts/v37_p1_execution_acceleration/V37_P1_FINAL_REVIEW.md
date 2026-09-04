# V37-P1 Final Review

V37-P1 is a science-neutral execution patch. It does not change K, beam,
seed, WorkLimit, solver settings, ordering, objective, MESS/AIDC limits,
voltage authority, or Fresh/OpenDSS behavior.

- Runtime profile: full MILP 65.791%,
  restricted solves 30.473%,
  screening 3.354%.
- Incremental fallback: 3560 logical repeated
  calls become 2160 cumulative unique calls;
  duplicate completed solves are 0.
- Saved-state equivalence: PASS.
- Focused pytest: PASS.
- Persistent workers preload immutable case context and construct a fresh model
  for every candidate; the dynamic-state leakage test passes.
- Local input staging: skipped because saved profiling did not identify I/O as
  material.
- Projected saved-fallback wallclock reduction: 39.642%.
- R2 artifacts are preserved, no partial final 24-PCC authority is frozen, and
  no May optimization was run.

Classification: `SCIENCE_NEUTRAL_EXECUTION_ACCELERATION`

`V37_R2_RESUME_READY`: YES
