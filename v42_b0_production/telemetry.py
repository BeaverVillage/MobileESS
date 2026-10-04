"""Live Windows physical/commit/paging and registered B0 process-tree telemetry."""
import csv
import ctypes
import json
import os
from pathlib import Path
import threading
import time
from ctypes import wintypes

import psutil
from v42_orchestrator.resources import Telemetry
from .authority import record


class PerformanceInfo(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('CommitTotal', ctypes.c_size_t),
        ('CommitLimit', ctypes.c_size_t), ('CommitPeak', ctypes.c_size_t),
        ('PhysicalTotal', ctypes.c_size_t), ('PhysicalAvailable', ctypes.c_size_t),
        ('SystemCache', ctypes.c_size_t), ('KernelTotal', ctypes.c_size_t),
        ('KernelPaged', ctypes.c_size_t), ('KernelNonpaged', ctypes.c_size_t),
        ('PageSize', ctypes.c_size_t), ('HandleCount', wintypes.DWORD),
        ('ProcessCount', wintypes.DWORD), ('ThreadCount', wintypes.DWORD)]


def commit_percent():
    data = PerformanceInfo(cb=ctypes.sizeof(PerformanceInfo))
    function = ctypes.WinDLL('psapi').GetPerformanceInfo
    function.argtypes = [ctypes.POINTER(PerformanceInfo), wintypes.DWORD]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(data), data.cb) or not data.CommitLimit:
        raise OSError('Windows system commit telemetry unavailable')
    return 100 * data.CommitTotal / data.CommitLimit


class Paging:
    def __init__(self):
        self.dll = ctypes.WinDLL('pdh')
        self.query = wintypes.HANDLE()
        self.counter = wintypes.HANDLE()
        self.available = False
        self.dll.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        self.dll.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        self.dll.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        if self.dll.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) == 0:
            self.available = self.dll.PdhAddEnglishCounterW(self.query, r'\Memory\Pages Input/sec', 0, ctypes.byref(self.counter)) == 0
            if self.available:
                self.dll.PdhCollectQueryData(self.query)

    def sample(self):
        if not self.available:
            return None
        class Value(ctypes.Structure):
            _fields_ = [('status', wintypes.DWORD), ('value', ctypes.c_double)]
        value = Value()
        function = self.dll.PdhGetFormattedCounterValue
        function.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(Value)]
        self.dll.PdhCollectQueryData(self.query)
        code = function(self.counter, 0x200, None, ctypes.byref(value))
        return float(value.value) if code == 0 and value.status in (0, 1) else None

    def close(self):
        self.dll.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        if self.query:
            self.dll.PdhCloseQuery(self.query)


def is_verification_command(command):
    text = ' '.join(command).lower()
    # This exact module was audited: immutable matrices/certificates only,
    # native_optimize_calls=0. Do not exempt other DW run/pricing commands.
    audited_verifier_SHA = 'f758bf5c07729e55e968056fd5c48f18e30f714997820de196f208f9c4bcef17'
    for argument in command:
        if Path(argument).name == 'verify_lane_tests.py':
            try:
                if record(argument)['sha256'] == audited_verifier_SHA:
                    return True
            except OSError:
                pass
    return ('v42_dw_accelerated.base' in command or
            any(x in text for x in ('unittest', 'v42_orchestrator mock', 'v42_orchestrator verify',
                                   '.finalize', '.report', '.prepare', '.verify', 'semantic', 'static')))


