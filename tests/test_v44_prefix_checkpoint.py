import pytest
from validation_tools.actual_performance import verify_prefix_checkpoint as experiment


@pytest.mark.parametrize('kind', ['json', 'dss'])
def test_export_import_loses_real_native_regcontrol_queue_even_with_clock_restored(kind):
    source = experiment.prefix()
    before = experiment.state(source)
    saved = experiment.exports(source)
    restored = experiment.restore(kind, saved[kind])
    try:
        assert before['queue'][0]['device'] == 'ctl'
        assert restored.Solution.DblHour()*3600 == before['clock_seconds']
        assert experiment.queue(restored) == []
        assert experiment.state(source) == before
    finally:
        source.Basic.ClearAll()
        restored.Basic.ClearAll()


@pytest.mark.parametrize('kind', ['json', 'dss'])
def test_missing_pending_action_changes_voltage_acceptance_at_original_095_limit(kind):
    source = experiment.prefix()
    saved = experiment.exports(source)
    restored = experiment.restore(kind, saved[kind])
    try:
        experiment.settle(source, 47, 13000)
        experiment.settle(restored, 47, 13000)
        reference, proposed = experiment.state(source), experiment.state(restored)
        assert reference['voltage_only_PASS'] is True
        assert proposed['voltage_only_PASS'] is False
        assert experiment.compare(reference, proposed)['physical_match'] is False
    finally:
        source.Basic.ClearAll()
        restored.Basic.ClearAll()
