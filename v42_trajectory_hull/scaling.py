"""Exact power-of-two row scaling; no coefficient deletion or tolerance changes."""
import numpy as np


def row_scaling(A, rhs):
    A=A.tocsr()
    exponents=np.zeros(A.shape[0],dtype=np.int32)
    for i in np.flatnonzero(np.diff(A.indptr)):
        a,b=A.indptr[i:i+2]
        minimum=float(np.min(abs(A.data[a:b])))
        if minimum < 1e-13:
            # Lift beyond 2^-40 using an integer exponent, never add epsilon.
            exponents[i]=max(0,-40-int(np.frexp(minimum)[1]-1))
    scaled=A.copy()
    scaled.data=np.ldexp(A.data,np.repeat(exponents,np.diff(A.indptr)))
    scaled_rhs=np.ldexp(np.asarray(rhs),exponents)
    if not np.isfinite(scaled.data).all() or not np.isfinite(scaled_rhs).all():
        raise ValueError('ROW_SCALING_OVERFLOW')
    restored=np.ldexp(scaled.data,-np.repeat(exponents,np.diff(A.indptr)))
    if restored.tobytes()!=A.data.tobytes() or np.ldexp(scaled_rhs,-exponents).tobytes()!=np.asarray(rhs).tobytes():
        raise ValueError('POWER_TWO_SCALING_NOT_BIT_REVERSIBLE')
    if np.min(abs(scaled.data),initial=np.inf)<1e-13 or np.max(abs(scaled.data),initial=0)>1e8:
        raise ValueError('ROW_SCALING_UNSAFE_COEFFICIENT_RANGE')
    if np.max(abs(scaled_rhs),initial=0)>2**21:
        raise ValueError('ROW_SCALING_UNSAFE_RHS_RANGE')
    return scaled,scaled_rhs,exponents


def restore_primal(point):
    """S=I, so objective/bounds/primal variables do not change."""
    return np.asarray(point).copy()


def restore_dual(dual,exponents):
    """Original-row multipliers are R^T*y_solver for A_solver=R*A."""
    result=np.ldexp(np.asarray(dual),np.asarray(exponents))
    if not np.isfinite(result).all():
        raise ValueError('RESTORED_DUAL_NOT_FINITE')
    return result