def module_paths(pid):
    """Enumerate loaded DLLs without scanning every mapped memory region."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    api = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise psutil.AccessDenied(pid)
    try:
        modules = (wintypes.HMODULE * 1024)()
        needed = wintypes.DWORD()
        api.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        if not api.EnumProcessModulesEx(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3):
            raise psutil.AccessDenied(pid)
        if needed.value > ctypes.sizeof(modules):
            raise OSError('Native module inventory exceeded the audited buffer')
        api.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        paths = []
        buffer = ctypes.create_unicode_buffer(32768)
        for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
            if api.GetModuleFileNameExW(handle, module, buffer, len(buffer)):
                paths.append(buffer.value.lower())
        return paths
    finally:
        kernel.CloseHandle(handle)


def is_heavy_command(command, rss, native_modules, cpu_delta):
    text = ' '.join(command).lower()
    if is_verification_command(command):
        return False
    native = any('gurobi' in n or 'dss_capi' in n for n in native_modules)
    run = any(x in text for x in ('gurobi_cl', 'v42_arc_floor.run', 'v42_dw_', 'v42_benders',
                                 'run_worker', 'production', 'campaign', 'root_pilot', 'fullscale'))
    return bool(native and run and rss >= 256 * 2**20 and cpu_delta > .05)


class LiveTelemetry:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.lock = threading.RLock()
        self.registered = {}
        self.samples = []
        self.foreign = []
        self.previous_cpu = {}
        self.guard_events = []
        self.current = Telemetry()
        self.paging_since = None
        self.stop_event = threading.Event()
        self.thread = None
        self.started = time.monotonic()
        self.fields = ['elapsed_s', 'timestamp_UTC', 'total_physical_GiB', 'available_GiB', 'commit_percent',
            'pagefile_used_GiB', 'pagefile_change_GiB', 'pages_input_per_sec', 'CPU_percent',
            'B0_tree_RSS_GiB', 'worker_trees', 'foreign_heavy', 'catastrophic_sustained_paging']
        self.stream = (root / 'B0_RESOURCE_TIMELINE.csv').open('w', encoding='utf8', newline='')
        self.writer = csv.DictWriter(self.stream, fieldnames=self.fields, lineterminator='\n')
        self.writer.writeheader()
        self.initial_swap = psutil.swap_memory().used
        self.paging = Paging()
        self.sample()

    def register(self, pid, day, stage):
        with self.lock:
            self.registered[pid] = dict(day=day, stage=stage)

    def unregister(self, pid):
        with self.lock:
            self.registered.pop(pid, None)

    def get(self):
        with self.lock:
            return self.current

    def sample(self):
        from datetime import datetime, timezone
        with self.lock:
            vm = psutil.virtual_memory()
            commit = commit_percent()
            paging = self.paging.sample()
            elapsed = time.monotonic() - self.started
            trees = {}
            known = {os.getpid()}
            for pid, entry in self.registered.items():
                try:
                    process = psutil.Process(pid)
                    family = [process, *process.children(recursive=True)]
                    known.update(p.pid for p in family)
                    rss = sum(p.memory_info().rss for p in family if p.is_running())
                    trees[str(pid)] = dict(entry, RSS_GiB=rss / 2**30)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            foreign = []
            # Query name first: collecting memory/cmdline for hundreds of system
            # services can exceed the sampling deadline on Windows.
            for p in psutil.process_iter(['name']):
                if p.pid in known or (p.info['name'] or '').lower() not in ('python.exe', 'gurobi_cl.exe', 'opendss.exe'):
                    continue
                try:
                    command = p.cmdline() or []
                    times = p.cpu_times()
                    cpu = times.user + times.system
                    delta = cpu - self.previous_cpu.get(p.pid, cpu)
                    self.previous_cpu[p.pid] = cpu
                    # Inspect native modules only for plausible full-scale commands.
                    rss = p.memory_info().rss
                    if is_verification_command(command) or delta <= .05 or rss < 256 * 2**20:
                        continue
                    modules = module_paths(p.pid)
                    if is_heavy_command(command, rss, modules, delta):
                        foreign.append(dict(PID=p.pid, RSS_GiB=rss / 2**30,
                                            classification='active unrelated full-scale native run'))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            high = paging is not None and paging >= self.config.CATASTROPHIC_PAGES_INPUT_PER_SECOND
            self.paging_since = elapsed if high and self.paging_since is None else self.paging_since if high else None
            catastrophic = self.paging_since is not None and elapsed - self.paging_since >= self.config.CATASTROPHIC_PAGING_SUSTAINED_SECONDS
            self.current = Telemetry(available_gib=vm.available / 2**30, commit_percent=commit,
                                     sustained_catastrophic_paging=catastrophic)
            self.foreign = foreign
            swap = psutil.swap_memory().used
            row = dict(elapsed_s=elapsed, timestamp_UTC=datetime.now(timezone.utc).isoformat(),
                total_physical_GiB=vm.total / 2**30, available_GiB=vm.available / 2**30, commit_percent=commit,
                pagefile_used_GiB=swap / 2**30, pagefile_change_GiB=(swap-self.initial_swap)/2**30,
                pages_input_per_sec=paging, CPU_percent=psutil.cpu_percent(interval=None),
                B0_tree_RSS_GiB=sum(v['RSS_GiB'] for v in trees.values()),
                worker_trees=trees, foreign_heavy=foreign, catastrophic_sustained_paging=catastrophic)
            self.samples.append(row)
            self.writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
            self.stream.flush()

    def start(self):
        def loop():
            deadline = time.monotonic() + self.config.SAMPLE_SECONDS
            while not self.stop_event.wait(max(0, deadline - time.monotonic())):
                try:
                    self.sample()
                except BaseException as error:
                    with self.lock:
                        self.current = None
                        self.guard_events.append(dict(reason='TELEMETRY_UNAVAILABLE', error=str(error)))
                deadline = max(deadline + self.config.SAMPLE_SECONDS, time.monotonic())
        self.thread = threading.Thread(target=loop, name='B0-live-telemetry', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)
        self.sample()
        self.stream.close()
        self.paging.close()

    def summary(self):
        rows = self.samples
        return dict(samples=len(rows), configured_sampling_seconds=self.config.SAMPLE_SECONDS,
            maximum_sample_gap_seconds=max((b['elapsed_s']-a['elapsed_s'] for a, b in zip(rows, rows[1:])), default=0),
            total_physical_GiB=rows[0]['total_physical_GiB'], minimum_available_GiB=min(r['available_GiB'] for r in rows),
            maximum_commit_percent=max(r['commit_percent'] for r in rows),
            peak_B0_tree_RSS_GiB=max(r['B0_tree_RSS_GiB'] for r in rows),
            peak_single_worker_tree_RSS_GiB=max((v['RSS_GiB'] for r in rows for v in r['worker_trees'].values()), default=0),
            pagefile_change_GiB=rows[-1]['pagefile_change_GiB'],
            max_pages_input_per_sec=max((r['pages_input_per_sec'] for r in rows if r['pages_input_per_sec'] is not None), default=None),
            paging_counter_available=any(r['pages_input_per_sec'] is not None for r in rows),
            catastrophic_sustained_paging=any(r['catastrophic_sustained_paging'] for r in rows),
            foreign_heavy_observations=sum(bool(r['foreign_heavy']) for r in rows),
            guard_events=self.guard_events, telemetry_source='psutil, Windows GetPerformanceInfo, PDH Pages Input/sec',
            unrelated_processes_terminated=0)
