"""Independent rational lower-capacity witnesses in original vehicle physics.

Checks both immutable C3A+B2 vehicle rows and original FULL vehicle rows through
the saved affine inverse, accumulated with exact rational constants. Grid rows
are explicitly excluded, so these witnesses are not global counterexamples.
"""
import gzip
import json
import time
from collections import Counter
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

import numpy as np

from .check_source_cutoff import ROOT, OUT, SOURCE, sha, read, write, load_sources, independent_physical_reader
from .check_grid_capacity import gz, q, split_name, expect_rejected, route_graph
from .check_vehicles import original_projection

FULL_PHYSICAL = {"flow", "terminal_location", "connected_Pch", "connected_Pdis", "connected_Qmax",
    "connected_Qmin", "no_simultaneous_charge", "no_simultaneous_discharge", "PCS16",
    "energy_balance", "initial_SOC", "terminal_SOC"}


def exact_rows(matrix, data, rows, values):
    families = Counter()
    for i in rows:
        i = int(i)
        left = F(0)
        for cursor in range(matrix.indptr[i], matrix.indptr[i + 1]):
            j = int(matrix.indices[cursor])
            if values.get(j, F(0)):
                left += q(matrix.data[cursor]) * values[j]
        right = q(data["rhs"][i])
        sense = str(data["sense"][i])
        passed = left == right if sense == "=" else left <= right if sense == "<" else left >= right if sense == ">" else False
        assert passed, "EXACT_ORIGINAL_ROW_VIOLATION:" + str(i) + ":" + str(left - right)
        families[str(data["row_names"][i]).split("[", 1)[0]] += 1
    return dict(families)


def exact_bounds_types(data, columns, values):
    binary = 0
    for j in columns:
        j = int(j)
        value = values.get(j, F(0))
        assert q(data["lower"][j]) <= value <= q(data["upper"][j]), "EXACT_ORIGINAL_BOUND_VIOLATION:" + str(j)
        if data["types"][j] == "B":
            binary += 1
            assert value in (F(0), F(1)), "EXACT_ORIGINAL_BINARY_VIOLATION:" + str(j)
    return binary


def inverse_function(values):
    path = ROOT / "docs/v42_m1_supercompact_exact_20261006"
    with np.load(path / "C2_RETAINED_AXES.npz", allow_pickle=False) as archive:
        retained = {int(j): index for index, j in enumerate(archive["columns"])}
    steps = {int(record["column"]): record for record in read(path / "C2_ELIMINATION_CERTIFICATES.json")}
    @lru_cache(None)
    def original(j):
        if j in retained:
            return values.get(retained[j], F(0))
        record = steps[j]
        assert len(record["terms"]) <= 1
        constant = q(record["constant"])
        for column, coefficient in record["terms"].items():
            assert coefficient == 1.0
            constant += q(coefficient) * original(int(column))
        return constant
    return original


def check_witness(witness, unit, A, d, AA, dd, weights, reader, edges, initial):
    assert witness["MESS"] == unit
    assert witness["source_matrix_sha256"] == sha(SOURCE / "C3A_A.npz")
    assert witness["source_data_sha256"] == sha(SOURCE / "C3A_DATA.npz")
    columns, rows, unused_matrix, unused_local = original_projection(AA, d, dd, unit)
    assert witness["projection_columns"] == columns.tolist()
    assert witness["projection_rows"] == rows.tolist()
    assert witness["all_other_projected_values_exactly_zero"]
    assert witness["projection_sha256"] == sha(OUT / "vehicles" / unit / "LOCAL_PROJECTION.npz")
    values = {}
    belongs = set(map(int, columns))
    for item in witness["nonzero_values"]:
        j = int(item["column"])
        assert j in belongs and j not in values and str(d["names"][j]) == item["name"]
        values[j] = F(item["value"])
        assert values[j] != 0
    binaries = exact_bounds_types(d, columns, values)
    families = exact_rows(AA, dd, rows, values)
    assert families == witness["row_families"]
    support = sum(weights.get(j, F(0)) * value for j, value in values.items())
    assert support == F(witness["support_exact"]), "EXACT_SUPPORT_EVALUATION_CHANGED"
    # All full original private physical columns are reconstructed using exact
    # saved elimination constants; no rounded float inverse vector is used.
    full, full_data = reader.full.tocsr(), reader.d
    full_columns = [j for j, name in enumerate(full_data["names"])
                    if "[" in str(name) and split_name(name)[1][0] == unit]
    inverse = inverse_function(values)
    full_values = {j: inverse(j) for j in full_columns if inverse(j)}
    full_binaries = exact_bounds_types(full_data, full_columns, full_values)
    belongs_full = set(full_columns)
    full_rows = []
    for i, name in enumerate(full_data["row_names"]):
        if str(name).split("[", 1)[0] not in FULL_PHYSICAL:
            continue
        indices = set(map(int, full.indices[full.indptr[i]:full.indptr[i + 1]]))
        if indices & belongs_full:
            assert indices.issubset(belongs_full), "FULL_PHYSICAL_ROW_CROSSES_VEHICLES"
            full_rows.append(i)
    full_families = exact_rows(full, full_data, full_rows, full_values)
    assert full_families["energy_balance"] == 96 and full_families["initial_SOC"] == full_families["terminal_SOC"] == 1
    assert full_families["terminal_location"] == 1
    arcs = [(split_name(full_data["names"][j])[1], value) for j, value in full_values.items()
            if str(full_data["names"][j]).startswith("arc[")]
    assert len(arcs) == 96 and all(value == 1 for unused, value in arcs)
    assert witness["original_integer_route_projection_sha256"] == sha(
        ROOT / "docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json")
    source_arcs = [edges[int(args[1])] for args, value in arcs]
    assert all(args[0] == unit for args, value in arcs)
    assert sorted(source_arcs) == [(initial[unit], t, initial[unit], t + 1, F(0), True)
                                   for t in range(96)], "ORIGINAL_WITNESS_IS_NOT_96_INITIAL_SITE_STAY_ARCS"
    return support, dict(PASS=True, MESS=unit, exact_support=str(support),
        C3A_B2_exact_rows=len(rows), C3A_binary_columns=binaries, C3A_row_families=families,
        FULL_original_exact_rows=len(full_rows), FULL_original_binary_columns=full_binaries,
        FULL_original_row_families=full_families, FULL_original_96_integer_STAY_arcs=True,
        independent_rational_affine_inverse=True, exact_bound_and_binary_checks=True,
        numerical_tolerance_used=False, original_coupled_grid_constraints_checked=False)


