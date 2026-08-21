# Conversation C Stage 7 — R12 representative-week refreeze

R12 supersedes only the calendar-month decomposition of the earlier Stage 7
plan.  It adopts the frozen K=12 representative weeks at PR #3 commit
`bfbbc7cb4bc03c131f4c26df82c7c55d231cbfc8` because the user explicitly made
that commit the new experiment-period authority after the original Stage 7
prompt was issued.

No representative-period selection is rerun here.  The three files under
`frozen_authority/` are byte-identical copies of the files at that commit.

R12 requires, before any Stage 7 Gurobi/OpenDSS execution:

1. all authority hashes and temporal axes pass `validate_r12_authority.py`;
2. a common 2025 exogenous authority/cache is bound once, then source coverage
   is proved for the 12 independent 2-day burn-in windows only, including every
   H54 forecast target used by their 6,912 controller issues;
3. the existing no-future-actual, h0-only commit, global certified gap,
   numerical, and Fresh Exact OpenDSS gates remain unchanged;
4. common-cache materialization may checkpoint in bounded shards, but each
   required absolute burn-in issue is generated at most once; per-week artifacts
   are slice manifests, not twelve restarts of the heavy source pipeline;
5. no 365-day run, 12-calendar-month materialization, 11 month-boundary test,
   or old 132-lane E7B matrix is launched.

The four stress periods remain separate zero-weight episodes.  They are not
silently mixed into representative-week weights or Stage 7 primary results.

Stage 7 stops at each representative week's evaluation-start state.  It does
not execute the following 2,016-step evaluation.  The 7-day bounds remain in
the frozen PR #3 input only so downstream result generation uses the same
periods.

The source preparation path preserves the exact R10 two-phase numerical order:
12 frozen 576-origin traffic blocks are created before E3/E4 is loaded, then
the 6,912 required issue artifacts may be materialized into the shared CAS.
Lazy E3/E4 prefetch is an optional performance optimization, never a Stage 7
scientific PASS condition.

The issue-artifact phase uses one frozen E3 GPU producer and up to 14 real CPU
processes for E4/metadata/compression.  Traffic generation runs in a separate
Python process.  The E4 process pool is forked before the parent loads E3 onto
CUDA, so the children share the frozen E4 authority by copy-on-write and never
inherit or replicate a CUDA context.  Workers may finish out of order, but
the authority index is committed strictly in issue order.  A restart first
quarantines any temporary or unindexed artifact and resumes only from the
SHA-verified committed prefix.  This does not duplicate CUDA models or change
the frozen traffic-before-E3/E4 numerical order.

Safe-ETA selector horizons retain the final dual-horizon runtime semantics.
If `ceil((Q90 + frozen margin)/300)` reaches a previously unseen integer step,
the duration is not clamped to the highest calibrated bin.  Instead a
collision-proof unseen token makes horizon-dependent template keys miss and
the existing frozen hierarchy may select only `physical_route` or `global`.
The continuous profile duration remains unchanged.  This closes the issue
19109 L19 boundary without changing a calibrated in-domain result or relaxing
any tolerance.  The per-issue committed index records the unseen row count and
step values so that this evidence also survives a later bounded restart.

Stage 7 PASS additionally requires all 12 uninterrupted burn-ins, all 12 exact
checkpoint/restart pairs, and all 12 pre-frozen independent-initializer pairs
to pass at evaluation start.  This authority/preflight package alone does not
declare Stage 7 complete.

## WSL execution order

Run these commands in order.  Every command is resumable and fail-closed:

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/stage7_r12_representative_weeks'
./run_r12_stage7.sh authority
./run_r12_stage7.sh source
./run_r12_stage7.sh canonical
./run_r12_stage7.sh restart
./run_r12_stage7.sh initializer
./run_r12_stage7.sh final-validate
```

During the long `source` phase, concise progress (without worker IDs) is:

```bash
watch -n 5 python3 show_r12_source_progress.py
```

It reports the SHA-committed prefix, recent issue rate, ETA, idle time, worker
count, and any scientifically authorized unseen Safe-horizon fallback rows.

`restart` does not recompute the first 288 steps.  It launches a new process
from each SHA-bound canonical step-288 POST and executes only the remaining 288
steps.  The three controller phases therefore commit at most 17,280 transitions
(6,912 canonical + 3,456 restart suffix + 6,912 independent initializer), not
20,736.  Four episode processes run concurrently and each Gurobi process is
limited to four threads.

Only `final-validate` may write `C_stage7_complete=true`, and it does so only
after 12/12 canonical chains, 12/12 restart endpoint hashes, and 12/12 frozen
initializer comparisons all pass.  If 48 hours does not wash out an assigned
initializer under the pre-frozen tolerance, validation fails; no tolerance is
relaxed automatically.
