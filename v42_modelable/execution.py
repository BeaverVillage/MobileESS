"""Shared B0 execution guards and residual calculations; no optimizer calls."""
import numpy as np
from v42_april_port.builder import B0_FLAGS, require_b0_physical_presence

def execution_guard(reference_audits):
    if len(reference_audits) != 30 or any(not r['full_reference_ready'] for r in reference_audits):
        raise ValueError('CAPACITY_FEASIBLE_COMMON_REFERENCE_REQUIRED')
    return dict(B0_FLAGS, COMMON_CC4_USED=True)

def residuals(plan, da, dday):
    arrays = [np.asarray(x,float) for x in (plan, da, dday)]
    if any(x.shape != arrays[0].shape or not np.isfinite(x).all() for x in arrays):
        raise ValueError('ALIGNED_FINITE_NODE_PHASE_SLOT_REQUIRED')
    p,d,a=arrays
    em=d-p; ef=a-d; et=a-p
    if not np.allclose(et,em+ef,rtol=0,atol=1e-12): raise ValueError('RESIDUAL_IDENTITY')
    return dict(e_model=em,e_forecast=ef,e_total=et,r_up=np.maximum(0,et),r_down=np.maximum(0,-et))

def b0_sanity(metrics):
    return require_b0_physical_presence(metrics)
