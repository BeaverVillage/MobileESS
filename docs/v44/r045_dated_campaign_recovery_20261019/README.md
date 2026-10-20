# Dated campaign dispatch recovery (r045a)

The r044 controller's entry name caused the inherited r029 boundary detector to count its own newly launched worker as a foreign protected worker. Twenty-five cases were excluded and three prepared Actual dispatches failed before entering Actual; the old fail-continue controller then incorrectly presented terminal dispatch failures as a complete campaign. This was an operational admission failure, not a cross-date scientific input failure.

The new scoped admission retains the original protected-worker/coordinator terminal checks and requires the actual current campaign's live PID/creation-time lease, exact root, real coordinator entry and complete external resource-lock set. Only this lease's admitted current workers are excluded from foreign-worker detection. Every preparation and baseline case first checks the actual subprocess entry under the live lease. Nonzero worker exits or missing START/RESULT records now stop in INFRASTRUCTURE_BLOCKED rather than being excluded through the whole queue. Parallel Actual errors drain existing workers before releasing the coordinator lease.

All seven date manifests and all 28 original/restarted request authorities were checked against their day/issue axis, native SHA, planning and Actual bundles, traffic forecast, electrical inputs, initial Running/MESS assumptions and public descriptors. WINDOWS matches the native planning-eligible roster, which is intentionally smaller than the full known population. The independent-daily initial-state assumptions remain assumptions; no prior optimized day's state is imported.

| Date | Known UID count | Planning-eligible / WINDOWS UID count | Dated input and B0 projection |
| --- | ---: | ---: | --- |
| 2025-05-08 | 4904 | 4842 | PASS |
| 2025-05-09 | 3383 | 3381 | PASS |
| 2025-05-10 | 3494 | 3492 | PASS |
| 2025-05-11 | 3525 | 3469 | PASS |
| 2025-05-12 | 1937 | 1937 | PASS |
| 2025-05-13 | 1534 | 1529 | PASS |
| 2025-05-14 | 2018 | 2004 | PASS |

May08's original R0 reference contains one additional UID (8823590) absent from both the native and planning input rosters. Its original record is PENDING, UNASSIGNED and POST_H_ONLY, starts at slot 20001, has no accepted assignment/WAN or migration, and has no must-complete-by-H obligation. The adapter projects this reference-only row out of the lookup view while preserving the original file and every native job, original site/start, duration and CC4 allocator. Any missing native UID, duplicate UID, assigned or within-horizon extra row is rejected. All seven days' original B0 computations and conservation checks pass.

Three verified prepared handoffs (May08 B1, May09 B1 and May09 B3) are adopted with unchanged source manifests and SHA. May08 B1 predates sequence dispatch labeling; the sealed r045a entry adds only current dispatch metadata during adoption. Failed and unstarted attempts remain preserved. Use **python -m v44_week2_restart_r045a --run** with its sealed runtime authorization; the preceding immutable r045 driver is retained as provenance and is not the active entry.

Validation: 31 focused regressions, the actual 28-case state-adoption preflight, and actual worker subprocess admission passed. The resumed May08 B3 A2 now reports **A2_STRICT_PASS**, full physical feasibility, independently validated LB and certified gap 0.0. The original exact M1 result is unchanged. A2 retained 12.59800386428833 prior Native seconds and consumed 1.4139997959136963 new seconds (14.012003660202026 total), with its original 5400-second ceiling and tolerances. Full acceptance and the completed-stage checkpoint were replayed.

At the verified snapshot, May08 B3 is actively running M2 with one preparation worker; three cases are PREPARED, ten main cases are PENDING and fourteen baseline cases are BASELINE_QUEUED. The original sequence remains B1/B3 prepare one at a time, then healthy Actual/Fresh up to seven workers, followed automatically by B0/B2 date-ordered full cases with one worker. No final case Actual/Fresh PASS is claimed. The existing 8795 monitor reports RUNNING and retains its 14-row date × B0/B1/B2/B3 table.
