# Controller heartbeat I/O repair and actual reload evidence

This package preserves controller-only repair commit `81a62242`, final owner and independent tests, a real isolated Windows sharing-lock reproduction, and the actual coordinator reload audit. It does not establish a daily scientific PASS or solver performance improvement. All copied evidence keeps its original bytes and labels.

The original 2026-10-09 21:38:35 UTC `PermissionError(13, 'Permission denied')` occurred when recovery read Source30 May05 `HEARTBEAT.json`. Prior coordinator87676 was observed in the historical baseline; later107856 was observed before the owned reload. The five-minute scheduled trigger is compatible with the recovery timing. Task Scheduler Operational logging was disabled, so no event-log proof of that recovery is available. The saved traceback does not serialize `winerror`; atomic replacement is plausible, not proven.

The repair defers only an access/sharing failure on an exactly owned, sealed-request heartbeat. Missing heartbeat is explicit absence. Missing reads, unsupported errors, and sealed request/manifest/queue/RESULT/source-proof errors do not become empty observations, Native0, or PASS. Three consecutive unresolved access failures create an explicit persistent observation error while the controller and other dates continue. Resolution requires a real matching clean heartbeat read for the same PID/create/request/queue identity; history remains.

Tests and limits:

| Evidence | Actual outcome | Meaning |
|---|---:|---|
| `owner/TARGETED_TESTS.xml` | 16 setup errors | External fixture-parent setup failure; no test case executed |
| `owner/TARGETED_TESTS_02.xml` | 15 PASS, 1 FAIL | List-versus-tuple assertion in the fixture; historical failure preserved |
| `owner/FULL_NATIVE_DENIED_TEST_RECEIPT.json` | 124 PASS | Historical owner suite before the added same-worker resolution regression |
| `owner/FULL_NATIVE_DENIED_TEST_RECEIPT_02.json` | 125 PASS, 9.896 s | Final owner four-file source/test hashes stable |
| `independent/INDEPENDENT_CONTROLLER_IO_NATIVE_DENIED_REVIEW_RECEIPT.json` | 125 PASS, 10.816 s | Independent model constructor/optimizer denial and stable source/test hashes |
| `owner/ACTUAL_WINDOWS_HEARTBEAT_SHARE_NATIVE_ZERO_PROOF.json` | PASS | Isolated Win32 exclusive-sharing read denial, then identical clean read after handle close |

Both final suites report Native optimize calls0 and real model constructions0. Synthetic test ledger values are fixture data, not actual solver measurements. The Windows reproduction establishes the scoped defer/clean-read behavior; it does not establish the historical fault's exact cause.

Root's actual reload at22:18:03UTC replaced only supervisor107856 with107788. The helper directly launched the verified replacement command. It did not terminate scientific workers. Root's receipt and three raw Native-before ledgers are under `root_reload/`; the manual lease `ec090...` was explicitly released at22:18:07UTC after successful adoption proof.

Independent actual audit `owner/CONTROLLER_HEARTBEAT_IO_RELOAD_INDEPENDENT_ACTUAL_AUDIT_02.json` passed2,276 checks. It rechecked actual OS PID/create/command/cwd, CP and sealed requests, all immutable D32 1110 files, current four controller/test hashes against commit81a62242, original completed Native call prefixes, and HTTP8794. May01/02/03 remain Source32 at PIDs106760/95584/107636. The captured Native totals were716.2020003795624/706.3659999370575/639.4100003242493 seconds; current date statuses were RUNNING. Files and API were observed sequentially at their recorded timestamps, not as one atomic campaign snapshot. The audit itself invoked no Native/model/process action and changed no production queue/manifest/source.

At22:23:20UTC, a new `LockBusy(LIVE_OS_LOCK:...AUTONOMOUS_SUPERVISOR.lock)` replaced the public `SUPERVISOR_ERROR.json`. The original heartbeat error remains byte-exact in the owner and independent raw copies (SHA39f02daf...050b). The initial read-only audit's error-file-unchanged assumption therefore failed; its script, raw snapshots and explicit failure receipt are preserved. The corrected audit distinguishes the original saved evidence from the new current error. At22:24:56UTC, the scheduled task was Ready, LastRun22:23:20, LastTaskResult1, next22:28:19, and only one matching supervisor process107788 was observed. This strongly fits duplicate task entry rejected by the live lock; no lock or task was changed by the reviewer. Any later duplicate-entry repair belongs to separate evidence, not this sealed package.

`SHA_INVENTORY.json` records all selected files with relative paths, original sources and byte SHA. `SHA256SUMS.txt` includes that inventory's checksum and all selected files. Large scientific matrices, models, points, and Native outputs are omitted. Root performs Git commit/push; packaging performed none.
