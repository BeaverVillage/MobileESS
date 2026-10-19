"""Checked, process-local diagnostic fix; sealed production files are untouched."""
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
import inspect
import textwrap
from v44.common import atomic, record, now
from v44_recovery_r024b.adaptive_pricing import AdaptivePricing


@contextmanager
def fixed_fresh_initializer(output):
    original = AdaptivePricing.__init__
    source = textwrap.dedent(inspect.getsource(original))
    before = 'from v44.common import read,verify'
    assert source.count(before) == 1
    corrected = source.replace(before, 'from v44.common import verify')
    namespace = dict(original.__globals__)
    exec(compile(corrected, __file__ + '.generated', 'exec'), namespace)
    repaired = namespace['__init__']
    output = Path(output)
    (output / 'CORRECTED_ADAPTIVE_INITIALIZER.py').write_text(corrected, encoding='utf-8')
    atomic(output / 'FRESH_INITIALIZER_FIX.json', dict(UTC=now(),
        original_source=record(inspect.getfile(original)),
        corrected_initializer=record(output / 'CORRECTED_ADAPTIVE_INITIALIZER.py'),
        only_change='Remove local read import so fresh M1_result uses the existing module read function',
        original_error='UnboundLocalError: read when M1_result is present without adaptive parent',
        process_local_diagnostic_only=True, production_source_modified=False,
        algorithm_selection_weights_thresholds_rows_and_solver_policy_changed=False))
    with patch.object(AdaptivePricing, '__init__', repaired):
        yield
