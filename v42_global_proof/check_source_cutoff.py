"""Independent saved-source/cutoff checker. No producer or solver build imports.

Native receipt hashes attest transport; saved native arrays are compared byte for
byte with independently loaded source archives. Solver INFEASIBLE alone is never
promoted to an exact global infeasibility certificate.
"""
import os

os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/v42_m1_global_physical_proof_20261008"
BASE = "4b19e85089171729a3225529a40cb00bf31f43d5"
SOURCE = ROOT / "docs/v42_m1_ultracompact_exact_20261006"
B2 = ROOT / "docs/v42_m1_b2_root_validation_20261008/artifacts"
RHO = 239826
CUTOFF = 0.60
EXPECTED = {
    SOURCE / "C3A_A.npz": "45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8",
    SOURCE / "C3A_DATA.npz": "20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467",
    SOURCE / "C3A_VALID_START.npz": "be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5",
    B2 / "TEMPORAL_VALID_ROWS.npz": "13e7f99897505e4b0e3134c923173925259971df218ec463e95f153b354e4536",
    B2 / "TEMPORAL_VALID_ROW_DATA.npz": "318f3b4d19e9b2e228368bc405dd7b26cf862c9d7bbb3a8ebde15c71f6f536d7",
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def clean(value):
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(item) for item in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def array_sha(value):
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def csr_sha(matrix):
    matrix = matrix.tocsr()
    digest = hashlib.sha256()
    for value in (matrix.indptr, matrix.indices, matrix.data):
        digest.update(value.tobytes())
    return digest.hexdigest()


def same_array(first, second, label):
    first, second = np.asarray(first), np.asarray(second)
    assert first.dtype == second.dtype, label + "_DTYPE_CHANGED"
    assert first.shape == second.shape, label + "_SHAPE_CHANGED"
    assert first.tobytes() == second.tobytes(), label + "_BITS_CHANGED"


def load_sources():
    sources = {}
    for path, expected in EXPECTED.items():
        actual = sha(path)
        assert actual == expected, "SOURCE_HASH_CHANGED:" + str(path)
        sources[path.relative_to(ROOT).as_posix()] = dict(sha256=actual, bytes=path.stat().st_size)
    A = sparse.load_npz(SOURCE / "C3A_A.npz").tocsr()
    with np.load(SOURCE / "C3A_DATA.npz", allow_pickle=False) as archive:
        d = {key: archive[key].copy() for key in archive.files}
    T = sparse.load_npz(B2 / "TEMPORAL_VALID_ROWS.npz").tocsr()
    with np.load(B2 / "TEMPORAL_VALID_ROW_DATA.npz", allow_pickle=False) as archive:
        rhs = archive["rhs"].copy()
    assert A.shape == (582808, 306040) and A.nnz == 5351612
    assert T.shape == (651, 306040) and T.nnz == 1302
    assert int(np.count_nonzero(d["types"] == "B")) == 9322
    assert set(d["types"]) == {"B", "C"}
    assert d["names"][RHO] == "rho_max"
    assert np.flatnonzero(d["objective"]).tolist() == [RHO] and d["objective"][RHO] == 1.0
    assert np.asarray(d["constant"]).tobytes().hex() == "0000000000000000"
    AA = sparse.vstack((A, T), format="csr")
    dd = dict(d, rhs=np.r_[d["rhs"], rhs], sense=np.r_[d["sense"], np.full(651, "<")],
              row_names=np.r_[d["row_names"], np.array([f"temporal_reachability[{i}]" for i in range(651)])])
    return A, d, T, AA, dd, sources


def expected_cutoff_data(dd, name="rho_cutoff_0p60"):
    return dict(dd, rhs=np.r_[dd["rhs"], np.float64(CUTOFF)], sense=np.r_[dd["sense"], np.array(["<"])],
                row_names=np.r_[dd["row_names"], np.array([name])])


def check_native_arrays(dd, candidate, cutoff_name="rho_cutoff_0p60"):
    expected = expected_cutoff_data(dd, cutoff_name)
    for key in ("objective", "constant", "names", "lower", "upper", "types", "rhs", "sense", "row_names"):
        assert key in candidate, "NATIVE_ARRAY_MISSING:" + key
        same_array(expected[key], candidate[key], "native_" + key)
    assert np.count_nonzero(candidate["types"] == "B") == 9322
    return {key: array_sha(candidate[key]) for key in expected if key in candidate}


def classify_saved_result(result, replayed_counterexample=False):
    status = int(result["Status"])
    solutions = int(result.get("SolCount", 0))
    if replayed_counterexample:
        assert solutions > 0 and status not in (3, 4), "CONTRADICTORY_SOLVER_RESULT"
        return "FEASIBLE_COUNTEREXAMPLE"
    if status == 3:
        assert solutions == 0, "INFEASIBLE_WITH_INCUMBENT"
        return "SOLVER_NUMERICAL_INFEASIBLE_NOT_EXACT"
    return "NOT_PROVEN"


def independent_physical_reader():
    # Reuse only the frozen validator/inverse authority, not current producers.
    sys.path.insert(0, str(ROOT))
    path = ROOT / "docs/v42_m1_gap_rootcause_20261007/common.py"
    spec = importlib.util.spec_from_file_location("independent_cutoff_historical_reader", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    import v42_bootstrap.m1 as native
    original = native.native_inputs
    route = ROOT / "docs/v42_m1_group_branching_20261008/artifacts/source_authority/ROUTE_TABLE.json.gz"
    expected = "3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9"
    def relocated(bundle):
        assert sha(route) == bundle["route_table"]["sha256"] == expected
        copy = dict(bundle)
        copy["route_table"] = dict(bundle["route_table"], path=str(route))
        return original(copy)
    native.native_inputs = relocated
    return module.physical_reader()


def replay(A, d, T, dd, x, reader, require_cutoff):
    x = np.asarray(x)
    assert x.dtype == np.dtype("float64") and x.shape == (306040,), "WRONG_PRIMAL_AXIS"
    residual = A @ x - d["rhs"]
    violation = np.where(d["sense"] == "=", np.abs(residual), np.where(d["sense"] == "<", residual, -residual))
    bound = max(float(np.max(d["lower"] - x, initial=0)), float(np.max(x - d["upper"], initial=0)))
    integers = d["types"] != "C"
    integer = float(np.max(np.abs(x[integers] - np.rint(x[integers])), initial=0))
    row = float(np.max(violation, initial=0))
    b2 = float(np.max(T @ x - dd["rhs"][-651:], initial=0))
    prepass = bool(np.isfinite(x).all() and row <= 1e-8 and bound <= 1e-8 and integer <= 1e-8 and b2 <= 1e-8)
    physical = reader.check(x, A, d) if prepass else None
    cutoff = bool(float(x[RHO]) <= CUTOFF)
    passed = bool(prepass and physical and physical["PASS"] and (cutoff or not require_cutoff))
    return dict(PASS=passed, finite=bool(np.isfinite(x).all()), max_constraint_violation=row,
                max_bound_violation=bound, max_integrality_violation=integer,
                maximum_B2_violation=b2, rho=float(x[RHO]), cutoff_satisfied_without_tolerance=cutoff,
                full_frozen_physical_replay=physical, raw_vector_unchanged=True,
                independent_original_sparse_row_replay=True, scientific_tolerance=1e-8)


def tamper_tests(dd):
    expected = expected_cutoff_data(dd)
    rejected = []
    for key, index, value in (("types", 0, "C" if dd["types"][0] == "B" else "B"),
                              ("objective", RHO, 0.0), ("rhs", -1, 0.61)):
        bad = dict(expected)
        bad[key] = bad[key].copy()
        bad[key][index] = value
        try:
            check_native_arrays(dd, bad)
        except AssertionError as error:
            rejected.append(dict(mutation=key, rejected=True, reason=str(error)))
        else:
            raise AssertionError("TAMPER_ACCEPTED:" + key)
    classification = classify_saved_result(dict(Status=9, SolCount=0))
    assert classification == "NOT_PROVEN"
    assert classify_saved_result(dict(Status=4, SolCount=0)) == "NOT_PROVEN"
    assert classify_saved_result(dict(Status=3, SolCount=0)) != "INFEASIBILITY_CERTIFIED"
    return dict(PASS=True, rejected_mutations=rejected,
                TIME_LIMIT_no_incumbent=classification, INF_OR_UNBD="NOT_PROVEN",
                numerical_INFEASIBLE_never_exact_certificate=True)


def check_identity_receipt(receipt, A, T, dd, native_hashes):
    required = dict(rows=583460, columns=306040, nnz=5352915, binaries=9322, model_sense=1)
    for key, value in required.items():
        assert receipt[key] == value, "NATIVE_MODEL_COUNT_OR_SENSE_CHANGED:" + key
    for key, expected in (("source_CSR_SHA256", csr_sha(A)), ("native_original_CSR_SHA256", csr_sha(A)),
                          ("B2_CSR_SHA256", csr_sha(T)), ("native_B2_CSR_SHA256", csr_sha(T))):
        assert receipt[key] == expected, "NATIVE_CSR_RECEIPT_CHANGED:" + key
    cutoff = receipt["cutoff"]
    assert cutoff["column"] == RHO and cutoff["coefficient"] == 1.0 and cutoff["nnz"] == 1
    assert cutoff["sense"] == "<"
    same_array(np.asarray(CUTOFF), np.asarray(cutoff["rhs"]), "cutoff_rhs")
    for key, value in receipt.get("native_array_hashes", {}).items():
        assert native_hashes[key] == value, "NATIVE_RECEIPT_ARRAY_HASH_CHANGED:" + key
    return dict(PASS=True, expected_native_counts=required,
                native_CSR_receipts_match_independent_source=True,
                saved_native_arrays_bit_identical=True,
                cutoff_column=RHO, cutoff_rhs_binary64_hex=np.float64(CUTOFF).tobytes().hex())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    import gurobipy as gp
    def forbidden(*unused, **also_unused):
        raise AssertionError("INDEPENDENT_CHECKER_NATIVE_OPTIMIZE_FORBIDDEN")
    gp.Model.optimize = forbidden
    begin = time.perf_counter()
    assert subprocess.check_output(["git", "merge-base", BASE, "HEAD"], cwd=ROOT, text=True).strip() == BASE
    A, d, T, AA, dd, sources = load_sources()
    source_receipt = read(OUT / "SOURCE_IDENTITY.json")
    assert source_receipt["PASS"] and source_receipt["source_HEAD"] == BASE
    for key, value in sources.items():
        assert source_receipt["sources"][key]["sha256"] == value["sha256"]
    for key, expected in source_receipt["original_arrays_SHA256"].items():
        assert array_sha(d[key]) == expected, "SOURCE_RECEIPT_ARRAY_HASH_CHANGED:" + key
    tests = tamper_tests(dd)
    reader = independent_physical_reader()
    baseline_path = ROOT / "docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz"
    with np.load(baseline_path, allow_pickle=False) as archive:
        baseline = replay(A, d, T, dd, archive["x"].copy(), reader, False)
    assert baseline["PASS"] and baseline["rho"] == 0.6284141956452488, "BASELINE_UB_REPLAY_FAILED"
    result = dict(PASS=True, exact_base=BASE, source_archives=sources,
                  original_counts=dict(rows=A.shape[0], columns=A.shape[1], nnz=A.nnz, binaries=9322),
                  B2_counts=dict(rows=T.shape[0], columns=T.shape[1], nnz=T.nnz),
                  source_objective_SHA256=hashlib.sha256(d["objective"].tobytes() + d["constant"].tobytes()).hexdigest(),
                  baseline_UB_replay=baseline, tamper_tests=tests, native_optimize_calls=0,
                  independent_of_new_source_and_cutoff_producers=True)
    if not args.source_only:
        receipt = read(OUT / "MODEL_IDENTITY.json")
        name = receipt["cutoff"].get("name", "rho_cutoff_0p60")
        with np.load(OUT / "MODEL_IDENTITY.npz", allow_pickle=False) as archive:
            native = {key: archive[key].copy() for key in archive.files}
        hashes = check_native_arrays(dd, native, name)
        result["native_model_identity"] = check_identity_receipt(receipt, A, T, dd, hashes)
        saved = read(OUT / "ORIGINAL_CUTOFF_RESULT.json")
        assert not saved.get("callback_errors", []), "UNRESOLVED_CALLBACK_ERROR"
        paths = [item["path"] if isinstance(item, dict) else item for item in saved.get("incumbent_paths", [])]
        if saved.get("incumbent_path"):
            paths.append(saved["incumbent_path"])
        checked = []
        for value in dict.fromkeys(paths):
            path = Path(value)
            if not path.is_absolute():
                path = OUT / path
            assert path.resolve().is_relative_to(OUT.resolve()), "INCUMBENT_OUTSIDE_NEW_NAMESPACE"
            with np.load(path, allow_pickle=False) as archive:
                checked.append(dict(path=str(path), sha256=sha(path),
                                    replay=replay(A, d, T, dd, archive["x"].copy(), reader, True)))
        success = any(item["replay"]["PASS"] for item in checked)
        result.update(saved_Status=int(saved["Status"]), saved_SolCount=int(saved.get("SolCount", 0)),
                      incumbent_replays=checked, classification=classify_saved_result(saved, success),
                      exact_global_infeasibility_proven=False,
                      solver_status_is_numerical_evidence_only=True)
    result["controller_wall_seconds"] = time.perf_counter() - begin
    write(OUT / ("INDEPENDENT_SOURCE_CHECK.json" if args.source_only else "INDEPENDENT_SOURCE_CUTOFF_CHECK.json"), result)
    print(json.dumps({key: result[key] for key in ("PASS", "native_optimize_calls", "controller_wall_seconds")}), flush=True)


if __name__ == "__main__":
    main()
