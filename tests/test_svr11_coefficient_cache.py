"""Exercise all96 values, archive-read counts and detached slot ownership."""
from collections import Counter
from types import SimpleNamespace
import ast
from pathlib import Path
import numpy as np
import pytest
from v42_svr11 import model

def predecessor_loader():
    p=Path(r'D:\v42_svr11_epoch06_20261011\v42_svr11\model.py')
    fn=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='load_coefficients')
    code=ast.Module(body=[fn],type_ignores=[]);scope=dict(model.__dict__)
    exec(compile(ast.fix_missing_locations(code),str(p),'exec'),scope)
    return scope['load_coefficients']

def test_cached_archive_read_once_and_bitwise_equal_detached_slots(monkeypatch):
    from v42_thermal import authority
    rng=np.random.default_rng(11);axis={f:rng.normal(size=(96,3,2)) for f in model.FIELDS}
    axis.update(branch_names=np.array(['line.l1::1','transformer.reg1a::1']),
        control_names=np.array(['PCC_P::STA01']),rating_a=np.array([400.,763.323673207438]),
        transformer_ratings=np.array([np.nan,5000.]),anchor_control=rng.normal(size=(96,3)))
    reads=Counter()
    class Archive:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def __getitem__(self,key):reads[key]+=1;return axis[key].copy()
    monkeypatch.setattr(model.np,'load',lambda *args,**kw:Archive())
    monkeypatch.setattr(model,'active',lambda:{'execution_SHA':'current'})
    monkeypatch.setattr(model,'record',lambda p:{'path':p,'sha256':'same'})
    monkeypatch.setattr(authority,'denominators',lambda names:axis['rating_a'].copy())
    monkeypatch.setattr(authority,'current_authority',lambda:{'transformer_current_authority_sha256':'thermal'})
    cert=dict(day='2025-05-03',source_SHA='current',outputs={'planning_coefficients':{'path':'fixture','sha256':'same'}})
    old=predecessor_loader()(cert,cert['day']);old_reads=reads.copy();reads.clear()
    new=model.load_coefficients(cert,cert['day'])
    assert all(old_reads[f]==96 and reads[f]==1 for f in model.FIELDS+('anchor_control',))
    for a,b in zip(old,new):
        assert a.slot==b.slot and a.branch_names==b.branch_names and a.control_names==b.control_names
        assert a.transformer_ratings==b.transformer_ratings and a.coefficient_sha256==b.coefficient_sha256
        for f in model.FIELDS+('anchor','current_denominators_A'):
            assert np.array_equal(getattr(a,f),getattr(b,f))
        for f in model.FIELDS:assert not np.shares_memory(getattr(b,f),axis[f])
    first=new[0].voltage_matrix.copy();new[1].voltage_matrix[:]=0
    assert np.array_equal(new[0].voltage_matrix,first)

def test_cache_does_not_remove_source_binding(monkeypatch):
    monkeypatch.setattr(model,'active',lambda:{'execution_SHA':'new'})
    with pytest.raises(PermissionError,match='EPOCH_DRIFT'):
        model.load_coefficients({'day':'2025-05-03','source_SHA':'old'},'2025-05-03')

def test_review_accepts_only_exact_read_cache_not_model_math():
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    from reuse_svr11_completed import normalized_reviewed_model
    old=Path(r'D:\v42_svr11_epoch06_20261011\v42_svr11\model.py').read_text()
    new=Path(model.__file__).read_text()
    assert normalized_reviewed_model(old)==normalized_reviewed_model(new)
    assert normalized_reviewed_model(old)!=normalized_reviewed_model(new.replace('(plus[k]-minus[k])/(2*d)','(plus[k]-minus[k])/d'))
    with pytest.raises(ValueError,match='UNREVIEWED_COEFFICIENT_CACHE'):
        normalized_reviewed_model(new.replace('cached={f:z[f]', 'cached={f:z[f]*2'))
