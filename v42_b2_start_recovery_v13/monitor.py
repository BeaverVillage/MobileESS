"""Reuse the verified Gap display against the V10 recovery checkpoint."""
from pathlib import Path
from types import SimpleNamespace
from v42_may_monitor_gap_v8 import monitor as previous
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from . import monitor_base as base
from .common import exclusive_lock, LockBusy


def view(root):
    value = rebound(previous.view, dict(previous.view.__globals__, previous=base))(root)
    value.update(display_version='B2_FULL_SOURCE_AUTHORITY_RECOVERY_V13',
        continuation_version='B2_FULL_SOURCE_AUTHORITY_RECOVERY_V13',
        precision_dates='2025-05-01..2025-05-31', precision_Heuristics=.05,
        phase_I_presolve=0, campaign_source_changed=True)
    return value


def run(root):
    try:
        with exclusive_lock(Path(root) / 'MONITOR_GAP_V8.lock'):
            proxy = SimpleNamespace(runtime_path=base.co.runtime_path, load_manifest=base.co.load_manifest)
            return rebound(display.run, dict(display.run.__globals__, original=proxy,
                view=view, __file__=__file__))(root)
    except LockBusy:
        return 0
