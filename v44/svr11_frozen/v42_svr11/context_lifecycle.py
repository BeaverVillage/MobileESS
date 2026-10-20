"""Retire only completed independent model probes; never reuse native state."""
import gc,weakref
_completed=[]

def retire_completed_probe(engine):
    # Pinned OpenDSSDirect 0.9.4/DSS-Python registries have weak keys but strong
    # values that retain the same context key through their owner. ClearAll alone
    # therefore leaves every independent probe reachable. Detach only the exact
    # completed owner; CFFI's existing gc(ctx_New(),ctx_Dispose) remains the sole
    # native destructor. No low-level pointer disposal or live-context reuse.
    from dss import CffiApiUtil
    utility=engine._api_util;ctx=utility.ctx;owners=type(engine)._ctx_to_dss
    if (ctx==utility.lib_unpatched.ctx_Get_Prime() or owners.get(ctx) is not engine
        or CffiApiUtil._ctx_to_util.get(ctx) is not utility):
        raise PermissionError('SVR11_PROBE_CONTEXT_OWNERSHIP_REQUIRED')
    engine.Basic.ClearAll()
    # The event manager also strongly owns the CFFI context key. Keep it until
    # the utility destructor has unregistered its callbacks: removing it earlier
    # would make that destructor recreate another manager for the same key.
    _completed.append((ctx,weakref.ref(engine),weakref.ref(utility)))
    del owners[ctx]
    del CffiApiUtil._ctx_to_util[ctx]

def flush_completed_probes():
    """After owner finalization, drop only exact retired callback managers."""
    from dss_python_backend.events import EventCallbackManager
    gc.collect();pending=[];released=0
    for ctx,engine,utility in _completed:
        if engine() is not None or utility() is not None:
            pending.append((ctx,engine,utility));continue
        manager=EventCallbackManager._ctx_to_manager.get(ctx)
        if manager is None or manager.ctx!=ctx:
            raise PermissionError('SVR11_RETIRED_CALLBACK_OWNER_DRIFT')
        manager.unregister_all()
        del EventCallbackManager._ctx_to_manager[ctx]
        released+=1
    _completed[:]=pending
    # CFFI remains the sole native disposer after the last context owner drops.
    return released
