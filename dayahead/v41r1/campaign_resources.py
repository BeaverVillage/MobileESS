"""Four simultaneous full-model build/solve probes; never scientific policy results."""
import argparse
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import psutil
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME


class Paging:
    """Windows measured paging rates, independent of psutil's unsupported sin/sout."""
    def __init__(self):
        self.pdh=ctypes.windll.pdh;self.query=ctypes.c_void_p();self.counters={}
        self.pdh.PdhOpenQueryW(None,0,ctypes.byref(self.query))
        for name,path in {'pages_input_per_sec':r'\Memory\Pages Input/sec',
                          'page_reads_per_sec':r'\Memory\Page Reads/sec',
                          'pagefile_percent':r'\Paging File(_Total)\% Usage'}.items():
            handle=ctypes.c_void_p()
            if not self.pdh.PdhAddEnglishCounterW(self.query,path,0,ctypes.byref(handle)):
                self.counters[name]=handle
        self.pdh.PdhCollectQueryData(self.query)
    def sample(self):
        class Value(ctypes.Structure):
            _fields_=[('status',ctypes.c_ulong),('value',ctypes.c_double)]
        self.pdh.PdhCollectQueryData(self.query);result={}
        for name,handle in self.counters.items():
            value=Value();code=self.pdh.PdhGetFormattedCounterValue(handle,0x200,None,ctypes.byref(value))
            result[name]=value.value if code==0 and value.status in (0,1) else None
        return result
    def close(self):self.pdh.PdhCloseQuery(self.query)


