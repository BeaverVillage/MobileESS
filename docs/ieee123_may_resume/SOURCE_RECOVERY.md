# Source and evidence recovery checklist

All paths below are relative to the missing historical campaign root
`IEEE123_RESITED_PRODUCTION_20260913`. They identify conversation-referenced
files; presence, completeness and hashes are **not verified by this PR**.

## Operational code and tests

```
resume_production.py
detached_entry.py
monitor_v41r4_resited.ps1
monitor_mess_compact.ps1
check_b3_readiness.py
check_campaign_date_transition.py
recover_completed_b1_archive.py
v41r4/v41r4_rho_certification.py
v41r4/v41r4_exact_cache.py
v41r4/v41r4_exact_runtime.py
v41r4/v41r4_exact_final_worker.py
v41r4/v41r4_exact_mess_worker.py
v41r4/v41r4_certification_state.py
v41r4/v41r4_b3_provenance.py
v41r4/v41r4_fresh_resume.py
v41r4/v41r4_archive_finalize.py
v41r4/v41r4_search_archive_scope.py
v41r4/tests/test_rho_certification_tolerance.py
v41r4/tests/test_certification_state_forensic.py
v41r4/tests/test_b3_runtime_readiness.py
v41r4/tests/test_fresh_resume.py
v41r4/tests/test_archive_event_finalization.py
v41r4/tests/test_search_archive_scope.py
v41r4/tests/test_resume_local_receipts.py
```

## Binding and validation evidence

```
manifests/AUTHORIZED_MAY_RESUME_CURRENT.json
manifests/rho_cert_tol_1e7/FINAL_GATE.json
manifests/b3_readiness_20260914_010509/RESULT.json
manifests/b3_fresh_completion_fix_20260914_0112/
manifests/date_transition_check_20260914_012505/RESULT.json
manifests/archive_stream_fix_20260914_0526/
manifests/search_archive_scope_fix_20260914_0726/
manifests/monitor_actual_display_fix_20260914/TOLERANCE_DISPLAY_CHECK.json
manifests/monitor_actual_display_fix_20260914/RESULT.json
manifests/monitor_actual_display_fix_20260914/LIVE_FRAME.txt
manifests/codex_independent/CAMPAIGN_ENTRY.json
manifests/native_artifact_repair/ADOPT_RUNNING_WORKERS.json
```

Also recover the frozen release manifest, relevant source/input identities,
candidate and full-vector certificates, original and archived K-stage receipts,
per-process exact-runtime events, and per-depth accounting. Large artifacts
should remain in controlled storage; commit only selected small evidence with
verified provenance.

Recovery order:

1. Locate original files or byte-identical backups. A later similarly named
   campaign is not sufficient identity evidence.
2. Resolve READY and frozen release bindings and verify source SHA values.
3. Preserve failure/retry lineage and original solution-vector identities.
   Missing vectors must remain missing, never inferred from scalar summaries.
4. Compare recovered implementation against an explicit Git base; include its
   actual dependencies and tests. Do not substitute this narrative for code.
5. Run relevant regressions without resuming scientific computation. Distinguish
   newly executed checks from historical reports.
6. Retain this handoff as historical context and update the PR's missing-source
   status only after the implementation is actually reviewable.
