"""Restore a completely certified SAME-pool packet under an external SHA seal.

First creation still executes the original independent row-deletion proof.
Reuse reads immutable packet bytes rather than repeating the proof kernel.
The approved manifest SHA must be supplied from a separate retained receipt.
This cache changes no solver parameter, route pool, objective, lift or Start.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from .m_engine import _write,file_record,matrix_sha,domain_sha,vector_sha
from .mess_joint_compression import _identity,pool_sha

VERSION="MESS_EXTERNALLY_SEALED_SAME_POOL_PACKET_V1"


def _actual_identity(packet, identity):
    # The existing full CSR/domain/lift/Start/source-proof digest is retained.
    bound=_identity(packet,identity)
    axis=packet[-1].get("lambda_axis")
    if axis:
        pools={}
        for entry in axis:
            paths=pools.setdefault(entry["unit"],[])
            if entry["ordinal"]!=len(paths):raise ValueError("MESS_SEALED_CACHE_LITERAL_LAMBDA_ORDER_REQUIRED")
            paths.append(entry["path"])
        if pool_sha(pools)!=identity["pool_sha"]:
            raise ValueError("MESS_SEALED_CACHE_POOL_SHA_DOES_NOT_DESCRIBE_ACTUAL_LAMBDA_PATHS")
    return bound


def seal_verified_packet(original, compressed, *, identity, folder):
    """Persist only an already independently certified exact five-item packet."""
    begin=perf_counter();folder=Path(folder)
    if (folder/"MANIFEST.json").exists():raise ValueError("MESS_SEALED_CACHE_CREATION_CANNOT_OVERWRITE_EXISTING_EVIDENCE")
    bound=_actual_identity(original,identity)
    A,d,lift,start,proof=compressed
    receipt=proof.get("exact_joint_grid_compression",{})
    if receipt.get("identity")!=bound or not receipt.get("independently_verified",{}).get("all_removed_rows_proven"):
        raise ValueError("MESS_SEALED_CACHE_INDEPENDENT_SAME_SOURCE_ROW_PROOF_REQUIRED")
    if receipt.get("compressed_matrix_sha")!=matrix_sha(A) or receipt.get("compressed_domain_sha")!=domain_sha(d):
        raise ValueError("MESS_SEALED_CACHE_COMPRESSED_MATRIX_DOMAIN_PROOF_DRIFT")
    if matrix_sha(lift)!=bound["lift_sha"] or vector_sha(start)!=bound["start_sha"]:
        raise ValueError("MESS_SEALED_CACHE_LIFT_OR_START_DRIFT")
    for key in ("names","lower","upper","types","objective","constant"):
        if not np.array_equal(d[key],original[1][key]):raise ValueError("MESS_SEALED_CACHE_ORIGINAL_COLUMN_DOMAIN_DRIFT:"+key)
    folder.mkdir(parents=True,exist_ok=True)
    sparse.save_npz(folder/"A.npz",A);sparse.save_npz(folder/"LIFT.npz",lift)
    np.savez_compressed(folder/"DATA.npz",**d);np.savez_compressed(folder/"START.npz",point=start)
    _write(folder/"PROOF.json",proof)
    files={name:file_record(folder/name) for name in ("A.npz","LIFT.npz","DATA.npz","START.npz","PROOF.json")}
    manifest=dict(schema=VERSION,status="PASS",identity=bound,files=files,
        output_matrix_sha=matrix_sha(A),output_domain_sha=domain_sha(d),
        output_lift_sha=matrix_sha(lift),output_start_sha=vector_sha(start),
        original_independent_proof=receipt,
        trust="External approved manifest SHA plus exact source/pool and all packet bytes; not an unsealed local cache.",
        compressed_equals_same_pool_integer_and_LP=True,Original_FULL_domain_equivalence_claimed=False,
        source_kernel_source=file_record(__file__),Native_optimize_calls=0)
    _write(folder/"MANIFEST.json",manifest)
    return dict(status="PASS",approved_manifest=file_record(folder/"MANIFEST.json"),
        first_seal_IO_and_hash_wall_seconds=perf_counter()-begin,
        initial_independent_proof_wall_seconds=receipt["compression_total_wall_seconds"],Native_optimize_calls=0)


def restore_verified_packet(original, *, identity, folder, approved_manifest_sha):
    """Refuse any source, pool, byte or external seal mismatch before restore."""
    begin=perf_counter();folder=Path(folder)
    if not isinstance(approved_manifest_sha,str) or len(approved_manifest_sha)!=64:
        raise ValueError("MESS_SEALED_CACHE_EXTERNAL_APPROVED_MANIFEST_SHA_REQUIRED")
    manifest_file=file_record(folder/"MANIFEST.json")
    if manifest_file["sha256"]!=approved_manifest_sha:
        raise ValueError("MESS_SEALED_CACHE_EXTERNAL_MANIFEST_SEAL_DRIFT")
    manifest=json.loads((folder/"MANIFEST.json").read_text(encoding="utf8"))
    if manifest.get("schema")!=VERSION or manifest.get("status")!="PASS":
        raise ValueError("MESS_SEALED_CACHE_APPROVED_SCHEMA_REQUIRED")
    if manifest["identity"]!=_actual_identity(original,identity):
        raise ValueError("MESS_SEALED_CACHE_SOURCE_CASE_PHYSICAL_POOL_OR_ACTUAL_DOMAIN_DRIFT")
    if set(manifest["files"])!={"A.npz","LIFT.npz","DATA.npz","START.npz","PROOF.json"}:
        raise ValueError("MESS_SEALED_CACHE_COMPLETE_PACKET_MEMBERS_REQUIRED")
    for name,receipt in manifest["files"].items():
        if name not in ("A.npz","LIFT.npz","DATA.npz","START.npz","PROOF.json"):
            raise ValueError("MESS_SEALED_CACHE_UNEXPECTED_PACKET_MEMBER")
        actual=file_record(folder/name)
        if any(actual[k]!=receipt[k] for k in ("sha256","bytes")):
            raise ValueError("MESS_SEALED_CACHE_PACKET_BYTES_DRIFT:"+name)
    A=sparse.load_npz(folder/"A.npz").tocsr();lift=sparse.load_npz(folder/"LIFT.npz").tocsr()
    with np.load(folder/"DATA.npz",allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    with np.load(folder/"START.npz",allow_pickle=False) as z:start=z["point"].copy()
    proof=json.loads((folder/"PROOF.json").read_text(encoding="utf8"))
    if matrix_sha(A)!=manifest["output_matrix_sha"] or domain_sha(d)!=manifest["output_domain_sha"] or (
            matrix_sha(lift)!=manifest["output_lift_sha"] or vector_sha(start)!=manifest["output_start_sha"]):
        raise ValueError("MESS_SEALED_CACHE_RESTORED_NUMERIC_DOMAIN_DRIFT")
    return (A,d,lift,start,proof),dict(status="PASS",cache_reuse_wall_seconds=perf_counter()-begin,
        approved_manifest=manifest_file,original_independent_proof_repeated=False,
        exact_certified_packet_restored=True,new_pool_proof_reused=False,Source_Case_scope=manifest["identity"],
        Native_optimize_calls=0,solver_speedup="NOT_RUN",total_Beam_iteration_speedup="NOT_CERTIFIED",
        experimental_default_disabled=True)
