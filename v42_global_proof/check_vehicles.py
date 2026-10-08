"""Independently replay saved vehicle projections and native results, optimize=0."""
import gzip
import hashlib
import json
import time
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

import numpy as np

from .check_source_cutoff import ROOT, OUT, read, sha, write, load_sources, same_array, csr_sha

PHYSICAL_FAMILIES = {"flow", "connected_Pch", "connected_Pdis", "no_simultaneous_charge",
    "no_simultaneous_discharge", "PCS16", "node_activity_link", "energy_balance", "temporal_reachability"}


def dyadic(value):
    return F.from_float(float(value))


def original_projection(AA, d, dd, unit):
    units = [str(name).split("[", 1)[1].split(",", 1)[0] if "[" in str(name) else "" for name in d["names"]]
    columns = np.array([j for j, value in enumerate(units) if value == unit], dtype=np.intp)
    belongs = set(map(int, columns))
    rows = []
    for i, name in enumerate(dd["row_names"]):
        if str(name).split("[", 1)[0] not in PHYSICAL_FAMILIES:
            continue
        support = set(map(int, AA.indices[AA.indptr[i]:AA.indptr[i + 1]]))
        if support & belongs:
            assert support.issubset(belongs), "ORIGINAL_PHYSICAL_ROW_HAS_COUPLED_UNIT_COLUMNS"
            rows.append(i)
    rows = np.array(rows, dtype=int)
    matrix = AA[rows][:, columns].tocsr()
    data = {key: d[key][columns].copy() for key in ("lower", "upper", "types", "names")}
    data.update({key: dd[key][rows].copy() for key in ("rhs", "sense", "row_names")})
    return columns, rows, matrix, data


def objective_and_conversion(columns, lower, upper, exact_weights):
    objective = np.array([float(exact_weights.get(int(j), F(0))) for j in columns])
    correction = F(0)
    for index, column in enumerate(columns):
        delta = exact_weights.get(int(column), F(0)) - dyadic(objective[index])
        correction += max(delta * dyadic(lower[index]), delta * dyadic(upper[index]))
    return objective, correction


def incumbent_replay(matrix, data, x, objective, exact_weights, columns):
    assert x.shape == (len(columns),) and x.dtype == np.dtype("float64")
    residual = matrix @ x - data["rhs"]
    violation = np.where(data["sense"] == "=", abs(residual), np.where(data["sense"] == "<", residual, -residual))
    maximum_row = float(np.max(violation, initial=0))
    maximum_bound = max(float(np.max(data["lower"] - x, initial=0)), float(np.max(x - data["upper"], initial=0)))
    integers = data["types"] == "B"
    maximum_integer = float(np.max(np.abs(x[integers] - np.rint(x[integers])), initial=0))
    support = sum(exact_weights.get(int(column), F(0)) * dyadic(x[index]) for index, column in enumerate(columns))
    passed = bool(np.isfinite(x).all() and maximum_row <= 1e-8 and maximum_bound <= 1e-8 and maximum_integer <= 1e-8)
    return dict(PASS=passed, max_original_row_violation=maximum_row, max_original_bound_violation=maximum_bound,
        max_original_integrality_violation=maximum_integer, scientific_tolerance=1e-8,
        original_exact_support=str(support), rounded_binary64_objective=float(objective @ x),
        raw_vector_unchanged=True, incumbent_is_not_capacity_upper_bound=True)


