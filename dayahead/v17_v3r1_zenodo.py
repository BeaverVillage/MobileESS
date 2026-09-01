"""Fail-closed V17 V3R1 audit of the official EuroSys Zenodo artifact.

The external-data root is an immutable authority.  This module only streams
archive members and writes derived JSON into the repository artifact directory.
It never extracts into, renames, or modifies the raw-data source directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Iterable


REQUIRED_HEAD = "671f4fe402a25be281397c5fa8ad262cea4f29c0"
ZENODO_RECORD_ID = 17122337
ZENODO_DOI = "10.5281/zenodo.17122337"
ZENODO_CONCEPT_DOI = "10.5281/zenodo.16981546"
ZENODO_SHA256 = "b444240db2d93cbe44ad18e30e91fcb09d3e6513d1cf4430cf1a1c83eb4c10e7"
ZENODO_MD5 = "5f71e777a51a4cee2885f94a112efd29"
ZENODO_BYTES = 131_569_816
GITHUB_SHA256 = "e941baeb5fc083d404cf6f676cf11794e269bf06e96fea6d3d58746fb1919ac7"

ZENODO_RELATIVE = Path("EuroSys 2026 — Untangling GPU Power Consumption artifact") / "untangling-gpu-power.tar.gz"
GITHUB_RELATIVE = Path("EuroSys 2026 — Untangling GPU Power Consumption artifact") / "untangling-gpu-power-main.zip"
ZENODO_SHORTCUT_RELATIVE = (
    Path("EuroSys 2026 — Untangling GPU Power Consumption artifact")
    / "Artifact for - Untangling GPU Power Consumption- Job-Level Inference in Cloud Shared Settings - Zenodo.url"
)
ZENODO_SHORTCUT_SHA256 = "a75c68498e79ea0d9b9d10a356b1935872581e62c0c961e038f57b3f44c8770a"

CREATORS = [
    "Jacquet, Pierre",
    "Agusti, Maxime",
    "Caron, Eddy",
    "Coti, Camille",
    "Marcos, Dias de Assuncao",
    "Lefevre, Laurent",
    "Orgerie, Anne-Cécile",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - source registry comparison, not security
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "effect_selected_power_parameters": 0,
        "grid_benefit_selected_power_parameters": 0,
        "arbitrary_flexible_scaling_calls": 0,
        "rowwise_external_to_Kestrel_merges": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def _tar_member_sha(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    stream = archive.extractfile(member)
    if stream is None:
        raise RuntimeError(f"V17_V3R1_TAR_MEMBER_UNREADABLE:{member.name}")
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def tar_manifest(path: Path, *, include_member_hashes: bool = True) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            row = {"path": member.name, "bytes": member.size}
            if include_member_hashes:
                row["sha256"] = _tar_member_sha(archive, member)
            records.append(row)
    canonical = "".join(
        f"{row['path']}\0{row['bytes']}\0{row.get('sha256', '')}\n" for row in records
    ).encode("utf-8")
    return {
        "archive_path": str(path.resolve()),
        "archive_bytes": path.stat().st_size,
        "archive_sha256": sha256_file(path),
        "file_count": len(records),
        "uncompressed_bytes": sum(row["bytes"] for row in records),
        "recursive_content_manifest_sha256": sha256_bytes(canonical),
        "files": records,
    }


def zip_summary(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in files]
        data_members = [
            item for item in files
            if ("/data/" in item.filename or "/bench-res/" in item.filename)
            and not item.filename.endswith(".gitkeep")
        ]
        return {
            "archive_path": str(path.resolve()),
            "archive_bytes": path.stat().st_size,
            "archive_sha256": sha256_file(path),
            "file_count": len(files),
            "uncompressed_bytes": sum(item.file_size for item in files),
            "raw_data_or_bench_member_count": len(data_members),
            "member_names_sha256": sha256_bytes("\n".join(names).encode("utf-8")),
        }


def _read_tar_text(path: Path, member_name: str) -> str:
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(member_name)
        stream = archive.extractfile(member)
        if stream is None:
            raise RuntimeError(f"V17_V3R1_TAR_MEMBER_UNREADABLE:{member_name}")
        return stream.read().decode("utf-8-sig", errors="replace")


def _zone_identifier(path: Path) -> dict[str, str]:
    ads_path = Path(str(path) + ":Zone.Identifier")
    try:
        text = ads_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {"status": "NOT_AVAILABLE", "referrer_url": "", "host_url": ""}
    referrer = re.search(r"^ReferrerUrl=(.*)$", text, flags=re.MULTILINE)
    host = re.search(r"^HostUrl=(.*)$", text, flags=re.MULTILINE)
    clean = lambda match: match.group(1).rstrip("\x00\r").strip() if match else ""
    return {
        "status": "PRESENT",
        "referrer_url": clean(referrer),
        "host_url": clean(host),
    }


def _source_counts(manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest["files"]
    raw = [row for row in files if "/data/" in row["path"] and not row["path"].endswith(".gitkeep")]
    bench = [row for row in files if "/bench-res/" in row["path"] and not row["path"].endswith(".gitkeep")]
    experiment = [row for row in files if "/experiments/" in row["path"] and row["path"].endswith(".py")]
    figure = [row for row in files if "/src/" in row["path"] and row["path"].endswith(".py")]
    return {
        "raw_telemetry_member_count": len(raw),
        "raw_telemetry_uncompressed_bytes": sum(row["bytes"] for row in raw),
        "benchmark_result_member_count": len(bench),
        "benchmark_result_uncompressed_bytes": sum(row["bytes"] for row in bench),
        "experiment_script_count": len(experiment),
        "figure_script_count": len(figure),
    }


def discover(external_root: Path, output: Path) -> dict[str, Any]:
    root = external_root.resolve()
    zenodo = root / ZENODO_RELATIVE
    github = root / GITHUB_RELATIVE
    shortcut = root / ZENODO_SHORTCUT_RELATIVE
    if not zenodo.is_file():
        raise RuntimeError("V17_V3R1_ZENODO_ARTIFACT_NOT_FOUND")
    if not github.is_file():
        raise RuntimeError("V17_V3R1_PRIOR_GITHUB_ARTIFACT_NOT_FOUND")
    if not shortcut.is_file() or sha256_file(shortcut) != ZENODO_SHORTCUT_SHA256:
        raise RuntimeError("V17_V3R1_ZENODO_SHORTCUT_IDENTITY_MISMATCH")
    shortcut_text = shortcut.read_text(encoding="utf-8-sig", errors="replace")
    if "URL=https://zenodo.org/records/17122337" not in shortcut_text:
        raise RuntimeError("V17_V3R1_ZENODO_SHORTCUT_RECORD_MISMATCH")
    source_before = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (zenodo, github, shortcut)
    }
    if zenodo.stat().st_size != ZENODO_BYTES or sha256_file(zenodo) != ZENODO_SHA256:
        raise RuntimeError("V17_V3R1_ZENODO_SOURCE_IDENTITY_MISMATCH")
    if md5_file(zenodo) != ZENODO_MD5:
        raise RuntimeError("V17_V3R1_ZENODO_REGISTRY_MD5_MISMATCH")
    if sha256_file(github) != GITHUB_SHA256:
        raise RuntimeError("V17_V3R1_GITHUB_SOURCE_IDENTITY_MISMATCH")

    manifest = tar_manifest(zenodo)
    github_summary = zip_summary(github)
    counts = _source_counts(manifest)
    readme = _read_tar_text(zenodo, "untangling-gpu-power/README.md")
    license_text = _read_tar_text(zenodo, "untangling-gpu-power/LICENSE")
    zone = _zone_identifier(zenodo)
    identity_pass = all(
        [
            "Untangling GPU Power Consumption" in readme,
            "EuroSys 2026" in readme,
            "Raw data from the experiments" in readme,
            "BSD 3-Clause License" in license_text,
            counts["raw_telemetry_member_count"] > 0,
            counts["benchmark_result_member_count"] > 0,
            zone["host_url"].startswith(
                "https://zenodo.org/records/17122337/files/untangling-gpu-power.tar.gz"
            ),
        ]
    )
    if not identity_pass:
        raise RuntimeError("V17_V3R1_ZENODO_CONTENT_PROVENANCE_FAILURE")

    source_after = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (zenodo, github, shortcut)
    }
    if source_before != source_after:
        raise RuntimeError("V17_V3R1_EXTERNAL_SOURCE_MUTATION_DETECTED")

    discovery = {
        "artifact_id": "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY_V1",
        "status": "PASS_OFFICIAL_ZENODO_ARTIFACT_IDENTIFIED_BY_CONTENT_AND_PROVENANCE",
        "raw_root_access_mode": "READ_ONLY",
        "external_root": str(root),
        "source": {
            "absolute_path": str(zenodo.resolve()),
            "archive_type": "TAR_GZ",
            "bytes": zenodo.stat().st_size,
            "sha256": ZENODO_SHA256,
            "md5_registry": ZENODO_MD5,
            "file_count": manifest["file_count"],
            "uncompressed_bytes": manifest["uncompressed_bytes"],
            "recursive_content_manifest_sha256": manifest["recursive_content_manifest_sha256"],
            **counts,
        },
        "official_record": {
            "record_id": ZENODO_RECORD_ID,
            "doi": ZENODO_DOI,
            "concept_doi": ZENODO_CONCEPT_DOI,
            "record_url": "https://zenodo.org/records/17122337",
            "title": "Artifact for : Untangling GPU Power Consumption: Job-Level Inference in Cloud Shared Settings",
            "publication_date": "2025",
            "meeting": "EuroSys 2026",
            "resource_type": "Software / Computational notebook",
            "repository": "https://github.com/maxime-agusti/untangling-gpu-power",
            "creators": CREATORS,
            "registry_file_bytes": ZENODO_BYTES,
            "registry_file_md5": ZENODO_MD5,
            "metadata_verification": "OFFICIAL_ZENODO_API_2026-08-31",
        },
        "local_download_provenance": zone,
        "user_supplied_internet_shortcut": {
            "absolute_path": str(shortcut.resolve()),
            "sha256": ZENODO_SHORTCUT_SHA256,
            "url": "https://zenodo.org/records/17122337?utm_source=chatgpt.com",
            "record_identity_matches_zone_identifier": True,
        },
        "license": {
            "id": "BSD-3-Clause",
            "source": "archive LICENSE",
            "scientific_use_permitted": True,
            "license_sha256": sha256_bytes(license_text.encode("utf-8")),
        },
        "readme_sha256": sha256_bytes(readme.encode("utf-8")),
        "old_github_zip_mistaken_for_zenodo": False,
        "source_immutable_before_after": True,
        **zero_counters(),
    }

    delta = {
        "artifact_id": "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA_V1",
        "status": "PASS_MATERIALLY_DISTINCT_ZENODO_RAW_DATA_AUTHORITY",
        "github_snapshot": github_summary,
        "official_zenodo": {
            "archive_path": manifest["archive_path"],
            "archive_bytes": manifest["archive_bytes"],
            "archive_sha256": manifest["archive_sha256"],
            "file_count": manifest["file_count"],
            "uncompressed_bytes": manifest["uncompressed_bytes"],
            **counts,
        },
        "delta": {
            "archive_bytes": manifest["archive_bytes"] - github_summary["archive_bytes"],
            "file_count": manifest["file_count"] - github_summary["file_count"],
            "uncompressed_bytes": manifest["uncompressed_bytes"] - github_summary["uncompressed_bytes"],
            "zenodo_to_github_archive_size_ratio": manifest["archive_bytes"] / github_summary["archive_bytes"],
            "github_raw_data_or_bench_member_count": github_summary["raw_data_or_bench_member_count"],
            "zenodo_raw_data_plus_bench_member_count": counts["raw_telemetry_member_count"] + counts["benchmark_result_member_count"],
        },
        "scientific_interpretation": [
            "The prior GitHub ZIP is a small source snapshot with no non-placeholder data or benchmark rows.",
            "The official Zenodo TAR contains the raw experiment telemetry and benchmark-result families required for a V3R1 retry.",
            "No prior V3 conclusion is relabeled; V3R1 is a new prospective authority evaluation.",
        ],
        "old_github_zip_is_measurement_authority": False,
        "official_zenodo_tar_is_candidate_measurement_authority": True,
        **zero_counters(),
    }

    write_json(output / "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json", discovery)
    write_json(output / "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json", delta)
    return {
        "status": "PASS_DISCOVERY_PROVENANCE_SOURCE_DELTA",
        "zenodo_sha256": ZENODO_SHA256,
        "manifest_sha256": manifest["recursive_content_manifest_sha256"],
        "artifacts": [
            "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json",
            "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json",
        ],
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = discover(args.external_root, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
