import numpy as np
from actual_controller import *
a=Limits(300,400,440,1080,.95,.95,.25)
def result(p,q):return dict(converged=True,v=np.array([1.]),ipu=np.array([.99+max(-p[0],0)*.002]),kva=np.array([.2]),taps=[])
def qonly(ev,q,lo,hi,q_da=None):return q,ev(q),{'status':'ROBUST_Q_ONLY_UNRESOLVED'}
c=Controller(a,[760],qonly)
p,q,r,e=c.step(slot=0,p_da=np.array([-20.]),q_da=np.array([0.]),connected=[True],travel_energy=[0.],evaluate=result)
assert ac_feasible(r) and -5.00001<=p[0]<=-4.999,'MINIMAL_CHARGING_CURTAILMENT'
debt=c.shadow-c.energy;assert debt[0]>0
def headroom(p,q):return dict(converged=True,v=np.array([1.]),ipu=np.array([.5]),kva=np.array([.2]),taps=[])
p,q,r,e=c.step(slot=1,p_da=np.array([-20.]),q_da=np.array([0.]),connected=[True],travel_energy=[0.],evaluate=headroom)
assert p[0]<-20 and np.max(np.abs(c.energy-c.shadow))<1e-6,'CAUSAL_RECOVERY'
assert e['future_actual_rows_exposed']==0
c=Controller(a,[760],qonly)
p,q,r,e=c.step(slot=0,p_da=np.array([-20.]),q_da=np.array([0.]),connected=[False],travel_energy=[0.],evaluate=headroom)
assert p[0]==q[0]==0 and c.energy[0]==760,'DISCONNECTION'
print('PASS: minimum charging curtailment; causal recovery; frozen disconnected state')
