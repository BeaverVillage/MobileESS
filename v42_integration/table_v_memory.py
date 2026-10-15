"""Small process/RAM/system commit telemetry without a subprocess per tick."""
import os


def memory_sample():
    import psutil
    process=psutil.Process();memory=process.memory_info();system=psutil.virtual_memory()
    row=dict(RSS_bytes=memory.rss,private_bytes=getattr(memory,'private',None),
        system_available_bytes=system.available,system_RAM_bytes=system.total,
        system_committed_bytes=None,system_commit_limit_bytes=None)
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Performance(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
                 'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
                 ('HandleCount',wintypes.DWORD),('ProcessCount',wintypes.DWORD),('ThreadCount',wintypes.DWORD)]
        data=Performance();data.cb=ctypes.sizeof(data)
        if ctypes.WinDLL('psapi').GetPerformanceInfo(ctypes.byref(data),data.cb):
            row.update(system_committed_bytes=data.CommitTotal*data.PageSize,
                       system_commit_limit_bytes=data.CommitLimit*data.PageSize)
    return row
