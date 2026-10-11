"""Actual RAM/Windows commit observations; only new dispatch is delayed."""
import ctypes
from ctypes import wintypes
import psutil

GIB=1024**3
class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
        ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache',
         'KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(name,wintypes.DWORD) for name in
        ('HandleCount','ProcessCount','ThreadCount')]

def snapshot():
    p=PERFORMANCE_INFORMATION();p.cb=ctypes.sizeof(p)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.cb):raise ctypes.WinError()
    ram=psutil.virtual_memory()
    return dict(RAM_total=ram.total,RAM_available=ram.available,RAM_used=ram.used,
        Commit_total=p.CommitTotal*p.PageSize,Commit_limit=p.CommitLimit*p.PageSize,
        Commit_available=(p.CommitLimit-p.CommitTotal)*p.PageSize,Commit_peak=p.CommitPeak*p.PageSize)

def admits(memory,peers,stage,contract):
    reservation=contract['worker_reservation_bytes'][stage]
    growth=reservation
    for peer in peers:
        p=psutil.Process(peer['PID']);info=p.memory_info()
        growth+=max(0,reservation-max(info.rss,getattr(info,'private',info.rss)))
    need=contract['system_reserve_bytes']+growth
    return memory['RAM_available']>=need and memory['Commit_available']>=need

def returned(before,after):
    # Positive observed release is required in both actual system counters.
    # Other apps can delay admission; process exit alone is not this receipt.
    return after['RAM_available']>=before['RAM_available'] and after['Commit_total']<=before['Commit_total']
