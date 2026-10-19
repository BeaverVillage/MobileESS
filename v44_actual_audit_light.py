"""Elide property reads whose values the static SVR checks discard.

Every comparison, consumed live field, native solve, chronological replay,
historical boundary guard, current measurement and independent Fresh remain.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import inspect
import linecache
import textwrap
from unittest.mock import patch

from v44_recovery_r029.class_metadata import ClassPropertySchema

BRANCH_DISCARDED = frozenset(('Bus', 'Buses', 'Bus1', 'Bus2', 'Wdg', 'WdgCurrents'))
ADDED_TRANSFORMER_DISCARDED = BRANCH_DISCARDED | {'Tap', 'Taps'}
REGULATOR_DISCARDED = frozenset(('TapNum', 'Reset'))


def transformed(function, old, new, helper):
    source = textwrap.dedent(inspect.getsource(function))
    if source.count(old) != 1:
        raise ValueError('R034_STATIC_READER_SOURCE_SHAPE_DRIFT:'+function.__name__)
    source = source.replace(old, new)
    filename = __file__+'.'+function.__name__+'.generated'
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    namespace = dict(function.__globals__, _r034_properties=helper)
    exec(compile(source, filename, 'exec'), namespace)
    return namespace[function.__name__]


class Projection:
    def __init__(self, original):
        self.original = original
        self.schema = ClassPropertySchema()
        self.added = ContextVar('r034_added_transformers', default=None)
        self.reads = self.omitted = self.calls = self.fallbacks = 0
        self.omitted_by_name = {}

    def properties(self, engine, name, *, regulators=False):
        props = engine.Properties
        if (self.added.get() is None or not hasattr(props, '_lib') or
                not hasattr(props._lib, 'Obj_GetAsString')):
            self.fallbacks += 1
            return self.original(engine, name)
        if not engine.Circuit.SetActiveElement(name):
            raise ValueError('SVR_ELEMENT_MISSING:'+name)
        lib = props._lib
        obj = lib.CktElement_Get_Pointer()
        if obj == props._api_util.ffi.NULL:
            raise ValueError('R029_ACTIVE_PROPERTY_OBJECT_REQUIRED')
        names = self.schema.names(engine, obj)
        if regulators:
            discarded = REGULATOR_DISCARDED
        else:
            discarded = (ADDED_TRANSFORMER_DISCARDED if name.lower() in self.added.get()
                         else BRANCH_DISCARDED)
        result = {}
        self.calls += 1
        for index, key in enumerate(names, 1):
            if key in discarded:
                self.omitted += 1
                self.omitted_by_name[key] = self.omitted_by_name.get(key, 0)+1
                continue
            raw = lib.Obj_GetAsString(obj, index)
            try:
                props._check_for_error()
                result[key] = str(props._get_string(raw))
                self.reads += 1
            finally:
                lib.DSS_Dispose_String(raw)
        # The existing r029 reader leaves this exact selector behind.
        if names:
            lib.DSSProperty_Set_Index(len(names)-1)
            props._check_for_error()
        return result

    def report(self):
        return dict(projected_static_property_calls=self.calls, consumed_live_property_reads=self.reads,
                    unused_property_reads_elided=self.omitted,
                    unused_reads_by_property=dict(self.omitted_by_name),
                    unsupported_engine_original_reader_calls=self.fallbacks,
                    native_solves_removed=0, historical_boundary_guards_removed=0,
                    physical_acceptance_checks_removed=0, independent_Fresh_changed=False)


@contextmanager
def measure_scope(module, oracle=None):
    """Only static helper consumers see a projection; returned Raw stays full."""
    original_measure = module.SeriesSVRCollection.measure
    projection = Projection(module._properties)
    branch = transformed(module._existing_branch, 'props = _properties(engine, element)',
                         'props = _r034_properties(engine, element)', projection.properties)
    regulators = transformed(module._original_regulators, 'props = _properties(engine, "RegControl." + name)',
                         'props = _r034_properties(engine, "RegControl." + name, regulators=True)', projection.properties)

    def measured(bank):
        if oracle is not None and (getattr(oracle, '_independent_fresh', False) or
                                  bank is not getattr(oracle, '_bank', None)):
            return original_measure(bank)
        added = frozenset('transformer.'+n.lower() for n in bank.installation_receipt['added_transformer_names'])
        token = projection.added.set(added)
        try:
            with patch.object(module, '_existing_branch', branch), patch.object(module, '_original_regulators', regulators):
                return original_measure(bank)
        finally:
            projection.added.reset(token)

    with patch.object(module.SeriesSVRCollection, 'measure', measured):
        yield projection


@contextmanager
def install():
    from v44_recovery_r029 import current_ac_performance as performance
    original = performance.current_probe_scope

    @contextmanager
    def current(oracle, rows, encoding):
        from v44.svr12 import scope
        from v44.common import atomic, now
        from pathlib import Path
        with scope():
            import v42_voltage_control.svr as module
            with measure_scope(module, oracle) as projection:
                with original(oracle, rows, encoding) as stats:
                    yield stats
                request = performance._actual_request.get()
                if request is not None:
                    atomic(Path(request['case_root'])/'R034_ACTUAL_AUDIT_LIGHT.json',
                           dict(UTC=now(), **projection.report()))
    with patch.object(performance, 'current_probe_scope', current):
        yield
