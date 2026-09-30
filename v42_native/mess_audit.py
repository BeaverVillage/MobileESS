"""Reproducible PR99 baseline and independent exhaustive bounded-path oracle.

No native solve/fabricated AIDC anchor. Loading the baseline requires the exact
Git object, whose source SHA is recorded in every audit.
"""
from collections import defaultdict
from dataclasses import asdict, replace
from functools import lru_cache
from math import cos, pi
from pathlib import Path
import hashlib
import subprocess
import sys
import types

import gurobipy as gp

from .contracts import Deadline
from .mess import Battery, RouteArc
from .mess_domain import build_domain
from .solver import size

BASE = '3309cd230cd8235201f5578d392241fa98e059bc'
ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def baseline():
    source = subprocess.check_output(['git', 'show', BASE + ':v42_native/mess.py'], cwd=ROOT)
    module = types.ModuleType('v42_native._pr99_mess_baseline')
    module.__package__ = 'v42_native'
    sys.modules[module.__name__] = module
    exec(compile(source, BASE + ':v42_native/mess.py', 'exec'), module.__dict__)
    module.source_sha256 = hashlib.sha256(source).hexdigest()
    inherited_optimize = module.optimize
    def exact_comparison(model, *args, **kwargs):
        # Same fixed diagnostic tolerances in both models. Default 1e-6 row
        # tolerance exceeds the 1e-7 inherited rho lock/comparison tolerance.
        model.Params.FeasibilityTol = 1e-9
        model.Params.OptimalityTol = 1e-9
        model.Params.IntFeasTol = 1e-9
        return inherited_optimize(model, *args, **kwargs)
    module.optimize = exact_comparison
    return module


def empty_grid(model, p, q):
    return [('rho', gp.LinExpr(0)), ('reserve_shortfall', gp.LinExpr(0))]


def diagnostic_grid(model, p, q):
    """Nontrivial bounded P1/P2 coupling, never a native anchor."""
    rho = model.addVar(lb=0, name='rho_max')
    reserve = model.addVar(lb=0, name='reserve_shortfall')
    last = max(t for _, t in p)
    for (s, t), value in p.items():
        critical = s == 'B' and t >= last - 1
        base = .9 if critical else .65 if s == 'A' and t < 2 else .2
        model.addConstr(base - .03 * value - .01 * q[s, t] <= rho, name='line_thermal')
        model.addConstr((.4 if critical else 0.) - .05 * value <= reserve, name='reserve_requirement')
    return [('rho', rho), ('reserve_shortfall', reserve)]


def baseline_build(sites, initial_sites, routes, battery, horizon, grid=empty_grid):
    old = baseline()
    saved = old.optimize
    audit = {}

    def hook(model, *args, **kwargs):
        stats = size(model)
        audit.update(model_size=stats, total_columns=model.NumVars, total_rows=model.NumConstrs,
                     family_columns={prefix: sum(v.VarName.startswith(prefix + '[') for v in model.getVars())
                                     for prefix in ('arc', 'charge_mode', 'Pch', 'Pdis', 'Q', 'SOC')})
        return None, dict(audit)

    try:
        old.optimize = hook
        _, receipt = old.solve('M1', Deadline('M1', 600), sites, initial_sites, routes, battery, horizon, grid)
        return dict(receipt, baseline_source_sha256=old.source_sha256, scope='MODEL_BUILD_ONLY_NO_OPTIMIZE')
    finally:
        old.optimize = saved


def all_paths(arcs, origin, horizon):
    outgoing = defaultdict(list)
    for a in arcs:
        outgoing[a.tail].append(a)

    def visit(node, prefix):
        if node[1] == horizon:
            yield tuple(prefix)
        else:
            for a in outgoing[node]:
                yield from visit(a.head, prefix + [a])
    return visit((origin, 0), [])


def path_soc(path, battery, horizon):
    """Exact energy-only projection for a FIXED path, independent of prescreen.

    Q=0 allows the full PCS-limited real-power interval. Each stay maps a
    continuous interval; one fixed path has no predecessor hull correlation.
    Forward/backward intersection gives every feasible E[t] on that path.
    """
    connected, travel = {}, {}
    for a in path:
        if a.route is None:
            connected[a.depart] = a.source
        else:
            travel[a.depart] = a.route.energy_kwh
    pmax = min(battery.p_limit, battery.pcs_kva * cos(pi / 16))
    step = []
    for t in range(horizon):
        if t in connected:
            step.append((-.25 * pmax / battery.eta_discharge, .25 * pmax * battery.eta_charge))
        else:
            e = travel.get(t, 0.)
            step.append((-e, -e))

    def clip(lo, hi):
        lo, hi = max(lo, battery.minimum), min(hi, battery.maximum)
        return (lo, hi) if lo <= hi + 1e-10 else None

    forward = [(battery.initial, battery.initial)]
    for lo, hi in step:
        prev = forward[-1]
        if prev is None:
            return None
        forward.append(clip(prev[0] + lo, prev[1] + hi))
    if forward[-1] is None or not forward[-1][0] - 1e-10 <= battery.terminal <= forward[-1][1] + 1e-10:
        return None
    backward = [None] * (horizon + 1)
    backward[horizon] = (battery.terminal, battery.terminal)
    for t in reversed(range(horizon)):
        lo, hi = step[t]
        dest = backward[t + 1]
        backward[t] = clip(dest[0] - hi, dest[1] - lo)
    intervals = [(max(f[0], b[0]), min(f[1], b[1])) for f, b in zip(forward, backward)]
    return dict(intervals=intervals, connected=connected, travel_kwh=sum(travel.values()))


