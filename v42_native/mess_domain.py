"""Immutable, grid-independent outer SOC prescreen of the inherited MESS DAG.

Induction: every physical prefix/suffix energy belongs to its interval hull.
An empty intersection or arc image therefore cannot contain a physical path.
Hull membership alone is NOT a feasibility certificate. Energy is deducted
at departure+1, not gradually over travel; transit bounds use that same timing.
"""
from dataclasses import asdict, dataclass
from functools import lru_cache
from math import inf, nextafter

from .contracts import digest, require

FACES = 16
ROUNDING_SLACK = 1e-9  # kWh, outward only; never cuts a marginal path


@dataclass(frozen=True)
class Arc:
    index: int
    source: str
    depart: int
    destination: str
    connect: int
    route: object = None

    @property
    def tail(self):
        return self.source, self.depart

    @property
    def head(self):
        return self.destination, self.connect


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float


def intersect(a, b):
    if a is None or b is None:
        return None
    lo, hi = max(a.lower, b.lower), min(a.upper, b.upper)
    return Interval(lo, hi) if lo <= hi else None


def hull(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return Interval(min(a.lower, b.lower), max(a.upper, b.upper))


def shift(a, lo, hi):
    if a is None:
        return None
    return Interval(nextafter(a.lower + lo - ROUNDING_SLACK, -inf),
                    nextafter(a.upper + hi + ROUNDING_SLACK, inf))


def delta(arc, battery):
    if arc.route is not None:
        return -arc.route.energy_kwh, -arc.route.energy_kwh
    return (-battery.dt_hours * battery.p_limit / battery.eta_discharge,
            battery.dt_hours * battery.eta_charge * battery.p_limit)


def structural(arcs, origin, terminals):
    forward = {origin}
    for a in sorted(arcs, key=lambda a: (a.depart, a.index)):
        if a.tail in forward:
            forward.add(a.head)
    backward = set(terminals)
    for a in sorted(arcs, key=lambda a: (a.depart, a.index), reverse=True):
        if a.head in backward:
            backward.add(a.tail)
    return forward, backward


def envelopes(arcs, origin, terminals, battery):
    bounds = Interval(battery.minimum, battery.maximum)
    forward = {origin: Interval(battery.initial, battery.initial)}
    backward = {v: Interval(battery.terminal, battery.terminal) for v in terminals}
    ordered = sorted(arcs, key=lambda a: (a.depart, a.index))
    for a in ordered:
        lo, hi = delta(a, battery)
        candidate = intersect(shift(forward.get(a.tail), lo, hi), bounds)
        if candidate is not None:
            forward[a.head] = hull(forward.get(a.head), candidate)
    for a in reversed(ordered):
        lo, hi = delta(a, battery)
        candidate = intersect(shift(backward.get(a.head), -hi, -lo), bounds)
        if candidate is not None:
            backward[a.tail] = hull(backward.get(a.tail), candidate)
    return forward, backward


@dataclass(frozen=True)
class Iteration:
    number: int
    forward_nodes: tuple
    backward_nodes: tuple
    forward_soc: tuple
    backward_soc: tuple
    intersections: tuple
    arc_mapping: tuple  # (index, possible)
    removed: tuple  # (index, reason)


@dataclass(frozen=True)
class UnitDomain:
    mess: str
    origin: str
    nodes: tuple
    arc_indices: tuple
    stay_indices: tuple
    travel_indices: tuple
    electrical_states: tuple  # surviving stay tails ONLY
    charge_times: tuple
    soc: tuple
    global_soc: tuple
    iterations: tuple
    removals: tuple


@dataclass(frozen=True)
class MESSDomain:
    sites: tuple
    initial_sites: tuple
    routes: tuple
    battery: object
    horizon: int
    arcs: tuple
    units: tuple
    authority_hashes: tuple
    duplicate_indices: tuple
    input_sha256: str
    sha256: str

    @property
    def pq_indices(self):
        return tuple((u.mess, s, t) for u in self.units for s, t in u.electrical_states)

    @property
    def pcs_indices(self):
        return tuple((m, s, t, f) for m, s, t in self.pq_indices for f in range(FACES))


def _unit(mess, origin, sites, arcs, battery, horizon):
    active = list(arcs)
    terminals = {(s, horizon) for s in sites}  # inherited ANY terminal site
    records, removed_all = [], []
    start = (origin, 0)
    while True:
        f, b = structural(active, start, terminals)
        removed, kept = [], []
        for a in active:
            reason = ('FORWARD_UNREACHABLE' if a.tail not in f else
                      'BACKWARD_DEAD_END' if a.head not in b else None)
            if reason:
                removed.append((a.index, reason))
            else:
                kept.append(a)
        ef, eb = envelopes(kept, start, terminals, battery)
        nodes = {v for a in kept for v in (a.tail, a.head)} | {start}
        intersections = {v: intersect(ef.get(v), eb.get(v)) for v in nodes}
        mapping, next_active = [], []
        for a in kept:
            reason = None
            for v in (a.tail, a.head):
                if v not in ef:
                    reason = 'FORWARD_SOC_INFEASIBLE'
                elif v not in eb:
                    reason = 'BACKWARD_SOC_INFEASIBLE'
                elif intersections[v] is None:
                    reason = 'SOC_FORWARD_BACKWARD_DISJOINT'
                if reason:
                    break
            lo, hi = delta(a, battery)
            possible = intersect(shift(intersections[a.tail], lo, hi), intersections[a.head]) is not None
            mapping.append((a.index, possible))
            if not reason and not possible:
                reason = 'ARC_SOC_MAPPING_EMPTY'
            if reason:
                removed.append((a.index, reason))
            else:
                next_active.append(a)
        records.append(Iteration(len(records) + 1, tuple(sorted(f)), tuple(sorted(b)),
                                 tuple(sorted(ef.items())), tuple(sorted(eb.items())),
                                 tuple(sorted(intersections.items())), tuple(mapping), tuple(sorted(removed))))
        removed_all.extend(removed)
        active = next_active
        if not removed:
            break
    surviving = tuple(sorted({v for a in active for v in (a.tail, a.head)}))
    electrical = tuple(sorted(a.tail for a in active if a.route is None))
    # A connected node contributes E[t]. A travel arc contributes E[depart+1]
    # through E[connect-1] AFTER full departure energy deduction. No charging.
    global_bounds = {}
    for v in surviving:
        global_bounds[v[1]] = hull(global_bounds.get(v[1]), intersections[v])
    for a in active:
        if a.route is None:
            continue
        corridor = intersect(shift(intersections[a.tail], -a.route.energy_kwh, -a.route.energy_kwh),
                             intersections[a.head])
        for t in range(a.depart + 1, a.connect):
            global_bounds[t] = hull(global_bounds.get(t), corridor)
    original = Interval(battery.minimum, battery.maximum)
    global_soc = tuple((t, intersect(global_bounds.get(t, original), original)) for t in range(horizon + 1))
    return UnitDomain(mess, origin, surviving, tuple(a.index for a in active),
                      tuple(a.index for a in active if a.route is None),
                      tuple(a.index for a in active if a.route is not None), electrical,
                      tuple(sorted({t for _, t in electrical})),
                      tuple((v, intersections[v]) for v in surviving), global_soc,
                      tuple(records), tuple(sorted(removed_all)))


def authority_key(sites, initial_sites, routes, battery, horizon):
    return digest(dict(sites=tuple(sites), initial=sorted(initial_sites.items()),
                       routes=[asdict(r) for r in routes], battery=asdict(battery),
                       horizon=horizon, faces=FACES, version=1))


def build_domain(sites, initial_sites, routes, battery, horizon):
    """Bounded LRU reuses the same immutable object across dynamic grid anchors."""
    return _cached(tuple(sites), tuple(sorted(initial_sites.items())), tuple(routes), battery, horizon)


@lru_cache(maxsize=8)
def _cached(sites, initial_sites, routes, battery, horizon):
    battery.validate()
    require(isinstance(horizon, int) and horizon > 0, 'MESS_HORIZON')
    require(sites and len(set(sites)) == len(sites) and initial_sites, 'MESS_SITES')
    for _, origin in initial_sites:
        require(origin in sites, 'INITIAL_SITE')
    canonical, duplicates, seen = [], [], {}
    for i, r in enumerate(routes):
        r.validate(horizon)
        require(r.source in sites and r.destination in sites, 'ROUTE_SITE')
        # ALL fields, including route_id/arrive/authority: no energy dominance.
        # Normalize numeric spelling in the audit signature (0 == 0.0).
        # Dataclass equality matches PR99's dict.fromkeys behavior exactly.
        signature = digest({k:float(v) if isinstance(v,(int,float)) else v for k,v in asdict(r).items()})
        if r in seen:
            duplicates.append((i, seen[r], signature))
        else:
            seen[r] = i
            canonical.append(r)
    arcs = [Arc(i, s, t, s, t + 1) for i, (s, t) in
            enumerate((s, t) for s in sites for t in range(horizon))]
    arcs += [Arc(len(arcs) + i, r.source, r.depart, r.destination, r.connect, r)
             for i, r in enumerate(canonical)]
    units = tuple(_unit(m, origin, sites, arcs, battery, horizon) for m, origin in initial_sites)
    key = authority_key(sites, dict(initial_sites), routes, battery, horizon)
    # Timings/audit history excluded; all model-affecting static data included.
    sha = digest(dict(input_sha256=key, units=[dict(mess=u.mess, nodes=u.nodes, arcs=u.arc_indices,
                                                 electrical=u.electrical_states,
                                                 soc=[(v, asdict(i)) for v, i in u.soc],
                                                 global_soc=[(t, asdict(i)) for t, i in u.global_soc]) for u in units]))
    return MESSDomain(sites, initial_sites, tuple(canonical), battery, horizon, tuple(arcs), units,
                      tuple(sorted({r.authority_sha256 for r in routes})), tuple(duplicates), key, sha)
