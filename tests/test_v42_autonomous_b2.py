from pathlib import Path
from types import SimpleNamespace
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90 import inputs
from v42_autonomous_b2.worker import CANONICAL

def test_provenance_rebound_keeps_original_code_object_and_checks():
    generated=rebound(inputs.generate_b2,dict(inputs.generate_b2.__globals__,ROOT=CANONICAL))
    assert generated.__code__ is inputs.generate_b2.__code__
    assert generated.__globals__['ROOT']==CANONICAL
    assert generated.__globals__['fixed_aidc'] is inputs.fixed_aidc
    assert generated.__globals__['sha'] is inputs.sha
    assert generated.__globals__['read'] is inputs.read

def test_admission_scope_installs_accounting_context_before_native_peer_guard(monkeypatch):
    from v42_autonomous_b2 import worker
    from v42_may_campaign import execution as legacy
    request=dict(manifest_SHA='x',worker_slot=2)
    monkeypatch.setattr(worker,'verify_request',lambda r:dict(valid=True))
    monkeypatch.setattr(worker,'assert_peers',lambda r:(_ for _ in ()).throw(AssertionError('Native only')))
    with worker.worker_scope(request):
        assert legacy._active.get()['worker_slot']==2
        assert legacy._active.get()['manifest']==dict(valid=True)
    assert legacy._active.get() is None
