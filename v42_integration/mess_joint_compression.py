"""Opt-in exact grid-row compression of the existing four-MESS Joint packet.

The packet's route pool, variables, binary types, objective, literal Start and
raw lift are unchanged. The continuous-domain theorem is for the SAME supplied
Joint packet; it does not equate a restricted route pool with Original FULL.
No solver is imported and no numeric bound is transferred between cases.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .m_engine import _write, domain_sha, file_record, matrix_sha, vector_sha
from .mess_scaling import (compress_native_grid_rows, verify_native_grid_compression,
                          _csr_box_support_vectorized_exact)

VERSION = "SAME_POOL_JOINT_GRID_EXACT_V2_EQUALITY_SUPPORT"
GRID_FAMILIES = frozenset(("voltage_lower", "voltage_upper", "transformer_current",
    "transformer_kVA", "line_thermal_face", "NormalAmps"))
IDENTITY_FIELDS = ("source_sha", "case_sha", "physical_sha", "pool_sha")


def pool_sha(pools):
    """Include route order: it controls lambda columns and the literal Start."""
    payload = {str(u): [list(map(int, p)) for p in paths]
               for u, paths in sorted(pools.items())}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _identity(packet, identity):
    A, d, lift, start, proof = packet
    if not proof.get("PASS") or not proof.get("restricted_to_FULL_inclusion"):
        raise ValueError("MESS_JOINT_ORIGINAL_ROUTE_LIFT_PROOF_REQUIRED")
    if not A.has_canonical_format or A.dtype != np.dtype("float64"):
        raise ValueError("MESS_JOINT_CANONICAL_EXACT_CSR_REQUIRED")
    for name in IDENTITY_FIELDS:
        value = identity.get(name)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("MESS_JOINT_SOURCE_CASE_PHYSICAL_POOL_SHA_REQUIRED:" + name)
    if len(start) != A.shape[1] or lift.shape[1] != A.shape[1]:
        raise ValueError("MESS_JOINT_START_LIFT_DIMENSION_DRIFT")
    return dict(version=VERSION, **{k: identity[k] for k in IDENTITY_FIELDS},
        matrix_sha=matrix_sha(A), domain_sha=domain_sha(d), lift_sha=matrix_sha(lift),
        proof_kernel_source_sha=file_record(__file__)["sha256"],
        box_support_kernel_source_sha=file_record(Path(__file__).with_name("mess_scaling.py"))["sha256"],
        start_sha=vector_sha(start), route_proof_sha=sha256(json.dumps(
            proof, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())


def implied_helper_bounds(A, d, *, rounds=8):
    """Outward bounds implied by retained literal helper equalities.

    For every +1 helper pivot z and equality z + a*x = b, derive
    b - max(a*x) <= z <= b + max(-a*x). Each maximum is outward
    rounded over a box already known to contain the ORIGINAL LP domain.
    Bounds are proof witnesses only and never installed on solver variables.
    Synchronous rounds are valid even when helper dependencies have cycles.
    """
    named = list(map(str, d["names"]))
    rows, pivots, pivot_set = [], [], set()
    for i, name in enumerate(map(str, d["row_names"])):
        family = name.split("[", 1)[0]
        if not family.endswith("_binding"):
            continue
        if d["sense"][i] != "=":
            raise ValueError("MESS_JOINT_HELPER_BINDING_MUST_REMAIN_EQUALITY")
        a, b = A.indptr[i:i+2]
        pivot = [j for j, v in zip(A.indices[a:b], A.data[a:b])
                 if v == 1. and named[j].split("[", 1)[0] + "_binding" == family]
        if len(pivot) != 1 or pivot[0] in pivot_set:
            raise ValueError("MESS_JOINT_HELPER_PIVOT_AUTHORITY_AMBIGUOUS")
        rows.append(i); pivots.append(pivot[0]); pivot_set.add(pivot[0])
    lower, upper = np.asarray(d["lower"]).copy(), np.asarray(d["upper"]).copy()
    # Direct substitution leaves physical connection inequalities intact.
    # A site absent from EVERY path of this pool may therefore have literal
    # Pch<=0/Pdis<=0 although its original global route-domain box was wider.
    # These witnesses come only from retained connection rows, never Grid rows.
    physical_rows, physical_pivots = [], []
    for i, name in enumerate(map(str, d["row_names"])):
        family = name.split("[", 1)[0]
        if family not in ("connected_Pch", "connected_Pdis"):
            continue
        expected = "Pch" if family == "connected_Pch" else "Pdis"
        a, b = A.indptr[i:i+2]
        pivot = [j for j, v in zip(A.indices[a:b], A.data[a:b])
                 if v == 1. and named[j].split("[", 1)[0] == expected]
        if d["sense"][i] != "<" or len(pivot) != 1:
            raise ValueError("MESS_JOINT_ORIGINAL_CONNECTION_PIVOT_DRIFT")
        physical_rows.append(i); physical_pivots.append(pivot[0])
    if physical_rows:
        P = A[physical_rows].tocsr()
        for i, j in enumerate(physical_pivots):
            a, b = P.indptr[i:i+2]
            P.data[a + np.flatnonzero(P.indices[a:b] == j)[0]] = 0.
        P.eliminate_zeros(); P.data *= -1.
        support = _csr_box_support_vectorized_exact(P, lower, upper, np.full(len(physical_rows), "<"))
        limits = np.nextafter(d["rhs"][physical_rows] + support, np.inf)
        upper[physical_pivots] = np.minimum(upper[physical_pivots], limits)
        if np.any(lower > upper):
            raise ValueError("MESS_JOINT_ORIGINAL_CONNECTION_DOMAIN_INFEASIBLE")
    if not rows:
        return lower, upper, dict(PASS=True, helper_equalities=0, rounds=[],
            bounds_are_installed_in_model=False, original_LP_domain_enclosed=True)
    rows, pivots = np.asarray(rows, dtype=np.int64), np.asarray(pivots, dtype=np.int64)
    B = A[rows].tocsr()
    for i, j in enumerate(pivots):
        a, b = B.indptr[i:i+2]
        B.data[a + np.flatnonzero(B.indices[a:b] == j)[0]] = 0.
    B.eliminate_zeros()
    negative = B.copy(); negative.data *= -1.
    sense = np.full(len(rows), "<")
    history = []
    for ordinal in range(rounds):
        positive_support = _csr_box_support_vectorized_exact(B, lower, upper, sense)
        negative_support = _csr_box_support_vectorized_exact(negative, lower, upper, sense)
        # An extra outward nextafter safely encloses addition/subtraction of
        # exact stored binary64 RHS with the outward support witness.
        lo = np.nextafter(d["rhs"][rows] - positive_support, -np.inf)
        hi = np.nextafter(d["rhs"][rows] + negative_support, np.inf)
        new_lo, new_hi = np.maximum(lower[pivots], lo), np.minimum(upper[pivots], hi)
        if np.any(new_lo > new_hi):
            raise ValueError("MESS_JOINT_ORIGINAL_HELPER_DOMAIN_INFEASIBLE")
        changed = np.count_nonzero(new_lo != lower[pivots]) + np.count_nonzero(new_hi != upper[pivots])
        lower[pivots], upper[pivots] = new_lo, new_hi
        history.append(dict(round=ordinal, changed_endpoints=int(changed),
            implied_box_sha=domain_sha(dict(lower=lower, upper=upper))))
        if changed == 0:
            break
    return lower, upper, dict(PASS=True, helper_equalities=len(rows), rounds=history,
        retained_connection_inequalities=len(physical_rows),
        physical_power_upper_endpoints_tightened=int(np.count_nonzero(upper[physical_pivots] < d["upper"][physical_pivots])),
        retained_helper_row_ids_sha=vector_sha(rows), retained_helper_pivot_ids_sha=vector_sha(pivots),
        original_bounds_sha=domain_sha(dict(lower=d["lower"], upper=d["upper"])),
        implied_bounds_sha=domain_sha(dict(lower=lower, upper=upper)),
        bounds_are_installed_in_model=False, original_LP_domain_enclosed=True,
        proof="Retained +1 power connection rows first imply outward upper bounds. Induction over synchronous helper rounds then uses each retained +1 equality and the previous enclosing box. Intersecting valid bounds remains valid for every Original integer and LP point. No grid row is used for bound inference and no source constraint or model variable bound is changed.")


def compress_joint_packet(packet, *, identity, cache_dir=None, output=None):
    """Return the existing five-item packet shape, retaining its exact raw lift.

    Cache entries bind every Source/Case/physical/pool and actual matrix/domain
    byte. On reuse, bytes AND each deletion theorem are checked again; cache
    restoration is never treated as new physical or solver certification.
    """
    begin = perf_counter()
    A, d, lift, start, source_proof = packet
    bound = _identity(packet, identity)
    key = sha256(json.dumps(bound, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ids = np.asarray([i for i, n in enumerate(map(str, d["row_names"]))
                      if n.split("[", 1)[0] in GRID_FAMILIES], dtype=np.int64)
    if not len(ids):
        raise ValueError("MESS_JOINT_ORIGINAL_GRID_ROW_NAMES_REQUIRED")
    bound_begin = perf_counter()
    lower, upper, helper_proof = implied_helper_bounds(A, d)
    helper_bound_seconds = perf_counter() - bound_begin
    block = A[ids].tocsr()
    cache = None if cache_dir is None else Path(cache_dir) / key
    hit = cache is not None and (cache / "MANIFEST.json").exists()
    proof_seconds = 0.
    restore_begin = perf_counter()
    if hit:
        manifest = json.loads((cache / "MANIFEST.json").read_text(encoding="utf8"))
        if manifest["identity"] != bound or manifest["cache_key"] != key:
            raise ValueError("MESS_JOINT_CACHE_AUTHORITY_DRIFT")
        actual = file_record(cache / "PROOF.npz")
        if actual["sha256"] != manifest["proof_file"]["sha256"] or actual["bytes"] != manifest["proof_file"]["bytes"]:
            raise ValueError("MESS_JOINT_CACHE_PROOF_BYTES_DRIFT")
        with np.load(cache / "PROOF.npz", allow_pickle=False) as z:
            row_proof = {k: z[k].copy() for k in ("keep", "reason", "representative", "support")}
        row_proof["certificate"] = manifest["certificate"]
    else:
        proof_begin = perf_counter()
        row_proof = compress_native_grid_rows(block, d["rhs"][ids], d["sense"][ids], lower, upper)
        proof_seconds = perf_counter() - proof_begin
    cache_restore_seconds = perf_counter() - restore_begin if hit else 0.
    verify_begin = perf_counter()
    theorem = verify_native_grid_compression(block, d["rhs"][ids], d["sense"][ids], lower, upper, row_proof)
    verify_seconds = perf_counter() - verify_begin
    cache_creation_seconds = 0.
    if cache is not None and not hit:
        create_begin = perf_counter()
        cache.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache / "PROOF.npz", **{k: row_proof[k] for k in ("keep", "reason", "representative", "support")})
        _write(cache / "MANIFEST.json", dict(identity=bound, cache_key=key,
            certificate=row_proof["certificate"], proof_file=file_record(cache / "PROOF.npz")))
        cache_creation_seconds = perf_counter() - create_begin
    deleted = ids[row_proof["reason"] != 0]
    mask = np.ones(A.shape[0], dtype=bool)
    mask[deleted] = False
    retained = np.flatnonzero(mask)
    compressed = A[retained].tocsr()
    cd = {k: np.asarray(v).copy() for k, v in d.items()}
    for k in ("rhs", "sense", "row_names"):
        cd[k] = cd[k][retained]
    proof = deepcopy(source_proof)
    receipt = dict(schema=VERSION, status="PASS", PASS=True, identity=bound, cache_key=key,
        cache_hit=hit, row_certificate=row_proof["certificate"], independently_verified=theorem,
        retained_helper_equality_support_proof=helper_proof,
        helper_bound_proof_seconds=helper_bound_seconds,
        original_joint_rows=A.shape[0], compressed_joint_rows=compressed.shape[0],
        original_joint_nonzeros=A.nnz, compressed_joint_nonzeros=compressed.nnz,
        original_matrix_sha=matrix_sha(A), original_domain_sha=domain_sha(d),
        compressed_matrix_sha=matrix_sha(compressed), compressed_domain_sha=domain_sha(cd),
        unchanged_columns=A.shape[1], unchanged_binary=int(np.count_nonzero(d["types"] == "B")),
        removed_grid_rows=len(deleted), non_grid_rows_removed=0,
        raw_lift_bit_identical=True, MIP_Start_bit_identical=True,
        objective_types_bounds_bit_identical=True,
        same_pool_integer_domain_equivalent=True, same_pool_LP_domain_equivalent=True,
        original_FULL_inclusion_inherited_from_source_packet=True,
        original_FULL_equals_restricted_joint_claimed=False, restricted_ObjBound_is_Global_LB=False,
        proof_seconds=proof_seconds, verification_seconds=verify_seconds,
        cache_creation_seconds=cache_creation_seconds, cache_reuse_seconds=cache_restore_seconds,
        compression_total_wall_seconds=perf_counter()-begin,
        Native_optimize_calls=0, solver_speedup="NOT_RUN", total_beam_iteration_speedup="NOT_CERTIFIED",
        experimental_default_disabled=True)
    proof["exact_joint_grid_compression"] = receipt
    if output is not None:
        _write(Path(output) / "JOINT_GRID_COMPRESSION_CERTIFICATE.json", receipt)
        np.savez_compressed(Path(output) / "JOINT_REMOVED_ROW_WITNESSES.npz", original_grid_ids=ids,
                            removed_original_rows=deleted, **{k: row_proof[k] for k in ("keep", "reason", "representative", "support")})
    return compressed, cd, lift, np.asarray(start).copy(), proof


def replay_same_pool_rows(packet, compressed_packet, point, *, tolerance=1e-8):
    """Inspect literal raw rows for integer OR fractional compact witnesses."""
    A, d, lift, _, _ = packet
    C, cd, clift, _, _ = compressed_packet
    x = np.asarray(point, dtype=np.float64)
    if x.shape != (A.shape[1],) or not np.isfinite(x).all():
        raise ValueError("MESS_JOINT_RAW_REPLAY_POINT_REQUIRED")
    if matrix_sha(lift) != matrix_sha(clift):
        raise ValueError("MESS_JOINT_RAW_LIFT_CHANGED")
    activity = np.asarray(A @ x).ravel() - d["rhs"]
    residual = np.where(d["sense"] == "<", np.maximum(activity, 0.),
        np.where(d["sense"] == ">", np.maximum(-activity, 0.), np.abs(activity)))
    box = max(0., float(np.max(d["lower"]-x)), float(np.max(x-d["upper"])))
    discrete = d["types"] != "C"
    integer_error = float(np.max(np.abs(x[discrete]-np.rint(x[discrete])))) if discrete.any() else 0.
    return dict(status="PASS" if max(float(residual.max()), box) <= tolerance else "FAIL",
        PASS=max(float(residual.max()), box) <= tolerance,
        original_joint_row_residual=float(residual.max()), original_bounds_residual=box,
        integer_residual=integer_error, witness_domain="INTEGER" if integer_error == 0. else "LP_FRACTIONAL",
        original_joint_objective=float(d["objective"] @ x + d["constant"]),
        compressed_joint_objective=float(cd["objective"] @ x + cd["constant"]),
        raw_lift_vector_sha=vector_sha(np.asarray(lift @ x).ravel()), numeric_repair=False,
        same_pool_row_theorem="ALL_DELETED_ROWS_PROVEN_OVER_ORIGINAL_LP_DOMAIN_ENCLOSED_BY_RETAINED_ROW_IMPLIED_BOX",
        Original_FULL_raw_replay="REQUIRES_SOURCE_CASE_VALIDATOR", Native_optimize_calls=0)
