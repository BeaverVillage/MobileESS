"""Protocol regressions: repeat violations cannot slip into the valid UB set."""
import unittest
import numpy as np
import gurobipy as gp
from scipy import sparse
from v42_one_tree_bc.core import OneTree,Separator
from v42_rowgen.core import separate

class NativeReceiver:
    def __init__(self,x):self.x=x;self.lazy=[];self.stopped=False
    def cbGetSolution(self,vars):return self.x
    def cbGet(self,code):return 0.
    def cbLazy(self,expr,sense,rhs):self.lazy.append((expr,sense,rhs))
    def terminate(self):self.stopped=True

class TestProtocol(unittest.TestCase):
    def data(self):
        A=sparse.csr_matrix([[1.],[-1.]])
        d=dict(row_names=np.array(['voltage_upper[0]','voltage_lower[0]']),
            sense=np.array(['<','<']),rhs=np.array([1.,0.]),types=np.array(['C']))
        return A,d
    def test_all_grid_scan_rejects_already_registered_violation(self):
        A,d=self.data();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
        m=gp.Model(env=env);v=m.addVar();m.update()
        cb=OneTree(A,d,[v],lambda x:dict(PASS=True,objective=float(x[0])))
        cb.registered[0]=2
        model=NativeReceiver(np.array([2.]))
        cb(model,gp.GRB.Callback.MIPSOL)
        self.assertEqual(len(model.lazy),1)
        self.assertEqual(cb.counts['lazy_resubmissions'],1)
        self.assertEqual(len(cb.registry),0)
        self.assertEqual(len(cb.valid),0)
        self.assertEqual(cb.ledger[0]['checked_rows'],2)
        self.assertFalse(model.stopped)
        m.dispose();env.dispose()
    def test_failed_nongrid_audit_never_records_UB(self):
        A,d=self.data();cb=OneTree(A,d,[],lambda x:dict(PASS=False,objective=.5))
        model=NativeReceiver(np.array([.5]));cb(model,gp.GRB.Callback.MIPSOL)
        self.assertTrue(model.stopped);self.assertEqual(len(cb.valid),0)
        self.assertEqual(cb.error['reason'],'GRID_FEASIBLE_CANDIDATE_FAILED_FULL_ORIGINAL_AUDIT')
    def test_cache_matches_PR158_with_cancellation_and_all_senses(self):
        rng=np.random.default_rng(20260929)
        A=sparse.csr_matrix(rng.normal(size=(24,7)))
        d=dict(rhs=rng.normal(size=24),sense=np.tile(['<','>','='],8),
            row_names=np.array(['line_thermal_face']*24))
        s=Separator(A,d)
        for scale in (1e-10,1.,1e9):
            x=rng.normal(size=7)*scale
            self.assertEqual(list(s.evaluate(x)['violated']),list(separate(A,d,x)['violated']))
    def test_nonfinite_point_fails_closed(self):
        A,d=self.data()
        with self.assertRaises(ValueError):Separator(A,d).evaluate(np.array([np.nan]))
    def test_strict_unapproved_repeat_fails_closed(self):
        A,d=self.data();cb=OneTree(A,d,[],lambda x:dict(PASS=True,objective=0.),allow_lazy_resubmission=False)
        cb.registered[0]=2;model=NativeReceiver(np.array([2.]))
        cb.submit(model,0,'MIPSOL',0,1.)
        self.assertTrue(model.stopped);self.assertEqual(len(model.lazy),0)
        self.assertEqual(cb.error['reason'],'PREVIOUSLY_SUBMITTED_ROW_VIOLATED')

if __name__=='__main__':unittest.main()
