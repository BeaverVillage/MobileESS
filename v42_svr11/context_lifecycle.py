"""Retire only completed independent model probes; never reuse native state."""
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
    del owners[ctx]
    del CffiApiUtil._ctx_to_util[ctx]
