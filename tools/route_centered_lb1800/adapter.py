"""Relocate evidence only; original builders and validators are untouched."""
from pathlib import Path
from functools import lru_cache
from fractions import Fraction as F
import hashlib,json,numpy as np
from tools.minimax_beam1800 import adapter as old
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_route_centered_local_branching1800'
BASE='ca2c050c5481e64d560ed35f5a03e30c9fffb829'
INITIAL_UB=.5421769340794683
HISTORICAL=.5461621302242249
GLOBAL_LB=.46498486997548166
MATERIAL=.5411621302242249
DELTA=1e-5
RAW_REL='docs/v42_b2_minimax_beam1800/calls/002_ROUTE_FIXED/native/RAW_000.npz'
REPLAY_REL='docs/v42_b2_minimax_beam1800/calls/002_ROUTE_FIXED/REPLAY_000.json'
RAW_SHA='6c24f3610df3d02188eb49b2473db43772b971f22dcf30c80c2c9aa492ba728a'
VECTOR_SHA='beb1f93db4bbb1a0092685d78f6079c377b0823b049358e5d8c630f62c5f0952'
v,r,n,g=old.v,old.r,old.n,old.g
write,read,record=old.write,old.read,old.record
old.DOCS=DOCS;old.prior.DOCS=DOCS;old.prior.base.DOCS=DOCS;old.prior.base.configure()
r.ORIGINALS['PR219']=(Path('D:/v42_b2_minimax_beam1800_20261012'),BASE)
guard=old.guard
paths_of=old.current_paths
route_values=old.prior.route_values

def route_spec(case,candidate):
    spec=old.route_spec(case,candidate)
    spec.update(stage='ABLATION',warm_start_compatible=False,
        start_reason='Changed route excludes the unchanged PR219 center; no incompatible MIP start',center_included=False)
    return spec

def restriction(case,center,spec):
    if spec['method']=='ROUTE_FIXED':return old.restriction(case,None,spec)
    low,high=case.d['lower'].copy(),case.d['upper'].copy()
    ids=np.asarray(spec['fixed_route_columns'],dtype=int);vals=np.asarray(spec['fixed_route_values'],dtype=float)
    low[ids]=vals;high[ids]=vals
    assert np.all(low>=case.d['lower']) and np.all(high<=case.d['upper'])
    ham=np.asarray(spec['hamming_columns'],dtype=int)
    coefficients=np.where(center[ham]==1.,-1.,1.);rhs=float(spec['hamming_radius'])-float(np.count_nonzero(center[ham]))
    return low,high,ham,coefficients,rhs,dict(PASS=True,center_always_included=True,all384_modes_free=True,
        route_only_Hamming=True,restricted_ObjBound_is_Global_LB=False,nonroute_bounds_unchanged=True)

def audit(case,center,spec,low,high,output=None):
    if spec['method']=='ROUTE_FIXED':result=old.audit(case,None,spec,low,high)
    else:
        from tools.route_centered_lb1800.proof import neighborhood
        result=neighborhood(case,center,spec,low,high)
    if output:write(output,result)
    return result

def signature(low,high,ham,coefficients,rhs):
    h=hashlib.sha256()
    for x in (low,high,ham,coefficients,np.asarray([rhs])):h.update(np.ascontiguousarray(x).tobytes())
    return h.hexdigest()
