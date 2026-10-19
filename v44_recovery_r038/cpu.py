"""Explicit P-only logical placement, including deliberate SMT sharing."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
import psutil
from v44.common import read,atomic,now
from v44.locks import alive,exclusive_lock
from v44_recovery_r029.cpu_placement import windows_cpu_sets,claim_core,release_core

def placement(rows,count=7):
    if not rows or any(r['group']!=0 for r in rows):raise PermissionError('R038_SINGLE_GROUP_TOPOLOGY_REQUIRED')
    highest=max(r['efficiency_class'] for r in rows)
    cores={}
    for r in rows:
        if r['efficiency_class']==highest and not(r['flags']&2 and not r['flags']&4):
            cores.setdefault(r['core'],[]).append(r)
    ordered=[]
    for sibling in range(max(map(len,cores.values()),default=0)):
        for core,values in sorted(cores.items()):
            values=sorted(values,key=lambda r:r['logical'])
            if sibling<len(values):ordered.append(values[sibling])
    if len(ordered)<count:raise PermissionError('R038_INSUFFICIENT_P_LOGICAL_PROCESSORS')
    return dict(physical_P_cores=len(cores),P_logical_processors=sorted(r['logical'] for v in cores.values() for r in v),
        efficiency_class=highest,slots=[dict(slot=i+1,logical=r['logical'],core=r['core'],group=r['group']) for i,r in enumerate(ordered[:count])],
        distinct_physical_cores=count<=len(cores),E_core_workers=0)

def validate_topology(plan):
    actual=placement(windows_cpu_sets(),len(plan['slots']))
    if actual!=plan:raise PermissionError('R038_P_CORE_TOPOLOGY_DRIFT')

@contextmanager
def reserve_pool(plan,ops,lease):
    validate_topology(plan);handles=[]
    try:
        rows=windows_cpu_sets()
        for core in sorted({r['core'] for r in plan['slots']}):
            handle=claim_core(next(r for r in rows if r['core']==core and r['group']==0))
            if handle is None:raise PermissionError('R038_P_PHYSICAL_CORE_ALREADY_RESERVED')
            handles.append(handle)
        atomic(Path(ops)/'R038_ACTUAL_CPU_POOL.json',dict(UTC=now(),lease=lease,placement=plan,physical_reservations_held=True))
        yield
    finally:
        for h in reversed(handles):release_core(h)

@contextmanager
def actual_slot(request,ops,plan):
    root=Path(request['campaign_root']);lease=request['lease'];slot=request['parallel_actual_slot']
    if type(slot) is not int or not 1<=slot<=len(plan['slots']):raise PermissionError('R038_ACTUAL_SLOT_OUT_OF_RANGE')
    if request.get('r038_phase')!='ACTUAL_PARALLEL' or request.get('worker_slot')!=1:raise PermissionError('R038_ACTUAL_ONLY_SLOT_AUTHORITY')
    if not alive(lease) or lease!=read(root/'COORDINATOR_LEASE.json'):raise PermissionError('R038_LIVE_LEASE_REQUIRED')
    phase=read(root/'PHASE.json');pool=read(Path(ops)/'R038_ACTUAL_CPU_POOL.json')
    if phase.get('lane')!='ACTUAL_PARALLEL' or pool['lease']!=lease or pool['placement']!=plan:
        raise PermissionError('R038_ACTUAL_BARRIER_AND_P_POOL_REQUIRED')
    selected=plan['slots'][slot-1]
    with ExitStack() as stack:
        stack.enter_context(exclusive_lock(root/f'locks/ACTUAL_PARALLEL_SLOT_{slot}.lock'))
        stack.enter_context(exclusive_lock(root/f"locks/cases/{request['day']}_{request['arm']}.lock"))
        stack.enter_context(exclusive_lock(root/f"locks/R038_LOGICAL_CPU_{selected['logical']}.lock"))
        process=psutil.Process();process.cpu_affinity([selected['logical']])
        if process.cpu_affinity()!=[selected['logical']]:raise PermissionError('R038_P_AFFINITY_NOT_APPLIED')
        yield selected

@contextmanager
def compute_scope(request,count,receipt,plan):
    if count!=1:raise PermissionError('R038_ACTUAL_NUMERICAL_THREADS_MUST_REMAIN_ONE')
    selected=plan['slots'][request['parallel_actual_slot']-1];p=psutil.Process()
    expected=[selected['logical']]
    if p.cpu_affinity()!=expected:raise PermissionError('R038_ACTUAL_AFFINITY_DRIFT')
    value=dict(applied=True,selected_affinity=expected,physical_core=selected['core'],P_core_only=True,
        efficiency_core_fallback=False,compute_threads=1,pool_distinct_physical_cores=plan['distinct_physical_cores'],
        pool_physical_reservations_held_by_coordinator=True,parallel_actual_slot=request['parallel_actual_slot'])
    try:yield value
    finally:
        if p.cpu_affinity()!=expected:raise PermissionError('R038_ACTUAL_AFFINITY_CHANGED_DURING_RUN')
        value.update(restored=True,restored_affinity=expected)
        if receipt is not None and Path(receipt).parent.exists():atomic(receipt,dict(UTC=now(),**value))
