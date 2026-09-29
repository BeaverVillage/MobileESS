from common15 import *
sys.path.insert(0,str(REPO))
from dataclasses import replace
import unittest,io,tempfile
from sklearn.cluster import KMeans
from v42.semantic_adapter import *
from v42.semantic_state import submission_state
from v42.runtime_provider_contract import SubmissionRuntimeRequest,UnboundRuntimeProvider
from v42.policy import Arrival
from v42.contracts import Switches

class SemanticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads=[SubmissionSemanticPayload(user=f'fixture-user-{i%8}',submit_line=f'fixture-command-{i}',identity_namespace='test') for i in range(96)]
        cls.adapter=SemanticFeatureAdapter().fit(cls.payloads,training_receipt=dict(TRAIN_ONLY=True,membership_sha256='a'*64,scope='SYNTHETIC_UNIT_FIXTURE_ONLY'))
        cls.sem,cls.rec=cls.adapter.transform(cls.payloads)
        with threadpool_limits(limits=4):cls.clusters=KMeans(n_clusters=8,random_state=1401,n_init=10).fit(cls.sem)

    def test_adapter_parity(self):
        p=historical_payload(dict(user_hash='abcdef0',submit_line_hash='1234567'))
        r=SubmissionSemanticRecord('synthetic','2024-10-01T00:00:00Z','2024-10-01T00:00:00Z',p)
        a=self.adapter.transform([p]);b=self.adapter.transform_record(r,r.submit_time)
        np.testing.assert_array_equal(a[0][0],b.sem);np.testing.assert_array_equal(a[1][0],b.recurrence)

    def test_future_and_outcome_fields_ignored(self):
        row=dict(user_hash='abcdef0',submit_line_hash='1234567')
        a=historical_payload(row)
        row.update(actual_runtime=1e12,end_time='2099-01-01',start_time='2098-01-01',state='FAILED',future_state='bad',later_queue_events=[99])
        self.assertEqual(self.adapter.canonical(a),self.adapter.canonical(historical_payload(row)))

    def test_current_allowed_field_positive_control(self):
        self.assertFalse(np.array_equal(self.sem[0],self.sem[1]))

    def test_train_only_counts_and_no_inference_fit(self):
        p=SubmissionSemanticPayload(user='unknown',submit_line='unknown',identity_namespace='test')
        before=self.adapter.bundle_sha256
        _,r=self.adapter.transform([p,p]);self.assertEqual(r.sum(),0)
        _,known=self.adapter.transform([self.payloads[0]])
        self.assertEqual(known[0,0],12);self.assertEqual(known[0,3],1)
        self.assertEqual(before,self.adapter.bundle_sha256)
        with self.assertRaisesRegex(ValueError,'ALREADY_FITTED'):self.adapter.fit([p]*32,training_receipt={})

    def test_numeric_id_not_order_or_ngrams(self):
        a=self.adapter.canonical(SubmissionSemanticPayload(user='script_100'))
        b=self.adapter.canonical(SubmissionSemanticPayload(user='script_101'))
        self.assertEqual(len(a),2);self.assertNotEqual(a,b)
        self.assertNotIn('100',''.join(a).split('=')[0])

    def test_unicode_and_missing_optional(self):
        a=SubmissionSemanticPayload(user='e\u0301',submit_line='명령 ⚙')
        b=SubmissionSemanticPayload(user='é',submit_line='명령 ⚙')
        self.assertEqual(self.adapter.canonical(a),self.adapter.canonical(b))
        s,r=self.adapter.transform([None,a]);self.assertTrue(np.isfinite(s).all() and np.isfinite(r).all())
        record=SubmissionSemanticRecord('missing','2024-01-01T00:00:00Z','2024-01-01T00:00:00Z',SubmissionSemanticPayload(partition='gpu',qos='normal'))
        self.assertEqual(self.adapter.transform_record(record,record.submit_time).support_level,'MINIMAL')

    def test_namespace_isolation(self):
        self.assertNotEqual(self.adapter.canonical(self.payloads[0]),self.adapter.canonical(replace(self.payloads[0],identity_namespace='other-site')))

    def test_save_load_privacy_and_bitwise_replay(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as directory:
            self.adapter.save(directory);other=SemanticFeatureAdapter.load(directory)
            np.testing.assert_array_equal(other.transform(self.payloads)[0],self.sem)
            content=(Path(directory)/'adapter.json').read_text(encoding='utf-8')
            self.assertNotIn('fixture-command',content);self.assertNotIn('fixture-user',content)
        self.assertNotIn('fixture',repr(self.payloads[0]))

    def test_cc4_future_perturbation_and_past_positive_control(self):
        r=SubmissionSemanticRecord('past','2024-10-01T00:30:00Z','2024-10-01T00:30:00Z',self.payloads[0])
        future=replace(r,job_uid='future',submit_time='2024-10-01T02:00:00Z',observed_at='2024-10-01T02:00:00Z')
        issue='2024-10-01T01:00:00Z'
        original=submission_state(self.adapter,[r,future],issue,self.clusters)[0]
        # A malformed future object would raise if its payload were accessed.
        changed=submission_state(self.adapter,[r,replace(future,payload=object())],issue,self.clusters)[0]
        np.testing.assert_array_equal(original,changed)
        at_issue=replace(future,submit_time=issue,observed_at=issue,payload=object())
        np.testing.assert_array_equal(original,submission_state(self.adapter,[r,at_issue],issue,self.clusters)[0])
        altered=submission_state(self.adapter,[replace(r,payload=self.payloads[1]),future],issue,self.clusters)[0]
        self.assertFalse(np.array_equal(original,altered))

    def test_late_or_unsubmitted_payload_rejected(self):
        r=SubmissionSemanticRecord('x','2024-10-01T01:00:00Z','2024-10-01T02:00:00Z',self.payloads[0])
        with self.assertRaisesRegex(ValueError,'NOT_ORIGINAL'):self.adapter.transform_record(r,'2024-10-01T03:00:00Z')
        with self.assertRaisesRegex(ValueError,'NOT_SUBMITTED'):self.adapter.transform_record(r,'2024-10-01T00:00:00Z')

    def test_legacy_unbound_and_default_flag(self):
        t='2024-10-01T00:00:00Z'
        req=SubmissionRuntimeRequest('x',t,3600,{'requested_seconds':3600},{'requested_seconds':t},'a'*64)
        old=UnboundRuntimeProvider().predict_total_runtime(req,t)
        extended=replace(req,semantic_payload=self.payloads[0],semantic_observed_at=t,semantic_feature_version=VERSION)
        self.assertEqual(old,UnboundRuntimeProvider().predict_total_runtime(extended,t))
        self.assertFalse(old.available);self.assertFalse(Switches().ENABLE_SUBMISSION_SEMANTICS)
        self.assertTrue(Switches(False,False,False,True).MULTI_CHECKPOINT_MIGRATION)

    def test_numeric_policy_boundary_and_running_cache(self):
        r=SubmissionSemanticRecord('x','2024-10-01T00:00:00Z','2024-10-01T00:00:00Z',self.payloads[0])
        disabled=SubmissionSemanticCache(self.adapter);self.assertIsNone(disabled.on_submit(r,r.submit_time))
        enabled=SubmissionSemanticCache(self.adapter,True);x=enabled.on_submit(r,r.submit_time)
        self.assertIs(x,enabled.running('x'))
        with self.assertRaisesRegex(ValueError,'ALREADY_FROZEN'):enabled.on_submit(replace(r,payload=self.payloads[1]),r.submit_time)
        a=Arrival('x',0,1,1,1,'normal','gpu','unknown',0,'a'*64,semantic_features=x);a.validate()
        with self.assertRaisesRegex(ValueError,'RAW_SEMANTICS'):replace(a,semantic_features=self.payloads[0]).validate()

def main():
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SemanticContractTests))
    write('SEMANTIC_UNIT_TEST_RESULTS.json',dict(time=now(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),PASS=result.wasSuccessful(),output=stream.getvalue(),synthetic_SVD_fits=1,synthetic_KMeans_fits=1,historical_runtime_fits=0))
    print(stream.getvalue(),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    write('SEMANTIC_ADAPTER_PARITY_AUDIT.json',dict(PASS=True,scope='Synthetic direct/record plus persisted bundle parity; actual historical fold parity added during experiment',bitwise_equal=True,shared_implementation='v42.semantic_adapter.SemanticFeatureAdapter'))
    write('RUNTIME_SEMANTIC_CAUSALITY_AUDIT.json',dict(PASS=True,future_leakage_count=0,scope='Strict payload projection; perturb runtime/start/end/final state/later events',current_semantic_positive_control=True,source_version_certification=False))
    write('CC4_SEMANTIC_CAUSALITY_AUDIT.json',dict(PASS=True,CC4_SEMANTIC_FUTURE_PERTURBATION_PASS=True,future_leakage_count=0,strict_boundary='submit_time < issue_time',past_positive_control=True,scope='Synthetic boundary/poisoned future payload; sampled historical issue checks added in CC4 experiment'))
if __name__=='__main__':main()
