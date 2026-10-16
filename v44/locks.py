"""One external campaign lease; two V44 B2 slots and per-case OS locks."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
import os
import psutil

from v42_may_campaign.common import exclusive_lock as inherited_lock
from types import FunctionType
from .common import RUNTIME,read,atomic,now,NotReady
from .config import require_day

EXTERNAL_LOCKS=(Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock'),
    *(Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{n}.lock') for n in (1,2,3)),
    Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),Path('D:/MobileESS_V43/runtime/V43_HEAVY_WORKER.lock'))


def _d_path(path):
    p=Path(path).resolve();value=str(p)
    # Windows can return its equivalent extended spelling during concurrent
    # parent creation. Keep the inherited D-drive rule for both spellings.
    if value.startswith('\\\\?\\') and value[4:6].upper()=='D:':p=Path(value[4:])
    if p.drive.upper()!='D:':raise ValueError('D_DRIVE_WRITES_REQUIRED:'+str(p))
    return p


_original=inherited_lock.__wrapped__
_routed=FunctionType(_original.__code__,dict(_original.__globals__,d_path=_d_path),
    _original.__name__,_original.__defaults__,_original.__closure__)
_routed.__kwdefaults__=_original.__kwdefaults__
exclusive_lock=contextmanager(_routed)


def process_identity():
    p=psutil.Process();return dict(pid=p.pid,process_created=p.create_time())


def alive(identity):
    try:return psutil.Process(identity['pid']).is_running() and abs(psutil.Process(identity['pid']).create_time()-identity['process_created'])<.001
    except (psutil.Error,KeyError,TypeError):return False


@contextmanager
def coordinator(root=RUNTIME,external=EXTERNAL_LOCKS):
    root=Path(root)
    with ExitStack() as stack:
        stack.enter_context(exclusive_lock(root/'locks/COORDINATOR.lock'))
        for path in external:stack.enter_context(exclusive_lock(path))
        lease=dict(**process_identity(),UTC=now(),root=str(root.resolve()),external_locks=[str(p) for p in external])
        atomic(root/'COORDINATOR_LEASE.json',lease)
        try:yield lease
        finally:atomic(root/'COORDINATOR_EXIT.json',dict(**lease,finished_UTC=now()))


@contextmanager
def worker_slot(day,arm,slot,*,root=RUNTIME,lease):
    require_day(day);root=Path(root)
    if not alive(lease) or lease!=read(root/'COORDINATOR_LEASE.json'):raise NotReady('COORDINATOR_LEASE_NOT_LIVE')
    if arm not in ('B0','B1','B2','B3') or (arm=='B2' and slot not in (1,2)) or (arm!='B2' and slot!=1):
        raise ValueError('V44_MAIN1_B2_TWO_SLOT_AXIS')
    lane='B2' if arm=='B2' else 'MAIN'
    with ExitStack() as stack:
        stack.enter_context(exclusive_lock(root/f'locks/{lane}_SLOT_{slot}.lock'))
        stack.enter_context(exclusive_lock(root/f'locks/cases/{day}_{arm}.lock'))
        # Main/B2 mutual exclusion is held by the coordinator's phase; no worker may choose another phase.
        phase=read(root/'PHASE.json')
        if phase.get('lane')!=lane:raise NotReady('CONSERVATIVE_LANE_PHASE_MISMATCH')
        yield dict(**process_identity(),day=day,arm=arm,worker_slot=slot,lane=lane)


def new_attempt(day,arm,stage,attempt,*,root=RUNTIME):
    from .stages import case_key
    case_key(day,arm,stage)
    if type(attempt) is not int or attempt<1:raise ValueError('EXPLICIT_POSITIVE_NEW_ATTEMPT')
    path=Path(root)/day/arm/f'attempt{attempt:03d}'/stage
    path.mkdir(parents=True,exist_ok=False)
    for name in ('tmp','nodefiles','logs'): (path/name).mkdir()
    return path
