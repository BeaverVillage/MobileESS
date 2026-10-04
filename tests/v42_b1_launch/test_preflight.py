"""B1 launch gates: tampered barrier, malformed dates, prohibited scope."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from v42_orchestrator.dag import load_dates
from v42_orchestrator.config import Config
from v42_native.planning import validate_plan

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('b1_preflight', ROOT / 'tools/v42/preflight_b1_may.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize('change', [dict(arm='B2'), dict(arm='B3'), dict(workers=2),
                                    dict(threads=2), dict(mess=True), dict(ml_off=True)])
def test_reject_forbidden_science(change):
    with pytest.raises(PermissionError):
        audit.scope(**change)


def test_incomplete_b0_cannot_authorize_b1():
    final = audit.read(ROOT / 'docs/v42_may_b0_production_31d/B0_CAMPAIGN_FINAL.json')
    state = audit.read(audit.B0_ROOT / 'CAMPAIGN_STATE.json')
    bad = copy.deepcopy(final)
    bad['flags']['B0_SCIENTIFIC_PASS'] = False
    with pytest.raises(ValueError, match='BARRIER_FAILED'):
        audit.barrier(bad, state, audit.B0_ROOT)


def test_receipt_hash_drift_cannot_authorize_b1():
    final = audit.read(ROOT / 'docs/v42_may_b0_production_31d/B0_CAMPAIGN_FINAL.json')
    state = audit.read(audit.B0_ROOT / 'CAMPAIGN_STATE.json')
    next(iter(state['stages'].values()))['receipt_sha'] = '0' * 64
    with pytest.raises(ValueError, match='RECEIPT_DRIFT'):
        audit.barrier(final, state, audit.B0_ROOT)


def test_explicit_production_flag_does_not_promote_mock_scheduler():
    with pytest.raises(PermissionError, match='no production adapter'):
        Config(ENABLE_PRODUCTION=True).production_guard()


def test_accepted_historical_a1_is_not_a_frozen_actual_policy():
    legacy = audit.read(ROOT / 'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE.json')
    assert legacy['PASS'] is True
    with pytest.raises(ValueError, match='DAYAHEAD_FREEZE_FIELDS_REQUIRED'):
        validate_plan(legacy)


@pytest.mark.parametrize('mutation', ['duplicate', 'omission', 'unsorted', 'wrong_month'])
def test_invalid_frozen_dates(tmp_path, mutation):
    days = list(load_dates())
    if mutation == 'duplicate': days[-1] = days[0]
    elif mutation == 'omission': days.pop()
    elif mutation == 'unsorted': days.reverse()
    else: days[0] = '2025-04-01'
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(dict(days=days)), encoding='utf8')
    with pytest.raises(ValueError): load_dates(path)
