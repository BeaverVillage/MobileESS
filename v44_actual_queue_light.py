"""Elide immediate queue rereads only when no user/capacitor callback can act."""
from contextlib import contextmanager
import inspect,linecache,textwrap
from unittest.mock import patch


def build(function):
    source=textwrap.dedent(inspect.getsource(function))
    changes={
        'if capture_events: pending = queue(engine)':
            'if capture_events and (observer is not None or bank is not None): pending = queue(engine)',
        'carried = queue(engine) if capture_events else pending':
            'carried = queue(engine) if capture_events and (observer is not None or bank is not None) else pending',
    }
    for old,new in changes.items():
        if source.count(old)!=1:raise ValueError('R035_NATIVE_QUEUE_SOURCE_DRIFT')
        source=source.replace(old,new)
    filename=__file__+'.clock.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__);exec(compile(source,filename,'exec'),ns)
    return ns[function.__name__]


@contextmanager
def clock_scope():
    from v42_voltage_control.timecontrol import CommonClock
    with patch.object(CommonClock,'settle_slot',build(CommonClock.settle_slot)):
        yield


@contextmanager
def install():
    from v44_recovery_r029 import current_ac_performance as performance
    original=performance.current_probe_scope
    @contextmanager
    def current(oracle,rows,encoding):
        # Current only: Fresh and Forecast continue through their original clocks.
        with clock_scope(),original(oracle,rows,encoding) as stats:yield stats
    with patch.object(performance,'current_probe_scope',current):yield
