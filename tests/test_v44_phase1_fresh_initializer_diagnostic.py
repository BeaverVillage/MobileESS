import inspect
from pathlib import Path
import pytest
import v44_recovery_r024b
from v44.common import read, record
from v44_recovery_r024b.adaptive_pricing import AdaptivePricing
from validation_tools.actual_performance.phase1_fresh_init_fix import fixed_fresh_initializer


CAMPAIGN = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
M1 = CAMPAIGN / '2025-05-01/B3/attempt002/M1/RESULT.json'


def test_real_fresh_a2_m1_initialization_reproduces_original_error_and_repairs_it(tmp_path):
    before = record(inspect.getfile(AdaptivePricing))
    with pytest.raises(UnboundLocalError, match='read'):
        AdaptivePricing(tmp_path, {'M1_result': record(M1)})
    with fixed_fresh_initializer(tmp_path):
        for value in (str(M1), record(M1)):
            fresh = AdaptivePricing(tmp_path, {'M1_result': value})
            assert fresh.plan == read(M1)['MESS_plan']
            assert fresh.round == 0 and fresh.feedback == [] and fresh.visited == {}
    assert record(inspect.getfile(AdaptivePricing)) == before
    with pytest.raises(UnboundLocalError, match='read'):
        AdaptivePricing(tmp_path, {'M1_result': record(M1)})


def test_existing_checkpoint_exploration_history_is_unchanged(tmp_path):
    parent = record(Path('D:/MobileESS_V44/development/r024b/current_continuation/ADAPTIVE_PARENT.json'))
    request = {'r024b_adaptive_parent': parent, 'M1_result': record(M1)}
    original = AdaptivePricing(tmp_path, request)
    with fixed_fresh_initializer(tmp_path):
        repaired = AdaptivePricing(tmp_path, request)
    for field in ('feedback', 'visited', 'round', 'last_full', 'previous', 'plan'):
        assert getattr(repaired, field) == getattr(original, field)


def test_fix_does_not_change_pricing_or_gain_decisions(tmp_path):
    methods = ('plan_classes', 'observe', 'price')
    before = {name: getattr(AdaptivePricing, name) for name in methods}
    with fixed_fresh_initializer(tmp_path):
        assert all(getattr(AdaptivePricing, name) is function for name, function in before.items())
