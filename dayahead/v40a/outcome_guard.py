"""Reject Fresh entrypoint calls during the Planning coordination stage."""
from contextlib import contextmanager
import sys


@contextmanager
def prohibit_fresh_calls():
    from dayahead.v28r2 import opendss_backend
    original = opendss_backend.run_fresh_opendss
    changed = []
    calls = {'FRESH_CALLS_INSIDE_COOPT_LOOP': 0, 'blocked_Fresh_attempts': 0}
    def denied(*args, **kwargs):
        calls['blocked_Fresh_attempts'] += 1
        raise PermissionError('FRESH_NOT_ALLOWED_INSIDE_COOPT_LOOP')
    # Replace already imported aliases as well as the canonical import location.
    for module in tuple(sys.modules.values()):
        if module is None or not getattr(module, '__name__', '').startswith('dayahead'):
            continue
        for name, value in tuple(vars(module).items()):
            if value is original:
                changed.append((module, name))
                setattr(module, name, denied)
    try:
        yield calls
    finally:
        for module, name in changed:
            setattr(module, name, original)
