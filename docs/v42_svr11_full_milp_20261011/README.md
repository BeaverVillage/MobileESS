# SVR11 U4 then unrestricted C3A MILP release

The shared M engine now preserves its independently replayed FULL incumbent and continues with the original unrestricted C3A MILP, using that incumbent as the MIP Start and only the remaining portion of the cumulative 1,800-second stage budget. B2 M and B3 M1/M2 call the same implementation. A1/A2 algorithms and their 5,400-second budgets are unchanged.

Every original row, objective, bound and integer type is checked against the rebuilt model. Phase 2 adds no Hamming cut or fixed binary neighborhood. Solver bounds remain diagnostics unless an original-problem independent certificate has been verified. A solver-only OPTIMAL status does not certify the Global Gap. Better candidates require the existing literal C3A/FULL integer and physical replay. A missing, worse, numerical-error or memory-error result cannot replace the incumbent. Unknown Native Runtime is reported as unknown and quarantined; its known prefix is preserved separately.

The candidate also routes V2 SVR11 electrical certificates to their existing strict loader. This removes the pre-Native `KeyError('operating_day')` caused by the legacy NPZ loader. It adds actual process/system memory observations and defers new B2 workers when RAM or Windows Commit admission fails.

The former Source14 development B2 results, optimizer logs and performance summaries were discarded under the user deletion request. Source13 Forecast generation and input/model provenance remain separate. Validated May01/02/03 Forecast models may be reused by the user's correction; all B2 optimization dates restart from May01 with new Native-zero attempts.

The historical Forecast and source transition authority is preserved in `FORECAST31_READY.json`, `OFFICIAL_EPOCH14_READY.json` and `WINDOWS_TASKS_RELEASE.json`. The official science SHA is `7d500e43d6b6fbd1b148918bada3c7533b1ee6eb070ef732a62dd2cb4904922c`; the manifest pins commit `8d1f35a623261e5fd4b7b6c69055322089952276`. Subsequent user cancellation discarded the old B2 campaign; its launch and result snapshots are not current execution authority.

The earlier failed-B2 deletion attempt was blocked by automatic policy. No files were deleted or space recovered by that attempt. The user's latest correction excludes Forecast models and model inputs from the old deletion plan.

`tools/prepare_svr11_epoch14.py` gates release on all31 independently checked Forecast models, natural worker exit and both real FULL MILP continuations. It preserves coefficient bytes and generation provenance, independently carries forward B0 only, starts all B2/B1/B3 dates in an empty policy namespace, and sizes M memory reservations from observed peak RAM/Commit. The existing Source13 policy hold remains intact.

The broad 240-test run initially passed 235 tests and exposed five obsolete cache-review expectations. Tests were repaired to distinguish the older LDC science from reviewed equivalent caches; the 64-test affected/shared-engine/V2/release-gate run passed. Both original and repair logs are preserved. Six additional user-handoff checks reject pending/reused runs, uncertified early termination, incorrectly labelled bounds and incumbent regression. `tools/verify_svr11_b2_first3.py` performs the actual independent FULL/Actual96/SHA/Native checks before the requested three-date handoff. These unit results do not replace real validation or a production date PASS.

The prior B2 continuation measurements and incumbent/UB/LB/gap/memory evidence were deleted. Minimal final Native Runtime/status and exact deletion counts remain in the separate stop audit. Mathematical equivalence records and source identifiers are preserved without reusing old performance.
