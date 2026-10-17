from types import SimpleNamespace
from unittest.mock import patch
import pytest

from v44_recovery_r022.fresh_performance import live_fresh_scope


def test_fresh_scope_requires_independent_context():
    with pytest.raises(PermissionError,match='INDEPENDENT_FRESH'):
        with live_fresh_scope(SimpleNamespace(_independent_fresh=False)):
            pass


@pytest.mark.parametrize('arm',['B0','B1','B3'])
def test_every_measurement_and_solve_function_is_kept_and_readers_restore(arm):
    from v44.svr12 import scope
    from v44.svr11_ac import SVR11CurrentAC
    with scope():
        from v42_regcontrol import authority
        import v42_voltage_control.integration as integration
        import v42_voltage_control.svr as svr
        oracle=SimpleNamespace(arm=arm,_independent_fresh=True,performance={'verified_history_reuses':0,'legacy_branch_measurement_reuses':0})
        source=authority.source()
        before=(integration.measure_full_network,svr.SeriesSVRCollection.measure,
                integration.PhysicalScenario.persist,source['inventory'],SVR11CurrentAC._state)
        with live_fresh_scope(oracle):
            assert integration.measure_full_network is before[0]
            assert svr.SeriesSVRCollection.measure is before[1]
            assert integration.PhysicalScenario.persist is before[2]
            assert source['inventory'] is not before[3]
        assert source['inventory'] is before[3] and SVR11CurrentAC._state is before[4]


def test_measurement_reuse_is_rejected():
    oracle=SimpleNamespace(_independent_fresh=True,performance={'verified_history_reuses':0})
    with pytest.raises(ValueError,match='FRESH_HISTORY_MEASUREMENT_REUSED'):
        with live_fresh_scope(oracle):
            oracle.performance['verified_history_reuses']+=1
