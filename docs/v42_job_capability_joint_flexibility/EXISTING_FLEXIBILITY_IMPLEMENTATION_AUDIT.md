# Existing implementation audit

PR [#75](https://github.com/BeaverVillage/MobileESS/pull/75), head `2330558cd98bb7ff8ddeb5baff3c454d1025142d`, is the historical baseline. Its registration, rule audit, final Korean review, funnel, delay distributions, cohort table, and all R0/R1/R2 membership tables were read. `R0_REPRODUCTION.json` recomputes the gate and bounds for 47,009 published records without invoking May policy evaluation.

| Definition | Job-days | Day-D GPUh | Day-D GPUh share |
|---|---:|---:|---:|
| Stored standby gate | 18,588 | 143,867.50 | 28.760644% |
| Restored production temporal domain | 4,767 | 52,192.75 | 10.433886% |
| Published standalone fixed-other-job witness | 1,611 | 17,273.50 | 3.453156% |

The denominator is 500,223.50 admitted Day-D GPUh; the job denominator is 47,009 job-days. The third quantity is additional conservative analysis, not jointly executable production dispatch. We reproduce its published membership aggregate, not rerun that resource screen. None is an optimizer-selected action share. PR75 normal cohort additions reached no extra executable domain under the old D24 rule; this does not prove intrinsic normal-workload inflexibility.

Audited native sources (exact paths and hashes in SOURCE_MANIFEST):

- `dayahead/v41r1/migration.py`: initial placement independently available to admitted in-day PENDING, fixed starts in V4; one first-checkpoint migration, full destination remaining work.
- `migration_admission.py`: frozen unadmitted jobs have separate backlog accounting and no physical IDC; they must never be converted into zero-service admitted jobs.
- `terminal.py`: issue origin 24 corresponds to D00, end 120 to D24; per-job terminal residual cannot increase for restored temporal options.
- `dayahead/v41/temporal_restore.py`: restores standalone start/site choices and explicitly rejects `NEW_TEMPORAL_MIGRATION_COMBINATION_FORBIDDEN`.
- `dayahead/v40g/domain.py`: whole options, fixed path/full-rate WAN, transfer pause and one 15-minute restart; latest V41 migration permits compute carry-out but requires useful destination compute before H.
- PFR migration JSON and `docs/IDC_MIGRATION_DATA_AUTHORITY_V1.md`: all-12 prestaging and checkpoint payload are modeled. Older PFR uses 300-second steps and five-minute restart; this is not silently substituted for V42's 900-second control grid/one-slot restart.

Latest local V42 implementation is under `v42_integrated_pr/v42`, not V41R4. `canonical.py` dispatches A1→M1→A2→M2 through a supplied backend factory. `checkpoint_planning.py` clones domain/prescreen/block functions for A1/A2 with the unified elapsed-phase checkpoint generator. `blocks.py` constructs complete-option binaries and full-tail GPU/WAN rows. `joint_mobility.py` constructs joint movement/P/Q/SOC flow with quadratic PCS constraints. `aidc.py` is an earlier bounded exhaustive reference search and does not replace the canonical block.

The shared planning implementation is identifiable and SHA-bound, but the native backend/grid objective callback is not uniquely frozen and ready in the inspected evidence. `canonical.py` requires native preflight before running. No new native binding is claimed. This is a production stop condition, not a reason to avoid modular synthetic validation.

`domain.start_bounds` still uses the PR75/D24 temporal rule. We do not reuse it as the new service authority. PR79 episode continuity also has unresolved pending reservations and capacity violations. `V42_SERVICE_BOUNDARY_AUDIT.json` records NOT_FINALIZED. No prior code/evidence was changed.
