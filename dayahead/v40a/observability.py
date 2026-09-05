"""Process-local solver event accounting, including inherited beam children."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import os
import time
import gurobipy as gp

_original = gp.Model.optimize
_event_root = None
_stage = 'UNSPECIFIED'


def install(root, stage):
    global _event_root, _stage
    _event_root=Path(root);_event_root.mkdir(parents=True,exist_ok=True);_stage=stage
    gp.Model.optimize=counted_optimize


def counted_optimize(model, *args, **kwargs):
    started=time.perf_counter()
    try:return _original(model,*args,**kwargs)
    finally:
        if _event_root is not None:
            row={'pid':os.getpid(),'stage':_stage,'wallclock_seconds':time.perf_counter()-started}
            try:row.update(model_name=model.ModelName,status=int(model.Status),work=float(model.Work),solver_runtime_seconds=float(model.Runtime),sol_count=int(model.SolCount))
            except gp.GurobiError:pass
            with (_event_root/f'{os.getpid()}.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush()


def initialize(root, initializer, initargs):
    install(root,'M1')
    from dayahead.v39e.runtime import initialize_runtime_worker
    initialize_runtime_worker(initializer,initargs)


class ObservedProductionPool(ProcessPoolExecutor):
    def __init__(self,max_workers=None,*,initializer=None,initargs=(),**kwargs):
        super().__init__(max_workers=1,initializer=initialize,initargs=(str(_event_root),initializer,initargs),**kwargs)


def read_events(root):
    rows=[]
    for p in sorted(Path(root).glob('*.jsonl')):
        rows.extend(json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line)
    return rows
