"""Exact graph migration census with indexed contiguous state membership."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from time import perf_counter


class StateIntervals:
    """Represent every occupied integer slot by maximal half-open runs."""

    def __init__(self, states):
        slots = defaultdict(set)
        for site, slot in states:
            slots[site].add(slot)
        self.runs = {}
        for site, values in slots.items():
            starts, ends = [], []
            for slot in sorted(values):
                if ends and ends[-1] == slot:
                    ends[-1] = slot + 1
                else:
                    starts.append(slot)
                    ends.append(slot + 1)
            self.runs[site] = starts, ends

    def contains(self, site, start, stop):
        # Match all(... for slot in range(start, stop)), including empty ranges.
        if stop <= start:
            return True
        runs = self.runs.get(site)
        if runs is None:
            return False
        starts, ends = runs
        index = bisect_right(starts, start) - 1
        return index >= 0 and stop <= ends[index]


def represented_migration_keys(graph, domain):
    """Keep the original candidates and predicates; index only range checks."""
    events = {name: set(value) for name, value in graph.events.items()}
    by_pair = defaultdict(list)
    for source, dest, tau in events['w']:
        by_pair[source, dest].append(tau)
    if not by_pair:
        return frozenset()
    states = {name: StateIntervals(value) for name, value in graph.states.items()
              if name in ('r0', 'h', 'r1')}
    result = set()
    for start, source, cp, physical, dest, gpu, taus in domain.blocks:
        candidates = by_pair.get((source, dest), ())
        if (not candidates or (source, start) not in events['y'] or (source, cp) not in events['q']
                or start not in graph.compatible.get((source, cp), ())
                or graph.physical.get((source, cp, start)) != physical
                or not states['r0'].contains(source, start, cp)):
            continue
        for tau in candidates:
            at = bisect_left(taus, tau)
            if at == len(taus) or taus[at] != tau:
                continue
            transfer = graph.transfers[source, dest, tau]
            end = transfer.restart + domain.duration - (cp - start)
            if ((dest, end) in events['f1']
                    and states['h'].contains(source, cp, tau)
                    and states['r1'].contains(dest, transfer.restart, end)):
                result.add((start, source, cp, physical, dest, tau))
    return frozenset(result)


class Census:
    """Measure the actual scoped binding without retaining graph/result caches."""

    def __init__(self):
        self.calls = 0
        self.seconds = 0.
        self.last_write = 0.
        self.output = None
        self.last_keys = 0

    def __call__(self, graph, domain):
        began = perf_counter()
        result = represented_migration_keys(graph, domain)
        self.seconds += perf_counter() - began
        self.calls += 1
        self.last_keys = len(result)
        from .adapters import ACTIVE
        request = ACTIVE.get()
        if request and request.get('iteration_stage') in ('A3', 'A4'):
            self.output = request['output']
            if perf_counter() - self.last_write >= 2.:
                self.flush()
        return result

    def report(self):
        return dict(calls=self.calls,wall_seconds=self.seconds,last_active_migration_keys=self.last_keys,
                    exact_state_interval_index=True,graph_results_cached=False,
                    candidate_enumeration_and_ledger_unchanged=True)

    def flush(self):
        if self.output is None:
            return
        from pathlib import Path
        from .io import atomic, now, record
        atomic(Path(self.output)/'ITERATION2_MIGRATION_CENSUS.json',
               dict(PASS=True,UTC=now(),source=record(__file__),**self.report()))
        self.last_write = perf_counter()
