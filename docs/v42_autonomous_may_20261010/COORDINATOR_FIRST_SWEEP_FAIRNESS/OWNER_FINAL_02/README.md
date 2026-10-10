# First-sweep scheduling fairness qualification

While an arm still has an unvisited initial date, the owned supervisor permits
at most two consecutive entered B2 repair starts, or one entered B3 repair
start, before assigning the next free slot to the earliest pending initial
date. The bounded streak is persisted in the campaign checkpoint. Retry
priority and FIFO selection inside the recovery queue are unchanged.

The first choice remains an eligible priority repair. With three free B2 slots,
the resulting allocation is two priority repairs and one initial date. B3 has
one worker and alternates repair and initial visits. The tradeoff is that
priority repairs need not occupy every available slot while initial dates
remain. After an arm's first sweep is complete this restriction is inactive;
after B2's 31 terminal first attempts the existing transition starts B3 even
when B2 failures or READY repairs remain.

Only an entered retry returned by the existing recovery dispatcher, including
a newly adopted entered worker, increments the streak. Re-adopting the same
checkpoint worker does not count it twice. A successfully started initial
date or a local admission failure with a preserved first terminal receipt
resets the streak. Lease contention, failed or unentered retry starts, and a
common source/environment block do not manufacture a counted start or reset.
Malformed persisted counters fail strictly. Existing healthy workers retain
their requests and source bindings; B2=3 and B3=1, all scientific precision,
constraints, independent certification and original Native budgets remain.

The guarantee concerns dispatch when slots become free and shared admission
is healthy. It does not assert a wall-clock completion bound, an algorithm
speed improvement, or a scientific date PASS.

Owner runner02 executed 156 passing tests: the complete existing 142 controller
recovery/supervisor regressions plus 14 new behavior cases. The new cases use
unending verified-repair fixtures with failed repairs, real controller cycles,
checkpoint reload and adoption after each cycle, mixed terminal daily failures,
priority order, healthy-worker and Native-prefix preservation, refused starts,
local first-date admission failure, common source blocking, completed-sweep
repair dispatch and invalid counter rejection. Workers and result receipts in
the tests are isolated simulations; no actual solver is admitted.

Seven scientific modules were preloaded before denying retained real
Gurobi Model.__init__, Model.optimize and gurobipy.Model. Actual attempted
model/Native entries were empty. Original repository science1007 and each
immutable D35/D36 source1111 matched their declared hashes and remained byte
exact. Read-only before/after observations preserved the three real worker
identities, current requests, completed Native-ledger prefixes and all nine
READY queue entries byte for byte. No production reload, worker stop, queue
mutation or Git mutation was performed by this qualification.

The original owner runner01 expected 15 focused cases instead of the actual
14. Its 156 tests all passed; only this harness count check made its receipt
PASS=false and exit1. Its source, receipt, JUnit XML and captured pytest output
remain in D:/v42_first_sweep_fairness_owner_review_20261010_01. Runner02 changes
only that expectation and re-runs the unchanged qualified source/tests.

Final owner receipt:
`FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json`, SHA256
`09b7b6d7c4ecf43dab7a5ddd1206d54048749f85e886830f529944a813728c59`.
The JUnit XML and Python-redirected exact pytest stdout/stderr are retained in
this same folder. Root owns independent review and any later supervisor reload.