def main():
    import gurobipy as gp
    gp.Model.optimize = lambda *a, **k: (_ for _ in ()).throw(AssertionError("EXACT_WITNESS_CHECKER_OPTIMIZE_FORBIDDEN"))
    start = time.perf_counter()
    A, d, T, AA, dd, unused = load_sources()
    selected = read(OUT / "GRID_DEMAND_CERTIFICATE.json")["selected"]
    grid = gz(selected["exact_artifact"])
    weights = {int(item["column"]): F(item["coefficient"]) for item in grid["weights"]}
    summary = read(OUT / "EXACT_LOCAL_CAPACITY_LOWER_WITNESSES.json")
    assert summary["PASS"] and not summary["global_feasible_counterexample"]
    reader = independent_physical_reader()
    unused_sites, edges, initial = route_graph()
    assert len(summary["vehicles"]) == 4 and {item["MESS"] for item in summary["vehicles"]} == set(initial), \
        "EXACT_WITNESS_VEHICLES_MISSING_OR_DUPLICATED"
    total, checks, tests = F(0), [], []
    for item in summary["vehicles"]:
        witness = gz(item["exact_artifact"])
        assert witness["grid_exact_sha256"] == selected["exact_artifact"]["sha256"]
        support, audit = check_witness(witness, item["MESS"], A, d, AA, dd, weights, reader, edges, initial)
        assert support == F(item["support_exact"]) and q(item["support_lower"]) <= support
        total += support
        checks.append(audit)
        if not tests:
            import copy
            bad = copy.deepcopy(witness)
            bad["support_exact"] = str(support + 1)
            tests.append(expect_rejected(lambda: check_witness(bad, item["MESS"], A, d, AA, dd, weights, reader, edges, initial), "edited_lower_support"))
    demand = F(grid["D_exact"])
    assert total == F(summary["sum_support_exact"]) and demand == F(summary["D_exact"])
    assert total - demand == F(summary["sum_support_minus_D_exact"]) and total > demand
    output = dict(PASS=True, vehicles=checks, exact_sum_capacity_lower=str(total), exact_D=str(demand),
        exact_lower_capacity_minus_D=str(total - demand),
        selected_scalar_direction_cannot_prove_infeasibility_even_with_exact_vehicle_physics=True,
        exact_zero_tolerance_original_FULL_physical_vehicle_witnesses=True,
        grid_feasible_counterexample=False, global_cutoff_feasibility="NOT_PROVEN",
        limitation="Each original vehicle witness satisfies exact local physical constraints, but coupled original grid constraints are not checked",
        tamper_tests=tests, native_optimize_calls=0, controller_wall_seconds=time.perf_counter() - start)
    write(OUT / "INDEPENDENT_LOCAL_EXACT_WITNESS_CHECK.json", output)
    print(json.dumps(dict(PASS=True, exact_lower_sum=float(total), D=float(demand),
        native_optimize_calls=0, controller_wall_seconds=output["controller_wall_seconds"])), flush=True)


if __name__ == "__main__":
    main()
