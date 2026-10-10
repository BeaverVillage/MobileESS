"""Actual native context reclamation without compile, AC or optimization."""
import gc,weakref
import opendssdirect as dss
from dss import CffiApiUtil
import pytest
from v42_svr11.context_lifecycle import retire_completed_probe

def test_completed_probe_registries_and_native_wrappers_are_reclaimed():
    owners=type(dss.dss)._ctx_to_dss;utilities=CffiApiUtil._ctx_to_util
    gc.collect();baseline=(len(owners),len(utilities));refs=[]
    for _ in range(16):
        engine=dss.NewContext();refs.append(weakref.ref(engine))
        # Exercise native clear callbacks with a real circuit but no solve.
        engine.Text.Command('new circuit.lifecycle basekv=4.16 pu=1 phases=3 bus1=a')
        retire_completed_probe(engine);del engine
    gc.collect()
    assert all(r() is None for r in refs)
    assert (len(owners),len(utilities))==baseline

def test_prime_and_nonowned_context_cannot_be_retired():
    with pytest.raises(PermissionError,match='OWNERSHIP_REQUIRED'):retire_completed_probe(dss.dss)
    engine=dss.NewContext();utility=engine._api_util;ctx=utility.ctx
    owners=type(engine)._ctx_to_dss;original=owners[ctx]
    owners[ctx]=object()
    try:
        with pytest.raises(PermissionError,match='OWNERSHIP_REQUIRED'):retire_completed_probe(engine)
    finally:owners[ctx]=original
    retire_completed_probe(engine)
