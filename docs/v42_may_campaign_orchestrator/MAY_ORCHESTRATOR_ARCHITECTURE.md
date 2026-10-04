# Lane D May orchestration

Base: PR #143 `ce5d30fb9bcb91ab8395d1313e868d24f5fde517`.
All changes live in `v42_orchestrator`, its tests, and this evidence directory.
Scientific optimizer internals and the historical sequential engine are preserved.

## Frozen science and scheduling

Dates are read from the explicit `days` array in
`docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json`.
The loader requires exactly 31 distinct ordered May dates from one year. Current
authority is 2025-05-01 through 2025-05-31; the execution host date is irrelevant.
Nodes copy frozen scientific metadata and the established `planning_stages`.

| Group | Planning stages per day | Day cap | M pricing slots |
| --- | --- | ---: | ---: |
| B0 | B0_PLANNING (fixed D1 workload, MESS off) | 4 | 0 |
| B1 | A1 (AIDC free, MESS off) | 1 | 0 |
| B2 | M1 (fixed D1 AIDC, MESS free) | 4 | 1 |
| B3 L1-L4 | A1 -> M1 -> A2 -> M2 | 1 | up to 4 |

Each day ends with PLANNING_FREEZE -> ACTUAL -> FRESH_AC -> VALIDATION_FREEZE.
These are mock stage labels, with no scientific adapter in this lane.
M2 keeps route, movement, P, Q and SOC free; A2 AIDC is its fixed counterpart,
and M1 MESS is only a validated warm candidate according to frozen metadata.

Main order is B0(all 31 PASS) -> B1(all 31 PASS) -> B2(all 31 PASS) ->
B3 L1(all 31 PASS) -> MAIN_MAY_CAMPAIGN_COMPLETE. Only then B3 L2 -> L3 -> L4,
each loop completing every day's validation. B0/B1/B2 never repeat.
The analytical fixed-point/two-cycle detector can record a result; it cannot
remove L4 or stop the queue. Main result selection requires B0/B1/B2/B3 L1.
L2-L4 are selected separately for convergence (L1 is already stored in main).

Count is derived: 3*31*5 + 4*31*8 + 1 = 1,458. The main-complete coordination
gate accounts for the extra one; no substitute scientific stages are introduced.
Historical stage count therefore has zero difference.

## Resource admission

An ordered dynamic ThreadPoolExecutor queue runs independent B0/B2 days, capped
at four, and B1/B3 at one. Every group joins before the next group starts. There
is one shared Resources object per coordinator and one OS coordinator lock per
campaign root. Day workers reserve no solver tokens. Each mock heavy solve
requests exactly one token. B2's four days each request one; B3 M stages create
up to four inner tasks. All share a default four-slot semaphore. Threads=1 is
required for every future Gurobi solve. Explicit JSON Config can reduce worker
caps, tighten guards, change solver capacity or bounded retries; it cannot
weaken the current scientific limits. No environment variable controls policy.

Mock telemetry checks available physical RAM >=1 GiB, OOM, commit >=95%,
catastrophic sustained paging, solver/license failure, and invalid telemetry.
Admission occurs at stage entry, solve acquisition/wait and solve completion.
A guard latches a global stop: no new work and interrupted active mock stages.
Tokens release in finally blocks. Mock sleep is cooperative; this code cannot
terminate a future opaque native solve. Future production integration must
define native cancellation and sustained paging observation windows.
This lane reads no live RAM/commit data and does not stress memory.

## Checkpoint, receipt, and retry

Stage transitions are validated against `ledger.TRANSITIONS` and atomically
replace CAMPAIGN_STATE.json after every transition. The checkpoint carries
campaign identity, arm/day/loop/stage, scientific/input/output SHA, stage version,
timestamps, worker, failure reason/type, retry count and receipt location.
CAMPAIGN_SUMMARY.json summarizes status counts by group.
Temporary files are flushed and fsynced before replace. Windows replace denial
gets eight bounded attempts; no in-place rewrite fallback exists.
OS file locks release on process death; the persistent lock filename is harmless.
Atomic replace plus file fsync does not claim hardware power-loss durability of
directory metadata on every filesystem.

