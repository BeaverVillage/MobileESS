import json
from pathlib import Path

from dayahead.v28r2.source_manifest import CATEGORIES, canonical_sha256, sha256_file, verify_day_manifest
from dayahead.v28r2.source_preflight import APRIL_DAYS


def test_april_axis_and_category_axis_are_exact():
    assert len(APRIL_DAYS) == 30
    assert APRIL_DAYS[0] == "2025-04-01" and APRIL_DAYS[-1] == "2025-04-30"
    assert len(CATEGORIES) == 13


def test_canonical_manifest_digest_excludes_no_hidden_state():
    payload = {"day": "2025-04-01", "categories": {}}
    assert canonical_sha256(payload) == canonical_sha256(json.loads(json.dumps(payload)))


def test_coverage_artifact_is_30_by_13_when_present():
    repo = Path(__file__).resolve().parents[2]
    path = repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_APRIL_SOURCE_COVERAGE.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["covered_day_count"] == 30
        assert payload["matrix_row_count"] == 390
        assert payload["GFS_contract"]["full_GRIB_download_count"] == 0
        assert payload["forecast_for_actual_substitution_count"] == 0


def test_materialized_source_cache_is_sha_verified_when_coverage_passes():
    repo = Path(__file__).resolve().parents[2]
    coverage_path = repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_APRIL_SOURCE_COVERAGE.json"
    if not coverage_path.exists():
        return
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    if not coverage["APRIL_SOURCE_COVERAGE_READY"]:
        return
    cache = repo / "cache/v28r2_campaign_sources/april_2025"
    for day in APRIL_DAYS:
        manifest_path = cache / "days" / day / "source_day_manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_day_manifest(payload)
        forecast = json.loads((cache / "days" / day / "aemo_forecast.json").read_text(encoding="utf-8"))
        assert len(forecast["demand_mw_96"]) == len(forecast["pv_mw_96"]) == 96
        assert forecast["demand_issue"] <= forecast["cutoff_fixed_aest"]
        assert forecast["pv_issue"] <= forecast["cutoff_fixed_aest"]

    lead_manifests = sorted(cache.glob("gfs/2025-04-*/f*/manifest.json"))
    assert len(lead_manifests) == 30 * 25
    records = [record for path in lead_manifests for record in json.loads(path.read_text(encoding="utf-8"))["records"]]
    assert len(records) == 30 * 25 * 6
    assert all(record["full_grib_download"] is False for record in records)
    assert all(sha256_file(Path(record["path"])) == record["sha256"] for record in records)
