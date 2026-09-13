"""Fresh IEEE8500 data in the original 60-control coefficient interface."""
import hashlib
from functools import lru_cache
import numpy as np
from electrical_engine import H,read,NAMES
from dayahead.v28r2.electrical_subproblem import SlotCoefficients,anchored_polygon_parameters,anchored_polygon_loading
AX=read(H/'AXES.json');NL=len(AX['line']);NT=len(AX['tx']);NW=len(AX['winding']);N=NL+NT+NW
def branch(label,kind):
    p=label.split('|');name=p[0].lower()
    return name+'::'+p[1]+'_'+(p[-1] if kind!='winding' else 'kva')
BRANCHES=tuple([branch(x,'line') for x in AX['line']]+[branch(x,'tx') for x in AX['tx']]+[branch(x,'winding') for x in AX['winding']])
assert len(set(BRANCHES))==N
def raw(t):
    with np.load(H/'coefficients'/f'slot_{t:02}'/'COEFFICIENTS.npz',allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def magnitude_gradient(anchor,jac):
    norm=np.abs(anchor)
    return np.divide(np.real(jac*np.conj(anchor)[None,:]),norm[None,:],out=np.zeros(jac.shape,float),where=norm[None,:]>0)
def build(t):
    z=raw(t);x=z['x'];a=np.r_[z['line'],z['tx'],z['S']];j=np.concatenate([z['line_J'],z['tx_J'],z['S_J']],axis=1)
    imag=np.r_[np.abs(z['line']),np.abs(z['tx']),np.zeros(NW)]
    ji=np.concatenate([magnitude_gradient(z['line'],z['line_J']),magnitude_gradient(z['tx'],z['tx_J']),np.zeros((60,NW))],axis=1)
    constant=a-x@j
    return SlotCoefficients(t,NAMES,BRANCHES,x,z['v2']-x@z['v2_J'],z['v2_J'],imag-x@ji,ji,constant.real,constant.imag,j.real.T,j.imag.T,tuple(np.r_[np.ones(NL+NT),AX['winding_rating_kVA']]),tuple([None]*(NL+NT)+AX['winding_rating_kVA']),hashlib.sha256((H/'coefficients'/f'slot_{t:02}'/'COEFFICIENTS.npz').read_bytes()).hexdigest())
class Coefficients:
    """Bounded cache preserves full axes and exact nonzero values."""
    def __len__(self):return 96
    def __iter__(self):
        for t in range(96):yield self[t]
    @lru_cache(maxsize=2)
    def __getitem__(self,t):
        if not 0<=t<96:raise IndexError(t)
        return build(t)
def predictions(c,x):
    v=np.sqrt(c.voltage_constant+c.voltage_matrix.T@x)
    p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
    return dict(voltage=v,line=anchored_polygon_loading(c,x)[:NL],tx=np.hypot(p[NL:NL+NT],q[NL:NL+NT]),winding=np.hypot(p[NL+NT:],q[NL+NT:])/np.asarray(AX['winding_rating_kVA']))
