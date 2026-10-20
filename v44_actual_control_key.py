"""Build a first-read cache key from the full live control check just obtained.

All first/final control checks remain. Only rereading the same tap, capacitor
and solver-counter values solely to construct the first-read key is avoided.
Unknown schemas retain the complete original key reader.
"""
from contextlib import contextmanager
import inspect
import linecache
import textwrap
from unittest.mock import patch
import numpy as np

from v44_recovery_r029 import history

COUNTERS = ('ControlActionsDone','solution_converged','ControlIterations','Solution_Iterations_total',
    'Solution_TotalIterations','Solution_MostIterationsDone_per_control_pass',
    'configured_MaxControlIterations','configured_MaxIterations','control_mode')


def from_controls(oracle, engine, controls):
    from v44.common import digest
    from v42_voltage_control.timecontrol import queue,seconds
    counts = getattr(oracle,'_r034_control_key_counts',None)
    if counts is None:
        counts=oracle._r034_control_key_counts=dict(live_inventory_rereads_elided=0,fallbacks=0)
    try:
        regs = list(controls['original_regulators'])+list(controls['added_regulators'])
        caps = controls['capacitors']
        expected_regs = [r['name'] for r in regs]
        expected_caps = [r['name'] for r in caps]
        if (engine.RegControls.AllNames()!=expected_regs or
                engine.Capacitors.AllNames()!=expected_caps):
            raise KeyError('axis')
        state = dict(taps=[r['initial_tap'] for r in regs],caps=[r['states'] for r in caps],
                     queue=queue(engine),physical_seconds=seconds(engine))
        counters = tuple(controls[k] for k in COUNTERS)
    except (KeyError,TypeError,AttributeError):
        counts['fallbacks']+=1
        return history.native_stamp(oracle,engine)
    counts['live_inventory_rereads_elided']+=1
    return digest(state),np.asarray(engine.Circuit.AllBusVolts(),dtype=np.float64).tobytes(),counters


def build():
    function=history.scope.__wrapped__
    source=textwrap.dedent(inspect.getsource(function))
    old='''            stamp=native_stamp(oracle,engine)
            active['control_calls']+=1
            # The first call is a full live settings/inventory check in every
            # historical slot, even when an identical certificate exists.
            cached=None if active['first_control'] else proofs.get(active['key'],stamp)
            active['first_control']=False
            if cached is None:
                stats['full_control_calls']+=1
                value=proofs.put(active['key'],stamp,original_controls(engine,scenario,authority))'''
    new='''            first=active['first_control']
            if first:
                live=original_controls(engine,scenario,authority)
                stamp=_r034_from_controls(oracle,engine,live)
            else:
                stamp=native_stamp(oracle,engine)
            active['control_calls']+=1
            cached=None if first else proofs.get(active['key'],stamp)
            active['first_control']=False
            if cached is None:
                stats['full_control_calls']+=1
                if not first:live=original_controls(engine,scenario,authority)
                value=proofs.put(active['key'],stamp,live)'''
    if source.count(old)!=1:
        raise ValueError('R034_FIRST_CONTROL_KEY_SOURCE_DRIFT')
    source=source.replace(old,new)
    filename=__file__+'.scope.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(function.__globals__,_r034_from_controls=from_controls)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[function.__name__]


@contextmanager
def install():
    adapted=build()
    with patch.object(history,'scope',adapted):
        yield
