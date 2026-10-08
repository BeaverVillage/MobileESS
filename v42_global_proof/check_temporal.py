"""Independent method-B source, support and complete-route audit, optimize=0."""
import copy
import json
import time
from collections import defaultdict
from fractions import Fraction as F
from itertools import combinations

import numpy as np

from .check_source_cutoff import ROOT, OUT, SOURCE, sha, read, write, load_sources, independent_physical_reader
from .check_grid_capacity import (q, split_name, route_graph, check_original_route_flow,
    dispatch_sources, check_demand, expect_rejected, ROUTE_SHA)


def check_temporal_rows(A, d, exact):
    weights = defaultdict(F)
    by_slot = defaultdict(F)
    row_weights = {}
    binding = [int(i) for i, name in enumerate(d["row_names"]) if str(name).split("[", 1)[0].endswith("_binding")]
    fixed = np.flatnonzero(d["lower"] == d["upper"]).tolist()
    for record in exact["critical_rows"]:
        i = int(record["row"])
        rho = q(A[i, 239826])
        assert rho < 0 and d["sense"][i] == "<"
        coefficient = -1 / rho
        certificate = dict(source_matrix_sha256=sha(SOURCE / "C3A_A.npz"),
            source_data_sha256=sha(SOURCE / "C3A_DATA.npz"), cutoff="3/5",
            rows=[dict(row=i, name=str(d["row_names"][i]), multiplier=str(coefficient))],
            weights=[dict(column=int(j), name=str(d["names"][int(j)]), coefficient=value)
                     for j, value in record["support_coefficients"].items()],
            constant=record["baseline_rho_exact"], rho_coefficient="-1",
            D_exact=record["demand_at_exact_three_fifths"], binding_rows=binding, fixed_columns=fixed)
        actual, constant, unused_rho, demand, unused_audit = check_demand(A, d, certificate)
        slot = int(record["slot"])
        assert {int(split_name(d["names"][j])[1][-1]) for j in actual} == {slot}
        assert demand == constant - F(3, 5) and record["positive_demand"] == (demand > 0)
        row_weights[i] = actual
        by_slot[slot] += max(F(0), demand)
        if demand > 0:
            for j, value in actual.items():
                weights[j] += value
    assert {int(slot): F(value) for slot, value in exact["demand_by_slot"].items()} == dict(by_slot)
    assert sum(by_slot.values()) == F(exact["total_demand_exact"])
    return weights, by_slot, row_weights


def check_rewards(exact, weights, groups, polygons):
    rewards = {}
    for name, record in exact["site_weights_and_rewards"].items():
        unit, site, slot = name.split("|")
        key = unit, site, int(slot)
        columns = groups[key]
        pweight = weights.get(columns["Pdis"], F(0))
        qweight = weights.get(columns["Q"], F(0))
        assert weights.get(columns["Pch"], F(0)) == -pweight
        assert F(record["p"]) == pweight and F(record["q"]) == qweight, "TEMPORAL_SUPPORT_WEIGHT_CHANGED"
        maximum = max(pweight * p + qweight * qvalue for points in polygons[key] for p, qvalue in points)
        assert F(record["upper"]) == maximum, "TEMPORAL_REWARD_UNDERESTIMATED"
        p, qvalue = map(F, record["maximizer"])
        assert pweight * p + qweight * qvalue == maximum
        # Registry is evidence, never an independent source of constraints.
        registry = exact["PCS_polygons"][record["PCS"]]
        assert all(F(a) * p + F(b) * qvalue <= F(c) for a, b, c in registry["halfspaces"])
        rewards[key] = maximum
    expected_keys = {(unit, site, slot) for unit in exact["initial_sites"] for site in exact["sites"] for slot in by_times(exact)}
    assert set(rewards) == expected_keys
    return rewards


def by_times(exact):
    return sorted(map(int, exact["demand_by_slot"]))


def backward_route_upper(sites, edges, initial, rewards):
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge[0], edge[1]].append(edge)
    values, reached = {}, {}
    for unit, origin in initial.items():
        potential = {(s, 96): F(0) for s in sites}
        for time_slot in reversed(range(96)):
            for site in sites:
                potential[site, time_slot] = max(
                    (rewards.get((unit, site, time_slot), F(0)) if stay else F(0)) + potential[dest, ready]
                    for unused_s, unused_t, dest, ready, unused_e, stay in outgoing[site, time_slot])
        values[unit] = potential[origin, 0]
        nodes = {(origin, 0)}
        for time_slot in range(96):
            for site in sites:
                if (site, time_slot) in nodes:
                    nodes.update((edge[2], edge[3]) for edge in outgoing[site, time_slot])
        reached[unit] = nodes
    return values, reached, outgoing


