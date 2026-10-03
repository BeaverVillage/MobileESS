"""Exact denominator-only change of existing affine current responses."""
import copy
import numpy as np
from .authority import current_authority,denominators,digest,require_certificate
from .common import SCHEMA

def normalized_response(names,constant,matrix,old_limits):
    old=np.asarray(old_limits,float);names=tuple(map(str,names));expected=denominators(names,old=True)
    if old.shape!=expected.shape or not np.array_equal(old,expected):
        raise ValueError('LEGACY_CURRENT_DENOMINATOR_SOURCE_MISMATCH')
    new=denominators(names);factor=old/new;mask=np.array([n.lower().startswith('transformer.') for n in names])
    cc=np.array(constant,copy=True);cm=np.array(matrix,copy=True)
    cc[...,mask]*=factor[mask];cm[...,mask]*=factor[mask]
    return cc,cm,new

def bind_coefficient(c,old_limits):
    updated=copy.copy(c)
    updated.current_constant,updated.current_matrix,updated.current_denominators_A=normalized_response(
        c.branch_names,c.current_constant,c.current_matrix,old_limits)
    updated.transformer_current_contract=SCHEMA
    updated.transformer_current_authority_sha256=current_authority()['transformer_current_authority_sha256']
    updated.coefficient_sha256=digest(dict(old_coefficient_SHA=c.coefficient_sha256,
        current_authority=updated.transformer_current_authority_sha256,schema=SCHEMA))
    return updated

def require_coefficient(c,authority=None):
    # Small synthetic row-geometry fixtures have no compiled feeder identity.
    # Every real feeder response is authority-bound; unbound IEEE123 rows fail.
    physical=any(n.lower().startswith(('transformer.reg','transformer.idc_','transformer.mess_','transformer.xfm')) for n in c.branch_names)
    if hasattr(c,'transformer_current_contract') or physical:
        require_certificate(vars(c))
        if not np.array_equal(c.current_denominators_A,denominators(c.branch_names)):
            raise ValueError('PLANNING_ACTUAL_CURRENT_DENOMINATOR_MISMATCH')
        if authority is not None and getattr(authority,'transformer_current_authority_sha256',None)!=c.transformer_current_authority_sha256:
            raise ValueError('GRID_CURRENT_AUTHORITY_MISMATCH')
    return True
