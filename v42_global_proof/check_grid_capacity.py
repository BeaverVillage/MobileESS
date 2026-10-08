"""Independent exact source-row and DAG-potential checker, optimize=0.

Demand is checked by directly adding immutable CSR rows and eliminating columns
with equality row operations. Capacity is checked by all original graph edges,
not by trusting a maximizing relaxed path or a maximization incumbent.
"""
import os
os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
import copy
import gzip
import json
import time
from collections import defaultdict
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import sparse

from .check_source_cutoff import ROOT, OUT, SOURCE, sha, read, write, load_sources, independent_physical_reader

ROUTE = ROOT / "docs/v42_m1_group_branching_20261008/artifacts/source_authority/ROUTE_TABLE.json.gz"
ROUTE_SHA = "3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9"
_DEFINITIONS = {}


def q(value):
    return F.from_float(float(value))


def split_name(name):
    name = str(name)
    family, rest = name.split("[", 1)
    return family, rest[:-1].split(",")


def gz(receipt):
    path = Path(receipt["path"])
    if not path.is_absolute():
        path = OUT / path
    assert path.resolve().is_relative_to(OUT.resolve()), "CERTIFICATE_OUTSIDE_NEW_NAMESPACE"
    assert sha(path) == receipt["sha256"], "EXACT_ARTIFACT_HASH_CHANGED"
    return json.loads(gzip.decompress(path.read_bytes()))


def check_demand(A, d, certificate):
    assert certificate["source_matrix_sha256"] == sha(SOURCE / "C3A_A.npz")
    assert certificate["source_data_sha256"] == sha(SOURCE / "C3A_DATA.npz")
    assert F(certificate["cutoff"]) == F(3, 5)
    families = [str(name).split("[", 1)[0] for name in d["names"]]
    definitions = _DEFINITIONS.get(id(A))
    if definitions is None:
        definitions = {}
    for i, name in enumerate(d["row_names"]) if id(A) not in _DEFINITIONS else []:
        family = str(name).split("[", 1)[0]
        if family.endswith("_binding"):
            indices = A.indices[A.indptr[i]:A.indptr[i + 1]]
            pivots = [int(j) for j in indices if families[j] == family[:-8]]
            assert len(pivots) == 1 and d["sense"][i] == "="
            assert pivots[0] not in definitions
            definitions[pivots[0]] = i
    _DEFINITIONS[id(A)] = definitions
    coefficients = defaultdict(F)
    rhs = F(0)
    sources = []
    for record in certificate["rows"]:
        i = int(record["row"])
        assert str(d["row_names"][i]) == record["name"]
        orientation = int(record.get("orientation", 1))
        sense = str(d["sense"][i])
        assert (sense == "<" and orientation == 1) or (sense == ">" and orientation == -1), "INVALID_THERMAL_SIGN_ORIENTATION"
        multiplier = F(record["multiplier"])
        assert multiplier >= 0, "MULTIPLIER_OUTSIDE_SIGN_CONE"
        multiplier *= orientation
        rhs += multiplier * q(d["rhs"][i])
        for j, value in zip(A.indices[A.indptr[i]:A.indptr[i + 1]], A.data[A.indptr[i]:A.indptr[i + 1]]):
            coefficients[int(j)] += multiplier * q(value)
        sources.append(i)
    assert len(sources) == len(set(sources)), "DUPLICATED_MULTIPLIER_SOURCE_ROW"
    used, fixed, operations = set(), set(), 0
    while True:
        unwanted = next((j for j, value in coefficients.items() if value and families[j] not in ("Pch", "Pdis", "Q", "rho_max")), None)
        if unwanted is None:
            break
        j, value = unwanted, coefficients.pop(unwanted)
        if d["lower"][j] == d["upper"][j]:
            rhs -= value * q(d["lower"][j])
            fixed.add(j)
        else:
            assert j in definitions, "UNELIMINATED_UNBOUNDED_AUXILIARY"
            i = definitions[j]
            row = A.getrow(i)
            pivot = q(row[0, j])
            assert pivot in (F(1), F(-1)), "INVALID_BINDING_PIVOT"
            factor = value / pivot
            rhs -= factor * q(d["rhs"][i])
            for k, a in zip(row.indices, row.data):
                if int(k) != j:
                    coefficients[int(k)] -= factor * q(a)
            used.add(i)
        operations += 1
        assert operations < 100000, "NONTERMINATING_BINDING_ROW_ELIMINATION"
    coefficients = {j: value for j, value in coefficients.items() if value}
    rho = next(j for j, family in enumerate(families) if family == "rho_max")
    rho_coefficient = coefficients.pop(rho, F(0))
    assert rho_coefficient < 0, "NO_VALID_RHO_NECESSITY"
    weights = {j: -value for j, value in coefficients.items()}
    declared = {int(record["column"]): F(record["coefficient"]) for record in certificate["weights"]}
    assert len(declared) == len(certificate["weights"]), "DUPLICATE_SUPPORT_COLUMN"
    for record in certificate["weights"]:
        assert str(d["names"][int(record["column"])]) == record["name"]
    assert declared == weights, "SUPPORT_COEFFICIENT_MISMATCH"
    constant = -rhs
    assert F(certificate["constant"]) == constant, "AFFINE_CONSTANT_MISSING_OR_CHANGED"
    assert F(certificate["rho_coefficient"]) == rho_coefficient, "RHO_COEFFICIENT_CHANGED"
    demand = constant + F(3, 5) * rho_coefficient
    assert F(certificate["D_exact"]) == demand, "DEMAND_MISMATCH"
    assert used.issubset(set(certificate["binding_rows"]))
    assert fixed.issubset(set(certificate["fixed_columns"]))
    return weights, constant, rho_coefficient, demand, dict(PASS=True, original_source_rows=len(sources),
        direct_CSR_equality_row_operations=operations, effective_binding_rows=len(used),
        exact_constant=str(constant), exact_rho_coefficient=str(rho_coefficient), exact_D=str(demand),
        no_primal_point_substitution=True, source_sign_cone_verified=True)


