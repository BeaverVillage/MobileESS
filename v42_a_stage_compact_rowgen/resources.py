"""System-wide memory only; never inspect or control the M-stage process."""
import ctypes
import psutil
class MemoryStatus(ctypes.Structure):
    _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong)]+[(k,ctypes.c_ulonglong) for k in ('ullTotalPhys','ullAvailPhys','ullTotalPageFile','ullAvailPageFile','ullTotalVirtual','ullAvailVirtual','ullAvailExtendedVirtual')]
def sample():
    m=MemoryStatus();m.dwLength=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('SYSTEM_COMMIT_MONITOR_UNAVAILABLE')
    reserve=2*1024**3
    workers=4 if min(m.ullAvailPhys,m.ullAvailPageFile)>8*1024**3 else 2 if min(m.ullAvailPhys,m.ullAvailPageFile)>4*1024**3 else 1
    return dict(available_RAM_bytes=m.ullAvailPhys,total_RAM_bytes=m.ullTotalPhys,
        commit_limit_bytes=m.ullTotalPageFile,available_commit_bytes=m.ullAvailPageFile,
        committed_bytes=m.ullTotalPageFile-m.ullAvailPageFile,allowed_pricing_workers=workers,
        reserve_bytes=reserve,unsafe=min(m.ullAvailPhys,m.ullAvailPageFile)<reserve,
        A_process_RSS_bytes=psutil.Process().memory_info().rss)
