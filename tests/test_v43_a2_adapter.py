"""Selective source boundaries only; no real A2 optimization claim."""
from copy import deepcopy
import ast
import numpy as np
import pytest

from v43_a2.adapter import fixed_grid,routed_function,source_tree,require_m1
from v43_actual.vendor.policy import digest


def plan():
    p=dict(case_sha=digest('NAMED_M1_FIXTURE'),P_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch',
        time_axis=list(range(96)),P_by_site={'STA01':[3.]*96},Q_by_site={'STA01':[-2.]*96},
        P_kW={'MESS01':[3.]*96},Q_kvar={'MESS01':[-2.]*96})
    p['plan_sha']=digest(p);return p


def test_fixed_m1_changes_only_stage_and_original_mess_constant_boundary():
    import v42_boundary.model as original
    function,changes=fixed_grid(original,plan())
    assert changes==dict(stage=2,control=1)
    lookup=function.__globals__['_v43_fixed_M1_control']
    assert lookup('mess_p_kw[STA01]',41)==3.
    assert lookup('mess_q_kvar[STA01]',41)==-2.
    with pytest.raises(ValueError,match='UNSUPPORTED'):lookup('aidc_load_kw[STA01]',41)
    original_tree=source_tree(original,'planning_grid')
    # Its AIDC/CC4 variable constructors and full objective expressions remain
    # structurally identical. The complete source is pinned by execution freeze.
    calls=[ast.dump(n) for n in ast.walk(original_tree) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr in ('addVar','addConstr')]
    source=function.__code__.co_names
    assert len(calls)>0 and 'bind_forecast' in source and 'bind_headroom' in source and 'add_grid' in source


def test_materializer_validates_actual_fixed_m1_instead_of_zero_b1_template():
    import v42_may_campaign_native90.a_stage as original
    ns=dict(original.__dict__);_,changes=routed_function(original,'_planning',ns,plan())
    assert changes['planning_check']==1 and changes['materialized_mess']==2


def test_a2_paths_are_honest_b3_and_never_accept_b1_or_may02():
    import v42_may_campaign_native90.a_stage as original
    ns=dict(original.__dict__);function,_=routed_function(original,'_paths',ns,plan())
    request=dict(day='2025-05-01',arm='B3',input_folder='D:/INPUT',output='D:/NEW_A2')
    assert function(request)[0]=='2025-05-01'
    with pytest.raises(ValueError):function(dict(request,arm='B1'))
    with pytest.raises(ValueError,match='MAY01_ONLY'):function(dict(request,day='2025-05-02'))


def test_a2_rejects_missing_full_or_changed_m1_before_grid_binding():
    good=dict(arm='B3',stage='M1',FULL_feasible=True,upper=dict(FULL_validated=True),
        case_sha=plan()['case_sha'],MESS_plan=plan())
    assert require_m1(good)['plan_sha']==good['MESS_plan']['plan_sha']
    with pytest.raises(ValueError):require_m1(dict(good,FULL_feasible=False))
    bad=deepcopy(good);bad['MESS_plan']['P_by_site']['STA01'][0]=7.
    with pytest.raises(ValueError,match='SHA_OR_CASE'):require_m1(bad)