def route_graph():
    assert sha(ROUTE) == ROUTE_SHA
    table = json.loads(gzip.decompress(ROUTE.read_bytes()))
    sites = table["service_ids"]
    edges = [(s, t, s, t + 1, F(0), True) for s in sites for t in range(96)]
    seen = set()
    for record in table["routes"]:
        origin = record["origin_service_id"]
        dest = record["destination_service_id"]
        depart = int(record["departure_slot_15"])
        arrive = depart + int(record["travel_slots_15min"])
        ready = depart + int(record["connection_ready_slots_15min"])
        if origin == dest or not 0 <= depart < arrive <= ready < 96:
            continue
        key = (origin, depart, dest, ready)
        assert key not in seen, "DUPLICATE_ORIGINAL_ROUTE_EDGE"
        seen.add(key)
        edges.append((*key, q(record["energy_safe_kwh"]), False))
    assert len(sites) == 24 and len(edges) == 53626
    prior = read(ROOT / "docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json")
    assert prior["PASS"]
    initial = prior["graph_receipt"]["initial_MESS_sites"]
    assert len(initial) == 4
    return sites, edges, initial


def check_original_route_flow(reader, sites, edges, initial):
    # Check original full integer-arc incidence rows against the graph. This
    # establishes one whole-horizon path; missing original arcs only enlarge R.
    full, data = reader.full.tocsr(), reader.d
    expected = defaultdict(dict)
    terminal = defaultdict(dict)
    alias = {}
    for j, name in enumerate(data["names"]):
        if not str(name).startswith("arc["):
            continue
        _, values = split_name(name)
        unit, index = values[0], int(values[1])
        assert data["types"][j] == "B" and 0 <= data["lower"][j] <= data["upper"][j] <= 1
        s, t, dest, end, energy, stay = edges[index]
        expected[unit, s, t][j] = F(1)
        if end < 96:
            expected[unit, dest, end][j] = F(-1)
        else:
            terminal[unit][j] = F(1)
        alias[unit, index] = (int(reader.target[j]), q(reader.offset[j]))
    checked = set()
    empty = 0
    for i in np.flatnonzero(data["row_names"] == "flow"):
        row = full.getrow(int(i))
        assert data["sense"][i] == "="
        if not row.nnz:
            assert data["rhs"][i] == 0
            empty += 1
            continue
        j, coefficient = int(row.indices[0]), q(row.data[0])
        _, values = split_name(data["names"][j])
        unit, index = values[0], int(values[1])
        s, t, dest, end, unused_energy, unused_stay = edges[index]
        key = (unit, s, t) if coefficient == 1 else (unit, dest, end)
        assert coefficient in (F(1), F(-1)) and key not in checked
        actual = {int(k): q(a) for k, a in zip(row.indices, row.data)}
        assert actual == expected[key], "ORIGINAL_FLOW_NOT_SOURCE_GRAPH_INCIDENCE"
        assert q(data["rhs"][i]) == (F(1) if key == (unit, initial[unit], 0) else F(0))
        checked.add(key)
    assert checked == set(expected) and empty + len(checked) == 4 * 24 * 96
    checked_terminal = set()
    for i in np.flatnonzero(data["row_names"] == "terminal_location"):
        row = full.getrow(int(i))
        unit = split_name(data["names"][row.indices[0]])[1][0]
        assert unit not in checked_terminal and data["sense"][i] == "=" and q(data["rhs"][i]) == 1
        assert {int(j): q(a) for j, a in zip(row.indices, row.data)} == terminal[unit]
        checked_terminal.add(unit)
    assert checked_terminal == set(initial)
    return alias, dict(PASS=True, original_binary_arcs=len(alias), flow_rows=len(checked) + empty,
        terminal_rows=len(checked_terminal), source_graph_edges=len(edges),
        original_integer_flow_implies_single_forward_path=True, added_unavailable_edges_only_relax_R=True)


