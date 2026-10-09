"""Independent final-delivery attacks; no solver construction or Native calls."""
from fractions import Fraction
from pathlib import Path
import json
import numpy as np
import pytest

from v42_m1_hybrid import final_verify, report, delivery_ready


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.mark.parametrize('lower', [True, False])
def test_displayed_rational_bound_is_on_certified_side(lower):
    q = Fraction(1, 10)
    value = final_verify._display_bound(q, lower=lower)
    assert np.isfinite(value)
    assert (Fraction(value) <= q) if lower else (Fraction(value) >= q)


@pytest.fixture
def packets(tmp_path, monkeypatch):
    run = tmp_path / 'run-a'; output = tmp_path / 'docs'
    run.mkdir(); output.mkdir()
    monkeypatch.setattr(report, 'inside_d', lambda path: Path(path).resolve())
    monkeypatch.setattr(report, 'RUNTIME', tmp_path)
    monkeypatch.setattr(report, 'REPORTS', output)
    save(run / 'NATIVE_PHASE_RESULTS.json', dict(case_sha=report.CASE_SHA, run_id='run-a'))
    save(run / 'NATIVE_RUNTIME_LEDGER.json', dict(case_sha=report.CASE_SHA))
    save(run / 'PREREGISTRATION.json', dict(case_sha=report.CASE_SHA))
    save(output / 'ZERO_NATIVE_REGRESSION.json', dict(PASS=True, failed=[]))
    return run, output


def test_same_case_receipt_from_other_run_is_rejected_before_writes(packets):
    run, output = packets
    save(output / 'INDEPENDENT_FINAL_VERIFICATION.json', dict(PASS=True, case_sha=report.CASE_SHA,
        Native_optimize_calls=0, run_id='run-b', run_path=str(run.parent / 'run-b')))
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(ValueError, match='EXACT_NEW_RUN_VERIFIER_BINDING_REQUIRED'):
        report.finalize(run)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_stale_same_run_packet_sha_is_rejected_before_writes(packets):
    run, output = packets
    save(output / 'INDEPENDENT_FINAL_VERIFICATION.json', dict(PASS=True, case_sha=report.CASE_SHA,
        Native_optimize_calls=0, run_id=run.name, run_path=str(run), source_evidence_sha256={}))
    with pytest.raises(ValueError, match='FINAL_VERIFIER_SOURCE_PACKET_DRIFT'):
        report.finalize(run)
    assert not (output / 'FINAL_RESEARCH_STATUS.json').exists()


def test_failed_hybrid_validation_preserves_existing_readiness(tmp_path, monkeypatch):
    output = tmp_path / 'docs'; output.mkdir()
    ready_file = tmp_path / 'V42_INTEGRATION_READY.json'
    ready_file.write_bytes(b'old validated readiness')
    monkeypatch.setattr(delivery_ready, 'ROOT', tmp_path)
    monkeypatch.setattr(delivery_ready, 'REPORTS', output)
    def integration():
        delivery_ready.integration_delivery.write(ready_file, {'schema': 'V1'})
        return dict(integration_HEAD='fake')
    monkeypatch.setattr(delivery_ready, 'integration_ready', integration)
    for name in ('FINAL_RESEARCH_STATUS.json', 'INDEPENDENT_FINAL_VERIFICATION.json',
                 'ZERO_NATIVE_REGRESSION.json', 'SOURCE_PRESERVATION_AUDIT.json', 'SHA256_MANIFEST.json'):
        save(output / name, dict(PASS=False))
    with pytest.raises(ValueError, match='CHECKED_HYBRID_DELIVERY_EVIDENCE_REQUIRED'):
        delivery_ready.ready()
    assert ready_file.read_bytes() == b'old validated readiness'


def test_empty_pass_manifest_cannot_certify_delivery(tmp_path, monkeypatch):
    output = tmp_path / 'docs'; output.mkdir()
    monkeypatch.setattr(delivery_ready, 'ROOT', tmp_path)
    monkeypatch.setattr(delivery_ready, 'REPORTS', output)
    monkeypatch.setattr(delivery_ready, 'integration_ready', lambda: dict(integration_HEAD='fake'))
    for name in ('FINAL_RESEARCH_STATUS.json', 'INDEPENDENT_FINAL_VERIFICATION.json',
                 'ZERO_NATIVE_REGRESSION.json', 'SOURCE_PRESERVATION_AUDIT.json', 'SHA256_MANIFEST.json'):
        save(output / name, dict(PASS=True, case_sha=delivery_ready.CASE_SHA,
            failed=[], M1_ACCEPTED=False, P2_certificate=None, files={}))
    with pytest.raises(ValueError, match='HYBRID_MANIFEST_COMPLETE_FILE_SET_REQUIRED'):
        delivery_ready.ready()
