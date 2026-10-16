"""Atomic native observations and unmodified terminal LP diagnostic arrays."""
import json
import math
import os
from pathlib import Path
from time import time,perf_counter
import uuid


def atomic_json(path,value):
    path=Path(path);temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)


class NativeJournal:
    def __init__(self,budget,label):
        self.budget=budget;self.label=label;self.last=-float('inf');self.observed=0.;self.errors=[]
        self.folder=Path(budget.path).parent/'NATIVE_CALL_JOURNAL'/uuid.uuid4().hex
        self.folder.mkdir(parents=True,exist_ok=False)
        atomic_json(self.folder/'START.json',dict(label=label,pid=os.getpid(),
            epoch_seconds=time(),diagnostic_only=True,FULL_UB_claimed=False))

    def callback(self,model,where):
        now=perf_counter()
        if now-self.last<2.:return
        try:
            import gurobipy as gp
            if where==gp.GRB.Callback.POLLING:return
            runtime=float(model.cbGet(gp.GRB.Callback.RUNTIME))
            if not math.isfinite(runtime) or runtime<self.observed:return
            call=self.budget.document.get('inflight')
            if not call or call.get('pid')!=os.getpid() or call.get('label')!=self.label:return
            atomic_json(self.folder/'LIVE.json',dict(schema='TABLE_V_NATIVE_RUNTIME_OBSERVATION_V1',
                pid=os.getpid(),observed_epoch_seconds=time(),Native_Runtime_observed=runtime,
                inflight=call,final_Runtime_available=False,diagnostic_only=True,FULL_UB_claimed=False))
            self.observed=runtime;self.last=now
        except Exception as error:
            if not self.errors:self.errors.append(repr(error))

    def finish(self,model,row):
        # Attribute reads never invoke optimize/presolve. Unavailable LP
        # attributes stay absent; partial BarX is never promoted to X or UB.
        import numpy as np
        from .m_engine import file_record
        arrays={};scalars={}
        if row.get('native_execution_entered'):
            for key in ('BarX','X','Pi','RC','VBasis','CBasis'):
                try:arrays[key]=np.asarray(model.getAttr(key))
                except Exception:pass
            for key in ('Kappa','BarIterCount','IterCount','SolCount'):
                try:
                    value=float(getattr(model,key))
                    if math.isfinite(value):scalars[key]=value
                except Exception:pass
        record=None
        if arrays:
            path=self.folder/'UNMODIFIED_NATIVE_ATTRIBUTES.npz'
            np.savez_compressed(path,**arrays);record=file_record(path)
        atomic_json(self.folder/'TERMINAL.json',dict(label=self.label,finalized_call=row,
            arrays=record,available_attributes=list(arrays),scalar_attributes=scalars,
            observed_native_runtime_lower_bound=self.observed,journal_errors=self.errors,
            diagnostic_only=True,partial_BarX_is_not_original_FULL_UB=True,
            original_solver_return_attributes_unmodified=True))