def corners(planes):
    # Exact complete vertex enumeration of the independently recovered halfspaces.
    result = set()
    for first, second in combinations(planes, 2):
        a, b, c = first
        e, f, g = second
        determinant = a * f - b * e
        if not determinant:
            continue
        point = ((c * f - b * g) / determinant, (a * g - c * e) / determinant)
        if all(u * point[0] + v * point[1] <= w for u, v, w in planes):
            result.add(point)
    assert result, "NO_BOUNDED_LOCAL_DISPATCH_VERTICES"
    return result


def dispatch_sources(A, d, edges, alias):
    families = [str(name).split("[", 1)[0] for name in d["names"]]
    groups = defaultdict(dict)
    reverse = {}
    for j, family in enumerate(families):
        if family not in ("Pch", "Pdis", "Q"):
            continue
        _, args = split_name(d["names"][j])
        key = args[0], args[1], int(args[2])
        groups[key][family] = j
        reverse[j] = key
    assert len(groups) == 8942 and all(set(value) == {"Pch", "Pdis", "Q"} for value in groups.values())
    planes = defaultdict(list)
    connections = defaultdict(set)
    for i in np.flatnonzero(d["row_names"] == "PCS16"):
        row = A.getrow(int(i))
        keys = {reverse[int(j)] for j in row.indices if int(j) in reverse}
        assert len(keys) == 1 and d["sense"][i] == "<"
        key = next(iter(keys))
        columns = groups[key]
        a = q(row[0, columns["Pdis"]])
        b = q(row[0, columns["Q"]])
        assert q(row[0, columns["Pch"]]) == -a
        bound = q(d["rhs"][i])
        aliases = []
        for j, coefficient in zip(row.indices, row.data):
            if int(j) in reverse:
                continue
            family, args = split_name(d["names"][j])
            assert family in ("route_flow", "node_activity")
            assert 0 <= d["lower"][j] <= d["upper"][j] <= 1
            unit, site, slot = key
            index = int(args[1]) if family == "route_flow" else next(index for index, edge in enumerate(edges[:2304]) if edge[:2] == (site, slot))
            assert edges[index][:4] == (site, slot, site, slot + 1), "DISPATCH_ALIAS_NOT_ORIGINAL_STAY"
            assert args[0] == unit and alias[unit, index] == (int(j), F(0)), "INVALID_ORIGINAL_INVERSE_STAY_ALIAS"
            aliases.append(int(j))
            bound -= min(q(coefficient) * q(d["lower"][j]), q(coefficient) * q(d["upper"][j]))
        assert len(aliases) == 1 and d["rhs"][i] == 0
        connections[key].add(aliases[0])
        planes[key].append((a, b, bound))
    # The original binary mode permits exactly one sign of net real power.
    seen_modes = set()
    for family, power, mode_sign, right in (("no_simultaneous_charge", "Pch", -1, 0),
                                           ("no_simultaneous_discharge", "Pdis", 1, 300)):
        for i in np.flatnonzero(d["row_names"] == family):
            row = A.getrow(int(i))
            modes = [(int(j), q(a)) for j, a in zip(row.indices, row.data) if families[j] == "charge_mode"]
            assert len(modes) == 1 and modes[0][1] == mode_sign * 300
            j = modes[0][0]
            assert d["types"][j] == "B" and d["lower"][j] == 0 and d["upper"][j] == 1
            unit, slot = split_name(d["names"][j])[1]
            assert d["sense"][i] == "<" and q(d["rhs"][i]) == right
            targets = {int(k): q(a) for k, a in zip(row.indices, row.data) if k != j}
            assert len(targets) == 1
            power_column, coefficient = next(iter(targets.items()))
            key = reverse[power_column]
            assert key[0] == unit and key[2] == int(slot)
            assert families[power_column] == power and coefficient == 1, "ORIGINAL_CHARGE_DISCHARGE_EXCLUSIVITY_NOT_COVERED"
            assert (family, key) not in seen_modes
            seen_modes.add((family, key))
    assert len(seen_modes) == 2 * len(groups)
    cache, polygons = {}, {}
    for key, columns in groups.items():
        ch, dis, reactive = (columns[power] for power in ("Pch", "Pdis", "Q"))
        assert d["lower"][ch] == d["lower"][dis] == 0
        assert len(connections[key]) == 1
        assert any(b > 0 for a, b, c in planes[key]) and any(b < 0 for a, b, c in planes[key]), "NO_ZERO_Q_DURING_TRAVEL_PROOF"
        local = tuple(planes[key] + [(F(1), F(0), q(d["upper"][dis])),
            (F(-1), F(0), q(d["upper"][ch])), (F(0), F(1), q(d["upper"][reactive])),
            (F(0), F(-1), -q(d["lower"][reactive]))])
        if local not in cache:
            cache[local] = (corners(local + ((F(1), F(0), F(0)),)),
                            corners(local + ((F(-1), F(0), F(0)),)))
        polygons[key] = cache[local]
    energy = defaultdict(lambda: defaultdict(F))
    rhs = defaultdict(F)
    counts = defaultdict(int)
    suffix_terms = defaultdict(lambda: defaultdict(F))
    suffix_rhs = defaultdict(F)
    suffix_rows = defaultdict(list)
    for i in np.flatnonzero(d["row_names"] == "energy_balance"):
        row = A.getrow(int(i))
        units = {split_name(d["names"][j])[1][0] for j in row.indices}
        assert len(units) == 1 and d["sense"][i] == "="
        unit = next(iter(units))
        counts[unit] += 1
        rhs[unit] += q(d["rhs"][i])
        slots = {reverse[int(j)][2] for j in row.indices if int(j) in reverse}
        assert len(slots) == 1
        slot = next(iter(slots))
        for j, coefficient in zip(row.indices, row.data):
            energy[unit][int(j)] += q(coefficient)
        if slot >= 66:
            suffix_rows[unit].append(int(i))
            suffix_rhs[unit] += q(d["rhs"][i])
            for j, coefficient in zip(row.indices, row.data):
                suffix_terms[unit][int(j)] += q(coefficient)
    for unit, coefficients in energy.items():
        assert counts[unit] == 96 and rhs[unit] == 0
        for j, coefficient in coefficients.items():
            if not coefficient:
                continue
            family, args = split_name(d["names"][j])
            if family == "route_flow":
                index = int(args[1])
                assert coefficient == edges[index][4] and not edges[index][5]
                assert alias[unit, index] == (j, F(0))
            else:
                assert family in ("Pch", "Pdis"), "UNCANCELLED_SOC_OR_UNMODELLED_ENERGY_TERM"
    suffix_allowances = {}
    for unit, terms in suffix_terms.items():
        remaining = {j: value for j, value in terms.items() if value}
        state = [(j, value) for j, value in remaining.items() if families[j] == "SOC"]
        assert len(suffix_rows[unit]) == 30 and len(state) == 1
        j, coefficient = state[0]
        assert str(d["names"][j]) == f"SOC[{unit},66]" and coefficient == -1
        assert suffix_rhs[unit] == -760
        allowance = suffix_rhs[unit] - min(coefficient * q(d["lower"][j]), coefficient * q(d["upper"][j]))
        assert allowance == 320
        for k, value in remaining.items():
            if k == j:
                continue
            assert value == energy[unit][k]
            if families[k] == "route_flow":
                index = int(split_name(d["names"][k])[1][1])
                assert edges[index][1] >= 66
            else:
                assert reverse[k][2] >= 66
        # Check omitted coefficients too, including arcs that cross slot 66.
        for k, value in energy[unit].items():
            if not value:
                continue
            if families[k] == "route_flow":
                departure = edges[int(split_name(d["names"][k])[1][1])][1]
            else:
                departure = reverse[k][2]
            assert terms.get(k, F(0)) == (value if departure >= 66 else F(0)), "INCOMPLETE_SUFFIX_ENERGY_COEFFICIENT_COVERAGE"
        suffix_allowances[unit] = allowance
    return groups, polygons, energy, suffix_allowances, dict(PASS=True, triplets=len(groups), local_PCS_rows=89420,
        independent_dispatch_polygons=len(cache), binary_mode_constraints=len(seen_modes),
        summed_energy_equalities=dict(counts), summed_energy_rhs={u: str(value) for u, value in rhs.items()},
        suffix_30_energy_equalities={u: rows for u, rows in suffix_rows.items()},
        suffix_energy_upper_bounds={u: str(value) for u, value in suffix_allowances.items()},
        all_original_stay_aliases_checked=True, travel_P_Q_zero_proven=True,
        intermediate_SOC_bounds_relaxed=True, full_original_feasible_domain_contained=True)