def check_bridges(exact, sites, outgoing):
    for record in exact["bridge_reachability"]:
        first, second = map(int, record["slots"])
        # Backward destination-bit reachability differs from the producer's
        # forward origin-bit propagation; first dispatch occupies its stay.
        masks = {(site, second): 1 << index for index, site in enumerate(sites)}
        for slot in reversed(range(first + 1, second)):
            for site in sites:
                value = 0
                for edge in outgoing[site, slot]:
                    if edge[3] <= second:
                        value |= masks.get((edge[2], edge[3]), 0)
                masks[site, slot] = value
        origin_masks = [0] * len(sites)
        for origin_index, site in enumerate(sites):
            destination_mask = masks.get((site, first + 1), 0)
            for destination_index in range(len(sites)):
                if destination_mask & (1 << destination_index):
                    origin_masks[destination_index] |= 1 << origin_index
        assert origin_masks == record["reachable_origin_masks"], "TWO_TIME_SOURCE_ROUTE_REACHABILITY_CHANGED"
        assert record["forbidden_ordered_site_pairs"] == len(sites) ** 2 - sum(mask.bit_count() for mask in origin_masks)
    assert len(exact["bridge_reachability"]) == len(list(combinations(by_times(exact), 2)))


def check_covers(exact, row_weights, groups, polygons, reached, sites, initial):
    requirements = {int(record["row"]): record for record in exact["critical_rows"]}
    cover_union = {}
    for cover in exact["simultaneous_support_candidate_covers"]:
        row = int(cover["row"])
        requirement = requirements[row]
        demand = F(requirement["demand_at_exact_three_fifths"])
        assert demand > 0 and F(cover["pigeonhole_threshold_exact"]) == demand / 4
        slot = int(cover["slot"])
        actual, union = {}, set()
        for unit in initial:
            candidates = []
            for site in sites:
                key = unit, site, slot
                if (site, slot) not in reached[unit] or key not in groups:
                    continue
                columns = groups[key]
                wp = row_weights[row].get(columns["Pdis"], F(0))
                wq = row_weights[row].get(columns["Q"], F(0))
                upper = max(wp * p + wq * value for points in polygons[key] for p, value in points)
                if upper >= demand / 4:
                    candidates.append(site)
            actual[unit] = sorted(candidates)
            union.update(candidates)
        assert actual == cover["candidate_sites_by_vehicle"], "PIGEONHOLE_CANDIDATE_COVER_UNSAFE"
        assert sorted(union) == cover["site_union"]
        cover_union[row] = union
    assert len(cover_union) == sum(F(record["demand_at_exact_three_fifths"]) > 0 for record in exact["critical_rows"])
    for hall in exact["Hall_disjoint_cover_tests"]:
        rows = [row for row, req in requirements.items() if int(req["slot"]) == int(hall["slot"]) and F(req["demand_at_exact_three_fifths"]) > 0]
        maximum, selected = 0, []
        for size in range(1, len(rows) + 1):
            for choice in combinations(rows, size):
                if all(not (cover_union[a] & cover_union[b]) for a, b in combinations(choice, 2)):
                    maximum, selected = size, choice
        assert maximum == hall["largest_pairwise_disjoint_site_cover_count"]
        empty = sorted(row for row in rows if not cover_union[row])
        assert empty == sorted(hall["empty_candidate_rows"])
        contradiction = bool(maximum > 4 or empty)
        assert hall["contradiction"] == contradiction
        assert not contradiction, "TEMPORAL_HALL_CONTRADICTION_REQUIRES_GLOBAL_REVIEW"


