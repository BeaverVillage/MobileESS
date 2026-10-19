"""Stage-local CPU placement; never change threads, priority or host power plan."""
from contextlib import contextmanager
import sys,struct
import psutil
from contextvars import ContextVar
from pathlib import Path
import os

_reservation=ContextVar('R011_PHYSICAL_CORE_RESERVATION',default=None)
CORE_LOCKS=Path('D:/MobileESS_V44/runtime/CPU_CORE_RESERVATIONS')


def parse_cpu_sets(data):
    result=[];offset=0
    while offset<len(data):
        if offset+8>len(data):raise ValueError('R011_TRUNCATED_CPU_SET_HEADER')
        size,kind=struct.unpack_from('<II',data,offset)
        if size<8 or offset+size>len(data):raise ValueError('R011_INVALID_CPU_SET_RECORD_SIZE')
        if kind==0:
            if size<24:raise ValueError('R011_TRUNCATED_CPU_SET_BODY')
            ident,group,logical,core,cache,node,efficiency,flags=struct.unpack_from('<IHBBBBBB',data,offset+8)
            result.append(dict(id=ident,group=group,logical=logical,core=core,efficiency_class=efficiency,flags=flags))
        offset+=size
    return result


def windows_cpu_sets():
    if sys.platform!='win32':return []
    import ctypes,ctypes.wintypes as w
    library=ctypes.WinDLL('kernel32',use_last_error=True)
    function=library.GetSystemCpuSetInformation
    function.argtypes=[w.LPVOID,w.ULONG,ctypes.POINTER(w.ULONG),w.HANDLE,w.ULONG];function.restype=w.BOOL
    size=w.ULONG();function(None,0,ctypes.byref(size),None,0)
    if not 0<size.value<=1024*1024:raise ValueError('R011_CPU_SET_BUFFER_SIZE')
    buffer=ctypes.create_string_buffer(size.value)
    if not function(buffer,size.value,ctypes.byref(size),None,0):raise ctypes.WinError(ctypes.get_last_error())
    return parse_cpu_sets(buffer.raw[:size.value])


def preferred_allowed(rows,allowed):
    # Group-aware affinity is a separate policy; retain the original mask there.
    if not rows or any(row['group']!=0 for row in rows):return list(allowed)
    available=[row for row in rows if row['logical'] in allowed and not(row['flags']&2 and not row['flags']&4)]
    classes={row['efficiency_class'] for row in available}
    if len(classes)<2:return list(allowed)
    highest=max(classes)
    result=sorted(row['logical'] for row in available if row['efficiency_class']==highest)
    return result or list(allowed)


def physical_candidates(rows,allowed):
    if not rows or any(row['group']!=0 for row in rows):
        raise ValueError('R011_SINGLE_GROUP_CPU_TOPOLOGY_REQUIRED')
    by_core={}
    for row in rows:
        if row['logical'] not in allowed or row['flags']&2 and not row['flags']&4:continue
        key=(row['group'],row['core'])
        if key not in by_core or row['logical']<by_core[key]['logical']:by_core[key]=row
    return sorted(by_core.values(),key=lambda row:(-row['efficiency_class'],row['group'],row['core']))


def claim_core(row):
    """OS byte lock reserves the physical core, including its SMT sibling."""
    import msvcrt
    CORE_LOCKS.mkdir(parents=True,exist_ok=True)
    path=CORE_LOCKS/f"GROUP{row['group']}_CORE{row['core']}.lock"
    stream=path.open('a+b');stream.seek(0,2)
    if stream.tell()==0:stream.write(b'0');stream.flush()
    stream.seek(0)
    try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:stream.close();return None
    return stream


def release_core(stream):
    import msvcrt
    try:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
    finally:stream.close()


@contextmanager
def compute_cpu_scope(count,receipt=None):
    if count not in (1,4):raise ValueError('R011_EXPLICIT_COMPUTE_THREADS_1_OR_4_REQUIRED')
    process=psutil.Process();before=process.cpu_affinity();handles=[];token=None
    metadata=dict(applied=False,original_affinity=before,restore_on_exit=True,compute_threads=count,
        distinct_physical_cores=True,global_power_plan_changed=False,priority_changed=False,
        availability_basis='OS_PHYSICAL_CORE_LOCKS_AMONG_COOPERATING_CAMPAIGN_COMPUTE_NOT_EXCLUSIVE_AGAINST_OTHER_APPLICATIONS')
    try:
        rows=windows_cpu_sets();candidates=physical_candidates(rows,before);chosen=[]
        inherited=_reservation.get()
        if inherited:
            allowed={(r['group'],r['core']) for r in inherited}
            chosen=[r for r in candidates if (r['group'],r['core']) in allowed][:count]
        else:
            for row in candidates:
                handle=claim_core(row)
                if handle is None:continue
                handles.append(handle);chosen.append(row)
                if len(chosen)==count:break
        if len(chosen)!=count:raise RuntimeError('R011_AVAILABLE_PHYSICAL_CPU_CAPACITY_REQUIRED')
        selected=[row['logical'] for row in chosen];process.cpu_affinity(selected)
        token=_reservation.set(chosen)
        highest=max(row['efficiency_class'] for row in rows)
        metadata.update(cpu_sets=rows,physical_core_selection=chosen,selected_affinity=process.cpu_affinity(),
            applied=selected!=before,efficiency_core_fallback=any(row['efficiency_class']<highest for row in chosen),
            inherited_own_stage_reservation=bool(inherited))
        yield metadata
    finally:
        if token is not None:_reservation.reset(token)
        try:
            if process.cpu_affinity()!=before:process.cpu_affinity(before)
            metadata['restored_affinity']=process.cpu_affinity();metadata['restored']=metadata['restored_affinity']==before
        finally:
            for stream in reversed(handles):release_core(stream)
        if receipt is not None:
            path=Path(receipt)
            if path.parent.exists():
                from v44.common import atomic,now
                atomic(path,dict(UTC=now(),**metadata))


@contextmanager
def actual_cpu_scope(receipt=None):
    with compute_cpu_scope(1,receipt) as metadata:yield metadata
