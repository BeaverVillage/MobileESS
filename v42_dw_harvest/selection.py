"""Exact equality/dominance; diversity affects Discovery selection only."""
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import math

K_MAX_PER_MESS = 8
K_MAX_PER_ROUND = 32
RC_LIMIT = F(float(-1e-7))


def projection_key(unit, coefficients):
    return (unit, tuple((int(i), F(v).numerator, F(v).denominator)
                        for i, v in sorted(coefficients.items()) if v))


def key_digest(key):
    return hashlib.sha256(repr(key).encode('ascii')).hexdigest()


@dataclass(frozen=True)
class UsefulColumn:
    unit: int
    trajectory_SHA: str
    projection: tuple
    objective: F
    true_RC: F
    search_RC: F
    values: tuple
    source: str


def rank(c):
    return (c.true_RC, c.search_RC, c.projection, c.trajectory_SHA)


def projection_distance(a, b):
    # Same original master row axis. Exact keys above, floating distance here
    # is a deterministic Discovery ranking diagnostic, never a certificate.
    av = {i: float(F(n, d)) for i, n, d in a.projection[1]}
    bv = {i: float(F(n, d)) for i, n, d in b.projection[1]}
    support = sorted(set(av) | set(bv))
    if not support:
        return 0.
    hamming = len(set(av) ^ set(bv)) / len(support)
    numer = math.fsum(abs(av.get(i, 0.) - bv.get(i, 0.)) for i in support)
    denom = math.fsum(abs(av.get(i, 0.)) + abs(bv.get(i, 0.)) for i in support)
    return hamming + numer / max(denom, 1e-300)


def select_batch(columns):
    columns = sorted(columns, key=rank)
    assert len({c.unit for c in columns}) <= 1
    selected = columns[:4]
    rest = columns[4:]
    while rest and len(selected) < K_MAX_PER_MESS:
        chosen = min(rest, key=lambda c: (-min(projection_distance(c, s) for s in selected), rank(c)))
        selected.append(chosen)
        rest.remove(chosen)
    return tuple(selected)


class HarvestState:
    """Validator is solver-free. Existing columns are never deleted/replaced."""
    def __init__(self, unit, adapter, existing_trajectories=(), existing_projections=None):
        self.unit = unit
        self.adapter = adapter
        self.existing_trajectories = frozenset(existing_trajectories)
        self.existing_projections = existing_projections or {}
        self.seen = set()
        self.useful = {}
        self.events = []
        self.errors = []

    def observe(self, values, source='MIPSOL', native_objective=None):
        values = tuple(map(float, values))
        report = self.adapter.audit(values)
        if not report['PASS']:
            self.events.append(dict(source=source, decision='INFEASIBLE', trajectory_SHA=None))
            return None
        trajectory, coefficients, objective, true_rc, search_rc = self.adapter.exact(values)
        objective, true_rc, search_rc = map(F, (objective, true_rc, search_rc))
        key = projection_key(self.unit, coefficients)
        event = dict(source=source, trajectory_SHA=trajectory, projection_SHA=key_digest(key),
                     true_RC=float(true_rc), search_RC=float(search_rc), feasible=True,
                     negative=true_rc <= RC_LIMIT and search_rc <= RC_LIMIT)
        if native_objective is not None and abs(float(search_rc) - native_objective) > 1e-8:
            event['decision'] = 'SEARCH_OBJECTIVE_MISMATCH'
        elif true_rc > RC_LIMIT or search_rc > RC_LIMIT:
            event['decision'] = 'NOT_VALIDATED_NEGATIVE'
        elif trajectory in self.existing_trajectories:
            event['decision'] = 'EXISTING_TRAJECTORY_DUPLICATE'
        elif trajectory in self.seen:
            event['decision'] = 'SAME_SOLVE_TRAJECTORY_DUPLICATE'
        elif key in self.existing_projections and self.existing_projections[key] <= objective:
            event['decision'] = ('EXISTING_PROJECTION_DUPLICATE' if self.existing_projections[key] == objective
                                 else 'EXISTING_PROJECTION_DOMINATES')
        elif key in self.useful and self.useful[key].objective <= objective:
            event['decision'] = ('SAME_ROUND_PROJECTION_DUPLICATE' if self.useful[key].objective == objective
                                 else 'SAME_ROUND_PROJECTION_DOMINATES')
        else:
            if key in self.useful:
                old = self.useful[key]
                event['replaced_dominated_SHA'] = old.trajectory_SHA
            self.useful[key] = UsefulColumn(self.unit, trajectory, key, objective, true_rc, search_rc, values, source)
            event['decision'] = 'USEFUL_NEGATIVE'
        self.seen.add(trajectory)
        self.events.append(event)
        return self.useful.get(key) if event['decision'] == 'USEFUL_NEGATIVE' else None

    def selected(self):
        return select_batch(self.useful.values())

    def metrics(self):
        decisions = [e['decision'] for e in self.events]
        return dict(captured_observations=len(self.events),
                    validated_negative=sum(e.get('negative', False) for e in self.events),
                    validated_negative_columns=len({e['trajectory_SHA'] for e in self.events if e.get('negative', False)}),
                    independently_validated=sum(e.get('feasible', False) for e in self.events),
                    duplicates_removed=sum('DUPLICATE' in d for d in decisions),
                    dominated_removed=sum('DOMINATES' in d for d in decisions) + sum('replaced_dominated_SHA' in e for e in self.events),
                    useful_nondominated=len(self.useful), retained_columns=len(self.selected()),
                    invalid_admitted=0, no_existing_column_deletion=True)
