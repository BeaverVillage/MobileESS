from practical_support import *
from injection_dual_repair import repair_binding_duals
import unittest
from fractions import Fraction

class TestRepair(unittest.TestCase):
    def test_unrestricted_binding_and_exact_bound(self):
        A=sparse.csc_matrix([[-1.,1.]])
        d=dict(names=np.array(['rho_max','injection_P[x]']),row_names=np.array(['injection_P_binding']),sense=np.array(['=']),objective=np.array([1.,0.]),constant=np.array(0.),rhs=np.array([0.]),lower=np.zeros(2),upper=np.array([1.,100.]))
        pi=np.array([.001]);old,clipped,residual,_=hc.exact_bounded_lagrangian(A,d,pi)
        new_pi,changes=repair_binding_duals(A,d,clipped,residual)
        new=hc.exact_bounded_lagrangian(A,d,new_pi)[0]
        self.assertEqual(len(changes),1)
        self.assertGreater(Fraction(new['exact_rational']),Fraction(old['exact_rational']))
        self.assertEqual(Fraction(new['exact_rational']),0)
        self.assertEqual(d['objective'].tolist(),[1.,0.])
        d['sense'][0]='<'
        untouched,changes=repair_binding_duals(A,d,pi,residual)
        self.assertEqual(changes,[]);self.assertTrue(np.array_equal(pi,untouched))
    def test_coupled_injection_row_is_omitted(self):
        A=sparse.csc_matrix([[1.,-1.]])
        d=dict(names=np.array(['injection_P[x]','injection_P[y]']),row_names=np.array(['injection_P_binding']),sense=np.array(['=']))
        pi=np.array([.25]);new,changes=repair_binding_duals(A,d,pi,np.array([.1,.2]))
        self.assertEqual(changes,[]);self.assertTrue(np.array_equal(new,pi))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestRepair))
    atomic(OUT/'INJECTION_DUAL_REPAIR_TESTS.json',dict(PASS=result.wasSuccessful(),tests=result.testsRun,optimize_calls=0))
    if not result.wasSuccessful():raise SystemExit(1)