def worker(folder,index):
    from dayahead.v41.electrical import load
    from dayahead.v41.common import build
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v40g.optimizer import solve
    from dayahead.v41.execution import science
    output=folder/f'worker_{index}';output.mkdir(parents=True,exist_ok=True)
    source=science();write_json(output/'START.json',dict(pid=os.getpid(),started=time.time(),source=source))
    # Replicas share one day input; serialize only the legacy loader's
    # identical certificate write. Production target days have distinct paths.
    import msvcrt
    lock=(folder/'shared_input_load.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    while True:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);break
        except OSError:time.sleep(.1)
    try:context=load('2025-05-01')
    finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
    try:
        snapshot=RUNTIME/'inputs/2025-05-01/V41_ML_SNAPSHOT_2025-05-01.json'
        bind(context,snapshot,record(snapshot)['sha256'])
        reference,_=build('2025-05-01',snapshot,context.capacity)
        power=planning_power(import_frozen(reference),context)
        structure=solve(reference,power['pcc'],context,output,build_only=True,diagnostic_work_limit=180)
        probe=read(output/'INFRASTRUCTURE_SOLVE_MEMORY.json')
        assert probe['status'] in (2,16) and probe['memory']['Threads']==4
        assert probe['memory']['SoftMemLimit_GB']=='UNLIMITED' and probe['memory']['MemLimit_GB']=='UNLIMITED'
        assert structure['domain_counts']['options']==4251141 and structure['matrix_nonzeros']==6838619
        assert source==science()
        write_json(output/'PASS.json',dict(status='PASS',scientific_solution=False,
            original_explicit_candidates=4251141,source=source,
            model=record(output/'PRIMARY_STRUCTURE.json'),build=record(output/'MODEL_BUILD_MEMORY.json'),
            solve=record(output/'INFRASTRUCTURE_SOLVE_MEMORY.json'),
            persistence=record(output/'MODEL_PERSISTENCE.json'),completed=time.time()))
    finally:context.electrical.voltage.close();context.electrical.current.close()


def stress():
    from dayahead.v41.execution import science
    folder=RUNTIME/'memory_stress'/uuid.uuid4().hex[:12];folder.mkdir(parents=True)
    source=science();write_json(OUT/'FOUR_WORKER_STRESS_CURRENT.json',dict(folder=str(folder),source=source))
    processes=[];streams=[];samples=[];paging=Paging();start=time.time()
    try:
        for i in range(4):
            stream=(folder/f'worker_{i}.log').open('w',encoding='utf-8');streams.append(stream)
            command=[sys.executable,'-u','-m','dayahead.v41r1.campaign_resources','worker','--folder',str(folder),'--index',str(i)]
            processes.append(subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                              stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW))
        while any(p.poll() is None for p in processes):
            now=time.time();host=psutil.virtual_memory();workers=[]
            for p in processes:
                try:
                    process=psutil.Process(p.pid);memory=process.memory_info()._asdict()
                    workers.append(dict(pid=p.pid,memory=memory,cpu_seconds=sum(process.cpu_times()[:2])))
                except psutil.NoSuchProcess:pass
            sample=dict(at=now,elapsed=now-start,available_RAM_bytes=host.available,
                used_host_RAM_bytes=host.total-host.available,workers=workers,paging=paging.sample(),
                swap=psutil.swap_memory()._asdict())
            samples.append(sample)
            heartbeat=dict(status='RUNNING',at=now,folder=str(folder),workers=workers,
                available_RAM_bytes=host.available,fixed_workers=4,threads_per_worker=4)
            before=time.perf_counter();write_json(folder/'heartbeat.json',heartbeat)
            assert read(folder/'heartbeat.json')==heartbeat
            sample['monitor_readback_seconds']=time.perf_counter()-before
            write_json(folder/'MEMORY_SAMPLES.json',dict(samples=samples))
            time.sleep(1)
        codes=[p.wait() for p in processes]
        peak=max(sum(w['memory']['rss'] for w in s['workers']) for s in samples)
        minimum=min(s['available_RAM_bytes'] for s in samples)
        gaps=[b['at']-a['at'] for a,b in zip(samples,samples[1:])]
        errors=[]
        if codes!=[0]*4:errors.append('WORKER_FAILURE')
        if minimum<2*1024**3:errors.append('INSUFFICIENT_MEASURED_HOST_HEADROOM')
        if max(gaps,default=0)>15:errors.append('HEARTBEAT_UNRESPONSIVE')
        workers=[]
        if not errors:
            for i in range(4):
                value=read(folder/f'worker_{i}/PASS.json');assert value['source']==source
                for key in ('model','build','solve','persistence'):
                    assert record(value[key]['path'])==value[key]
                workers.append(value)
        result=dict(status='FAIL' if errors else 'PASS',errors=errors,worker_exit_codes=codes,
            source=source,PARALLEL_DAY_WORKERS=4,SOLVER_THREADS_PER_DAY=4,
            explicit_candidates_per_worker=4251141,representative='Four copies of the full causal May-1 model; no scientific candidate pruning',
            scientific_policy_results_produced=False,bounded_probe_work_per_worker=180,
            peak_simultaneous_worker_RSS_bytes=peak,peak_host_used_RAM_bytes=max(s['used_host_RAM_bytes'] for s in samples),
            minimum_available_RAM_bytes=minimum,maximum_heartbeat_gap_seconds=max(gaps,default=0),
            maximum_monitor_readback_seconds=max(s['monitor_readback_seconds'] for s in samples),
            peak_pagefile_used_bytes=max(s['swap']['used'] for s in samples),
            paging_counters_available=all(all(v is not None for v in s['paging'].values()) and len(s['paging'])==3 for s in samples[1:]),
            samples=record(folder/'MEMORY_SAMPLES.json'),workers=workers,folder=str(folder),
            memory_limits='UNLIMITED_BY_USER',NodefileStart_GB=.5,Method=1,
            guarantee='Measured build and bounded primary solve envelope only; later campaign memory and artifacts remain monitored')
        write_json(folder/'RESULT.json',result);write_json(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json',result)
        print({k:result[k] for k in ('status','errors','peak_simultaneous_worker_RSS_bytes','minimum_available_RAM_bytes')},flush=True)
    finally:
        paging.close()
        for stream in streams:stream.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['stress','worker'])
    p.add_argument('--folder',type=Path);p.add_argument('--index',type=int);args=p.parse_args()
    stress() if args.mode=='stress' else worker(args.folder,args.index)
