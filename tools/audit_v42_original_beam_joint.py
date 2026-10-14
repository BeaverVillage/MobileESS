"""Native0 audit of one immutable PR221 original 4x24 Adaptive Joint pool.

All large packets are extracted into ignored runtime/. The audit neither
optimizes nor changes an incumbent registry or any historical artifact.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration.m_engine import _write, file_record, matrix_sha, domain_sha, vector_sha
from v42_integration.mess_joint_compression import compress_joint_packet, pool_sha, replay_same_pool_rows

PR221 = "a874df15b9a306a7d769a60622b40fb76de3ffcc"
SOURCE = "docs/v42_b2_adaptive_perf_v3/packages/INITIAL_1001/DIRECT"
NAMES = ("SPEC.json", "EXACT_INTEGER_AND_ROW_EQUIVALENCE.json", "A.npz", "DATA.npz", "LIFT.npz", "START.npz")


def extract(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in NAMES:
        ref = PR221 + ":" + SOURCE + "/" + name
        raw = subprocess.check_output(["git", "show", ref], cwd=ROOT)
        path = runtime / name
        if not path.exists() or path.read_bytes() != raw:
            path.write_bytes(raw)
        files[name] = dict(git_ref=ref, **file_record(path))
    return files


def load_packet(runtime):
    spec = json.loads((runtime / "SPEC.json").read_text(encoding="utf8"))
    proof = json.loads((runtime / "EXACT_INTEGER_AND_ROW_EQUIVALENCE.json").read_text(encoding="utf8"))
    for name in ("A", "DATA", "LIFT", "START"):
        if file_record(runtime / (name + ".npz"))["sha256"] != spec["packets"][name]["sha256"]:
            raise ValueError("ORIGINAL_PR221_GIT_PACKET_SHA_DRIFT:" + name)
    A, lift = sparse.load_npz(runtime / "A.npz").tocsr(), sparse.load_npz(runtime / "LIFT.npz").tocsr()
    with np.load(runtime / "DATA.npz", allow_pickle=False) as z:
        d = {k: z[k].copy() for k in z.files}
    with np.load(runtime / "START.npz", allow_pickle=False) as z:
        start = z["point"].copy()
    proof["lambda_axis"] = spec["lambda_axis"]
    proof["keep_columns"] = spec["keep_columns"]
    proof["removed_route_columns"] = spec["removed_route_columns"]
    units = {a["unit"] for a in spec["lambda_axis"]}
    if units != {"MESS01", "MESS02", "MESS03", "MESS04"} or units != set(spec["pools"]):
        raise ValueError("ORIGINAL_PR221_FOUR_UNIT_SOURCE_SCOPE_REQUIRED")
    if len(spec["lambda_axis"]) != spec["lambda_count"] or len(start) != spec["compact_columns"]:
        raise ValueError("ORIGINAL_PR221_LAMBDA_AND_COLUMN_SCOPE_DRIFT")
    for entry in spec["lambda_axis"]:
        if entry["path"] != spec["pools"][entry["unit"]][entry["ordinal"]]:
            raise ValueError("ORIGINAL_PR221_POOL_AND_LAMBDA_PATH_DRIFT")
    return (A, d, lift, start, proof), spec


def load_compressed_packet(runtime):
    folder = Path(runtime) / "COMPRESSED"
    A, lift = sparse.load_npz(folder / "A.npz").tocsr(), sparse.load_npz(folder / "LIFT.npz").tocsr()
    with np.load(folder / "DATA.npz", allow_pickle=False) as z:
        d = {k:z[k].copy() for k in z.files}
    with np.load(folder / "START.npz", allow_pickle=False) as z:
        start = z["point"].copy()
    proof = json.loads((folder / "PROOF.json").read_text(encoding="utf8"))
    receipt = proof["exact_joint_grid_compression"]
    if receipt.get("compressed_matrix_sha") and (receipt["compressed_matrix_sha"] != matrix_sha(A) or
            receipt["compressed_domain_sha"] != domain_sha(d)):
        raise ValueError("ORIGINAL_PR221_COMPRESSED_PACKET_BYTES_DRIFT")
    if receipt["identity"]["lift_sha"] != matrix_sha(lift) or receipt["identity"]["start_sha"] != vector_sha(start):
        raise ValueError("ORIGINAL_PR221_COMPRESSED_LIFT_START_DRIFT")
    return A, d, lift, start, proof


def full_raw_replay(output, runtime):
    """Fresh original FULL validation; no native model or solve is created."""
    from v42_integration.pr222_regression import load_case
    from v42_integration.m_engine import strict_full, PathGraph
    packet, spec = load_packet(runtime / "ORIGINAL")
    original, d, lift, start, proof = packet
    dense = np.asarray(lift @ start).ravel()
    del packet, original, d, lift, start
    case = load_case("2025-05-01", output / "ORIGINAL_BEAM_FULL_REPLAY")
    sites, initial, arcs = case.graph[:3]
    if len(sites) != 24 or len(initial) != 4 or max(a[3] for a in arcs) != 96:
        raise ValueError("ORIGINAL_PR221_SOURCE_GRAPH_4X24_FULL96_REQUIRED")
    if dense.shape != (case.A.shape[1],):
        raise ValueError("ORIGINAL_PR221_RAW_LIFT_SOURCE_AXIS_DRIFT")
    path = output / "ORIGINAL_BEAM_FULL_REPLAY/ORIGINAL_CENTER_DENSE_RAW.npz"
    np.savez_compressed(path, point=dense)
    cert = strict_full(case, path)
    graph = PathGraph(case)
    result = dict(status="PASS", PASS=True, Native_optimize_calls=0,
        current_metadata_case_sha=case.case_sha, exact_original_metadata_case_sha=spec["case_sha"],
        metadata_case_sha_equal=case.case_sha == spec["case_sha"],
        provenance_scope="PR221_HISTORICAL_EXACT_NUMERIC_CASE_REPRODUCTION_ONLY",
        old_source_git=spec["source_sha"], original_center_dense_sha=vector_sha(dense),
        old_center_dense_sha=spec["center_vector_SHA"], center_raw_sha_matches=vector_sha(dense)==spec["center_vector_SHA"],
        graph_counts=dict(MESS_count=len(initial), candidate_nodes=len(sites), slots=graph.horizon),
        Original_FULL_raw_replay=cert, center_is_moving=graph.moving(dense),
        center_is_protected_PR220_winner=vector_sha(dense)=="f717de66ee0ad06aadd6c09baa1a3667d775b045bceb4305510ce0db184f8776",
        source_matrix_sha=matrix_sha(case.A), source_domain_sha=domain_sha(case.d),
        original_FULL_matrix_sha=matrix_sha(case.original_A), original_FULL_domain_sha=domain_sha(case.original_d),
        original_center_objective=cert["Global_UB"], numeric_repair=False,
        incumbent_registry_mutations=0, Source_Case_not_rebound_to_latest_AIDC=True)
    _write(output / "ORIGINAL_BEAM_FULL_RAW_REPLAY.json", result)
    return result


def native0_readback(output, runtime):
    """Sequential original/compressed real native attribute verification only."""
    from types import SimpleNamespace
    from v42_integration.m_engine import _native_joint
    from v42_common_mess.model import memory_observation
    before = memory_observation()
    if before["RAM_available"] < 8*1024**3:
        raise RuntimeError("ORIGINAL_4X24_NATIVE0_8GB_RAM_GATE")
    original, _ = load_packet(runtime / "ORIGINAL")
    compressed = load_compressed_packet(runtime)
    variants = []
    for name, packet in (("ORIGINAL", original), ("COMPRESSED", compressed)):
        began = perf_counter()
        result, captures = _native_joint(SimpleNamespace(), None, packet,
            output / "ORIGINAL_BEAM_NATIVE0_READBACK" / name, 20., native0=True)
        variants.append(dict(variant=name, status="PASS", wall_seconds=perf_counter()-began,
            result=result, captures=len(captures), after_memory=memory_observation()))
    result = dict(status="PASS", Native_optimize_calls=0, Presolve_calls=0,
        worker=1, threads=1, sequential=True, before_memory=before, variants=variants,
        scope="ORIGINAL_AND_EXACT_COMPRESSED_SAME_RESTRICTED_FOUR_MESS_POOL_NATIVE_ATTRIBUTES_ONLY")
    _write(output / "ORIGINAL_BEAM_NATIVE0_READBACK.json", result)
    return result


def audit(output, runtime, *, reuse=False):
    began = perf_counter()
    source_files = extract(runtime / "ORIGINAL")
    packet, spec = load_packet(runtime / "ORIGINAL")
    A, d, lift, start, proof = packet
    # Source18r used a Git commit identifier; the compression cache stores a
    # 64-character provenance digest while retaining its literal Git identity.
    authority = dict(source_git=spec["source_sha"], original_case=spec["case_sha"],
        original_route_lift_proof=source_files["EXACT_INTEGER_AND_ROW_EQUIVALENCE.json"]["sha256"],
        source_matrix_sha=proof.get("source_matrix_SHA", proof.get("source_matrix_sha")),
        complete_original_physical_rows_retained=proof.get("original_source_CSR_RHS_Sense_Bounds_Objective_preserved"),
        original_charge_modes_free=proof.get("retained_384_charge_modes_free"))
    identity = dict(source_sha=sha256(spec["source_sha"].encode()).hexdigest(),
        case_sha=spec["case_sha"], physical_sha=sha256(json.dumps(authority, sort_keys=True).encode()).hexdigest(),
        pool_sha=pool_sha(spec["pools"]))
    compressed = compress_joint_packet(packet, identity=identity, cache_dir=runtime / "CACHE", output=output)
    receipt = compressed[-1]["exact_joint_grid_compression"]
    raw = replay_same_pool_rows(packet, compressed, start)
    folder = runtime / "COMPRESSED"
    folder.mkdir(parents=True, exist_ok=True)
    sparse.save_npz(folder / "A.npz", compressed[0])
    sparse.save_npz(folder / "LIFT.npz", compressed[2])
    np.savez_compressed(folder / "DATA.npz", **compressed[1])
    np.savez_compressed(folder / "START.npz", point=compressed[3])
    _write(folder / "PROOF.json", compressed[4])
    result = dict(schema="ORIGINAL_4X24_SAME_POOL_COMPRESSION_AUDIT_V1", status="PASS" if raw["PASS"] else "FAIL",
        original_PR221_git=PR221, fixed_original_pool="INITIAL_1001/DIRECT", slots=96, physical_vehicles=4,
        candidate_nodes=24, pool_counts={u:len(p) for u,p in spec["pools"].items()},
        exact_original_source_files=source_files, physical_authority=authority, compression=receipt,
        original_joint_start_raw_replay=raw,
        original_full_raw_replay="NOT_RUN_USE_SEPARATE_SAME_SOURCE_CASE_VALIDATOR",
        original_START_center_vector_sha=spec["center_vector_SHA"],
        original_CENTER_is_protected_PR220_winner=spec["center_vector_SHA"] == "f717de66ee0ad06aadd6c09baa1a3667d775b045bceb4305510ce0db184f8776",
        protected_PR220_moving_incumbent_UB=0.5398310226338695,
        incumbent_registry_mutations=0, prior_incumbent_never_replaced=True,
        model_vars=A.shape[1], binary=int(np.count_nonzero(d["types"]=="B")),
        original_rows=A.shape[0], compressed_rows=compressed[0].shape[0], original_NNZ=A.nnz, compressed_NNZ=compressed[0].nnz,
        raw_lift_SHA=matrix_sha(lift), raw_START_sha=vector_sha(start), identity=identity,
        model_packet_materialization_and_audit_wall_seconds=perf_counter()-began,
        Gurobi_model_build="NOT_RUN", Native_optimize_calls=0, solver_speedup="NOT_RUN",
        total_beam_iteration_speedup="NOT_CERTIFIED", original_LP_domain_equivalence_scope="SAME_RESTRICTED_DIRECT_JOINT_PACKET",
        Original_FULL_domain_equivalence_claimed=False, experimental_compression=True,
        runtime_packets_are_local_ignored=True, compressed_runtime_packet=str(folder.resolve()))
    _write(output / "ORIGINAL_BEAM_JOINT_COMPRESSION_AUDIT.json", result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=ROOT / "docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP")
    p.add_argument("--runtime", type=Path, default=ROOT / "runtime/FOLLOWUP_ORIGINAL_BEAM_JOINT")
    p.add_argument("--full-raw-replay", action="store_true")
    p.add_argument("--native0-readback", action="store_true")
    args = p.parse_args()
    if args.native0_readback:
        result = native0_readback(args.output, args.runtime)
        print(json.dumps(dict(status=result["status"], Native_optimize_calls=0,
            build_wall_seconds={v["variant"]:v["wall_seconds"] for v in result["variants"]})))
    elif args.full_raw_replay:
        result = full_raw_replay(args.output, args.runtime)
        print(json.dumps({k:result[k] for k in ("status", "center_is_moving", "center_raw_sha_matches", "Native_optimize_calls", "original_center_objective")}))
    else:
        result = audit(args.output, args.runtime)
        print(json.dumps({k:result[k] for k in ("status", "original_rows", "compressed_rows", "original_NNZ", "compressed_NNZ", "Native_optimize_calls", "model_packet_materialization_and_audit_wall_seconds")}))


if __name__ == "__main__":
    main()