def exhaustive(case):
    sites, H, battery, routes = case
    domain = build_domain(sites, {'M': sites[0]}, routes, battery, H)
    unit = domain.units[0]
    surviving = set(unit.arc_indices)
    node_soc = dict(unit.soc)
    global_soc = dict(unit.global_soc)
    old_feasible, new_feasible, total = set(), set(), 0
    for path in all_paths(domain.arcs, sites[0], H):
        total += 1
        physical = path_soc(path, battery, H)
        if physical is None:
            continue
        signature = tuple(a.index for a in path)
        old_feasible.add(signature)
        if set(signature) <= surviving:
            new_feasible.add(signature)
        for a in path:
            for node in (a.tail, a.head):
                interval = node_soc[node]
                lo, hi = physical['intervals'][node[1]]
                assert interval.lower <= lo + 1e-8 and interval.upper >= hi - 1e-8
                # Every iteration's forward/backward envelope must contain
                # all feasible continuous fixed-path energies, not a grid sample.
                for iteration in unit.iterations:
                    f, b = dict(iteration.forward_soc)[node], dict(iteration.backward_soc)[node]
                    assert f.lower <= lo + 1e-8 and f.upper >= hi - 1e-8
                    assert b.lower <= lo + 1e-8 and b.upper >= hi - 1e-8
            if a.route is None:
                assert a.tail in unit.electrical_states
        for t, (lo, hi) in enumerate(physical['intervals']):
            interval = global_soc[t]
            assert interval.lower <= lo + 1e-8 and interval.upper >= hi - 1e-8
    assert old_feasible == new_feasible
    return dict(PASS=True, total_paths=total, feasible_paths=len(old_feasible),
                retained_feasible_paths=len(new_feasible), false_pruned=0,
                proof_scope='All fixed-path continuous SOC intervals, PCS-admissible Q=0 projection; P/Q rows/equations inherited on every surviving path',
                domain_sha256=domain.sha256)


def adversarial_cases():
    b = Battery(0., 4., 1., 1., 4., 5., .8, .9)
    def r(uid, source='A', destination='B', depart=0, connect=1, energy=0., sha='a' * 64):
        return RouteArc(uid, source, destination, depart, connect, connect, energy, sha)
    return {
        'near_minimum': (('A', 'B'), 5, b, (r('min', energy=.999999999),)),
        'near_max_charge': (('A', 'B'), 5, replace(b, initial=0., terminal=3.2), (r('skip', energy=0.),)),
        'terminal_equality_and_transit_only': (('A', 'B'), 5, replace(b, initial=4., terminal=0., p_limit=1.), (r('dissipate', connect=4, energy=4.),)),
        'long_travel': (('A', 'B'), 6, b, (r('long', connect=4, energy=.5),)),
        'zero_energy': (('A', 'B'), 5, b, (r('zero'),)),
        'forward_SOC_impossible': (('A', 'B'), 5, b, (r('too_much', energy=2.),)),
        'terminal_SOC_impossible': (('A', 'B'), 5, b, (r('late', depart=3, connect=4, energy=3.35),)),
        'multiple_predecessors': (('A', 'B', 'C'), 5, b, (r('AB', energy=.2), r('AC', destination='C', energy=.8),
                                                       r('CB', source='C', depart=1, connect=2, energy=.1))),
        'different_energy_no_dominance': (('A', 'B'), 5, replace(b, initial=4., terminal=0.),
                                         (r('low', connect=4, energy=0.), r('high', connect=4, energy=4.))),
        'exact_duplicates_only': (('A', 'B'), 5, b, (r('same'), r('same'), r('other_id'), r('other_authority', sha='b'*64))),
        'PCS_limits_below_Plimit': (('A', 'B'), 5, replace(b, p_limit=4., pcs_kva=4.), (r('pcs', energy=.5),)),
        'empty_domain': (('A', 'B'), 5, replace(b, initial=0., terminal=4.), ()),
    }


def random_cases(count=64):
    import random
    rng = random.Random(20260930)
    for i in range(count):
        H = rng.randint(3, 6)
        b = Battery(0., 4., rng.choice((0., .25, 1., 3.75, 4.)), rng.choice((0., .25, 1., 3.75, 4.)),
                    4., rng.choice((4., 5.)), rng.choice((.7, .95, 1.)), rng.choice((.7, .95, 1.)))
        routes = []
        for j in range(rng.randint(1, 9)):
            source, dest = rng.sample(('A', 'B', 'C'), 2)
            depart = rng.randrange(H - 1)
            connect = rng.randrange(depart + 1, H)
            routes.append(RouteArc(str(j), source, dest, depart, connect, connect,
                                   rng.choice((0., .1, .75, 1., 3.9, 5.)), 'a'*64))
        yield str(i), (('A', 'B', 'C'), H, b, tuple(routes))
