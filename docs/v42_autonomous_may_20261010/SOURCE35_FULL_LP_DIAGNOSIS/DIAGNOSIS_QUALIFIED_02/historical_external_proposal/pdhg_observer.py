"""External design prototype: scalar observations, no Gurobi import/Native calls.

Not a production admission factory. A future owned Scope must validate its
request, complete declared source map, exact model, original call and callable
code before constructing this object. The original DateBudget callback remains
the sole Runtime cap/accounting controller and invokes this after its own work.
"""
from copy import deepcopy
from datetime import datetime, timezone
import math
from time import perf_counter

UNKNOWN = 'UNKNOWN'
FIELDS = {
    'PDHG': ('PDHG_ITRCNT', 'PDHG_PRIMOBJ', 'PDHG_DUALOBJ',
             'PDHG_PRIMINF', 'PDHG_DUALINF', 'PDHG_COMPL'),
    'SIMPLEX': ('SPX_ITRCNT', 'SPX_PRIMINF', 'SPX_DUALINF'),
    'BARRIER': ('BARRIER_ITRCNT', 'BARRIER_PRIMOBJ', 'BARRIER_DUALOBJ',
                'BARRIER_PRIMINF', 'BARRIER_DUALINF', 'BARRIER_COMPL'),
    'PRESOLVE': ('PRE_COLDEL', 'PRE_ROWDEL', 'PRE_SENCHG', 'PRE_BNDCHG', 'PRE_COECHG'),
}


def finite(value, infinity):
    if isinstance(value, bool):
        return UNKNOWN
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return UNKNOWN
    return result if math.isfinite(result) and abs(result) < infinity else UNKNOWN


class ScopedObserver:
    """One exact model, diagnostic-only callbacks; never returns a certified LB."""
    def __init__(self, model, callback_codes, gurobi_error, infinity, *,
                 assert_authority, binding, publish=None, original_callback=None,
                 clock=perf_counter):
        assert_authority()  # Caller must bind original/code/request/current scope.
        self.model = model
        self.codes = callback_codes
        self.query_error = gurobi_error
        self.infinity = infinity
        self.authority = assert_authority
        self.binding = deepcopy(binding)
        self.publish = publish
        self.original_callback = original_callback
        self.clock = clock
        self.next_publication = -math.inf
        self.phase_counts = {}
        self.first_runtime = {}
        self.last_runtime = {}
        self.last_by_phase = {}
        self.last_phase = UNKNOWN
        self.faults = []
        self.closed = False

    def _get(self, model, field):
        try:
            code = getattr(self.codes, field)
            return finite(model.cbGet(code), self.infinity)
        except (self.query_error, AttributeError) as error:
            self.faults.append(dict(kind='UNAVAILABLE_SCALAR', field=field, error=repr(error)))
            return UNKNOWN

    def __call__(self, model, where):
        if self.closed or model is not self.model:
            raise PermissionError('EXACT_CURRENT_OWNED_MODEL_AND_OPEN_SCOPE_REQUIRED')
        self.authority()
        # Original caller semantics/errors are not swallowed by diagnostics.
        if self.original_callback is not None:
            self.original_callback(model, where)
        phase = next((name for name in FIELDS
                      if where == getattr(self.codes, name, object())), None)
        if phase is None:
            return  # No phase inferred from MESSAGE or POLLING.
        runtime = self._get(model, 'RUNTIME')
        row = dict(phase=phase, callback_where=where, callback_Runtime=runtime,
                   observation_UTC=datetime.now(timezone.utc).isoformat(),
                   fields={name: self._get(model, name) for name in FIELDS[phase]})
        self.phase_counts[phase] = self.phase_counts.get(phase, 0) + 1
        self.first_runtime.setdefault(phase, runtime)
        self.last_runtime[phase] = runtime
        self.last_by_phase[phase] = row
        self.last_phase = phase
        # Diagnostic publication coalescing only; no sleeps/affinity/solver caps.
        elapsed = self.clock()
        if self.publish is not None and elapsed >= self.next_publication:
            try:
                self.publish(self.snapshot())
            except OSError as error:
                self.faults.append(dict(kind='OBSERVATION_PUBLICATION_FAILED', error=repr(error)))
            self.next_publication = elapsed + 1.

    def snapshot(self):
        return deepcopy(dict(schema='DRAFT_OWNED_FULL_LP_CALLBACK_DIAGNOSTICS',
            binding=self.binding, Native_accounting_authority=False,
            certified_LB_UB_or_Gap_authority=False, Native_Pi_observed=False,
            current_observed_callback_phase=self.last_phase, phase_callback_counts=self.phase_counts,
            phase_first_Runtime=self.first_runtime, phase_last_Runtime=self.last_runtime,
            last_observation_by_phase=self.last_by_phase, observation_errors=self.faults))

    def finish(self, original_completed_call=None):
        """No post-Native reset/update/start reads; retain original UNKNOWN."""
        self.authority()
        actual = original_completed_call
        completed = (isinstance(actual, dict) and actual.get('entered_native') is True
                     and actual.get('status') in ('FINISHED', 'FAILED')
                     and not actual.get('runtime_unavailable', True)
                     and finite(actual.get('Native_Runtime'), self.infinity) != UNKNOWN)
        row = self.snapshot()
        row['original_call_completion_receipt_supplied'] = completed
        row['original_accounting_record'] = deepcopy(actual) if actual is not None else None
        # Only query scalar counters after genuine original Native accounting.
        row['post_Native_scalar_counters'] = {name: UNKNOWN for name in
                                             ('PDHGIterCount', 'IterCount', 'BarIterCount')}
        if completed:
            for name in row['post_Native_scalar_counters']:
                try:
                    value = getattr(self.model, name)
                    row['post_Native_scalar_counters'][name] = finite(value, self.infinity)
                except (self.query_error, AttributeError) as error:
                    row['observation_errors'].append(dict(kind='UNAVAILABLE_POST_NATIVE_SCALAR',
                                                         field=name, error=repr(error)))
        self.closed = True
        return row
