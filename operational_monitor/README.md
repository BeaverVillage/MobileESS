# Existing monitor · V44_iteration2

Deploy these files into `D:/MobileESS_V44/development/monitor_recovery_20261022`.
The existing `MobileESS_V44_StatusMonitor_20261022` task and
`http://127.0.0.1:8795/` remain the sole monitor. The existing template,
Native/UB/LB/Gap cards, execution details, one refresh loop and `/api/status`
are edited in place. The retired8796 task must not be recreated.

The monitor now reads only the runtime selected by
`D:/MobileESS_V44/runtime/ACTIVE_ITERATION2_CAMPAIGN.json`. It never loads the
old campaign view, equipment overlay, historical cache or baseline ZIPs.
The previous r043 heading, B0/B1/B2/B3 comparison card and follow-up labels
are removed. All31 dates show M2/A3/M3/A4/M4 and Actual/Fresh120, live Native
usage, bounds, voltage proofs, Phase-I Phi/zero status and nested budget.
Tiny positive Phi values use scientific notation. Public M PASS needs its
SHA-bound voltage matrix and plan proofs; Fresh PASS needs the independent
audit. A missing iteration state cannot fall back to an old result.

Historical read helpers remain versioned for prior tests and evidence, but
are not used by the active snapshot producer. Current journals are read from
their real files. No result, ledger, authorization or scientific source is
modified by the monitor.

The existing immutable display helpers under
`D:/MobileESS_V43/development/monitor_partial` and
`D:/v44_may01_07_prepare_20261016` remain dependencies. No scientific worker,
ledger or source package is changed by deploying this directory.

Validation:
`python -B -X utf8 -m unittest discover -s operational_monitor -p "test_*.py" -q`
and `python -B -X utf8 operational_monitor/test_monitor_service.py`.

Deployment restarts only the existing monitor task. The running supervisor
and solver PID stay intact. No archive-index cold scan is required. The
snapshot timestamp and current journal age remain separate.
