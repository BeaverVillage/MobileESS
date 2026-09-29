import unittest,tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from bridge16 import RichCategoryAdapter
from semantic_payload_v2_candidate import SubmissionSemanticPayloadV2
from v42.semantic_adapter import SemanticFeatureAdapter

class BridgeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.frame=pd.DataFrame({'user':['user-a','user-b','user-a'],'submit_line':['cmd-a','cmd-b','cmd-a']})
        self.adapter=RichCategoryAdapter().fit(self.frame)
        self.receipt=dict(submit_time='2025-01-01T00:00:00Z',observed_time='2025-01-01T00:00:00Z',
            namespace='kestrel-job-anon-v1',metadata={'user':'user-a','submit_line':'cmd-a'})

    def test_saved_event_interface_parity(self):
        with tempfile.TemporaryDirectory(prefix='v16_adapter_test_') as directory:
            path=Path(directory)/'adapter.json';self.adapter.save(path);loaded=RichCategoryAdapter.load(path)
            np.testing.assert_array_equal(loaded.record(self.receipt,self.receipt['submit_time']),self.adapter.transform(self.frame.iloc[:1]))

    def test_outcome_and_namespace_rejection(self):
        for key in ['runtime','end_time','start_time','queue_wait','avg_power_per_node']:
            bad=dict(self.receipt,metadata=dict(self.receipt['metadata'],**{key:1}))
            with self.assertRaises(ValueError):self.adapter.record(bad,self.receipt['submit_time'])
        with self.assertRaises(ValueError):self.adapter.record(dict(self.receipt,namespace='invented_namespace'),self.receipt['submit_time'])

    def test_receipt_time_order(self):
        for t in ['2025-01-01T00:00:01Z']:
            with self.assertRaises(ValueError):self.adapter.record(dict(self.receipt,observed_time=t),self.receipt['submit_time'])
        with self.assertRaises(ValueError):self.adapter.record(self.receipt,'2024-12-31T23:59:59Z')

    def test_minimal_partial_full_and_legacy(self):
        for args,level in [({},'MINIMAL'),({'user':'u'},'PARTIAL'),({'user':'u','submit_line':'c'},'FULL')]:
            p=SubmissionSemanticPayloadV2(**args);self.assertEqual(p.support_level,level)
            self.assertEqual(SemanticFeatureAdapter().canonical(p),SemanticFeatureAdapter().canonical(p.as_legacy()))
            self.assertNotIn('user=',repr(p))
        np.testing.assert_array_equal(self.adapter.record(dict(self.receipt,metadata={}),self.receipt['submit_time']),[[-1,-1]])
        for field in ['account','script','modules','conda_envs','workdir']:
            with self.assertRaises(ValueError):SubmissionSemanticPayloadV2.from_mapping({field:'unauthorized'})

    def test_unseen(self):
        d=pd.DataFrame({'user':['unseen'],'submit_line':['unseen']})
        np.testing.assert_array_equal(self.adapter.transform(d),[[-1,-1]])

if __name__=='__main__':unittest.main(verbosity=2)
