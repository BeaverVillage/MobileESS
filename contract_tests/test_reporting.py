import gurobipy as gp
import numpy as np
from v42_two.reporting import reserve_metrics
from v42_two.contract import aidc_groups,mess_groups
import pytest

def test_reserve_report_is_fixed_plan_arithmetic_and_does_not_change_model():
    m=gp.Model();m.Params.OutputFlag=0;m._two_caps={'A':5}
    for t in range(24,120):
        for name,value in [(f'known[A,{t}]',2),(f'anonymous_GPU[A,{t-24}]',1),
            (f'arrival_target_GPU[A,{t-24}]',3),(f'risk[A,{t}]',2),
            (f'CC4_reserve[A,{t}]',1),(f'RT_reserve[A,{t}]',1),
            (f'CC4_shortfall[A,{t}]',99),(f'RT_shortfall[A,{t}]',99)]:
            m.addVar(lb=value,ub=value,name=name)
    m.update();before=m.Fingerprint
    snapshot=np.asarray(m.getAttr('LB'))
    report=reserve_metrics(m,snapshot)
    assert report['total_minimum_shortfall_for_selected_upstream']==pytest.approx(96*3)
    assert report['raw_solver_total_shortfall']==96*198
    assert report['symmetric_CC4_component']+report['symmetric_Runtime_component']==pytest.approx(96*3)
    assert not report['optimized'] and not report['component_split_scientific']
    assert m.Fingerprint==before
    m.dispose()

def test_unrecognized_objective_authority_fails_closed():
    with pytest.raises(ValueError,match='AUTHORITY'):aidc_groups([('rho',1),('new_contract',2)],[],())
    with pytest.raises(ValueError,match='AUTHORITY'):mess_groups([('rho',1),('weighted_PQ',2)])
