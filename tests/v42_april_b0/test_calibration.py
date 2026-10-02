"""Small invented UNIT FIXTURES only; never written as April scientific results."""
from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from v42_april_b0.contracts import (BASE, CRITERIA, QUANTILES, authority_gate, require_execution,
    require_april, freeze_plan, require_replay, feasibility_labels)
from v42_april_b0.statistics import residuals, quantile, day_worst, margin_summary, component_summary

OUT = Path(__file__).resolve().parents[2]/'docs/v42_april_b0_voltage_margin_calibration'
DATES = ('2025-04-01','2025-04-02')


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def fixture_audit():
    # Not repository scientific authority: explicit test of contract branches.
    return dict(base_head=BASE, criteria={k:True for k in CRITERIA},
                criterion_evidence={k:[dict(path='UNIT_ONLY',line=1,sha256='a'*64,
                                         supports_authority=True)] for k in CRITERIA})


def fixture_plan():
    return dict(route=['TEST'],known_jobs=['TEST'],P=[0],Q=[0])


def fixture_replay():
    plan = fixture_plan()
    frozen = freeze_plan(plan, frozen_at=1, issue_time=1, inputs_available_at=1, authoritative=True)
    da = dict(schedule_sha256=frozen['schedule_sha256'], started_at=2,
              OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True, operational_gate=False,
              P_repair=False, Q_repair=False, route_repair=False, schedule_repair=False,
              global_reoptimization=False, engine='OpenDSS', fresh_run=True, synthetic=False)
    return plan, frozen, da, deepcopy(da)


def fixture_series():
    keys = [(DATES[0], 'TEST-A','1','00:00'), (DATES[0],'TEST-B','2','00:00'),
            (DATES[1],'TEST-A','1','00:00'), (DATES[1],'TEST-A','1','00:15')]
    def series(values):
        return [dict(date=d,node=n,phase=p,time=t,voltage_pu=v)
                for (d,n,p,t),v in zip(keys, values)]
    return series([1.,1.,1.,1.]), series([1.001,.999,1.002,1.]), series([1.01,.998,1.004,.996])


@pytest.mark.parametrize('criterion', CRITERIA)
def test_every_authority_required_before_execution(criterion):
    audit = fixture_audit(); audit['criteria'][criterion] = False
    with pytest.raises(ValueError, match='BLOCKED_B0_ACTUAL_AUTHORITY'):
        require_execution(audit, dict(PASS=True, authoritative=True, synthetic=False, future_filled=False))


def test_boolean_claims_and_wrong_base_cannot_authorize():
    audit = fixture_audit(); audit['criterion_evidence'] = {}
    assert not authority_gate(audit)['B0_APRIL_EXECUTION_AUTHORIZED']
    audit = fixture_audit(); audit['base_head'] = 'wrong'
    assert not authority_gate(audit)['B0_APRIL_EXECUTION_AUTHORIZED']


@pytest.mark.parametrize('change', [dict(PASS=False),dict(authoritative=False),dict(synthetic=True),dict(future_filled=True)])
def test_data_authority_cannot_be_synthetic_or_future_filled(change):
    data = dict(PASS=True,authoritative=True,synthetic=False,future_filled=False); data.update(change)
    with pytest.raises(ValueError, match='BLOCKED_APRIL_DATA_AUTHORITY'):
        require_execution(fixture_audit(),data)


@pytest.mark.parametrize('change', [dict(authoritative=False),dict(anonymous_promoted=True),dict(synthetic=True)])
def test_no_invented_b0_schedule(change):
    args = dict(frozen_at=1,issue_time=1,inputs_available_at=1,authoritative=True); args.update(change)
    with pytest.raises(ValueError,match='NO_INVENTED_OR_ANONYMOUS'):
        freeze_plan(fixture_plan(),**args)


