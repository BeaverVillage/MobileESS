from __future__ import annotations

import json
import tarfile
from pathlib import Path

from dayahead.v17_v3r1_zenodo import tar_manifest, zero_counters


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_tar_manifest_is_deterministic_and_source_immutable(tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        readme = tmp_path / "README.md"
        readme.write_text("authority\n", encoding="utf-8")
        archive.add(readme, arcname="artifact/README.md")
    before = source.read_bytes()
    first = tar_manifest(source)
    second = tar_manifest(source)
    assert first == second
    assert source.read_bytes() == before


def test_official_zenodo_identity_is_not_old_github_zip() -> None:
    discovery = load("V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json")
    delta = load("V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json")
    assert discovery["status"] == "PASS_OFFICIAL_ZENODO_ARTIFACT_IDENTIFIED_BY_CONTENT_AND_PROVENANCE"
    assert discovery["official_record"]["doi"] == "10.5281/zenodo.17122337"
    assert discovery["source"]["sha256"] == "b444240db2d93cbe44ad18e30e91fcb09d3e6513d1cf4430cf1a1c83eb4c10e7"
    assert discovery["old_github_zip_mistaken_for_zenodo"] is False
    assert discovery["user_supplied_internet_shortcut"]["record_identity_matches_zone_identifier"] is True
    assert delta["official_zenodo"]["archive_sha256"] != delta["github_snapshot"]["archive_sha256"]
    assert delta["delta"]["zenodo_to_github_archive_size_ratio"] > 1000


def test_zenodo_contains_raw_measurements_and_benchmark_results() -> None:
    discovery = load("V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json")
    assert discovery["source"]["raw_telemetry_member_count"] > 0
    assert discovery["source"]["benchmark_result_member_count"] > 0
    assert discovery["license"]["scientific_use_permitted"] is True
    assert discovery["source_immutable_before_after"] is True


def test_discovery_firewall_counters_zero() -> None:
    expected = zero_counters()
    for name in [
        "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json",
        "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json",
    ]:
        payload = load(name)
        for key, value in expected.items():
            assert payload[key] == value
