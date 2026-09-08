"""Four simultaneous full-size F&O model copies, four Gurobi threads each."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import psutil
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from dayahead.v41.data import RUNTIME


def worker(root,index):
    import gurobipy as gp
    from .feasible_seed import row_audit
    from .bounded_solver import BoundedLex,PolicyBudget
    root=Path(root);out=root/str(index);out.mkdir(parents=True,exist_ok=True)
    request=read(root/'REQUEST.json');m=gp.read(request['model'])
    try:
        m.Params.OutputFlag=0;m.Params.Threads=4;m.Params.Method=1;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
        m.Params.NodefileStart=.5;m.Params.NodefileDir=str(out)
        with np.load(request['seed'],allow_pickle=False) as z:
            by_name=dict(zip(z['names'].tolist(),z['values'].tolist()))
        values=np.asarray([by_name[v.VarName] for v in m.getVars()]);del by_name
        assert row_audit(m,values)['status']=='PASS'
        write_json(out/'READY.json',dict(pid=os.getpid(),variables=m.NumVars,nonzeros=m.NumNZs))
        while not (root/'GO.json').exists():time.sleep(.25)
        engine=BoundedLex(m,values,out,PolicyBudget(40),allocation=[1],objective_expressions=[m.getObjective()])
        stage=engine.optimize('P1_STRESS');assert stage['feasibility']['status']=='PASS'
        write_json(out/'RESULT.json',dict(status='PASS',threads=m.Params.Threads,variables=m.NumVars,
            matrix_nonzeros=m.NumNZs,stage=stage,peak_rss=psutil.Process().memory_info()._asdict().get('peak_wset')))
    finally:m.dispose()


def run(seed_root,tag):
    seed_root=Path(seed_root);root=RUNTIME/'bounded_compute'/tag
    if root.exists():raise ValueError('PRESERVE_STRESS_ATTEMPT')
    root.mkdir(parents=True);short=Path('D:/MobileESS_FO_stress')/uuid.uuid4().hex[:10];short.mkdir(parents=True)
    model=short/'model.mps';h=hashlib.sha256()
    with gzip.open(seed_root/'PRIMARY_MODEL.mps.gz','rb') as src,model.open('wb') as dst:
        for block in iter(lambda:src.read(8*1024*1024),b''):h.update(block);dst.write(block)
    write_json(root/'REQUEST.json',dict(model=str(model),seed=str(seed_root/'POLICY_FEASIBLE_SEED.npz'),
        uncompressed_model_SHA=h.hexdigest(),input_model=record(seed_root/'PRIMARY_MODEL.mps.gz'),input_seed=record(seed_root/'POLICY_FEASIBLE_SEED.npz')))
    processes=[];streams=[];samples=[];started=time.time()
    try:
        for i in range(4):
            stream=(root/f'worker_{i}.log').open('w',encoding='utf-8');streams.append(stream)
            processes.append(subprocess.Popen([sys.executable,'-u','-m','dayahead.v41r1.fo_stress','worker',str(root),'--index',str(i)],
                stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        while any(p.poll() is None for p in processes):
            if any(p.poll() not in (None,0) for p in processes):raise RuntimeError('FOUR_WORKER_STRESS_CHILD_FAILED')
            if time.time()-started>600:raise RuntimeError('STRESS_IMPLEMENTATION_DEADLINE')
            workers=[]
            for p in processes:
                try:workers.append(dict(pid=p.pid,rss=psutil.Process(p.pid).memory_info().rss))
                except psutil.NoSuchProcess:pass
            samples.append(dict(at=time.time(),workers=workers,available=psutil.virtual_memory().available))
            if all((root/str(i)/'READY.json').exists() for i in range(4)) and not (root/'GO.json').exists():
                write_json(root/'GO.json',dict(at=time.time(),simultaneous_ready_workers=4));print('FOUR_MODELS_READY',flush=True)
            time.sleep(1)
        results=[read(root/str(i)/'RESULT.json') for i in range(4)]
        assert all(r['status']=='PASS' and r['threads']==4 for r in results)
        value=dict(status='PASS',workers=4,threads_per_worker=4,case='2025-05-04_B1_FOUR_IDENTICAL_FULL_SIZE_COPIES',
            wall_seconds=time.time()-started,uncompressed_model_SHA=h.hexdigest(),results=results,
            maximum_worker_RSS_sum=max(sum(p['rss'] for p in s['workers']) for s in samples),
            minimum_available_RAM=min(s['available'] for s in samples),samples=samples,request=record(root/'REQUEST.json'))
        write_json(root/'STRESS_RESULT.json',value);print('FOUR_BY_FOUR_STRESS_PASS',flush=True)
    except BaseException as error:
        write_json(root/'STRESS_ERROR.json',dict(error=repr(error),samples=samples));raise
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:p.wait()
        for stream in streams:stream.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['run','worker']);p.add_argument('path');p.add_argument('--tag');p.add_argument('--index',type=int)
    a=p.parse_args();worker(a.path,a.index) if a.mode=='worker' else run(a.path,a.tag)