def main():
    import gurobipy as gp
    gp.Model.optimize = lambda *a, **k: (_ for _ in ()).throw(AssertionError("VEHICLE_CHECKER_OPTIMIZE_FORBIDDEN"))
    start = time.perf_counter()
    A, d, T, AA, dd, unused = load_sources()
    demand = read(OUT / "GRID_DEMAND_CERTIFICATE.json")["selected"]
    exact_path = OUT / Path(demand["exact_artifact"]["path"]).name
    assert exact_path.resolve().is_relative_to(OUT.resolve())
    assert sha(exact_path) == demand["exact_artifact"]["sha256"]
    exact = json.loads(gzip.decompress(exact_path.read_bytes()))
    weights = {int(item["column"]): F(item["coefficient"]) for item in exact["weights"]}
    registration = read(OUT / "EXPERIMENT_PREREGISTRATION.json")
    checks, covered_binary_columns = [], set()
    incumbent_support_total = F(0)
    for unit in ("MESS01", "MESS02", "MESS03", "MESS04"):
        folder = OUT / "vehicles" / unit
        columns, rows, matrix, data = original_projection(AA, d, dd, unit)
        with np.load(folder / "LOCAL_PROJECTION.npz", allow_pickle=False) as archive:
            saved = {key: archive[key].copy() for key in archive.files}
        same_array(columns, saved["columns"], unit + "_all_private_columns")
        same_array(rows, saved["rows"], unit + "_all_physical_rows")
        for key in ("lower", "upper", "types", "rhs", "sense"):
            same_array(data[key], saved[key], unit + "_" + key)
        objective, correction = objective_and_conversion(columns, data["lower"], data["upper"], weights)
        same_array(objective, saved["objective"], unit + "_objective")
        identity = read(folder / "MODEL_IDENTITY.json")
        result = read(folder / "RESULT.json")
        assert identity["PASS"] and identity["MESS"] == result["MESS"] == unit
        assert identity["source_columns"] == len(columns) and identity["source_rows"] == len(rows)
        binaries = columns[data["types"] == "B"]
        assert identity["binary_count"] == len(binaries)
        assert not covered_binary_columns.intersection(map(int, binaries))
        covered_binary_columns.update(map(int, binaries))
        assert identity["source_CSR_sha256"] == csr_sha(matrix)
        families = Counter(str(name).split("[", 1)[0] for name in data["row_names"])
        assert dict(families) == identity["row_families"]
        assert families["energy_balance"] == 96 and families["PCS16"] > 0 and families["flow"] > 0
        assert F(identity["objective_binary64_conversion_error_upper_exact"]) == correction
        assert F(result["objective_conversion_error_upper_exact"]) == correction
        assert identity["settings"] == registration["vehicle_settings"]
        assert identity["settings"]["Threads"] == 1
        for key in ("FeasibilityTol", "OptimalityTol", "IntFeasTol"):
            assert identity["settings"][key] == 1e-8
        assert result["native_calls"] == 1 and result["Runtime"] <= 600
        assert not result.get("callback_errors", []), "VEHICLE_CALLBACK_ERROR"
        assert not result["exact_bound_adopted"] and not result["numerical_MIP_bound_used_as_global_proof"]
        incumbent = None
        if int(result.get("SolCount", 0)) > 0:
            with np.load(folder / "INCUMBENT.npz", allow_pickle=False) as archive:
                incumbent = incumbent_replay(matrix, data, archive["x"].copy(), objective, weights, columns)
            assert incumbent["PASS"] == result["local_incumbent_replay"]["PASS"]
            assert F(result["incumbent_support_exact_evaluation"]) == F(incumbent["original_exact_support"])
            assert incumbent["PASS"], "VEHICLE_INCUMBENT_SCIENTIFIC_REPLAY_FAILED"
            incumbent_support_total += F(incumbent["original_exact_support"])
        if result.get("ObjBound") is not None:
            assert dyadic(result["numerical_support_upper_after_conversion"]) >= dyadic(result["ObjBound"]) + correction
        checks.append(dict(PASS=True, MESS=unit, source_columns=len(columns), original_physical_rows=len(rows),
            original_binaries=len(binaries), original_B2_rows=families.get("temporal_reachability", 0),
            exact_objective_rounding_allowance=str(correction), incumbent_replay=incumbent,
            numerical_Status=result["Status"], native_Runtime=result["Runtime"], numerical_Work=result["Work"],
            observed_sampled_peak_RSS_bytes=result["peak_RSS_bytes"],
            RSS_measurement_scope="Lower bound from periodic process RSS samples; not an OS lifetime peak",
            analytical_capacity_upper_remains_authority=True, numerical_bound_never_exact_proof=True))
    assert covered_binary_columns == set(map(int, np.flatnonzero(d["types"] == "B"))), "NOT_ALL_9322_ORIGINAL_BINARIES_COVERED"
    capacity = read(OUT / "MESS_CAPACITY_UPPER_BOUNDS.json")["selected"]
    analytical_upper = F(capacity["sum_U_exact"])
    scalar_demand = F(demand["D_exact"])
    all_incumbents = all(item["incumbent_replay"] is not None for item in checks)
    output = dict(PASS=True, vehicles=checks, all_original_9322_binary_columns_covered=True,
        all_unit_private_physical_rows_preserved=True, exact_support_to_binary64_conversion_certified=True,
        grid_coupling_removed_is_a_valid_projection_relaxation=True,
        analytical_uppers_remain_authoritative=True, numerical_MIP_bounds_not_exact_certificates=True,
        scalar_certificate_strength=dict(selected_label=demand["label"],
            exact_D=str(scalar_demand), exact_analytical_sum_U=str(analytical_upper),
            all_four_scientifically_valid_original_vehicle_incumbents=all_incumbents,
            exact_evaluation_sum_incumbent_support=str(incumbent_support_total),
            analytical_upper_minus_scientific_incumbents_exact=str(analytical_upper - incumbent_support_total),
            scientific_incumbent_support_minus_D_exact=str(incumbent_support_total - scalar_demand),
            scalar_contradiction_still_fails=all_incumbents and incumbent_support_total >= scalar_demand,
            implication="For these fixed support weights, capacity relaxation looseness cannot bridge the demand deficit; independent vehicle incumbents already support more than D",
            limitation="These are separate vehicle schedules. Combined grid feasibility is not checked and this is not a global cutoff counterexample",
            scientific_feasibility_tolerance=1e-8, exact_primal_feasibility_certificate=False),
        native_optimize_calls=0, controller_wall_seconds=time.perf_counter() - start)
    write(OUT / "INDEPENDENT_VEHICLE_CHECK.json", output)
    print(json.dumps(dict(PASS=True, native_optimize_calls=0, controller_wall_seconds=output["controller_wall_seconds"])), flush=True)


if __name__ == "__main__":
    main()
