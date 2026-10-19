"""Opt-in scope on top of the sealed r015 live-read adapter."""
from contextlib import contextmanager
from unittest.mock import patch

from .memo_copy import clone_physical


@contextmanager
def scope(encoding, oracle):
    from v44_recovery_r015 import current_ac_performance as current
    from v44_recovery_r015 import physical_copy

    if getattr(oracle, '_independent_fresh', False):
        yield
        return
    if getattr(oracle, 'arm', None) != 'B3':
        with current.live_read_scope(encoding, oracle):
            yield
        return

    original_bank_reader = current.bank_reader

    def bank_reader(function, owner):
        # The copied globals affect only this generated closure. Other users of
        # copy.deepcopy, and the original/fresh path, retain their own binding.
        globals_ = dict(original_bank_reader.__globals__)
        # bank_reader imports deepcopy inside its body; compile that one exact
        # boundary to bind our graph copier without changing the sealed file.
        import inspect
        import textwrap
        source = textwrap.dedent(inspect.getsource(original_bank_reader))
        old = 'from copy import deepcopy'
        if source.count(old) != 1:
            raise ValueError('R016_BANK_COPY_BOUNDARY_DRIFT')
        source = source.replace(old, 'deepcopy = _r016_clone')
        globals_['_r016_clone'] = clone_physical
        exec(compile(source, __file__, 'exec'), globals_)
        return globals_['bank_reader'](function, owner)

    with patch.object(physical_copy, 'clone_physical', clone_physical), patch.object(current, 'bank_reader', bank_reader):
        with current.live_read_scope(encoding, oracle):
            import v44.svr11_ac as ac
            with patch.object(ac, 'deepcopy', clone_physical):
                yield
