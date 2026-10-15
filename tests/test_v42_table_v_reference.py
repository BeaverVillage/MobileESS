"""D0 axis and original power equations on named public numeric fixtures."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

from test_v42_table_v_flex_planning import fixture
from v42_integration import table_v_reference as api
from v42_integration.table_v_flex_planning import compile_flex_descriptors


def reference_fixture():
    base,stats,uids=fixture()
    c=compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    c['data'][0]['unknown_nominal_GPU']=[1.]*96
    base['data'][0]['unknown_nominal_GPU']=[1.]*96
    context=dict(base,data=c['data'],tablev_flex=dict(reference_records=c['reference'].assigned,
        reference_sha=c['reference'].reference_sha),
        manifest=dict(base['manifest'],identity=c['identity']))
    grid=SimpleNamespace(power={(s,t):SimpleNamespace(slope=.8,intercept_kw=3.)
        for s in ('A','B') for t in range(96)},idle_kw=.2,swing_kw=.7)
    return context,grid,uids


def test_reference_running_native24_continuation_not_omitted_six_hour_prefix():
    c,g,u=reference_fixture();r=api.reference_arrays(c,g)
    assert r['selected_jobs'][u['running']]['start']==24
    assert r['selected_jobs'][u['running']]['segments']==(('A',24,29),)
    assert r['known_site_GPU']['A'][0]>=1
    assert type(r['reference_service_proof']['PASS']) is bool
    assert r['reference_service_proof']['PASS'] is True


def test_original_affine_PCC_and_fixed_power_factor_equations_exact():
    c,g,u=reference_fixture();r=api.reference_arrays(c,g)
    for site in ('A','B'):
        for t in range(96):
            expected=.8*(.2*8+.7*(r['known_site_GPU'][site][t]+r['nominal_site_GPU'][site][t]))+3.
            assert r['AIDC_P_by_site'][site][t]==expected
        np.testing.assert_array_equal(r['AIDC_Q_by_site'][site],
            np.array(r['AIDC_P_by_site'][site])*np.tan(np.arccos(.95)))


def test_reference_no_E1_intervention_and_CC4_full_mass_carry_conserved():
    c,g,u=reference_fixture();before=deepcopy(c['state']);r=api.reference_arrays(c,g)
    assert c['state']==before and r['FULL_feasible'] is False
    assert r['additional_timeshifting']==r['additional_presite']==r['migration_count']==0
    assert r['CC4_service']['GRID_BLIND_NOMINAL_GPUh']+r['CC4_carryout']['GRID_BLIND_NOMINAL_GPUh']==24.
    assert r['source_B0_B2_reference_identical'] is True


def test_original_reference_current_hold_adds_only_native24_without_service_invention():
    c,g,u=reference_fixture();before=api.reference_arrays(c,g)
    c['data'][3].fixed_gpu[('B',24)]=1
    after=api.reference_arrays(c,g)
    assert after['known_site_GPU']['B'][0]==before['known_site_GPU']['B'][0]+1
    assert after['known_site_GPU']['B'][1:]==before['known_site_GPU']['B'][1:]
    assert after['service_obligations']==before['service_obligations']


def test_unknown_profile_overfull_forecast_mass_fails_instead_of_clipping():
    c,g,u=reference_fixture();c['data'][0]['unknown_nominal_GPU']=[100.]*96
    with pytest.raises(ValueError,match='MASS_EXCEEDS'):
        api.reference_arrays(c,g)
