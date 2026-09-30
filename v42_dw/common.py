from v42_compact.common import OLD, PR97, PR98, read, sha, rec, clean, require
from pathlib import Path
import json
from time import sleep

# Keep new receipts on the calling checkout's path. Historical compatibility
# can resolve D paths back through the retained C junction; old evidence stays
# untouched and is still read via its inherited authority paths.
ROOT = Path(__file__).absolute().parents[1]

BASE = '3309cd230cd8235201f5578d392241fa98e059bc'
OUT = ROOT / 'docs/v42_dantzig_wolfe_pricing'
LOCAL = ROOT.parent / 'V42_DW_PRICING_LOCAL'
RC_TOL = 1e-7
PHASE1_TOL = 1e-9

def atomic(path,value):
    """Atomic replacement with bounded Windows reader-sharing retries.

    Old supervisor code is preserved. Temporary files from failed replacement
    are retained as evidence. The same diagnostic is retried; no model changes.
    """
    from v42_native.supervision import atomic as original
    for attempt in range(8):
        try:return original(path,value)
        except PermissionError:
            if attempt==7:raise
            sleep(.02*(attempt+1))

def progress(context,value):
    from v42_native.contracts import digest
    atomic(context.folder/'solver_progress.json',dict(clean(value),request_sha256=digest(context.request),scientific_acceptance=False))

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')
