from v42_cutpass.common import POLICY
from v42_cutpass.monitor import Monitor,root_pass
def test_single_parameter_policy():
    assert POLICY['Threads']==1 and POLICY['DegenMoves']==0 and POLICY['CutPasses']==1 and POLICY['MIPGap']==.005
    assert all(POLICY[k]==1e-8 for k in ('FeasibilityTol','OptimalityTol','IntFeasTol'))
def test_incumbent_does_not_override_600_root_stop():
    monitor=Monitor([]);monitor.solutions.append(dict(time=100,objective=.6))
    state=monitor.state('monotonic_wall_since_optimize',600)
    assert state['incumbent_observed'] and state['termination_requested'] and not root_pass(monitor.times)
def test_late_nonroot_does_not_pass_checkpoint():
    monitor=Monitor([]);monitor.times['first_nonroot']=600.01;assert not root_pass(monitor.times)
    monitor.times['first_nonroot']=600;assert root_pass(monitor.times)
def test_stale_mip_observation_not_exact_600():
    monitor=Monitor([]);monitor.latest=dict(time=570,nodes=0,UB=.7,LB=.5,cuts=2)
    row=monitor.state('monotonic_wall_since_optimize',600)
    assert row['checkpoint_UB'] is None and row['exact_600_UB'] is None and row['last_MIP_observation']['time']==570
