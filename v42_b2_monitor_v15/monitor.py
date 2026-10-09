"""Simple live B2 display, independent of admitted campaign science."""
from pathlib import Path
from types import SimpleNamespace
from v42_b2_monitor_v14.monitor import view as previous_view
from v42_b2_start_recovery_v13 import coordinator as co
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90.common import exclusive_lock, LockBusy
from v42_pr134_b1.common import same_process
from .actual import comparison


def view(root):
    root = Path(root)
    value = previous_view(root)
    for worker in value['workers']:
        progress = worker.get('progress') or {}
        measured = worker.get('Native_Runtime_seconds')
        reported = progress.get('Native_Runtime')
        # The budget callback reports completed Runtime plus the current model's
        # Runtime. Display that measured report separately; never extrapolate wall.
        eligible = (worker.get('native_inflight') and display.finite(measured)
                    and progress.get('Native_Runtime_completed') == measured
                    and display.finite(reported) and reported >= measured)
        worker['reported_native_runtime_seconds'] = reported if eligible else measured
        worker['reported_native_remaining_seconds'] = (
            max(0., 5400. - worker['reported_native_runtime_seconds'])
            if display.finite(worker['reported_native_runtime_seconds']) else None)
        worker['native_runtime_basis'] = 'SOLVER_CALLBACK_CURRENT_CALL_INCLUDED' if eligible else 'COMPLETED_NATIVE_LEDGER'
    checkpoint = co.read(root / 'CHECKPOINT_V13.json')
    value['actual_comparison'] = comparison(checkpoint['dates'])
    heartbeat = co.read(root / 'COORDINATOR_HEARTBEAT.json')
    value['coordinator_alive'] = same_process(heartbeat.get('process', {}))
    value['last_error'] = checkpoint.get('last_error')
    gate = value['B2_validation_detail']
    value['B2_validation_detail'] = {k: gate.get(k) for k in ('PASS', 'status', 'error')}
    value['display_version'] = 'B2_SIMPLE_ACTUAL_MONITOR_V15'
    # Only compact records are sent for completed days; solver data stay on disk.
    value.pop('date_tables', None)
    value.pop('progress', None)
    value.pop('B2_build_validation', None)
    value['runtime_root'] = str(root)
    return display.clean(value)


def run(root):
    try:
        with exclusive_lock(Path(root) / 'MONITOR_GAP_V8.lock'):
            proxy = SimpleNamespace(runtime_path=co.runtime_path, load_manifest=co.load_manifest)
            return rebound(display.run, dict(display.run.__globals__, original=proxy,
                                             view=view, __file__=__file__))(root)
    except LockBusy:
        return 0
