"""Inspect saved incomplete LP vectors, without building or optimizing models."""
from common import *
from run_root import arrays_for

def run(label):
    gp,old=forbid_optimize()
    try:
        folder=OUT/'runs'/label;receipt=read(folder/'RESULT.json')
        assert receipt['status_name']!='OPTIMAL'
        A,d,n=arrays_for(label);original,od,_=load()
        with np.load(folder/'UNRESOLVED_POINT.npz') as z:x=z['x']
        b=x[:n][od['types']=='B']
        report=dict(status=receipt['status_name'],diagnostic_only=True,accepted_as_LB=False,accepted_as_UB=False,raw_primal_objective=float(d['objective']@x+float(d['constant'])),strengthened_relaxed_replay=hc.replay(A,dict(d,types=np.full(A.shape[1],'C')),x,False),original_relaxed_replay=hc.replay(original,dict(od,types=np.full(n,'C')),x[:n],False),fractional_original_binary_count=int(np.count_nonzero(np.minimum(abs(b),abs(1-b))>1e-8)),optimize_calls=0,warning='Not an optimum or proof. Original integer UB remains unchanged.')
        atomic(folder/'UNRESOLVED_POINT_DIAGNOSTIC.json',report);print(json.dumps(report))
    finally:gp.Model.optimize=old

if __name__=='__main__':run(sys.argv[1])
