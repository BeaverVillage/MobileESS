"""Audited Q boundary normalization and immutable ETA95 baseline reuse.

Authorized after the May 8 frozen outer/inner bound-check mismatch. Sealed
source files, electrical limits, solver tolerances and Q_DA reference stay intact.
"""
from pathlib import Path
import numpy as np
from types import SimpleNamespace

def boundary_wrapper(original,record):
    def correct(evaluate,q_original,lower,upper,q_da=None):
        q=np.asarray(q_original).copy()
        fixed=np.clip(q,lower,upper)
        delta=float(np.max(np.abs(fixed-q)))
        assert delta<=1e-7,('ORIGINAL_Q_OUTSIDE_EXISTING_OUTER_TOLERANCE',delta)
        result=original(evaluate,fixed,lower,upper,q_da=q_da)
        if delta:
            accepted,physical,event=result
            event=dict(event,numerical_boundary_normalization_kvar=delta)
            if event['status']=='UNCHANGED':event['status']='Q_CORRECTED'
            record(dict(Q_original=q.tolist(),Q_initial_normalized=fixed.tolist(),maximum_adjustment_kvar=delta,Q_DA_reference_unchanged=True))
            return accepted,physical,event
        return result
    return correct

def install(worker,common,out,day):
    records=[]
    def record(row):
        records.append(row)
        common.save(out/'NUMERICAL_BOUNDARY_NORMALIZATION.json',dict(
            user_authorized=True,existing_outer_acceptance_kvar=1e-7,
            electrical_constraints_and_tolerances_changed=False,
            exact_frozen_execution_deviation='Initial Q projected to existing bounds within original outer acceptance only',
            events=records))
    search=worker.robust_search
    search.namespace['correct_slot']=boundary_wrapper(search.correct_slot,record)
    # Reuse only the baseline from this exact date/decision; never another policy.
    baseline=out/'replays'/day/'B3/ETA95_ACTUAL'
    required=['EXECUTION.npz','OPENDSS_SUMMARY.json','ACTUAL_ENGINE_BINDING_READBACK.json','ACTUATOR.json']
    if not all((baseline/name).exists() for name in required):return
    hashes={str(p):common.sha(p) for p in baseline.iterdir() if p.is_file()}
    old_replay=worker.namespace['replay'];old_save=worker.namespace['save']
    class ArraysProxy:
        def __getattr__(self,name):return getattr(np,name)
        def savez_compressed(self,path,**values):
            if Path(path)==baseline/'EXECUTION.npz':
                previous=common.arrays(path)
                assert previous.keys()==values.keys() and all(np.array_equal(previous[k],v) for k,v in values.items()),'BASELINE_EXECUTION_REUSE_MISMATCH'
                return
            return np.savez_compressed(path,**values)
    def save(path,value):
        if Path(path)==baseline/'ACTUATOR.json':
            assert common.read(path)==common.clean(value),'BASELINE_ACTUATOR_REUSE_MISMATCH'
            return
        return old_save(path,value)
    def replay(*args,**kwargs):
        folder=Path(args[-1]) if args else Path(kwargs['output'])
        if folder!=baseline:return old_replay(*args,**kwargs)
        assert all(common.sha(p)==h for p,h in hashes.items()),'BASELINE_REUSE_SHA_CHANGED'
        summary=common.read(baseline/'OPENDSS_SUMMARY.json')
        common.save(out/'ETA95_BASELINE_REUSE.json',dict(status='PASS',source_hashes=hashes,baseline_AC_rerun=False,decision_and_actuator_revalidated=True))
        return SimpleNamespace(summary=summary),common.read(baseline/'ACTUAL_ENGINE_BINDING_READBACK.json')
    worker.namespace.update(replay=replay,save=save,np=ArraysProxy())