def vehicle_rewards(weights, groups, polygons, energy, unit, multiplier, suffix_multiplier=F(0)):
    rewards = {}
    for key, columns in groups.items():
        if key[0] != unit:
            continue
        wp = weights.get(columns["Pdis"], F(0))
        wq = weights.get(columns["Q"], F(0))
        assert weights.get(columns["Pch"], F(0)) == -wp
        ch, dis = energy[unit][columns["Pch"]], energy[unit][columns["Pdis"]]
        assert ch < 0 < dis
        local_multiplier = multiplier + (suffix_multiplier if key[2] >= 66 else F(0))
        rewards[key[1:]] = max((wp * p + wq * reactive - local_multiplier * (ch * (-p) if p <= 0 else dis * p))
                              for vertices in polygons[key] for p, reactive in vertices)
    return rewards


def check_vehicle(proof, weights, groups, polygons, energy, suffix_allowances, sites, edges, initial):
    unit = proof["MESS"]
    assert proof["initial_site"] == initial[unit] and F(proof["terminal_energy_identity_rhs"]) == 0
    multiplier = F(proof["mu"])
    suffix_multiplier = F(proof.get("suffix_mu", "0"))
    assert suffix_multiplier >= 0, "INVALID_SUFFIX_ENERGY_MULTIPLIER_SIGN"
    if "suffix_energy_allowance" in proof:
        assert F(proof["suffix_energy_allowance"]) == suffix_allowances[unit]
    rewards = vehicle_rewards(weights, groups, polygons, energy, unit, multiplier, suffix_multiplier)
    declared_rewards = {(record["site"], int(record["slot"])): F(record["value"]) for record in proof["stay_rewards"]}
    assert declared_rewards == rewards, "DISPATCH_SUPPORT_UNDER_OR_MIS_ESTIMATED"
    potentials = {(record["site"], int(record["slot"])): F(record["value"]) for record in proof["edge_potentials"]}
    assert len(potentials) == len(proof["edge_potentials"])
    assert set(potentials) == {(s, t) for s in sites for t in range(97)}, "DP_ROUTE_RELAXATION_NODE_OMITTED"
    assert all(potentials[s, 96] == 0 for s in sites), "INVALID_TERMINAL_POTENTIAL"
    maximum = None
    for origin, depart, dest, ready, route_energy, stay in edges:
        local_multiplier = multiplier + (suffix_multiplier if depart >= 66 else F(0))
        gain = rewards.get((origin, depart), F(0)) if stay else -local_multiplier * route_energy
        slack = potentials[origin, depart] - gain - potentials[dest, ready]
        assert slack >= 0, "ORIGINAL_ROUTE_EDGE_NOT_COVERED_BY_UPPER_BOUND"
        maximum = slack if maximum is None else max(maximum, slack)
    upper = potentials[initial[unit], 0] + suffix_multiplier * suffix_allowances[unit]
    assert F(proof["U_exact"]) == upper, "CAPACITY_UNDERESTIMATED_OR_INCUMBENT_AS_UPPER"
    return upper, dict(PASS=True, MESS=unit, original_edges_checked=len(edges),
        terminal_nodes=len(sites), exact_U=str(upper), exact_mu=str(multiplier), exact_suffix_mu=str(suffix_multiplier),
        potential_telescoping_bound=True, complete_source_DAG_checked=True,
        full_original_energy_equality_rhs_zero=True, no_maximization_incumbent_used=True)


