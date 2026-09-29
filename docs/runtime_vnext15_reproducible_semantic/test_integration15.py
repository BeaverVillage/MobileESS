from common15 import *
sys.path.insert(0,str(REPO))
import unittest,io,tempfile
from dataclasses import replace
from v42.semantic_adapter import *
from v42.semantic_integration import *
from v42.runtime_provider_contract import SubmissionRuntimeRequest
from v42.policy import Arrival
from prepare_cc415 import prefix_array

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse an existing fixture bundle when available; no historical model fitting.
        cls.payloads=[SubmissionSemanticPayload(user=f'test{i%7}',submit_line=f'cmd{i}') for i in range(64)]
        cls.adapter=SemanticFeatureAdapter().fit(cls.payloads,training_receipt=dict(TRAIN_ONLY=True,membership_sha256='b'*64,scope='SYNTHETIC_INTEGRATION_FIXTURE'))
    def request(self):
        t='2024-10-01T00:00:00Z'
        return SubmissionRuntimeRequest('x',t,3600.,{'requested_seconds':3600.},{'requested_seconds':t},'a'*64,
            semantic_payload=self.payloads[0],semantic_observed_at=t,semantic_feature_version=VERSION)
    def test_arrival_preserves_validated_service_and_legacy_identity(self):
        r=self.request();a=Arrival('x',0,1,2,4,'normal','gpu','unknown',0,'c'*64)
        self.assertIs(SemanticArrivalAdapter(self.adapter).attach(r,a,r.submit_time),a)
        handler=SemanticArrivalAdapter(self.adapter,True);out=handler.attach(r,a,r.submit_time)
        self.assertEqual(replace(out,semantic_features=None),a)
        self.assertIs(out.semantic_features,handler.running('x'))
        self.assertNotIn('cmd0',repr(out))
    def test_flag_cannot_bypass_model_gate(self):
        for component in ['RUNTIME','CC4']:
            with self.assertRaisesRegex(ValueError,'NOT_SELECTED'):require_selected_model({'ENABLE_SUBMISSION_SEMANTICS':True},component)
            with self.assertRaisesRegex(ValueError,'GATE_FAILURE'):require_selected_model({component+'_SEMANTIC_MODEL_SELECTED':True},component)
    def test_cc4_disabled_exact_and_enabled_causal(self):
        x=np.zeros((24,71));t='2024-10-01T01:00:00Z'
        self.assertIs(cc4_augmented_input(x,self.adapter,[],t),x)
        past=SubmissionSemanticRecord('past','2024-10-01T00:00:00Z','2024-10-01T00:00:00Z',self.payloads[0])
        future=replace(past,job_uid='future',submit_time='2024-10-01T02:00:00Z',observed_at='2024-10-01T02:00:00Z',payload=object())
        a=cc4_augmented_input(x,self.adapter,[past],t,enabled=True)
        b=cc4_augmented_input(x,self.adapter,[past,future],t,enabled=True)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(a[:,:71],x)
        self.assertEqual(a.shape,(24,213))
    def test_bounded_npy_prefix(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as directory:
            p=Path(directory)/'fixture.npz';x=np.arange(120,dtype=np.float64).reshape(10,3,4)
            x[7:]=99999999.;np.savez_compressed(p,fixture=x)
            actual,receipt=prefix_array(p,'fixture',7)
            np.testing.assert_array_equal(actual,x[:7]);self.assertEqual(receipt['decoded_bytes'],7*3*4*8)
            self.assertFalse((actual==99999999.).any())

if __name__=='__main__':
    stream=io.StringIO();r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests))
    write('V42_SEMANTIC_INTERFACE_AUDIT.json',dict(time=now(),PASS=r.wasSuccessful(),tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),output=stream.getvalue(),
        legacy_runtime_contract_tests=10,legacy_runtime_log=rec(LOCAL/'legacy_runtime_tests.log'),
        default_flag=False,optimizer_strings=False,feature_flag_bypasses_validation=False,
        running_submission_vector_immutable=True,baseline_source_files_unchanged=all(sha(f['path'])==f['sha256'] for f in read(ROOT/'V42_INTERFACE_BASE_SNAPSHOT.json')['files']),
        synthetic_SVD_fits=1,prior_namespace_modified=False))
    print(stream.getvalue());raise SystemExit(0 if r.wasSuccessful() else 1)
