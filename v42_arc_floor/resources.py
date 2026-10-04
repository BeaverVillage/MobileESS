"""Windows commit and hard paging counters; sampled peaks, not exact peaks."""
from .common import *
import psutil,threading,ctypes
from ctypes import wintypes as W
from datetime import datetime,timezone
class Performance(ctypes.Structure):
    _fields_=[('cb',W.DWORD)]+[(n,ctypes.c_size_t) for n in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(n,W.DWORD) for n in ('HandleCount','ProcessCount','ThreadCount')]
class CounterValue(ctypes.Structure):
    _fields_=[('CStatus',W.DWORD),('doubleValue',ctypes.c_double)]
class WindowsCounters:
    def __init__(self):
        self.query=W.HANDLE();self.counter=W.HANDLE();self.pdh=ctypes.WinDLL('pdh');self.psapi=ctypes.WinDLL('psapi');self.error=None
        self.psapi.GetPerformanceInfo.argtypes=[ctypes.POINTER(Performance),W.DWORD];self.psapi.GetPerformanceInfo.restype=W.BOOL
        self.pdh.PdhOpenQueryW.argtypes=[W.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(W.HANDLE)]
        self.pdh.PdhAddEnglishCounterW.argtypes=[W.HANDLE,W.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(W.HANDLE)]
        self.pdh.PdhCollectQueryData.argtypes=[W.HANDLE]
        self.pdh.PdhGetFormattedCounterValue.argtypes=[W.HANDLE,W.DWORD,ctypes.POINTER(W.DWORD),ctypes.POINTER(CounterValue)]
        self.pdh.PdhCloseQuery.argtypes=[W.HANDLE]
        try:
            assert self.pdh.PdhOpenQueryW(None,0,ctypes.byref(self.query))==0
            assert self.pdh.PdhAddEnglishCounterW(self.query,r'\Memory\Pages Input/sec',0,ctypes.byref(self.counter))==0
            assert self.pdh.PdhCollectQueryData(self.query)==0
        except Exception as e:self.error=repr(e)
    def sample(self):
        p=Performance();p.cb=ctypes.sizeof(p);ok=self.psapi.GetPerformanceInfo(ctypes.byref(p),p.cb)
        charge=int(p.CommitTotal*p.PageSize) if ok else None;limit=int(p.CommitLimit*p.PageSize) if ok else None
        rate=None
        if self.error is None:
            try:
                status=self.pdh.PdhCollectQueryData(self.query);v=CounterValue();kind=W.DWORD()
                result=self.pdh.PdhGetFormattedCounterValue(self.counter,0x200,ctypes.byref(kind),ctypes.byref(v))
                if status==0 and result==0 and v.CStatus in (0,1):rate=float(v.doubleValue)
            except Exception as e:self.error=repr(e)
        return dict(commit_charge=charge,commit_limit=limit,commit_percent=100*charge/limit if limit else None,hard_page_input_pages_per_sec=rate,hard_page_fault_events_per_sec=None,hard_paging_source='PDH Memory Pages Input/sec: pages read for hard faults; not fault-event count',hard_paging_counter_error=self.error,commit_source='GetPerformanceInfo CommitTotal/CommitLimit * PageSize',thermal_C=None,clock_MHz=psutil.cpu_freq().current if psutil.cpu_freq() else None)
    def close(self):
        if self.query:self.pdh.PdhCloseQuery(self.query)
class Monitor:
    def __init__(self,pids,stop_event):
        self.pids=pids;self.stop_event=stop_event;self.rows=[];self.phase='build';self.begin=time.perf_counter();self.failed=[];self.baseline=psutil.swap_memory().used;self.done=threading.Event();self.lock=threading.Lock();self.processes={};self.windows=WindowsCounters();self.parent=psutil.Process();self.parent.cpu_percent()
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
    def sample(self):
        with self.lock:
            v=psutil.virtual_memory();s=psutil.swap_memory();children=[]
            for pid in list(self.pids):
                try:
                    p=self.processes.setdefault(pid,psutil.Process(pid));children.append(dict(pid=pid,RSS=p.memory_info().rss,CPU_percent=p.cpu_percent()))
                except psutil.NoSuchProcess:pass
            parent=self.parent.memory_info().rss
            r=dict(UTC=datetime.now(timezone.utc).isoformat(),perf=time.perf_counter(),elapsed=time.perf_counter()-self.begin,phase=self.phase,parent_RSS=parent,pricing_RSS=sum(x['RSS'] for x in children),total_tree_RSS=parent+sum(x['RSS'] for x in children),pricing_processes=children,available_RAM=v.available,total_RAM=v.total,pagefile_used=s.used,pagefile_delta=s.used-self.baseline,CPU_total_percent=psutil.cpu_percent(),CPU_parent_percent=self.parent.cpu_percent(),license_errors=None,**self.windows.sample())
            self.rows.append(r);path=OUT/'DW_TRUE_4WAY_RESOURCE_TIMELINE.csv';exists=path.exists()
            with path.open('a',encoding='utf8',newline='') as f:
                flat=dict(r,pricing_processes=json.dumps(children));writer=csv.DictWriter(f,fieldnames=list(flat))
                if not exists:writer.writeheader()
                writer.writerow(flat)
            reasons=resource_failures(r,self.rows)
            if STOP.exists():reasons.append('USER_STOP_REQUEST')
            if reasons:self.failed.extend(reasons);self.stop_event.set()
            return r
    def watch(self):
        while not self.done.wait(.5):
            try:self.sample()
            except Exception as e:
                self.failed.append('TELEMETRY_FAILURE:'+repr(e));self.stop_event.set();break
    def close(self):
        self.done.set();self.thread.join();self.sample();self.windows.close()
    def summary(self,rows):
        return dict(observed_per_process_peak_RSS={str(pid):max((p['RSS'] for r in rows for p in r['pricing_processes'] if p['pid']==pid),default=0) for pid in self.pids},observed_total_pricing_peak_RSS=max((r['pricing_RSS'] for r in rows),default=0),observed_total_tree_peak_RSS=max((r['total_tree_RSS'] for r in rows),default=0),observed_parent_peak_RSS=max((r['parent_RSS'] for r in rows),default=0),min_available_RAM=min((r['available_RAM'] for r in rows),default=None),physical_RAM=rows[0]['total_RAM'] if rows else None,max_commit_percent=max((r['commit_percent'] for r in rows if r['commit_percent'] is not None),default=None),pagefile_delta_bytes=(rows[-1]['pagefile_used']-rows[0]['pagefile_used']) if rows else None,max_pagefile_delta_bytes=max((r['pagefile_delta'] for r in rows),default=None),max_hard_page_input_pages_per_sec=max((r['hard_page_input_pages_per_sec'] for r in rows if r['hard_page_input_pages_per_sec'] is not None),default=None),hard_fault_events_observable=False,hard_paging_pages_observable=any(r['hard_page_input_pages_per_sec'] is not None for r in rows),max_CPU_percent=max((r['CPU_total_percent'] for r in rows),default=None),sample_target_seconds=.5,max_sample_gap_seconds=max((b['perf']-a['perf'] for a,b in zip(rows,rows[1:])),default=None),exact_unsampled_peak_not_claimed=True,thermal_observable=False,license_errors=[])
