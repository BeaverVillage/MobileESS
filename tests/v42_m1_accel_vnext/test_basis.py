import gurobipy as gp
import pytest
from v42_m1_accel_vnext.basis import BasisSession
from v42_m1_accel_vnext.native_state import classify

def toy(costs):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    for p in ('FeasibilityTol','OptimalityTol','IntFeasTol'):m.setParam(p,1e-8)
    x=m.addVars(len(costs), obj=costs)
    m.addConstr(gp.quicksum(x.values())==1, name='conv')
    m.addConstr(gp.quicksum((i+1)*x[i] for i in x)>=2, name='coupling')
    m.optimize();return m

def test_three_exact_append_iterations():
    costs=[5.,4.,6.];m=toy(costs);session=BasisSession(m);session.capture()
    for cost in [3.,2.,1.]:
        costs.append(cost)
        m.addVar(obj=cost,column=gp.Column([1.,float(len(costs))],m.getConstrs()))
        receipt=session.restore();m.optimize();cold=toy(costs)
        assert receipt['new_nonbasic_columns']==1
        assert abs(m.ObjVal-cold.ObjVal)<1e-10
        assert (m.getA()!=cold.getA()).nnz==0
        session.capture();cold.dispose()
    m.dispose()

def test_axis_change_rejected():
    m=toy([5.,4.]);s=BasisSession(m);s.capture();m.addConstr(m.getVars()[0]<=1,name='new')
    with pytest.raises(ValueError,match='axis'):s.restore()
    m.dispose()

def observation(source,line,name='optimize'):
    return classify(dict(pid=7,native_maps=['gurobi130.dll']),
        [dict(pid=7,thread_id=8,frames=[dict(filename='worker.py',line=line,name=name)])],lambda _:source)

def test_proven_native_subclass():
    src='import gurobipy as gp\noriginal=gp.Model\nclass GuardedModel(original):\n def optimize(self):\n  return super().optimize()\n'
    assert observation(src,5)['classification']=='CONFIRMED_FOREIGN_NATIVE_SOLVE'

def test_python_super_not_native():
    src='class GuardedModel(Scheduler):\n def optimize(self):\n  return super().optimize()\n'
    assert observation(src,3)['optimize_state']=='UNCONFIRMED'

def test_import_not_native():
    assert observation('import gurobipy as gp\n',1)['optimize_state']=='UNCONFIRMED'

def test_opendss_real_FFI_wrapper_is_live_native_evidence():
    source='def Solve(self):\n self._check_for_error(self._lib.Solution_Solve())\n'
    stack=[dict(pid=7,thread_id=8,frames=[dict(filename='C:/Python/Lib/site-packages/opendssdirect/Solution.py',line=2,name='Solve')])]
    r=classify(dict(pid=7,native_maps=['dss_capi.dll']),stack,lambda _:source)
    assert r['classification']=='CONFIRMED_FOREIGN_NATIVE_SOLVE'
    assert r['live_call_proofs'][0]['call']=='Solution_Solve'

def test_opendss_mock_wrapper_not_installed_native_library():
    source='def Solve(self):\n self._check_for_error(self._lib.Solution_Solve())\n'
    stack=[dict(pid=7,thread_id=8,frames=[dict(filename='tests/fake_solution.py',line=2,name='Solve')])]
    r=classify(dict(pid=7,native_maps=['dss_capi.dll']),stack,lambda _:source)
    assert r['optimize_state']=='UNCONFIRMED'
