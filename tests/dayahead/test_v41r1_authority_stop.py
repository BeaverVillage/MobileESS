from pathlib import Path
import pandas as pd
import pytest

from dayahead.v41r1.audit import OUT, STOP, cannot_freeze, dated_path, read, require_premay, sha


@pytest.mark.parametrize('day', ['2025-01-13', '2025-03-10', '2025-04-01', '2025-04-30'])
def test_premay_date_boundary(day):
    assert str(require_premay(day)) == day


@pytest.mark.parametrize('day', ['2025-05-01', '2025-05-02', '2025-05-31', '2025-06-01'])
def test_may_and_later_are_rejected(day):
    with pytest.raises(ValueError, match='MAY_OR_LATER'):
        require_premay(day)


@pytest.mark.parametrize('path', ['undated/OPENDSS_PHASE_ARRAYS.npz',
    '2025-04-01/source_2025-05-01.npz', '20250502/OPENDSS_PHASE_ARRAYS.npz'])
def test_undated_or_mixed_date_numerical_paths_rejected(path):
    with pytest.raises(ValueError):
        dated_path(path)


def test_empty_authority_cannot_be_zero_margin():
    with pytest.raises(ValueError, match=STOP):
        cannot_freeze([])


def test_nonempty_unverified_input_cannot_bypass_audit():
    with pytest.raises(ValueError, match='VERIFIED_PAIRING_REVIEW'):
        cannot_freeze([{'day': '2025-04-01'}])


def test_no_freeze_or_launch_is_claimed_on_empty_population():
    freeze = read(OUT / 'V41R1_VOLTAGE_SECURITY_MARGIN_FREEZE.json')
    propagation = read(OUT / 'V41R1_MAY_VOLTAGE_MARGIN_PROPAGATION_AUDIT.json')
    assert freeze['status'] == 'NOT_FROZEN'
    assert freeze['N_preMay_policy_days'] == 0
    for field in ('EPSILON_V_UP', 'V_MAX_PLANNING', 'k_order_statistic', 'scientific_commit'):
        assert freeze[field] is None
    assert freeze['V_MAX_PHYSICAL'] == 1.05 and freeze['V_MIN_PHYSICAL'] == .95
    assert propagation['launched_units'] == propagation['passed_units'] == 0
    assert propagation['full_May_launch_gate'] == 'FAIL'


def test_no_legacy_mapper_or_fresh_sample_admitted():
    audit = read(OUT / 'V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json')
    candidates = read(audit['candidate_rows']['path'])['rows']
    assert audit['eligible_policy_days'] == [] and audit['eligible_element_rows'] == 0
    assert len(candidates) == audit['historical_Actual_candidate_count']
    for row in candidates:
        require_premay(row['day'])
        assert row['compatibility_status'] == 'REJECTED'
        assert not row['numerical_pairing_performed']
        assert row['source_SHA256'] == sha(row['actual_source']['path'])
    assert audit['corrected_April']['compatibility_status'] == 'REJECTED_NO_REALIZED_ACTUAL'


@pytest.mark.parametrize('table', ['V41R1_PREMAY_VOLTAGE_ELEMENT_RESIDUALS.parquet',
                                 'V41R1_PREMAY_VOLTAGE_DAILY_MAX.parquet'])
def test_empty_tables_readback_and_hash(table):
    audit = read(OUT / 'V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json')
    receipt = audit['tables'][table]
    path = Path(receipt['path'])
    # Frozen historical receipts retain their original owner in a new worktree.
    # Verify the named artifact and exact frozen bytes rather than moving it.
    assert path.parent.name == OUT.name and path.name == table and path.is_file()
    assert sha(path) == receipt['sha256']
    assert pd.read_parquet(path).empty and receipt['rows'] == 0


def test_firewall_and_old_preservation():
    firewall = read(OUT / 'V41R1_VOLTAGE_MARGIN_DATA_FIREWALL.json')
    preserved = read(OUT / 'V41R1_OLD_MAY01_READBACK_AUDIT.json')
    assert firewall['May_calibration_rows'] == firewall['numerical_calibration_rows'] == 0
    assert not firewall['May02_31_Actual_scientific_outcomes_opened']
    assert not firewall['margin_computed'] and not firewall['May_based_retuning']
    assert preserved['status'] == 'PASS' and preserved['changed'] == 0


def test_scientific_contracts_unchanged():
    # This is the historical authority-stop audit, before the subsequently
    # authorized terminal revision. Verify its frozen base rather than assert
    # that the current terminal formulation still has the old source bytes.
    import hashlib, subprocess
    from dayahead.v41r1.audit import ROOT, OLD, BASE
    audit = read(OUT / 'V41R1_UNCHANGED_SCIENTIFIC_IMPLEMENTATION.json')
    for source in audit['files']:
        blob=subprocess.check_output(['git','show',BASE+':'+source['path']],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == source['sha256'] == sha(OLD / source['path'])
    assert audit['new_optimizer_calls'] == audit['new_Actual_calls'] == 0


def test_background_native_readback():
    audit = read(OUT / 'V41R1_BACKGROUND_LOAD_REGRESSION.json')
    assert audit['status'] == 'PASS' and audit['calibration_rows_created'] == 0
    assert {row['stage'] for row in audit['results']} == {'Planning', 'Fresh', 'Actual'}
    for row in audit['results']:
        assert row['slots'] == 96 and row['duplicated_group_slots'] == 0
        assert sha(row['audit']['path']) == row['audit']['sha256']
