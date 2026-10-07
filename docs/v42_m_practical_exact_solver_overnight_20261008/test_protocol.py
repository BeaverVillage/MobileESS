"""Solver-free authority-boundary and immutable-deadline regression fixtures."""
from practical_support import *
def run():
    tests=[]
    baseline=dict(Status=9,ObjBound=.58,callback_errors=[],exception=None)
    assert native_bound_valid(baseline,True,False,.63,'')['PASS'];tests.append('Full-domain valid native bound eligible')
    assert not native_bound_valid(baseline,True,True,.63,'')['PASS'];tests.append('Restricted bound never global even with TIME_LIMIT')
    assert not native_bound_valid(dict(baseline,ObjBound=.64),True,False,.63,'')['PASS'];tests.append('Native bound contradicting independently validated UB rejected')
    assert not native_bound_valid(baseline,False,False,.63,'')['PASS'];tests.append('Objective/domain identity failure rejected')
    assert not native_bound_valid(dict(baseline,Status=12),True,False,.63,'')['PASS'];tests.append('NUMERIC status rejected')
    assert not native_bound_valid(dict(baseline,callback_errors=['failure']),True,False,.63,'')['PASS'];tests.append('Callback error cannot certify LB')
    assert not native_bound_valid(baseline,True,False,.63,'Warning: unscaled primal violation = 0.1')['PASS'];tests.append('Severe numerical warning rejected')
    assert native_bound_valid(baseline,True,False,.63,'Warning: Model contains large matrix coefficient range')['PASS'];tests.append('Advisory coefficient range is recorded but is not itself solver failure')
    clock=read(OUT/'IMMUTABLE_DEADLINE.json');start=datetime.fromisoformat(clock['task_start_UTC'])
    assert remaining(0,start)==28800 and remaining(900,start)==27900
    assert deadline().isoformat()==clock['deadline_UTC'];tests.append('Immutable task receipt start gives exactly 28800s, reserve subtracts without resetting')
    from native_runner import neighborhood
    A,d,_=hc.load()
    with np.load(OLD/'BEST_VALID_POINT.npz') as z:x=z['x']
    B,e,free,fixed,weights,rhs=neighborhood(A,d,x,64)
    assert hc.replay(A,d,x,True)['PASS'] and hc.replay(B,e,x,True)['PASS']
    assert len(free)==2100 and len(fixed)==7222 and B.shape[0]==A.shape[0]+1
    assert np.array_equal(e['objective'],d['objective']) and verifier.verify(ROOT,e)['PASS']
    assert (B[:A.shape[0]]!=A).nnz==0 and np.array_equal(e['lower'][d['types']=='C'],d['lower'][d['types']=='C'])
    assert float(weights@x[free]-rhs)==-64
    tests.append('H64 exact prior axes, H=0 center, original matrix/objective and continuous bounds retained')
    atomic(OUT/'PROTOCOL_TESTS.json',dict(PASS=True,optimize_calls=0,tests=tests,UTC=stamp()))
    print('PROTOCOL_TESTS_PASS',len(tests),'OPTIMIZE_0')
if __name__=='__main__':run()
