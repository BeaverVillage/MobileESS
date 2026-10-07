# PR134 accepted A1 exact compression

Base: `52ef855a59144a7c561df44b81dc2ad265babdbd`. Scientific inputs, source, accepted freeze and raw point come exclusively from the accepted 1,499-job/96-slot PR134 attempt. PR150/151 input reconstructions are excluded. Generic matrix proof code is replayed against this newly frozen PR134 matrix.

Gates: accepted full-variable axis identity and every original row/bound/type/lock plus independent physical checks; recomputed raw census; native read-only presolve; exact projection proofs and independent verifier; accepted witness mapping/reconstruction; exhaustive fixtures and adversarial tests; candidate presolve and >=15% size gate; exclusive scientific optimizer inventory before each optimize.

A1R uses certified zero fixing, row intervals and duplicates. A2SC adds +/-1 zero-RHS equality contractions, exact resource bounds, and proportional/dominated rows with exact power-of-two normalization and independent rational implication proofs, with no density-increasing substitution. Unsupported general domination, rank, semantic state pruning and non-unit affine elimination remain UNKNOWN_KEEP. Every permanent deletion requires a full-LP certificate, preserving all six model-defined expressions and the four executed objectives. The witness is never a domain pruning proof.

If gates pass, exactly one sequential short P1 MILP per A0/A2SC, native TimeLimit=300 seconds, Method=1, Threads=1, Seed=20260929, MIPGap=.005, native Presolve/Cuts/Heuristics/NumericFocus and original feasibility tolerances. Identical raw accepted starts are mapped only after validating them. No parameter sweep. Setup/build time is reported separately; the solver runtime is capped at 300 seconds per arm. No automatic cap extension.

Selection requires exactness and actual >=15% root relaxation time/Work reduction, or >=15% observed peak RSS reduction, or >=15% faster independently validated incumbent / same objective and gap. If an arm does not complete root, no root speedup is inferred from elapsed time. Bound and gap require a valid native incumbent and independent original-row replay. Sampled memory is reported as observed, not an exact peak.

Latest user's two-phase instruction also permits meaningful model-build benefit. Before any benchmark, this is fixed as >=15% and >=10 seconds less setup time with identical materialization method. Incumbent-time benefit requires >=1 second absolute improvement in addition to >=15%, avoiding selection from trivial accepted-start processing jitter.

One paired full four-pass comparison is permitted only after a measured qualifying root/memory benefit and no other active scientific optimizer. It uses PR134's four objectives and original cumulative 3600-second budget per arm; it is not triggered by model-size savings alone. Otherwise full A1 is not run.

RAM/commit/paging are read-only telemetry. No resource thresholds, kill, waiting or parameter adaptation. The other-optimizer gate tests actual scientific solver activity, not unrelated monitoring Python processes. M-stage and prior campaigns remain stopped.
