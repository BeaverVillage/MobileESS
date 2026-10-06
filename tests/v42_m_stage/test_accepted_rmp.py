from types import SimpleNamespace
from v42_m_stage_root.accepted import accepted_rmp
from v42_m_stage_root.integration import Integration

def test_native_optimal_but_rejected_dual_cannot_replace_last_audited_point():
    valid=dict(status=2,point_file='accepted.npz',point_SHA='saved-point',dual_SHA='true-dual',objective=.57)
    rejected=dict(status=2,point_file=None,dual_SHA=None,objective=None)
    experiment=SimpleNamespace(rmps=[valid,rejected],initial_rmp=valid)
    assert Integration.authority_rmp(experiment) is valid
    assert accepted_rmp(valid) and not accepted_rmp(rejected)
    assert Integration.authority_rmp(SimpleNamespace(rmps=[rejected],initial_rmp=valid)) is valid
