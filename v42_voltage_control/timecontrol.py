"""Causal, event-driven native TIME controls on piecewise-constant slot inputs.

The CAPI 0.14.5 TIME controller processes due actions at an explicit clock,
whereas STATIC ignores their delay. An event on the next slot boundary is
sampled using that next slot's inputs. No control queue or equipment state is
reset, and a control iteration is never counted as a physical second.
"""
import csv
from datetime import date
import math

from v42_b3_joint.contracts import require

PINNED_CAPI_REVISION = '87d85c2622c8281b92255335bc7c09b11191b21d'


def seconds(engine):
    return int(engine.Solution.Hour()) * 3600 + float(engine.Solution.Seconds())


def queue(engine):
    """Read the native queue without popping, clearing, or executing it."""
    raw = list(engine.CtrlQueue.Queue())
    if not raw or raw == ['No events'] or raw == ['None']:
        require(int(engine.CtrlQueue.QueueSize()) == 0, 'TIME_QUEUE_EMPTY_SIZE_DRIFT')
        return []
    reader = list(csv.reader(raw, skipinitialspace=True))
    require([s.strip().lower() for s in reader[0]] ==
            ['handle', 'hour', 'sec', 'actioncode', 'proxydevref', 'device'],
            'TIME_QUEUE_NATIVE_HEADER_UNKNOWN')
    result = []
    for row in reader[1:]:
        require(len(row) == 6, 'TIME_QUEUE_NATIVE_ROW_UNKNOWN')
        handle, hour, sec, action, proxy, device = [x.strip() for x in row]
        value = dict(handle=int(handle), hour=int(hour), seconds=float(sec),
                     action_code=int(action), proxy_device_ref=int(proxy), device=device.lower())
        value['absolute_seconds'] = value['hour'] * 3600 + value['seconds']
        require(value['handle'] > 0 and value['hour'] >= 0 and
                math.isfinite(value['absolute_seconds']) and value['absolute_seconds'] >= 0
                and bool(value['device']), 'TIME_QUEUE_NONFINITE_OR_INVALID_EVENT')
        # QueueItem() emits Sec with %.9g. Integral seconds within an hour are
        # exact; a rounded fractional timestamp cannot authorize an exact
        # physical action time. All admitted original and new delays use whole
        # seconds, and unsupported fractional events fail rather than skip.
        require(value['seconds'].is_integer(), 'TIME_FRACTIONAL_QUEUE_PRECISION_UNSUPPORTED')
        result.append(value)
    require(len(result) == int(engine.CtrlQueue.QueueSize()), 'TIME_QUEUE_READBACK_SIZE_DRIFT')
    return sorted(result, key=lambda r: (r['absolute_seconds'], r['handle']))


