"""Saved full-size May12 failure; created and run before the verifier repair."""
import gzip,pickle
from pathlib import Path
from v42_pr134_b1.common import read,record
from v42_may12_rescue.policy import OUT

def test_saved_may12_artificial_free_p1_activation_preserves_old_point(monkeypatch,tmp_path):
    r=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')['payload']
    assert record(r['path'])==r
    with gzip.open(r['path'],'rb') as f:p=pickle.load(f)
    import v42_a_stage_canary.phase as phase
    # The rebuilt matrix/descriptor come from actual independently reconstructed
    # May12 data. Avoid another expensive full native static reconstruction.
    monkeypatch.setattr(phase,'build',lambda *a,**kw:p['new'])
    monkeypatch.setattr(phase,'update_graph',lambda data,domains,key,graph:(data,p['old']['ledger']))
    if hasattr(phase,'batch_graphs'):
        monkeypatch.setattr(phase,'batch_graphs',lambda data,domains,selected:(data,p['new']['ledger']))
    new,mapped=phase.activate(p['old'],p['negative'],p['raw']['X'],tmp_path)
    from v42_a_stage_phase1.core import primal_replay
    assert primal_replay(new['compact'],mapped)['PASS']
    assert new['compact'].objective('rho')==p['old']['compact'].objective('rho')
