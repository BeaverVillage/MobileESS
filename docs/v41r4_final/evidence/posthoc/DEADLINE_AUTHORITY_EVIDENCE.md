FINAL_DEADLINE_AUDIT_CLASSIFICATION: C

DEADLINE_AUTHORITY_NOT_ESTABLISHED

## Authority boundary

All numeric results come from the one final raw tar.gz identified in the manifest. The entire compressed archive and every member were freshly streamed and hashed. Subsequent byte reads from the extraction cache were accepted only after matching that fresh per-member size and SHA256; this cache was used solely as a verified mirror of the tar archive. Existing reaudit CSV is used for cohort keys only. PR #42 at `33a86d31c27051aedbdb93d60b844216533a45a9` is used only for method semantics. Original upstream paths embedded in manifests were treated as provenance strings; no external workspace result was opened. The archive does not contain the original `V37_R4A_JOB_LEDGER.parquet`, `V37_R4A_D1_SNAPSHOT.parquet`, or `COMMON_INPUT_RECEIPT.json` bodies. Their construction is traced statically in PR source, not numerically supplemented from another workspace.

The four executable method files domain.py, migration.py, terminal.py and temporal_restore.py match the SHA256 in all 31 archived DAILY_DOMAIN_AUTHORITY files: 124/124 comparisons. Other PR sources below explain their lineage; they are not represented as separately hash-bound source files where that binding is unavailable. The user contract text is supporting method evidence in PR; archived hashes of the active implementations provide the execution binding.

## What the fields actually mean

| Field/boundary | Established meaning | Job-specific latest permitted completion? |
| --- | --- | --- |
| ISSUE_BEGIN=24, ISSUE_END=120 | Half-open D-day evaluation interval [24,120), 96 fifteen-minute slots | No |
| B0 reference completion | max end of same-day frozen B0 compute_segments | No |
| optimized/final completion | max end of final accepted DA compute_segments | Outcome, not a permission bound |
| RW_completion_slot | Completion of engineered requested-walltime reference scheduling, inherited from RW_scheduled_completion | Not established for checkpoint migration |
| RSP_start_slot | Current common Q90 reference earliest scheduled start, rematerialized under current capacity | Start reference, not completion deadline |
| safe_duration_slots/seconds | Frozen planned compute-service duration (PENDING current causal Q90; RUNNING requested remaining); segments preserve slots | Duration, not absolute due time |
| requested walltime / requested_seconds | Scheduler request duration; normalize converts wallclock_req to seconds | No archive-backed absolute deadline or interruption accounting rule |
| qos | Scheduler class/priority and flexibility eligibility input | No job-specific SLA end mapping found |
| state_at_issue | RUNNING/PENDING at the frozen issue cutoff; can differ from state at D00 | No |
| deadline/latest_finish/completion_deadline/reservation_window_end/SLA end/due time/eligible completion window | No usable job-level authority found in final job payloads or raw job request inputs | NOT_AVAILABLE |

