"""Short-circuit a costly measurement-cache key when a cheap field differs.

This changes neither a physical check nor a measurement. If the native clock
has advanced, the old exact cache key cannot match: it contains that clock.
The immediate duplicate read still compares the complete original key.
"""
from contextlib import contextmanager
import inspect
import linecache
import math
import textwrap
from unittest.mock import patch

from v44_recovery_r029 import current_ac_performance as original


def possible(oracle, engine, prior, slot):
    counts = getattr(oracle, '_r034_bank_gate_counts', None)
    if counts is None:
        counts = oracle._r034_bank_gate_counts = dict(calls=0, no_prior=0, row_mismatch=0,
            clock_mismatch=0, full_before_stamp=0, clock_reads=0)
    counts['calls'] += 1
    if prior is None:
        counts['no_prior'] += 1
        return False
    if slot != prior[0]+1:
        counts['row_mismatch'] += 1
        return False
    prior_state = prior[1][0]
    if isinstance(prior_state, dict) and 'physical_seconds' in prior_state:
        old = prior_state['physical_seconds']
        if isinstance(old, (int, float)) and math.isfinite(old):
            now = int(engine.Solution.Hour())*3600+float(engine.Solution.Seconds())
            counts['clock_reads'] += 1
            if math.isfinite(now) and now != old:
                counts['clock_mismatch'] += 1
                return False
    counts['full_before_stamp'] += 1
    return True


def build():
    function = original.bank_reader
    source = textwrap.dedent(inspect.getsource(function))
    changes = {
        'before=stamp();slot=len(audit.rows)':
            'slot=len(audit.rows)\n        eligible=_r034_possible(oracle,engine,prior,slot)\n        before=stamp() if eligible else None',
        'if prior is not None and slot==prior[0]+1 and before==prior[1]:':
            'if eligible and before==prior[1]:',
    }
    for old, new in changes.items():
        if source.count(old) != 1:
            raise ValueError('R034_BANK_CACHE_PREDICATE_SOURCE_DRIFT')
        source = source.replace(old, new)
    filename = __file__+'.bank_reader.generated'
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    namespace = dict(function.__globals__, _r034_possible=possible)
    exec(compile(source, filename, 'exec'), namespace)
    return namespace[function.__name__]


@contextmanager
def install():
    factory = build()
    old_scope = original.current_probe_scope

    @contextmanager
    def scope(oracle, rows, encoding):
        with old_scope(oracle, rows, encoding) as stats:
            yield stats
        request = original._actual_request.get()
        if request is not None:
            from v44.common import atomic, now
            from pathlib import Path
            counts = dict(getattr(oracle, '_r034_bank_gate_counts', {}))
            atomic(Path(request['case_root'])/'R034_BANK_CACHE_GATE.json', dict(UTC=now(),counts=counts,
                first_control_key_counts=dict(getattr(oracle,'_r034_control_key_counts',{})),
                full_cache_stamp_short_circuits=sum(counts.get(k,0) for k in ('no_prior','row_mismatch','clock_mismatch')),
                native_solves_removed=0,physical_checks_removed=0,
                immediate_duplicate_full_key_checks_unchanged=True,independent_Fresh_changed=False))
    with patch.object(original, 'bank_reader', factory), patch.object(original, 'current_probe_scope', scope):
        yield
