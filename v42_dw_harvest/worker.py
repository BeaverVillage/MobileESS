"""Owned-process adapter around byte-unchanged PR152 pricing transport."""
from .common import *
from .selection import HarvestState
from .adapter import Adapter
import time


def controller_factory(state, existing, original):
    def factory(kind, unit, snapshot, validator, flags, retained_SHAs=()):
        if kind != 'DISCOVERY':
            return original(kind, unit, snapshot, validator, flags, retained_SHAs)
        class Controller:
            def __init__(self):
                self.harvest = HarvestState(unit, Adapter(validator,snapshot), retained_SHAs, existing)
                self.accepted={};self.errors=[];self.stop_reason=None
                state['controller']=self

            def observe(self, values, native, observed_objective=None):
                try:
                    self.harvest.observe(values,native_objective=observed_objective)
                    self.accepted={c.trajectory_SHA:c for c in self.harvest.useful.values()}
                    if len(self.accepted)>=8:
                        self.stop_reason='MULTICOLUMN_QUOTA_FILLED';native.terminate()
                except Exception as e:
                    self.errors.append(repr(e));self.accepted.clear()
                    self.stop_reason='CALLBACK_VALIDATION_ERROR';native.terminate()

            def terminal_receipt(self,status):
                return dict(native_status=int(status),STOP_REASON=self.stop_reason,accepted_count=len(self.accepted),accepted_SHAs=sorted(self.accepted),true_dual_SHA=snapshot.dual_SHA,iteration=snapshot.iteration,valid_bound=False,pricing_optimality_claimed=False,no_negative_certificate=False,pricing_convergence=False,errors=self.errors.copy())
        return Controller()
    return factory


def main(connection,unit,stop_event,legroot,mode,existing):
    """Exactly one old worker job; no modification to old files or certificates."""
    import numpy as np,gurobipy as gp
    import v42_dw_continuation.worker as legacy
    import v42_dw_runtime.validation as validation
    legroot=Path(legroot);live=legroot/'live';os.chdir(legroot)
    legacy.ROOT=legroot;legacy.OUT=live;legacy.SCI=legroot/'immutable'
    legacy.STOP=live/'STOP_REQUEST.json'
    legacy.write=lambda name,value:write(live/name,value)
    original_optimize=gp.Model.optimize;original_controller=validation.DiscoveryController
    events=dict(encountered=0,negative_candidates=0,optimize_calls=0)
    state={}
    if mode=='CHALLENGER':
        legacy.MAX_COLUMNS=8
        validation.DiscoveryController=controller_factory(state,existing,original_controller)
    def optimize(model,callback):
        events['optimize_calls']+=1
        assert events['optimize_calls']==1,'NO_REPEATED_PRICING_ENUMERATION'
        def observed(native,where):
            if where==gp.GRB.Callback.MIPSOL:
                events['encountered']+=1
                if float(native.cbGet(gp.GRB.Callback.MIPSOL_OBJ))<=-1e-7:events['negative_candidates']+=1
            callback(native,where)
        connection.send(dict(native_started=time.perf_counter(),unit=unit))
        try:return original_optimize(model,observed)
        finally:connection.send(dict(native_ended=time.perf_counter(),unit=unit))
    gp.Model.optimize=optimize
    class Pipe:
        def recv(self):
            value=connection.recv()
            if value is not None:assert value['type']=='DISCOVERY'
            return value
        def send(self,value):
            if 'result' in value:
                p=live/value['result'];r=read(p);r['callback_observations']=events.copy()
                if mode=='CHALLENGER':
                    controller=state['controller'];h=controller.harvest
                    # Recheck the terminal incumbent after the single tree, too.
                    for c in r['candidates']:
                        with np.load(live/c['point_file']) as z:x=z['x']
                        h.observe(x,source='POSTSOLVE',native_objective=c['solver_objective'])
                    selected={c.trajectory_SHA for c in h.selected()}
                    assert len(selected)<=8 and not controller.errors and not r['capture_errors']
                    for c in r['candidates']:c['selected']=c['valid_negative'] and c['column_SHA'] in selected
                    r['harvest_metrics']=h.metrics();r['harvest_events']=h.events
                    r['selected_trajectory_SHAs']=sorted(selected)
                else:
                    r['harvest_metrics']=dict(captured_observations=len(r['candidates']),independently_validated=sum(c['physical']['PASS'] and c['full_original_local']['PASS'] for c in r['candidates']),validated_negative=sum(c['valid_negative'] for c in r['candidates']),duplicates_removed=sum(c['valid_negative'] and not c['selected'] for c in r['candidates']),dominated_removed=0,retained_columns=sum(c['selected'] for c in r['candidates']),invalid_admitted=0)
                r['development_only']=True;r['certification_implementation_unchanged']=True
                write(p,r)
            connection.send(value)
        def close(self):connection.close()
    try:
        legacy.main(Pipe(),[unit],stop_event)
    finally:
        gp.Model.optimize=original_optimize;validation.DiscoveryController=original_controller