def main():
    import gurobipy as gp
    gp.Model.optimize = lambda *a, **k: (_ for _ in ()).throw(AssertionError("TEMPORAL_CHECKER_OPTIMIZE_FORBIDDEN"))
    start = time.perf_counter()
    A, d, T, AA, dd, unused = load_sources()
    exact = read(OUT / "TEMPORAL_EXACT_DATA.json")
    audit = read(OUT / "TEMPORAL_CONFLICT_AUDIT.json")
    assert sha(OUT / "TEMPORAL_EXACT_DATA.json") == audit["detailed_exact_data_SHA256"]
    assert exact["source_matrix_SHA256"] == sha(SOURCE / "C3A_A.npz")
    assert exact["source_data_SHA256"] == sha(SOURCE / "C3A_DATA.npz") and exact["route_SHA256"] == ROUTE_SHA
    sites, edges, initial = route_graph()
    assert exact["sites"] == sites and exact["initial_sites"] == initial and exact["graph_arc_count"] == len(edges)
    reader = independent_physical_reader()
    alias, flow = check_original_route_flow(reader, sites, edges, initial)
    groups, polygons, energy, suffix, structure = dispatch_sources(A, d, edges, alias)
    weights, demand_by_time, row_weights = check_temporal_rows(A, d, exact)
    rewards = check_rewards(exact, weights, groups, polygons)
    uppers, reached, outgoing = backward_route_upper(sites, edges, initial, rewards)
    assert {unit: F(value) for unit, value in exact["vehicle_route_upper_bounds"].items()} == uppers
    total = sum(uppers.values())
    assert total == F(exact["total_upper_exact"]), "TEMPORAL_CAPACITY_UPPER_CHANGED"
    assert sum(demand_by_time.values()) <= total
    check_bridges(exact, sites, outgoing)
    check_covers(exact, row_weights, groups, polygons, reached, sites, initial)
    # The supplied maximizing paths are lower witnesses for R, not upper proofs.
    for path in exact["maximizing_relaxed_paths"]:
        unit, position, value = path["MESS"], (initial[path["MESS"]], 0), F(0)
        travel = F(0)
        for index in path["arc_indices"]:
            origin, depart, dest, ready, route_energy, stay = edges[int(index)]
            assert position == (origin, depart)
            value += rewards.get((unit, origin, depart), F(0)) if stay else F(0)
            travel += route_energy
            position = dest, ready
        assert position[1] == 96 and value == uppers[unit] and value == F(path["upper_exact"])
        assert travel == F(path["original_travel_energy_exact"])
        assert path["SOC_feasibility_of_original_cutoff"] == "NOT_PROVEN"
    bad = copy.deepcopy(exact)
    key = next(iter(bad["site_weights_and_rewards"]))
    bad["site_weights_and_rewards"][key]["upper"] = str(F(bad["site_weights_and_rewards"][key]["upper"]) - 1)
    tests = [expect_rejected(lambda: check_rewards(bad, weights, groups, polygons), "underestimated_temporal_reward")]
    bad = copy.deepcopy(exact)
    unit = next(iter(initial))
    bad["vehicle_route_upper_bounds"][unit] = str(uppers[unit] - 1)
    tests.append(expect_rejected(lambda: assert_upper_mapping(bad, uppers), "underestimated_temporal_vehicle_upper"))
    assert audit["classification"] == exact["classification"] == "NOT_PROVEN"
    write(OUT / "INDEPENDENT_TEMPORAL_CHECK.json", dict(PASS=True, classification="NOT_PROVEN",
        exact_D=str(sum(demand_by_time.values())), exact_sum_U=str(total),
        exact_slack=str(total - sum(demand_by_time.values())), critical_grid_rows=len(exact["critical_rows"]),
        original_route_flow=flow, source_dispatch=structure, all_four_vehicle_route_uppers_verified=True,
        independent_backward_DP=True, source_bridge_pairs_verified=len(exact["bridge_reachability"]),
        candidate_covers_verified=len(exact["simultaneous_support_candidate_covers"]),
        Hall_cover_tests_verified=len(exact["Hall_disjoint_cover_tests"]),
        local_SOC_diagnostics_are_not_global_proofs=True, tamper_tests=tests,
        native_optimize_calls=0, controller_wall_seconds=time.perf_counter() - start))
    print(json.dumps(dict(PASS=True, native_optimize_calls=0, controller_wall_seconds=time.perf_counter() - start)), flush=True)


def assert_upper_mapping(exact, uppers):
    assert {unit: F(value) for unit, value in exact["vehicle_route_upper_bounds"].items()} == uppers, "TEMPORAL_VEHICLE_UPPER_CHANGED"


if __name__ == "__main__":
    main()
