"""Actual native context reclamation without compile, AC or optimization."""
import gc,weakref
import opendssdirect as dss
from dss import CffiApiUtil
import pytest
from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes
from dss_python_backend.events import EventCallbackManager

def test_completed_probe_registries_and_native_wrappers_are_reclaimed():
    owners=type(dss.dss)._ctx_to_dss;utilities=CffiApiUtil._ctx_to_util
    flush_completed_probes();gc.collect()
    baseline=(len(owners),len(utilities),len(EventCallbackManager._ctx_to_manager));refs=[];contexts=[]
    for _ in range(16):
        engine=dss.NewContext();refs.append(weakref.ref(engine));contexts.append(weakref.ref(engine._api_util.ctx))
        # Exercise native clear callbacks with a real circuit but no solve.
        engine.Text.Command('new circuit.lifecycle basekv=4.16 pu=1 phases=3 bus1=a')
        retire_completed_probe(engine);del engine
    flush_completed_probes();gc.collect()
    assert all(r() is None for r in refs)
    assert all(r() is None for r in contexts)
    assert (len(owners),len(utilities),len(EventCallbackManager._ctx_to_manager))==baseline

def test_live_completed_owner_waits_for_finalization():
    engine=dss.NewContext();ctx=engine._api_util.ctx
    retire_completed_probe(engine);flush_completed_probes()
    assert ctx in EventCallbackManager._ctx_to_manager
    del engine
    flush_completed_probes()
    assert ctx not in EventCallbackManager._ctx_to_manager

def test_prime_and_nonowned_context_cannot_be_retired():
    with pytest.raises(PermissionError,match='OWNERSHIP_REQUIRED'):retire_completed_probe(dss.dss)
    engine=dss.NewContext();utility=engine._api_util;ctx=utility.ctx
    owners=type(engine)._ctx_to_dss;original=owners[ctx]
    owners[ctx]=object()
    try:
        with pytest.raises(PermissionError,match='OWNERSHIP_REQUIRED'):retire_completed_probe(engine)
    finally:owners[ctx]=original
    retire_completed_probe(engine)
