"""Memory telemetry only. No reserve, allocation cap, or memory stop."""
import ctypes
import psutil
from v42_a_stage_compact_rowgen.resources import MemoryStatus

def sample():
    out=dict(memory_limits_enabled=False,automatic_memory_stop=False)
    m=MemoryStatus();m.dwLength=ctypes.sizeof(m)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('SYSTEM_MEMORY_TELEMETRY_UNAVAILABLE')
        out.update(available_RAM_bytes=m.ullAvailPhys,total_RAM_bytes=m.ullTotalPhys,
            system_commit_limit_bytes=m.ullTotalPageFile,available_commit_bytes=m.ullAvailPageFile,
            committed_bytes=m.ullTotalPageFile-m.ullAvailPageFile)
    except Exception as error:out['system_memory_telemetry_error']=repr(error)
    try:out['A_process_RSS_bytes']=psutil.Process().memory_info().rss
    except Exception as error:out.update(A_process_RSS_bytes=None,RSS_telemetry_error=repr(error))
    return out