Issue origin is D-1 18:00 fixed AEST, six hours before D00; it is a per-day relative issue coordinate, not Unix absolute time. Day-origin slot = issue-origin slot - 24. Thus 120 issue slots and 96 day slots denote the same evaluation end. See [dayahead/v41/data.py:39](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/data.py#L39-L49) and archived AIDC_FIELD_AUTHORITY.slot_origin. All 62 B1/B3 boundary audits independently confirm H=96, issue_begin=24, issue_end_exclusive=120.

## RW: eight required questions

1. **Full name/definition:** RW is the **requested-walltime reference/reservation mode**. The recovered scheduler contract defines it as `running requested-remaining; pending requested-walltime; tier/FIFO first-fit`. There is no source basis for expanding RW as an independently authorized “reservation window” or an SLA deadline. [dayahead/v37/aidc_materializer.py:831](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v37/aidc_materializer.py#L831-L844)
2. **Generation:** raw scheduler `wallclock_req` supplies duration; RUNNING uses max(requested minus elapsed, 900 seconds), PENDING uses requested duration. First-fit/tier/FIFO scheduling creates start/end slots, then the scheduled end is renamed `RW_scheduled_completion`. [dayahead/v37/aidc_materializer.py:390](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v37/aidc_materializer.py#L390-L412), [dayahead/v37/aidc_materializer.py:436](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v37/aidc_materializer.py#L436-L456), [dayahead/v37/aidc_materializer.py:560](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v37/aidc_materializer.py#L560-L573)
3. **Measured/raw field?** No. The request duration is a raw scheduler input; RW completion is a generated schedule output. The archived JOB_REQUEST_INPUTS schemas contain wallclock_req and scheduler state/resource fields, but no RW or deadline field.
4. **Engineering-derived window?** Yes as a reference schedule completion, and as a derived noninferiority upper bound for eligible standalone time shifting. It is not a universal migration completion permission.
5. **Generated from current B0 Q90 reservation?** No. `common.build` separately rematerializes current Q90 B0 scheduling and `RSP_start_slot`, while assigning `RW_completion_slot=int(row.RW_scheduled_completion)` from the preserved V37 ledger. [dayahead/v41/common.py:39](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/common.py#L39-L80) Current duration authority differs from the historical materializer's duration policy; no old Q90 values were imported as audit results.
6. **Absolute issue-slot coordinate?** It is an end coordinate in the common issue-origin slot axis, not a duration. “Absolute” here means a position on that axis, not a global timestamp.
7. **D-day coordinate?** No. Subtract 24 to express it relative to D00.
8. **Hard contract requiring every checkpoint migration to complete <= RW?** None established. In `terminal.start_bounds`, RW minus duration is an upper bound for eligible standalone shifted starts. The active migration branch preserves RW metadata equality but never compares migrated completion to RW. [dayahead/v41r1/terminal.py:59](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/terminal.py#L59-L74), [dayahead/v41r1/migration.py:87](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/migration.py#L87-L111), [dayahead/v41/temporal_restore.py:20](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/temporal_restore.py#L20-L35)

## Candidate generation and acceptance

**Checkpoint migration candidate generation directly checked a job-specific completion deadline: NO.**

`domain.options` calls `migration_options(..., allow_cross_midnight=True)` for the active migration contract. Candidate completion is `reference_end + transfer_end + 1 - checkpoint`. With cross-midnight enabled, the timing gate requires `transfer_end + 1 < H`, not `finish <= H` and not `finish <= RW_completion_slot`. Site/rack GPU eligibility and WAN capacity/path constraints still apply. [dayahead/v40g/domain.py:39](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L39-L57), [dayahead/v40g/domain.py:73](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L73-L88)

Materialization preserves compute service in two segments and encodes one-slot restart. `migration.check` requires fixed reference start and admission, deterministic first checkpoint, one migration, checkpoint < restart < 120, preserved immutable fields, and useful destination service before D24. RW is checked only for equality with the original metadata. `domain.audit` preserves total safe-duration slots, validates WAN transfers, and treats the reference tail as a service ledger rather than a cap. [dayahead/v40g/domain.py:102](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L102-L133), [dayahead/v40g/domain.py:140](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L140-L172), [dayahead/v41r1/migration.py:87](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/migration.py#L87-L111)

Standalone time shifting is a separate branch: a changed start cannot be combined with migration, and only that branch invokes terminal.check. Having an RW bound there does not establish a bound for the 677 migrated decisions. [dayahead/v41/temporal_restore.py:20](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/temporal_restore.py#L20-L60)

All 677 selected migrations were also matched to the archived per-job MIGRATION_CANDIDATES tables; all are marked migration_eligible and first-checkpoint-only, and those tables contain no deadline column. All 62 model boundary audits record terminal_residual_constraint_active=false and service_neutrality_constraint_active=false. No model was executed to perform these checks.

The frozen contract permits cross-midnight completion and explicitly deactivates per-job terminal residual and spill constraints. It requires useful in-day destination service. [dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt:363](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt#L363-L408), [dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt:820](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt#L820-L833)

## Diagnostic names that must not be mistaken for authority

Archived `AIDC_FIELD_AUTHORITY.json` says `completion_lateness_role: evaluation versus existing RW completion; not a new objective variable`. `actual_dispatch.py` uses a local variable named deadline and emits contention_caused_RW_deadline_miss, but the accompanying `SLA_debt_authority` explicitly labels this diagnostic lateness versus frozen RW. The local variable's name does not establish a scheduler-provided deadline. [dayahead/v41/actual_dispatch.py:118](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/actual_dispatch.py#L118-L131), [dayahead/v41/actual_dispatch.py:150](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/actual_dispatch.py#L150-L156), [dayahead/v41/scientific_archive.py:140](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/scientific_archive.py#L140-L168)

`deadline_overrun_noninterruptible_work_seconds` is a separate optimizer search-loop budget diagnostic, computed as max(0, elapsed search time minus the fixed search budget). It is not a job completion deadline. See [v41r4_loop_budget.py:46](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/v41r4_loop_budget.py#L46-L60) and archived SEARCH_LOOP_WALL_CLOCK_AUDIT.json, whose budget_basis is CONTINUOUS_SEARCH_LOOP_WALL_CLOCK.

## Archive search scope and findings

All 49,444 JSON members and all 10,640 Parquet members were included in the field search (identical content deduplicated by archive SHA256), along with archived source/text/CSV files. Total covered members: 60385; unique contents: 39085; content bytes read: 22538633111. Search covered deadline/latest finish/latest completion/reservation window end/SLA end/due time/eligible completion window aliases. Every canonical final job was separately recursively inspected, so the primary population check is not dependent on a text search alone.

All 124 JOB_REQUEST_INPUTS files, including metadata, were inspected. All 184,368 selected job-policy-day records have no explicit job-level deadline field. This is absence of archived authority, not proof that the physical scheduler never had any other contract. Compressed FULL_CANDIDATES first-record schemas were inspected for all 46 unique compressed contents; complete compressed candidate/model internals were not used to infer a job deadline. Binary physical arrays were not interpreted as scheduler authority.

JSON search findings:

- `contention_caused_RW_deadline_miss`: 292 archive members; 546640 key occurrences.
- `contention_caused_RW_deadline_misses`: 665 archive members; 668 key occurrences.
- `deadline_overrun_noninterruptible_work_seconds`: 335 archive members; 462 key occurrences.

Parquet deadline-like columns:

- `DELAYED_JOBS.parquet`: `contention_caused_RW_deadline_miss` (11606/11606 non-null diagnostic values)
- `JOB_DECISIONS.parquet`: `contention_caused_RW_deadline_miss` (179302/179302 non-null diagnostic values)
- `PHYSICAL_EXECUTION_DISPATCH.parquet`: `contention_caused_RW_deadline_miss` (367338/367338 non-null diagnostic values)

Every discovered deadline-like key is classified in the manifest's scan_review. No requested walltime, reference completion, optimized completion, horizon boundary, or diagnostic RW metric was substituted for an authoritative deadline.

## Source hash evidence

| PR source | SHA256 | binding |
| --- | --- | --- |
| dayahead/v37/aidc_materializer.py | 64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022 | PR42 lineage/supporting semantics |
| dayahead/v41/common.py | e21bde3188d1a246dbebfb50262c7722782ff2fa69b7e9b331ff2fba8a9d8a75 | PR42 lineage/supporting semantics |
| dayahead/v41/data.py | 796fccf3179be61a1ed4f315e41dfc1142f6993de807a9503e3c9b0eed9dd8f4 | PR42 lineage/supporting semantics |
| dayahead/v41r2/reference.py | 9b981c854575a6fe4777e52908be85d2f5edd927c655b8c417b57302c040c075 | PR42 lineage/supporting semantics |
| dayahead/v41r1/migration.py | c8908d56662dcb3820d90412dc1fa4a1094b73c95638938ff5096a4bdad37aff | 31 archived domain authorities |
| dayahead/v40g/domain.py | 0631175ce7a63379673dae0579baf213b82a9b06a43b17b73e51d7167337e6b5 | 31 archived domain authorities |
| dayahead/v41r1/terminal.py | 593721d7cc85512bf34b900255468473607550af4011c00de1c5fecafef44c41 | 31 archived domain authorities |
| dayahead/v41/temporal_restore.py | 7153a4cfafa33f5546348c1e0957475606957265a01dad8d38bdb719d9ba39b0 | 31 archived domain authorities |
| dayahead/v41/scientific_archive.py | ceb515edba2e4a8a8e66329dbaca34f090fe7731ad61477b58eee8defd680ef2 | PR42 lineage/supporting semantics |
| dayahead/v41/actual_dispatch.py | 27c4a59e5e237cee45ed4e26ed03eab8368b5e18afea552963cd3377264e82d9 | PR42 lineage/supporting semantics |
| dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt | 4f8c1ec09485f24c4ea959f3e1eeb1a6dc8f52aefbf59dd589abc5eb2891ecf0 | PR42 lineage/supporting semantics |
| v41r4_loop_budget.py | 68ae5b101db061979f04024bf5a33b2bcea819f14b56400dd8ff3a7194e9e28c | PR42 lineage/supporting semantics |