class CommonClock:
    def __init__(self, namespace, day, slot_seconds=900, *, max_event_solves=2000):
        require(namespace in ('DAYAHEAD', 'ACTUAL'), 'TIME_INDEPENDENT_NAMESPACE_REQUIRED')
        require(date.fromisoformat(day).isoformat() == day, 'TIME_ISO_DAY_REQUIRED')
        require(type(slot_seconds) is int and slot_seconds == 900, 'TIME_ORIGINAL_15_MIN_SLOT_REQUIRED')
        require(type(max_event_solves) is int and max_event_solves > 0, 'TIME_EVENT_SOLVE_GUARD_REQUIRED')
        self.namespace, self.day, self.slot_seconds = namespace, day, slot_seconds
        self.max_event_solves = max_event_solves
        self.engine = None
        self.next_slot = 0
        self.total_physical_solve_count = 0
        self._log_count = 0

    def bind(self, engine):
        require(self.engine is None, 'TIME_CLOCK_BINDS_ONE_FRESH_ENGINE_ONLY')
        version = str(engine.Basic.Version())
        require('0.14.5' in version and PINNED_CAPI_REVISION in version, 'TIME_PINNED_CAPI_SOURCE_REQUIRED')
        require(int(engine.Solution.Mode()) == 0, 'TIME_SNAPSHOT_SOLUTION_BODY_REQUIRED')
        require(int(engine.Solution.MaxControlIterations()) == 100 and
                int(engine.Solution.MaxIterations()) == 15, 'TIME_SOURCE_100_15_LIMITS_REQUIRED')
        require(not queue(engine), 'TIME_FRESH_SOURCE_INITIAL_QUEUE_REQUIRED')
        require(seconds(engine) == 0, 'TIME_FRESH_SOURCE_INITIAL_CLOCK_REQUIRED')
        # This global mode is explicit new Source-epoch authority, not a change
        # to any original regulator's Delay, TapDelay, or automatic settings.
        engine.Solution.ControlMode(2)
        self.engine = engine
        self._log_count = len(engine.Solution.EventLog())
        return dict(namespace=self.namespace, day=self.day, control_mode='TIME',
                    start_seconds=0, CAPI_version=version, source_initial_queue=[])

    def _at(self, engine, value):
        require(math.isfinite(value) and value >= seconds(engine), 'TIME_CLOCK_BACKWARDS_FORBIDDEN')
        hour = int(value // 3600)
        engine.Solution.Hour(hour)
        engine.Solution.Seconds(value - hour * 3600)
        require(seconds(engine) == value, 'TIME_CLOCK_NATIVE_READBACK_DRIFT')

    def settle_slot(self, engine, slot, *, bank=None, observer=None, solve=None,
                    initial_solve_already_done=False, capture_events=True):
        require(capture_events or (bank is None and observer is None),
                'TIME_TRACE_FREE_PROBE_CANNOT_SKIP_OBSERVER')
        require(engine is self.engine, 'TIME_OWNED_ENGINE_REQUIRED')
        require(type(slot) is int and slot == self.next_slot and 0 <= slot < 96,
                'TIME_CHRONOLOGICAL_SLOTS_REQUIRED')
        start, end = slot * self.slot_seconds, (slot + 1) * self.slot_seconds
        require(seconds(engine) == start and int(engine.Solution.ControlMode()) == 2,
                'TIME_SLOT_START_OR_NATIVE_MODE_DRIFT')
        require(int(engine.Solution.MaxControlIterations()) == 100 and
                int(engine.Solution.MaxIterations()) == 15, 'TIME_SOURCE_100_15_LIMITS_DRIFT')
        solve = solve or engine.Solution.SolveSnap
        events = []

        def observe(kind, already_completed=False):
            now = seconds(engine)
            require(bool(engine.Solution.Converged()), 'TIME_NATIVE_AC_NONCONVERGENCE')
            require(bool(engine.Solution.ControlActionsDone()), 'TIME_NATIVE_DUE_CONTROL_ACTIONS_INCOMPLETE')
            pending = queue(engine)
            require(all(r['absolute_seconds'] > now for r in pending), 'TIME_NATIVE_OVERDUE_QUEUE_REMAINS')
            if not capture_events:
                # Forecast probes discard these receipts. Keep every solve,
                # clock action and strict convergence/control/queue check;
                # avoid copying the growing native EventLog and unused rows.
                return pending
            logs = list(engine.Solution.EventLog())
            # A native log reset is recorded; never silently lose events.
            delta = logs[self._log_count:] if len(logs) >= self._log_count else logs
            reset = len(logs) < self._log_count
            self._log_count = len(logs)
            cap = None if bank is None else bank.observe_at(now)
            row = dict(kind=kind, absolute_seconds=now, initial_solve_already_completed=already_completed,
                       solution_converged=True, control_actions_done_as_of_current_time=True,
                       control_iterations=int(engine.Solution.ControlIterations()),
                       electrical_iterations=int(engine.Solution.Iterations()),
                       native_event_log=delta, native_event_log_reset=reset,
                       pending_queue=pending, capacitors=cap)
            events.append(row)
            if observer is not None and not already_completed:
                observer(row)
            return pending

        if initial_solve_already_done:
            pending = observe('INITIAL_ALREADY_COMPLETED', True)
        else:
            solve()
            pending = observe('SLOT_INPUT_SAMPLE_AND_DUE_ACTIONS')
        extra = 0
        while True:
            if capture_events: pending = queue(engine)
            if not pending or pending[0]['absolute_seconds'] >= end:
                break
            require(extra < self.max_event_solves, 'TIME_EVENT_SOLVE_LIMIT_EXCEEDED')
            self._at(engine, pending[0]['absolute_seconds'])
            # Full automatic native SolveSnap samples present voltages before
            # applying due actions and resamples after every executed action.
            solve()
            extra += 1
            pending = observe('NATIVE_QUEUED_EVENT')
        last_solve = seconds(engine)
        carried = queue(engine) if capture_events else pending
        self._at(engine, end)  # Do not execute boundary events with old inputs.
        self.next_slot += 1
        self.total_physical_solve_count += 1 + extra
        return dict(schema='V42_NATIVE_TIME_SLOT_V1', namespace=self.namespace, day=self.day, slot=slot,
                    start_seconds=start, end_seconds=end, last_solve_seconds=last_solve,
                    physical_solve_count=1 + extra, extra_SolveSnap_count=extra,
                    total_physical_solve_count=self.total_physical_solve_count,
                    events=events, queue_carried_to_next_slot=carried,
                    control_actions_done_as_of_current_time=True, converged=True, PASS=True,
                    boundary_semantics='[start,end); next inputs sampled before end-boundary actions',
                    unsolved_hold_seconds=end-last_solve,
                    hold_assumption='piecewise-constant slot injections; no native queued events before end',
                    physical_elapsed_seconds=self.slot_seconds,
                    iteration_to_seconds_conversion=False, manual_tap_or_cap_actions=0)
