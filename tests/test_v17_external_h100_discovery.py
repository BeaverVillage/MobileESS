from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from dayahead.v17_external_h100_forensic import archive_manifest, sha256_file


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_archive_manifest_is_read_only_and_sha_reproducible(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("README.md", "authority\n")
        archive.writestr("data/row.csv", "x,y\n1,2\n")
    before = source.read_bytes()
    first = archive_manifest(source)
    second = archive_manifest(source)
    assert source.read_bytes() == before
    assert first == second
    assert first["archive_sha256"] == sha256_file(source) == hashlib.sha256(before).hexdigest()


def test_two_sources_are_content_identified_and_frozen() -> None:
    discovery = load("V17_EXTERNAL_H100_DATASET_DISCOVERY.json")
    authority = load("V17_EXTERNAL_H100_SOURCE_AUTHORITY_MANIFEST.json")
    assert discovery["status"] == "PASS_TWO_INTENDED_DATASET_IDENTITIES_UNIQUE"
    assert len(discovery["datasets"]) == 2
    assert discovery["candidate_resolution"]["scientific_duplicate_directory_is_exact_nested_payload"]
    assert authority["status"] == "PASS_SOURCE_PROVENANCE_FROZEN_READ_ONLY"
    assert authority["datasets"]["EUROSYS_UNTANGLING_GPU_POWER"]["archive"]["archive_sha256"] == (
        "e941baeb5fc083d404cf6f676cf11794e269bf06e96fea6d3d58746fb1919ac7"
    )


def test_hardware_firewall_forbids_absolute_external_kappa_replacement() -> None:
    compatibility = load("V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY.json")
    assert compatibility["absolute_external_kW_may_replace_Dataset312_kappa"] is False
    assert compatibility["Dataset312_kappa_changes"] == 0
    classes = {row["classification"] for row in compatibility["relationships"]}
    assert "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY" in classes
    assert "QUALITATIVE_ONLY" in classes


def test_utilization_allocation_and_sharing_semantics_are_separate() -> None:
    schema = load("V17_EXTERNAL_H100_SCHEMA_AUDIT.json")
    firewall = schema["concept_firewall"]
    assert firewall["GPU_utilization_percentage_is_GPU_allocation_fraction"] is False
    assert firewall["MIG_2g20gb_is_Kestrel_2_of_4_GPU_request"] is False
    assert firewall["time_slicing_is_Kestrel_co_residency"] is False


def test_no_forbidden_data_or_science_calls_in_discovery_artifacts() -> None:
    for name in [
        "V17_EXTERNAL_H100_DATASET_DISCOVERY.json",
        "V17_EXTERNAL_H100_SOURCE_AUTHORITY_MANIFEST.json",
        "V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY.json",
        "V17_EXTERNAL_H100_SCHEMA_AUDIT.json",
    ]:
        payload = load(name)
        assert payload["May_scientific_input_reads"] == 0
        assert payload["June_scientific_input_reads"] == 0
        assert payload["remaining_April_day_runs"] == 0
        assert payload["rowwise_external_to_Kestrel_merges"] == 0