def expect_rejected(callable_check, label):
    try:
        callable_check()
    except AssertionError as error:
        return dict(mutation=label, rejected=True, reason=str(error))
    raise AssertionError("INDEPENDENT_CHECKER_ACCEPTED_TAMPER:" + label)


def main():
    import gurobipy as gp
    gp.Model.optimize = lambda *a, **k: (_ for _ in ()).throw(AssertionError("CHECKER_OPTIMIZE_FORBIDDEN"))
    begin = time.perf_counter()
    A, d, T, AA, dd, unused_sources = load_sources()
    demands = read(OUT / "GRID_DEMAND_CERTIFICATE.json")
    capacities = read(OUT / "MESS_CAPACITY_UPPER_BOUNDS.json")
    sites, edges, initial = route_graph()
    reader = independent_physical_reader()
    alias, flow_audit = check_original_route_flow(reader, sites, edges, initial)
    groups, polygons, energy, suffix_allowances, structure = dispatch_sources(A, d, edges, alias)
    results, mutations = [], []
    for demand_summary in demands["candidates"]:
        label = demand_summary["label"]
        certificate = gz(demand_summary["exact_artifact"])
        weights, constant, rho_coefficient, demand, demand_audit = check_demand(A, d, certificate)
        assert q(demand_summary["D_0_60_lower"]) <= demand <= q(demand_summary["D_0_60_upper"])
        summary = next(item for item in capacities["candidates"] if item["label"] == label)
        capacity = gz(summary["exact_artifact"])
        assert capacity["source_route_sha256"] == ROUTE_SHA
        assert {item["MESS"] for item in capacity["vehicles"]} == set(initial)
        audits = []
        total = F(0)
        for proof in capacity["vehicles"]:
            upper, audit = check_vehicle(proof, weights, groups, polygons, energy, suffix_allowances, sites, edges, initial)
            vehicle_summary = next(item for item in summary["vehicles"] if item["MESS"] == proof["MESS"])
            assert q(vehicle_summary["U_lower"]) <= upper <= q(vehicle_summary["U_upper"])
            assert F(vehicle_summary["U_exact"]) == upper
            assert vehicle_summary["certified_support_incumbent"] is None
            audits.append(audit)
            total += upper
        assert F(summary["sum_U_exact"]) == total and q(summary["sum_U_upper"]) >= total
        difference = demand - total
        lower_bound = (total - constant) / rho_coefficient
        results.append(dict(label=label, PASS=True, demand=demand_audit, vehicles=audits,
            exact_D=str(demand), exact_sum_U=str(total), exact_D_minus_sum_U=str(difference),
            exact_support_lower_bound=str(lower_bound), strict_global_contradiction=difference > 0,
            status="INFEASIBILITY_CERTIFIED" if difference > 0 else "NOT_PROVEN"))
        if not mutations:
            bad = copy.deepcopy(certificate)
            bad["constant"] = str(constant + 1)
            mutations.append(expect_rejected(lambda: check_demand(A, d, bad), "missing_affine_constant"))
            bad = copy.deepcopy(certificate)
            bad["rows"][0]["orientation"] = -int(bad["rows"][0].get("orientation", 1))
            mutations.append(expect_rejected(lambda: check_demand(A, d, bad), "reversed_thermal_sign"))
            bad = copy.deepcopy(certificate)
            bad["weights"][0]["coefficient"] = str(F(bad["weights"][0]["coefficient"]) + 1)
            mutations.append(expect_rejected(lambda: check_demand(A, d, bad), "edited_support_coefficient"))
            bad = copy.deepcopy(capacity["vehicles"][0])
            bad["U_exact"] = str(F(bad["U_exact"]) - 1)
            mutations.append(expect_rejected(lambda: check_vehicle(bad, weights, groups, polygons, energy, suffix_allowances, sites, edges, initial), "capacity_underestimated_incumbent"))
            bad = copy.deepcopy(capacity["vehicles"][0])
            bad["edge_potentials"].pop()
            mutations.append(expect_rejected(lambda: check_vehicle(bad, weights, groups, polygons, energy, suffix_allowances, sites, edges, initial), "unsafe_DP_route_relaxation"))
    output = dict(PASS=True, source_flow_containment=flow_audit, source_dispatch_energy_containment=structure,
        comparisons=results, tamper_rejection_tests=mutations, native_optimize_calls=0,
        independent_CSR_row_combination=True, producer_recursive_affine_closure_not_imported=True,
        every_original_full_graph_edge_checked=True, precision="Exact rationals from original immutable binary64 inputs",
        controller_wall_seconds=time.perf_counter() - begin)
    write(OUT / "INDEPENDENT_GRID_CAPACITY_CHECK.json", output)
    print(json.dumps(dict(PASS=True, comparisons=len(results), native_optimize_calls=0,
        controller_wall_seconds=output["controller_wall_seconds"])), flush=True)


if __name__ == "__main__":
    main()
