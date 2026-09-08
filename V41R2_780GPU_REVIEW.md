# V41R2 780-GPU capacity rebase review

This revision applies the exact 624-to-780 GPU vector, rematerializes the causal Q90 B0 reference, rebinds installed-capacity IT/PCC power, and regenerates the required May-04 operating-point electrical coefficients. It preserves the accepted first-improvement F&O implementation from PR #35, frozen ML models, logical rack/gang semantics, fixed B1 reference starts, and existing grid/WAN constraints.

## Acceptance: FAIL-CLOSE

Fresh B0/B1 passed. Actual fixed-decision replay, capacity checks, and persistence completed with zero reoptimization, but **both Actual physical acceptance checks failed** due to voltage above 1.05 pu. B0 maximum: 1.050726698 pu; B1 maximum: 1.050999114 pu. The affected nodes are bus 83 phase A and its connected MESS PCC. Full May remains HOLD and was not started.

The Day-Ahead B0/B1 P1 values are 0.525000724 / 0.520942774; P2 values are 1413.178297 / 1170.086271 GPUh. These improvements do not override the failed Actual voltage gate. B1 uses 27 prestart relocations and 10 checkpoint migrations; maximum WAN waiting is 16.25 hours and 1343 GPUh of compute service shifts beyond D24. The latter includes complete migration interruption, not a causal estimate of WAN waiting alone.

## Validation and provenance

The sealed pilot ran 360 tests: 358 passed and 2 failed. The failures are exactly the Actual B0 and B1 physical acceptance tests in `tests/dayahead/test_capacity_rebase_acceptance_outputs.py`. They are retained unchanged. All 4,772,575 candidates were independently re-enumerated. Combined optimization time, including the conservatively charged invalidated metadata draft, was 1778.794240 seconds against the 1800-second limit.

See `dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_780GPU_MAY04_ACCEPTANCE.md` and its JSON equivalent. That directory contains audit summaries, compact power/violation data, source snapshots, test logs/XML, and frozen hashes. Heavy `frozen_artifacts/` execution outputs and the invalidated draft remain local under the repository's existing output policy.

The evidence was generated in `D:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase`, before this PR packaging commit. Absolute paths and historical commit/hash references intentionally retain that provenance. The PR checkout is a separate worktree, preserving the sealed execution tree. Runtime integration tests depend on that local frozen-data environment and upstream V41R1/model/electrical repositories; this PR does not claim they are self-contained GitHub CI tests. No heavy simulation or optimization was rerun for packaging.

This draft requests review of the capacity rebase and failed acceptance evidence. It does not authorize Full May, change voltage limits, or claim production/campaign readiness.
