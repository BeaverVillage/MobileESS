"""Immutable input preparation happens before any performance clock."""
from .common import *
import numpy as np

def payload(path):
    with np.load(path) as z:
        return (z['x'].copy() if 'x' in z else z['local_values'].copy(),
                z['a'].copy() if 'a' in z else z['master_coefficients'].copy(),
                float(z['c'] if 'c' in z else z['objective']),
                z['axis'].copy() if 'axis' in z else z['original_columns'].copy())

class Snapshot:
    def __init__(self):
        from v42_degen.identity import inputs,signature
        from v42_dw_root.partition import axes
        from v42_dw_resume.audit import prototypes
        from v42_dw_continuation.common import OLD as NATIVE_NAMES
        self.A,self.d,self.B,self.e,*_=inputs()
        self.owner,self.row_owner=axes()
        with np.load(NATIVE_NAMES/'DW_NATIVE_ROW_NAMES.npz') as z:self.native=z['names'].copy()
        self.blocks=prototypes(self.B,self.e,self.owner,self.row_owner,self.native)
        for b in self.blocks:b.CSC=b.B.tocsc()
        self.cp=read(OLD/'DW_CHECKPOINT_LATEST.json');assert len(self.cp['pool'])==1604
        assert signature(self.A,self.d)==read(OLD/'DW_CONTINUATION_BASE_AUDIT.json')['full_matrix_signature']
        with np.load(OLD/self.cp['RMP']['point_file']) as z:
            self.pi=z['pi'].copy();self.alpha=z['alpha'].copy()
        assert hashlib.sha256(self.pi.tobytes()+self.alpha.tobytes()).hexdigest()==self.cp['RMP']['dual_SHA']
        self.pool=[]
        for h in self.cp['pool']:
            p=ROOT/h['file']; assert sha(p)==h['file_SHA']
            unit=int(h['MESS'][-2:])-1;x,a,c,axis=payload(p)
            assert np.array_equal(axis,self.blocks[unit].columns)
            assert self.blocks[unit].column(x)[2]==h['column_SHA']
            self.pool.append(dict(unit=unit,x=x,a=a,c=c,key=h['column_SHA']))

    def master(self, pool):
        from v42_dw_resume.audit import Master
        master=Master(self.B,self.e,self.owner,self.row_owner,self.native)
        for c in pool:master.add(c['unit'],c['x'],c['a'],c['c'],c['key'])
        return master

    def audit(self, master):
        from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
        p=np.zeros(len(self.owner));p[master.columns]=master.model.getAttr('X',master.z)
        for v,c in zip(master.lambdas,master.column_data):p[self.blocks[c['unit']].columns]+=float(v.X)*c['x']
        raw=master.raw_audit(); original=corrected_rows(self.A,self.d,p,False,pure_binary_equalities(self.A,self.d))
        upper=float(self.d['objective']@p+self.d['constant'])
        assert raw['PASS'] and original['PASS'] and abs(upper-master.model.ObjVal)<=1e-6
        return dict(PASS=True,upper=upper,master=raw,full_original=original)

def controlled_columns(snapshot):
    from v42_dw_root.run import exact_rc
    frozen=read(OUT/'CONTROLLED_INPUTS.json');result=[]
    seen={c['key'] for c in snapshot.pool}
    for h in frozen['columns']:
        p=OUT/h['file'];assert sha(p)==h['file_SHA']
        unit=h['unit'];b=snapshot.blocks[unit]
        with np.load(p) as z:x=z['x'].copy();axis=z['axis'].copy()
        assert np.array_equal(axis,b.columns) and b.validate(x,True)['PASS']
        a,c,key=b.column(x);assert key not in seen and key==h['column_SHA'];seen.add(key)
        rc=exact_rc(b,x,snapshot.pi,snapshot.alpha[unit]);assert rc<=-1e-7
        result.append(dict(unit=unit,x=x,a=a,c=c,key=key,true_RC=float(rc)))
    assert len(result)==10
    return result
