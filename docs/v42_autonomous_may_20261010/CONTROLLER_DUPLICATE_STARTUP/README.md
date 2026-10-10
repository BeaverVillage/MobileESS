# Verified duplicate supervisor startup rejection

Status at this package's creation: final owner142 tests PASS; independent142 review pending. The existing Windows periodic task has already loaded the future startup candidate and recorded a verified rejection. Active supervisor107788 and the scientific Source32 workers were not restarted. A coordinator reload is unnecessary for this startup-only path. No Git action was performed by the owner.

The prior five-minute duplicate entry raised canonical `LockBusy` at the global `AUTONOMOUS_SUPERVISOR.lock`. The broad CLI error writer replaced `SUPERVISOR_ERROR.json` with that duplicate error. This repair intercepts only mutex-entry refusal. An exact canonical exception, exact resolved root lock, recognized OS errno, actual live PID/create/command/cwd/executable, and matching heartbeat no older than60seconds are all required. The freshness window establishes operational ownership; it is not a scientific time budget or resource throttle.

Verified duplicate entry creates a unique immutable JSON under `autonomous/startup_rejections` and returns. Existing public error, CP, scientific request/ledger files and lock ownership are untouched. Dead, mismatched, stale, corrupt or unreadable owner proof remains a strict startup error. Different locks, unsupported exceptions, and errors raised after mutex acquisition remain on their existing strict paths. No lock removal, lease breaking, or scientific change is introduced.

Owner results and historical failures:

| Evidence | Outcome | Scope |
|---|---:|---|
| `owner/TARGETED_NATIVE_DENIED_TEST_RECEIPT_02.json` |16 PASS,1 FAIL| Isolated owner child lacked its synthetic continuation manifest; the child remained Native/model-denied |
| `owner/HARNESS_ROOT_PATH_CLONE_FAILURE_03.json` |Tests0| Output-suffix clone accidentally altered the runner root; strict FileNotFound occurred before tests |
| `owner/TARGETED_NATIVE_DENIED_TEST_RECEIPT_04.json` |17 PASS| Corrected targeted fixture before the final mutex-still-held assertion was added |
| `owner/FULL_NATIVE_DENIED_TEST_RECEIPT.json` |142 PASS,10.680s| Final four-file hashes stable; parent and child real model constructors/optimize denied; attempted entries[] |
| `owner/ACTUAL_ISOLATED_WIN_MUTEX_DUPLICATE_PROOF_RECEIPT.json` |PASS| Real canonical supervisor child and real Windows byte-range mutex; duplicate returned and original mutex stayed held |

The isolated proof checks prior error, CP, three sealed-request fixtures and Native-ledger fixtures byte-for-byte. Its child is terminated only as external test teardown. Fictional fixture date PASS and empty ledgers are not scientific evidence. No production process action or Native/model construction occurred in the owner test work.

Actual periodic observation: event`20261009T223320448514_df070a15592346f9b4f2b2dea7531cc4.json` records duplicate98264 and unchanged owner107788 at22:33:20UTC, matching owner heartbeat age about1second. Scheduled task LastRun22:33:20 and result0 support successful rejection. `owner/ACTUAL_PERIODIC_DUPLICATE_STARTUP_READ_ONLY_AUDIT.json` independently verifies unchanged actual OS identities, same sealed requests, preserved completed Native prefixes, and HTTP8794. Current Source32 PIDs are106760/95584/107636; captured Native totals were1240.6150002479553/1246.7820000648499/1005.8949999809265 seconds. Date PASS is not claimed.

The public error file still exactly matched the pre-full-test22:28 LockBusy observation after the22:33 rejection. It had already replaced the original21:38 heartbeat error before this fix; that original evidence remains byte-exact in the separate sealed `CONTROLLER_HEARTBEAT_IO` package. This package does not rewrite that earlier package or retrospectively label the historical sharing cause as proven.

Actual OS task execution was not instrumented by the reviewer; its event declares Native/model0, and the unchanged worker ledgers plus source path support the operational scope. The independent audit itself invoked no Native/model/process action. Operational files/API were captured sequentially at recorded timestamps. Current immutable D32 source was used for science binding while separate Repo Source33 science work proceeded. No solver performance or final scientific PASS is established here.

Raw copied bytes are preserved. `SHA_INVENTORY_PENDING_REVIEW.json` and `SHA256SUMS_PENDING_REVIEW.txt` seal this state. Later independent acceptance can be added separately without altering these historical pending records.
