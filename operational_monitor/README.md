# Existing V44 r043 monitor extension

Deploy these files into `D:/MobileESS_V44/development/monitor_recovery_20261022`.
The existing `MobileESS_V44_StatusMonitor_20261022` task and
`http://127.0.0.1:8795/` remain the sole monitor. The original DOM, comparison
table, Native/UB/LB/Gap cards, execution details and `/api/status` are extended
in place. The retired8796 task must not be recreated.

The current B2 coordinator/worker retain the primary cards. The same response
adds31 follow-up rows, exact public-stage receipts, Native/bounds, resource
gates and seven Actual slots. On natural B2 completion, the primary cards
follow V44_iteration2. Status flags alone never establish Fresh PASS.

`archive_reads.py` reads missing exported evidence directly from verified ZIP
members without restoring original result directories. Live journals are read
from their real files. Completed history may be cached only for the exact
original batch key; current B2 and iteration status are always overlaid.

The existing immutable display helpers under
`D:/MobileESS_V43/development/monitor_partial` and
`D:/v44_may01_07_prepare_20261016` remain dependencies. No scientific worker,
ledger or source package is changed by deploying this directory.

Validation:
`python -B -X utf8 -m unittest discover -s operational_monitor -p "test_*.py" -q`
and `python -B -X utf8 operational_monitor/test_monitor_service.py`.

Deployment restarts only the existing monitor task. Cold startup first loads
archive indexes; an exact-key historical cache avoids rescanning completed
raw outputs. The snapshot timestamp and current journal age remain separate.
