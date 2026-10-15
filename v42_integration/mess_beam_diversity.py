"""Experimental diversity admission inside the original Adaptive Beam grammar.

Keep the same per-vehicle route-pool size and all verified incumbent/STAY paths.
Every alternative uses literal original DAG arcs. Scores must come from the
existing signed multi-critical P/Q/SOC/rebound scorer; they remain heuristic.
This module neither solves nor inserts a point in the incumbent registry.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from time import perf_counter

from .m_engine import PathGraph
from .mess_joint_compression import pool_sha


def optimistic_path_possible(graph, battery, path):
    """Only an exact optimistic energy envelope is used for necessary rejection."""
    upper = Fraction(float(battery.initial))
    minimum, maximum = Fraction(float(battery.minimum)), Fraction(float(battery.maximum))
    terminal = Fraction(float(battery.terminal))
    step = Fraction(float(battery.dt_hours*battery.eta_charge))*Fraction(float(battery.p_limit))
    for k in path:
        arc = graph.arcs[k]
        upper = upper-Fraction(float(arc[-1].energy_kwh)) if arc[-1] is not None else min(maximum, upper+step)
        if upper < minimum:
            return False
    return upper >= terminal


def diversify_pool(graph, battery, baseline, protected, original_pools, score, *, size=8,
                   candidate_cap=512, departure_band=12):
    """Fixed-size admission with location/time/MOVE coverage and joint scoring.

    score accepts the entire four-vehicle path dictionary. Existing signed
    electrical coupling, service loss, PCS/SOC and recharge rebound thus enter
    ranking together. No heuristic score becomes a hard Grid exclusion.
    """
    began = perf_counter()
    if size < 3 or candidate_cap < size or departure_band < 1:
        raise ValueError("MESS_DIVERSITY_VALID_FIXED_BUDGET_REQUIRED")
    if set(original_pools) != set(graph.origins) or set(baseline) != set(graph.origins):
        raise ValueError("MESS_DIVERSITY_ALL_PHYSICAL_VEHICLES_REQUIRED")
    counters, output, diagnostics = Counter(), {}, {}
    joint = {u:list(p) for u,p in baseline.items()}
    for unit in sorted(graph.origins):
        candidates, pins = {}, []
        def register(path, origin, mandatory=False):
            graph.validate(unit, path)
            key = tuple(path)
            if mandatory:
                if list(path) not in pins:
                    pins.append(list(path))
            elif not optimistic_path_possible(graph, battery, path):
                counters["proven_optimistic_SOC_path_rejections"] += 1
                return
            if key in candidates or not mandatory and len(candidates) >= candidate_cap:
                if key not in candidates:
                    counters["heuristic_candidate_cap_discards"] += 1
                return
            moves = [graph.arcs[k] for k in path if graph.arcs[k][-1] is not None]
            candidates[key] = dict(path=list(path), origin=origin, moves=len(moves),
                first_destination=moves[0][2] if moves else graph.origins[unit],
                first_departure_band=moves[0][1]//departure_band if moves else -1,
                all_destinations=sorted({a[2] for a in moves}),
                travel_energy=sum(float(a[-1].energy_kwh) for a in moves))
        register(graph.complete(unit), "MANDATORY_STAY", True)
        register(baseline[unit], "CURRENT_FULL_INCUMBENT", True)
        for path in protected.get(unit, []):
            register(path, "PROTECTED_FULL_INCUMBENT", True)
        if len(pins) > size:
            raise ValueError("MESS_DIVERSITY_SIZE_CANNOT_DROP_VERIFIED_INCUMBENTS")
        for path in original_pools[unit]:
            register(path, "ORIGINAL_BEAM_POOL")
        # Spread first moves over every original destination and 12-slot band.
        # Their enumeration is a reservoir; only the existing fixed-size pool
        # enters Joint MILP and its binary workload stays the same.
        move_groups = defaultdict(list)
        for k in sorted(graph.available[unit]):
            arc = graph.arcs[k]
            if arc[-1] is not None and arc[0] == graph.origins[unit]:
                move_groups[arc[2], arc[1]//departure_band].append(k)
        for key in sorted(move_groups):
            arcs = move_groups[key]
            for k in (arcs[0], arcs[-1]):
                register(graph.complete(unit, [k]), "ALL_VEHICLE_LOCATION_TIME_SINGLE_MOVE")
        # Recover alternatives around every unit's actual moving incumbent.
        move_lookup = {(a[0],a[2],a[1]):k for k,a in enumerate(graph.arcs) if a[-1] is not None}
        for pinned in list(pins):
            moves = [k for k in pinned if graph.arcs[k][-1] is not None]
            for i,k in enumerate(moves):
                a = graph.arcs[k]
                for delta in (-12,-6,-2,2,6,12):
                    alternative = move_lookup.get((a[0],a[2],a[1]+delta))
                    if alternative is None:
                        continue
                    trial = moves.copy(); trial[i] = alternative
                    try:
                        register(graph.complete(unit, trial), "ALL_VEHICLE_INCUMBENT_RETIMING")
                    except ValueError:
                        counters["exact_DAG_retiming_rejections"] += 1
        def ranking(candidate):
            test = dict(joint); test[unit] = candidate["path"]
            value = score(test)
            peak = float(value[0] if isinstance(value, tuple) else value)
            return peak, candidate["travel_energy"], tuple(candidate["path"])
        chosen = list(pins)
        # Keep at least one single and multiple MOVE option where the reservoir
        # contains one. This admits options; Joint MILP never forces a MOVE.
        for predicate in (lambda c:c["moves"]==1, lambda c:c["moves"]>=2):
            choices = [c for c in candidates.values() if predicate(c) and c["path"] not in chosen]
            if choices and len(chosen) < size:
                chosen.append(min(choices, key=ranking)["path"])
        while len(chosen) < size:
            choices = [c for c in candidates.values() if c["path"] not in chosen]
            if not choices:
                break
            visited_dest = set()
            visited_time = set()
            for path in chosen:
                c = candidates[tuple(path)]
                visited_dest.update(c["all_destinations"])
                visited_time.add(c["first_departure_band"])
            ranked = sorted(((*ranking(c),c) for c in choices), key=lambda z:z[:3])
            near = [z for z in ranked if z[0] <= ranked[0][0]+.025]
            selected = min(near, key=lambda z:(
                -len(set(z[-1]["all_destinations"])-visited_dest),
                -(z[-1]["first_departure_band"] not in visited_time), z[0], z[1], z[2]))[-1]
            chosen.append(selected["path"])
            joint[unit] = selected["path"]
        output[unit] = chosen
        chosen_rows = [candidates[tuple(p)] for p in chosen]
        diagnostics[unit] = dict(candidate_count=len(candidates), pool_size=len(chosen),
            protected_path_count=len(pins), generated_move_classes=dict(Counter(c["moves"] for c in candidates.values())),
            selected_move_classes=dict(Counter(c["moves"] for c in chosen_rows)),
            selected_destinations=sorted({s for c in chosen_rows for s in c["all_destinations"]}),
            generated_destinations=sorted({s for c in candidates.values() for s in c["all_destinations"]}),
            selected_departure_bands=sorted({c["first_departure_band"] for c in chosen_rows if c["moves"]}),
            generated_departure_bands=sorted({c["first_departure_band"] for c in candidates.values() if c["moves"]}))
    return output, dict(status="PASS", PASS=True, Native_optimize_calls=0, incumbent_registry_mutations=0,
        pool_sha=pool_sha(output), units=diagnostics, counters=dict(counters),
        wall_seconds=perf_counter()-began, per_unit_pool_budget=size, candidate_cap_per_unit=candidate_cap,
        all_STAY_and_verified_incumbents_pinned=True, all_vehicle_single_multiple_options=True,
        Original_DAG_arc_domains_preserved=True, score="EXISTING_SIGNED_MULTI_CRITICAL_JOINT_PQ_SOC_REBOUND",
        scores_are_heuristic=True, FULL_UB=False, Global_LB=False, new_FULL_UB="NOT_RUN",
        sufficient_all_nodes_time_coverage_claimed=False, no_MOVE_forcing=True,
        experimental_default_disabled=True)


def diversify_existing_beam(case, point, bank, scorer, original_pools, *, size=8):
    """Adapter for a current-case SignedMinimax instance, never an archived score."""
    graph = PathGraph(case)
    protected = defaultdict(list)
    for witness in (bank.best, bank.best_moving):
        if witness is not None:
            for unit,path in graph.paths(witness[0]).items():
                protected[unit].append(path)
    return diversify_pool(graph, case.graph[3], graph.paths(point), protected,
                          original_pools, scorer.peak, size=size)
