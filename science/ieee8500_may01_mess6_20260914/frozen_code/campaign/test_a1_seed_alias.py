import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
import bootstrap as b
import a1_seed_alias_binding as fix
class SeedAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=b.read(b.H/'FINAL_B1_REUSE.json')['seed_bundle']
        with b.np.load(b.H/'B1_REUSE/variable_names.npz',allow_pickle=False) as z:cls.names=z['names'].tolist()
        with b.np.load(b.H/'B1_REUSE/assignment.npz',allow_pickle=False) as z:cls.values=z['values'].copy()
    def context(self):return SimpleNamespace(new_production_root=b.H,ieee8500_final_B1_seed=copy.deepcopy(self.bundle))
    def model(self,names=None):
        return SimpleNamespace(NumVars=len(self.values),getVars=lambda:[],getAttr=lambda *args:self.names if names is None else names)
    def test_original_rejects_alias_then_fixed_gate_preserves_exact_values(self):
        ctx=self.context()
        with self.assertRaises(AssertionError):fix.ORIGINAL(self.model(),ctx)
        actual=fix.validated_B1_assignment(self.model(),ctx)
        self.assertTrue(b.np.array_equal(actual,self.values))
        self.assertEqual(ctx.ieee8500_final_B1_seed,self.bundle)
        self.assertTrue(b.Path(ctx.v41_a1_seed_checkpoint['path']).is_relative_to(b.H))
    def test_bad_sha_rejected(self):
        value=copy.deepcopy(self.bundle);value['assignment']['sha256']='0'*64
        with self.assertRaises(AssertionError):fix.normalize(value,b.H)
    def test_different_file_rejected(self):
        with patch.object(fix.os.path,'samefile',return_value=False):
            with self.assertRaises(AssertionError):fix.normalize(self.bundle,b.H)
    def test_original_variable_order_gate_remains(self):
        with self.assertRaises(AssertionError):fix.validated_B1_assignment(self.model(['wrong']),self.context())
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SeedAliasTests))
    folder=b.H/'a1_alias_recovery_20260914';folder.mkdir(exist_ok=True)
    b.save(folder/'PREFLIGHT.json',dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,optimization_calls=0,assignment_values_unchanged=True,original_sha_and_variable_order_checks_retained=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
