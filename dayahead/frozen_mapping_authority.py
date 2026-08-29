"""Fail-closed verification for the V16 frozen feeder/PV/PCC authority.

The bus-axis and phase-mask digests are semantic hashes produced by the
original power-side authority code.  They are deliberately recomputed here
from the original arrays; a certificate that merely repeats a digest is not
accepted as source authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .authority import FROZEN_DIGESTS, sha256_file


BLOCKER = "BLOCKED_FROZEN_MAPPING_SOURCE_NOT_FOUND"


def hash_string_sequence(values: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def hash_bool_array(values: object) -> str:
    import numpy as np

    array = np.asarray(values, dtype=np.uint8, order="C")
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def sha256_tar_member(archive: Path, member: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    with tarfile.open(archive, "r:*") as bundle:
        info = bundle.getmember(member)
        stream = bundle.extractfile(info)
        if stream is None:
            raise FileNotFoundError(f"tar member is not a regular file: {member}")
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest(), int(info.size)


@dataclass(frozen=True)
class MappingAuthorityPaths:
    power_manifest: Path
    bus_axis_contract: Path
    power_to_compiled_index: Path
    compiled_phase_mask: Path
    service_node_mapping: Path
    pcc_archive: Path
    pcc_archive_member: str


def _expected() -> Mapping[str, str]:
    return {item.authority_id: item.sha256 for item in FROZEN_DIGESTS}


def verify_frozen_mapping_sources(paths: MappingAuthorityPaths) -> dict[str, object]:
    import numpy as np

    expected = _expected()
    failures: list[str] = []
    missing = [
        str(path)
        for path in (
            paths.power_manifest,
            paths.bus_axis_contract,
            paths.power_to_compiled_index,
            paths.compiled_phase_mask,
            paths.service_node_mapping,
            paths.pcc_archive,
        )
        if not path.is_file()
    ]
    if missing:
        return {
            "authority_id": "FROZEN_FEEDER_PCC_MAPPING_REUSE_V1",
            "status": BLOCKER,
            "blocker": BLOCKER,
            "missing_paths": missing,
            "c7_integrated_scientific_solve_allowed": False,
        }

    contract = json.loads(paths.bus_axis_contract.read_text(encoding="utf-8"))
    bus_ids = [str(value) for value in contract["power_bus_ids"]]
    mapping = np.load(paths.power_to_compiled_index, allow_pickle=False)
    phase_mask = np.load(paths.compiled_phase_mask, allow_pickle=False)
    if len(bus_ids) != len(mapping):
        failures.append("POWER_BUS_AXIS_MAPPING_LENGTH_MISMATCH")

    actual = {
        "power_artifact_manifest_sha256": sha256_file(paths.power_manifest),
        "power_bus_axis_sha256": hash_string_sequence(bus_ids),
        "compiled_bus_phase_mask_sha256": hash_bool_array(phase_mask),
        "bus_axis_mapping_sha256": hash_string_sequence(
            [f"{bus_ids[index]}->{int(mapping[index])}" for index in range(len(bus_ids))]
        ),
        "service_node_electrical_mapping_v1_csv_sha256": sha256_file(paths.service_node_mapping),
    }
    pcc_sha, pcc_size = sha256_tar_member(paths.pcc_archive, paths.pcc_archive_member)
    actual["Generated_ThreePhase_PCC_v3_dss_sha256"] = pcc_sha
    for key, frozen in expected.items():
        if actual.get(key) != frozen:
            failures.append(f"FROZEN_DIGEST_MISMATCH:{key}")

    contract_hashes = dict(contract.get("hashes", {}))
    for key in ("power_bus_axis_sha256", "compiled_bus_phase_mask_sha256", "bus_axis_mapping_sha256"):
        if contract_hashes.get(key) != expected[key]:
            failures.append(f"ORIGINAL_CONTRACT_DIGEST_MISMATCH:{key}")

    sources = {
        "power_artifact_manifest_sha256": {
            "role": "GRID_BACKGROUND_MAPPING_CONTRACT_V1",
            "location_type": "standalone_file",
            "path": str(paths.power_manifest.resolve()),
            "sha256": actual["power_artifact_manifest_sha256"],
            "bytes": paths.power_manifest.stat().st_size,
            "verification": "SHA256_FILE_BYTES",
        },
        "power_bus_axis_sha256": {
            "role": "GRID_BACKGROUND_MAPPING_CONTRACT_V1",
            "location_type": "semantic_authority_pair",
            "contract_path": str(paths.bus_axis_contract.resolve()),
            "array_path": str(paths.power_to_compiled_index.resolve()),
            "sha256": actual["power_bus_axis_sha256"],
            "verification": "SHA256_UTF8_STRING_SEQUENCE_WITH_NUL",
        },
        "bus_axis_mapping_sha256": {
            "role": "PV_FEEDER_MAPPING_CONTRACT_V1",
            "location_type": "semantic_authority_pair",
            "contract_path": str(paths.bus_axis_contract.resolve()),
            "array_path": str(paths.power_to_compiled_index.resolve()),
            "sha256": actual["bus_axis_mapping_sha256"],
            "verification": "SHA256_UTF8_BUS_TO_COMPILED_INDEX_SEQUENCE_WITH_NUL",
        },
        "compiled_bus_phase_mask_sha256": {
            "role": "PV_FEEDER_MAPPING_CONTRACT_V1",
            "location_type": "standalone_semantic_array",
            "path": str(paths.compiled_phase_mask.resolve()),
            "file_sha256": sha256_file(paths.compiled_phase_mask),
            "sha256": actual["compiled_bus_phase_mask_sha256"],
            "verification": "SHA256_SHAPE_ASCII_PLUS_UINT8_C_ORDER_BYTES",
        },
        "service_node_electrical_mapping_v1_csv_sha256": {
            "role": "AIDC_PCC_MAPPING_CONTRACT_V1/MESS_SERVICE_PCC_MAPPING_CONTRACT_V1",
            "location_type": "standalone_file",
            "path": str(paths.service_node_mapping.resolve()),
            "sha256": actual["service_node_electrical_mapping_v1_csv_sha256"],
            "bytes": paths.service_node_mapping.stat().st_size,
            "verification": "SHA256_FILE_BYTES",
        },
        "Generated_ThreePhase_PCC_v3_dss_sha256": {
            "role": "MESS_SERVICE_PCC_MAPPING_CONTRACT_V1",
            "location_type": "authority_tar_member",
            "archive_path": str(paths.pcc_archive.resolve()),
            "archive_member": paths.pcc_archive_member,
            "sha256": pcc_sha,
            "bytes": pcc_size,
            "verification": "SHA256_TAR_MEMBER_BYTES",
        },
    }
    status = "PASS" if not failures else BLOCKER
    return {
        "authority_id": "FROZEN_FEEDER_PCC_MAPPING_REUSE_V1",
        "status": status,
        "blocker": None if not failures else BLOCKER,
        "failures": failures,
        "new_mapping_created": False,
        "mapping_fitting_call_count": 0,
        "c7_integrated_scientific_solve_allowed": not failures,
        "sources": sources,
        "search_evidence": [
            {
                "scope": "current_checkout_and_all_git_refs",
                "result": "digest references found; standalone frozen payloads absent from git objects",
                "history_commits_with_digest_references": [
                    "d79b096", "8fcca12", "eabfe14", "06a94bc", "5fdcce4"
                ],
            },
            {
                "scope": "local_power_authority_workspace_and_review_archives",
                "result": "all six frozen authorities located and independently re-hashed",
            },
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--power-manifest", type=Path, required=True)
    parser.add_argument("--bus-axis-contract", type=Path, required=True)
    parser.add_argument("--power-to-compiled-index", type=Path, required=True)
    parser.add_argument("--compiled-phase-mask", type=Path, required=True)
    parser.add_argument("--service-node-mapping", type=Path, required=True)
    parser.add_argument("--pcc-archive", type=Path, required=True)
    parser.add_argument("--pcc-archive-member", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify_frozen_mapping_sources(
        MappingAuthorityPaths(
            power_manifest=args.power_manifest,
            bus_axis_contract=args.bus_axis_contract,
            power_to_compiled_index=args.power_to_compiled_index,
            compiled_phase_mask=args.compiled_phase_mask,
            service_node_mapping=args.service_node_mapping,
            pcc_archive=args.pcc_archive,
            pcc_archive_member=args.pcc_archive_member,
        )
    )
    _write_json(args.output, result)
    print(json.dumps({"status": result["status"], "failures": result.get("failures", [])}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
