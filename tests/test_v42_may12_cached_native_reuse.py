from types import SimpleNamespace
import numpy as np
import pytest
import v42_may12_rescue.native as n
from v42_pr134_b1.common import atomic,record

def prepare(tmp_path,monkeypatch):
    monkeypatch.setattr(n,'OUT',tmp_path)
    import v42_a_stage_acceptance.native as old
    def init(self,b,day):
        self.calls=[];self.native_seconds=0.;self.budget=b
    monkeypatch.setattr(old.Native,'__init__',init)
    folder=tmp_path/'PRICE/B/actual';folder.mkdir(parents=True)
    path=folder/'raw.npz';np.savez(path,X=np.array([1.]),Pi=np.array([0.]),RC=np.array([0.]))
    atomic(folder/'MODEL_IDENTITY.json',dict(original_snapshot_sha256='same'))
    rec=dict(status=2,raw_attributes=record(path),model_identity=record(folder/'MODEL_IDENTITY.json'),native_seconds=.77,Work=1.)
    atomic(folder/'NATIVE_RESULT.json',rec)
    atomic(tmp_path/'NEW_NATIVE_CALLS.json',dict(calls=[dict(rec,folder=str(folder))],actual_Runtime=.77))
    native=n.create();native.verify=lambda:True
    return native,folder,SimpleNamespace(fingerprint=lambda:'same')

def test_completed_oracle_is_reused_without_recharging_budget(tmp_path,monkeypatch):
    native,folder,snapshot=prepare(tmp_path,monkeypatch)
    rec,raw=native.solve(snapshot,folder,'LOCAL_PRICING')
    assert rec['status']==2 and raw['X'][0]==1
    assert native.native_seconds==.77 and native.budget.used==.77 and len(native.calls)==1

def test_reuse_rejects_different_model(tmp_path,monkeypatch):
    native,folder,snapshot=prepare(tmp_path,monkeypatch)
    snapshot.fingerprint=lambda:'different'
    with pytest.raises(ValueError):native.solve(snapshot,folder,'LOCAL_PRICING')

def test_reuse_rejects_raw_byte_corruption(tmp_path,monkeypatch):
    native,folder,snapshot=prepare(tmp_path,monkeypatch)
    (folder/'raw.npz').write_bytes(b'corrupt')
    with pytest.raises(ValueError):native.solve(snapshot,folder,'LOCAL_PRICING')