@pytest.mark.parametrize('change', [dict(future_used=True),dict(inputs_available_at=2)])
def test_no_future_leakage(change):
    args = dict(frozen_at=1,issue_time=1,inputs_available_at=1,authoritative=True); args.update(change)
    with pytest.raises(ValueError,match='FUTURE_INFORMATION'):
        freeze_plan(fixture_plan(),**args)


@pytest.mark.parametrize('date', ['2025-05-01','2025-03-31','2026-04-01'])
def test_april_only_frozen_date_window(date):
    with pytest.raises(ValueError,match='APRIL_ONLY'):
        require_april(date,DATES)


def test_may_unused_in_audit_artifacts():
    assert read('FINAL_FLAGS.json')['MAY_USED_FOR_CALIBRATION'] is False
    assert read('MAY_HOLDOUT_RECEIPT.json')['May_experiments'] == 0
    assert read('MAY_HOLDOUT_RECEIPT.json')['margin_tuning_on_May'] is False


def test_freeze_before_da_ac():
    plan,frozen,da,dday = fixture_replay(); da['started_at'] = 0
    with pytest.raises(ValueError,match='FREEZE_BEFORE_AC'):
        require_replay(plan,frozen,da,dday)


def test_freeze_after_issue_time_uses_only_available_inputs():
    frozen = freeze_plan(fixture_plan(), frozen_at=2, issue_time=1,
                         inputs_available_at=1, authoritative=True)
    assert frozen['frozen_at'] == 2


def test_same_sha_in_da_and_dday():
    plan,frozen,da,dday = fixture_replay(); dday['schedule_sha256'] = 'b'*64
    with pytest.raises(ValueError,match='SAME_PLAN_SHA'):
        require_replay(plan,frozen,da,dday)


@pytest.mark.parametrize('field', ['route','known_jobs','P','Q'])
def test_frozen_plan_content_never_changes(field):
    plan,frozen,da,dday = fixture_replay(); plan[field] = []
    with pytest.raises(ValueError,match='FROZEN_PLAN_CHANGED'):
        require_replay(plan,frozen,da,dday)


@pytest.mark.parametrize('field', ['P_repair','Q_repair','route_repair','schedule_repair','global_reoptimization'])
def test_no_actual_repair_or_global_reoptimization(field):
    plan,frozen,da,dday = fixture_replay(); dday[field] = True
    with pytest.raises(ValueError,match='IMMUTABLE_REPLAY'):
        require_replay(plan,frozen,da,dday)


def test_da_ac_never_operational_gate_even_on_physical_failure():
    plan,frozen,da,dday = fixture_replay(); da['voltage_violations'] = 10
    assert require_replay(plan,frozen,da,dday) # Offline result cannot revise plan or block Actual.
    da['operational_gate'] = True
    with pytest.raises(ValueError,match='DA_AC_OFFLINE_ONLY'):
        require_replay(plan,frozen,da,dday)


def test_alignment_is_by_keys_not_row_order():
    p,a,d = fixture_series()
    expected = residuals(p,a,d,frozen_dates=DATES)
    assert residuals(p,list(reversed(a)),list(reversed(d)),frozen_dates=DATES) == expected
    d[0]['phase'] = '3'
    with pytest.raises(ValueError,match='NODE_PHASE_TIME_ALIGNMENT'):
        residuals(p,a,d,frozen_dates=DATES)


def test_duplicate_and_nonfinite_cannot_silently_align():
    p,a,d = fixture_series()
    with pytest.raises(ValueError,match='DUPLICATE_OR_NONFINITE'):
        residuals(p+[p[0]],a,d,frozen_dates=DATES)
    d[0]['voltage_pu'] = float('nan')
    with pytest.raises(ValueError,match='DUPLICATE_OR_NONFINITE'):
        residuals(p,a,d,frozen_dates=DATES)


