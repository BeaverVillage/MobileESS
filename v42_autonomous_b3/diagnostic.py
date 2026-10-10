"""A process-local Native-zero scope for independently verifying B1 reuse."""
from contextlib import contextmanager
from .admission import _native_zero


@contextmanager
def native_zero_diagnostic():
    # The original static-only Model wrapper rejects direct optimize(), while
    # the ContextVar rejects every measured/source Native admission as well.
    # This wraps authority construction and both independent proof replays.
    import gurobipy as gp
    from v42_may_campaign_native90.a_routing import native_zero_scope
    token = _native_zero.set(True)
    original_read = gp.read
    def blocked_read(*args, **kwargs):
        raise PermissionError("B3_DIAGNOSTIC_UNGUARDED_MODEL_LOAD_FORBIDDEN")
    gp.read = blocked_read
    try:
        with native_zero_scope(gp):
            yield
    finally:
        gp.read = original_read
        _native_zero.reset(token)
