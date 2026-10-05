"""Pricing-only input audit without loading 1,604 dense master projections."""
from .common import *
import numpy as np

def load():
    from v42_degen.identity import inputs
    from v42_dw_root.partition import axes
    from v42_dw_resume.audit import prototypes
    from v42_dw_continuation.common import OLD as NATIVE_NAMES
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(NATIVE_NAMES/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names'].copy()
    blocks=prototypes(B,e,owner,row_owner,native)
    for b in blocks:b.CSC=b.B.tocsc()
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json')
    with np.load(OLD/cp['RMP']['point_file']) as z:pi=z['pi'].copy();alpha=z['alpha'].copy()
    seeds=[]
    for unit in range(4):
        h=next(c for c in reversed(cp['pool']) if c['MESS']==f'MESS{unit+1:02d}')
        with np.load(ROOT/h['file']) as z:seeds.append((z['x'] if 'x' in z else z['local_values']).copy())
    return blocks,cp,pi,alpha,seeds
