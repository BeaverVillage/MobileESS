"""Selected legacy CG mechanics; globals are bound by the stage-local adapter.
No old M1 inputs, checkpoints, authority or numerical thresholds are imported.
"""
import numpy as np
import hashlib
from .case import file_sha as sha

def next_smoothing_weight(current,d_norm):
    if d_norm>.50:return max(.10,.5*current)
    if d_norm>.10:return current
    return min(.80,1.25*current)

def smooth_snapshot(self,dual):
    pi,conv,true_key,file=dual;weight=self.smooth_weight;first=self.smooth_pi is None
    if first:self.smooth_pi=pi.copy();self.smooth_conv=conv.copy()
    else:self.smooth_pi=weight*pi+(1-weight)*self.smooth_pi;self.smooth_conv=weight*conv+(1-weight)*self.smooth_conv
    change=0. if self.last_true_pi is None else float(np.linalg.norm(pi-self.last_true_pi,np.inf)/max(1e-12,np.linalg.norm(self.last_true_pi,np.inf)))
    next_weight=weight if first else next_smoothing_weight(weight,change);key=hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest();file=f'SMOOTHED_DUAL_{self.current_round:04d}.npz';np.savez_compressed(OUT/file,pi=self.smooth_pi,alpha=self.smooth_conv)
    self.smooth_key=key;self.smooth_file=file;self.smooth_weight=next_weight
    self.smoothing_rows.append(dict(round=self.current_round,true_dual_SHA=true_key,smoothed_dual_SHA=key,smooth_file=file,alpha_used=weight,alpha_next=next_weight,first_no_distortion=first,normalized_true_change=change,accepted=0,proposed=0,rejected_after_true_RC=0))
    return file,key

def add(self,r,pi,alpha):
    assert r['type']=='DISCOVERY' and r['valid_negative'] and r['rc_inc']<=DISCOVERY_RC
    m=r['unit'];b=self.blocks[m]
    with np.load(OUT/r['point_file']) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
    assert b.validate(x,True)['PASS'] and r['full_original_local']['PASS'];rc=float(exact_rc(b,x,pi,alpha[m]));assert abs(rc-r['rc_inc'])<=EPS
    a,c,key=b.column(x)
    if key in self.seen[m]:return False
    exact,error=b.exact_coupling(x,a);assert error<=1e-12
    n=self.column_id;self.column_id+=1;file=f'columns/COLUMN_{n:06d}_{b.unit}.npz';ix=sorted(i for i,v in exact.items() if v)
    np.savez_compressed(OUT/file,x=x,axis=b.columns,a=a,c=np.array(c),exact_rows=ix,exact_numerators=np.array([str(exact[i].numerator) for i in ix]),exact_denominators=np.array([str(exact[i].denominator) for i in ix]))
    (self.persistent_adapter.append([dict(unit=m,x=x,a=a,c=c,key=key)]) if self.persistent_selected else self.master.add(m,x,a,c,key));self.seen[m].add(key);self.columns.append(dict(number=n,round=self.current_round,MESS=b.unit,file=file,file_SHA=sha(OUT/file),SHA256=key,pricing_call=r['call'],rc_inc=rc,label='VALID_NEGATIVE_DISCOVERY_COLUMNS',pricing_optimum_claimed=False,native_status=r['native_status']))
    return True