def test_residual_identity_and_directional_asymmetry():
    rows = residuals(*fixture_series(),frozen_dates=DATES)
    for row in rows:
        assert row['e_total'] == pytest.approx(row['e_model']+row['e_forecast'],abs=1e-12)
        assert min(row['r_up'],row['r_down']) == 0
    assert rows[0]['r_up'] == pytest.approx(.01)
    assert rows[1]['r_down'] == pytest.approx(.002)
    assert max(r['r_up'] for r in rows) != max(r['r_down'] for r in rows)


@pytest.mark.parametrize('q,expected',[(.9,2.7),(.95,2.85),(.975,2.925),(.99,2.97)])
def test_quantile_reproducibility(q,expected):
    assert quantile([3,1,0,2],q) == pytest.approx(expected)
    assert quantile([2,0,1,3],q) == pytest.approx(expected)
    assert quantile([.02],q) == .02


def test_day_worst_directional_separate_from_pointwise():
    rows = residuals(*fixture_series(),frozen_dates=DATES)
    days = day_worst(rows)
    assert days[0]['R_up_day'] == pytest.approx(.01)
    assert days[0]['R_down_day'] == pytest.approx(.002)
    assert days[1]['R_down_day'] == pytest.approx(.004)
    summary = margin_summary(rows)
    assert len(summary) == 8 and {r['q'] for r in summary} == set(QUANTILES)
    assert all(r['IID_claim'] is False for r in summary)


def test_current_005_comparison_and_candidate_band():
    rows = residuals(*fixture_series(),frozen_dates=DATES)
    summary = margin_summary(rows)
    for r in summary:
        assert r['delta_up_minus_current'] == pytest.approx(r['delta_up']-.005)
        assert r['V_lower'] == pytest.approx(.95+r['delta_down'])
        assert r['V_upper'] == pytest.approx(1.05-r['delta_up'])
        assert r['FINAL_MARGIN_ACCEPTED'] is False
    assert summary[0]['current_up_empirical_percentile'] == .75
    assert summary[0]['current_down_empirical_percentile'] == 1
    assert summary[4]['current_up_empirical_percentile'] == .5


def test_s0_s2_feasibility_labels_not_conflated():
    assert feasibility_labels(True,False) == dict(B0_PHYSICALLY_FEASIBLE=True,B0_ROBUST_MARGIN_FEASIBLE=False)
    assert feasibility_labels(None,None) == dict(B0_PHYSICALLY_FEASIBLE=None,B0_ROBUST_MARGIN_FEASIBLE=None)


def test_component_dominance_uses_preregistered_metric():
    r = component_summary(residuals(*fixture_series(),frozen_dates=DATES))
    assert r['dominance_metric'] == 'RMSE' and r['dominant'] == 'e_forecast'


def test_blocked_outputs_do_not_fabricate_day_results():
    verdict = read('FINAL_VERDICT.json')
    assert verdict['classification'] == 'BLOCKED_B0_ACTUAL_AUTHORITY'
    assert verdict['executed_days'] == 0 and verdict['S0_feasible_days'] is None
    assert not list(OUT.glob('DAY_*'))
    assert read('VOLTAGE_MARGIN_CANDIDATES.json')['candidates'] == []
    for name in ('APRIL_RESIDUAL_ALL.csv','VOLTAGE_MARGIN_QUANTILES.csv','APRIL_DATE_MANIFEST.csv'):
        with (OUT/name).open(encoding='utf-8') as f:
            assert list(csv.DictReader(f)) == []


def test_persisted_authority_gate_is_fail_closed():
    audit = read('B0_AUTHORITY_AUDIT.json')
    assert authority_gate(audit)['B0_APRIL_EXECUTION_AUTHORIZED'] is False
    with pytest.raises(ValueError,match='BLOCKED_B0_ACTUAL_AUTHORITY'):
        require_execution(audit,read('APRIL_DATA_AUTHORITY.json'))
    assert read('FINAL_FLAGS.json')['FINAL_MARGIN_ACCEPTED'] is False
