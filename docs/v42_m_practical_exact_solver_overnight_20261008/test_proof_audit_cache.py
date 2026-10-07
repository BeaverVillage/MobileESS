"""No optimize: real exact certificates, changed-input misses and scope restore."""
from practical_support import *
from proof_audit_cache import CertificateAuditCache
import unittest,types,copy

class TestCache(unittest.TestCase):
    def setUp(self):
        self.A=sparse.csc_matrix(np.array([[1.,2.],[-1.,0.]]))
        self.d=dict(objective=np.array([1.,0.]),constant=np.array(0.),rhs=np.array([.5,.25]),sense=np.array(['=','<']),lower=np.zeros(2),upper=np.ones(2))
        self.pi=np.array([.125,-.25])
        self.cache=CertificateAuditCache(hc.exact_bounded_lagrangian)
    def test_repeat_same_exact_inputs(self):
        a=self.cache.certificate_only(self.A,self.d,self.pi)[0]
        b=self.cache.certificate_only(self.A,self.d,self.pi)[0]
        self.assertEqual(a,b);self.assertEqual(self.cache.hits,1)
        a['exact_rational']='forged'
        self.assertNotEqual(self.cache.certificate_only(self.A,self.d,self.pi)[0]['exact_rational'],'forged')
    def test_every_math_input_changes_key_and_recomputes(self):
        original=self.cache.key(self.A,self.d,self.pi)
        mutations=[]
        for field in ['objective','constant','rhs','lower','upper']:
            d=copy.deepcopy(self.d);v=d[field].reshape(-1);v[0]=np.nextafter(v[0],np.inf)
            mutations.append((self.A,d,self.pi))
        d=copy.deepcopy(self.d);d['sense'][0]='<';mutations.append((self.A,d,self.pi))
        A=self.A.copy();A.data[0]=np.nextafter(A.data[0],np.inf);mutations.append((A,self.d,self.pi))
        pi=self.pi.copy();pi[0]=np.nextafter(pi[0],np.inf);mutations.append((self.A,self.d,pi))
        for A,d,pi in mutations:
            self.assertNotEqual(self.cache.key(A,d,pi),original)
            cached=self.cache.certificate_only(A,d,pi)[0]
            actual=hc.exact_bounded_lagrangian(A,d,pi)[0]
            self.assertEqual(cached['exact_rational'],actual['exact_rational'])
        self.assertEqual(self.cache.misses,len(mutations))
    def test_scope_restores_on_error_and_new_process_state_empty(self):
        m=types.SimpleNamespace(exact_bounded_lagrangian=hc.exact_bounded_lagrangian)
        with self.assertRaises(RuntimeError):
            with self.cache.audit_scope(m):
                m.exact_bounded_lagrangian(self.A,self.d,self.pi)
                raise RuntimeError('simulated audit interruption')
        self.assertIs(m.exact_bounded_lagrangian,hc.exact_bounded_lagrangian)
        fresh=CertificateAuditCache(hc.exact_bounded_lagrangian)
        fresh.certificate_only(self.A,self.d,self.pi)
        self.assertEqual(fresh.misses,1);self.assertEqual(fresh.hits,0)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TestCache)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    atomic(OUT/'PROOF_AUDIT_CACHE_TESTS.json',dict(PASS=result.wasSuccessful(),tests=result.testsRun,optimize_calls=0,immutable_scientific_arrays_changed=False))
    if not result.wasSuccessful():raise SystemExit(1)