Receipts match scientific SHA (base plus frozen scientific authority), external
input SHA, data-dependency output SHA, plan SHA, stage version, mode and full
day/arm/loop/stage identity. PASS requires a matching receipt and payload hash.
Receipt artifacts are exclusively atomically published at
`campaign/B3/Lk/YYYY-MM-DD/stage/identity-hash/PASS.json` (B0-B2 omit Lk).
An identity change invalidates affected stages and required downstream nodes;
new generations get different paths. Corrupt current receipts move to quarantine.
Valid accepted artifacts are never overwritten or recomputed on replay.

On restart, orphan RUNNING becomes INTERRUPTED. A matching published receipt
reconciles it to PASS even if the coordinator died before checkpoint acceptance;
otherwise it becomes READY once dependencies pass. All valid PASS receipts are
preserved. Only unfinished days enter the deterministic queue. The 31-day
partial fixture preserves B0 days 1-8 and queues days 9-31; all B0 PASS unlocks B1.
The machine restart test uses an abruptly terminated fresh child process and
new coordinator state; it does not physically reboot the user's machine.

ScientificFailure (infeasible/physical audit/certificate failure) records FAIL
and blocks required descendants. TransientFailure permits at most two default
retries with a persisted count; exhausted retries block descendants. Resource
and unknown/worker failures interrupt instead of becoming scientific PASS.
FAIL/BLOCKED campaigns require deliberate operator repair; reopening cannot
silently retry hard failures. Resume validates checkpoint topology/status and
every PASS receipt before releasing work. Invalid checkpoint JSON fails closed.

## Planning/Actual firewall

Control dependencies and Planning_dependencies are distinct. Actual completion
can open a group gate. Its values and output SHA never enter the next Planning
stage input digest or adapter context. B3 next-loop A1 receives only that same
day's previous Planning freeze. The broker rejects undeclared dependencies and
non-PLANNING provenance and deep copies contexts. Adversarial tests poison Actual
SHA, inject Actual payloads and forge provenance. This is a scheduler data
firewall for the fixed mock backend, not an OS sandbox for arbitrary native I/O.
The existing PlanningReads read audit should be integrated into future trusted
production adapters with concurrency-safe scopes; its historical global scope
cannot simply be installed around multiple day threads.

## Commands and future integration

`python -m v42_orchestrator plan` writes the full NOT_RUN DAG/CSV and policy audits.
`python -m v42_orchestrator verify` runs only the bounded scheduler unittest suite
and regenerates measured evidence. The full pytest suite is deferred for Lane A.
`python -m v42_orchestrator mock --output <separate-root> --mock-days 4` runs a
bounded synthetic campaign and resumes the same root without duplicate artifacts.
Use `--config <explicit-json>` for supported resource overrides.
`python -m v42_orchestrator production` always blocks in Lane D, including when
ENABLE_PRODUCTION=true. Arbitrary adapter callbacks are rejected. No Gurobi,
pricing optimizer, Branch-and-Price or OpenDSS module is imported or invoked.

After M1 algorithm authority is accepted, a separate reviewed change must:

1. Bind frozen per-day D1/forecast/Runtime-CC4 source hashes instead of synthetic
   input identity. Carry planning outputs through validated handoffs preserving
   fixed counterparts and M2 freedom. Use a new stage version and new production
   identity/root so mock PASS can never count as scientific completion.
2. Add explicit production command/config and trusted per-stage adapters. Validate
   scientific numerical, physical and certificate acceptance before PASS;
   Actual/Fresh AC require separate complete audits. Synthetic PASS is never a
   paper result or acceptance certificate.
3. Connect every heavy solve to this central semaphore (including retries),
   enforce Threads=1 in native calls, implement live telemetry and native solve
   cancellation, and audit all Planning reads with a concurrency-safe broker.
4. Keep arm barriers, same-day previous Planning seeds, mandatory L4 and result
   selector unchanged. Re-run isolated mocks/static tests before separately
   authorized production validation. Do not merge/rebase lanes A/B/C here.
