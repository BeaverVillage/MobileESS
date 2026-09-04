"""V17 V3R2 Eagle/Kestrel fail-closed forensic helpers.

The downloaded Eagle roots are immutable authorities.  This module permits
archive streaming and Eagle-internal node/time joins, but deliberately exposes
no operation that can merge Eagle rows with Kestrel rows or transfer Eagle
absolute kW to the H100 authority.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable


REQUIRED_HEAD = "d20141f41b145d1585f2bb92b109220dbc299407"
EAGLE_NODES = ("r103u17", "r103u21", "r104u29", "r104u33", "r105u09", "r105u15")

GANGLIA_NAME = "esif.hpc.eagle.ganglia.gpu.sixnodes.csv.zip"
GANGLIA_BYTES = 1_149_353_389
GANGLIA_SHA256 = "f8e14651bf3cad97e83fe22a704734bffdc1307afa935430da2b37833db34e1f"
GANGLIA_MD5 = "bf2c397ce74dfcc82ac1be425647f2fc"

ILO_NAME = "esif.hpc.eagle.ilo-power.gpu.sixnodes.csv.zip"
ILO_BYTES = 53_704_398
ILO_SHA256 = "ee73ff938dd1ede6c3e1064e0fb042bcdb35f7e1a9bc582e2fa420fe7e50cda3"
ILO_MD5 = "2c4320667daca7d55a31181bc47b56d9"

JOBS_NAME = "esif.hpc.eagle.job-anon-energy-metrics.zip"
JOBS_BYTES = 1_441_620_944
JOBS_SHA256 = "966ca575cc50b3273719b39781e32728ae066ece4af699fb5d73d9db4362ecce"
JOBS_MD5 = "cc60eac4d10b38a1bbfe3ef7dede5590"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - registry identity, not security
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "arbitrary_flexible_scaling_calls": 0,
        "effect_selected_power_parameters": 0,
        "grid_benefit_selected_power_parameters": 0,
        "Eagle_absolute_kW_to_H100_transfer_calls": 0,
        "rowwise_Eagle_to_Kestrel_merges": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def zip_content_manifest(path: Path) -> dict[str, Any]:
    """Return metadata-only ZIP content identity without extracting the source."""
    with zipfile.ZipFile(path) as archive:
        rows = [
            {
                "path": item.filename,
                "compressed_bytes": item.compress_size,
                "uncompressed_bytes": item.file_size,
                "crc32": f"{item.CRC:08x}",
            }
            for item in archive.infolist()
            if not item.is_dir()
        ]
    canonical = "".join(
        f"{row['path']}\0{row['compressed_bytes']}\0{row['uncompressed_bytes']}\0{row['crc32']}\n"
        for row in rows
    ).encode("utf-8")
    return {
        "member_count": len(rows),
        "uncompressed_bytes": sum(row["uncompressed_bytes"] for row in rows),
        "content_index_sha256": hashlib.sha256(canonical).hexdigest(),
        "members": rows,
    }


def verify_source(path: Path, *, size: int, sha256: str, md5: str) -> dict[str, Any]:
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    actual_sha = sha256_file(path)
    actual_md5 = md5_file(path)
    after = (path.stat().st_size, path.stat().st_mtime_ns)
    if before != after:
        raise RuntimeError("V17_V3R2_EAGLE_SOURCE_MUTATION_DETECTED")
    if before[0] != size or actual_sha != sha256 or actual_md5 != md5:
        raise RuntimeError(f"V17_V3R2_EAGLE_SOURCE_IDENTITY_MISMATCH:{path.name}")
    return {
        "absolute_path": str(path.resolve()),
        "bytes": size,
        "sha256": actual_sha,
        "md5_official_registry": actual_md5,
        "immutable_before_after": True,
        **zip_content_manifest(path),
    }


def assert_eagle_only_join(left_source: str, right_source: str) -> None:
    """Reject any row-wise bridge between the two machine ecosystems."""
    sources = {left_source.upper(), right_source.upper()}
    if "EAGLE" in sources and "KESTREL" in sources:
        raise RuntimeError("V17_V3R2_ROWWISE_EAGLE_KESTREL_MERGE_FORBIDDEN")


def assert_no_eagle_absolute_kw_to_h100(*, source_hardware: str, target_hardware: str, absolute: bool) -> None:
    if absolute and source_hardware.upper().startswith("V100") and target_hardware.upper().startswith("H100"):
        raise RuntimeError("V17_V3R2_EAGLE_ABSOLUTE_KW_TO_H100_FORBIDDEN")


def assert_common_features(features: Iterable[str]) -> None:
    forbidden = {"future_node_id", "gpu_utilization", "future_gpu_utilization", "measured_power_kw"}
    bad = sorted(set(features) & forbidden)
    if bad:
        raise RuntimeError(f"V17_V3R2_NONCAUSAL_OR_LABEL_FEATURE:{','.join(bad)}")


def assert_block_split(train_blocks: Iterable[str], heldout_blocks: Iterable[str]) -> None:
    overlap = sorted(set(train_blocks) & set(heldout_blocks))
    if overlap:
        raise RuntimeError(f"V17_V3R2_HELDOUT_BLOCK_LEAKAGE:{','.join(overlap)}")


def assert_node_energy_not_job_power(*, source_semantics: str, requested_interpretation: str) -> None:
    if source_semantics != "JOB_ATTRIBUTED_ENERGY" and requested_interpretation == "INDIVIDUAL_JOB_POWER":
        raise RuntimeError("V17_V3R2_SHARED_NODE_ENERGY_AS_JOB_POWER_FORBIDDEN")


def assert_disjoint_sets(*sets: set[str]) -> None:
    seen: set[str] = set()
    for values in sets:
        overlap = seen & values
        if overlap:
            raise RuntimeError(f"V17_V3R2_COHORT_OVERLAP:{sorted(overlap)[0]}")
        seen |= values

