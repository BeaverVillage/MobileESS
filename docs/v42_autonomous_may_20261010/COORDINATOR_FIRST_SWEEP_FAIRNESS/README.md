# Coordinator first-sweep fairness: qualification and actual owned reload

The previous coordinator preferred a verified repair at every free slot.
Finite READY entries were consumed once and did not themselves create HOLD,
but continuously supplied new verified repairs could indefinitely postpone
unvisited dates. The new scheduling rule bounds that dispatch streak while
retaining the existing queue priority order and worker counts.

While an arm has an unvisited initial date, at most two consecutive entered B2
repair starts or one entered B3 repair start precede an initial-date visit in
the next free slot. The streak is durable in the checkpoint. B2 stays at three
workers and B3 at one. Only entered repair starts, including new adoption, count;
re-adopting the same persisted worker does not count twice. Successful initial
starts and local initial admission failures with preserved terminal receipts
reset the streak. Lease contention, unentered retry failures and shared source
blocks do not fabricate a counted start or reset. Malformed counters fail
strictly. Once the first sweep is complete, this restriction is inactive.

The first eligible selection still favors a priority repair. With three free
B2 slots, two priority repairs and one unvisited date start. B3 alternates
repair and initial visits. This means priority repairs need not occupy every
available slot while unvisited dates remain. The existing transition starts
B3 after B2's 31 terminal first attempts even when B2 FAIL or READY repairs
remain. Shared source/environment blocking and all original scientific and
Native-budget guards remain in place. Scheduling liveness applies when slots
become free and shared admission is healthy; no wall-clock or solver-speed
guarantee is made.

## Exact qualification evidence

`OWNER_FINAL_02` and `INDEPENDENT_156` each contain a 156-test strong-denial PASS:
the existing 142 recovery/supervisor regressions and 14 new behavior cases.
Tests exercise endless verified repairs that keep failing, checkpoint reload
and worker re-adoption on every cycle, all 31 first dates, mixed daily terminal
failures, unchanged repair priority, healthy-worker/Native-prefix preservation,
refused starts, local initial admission failure, shared source blocking,
completed-sweep dispatch and strict invalid-counter rejection.

Seven scientific modules were preloaded before denying the actual retained
Gurobi Model.__init__, Model.optimize and gurobipy.Model. Attempted actual model
and Native entries were empty. Test workers and their terminal receipts are
isolated simulations, not new scientific results. The original repository
science1007 and immutable D35/D36 source1111 were byte exact; owner/independent
read-only observations preserved the real three worker identities/requests,
completed Native-ledger prefixes and all nine READY queue entries.

`OWNER_INITIAL_COUNT_FAILURE_01` retains the initial runner's actual exit1 and
PASS=false receipt. All 156 tests passed, but the runner expected 15 focused
cases instead of the actual 14. Only that count check failed. Final runner02
corrected only the expectation and re-ran unchanged source/tests. Exact original
receipt, XML, captured pytest stdout/stderr and raw Native snapshots are kept;
the initial harness failure is not hidden or labeled as a scientific failure.
The receipt's `actual_exit_code` records pytest exit0; the wrapper process
returned exit1 because the separate count check failed.

`CONTROL_CURRENT` contains the qualified supervisor, unchanged recovery module,
new focused tests and both existing controller test modules. The archived
`CONTROL_BEFORE_POLICY` supervisor SHA4ad79721 is copied from the previously
sealed startup evidence. It is a historical control baseline, not a newly
invented initial read-only audit. The earlier scheduling review was communicated
in this task; no separate sealed proposal artifact existed to copy.

## Actual reload evidence

`ROOT_ACTUAL_RELOAD` contains the exact helper, ownership/heartbeat/OS-mutex
baseline, launch receipt, original three Native-prefix snapshots, prior raw
SUPERVISOR_ERROR bytes, actual verification, stdout/stderr and historical lease
receipts. The independently reviewed helper was unexecuted at its static review;
the later Root actual verification records the real operation.

Root terminated only exact owned old supervisor107788 and launched sole owned
replacement82852. The actual verification binds the new supervisor creation,
command and cwd, all three unchanged Source35 workers98148/103128/80288, current
requests, original completed Native prefixes and unchanged raw prior error.
Scientific-worker terminate calls, new Model/Native calls and replacement P2
calls were zero. Original 5400-second budgets and scientific source identities
were retained. No date PASS, final 3% Global Gap or fresh Actual result is claimed.

`ACTUAL_RELOAD_INDEPENDENT` contains the separate read-only post-reload audit
and its exact raw observations. All three scientific slots were occupied at
that audit, so no live fairness dispatch choice or Source36 Native execution
was observed yet. Process-memory bytecode was not inspected; source hashes,
owned process/launch/heartbeat observations and separate controller tests are
the evidence. The historical fairness repair lease705bf36e...
was RELEASED at00:54:59.422107 UTC; this is a historical receipt, not a claim
about any later global repair lease. These observations describe their sealed
timestamps and do not freeze subsequent healthy scientific progress.
The latest Root hourly-automation verification is copied exactly. Its ACTIVE
configuration and saved policy are distinguished from an actual scheduled run.

`PACKAGE_HARNESS_FAILURE_01` preserves the first packaging assertion failure,
which confused that owner01 pytest exit0 field with the wrapper's exit1.
It failed before creating this new docs directory or performing any production
action. The corrected assertion preserves both distinct exit-code meanings.

## Package seal

`COPY_PROVENANCE.json` maps every exact source copy to its origin SHA256/bytes.
`SHA_INVENTORY.json` seals every payload except itself. Local `.gitattributes`
disables text conversion only in this new evidence directory. Existing Source35,
Source36, monitor, full-LP diagnosis and earlier controller inventories are
unchanged. This packaging step imported no scientific modules, constructed no
model, ran no Native, changed no production processes or queues and made no
Git mutation. Actual Root reload is recorded separately and accurately.
