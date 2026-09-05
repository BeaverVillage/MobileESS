# V39L detached launcher contract

The production resume is registered as a one-shot Windows Task Scheduler task
and is started by a short-lived PowerShell scheduling client. The scheduled
task runs `run_v39l_detached_may.py --scheduled-resume` in the current user
session. The campaign process therefore belongs to Task Scheduler's launch
tree rather than the Codex unified execution tree.

The scheduled entry point acquires an exclusive instance file only after it
checks live Windows process identities. A valid identity requires PID,
creation time, and command tokens. Stale PID files are archived. A second live
authoritative orchestrator or duplicate `--day` worker fails closed. The code
never terminates Python processes.

The orchestrator writes the master progress files every ten seconds from an
independent heartbeat thread. Every write uses a temporary file, flush,
`fsync`, close, and atomic replace. Heartbeats include orchestrator identity,
active dates and worker PIDs, completed and failed dates, and the V39K-bound
campaign fingerprint.

The monitor reports RUNNING only when the PID, creation time, command tokens,
and heartbeat freshness all validate. Its liveness states are RUNNING, STALE,
DEAD, FAIL, and PASS. A stale JSON snapshot cannot authorize RUNNING.

This infrastructure does not alter B0/B1/B2/B3, objective J, DA authority,
MESS, electrical limits, solver search settings, or Fresh/restoration logic.
