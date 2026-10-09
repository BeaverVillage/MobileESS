from pathlib import Path
from types import SimpleNamespace
from v42_b2_monitor_v15.monitor import view as previous_view
from v42_b2_start_recovery_v13 import coordinator as co
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90.common import exclusive_lock, LockBusy
from .certificates import enrich


def view(root):
    value = previous_view(root)
    value['workers'] = [enrich(w) for w in value['workers']]
    value['worker_slots'] = [next((w for w in value['workers'] if w['worker_slot']==slot['worker_slot']),slot)
                             for slot in value['worker_slots']]
    value['display_version'] = 'B2_CERTIFICATE_STATUS_MONITOR_V16'
    return display.clean(value)


def run(root):
    try:
        with exclusive_lock(Path(root)/'MONITOR_GAP_V8.lock'):
            proxy = SimpleNamespace(runtime_path=co.runtime_path,load_manifest=co.load_manifest)
            return rebound(display.run,dict(display.run.__globals__,original=proxy,view=view,__file__=__file__))(root)
    except LockBusy:
        return 0
