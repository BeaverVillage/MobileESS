from types import SimpleNamespace as NS
from v42_b2_seed_recovery_v19 import m_stage
from v42_b2_seed_recovery_v19.common import atomic

def test_exhausted_initialization_does_not_launch_duplicate_seed(tmp_path):
    atomic(tmp_path/'INITIALIZATION_FAILURE.json',dict(PASS=False,Native_Runtime=1500.,FULL_MILP_infeasibility_claimed=False))
    point,receipt=m_stage.exhausted_seed(NS(output=tmp_path),NS(used=lambda:1500.),None)
    assert point is None and not receipt['automatic_retry']
    assert not receipt['FULL_MILP_infeasibility_claimed'] and receipt['Native_Runtime']==1500.

def test_frozen_adaptive_wrapper_receives_v19_prepare_and_exhausted_seed(monkeypatch):
    import v42_b2_seed_recovery_v18.m_stage as previous
    from v42_may_campaign_native90 import a_routing
    old=previous.run;request={};budget=object();sentinel=object()
    def rebound(fn,namespace):
        assert fn is old and namespace['prepare'] is m_stage.prepare
        assert namespace['seed_integer'] is m_stage.exhausted_seed
        return lambda r,b,p:sentinel
    monkeypatch.setattr(a_routing,'rebound',rebound)
    assert m_stage.run(request,budget) is sentinel
