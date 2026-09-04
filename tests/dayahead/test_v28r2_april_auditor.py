import json
from pathlib import Path

from dayahead.v28r2.certificate import write_certificate
from dayahead.v28r2.source_manifest import CATEGORIES
from tools.final_campaign.audit_v28r2_april import APRIL_DAYS, REQUIRED_REFERENCES, audit, certificate_path


def test_april_auditor_fails_closed_without_30_certificates(tmp_path: Path):
    result = audit(tmp_path)
    assert result["APRIL_FULL_MONTH_PREFLIGHT_PASS"] is False
    assert result["valid_day_count"] == 0
    assert len(result["invalid_or_missing"]) == 30


def test_april_auditor_accepts_only_complete_verified_day_set(tmp_path: Path):
    root = tmp_path / "frozen_artifacts/v28r2_april_full_month_preflight"
    reference = tmp_path / "evidence.txt"
    reference.write_text("verified\n", encoding="utf-8")
    record = {"path": str(reference.resolve()), "sha256": __import__("hashlib").sha256(reference.read_bytes()).hexdigest(), "bytes": reference.stat().st_size}
    references = {name: record for name in REQUIRED_REFERENCES}
    source_manifest = tmp_path / "source_day_manifest.json"
    source_manifest.write_text(json.dumps({
        "categories": {name: {"status": "NOT_APPLICABLE_BY_AUTHORITY", "authority_evidence": "test"} for name in CATEGORIES}
    }), encoding="utf-8")
    references["source_day_manifest"] = {
        "path": str(source_manifest.resolve()),
        "sha256": __import__("hashlib").sha256(source_manifest.read_bytes()).hexdigest(),
        "bytes": source_manifest.stat().st_size,
    }
    for day in APRIL_DAYS:
        write_certificate(certificate_path(root, day), {
            "artifact_id": "V28R2_APRIL_DAY_CERTIFICATE_V1",
            "status": "PASS", "day": day, "non_authority_smoke": False,
            "actual_optimizer_calls": 0, "hidden_shedding_nodeh": 0.0,
            "workload_mass_error_nodeh": 0.0,
            "OpenDSS_real_solved_slots": {"DA/B0": 96},
            "git_head": "a" * 40, "references": references,
        })
    result = audit(tmp_path)
    assert result["APRIL_FULL_MONTH_PREFLIGHT_PASS"] is True
    assert result["valid_day_count"] == 30
    assert result["invalid_or_missing"] == []


def test_april_audit_shell_is_v28r2_and_lf_only():
    script = Path(__file__).resolve().parents[2] / "tools/final_campaign/audit_2025_april_preflight.sh"
    raw = script.read_bytes()
    assert b"set -euo pipefail" in raw
    assert b"audit_v28r2_april" in raw
    assert b"\r\n" not in raw
