import numpy as np
import pandas as pd
import pytest
from dayahead.v41.persistence import actual_rows, optimizer_rows, table, verify_table
from dayahead.v41.reserve import diagnostics
from tests.dayahead.test_v41_scalar_interface import fixture


def test_raw_and_actionable_coverage_are_independent_results(tmp_path):
    ctx, _, snapshot = fixture(); snapshot['target_day'] = '2025-05-01'
    snapshot['H4_RAW_R85_B2_GPUh'] = [10.] * 81
    snapshot['H4_ACTIONABLE_RESERVE_GPUh'] = [4.] * 81
    result = actual_rows(tmp_path, snapshot, [5.] * 81)
    frame = verify_table(result['persisted'])
    assert len(frame) == 81
    assert result['raw_H4_coverage'] == 1. and result['actionable_H4_coverage'] == 0.
    assert result['raw_over_GPUh'] == 405. and result['actionable_under_GPUh'] == 81.
    assert result['clipped_GPUh'] == 486.
    assert frame.RAW_R85_B2_GPUh.eq(10.).all() and frame.ACTIONABLE_H4_GPUh.eq(4.).all()
    assert not result['actionable_performance_is_raw_ML_accuracy']


def test_optimizer_persists_81_scalar_constraint_rows(tmp_path):
    ctx, _, snapshot = fixture(); snapshot['target_day'] = '2025-05-01'
    report = diagnostics(snapshot, ctx.capacity, np.ones((96, 2)))
    receipt = optimizer_rows(tmp_path, snapshot, 'a' * 64, report)
    frame = verify_table(receipt)
    assert len(frame) == 81 and frame.snapshot_hash.eq('a' * 64).all()
    np.testing.assert_array_equal(frame.constraint_slack, frame.available_headroom_GPUh + frame.reserve_shortfall_xi_GPUh - frame.ACTIONABLE_H4_GPUh)
    assert frame.constraint_slack.ge(0).all()


def test_saved_rows_cannot_be_replaced_or_silently_repaired(tmp_path):
    path = tmp_path / 'rows.parquet'; expected = pd.DataFrame({'value': [1.]})
    receipt = table(path, expected)
    pd.DataFrame({'value': [2.]}).to_parquet(path, index=False)
    with pytest.raises(ValueError, match='SHA256_DRIFT'):
        verify_table(receipt)
    with pytest.raises(AssertionError):
        table(path, expected)


def test_service_level_uses_085_not_observed_cal_or_exposed_coverage(monkeypatch):
    import dayahead.v41.workload as workload
    residual = list(np.arange(100) / 100.)
    monkeypatch.setattr(workload, 'frozen_history', lambda issue: (residual.copy(), [1.], ['old'], set(range(20))))
    monkeypatch.setattr(workload, 'extend_history', lambda *args: (residual * 4, [], ['new'], set(), []))
    monkeypatch.setattr(workload, 'features', lambda *args: np.zeros((81, 71), dtype='float32'))
    monkeypatch.setattr(workload, 'base_predict', lambda X: (np.ones(81), {'CAL_coverage': .8953, 'EXPOSED_coverage': .8579}))
    result, pool = workload.predict('2025-05-01', None, None)
    assert workload.SERVICE_LEVEL == .85
    # ceil((500+1)*.85)=426, value .85 for five copies of [0,.01,..,.99].
    assert result['H4_calibration_support']['order_rank'] == 426
    assert result['H4_delta85'] == .85
    np.testing.assert_array_equal(result['H4_raw_predictions'], np.full(81, np.expm1(np.log(2) + .85)))
