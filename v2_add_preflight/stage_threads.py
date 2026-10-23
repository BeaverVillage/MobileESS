"""Reentrant IO scope around the unchanged r043 four-thread M overlay."""
from contextlib import contextmanager
from contextvars import ContextVar

_active=ContextVar('V2_ADD_M4_SOURCE_OVERLAY',default=None)


@contextmanager
def scope(request):
    from v44.q250_m4 import m_threads
    key=tuple(request[k] for k in ('day','arm','stage','worker_slot','Threads'))
    existing=_active.get()
    if existing is not None:
        if existing[0]!=key:raise PermissionError('NESTED_M_THREAD_STAGE_DRIFT')
        yield existing[1];return
    # Install before execution.native_stage wraps the source thread guard;
    # its nested arithmetic bindings reuse this exact overlay instance.
    with m_threads(request) as effective:
        token=_active.set((key,effective))
        try:yield effective
        finally:_active.reset(token)
